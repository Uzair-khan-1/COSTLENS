"""
Drawing-package analyser - reads a full 5-10 marla drawing set WITHOUT AI.

Most Pakistani residential drawings are CAD exports (AutoCAD/Revit ->
PDF). Those PDFs contain exact information that costs zero AI tokens to
read:

  * the TEXT layer - sheet titles ("GROUND FLOOR PLAN", "SECTION A-A"),
    room labels with sizes ("BED ROOM 12'-0" x 14'-0""), level marks on
    sections ("+1'-6"", "+11'-6""), footing/column schedules, plot size,
    covered-area statements and the drawing scale;
  * the VECTOR geometry - walls are drawn as pairs of parallel lines a wall
    thickness apart, door swings as quarter arcs. With the scale known,
    wall lengths, the building footprint and door counts can be MEASURED.

This module:
  1. sorts every page into views (plan per floor, section, elevation,
     structural, site, MEP, schedule) - a page may hold several views;
  2. extracts facts per view from text and geometry;
  3. cross-checks the sheets against each other;
  4. merges the facts into ExtractedBuildingParams with provenance notes
     (apply_package_facts), and picks which pages are worth sending to the
     AI for whatever is still missing (pages_for_ai).

Scanned drawings / photos have no text layer or vectors; they simply yield
no facts here and are left to the AI + plot template. Everything is
heuristic: values carry confidence levels and sources, and Step 3 shows
them for the user to confirm.
"""
from __future__ import annotations

import bisect
import math
import re
import statistics
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import pymupdf

from models.schemas import ConfidenceLevel, Estimate, ExtractedBuildingParams, ProjectInputs, Source
from utils import units

FT = 0.3048
IN = 0.0254
SQFT = FT * FT
MAX_PACKAGE_PAGES = 20

FLOOR_ORDER = ["basement", "ground", "first", "second", "third"]
FLOOR_NAMES = {
    "basement": "Basement", "ground": "Ground floor", "first": "First floor",
    "second": "Second floor", "third": "Third floor", "roof": "Roof / mumty",
}

# --------------------------------------------------------------------------
# Text helpers
# --------------------------------------------------------------------------
_QUOTES = str.maketrans({"’": "'", "′": "'", "‘": "'", "`": "'", "”": '"', "″": '"', "“": '"', "×": "x", "–": "-", "—": "-"})
_FTIN = r"(\d{1,3})\s*'\s*-?\s*(?:(\d{1,2}(?:\.\d+)?)(?:\s+(\d)/(\d{1,2}))?\s*\"?)?"
_DIMS_RE = re.compile(_FTIN + r"\s*[xX]\s*" + _FTIN)
_LEVEL_RE = re.compile(r"(?<![\w'])([+\-±])\s*" + _FTIN)
_INCH_DIMS_RE = re.compile(r"(\d{1,2}(?:\.\d+)?)\s*\"\s*[xX]\s*(\d{1,2}(?:\.\d+)?)\s*\"")


def normalize_text(text: str) -> str:
    return (text or "").translate(_QUOTES)


def _ftin_value(g: Tuple) -> float:
    feet, inches, num, den = g
    value = float(feet)
    if inches:
        value += float(inches) / 12.0
    if num and den and float(den) > 0:
        value += float(num) / float(den) / 12.0
    return value


def parse_ftin(text: str) -> Optional[float]:
    """"12'-6"" -> 12.5 ; "12'" -> 12.0 ; "9\"" -> 0.75 ; None if no match."""
    t = normalize_text(text)
    m = re.search(_FTIN, t)
    if m:
        return _ftin_value(m.groups())
    m = re.search(r"(\d{1,2}(?:\.\d+)?)\s*\"", t)
    return float(m.group(1)) / 12.0 if m else None


def parse_room_dims(text: str) -> Optional[Tuple[float, float]]:
    m = _DIMS_RE.search(normalize_text(text))
    if not m:
        return None
    g = m.groups()
    return _ftin_value(g[:4]), _ftin_value(g[4:])


ROOM_KINDS = [
    ("bathroom", r"\b(BATH|TOILET|W\.?\s?C\b|WASH\s?ROOM|POWDER|LAV)"),
    ("kitchen", r"\bKITCHEN"),
    ("bedroom", r"\b(BED|MASTER|GUEST\s?ROOM)"),
    ("living", r"\b(DRAWING|DINING|LOUNGE|LIVING|T\.?V\.?|FAMILY|SITTING)"),
    ("stair", r"\bSTAIR"),
    ("store", r"\b(STORE|LAUNDRY|DRESS)"),
    ("open", r"\b(CAR\s?PORCH|PORCH|LAWN|TERRACE|BALCONY|VERANDAH|OPEN|COURT|PARKING|GARAGE)"),
]


def room_kind(name: str) -> str:
    up = name.upper()
    for kind, pattern in ROOM_KINDS:
        if re.search(pattern, up):
            return kind
    return "room"


# --------------------------------------------------------------------------
# Sheet / view classification
# --------------------------------------------------------------------------
_FLOOR_WORDS = [
    ("basement", r"BASEMENT"), ("ground", r"GROUND"), ("first", r"FIRST|1ST"),
    ("second", r"SECOND|2ND"), ("third", r"THIRD|3RD"), ("roof", r"ROOF|MUMTY|TOP"),
]
_VIEW_PATTERNS = [
    ("structural", r"FOUNDATION\s*(PLAN|LAYOUT|DETAIL)|FOOTING\s*(SCHEDULE|LAYOUT|PLAN|DETAIL)|COLUMN\s*(LAYOUT|SCHEDULE|PLAN)|BEAM\s*(LAYOUT|SCHEDULE|PLAN)|STRUCTURAL"),
    ("mep", r"ELECTRIC|PLUMBING|SEWER|DRAINAGE|WATER\s*SUPPLY|GAS\s*LAYOUT"),
    ("site", r"SITE\s*PLAN|LOCATION\s*PLAN|KEY\s*PLAN"),
    ("schedule", r"(DOOR|WINDOW).{0,6}SCHEDULE"),
    ("section", r"\bSECTION\b|\bSEC\.\s*[A-Z]"),
    ("elevation", r"\bELEVATION\b"),
    ("plan", r"\b(BASEMENT|GROUND|FIRST|SECOND|THIRD|1ST|2ND|3RD|ROOF|MUMTY|TOP)\s*(FLOOR\s*)?PLAN\b"),
]


