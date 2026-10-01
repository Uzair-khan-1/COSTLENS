"""
Cost of the house at MARKET prices for the chosen city - the main figure shown to the owner.

  materials  = every material to buy (quantities incl. wastage, owner's scope only) x rate for the city
  labour     = every BOQ work item x labour (thekedar) rate for the city
  contractor = profit & overhead % on what the contractor supplies - depends on the contract type:
                 "labour"  : owner buys all materials, contractor supplies labour      -> % on labour
                 "grey"    : contractor builds the grey structure with material,
                             owner buys finishing materials, finishing labour contracted -> % on grey materials + labour
                 "turnkey" : contractor supplies everything                           -> % on materials + labour
  extras     = optional owner costs (cartage, approvals, utility connections, design fees, soil test)
  contingency= % on the above
  escalation = prices rising while the house is built: +x% per month on money spent later (from the schedule)

Every rate carries its city, date and source; low/high rates give the cost range.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Tuple

from pricing.base_rates import city_key
from pricing.ratebook import RateBook

CONTRACTS = {
    "labour": ("Labour contract (thekedari) - I buy the materials",
               "You buy all materials yourself; a thekedar supplies the labour. Most common for 5-10 marla houses."),
    "grey": ("Grey structure contract - contractor builds the structure with material",
             "The contractor builds foundations, walls, slabs, plaster and pipes with his material; you buy the "
             "finishing materials (tiles, fittings, paint ...) and he supplies the finishing labour."),
    "turnkey": ("Turnkey - contractor does everything",
                "One contractor supplies all materials and labour and hands over a finished house."),
}
GREY_DIVISIONS = {"Preliminaries", "Earthwork", "Concrete", "Reinforcement", "Formwork", "Masonry", "Plaster",
                  "Waterproofing", "Drainage", "Water supply", "Wiring", "Distribution", "Earthing", "External"}

NOT_MATERIAL = {"MSC-008"}  # approvals / utility connections - handled as owner extras

# labour of a BOQ division is shown under the same trade as its materials
DIVISION_TRADE = {
    "Preliminaries": "Preliminaries & Site", "Earthwork": "Earthwork & Site Prep", "Concrete": "Concrete & Aggregates",
    "Reinforcement": "Reinforcement & Steel", "Formwork": "Formwork & Temporary Works", "Masonry": "Masonry",
    "Plaster": "Plaster & Screeds", "Waterproofing": "Waterproofing, DPC & Insulation", "Flooring": "Flooring & Tiling",
    "Doors": "Doors, Windows & Glazing", "Windows": "Doors, Windows & Glazing", "Metalwork": "Joinery & Metalwork",
    "Joinery": "Joinery & Metalwork", "Ceiling": "Ceilings & Partitions", "Paint": "Paints & Coatings", "Wiring": "Electrical",
    "Distribution": "Electrical", "Fixtures": "Electrical", "Earthing": "Electrical", "AC": "HVAC & Ventilation",
    "Ventilation": "HVAC & Ventilation", "Water supply": "Plumbing - Water Supply", "Sanitary": "Sanitaryware & CP Fittings",
    "Drainage": "Plumbing - Drainage & Sanitary", "Gas": "Gas", "Kitchen": "Kitchen", "External": "External Works",
}

EXTRAS = {  # key: (label, kind "pct_materials" | "pct_construction" | "amount", default value, help)
    "cartage": ("Cartage (transport to site)", "pct_materials", 3.0, "Extra delivery / loading charges, % of materials"),
    "approval": ("Map approval & NOC fees", "amount", 150000.0, "CDA / RDA / LDA / Cantonment fees - check your authority"),
    "utilities": ("Utility connections (electricity, gas, water meters)", "amount", 250000.0, "Demand notices & meters"),
    "design": ("Architect / engineer fees", "pct_construction", 2.0, "Design & supervision, % of construction cost"),
    "soil": ("Soil test (boring)", "amount", 40000.0, "Geotechnical investigation"),
}


@dataclass
class CostSettings:
    city: str = "Islamabad"
    contract: str = "labour"
    profit_pct: float = 10.0
    contingency_pct: float = 5.0
    escalation_pct_month: float = 1.0
    extras_on: Dict[str, bool] = field(default_factory=dict)
    extras_value: Dict[str, float] = field(default_factory=dict)
    user_rates: Dict[str, float] = field(default_factory=dict)  # mat_id -> rate (supplier quotes)
    user_labour: Dict[str, float] = field(default_factory=dict)  # wi_id -> labour rate
    gov_mode: bool = False
    gov_bst_pct: float = 4.0
    gov_consultancy_pct: float = 1.0
    gov_contingency_pct: float = 1.0
    labour_update_pct: float = 4.0  # government estimate: labour increase per year since the rate book's edition
    material_update_pct: float = 0.0  # ... and for materials (Punjab 2024 -> 2026 evidence: +4%/yr labour, ~0% materials)


@dataclass
class CostLine:
    kind: str  # material | labour
    code: str
    name: str
    trade: str
    unit: str
    qty: float
    rate: float
    amount: float
    low: float
    high: float
    status: str  # live | indicative | user
    as_of: str
    source: str
    grey: bool
    buy_qty: str = ""
    stage: str = ""


@dataclass
class CostResult:
    settings: CostSettings
    lines: List[CostLine]
    materials: float
    labour: float
    profit: float
    extras: List[Tuple[str, float]]
    contingency: float
    escalation: float
    total: float
    low: float
    high: float
    covered_sft: float
    contractor_part: float
    owner_buys: float
    cashflow: List[dict] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    @property
    def per_sft(self) -> float:
        return self.total / self.covered_sft if self.covered_sft else 0.0

    def by_trade(self) -> List[Tuple[str, float, float]]:
        out: Dict[str, List[float]] = {}
        for ln in self.lines:
            t = out.setdefault(ln.trade, [0.0, 0.0])
            t[0 if ln.kind == "material" else 1] += ln.amount
        return sorted(((k, v[0], v[1]) for k, v in out.items()), key=lambda x: -(x[1] + x[2]))

    def grey_finishing(self) -> Tuple[float, float]:
        g = sum(ln.amount for ln in self.lines if ln.grey)
        f = sum(ln.amount for ln in self.lines if not ln.grey)
        return g, f

    def rate_status_share(self) -> Dict[str, float]:
        tot = sum(ln.amount for ln in self.lines) or 1.0
        out: Dict[str, float] = {}
        for ln in self.lines:
            out[ln.status] = out.get(ln.status, 0.0) + ln.amount / tot
        return out


def _wi_division(kb, wi_id: str) -> str:
    w = kb.work_items.get(wi_id)
    return w.division if w else ""


def compute_cost(res, settings: CostSettings, book: Optional[RateBook] = None, sched=None) -> CostResult:
    from detailed_mto.engine import purchase_qty
    from knowledge import load_knowledge_base

    kb = load_knowledge_base()
    book = book or RateBook()
    city = city_key(settings.city)
    lines: List[CostLine] = []
    from detailed_mto.engine import material_in_scope
    for m in res.purchase_list():
        if m.material.mat_id in NOT_MATERIAL:
            continue  # fees are owner extras (below), not materials
        info = book.rate(m.material.mat_id, city, settings.user_rates)
        grey = material_in_scope(kb, m.material, "Grey Structure (PK)")
        q, unit = purchase_qty(m.material, m.gross_qty)
        lines.append(CostLine("material", m.material.mat_id, m.material.description, m.material.category, m.material.unit,
                              m.gross_qty, info.rate, m.gross_qty * info.rate, m.gross_qty * info.low, m.gross_qty * info.high,
                              info.status, info.as_of, info.source, grey,
                              f"{q:,.0f} {unit}" if unit != "lump sum" else "lump sum", (m.material.stage or "")[:3]))
    for w in res.scoped_work_items():
        if w.qty <= 0 or w.status in ("Option - not included", "Not required"):
            continue
        info = book.labour_rate(w.wi_id, city, settings.user_labour)
        if info.rate <= 0:
            continue
        div = _wi_division(kb, w.wi_id)
        lines.append(CostLine("labour", w.wi_id, w.description, DIVISION_TRADE.get(div, div), w.unit, w.qty, info.rate, w.qty * info.rate,
                              w.qty * info.low, w.qty * info.high, info.status, info.as_of, info.source, div in GREY_DIVISIONS))
    materials = sum(ln.amount for ln in lines if ln.kind == "material")
    labour = sum(ln.amount for ln in lines if ln.kind == "labour")
    grey_mat = sum(ln.amount for ln in lines if ln.kind == "material" and ln.grey)
    if settings.contract == "turnkey":
        base = materials + labour
    elif settings.contract == "grey":
        base = grey_mat + labour
    else:
        base = labour
    profit = base * settings.profit_pct / 100.0
    construction = materials + labour + profit
    extras: List[Tuple[str, float]] = []
    for key, (label, kind, default, _h) in EXTRAS.items():
        if not settings.extras_on.get(key):
            continue
        v = float(settings.extras_value.get(key, default))
        amt = materials * v / 100 if kind == "pct_materials" else construction * v / 100 if kind == "pct_construction" else v
        extras.append((label, amt))
    subtotal = construction + sum(a for _l, a in extras)
    contingency = subtotal * settings.contingency_pct / 100.0
    lo = sum(ln.low for ln in lines)
    hi = sum(ln.high for ln in lines)
    k = (1 + settings.profit_pct / 100.0 * (base / max(materials + labour, 1)))
    covered = sum(f.covered_sft for f in res.project.floors)
    result = CostResult(settings, lines, materials, labour, profit, extras, contingency, 0.0,
                        subtotal + contingency, 0.0, 0.0, covered, base + profit, materials + labour - base)
    cash, escal = cashflow(result, res, sched, settings.escalation_pct_month)
    result.cashflow, result.escalation = cash, escal
    result.total = subtotal + contingency + escal
    extra_fixed = sum(a for _l, a in extras)
    result.low = (lo * k + extra_fixed) * (1 + settings.contingency_pct / 100.0) + escal * 0.5
    result.high = (hi * k + extra_fixed) * (1 + settings.contingency_pct / 100.0) + escal * 1.5
    live = result.rate_status_share().get("live", 0.0)
    if live < 0.5:
        result.notes.append(f"Only {live:.0%} of the cost uses live market prices; the rest uses the indicative "
                            "rate book (Sep 2026) - add your suppliers' quotes for a firmer figure.")
    return result


# ---------------------------------------------------------------------------
# cash flow from the schedule
# ---------------------------------------------------------------------------
def _month_index(d0: date, d: date) -> int:
    return (d.year - d0.year) * 12 + (d.month - d0.month)


def cashflow(cost: CostResult, res, sched, esc_pct: float) -> Tuple[List[dict], float]:
    """Money needed each month: materials are bought when the first activity using them starts, labour is paid
    as the work is done; profit, extras and contingency follow the same pattern. Escalation adds esc_pct per
    month to everything spent after the first month."""
    if sched is None or not getattr(sched, "activities", None):
        return [], 0.0
    start = sched.start
    first_act: Dict[str, object] = {}
    for a in sorted(sched.activities, key=lambda x: x.es):
        for c in a.components:
            first_act.setdefault(c.wi_id, a)
    share_by_mat: Dict[str, Dict[str, float]] = {}
    for c in res.contributions:
        if c.net_qty > 0:
            share_by_mat.setdefault(c.mat_id, {})
            share_by_mat[c.mat_id][c.wi_id] = share_by_mat[c.mat_id].get(c.wi_id, 0.0) + c.net_qty
    n_months = _month_index(start, sched.finish) + 1
    months = [{"Month": i + 1, "Materials": 0.0, "Labour": 0.0} for i in range(n_months)]

    def put(idx: int, key: str, amt: float):
        months[max(0, min(idx, n_months - 1))][key] += amt

    for ln in cost.lines:
        if ln.kind == "material":
            shares = share_by_mat.get(ln.code) or {}
            tot = sum(shares.values())
            placed = False
            for wi, q in shares.items():
                a = first_act.get(wi)
                if a is not None and tot > 0:
                    put(_month_index(start, a.start), "Materials", ln.amount * q / tot)
                    placed = True
            if not placed:
                put(0 if ln.stage in ("S0", "S1") else n_months // 2, "Materials", ln.amount)
        else:
            a = first_act.get(ln.code)
            if a is None or not a.duration:
                put(0, "Labour", ln.amount)
                continue
            per_day = ln.amount / a.duration
            for i in range(a.es, a.ef + 1):
                put(_month_index(start, sched.calendar[i]), "Labour", per_day)
    direct = cost.materials + cost.labour
    over = cost.profit + sum(a for _l, a in cost.extras) + cost.contingency
    esc_total, cum = 0.0, 0.0
    for i, m in enumerate(months):
        base = m["Materials"] + m["Labour"]
        m["Contractor, extras & contingency"] = over * base / direct if direct else 0.0
        subtotal = base + m["Contractor, extras & contingency"]
        esc = subtotal * ((1 + esc_pct / 100.0) ** i - 1)
        m["Price rise (escalation)"] = esc
        m["Total"] = subtotal + esc
        esc_total += esc
        cum += m["Total"]
        m["Cumulative"] = cum
        first = date(start.year + (start.month - 1 + i) // 12, (start.month - 1 + i) % 12 + 1, 1)
        m["Month of"] = first
    return months, esc_total


# ---------------------------------------------------------------------------
# Pakistani number format
# ---------------------------------------------------------------------------
def pkr(amount: float, short: bool = True) -> str:
    """Rs 1.52 crore / Rs 45.3 lakh / Rs 12,500."""
    a = float(amount or 0)
    if not short:
        return f"Rs {a:,.0f}"
    if abs(a) >= 1e7:
        return f"Rs {a / 1e7:.2f} crore"
    if abs(a) >= 1e5:
        return f"Rs {a / 1e5:.1f} lakh"
    return f"Rs {a:,.0f}"


def round_to(x: float, step: float) -> float:
    return math.floor(x / step + 0.5) * step


def wi_market_costs(cost: CostResult, res) -> Tuple[Dict[str, float], float]:
    """Market cost per BOQ work item (its labour + its share of every material), and the cost of materials that
    belong to no work item (fittings bought as units, lump sums)."""
    out: Dict[str, float] = {}
    shares: Dict[str, Dict[str, float]] = {}
    for c in res.contributions:
        if c.net_qty > 0:
            shares.setdefault(c.mat_id, {})
            shares[c.mat_id][c.wi_id] = shares[c.mat_id].get(c.wi_id, 0.0) + c.net_qty
    loose = 0.0
    for ln in cost.lines:
        if ln.kind == "labour":
            out[ln.code] = out.get(ln.code, 0.0) + ln.amount
            continue
        sh = shares.get(ln.code)
        tot = sum(sh.values()) if sh else 0.0
        if not tot:
            loose += ln.amount
            continue
        for wi, q in sh.items():
            out[wi] = out.get(wi, 0.0) + ln.amount * q / tot
    return out, loose
