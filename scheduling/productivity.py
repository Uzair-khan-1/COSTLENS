"""
Default productivity norms for 5-10 marla houses in Pakistan.

Each value is the OUTPUT OF ONE GANG IN ONE WORKING DAY (8 h), in the BOQ
work-item unit, for typical private-contractor practice (manual excavation,
site-mixed concrete with a 1-bag mixer and vibrator, hired steel shuttering).
They are planning figures, not guarantees - the user can edit every one of
them in the Schedule tab.

Gang = the crew that does the work end to end, e.g. a brick-masonry gang is
2 masons + 4 labourers; a steel-fixing gang is 2 fixers + 2 helpers.
"""
from __future__ import annotations

from typing import Dict, Tuple

# wi_id -> (output per gang-day, gang composition / basis)
DEFAULT_RATES: Dict[str, Tuple[float, str]] = {
    # Earthwork
    "WI-EW-01": (400, "4 labourers (~100 cft each, manual)"),
    "WI-EW-02": (400, "4 labourers (~100 cft each, manual)"),
    "WI-EW-03": (300, "4 labourers, deeper/narrow pits"),
    "WI-EW-04": (500, "4 labourers + rammer, 6in layers"),
    "WI-EW-05": (500, "4 labourers + rammer, 6in layers"),
    "WI-EW-06": (500, "4 labourers"),
    "WI-EW-07": (2000, "1 applicator + helper"),
    "WI-EW-08": (2000, "2 labourers"),
    "WI-EW-09": (1000, "tractor-trolley + 3 labourers"),
    # Concrete (site-mixed, 1-bag mixer + vibrator, ~10-12 labour)
    "WI-CN-01": (250, "mixer gang (1 mason + 10 labour)"),
    "WI-CN-02": (250, "mixer gang (1 mason + 10 labour)"),
    "WI-CN-03": (300, "mixer gang + vibrator"),
    "WI-CN-04": (200, "mixer gang + vibrator"),
    "WI-CN-05": (150, "mixer gang, column lifts"),
    "WI-CN-06": (400, "mixer gang, poured with slab"),
    "WI-CN-07": (400, "mixer gang, one-day slab pour"),
    "WI-CN-08": (150, "mixer gang"),
    "WI-CN-09": (100, "2 masons + 4 labour, small pours"),
    "WI-CN-10": (60, "2 masons + 4 labour, small pours"),
    "WI-CN-11": (150, "mixer gang"),
    "WI-CN-12": (400, "2 masons + 4 labour"),
    "WI-CN-13": (400, "2 masons + 4 labour"),
    # Reinforcement (2 steel fixers + 2 helpers)
    "WI-RF-01": (400, "2 fixers + 2 helpers"),
    "WI-RF-02": (300, "2 fixers + 2 helpers (column cages)"),
    "WI-RF-03": (350, "2 fixers + 2 helpers"),
    "WI-RF-04": (450, "2 fixers + 2 helpers (slab mesh)"),
    "WI-RF-05": (250, "2 fixers + 2 helpers"),
    "WI-RF-06": (250, "2 fixers + 2 helpers"),
    "WI-RF-07": (250, "2 fixers + 2 helpers"),
    # Formwork
    "WI-FW-01": (400, "shuttering fundi + 4 helpers (steel plates)"),
    "WI-FW-02": (250, "2 carpenters + 2 helpers (ply/timber)"),
    # Masonry (2 masons + 4 labourers)
    "WI-MS-01": (160, "2 masons + 4 labour"),
    "WI-MS-02": (160, "2 masons + 4 labour (~1,000 bricks/mason-day)"),
    "WI-MS-03": (300, "2 masons + 4 labour"),
    "WI-MS-04": (120, "2 masons + 4 labour, at height"),
    "WI-MS-05": (600, "1 mason + 4 labour"),
    "WI-MS-06": (250, "2 masons + 4 labour"),
    # Plaster (2 masons + 3 labourers)
    "WI-PL-01": (220, "2 masons + 3 labour"),
    "WI-PL-02": (160, "2 masons + 3 labour, on scaffold"),
    "WI-PL-03": (150, "2 masons + 3 labour, overhead"),
    "WI-PL-04": (150, "2 masons + 3 labour"),
    # Waterproofing / roof
    "WI-WP-01": (500, "roof gang (1 mistri + 6 labour)"),
    "WI-WP-02": (500, "roof gang"),
    "WI-WP-03": (300, "applicator + 2 helpers"),
    "WI-WP-04": (400, "2 masons + 4 labour"),
    # Flooring & tiling (2 tile fixers + 2 helpers)
    "WI-FL-01": (180, "2 tile fixers + 2 helpers"),
    "WI-FL-02": (180, "2 tile fixers + 2 helpers"),
    "WI-FL-03": (120, "2 tile fixers + 2 helpers"),
    "WI-FL-04": (120, "2 marble fixers + 2 helpers"),
    "WI-FL-05": (200, "2 tile fixers + 2 helpers"),
    "WI-FL-06": (40, "2 marble fixers + 2 helpers"),
    "WI-FL-07": (250, "2 fixers + 3 helpers"),
    "WI-FL-08": (60, "2 marble fixers + 2 helpers"),
    # Doors, windows, metalwork
    "WI-DW-01": (120, "carpenter + helper (~8 frames/day)"),
    "WI-DW-02": (100, "2 carpenters (~5 shutters/day)"),
    "WI-DW-03": (8, "carpenter"),
    "WI-DW-04": (100, "aluminium/uPVC fabricator team"),
    "WI-DW-05": (150, "welder + helper"),
    "WI-DW-06": (30, "welder + helper"),
    "WI-DW-07": (70, "welder + helper"),
    # Ceiling / paint (3 painters)
    "WI-CL-01": (200, "2 gypsum fixers + helper"),
    "WI-PT-01": (350, "3 painters (putty, primer, 2 coats)"),
    "WI-PT-02": (300, "3 painters, overhead"),
    "WI-PT-03": (350, "3 painters on scaffold"),
    "WI-PT-04": (250, "2 painters"),
    "WI-PT-05": (120, "2 polish men"),
    # Electrical (1 electrician + 1 helper)
    "WI-EL-01": (8, "electrician + helper"),
    "WI-EL-02": (8, "electrician + helper"),
    "WI-EL-03": (8, "electrician + helper"),
    "WI-EL-04": (6, "electrician + helper"),
    "WI-EL-05": (4, "electrician + helper"),
    "WI-EL-06": (8, "electrician + helper"),
    "WI-EL-07": (60, "electrician + helper"),
    "WI-EL-08": (1, "electrician + helper"),
    "WI-EL-09": (1, "electrician + 2 labour"),
    "WI-EL-10": (20, "electrician + helper"),
    # HVAC
    "WI-HV-01": (2, "AC technician + helper"),
    "WI-HV-02": (6, "electrician + helper"),
    # Plumbing (1 plumber + 1 helper)
    "WI-PB-01": (3, "plumber + helper"),
    "WI-PB-02": (4, "plumber + helper"),
    "WI-PB-03": (4, "plumber + helper"),
    "WI-PB-04": (8, "plumber + helper"),
    "WI-PB-05": (6, "plumber + helper"),
    "WI-PB-06": (0.5, "plumber + helper (~2 days per bathroom)"),
    "WI-PB-07": (2, "plumber + helper"),
    "WI-PB-08": (4, "plumber + helper"),
    "WI-PB-09": (60, "plumber + helper"),
    "WI-PB-10": (4, "plumber + helper"),
    "WI-PB-11": (40, "plumber + 2 labour"),
    "WI-PB-12": (0.5, "mason + 2 labour (~2 days each)"),
    "WI-PB-13": (2, "mason + labour"),
    "WI-GS-01": (3, "gas fitter + helper"),
    # Kitchen / joinery
    "WI-KT-01": (8, "2 carpenters"),
    "WI-KT-02": (8, "2 carpenters"),
    "WI-KT-03": (16, "stone fixer + helper"),
    "WI-JN-01": (40, "2 carpenters"),
    # External
    "WI-EX-01": (15, "2 masons + 4 labour, incl. foundation"),
    "WI-EX-02": (0.2, "boring + mason (~5 days)"),
}