@dataclass
class TextLine:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2


@dataclass
class View:
    kind: str  # plan | section | elevation | structural | site | mep | schedule | unknown
    floor: Optional[str]
    title: str
    cx: float
    cy: float


def classify_title(line: str) -> Optional[Tuple[str, Optional[str]]]:
    """(kind, floor) if the line reads like a sheet/view title."""
    up = normalize_text(line).upper().strip()
    if not up or len(up.split()) > 8:
        return None  # long lines are notes, not titles
    for kind, pattern in _VIEW_PATTERNS:
        if re.search(pattern, up):
            floor = None
            if kind == "plan":
                for f, fp in _FLOOR_WORDS:
                    if re.search(r"\b(" + fp + r")\b", up):
                        floor = f
                        break
            return kind, floor
    return None


def _text_lines(page: "pymupdf.Page") -> List[TextLine]:
    words = page.get_text("words")
    grouped: Dict[Tuple[int, int], List] = {}
    for w in words:
        grouped.setdefault((w[5], w[6]), []).append(w)
    lines = []
    for ws in grouped.values():
        ws.sort(key=lambda w: w[0])
        # split a PDF "line" where words are far apart - CAD exports often
        # merge separate labels at the same height (e.g. "BATH   TOILET")
        chunks, cur = [], [ws[0]]
        for w in ws[1:]:
            height = max(cur[-1][3] - cur[-1][1], 1.0)
            if w[0] - cur[-1][2] > 1.5 * height:
                chunks.append(cur)
                cur = [w]
            else:
                cur.append(w)
        chunks.append(cur)
        for ch in chunks:
            text = normalize_text(" ".join(w[4] for w in ch))
            lines.append(TextLine(text, min(w[0] for w in ch), min(w[1] for w in ch), max(w[2] for w in ch), max(w[3] for w in ch)))
    return lines


def _nearest_view(views: List[View], x: float, y: float, kinds: Optional[set] = None) -> Optional[View]:
    cands = [v for v in views if kinds is None or v.kind in kinds]
    if not cands:
        return None
    return min(cands, key=lambda v: (v.cx - x) ** 2 + (v.cy - y) ** 2)


# --------------------------------------------------------------------------
# Scale
# --------------------------------------------------------------------------
_SCALE_IMPERIAL = re.compile(r"SCALE\s*[:=-]?\s*(\d+)\s*/\s*(\d+)\s*\"?\s*=\s*1\s*'")
_SCALE_IMPERIAL_WHOLE = re.compile(r"SCALE\s*[:=-]?\s*(\d+)\s*\"\s*=\s*1\s*'")
_SCALE_RATIO = re.compile(r"SCALE\s*[:=-]?\s*1\s*:\s*(\d+)")
CANDIDATE_SCALES_FT_PER_PT = {
    '1/8"=1\'-0"': 8 / 72, '3/16"=1\'-0"': (16 / 3) / 72, '1/4"=1\'-0"': 4 / 72, '1/16"=1\'-0"': 16 / 72,
    "1:100": 100 / 72 / 12, "1:50": 50 / 72 / 12, "1:200": 200 / 72 / 12,
}


def parse_scale(text: str) -> Optional[Tuple[str, float]]:
    """(label, real feet per PDF point) from a scale note."""
    up = normalize_text(text).upper()
    m = _SCALE_IMPERIAL.search(up)
    if m and int(m.group(1)) > 0:
        paper_in_per_ft = int(m.group(1)) / int(m.group(2))
        return f'{m.group(1)}/{m.group(2)}"=1\'-0"', 1 / (paper_in_per_ft * 72)
    m = _SCALE_IMPERIAL_WHOLE.search(up)
    if m and int(m.group(1)) > 0:
        return f'{m.group(1)}"=1\'-0"', 1 / (int(m.group(1)) * 72)
    m = _SCALE_RATIO.search(up)
    if m:
        n = int(m.group(1))
        return f"1:{n}", n / 72 / 12
    return None


# --------------------------------------------------------------------------
# Geometry: wall pairs, footprint, door swings
# --------------------------------------------------------------------------


def _segments(page: "pymupdf.Page") -> Tuple[list, list, list]:
    """Axis-aligned horizontal (y, x0, x1) and vertical (x, y0, y1)
    segments in PDF points, plus curve bounding boxes (door swings)."""
    H, V, curves = set(), set(), []

    def add(p, q):
        dx, dy = q.x - p.x, q.y - p.y
        length = math.hypot(dx, dy)
        if length < 1e-6:
            return
        if abs(dy) <= 0.02 * length:
            H.add((round((p.y + q.y) / 2, 1), round(min(p.x, q.x), 1), round(max(p.x, q.x), 1)))
        elif abs(dx) <= 0.02 * length:
            V.add((round((p.x + q.x) / 2, 1), round(min(p.y, q.y), 1), round(max(p.y, q.y), 1)))

    for path in page.get_drawings():
        curve_pts = []
        for item in path["items"]:
            op = item[0]
            if op == "l":
                add(item[1], item[2])
            elif op == "re":
                r = item[1]
                add(r.tl, r.tr), add(r.bl, r.br), add(r.tl, r.bl), add(r.tr, r.br)
            elif op == "qu":
                q = item[1]
                add(q.ul, q.ur), add(q.ll, q.lr), add(q.ul, q.ll), add(q.ur, q.lr)
            elif op == "c":
                curve_pts.extend([item[1], item[4]])
        if curve_pts:
            xs, ys = [p.x for p in curve_pts], [p.y for p in curve_pts]
            curves.append((min(xs), min(ys), max(xs), max(ys)))
    return sorted(H), sorted(V), curves


