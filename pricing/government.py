"""
Government-rate estimate (engineer's estimate / PC-I style) from the official rate books:

  Islamabad, Rawalpindi            Punjab MRS, District Rawalpindi (Finance Department, bi-annual)
  Lahore, Faisalabad, Multan       Punjab MRS, District Lahore
  Peshawar                         Khyber Pakhtunkhwa MRS (MRS Cell, Finance Department)
  Karachi                          Sindh Composite Schedule of Rates (Standing Rates Committee)
  Quetta                           Balochistan CSR-2026 rates quoted in two real CSR-2026 estimates
                                   (Khuzdar staff quarter, Loralai DSP residence); other items from Rawalpindi MRS +5%

Books are imported by pricing/mrs.py into data/rates/. Each BOQ work item is found in a book by its WORDING
(WI_SPECS: required patterns + unit), so new editions and other provinces work without renumbering.
Rates from an older edition are brought to today with factors per year since the edition:
labour +4%/year and materials +0%/year by default - measured from the two Rawalpindi editions
(2nd Bi-Annual 2024 -> 2nd Bi-Annual 2026, 1,874 identical items: labour +8%, material part -2%).
Work items without a government item are priced at their market cost and flagged.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from pricing.base_rates import city_key
from pricing.mrs import load_all

RATES_DIR = Path(__file__).resolve().parent.parent / "data" / "rates"
CWT_KG = 50.8
CUM_CFT = 35.3147
SQM_SFT = 10.7639

CITY_BOOK = {"Islamabad": ("Rawalpindi", 1.00), "Rawalpindi": ("Rawalpindi", 1.00), "Lahore": ("Lahore", 1.00),
             "Peshawar": ("Peshawar", 1.00), "Karachi": ("Karachi", 1.00), "Quetta": ("Rawalpindi", 1.05)}

_EXCL = (r"dismantl|repair|\bold\b|extra (?:for|labour|cost|over|on)|add(?:ing)? extra|deduct|cleaning|removing|re-?lay|"
         r"\bpiles?\b|culvert|canal|weir|barrage|sewer|manhole|road|pavement|lining|\bwells?\b|syphon|tunnel|"
         r"spout|carriage|stack|sub-?soil|below water|sedimentation|filter bed|hydraulic|\bdams?\b|"
         r"jack arch|rubble|stone masonry|mud mortar|kankar|perforated|honey ?comb|underpinning|tube ?well|"
         r"false ceiling|plaster of paris|collapsible|\bgates?\b")
# WI: list of alternatives, each (required regexes, unit base, multiplier on top of the unit conversion) - first match wins
_R124 = r"1\s*:\s*2\s*:\s*4"
_RCC = r"r\.?\s?c\.?\s?c\b|reinforced cement concrete|reinforced concrete"
_NOEX = r"shingle|gravel|rock|blasting|ballast"
_EXC = [([r"excavat", r"foundation", r"build", r"ordinary"], "cft", 1.0, _NOEX), ([r"excavat", r"foundation", r"build"], "cft", 1.0, _NOEX),
        ([r"excavat", r"foundation"], "cft", 1.0, _NOEX)]
_BRICK = r"brick\s*work|pacca brick|burnt brick|1st class brick"
WI_SPECS: Dict[str, list] = {
    "WI-EW-01": _EXC, "WI-EW-02": _EXC, "WI-EW-03": _EXC,
    "WI-EW-04": [([r"fill", r"under floor", r"surplus|excavated"], "cft", 1.0), ([r"fill", r"surplus"], "cft", 1.0)],
    "WI-EW-05": [([r"fill", r"under floor", r"new earth|from outside|borrow"], "cft", 1.0),
                 ([r"fill", r"new earth|from outside|borrow"], "cft", 1.0)],
    "WI-CN-01": [([r"concrete", r"plain|p\.?c\.?c", r"1\s*:\s*4\s*:\s*8"], "cft", 1.0, r"ballast|precast|block"),
                 ([r"concrete", r"1\s*:\s*4\s*:\s*8"], "cft", 1.0, r"precast|block|ballast")],
    "WI-CN-02": [([r"concrete", r"plain|p\.?c\.?c", r"1\s*:\s*4\s*:\s*8"], "cft", 1.0, r"ballast|precast|block"),
                 ([r"concrete", r"1\s*:\s*4\s*:\s*8"], "cft", 1.0, r"precast|block|ballast")],
    **{w: [([_RCC, r"slab|beam|column", _R124], "cft", 1.0, r"raft|piles?\b|block|kerb|precast (?:units|slab)"),
           ([_RCC, _R124], "cft", 1.0, r"block|kerb"), ([r"concrete", r"plain", _R124], "cft", 1.0, r"block|kerb|ballast")]
       for w in ("WI-CN-03", "WI-CN-04", "WI-CN-05", "WI-CN-06", "WI-CN-07", "WI-CN-08", "WI-CN-09", "WI-CN-10", "WI-CN-11")},
    "WI-CN-12": [([r"damp\s*-?\s*proof|d\.?\s?p\.?\s?c", r"concrete|1\s*:\s*2\s*:\s*4"], "sft", 1.0)],
    **{f"WI-RF-0{i}": [([r"reinforcement|tor steel|deformed", r"fabricat|cutting|bending|bind", r"deformed|grade[- ]?60|tor"], "kg", 1.0),
                       ([r"reinforcement", r"fabricat|cutting|bending|bind"], "kg", 1.0)] for i in range(1, 8)},
    "WI-MS-01": [([_BRICK, r"foundation|plinth", r"cement,?\s*sand\s*(?:-\s*)?mortar", r"1\s*:\s*6(?!\s*:)"], "cft", 1.0, r"lime|surkhi|mud")],
    "WI-MS-02": [([_BRICK, r"ground floor|super\s*-?structure", r"cement,?\s*sand\s*(?:-\s*)?mortar", r"1\s*:\s*6(?!\s*:)"], "cft", 1.0, r"lime|surkhi|mud")],
    "WI-MS-04": [([_BRICK, r"ground floor|super\s*-?structure", r"cement,?\s*sand\s*(?:-\s*)?mortar", r"1\s*:\s*6(?!\s*:)"], "cft", 1.0, r"lime|surkhi|mud")],
    "WI-MS-03": [([_BRICK, r"ground floor|super\s*-?structure", r"cement,?\s*sand\s*(?:-\s*)?mortar", r"1\s*:\s*4(?!\s*:)"], "cft", 0.375, r"lime|surkhi|mud")],
    "WI-PL-01": [([r"^cement (?:sand )?plaster|cement plaster 1\s*:\s*4", r"1\s*:\s*4", r"½|1/2\s*\"|13\s*mm|12\s*mm"], "sft", 1.0)],
    "WI-PL-02": [([r"^cement (?:sand )?plaster|cement plaster 1\s*:\s*4", r"1\s*:\s*4", r"¾|3/4\s*\"|20\s*mm|19\s*mm"], "sft", 1.0)],
    "WI-PL-03": [([r"cement (?:sand )?plaster", r"soffit", r"1\s*:\s*[34]"], "sft", 1.0),
                 ([r"cement (?:sand )?plaster", r"soffit|ceiling"], "sft", 1.0)],
    "WI-WP-01": [([r"tile roofing|tiles?", r"roof", r"earth", r"mud"], "sft", 1.0)],
    "WI-FL-01": [([r"porcelain", r"floor"], "sft", 1.0), ([r"porcelain", r"tile"], "sft", 1.0)],
    "WI-FL-02": [([r"ceramic", r"floor"], "sft", 1.0), ([r"glazed tile|ceramic tile", r"floor"], "sft", 1.0)],
    "WI-FL-03": [([r"ceramic|glazed tile", r"dado|wall"], "sft", 1.0)],
    "WI-FL-04": [([r"marble", r"floor"], "sft", 1.0, r"mosaic|chips|powder|terrazzo|skirting|strip")],
    "WI-FL-07": [([r"tuff|paver"], "sft", 1.0)],
    "WI-PT-01": [([r"plastic emulsion", r"3 coats|three coats"], "sft", 1.0), ([r"plastic emulsion", r"first coat|1st coat"], "sft", 3.0),
                 ([r"emulsion", r"first coat|1st coat"], "sft", 3.0), ([r"emulsion"], "sft", 1.0, r"distemper")],
    "WI-PT-02": [([r"plastic emulsion", r"3 coats|three coats"], "sft", 1.0), ([r"plastic emulsion", r"first coat|1st coat"], "sft", 3.0),
                 ([r"emulsion", r"first coat|1st coat"], "sft", 3.0), ([r"emulsion"], "sft", 1.0, r"distemper")],
    "WI-PT-03": [([r"weather\s*(?:shield|coat)", r"first coat|1st coat"], "sft", 2.0), ([r"weather\s*(?:shield|coat)"], "sft", 1.0)],
    "WI-PT-04": [([r"^(?:\(?[a-z0-9]{1,3}\)\s*)?(?:preparing|painting|paint|applying)", r"enamel|synthetic", r"steel|iron|metal|grill"],
                  "sft", 1.0), ([r"painting", r"enamel"], "sft", 1.0)],
    "WI-PB-01": [([r"water closet|w\.\s?c\.?", r"european|commode"], "nos", 1.0)],
}

# ---- Balochistan CSR-2026 rates quoted in the two real estimates, per WI unit (rate, CSR item, source)
_KHZ = "CSR-2026 (Khuzdar quarter estimate)"
CSR_BAL_2026: Dict[str, Tuple[float, str, str]] = {
    "WI-EW-01": (662.16 / CUM_CFT, "3-21-a/iv", _KHZ), "WI-EW-02": (662.16 / CUM_CFT, "3-21-a/iv", _KHZ),
    "WI-EW-03": (662.16 / CUM_CFT, "3-21-a/iv", _KHZ), "WI-EW-04": (296.69 / CUM_CFT, "3-16-a", _KHZ),
    "WI-EW-05": (360.83 / CUM_CFT, "3-16-b", _KHZ),
    "WI-CN-01": (12247.53 / CUM_CFT, "5-4-b", _KHZ), "WI-CN-02": (15090.08 / CUM_CFT, "14-1-b", _KHZ),
    "WI-CN-03": (18906.78 / CUM_CFT, "5-8-c", _KHZ), "WI-CN-04": (20538.84 / CUM_CFT, "5-49-a", _KHZ),
    "WI-CN-05": (22238.94 / CUM_CFT, "5-15-c", _KHZ), "WI-CN-06": (21778.14 / CUM_CFT, "5-16-a", _KHZ),
    "WI-CN-07": (22200.54 / CUM_CFT, "5-17-a/i", _KHZ), "WI-CN-08": (22200.54 / CUM_CFT, "5-17-a/i", _KHZ),
    "WI-CN-09": (21012.33 / CUM_CFT, "5-49-b", _KHZ), "WI-CN-10": (21778.14 / CUM_CFT, "5-16-a", _KHZ),
    "WI-CN-12": (428.46 / SQM_SFT, "8-1-a", _KHZ),
    **{f"WI-RF-0{i}": (317314.80 / 1000.0, "5-65-a", _KHZ) for i in range(1, 8)},
    "WI-MS-01": (15475.18 / CUM_CFT, "9-2-d (block)", _KHZ), "WI-MS-02": (16997.03 / CUM_CFT, "9-7-ii (block)", _KHZ),
    "WI-MS-04": (19572.08 / CUM_CFT, "9-7-ii+9-10", _KHZ),
    "WI-PL-01": (614.10 / SQM_SFT, "15-4-iii", _KHZ), "WI-PL-02": (614.10 / SQM_SFT, "15-4-iii", _KHZ),
    "WI-PL-03": (551.06 / SQM_SFT, "15-1-a/iii", _KHZ),
    "WI-FL-02": (2299.12 / SQM_SFT, "14-64-a", _KHZ), "WI-FL-03": (2299.12 / SQM_SFT, "14-64-a", _KHZ),
    "WI-PT-01": (405.64 / SQM_SFT, "17-67-1", _KHZ), "WI-PT-02": (405.64 / SQM_SFT, "17-67-1", _KHZ),
    "WI-PT-03": (533.31 / SQM_SFT, "17-69-1", _KHZ), "WI-PT-04": (727.56 / SQM_SFT, "17-7-1", _KHZ),
    "WI-EL-01": (11441.76, "30-2-a", _KHZ), "WI-EL-03": (3989.04, "30-8-a", _KHZ),
    "WI-PB-01": (8824.80, "23-3-a", _KHZ), "WI-PB-02": (40917.60, "23-5-c/d", _KHZ), "WI-PB-05": (1293.60, "23-9-b", _KHZ),
    "WI-PB-12": (18838.36, "25-4-a", _KHZ), "WI-PB-13": (11391.09, "25-2-a", _KHZ),
}


@dataclass
class UpdateFactors:
    labour_pct_year: float = 4.0
    material_pct_year: float = 0.0
    basis: str = "Punjab MRS 2024-2 -> 2026-2, 1,874 identical items: labour +8%, materials -2% over two years"


@dataclass
class GovRate:
    composite: float  # per WI unit, updated to today
    labour: float
    source: str
    detail: str = ""


@dataclass
class GovEstimate:
    lines: List[dict] = field(default_factory=list)
    subtotal: float = 0.0
    mapped_share: float = 0.0
    extras: List[Tuple[str, float]] = field(default_factory=list)
    total: float = 0.0
    edition: str = ""
    book: str = ""


# ---------------------------------------------------------------------------
# books
# ---------------------------------------------------------------------------
_MRS_CACHE: Dict[str, object] = {}


def mrs_index() -> Dict[str, dict]:
    """Imported books by district (latest edition), cached until a file in data/rates changes."""
    stamp = tuple(sorted((p.name, p.stat().st_mtime) for p in Path(RATES_DIR).glob("mrs_*.json")))
    if _MRS_CACHE.get("stamp") != stamp:
        _MRS_CACHE["stamp"], _MRS_CACHE["data"], _MRS_CACHE["found"] = stamp, load_all(RATES_DIR), {}
    return _MRS_CACHE["data"]  # type: ignore[return-value]


def edition_age_years(book: dict, today: Optional[date] = None) -> float:
    """Years between the middle of the edition's validity and today (0 for the current edition)."""
    today = today or date.today()
    ed = str(book.get("edition", ""))
    m = re.match(r"(\d{4})-(\d)", ed)
    if m:
        y, half = int(m.group(1)), int(m.group(2))
        mid = date(y, 4 if half == 1 else 10, 1)
        end = date(y, 6 if half == 1 else 12, 30)
    elif re.match(r"\d{4}$", ed):
        mid = end = date(int(ed), 6, 1)
    else:
        return 0.0
    if today <= end:
        return 0.0
    return (today - mid).days / 365.25


