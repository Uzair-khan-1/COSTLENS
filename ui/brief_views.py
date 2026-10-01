"""
Step 2 for users WITHOUT architectural drawings: "Your House Requirements".

1. The user uploads a sketch / photo and/or describes the house.
2. The AI (free Groq model, optional) reads it and asks follow-up questions;
   without an AI key the description is read with simple rules.
3. Six short, plain-language question groups complete the brief.
4. The brief becomes the rooms, doors & windows, floors and key inputs of the
   take-off, and the user continues to the normal Step 3 review.
"""
from __future__ import annotations

from typing import List

import pandas as pd
import streamlit as st

from detailed_mto.brief import (FLOORS, ROOM_TYPES, BriefRoom, ProjectBrief, add_attached_baths, apply_ai_result,
                                brief_summary, brief_to_inputs, complete_programme, parse_description, typical_rooms)
from ui.illustrations import tip_box_html
from models.schemas import ConfidenceLevel, Estimate, Source

ROOM_COLS = ["Floor", "Room", "Room type", "Length (ft)", "Width (ft)", "Source"]


def _brief(pi) -> ProjectBrief:
    b = st.session_state.get("brief")
    if b is None:
        b = ProjectBrief(marla=0.0, marla_sqft=float(pi.marla_sqft or 272.25), plot_width_ft=None, plot_depth_ft=None,
                         storeys=0)
        b.rooms = []  # nothing is assumed: the owner adds rooms (or explicitly starts from a typical layout)
        st.session_state["brief"] = b
        st.session_state["brief_ver"] = 0
    return b


def _ver() -> int:
    return int(st.session_state.get("brief_ver", 0))


def _bump():
    st.session_state["brief_ver"] = _ver() + 1


def _rooms_df(b: ProjectBrief) -> pd.DataFrame:
    return pd.DataFrame([{"Floor": r.floor, "Room": r.name, "Room type": r.room_type, "Length (ft)": r.length_ft,
                          "Width (ft)": r.width_ft, "Source": r.source} for r in b.rooms], columns=ROOM_COLS)


def _rows_to_brief_rooms(rows: List[dict], old: List[BriefRoom]) -> List[BriefRoom]:
    before = {(r.floor, r.name, r.room_type, round(r.length_ft, 2), round(r.width_ft, 2)) for r in old}
    out = []
    for r in rows:
        name = str(r.get("Room") or "").strip()
        try:
            L, W = float(r.get("Length (ft)") or 0), float(r.get("Width (ft)") or 0)
        except (TypeError, ValueError):
            continue
        if not name or L <= 0 or W <= 0 or L != L or W != W:
            continue
        fk = r.get("Floor") or "ground"
        rt = r.get("Room type") or "Bedroom"
        src = str(r.get("Source") or "")
        if (fk, name, rt, round(L, 2), round(W, 2)) not in before:
            src = "You"
        out.append(BriefRoom(fk, name.upper(), rt, L, W, src or "You"))
    return out


