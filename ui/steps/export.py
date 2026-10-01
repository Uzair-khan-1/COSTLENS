"""Step 7 - downloads (one ZIP with everything, or file by file)."""
from __future__ import annotations


import streamlit as st

import config
from models.schemas import ProjectInputs
from ui import mto_views
from ui.state import go_to_step, reset_project


# ---------------------------------------------------------------------------
# STEP 5 — Export
# ---------------------------------------------------------------------------
def step_5():
    from ui.guide import step_header
    step_header(7)
    pi: ProjectInputs = st.session_state["project_inputs"]
    res = mto_views.ensure_current_result(pi, st.session_state.get("extracted_params"))
    if res is None:
        st.info("Calculate the materials first (Step 3 \u2192 'Calculate materials').")
        if st.button("\u2190 Back to check details"):
            go_to_step(3)
            st.rerun()
        return
    mto_views.render_drawing_mode_banner(res.project.drawing_mode)
    from ui.state import display_name, file_stem
    name = file_stem()
    from detailed_mto.shopping import shopping_pdf, shopping_text
    from urllib.parse import quote

    counts = res.status_counts()
    from persistence.project_file import project_to_json
    keys = ("project_inputs", "extracted_params", "input_mode", "dmto_options", "dmto_rooms", "dmto_openings",
            "dmto_overrides", "dmto_floors", "package_facts", "dmto_scan", "uploaded_signature", "drawing_filled",
            "brief", "copilot_scenarios", "copilot_msgs", "uploaded_files", "step", "max_step",
                    "scope_sel", "scope_confirmed", "spec_answers", "assumptions_ack", "plot_dims_user",
                    "sched_settings", "sched_target", "sched_baseline", "cost_settings")
    snap = {k: st.session_state.get(k) for k in keys}
    cost = gov = None
    try:
        from ui.cost_views import current_cost, government
        cost, _s = current_cost(res)
        gov, _uf = government(res, cost)
    except Exception:  # noqa: BLE001 - downloads without cost still work
        pass
    prices = {ln.code: ln.amount for ln in cost.lines if ln.kind == "material"} if cost else None
    city = cost.settings.city if cost else ""
    from pricing.costing import pkr
    from pricing.export import build_cost_workbook, cost_pdf
    from ui.schedule_views import workbook_bytes

    def everything() -> bytes:
        import io
        import zipfile
        files = [(f"1_{name}_Materials_and_BOQ.xlsx", lambda: mto_views.export_bytes(res),
                  "Everything to buy + the Bill of Quantities - give it to your contractor."),
                 (f"2_{name}_Cost_Estimate.xlsx", lambda: build_cost_workbook(cost, display_name(), gov) if cost else None,
                  "The cost: rates, amounts, money per month, government estimate."),
                 (f"3_{name}_Cost_Summary.pdf", lambda: cost_pdf(cost, display_name(), gov) if cost else None,
                  "One page: total cost, cost per sq ft, money needed each month."),
                 (f"4_{name}_Schedule.xlsx", lambda: workbook_bytes(res, display_name()),
                  "When each job happens, Gantt chart, workers needed each week, when to order materials."),
                 (f"5_{name}_Shopping_list.pdf", lambda: shopping_pdf(res, prices=prices, city=city),
                  "Shopping list for shops, with approximate prices."),
                 (f"6_{name}_Shopping_list.txt", lambda: shopping_text(res).encode("utf-8"), "The same list as text (WhatsApp)."),
                 (f"7_{name}.costlens.json", lambda: project_to_json(snap, False),
                  "Your project - open it again in CostLens (sidebar -> Project) to continue.")]
        bio = io.BytesIO()
        readme = [f"{display_name()} - files from CostLens", ""]
        with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as z:
            for fn, make, what in files:
                try:
                    data = make()
                except Exception:  # noqa: BLE001
                    data = None
                if data:
                    z.writestr(fn, data)
                    readme.append(f"{fn}\n    {what}")
            z.writestr("0_READ_ME.txt", "\n".join(readme) + "\n\nPreliminary estimate from drawings - verify before buying.\n")
        return bio.getvalue()

    summary = f"**{len(res.purchase_list())} materials** to buy, a **Bill of Quantities**"
    if cost:
        summary += f", a cost of about **{pkr(cost.total)}** ({city})"
    summary += " and a construction **schedule** for *" + display_name() + "*."
    if counts.get("Needs input"):
        summary += f" {counts.get('Needs input')} item(s) still need your input."
    st.markdown(summary)
    st.download_button("\U0001f4e6 Download everything (one ZIP file)", data=everything, file_name=f"{name}_CostLens_files.zip",
                       mime="application/zip", type="primary", width="stretch", key="exp_zip",
                       help="All Excel and PDF files, the shopping list and your project file - with a READ_ME explaining each.")
    st.caption("Or download the files one by one:")

    c1, c2, c3 = st.columns(3)
    with c1.container(border=True):
        st.markdown("<div style='font-size:30px'>\U0001f9f1</div><b>Materials & BOQ</b>", unsafe_allow_html=True)
        st.caption("For your contractor: everything to buy, the Bill of Quantities and all calculations.")
        st.download_button("\u2b07\ufe0f Materials & BOQ (Excel)", data=lambda: mto_views.export_bytes(res),
                           file_name=f"{name}_Materials_and_BOQ.xlsx", width="stretch",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        st.download_button("\u2b07\ufe0f Material list (CSV)", data=mto_views.schedule_csv(res),
                           file_name=f"{name}_Material_list.csv", mime="text/csv", width="stretch")
    with c2.container(border=True):
        st.markdown("<div style='font-size:30px'>\U0001f4b0</div><b>Cost & budget</b>", unsafe_allow_html=True)
        st.caption("Total cost, rates, cost per sq ft and the money you need each month.")
        if cost:
            st.download_button("\u2b07\ufe0f Cost estimate (Excel)", data=lambda: build_cost_workbook(cost, display_name(), gov),
                               file_name=f"{name}_Cost_Estimate.xlsx", width="stretch", key="exp_cost_xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            st.download_button("\u2b07\ufe0f Cost summary (PDF)", data=lambda: cost_pdf(cost, display_name(), gov),
                               file_name=f"{name}_Cost_Summary.pdf", mime="application/pdf", width="stretch", key="exp_cost_pdf")
        else:
            st.caption("Open Step 5 first.")
    with c3.container(border=True):
        st.markdown("<div style='font-size:30px'>\U0001f4c5</div><b>Schedule & workers</b>", unsafe_allow_html=True)
        st.caption("When each job happens, the Gantt chart, workers needed each week and when to order materials.")
        st.download_button("\u2b07\ufe0f Schedule (Excel)", data=lambda: workbook_bytes(res, display_name()),
                           file_name=f"{name}_Schedule.xlsx", width="stretch", key="exp_sched_xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    trades = list(dict.fromkeys(m.material.category for m in res.purchase_list()))
    d1, d2 = st.columns([2, 1])
    with d1.container(border=True):
        st.markdown("<div style='font-size:30px'>\U0001f3ea</div><b>For shops & suppliers</b>", unsafe_allow_html=True)
        st.caption("A clean shopping list with approximate prices - all materials, or only what one shop sells.")
        pick = st.multiselect("Only these trades", trades, default=[], placeholder="All trades", key="share_trades")
        text = shopping_text(res, pick or None)
        s1, s2, s3 = st.columns(3)
        s1.download_button("\U0001f5a8\ufe0f Shopping list (PDF)", data=lambda: shopping_pdf(res, pick or None, prices, city),
                           file_name=f"{name}_Shopping_list.pdf", mime="application/pdf", width="stretch")
        short = text if len(text) < 1800 else text[:1750] + "\n... (full list in the PDF)"
        s2.link_button("\U0001f4ac WhatsApp", f"https://wa.me/?text={quote(short)}", width="stretch",
                       help="Opens WhatsApp with the list ready to send. Long lists are shortened - send the PDF instead.")
        s3.download_button("\U0001f4dd Text file", data=text.encode("utf-8"), file_name=f"{name}_Shopping_list.txt",
                           mime="text/plain", width="stretch")
    with d2.container(border=True):
        st.markdown("<div style='font-size:30px'>\U0001f4be</div><b>Keep your project</b>", unsafe_allow_html=True)
        st.caption("Save this file and open it later (sidebar \u2192 Project) to continue where you stopped.")
        st.download_button("\u2b07\ufe0f Project file", data=lambda: project_to_json(snap, False), file_name=f"{name}.costlens.json",
                           mime="application/json", width="stretch")

    with st.expander("\U0001f440 Preview the shopping list text"):
        st.code(text, language=None)
    st.caption(f"\u26a0\ufe0f {config.DISCLAIMER_TEXT_SHORT}")
    b1, b2 = st.columns(2)
    with b1:
        if st.button("\u2190 Back to schedule"):
            go_to_step(6)
            st.rerun()
    with b2:
        if st.button("\U0001f504 Start a new house", width="stretch"):
            reset_project()
            st.rerun()
