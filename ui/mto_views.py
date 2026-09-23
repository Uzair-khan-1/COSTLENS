"""
Streamlit views for the drawing-based Material Take-Off:

* Step 2  - what the label scan found (plumbing, door schedule, tanks)
* Step 3  - review tables (rooms, doors & windows, counts & key dimensions, coefficients)
* Step 4  - material take-off (schedule, by stage, work items, traceability, assumptions, checks)
* Step 5  - export

All engineering lives in detailed_mto/ and knowledge/; this module only renders.
Costs are intentionally excluded in this version.
"""
from __future__ import annotations

from typing import List, Optional

import pandas as pd
import streamlit as st

from detailed_mto import build_project, compute
from detailed_mto.edits import (OPENING_COLS, ROOM_COLS, mark_user_edits, openings_to_rows, rooms_to_rows,
                                rows_to_openings, rows_to_rooms)
from detailed_mto.engine import (INCLUDED_STATUSES, ST_CALC, ST_CALC_ASSUMED, ST_NEEDS_INPUT, ST_OPTION, ST_PROVISIONAL,
                                 ST_REFERENCE, DetailedResult)
from detailed_mto.export import benchmarks_for
from knowledge import load_knowledge_base

FLOOR_KEYS = ["basement", "ground", "first", "second", "third", "roof"]
CONF_ICON = {"High": "🟢", "Medium": "🟡", "Low": "🟠", "Assumed": "⚪", "User": "🔵", "": ""}


def kb():
    return load_knowledge_base()


# ---------------------------------------------------------------- project building
def seed_review_rows(pi, params) -> None:
    """First time Step 3 opens after an analysis: fill rooms/openings from the drawings."""
    if st.session_state.get("dmto_rooms") is not None and st.session_state.get("dmto_openings") is not None:
        return
    p = build_project(pi, params, kb(), facts=st.session_state.get("package_facts"),
                      scan=st.session_state.get("dmto_scan"), options=st.session_state["dmto_options"])
    if st.session_state.get("dmto_rooms") is None:
        st.session_state["dmto_rooms"] = rooms_to_rows(p)
    if st.session_state.get("dmto_openings") is None:
        st.session_state["dmto_openings"] = openings_to_rows(p)


def current_project(pi, params, room_rows=None, opening_rows=None, with_overrides=True):
    room_rows = st.session_state.get("dmto_rooms") if room_rows is None else room_rows
    opening_rows = st.session_state.get("dmto_openings") if opening_rows is None else opening_rows
    p = build_project(pi, params, kb(), facts=st.session_state.get("package_facts"), scan=st.session_state.get("dmto_scan"),
                      options=st.session_state["dmto_options"],
                      rooms_override=rows_to_rooms(room_rows) if room_rows is not None else None,
                      openings_override=rows_to_openings(opening_rows) if opening_rows is not None else None)
    if with_overrides:
        for k, v in (st.session_state.get("dmto_overrides") or {}).items():
            p.override(k, v)
    return p


def run_takeoff(pi, params) -> DetailedResult:
    p = current_project(pi, params)
    res = compute(p, kb(), scope=st.session_state["dmto_options"].scope)
    st.session_state["dmto_result"] = res
    st.session_state["dmto_xlsx"] = None
    return res


# ---------------------------------------------------------------- Step 2
def render_scan_summary(scan) -> None:
    if scan is None:
        return
    rows = []
    names = {"FT": "Floor traps (F.T)", "MH": "Manholes (M.H)", "GT": "Gully traps (G.T)", "CO": "Cleanouts (C.O)",
             "VANITY": "Vanities / basins", "WC": "WCs", "SHOWER": "Showers", "SUMP": "Roof outlets (sump/khura)",
             "WARDROBE": "Wardrobes", "BALCONY": "Balconies", "TERRACE": "Terraces", "DB": "Distribution boards",
             "GEYSER": "Water heaters", "OVEN": "Built-in oven"}
    for k, n in scan.label_counts.items():
        rows.append({"Item": names.get(k, k), "Count": n,
                     "Note": "detail/legend sheet only - not used as a count" if k in scan.detail_only else "from plan labels"})
    for d in scan.doors:
        rows.append({"Item": f"Door schedule: {d.name} {d.width_ft:g}'x{d.height_ft:g}' "
                             f"({'double' if d.leaves == 2 else 'single'}, {d.chogath_in:g}\" chogath)",
                     "Count": d.qty, "Note": d.source})
    if scan.oh_tank_gal:
        rows.append({"Item": f"Overhead tank {scan.oh_tank_gal:g} gal {scan.oh_tank_type}", "Count": 1, "Note": scan.sources.get("OH_TANK", "")})
    for label, v in (("Septic tank (detail)", scan.septic_detail), ("Septic tank (plan)", scan.septic_plan),
                     ("UG water tank (detail)", scan.ug_tank_detail), ("OH tank RCC (detail)", scan.oh_tank_detail)):
        if v:
            rows.append({"Item": f"{label} {v[0]:g}' x {v[1]:g}'", "Count": 1, "Note": ""})
    if rows:
        st.markdown("##### \U0001f50e Services & schedules read from the drawings")
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    for n in scan.notes:
        st.warning(n)


