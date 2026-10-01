"""
Plain-language texts for a non-technical audience (land owners), with short Urdu hints,
and the common Pakistani residential defaults used when the user does not choose otherwise.
"""
from __future__ import annotations

STEP_TITLES = {
    1: ("Start your project", "اپنا پروجیکٹ شروع کریں"),
    2: ("Your house design", "گھر کا نقشہ"),
    3: ("Your scope & details", "کام کی تفصیل اور ضروری معلومات"),
    4: ("Materials you need (MTO)", "درکار سامان کی فہرست"),
    5: ("Bill of Quantities & cost", "کام کی فہرست (BOQ) اور لاگت"),
    6: ("When can I move in? Schedule, workers & money per month", "گھر کب تیار ہوگا؟ شیڈول، مزدور اور ماہانہ رقم"),
    7: ("Download & share", "ڈاؤن لوڈ اور شیئر کریں"),
}
STEP_TITLE_SKETCH_2 = ("Your requirements", "آپ کی ضروریات")

TIPS = {
    1: (["Choose what you have: architect's drawings, a hand sketch, or just an idea.",
         "Pick your city. The plot size is read from your drawings - you don't have to enter it.",
         "Nothing is guessed: whatever is not on your drawings is asked in simple questions later."],
        "جو آپ کے پاس ہے وہ منتخب کریں اور شہر چنیں - پلاٹ کا سائز نقشے سے لیا جائے گا"),
    2: (["We read the drawings for you - room sizes, walls, doors, bathrooms, tanks.",
         "If it looks right, press the green button. The AI is optional."],
        "ہم آپ کے نقشے سے کمرے، دیواریں اور دروازے خود پڑھتے ہیں"),
    3: (["Tick what you want in the house (tiles, paint, doors, kitchen, ACs ...). Only ticked items are estimated.",
         "Answer the short questions for what you ticked - answers found on your drawings are already filled in.",
         "Read the few standard assumptions at the bottom, tick to confirm, then press 'Calculate materials'."],
        "جو کام چاہیے اس پر نشان لگائیں، سوالات کے جواب دیں، پھر حساب کریں"),
    4: (["This is everything you need to buy, in bags, tons and bricks - wastage is already included.",
         "'Things to double-check' tells you what may be wrong before you order.",
         "Ask the assistant anything, e.g. 'what if I use block walls?'"],
        "یہ آپ کی خریداری کی فہرست ہے - بوریاں، ٹن اور اینٹیں"),
    5: (["The Bill of Quantities lists all the work with quantities and rates - give it to contractors to compare quotes.",
         "Pick your city and how you'll build (labour contract, grey structure or turnkey) to see the total cost.",
         "Type your suppliers' prices or upload their quotation - the estimate updates."],
        "BOQ اور کل لاگت - شہر اور ٹھیکے کی قسم چنیں"),
    6: (["Pick when you want to move in (e.g. 6 months). The app plans every job and the workers needed to make it.",
         "See how much money you need each month, so you can arrange it in time.",
         "Engineers: switch on Engineer mode for crews, dependencies, productivity, critical path and progress tracking."],
        "کب تک گھر تیار چاہیے؟ مہینے چنیں - ہر ماہ درکار رقم بھی دیکھیں"),
    7: (["'Download everything' gives you one ZIP with all files and a READ_ME that explains each one.",
         "Excel and PDF for your contractor, the shopping list (with approximate prices) for shops, WhatsApp to send it.",
         "Save the project file to continue later."],
        "سب کچھ ایک ZIP فائل میں ڈاؤن لوڈ کریں"),
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

STEP_LABELS_PLAIN = ["1. Your project", "2. Your house design", "3. Scope & details", "4. Materials & BOQ", "5. Schedule & Gantt",
               "6. Download"]
