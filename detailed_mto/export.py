"""
Excel export of the Detailed Material Take-Off.

The workbook lists EVERY material of the Master Database (with status), the
work-item BOQ, full traceability (material <- work item <- drawing input),
all project inputs with source/confidence, rooms, openings, assumptions and
benchmark checks. Rates are left blank (yellow) for the next step; Amount
and totals are live Excel formulas, so filling rates prices the schedule.
"""
from __future__ import annotations

from datetime import datetime
from io import BytesIO


from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from detailed_mto.engine import (ST_CALC, ST_CALC_ASSUMED, ST_NEEDS_INPUT, ST_NOT_REQ, ST_OPTION, ST_PROVISIONAL,
                                 ST_REFERENCE, ST_SCOPE, DetailedResult)

FONT = "Arial"
HDR_FILL = PatternFill("solid", fgColor="1F3864")
SUB_FILL = PatternFill("solid", fgColor="D9E1F2")
YELLOW = PatternFill("solid", fgColor="FFFF00")
STATUS_FILL = {
    ST_CALC: PatternFill("solid", fgColor="E2EFDA"),
    ST_CALC_ASSUMED: PatternFill("solid", fgColor="FFF2CC"),
    ST_PROVISIONAL: PatternFill("solid", fgColor="FCE4D6"),
    ST_NEEDS_INPUT: PatternFill("solid", fgColor="F8CBAD"),
    ST_OPTION: PatternFill("solid", fgColor="EDEDED"),
    ST_SCOPE: PatternFill("solid", fgColor="EDEDED"),
    ST_NOT_REQ: PatternFill("solid", fgColor="F2F2F2"),
    ST_REFERENCE: PatternFill("solid", fgColor="DDEBF7"),
}
thin = Side(style="thin", color="BFBFBF")
BORDER = Border(left=thin, right=thin, top=thin, bottom=thin)
WRAP = Alignment(wrap_text=True, vertical="top")

BENCHMARKS = [  # (label, numerator mat_ids, unit, low, high)
    ("Cement per sft covered area", ["CON-001"], "bags/sft", 0.30, 0.55),
    ("Steel per sft covered area", ["RBR-001", "RBR-002", "RBR-003", "RBR-004"], "kg/sft", 1.5, 3.0),
    ("Bricks per sft covered area", ["MAS-001", "MAS-002"], "Nos/sft", 20, 35),
    ("Sand per sft covered area", ["CON-004", "CON-005"], "cft/sft", 1.2, 2.2),
    ("Crush per sft covered area", ["CON-006", "CON-007", "CON-008"], "cft/sft", 0.7, 1.4),
]


def _font(**kw):
    return Font(name=FONT, size=kw.pop("size", 9), **kw)


def _sheet(wb, name, headers, widths):
    ws = wb.create_sheet(name)
    for i, h in enumerate(headers, 1):
        c = ws.cell(row=1, column=i, value=h)
        c.font = _font(bold=True, color="FFFFFF")
        c.fill = HDR_FILL
        c.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
        c.border = BORDER
        ws.column_dimensions[get_column_letter(i)].width = widths[i - 1] if i - 1 < len(widths) else 14
    ws.row_dimensions[1].height = 30
    ws.freeze_panes = "B2"
    return ws


def _put(ws, r, c, v, bold=False, fill=None, fmt=None, color=None):
    cell = ws.cell(row=r, column=c, value=v)
    cell.font = _font(bold=bold, color=color) if color else _font(bold=bold)
    cell.alignment = WRAP
    cell.border = BORDER
    if fill is not None:
        cell.fill = fill
    if fmt:
        cell.number_format = fmt
    return cell


def _txt(v) -> str:
    s = "" if v is None else str(v)
    return ("'" + s) if s.startswith("=") else s


