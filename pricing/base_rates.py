"""
Indicative starting rates (PKR, September 2026, Islamabad/Rawalpindi basis) for every material of the
Master Material Database, per MATERIAL UNIT, plus labour rates per BOQ work item and city factors.

STATUS: INDICATIVE - TO CONFIRM. These are market-indication starting points compiled from public rate
reports (e.g. steel Rs 258-265/kg and cement Rs 1,350-1,560/bag reported in Aug-Sep 2026; A-class bricks
Rs 17-19 each in Lahore; crush Rs 95-330/cft). The price agent (pricing/agent.py) replaces the frequently
changing items with dated, sourced rates per city; everything else should be reviewed every 3-6 months.

Format: MAT_ID: (typical, low, high) per material unit.
"""
from __future__ import annotations

BASE_DATE = "2026-09-01"
BASE_SOURCE = "CostLens indicative rate book (Sep 2026) - to confirm"

CITIES = ["Islamabad", "Rawalpindi", "Lahore", "Karachi", "Peshawar", "Quetta"]
CITY_ALIASES = {"Faisalabad": "Lahore", "Multan": "Lahore", "Other": "Islamabad"}
# multiplier on the Islamabad basis when no city-specific (live) rate exists
MATERIAL_CITY_FACTOR = {"Islamabad": 1.00, "Rawalpindi": 0.99, "Lahore": 0.97, "Karachi": 1.04, "Peshawar": 1.01, "Quetta": 1.08}
LABOUR_CITY_FACTOR = {"Islamabad": 1.00, "Rawalpindi": 0.97, "Lahore": 0.95, "Karachi": 1.05, "Peshawar": 0.92, "Quetta": 0.95}


def city_key(city: str) -> str:
    c = (city or "").strip()
    return c if c in CITIES else CITY_ALIASES.get(c, "Islamabad")


