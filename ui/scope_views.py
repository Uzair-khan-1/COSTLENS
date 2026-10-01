"""
Step 3 building blocks for non-technical owners:

  render_checklist(r)          what we found / what is still needed (at the top of the page)
  render_scope_picker()        "What do you want in your house?" - tick boxes with presets
  render_detail_questions(p)   plain questions only for the ticked items; drawing values pre-filled
  render_assumptions(r)        the remaining standard values, to be acknowledged before estimating
"""
from __future__ import annotations

from typing import Dict

import streamlit as st

from detailed_mto.readiness import Readiness
from detailed_mto.scope import CORE_LABELS, GROUPS, PRESETS, SCOPE_ITEMS, active_questions
from ui.guide import section


def _answers() -> Dict[str, object]:
    return dict(st.session_state.get("spec_answers") or {})


def render_checklist(r: Readiness) -> None:
    n_miss = len(r.missing)
    done = len(r.found)
    if n_miss == 0:
        st.success(f"\u2705 **Everything needed for a realistic estimate is here.** {done} item(s) from your drawings/answers. "
                   "Review the assumptions at the bottom and press **Calculate materials**.")
    else:
        st.warning(f"\u270b **{n_miss} thing(s) still needed before we can estimate** - answer them below. "
                   "Nothing is guessed without telling you.")
    c1, c2 = st.columns(2)
    with c1.container(border=True):
        st.markdown("**\u2705 Found in your drawings / answers**")
        for f in r.found[:14]:
            st.markdown(f"<div style='font-size:14px'>\u2714\ufe0f <b>{f.title}</b> - <span style='opacity:.75'>{f.detail}</span></div>",
                        unsafe_allow_html=True)
        if len(r.found) > 14:
            st.caption(f"... and {len(r.found) - 14} more")
        if not r.found:
            st.caption("Nothing yet.")
    with c2.container(border=True):
        st.markdown("**\u2753 Still needed from you**")
        if not r.missing:
            st.caption("Nothing - all set.")
        for m in r.missing[:14]:
            st.markdown(f"<div style='font-size:14px'>\u2b55 <b>{m.title}</b> - <span style='opacity:.75'>{m.detail}</span></div>",
                        unsafe_allow_html=True)
        if len(r.missing) > 14:
            st.caption(f"... and {len(r.missing) - 14} more")


def render_scope_picker() -> None:
    section("1\ufe0f\u20e3 What do you want in your house?",
            "Tick everything you want us to include. Only ticked items are estimated - nothing else is assumed.")
    sel = set(st.session_state.get("scope_sel") or ())
    ver = st.session_state.get("scope_ver", 0)
    with st.container(border=True):
        st.markdown("<b>Always included</b> <span style='opacity:.7'>(every house needs these)</span>", unsafe_allow_html=True)
        st.markdown(" &nbsp;\u2022&nbsp; ".join(f"{i} {t}" for i, t in CORE_LABELS), unsafe_allow_html=True)
    p1, p2, p3, _ = st.columns([1.3, 1.6, 1, 2])
    for col, key in zip((p1, p2, p3), ("grey", "typical", "all")):
        if col.button(PRESETS[key][0], key=f"preset_{key}", width="stretch"):
            st.session_state["scope_sel"] = list(PRESETS[key][1])
            st.session_state["scope_confirmed"] = False
            st.session_state["scope_ver"] = ver + 1
            st.rerun()
    new_sel = set()
    cols = st.columns(2)
    for gi, group in enumerate(GROUPS):
        with cols[gi % 2].container(border=True):
            st.markdown(f"**{group}**")
            for it in [s for s in SCOPE_ITEMS if s.group == group]:
                if st.checkbox(f"{it.icon} {it.label}", value=it.key in sel, key=f"sc_{it.key}_{ver}", help=it.help):
                    new_sel.add(it.key)
    if new_sel != sel:
        st.session_state["scope_sel"] = sorted(new_sel)
        st.session_state["scope_confirmed"] = False
    confirmed = st.session_state.get("scope_confirmed")
    c1, c2 = st.columns([1, 2])
    if c1.button("\u2705 Confirm my scope" if not confirmed else "\u2714\ufe0f Scope confirmed", type="primary" if not confirmed else "secondary",
                 key="scope_confirm", width="stretch", disabled=bool(confirmed)):
        st.session_state["scope_confirmed"] = True
        st.rerun()
    c2.caption(f"{len(new_sel)} item(s) ticked. " + ("Change the ticks any time - press Confirm again after changes." if confirmed
                                                   else "Press 'Confirm my scope' when the ticks are right."))


