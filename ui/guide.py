"""Friendly step headers (English + Urdu hint) and 'what to do here' tips."""
from __future__ import annotations

import streamlit as st

from ui.illustrations import tip_box_html
from ui.texts import STEP_TITLE_SKETCH_2, STEP_TITLES, TIPS


def step_header(step: int, show_tips: bool = True) -> None:
    title, urdu = STEP_TITLES[step]
    if step == 2 and st.session_state.get("input_mode") == "sketch":
        title, urdu = STEP_TITLE_SKETCH_2
    st.markdown(f"<h2 style='margin-bottom:0'>Step {step} \u00b7 {title}</h2>"
                f"<div dir='rtl' style='text-align:left;color:#64748B;font-size:15px;margin:0 0 6px 0'>{urdu}</div>",
                unsafe_allow_html=True)
    if show_tips and step in TIPS and not st.session_state.get("hide_tips"):
        lines, ur = TIPS[step]
        st.markdown(tip_box_html("What to do here", lines, ur), unsafe_allow_html=True)


def section(title: str, subtitle: str = "") -> None:
    st.markdown(f"<div style='font-size:20px;font-weight:700;color:#0B1E3D;margin:14px 0 2px 0'>{title}</div>"
                + (f"<div style='color:#64748B;font-size:14px;margin-bottom:6px'>{subtitle}</div>" if subtitle else ""),
                unsafe_allow_html=True)
