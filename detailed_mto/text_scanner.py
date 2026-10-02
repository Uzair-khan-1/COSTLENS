"""
Supplementary text-layer scanner for the Detailed MTO.

The existing ``drawing_processing.package_analyzer`` already extracts rooms,
walls, levels, footings and door/window totals. This module reads the SAME
PDF text layer for the extra facts a complete material schedule needs:

* plumbing labels on "PLUMBING" sheets: F.T, M.H, G.T, C.O, VANITY,
  CONCEALED WC, SHOWER AREA, SUMP (roof khuras), SEPTIC TANK, "600 GAL." tank;
* door schedule rows (size, chogath width, single/double, qty, name);
* furniture/plan labels: WARDROBE, BALCONY, TERRACE, FRIDGE, OVEN, DB;
* tank plan sizes from the tank detail sheet.

It never raises: scanned drawings simply give an empty result and the
builder falls back to room-based defaults (marked "Assumed").
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

try:  # pymupdf is a hard dependency of the app, but keep this module importable without it
    import pymupdf
except Exception:  # pragma: no cover
    pymupdf = None

_Q = str.maketrans({"’": "'", "′": "'", "‘": "'", "`": "'", "”": '"', "″": '"', "“": '"', "×": "x", "–": "-", "—": "-"})
_FTIN = r"(\d{1,2})\s*'\s*-?\s*(\d{1,2}(?:\.\d+)?)?\s*\"?"
_SIZE = re.compile(_FTIN + r"\s*[xX]\s*" + _FTIN)
_GAL = re.compile(r"(\d{2,5})\s*GAL", re.I)


def _ftin(a, b) -> float:
    return float(a) + (float(b) / 12.0 if b else 0.0)


@dataclass
class DoorRow:
    name: str
    width_ft: float
    height_ft: float
    qty: int
    leaves: int
    chogath_in: float
    source: str


@dataclass
class WindowRow:
    name: str
    width_ft: float
    height_ft: float
    qty: int
    sill_ft: float
    kind: str  # window | ventilator
    source: str


@dataclass
class ScanResult:
    label_counts: Dict[str, int] = field(default_factory=dict)  # max count on any single sheet, summed over floors
    per_page: Dict[int, Dict[str, int]] = field(default_factory=dict)
    doors: List[DoorRow] = field(default_factory=list)
    oh_tank_gal: Optional[float] = None
    oh_tank_type: str = ""
    septic_plan: Optional[Tuple[float, float]] = None
    septic_detail: Optional[Tuple[float, float]] = None
    ug_tank_detail: Optional[Tuple[float, float]] = None
    oh_tank_detail: Optional[Tuple[float, float]] = None
    windows: List[WindowRow] = field(default_factory=list)  # from a window schedule table
    rebar: object = None  # detailed_mto.rebar.RebarFacts - reinforcement details / BBS read from the drawings
    gate: Optional[Tuple[float, float]] = None  # main gate (width, height) from a schedule
    detail_only: set = field(default_factory=set)
    sources: Dict[str, str] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)

    def get(self, key: str, default: int = 0) -> int:
        return self.label_counts.get(key, default)


# label key -> exact line texts (upper-cased) that count as one occurrence
_LABELS = {
    "FT": ("F.T", "F.T.", "FT", "FLOOR TRAP"),
    "MH": ("M.H", "M.H.", "MANHOLE"),
    "GT": ("G.T", "G.T.", "GULLY TRAP"),
    "CO": ("C.O", "C.O.", "CLEAN OUT", "CLEANOUT"),
    "VANITY": ("VANITY",),
    "WC": ("CONCEALED WC", "WC", "W.C", "COMMODE"),
    "SHOWER": ("SHOWER AREA", "CONCEALED SHOWER"),
    "SUMP": ("SUMP", "KHURA"),
    "WARDROBE": ("WARDROBE",),
    "BALCONY": ("BALCONY",),
    "TERRACE": ("FRONT TERRACE", "BACK TERRACE", "TERRACE"),
    "DB": ("DB", "D.B", "DISTRIBUTION BOARD"),
    "GEYSER": ("GEYSER", "WATER HEATER"),
    "OVEN": ("FRIDGE & OVEN", "OVEN"),
}


def _page_lines(page) -> List[Tuple[str, Tuple[float, float, float, float]]]:
    out = []
    for b in page.get_text("dict").get("blocks", []):
        for ln in b.get("lines", []):
            t = " ".join(s.get("text", "") for s in ln.get("spans", [])).strip().translate(_Q)
            t = re.sub(r"\s*½", ".5", t)
            if t:
                out.append((t, tuple(ln["bbox"])))
    return out


def _floor_of(text_upper: str) -> str:
    for key, words in (("ground", ("GROUND FLOOR PLAN",)), ("first", ("FIRST FLOOR PLAN",)),
                       ("second", ("SECOND FLOOR PLAN",)), ("roof", ("MUMTY PLAN", "ROOF PLAN"))):
        if any(w in text_upper for w in words):
            return key
    return "other"


def _parse_door_schedule(lines, src: str) -> List[DoorRow]:
    sizes = []
    for t, bb in lines:
        m = _SIZE.search(t)
        if m and "X" in t.upper():
            w, h = _ftin(m.group(1), m.group(2)), _ftin(m.group(3), m.group(4))
            if 1.5 <= w <= 10 and 6 <= h <= 10:
                sizes.append((w, h, t, bb))
    rows = []
    for w, h, t, bb in sizes:
        yc = (bb[1] + bb[3]) / 2
        same = [(tt, b2) for tt, b2 in lines if abs((b2[1] + b2[3]) / 2 - yc) <= 8 and b2 != bb]
        qty = None
        leaves = 1
        chog = None
        name = ""
        tail = re.split(r"[xX]", t)[-1]
        mc = re.search(r"\s(\d{1,2})\s*\"\s*$", tail)  # trailing chogath width, e.g. '4'-6" X 8'-0"   10"'
        if mc:
            chog = float(mc.group(1))
        for tt, b2 in same:
            u = tt.upper()
            if re.fullmatch(r"\d{1,2}", tt) and b2[0] > bb[0]:
                qty = int(tt)
            elif u in ("DOUBLE", "SINGLE"):
                leaves = 2 if u == "DOUBLE" else 1
            elif re.fullmatch(r"\d{1,2}\s*\"", tt):
                chog = float(re.match(r"\d+", tt).group(0))
            elif "DOOR" in u:
                name = tt.title()
        if qty:
            rows.append(DoorRow(name or f"Door {w:g}x{h:g}", w, h, qty, leaves, chog or 5.0, src))
    return rows


_REBAR_HINT = re.compile(r"#\s*\d\s*@|\d\s*-\s*#\s*\d|\b\d{1,2}\s*mm\s*@|[TY]\d{1,2}\s*@|c/c|bar\s*mark|bar\s*bending|"
                         r"reinforcement|stirrup|\brings?\b", re.I)


def _merge_rebar(res: "ScanResult", rb) -> None:
    if rb is None or not (rb.any() or rb.stated_total_kg):
        return
    if res.rebar is None:
        res.rebar = rb
        return
    cur = res.rebar
    for k, m in rb.members.items():
        if k not in cur.members:
            cur.members[k] = m
        else:
            c = cur.members[k]
            c.long_bars = c.long_bars or m.long_bars
            c.ties = c.ties or m.ties
            c.mesh = c.mesh or m.mesh
            c.both_ways = c.both_ways or m.both_ways
            c.count = c.count or m.count
            c.size_in = c.size_in or m.size_in
            c.width_in = c.width_in or m.width_in
    cur.bbs += rb.bbs
    if cur.stated_total_kg is None and rb.stated_total_kg:
        cur.stated_total_kg, cur.stated_total_text = rb.stated_total_kg, rb.stated_total_text
    cur.notes += rb.notes


def scan_pdf_bytes(files: List[dict]) -> ScanResult:
    """files: [{"name": str, "bytes": bytes, ...}] as stored in session state."""
    res = ScanResult()
    if pymupdf is None or not files:
        return res
    floor_counts: Dict[Tuple[str, str], int] = {}
    for f in files:
        name = f.get("name", "")
        data = f.get("bytes")
        if not data or not name.lower().endswith(".pdf"):
            continue
        try:
            doc = pymupdf.open(stream=data, filetype="pdf")
        except Exception:
            res.notes.append(f"Could not open {name} for label scan.")
            continue
        rebar_pages = []
        for pi, page in enumerate(doc):
            if pi >= 80:
                break
            try:
                if _REBAR_HINT.search(page.get_text()):
                    rebar_pages.append(page)
            except Exception:  # noqa: BLE001
                pass
            try:
                lines = _page_lines(page)
            except Exception:
                continue
            if not lines:
                continue
            full = " ".join(t for t, _ in lines).upper()
            src = f"{name} p{pi + 1}"
            var_counts: Dict[Tuple[str, str], int] = {}
            for t, _ in lines:
                u = t.upper().strip()
                for key, variants in _LABELS.items():
                    if u in variants:
                        var_counts[(key, u)] = var_counts.get((key, u), 0) + 1
            counts: Dict[str, int] = {}
            for (key, _v), n in var_counts.items():  # 'CONCEALED WC' + 'wc' tags on one fixture -> max, not sum
                counts[key] = (counts.get(key, 0) + n) if key == "TERRACE" else max(counts.get(key, 0), n)
            res.per_page[pi + 1] = counts
            fl = _floor_of(full)
            is_plumb = "PLUMBING" in full or "SANITARY" in full
            for key, n in counts.items():
                # plumbing labels only trusted on plumbing sheets (they are repeated on other sheets)
                if key in ("FT", "MH", "GT", "CO", "SUMP") and not is_plumb:
                    continue
                k2 = (key, fl)
                if n > floor_counts.get(k2, 0):
                    floor_counts[k2] = n
                    res.sources[f"{key}:{fl}"] = src
            # door schedule
            if "CHOGATH" in full or "CHOGATTH" in full or "DOOR SCHEDULE" in full:
                rows = _parse_door_schedule(lines, src)
                if rows:
                    res.doors = rows
            # schedule TABLES with separate columns (Symbol | Width | Height | Count | Sill)
            if "SCHEDULE" in full and "WIDTH" in full and "HEIGHT" in full:
                tdoors, twins, gate = _parse_schedule_tables(lines, src)
                if tdoors and not res.doors:
                    res.doors = tdoors
                if twins:
                    res.windows = twins
                if gate:
                    res.gate = gate
            # overhead tank
            for t, _ in lines:
                mg = _GAL.search(t)
                if mg and res.oh_tank_gal is None:
                    res.oh_tank_gal = float(mg.group(1))
                    res.oh_tank_type = "FG/GRP" if ("FG" in full or "GRP" in full) else ""
                    res.sources["OH_TANK"] = src
            # septic / UG / OH tank sizes
            if "TANK" in full and "DETAIL" in full:
                for kind, size in _tank_details(lines).items():
                    setattr(res, kind, size)
                    res.sources[kind] = src
            for t, bb in lines:
                u = t.upper()
                if "SEPTIC" in u and "DETAIL" not in u and res.septic_plan is None:
                    near = _nearest_size(lines, bb)
                    if near:
                        res.septic_plan = near
                        res.sources["septic_plan"] = src
        if rebar_pages:
            try:
                from detailed_mto.rebar import read_rebar
                _merge_rebar(res, read_rebar(rebar_pages, name))
            except Exception as exc:  # noqa: BLE001 - never block the drawing scan
                res.notes.append(f"Reinforcement details in {name} could not be read: {exc}")
        doc.close()
    # sum per-floor maxima; detail/legend sheets ("other") only count when no plan sheet has the label
    keys_on_plans = {k for (k, fl) in floor_counts if fl != "other"}
    tot: Dict[str, int] = {}
    for (key, fl), n in floor_counts.items():
        if fl == "other" and key in keys_on_plans:
            continue
        if fl == "other":
            res.detail_only.add(key)
        tot[key] = tot.get(key, 0) + n
    res.label_counts = tot
    if res.septic_plan and res.septic_detail and res.septic_plan != res.septic_detail:
        res.notes.append(
            f"Septic tank size differs: plan {res.septic_plan[0]:g}'x{res.septic_plan[1]:g}' vs detail "
            f"{res.septic_detail[0]:g}'x{res.septic_detail[1]:g}' - the detail is used; please confirm."
        )
    return res


def _nearest_size(lines, bb, exclude=None) -> Optional[Tuple[float, float]]:
    cx, cy = (bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2
    best, bd = None, 1e9
    for t, b2 in lines:
        m = _SIZE.search(t)
        if not m:
            continue
        a, b = _ftin(m.group(1), m.group(2)), _ftin(m.group(3), m.group(4))
        if not (2 <= a <= 20 and 2 <= b <= 20) or (exclude and (a, b) == exclude):
            continue
        d = ((b2[0] + b2[2]) / 2 - cx) ** 2 + ((b2[1] + b2[3]) / 2 - cy) ** 2
        if d < bd:
            best, bd = (a, b), d
    return best


def _tank_details(lines) -> Dict[str, Tuple[float, float]]:
    """Assign 'L x W' size callouts to tank-detail titles. Titles sit beside their
    drawing (below it on normal sheets, to its left on rotated sheets), so a size
    belongs to the nearest title on the 'drawing side' along the reading axis."""
    titles = []
    for t, bb in lines:
        u = t.upper()
        if "DETAIL" in u and "TANK" in u and "TANKS DETAILS" not in u:
            kind = ("septic_detail" if "SEPTIC" in u else "ug_tank_detail" if ("U.G" in u or "UG" in u or "UNDERGROUND" in u)
                    else "oh_tank_detail" if ("O.H" in u or "OVERHEAD" in u or "OH" in u) else None)
            if kind:
                titles.append((kind, bb))
    if not titles:
        return {}
    vertical = sum((b[3] - b[1]) > (b[2] - b[0]) for _, b in titles) > len(titles) / 2
    out: Dict[str, Tuple[float, float]] = {}
    best: Dict[str, float] = {}
    for t, bb in lines:
        m = _SIZE.search(t)
        if not m or "X" not in t.upper():
            continue
        a, b = _ftin(m.group(1), m.group(2)), _ftin(m.group(3), m.group(4))
        if not (2 <= a <= 20 and 2 <= b <= 20):
            continue
        pos = (bb[0] + bb[2]) / 2 if vertical else (bb[1] + bb[3]) / 2
        cand = []
        for kind, tb in titles:
            tpos = (tb[0] + tb[2]) / 2 if vertical else (tb[1] + tb[3]) / 2
            d = (pos - tpos) if vertical else (tpos - pos)  # size must be on the drawing side of its title
            if d > 0:
                cand.append((d, kind))
        if cand:
            _d, kind = min(cand)
            if a * b > best.get(kind, 0):  # largest plan size in the title's band (skips 2'x2' sump callouts)
                best[kind] = a * b
                out[kind] = (a, b)
    return out


_HEAD = {"symbol": r"^(SYMBOL|MARK|TYPE|TAG|CODE|ID|NO\.?)$", "width": r"^WIDTH$", "height": r"^HEIGHT$",
         "count": r"^(COUNT|QTY|QUANTITY|NOS\.?|NUMBER)$", "sill": r"^SILL( LEVEL| HEIGHT| LVL)?$", "name": r"^(NAME|DESCRIPTION|LOCATION)$"}


def _ft(text: str) -> Optional[float]:
    t = text.strip()
    m = re.fullmatch(_FTIN, t)
    if m:
        return _ftin(m.group(1), m.group(2))
    m = re.fullmatch(r"(\d{1,3})\s*\"", t)
    return float(m.group(1)) / 12.0 if m else None


def _parse_schedule_tables(lines, src: str):
    """Door / window schedule TABLES whose columns are separate text items, e.g.
         Door Schedule                      Window Schedule
         Symbol Width Height Count          Symbol Width Height Count Sill Level
         D1     3'-6" 7'-0"  2              W1     4'-0"  5'-0"  2     2'-0"
    Returns (door rows, window rows, gate (w, h) or None)."""
    doors: List[DoorRow] = []
    wins: List[WindowRow] = []
    gate = None
    items = [(t.strip(), bb) for t, bb in lines]
    heads = [(t, bb) for t, bb in items if re.fullmatch(_HEAD["symbol"], t.upper())]
    for _st, sbb in heads:
        yc = (sbb[1] + sbb[3]) / 2
        row = sorted([(t, bb) for t, bb in items if abs((bb[1] + bb[3]) / 2 - yc) <= 8], key=lambda x: x[1][0])
        # several tables can share one header line (door + window schedules side by side): this table runs from
        # its own 'Symbol' cell to the next 'Symbol' cell on the same line
        sym_x = sorted(bb[0] for t, bb in row if re.fullmatch(_HEAD["symbol"], t.upper()))
        nxt = next((x for x in sym_x if x > sbb[0] + 5), 1e9)
        row = [(t, bb) for t, bb in row if sbb[0] - 5 <= bb[0] < nxt - 5]
        cols = {}
        for t, bb in row:
            for k, pat in _HEAD.items():
                if re.fullmatch(pat, t.upper()) and k not in cols:
                    cols[k] = (bb[0] + bb[2]) / 2
        if not {"width", "height"} <= set(cols):
            continue
        x_lo, x_hi = min(cols.values()) - 80, min(max(cols.values()) + 80, nxt - 5)
        # the table title just above the header decides doors vs windows
        title = ""
        for t, bb in items:
            if "SCHEDULE" in t.upper() and 0 < yc - (bb[1] + bb[3]) / 2 < 120 and x_lo - 150 <= (bb[0] + bb[2]) / 2 <= x_hi + 150:
                title = t.upper()
        is_window = "WINDOW" in title or "sill" in cols
        # data rows below the header, until a gap
        below = sorted([(t, bb) for t, bb in items if (bb[1] + bb[3]) / 2 > yc + 6 and x_lo <= (bb[0] + bb[2]) / 2 <= x_hi],
                       key=lambda x: (x[1][1] + x[1][3]) / 2)
        rows_by_y: List[list] = []
        last_y = yc
        for t, bb in below:
            cy = (bb[1] + bb[3]) / 2
            if cy - last_y > 90:
                break
            if rows_by_y and abs(cy - rows_by_y[-1][0]) <= 8:
                rows_by_y[-1][1].append((t, bb))
            else:
                rows_by_y.append([cy, [(t, bb)]])
            last_y = cy
        for _cy, cells in rows_by_y:
            rec = {}
            for t, bb in cells:
                cx = (bb[0] + bb[2]) / 2
                k = min(cols, key=lambda c: abs(cols[c] - cx))
                rec.setdefault(k, t)
            w, h = _ft(rec.get("width", "")), _ft(rec.get("height", ""))
            try:
                qty = int(float(rec.get("count", "1") or 1))
            except ValueError:
                qty = 1
            sym = rec.get("symbol") or rec.get("name") or ""
            if not (w and h) or qty <= 0 or not sym:
                continue
            u = sym.upper()
            if u in ("MG", "G", "GATE") or "GATE" in u:
                gate = (w, h)
            elif is_window or u.startswith(("W", "V")):
                kind = "ventilator" if (u.startswith("V") or (h <= 2.0 and w <= 3.0)) else "window"
                sill = _ft(rec.get("sill", "")) or 0.0
                wins.append(WindowRow(sym, w, h, qty, sill, kind, src))
            else:
                leaves = 2 if w >= 4.5 else 1
                doors.append(DoorRow(f"{sym} door", w, h, qty, leaves, 5.0, src))
    return doors, wins, gate
