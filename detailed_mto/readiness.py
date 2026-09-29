"""
Is there enough information for a realistic estimate?

Before anything is calculated the app checks:
  * FOUND      - what was read from the drawings (shown so the owner can confirm)
  * MISSING    - required information that is neither in the drawings nor answered -> must be answered
  * ASSUMPTIONS- the unavoidable standard values that remain (engineering rules, standard sizes) -> listed
                 plainly and the owner must acknowledge them before the estimate is produced
Nothing is silently assumed.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from detailed_mto.model import DetailedProject
from detailed_mto.scope import active_questions


@dataclass
class Check:
    key: str
    title: str
    detail: str
    where: str = ""  # which section of the page fixes it


@dataclass
class Readiness:
    found: List[Check] = field(default_factory=list)
    missing: List[Check] = field(default_factory=list)
    assumptions: List[Check] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return not self.missing

    def assumptions_hash(self) -> str:
        return hashlib.sha1("|".join(a.key + a.detail for a in self.assumptions).encode()).hexdigest()[:12]


# inputs the owner can't be expected to know - listed as engineering assumptions when not from drawings
ENGINEERING = {
    "FDN_DEPTH": "Foundation depth", "PCC_T": "Foundation concrete (PCC) thickness", "PCC_W_9": "Foundation width under main walls",
    "T_SLAB_IN": "Roof slab thickness", "H_PLINTH": "Plinth height", "H_PARAPET": "Roof wall (parapet) height",
    "COL_N": "Number of RCC columns", "BEAM_N": "Number of RCC beams", "FTG_L": "Column footing size",
    "BAND_LEN": "Earthquake band length", "STAIR_W": "Stair width", "N_RWP": "Rain-water pipes", "SEWER_LEN": "Sewer connection length",
    "N_MH": "Manholes", "N_GT": "Gully traps", "N_FT": "Floor traps", "N_EARTH": "Earth pits", "N_DB": "Distribution boards",
    "UGT_D": "Water tank depth", "SEP_L": "Septic tank size", "TANK_WALL_IN": "Tank wall thickness", "GATE_W": "Gate width",
    "RAIL_LEN": "Railing length",
}


def _is_known(prm) -> bool:
    return prm is not None and prm.confidence in ("High", "User")


def evaluate(p: DetailedProject, selected: set, answers: Dict[str, object], scope_confirmed: bool,
             settings_window: Optional[tuple] = None) -> Readiness:
    r = Readiness()

    # ---- plot
    if _is_known(p.params.get("PLOT_W")) and (p.v("PLOT_D") > 0 and _is_known(p.params.get("PLOT_D"))):
        r.found.append(Check("plot", "Plot size", f"{p.v('PLOT_W'):.0f} ft x {p.v('PLOT_D'):.0f} ft = {p.v('PLOT_W') * p.v('PLOT_D'):,.0f} sq ft"))
    else:
        r.missing.append(Check("plot", "Plot size", "The plot width and depth were not found - enter them.", "plot"))

    # ---- floors & rooms
    rooms = [x for x in p.rooms if x.area > 0]
    if not rooms:
        r.missing.append(Check("rooms", "Rooms", "No rooms with sizes yet - add them in the rooms table.", "rooms"))
    else:
        typical = [x for x in rooms if x.confidence == "Assumed"]
        known = len(rooms) - len(typical)
        r.found.append(Check("rooms", "Rooms", f"{len(rooms)} rooms on {len(p.storeys)} floor(s), "
                                               f"{sum(x.area for x in rooms):,.0f} sq ft of rooms" +
                             (f" ({known} with sizes from your drawings/answers)" if typical else "")))
        if typical:
            r.assumptions.append(Check("rooms_typical", "Room sizes",
                                       f"{len(typical)} room(s) use typical sizes: " + ", ".join(x.name for x in typical[:6]) +
                                       ("..." if len(typical) > 6 else "") + ". Correct them in the rooms table if you know the sizes."))
    if p.storeys:
        cov = sum(f.covered_sft for f in p.floors)
        r.found.append(Check("floors", "Floors", f"{len(p.storeys)} floor(s)" + (" + mumty" if p.mumty else "") + f", covered area {cov:,.0f} sq ft"))

    # ---- scope
    if not scope_confirmed:
        r.missing.append(Check("scope", "Scope of work", "Tick what you want included in the house and press 'Confirm my scope'.", "scope"))

    # ---- specification questions
    for q in active_questions(selected):
        found = q.found(p) if q.found else None
        if found is not None and q.id not in answers:
            r.found.append(Check(q.id, q.title, "from your drawings"))
            continue
        if q.id not in answers or answers[q.id] is None:
            if q.required:
                r.missing.append(Check(q.id, q.title, q.question, "details"))

    # ---- doors & windows present when in scope
    if "doors" in selected and not p.doors():
        r.missing.append(Check("doors_list", "Doors", "No doors in the list - add them in 'Doors & windows'.", "rooms"))
    if "windows" in selected and not [o for o in p.windows() if o.kind == "window"]:
        r.missing.append(Check("windows_list", "Windows", "No windows in the list - add them in 'Doors & windows'.", "rooms"))

    # ---- structure without structural drawings
    if p.drawing_mode != "cad" or not _is_known(p.params.get("COL_N")):
        r.assumptions.append(Check("steel", "Steel (sarya) & concrete sizes",
                                   "No structural (engineer's) details were found, so column, beam and slab steel is worked out with "
                                   "standard kg-per-cubic-foot ratios. Your engineer's bar schedule would make this exact."))

    # ---- remaining engineering standards
    eng = [f"{label} {p.v(k):g} {p.params[k].unit if p.params[k].unit not in ('-', 'flag') else ''}".strip()
           for k, label in ENGINEERING.items() if k in p.params and not _is_known(p.params[k])]
    if eng:
        r.assumptions.append(Check("engineering", "Standard construction values",
                                   "Not on your drawings, so common Pakistani standards are used: " + "; ".join(eng[:12]) +
                                   ("; ..." if len(eng) > 12 else "") + "."))
    try:  # items that would still have no quantity -> say so plainly (they are left out, not guessed)
        from detailed_mto import compute
        from detailed_mto.engine import ST_NEEDS_INPUT
        from knowledge import load_knowledge_base
        res = compute(p, load_knowledge_base())
        gaps = [m.material.description for m in res.scoped_materials() if m.status == ST_NEEDS_INPUT]
        if gaps:
            r.assumptions.append(Check("not_estimated", "Left out (no information)",
                                       "These are NOT estimated because nothing about them is known: " + "; ".join(gaps[:6]) +
                                       ". Add them later if you need them."))
    except Exception:  # noqa: BLE001 - the check must never block the page
        pass
    r.assumptions.append(Check("wastage", "Wastage & mixes",
                               "Normal site wastage (e.g. cement 2%, sand 10%, bricks 5%, tiles 7%) and standard concrete/mortar "
                               "mixes (1:2:4, 1:4:8, 1:6) are included."))
    if p.conflicts:
        r.assumptions.append(Check("conflicts", "Differences found in your drawings", " | ".join(p.conflicts[:3])))
    return r