def unit_multiplier(unit: str, base: str) -> Optional[float]:
    """Book unit ("100 Cft.", "P.Sft", "Per Cwt.", "% Cft", "Each") -> multiplier giving the rate per WI base unit."""
    u = (unit or "").lower().replace(",", ".").strip()
    if not u:
        return None
    n = 1.0
    m = re.match(r"^(\d+)\s*", u)
    if m:
        n = float(m.group(1))
    if u.startswith("%"):
        n = 100.0
    if re.search(r"c\.?\s?ft|cft|cubic f", u):
        b = "cft"
    elif re.search(r"s\.?\s?ft|sft|sq\.?\s?f|square f", u):
        b = "sft"
    elif re.search(r"r\.?\s?ft|rft|running f", u):
        b = "rft"
    elif "cwt" in u:
        return (1.0 / (n * CWT_KG)) if base == "kg" else None
    elif re.search(r"ton", u):
        return (1.0 / (n * 1000.0)) if base == "kg" else None
    elif re.search(r"\bkg", u):
        b = "kg"
    elif re.search(r"each|no\b|nos|number|p\.?\s?no", u):
        b = "nos"
    else:
        return None
    return 1.0 / n if b == base else None


def find_item(book: dict, wi_id: str) -> Optional[Tuple[dict, float]]:
    """First item in the book (book order) whose wording matches the WI and whose unit converts."""
    cache = _MRS_CACHE.setdefault("found", {})
    key = (book.get("source"), book.get("edition"), wi_id)
    if key in cache:
        return cache[key]
    hit = None
    for spec in WI_SPECS.get(wi_id, []):
        must, base, extra = spec[0], spec[1], spec[2]
        neg = spec[3] if len(spec) > 3 else ""
        for it in book.get("items", []):
            d = it.get("description", "")
            if it.get("composite") is None and it.get("labour") is None:
                continue
            if re.search(_EXCL, d, re.I) or (neg and re.search(neg, d, re.I)) or not all(re.search(p, d, re.I) for p in must):
                continue
            mult = unit_multiplier(it.get("unit", ""), base)
            if mult is None:
                continue
            hit = (it, mult * extra)
            break
        if hit:
            break
    cache[key] = hit
    return hit