def render_brief_step(pi, go_to_step, groq_key: str) -> None:
    from ui.guide import step_header
    step_header(2, show_tips=False)
    idea = st.session_state.get("ui_choice") == "idea"
    st.markdown(tip_box_html("What to do here", [
        ("Describe your house in your own words" if idea else "Upload a photo of your sketch and/or describe the house") +
        " - e.g. '5 marla, double storey, 4 bedrooms with attached baths'.",
        "Press 'Read my description' (or the AI button). Then check the 6 short sections below.",
        "Press 'Create my project' at the bottom."], "اپنے گھر کی تفصیل لکھیں اور نیچے کے سوالات چیک کریں"),
        unsafe_allow_html=True)
    b = _brief(pi)
    v = _ver()
    from ai.llm import keys_from_mapping
    keys = keys_from_mapping(st.session_state)
    ai_ready = keys.any()

    # ------------------------------------------------------------ 1. input
    with st.container(border=True):
        st.markdown("##### \u270f\ufe0f 1. Show or tell us about your house")
        c1, c2 = st.columns([1, 1])
        with c1:
            files = st.file_uploader("Hand sketch, photo of a sketch, or any plan (optional)", type=["png", "jpg", "jpeg", "pdf"],
                                     accept_multiple_files=True, key="sketch_uploader",
                                     help="A phone photo of a paper sketch is fine. Writing room sizes on it (e.g. 12x13) helps a lot.")
            if files:
                st.session_state["sketch_files"] = [{"name": f.name, "bytes": f.getvalue()} for f in files[:4]]
            kept = st.session_state.get("sketch_files") or []
            if kept and not files:
                st.caption("Using previously uploaded: " + ", ".join(f["name"] for f in kept))
            for f in kept[:2]:
                if not f["name"].lower().endswith(".pdf"):
                    st.image(f["bytes"], width=220)
        with c2:
            desc = st.text_area(
                "Describe the house in your own words (optional)", value=b.description, height=150, key=f"brief_desc_{v}",
                placeholder="e.g. 5 marla double storey, 33x41 plot, corner. Ground floor: drawing room, lounge, kitchen, "
                            "1 bedroom with attached bath, car porch. First floor: 3 bedrooms with attached baths, TV lounge, "
                            "kitchen, front terrace. Load-bearing brick walls.")
            b.description = desc
        a1, a2 = st.columns(2)
        with a1:
            ai_clicked = st.button("\U0001f9e0 Read my sketch & description with AI", type="primary", width="stretch",
                                   disabled=not ai_ready or not (kept or desc.strip()),
                                   help=None if ai_ready else "The AI is not set up yet - the administrator must add the AI keys in Streamlit secrets.")
        with a2:
            rule_clicked = st.button("Read my description (no AI)", width="stretch", disabled=not desc.strip(),
                                     help="Reads plot size, storeys, number of bedrooms etc. from your text with simple rules.")
        if not ai_ready:
            st.caption("No AI key set - you can still describe the house and answer the questions below. "
                       "A free key from console.groq.com lets the AI read hand sketches.")
        if ai_clicked:
            from ai.sketch_reader import files_to_images, read_sketch
            with st.spinner("The AI is reading your sketch and description..."):
                data, err = read_sketch(groq_key, files_to_images(kept), desc, keys=keys)
            if err:
                st.error(err)
            else:
                st.session_state["brief_ai_json"] = data
                st.session_state["brief_ai_got"] = apply_ai_result(data, b)
                st.session_state["brief_added"] = complete_programme(b)
                st.session_state["brief_used_ai"] = True
                _bump()
                st.rerun()
        if rule_clicked:
            st.session_state["brief_ai_got"] = parse_description(desc, b)
            st.session_state["brief_added"] = complete_programme(b)
            st.session_state["brief_ai_json"] = None
            _bump()
            st.rerun()
        got = st.session_state.get("brief_ai_got")
        if got:
            st.success("**Understood:** " + ", ".join(got) + ". Check and complete the answers below.")
        if st.session_state.get("brief_added"):
            st.info("**Added because every house needs them** (typical sizes - edit in question 4): "
                    + ", ".join(st.session_state["brief_added"]))
        if b.ai_notes:
            st.info(f"**AI:** {b.ai_notes}")
        if b.ai_questions and st.session_state.get("brief_ai_json"):
            st.markdown("**The AI has a few questions for you:**")
            answers = []
            for i, q in enumerate(b.ai_questions):
                answers.append((q, st.text_input(q, key=f"brief_aiq_{v}_{i}")))
            if st.button("Update with my answers", disabled=not any(a.strip() for _, a in answers)):
                from ai.sketch_reader import files_to_images, read_sketch
                with st.spinner("Updating with your answers..."):
                    data, err = read_sketch(groq_key, files_to_images(kept), desc, keys=keys, previous=st.session_state["brief_ai_json"],
                                            answers=answers)
                if err:
                    st.error(err)
                else:
                    st.session_state["brief_ai_json"] = data
                    st.session_state["brief_ai_got"] = apply_ai_result(data, b)
                    st.session_state["brief_added"] = complete_programme(b)
                    _bump()
                    st.rerun()

    # ------------------------------------------------------------ 2. plot & floors
    with st.container(border=True):
        st.markdown("##### \U0001f4cf 2. Plot & floors  <span style='font-size:13px;opacity:.7'>(required)</span>", unsafe_allow_html=True)
        c1, c2, c3, c4 = st.columns(4)
        b.plot_width_ft = c1.number_input("Plot width at the road (ft)", min_value=10.0, max_value=300.0, value=b.plot_width_ft,
                                          step=0.5, placeholder="e.g. 30", key=f"bq_w_{v}")
        b.plot_depth_ft = c2.number_input("Plot depth (ft)", min_value=10.0, max_value=400.0, value=b.plot_depth_ft, step=0.5,
                                          placeholder="e.g. 45", key=f"bq_d_{v}")
        if b.plot_width_ft and b.plot_depth_ft:
            b.marla = round(b.plot_width_ft * b.plot_depth_ft / b.marla_sqft, 2)
            c3.markdown(f"<div style='padding-top:28px'>= {b.plot_width_ft * b.plot_depth_ft:,.0f} sq ft \u2248 "
                        f"<b>{b.marla:.1f} marla</b></div>", unsafe_allow_html=True)
        floors_lbl = {1: "Single storey", 2: "Double storey (G+1)", 3: "Triple storey (G+2)"}
        pick = c4.segmented_control("Floors", [1, 2, 3], default=b.storeys if b.storeys in (1, 2, 3) else None,
                                    format_func=lambda n: floors_lbl[n], key=f"bq_storeys_{v}")
        b.storeys = int(pick) if pick else 0
        b.mumty = st.checkbox("Mumty (stair room on the roof)", value=b.mumty, key=f"bq_mumty_{v}")
        st.caption("Wall material, roof, neighbours and room height are asked in the next step with everything else.")

    # ------------------------------------------------------------ 4. rooms
    with st.container(border=True):
        st.markdown("##### \U0001f3e0 4. Rooms")
        st.caption("One row per room, sizes in feet (length x width). Add or delete rows as needed. "
                   "Rooms without a size from you use typical sizes - change them if you know better.")
        edited = st.data_editor(
            _rooms_df(b), key=f"brief_rooms_{v}", hide_index=True, width="stretch", num_rows="dynamic",
            column_config={
                "Floor": st.column_config.SelectboxColumn(options=FLOORS[: b.storeys], required=True),
                "Room type": st.column_config.SelectboxColumn(options=ROOM_TYPES, required=True),
                "Length (ft)": st.column_config.NumberColumn(min_value=0.0, step=0.5, format="%.1f"),
                "Width (ft)": st.column_config.NumberColumn(min_value=0.0, step=0.5, format="%.1f"),
            }, disabled=["Source"])
        rooms_now = _rows_to_brief_rooms(edited.to_dict("records"), b.rooms)
        r1, r2, r3 = st.columns(3)
        if r1.button("Start from a typical layout (then edit)", width="stretch",
                     disabled=not (b.plot_width_ft and b.plot_depth_ft and b.storeys),
                     help="Fills a typical room list for your plot and floors. Room sizes are marked 'typical' and listed as "
                          "assumptions until you change them."):
            b.rooms = typical_rooms(b)
            _bump()
            st.rerun()
        if r2.button("Give every bedroom an attached bath", width="stretch"):
            b.rooms = add_attached_baths(rooms_now)
            _bump()
            st.rerun()
        # b.rooms stays as the editor's source data until the user continues (so table edits are never applied twice)
        st.session_state["brief_rooms_live"] = rooms_now
        beds = sum(1 for r in rooms_now if r.room_type == "Bedroom")
        baths = sum(1 for r in rooms_now if r.room_type == "Bathroom")
        r3.metric("Bedrooms / baths", f"{beds} / {baths}")
        from ui.mto_views import render_concept_plan
        render_concept_plan([{"Floor": r.floor, "Room": r.name, "Room type": r.room_type, "Length (ft)": r.length_ft,
                              "Width (ft)": r.width_ft} for r in rooms_now], expanded=False)
        orphan = [r for r in rooms_now if r.floor not in FLOORS[: b.storeys]]
        if orphan:
            st.warning(f"{len(orphan)} room(s) are on a floor above the number of storeys and will be ignored.")

    # ------------------------------------------------------------ summary & go
    with st.container(border=True):
        st.markdown("##### \u2705 Your project")
        rooms_now = st.session_state.get("brief_rooms_live", b.rooms)
        import copy
        preview = copy.copy(b)
        preview.rooms = rooms_now
        for k, txt in brief_summary(preview):
            st.markdown(f"**{k}:** {txt}")
        need = []
        if not (b.plot_width_ft and b.plot_depth_ft):
            need.append("plot width and depth")
        if b.storeys not in (1, 2, 3):
            need.append("number of floors")
        if not rooms_now:
            need.append("at least one room with its size")
        can_go = not need
        c1, c2 = st.columns([1, 2])
        with c1:
            if st.button("\u2190 Back to Step 1"):
                go_to_step(1)
                st.rerun()
        with c2:
            if st.button("Create my project & review \u2192", type="primary", width="stretch", disabled=not can_go):
                b.rooms = rooms_now
                apply_brief_to_session(pi, b)
                go_to_step(3)
                st.rerun()
        if not can_go:
            st.caption("Still needed: " + ", ".join(need) + ".")


