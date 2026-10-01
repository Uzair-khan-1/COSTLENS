"""Step 1 - your plot: what the user has (drawings / sketch / idea), city & plot, finish level, advanced settings."""
from __future__ import annotations

import hashlib

import streamlit as st

import config
from detailed_mto import Options
from engineering import plot_templates
from knowledge import load_knowledge_base
from models.schemas import EngineeringAssumptions, ProjectInputs
from ui import illustrations as ill
from ui.guide import section, step_header
from ui.illustrations import tip_box_html
from ui.state import clear_dmto_review, clear_drawing_derived_state, go_to_step
from ui.steps.analysis import base_params
from ui.steps.constants import RCC_MIXES, TIER_TO_FINISH, TIERS
from ui.texts import CITIES
from utils import units

CHOICES = {
    "drawings": ("Architect's drawings", "A PDF drawing set (AutoCAD export) - the most accurate result.", ill.card_cad),
    "sketch": ("A hand sketch or photo", "A rough plan on paper or a photo - we ask a few questions to complete it.", ill.card_sketch),
    "idea": ("Just an idea", "No drawing yet? Describe the house (e.g. 5 marla, 4 bedrooms) and answer simple questions.", ill.card_idea),
}
GAS_LABELS = {"SNGPL": "Piped gas (Sui gas)", "LPG": "LPG cylinders", "None": "No gas (electric)"}


def _uploads_signature(files: list) -> tuple:
    """Content fingerprint of the uploaded drawings + their view tags."""
    return tuple((f["name"], hashlib.md5(f["bytes"]).hexdigest(), f["view_tag"]) for f in files)


def _choice_cards() -> str:
    cur = st.session_state.get("ui_choice") or ("sketch" if st.session_state.get("input_mode") == "sketch" else "drawings")
    cols = st.columns(3)
    for col, (key, (title, desc, art)) in zip(cols, CHOICES.items()):
        with col.container(border=True):
            st.markdown(art(), unsafe_allow_html=True)
            st.markdown(f"<div style='font-weight:700;color:inherit;font-size:16px'>{title}</div>"
                        f"<div style='opacity:.72;font-size:13.5px;min-height:62px;margin:2px 0 6px 0'>{desc}</div>",
                        unsafe_allow_html=True)
            chosen = key == cur
            if st.button("\u2713 Selected" if chosen else "Choose", key=f"choice_{key}", width="stretch",
                         type="primary" if chosen else "secondary"):
                st.session_state["ui_choice"] = key
                st.rerun()
    return cur