# ---------------------------------------------------------------- Step 3 review tables
def render_rooms_editor() -> List[dict]:
    types = [rd.room_type for rd in kb().room_defaults]
    df = pd.DataFrame(st.session_state["dmto_rooms"] or [], columns=ROOM_COLS)
    st.caption("Rooms drive floor/wall finishes, plaster, paint, ceilings, waterproofing and the default electrical "
               "points. Room type decides the finish defaults. Add rows for anything missing (e.g. terraces with sizes).")
    edited = st.data_editor(
        df, key=f"dmto_rooms_editor_{st.session_state['dmto_ver']}", hide_index=True, width="stretch", num_rows="dynamic",
        column_config={
            "Room type": st.column_config.SelectboxColumn(options=types, required=True),
            "Floor": st.column_config.SelectboxColumn(options=FLOOR_KEYS, required=True),
            "Length (ft)": st.column_config.NumberColumn(min_value=0.0, step=0.25, format="%.2f"),
            "Width (ft)": st.column_config.NumberColumn(min_value=0.0, step=0.25, format="%.2f"),
        },
        disabled=["Source", "Confidence"])
    rows = edited.to_dict("records")
    tot = sum(r.area for r in rows_to_rooms(rows))
    st.caption(f"{len(rows_to_rooms(rows))} rooms, total {tot:,.0f} sft.")
    return rows


def render_openings_editor() -> List[dict]:
    df = pd.DataFrame(st.session_state["dmto_openings"] or [], columns=OPENING_COLS)
    st.caption("Doors come from the chogath/door schedule when the drawings have one. Window WIDTHS are rarely given "
               "on Pakistani D&W sheets - replace the assumed 4'x5' sizes with the real ones.")
    edited = st.data_editor(
        df, key=f"dmto_open_editor_{st.session_state['dmto_ver']}", hide_index=True, width="stretch", num_rows="dynamic",
        column_config={
            "Kind": st.column_config.SelectboxColumn(options=["door", "window", "ventilator"], required=True),
            "Width (ft)": st.column_config.NumberColumn(min_value=0.0, step=0.25, format="%.2f"),
            "Height (ft)": st.column_config.NumberColumn(min_value=0.0, step=0.25, format="%.2f"),
            "Qty": st.column_config.NumberColumn(min_value=0, step=1),
            "Leaves": st.column_config.NumberColumn(min_value=1, max_value=4, step=1),
            "External": st.column_config.CheckboxColumn(),
        },
        disabled=["Source", "Confidence"])
    return edited.to_dict("records")


def render_counts_editor(pi, params, room_rows, opening_rows) -> None:
    base = current_project(pi, params, room_rows, opening_rows, with_overrides=False)
    ov = dict(st.session_state.get("dmto_overrides") or {})
    groups = sorted({p.group for p in base.params.values()})
    st.caption("Counts and dimensions used by the take-off. 🟢 read from drawings · 🟡 derived · ⚪ assumed default · "
               "🔵 your edit. Change any value - it overrides the drawing/default value.")
    sel = st.multiselect("Show groups", groups, default=groups, key="dmto_count_groups")
    rows = []
    for prm in sorted(base.params.values(), key=lambda x: (x.group, x.key)):
        if prm.group not in sel:
            continue
        val = ov.get(prm.key, prm.value)
        conf = "User" if prm.key in ov else prm.confidence
        rows.append({"Key": prm.key, "Group": prm.group, "Parameter": prm.label, "Value": round(float(val), 3),
                     "Unit": prm.unit, "": CONF_ICON.get(conf, ""), "Source": "User input" if prm.key in ov else prm.source})
    df = pd.DataFrame(rows)
    edited = st.data_editor(df, key=f"dmto_counts_editor_{st.session_state['dmto_ver']}_{'-'.join(sel)}", hide_index=True,
                            width="stretch", disabled=["Key", "Group", "Parameter", "Unit", "", "Source"],
                            column_config={"Value": st.column_config.NumberColumn(format="%.2f")})
    for (_, a), (_, b) in zip(df.iterrows(), edited.iterrows()):
        key = a["Key"]
        try:
            newv = float(b["Value"])
        except (TypeError, ValueError):
            continue
        basev = base.params[key].value
        if abs(newv - basev) > 1e-6:
            ov[key] = newv
        elif key in ov and abs(newv - basev) <= 1e-6:
            ov.pop(key, None)
    st.session_state["dmto_overrides"] = ov
    if ov and st.button("Reset all edited counts to drawing/default values", key="dmto_reset_ov"):
        st.session_state["dmto_overrides"] = {}
        st.session_state["dmto_ver"] += 1
        st.rerun()


