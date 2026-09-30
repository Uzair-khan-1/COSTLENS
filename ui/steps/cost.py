"""Step 6 - cost & cash flow (pricing/)."""
from __future__ import annotations

import streamlit as st

from models.schemas import ProjectInputs
from ui import mto_views
from ui.state import go_to_step


def step_cost():
    from ui.cost_views import render_cost_step
    from ui.guide import step_header

    step_header(6)
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
        if st.button("\u2190 Back to schedule", key="cost_back_to_5"):
            go_to_step(5)
            st.rerun()
    with c2:
        if st.button("Next: download & share \u2192", type="primary", width="stretch", key="cost_next_7"):
            go_to_step(7)
            st.rerun()