def render_detail_questions(p) -> None:
    """Plain questions for the ticked items; values found on the drawings are pre-filled (marked)."""
    sel = set(st.session_state.get("scope_sel") or ())
    qs = active_questions(sel)
    answers = _answers()
    need = [q for q in qs if q.id not in answers and not (q.found and q.found(p) is not None)]
    section("2\ufe0f\u20e3 A few details we need",
            f"{len(qs) - len(need)} of {len(qs)} answered. Items marked \U0001f4d0 were read from your drawings - change them only if wrong.")
    ver = st.session_state.get("spec_ver", 0)
    changed = False

    def card(q, col) -> bool:
        opts = q.options(p)
        if not opts:
            return False
        labels = [lbl for lbl, _v in opts]
        found = q.found(p) if q.found else None
        cur = answers.get(q.id, found)
        idx = next((k for k, (_l, v) in enumerate(opts) if v == cur or (isinstance(v, float) and isinstance(cur, (int, float))
                                                                        and abs(v - float(cur)) < 1e-6)), None)
        with col.container(border=True):
            tag = ("\U0001f4d0 from your drawings" if (found is not None and q.id not in answers) else
                   ("\u2714\ufe0f answered" if q.id in answers else "\u2b55 needed"))
            st.markdown(f"<div style='font-size:16px;font-weight:700'>{q.icon} {q.title} "
                        f"<span style='float:right;font-size:12px;font-weight:500;opacity:.8'>{tag}</span></div>"
                        f"<div style='margin:2px 0 4px 0'>{q.question}</div>", unsafe_allow_html=True)
            if found is not None and idx is None and q.id not in answers:
                st.caption("\U0001f4d0 Read from your drawings - no answer needed. Pick an option only to replace it.")
            pick = st.radio(q.question, labels, index=idx, key=f"q_{q.id}_{ver}", label_visibility="collapsed")
            if q.help:
                st.caption("\u2139\ufe0f " + q.help)
            if pick is not None:
                val = dict(opts)[pick]
                if found is not None and val == found and q.id not in answers:
                    return False  # still the drawing value - nothing to store
                if answers.get(q.id) != val:
                    answers[q.id] = val
                    return True
        return False

    from_drawings = [q for q in qs if q.id not in answers and q.found and q.found(p) is not None]
    main = [q for q in qs if q not in from_drawings]
    cols = st.columns(2)
    for i, q in enumerate(main):
        changed = card(q, cols[i % 2]) or changed
    if from_drawings:
        with st.expander(f"\U0001f4d0 Already filled in from your drawings ({len(from_drawings)}) - open only to check or change"):
            dcols = st.columns(2)
            for i, q in enumerate(from_drawings):
                changed = card(q, dcols[i % 2]) or changed
    if changed:
        st.session_state["spec_answers"] = answers
        st.rerun()


def render_assumptions(r: Readiness) -> None:
    section("4\ufe0f\u20e3 What we will assume",
            "These values are not on your drawings and are not something an owner is expected to know. "
            "We use common Pakistani construction standards for them - please read and confirm.")
    with st.container(border=True):
        for a in r.assumptions:
            st.markdown(f"\u2022 **{a.title}:** {a.detail}")
    h = r.assumptions_hash()
    ok = st.session_state.get("assumptions_ack") == h
    val = st.checkbox("I have read these assumptions and want to use them for my estimate", value=ok, key=f"ack_{h}")
    if val and not ok:
        st.session_state["assumptions_ack"] = h
        st.rerun()
    if not val and ok:
        st.session_state["assumptions_ack"] = ""
        st.rerun()