def save_review(room_rows, opening_rows) -> None:
    st.session_state["dmto_rooms"] = mark_user_edits(room_rows, st.session_state.get("dmto_rooms") or [],
                                                     ["Floor", "Room", "Room type", "Length (ft)", "Width (ft)"])
    st.session_state["dmto_openings"] = mark_user_edits(opening_rows, st.session_state.get("dmto_openings") or [],
                                                        ["Kind", "Name", "Width (ft)", "Height (ft)", "Qty", "Leaves", "External"])
    st.session_state["dmto_ver"] += 1


def render_coefficients() -> None:
    k = kb()
    st.caption("Engineering coefficients, mixes and wastage come from the Master Material Database "
               "(data/master_material_database.xlsx). Edit them in Excel and run scripts/validate_knowledge_base.py.")
    groups = sorted({m["group"] for m in k.coefficient_meta.values()})
    g = st.selectbox("Coefficient group", groups, index=groups.index("Steel") if "Steel" in groups else 0, key="dmto_coef_group")
    st.dataframe(pd.DataFrame([{"Coeff_ID": cid, "Description": m["description"], "Value": round(k.coefficients[cid], 4),
                                "Unit": m["unit"], "Source": m["source"]}
                               for cid, m in k.coefficient_meta.items() if m["group"] == g]), hide_index=True, width="stretch")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Nominal mixes**")
        st.dataframe(pd.DataFrame([{"Mix": x.description, "Cement bags/cft": round(x.values["J"], 4),
                                    "Sand cft/cft": round(x.values["K"], 3), "Crush cft/cft": round(x.values["L"], 3)}
                                   for x in k.mixes.values()]), hide_index=True, width="stretch")
    with c2:
        st.markdown("**Wastage**")
        st.dataframe(pd.DataFrame([{"Key": key, "Wastage": f"{v * 100:.1f}%"} for key, v in k.wastage.items()]),
                     hide_index=True, width="stretch", height=300)


# ---------------------------------------------------------------- Step 4
KEY_TOTALS = [
    ("Cement", {"CON-001"}, "bags", 1),
    ("Steel", {"RBR-001", "RBR-002", "RBR-003", "RBR-004"}, "ton", 1000),
    ("Bricks", {"MAS-001", "MAS-002"}, "Nos", 1),
    ("Sand", {"CON-004", "CON-005", "EW-003", "EXT-003", "PDR-020"}, "cft", 1),
    ("Crush", {"CON-006", "CON-007", "CON-008"}, "cft", 1),
    ("Tiles (floor + wall)", {"FLR-001", "FLR-002", "FLR-003"}, "sft", 1),
]


def _total(res: DetailedResult, ids) -> float:
    return sum(m.gross_qty for m in res.materials if m.material.mat_id in ids)