def _pair_walls(segs: list, ft_per_pt: float) -> List[Tuple[float, float, float, float, float]]:
    """Pairs parallel segments a wall-thickness apart (3"-9.75" real).
    Returns wall spans (position_mid, start, end, thickness_ft, outer_lo, outer_hi)
    after merging collinear pieces across openings (gaps <= 8 ft)."""
    if not segs:
        return []
    t_min, t_max = (3.0 / 12) / ft_per_pt, (9.75 / 12) / ft_per_pt
    min_overlap = 0.75 / ft_per_pt
    positions = [s[0] for s in segs]
    raw = []
    for i, (pos, a0, a1) in enumerate(segs):
        j = bisect.bisect_right(positions, pos + t_min)
        best = None
        while j < len(segs) and positions[j] <= pos + t_max:
            q, b0, b1 = segs[j]
            ov = min(a1, b1) - max(a0, b0)
            if ov >= min_overlap and (best is None or q < best[0]):
                best = (q, max(a0, b0), min(a1, b1))
            j += 1
        if best:
            raw.append(((pos + best[0]) / 2, best[1], best[2], (best[0] - pos) * ft_per_pt, pos, best[0]))
    # merge collinear pieces of the same wall across door/window gaps
    raw.sort(key=lambda r: (round(r[0] / (1.0 / 12 / ft_per_pt)), round(r[3] * 12), r[1]))
    merged = []
    gap = 8.0 / ft_per_pt
    tol = (1.0 / 12) / ft_per_pt
    for r in raw:
        if merged:
            m = merged[-1]
            if abs(m[0] - r[0]) <= tol and abs(m[3] - r[3]) <= 1.0 / 12 and r[1] <= m[2] + gap:
                merged[-1] = (m[0], m[1], max(m[2], r[2]), m[3], min(m[4], r[4]), max(m[5], r[5]))
                continue
        merged.append(r)
    return [m for m in merged if (m[2] - m[1]) * ft_per_pt >= 2.0]


@dataclass
class WallMeasurement:
    wall_length_ft: float
    width_ft: float
    depth_ft: float
    avg_thickness_in: float
    thickness_breakdown: Dict[float, float]  # thickness (in) -> length (ft)
    doors: int


def measure_plan(H: list, V: list, curves: list, ft_per_pt: float) -> Optional[WallMeasurement]:
    hw = _pair_walls(H, ft_per_pt)
    vw = _pair_walls(V, ft_per_pt)
    if len(hw) < 2 or len(vw) < 2:
        return None
    length = sum((w[2] - w[1]) * ft_per_pt for w in hw + vw)
    xs = [w[1] for w in hw] + [w[2] for w in hw] + [w[4] for w in vw] + [w[5] for w in vw]
    ys = [w[4] for w in hw] + [w[5] for w in hw] + [w[1] for w in vw] + [w[2] for w in vw]
    width = (max(xs) - min(xs)) * ft_per_pt
    depth = (max(ys) - min(ys)) * ft_per_pt
    breakdown: Dict[float, float] = {}
    for w in hw + vw:
        t_in = round(w[3] * 12 * 2) / 2  # nearest 1/2"
        breakdown[t_in] = breakdown.get(t_in, 0.0) + (w[2] - w[1]) * ft_per_pt
    avg_t = sum(t * l for t, l in breakdown.items()) / max(sum(breakdown.values()), 1e-9)
    x_lo, x_hi, y_lo, y_hi = min(xs), max(xs), min(ys), max(ys)
    doors = 0
    for (cx0, cy0, cx1, cy1) in curves:
        w_ft, h_ft = (cx1 - cx0) * ft_per_pt, (cy1 - cy0) * ft_per_pt
        inside = x_lo - 1 <= cx0 and cx1 <= x_hi + 1 and y_lo - 1 <= cy0 and cy1 <= y_hi + 1
        if inside and 2.0 <= w_ft <= 4.5 and 2.0 <= h_ft <= 4.5 and 0.75 <= w_ft / h_ft <= 1.33:
            doors += 1
    return WallMeasurement(length, width, depth, avg_t, breakdown, doors)


# --------------------------------------------------------------------------
# Result containers
# --------------------------------------------------------------------------


@dataclass
class FloorFacts:
    floor: str
    source: str
    covered_sqft: Optional[float] = None
    covered_source: str = ""
    width_ft: Optional[float] = None
    depth_ft: Optional[float] = None
    wall_length_ft: Optional[float] = None
    perimeter_ft: Optional[float] = None
    avg_wall_thickness_in: Optional[float] = None
    thickness_breakdown: Dict[float, float] = field(default_factory=dict)
    doors: Optional[int] = None
    rooms: List[Tuple[str, float, float, str]] = field(default_factory=list)
    geometry_confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM
    scale_label: str = ""

    def count(self, kind: str) -> int:
        return sum(1 for r in self.rooms if r[3] == kind)


@dataclass
class SheetSummary:
    file_name: str
    page_no: int
    views: List[str]
    findings: List[str]
    has_text: bool
    has_vectors: bool


