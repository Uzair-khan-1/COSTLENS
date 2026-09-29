"""Step 5 - export (Excel workbook, CSV, shopping list)."""
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
    from ui.guide import section, step_header
    step_header(6)
    pi: ProjectInputs = st.session_state["project_inputs"]
    res = mto_views.ensure_current_result(pi, st.session_state.get("extracted_params"))
    if res is None:
        st.info("Calculate the materials first (Step 3 \u2192 'Calculate materials').")
        if st.button("\u2190 Back to check details"):
            go_to_step(3)
            st.rerun()
        return
    mto_views.render_drawing_mode_banner(res.project.drawing_mode)
    name = ((pi.project_name if pi.project_name not in ("", "Untitled Project") else "My_house") or "My_house").replace(" ", "_")
    from detailed_mto.shopping import shopping_pdf, shopping_text
    from urllib.parse import quote

    counts = res.status_counts()
    st.markdown(f"**{len(res.purchase_list())} materials to buy** and a **Bill of Quantities** for "
                f"*{pi.project_name if pi.project_name not in ('', 'Untitled Project') else 'your house'}*" + (f" \u2014 {counts.get('Needs input')} item(s) still need your input."
                                                         if counts.get("Needs input") else "."))

    c1, c2, c3 = st.columns(3)
    with c1.container(border=True):
        st.markdown("<div style='font-size:34px'>\U0001f477</div><b>For your contractor</b>", unsafe_allow_html=True)
        st.caption("Excel workbook: shopping list, Bill of Quantities, stage-wise purchases and every calculation. "
                   "Contractors can add their rates to the BOQ sheet.")
        st.download_button("\u2b07\ufe0f Excel workbook", data=mto_views.export_bytes(res), file_name=f"{name}_Materials_and_BOQ.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", width="stretch", type="primary")
        st.download_button("\u2b07\ufe0f Material list (CSV)", data=mto_views.schedule_csv(res),
                           file_name=f"{name}_Material_Schedule.csv", mime="text/csv", width="stretch")
    trades = list(dict.fromkeys(m.material.category for m in res.purchase_list()))
    with c2.container(border=True):
        st.markdown("<div style='font-size:34px'>\U0001f3ea</div><b>For shops &amp; suppliers</b>", unsafe_allow_html=True)
        st.caption("A clean shopping list - all materials, or only what one shop sells (e.g. only sanitary or electrical).")
        pick = st.multiselect("Only these trades", trades, default=[], placeholder="All trades", key="share_trades")
        text = shopping_text(res, pick or None)
        st.download_button("\U0001f5a8\ufe0f Shopping list (PDF)", data=lambda: shopping_pdf(res), file_name=f"{name}_shopping_list.pdf",
                           mime="application/pdf", width="stretch")
        short = text if len(text) < 1800 else text[:1750] + "\n... (full list in the PDF)"
        st.link_button("\U0001f4ac Send on WhatsApp", f"https://wa.me/?text={quote(short)}", width="stretch",
                       help="Opens WhatsApp with the list ready to send. Long lists are shortened - send the PDF instead.")
        st.download_button("\U0001f4dd Text file", data=text.encode("utf-8"), file_name=f"{name}_shopping_list.txt",
                           mime="text/plain", width="stretch")
    with c3.container(border=True):
        st.markdown("<div style='font-size:34px'>\U0001f4be</div><b>Keep your project</b>", unsafe_allow_html=True)
        st.caption("Save the project file and open it later (sidebar \u2192 Project: save / open) to change rooms, "
                   "compare options or add prices when available.")
        from persistence.project_file import project_to_json
        keys = ("project_inputs", "extracted_params", "input_mode", "dmto_options", "dmto_rooms", "dmto_openings",
                "dmto_overrides", "dmto_floors", "package_facts", "dmto_scan", "uploaded_signature", "drawing_filled",
                "brief", "copilot_scenarios", "copilot_msgs", "uploaded_files", "step", "max_step",
                    "scope_sel", "scope_confirmed", "spec_answers", "assumptions_ack", "plot_dims_user",
                    "sched_settings", "sched_target", "sched_baseline")
        snap = {k: st.session_state.get(k) for k in keys}
        st.download_button("\u2b07\ufe0f Project file", data=lambda: project_to_json(snap, False), file_name=f"{name}.costlens.json",
                           mime="application/json", width="stretch")

    with st.expander("\U0001f440 Preview the shopping list text"):
        st.code(text, language=None)
    section("", "")
    st.caption("Prices are not included yet - they will be added as a separate step. "
               f"\u26a0\ufe0f {config.DISCLAIMER_TEXT_SHORT}")
    b1, b2 = st.columns(2)
    with b1:
        if st.button("\u2190 Back to materials"):
            go_to_step(4)
            st.rerun()
    with b2:
        if st.button("\U0001f504 Start a new house", width="stretch"):
            reset_project()
            st.rerun()
