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
        st.session_state["scope_not_needed"] = sorted(set(st.session_state.get("scope_not_needed") or ()) - new_sel)
    confirmed = st.session_state.get("scope_confirmed")
    c1, c2 = st.columns([1, 2])
    if c1.button("\u2705 Confirm my scope" if not confirmed else "\u2714\ufe0f Scope confirmed", type="primary" if not confirmed else "secondary",
                 key="scope_confirm", width="stretch", disabled=bool(confirmed)):
        st.session_state["scope_confirmed"] = True
        st.rerun()
    c2.caption(f"{len(new_sel)} item(s) ticked. " + ("Change the ticks any time - press Confirm again after changes." if confirmed
                                                   else "Press 'Confirm my scope' when the ticks are right."))


NOT_NEEDED = "\U0001f6ab Not needed in my house"


def _primary_question_ids() -> dict:
    """The first question of each optional scope item gets a 'Not needed' answer (it removes the item)."""
    from detailed_mto.scope import QUESTIONS
    keep = {"wiring", "fixtures"}  # every house is wired; fans already have "No ceiling fans"
    out = {}
    for q in QUESTIONS:
        if q.scope != "core" and q.scope not in keep and q.scope not in out.values():
            out[q.id] = q.scope
    return out


CUSTOM_LABEL = "\u270f\ufe0f Type my own number"