def update_factors(_book=None, labour_pct_year: float = 4.0, material_pct_year: float = 0.0) -> UpdateFactors:
    return UpdateFactors(labour_pct_year, material_pct_year)


def gov_rate(wi_id: str, city: str, uf: UpdateFactors, books: Optional[Dict[str, dict]] = None) -> Optional[GovRate]:
    c = city_key(city)
    if c == "Quetta" and wi_id in CSR_BAL_2026:
        rate, item, src = CSR_BAL_2026[wi_id]
        return GovRate(rate, rate * 0.25, f"Balochistan {src}", f"CSR item {item}")
    books = books if books is not None else mrs_index()
    district, f = CITY_BOOK.get(c, ("Rawalpindi", 1.0))
    book = books.get(district) or books.get("Rawalpindi")
    if not book:
        return None
    hit = find_item(book, wi_id)
    if hit is None:
        return None
    it, mult = hit
    age = edition_age_years(book)
    lf = (1 + uf.labour_pct_year / 100.0) ** age
    mf = (1 + uf.material_pct_year / 100.0) ** age
    L = float(it.get("labour") or 0.0)
    C = float(it["composite"]) if it.get("composite") is not None else L  # labour-only items
    comp = (L * lf + (C - L) * mf) * mult * f
    src = f"{book.get('book', 'MRS')} {book['district']} {book['edition']}"
    if age > 0.05:
        src += f", updated {age:.1f} yr to today"
    if f != 1.0:
        src += f", x{f:g} for {c}"
    return GovRate(comp, L * lf * mult * f, src, f"item {it.get('item_no')}{('-' + it['sub']) if it.get('sub') else ''} "
                   f"({it.get('unit')}): {it.get('description', '')[:90]}")