R = {
    # ---- preliminaries & site
    "PRE-001": (650, 450, 900), "PRE-002": (45000, 30000, 70000), "PRE-003": (60000, 40000, 90000), "PRE-004": (8000, 5000, 12000),
    "PRE-005": (35000, 25000, 60000), "PRE-006": (1500, 1000, 2500), "PRE-007": (25000, 15000, 40000),
    # ---- earthwork
    "EW-001": (12, 8, 20), "EW-002": (35, 25, 55), "EW-003": (45, 30, 70), "EW-004": (2200, 1600, 3200), "EW-005": (40000, 20000, 80000),
    "EW-006": (60, 40, 90), "EW-007": (12, 8, 18),
    # ---- concrete & aggregates
    "CON-001": (1450, 1300, 1600), "CON-002": (1650, 1500, 1850), "CON-003": (180, 140, 240),
    "CON-004": (135, 95, 190), "CON-005": (95, 60, 140), "CON-006": (190, 130, 280), "CON-007": (210, 150, 300), "CON-008": (160, 100, 240),
    "CON-009": (650, 550, 800), "CON-010": (900, 650, 1300), "CON-011": (1100, 800, 1600), "CON-012": (18, 10, 30), "CON-013": (6, 4, 10),
    "CON-014": (220, 160, 320),
    # ---- steel
    "RBR-001": (265, 245, 285), "RBR-002": (262, 240, 282), "RBR-003": (260, 238, 280), "RBR-004": (260, 238, 280),
    "RBR-006": (420, 350, 500), "RBR-007": (262, 240, 282), "RBR-008": (140, 110, 180), "RBR-009": (320, 280, 380), "RBR-010": (262, 240, 282),
    # ---- formwork (hire / consumables)
    "FRM-001": (18, 12, 28), "FRM-002": (95, 70, 130), "FRM-003": (40, 25, 60), "FRM-004": (4500, 3500, 6000), "FRM-005": (380, 320, 450),
    "FRM-006": (250, 150, 400), "FRM-007": (12, 8, 18), "FRM-008": (10, 7, 15),
    # ---- masonry
    "MAS-001": (17.5, 15, 21), "MAS-002": (13, 11, 16), "MAS-003": (22, 16, 30), "MAS-004": (95, 75, 130), "MAS-005": (900, 700, 1200),
    "MAS-006": (1800, 1400, 2400), "MAS-009": (450, 350, 600), "MAS-010": (120, 80, 200), "MAS-011": (180, 120, 280), "MAS-012": (450, 300, 750),
    "MAS-013": (35, 25, 55), "MAS-014": (350, 250, 550),
    # ---- waterproofing & insulation
    "WPF-001": (260, 200, 350), "WPF-002": (2800, 2000, 3800), "WPF-003": (14, 9, 20), "WPF-004": (650, 450, 900), "WPF-005": (220, 160, 320),
    "WPF-006": (1400, 1000, 2000), "WPF-007": (380, 280, 520), "WPF-008": (85, 60, 130), "WPF-009": (25, 15, 40), "WPF-010": (25, 15, 40),
    "WPF-011": (450, 350, 650), "WPF-012": (2200, 1600, 3200), "WPF-013": (180, 120, 260), "WPF-014": (40, 25, 60),
    # ---- plaster
    "PLS-001": (45, 30, 70), "PLS-002": (60, 40, 90), "PLS-003": (1400, 1100, 1800), "PLS-004": (900, 700, 1200), "PLS-005": (1500, 1100, 2000),
    "PLS-006": (120, 80, 180),
    # ---- flooring & tiling
    "FLR-001": (260, 170, 450), "FLR-002": (130, 90, 200), "FLR-003": (150, 100, 250), "FLR-004": (380, 220, 650), "FLR-005": (650, 450, 1100),
    "FLR-006": (450, 300, 750), "FLR-007": (120, 70, 200), "FLR-008": (420, 280, 650), "FLR-010": (60, 45, 85), "FLR-011": (180, 120, 450),
    "FLR-012": (2, 1, 4), "FLR-013": (180, 120, 300), "FLR-014": (45, 30, 70), "FLR-015": (220, 160, 320), "FLR-016": (450, 300, 750),
    "FLR-018": (350, 220, 550),
    # ---- doors & windows
    "DWG-001": (9500, 7000, 14000), "DWG-002": (2200, 1500, 3500), "DWG-003": (1100, 800, 1600), "DWG-004": (22000, 15000, 35000),
    "DWG-005": (180000, 120000, 300000), "DWG-006": (6500, 4000, 11000), "DWG-007": (4500, 3000, 8000), "DWG-008": (250, 180, 350),
    "DWG-009": (1300, 950, 1900), "DWG-010": (1600, 1200, 2300), "DWG-011": (320, 220, 500), "DWG-012": (1100, 800, 1600), "DWG-013": (360, 300, 450),
    "DWG-014": (220, 150, 320), "DWG-015": (1100, 800, 1600), "DWG-016": (850, 600, 1200), "DWG-017": (35000, 25000, 55000), "DWG-018": (1200, 900, 1800),
    # ---- ceilings
    "CLG-001": (95, 70, 140), "CLG-002": (110, 80, 160), "CLG-003": (180, 120, 280), "CLG-004": (350, 250, 500), "CLG-005": (180, 120, 300),
    "CLG-006": (4500, 3000, 7000),
    # ---- paints
    "PNT-001": (190, 140, 260), "PNT-002": (3200, 2400, 4500), "PNT-003": (4200, 2800, 6500), "PNT-004": (3000, 2200, 4200), "PNT-005": (6500, 4500, 9000),
    "PNT-006": (450, 300, 700), "PNT-007": (4800, 3500, 6500), "PNT-008": (3800, 2800, 5000), "PNT-009": (2200, 1500, 3200), "PNT-010": (900, 650, 1300),
    "PNT-011": (15000, 10000, 25000), "PNT-012": (220, 150, 320), "PNT-013": (650, 450, 900),
    # ---- joinery
    "JNR-001": (420, 300, 650), "JNR-002": (650, 450, 1000), "JNR-003": (6500, 4000, 12000), "JNR-004": (28000, 18000, 45000), "JNR-005": (4500, 2800, 9000),
    "JNR-007": (420, 350, 520), "JNR-008": (650, 400, 1200), "JNR-009": (450, 250, 800), "JNR-010": (1200, 800, 2000),
    # ---- kitchen
    "KIT-001": (6500, 4500, 10000), "KIT-002": (5000, 3500, 8000), "KIT-003": (850, 550, 1400), "KIT-004": (1100, 750, 1800), "KIT-005": (18000, 12000, 30000),
    "KIT-006": (9000, 5500, 16000), "KIT-007": (38000, 25000, 70000), "KIT-008": (45000, 28000, 90000), "KIT-009": (15000, 9000, 28000),
    "KIT-010": (95000, 65000, 160000), "KIT-013": (25, 15, 40),
    # ---- water supply
    "PWS-001": (70, 55, 95), "PWS-002": (100, 80, 135), "PWS-003": (150, 120, 200), "PWS-004": (320, 240, 450), "PWS-005": (110, 85, 150),
    "PWS-006": (90, 60, 140), "PWS-007": (450, 300, 700), "PWS-008": (1400, 900, 2400), "PWS-009": (2800, 1800, 4500), "PWS-010": (1500, 1000, 2400),
    "PWS-011": (6500, 4000, 11000), "PWS-012": (25000, 15000, 45000), "PWS-013": (38000, 25000, 65000), "PWS-014": (28000, 18000, 45000),
    "PWS-015": (1800, 1200, 3000), "PWS-016": (42000, 30000, 60000), "PWS-017": (160, 110, 240), "PWS-018": (60, 35, 100), "PWS-019": (6000, 4000, 10000),
    "PWS-020": (3500, 2200, 6000), "PWS-021": (32000, 22000, 50000), "PWS-022": (65000, 40000, 120000), "PWS-023": (130, 90, 180), "PWS-024": (250, 150, 400),
    # ---- drainage
    "PDR-001": (220, 170, 300), "PDR-002": (150, 115, 200), "PDR-003": (90, 70, 125), "PDR-004": (120, 90, 170), "PDR-005": (200, 150, 280),
    "PDR-006": (350, 200, 600), "PDR-007": (1600, 1100, 2400), "PDR-008": (250, 150, 400), "PDR-009": (2200, 1200, 4000), "PDR-010": (900, 600, 1500),
    "PDR-011": (1800, 1100, 3200), "PDR-012": (450, 350, 650), "PDR-013": (9000, 6000, 14000), "PDR-014": (6500, 4000, 11000), "PDR-015": (4500, 3000, 7000),
    "PDR-016": (5500, 3500, 8500), "PDR-017": (450, 300, 700), "PDR-018": (380, 280, 520), "PDR-019": (1600, 1100, 2500), "PDR-020": (95, 60, 140),
    "PDR-021": (250, 150, 400), "PDR-022": (2500, 1500, 4500), "PDR-023": (15000, 10000, 25000),
    # ---- sanitary & CP
    "SAN-001": (28000, 16000, 55000), "SAN-002": (38000, 22000, 65000), "SAN-003": (26000, 15000, 55000), "SAN-004": (14000, 8000, 30000),
    "SAN-005": (9500, 5500, 20000), "SAN-006": (32000, 18000, 65000), "SAN-007": (3500, 2000, 7000), "SAN-008": (1200, 700, 2200), "SAN-009": (650, 400, 1100),
    "SAN-010": (12000, 7000, 25000), "SAN-011": (9000, 5000, 18000), "SAN-012": (1400, 1000, 2000), "SAN-013": (14000, 9000, 25000), "SAN-014": (1800, 1100, 3000),
    "SAN-015": (1400, 900, 2500), "SAN-016": (65000, 40000, 120000), "SAN-017": (140000, 100000, 220000), "SAN-018": (38000, 25000, 65000),
    "SAN-019": (42000, 30000, 60000),
    # ---- gas
    "GAS-001": (320, 250, 420), "GAS-002": (250, 150, 400), "GAS-003": (1600, 1000, 2600), "GAS-004": (35, 20, 55), "GAS-005": (35000, 20000, 60000),
    "GAS-006": (12000, 8000, 20000),
    # ---- electrical
    "ELE-001": (32, 24, 45), "ELE-002": (48, 36, 65), "ELE-003": (90, 60, 140), "ELE-004": (35, 20, 60), "ELE-005": (45, 30, 80),
    "ELE-006": (110, 90, 140), "ELE-007": (185, 150, 230), "ELE-008": (310, 250, 380), "ELE-009": (470, 380, 580), "ELE-010": (1300, 1000, 1700),
    "ELE-011": (110, 90, 140), "ELE-012": (18000, 12000, 28000), "ELE-013": (1800, 1300, 2500), "ELE-014": (12000, 7000, 25000), "ELE-015": (850, 500, 1600),
    "ELE-016": (4500, 2800, 8000), "ELE-017": (7500, 4500, 14000), "ELE-018": (9000, 5000, 18000), "ELE-019": (9500, 6000, 16000), "ELE-020": (450, 250, 900),
    "ELE-021": (650, 350, 1200), "ELE-022": (750, 450, 1300), "ELE-023": (2200, 1400, 3800), "ELE-024": (1800, 1100, 3200), "ELE-025": (1500, 900, 2600),
    "ELE-026": (1600, 900, 3000), "ELE-027": (2200, 1200, 4500), "ELE-028": (90, 60, 130), "ELE-029": (140, 100, 200), "ELE-030": (28000, 15000, 55000),
    "ELE-031": (6500, 4000, 12000), "ELE-032": (1100, 600, 2200), "ELE-033": (1800, 1100, 3000), "ELE-034": (15000, 6000, 45000), "ELE-035": (3500, 2000, 7000),
    "ELE-036": (14000, 9000, 24000), "ELE-037": (450, 300, 700), "ELE-038": (6500, 4000, 11000), "ELE-039": (12000, 8000, 20000), "ELE-040": (85000, 60000, 140000),
    # ---- HVAC
    "HVC-001": (165000, 120000, 260000), "HVC-002": (1100, 850, 1500), "HVC-003": (180, 120, 260), "HVC-004": (220, 170, 300), "HVC-005": (60, 40, 90),
    "HVC-006": (3500, 2200, 6000), "HVC-007": (450, 300, 700), "HVC-008": (5500, 3500, 9000), "HVC-009": (350, 220, 550), "HVC-010": (1500, 900, 2500),
    "HVC-011": (650, 450, 1000), "HVC-012": (85, 60, 130), "HVC-013": (3500, 2000, 6000),
    # ---- solar & backup
    "SOL-001": (25000, 15000, 40000), "SOL-002": (135000, 105000, 180000), "SOL-003": (15000, 8000, 25000),
    # ---- external works
    "EXT-001": (180, 120, 280), "EXT-002": (350, 250, 500), "EXT-003": (95, 60, 140), "EXT-004": (60, 40, 90), "EXT-005": (90, 50, 160),
    "EXT-006": (220, 160, 320), "EXT-007": (5500, 4000, 8000), "EXT-008": (1800, 1200, 3000), "EXT-009": (8000, 3000, 18000), "EXT-010": (650, 350, 1300),
    "EXT-011": (4500, 2800, 9000), "EXT-012": (1100, 700, 2000),
    # ---- rainwater harvesting
    "RWH-001": (950, 700, 1400), "RWH-002": (160, 100, 250), "RWH-003": (35000, 22000, 55000), "RWH-004": (6500, 4000, 11000), "RWH-005": (650, 450, 1000),
    "RWH-006": (220, 170, 300), "RWH-007": (1200, 900, 1700),
    # ---- fire & life safety
    "FLS-001": (4500, 2500, 8000), "FLS-002": (8500, 6000, 14000), "FLS-003": (6500, 4000, 11000),
    # ---- miscellaneous
    "MSC-001": (1.2, 0.8, 2.0), "MSC-002": (15, 8, 25), "MSC-003": (8000, 5000, 12000), "MSC-004": (8, 5, 12), "MSC-005": (12, 8, 20),
    "MSC-006": (20000, 12000, 35000), "MSC-007": (30000, 20000, 50000), "MSC-008": (150000, 80000, 300000), "MSC-009": (3500, 2500, 5000),
}