# The same work item can be priced at a different rate inside a particular activity:
# electrical points are first chased & conduited (rough-in), later wired and fitted.
ACTIVITY_RATES: Dict[Tuple[str, str], Tuple[float, str]] = {
    ("ELR", "WI-EL-01"): (10, "chasing, conduit & boxes"),
    ("ELR", "WI-EL-02"): (10, "chasing, conduit & boxes"),
    ("ELR", "WI-EL-03"): (10, "chasing, conduit & boxes"),
    ("ELR", "WI-EL-04"): (8, "chasing, conduit & boxes"),
    ("ELR", "WI-EL-05"): (6, "chasing, conduit & boxes"),
    ("ELR", "WI-EL-06"): (10, "chasing, conduit & boxes"),
    ("ELF", "WI-EL-01"): (15, "wire pulling, switches & sockets"),
    ("ELF", "WI-EL-02"): (15, "wire pulling, regulators"),
    ("ELF", "WI-EL-03"): (15, "wire pulling, sockets"),
    ("ELF", "WI-EL-04"): (12, "wire pulling, sockets"),
    ("ELF", "WI-EL-05"): (8, "wire pulling, isolators"),
    ("ELF", "WI-EL-06"): (15, "cabling & outlets"),
}

FALLBACK_RATE = (1.0, "no norm - edit")