def render_takeoff(res: DetailedResult) -> None:
    counts = res.status_counts()
    quantified = sum(v for k, v in counts.items() if k in INCLUDED_STATUSES)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Materials in database", len(res.materials))
    m2.metric("Quantified", quantified)
    m3.metric("Using assumed inputs", counts.get(ST_CALC_ASSUMED, 0))
    m4.metric("Need your input", counts.get(ST_NEEDS_INPUT, 0))
    cols = st.columns(len(KEY_TOTALS))
    for c, (label, ids, unit, div) in zip(cols, KEY_TOTALS):
        v = _total(res, ids) / div
        c.metric(label, f"{v:,.2f} {unit}" if div > 1 else f"{v:,.0f} {unit}")
    if res.project.conflicts:
        with st.expander(f"⚠️ Drawing conflicts found ({len(res.project.conflicts)})", expanded=True):
            for c in res.project.conflicts:
                st.warning(c)

    t1, t2, t3, t4, t5, t6 = st.tabs(["📋 Material schedule", "🗓️ By construction stage", "📐 Work items",
                                       "🔍 Traceability", "📝 Assumptions & gaps", "✅ Checks"])
    with t1:
        _schedule_tab(res)
    with t2:
        _stage_tab(res)
    with t3:
        st.dataframe(pd.DataFrame([{"WI_ID": w.wi_id, "Division": w.division, "Work item": w.description, "Unit": w.unit,
                                    "Quantity": round(w.qty, 2), "Status": w.status, "Confidence": w.confidence,
                                    "Calculation": w.calculation} for w in res.work_items]),
                     hide_index=True, width="stretch", height=520)
    with t4:
        _trace_tab(res)
    with t5:
        _assumptions_tab(res)
    with t6:
        _checks_tab(res)


def _schedule_tab(res: DetailedResult) -> None:
    cats = list(dict.fromkeys(m.material.category for m in res.materials))
    statuses = [ST_CALC, ST_CALC_ASSUMED, ST_PROVISIONAL, ST_NEEDS_INPUT, ST_OPTION, ST_REFERENCE, "Not required", "Not in scope"]
    c1, c2, c3 = st.columns([2, 2, 1])
    sel_cats = c1.multiselect("Categories", cats, default=[], placeholder="All categories", key="dmto_f_cat")
    sel_st = c2.multiselect("Status", statuses, default=[ST_CALC, ST_CALC_ASSUMED, ST_PROVISIONAL, ST_NEEDS_INPUT], key="dmto_f_st")
    q = c3.text_input("Search", key="dmto_f_q")
    rows = []
    for m in res.materials:
        if sel_cats and m.material.category not in sel_cats:
            continue
        if sel_st and m.status not in sel_st:
            continue
        text = f"{m.material.mat_id} {m.material.description} {m.material.specification}".lower()
        if q and q.lower() not in text:
            continue
        rows.append({"Mat_ID": m.material.mat_id, "Category": m.material.category, "Material": m.material.description,
                     "Specification": m.material.specification, "Unit": m.material.unit,
                     "Net qty": round(m.net_qty, 2), "Wastage": f"{m.wastage_pct * 100:.1f}%",
                     "Qty incl. wastage": round(m.gross_qty, 2), "Purchase": m.purchase, "Status": m.status,
                     "Conf.": CONF_ICON.get(m.confidence, "") + " " + (m.confidence or ""), "Stage": m.material.stage,
                     "If selected": round(m.if_selected_qty, 2) if m.if_selected_qty else None})
    st.caption(f"{len(rows)} line(s) shown. Status 'Option - not included' lines show the quantity they would need in "
               "'If selected'; 'Counted elsewhere' lines are assemblies/duplicates, not bought twice.")
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", height=560)


def _stage_code(m) -> str:
    return (m.material.stage or "S?").split(",")[0].split("-")[0].strip()


def _stage_tab(res: DetailedResult) -> None:
    k = kb()
    stages = sorted({_stage_code(m) for m in res.materials if m.included})
    labels = {s: f"{s} - {k.stages.get(s, '')}" for s in stages}
    s = st.selectbox("Construction stage", stages, format_func=lambda x: labels[x], key="dmto_stage")
    rows = [{"Mat_ID": m.material.mat_id, "Material": m.material.description, "Unit": m.material.unit,
             "Qty incl. wastage": round(m.gross_qty, 2), "Purchase": m.purchase, "Status": m.status}
            for m in res.materials if m.included and _stage_code(m) == s]
    st.caption("Order these before/at this stage. Items cast into slabs or walls (sleeves, fan hooks, conduits, "
               "concealed cisterns, mixer bodies) are listed under the stage when they must be on site.")
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", height=480)


