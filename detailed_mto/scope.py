"""
User-defined SCOPE OF WORK and SPECIFICATIONS.

Nothing optional is assumed: the owner ticks what they want in the house (scope items) and answers
the specification questions for what they ticked. Answers already found in the drawings are
pre-filled (and marked so). Everything is turned into engine settings:

  compile_scope(selected, answers) -> ScopeSettings(options=..., overrides=..., excluded/included ...)

The grey-structure core (foundations, RCC, brickwork, plaster, waterproofing, drainage & water pipes)
is always part of building a house and cannot be switched off.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from detailed_mto.model import DetailedProject


# ---------------------------------------------------------------------------
# scope items
# ---------------------------------------------------------------------------
@dataclass
class ScopeItem:
    key: str
    group: str
    icon: str
    label: str
    help: str
    wis: Tuple[str, ...] = ()  # work items removed when NOT selected
    mats: Tuple[str, ...] = ()  # materials removed when NOT selected
    core: bool = False  # always included


CORE_LABELS = [
    ("\U0001f3d7\ufe0f", "Foundations, RCC slabs, columns & stairs"), ("\U0001f9f1", "Brick walls & plaster"),
    ("\U0001f4a7", "Damp-proofing (DPC) & roof waterproofing"), ("\U0001f6b0", "Drainage, sewer & water supply pipes"),
    ("\U0001f50c", "Electrical conduits (pipes in walls & slabs)"),
]

SCOPE_ITEMS: List[ScopeItem] = [
    # ---- finishing
    ScopeItem("floor", "Finishing", "\U0001f7eb", "Floor tiles / marble", "All rooms, bathrooms, kitchen, stairs & skirting.",
              ("WI-FL-01", "WI-FL-02", "WI-FL-04", "WI-FL-05", "WI-FL-06", "WI-FL-08"),
              ("FLR-001", "FLR-002", "FLR-004", "FLR-005", "FLR-006", "FLR-007", "FLR-008", "FLR-010", "FLR-011", "FLR-012",
               "FLR-013", "FLR-014", "FLR-015", "FLR-016", "FLR-018")),
    ScopeItem("walltiles", "Finishing", "\U0001f6c1", "Wall tiles in bathrooms & kitchen", "Tiles on bathroom walls and behind the kitchen counter.",
              ("WI-FL-03",), ("FLR-003",)),
    ScopeItem("paint", "Finishing", "\U0001f3a8", "Paint (inside & outside)", "Putty, primer and paint on walls, ceilings, doors and grills.",
              ("WI-PT-01", "WI-PT-02", "WI-PT-03", "WI-PT-04", "WI-PT-05"), tuple(f"PNT-{i:03d}" for i in range(1, 14))),
    ScopeItem("ceiling", "Finishing", "\u2601\ufe0f", "False ceilings", "Gypsum ceilings in main rooms, PVC panels in bathrooms.",
              ("WI-CL-01",), ("CLG-001", "CLG-002", "CLG-003", "CLG-004", "CLG-005", "CLG-006", "PLS-004")),
    ScopeItem("doors", "Finishing", "\U0001f6aa", "Doors", "Door frames (chogath), shutters, locks & hinges.",
              ("WI-DW-01", "WI-DW-02", "WI-DW-03"), ("DWG-001", "DWG-002", "DWG-003", "DWG-004", "DWG-005", "DWG-006", "DWG-007",
                                                      "DWG-008", "DWG-017")),
    ScopeItem("windows", "Finishing", "\U0001fa9f", "Windows", "Window frames, glass, mosquito nets and ventilators.",
              ("WI-DW-04",), ("DWG-009", "DWG-010", "DWG-011", "DWG-012", "DWG-014", "DWG-015", "DWG-016")),
    ScopeItem("grills", "Finishing", "\U0001f9f1", "Window grills", "Steel safety grills on windows.", ("WI-DW-05",), ("DWG-013",)),
    ScopeItem("railings", "Finishing", "\U0001fa9c", "Stair & balcony railings", "Steel / glass railings.", ("WI-DW-06",), ("JNR-005", "EXT-011")),
    # ---- bathrooms & kitchen
    ScopeItem("sanitary", "Bathrooms & kitchen", "\U0001f6bd", "Bathroom fittings", "WC, wash basin, shower set, taps, mirrors & accessories.",
              ("WI-PB-01", "WI-PB-02", "WI-PB-03", "WI-PB-04"),
              ("SAN-001", "SAN-002", "SAN-003", "SAN-004", "SAN-005", "SAN-006", "SAN-007", "SAN-008", "SAN-009", "SAN-010", "SAN-011",
               "SAN-012", "SAN-013", "PDR-011", "JNR-004")),
    ScopeItem("geyser", "Bathrooms & kitchen", "\U0001f525", "Water heater (geyser)", "Gas or electric geyser(s).", (), ("PWS-022", "SAN-016", "SAN-017")),
    ScopeItem("kitchen", "Bathrooms & kitchen", "\U0001f373", "Kitchen cabinets & countertop", "Base & wall cabinets, countertop, sink and mixer.",
              ("WI-KT-01", "WI-KT-02", "WI-KT-03", "WI-PB-07"),
              ("KIT-001", "KIT-002", "KIT-003", "KIT-004", "KIT-005", "KIT-006", "KIT-009", "KIT-013", "PDR-022")),
    ScopeItem("appliances", "Bathrooms & kitchen", "\U0001f37d\ufe0f", "Kitchen hob, hood & oven", "Built-in appliances.", (),
              ("KIT-007", "KIT-008", "KIT-010")),
    ScopeItem("wardrobes", "Bathrooms & kitchen", "\U0001f45a", "Built-in wardrobes", "Wardrobes in bedrooms.", ("WI-JN-01",),
              ("JNR-001", "JNR-002", "JNR-003")),
    # ---- electrical & cooling
    ScopeItem("wiring", "Electrical & cooling", "\U0001f4a1", "Wiring, switches & sockets", "Wires, switches, sockets and the distribution boards.",
              ("WI-EL-01", "WI-EL-02", "WI-EL-03", "WI-EL-04", "WI-EL-07", "WI-EL-08"),
              ("ELE-006", "ELE-007", "ELE-009", "ELE-011", "ELE-014", "ELE-015", "ELE-016", "ELE-017", "ELE-018", "ELE-019", "ELE-020",
               "ELE-021", "ELE-022", "ELE-024", "ELE-025", "ELE-026", "ELE-027")),
    ScopeItem("fixtures", "Electrical & cooling", "\U0001f300", "Lights & ceiling fans", "Supply of LED lights, fans and outdoor lights.",
              ("WI-EL-10",), ("ELE-032", "ELE-033", "ELE-034", "ELE-035", "ELE-036")),
    ScopeItem("ac", "Electrical & cooling", "\u2744\ufe0f", "Air-conditioner provisions", "AC points, copper piping, drain pipes and brackets.",
              ("WI-EL-05", "WI-HV-01"), ("ELE-008", "ELE-023", "HVC-001", "HVC-002", "HVC-003", "HVC-004", "HVC-005", "HVC-006", "HVC-007")),
    ScopeItem("exhaust", "Electrical & cooling", "\U0001f4a8", "Exhaust fans", "Bathroom & kitchen exhaust fans.", ("WI-HV-02",),
              ("HVC-008", "HVC-009", "HVC-010")),
    ScopeItem("lowvolt", "Electrical & cooling", "\U0001f4fa", "TV, internet & intercom points", "Cable TV, internet (CAT6) and intercom.",
              ("WI-EL-06",), ("ELE-028", "ELE-029", "ELE-030", "ELE-031")),
    ScopeItem("earthing", "Electrical & cooling", "\u26a1", "Earthing", "Earth pits for electrical safety (recommended).", ("WI-EL-09",),
              ("ELE-012", "ELE-013")),
    ScopeItem("solar", "Electrical & cooling", "\u2600\ufe0f", "Solar panel provision", "Pipes and space ready for solar panels later.", (),
              ("SOL-001", "SOL-002", "SOL-003")),
    # ---- services & outside
    ScopeItem("water", "Water, gas & outside", "\U0001f4a7", "Water tanks & pumps", "Underground & roof tanks, pumps and valves.",
              ("WI-PB-14",), ("PWS-011", "PWS-013", "PWS-014", "PWS-016", "SAN-018", "SAN-019")),
    ScopeItem("gas", "Water, gas & outside", "\U0001f525", "Gas pipes & points", "Gas pipes to kitchen / geysers.", ("WI-GS-01",),
              ("GAS-001", "GAS-002", "GAS-003", "GAS-004", "GAS-005", "GAS-006")),
    ScopeItem("boundary", "Water, gas & outside", "\U0001f9f1", "Boundary wall & main gate", "Outer walls of the plot and the steel gate.",
              ("WI-EX-01", "WI-DW-07"), ("EXT-007", "EXT-008", "JNR-007")),
    ScopeItem("paving", "Water, gas & outside", "\U0001f697", "Porch paving & landscaping", "Tiles/pavers on porch & driveway, lawn, plants.",
              ("WI-FL-07",), ("EXT-001", "EXT-002", "EXT-003", "EXT-004", "EXT-005", "EXT-006")),
    ScopeItem("cladding", "Water, gas & outside", "\U0001faa8", "Front elevation cladding", "Stone / tile / brick-slip finish on the front wall.",
              (), ("EXT-010",)),
    ScopeItem("rwh", "Water, gas & outside", "\U0001f327\ufe0f", "Rainwater recharge well", "Required by CDA in Islamabad.", ("WI-EX-02",),
              tuple(f"RWH-{i:03d}" for i in range(1, 8))),
    ScopeItem("fire", "Water, gas & outside", "\U0001f9ef", "Smoke detectors & fire extinguisher", "Basic fire safety.", (),
              ("FLS-001", "FLS-002", "FLS-003")),
]
ITEMS: Dict[str, ScopeItem] = {s.key: s for s in SCOPE_ITEMS}
GROUPS = list(dict.fromkeys(s.group for s in SCOPE_ITEMS))

PRESETS = {
    "grey": ("Grey structure only", []),
    "typical": ("Complete house - typical items", ["floor", "walltiles", "paint", "doors", "windows", "grills", "railings", "sanitary",
                                                    "geyser", "kitchen", "wiring", "fixtures", "ac", "exhaust", "earthing", "water", "gas",
                                                    "boundary", "paving"]),
    "all": ("Everything", [s.key for s in SCOPE_ITEMS]),
}


# ---------------------------------------------------------------------------
# specification questions
# ---------------------------------------------------------------------------
@dataclass
class Effect:
    options: Dict[str, object] = field(default_factory=dict)
    overrides: Dict[str, float] = field(default_factory=dict)
    excl: Tuple[str, ...] = ()
    incl: Tuple[str, ...] = ()


@dataclass
class Question:
    id: str
    scope: str  # scope item key, or "core"
    icon: str
    title: str
    question: str
    options: Callable[[DetailedProject], List[Tuple[str, object]]]
    apply: Callable[[object], Effect]
    found: Optional[Callable[[DetailedProject], Optional[object]]] = None  # value read from the drawings
    help: str = ""
    required: bool = True


def _c(p: DetailedProject) -> dict:
    n = lambda *t: len(p.rooms_of(*t))  # noqa: E731
    return {"beds": n("Bedroom"), "lounges": n("Lounge / TV lounge", "Drawing room"), "baths": n("Bathroom"), "kitchens": n("Kitchen"),
            "main": n("Bedroom", "Drawing room", "Lounge / TV lounge", "Servant quarter"),
            "other": n("Kitchen", "Bathroom", "Laundry", "Staircase", "Store / utility"), "floors": len(p.storeys)}


def _fixed(opts):
    return lambda p: opts


def _param_effect(key):
    return lambda v: Effect(overrides={key: float(v)})


def _dedupe(opts):
    seen, out = set(), []
    for lbl, v in opts:
        k = round(v, 3) if isinstance(v, float) else v
        if k not in seen:
            seen.add(k)
            out.append((lbl, v))
    return out


def _structure_found(p):
    if p.drawing_mode == "cad" and p.params.get("FDN_STRIP") and p.params["FDN_STRIP"].confidence in ("High", "User"):
        return "load" if p.v("FDN_STRIP") >= 0.5 else "frame"
    return None


def _floor_h_found(p):
    prm = p.params.get("H_FLOOR")
    return round(prm.value, 2) if prm and prm.confidence in ("High", "User") else None


def _doors_found(p):
    ds = p.doors()
    return "ok" if ds and all(o.confidence in ("High", "User") for o in ds) else None


def _windows_found(p):
    ws = [o for o in p.windows() if o.kind == "window"]
    return "drawings" if ws and all(o.confidence in ("High", "User") for o in ws) else None


def _oht_found(p):
    prm = p.params.get("N_OHT")
    return 1.0 if prm and prm.confidence == "High" and prm.value >= 1 else None


def _septic_found(p):
    prm = p.params.get("SEPTIC_N")
    return 1.0 if prm and prm.confidence == "High" and prm.value >= 1 else None


def _ugt_found(p):
    prm = p.params.get("UGT_L")
    return round(prm.value, 2) if prm and prm.confidence == "High" else None


def _boundary_opts(p):
    w, d, g = p.v("PLOT_W") or 30.0, p.v("PLOT_D") or 45.0, p.v("GATE_W") or 10.0
    return [(f"Only the front wall with the gate (~{max(w - g, 0):.0f} ft)", round(max(w - g, 0), 1)),
            (f"Front and back (~{max(2 * w - g, 0):.0f} ft)", round(max(2 * w - g, 0), 1)),
            (f"All around the plot (~{max(2 * (w + d) - g, 0):.0f} ft)", round(max(2 * (w + d) - g, 0), 1))]


def _paving_opts(p):
    porch = sum(r.area for r in p.rooms_of("Porch / car porch"))
    opts = []
    if porch:
        opts += [(f"Only the car porch (~{porch:.0f} sq ft)", round(porch)), (f"Porch + front path (~{porch * 1.5:.0f} sq ft)", round(porch * 1.5))]
    opts += [("About 150 sq ft", 150.0), ("About 300 sq ft", 300.0)]
    return _dedupe(opts)


def _sockets(p):
    c = _c(p)
    b = c["main"]
    return [(f"Basic - 2 per room (about {2 * b + 2 * c['kitchens'] + c['baths']})", float(2 * b + 2 * c["kitchens"] + c["baths"])),
            (f"Normal - 4 per room (about {4 * b + 4 * c['kitchens'] + c['baths']})", float(4 * b + 4 * c["kitchens"] + c["baths"])),
            (f"Plenty - 6 per room (about {6 * b + 5 * c['kitchens'] + 2 * c['baths']})", float(6 * b + 5 * c["kitchens"] + 2 * c["baths"]))]


def _lights(p):
    c = _c(p)
    b, o = c["main"], c["other"]
    return [(f"Simple - 2 lights per room (about {2 * b + o + 4})", float(2 * b + o + 4)),
            (f"Normal - 4 per room (about {4 * b + 2 * o + 4})", float(4 * b + 2 * o + 4)),
            (f"Decorative - spotlights, 7+ per room (about {7 * b + 3 * o + 6})", float(7 * b + 3 * o + 6))]


def _fans(p):
    c = _c(p)
    return _dedupe([(f"In bedrooms & lounges ({c['beds'] + c['lounges']})", float(c["beds"] + c["lounges"])),
                    (f"Also in the kitchen(s) ({c['beds'] + c['lounges'] + c['kitchens']})", float(c["beds"] + c["lounges"] + c["kitchens"])),
                    ("No ceiling fans", 0.0)])


def _acs(p):
    c = _c(p)
    return _dedupe([(f"Bedrooms only ({c['beds']})", float(c["beds"])),
                    (f"Bedrooms + lounges ({c['beds'] + c['lounges']})", float(c["beds"] + c["lounges"])),
                    (f"Every main room ({c['main']})", float(c["main"]))])


def _geysers(p):
    c = _c(p)
    return _dedupe([(f"One per floor ({max(c['floors'], 1)})", float(max(c["floors"], 1))),
                    (f"One per bathroom ({c['baths']})", float(max(c["baths"], 1))), ("One for the whole house", 1.0)])


def _wardrobes(p):
    c = _c(p)
    return _dedupe([(f"In every bedroom ({c['beds']})", 48.0 * c["beds"]), ("Only in 2 main bedrooms", 96.0), ("Only in 1 bedroom", 48.0)])


def _counter(p):
    k = max(_c(p)["kitchens"], 1)
    return [("Small (straight counter, ~10 ft)", 10.0 * k), ("Normal L-shape (~14 ft)", 14.0 * k), ("Large (~20 ft)", 20.0 * k)]


def _lowvolt(p):
    c = _c(p)
    return _dedupe([(f"TV + internet in bedrooms & lounges (~{2 * (c['beds'] + c['lounges']) + 2})", float(2 * (c["beds"] + c["lounges"]) + 2)),
                    (f"Only in lounges (~{2 * c['lounges'] + 2})", float(2 * c["lounges"] + 2))])


QUESTIONS: List[Question] = [
    # ---- core (always asked unless read from the drawings)
    Question("structure", "core", "\U0001f3d7\ufe0f", "How the house is built", "Do brick walls carry the roof, or concrete columns and beams?",
             _fixed([("Brick walls carry the roof (load-bearing - most 5-10 marla houses)", "load"),
                     ("Concrete columns & beams (RCC frame)", "frame")]),
             lambda v: Effect(overrides={"FDN_STRIP": 1.0 if v == "load" else 0.0}), _structure_found,
             "Your engineer's drawings show this: columns on every corner = RCC frame."),
    Question("floor_h", "core", "\U0001f4cf", "Room height", "How high is each floor (floor to floor)?",
             _fixed([("Standard - 11'-6\" (rooms about 10'-6\" high)", 11.5), ("12 ft (rooms about 11 ft high)", 12.0),
                     ("13 ft (rooms about 12 ft high)", 13.0)]), _param_effect("H_FLOOR"), _floor_h_found),
    Question("walls", "core", "\U0001f9f1", "Wall material", "What will the walls be built with?",
             _fixed([("Burnt clay bricks (most common)", "Brick"), ("Concrete blocks", "Block")]),
             lambda v: Effect(options={"masonry": v})),
    Question("roof", "core", "\U0001f3e0", "Roof treatment", "How should the roof be protected from rain and heat?",
             _fixed([("Traditional - bitumen, polythene, mud & brick tiles", "Traditional"),
                     ("Insulated - foam boards + waterproof membrane (cooler house)", "Insulated")]),
             lambda v: Effect(options={"roof_system": v})),
    Question("sewer", "core", "\U0001f6bd", "Sewage", "Where does the house sewage go?",
             _fixed([("To the street sewer line", 0.0), ("To a septic tank on the plot", 1.0)]), _param_effect("SEPTIC_N"), _septic_found),
    Question("neighbours", "core", "\U0001f3d8\ufe0f", "Neighbours", "Is the house joined to the neighbours' houses?",
             _fixed([("Joined on both sides", 0.6), ("Corner plot - joined on one side", 0.8), ("Standing alone - open on all sides", 1.0)]),
             _param_effect("EXT_EXPOSED_FRAC"), help="Shared walls are not plastered or painted outside."),
    # ---- finishing
    Question("floor_type", "floor", "\U0001f7eb", "Floor finish", "What should be on the floors of the rooms?",
             _fixed([("Porcelain tiles 24x24 (most popular)", "Porcelain"), ("Ceramic tiles (economical)", "Ceramic"), ("Marble", "Marble")]),
             lambda v: Effect(options={"floor_finish": v}), help="Bathrooms & kitchen always get anti-slip tiles."),
    Question("bath_tiles", "walltiles", "\U0001f6c1", "Bathroom wall tiles", "How high should the bathroom wall tiles go?",
             _fixed([("Full height (~8 ft, most common)", 8.0), ("Half height (~4 ft)", 4.0)]),
             lambda v: Effect(options={"bath_tile_height_ft": float(v)})),
    Question("kit_tiles", "walltiles", "\U0001f373", "Kitchen wall tiles", "Tiles behind the kitchen counter?",
             _fixed([("Yes - about 2 ft above the counter", 2.0), ("Full wall height", 7.0), ("No kitchen wall tiles", 0.0)]),
             lambda v: Effect(options={"kitchen_tile_height_ft": float(v)})),
    Question("door_type", "doors", "\U0001f6aa", "Door type", "What kind of room doors?",
             _fixed([("Solid wood (deodar / ash) - traditional", "solid"), ("Flush doors (MDF / ply with laminate) - economical", "flush")]),
             lambda v: Effect(excl=("DWG-002",), incl=("DWG-003",)) if v == "flush" else Effect()),
    Question("door_count", "doors", "\U0001f6aa", "Doors", "We counted the doors from your rooms - is this right?",
             lambda p: [(f"Yes - {sum(o.qty for o in p.doors())} doors as listed in 'Doors & windows'", "ok")],
             lambda v: Effect(), _doors_found, "If not, correct the list in the 'Doors & windows' table below."),
    Question("win_type", "windows", "\U0001fa9f", "Window frames", "Which window frames?",
             _fixed([("Aluminium (most common)", "alu"), ("uPVC (better insulation, costlier)", "upvc")]),
             lambda v: Effect(excl=("DWG-009",), incl=("DWG-010",)) if v == "upvc" else Effect()),
    Question("win_size", "windows", "\U0001fa9f", "Window size", "How big are the windows in the rooms?",
             _fixed([("Small - 3 ft x 4 ft", (3.0, 4.0)), ("Standard - 4 ft x 5 ft", (4.0, 5.0)), ("Large - 5 ft x 5 ft", (5.0, 5.0)),
                     ("Very large - 6 ft x 5 ft", (6.0, 5.0))]),
             lambda v: Effect(options={"_window_size": v}), _windows_found,
             "Window widths are usually not written on house drawings. Glass, frames, grills and brickwork depend on them."),
    # ---- bathrooms & kitchen
    Question("wc_type", "sanitary", "\U0001f6bd", "Toilet type", "Which kind of WC (commode)?",
             _fixed([("Wall-hung with hidden tank (modern)", "wall"), ("Floor-mounted commode with tank", "floor")]),
             lambda v: Effect(excl=("SAN-001", "SAN-002"), incl=("SAN-003",)) if v == "floor" else Effect()),
    Question("geysers", "geyser", "\U0001f525", "Water heaters", "How many geysers?", _geysers, _param_effect("N_GEYSER")),
    Question("counter", "kitchen", "\U0001f373", "Kitchen counters", "How big are the kitchen counters?", _counter, _param_effect("COUNTER_LEN")),
    Question("countertop", "kitchen", "\U0001faa8", "Countertop", "Countertop material?",
             _fixed([("Granite (most common)", "granite"), ("No countertop (cabinets only)", "none")]),
             lambda v: Effect(excl=("KIT-004",)) if v == "none" else Effect()),
    Question("wardrobes", "wardrobes", "\U0001f45a", "Wardrobes", "Where do you want built-in wardrobes?", _wardrobes, _param_effect("WARDROBE_AREA")),
    # ---- electrical & cooling
    Question("lights", "wiring", "\U0001f4a1", "Lights", "What kind of lighting?", _lights, _param_effect("N_LIGHT"),
             help="Electrical symbols on drawings can't be counted automatically yet - pick what fits."),
    Question("sockets", "wiring", "\U0001f50c", "Plug sockets", "How many plug sockets?", _sockets, _param_effect("N_SK13")),
    Question("fans", "fixtures", "\U0001f300", "Ceiling fans", "Where do you want ceiling fans?", _fans, _param_effect("N_FAN")),
    Question("acs", "ac", "\u2744\ufe0f", "Air-conditioners", "Where will you install split ACs?", _acs, _param_effect("N_AC")),
    Question("ac_units", "ac", "\u2744\ufe0f", "AC units", "Should the AC units themselves be in the list?",
             _fixed([("No - only the piping & points (units bought later)", "no"), ("Yes - include the AC units", "yes")]),
             lambda v: Effect(incl=("HVC-001",)) if v == "yes" else Effect(excl=("HVC-001",))),
    Question("lowvolt_n", "lowvolt", "\U0001f4fa", "TV & internet points", "Where do you want TV / internet points?", _lowvolt, _param_effect("N_LV")),
    # ---- services & outside
    Question("ug_tank", "water", "\U0001f4a7", "Underground tank", "How big should the underground water tank be?",
             _fixed([("About 500 gallons", 4.0), ("About 1,000 gallons (6-8 people)", 5.7), ("About 1,500 gallons", 7.0),
                     ("About 2,000 gallons", 8.0), ("No underground tank", 0.0)]),
             lambda v: Effect(overrides={"UGT_L": float(v), "UGT_W": float(v), "UGT_D": 5.0 if v else 0.0}), _ugt_found),
    Question("oh_tank", "water", "\U0001f6b0", "Roof tank", "A water tank on the roof?",
             _fixed([("Yes - one roof tank", 1.0), ("No roof tank", 0.0)]), _param_effect("N_OHT"), _oht_found),
    Question("gas_src", "gas", "\U0001f525", "Gas supply", "What gas will the house use?",
             _fixed([("Piped gas (Sui gas)", "SNGPL"), ("LPG cylinders", "LPG")]), lambda v: Effect(options={"gas_source": v}),
             help="New Sui gas connections are restricted in many areas."),
    Question("boundary_len", "boundary", "\U0001f9f1", "Boundary wall", "Which boundary walls will you build?", _boundary_opts,
             _param_effect("BOUNDARY_LEN")),
    Question("cladding_area", "cladding", "\U0001faa8", "Front cladding", "How much of the front wall gets cladding?",
             lambda p: [(f"A feature strip (~{max(p.v('PLOT_W'), 20) * 4:.0f} sq ft)", round(max(p.v("PLOT_W"), 20) * 4)),
                        (f"About half the front (~{max(p.v('PLOT_W'), 20) * 10:.0f} sq ft)", round(max(p.v("PLOT_W"), 20) * 10)),
                        (f"The whole front (~{max(p.v('PLOT_W'), 20) * 22:.0f} sq ft)", round(max(p.v("PLOT_W"), 20) * 22))],
             _param_effect("CLADDING_AREA")),
    Question("paving_area", "paving", "\U0001f697", "Paving", "Which outside areas get tiles or pavers?", _paving_opts, _param_effect("PAVING_AREA")),
]
QUESTIONS_BY_ID = {q.id: q for q in QUESTIONS}


# ---------------------------------------------------------------------------
# compile
# ---------------------------------------------------------------------------
@dataclass
class ScopeSettings:
    options: Dict[str, object]
    overrides: Dict[str, float]
    window_size: Optional[Tuple[float, float]] = None


def active_questions(selected: set) -> List[Question]:
    return [q for q in QUESTIONS if q.scope == "core" or q.scope in selected]


def compile_scope(selected: set, answers: Dict[str, object]) -> ScopeSettings:
    """Unselected scope items -> excluded work items & materials; answers -> options & overrides."""
    excl_wis, excl_mats, incl_mats = set(), set(), set()
    for it in SCOPE_ITEMS:
        if it.key not in selected:
            excl_wis.update(it.wis)
            excl_mats.update(it.mats)
    opts: Dict[str, object] = {"include_false_ceiling": "ceiling" in selected, "include_rwh": "rwh" in selected}
    over: Dict[str, float] = {}
    win = None
    for q in active_questions(selected):
        if q.id not in answers or answers[q.id] is None:
            continue
        e = q.apply(answers[q.id])
        for k, v in e.options.items():
            if k == "_window_size":
                win = tuple(v)
            else:
                opts[k] = v
        over.update(e.overrides)
        excl_mats.update(e.excl)
        incl_mats.update(e.incl)
    if "gas" not in selected:
        opts["gas_source"] = "None"
    incl_mats -= excl_mats
    opts.update(excluded_wis=tuple(sorted(excl_wis)), excluded_mats=tuple(sorted(excl_mats)), included_mats=tuple(sorted(incl_mats)))
    return ScopeSettings(opts, over, win)


def answer_label(q: Question, p: DetailedProject, value) -> Optional[str]:
    for lbl, v in q.options(p):
        if v == value or (isinstance(v, float) and isinstance(value, (int, float)) and abs(v - float(value)) < 1e-6):
            return lbl
    return None
