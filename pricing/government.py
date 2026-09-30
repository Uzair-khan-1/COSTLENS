"""
Government-rate estimate (as used for PC-Is and engineer's estimates).

Sources
-------
* Punjab MRS (Market Rate System), District Rawalpindi, 2nd Bi-Annual 2024 - imported from the Finance
  Department PDF by pricing/mrs.py (labour + composite rates for every item).
* Balochistan CSR-2026 (Composite Schedule of Rates) - the rates quoted in two real CSR-2026 engineer's
  estimates (Staff Quarter, Trauma Centre Khuzdar; DSP Residence, Loralai). Used for Quetta.

Bringing an old MRS to today
----------------------------
    composite_today = labour x labour_factor + (composite - labour) x material_factor
labour_factor   - wage increase since the MRS edition (default +20%, editable)
material_factor - today's rate book / the MRS-period prices of a basket of main materials (cement, steel,
                  bricks, sand, crush), weighted by their share of a typical house.
When a newer MRS is imported, its edition date is used and the factors fall back towards 1.0.

Each BOQ work item is matched to MRS items (MRS_MAP). Items without a match are priced from the market
cost of the same work item and flagged as such - nothing is left out silently.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from pricing.base_rates import city_key
from pricing.mrs import load_all

RATES_DIR = Path(__file__).resolve().parent.parent / "data" / "rates"
CWT_KG = 50.8
CUM_CFT = 35.3147
SQM_SFT = 10.7639

# ---- MRS item(s) per BOQ work item: [(key "chapter-item-sub", multiplier from the MRS unit to the WI unit)]
_C100 = 1 / 100.0  # per 100 cft / 100 sft -> per cft / sft
MRS_MAP: Dict[str, List[Tuple[str, float]]] = {
    "WI-EW-01": [("3-7-i", 1 / 1000.0)], "WI-EW-02": [("3-7-i", 1 / 1000.0)], "WI-EW-03": [("3-8-i", 1 / 1000.0)],
    "WI-EW-04": [("3-15-i", 1 / 1000.0)], "WI-EW-05": [("3-15-ii", 1 / 1000.0)],
    "WI-CN-01": [("6-5-i", _C100)], "WI-CN-02": [("6-5-i", _C100)],
    "WI-CN-03": [("6-5-f", _C100)], "WI-CN-04": [("6-5-f", _C100)], "WI-CN-05": [("6-5-f", _C100)],
    "WI-CN-06": [("6-5-f", _C100)], "WI-CN-07": [("6-5-f", _C100)], "WI-CN-08": [("6-5-f", _C100)],
    "WI-CN-09": [("6-5-f", _C100)], "WI-CN-10": [("6-5-f", _C100)], "WI-CN-11": [("6-5-f", _C100)],
    "WI-CN-12": [("6-36-i", _C100)],
    **{f"WI-RF-0{i}": [("6-12-ii", 1 / CWT_KG)] for i in range(1, 8)},
    "WI-MS-01": [("7-4-i.4", _C100)], "WI-MS-02": [("7-5-i.4", _C100)], "WI-MS-04": [("7-5-i.4", _C100)],
    "WI-MS-03": [("7-5-i.2", _C100 * 0.375)],  # 4.5 in wall: 0.375 cft per sft
    "WI-PL-01": [("11-9-b", _C100)], "WI-PL-02": [("11-9-c", _C100)], "WI-PL-03": [("11-10-c", _C100)],
    "WI-WP-01": [("9-5-", _C100), ("9-10-b", _C100), ("13-9-i", _C100)],
    "WI-FL-01": [("10-46-ii", 1.0)], "WI-FL-02": [("10-24-i", 1.0)], "WI-FL-03": [("10-25-i", 1.0)],
    "WI-FL-04": [("10-48-i", 1.0)], "WI-FL-07": [("10-45-b", 1.0)],
    "WI-PT-01": [("13-46-", _C100), ("13-31-a", _C100), ("13-31-b", _C100)],
    "WI-PT-02": [("13-46-", _C100), ("13-31-a", _C100), ("13-31-b", _C100)],
    "WI-PT-03": [("13-33-i", _C100), ("13-33-ii", _C100)],
    "WI-PB-01": [("19-3-", 1.0)],
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

# Other cities while their own MRS is not imported: multiplier on the (updated) Rawalpindi MRS
GOV_CITY_FACTOR = {"Rawalpindi": 1.00, "Islamabad": 1.03, "Lahore": 0.98, "Karachi": 1.05, "Peshawar": 1.00, "Quetta": 1.05}

# Market prices in the period of the Rawalpindi MRS 2nd Bi-Annual 2024 (Jul-Dec 2024), per database unit -
# used only to measure how much material prices moved since then. Weights = share in a typical house.
MRS_PERIOD_BASKET = {  # mat_id: (price then, weight)
    "CON-001": (1420.0, 0.30), "RBR-002": (262.0, 0.30), "MAS-001": (16.0, 0.20), "CON-004": (125.0, 0.10), "CON-006": (185.0, 0.10),
}


BASKET_NAMES = {"CON-001": "cement", "RBR-002": "steel", "MAS-001": "bricks", "CON-004": "sand", "CON-006": "crush"}


@dataclass
class UpdateFactors:
    labour: float = 1.20
    material: float = 1.00
    basis: str = ""


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
    mapped_share: float = 0.0  # share of the subtotal priced from MRS/CSR items (rest: market fallback)
    extras: List[Tuple[str, float]] = field(default_factory=list)
    total: float = 0.0
    edition: str = ""


_MRS_CACHE: Dict[str, object] = {}


def mrs_index() -> Dict[str, dict]:
    """Imported MRS editions (cached until a file in data/rates changes)."""
    stamp = tuple(sorted((p.name, p.stat().st_mtime) for p in Path(RATES_DIR).glob("mrs_*.json")))
    if _MRS_CACHE.get("stamp") != stamp:
        _MRS_CACHE["stamp"], _MRS_CACHE["data"] = stamp, load_all(RATES_DIR)
    return _MRS_CACHE["data"]  # type: ignore[return-value]


def update_factors(book, labour_factor: float = 1.20) -> UpdateFactors:
    """Material factor from today's rate book vs the MRS-period basket."""
    num = den = 0.0
    parts = []
    for mid, (then, w) in MRS_PERIOD_BASKET.items():
        now = book.rate(mid, "Rawalpindi").rate
        if then > 0 and now > 0:
            num += w * now / then
            den += w
            parts.append(f"{BASKET_NAMES.get(mid, mid)} {now / then - 1:+.0%}")
    mf = num / den if den else 1.0
    return UpdateFactors(labour_factor, mf, "materials " + ", ".join(parts))


