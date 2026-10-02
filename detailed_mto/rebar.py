"""
Steel (reinforcement) from the DRAWINGS instead of thumb rules.

What is read from the structural / sectional sheets (PDF text layer):
  1. A bar bending schedule (BBS) table - bar mark, dia, number, length (and weight) -> used as it is.
  2. Reinforcement details and schedules, e.g.
        "Column C1 (16)   6-#5   #3 rings @ 9 in c/c"
        "F1 isolated footing 4'-0\" x 4'-0\"  #4 @ 6 in c/c both ways"
        "Plinth band 4-#4  #3 rings @ 9 in c/c"      "Roof slab #4 @ 6 in c/c main + #4 @ 6 in c/c distribution"
     metric too: "6-12mm", "4 Nos 16 mm", "T10 @ 150 c/c", "Y12".
  3. Member sizes and counts printed with them (column size, footing size, number of columns / footings).
  4. A total steel weight printed on the drawings ("TOTAL STEEL 8,720.54 lb = 3.96 ton") - used as a cross-check.

Calculation, member by member, with the geometry CostLens already has (column heights, footing sizes, band and
beam lengths, slab areas):
   bar weight = number of bars x bar length x unit weight of the bar size
   bar length = member length + laps (50 d) + anchorage / bends (hooks 10 d), less cover
   ties / rings / stirrups = (member length / spacing + 1) x tie length
Members without details on the drawings keep the thumb-rule ratio, and say so.

Text is rebuilt into ROWS and side-by-side COLUMNS (words grouped by y, split at large x gaps), so table rows
("Plinth band | 4-#4 | #3 rings @ 9 in c/c") and detail drawings (a heading with its bar notes below it) are both
read correctly.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# bar sizes
# ---------------------------------------------------------------------------
LB_PER_FT = {2: 0.167, 3: 0.376, 4: 0.668, 5: 1.043, 6: 1.502, 7: 2.044, 8: 2.670, 9: 3.400, 10: 4.303, 11: 5.313}
KG_PER_LB = 0.45359237
FT_PER_M = 3.28084


def bar_dia_in(size: str) -> float:
    """'#4' -> 0.5 in;  '12mm' -> 0.472 in."""
    if size.startswith("#"):
        return int(size[1:]) / 8.0
    return float(size.replace("mm", "")) / 25.4


def kg_per_ft(size: str) -> float:
    if size.startswith("#"):
        n = int(size[1:])
        return LB_PER_FT.get(n, (n / 8.0) ** 2 * 2.67) * KG_PER_LB
    d = float(size.replace("mm", ""))
    return d * d / 162.0 / FT_PER_M


# ---------------------------------------------------------------------------
# what was read
# ---------------------------------------------------------------------------
@dataclass
class Bars:
    count: int  # longitudinal bars in the section
    size: str  # "#5" / "12mm"


@dataclass
class Spaced:
    size: str
    spacing_in: float
    role: str = ""  # ties | main | distribution | mesh


@dataclass
class MemberSpec:
    kind: str  # footing | column | plinth | lintel | roof_band | beam | slab | stair | tank
    long_bars: Optional[Bars] = None
    ties: Optional[Spaced] = None
    mesh: List[Spaced] = field(default_factory=list)  # slabs / footings
    both_ways: bool = False
    count: Optional[int] = None  # number of members (columns, footings)
    size_in: Optional[Tuple[float, float]] = None  # section (b, d) or footing plan size in inches
    width_in: Optional[float] = None  # bands / beams
    volume_cft: Optional[float] = None  # concrete volume printed with the member (schedules often give it)
    source: str = ""

    def has_detail(self) -> bool:
        return bool(self.long_bars or self.ties or self.mesh)


@dataclass
class BBSRow:
    member: str
    size: str
    count: float
    length_ft: float
    weight_kg: Optional[float] = None

    @property
    def kg(self) -> float:
        return self.weight_kg if self.weight_kg is not None else self.count * self.length_ft * kg_per_ft(self.size)


@dataclass
class RebarFacts:
    members: Dict[str, MemberSpec] = field(default_factory=dict)
    bbs: List[BBSRow] = field(default_factory=list)
    stated_total_kg: Optional[float] = None
    stated_total_text: str = ""
    notes: List[str] = field(default_factory=list)

    def any(self) -> bool:
        return bool(self.bbs or any(m.has_detail() for m in self.members.values()))


# ---------------------------------------------------------------------------
# patterns
# ---------------------------------------------------------------------------
MEMBER_PATTERNS = [  # order matters: first match wins
    ("roof_band", r"roof\s*band"),
    ("fdn_tie", r"foundation\s*\(?\s*tie|foundation\s*tie|tie\s*bars|tie\s*beam|grade\s*beam"),
    ("plinth", r"plinth\s*(?:band|beam)"),
    ("lintel", r"lintel|door\s*band|sill\s*band|lintel\s*band"),
    ("footing", r"footing|\bf\d\b|foundation\s*pad|\bpad\b"),
    ("column", r"column|\bc\d\b"),
    ("slab", r"slab"),
    ("stair", r"stair"),
    ("tank", r"tank"),
    ("beam", r"\bbeams?\b"),
]
_SIZE = r"(?:#\s*(\d{1,2})|(\d{1,2})\s*mm\b|[TYØΦø]\s?(\d{1,2})\b)"
LONG_RE = re.compile(rf"\b(\d{{1,2}})\s*(?:nos?\.?\s*)?(?:[-–x×]\s*|\s+)(?:{_SIZE})", re.I)
SPACED_RE = re.compile(rf"{_SIZE}\s*(?:dia\.?\s*)?(?:bars?\s*|rings?\s*|stirrups?\s*|ties?\s*|links?\s*)?@\s*(\d+(?:\.\d+)?)\s*(in\b|inch|\"|mm|cm)?",
                       re.I)
FTIN_RE = r"(\d+)\s*'\s*-?\s*(\d+(?:\.\d+)?)?\s*\"?"


def _size(m, a, b, c) -> str:
    g = m.group(a) or None
    if g:
        return f"#{int(g)}"
    g = m.group(b) or m.group(c)
    return f"{int(g)}mm"


def _spacing_in(val: str, unit: str) -> float:
    v = float(val)
    u = (unit or "").lower()
    if u == "mm":
        return v / 25.4
    if u == "cm":
        return v / 2.54
    if not u and v >= 50:  # bare 150 / 200 -> mm
        return v / 25.4
    return v


def member_of(text: str) -> Optional[str]:
    t = text.lower()
    for kind, pat in MEMBER_PATTERNS:
        if re.search(pat, t):
            return kind
    return None


def parse_callouts(text: str):
    """-> (long Bars or None, [Spaced ...], both_ways)."""
    long_bars = None
    spaced: List[Spaced] = []
    t = text.replace("\u2013", "-")
    for m in SPACED_RE.finditer(t):
        size = _size(m, 1, 2, 3)
        sp = _spacing_in(m.group(4), m.group(5) or "")
        if not 2 <= sp <= 24:
            continue
        ctx = t[max(0, m.start() - 25): m.end() + 30].lower()
        role = ("ties" if re.search(r"ring|stirrup|tie|link", ctx) else
                "distribution" if "distribution" in ctx or "dist" in ctx else "main" if "main" in ctx else "mesh")
        spaced.append(Spaced(size, sp, role))
    t_wo = SPACED_RE.sub(" ", t)
    for m in LONG_RE.finditer(t_wo):
        n = int(m.group(1))
        if 2 <= n <= 24:
            long_bars = Bars(n, _size(m, 2, 3, 4))
            break
    both = bool(re.search(r"both\s*ways|each\s*way|b\.?\s*w\.?\b|both\s*directions", t, re.I))
    return long_bars, spaced, both


def _ftin(text: str) -> List[float]:
    out = []
    for m in re.finditer(FTIN_RE, text):
        out.append(float(m.group(1)) + float(m.group(2) or 0) / 12.0)
    return out


def parse_sizes(kind: str, text: str, spec: MemberSpec) -> None:
    t = text.lower()
    if spec.volume_cft is None:
        m = re.search(r"(?:=\s*)?(\d+(?:\.\d+)?)\s*(m3|m\u00b3|cum|cu\.?\s*m|cft|cu\.?\s*ft)\b", t)
        if m and "+" not in t[max(0, m.start() - 12):m.start()]:
            v = float(m.group(1))
            spec.volume_cft = v * 35.3147 if m.group(2).startswith(("m", "cu")) and "ft" not in m.group(2) else v
    # number of members: "16 x C1", "16 Nos", "Column C1 (16)"
    if spec.count is None and kind in ("column", "footing"):
        m = (re.search(r"\b(\d{1,3})\s*x\s*(?:c|f)\d", t) or re.search(r"\b(\d{1,3})\s*nos\b", t)
             or re.search(r"(?:c|f)\d\s*\((\d{1,3})\)", t))
        if m and 1 <= int(m.group(1)) <= 200:
            spec.count = int(m.group(1))
    if kind == "column" and spec.size_in is None:
        m = re.search(r"~\s*(\d+(?:\.\d+)?)\s*in\b", t) or re.search(r"(\d+(?:\.\d+)?)\s*(?:in|\")\s*sq", t)
        if m:
            v = float(m.group(1))
            spec.size_in = (v, v)
        else:
            m = re.search(r"(\d+(?:\.\d+)?)\s*(?:in|\")\s*[x×]\s*(\d+(?:\.\d+)?)\s*(?:in|\")", t)
            if m:
                spec.size_in = (float(m.group(1)), float(m.group(2)))
            else:
                m = re.search(r"(\d{3})\s*[x×]\s*(\d{3})\s*mm", t)
                if m:
                    spec.size_in = (float(m.group(1)) / 25.4, float(m.group(2)) / 25.4)
    if kind == "footing" and spec.size_in is None:
        ft = _ftin(text)
        if len(ft) >= 2 and 2 <= ft[0] <= 15 and 2 <= ft[1] <= 15:
            spec.size_in = (ft[0] * 12, ft[1] * 12)
        else:
            m = re.search(r"(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)\s*\(?\s*ft", t)
            if m and 2 <= float(m.group(1)) <= 15:
                spec.size_in = (float(m.group(1)) * 12, float(m.group(2)) * 12)
    if kind in ("plinth", "fdn_tie", "lintel", "roof_band", "beam") and spec.width_in is None:
        m = re.search(r"\b(\d{1,2}(?:\.\d+)?)\s*(?:in|\")\s*(?:wide|width|x)", t) or re.fullmatch(r"\s*(\d{1,2})\s*in\s*", t)
        if m and 4 <= float(m.group(1)) <= 24:
            spec.width_in = float(m.group(1))


# ---------------------------------------------------------------------------
# page layout -> segments
# ---------------------------------------------------------------------------
@dataclass
class Seg:
    text: str
    x0: float
    x1: float
    y: float


def page_segments(page, gap: float = 28.0) -> List[Seg]:
    words = page.get_text("words")
    rows: List[list] = []
    for w in sorted(words, key=lambda w: (round(w[1]), w[0])):
        if rows and abs(rows[-1][0] - w[1]) <= 3:
            rows[-1][1].append(w)
        else:
            rows.append([w[1], [w]])
    segs: List[Seg] = []
    for y, ws in rows:
        ws.sort(key=lambda w: w[0])
        cur = [ws[0]]
        for w in ws[1:]:
            if w[0] - cur[-1][2] > gap:
                segs.append(Seg(" ".join(c[4] for c in cur), cur[0][0], cur[-1][2], y))
                cur = [w]
            else:
                cur.append(w)
        segs.append(Seg(" ".join(c[4] for c in cur), cur[0][0], cur[-1][2], y))
    return segs


def _merge(dst: MemberSpec, long_bars, spaced, both, src: str) -> None:
    if long_bars and not dst.long_bars:
        dst.long_bars = long_bars
    for s in spaced:
        if s.role == "ties" or (dst.kind in ("column", "plinth", "fdn_tie", "lintel", "roof_band", "beam") and s.role == "mesh"):
            if not dst.ties:
                dst.ties = Spaced(s.size, s.spacing_in, "ties")
        elif dst.kind in ("slab", "footing", "tank", "stair"):
            if all(not (m.size == s.size and m.spacing_in == s.spacing_in and m.role == s.role) for m in dst.mesh):
                dst.mesh.append(s)
    dst.both_ways = dst.both_ways or both
    if src and src not in dst.source:
        dst.source = (dst.source + "; " + src).strip("; ")


def read_rebar(pages, source_name: str = "") -> RebarFacts:
    """pages: PyMuPDF pages (any sheets - only reinforcement-looking text is used)."""
    facts = RebarFacts()
    for pno, page in enumerate(pages, 1):
        segs = page_segments(page)
        src = f"{source_name} p{pno}".strip()
        full = " ".join(s.text for s in sorted(segs, key=lambda s: (s.y, s.x0)))
        _read_bbs(segs, facts, src)
        # total steel printed on the drawings
        m = re.search(r"total\s+steel.{0,160}?([\d,]+(?:\.\d+)?)\s*(lbs?|kgs?|tons?|tonnes?|mt)\b", full, re.I | re.S)
        if m and facts.stated_total_kg is None:
            v = float(m.group(1).replace(",", ""))
            u = m.group(2).lower()
            kg = v * KG_PER_LB if u.startswith("lb") else v * 1000 if u.startswith(("ton", "mt")) else v
            if 50 < kg < 500000:
                facts.stated_total_kg, facts.stated_total_text = kg, f"{m.group(1)} {m.group(2)} ({src})"
        # rows that name a member AND carry bars (schedule tables, notes); rows with bars only -> nearest heading above
        heads = [(s, member_of(s.text)) for s in segs]
        row_text: Dict[float, List[Seg]] = {}
        for s in segs:
            row_text.setdefault(round(s.y), []).append(s)
        for s, kind in heads:
            long_bars, spaced, both = parse_callouts(s.text)
            if not (long_bars or spaced):
                if kind:
                    spec = facts.members.setdefault(kind, MemberSpec(kind))
                    parse_sizes(kind, s.text, spec)
                continue
            k = kind
            if k is None:  # same table row: a member name in another cell of this row
                row = sorted(row_text.get(round(s.y), []), key=lambda z: z.x0)
                k = next((member_of(z.text) for z in row if z.x0 < s.x0 and member_of(z.text)), None)
            if k is None:  # detail drawing: the nearest heading above, overlapping in x
                above = [(h, kk) for h, kk in heads if kk and h.y < s.y and s.y - h.y < 220
                         and not (h.x1 < s.x0 - 40 or h.x0 > s.x1 + 40)]
                if above:
                    k = max(above, key=lambda hk: hk[0].y)[1]
            if k is None:
                continue
            spec = facts.members.setdefault(k, MemberSpec(k))
            _merge(spec, long_bars, spaced, both, src)
            parse_sizes(k, s.text, spec)
        for s, kind in heads:  # sizes / counts in any row of that member, incl. the other cells of a table row
            if kind:
                spec = facts.members.setdefault(kind, MemberSpec(kind))
                parse_sizes(kind, s.text, spec)
                row = sorted(row_text.get(round(s.y), []), key=lambda z: z.x0)
                nxt = next((z.x0 for z in row if z.x0 > s.x0 and member_of(z.text)), 1e9)
                for z in row:
                    if s.x0 < z.x0 < nxt and spec.volume_cft is None:
                        parse_sizes(kind, z.text, spec)
    facts.members = {k: v for k, v in facts.members.items() if v.has_detail() or v.count or v.size_in}
    return facts


def _read_bbs(segs: List[Seg], facts: RebarFacts, src: str) -> None:
    """Bar bending schedule: a header row with 'mark' and 'dia/size' and 'length'; rows below it."""
    rows: Dict[int, List[Seg]] = {}
    for s in segs:
        rows.setdefault(round(s.y), []).append(s)
    ys = sorted(rows)
    for i, y in enumerate(ys):
        head = " ".join(z.text for z in sorted(rows[y], key=lambda z: z.x0)).lower()
        if not ("mark" in head and re.search(r"dia|size", head) and "length" in head):
            continue
        member = "beam"
        for y2 in ys[i + 1:]:
            line = " ".join(z.text for z in sorted(rows[y2], key=lambda z: z.x0))
            if not line.strip():
                break
            kind = member_of(line)
            if kind and not re.search(r"\d", line):  # section heading inside the table ("COLUMNS")
                member = kind
                continue
            m_size = re.search(_SIZE, line, re.I)
            if not m_size:
                if facts.bbs and y2 - ys[i] > 900:
                    break
                continue
            size = _size(m_size, 1, 2, 3)
            rest = line[m_size.end():]
            nums = [float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*(?:\.\d+)?", rest)]
            lens = _ftin(rest)
            wt = re.search(r"([\d,]+(?:\.\d+)?)\s*(kg|lbs?)\b", rest, re.I)
            if not nums:
                continue
            count = nums[0]
            length_ft = lens[0] if lens else (nums[1] * FT_PER_M if len(nums) > 1 and nums[1] < 30 else
                                              nums[1] / 304.8 if len(nums) > 1 else 0.0)
            weight = None
            if wt:
                weight = float(wt.group(1).replace(",", "")) * (KG_PER_LB if wt.group(2).lower().startswith("lb") else 1)
            facts.bbs.append(BBSRow(kind or member, size, count, length_ft, weight))
        if facts.bbs:
            facts.notes.append(f"Bar bending schedule read from {src} ({len(facts.bbs)} bar marks).")


# ---------------------------------------------------------------------------
# calculation
# ---------------------------------------------------------------------------
COVER_IN = {"column": 1.5, "beam": 1.5, "plinth": 1.5, "fdn_tie": 2.0, "lintel": 1.0, "roof_band": 1.0, "footing": 3.0, "slab": 0.75}
STOCK_FT = 40.0  # bars are bought ~12 m long -> one lap every 40 ft of run


@dataclass
class SteelLine:
    kind: str
    kg: float
    calc: str


def lap_factor(size: str, run_ft: float) -> float:
    if run_ft <= STOCK_FT:
        return 1.0
    lap_ft = 50 * bar_dia_in(size) / 12
    return 1.0 + lap_ft / STOCK_FT


def column_steel(spec: MemberSpec, n_cols: float, b_in: float, d_in: float, h_ft: float, storeys: int) -> SteelLine:
    c = COVER_IN["column"]
    parts, kg = [], 0.0
    if spec.long_bars:
        lb = spec.long_bars
        dia = bar_dia_in(lb.size)
        L = h_ft + 1.5 + max(storeys - 1, 0) * 50 * dia / 12  # bend into footing + laps at each floor
        w = n_cols * lb.count * L * kg_per_ft(lb.size)
        kg += w
        parts.append(f"{n_cols:g} cols x {lb.count}-{lb.size} x {L:.1f} ft = {w:,.0f} kg")
    if spec.ties:
        t = spec.ties
        dt = bar_dia_in(t.size)
        n = h_ft * 12 / t.spacing_in + 1
        tie_ft = (2 * ((b_in - 2 * c) + (d_in - 2 * c)) + 2 * 10 * dt) / 12
        w = n_cols * n * tie_ft * kg_per_ft(t.size)
        kg += w
        parts.append(f"ties {t.size} @ {t.spacing_in:g} in: {n_cols:g} x {n:.0f} x {tie_ft:.2f} ft = {w:,.0f} kg")
    return SteelLine("column", kg, "; ".join(parts) + f" (column {b_in:.0f}x{d_in:.0f} in, {h_ft:.1f} ft high)")


def footing_steel(spec: MemberSpec, n: float, L_ft: float, B_ft: float, D_ft: float) -> SteelLine:
    c = COVER_IN["footing"] / 12
    kg, parts = 0.0, []
    meshes = spec.mesh or []
    if not meshes:
        return SteelLine("footing", 0.0, "")
    dirs = [(meshes[0], L_ft, B_ft), ((meshes[1] if len(meshes) > 1 else meshes[0]), B_ft, L_ft)] \
        if (spec.both_ways or len(meshes) > 1) else [(meshes[0], L_ft, B_ft)]
    for m, span, across in dirs:
        nb = (across - 2 * c) * 12 / m.spacing_in + 1
        bar = span - 2 * c + 2 * max(D_ft - 2 * c, 0.25)  # bent up at both ends
        w = n * nb * bar * kg_per_ft(m.size)
        kg += w
        parts.append(f"{m.size} @ {m.spacing_in:g} in: {n:g} footings x {nb:.0f} bars x {bar:.2f} ft = {w:,.0f} kg")
    return SteelLine("footing", kg, "; ".join(parts) + f" (footing {L_ft:.2f} x {B_ft:.2f} ft)")


def linear_steel(kind: str, spec: MemberSpec, run_ft: float, b_in: float, d_in: float) -> SteelLine:
    c = COVER_IN.get(kind, 1.5)
    kg, parts = 0.0, []
    if run_ft <= 0:
        return SteelLine(kind, 0.0, "")
    if spec.long_bars:
        lb = spec.long_bars
        L = run_ft * lap_factor(lb.size, run_ft) * 1.02  # + corner/end anchorages
        w = lb.count * L * kg_per_ft(lb.size)
        kg += w
        parts.append(f"{lb.count}-{lb.size} x {L:,.0f} ft = {w:,.0f} kg")
    if spec.ties:
        t = spec.ties
        dt = bar_dia_in(t.size)
        n = run_ft * 12 / t.spacing_in + 1
        ring = (2 * ((b_in - 2 * c) + (d_in - 2 * c)) + 2 * 10 * dt) / 12
        w = n * ring * kg_per_ft(t.size)
        kg += w
        parts.append(f"rings {t.size} @ {t.spacing_in:g} in: {n:,.0f} x {ring:.2f} ft = {w:,.0f} kg")
    return SteelLine(kind, kg, "; ".join(parts) + f" (run {run_ft:,.0f} ft, section {b_in:.0f}x{d_in:.0f} in)")


def slab_steel(spec: MemberSpec, area_sft: float) -> SteelLine:
    if not spec.mesh or area_sft <= 0:
        return SteelLine("slab", 0.0, "")
    mains = [m for m in spec.mesh if m.role in ("main", "mesh")] or spec.mesh[:1]
    dists = [m for m in spec.mesh if m.role == "distribution"]
    main = mains[0]
    dist = dists[0] if dists else (main if spec.both_ways or len(spec.mesh) == 1 else spec.mesh[-1])
    kg, parts = 0.0, []
    for lab, m in (("main", main), ("distribution", dist)):
        ft = area_sft * 12 / m.spacing_in * 1.12  # cranks, laps, edge anchorage
        w = ft * kg_per_ft(m.size)
        kg += w
        parts.append(f"{lab} {m.size} @ {m.spacing_in:g} in: {ft:,.0f} ft = {w:,.0f} kg")
    return SteelLine("slab", kg, "; ".join(parts) + f" over {area_sft:,.0f} sft (incl. 12% for cranks & laps)")


def bbs_by_kind(facts: RebarFacts) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for r in facts.bbs:
        out[r.member] = out.get(r.member, 0.0) + r.kg
    return out