def _trace_tab(res: DetailedResult) -> None:
    inc = [m for m in res.materials if m.included or m.if_selected_qty]
    if not inc:
        return
    labels = {m.material.mat_id: f"{m.material.mat_id} - {m.material.description}" for m in inc}
    mid = st.selectbox("Material", list(labels), format_func=lambda x: labels[x], key="dmto_trace")
    m = res.by_id(mid)
    st.markdown(f"**{m.material.description}** - {m.material.specification}")
    st.markdown(f"Net **{m.net_qty:,.2f} {m.material.unit}** × (1 + {m.wastage_pct * 100:.1f}% wastage) = "
                f"**{m.gross_qty:,.2f} {m.material.unit}** · status: {m.status} · confidence: {m.confidence or '-'}")
    st.code(m.calculation or "-", language=None)
    contrib = [c for c in res.contributions if c.mat_id == mid]
    if contrib:
        wmap = {w.wi_id: w for w in res.work_items}
        st.dataframe(pd.DataFrame([{"Work item": f"{c.wi_id} {c.wi_desc}", "WI qty": round(c.wi_qty, 2), "WI unit": c.wi_unit,
                                    "Coefficient": round(c.coefficient, 5), "Coeff_ID": c.coeff_id, "Mix": c.mix_ref,
                                    "Material qty": round(c.net_qty, 2),
                                    "WI calculation": wmap[c.wi_id].calculation if c.wi_id in wmap else ""}
                                   for c in contrib]), hide_index=True, width="stretch")
    if m.material.notes:
        st.caption(m.material.notes)


def _assumptions_tab(res: DetailedResult) -> None:
    p = res.project
    for a in p.assumptions:
        st.info(a)
    needs = [m for m in res.materials if m.status == ST_NEEDS_INPUT]
    if needs:
        st.markdown("**Materials that need an input**")
        for m in needs:
            st.write(f"- {m.material.mat_id} {m.material.description}: {m.material.required_inputs or 'quantity'}")
    low = [x for x in p.params.values() if x.confidence in ("Assumed", "Low")]
    if low:
        st.markdown("**Inputs still at default values** (edit them in Step 3 → Counts & dimensions)")
        st.dataframe(pd.DataFrame([{"Parameter": x.label, "Value": round(x.value, 2), "Unit": x.unit, "Basis": x.source}
                                   for x in low]), hide_index=True, width="stretch")


def benchmark_rows(res: DetailedResult) -> List[dict]:
    cov = sum(f.covered_sft for f in res.project.floors) or 1.0
    out = []
    for label, ids, unit, lo, hi in benchmarks_for(res.project):
        v = _total(res, set(ids)) / cov
        out.append({"Check": label, "Value": round(v, 2), "Unit": unit, "Typical range": f"{lo:g} - {hi:g}",
                    "Result": "OK" if lo <= v <= hi else "CHECK"})
    return out


def _checks_tab(res: DetailedResult) -> None:
    cov = sum(f.covered_sft for f in res.project.floors)
    st.caption(f"Ratios per sft of total covered area ({cov:,.0f} sft incl. mumty). Indicative ranges for 5-10 marla "
               "houses - a CHECK means look at the inputs, not that the number is wrong.")
    st.dataframe(pd.DataFrame(benchmark_rows(res)), hide_index=True, width="stretch")


# ---------------------------------------------------------------- Step 5
def export_bytes(res: DetailedResult) -> bytes:
    from detailed_mto.export import build_detailed_mto_workbook
    cache = st.session_state.get("dmto_xlsx")
    if cache and cache[0] == id(res):
        return cache[1]
    data = build_detailed_mto_workbook(res)
    st.session_state["dmto_xlsx"] = (id(res), data)
    return data


def schedule_csv(res: DetailedResult) -> bytes:
    df = pd.DataFrame([{"Mat_ID": m.material.mat_id, "Category": m.material.category, "Subcategory": m.material.subcategory,
                        "Material": m.material.description, "Specification": m.material.specification, "Unit": m.material.unit,
                        "Net qty": round(m.net_qty, 3), "Wastage %": round(m.wastage_pct * 100, 1),
                        "Qty incl. wastage": round(m.gross_qty, 3), "Purchase": m.purchase, "Status": m.status,
                        "Confidence": m.confidence, "Stage": m.material.stage} for m in res.materials])
    return df.to_csv(index=False).encode("utf-8")


def options_summary(opts) -> str:
    mix = {"MX_RCC124": "RCC 1:2:4", "MX_RCC1153": "RCC 1:1.5:3"}.get(opts.rcc_mix, opts.rcc_mix)
    return (f"Scope: **{opts.scope}** · Finish: **{opts.finish_tier}** · {mix} · Roof: {opts.roof_system} · "
            f"Walls: {opts.masonry} · Gas: {opts.gas_source} · False ceilings: {'yes' if opts.include_false_ceiling else 'no'} · "
            f"Recharge well: {'yes' if opts.include_rwh else 'no'} · Seismic bands: {'yes' if opts.seismic_bands else 'no'}")


def result_is_stale(res: Optional[DetailedResult]) -> bool:
    return res is None