def render_detail_questions(p) -> None:
    """All questions in one fixed grid - nothing moves or disappears when you answer.
    Every question starts with the most common answer pre-selected (marked 'suggested'); values read from the
    drawings are pre-selected too. Change any answer by clicking; where it makes sense you can type your own number.
    'Not needed' removes an optional item from materials, BOQ, cost and schedule (and can be undone right here)."""
    from detailed_mto.scope import ITEMS, QUESTIONS_BY_ID, default_answer
    sel = set(st.session_state.get("scope_sel") or ())
    not_needed = set(st.session_state.get("scope_not_needed") or ()) - sel
    primary = _primary_question_ids()
    qs = [q for q in active_questions(sel)]
    # questions of items marked 'Not needed' stay visible (with 'Not needed' selected) so the choice can be undone
    for qid, scope_key in primary.items():
        if scope_key in not_needed and qid in QUESTIONS_BY_ID:
            qs.append(QUESTIONS_BY_ID[qid])
    order = {q.id: i for i, q in enumerate(QUESTIONS_BY_ID.values())}
    qs.sort(key=lambda q: order.get(q.id, 999))
    answers = _answers()
    custom_raw = dict(st.session_state.get("spec_custom") or {})
    suggested = set(st.session_state.get("spec_suggested") or ())

    def is_found(q):
        return q.found is not None and q.found(p) is not None

    # pre-select the most common answer for every unanswered question (owner can change it)
    filled = False
    for q in qs:
        if q.id not in answers and not is_found(q) and q.scope not in not_needed:
            v = default_answer(q, p)
            if v is not None:
                answers[q.id] = v
                suggested.add(q.id)
                filled = True
    if filled:
        st.session_state["spec_answers"] = answers
        st.session_state["spec_suggested"] = sorted(suggested)

    n_sug = sum(1 for q in qs if q.id in suggested and q.id in answers)
    n_found = sum(1 for q in qs if q.id not in answers and is_found(q))
    section("2\ufe0f\u20e3 A few details we need",
            "We have pre-selected the most common choice for each question (\u2b50 suggested) - check them and change "
            "anything that is different in your house. Your changes update the materials, cost and schedule.")
    st.caption(f"\u2b50 {n_sug} suggested \u00b7 \U0001f4d0 {n_found} from your drawings \u00b7 "
               f"\u2714\ufe0f {len(qs) - n_sug - n_found} chosen by you")
    removed = st.session_state.pop("scope_removed_msg", None)
    if removed:
        st.info(removed)
    ver = st.session_state.get("spec_ver", 0)
    changes, new_custom = {}, {}

    cols = st.columns(2)
    for i, q in enumerate(qs):
        opts = list(q.options(p))
        if not opts:
            continue
        labels = [lbl for lbl, _v in opts]
        values = [v for _l, v in opts]
        if q.custom:
            labels.append(CUSTOM_LABEL)
        if q.id in primary:
            labels.append(NOT_NEEDED)
        found = q.found(p) if q.found else None
        cur = answers.get(q.id, found)
        if q.scope in not_needed:
            idx = labels.index(NOT_NEEDED)
        else:
            idx = next((k for k, v in enumerate(values) if v == cur or (isinstance(v, (int, float)) and
                        isinstance(cur, (int, float)) and abs(float(v) - float(cur)) < 1e-6)), None)
            if idx is None and q.custom and q.id in answers:
                idx = labels.index(CUSTOM_LABEL)
        if q.scope in not_needed:
            tag = "\U0001f6ab not needed"
        elif q.id not in answers and found is not None:
            tag = "\U0001f4d0 from your drawings"
        elif q.id in suggested:
            tag = "\u2b50 suggested"
        elif idx is not None and q.custom and labels[idx] == CUSTOM_LABEL:
            tag = "\u270f\ufe0f your number"
        else:
            tag = "\u2714\ufe0f your choice"
        with cols[i % 2].container(border=True):
            st.markdown(f"<div style='font-size:16px;font-weight:700'>{q.icon} {q.title} "
                        f"<span style='float:right;font-size:12px;font-weight:500;opacity:.85'>{tag}</span></div>"
                        f"<div style='margin:2px 0 4px 0'>{q.question}</div>", unsafe_allow_html=True)
            pick = st.radio(q.question, labels, index=idx, key=f"q_{q.id}_{ver}", label_visibility="collapsed")
            if pick == CUSTOM_LABEL and q.custom:
                c = q.custom
                raw0 = custom_raw.get(q.id)
                if raw0 is None:
                    try:
                        raw0 = c.from_value(cur) if cur is not None else c.default
                    except (TypeError, ValueError):
                        raw0 = c.default
                raw0 = min(max(float(raw0), c.min), c.max)
                raw = st.number_input(f"{c.prompt} ({c.unit})", min_value=float(c.min), max_value=float(c.max),
                                      value=float(raw0), step=float(c.step), key=f"qn_{q.id}_{ver}")
                val = c.to_value(raw)
                if q.id not in answers or answers.get(q.id) != val or q.id in suggested:
                    if answers.get(q.id) != val or q.id in suggested:
                        changes[q.id] = val
                        new_custom[q.id] = raw
            elif pick == NOT_NEEDED:
                if q.scope not in not_needed:
                    changes[q.id] = "__not_needed__"
            elif pick is not None:
                val = dict(zip(labels, values + [None] * (len(labels) - len(values))))[pick]
                if q.scope in not_needed:
                    changes[q.id] = ("__add_back__", val)
                elif not (found is not None and val == found and q.id not in answers):
                    if answers.get(q.id) != val:
                        changes[q.id] = val
            if q.help:
                st.caption("\u2139\ufe0f " + q.help)

    if not changes:
        return
    sel_now = set(st.session_state.get("scope_sel") or ())
    nn_now = set(st.session_state.get("scope_not_needed") or ())
    for qid, v in changes.items():
        scope_key = primary.get(qid)
        if v == "__not_needed__" and scope_key:
            sel_now.discard(scope_key)
            nn_now.add(scope_key)
            label = ITEMS[scope_key].label if scope_key in ITEMS else scope_key
            st.session_state["scope_removed_msg"] = (f"\U0001f6ab **{label}** is no longer in the materials, BOQ, cost or "
                                                     "schedule. Pick another answer in the same box to add it back.")
            answers.pop(qid, None)
        elif isinstance(v, tuple) and v and v[0] == "__add_back__" and scope_key:
            sel_now.add(scope_key)
            nn_now.discard(scope_key)
            answers[qid] = v[1]
        else:
            answers[qid] = v
        suggested.discard(qid)
        if qid in new_custom:
            custom_raw[qid] = new_custom[qid]
    st.session_state["scope_sel"] = sorted(sel_now)
    st.session_state["scope_not_needed"] = sorted(nn_now)
    st.session_state["scope_ver"] = st.session_state.get("scope_ver", 0) + 1  # tick boxes follow
    st.session_state["spec_answers"] = answers
    st.session_state["spec_custom"] = custom_raw
    st.session_state["spec_suggested"] = sorted(suggested)
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
