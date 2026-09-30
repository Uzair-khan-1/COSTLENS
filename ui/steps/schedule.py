"""Step 5 - construction schedule (CPM) and Gantt chart, estimated from the take-off quantities."""
from __future__ import annotations

import streamlit as st

from models.schemas import ProjectInputs
from ui import mto_views
from ui.state import go_to_step


def step_schedule():
    from ui.guide import step_header
    from ui.schedule_views import render_schedule_tab

    step_header(5)
    pi: ProjectInputs = st.session_state["project_inputs"]
    res = mto_views.ensure_current_result(pi, st.session_state.get("extracted_params"))
    if res is None:
        st.info("Calculate the materials first (Step 3 → 'Calculate materials').")
        if st.button("← Back to check details", key="sched_back_to_3"):
            go_to_step(3)
            st.rerun()
        return
    mto_views.render_drawing_mode_banner(res.project.drawing_mode)
    render_schedule_tab(res)

    c1, c2 = st.columns(2)
    with c1:
        if st.button("← Back to materials", key="sched_back_to_4"):
            go_to_step(4)
            st.rerun()
    with c2:
        if st.button("Next: what will it cost? →", type="primary", width="stretch", key="sched_next_6"):
            go_to_step(6)
            st.rerun()