# ---------------------------------------------------------------------------
# Frequently changing materials refreshed by the price agent
#   query  : web search words ({city} is filled in)
#   unit   : material unit in the database;  units: accepted price units -> multiplier to the material unit
#   sane   : plausible range per material unit (anything outside is rejected)
# ---------------------------------------------------------------------------
LIVE_ITEMS = {
    "CON-001": {"name": "Cement (OPC, 50 kg bag)", "query": "cement price today {city} per bag", "unit": "bag",
                "units": {"bag": 1.0, "50 kg bag": 1.0, "50kg bag": 1.0}, "sane": (1100, 2200), "keywords": ["cement"]},
    "RBR-002": {"name": "Steel bars Grade 60 (#4, 12 mm)", "query": "steel sarya rate today {city} grade 60 per kg", "unit": "kg",
                "units": {"kg": 1.0, "ton": 0.001, "tonne": 0.001, "metric ton": 0.001, "maund": 1 / 40.0}, "sane": (190, 360),
                "keywords": ["steel", "sarya", "saria", "rebar"], "also": ["RBR-001", "RBR-003", "RBR-004", "RBR-007", "RBR-010"]},
    "MAS-001": {"name": "Bricks, A class (awwal)", "query": "bricks rate today {city} per 1000", "unit": "Nos",
                "units": {"brick": 1.0, "piece": 1.0, "1000 bricks": 0.001, "thousand": 0.001, "1000": 0.001}, "sane": (9, 32),
                "keywords": ["brick", "bricks", "eent"]},
    "CON-004": {"name": "Sand for concrete (Lawrencepur / Chenab)", "query": "sand rate per cft today {city} lawrencepur chenab",
                "unit": "cft", "units": {"cft": 1.0, "cubic feet": 1.0, "cubic foot": 1.0, "100 cft": 0.01}, "sane": (35, 260),
                "keywords": ["sand", "rait", "lawrencepur", "chenab", "ravi"], "also": ["CON-005"]},
    "CON-006": {"name": "Crush / bajri 3/4 inch", "query": "crush bajri rate per cft today {city}", "unit": "cft",
                "units": {"cft": 1.0, "cubic feet": 1.0, "cubic foot": 1.0, "100 cft": 0.01}, "sane": (70, 380),
                "keywords": ["crush", "bajri", "aggregate", "margalla", "sargodha"], "also": ["CON-007", "CON-008"]},
    "ELE-006": {"name": "Copper house wire 3/29 (90 m coil)", "query": "3/29 wire price pakistan cables fast 90 meter coil",
                "unit": "m", "units": {"m": 1.0, "meter": 1.0, "metre": 1.0, "coil": 1 / 90.0, "90 m coil": 1 / 90.0, "roll": 1 / 90.0},
                "sane": (60, 220), "keywords": ["3/29", "wire", "cable"], "national": True},
    "ELE-007": {"name": "Copper house wire 7/29 (90 m coil)", "query": "7/29 wire price pakistan cables 90 meter coil",
                "unit": "m", "units": {"m": 1.0, "meter": 1.0, "coil": 1 / 90.0, "90 m coil": 1 / 90.0, "roll": 1 / 90.0},
                "sane": (100, 350), "keywords": ["7/29", "wire", "cable"], "national": True},
    "ELE-008": {"name": "Copper house wire 7/36 (90 m coil)", "query": "7/36 wire price pakistan cables 90 meter coil",
                "unit": "m", "units": {"m": 1.0, "meter": 1.0, "coil": 1 / 90.0, "90 m coil": 1 / 90.0, "roll": 1 / 90.0},
                "sane": (170, 560), "keywords": ["7/36", "wire", "cable"], "national": True},
    "PWS-001": {"name": "PPR pipe 20 mm PN20", "query": "PPR pipe 20mm price pakistan per length", "unit": "rft",
                "units": {"rft": 1.0, "ft": 1.0, "foot": 1.0, "4 m length": 1 / 13.12, "length": 1 / 13.12, "meter": 1 / 3.281, "m": 1 / 3.281},
                "sane": (35, 160), "keywords": ["ppr", "pipe"], "national": True},
    "PDR-001": {"name": "uPVC pipe 4 inch", "query": "4 inch upvc pipe price pakistan per foot", "unit": "rft",
                "units": {"rft": 1.0, "ft": 1.0, "foot": 1.0, "10 ft length": 0.1, "length": 0.1}, "sane": (100, 480),
                "keywords": ["upvc", "pvc", "pipe"], "national": True, "also": ["PDR-002", "PDR-003", "PDR-004", "PDR-005"]},
    "FLR-001": {"name": "Porcelain floor tiles 24x24", "query": "porcelain tiles 24x24 price per sq ft pakistan {city}", "unit": "sft",
                "units": {"sft": 1.0, "sq ft": 1.0, "square foot": 1.0, "sqm": 1 / 10.764, "square meter": 1 / 10.764}, "sane": (110, 700),
                "keywords": ["tile", "tiles", "porcelain"]},
    "PNT-003": {"name": "Interior emulsion paint (gallon)", "query": "emulsion paint price per gallon pakistan", "unit": "gal",
                "units": {"gallon": 1.0, "gal": 1.0, "litre": 3.64, "liter": 3.64}, "sane": (1800, 11000), "keywords": ["emulsion", "paint"],
                "national": True},
    "WPF-001": {"name": "Bitumen (roofing)", "query": "bitumen price per kg pakistan", "unit": "kg",
                "units": {"kg": 1.0, "ton": 0.001, "tonne": 0.001}, "sane": (120, 500), "keywords": ["bitumen", "coal tar"], "national": True},
}