def _items_by_key(mrs: dict) -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    for it in mrs.get("items", []):
        k = f"{it['chapter']}-{it['item_no']}-{it['sub']}"
        out.setdefault(k, it)  # first occurrence (British-unit table)
    return out


def gov_rate(wi_id: str, city: str, uf: UpdateFactors, mrs_cache: Dict[str, dict]) -> Optional[GovRate]:
    c = city_key(city)
    if c == "Quetta" and wi_id in CSR_BAL_2026:
        rate, item, src = CSR_BAL_2026[wi_id]
        return GovRate(rate, rate * 0.25, f"Balochistan {src}", f"CSR item {item}")
    rw = mrs_cache.get("Rawalpindi")
    if not rw or wi_id not in MRS_MAP:
        return None
    idx = rw.setdefault("_idx", _items_by_key(rw))
    comp = lab = 0.0
    keys = []
    for key, mult in MRS_MAP[wi_id]:
        it = idx.get(key)
        if it is None or (it.get("composite") is None and it.get("labour") is None):
            return None
        L = float(it.get("labour") or 0.0)
        C = float(it["composite"]) if it.get("composite") is not None else L  # labour-only items
        comp += (L * uf.labour + (C - L) * uf.material) * mult
        lab += L * uf.labour * mult
        keys.append(key)
    f = GOV_CITY_FACTOR.get(c, 1.0)
    return GovRate(comp * f, lab * f, f"Punjab MRS Rawalpindi {rw['edition']} updated to today"
                   + ("" if c == "Rawalpindi" else f", x{f:g} for {c}"), "MRS item " + " + ".join(keys))


def government_estimate(res, city: str, uf: UpdateFactors, market_wi_cost: Dict[str, float],
                        bst_pct: float = 4.0, consultancy_pct: float = 1.0, contingency_pct: float = 1.0,
                        loose_materials: float = 0.0) -> GovEstimate:
    """Engineer's-estimate style: BOQ qty x composite rate (+ BST, consultancy, contingency)."""
    cache = mrs_index()
    est = GovEstimate(edition=(cache.get("Rawalpindi") or {}).get("edition", ""))
    mapped = 0.0
    for w in res.scoped_work_items():
        if w.qty <= 0 or w.status in ("Option - not included", "Not required"):
            continue
        g = gov_rate(w.wi_id, city, uf, cache)
        if g is not None:
            amount = w.qty * g.composite
            mapped += amount
            src, rate = g.source, g.composite
        else:
            amount = market_wi_cost.get(w.wi_id, 0.0)
            rate = amount / w.qty if w.qty else 0.0
            src = "No government item - market cost of this work used"
        est.lines.append({"WI_ID": w.wi_id, "Description": w.description, "Unit": w.unit, "Quantity": round(w.qty, 2),
                          "Rate": round(rate, 2), "Amount": round(amount, 0), "Source": src,
                          "Item": g.detail if g else ""})
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