def government_estimate(res, city: str, uf: UpdateFactors, market_wi_cost: Dict[str, float],
                        bst_pct: float = 4.0, consultancy_pct: float = 1.0, contingency_pct: float = 1.0,
                        loose_materials: float = 0.0) -> GovEstimate:
    """Engineer's-estimate style: BOQ qty x composite rate (+ contingency, consultancy, BST)."""
    books = mrs_index()
    district, _f = CITY_BOOK.get(city_key(city), ("Rawalpindi", 1.0))
    book = books.get(district) or books.get("Rawalpindi") or {}
    est = GovEstimate(edition=str(book.get("edition", "")), book=f"{book.get('book', '')} {book.get('district', '')}".strip())
    if city_key(city) == "Quetta":
        est.book, est.edition = "Balochistan CSR-2026 (rates from real estimates) + Punjab MRS Rawalpindi", str(book.get("edition", ""))
    mapped = 0.0
    # does this book's RCC rate already include formwork / shuttering? (Punjab: "including forms, moulds, shuttering";
    # KP: "(Except Formwork)") - then the separate formwork items must not be charged again
    rcc = find_item(book, "WI-CN-07") if book else None
    fw_included = bool(rcc and re.search(r"forms|mould|shuttering|formwork|centering", rcc[0]["description"], re.I)
                       and not re.search(r"except\s+form|excluding\s+form|without\s+shutter", rcc[0]["description"], re.I))
    for w in res.scoped_work_items():
        if w.qty <= 0 or w.status in ("Option - not included", "Not required"):
            continue
        if fw_included and w.wi_id.startswith("WI-FW-") and city_key(city) != "Quetta":
            est.lines.append({"WI_ID": w.wi_id, "Description": w.description, "Unit": w.unit, "Quantity": round(w.qty, 2),
                              "Rate": 0.0, "Amount": 0.0, "Source": "Included in the RCC rate of this book", "Item": ""})
            continue
        g = gov_rate(w.wi_id, city, uf, books)
        if g is not None:
            amount = w.qty * g.composite
            mapped += amount
            src, rate = g.source, g.composite
        else:
            amount = market_wi_cost.get(w.wi_id, 0.0)
            rate = amount / w.qty if w.qty else 0.0
            src = "No government item - market cost of this work used"
        est.lines.append({"WI_ID": w.wi_id, "Description": w.description, "Unit": w.unit, "Quantity": round(w.qty, 2),
                          "Rate": round(rate, 2), "Amount": round(amount, 0), "Source": src, "Item": g.detail if g else ""})
        est.subtotal += amount
    if loose_materials > 0:
        est.lines.append({"WI_ID": "-", "Description": "Fittings & items supplied as units (not measured work items)",
                          "Unit": "LS", "Quantity": 1, "Rate": round(loose_materials, 0), "Amount": round(loose_materials, 0),
                          "Source": "Market prices", "Item": ""})
        est.subtotal += loose_materials
    est.mapped_share = mapped / est.subtotal if est.subtotal else 0.0
    for name, pct in (("Contingency", contingency_pct), ("Consultancy (design)", consultancy_pct), ("BST", bst_pct)):
        if pct:
            est.extras.append((f"{name} @ {pct:g}%", est.subtotal * pct / 100.0))
    est.total = est.subtotal + sum(v for _n, v in est.extras)
    return est
