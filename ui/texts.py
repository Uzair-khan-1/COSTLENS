"""
Plain-language texts for a non-technical audience (land owners), with short Urdu hints,
and the common Pakistani residential defaults used when the user does not choose otherwise.
"""
from __future__ import annotations

STEP_TITLES = {
    1: ("Tell us about your plot", "اپنے پلاٹ کے بارے میں بتائیں"),
    2: ("Your house design", "گھر کا نقشہ"),
    3: ("Check the details", "تفصیلات چیک کریں"),
    4: ("Materials & Bill of Quantities", "سامان کی فہرست اور BOQ"),
    5: ("Download & share", "ڈاؤن لوڈ اور شیئر کریں"),
}
STEP_TITLE_SKETCH_2 = ("Your requirements", "آپ کی ضروریات")

TIPS = {
    1: (["Choose what you have: architect's drawings, a hand sketch, or just an idea.",
         "Pick your city and plot size - everything else starts from common Pakistani house standards.",
         "Engineers can change the technical settings under 'Advanced settings'."],
        "جو آپ کے پاس ہے وہ منتخب کریں، پھر شہر اور پلاٹ کا سائز"),
    2: (["We read the drawings for you - room sizes, walls, doors, bathrooms, tanks.",
         "If it looks right, press the green button. The AI is optional."],
        "ہم آپ کے نقشے سے کمرے، دیواریں اور دروازے خود پڑھتے ہیں"),
    3: (["Answer the few questions at the top - they change the quantities the most.",
         "Check the list of rooms and the door & window sizes. Fix anything that looks wrong.",
         "Then press 'Calculate materials'."],
        "اوپر کے سوالات کے جواب دیں اور کمروں کی فہرست چیک کریں"),
    4: (["'What to buy' is your shopping list, in bags, tons and bricks.",
         "'Things to double-check' tells you what may be wrong before you order.",
         "Ask the assistant anything, e.g. 'what if I use block walls?'"],
        "یہ آپ کی خریداری کی فہرست ہے - بوریاں، ٹن اور اینٹیں"),
    5: (["Excel for your contractor, PDF or WhatsApp for your suppliers.",
         "Save the project file to continue later."],
        "ٹھیکیدار کے لیے ایکسل، دکاندار کے لیے PDF یا واٹس ایپ"),
}

# City -> common defaults (marla size, CDA recharge-well rule, piped gas name)
CITIES = {
    "Islamabad": {"marla_sqft": 272.25, "rwh": True, "gas": "SNGPL", "note": "CDA: 1 marla = 272.25 sq ft; rainwater recharge well required."},
    "Rawalpindi": {"marla_sqft": 272.25, "rwh": False, "gas": "SNGPL", "note": "1 marla = 272.25 sq ft (traditional)."},
    "Lahore": {"marla_sqft": 225.0, "rwh": False, "gas": "SNGPL", "note": "LDA / most societies: 1 marla = 225 sq ft."},
    "Faisalabad": {"marla_sqft": 272.25, "rwh": False, "gas": "SNGPL", "note": "1 marla = 272.25 sq ft (traditional)."},
    "Multan": {"marla_sqft": 272.25, "rwh": False, "gas": "SNGPL", "note": "1 marla = 272.25 sq ft (traditional)."},
    "Peshawar": {"marla_sqft": 272.25, "rwh": False, "gas": "SNGPL", "note": "1 marla = 272.25 sq ft (traditional)."},
    "Karachi": {"marla_sqft": 225.0, "rwh": False, "gas": "SNGPL", "note": "Karachi plots are in square yards: 120 sq yd = 1,080 sq ft (about 4.8 marla of 225)."},
    "Other": {"marla_sqft": 272.25, "rwh": False, "gas": "SNGPL", "note": "Check your society's marla size (225 or 272.25 sq ft)."},
}

FINISH_CARDS = {
    "Economy": ("\U0001f3e0", "Economy", "Ceramic tiles, basic fittings, no false ceilings."),
    "Standard": ("\U0001f3e1", "Standard", "Porcelain tiles, good fittings, false ceiling in main rooms. Most common."),
    "Premium": ("\U0001f3db\ufe0f", "Premium", "Marble / large tiles, premium fittings, extra features."),
}

GLOSSARY = [
    ("Marla", "Unit of land area: 272.25 sq ft (traditional / CDA) or 225 sq ft (LDA and many societies)."),
    ("Kanal", "20 marla."),
    ("Covered area", "Built-up floor area of the house (all floors), not the plot."),
    ("Mumty", "The small room on the roof over the stairs."),
    ("MTO (Material Take-Off)", "The list of materials and quantities needed to build the house."),
    ("BOQ (Bill of Quantities)", "The list of work items (e.g. brickwork in cft, plaster in sq ft) with quantities. "
                                 "Prices will be added in a later version."),
    ("Grey structure", "The shell: foundations, walls, slabs, plaster, plumbing & wiring pipes - before finishing."),
    ("Finishing", "Tiles, paint, doors, windows, sanitary fittings, lights, kitchen..."),
    ("PCC", "Plain cement concrete (no steel) - e.g. under foundations and floors."),
    ("RCC", "Reinforced cement concrete (with steel bars / sarya) - slabs, beams, columns."),
    ("Sarya", "Steel bars. #3 = 10 mm, #4 = 12 mm, #5 = 16 mm."),
    ("Bajri / crush", "Crushed stone aggregate used in concrete."),
    ("DPC", "Damp proof course - a waterproof layer at plinth level that stops rising damp."),
    ("Plinth", "The height of the house floor above the road/ground."),
    ("Chogath", "Door frame (usually wood)."),
    ("Lintel / band", "Concrete beam over doors and windows; a continuous 'seismic band' makes the house safer in earthquakes."),
    ("Wastage", "Extra quantity for breakage, cutting and spillage - already included in the quantities to buy."),
    ("Load-bearing", "The brick walls carry the roof (common for 5-10 marla). 'RCC frame' = concrete columns and beams carry it."),
]

STEP_LABELS_PLAIN = ["1. Your plot", "2. Your house design", "3. Check details", "4. Materials & BOQ", "5. Download"]
