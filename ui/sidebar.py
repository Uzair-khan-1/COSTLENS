"""
Sidebar: Groq key, clickable step navigation, project save / open, new project.
"""
from __future__ import annotations

import streamlit as st

import config
from ui import mto_views, theme
from ui.state import go_to_step, reset_project
from ui.steps.constants import STEP_LABELS


def _step_available(n: int) -> bool:
    if n <= 2:
        return True
    if n in (3, 4):
        return st.session_state.get("extracted_params") is not None
    return st.session_state.get("dmto_result") is not None


def render_sidebar() -> None:
    with st.sidebar:
        if not hasattr(st, "logo"):
            st.title(config.APP_NAME)
        st.markdown("### Your progress")
        st.caption("Click a step to go back to it.")
        labels = list(STEP_LABELS)
        if st.session_state.get("input_mode") == "sketch":
            labels[1] = "2. Your requirements"
        target = theme.render_step_nav(labels, st.session_state["step"], int(st.session_state.get("max_step", 1) or 1),
                                       _step_available)
        if target is not None:
            if st.session_state["step"] == 3:
                mto_views.commit_review_from_widgets()  # keep unsaved room / door-window table edits
            go_to_step(target)
            st.rerun()

        st.markdown("---")
        _render_project_box()
        _render_help_box()
        # AI keys live on the server only (Streamlit secrets) - never typed in by users, never saved in project files
        st.session_state["groq_api_key"] = config.get_secret("GROQ_API_KEY", "") or ""
        st.session_state["gemini_api_key"] = config.get_secret("GEMINI_API_KEY", "") or ""
        st.session_state["openrouter_api_key"] = config.get_secret("OPENROUTER_API_KEY", "") or ""
        active = [n for n, k in (("Groq", "groq_api_key"), ("Gemini", "gemini_api_key"), ("OpenRouter", "openrouter_api_key"))
                  if st.session_state.get(k)]
        if active:
            st.caption("\U0001f916 AI assistant: " + " \u2192 ".join(active) + " (tried in this order)")
            with st.expander("\U0001fa7a Test AI services"):
                st.caption("Sends a tiny test to each AI service and shows whether it answers.")
                if st.button("Run the test", key="ai_test_btn", width="stretch"):
                    from ai.groq_client import check_ai_services
                    from ai.llm import keys_from_mapping
                    with st.spinner("Testing..."):
                        st.session_state["ai_test_result"] = check_ai_services(keys_from_mapping(st.session_state))
                for r in st.session_state.get("ai_test_result") or []:
                    icon = "\u2705" if r["ok"] else "\u274c"
                    st.markdown(f"{icon} **{r['service']}** ({r['kind']}) - "
                                f"<span style='font-size:12px'>{r['model']}: {r['detail']}</span>", unsafe_allow_html=True)
        else:
            st.caption("\u26a0\ufe0f AI assistant not set up - the administrator must add GROQ_API_KEY / GEMINI_API_KEY "
                       "in Streamlit secrets.")
        if st.button("\U0001f504 Start New Project", width="stretch"):
            reset_project()
            st.rerun()

        st.markdown("---")
        st.caption(f"\u26a0\ufe0f {config.DISCLAIMER_TEXT_SHORT}")


def _render_help_box() -> None:
    from ui.texts import GLOSSARY
    with st.expander("\U0001f4d6 Words explained"):
        for word, meaning in GLOSSARY:
            st.markdown(f"**{word}** - {meaning}")
    st.checkbox("Show 'what to do here' tips", value=not st.session_state.get("hide_tips", False), key="ui_show_tips",
                on_change=lambda: st.session_state.update(hide_tips=not st.session_state.get("ui_show_tips", True)))


def _render_project_box() -> None:
    from persistence.project_file import library_delete, library_list, library_save, project_from_json, project_to_json

    with st.expander("\U0001f4be Project: save / open", expanded=False):
        pi = st.session_state.get("project_inputs")
        has_work = st.session_state.get("extracted_params") is not None or st.session_state.get("brief") is not None
        name = ((pi.project_name if pi else "") or "project").replace(" ", "_")
        if has_work:
            inc = st.checkbox("Include the drawings in the file", value=False, key="proj_inc_drawings",
                              help="Makes the file larger (the drawing set is stored inside). Without it, the project still "
                                   "reopens with everything read from the drawings.")
            keys = ("project_inputs", "extracted_params", "input_mode", "dmto_options", "dmto_rooms", "dmto_openings",
                    "dmto_overrides", "dmto_floors", "package_facts", "dmto_scan", "uploaded_signature", "drawing_filled",
                    "brief", "copilot_scenarios", "copilot_msgs", "uploaded_files", "step", "max_step",
                    "scope_sel", "scope_confirmed", "spec_answers", "assumptions_ack", "plot_dims_user",
                    "sched_settings", "sched_target", "sched_baseline", "cost_settings",
                    "spec_custom", "spec_suggested", "scope_not_needed")
            snap = {k: st.session_state.get(k) for k in keys}  # built lazily on click (runs outside the script thread)
            st.download_button("\u2b07\ufe0f Download project file", data=lambda: project_to_json(snap, inc),
                               file_name=f"{name}.costlens.json", mime="application/json", width="stretch",
                               help="Keep this file - open it later to continue exactly where you left off.")
            if st.button("Save to project library", width="stretch", key="proj_lib_save"):
                try:
                    path = library_save(st.session_state)
                    st.success(f"Saved as {path.name}")
                except OSError as exc:
                    st.error(f"Could not save: {exc}")
        else:
            st.caption("Start a project first - then you can save it here.")

        st.markdown("**Open a project**")
        up = st.file_uploader("Project file (.costlens.json)", type=["json"], key="proj_upload", label_visibility="collapsed")
        if up is not None and st.button("Open this file", width="stretch", key="proj_open_file"):
            _load(project_from_json, up.getvalue())
        items = library_list()
        if items:
            labels = {str(i["path"]): f"{i['name']} ({i['saved_at'][:16].replace('T', ' ')})" for i in items}
            pick = st.selectbox("Project library", list(labels), format_func=lambda k: labels[k], key="proj_lib_pick")
            c1, c2 = st.columns(2)
            if c1.button("Open", key="proj_lib_open", width="stretch"):
                from pathlib import Path
                _load(project_from_json, Path(pick).read_bytes())
            if c2.button("Delete", key="proj_lib_del", width="stretch"):
                from pathlib import Path
                library_delete(Path(pick))
                st.rerun()
            st.caption("On Streamlit Cloud the library is temporary - also download your project file.")


def _load(parser, raw: bytes) -> None:
    try:
        data = parser(raw)
    except ValueError as exc:
        st.error(str(exc))
        return
    reset_project()  # clean slate, then restore
    for k, v in data.items():
        st.session_state[k] = v
    st.session_state["_scrolled_step"] = None
    st.session_state["project_loaded_flash"] = f"Opened project '{data['project_inputs'].project_name}'."
    st.rerun()
