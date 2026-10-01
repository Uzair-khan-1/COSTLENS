"""Step 5 - Bill of Quantities & cost (pricing/)."""
from __future__ import annotations

import streamlit as st

from models.schemas import ProjectInputs
from ui import mto_views
from ui.state import go_to_step


def step_cost():
    from ui.cost_views import render_cost_step
    from ui.guide import step_header

    step_header(5)
    pi: ProjectInputs = st.session_state["project_inputs"]
    res = mto_views.ensure_current_result(pi, st.session_state.get("extracted_params"))
    if res is None:
        st.info("Calculate the materials first (Step 3 \u2192 'Calculate materials').")
        if st.button("\u2190 Back to scope & details", key="cost_back_to_3"):
            go_to_step(3)
            st.rerun()
        return
    mto_views.render_drawing_mode_banner(res.project.drawing_mode)
    render_cost_step(res)
    c1, c2 = st.columns(2)
    with c1:
        if st.button("\u2190 Back to materials", key="cost_back_to_4"):
            go_to_step(4)
            st.rerun()
    with c2:
        if st.button("Next: when can I move in? (schedule & money per month) \u2192", type="primary", width="stretch",
                     key="cost_next_6"):
            go_to_step(6)
            st.rerun()
