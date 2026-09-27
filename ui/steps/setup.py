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
from ui.texts import CITIES, FINISH_CARDS
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
            st.markdown(f"<div style='font-weight:700;color:#0B1E3D;font-size:16px'>{title}</div>"
                        f"<div style='color:#64748B;font-size:13.5px;min-height:62px;margin:2px 0 6px 0'>{desc}</div>",
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

    # ---------------------------------------------------------------- 2. plot
    section("2\ufe0f\u20e3 Your plot", "Common Pakistani standards are filled in for you.")
    left, right = st.columns([3, 2])
    with left:
        city_names = list(CITIES)
        city0 = pi.location if pi.location in CITIES else "Islamabad"
        city = st.selectbox("City", city_names, index=city_names.index(city0), key="ui_city")
        st.caption(CITIES[city]["note"])
        sizes = list(plot_templates.PLOT_SIZES_MARLA)
        plot_marla = st.segmented_control(
            "Plot size", sizes, default=pi.plot_marla if pi.plot_marla in sizes else 5, required=True,
            format_func=lambda m: f"{m} marla", key="ui_plot_size",
            help="Pick the closest size. For other sizes choose the nearest and enter the real frontage below.")
        storey_labels = {1: "Single storey", 2: "Double storey", 3: "Triple storey"}
        plot_storeys = st.segmented_control(
            "Number of floors", plot_templates.STOREY_OPTIONS,
            default=pi.plot_storeys if pi.plot_storeys in plot_templates.STOREY_OPTIONS else 2, required=True,
            format_func=lambda n: storey_labels[n], key="ui_storeys")
        project_name = st.text_input("Project name (for your files)",
                                     "" if pi.project_name in ("", "Untitled Project") else pi.project_name,
                                     placeholder="e.g. My house - G-13 Islamabad")

    # advanced settings are rendered further down but some values are needed for the picture
    marla_default = CITIES[city]["marla_sqft"]
    marla_sqft = st.session_state.get(f"adv_marla_{city}", marla_default)
    unit_system = st.session_state.get("unit_system_selector", pi.unit_system if pi.unit_system in (units.SI, units.FPS) else units.FPS)
    typical_w, _ = plot_templates.plot_dimensions_ft(plot_marla or 5, marla_sqft)
    with left:
        fps_units = units.is_fps(unit_system)
        current_w = pi.plot_width_ft if (pi.plot_width_ft and pi.plot_marla == plot_marla and pi.marla_sqft == marla_sqft) else typical_w
        shown_w = current_w if fps_units else current_w * 0.3048
        entered_w = st.number_input(
            f"Plot width at the road ({'ft' if fps_units else 'm'})", min_value=1.0, value=float(round(shown_w, 1)),
            step=1.0 if fps_units else 0.5, key=f"plot_width_{plot_marla}_{marla_sqft}_{unit_system}",
            help="The typical frontage for this plot size is filled in - change it to match your plot.")
    entered_w_ft = entered_w if fps_units else entered_w / 0.3048
    plot_width_ft = None if abs(entered_w_ft - typical_w) < 0.01 else entered_w_ft
    with right:
        W, D = plot_templates.plot_dimensions_ft(plot_marla, marla_sqft, plot_width_ft)
        cw, cd = plot_templates.covered_footprint_ft(plot_marla, marla_sqft, plot_width_ft)
        st.markdown(ill.plot_diagram(W, D, plot_marla, marla_sqft, (cw, cd)), unsafe_allow_html=True)
        st.markdown(ill.house_elevation(int(plot_storeys), True), unsafe_allow_html=True)

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
        st.info("\u270f\ufe0f Next you can upload your sketch or photo (optional), describe the house in your own words, "
                "and answer a few simple questions. The result is a concept estimate (about \u00b115-30%).")

    # ---------------------------------------------------------------- 4. finish level
    section(("4\ufe0f\u20e3" if input_mode == "drawings" else "3\ufe0f\u20e3") + " Finish level",
            "How good should the tiles, fittings and ceilings be?")
    tier = st.segmented_control("Finish level", TIERS, default=opts.finish_tier if opts.finish_tier in TIERS else "Standard",
                                required=True, format_func=lambda t: f"{FINISH_CARDS[t][0]} {t}", key="ui_tier",
                                label_visibility="collapsed")
    st.caption(FINISH_CARDS[tier][2])

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
        b1, b2, b3, b4 = st.columns(4)
        scope = b1.selectbox("What to include", kb.scope_names,
                             index=kb.scope_names.index(opts.scope) if opts.scope in kb.scope_names else 0,
                             help="Complete house, one trade, or the 'Grey Structure' / 'Finishing' contract packages.")
        mix_keys = list(RCC_MIXES)
        rcc_mix = b2.selectbox("Concrete for slabs & columns", mix_keys,
                               index=mix_keys.index(opts.rcc_mix) if opts.rcc_mix in mix_keys else 0,
                               format_func=lambda k: RCC_MIXES[k])
        roof = b3.selectbox("Roof treatment", ["Traditional", "Insulated"], index=["Traditional", "Insulated"].index(opts.roof_system),
                            format_func=lambda r: {"Traditional": "Traditional (bitumen, mud, brick tiles)",
                                                   "Insulated": "Insulated (foam boards + membrane)"}[r])
        masonry = b4.selectbox("Walls", ["Brick", "Block"], index=["Brick", "Block"].index(opts.masonry),
                               format_func=lambda m: {"Brick": "Burnt clay bricks", "Block": "Concrete blocks"}[m])
        c1, c2, c3, c4 = st.columns(4)
        gas = c1.selectbox("Cooking gas", list(GAS_LABELS), index=list(GAS_LABELS).index(opts.gas_source),
                           format_func=lambda g: GAS_LABELS[g])
        fc = c2.checkbox("False ceilings", value=opts.include_false_ceiling if tier != "Economy" else False, key=f"adv_fc_{tier}")
        rwh = c2.checkbox("Rainwater recharge well", value=CITIES[city]["rwh"],
                          key=f"adv_rwh_{city}", help="Required by CDA in Islamabad.")
        bands = c3.checkbox("Earthquake (seismic) bands", value=opts.seismic_bands,
                            help="Recommended - Pakistan's main cities are in seismic zones 2A-3.")
        include_opt = c3.checkbox("Also list optional items", value=opts.include_options)
        client_name = c4.text_input("Client name (optional)", pi.client_name)

    label = "Continue \u2192 read my drawings" if input_mode == "drawings" else "Continue \u2192 describe my house"
    if input_mode == "drawings" and not uploaded_files_with_tags:
        st.caption("No drawings uploaded yet - you can still continue; the app then starts from a typical house for your plot.")
    submitted = st.button(label, width="stretch", type="primary")

    if submitted:
        st.session_state["project_inputs"] = pi.model_copy(update=dict(
            project_name=project_name or "Untitled Project",
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