@dataclass
class PackageFacts:
    sheets: List[SheetSummary] = field(default_factory=list)
    floors: Dict[str, FloorFacts] = field(default_factory=dict)
    section: Dict[str, Tuple[float, str]] = field(default_factory=dict)  # key -> (feet, source)
    structural: Dict[str, Tuple[float, str]] = field(default_factory=dict)
    plot: Dict[str, Tuple[float, str]] = field(default_factory=dict)
    conflicts: List[str] = field(default_factory=list)
    page_kinds: Dict[Tuple[int, int], str] = field(default_factory=dict)  # (file_idx, page_idx) -> best view kind/floor

    @property
    def storeys(self) -> int:
        return sum(1 for f in self.floors if f in FLOOR_ORDER)

    def has_facts(self) -> bool:
        return bool(self.floors or self.section or self.structural or self.plot)


# --------------------------------------------------------------------------
# Per-view fact extraction
# --------------------------------------------------------------------------


def _rooms_from_lines(lines: List[TextLine]) -> List[Tuple[str, float, float, str, float, float]]:
    rooms = []
    for i, ln in enumerate(lines):
        dims = parse_room_dims(ln.text)
        if not dims or not (3 <= dims[0] <= 40 and 3 <= dims[1] <= 40):
            continue
        name = _DIMS_RE.sub("", ln.text).strip(" :-,")
        if not re.search(r"[A-Za-z]{3,}", name):
            h = max(ln.y1 - ln.y0, 1.0)
            above = [o for o in lines if o is not ln and 0 < ln.cy - o.cy <= 3 * h and abs(o.cx - ln.cx) <= 6 * h
                     and re.search(r"[A-Za-z]{3,}", o.text) and not parse_room_dims(o.text)]
            if not above:
                continue
            name = min(above, key=lambda o: (ln.cy - o.cy) + abs(o.cx - ln.cx)).text.strip()
        if classify_title(name):
            continue
        rooms.append((name.upper(), dims[0], dims[1], room_kind(name), ln.cx, ln.cy))
    return rooms


def _section_facts(lines: List[TextLine]) -> Dict[str, float]:
    levels = []
    slab_in = None
    for ln in lines:
        for m in _LEVEL_RE.finditer(ln.text):
            v = _ftin_value(m.groups()[1:])
            levels.append(-v if m.group(1) == "-" else v)
        up = ln.text.upper()
        sm = re.search(r"(\d{1,2}(?:\.\d+)?)\s*\"\s*(?:THK\.?|THICK)?\s*(?:R\.?C\.?C\.?\s*)?SLAB", up) or re.search(
            r"SLAB\s*(?:THK\.?|THICKNESS)?\s*[:=]?\s*(\d{1,2}(?:\.\d+)?)\s*\"", up)
        if sm and 3.5 <= float(sm.group(1)) <= 9:
            slab_in = float(sm.group(1))
    out: Dict[str, float] = {}
    if slab_in:
        out["slab_thickness_ft"] = slab_in / 12
    pos = sorted({round(v, 3) for v in levels if v > 0})
    neg = [v for v in levels if v < 0]
    plinth = [v for v in pos if v <= 3.5]
    if plinth:
        out["plinth_height_ft"] = max(plinth)
    base = max(plinth) if plinth else 0.0
    upper = [base] + [v for v in pos if v > base]
    diffs = [b - a for a, b in zip(upper, upper[1:])]
    storey_diffs = [d for d in diffs if 8.0 <= d <= 14.0]
    if storey_diffs:
        out["floor_height_ft"] = statistics.median(storey_diffs)
        out["levels_storeys"] = float(len(storey_diffs))
    if diffs and 2.0 <= diffs[-1] <= 5.0 and storey_diffs:
        out["parapet_height_ft"] = diffs[-1]
    deep = [abs(v) for v in neg if 2.5 <= abs(v) <= 12]
    if deep:
        out["founding_depth_ft"] = max(deep)
    return out