def default_rate(template: str, wi_id: str) -> Tuple[float, str]:
    return ACTIVITY_RATES.get((template, wi_id)) or DEFAULT_RATES.get(wi_id) or FALLBACK_RATE


# ---------------------------------------------------------------------------
# CREWS - who actually does the work (Pakistani site practice, 5-10 marla houses)
# ---------------------------------------------------------------------------
# Trade names shown to the owner, with the word used on site.
TRADES = {
    "Mason": "Mason (mistri)", "Labourer": "Labourer (mazdoor)", "Steel fixer": "Steel fixer (sarya binder)",
    "Shuttering carpenter": "Shuttering carpenter", "Carpenter": "Carpenter (tarkhan)", "Mixer operator": "Mixer operator",
    "Electrician": "Electrician", "Plumber": "Plumber", "Tile fixer": "Tile / marble fixer", "Painter": "Painter (rang-saz)",
    "Welder": "Welder / steel fabricator", "Aluminium fitter": "Aluminium / uPVC fitter", "Waterproofer": "Waterproofing applicator",
    "Ceiling fixer": "False-ceiling fixer", "AC technician": "AC technician", "Gas fitter": "Gas fitter", "Stone fixer": "Granite fixer",
    "Helper": "Helper",
}

# crew key -> (composition {trade: number}, max crews that can work on ONE activity at once)
CREWS: Dict[str, Tuple[Dict[str, int], int]] = {
    "earth": ({"Labourer": 4}, 4),
    "termite": ({"Waterproofer": 1, "Helper": 1}, 1),
    "haul": ({"Labourer": 3}, 2),
    "concrete": ({"Mason": 1, "Mixer operator": 1, "Labourer": 10}, 2),  # one mixer per gang
    "mason_small": ({"Mason": 2, "Labourer": 4}, 3),
    "steel": ({"Steel fixer": 2, "Helper": 2}, 4),
    "shutter_plate": ({"Shuttering carpenter": 1, "Helper": 4}, 3),
    "shutter_timber": ({"Shuttering carpenter": 2, "Helper": 2}, 3),
    "mason": ({"Mason": 2, "Labourer": 4}, 4),
    "soling": ({"Mason": 1, "Labourer": 4}, 2),
    "plaster": ({"Mason": 2, "Labourer": 3}, 4),
    "roof": ({"Mason": 1, "Labourer": 6}, 2),
    "waterproof": ({"Waterproofer": 1, "Helper": 2}, 2),
    "tile": ({"Tile fixer": 2, "Helper": 2}, 4),
    "carpenter": ({"Carpenter": 2}, 3),
    "frames": ({"Carpenter": 1, "Helper": 1}, 3),
    "aluminium": ({"Aluminium fitter": 2}, 2),
    "welder": ({"Welder": 1, "Helper": 1}, 2),
    "ceiling": ({"Ceiling fixer": 2, "Helper": 1}, 3),
    "painter": ({"Painter": 3}, 4),
    "polish": ({"Painter": 2}, 2),
    "electric": ({"Electrician": 1, "Helper": 1}, 4),
    "earthing": ({"Electrician": 1, "Labourer": 2}, 1),
    "ac": ({"AC technician": 1, "Helper": 1}, 2),
    "plumber": ({"Plumber": 1, "Helper": 1}, 3),
    "drain": ({"Plumber": 1, "Labourer": 2}, 2),
    "gas": ({"Gas fitter": 1, "Helper": 1}, 1),
    "stone": ({"Stone fixer": 1, "Helper": 1}, 1),
    "boring": ({"Mason": 1, "Labourer": 3}, 1),
    "general": ({"Mason": 1, "Labourer": 3}, 1),
    "handover": ({"Electrician": 1, "Plumber": 1, "Labourer": 2}, 1),
}

