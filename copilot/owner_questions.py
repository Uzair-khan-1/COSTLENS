"""
Plain-language 'quick questions' for home owners.

The sensitivity ranking (copilot.analysis.sensitivity) finds which assumed inputs move the
quantities most. This module turns the ones an OWNER can answer into everyday questions with
ready-made answers worked out from their own house (number of bedrooms, plot size ...), e.g.
"Where will you install ACs?  No AC / Bedrooms only (5) / Bedrooms + lounges (8)".
Technical inputs (PCC thickness, columns ...) are kept for the engineer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from copilot.analysis import WINDOW_TEST, Sensitivity
from detailed_mto.model import DetailedProject

ENGINEER_KEYS = {"PCC_T", "PCC_W_9", "FDN_DEPTH", "T_SLAB_IN", "COL_N", "BEAM_N", "FTG_L", "FTG_D", "ROOF_AREA",
                 "BAND_LEN", "RAIL_LEN", "N_RWP", "N_BATH"}

PLAIN_MATERIAL = {"Cement": "cement", "Steel": "steel (sarya)", "Bricks": "bricks", "Sand": "sand", "Crush": "bajri",
                  "Tiles": "tiles", "Paint": "paint", "Wiring": "wires & switches"}


@dataclass
class OwnerQuestion:
    key: str
    icon: str
    title: str
    question: str
    options: List[Tuple[str, object]]  # (label, value)
    current: str  # plain description of what we assumed
    effect: str  # "Big effect on wires & switches"
    help: str = ""
    level: int = 1  # 3 big, 2 medium, 1 small
    extra: dict = field(default_factory=dict)


def _counts(p: DetailedProject) -> dict:
    n = lambda *t: len(p.rooms_of(*t))  # noqa: E731
    main = n("Bedroom", "Drawing room", "Lounge / TV lounge", "Servant quarter")
    return {"beds": n("Bedroom"), "lounges": n("Lounge / TV lounge", "Drawing room"), "baths": n("Bathroom"),
            "kitchens": n("Kitchen"), "main": main, "other": n("Kitchen", "Bathroom", "Laundry", "Staircase", "Store / utility")}


def _effect(s: Sensitivity) -> Tuple[str, int]:
    level = 3 if s.impact >= 2.0 else (2 if s.impact >= 0.7 else 1)
    words = []
    for d in s.drivers[:2]:
        name = d.rsplit(" ", 1)[0]
        words.append(PLAIN_MATERIAL.get(name, name.lower()))
    what = " and ".join(words) if words else "several items"
    return f"{['', 'Small', 'Medium', 'Big'][level]} effect on {what}", level


def _nearest_label(options: List[Tuple[str, object]], value: float) -> Optional[str]:
    best, bd = None, 1e9
    for lbl, v in options:
        if isinstance(v, tuple) or v is None:
            continue
        d = abs(float(v) - value)
        if d < bd:
            best, bd = lbl, d
    if best is not None and bd <= max(0.12 * abs(value), 0.05):
        return best
    return None


def build_owner_question(s: Sensitivity, p: DetailedProject) -> Optional[OwnerQuestion]:
    if s.key in ENGINEER_KEYS:
        return None
    c = _counts(p)
    effect, level = _effect(s)
    w = p.v("PLOT_W") or 30.0
    d = p.v("PLOT_D") or 45.0
    gate = p.v("GATE_W") or 10.0
    k = s.key
    q: Optional[OwnerQuestion] = None
    if k == "N_AC":
        opts = [("No AC", 0), (f"Bedrooms only ({c['beds']})", c["beds"]),
                (f"Bedrooms + lounges ({c['beds'] + c['lounges']})", c["beds"] + c["lounges"]),
                (f"Every main room ({c['main']})", c["main"])]
        q = OwnerQuestion(k, "\u2744\ufe0f", "Air-conditioners", "Where will you install split ACs?", _dedupe(opts), "", effect,
                          "Each AC needs its own thick wire, switch and copper piping.")
    elif k == "N_SK13":
        base = c["main"]
        opts = [(f"Basic - 2 per room (about {2 * base + 2 * c['kitchens'] + c['baths']})", 2 * base + 2 * c["kitchens"] + c["baths"]),
                (f"Normal - 4 per room (about {4 * base + 4 * c['kitchens'] + c['baths']})", 4 * base + 4 * c["kitchens"] + c["baths"]),
                (f"Plenty - 6 per room (about {6 * base + 5 * c['kitchens'] + 2 * c['baths']})", 6 * base + 5 * c["kitchens"] + 2 * c["baths"])]
        q = OwnerQuestion(k, "\U0001f50c", "Plug sockets", "How many plug sockets do you want in the rooms?", opts, "", effect,
                          "More sockets = more wire, pipes and switch plates.")
    elif k == "N_LIGHT":
        base, other = c["main"], c["other"]
        opts = [(f"Simple - 2 lights per room (about {2 * base + other + 4})", 2 * base + other + 4),
                (f"Normal - 4 per room (about {4 * base + 2 * other + 4})", 4 * base + 2 * other + 4),
                (f"Decorative - spotlights, 7+ per room (about {7 * base + 3 * other + 6})", 7 * base + 3 * other + 6)]
        q = OwnerQuestion(k, "\U0001f4a1", "Lights", "What kind of lighting do you want?", opts, "", effect,
                          "Spotlights in false ceilings need many more light points and wires.")
    elif k == "N_FAN":
        opts = [("No ceiling fans", 0), (f"In bedrooms & lounges ({c['beds'] + c['lounges']})", c["beds"] + c["lounges"]),
                (f"Also in the kitchen(s) ({c['beds'] + c['lounges'] + c['kitchens']})", c["beds"] + c["lounges"] + c["kitchens"])]
        q = OwnerQuestion(k, "\U0001f300", "Ceiling fans", "Where do you want ceiling fans?", _dedupe(opts), "", effect)
    elif k == "BOUNDARY_LEN":
        opts = [("No boundary wall", 0), (f"Only the front wall with the gate (~{max(w - gate, 0):.0f} ft)", round(max(w - gate, 0), 1)),
                (f"Front and back (~{max(2 * w - gate, 0):.0f} ft)", round(max(2 * w - gate, 0), 1)),
                (f"All around the plot (~{max(2 * (w + d) - gate, 0):.0f} ft)", round(max(2 * (w + d) - gate, 0), 1))]
        q = OwnerQuestion(k, "\U0001f9f1", "Boundary wall", "Which boundary walls will you build?", opts, "", effect,
                          "Houses joined to neighbours usually only build the front wall.")
    elif k == "EXT_EXPOSED_FRAC":
        opts = [("Joined to houses on both sides", 0.6), ("Corner plot - joined on one side", 0.8),
                ("Standing alone - open on all sides", 1.0)]
        q = OwnerQuestion(k, "\U0001f3d8\ufe0f", "Neighbours", "Is your house joined to the neighbours' houses?", opts, "", effect,
                          "Walls shared with neighbours are not plastered or painted outside.")
    elif k == WINDOW_TEST:
        opts = [("Small - 3 ft x 4 ft", (3.0, 4.0)), ("Standard - 4 ft x 5 ft", (4.0, 5.0)),
                ("Large - 5 ft x 5 ft", (5.0, 5.0)), ("Very large - 6 ft x 5 ft", (6.0, 5.0))]
        q = OwnerQuestion(k, "\U0001fa9f", "Windows", "How big are the windows in the rooms?", opts,
                          "Standard - 4 ft x 5 ft", effect, "Window size changes glass, aluminium, grills and brickwork.")
    elif k == "UGT_L":
        opts = [("Small - about 500 gallons", 4.0), ("Standard - about 1,000 gallons", 5.7), ("Large - about 1,500 gallons", 7.0),
                ("Very large - about 2,000 gallons", 8.0)]
        q = OwnerQuestion(k, "\U0001f4a7", "Water tank", "How big should the underground water tank be?", opts, "", effect,
                          "A family of 6-8 usually needs 1,000-1,500 gallons.")
    elif k == "H_FLOOR":
        opts = [("Standard - rooms about 10.5 ft high", 11.5), ("High - rooms about 11 ft high", 12.0),
                ("Very high - rooms about 12 ft high", 13.0)]
        q = OwnerQuestion(k, "\U0001f4cf", "Room height", "How high will the rooms be?", opts, "", effect,
                          "Higher rooms need more bricks, plaster and paint.")
    elif k == "H_PLINTH":
        opts = [("About 1 ft above the road", 1.0), ("About 1.5 ft (common)", 1.5), ("About 2 ft", 2.0), ("About 3 ft", 3.0)]
        q = OwnerQuestion(k, "\U0001f6e3\ufe0f", "House floor level", "How high is the house floor above the road?", opts, "", effect,
                          "A higher floor needs more earth filling and foundation brickwork.")
    elif k == "H_PARAPET":
        opts = [("Low - about 2 ft", 2.0), ("Standard - about 3 ft", 3.0), ("High for privacy - about 4-5 ft", 4.5)]
        q = OwnerQuestion(k, "\U0001f3e0", "Roof wall", "How high should the wall around the roof be?", opts, "", effect)
    elif k == "WARDROBE_AREA":
        opts = [("No built-in wardrobes", 0), ("Only in 2 main bedrooms", 96), (f"In every bedroom ({c['beds']})", 48 * c["beds"])]
        q = OwnerQuestion(k, "\U0001f6aa", "Wardrobes", "Where do you want built-in wardrobes?", _dedupe(opts), "", effect)
    elif k == "COUNTER_LEN":
        kn = max(c["kitchens"], 1)
        opts = [("Small kitchen counters", 10 * kn), ("Normal L-shaped counters", 14 * kn), ("Large kitchen with long counters", 20 * kn)]
        q = OwnerQuestion(k, "\U0001f373", "Kitchen", "How big are the kitchen counters?", opts, "", effect)
    elif k == "PAVING_AREA":
        porch = sum(r.area for r in p.rooms_of("Porch / car porch")) or 200
        opts = [("No paving (plain concrete)", 0), (f"Only the car porch (~{porch:.0f} sq ft)", round(porch)),
                (f"Porch + front path (~{porch * 1.5:.0f} sq ft)", round(porch * 1.5))]
        q = OwnerQuestion(k, "\U0001f697", "Porch & driveway", "Which outside areas get tiles or pavers?", opts, "", effect)
    elif k == "SEWER_LEN":
        opts = [("Close - about 10 ft", 10.0), ("About 25 ft", 25.0), ("Far - about 50 ft", 50.0)]
        q = OwnerQuestion(k, "\U0001f6b0", "Sewer connection", "How far is the street sewer from the house?", opts, "", effect)
    if q is None:
        return None
    q.level = level
    if not q.current:
        unit = "" if s.unit in ("-", "Nos") else f" {s.unit}"
        q.current = _nearest_label(q.options, s.value) or f"about {s.value:,.0f}{unit}"
    return q


def _dedupe(opts: List[Tuple[str, object]]) -> List[Tuple[str, object]]:
    seen, out = set(), []
    for lbl, v in opts:
        key = v if not isinstance(v, float) else round(v, 3)
        if key in seen:
            continue
        seen.add(key)
        out.append((lbl, v))
    return out


def split_questions(sens: List[Sensitivity], p: DetailedProject, max_owner: int = 6) -> Tuple[List[OwnerQuestion], List[Sensitivity]]:
    owner, engineer = [], []
    for s in sens:
        q = build_owner_question(s, p)
        if q is not None:
            if len(owner) < max_owner:
                owner.append(q)
        elif s.key in ENGINEER_KEYS:
            engineer.append(s)
    return owner, engineer[:6]


def stars(level: int) -> str:
    return "\u2605" * level + "\u2606" * (3 - level)