def _structural_facts(lines: List[TextLine], words: List[str]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    sizes = {}
    for ln in lines:
        up = ln.text.upper()
        m = re.search(r"\b(F-?\d{1,2})\b", up)
        dims = parse_room_dims(up)
        if m and dims and 2 <= dims[0] <= 12:
            depth = None
            rest = _DIMS_RE.sub("", up, count=1)
            dm = re.search(r"[xX]\s*" + _FTIN, up[_DIMS_RE.search(up).end():]) if _DIMS_RE.search(up) else None
            if dm:
                depth = _ftin_value(dm.groups())
            else:
                im = re.search(r"(\d{1,2})\s*\"\s*(?:THK|THICK|DEEP|D)", rest)
                depth = float(im.group(1)) / 12 if im else None
            sizes[m.group(1).replace("-", "")] = (dims[0], dims[1], depth)
        cm = re.search(r"\b(C-?\d{1,2})\b", up)
        cd = _INCH_DIMS_RE.search(up)
        if cm and cd:
            a, b = sorted([float(cd.group(1)), float(cd.group(2))])
            if 6 <= a <= 24 and 9 <= b <= 36:
                out["column_width_ft"], out["column_depth_ft"] = a / 12, b / 12
    tags = [w.upper().replace("-", "") for w in words if re.fullmatch(r"[Ff]-?\d{1,2}", w)]
    counts = {t: tags.count(t) - 1 for t in set(tags) if t in sizes}  # minus the schedule row
    total = sum(max(c, 0) for c in counts.values())
    if sizes:
        if total > 0:
            area = sum(sizes[t][0] * sizes[t][1] * max(c, 0) for t, c in counts.items()) / total
            depths = [sizes[t][2] for t in counts if sizes[t][2]]
            out["footing_count"] = float(total)
        else:
            area = statistics.mean(s[0] * s[1] for s in sizes.values())
            depths = [s[2] for s in sizes.values() if s[2]]
        side = math.sqrt(area)
        out["footing_length_ft"] = out["footing_width_ft"] = side
        if depths:
            out["footing_thickness_ft"] = statistics.mean(depths)
    ctags = [w for w in words if re.fullmatch(r"[Cc]-?\d{1,2}", w)]
    if len(ctags) >= 4:
        out["column_count"] = float(len(ctags) - len({c.upper().replace("-", "") for c in ctags}))
    return out


def _plot_facts(text: str) -> Dict[str, float]:
    up = normalize_text(text).upper()
    out: Dict[str, float] = {}
    m = re.search(r"(\d{1,2}(?:\.\d+)?)\s*-?\s*MARLA", up)
    if m:
        out["marla"] = float(m.group(1))
    m = re.search(r"PLOT\s*(?:SIZE|DIMENSIONS?|AREA)?\s*[:=]?\s*" + _DIMS_RE.pattern, up)
    if m:
        g = m.groups()
        a, b = sorted([_ftin_value(g[:4]), _ftin_value(g[4:])])
        out["plot_width_ft"], out["plot_depth_ft"] = a, b
    for fm in re.finditer(r"(BASEMENT|GROUND|FIRST|SECOND|1ST|2ND)\s*(?:FLOOR)?\s*(?:COVERED)?\s*AREA\s*[:=]?\s*([\d,]+(?:\.\d+)?)\s*(?:SFT|SQ\.?\s*FT|SQFT|S\.?\s*FT)", up):
        key = {"1ST": "FIRST", "2ND": "SECOND"}.get(fm.group(1), fm.group(1)).lower()
        out[f"covered_{key}_sqft"] = float(fm.group(2).replace(",", ""))
    return out


# --------------------------------------------------------------------------
# Package analysis
# --------------------------------------------------------------------------


def _infer_scale(H, V, curves, plot_width_ft: Optional[float]) -> Optional[Tuple[str, float, WallMeasurement]]:
    """No scale note: try the usual drawing scales and keep the one whose
    measured footprint is a plausible 5-10 marla house (and, if the plot
    width is known, whose frontage matches it best)."""
    best = None
    for label, fpp in CANDIDATE_SCALES_FT_PER_PT.items():
        m = measure_plan(H, V, curves, fpp)
        if not m:
            continue
        area = m.width_ft * m.depth_ft
        if not (400 <= area <= 3500):
            continue
        score = abs(min(m.width_ft, m.depth_ft) - plot_width_ft) if plot_width_ft else -m.wall_length_ft / max(area, 1)
        if best is None or score < best[0]:
            best = (score, label, fpp, m)
    return (best[1], best[2], best[3]) if best else None


def _finding(key: str, value: float, unit_system: str) -> str:
    label = key.replace("_ft", "").replace("_", " ").capitalize()
    if key in ("footing_count", "column_count"):
        return f"{label}: {value:g}"
    if key == "levels_storeys":
        return f"Storey levels on section: {value:g}"
    small = key in ("slab_thickness_ft", "column_width_ft", "column_depth_ft", "footing_thickness_ft")
    if units.is_fps(unit_system):
        return f"{label}: {units.fmt_in(value * FT) if small else units.fmt_ftin(value * FT)}"
    return f"{label}: {value * FT * (1000 if small else 1):.{0 if small else 2}f} {'mm' if small else 'm'}"


def analyze_package(files: List[dict], plot_width_hint_ft: Optional[float] = None, unit_system: str = "FPS") -> PackageFacts:
    """files: [{"name", "bytes", "view_tag"}]. Only PDFs are analysed here
    (images carry no text/vectors). Reads at most MAX_PACKAGE_PAGES pages."""
    facts = PackageFacts()
    pages_read = 0
    plan_views: List[Tuple[View, List[TextLine], tuple, Optional[Tuple[str, float]], str]] = []
    for fi, f in enumerate(files):
        if not f["name"].lower().endswith(".pdf"):
            facts.sheets.append(SheetSummary(f["name"], 1, [f.get("view_tag", "Image")], ["Image - left to the AI (no text layer or vectors)."], False, False))
            continue
        try:
            doc = pymupdf.open(stream=f["bytes"], filetype="pdf")
        except Exception:  # noqa: BLE001
            facts.sheets.append(SheetSummary(f["name"], 1, ["unreadable"], ["Could not open this PDF."], False, False))
            continue
        with doc:
            for pi_, page in enumerate(doc):
                if pages_read >= MAX_PACKAGE_PAGES:
                    break
                pages_read += 1
                lines = _text_lines(page)
                full_text = "\n".join(ln.text for ln in lines)
                H, V, curves = _segments(page)
                views = []
                for ln in lines:
                    c = classify_title(ln.text)
                    if c:
                        views.append(View(c[0], c[1], ln.text.strip(), ln.cx, ln.cy))
                findings: List[str] = []
                for k, v in _plot_facts(full_text).items():
                    facts.plot.setdefault(k, (v, f"{f['name']} p{pi_ + 1}"))
                scale = parse_scale(full_text)
                src = f"{f['name']} p{pi_ + 1}"
                kinds_here = {v.kind for v in views}
                if not views:
                    facts.page_kinds[(fi, pi_)] = "unknown"
                else:
                    order = ["plan", "section", "elevation", "structural", "site", "schedule", "mep"]
                    top = min(views, key=lambda v: order.index(v.kind) if v.kind in order else 99)
                    facts.page_kinds[(fi, pi_)] = f"{top.kind}:{top.floor or ''}"
                # section facts: text near section views (whole page if single view)
                if "section" in kinds_here:
                    sec_lines = [ln for ln in lines if _nearest_view(views, ln.cx, ln.cy) and _nearest_view(views, ln.cx, ln.cy).kind in {"section", "elevation"}]
                    for k, v in _section_facts(sec_lines).items():
                        facts.section.setdefault(k, (v, src))
                        findings.append(_finding(k, v, unit_system))
                if "structural" in kinds_here:
                    words = [w[4] for w in page.get_text("words")]
                    for k, v in _structural_facts(lines, words).items():
                        facts.structural.setdefault(k, (v, src))
                        findings.append(_finding(k, v, unit_system))
                for v in views:
                    if v.kind == "plan" and v.floor:
                        vlines = [ln for ln in lines if _nearest_view(views, ln.cx, ln.cy, {"plan"}) is v]
                        plan_views.append((v, vlines, (H, V, curves), scale, src))
                facts.sheets.append(SheetSummary(
                    f["name"], pi_ + 1,
                    [f"{v.kind}{' (' + FLOOR_NAMES.get(v.floor, v.floor) + ')' if v.floor else ''}" for v in views] or ["unrecognised"],
                    findings, bool(lines), bool(H or V),
                ))

    plot_w = facts.plot.get("plot_width_ft", (plot_width_hint_ft, ""))[0]
    for view, vlines, (H, V, curves), scale, src in plan_views:
        if view.floor in facts.floors:
            continue
        ff = FloorFacts(floor=view.floor, source=f"{view.title.title()} ({src})")
        rooms = _rooms_from_lines(vlines)
        ff.rooms = [(r[0], r[1], r[2], r[3]) for r in rooms]
        # geometry only for the part of the page belonging to this plan view
        same_page = [pv for pv in plan_views if pv[4] == src]
        if len(same_page) > 1:
            def mine(x, y):
                return min(same_page, key=lambda pv: (pv[0].cx - x) ** 2 + (pv[0].cy - y) ** 2)[0] is view
            Hs = [s for s in H if mine((s[1] + s[2]) / 2, s[0])]
            Vs = [s for s in V if mine(s[0], (s[1] + s[2]) / 2)]
            Cs = [c for c in curves if mine((c[0] + c[2]) / 2, (c[1] + c[3]) / 2)]
        else:
            Hs, Vs, Cs = H, V, curves
        m = None
        if scale:
            m = measure_plan(Hs, Vs, Cs, scale[1])
            if m and not (300 <= m.width_ft * m.depth_ft <= 4000):
                m = None  # scale note does not match the PDF's plotted size
            ff.scale_label = scale[0] if m else ""
        if m is None and (Hs or Vs):
            inferred = _infer_scale(Hs, Vs, Cs, plot_w)
            if inferred:
                ff.scale_label, _, m = inferred
                ff.scale_label += " (inferred)"
                ff.geometry_confidence = ConfidenceLevel.LOW
        if m:
            ff.width_ft, ff.depth_ft = m.width_ft, m.depth_ft
            ff.wall_length_ft = m.wall_length_ft
            ff.perimeter_ft = 2 * (m.width_ft + m.depth_ft)
            ff.avg_wall_thickness_in = m.avg_thickness_in
            ff.thickness_breakdown = m.thickness_breakdown
            ff.doors = m.doors or None
            ff.covered_sqft, ff.covered_source = m.width_ft * m.depth_ft, "measured footprint"
        stated = facts.plot.get(f"covered_{view.floor}_sqft")
        if stated:
            if ff.covered_sqft and abs(stated[0] - ff.covered_sqft) / stated[0] > 0.10:
                facts.conflicts.append(
                    f"{FLOOR_NAMES[view.floor]}: stated covered area {stated[0]:,.0f} sqft vs measured footprint "
                    f"{ff.covered_sqft:,.0f} sqft - the stated figure is used."
                )
            ff.covered_sqft, ff.covered_source = stated[0], f"stated on drawing ({stated[1]})"
        if ff.covered_sqft and ff.rooms:
            room_area = sum(r[1] * r[2] for r in ff.rooms if r[3] != "open")
            if room_area > ff.covered_sqft * 1.05:
                facts.conflicts.append(
                    f"{FLOOR_NAMES[view.floor]}: room areas add up to {room_area:,.0f} sqft, more than the covered area "
                    f"{ff.covered_sqft:,.0f} sqft - check the scale or the room labels."
                )
        facts.floors[view.floor] = ff
        sheet = next((sh for sh in facts.sheets if f"{sh.file_name} p{sh.page_no}" == src), None)
        if sheet is not None:
            Ar = (lambda sq: f"{sq:,.0f} sqft") if units.is_fps(unit_system) else (lambda sq: f"{sq * SQFT:,.1f} m²")
            bits = []
            if ff.covered_sqft:
                bits.append(f"covered {Ar(ff.covered_sqft)}")
            if ff.wall_length_ft:
                bits.append(f"walls {units.length_text(ff.wall_length_ft * FT, unit_system, f'{ff.wall_length_ft * FT:.1f} m')}")
            if ff.doors:
                bits.append(f"{ff.doors} doors")
            if ff.rooms:
                bits.append(f"{len(ff.rooms)} rooms ({ff.count('bathroom')} bath, {ff.count('kitchen')} kitchen)")
            if ff.scale_label:
                bits.append(f"scale {ff.scale_label}")
            sheet.findings.append(f"{FLOOR_NAMES[view.floor]}: " + (", ".join(bits) if bits else "no measurable geometry"))

    _cross_check(facts)
    return facts


def _cross_check(facts: PackageFacts) -> None:
    lv = facts.section.get("levels_storeys")
    if lv and facts.storeys and int(lv[0]) != facts.storeys:
        facts.conflicts.append(
            f"The section shows {int(lv[0])} storey level(s) but {facts.storeys} floor plan(s) were found - "
            "check that every floor plan was uploaded."
        )
    fc, cc = facts.structural.get("footing_count"), facts.structural.get("column_count")
    if fc and cc and fc[0] != cc[0]:
        facts.conflicts.append(f"Foundation plan shows {fc[0]:g} footings but {cc[0]:g} columns.")
    pw = facts.plot.get("plot_width_ft")
    for ff in facts.floors.values():
        if pw and ff.width_ft and min(ff.width_ft, ff.depth_ft) > pw[0] * 1.05:
            facts.conflicts.append(
                f"{FLOOR_NAMES.get(ff.floor, ff.floor)} footprint ({min(ff.width_ft, ff.depth_ft):.1f} ft wide) is wider "
                f"than the plot ({pw[0]:.1f} ft) - check the drawing scale."
            )
    areas = [f.covered_sqft for k, f in facts.floors.items() if k in FLOOR_ORDER and f.covered_sqft]
    if len(areas) > 1 and (max(areas) - min(areas)) / max(areas) > 0.10:
        facts.conflicts.append(
            "Floors have different covered areas; the calculation uses their average per floor, "
            "which keeps total areas and quantities correct."
        )


# --------------------------------------------------------------------------
# Merge into parameters
# --------------------------------------------------------------------------


def apply_package_facts(
    params: ExtractedBuildingParams, facts: PackageFacts, project_inputs: ProjectInputs
) -> Tuple[ExtractedBuildingParams, Dict[str, float], List[str]]:
    """Overrides params with values read from the drawings. Returns
    (params, assumption_updates_in_metres, list_of_fields_filled)."""
    us = project_inputs.unit_system
    p = params.model_copy(deep=True)
    filled: List[str] = []
    asm: Dict[str, float] = {}
    L = lambda ft: units.length_text(ft * FT, us, f"{ft * FT:.2f} m")  # noqa: E731
    Ar = lambda sq: units.area_text(sq * SQFT, us, f"{sq * SQFT:.1f} m²", 0)  # noqa: E731

    def est(value: float, conf: ConfidenceLevel, note: str) -> Estimate:
        return Estimate(value=value, confidence=conf, source=Source.DRAWING_READ, note=f"From drawings: {note}")

    floors = [facts.floors[k] for k in FLOOR_ORDER if k in facts.floors]
    if floors:
        p.num_floors = est(len(floors), ConfidenceLevel.HIGH, f"{len(floors)} floor plan(s): " + ", ".join(FLOOR_NAMES[f.floor] for f in floors))
        filled.append("number of floors")

    def avg(attr):
        vals = [getattr(f, attr) for f in floors if getattr(f, attr)]
        return (sum(vals) / len(vals), vals) if vals else (None, [])

    cov, cov_vals = avg("covered_sqft")
    if cov:
        conf = ConfidenceLevel.HIGH if all("stated" in f.covered_source for f in floors if f.covered_sqft) else min(
            (f.geometry_confidence for f in floors), key=lambda c: ["Low", "Medium", "High"].index(c.value))
        note = f"{Ar(cov)} per floor" + (" (average of floors)" if len(cov_vals) > 1 else "") + f" - {floors[0].covered_source}"
        p.plinth_area_per_floor_sqm = est(cov * SQFT, conf, note)
        p.slabs.area_per_floor_sqm = est(cov * SQFT, conf, note)
        filled.append("covered / slab area")
    gconf = min((f.geometry_confidence for f in floors), key=lambda c: ["Low", "Medium", "High"].index(c.value), default=ConfidenceLevel.MEDIUM)
    scales = ", ".join(sorted({f.scale_label for f in floors if f.scale_label}))
    wl, _ = avg("wall_length_ft")
    if wl:
        p.walls.total_length_per_floor_m = est(wl * FT, gconf, f"{L(wl)} measured from wall lines (scale {scales})")
        filled.append("total wall length")
    per, _ = avg("perimeter_ft")
    if per:
        p.walls.external_perimeter_m = est(per * FT, gconf, f"{L(per)} = outer footprint (scale {scales})")
        filled.append("external perimeter")
    thk, _ = avg("avg_wall_thickness_in")
    if thk and 3.5 <= thk <= 13.5:
        bd = {}
        for f in floors:
            for t, length in f.thickness_breakdown.items():
                bd[t] = bd.get(t, 0) + length
        detail = ", ".join(f'{units.fmt_in(t * IN) if units.is_fps(us) else f"{t * 25.4:.0f} mm"}: {L(length / len(floors))}' for t, length in sorted(bd.items()))
        p.walls.thickness_m = est(thk * IN, gconf, f"length-weighted average of {detail}")
        filled.append("average wall thickness")
    doors, _ = avg("doors")
    if doors:
        p.openings.door_count_per_floor = est(round(doors), ConfidenceLevel.MEDIUM, "door swings counted on the plans")
        filled.append("doors per floor")
    if any(f.rooms for f in floors):
        baths = sum(f.count("bathroom") for f in floors)
        kitchens = sum(f.count("kitchen") for f in floors)
        if baths:
            p.services.bathroom_count_total = est(baths, ConfidenceLevel.HIGH, "bathrooms labelled on the plans")
            filled.append("bathrooms")
        if kitchens:
            p.services.kitchen_count_total = est(kitchens, ConfidenceLevel.HIGH, "kitchens labelled on the plans")
            filled.append("kitchens")

    s = facts.section
    if "floor_height_ft" in s:
        v, src = s["floor_height_ft"]
        p.columns.height_per_floor_m = est(v * FT, ConfidenceLevel.HIGH, f"{L(v)} from section levels ({src})")
        p.walls.height_m = est(v * FT, ConfidenceLevel.HIGH, f"{L(v)} from section levels ({src})")
        filled.append("floor height")
    if "slab_thickness_ft" in s:
        v, src = s["slab_thickness_ft"]
        p.slabs.thickness_m = est(v * FT, ConfidenceLevel.HIGH, f"slab thickness noted on section ({src})")
        filled.append("slab thickness")
    if "founding_depth_ft" in s:
        v, src = s["founding_depth_ft"]
        p.footings.founding_depth_m = est(v * FT, ConfidenceLevel.HIGH, f"{L(v)} foundation level on section ({src})")
        filled.append("founding depth")
    if "plinth_height_ft" in s:
        asm["plinth_height_m"] = s["plinth_height_ft"][0] * FT
        filled.append("plinth height")
    if "parapet_height_ft" in s:
        asm["parapet_height_m"] = s["parapet_height_ft"][0] * FT
        filled.append("parapet height")

    st = facts.structural
    for key, attr, obj, label in [
        ("footing_count", "count", p.footings, "footing count"),
        ("footing_length_ft", "length_m", p.footings, "footing length"),
        ("footing_width_ft", "width_m", p.footings, "footing width"),
        ("footing_thickness_ft", "depth_m", p.footings, "footing thickness"),
        ("column_count", "count", p.columns, "column count"),
        ("column_width_ft", "width_m", p.columns, "column width"),
        ("column_depth_ft", "depth_m", p.columns, "column depth"),
    ]:
        if key in st:
            v, src = st[key]
            value = v if attr == "count" else v * FT
            setattr(obj, attr, est(value, ConfidenceLevel.HIGH, f"{label} from structural sheet ({src})"))
            filled.append(label)

    # AI-missing fields that the drawings supplied are no longer missing.
    field_to_filled = {
        "number of floors": "number of floors", "plinth area": "covered / slab area", "slab area": "covered / slab area",
        "total wall length": "total wall length", "external perimeter": "external perimeter",
        "wall thickness": "average wall thickness", "door count": "doors per floor", "bathroom count": "bathrooms",
        "kitchen count": "kitchens", "height per floor": "floor height", "wall height": "floor height",
        "slab thickness": "slab thickness", "founding depth": "founding depth", "footing count": "footing count",
        "footing length": "footing length", "footing width": "footing width", "footing thickness": "footing thickness",
        "column count": "column count", "column width": "column width", "column depth": "column depth",
    }
    cleaned = []
    for w in p.extraction_warnings:
        m = re.match(r"(AI did not return: |AI values were unreadable for: )(.*) - (.*) used\.$", w)
        if m:
            left = [f for f in m.group(2).split(", ") if field_to_filled.get(f) not in filled]
            if not left:
                continue
            w = f"{m.group(1)}{', '.join(left)} - {m.group(3)} used."
        cleaned.append(w)
    p.extraction_warnings = cleaned

    marla = facts.plot.get("marla")
    if marla and project_inputs.plot_marla and abs(marla[0] - project_inputs.plot_marla) > 0.01:
        facts_note = (
            f"The drawings say {marla[0]:g} marla ({marla[1]}) but Step 1 is set to {project_inputs.plot_marla:g} marla - "
            "correct the plot size in Step 1 so the plot checks and template are right."
        )
        if facts_note not in facts.conflicts:
            facts.conflicts.append(facts_note)
    elif marla and not project_inputs.plot_marla:
        note = f"The drawings say {marla[0]:g} marla - choose it as the plot size in Step 1 to enable plot checks."
        if note not in facts.conflicts:
            facts.conflicts.append(note)

    warnings = []
    for w in p.extraction_warnings:
        if filled and "template - please review" in w:
            w = w.replace("Values come from the", "Values NOT found in the drawings come from the")
        elif filled and w.startswith("All values are generic defaults"):
            w = "Values NOT found in the drawings are generic defaults - please review them."
        warnings.append(w)
    p.extraction_warnings = warnings + facts.conflicts
    return p, asm, filled


def pages_for_ai(facts: PackageFacts, limit: int) -> List[Tuple[int, int]]:
    """Most useful pages to show the AI: ground plan, section, other plans,
    elevation, then unrecognised pages (e.g. scans)."""
    rank = {"plan:ground": 0, "section:": 1, "plan:first": 2, "plan:second": 3, "elevation:": 4, "plan:basement": 5, "unknown": 6}
    ordered = sorted(facts.page_kinds.items(), key=lambda kv: rank.get(kv[1], 9))
    return [k for k, v in ordered if rank.get(v, 9) < 9][:limit]


def render_pages(file_bytes: bytes, page_indices: List[int], dpi: int = 150):
    """Renders selected PDF pages to PIL images (for the AI / preview)."""
    from PIL import Image

    out = []
    with pymupdf.open(stream=file_bytes, filetype="pdf") as doc:
        for i in page_indices:
            if 0 <= i < doc.page_count:
                pix = doc[i].get_pixmap(dpi=dpi)
                out.append(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))
    return out


def ai_hint_from_facts(facts: PackageFacts) -> str:
    """Tells the AI what is already known exactly, so it focuses on the rest."""
    bits = []
    for k in FLOOR_ORDER:
        f = facts.floors.get(k)
        if f and f.covered_sqft:
            bits.append(f"{FLOOR_NAMES[k]} covered area {f.covered_sqft:.0f} sqft")
    for key, (v, _) in facts.section.items():
        if key != "levels_storeys":
            bits.append(f"{key.replace('_ft', '').replace('_', ' ')} {v:.2f} ft")
    for key, (v, _) in facts.structural.items():
        bits.append(f"{key.replace('_ft', '').replace('_', ' ')} {v:g}{'' if 'count' in key else ' ft'}")
    if not bits:
        return ""
    return "Already read exactly from the drawing text/geometry (use these values): " + "; ".join(bits) + "."