_CREW_BY_WI = {
    "WI-EW-07": "termite", "WI-EW-08": "termite", "WI-EW-09": "haul",
    "WI-CN-09": "mason_small", "WI-CN-10": "mason_small", "WI-CN-12": "mason_small", "WI-CN-13": "mason_small",
    "WI-FW-01": "shutter_plate", "WI-FW-02": "shutter_timber", "WI-MS-05": "soling",
    "WI-WP-01": "roof", "WI-WP-02": "roof", "WI-WP-03": "waterproof", "WI-WP-04": "mason",
    "WI-DW-01": "frames", "WI-DW-02": "carpenter", "WI-DW-03": "carpenter", "WI-DW-04": "aluminium",
    "WI-DW-05": "welder", "WI-DW-06": "welder", "WI-DW-07": "welder", "WI-CL-01": "ceiling",
    "WI-PT-04": "polish", "WI-PT-05": "polish", "WI-EL-09": "earthing", "WI-HV-01": "ac", "WI-HV-02": "electric",
    "WI-PB-11": "drain", "WI-PB-12": "mason_small", "WI-PB-13": "mason_small", "WI-GS-01": "gas",
    "WI-KT-01": "carpenter", "WI-KT-02": "carpenter", "WI-KT-03": "stone", "WI-JN-01": "carpenter",
    "WI-EX-01": "mason", "WI-EX-02": "boring", "WI-PRE-01": "general", "WI-PRE-02": "general",
}
_CREW_BY_PREFIX = [("WI-EW-", "earth"), ("WI-CN-", "concrete"), ("WI-RF-", "steel"), ("WI-MS-", "mason"), ("WI-PL-", "plaster"),
                   ("WI-FL-", "tile"), ("WI-PT-", "painter"), ("WI-EL-", "electric"), ("WI-PB-", "plumber")]
# activities with a fixed duration and no measured work
FIXED_CREWS = {"PRE": "general", "HND": "handover", "WSS": "plumber"}


def crew_of(wi_id: str) -> str:
    if wi_id in _CREW_BY_WI:
        return _CREW_BY_WI[wi_id]
    for pre, crew in _CREW_BY_PREFIX:
        if wi_id.startswith(pre):
            return crew
    return "general"


def crew_size(crew: str) -> int:
    return sum(CREWS.get(crew, ({}, 1))[0].values())


# Space on site limits how many crews can work on one activity: one crew per this many sq ft of the floor
# being worked on (masons need ~15-20 ft of wall each, tile gangs a room each ...). Documented planning rule.
AREA_PER_CREW = {"MAS": 350, "PLI": 350, "FLR": 350, "PTI": 450, "ELR": 500, "PLR": 700, "FCL": 450, "EXP": 400,
                 "COL": 700, "SLB": 450, "MUM": 700, "EXC": 350, "PCC": 600, "FTG": 450, "FMS": 400, "PLB": 500,
                 "BKF": 450, "GFB": 400, "PAR": 500, "ROF": 500, "WIN": 700, "STM": 1500, "DOR": 900, "JNR": 900,
                 "ELF": 600, "SAN": 900, "EXD": 900, "BND": 800, "OUT": 700, "PTE": 500, "PTM": 900, "RAI": 1500,
                 "TNK": 1500, "DPC": 800}
