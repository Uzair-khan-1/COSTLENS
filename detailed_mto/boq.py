"""
Bill of Quantities (BOQ) in plain sections and the usual Pakistani order: the measured work items
(brickwork in cft, plaster in sq ft ...) with quantities. Rates are not part of this version.
"""
from __future__ import annotations

from typing import List

from detailed_mto.engine import DetailedResult

BOQ_DIVISIONS = [  # (division in the database, section name shown to the owner) in the usual Pakistani BOQ order
    ("Preliminaries", "A. Site preparation"), ("Earthwork", "B. Excavation & filling"), ("Concrete", "C. Concrete work"),
    ("Reinforcement", "D. Steel (sarya)"), ("Formwork", "E. Shuttering"), ("Masonry", "F. Brickwork"), ("Plaster", "G. Plaster"),
    ("Waterproofing", "H. Waterproofing & DPC"), ("Flooring", "I. Floors & tiles"), ("Doors", "J. Doors"), ("Windows", "K. Windows"),
    ("Metalwork", "L. Grills, railings & gate"), ("Joinery", "M. Woodwork & wardrobes"), ("Ceiling", "N. Ceilings"),
    ("Paint", "O. Paint"), ("Wiring", "P. Electrical wiring"), ("Distribution", "Q. Electrical boards"),
    ("Fixtures", "R. Lights & fans"), ("Earthing", "S. Earthing"), ("AC", "T. Air-conditioning"), ("Ventilation", "U. Exhaust fans"),
    ("Water supply", "V. Water supply"), ("Sanitary", "W. Bathroom fittings"), ("Drainage", "X. Drainage & sewer"),
    ("Gas", "Y. Gas"), ("Kitchen", "Z. Kitchen"), ("External", "Outside works"),
]
_DIV_ORDER = {d: i for i, (d, _n) in enumerate(BOQ_DIVISIONS)}
_DIV_NAME = dict(BOQ_DIVISIONS)


def boq_rows(res: DetailedResult) -> List[dict]:
    """Bill of Quantities (work items with quantities, no rates) in the usual Pakistani order."""
    items = [w for w in res.scoped_work_items() if w.qty > 0 and w.status not in ("Option - not included", "Not required")]
    items.sort(key=lambda w: (_DIV_ORDER.get(w.division, 99), w.wi_id))
    rows = []
    for n, w in enumerate(items, 1):
        rows.append({"No.": n, "Section": _DIV_NAME.get(w.division, w.division), "Description of work": w.description,
                     "Unit": w.unit, "Quantity": round(w.qty, 2),
                     "Check": "" if w.confidence in ("High", "Medium", "User") else "\u26a0\ufe0f"})
    return rows