def build_detailed_mto_workbook(result: DetailedResult) -> bytes:
    p = result.project
    wb = Workbook()
    wb.remove(wb.active)
    summary = wb.create_sheet("Summary")

    # ------------------------------------------------ Material_Schedule
    MH = ["Mat_ID", "Category", "Subcategory", "Material Description", "Specification/Grade", "Unit", "Net Qty",
          "Wastage %", "Qty incl. Wastage", "Purchase Qty", "Status", "Confidence", "Construction Stage", "Tier/Option",
          "Calculation (traceable)", "Driven by Work Items", "Required Inputs", "Notes", "Info / If-selected Qty",
          "Rate (PKR/unit)", "Amount (PKR)"]
    ws = _sheet(wb, "Material_Schedule", MH, [9, 20, 15, 36, 26, 6, 11, 7, 12, 16, 16, 9, 9, 10, 60, 18, 24, 34, 10, 11, 13])
    for i, m in enumerate(result.materials):
        r = i + 2
        mat = m.material
        fill = STATUS_FILL.get(m.status)
        vals = [mat.mat_id, mat.category, mat.subcategory, mat.description, mat.specification, mat.unit]
        for j, v in enumerate(vals, 1):
            _put(ws, r, j, _txt(v), fill=fill if j == 1 else None)
        _put(ws, r, 7, round(m.net_qty, 3), fmt="#,##0.00")
        _put(ws, r, 8, m.wastage_pct, fmt="0.0%", color="0000FF")
        _put(ws, r, 9, f"=G{r}*(1+H{r})", fmt="#,##0.00")
        _put(ws, r, 10, m.purchase)
        _put(ws, r, 11, m.status, fill=fill)
        _put(ws, r, 12, m.confidence)
        _put(ws, r, 13, mat.stage)
        _put(ws, r, 14, mat.tier)
        _put(ws, r, 15, _txt(m.calculation))
        _put(ws, r, 16, ", ".join(m.driven_by))
        _put(ws, r, 17, _txt(mat.required_inputs))
        _put(ws, r, 18, _txt(mat.notes))
        _put(ws, r, 19, round(m.if_selected_qty, 3) if m.if_selected_qty else None, fmt="#,##0.00")
        _put(ws, r, 20, None, fill=YELLOW, fmt="#,##0.00", color="0000FF")
        _put(ws, r, 21, f"=IF(T{r}=\"\",0,I{r}*T{r})", fmt="#,##0")
    n_last = len(result.materials) + 1
    ws.auto_filter.ref = f"A1:{get_column_letter(len(MH))}{n_last}"
    ws.freeze_panes = "E2"
    tr = n_last + 1
    _put(ws, tr, 4, "TOTAL (priced lines)", bold=True)
    _put(ws, tr, 21, f"=SUM(U2:U{n_last})", bold=True, fmt="#,##0")
    SCH = f"Material_Schedule!$A$2:$A${n_last}"

    # ------------------------------------------------ Procurement_by_Stage
    ws2 = _sheet(wb, "Procurement_by_Stage", ["Stage", "Stage Name", "Mat_ID", "Material Description", "Unit",
                                               "Qty incl. Wastage", "Purchase Qty", "Status"], [8, 30, 9, 44, 7, 13, 20, 18])
    stage_rows = []
    for m in result.materials:
        if not m.included:
            continue
        stg = (m.material.stage or "S?").split(",")[0].split("-")[0].strip()
        stage_rows.append((stg, m))
    stage_rows.sort(key=lambda x: (x[0], x[1].material.category, x[1].material.mat_id))
    r = 2
    for stg, m in stage_rows:
        sched_row = result.materials.index(m) + 2
        _put(ws2, r, 1, stg)
        _put(ws2, r, 2, result_stage_name(stg))
        _put(ws2, r, 3, m.material.mat_id)
        _put(ws2, r, 4, m.material.description)
        _put(ws2, r, 5, m.material.unit)
        _put(ws2, r, 6, f"=Material_Schedule!I{sched_row}", fmt="#,##0.00", color="008000")
        _put(ws2, r, 7, m.purchase)
        _put(ws2, r, 8, m.status)
        r += 1
    ws2.auto_filter.ref = f"A1:H{max(r - 1, 2)}"

    # ------------------------------------------------ BOQ_Work_Items
    ws3 = _sheet(wb, "BOQ_Work_Items", ["WI_ID", "Scope", "Division", "Work Item", "Unit", "Quantity", "Status", "Confidence",
                                         "Calculation (from drawing inputs)", "Measurement Rule", "Legacy App Code"],
                 [10, 10, 14, 40, 6, 11, 16, 9, 70, 44, 14])
    for i, w in enumerate(result.work_items):
        r = i + 2
        fill = STATUS_FILL.get(w.status)
        for j, v in enumerate([w.wi_id, w.scope, w.division, w.description, w.unit], 1):
            _put(ws3, r, j, _txt(v), fill=fill if j == 1 else None)
        _put(ws3, r, 6, round(w.qty, 3), fmt="#,##0.00")
        _put(ws3, r, 7, w.status, fill=fill)
        _put(ws3, r, 8, w.confidence)
        _put(ws3, r, 9, _txt(w.calculation))
        _put(ws3, r, 10, _txt(w.measurement_rule))
        _put(ws3, r, 11, w.legacy_code)
    ws3.auto_filter.ref = f"A1:K{len(result.work_items) + 1}"

    # ------------------------------------------------ Material_Breakdown
    ws4 = _sheet(wb, "Material_Breakdown", ["Mat_ID", "Material", "WI_ID", "Work Item", "WI Qty", "WI Unit", "Coefficient",
                                             "Coeff_ID", "Mix", "Net Material Qty", "Material Unit"],
                 [9, 36, 10, 36, 11, 7, 10, 20, 12, 13, 8])
    mats = {m.material.mat_id: m for m in result.materials}
    rows = sorted(result.contributions, key=lambda c: (c.mat_id, c.wi_id))
    for i, c in enumerate(rows):
        r = i + 2
        m = mats.get(c.mat_id)
        _put(ws4, r, 1, c.mat_id)
        _put(ws4, r, 2, m.material.description if m else "")
        _put(ws4, r, 3, c.wi_id)
        _put(ws4, r, 4, c.wi_desc)
        _put(ws4, r, 5, round(c.wi_qty, 3), fmt="#,##0.00")
        _put(ws4, r, 6, c.wi_unit)
        _put(ws4, r, 7, round(c.coefficient, 6), fmt="0.0000", color="0000FF")
        _put(ws4, r, 8, c.coeff_id)
        _put(ws4, r, 9, c.mix_ref)
        _put(ws4, r, 10, f"=E{r}*G{r}", fmt="#,##0.00")
        _put(ws4, r, 11, m.material.unit if m else "")
    ws4.auto_filter.ref = f"A1:K{max(len(rows) + 1, 2)}"

    # ------------------------------------------------ Project_Inputs
    ws5 = _sheet(wb, "Project_Inputs", ["Key", "Group", "Parameter", "Value", "Unit", "Source", "Confidence", "Note"],
                 [16, 12, 44, 11, 7, 46, 10, 50])
    for i, prm in enumerate(sorted(p.params.values(), key=lambda x: (x.group, x.key))):
        r = i + 2
        for j, v in enumerate([prm.key, prm.group, prm.label], 1):
            _put(ws5, r, j, v)
        _put(ws5, r, 4, round(prm.value, 3), fmt="#,##0.00", color="0000FF")
        _put(ws5, r, 5, prm.unit)
        _put(ws5, r, 6, _txt(prm.source))
        _put(ws5, r, 7, prm.confidence)
        _put(ws5, r, 8, _txt(prm.note))
    base = len(p.params) + 3
    _put(ws5, base, 1, "Floors", bold=True, fill=SUB_FILL)
    for j, h in enumerate(["Floor", "Covered (sft)", "Ext. perimeter (rft)", "9in walls (rft)", "4.5in walls (rft)",
                           "Storey height (ft)", "Source", "Confidence"], 1):
        _put(ws5, base + 1, j, h, bold=True, fill=SUB_FILL)
    for i, f in enumerate(p.floors):
        r = base + 2 + i
        for j, v in enumerate([f.name, f.covered_sft, f.ext_perimeter_ft, f.wall9_len_ft, f.wall45_len_ft,
                               f.storey_height_ft, f.source, f.confidence], 1):
            _put(ws5, r, j, round(v, 2) if isinstance(v, float) else v, fmt="#,##0.0" if isinstance(v, float) else None)
    opt_r = base + 3 + len(p.floors)
    _put(ws5, opt_r, 1, "Options", bold=True, fill=SUB_FILL)
    for i, (k, v) in enumerate(vars(p.options).items()):
        _put(ws5, opt_r + 1 + i, 1, k)
        _put(ws5, opt_r + 1 + i, 3, str(v))

    # ------------------------------------------------ Rooms
    ws6 = _sheet(wb, "Rooms", ["Floor", "Room (label)", "Room Type (finish defaults)", "Length (ft)", "Width (ft)",
                               "Area (sft)", "Perimeter (rft)", "Wet area?", "Source", "Confidence"],
                 [10, 22, 22, 9, 9, 10, 10, 8, 30, 10])
    for i, rm in enumerate(p.rooms):
        r = i + 2
        _put(ws6, r, 1, rm.floor)
        _put(ws6, r, 2, rm.name)
        _put(ws6, r, 3, rm.room_type)
        _put(ws6, r, 4, round(rm.length_ft, 3), fmt="0.00", color="0000FF")
        _put(ws6, r, 5, round(rm.width_ft, 3), fmt="0.00", color="0000FF")
        _put(ws6, r, 6, f"=D{r}*E{r}", fmt="#,##0.0")
        _put(ws6, r, 7, f"=2*(D{r}+E{r})", fmt="#,##0.0")
        _put(ws6, r, 8, "Yes" if rm.is_wet else "")
        _put(ws6, r, 9, rm.source)
        _put(ws6, r, 10, rm.confidence)
    lr = len(p.rooms) + 1
    _put(ws6, lr + 1, 2, "TOTAL", bold=True)
    _put(ws6, lr + 1, 6, f"=SUM(F2:F{lr})", bold=True, fmt="#,##0")

    # ------------------------------------------------ Openings
    ws7 = _sheet(wb, "Openings", ["Kind", "Name", "Width (ft)", "Height (ft)", "Qty", "Leaves", "Chogath width (in)",
                                  "External?", "Area each (sft)", "Total area (sft)", "Source", "Confidence"],
                 [10, 26, 9, 9, 6, 7, 9, 8, 10, 11, 26, 10])
    for i, o in enumerate(p.openings):
        r = i + 2
        _put(ws7, r, 1, o.kind)
        _put(ws7, r, 2, o.name)
        _put(ws7, r, 3, o.width_ft, fmt="0.00", color="0000FF")
        _put(ws7, r, 4, o.height_ft, fmt="0.00", color="0000FF")
        _put(ws7, r, 5, o.qty, color="0000FF")
        _put(ws7, r, 6, o.leaves)
        _put(ws7, r, 7, o.chogath_in or None)
        _put(ws7, r, 8, "Yes" if o.external else "")
        _put(ws7, r, 9, f"=C{r}*D{r}", fmt="0.0")
        _put(ws7, r, 10, f"=I{r}*E{r}", fmt="#,##0.0")
        _put(ws7, r, 11, o.source)
        _put(ws7, r, 12, o.confidence)

    # ------------------------------------------------ Assumptions_Gaps
    ws8 = _sheet(wb, "Assumptions_Gaps", ["#", "Type", "Item"], [5, 16, 120])
    r = 2
    items = [("Drawing conflict", c) for c in p.conflicts] + [("Assumption", a) for a in p.assumptions]
    for m in result.materials:
        if m.status == ST_NEEDS_INPUT:
            items.append(("Needs input", f"{m.material.mat_id} {m.material.description}: provide {m.material.required_inputs or 'quantity'}"))
    low = [prm for prm in p.params.values() if prm.confidence in ("Assumed", "Low")]
    for prm in low:
        items.append(("Assumed input", f"{prm.label} = {prm.value:,.2f} {prm.unit} ({prm.source}) - verify"))
    for i, (t, txt) in enumerate(items):
        _put(ws8, r, 1, i + 1)
        _put(ws8, r, 2, t)
        _put(ws8, r, 3, _txt(txt))
        r += 1

    # ------------------------------------------------ Benchmarks
    ws9 = _sheet(wb, "Benchmarks", ["Check", "Value", "Unit", "Typical Low", "Typical High", "Result"], [36, 12, 10, 11, 11, 10])
    cov_total = sum(f.covered_sft for f in p.floors)
    _put(ws9, 2, 1, "Total covered area (all floors incl. mumty)", bold=True)
    _put(ws9, 2, 2, round(cov_total, 1), fmt="#,##0", color="0000FF")
    _put(ws9, 2, 3, "sft")
    for i, (label, ids, unit, lo, hi) in enumerate(BENCHMARKS):
        r = i + 3
        refs = "+".join(f"SUMIF({SCH},\"{mid}\",Material_Schedule!$I$2:$I${n_last})" for mid in ids)
        _put(ws9, r, 1, label)
        _put(ws9, r, 2, f"=IF($B$2=0,0,({refs})/$B$2)", fmt="0.00")
        _put(ws9, r, 3, unit)
        _put(ws9, r, 4, lo, color="0000FF")
        _put(ws9, r, 5, hi, color="0000FF")
        _put(ws9, r, 6, f"=IF(AND(B{r}>=D{r},B{r}<=E{r}),\"OK\",\"CHECK\")")
    _put(ws9, len(BENCHMARKS) + 4, 1, "Indicative ranges for 5-10 marla load-bearing / RCC houses (grey + finishing). "
                                       "Warnings only - calibrate against your own completed projects.")

    # ------------------------------------------------ Summary
    ws = summary
    ws.column_dimensions["A"].width = 38
    ws.column_dimensions["B"].width = 22
    ws.column_dimensions["C"].width = 14
    ws.column_dimensions["D"].width = 60
    t = ws.cell(row=1, column=1, value="Detailed Material Take-Off (MTO)")
    t.font = _font(size=14, bold=True, color="1F3864")
    info = [
        ("Project", p.project_name), ("Client", p.client), ("Location", p.location), ("Scope", result.scope),
        ("Finish tier", p.options.finish_tier), ("Roof system", p.options.roof_system), ("Gas source", p.options.gas_source),
        ("Generated", datetime.now().strftime("%Y-%m-%d %H:%M")), ("Knowledge base", "Master Material Database v1 (data/master_material_database.xlsx)"),
    ]
    r = 3
    for k, v in info:
        _put(ws, r, 1, k, bold=True)
        _put(ws, r, 2, _txt(v))
        r += 1
    r += 1
    _put(ws, r, 1, "Material lines by status", bold=True, fill=SUB_FILL)
    _put(ws, r, 2, "Count", bold=True, fill=SUB_FILL)
    _put(ws, r, 4, "Meaning", bold=True, fill=SUB_FILL)
    meaning = {
        ST_CALC: "Quantity calculated from drawing/verified inputs",
        ST_CALC_ASSUMED: "Calculated, but one or more inputs are defaults - verify (see Assumptions_Gaps)",
        ST_PROVISIONAL: "Provisional quantity (owner-supplied / PC items)",
        ST_REFERENCE: "Assembly/duplicate line - quantity shown for info, procured under another Mat_ID",
        ST_OPTION: "Optional/alternative material not selected - 'Info / If-selected Qty' shows the quantity if chosen",
        ST_NEEDS_INPUT: "Cannot be calculated without a user input (listed in Assumptions_Gaps)",
        ST_NOT_REQ: "Calculated as zero for this project",
        ST_SCOPE: "Outside the selected scope",
    }
    for st, txt in meaning.items():
        r += 1
        _put(ws, r, 1, st, fill=STATUS_FILL.get(st))
        _put(ws, r, 2, f"=COUNTIF(Material_Schedule!$K$2:$K${n_last},A{r})")
        _put(ws, r, 4, txt)
    r += 1
    _put(ws, r, 1, "TOTAL materials in database", bold=True)
    _put(ws, r, 2, f"=COUNTA({SCH})", bold=True)
    r += 2
    _put(ws, r, 1, "Key quantities (incl. wastage)", bold=True, fill=SUB_FILL)
    _put(ws, r, 2, "Quantity", bold=True, fill=SUB_FILL)
    _put(ws, r, 3, "Unit", bold=True, fill=SUB_FILL)
    key = [("Cement (OPC 50 kg)", ["CON-001"], "bags"), ("Steel Grade 60 (all dia.)", ["RBR-001", "RBR-002", "RBR-003", "RBR-004"], "kg"),
           ("Bricks (Class A + B)", ["MAS-001", "MAS-002"], "Nos"), ("Sand (all)", ["CON-004", "CON-005", "EW-003", "EXT-003", "PDR-020"], "cft"),
           ("Crush (all sizes)", ["CON-006", "CON-007", "CON-008"], "cft"), ("Floor tiles", ["FLR-001", "FLR-002"], "sft"),
           ("Wall tiles", ["FLR-003"], "sft"), ("Interior emulsion", ["PNT-003", "PNT-004"], "gal"),
           ("Exterior paint", ["PNT-005"], "gal"), ("House wires (all sizes)", ["ELE-006", "ELE-007", "ELE-008", "ELE-009", "ELE-011"], "m"),
           ("PPR pipes (all)", ["PWS-001", "PWS-002", "PWS-003", "PWS-004", "PWS-005"], "rft"),
           ("uPVC drainage pipes", ["PDR-001", "PDR-002", "PDR-003", "PDR-004", "PDR-005", "PDR-012"], "rft")]
    for label, ids, unit in key:
        r += 1
        refs = "+".join(f"SUMIF({SCH},\"{mid}\",Material_Schedule!$I$2:$I${n_last})" for mid in ids)
        _put(ws, r, 1, label)
        _put(ws, r, 2, f"={refs}", fmt="#,##0")
        _put(ws, r, 3, unit)
    r += 2
    _put(ws, r, 1, "Priced total (fill rates in Material_Schedule col T)", bold=True)
    _put(ws, r, 2, f"=Material_Schedule!U{tr}", bold=True, fmt="#,##0")
    _put(ws, r, 3, "PKR")
    r += 2
    notes = [
        "Every material of the Master Material Database is listed in Material_Schedule with a status - nothing is silently dropped.",
        "Quantities are traceable: Material_Schedule -> Material_Breakdown (work item x coefficient) -> BOQ_Work_Items -> Project_Inputs / Rooms / Openings.",
        "Blue values are inputs you may edit; yellow cells are rates to fill in. Amounts and totals recalculate automatically.",
        "Steel is by the ratio method until a structural BBS is available; electrical point counts use room-type defaults until symbols are verified.",
        "Indicative estimate for budgeting and procurement planning - not a substitute for professional design or a QS takeoff.",
    ]
    for n in notes:
        c = ws.cell(row=r, column=1, value=n)
        c.font = _font()
        c.alignment = Alignment(wrap_text=True, vertical="top")
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=4)
        ws.row_dimensions[r].height = 24
        r += 1

    bio = BytesIO()
    wb.save(bio)
    return bio.getvalue()


_STAGE_NAMES = {
    "S0": "Pre-construction / preliminaries", "S1": "Substructure", "S2": "MEP rough-in (first fix)",
    "S3": "Superstructure masonry", "S4": "RCC frame & slabs", "S5": "Second-fix MEP in walls",
    "S6": "Finishes (wet trades)", "S7": "Roof & external envelope", "S8": "External works & services",
    "S9": "Fixtures & handover",
}


def result_stage_name(code: str) -> str:
    return _STAGE_NAMES.get(code, "")