# ---------------------------------------------------------------------------
# Labour rates per BOQ work item unit (PKR, Islamabad basis, Sep 2026) - INDICATIVE, TO CONFIRM
# 'labour only' contract rates (materials by owner), as commonly quoted by thekedars.
# ---------------------------------------------------------------------------
LABOUR = {
    "WI-PRE-01": 60000, "WI-PRE-02": 0.0,
    "WI-EW-01": 22, "WI-EW-02": 25, "WI-EW-03": 28, "WI-EW-04": 12, "WI-EW-05": 10, "WI-EW-06": 8, "WI-EW-07": 4, "WI-EW-08": 3,
    "WI-EW-09": 3,
    "WI-CN-01": 55, "WI-CN-02": 55, "WI-CN-03": 85, "WI-CN-04": 95, "WI-CN-05": 110, "WI-CN-06": 100, "WI-CN-07": 80, "WI-CN-08": 120,
    "WI-CN-09": 95, "WI-CN-10": 110, "WI-CN-11": 110, "WI-CN-12": 25, "WI-CN-13": 18,
    "WI-RF-01": 22, "WI-RF-02": 26, "WI-RF-03": 25, "WI-RF-04": 22, "WI-RF-05": 28, "WI-RF-06": 26, "WI-RF-07": 26,
    "WI-FW-01": 40, "WI-FW-02": 55,
    "WI-MS-01": 60, "WI-MS-02": 70, "WI-MS-03": 32, "WI-MS-04": 75, "WI-MS-05": 10, "WI-MS-06": 35,
    "WI-PL-01": 32, "WI-PL-02": 40, "WI-PL-03": 38, "WI-PL-04": 45,
    "WI-WP-01": 45, "WI-WP-02": 40, "WI-WP-03": 30, "WI-WP-04": 18,
    "WI-FL-01": 65, "WI-FL-02": 60, "WI-FL-03": 70, "WI-FL-04": 90, "WI-FL-05": 35, "WI-FL-06": 250, "WI-FL-07": 45, "WI-FL-08": 120,
    "WI-DW-01": 120, "WI-DW-02": 60, "WI-DW-03": 1200, "WI-DW-04": 90, "WI-DW-05": 40, "WI-DW-06": 350, "WI-DW-07": 60,
    "WI-CL-01": 65,
    "WI-PT-01": 30, "WI-PT-02": 32, "WI-PT-03": 28, "WI-PT-04": 18, "WI-PT-05": 45,
    "WI-EL-01": 1100, "WI-EL-02": 1100, "WI-EL-03": 1100, "WI-EL-04": 1500, "WI-EL-05": 2500, "WI-EL-06": 1200, "WI-EL-07": 60,
    "WI-EL-08": 6000, "WI-EL-09": 8000, "WI-EL-10": 500,
    "WI-HV-01": 9000, "WI-HV-02": 1500,
    "WI-PB-01": 6000, "WI-PB-02": 3500, "WI-PB-03": 4500, "WI-PB-04": 1200, "WI-PB-05": 2500, "WI-PB-06": 15000, "WI-PB-07": 3500,
    "WI-PB-08": 2000, "WI-PB-09": 80, "WI-PB-10": 3000, "WI-PB-11": 150, "WI-PB-12": 12000, "WI-PB-13": 5000, "WI-PB-14": 25000,
    "WI-GS-01": 3500,
    "WI-KT-01": 1800, "WI-KT-02": 1500, "WI-KT-03": 600, "WI-JN-01": 220,
    "WI-EX-01": 1400, "WI-EX-02": 45000,
}