def apply_brief_to_session(pi, b: ProjectBrief) -> None:
    """Turn the brief into the same session inputs the drawing route produces."""
    from engineering import plot_templates
    from ai.extraction import default_building_params
    from ui.state import clear_dmto_review

    w, d = b.plot_dims()
    pi2 = pi.model_copy(update=dict(plot_marla=b.marla, marla_sqft=b.marla_sqft, plot_width_ft=w,
                                    plot_storeys=int(b.storeys), finish_level={"Economy": "Basic"}.get(
                                        st.session_state["dmto_options"].finish_tier, st.session_state["dmto_options"].finish_tier)))
    st.session_state["project_inputs"] = pi2
    params = plot_templates.build_template_params(pi2) or default_building_params(
        wall_thickness_mm=pi2.wall_thickness_mm, wall_material=pi2.wall_material, unit_system=pi2.unit_system)
    inp = brief_to_inputs(b)

    def est(val, note):
        return Estimate(value=val, confidence=ConfidenceLevel.MEDIUM, source=Source.USER_INPUT, note=note)

    params.num_floors = est(float(b.storeys), "From your requirements")
    if inp["load_bearing"]:
        # load-bearing: strip foundations under the walls, only a few RCC columns (porch / large openings)
        params.footings.footing_type = "strip"
        params.footings.width_m = Estimate(value=0.762, confidence=ConfidenceLevel.LOW, source=Source.DEFAULT_ASSUMPTION,
                                           note="Typical strip foundation width 2'-6\"")
        params.footings.depth_m = Estimate(value=0.1524, confidence=ConfidenceLevel.LOW, source=Source.DEFAULT_ASSUMPTION,
                                           note="Typical 6\" PCC bed")
        params.footings.founding_depth_m = Estimate(value=1.067, confidence=ConfidenceLevel.LOW, source=Source.DEFAULT_ASSUMPTION,
                                                    note="Typical 3'-6\" founding depth")
        params.columns.count = Estimate(value=4.0, confidence=ConfidenceLevel.LOW, source=Source.DEFAULT_ASSUMPTION,
                                        note="A few RCC columns (porch / wide openings) in a load-bearing house")
        params.beams.count = Estimate(value=4.0, confidence=ConfidenceLevel.LOW, source=Source.DEFAULT_ASSUMPTION,
                                      note="A few RCC beams over wide openings per level")
    clear_dmto_review()
    st.session_state["extracted_params"] = params
    st.session_state["package_facts"] = None
    st.session_state["dmto_scan"] = None
    st.session_state["dmto_rooms"] = inp["rooms"]
    st.session_state["dmto_openings"] = inp["openings"]
    st.session_state["dmto_floors"] = inp["floors"]
    st.session_state["dmto_overrides"] = inp["overrides"]
    st.session_state["drawing_filled"] = []
    st.session_state["used_ai"] = bool(st.session_state.get("brief_used_ai"))