def step_1():
    step_header(1)
    pi: ProjectInputs = st.session_state["project_inputs"]
    opts: Options = st.session_state["dmto_options"]
    if int(st.session_state.get("max_step", 1) or 1) == 1:
        st.markdown(ill.how_it_works(), unsafe_allow_html=True)

    # ---------------------------------------------------------------- 1. what do you have
    section("1\ufe0f\u20e3 What do you have?", "Choose one - you can change it later.")
    choice = _choice_cards()
    input_mode = "drawings" if choice == "drawings" else "sketch"

    # ---------------------------------------------------------------- 2. where
    section("2\ufe0f\u20e3 Where is the house?", "The city sets the local marla size and rules. The plot size is read from "
            + ("your drawings in the next step." if input_mode == "drawings" else "your answers in the next step."))
    c_city, c_name = st.columns([1, 2])
    city_names = list(CITIES)
    city0 = pi.location if pi.location in CITIES else "Islamabad"
    city = c_city.selectbox("City", city_names, index=city_names.index(city0), key="ui_city")
    project_name = c_name.text_input("Project name (for your files)",
                                     "" if pi.project_name in ("", "Untitled Project") else pi.project_name,
                                     placeholder="e.g. My house - G-13 Islamabad")
    st.caption(CITIES[city]["note"])
    marla_default = CITIES[city]["marla_sqft"]
    # the plot size is NOT chosen here: it is read from the drawings (or asked in the requirements step)
    plot_marla, plot_width_ft, plot_storeys = pi.plot_marla, pi.plot_width_ft, pi.plot_storeys
    unit_system = st.session_state.get("unit_system_selector", pi.unit_system if pi.unit_system in (units.SI, units.FPS) else units.FPS)

    # ---------------------------------------------------------------- 3. drawings upload (drawing route)
    uploaded_files_with_tags = list(st.session_state.get("uploaded_files") or [])
    if input_mode == "drawings":
        section("3\ufe0f\u20e3 Upload your drawings",
                "The complete set from your architect works best (plans, elevations, foundation, plumbing and electrical sheets).")
        st.markdown(tip_box_html("Tips for the best result", [
            "Ask your architect for the PDF exported from AutoCAD (not a scan or photo) - we can read every size from it.",
            "One multi-page PDF with all sheets is perfect. Photos also work, but then we need the AI or your answers.",
            f"Up to {config.MAX_DRAWING_FILES} files. The sheet type is detected automatically - you don't have to set it."],
            "آرکیٹیکٹ سے AutoCAD والی PDF مانگیں - اسکین نہیں"), unsafe_allow_html=True)
        raw_uploads = st.file_uploader(
            "Drawing files (PDF, PNG or JPG)",
            type=config.SUPPORTED_FILE_TYPES,
            accept_multiple_files=True,
            key="drawing_uploader",
        )

        uploaded_files_with_tags = []
        if raw_uploads:
            if len(raw_uploads) > config.MAX_DRAWING_FILES:
                st.warning(f"Only the first {config.MAX_DRAWING_FILES} files will be used - remove some to change which ones.")
            for i, f in enumerate(raw_uploads[: config.MAX_DRAWING_FILES]):
                fc1, fc2 = st.columns([3, 2])
                fc1.caption(f"\U0001f4c4 {f.name}")
                if f.name.lower().endswith(".pdf"):
                    # every sheet of a PDF is classified automatically (plans, elevations, sections ...)
                    fc2.caption("\u2705 sheets detected automatically")
                    view_tag = config.DRAWING_VIEW_TYPES[-1]
                else:
                    view_tag = fc2.selectbox(
                        "What does this picture show?", config.DRAWING_VIEW_TYPES,
                        index=min(i, len(config.DRAWING_VIEW_TYPES) - 1), key=f"view_tag_{i}",
                        label_visibility="collapsed")
                uploaded_files_with_tags.append({"name": f.name, "bytes": f.getvalue(), "view_tag": view_tag})
        elif st.session_state.get("uploaded_files"):
            # Streamlit empties a file_uploader when you navigate away from the
            # step that shows it, so coming back to Step 1 would otherwise
            # silently drop the drawings. Keep the previously attached files
            # (with editable view tags) unless new files are uploaded or the
            # user explicitly removes them.
            st.caption("Previously attached drawing(s) are kept. Upload new files above to replace them.")
            for i, f in enumerate(st.session_state["uploaded_files"]):
                fc1, fc2 = st.columns([3, 2])
                fc1.caption(f"\U0001f4ce {f['name']}")
                tag = f.get("view_tag", config.DRAWING_VIEW_TYPES[-1])
                view_tag = fc2.selectbox(
                    "View type",
                    config.DRAWING_VIEW_TYPES,
                    index=config.DRAWING_VIEW_TYPES.index(tag) if tag in config.DRAWING_VIEW_TYPES else len(config.DRAWING_VIEW_TYPES) - 1,
                    key=f"kept_view_tag_{i}",
                    label_visibility="collapsed",
                )
                uploaded_files_with_tags.append({"name": f["name"], "bytes": f["bytes"], "view_tag": view_tag})
            if st.button("Remove attached drawing(s)"):
                st.session_state["uploaded_files"] = []
                clear_drawing_derived_state()
                st.session_state["uploaded_signature"] = None
                st.rerun()

    if input_mode == "sketch":
        st.info("\u270f\ufe0f Next you enter your plot size and rooms (or upload a sketch / describe the house), then choose "
                "what you want in the house. Nothing is assumed without asking you.")

    tier = opts.finish_tier if opts.finish_tier in TIERS else "Standard"  # finishes are chosen item by item in Step 3

    # ---------------------------------------------------------------- advanced (engineers)
    kb = load_knowledge_base()
    with st.expander("\u2699\ufe0f Advanced settings (for engineers) - common Pakistani standards are already selected"):
        a1, a2, a3 = st.columns(3)
        marla_options = list(plot_templates.MARLA_STANDARDS)
        marla_sqft = a1.selectbox("Marla size", marla_options, index=marla_options.index(marla_default),
                                  format_func=lambda v: plot_templates.MARLA_STANDARDS[v], key=f"adv_marla_{city}")
        unit_system_options = [units.FPS, units.SI]
        unit_system = a2.selectbox("Units", unit_system_options, format_func=lambda v: units.UNIT_SYSTEM_LABELS[v],
                                   index=unit_system_options.index(pi.unit_system) if pi.unit_system in unit_system_options else 0,
                                   key="unit_system_selector",
                                   help="FPS (feet, sq ft, cft, bags) is standard in Pakistan. The material take-off is always in FPS.")
        grade_unit_key = units.FPS if unit_system == units.FPS else units.SI
        wall_thickness_options = units.WALL_THICKNESS_OPTIONS_MM[grade_unit_key]
        current_wall_mm = units.nearest_option(pi.wall_thickness_mm, wall_thickness_options)
        wall_thickness_mm = a3.selectbox(
            "Main wall thickness", wall_thickness_options,
            index=wall_thickness_options.index(current_wall_mm) if current_wall_mm in wall_thickness_options else 3,
            format_func=lambda mm: units.wall_thickness_label(mm, unit_system),
            help="Standard: 9 inch outer walls. Only used when drawings are scans (CAD drawings give measured walls).")
        b1, b2, b3 = st.columns(3)
        scope = b1.selectbox("Report package", kb.scope_names,
                             index=kb.scope_names.index(opts.scope) if opts.scope in kb.scope_names else 0,
                             help="Normally 'Complete Project' - the owner's scope of work is chosen item by item in Step 3.")
        mix_keys = list(RCC_MIXES)
        rcc_mix = b2.selectbox("Concrete for slabs & columns", mix_keys,
                               index=mix_keys.index(opts.rcc_mix) if opts.rcc_mix in mix_keys else 0,
                               format_func=lambda k: RCC_MIXES[k])
        bands = b3.checkbox("Earthquake (seismic) bands", value=opts.seismic_bands,
                            help="Recommended - Pakistan's main cities are in seismic zones 2A-3.")
        include_opt = b3.checkbox("Also list optional items", value=opts.include_options)
        client_name = b1.text_input("Client name (optional)", pi.client_name)
        # walls, roof, gas, ceilings and the recharge well are the owner's choices in Step 3 (scope & details)
        roof, masonry, gas = opts.roof_system, opts.masonry, opts.gas_source
        fc, rwh = opts.include_false_ceiling, opts.include_rwh

    label = "Continue \u2192 read my drawings" if input_mode == "drawings" else "Continue \u2192 describe my house"
    no_files = input_mode == "drawings" and not uploaded_files_with_tags
    if no_files:
        st.info("\U0001f4c2 Upload your drawings to continue - or choose 'A hand sketch or photo' / 'Just an idea' above.")
    submitted = st.button(label, width="stretch", type="primary", disabled=no_files)

    if submitted:
        st.session_state["project_inputs"] = pi.model_copy(update=dict(
            project_name=project_name or "My house",
            client_name=client_name,
            location=city,
            wall_thickness_mm=wall_thickness_mm,
            finish_level=TIER_TO_FINISH.get(tier, "Standard"),
            unit_system=unit_system,
            plot_marla=plot_marla,
            marla_sqft=marla_sqft,
            plot_width_ft=plot_width_ft,
            plot_storeys=plot_storeys,
        ))
        new_opts = Options(scope=scope, finish_tier=tier, roof_system=roof, masonry=masonry, gas_source=gas,
                           include_false_ceiling=fc, include_rwh=rwh, include_options=include_opt, seismic_bands=bands,
                           rcc_mix=rcc_mix)
        if new_opts != opts:
            st.session_state["dmto_options"] = new_opts
            st.session_state["dmto_result"] = None
        # If the drawings (or their view tags) changed since the last
        # analysis, drop every cached image/OCR/AI result derived from the
        # old ones - otherwise Step 2 would analyse the stale drawings.
        if unit_system != pi.unit_system:
            # Switch the Step 3 engineering-assumption defaults to the new
            # unit system's round values - unless the user edited them.
            if st.session_state["assumptions"] == EngineeringAssumptions.for_unit_system(pi.unit_system):
                st.session_state["assumptions"] = EngineeringAssumptions.for_unit_system(unit_system)
            st.session_state["dmto_result"] = None
        new_pi = st.session_state["project_inputs"]
        plot_key = lambda x: (x.plot_marla, x.marla_sqft, x.plot_width_ft, x.plot_storeys)  # noqa: E731
        if unit_system != pi.unit_system or plot_key(pi) != plot_key(new_pi):
            # Parameters still at the old starting point (plot template or
            # unit-system defaults) are dropped so the new one is used, e.g.
            # 1.2 m -> 4'-0" footings, or a 5 -> 10 marla template.
            if st.session_state.get("extracted_params") is not None and st.session_state["extracted_params"] == base_params(pi):
                st.session_state["extracted_params"] = None
            # The drawing analysis text is unit-formatted and uses the plot
            # width as a hint - redo it for the new settings.
            st.session_state["package_facts"] = None
            st.session_state["uploaded_images"] = []
            clear_dmto_review()
        if input_mode != st.session_state.get("input_mode", "drawings"):
            clear_drawing_derived_state()
            st.session_state["uploaded_signature"] = None
            st.session_state["brief"] = None
        st.session_state["input_mode"] = input_mode
        if input_mode == "sketch":
            st.session_state["uploaded_files"] = []
            go_to_step(2)
            st.rerun()
        signature = _uploads_signature(uploaded_files_with_tags)
        if signature != st.session_state.get("uploaded_signature"):
            clear_drawing_derived_state()
            st.session_state["uploaded_signature"] = signature
        st.session_state["uploaded_files"] = uploaded_files_with_tags
        go_to_step(2)
        st.rerun()
