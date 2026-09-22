"""
AI Residential MTO/BOQ Estimator - Streamlit entrypoint.

A 5-step wizard:
  1. Project setup (technical inputs) + drawing upload
  2. AI drawing interpretation (Groq) -> structured JSON
  3. User verification/edit of every AI-extracted parameter
  4. Deterministic MTO calculation + traceability breakdown
  5. BOQ (rates + wastage) + cost estimate + Excel/PDF export

See README.md for the full architecture rationale.
"""
from __future__ import annotations

import hashlib
from io import BytesIO

import streamlit as st
from PIL import Image

import config
from ai.extraction import default_building_params, extract_building_params
from drawing_processing.image_processor import clean_drawing_image, estimate_is_drawing_like
from drawing_processing.ocr_engine import build_ocr_hint_text, ocr_available
from drawing_processing.pdf_processor import process_pdf
from engineering import rules
from engineering.calculations import external_perimeter_estimate, founding_depth_estimate
from engineering.validation import validate_params
from export.excel_export import build_excel_workbook
from export.pdf_export import build_pdf_report
from models.schemas import ConfidenceLevel, EngineeringAssumptions, ProjectInputs
from mto_boq.boq_generator import boq_to_dataframe, cost_by_category, generate_boq
from mto_boq.mto_generator import (
    compute_procurement_totals,
    compute_reinforcement_summary,
    generate_mto,
    group_by_category,
    mto_to_dataframe,
)
from ui.components import (
    confidence_badge,
    render_assumptions_editor,
    render_estimate_input,
    render_rate_editor,
    render_wastage_editor,
)
from ui.state import clear_drawing_derived_state, go_to_step, init_session_state, reset_project
from ui import theme
from utils import units

_page_icon = str(config.LOGO_ICON_PATH) if config.LOGO_ICON_PATH.exists() else "\U0001f3d7\ufe0f"
st.set_page_config(page_title=f"{config.APP_NAME} \u00b7 {config.APP_TAGLINE}", page_icon=_page_icon, layout="wide")
init_session_state()
theme.inject_theme()

if hasattr(st, "logo"):
    # st.logo() renders into the sidebar header, which this app themes as
    # dark navy - so it needs the white-text lockup (LOGO_HORIZONTAL_ON_DARK_PATH),
    # not the navy-text one used on light backgrounds elsewhere (the hero
    # banner draws its own text via CSS instead of a baked-in PNG, so it's
    # unaffected). `size="large"` is only available on newer Streamlit
    # (>=1.41) - fall back to the call without it on older versions. Either
    # way, ui.theme's CSS also force-enlarges the rendered image (st.logo
    # renders quite small by default), so sizing works regardless of version.
    try:
        st.logo(str(config.LOGO_HORIZONTAL_ON_DARK_PATH), icon_image=str(config.LOGO_ICON_PATH), size="large")
    except TypeError:
        try:
            st.logo(str(config.LOGO_HORIZONTAL_ON_DARK_PATH), icon_image=str(config.LOGO_ICON_PATH))
        except Exception:
            pass
    except Exception:
        pass

STEP_LABELS = ["1. Project Setup", "2. AI Analysis", "3. Verify Data", "4. MTO", "5. BOQ & Export"]


def _grade_select_index(options: dict, stored_value: str, default_index: int) -> int:
    """Finds `stored_value`'s position in options[grade_unit_key] so a grade
    selectbox re-shows the project's actual saved grade instead of silently
    snapping back to the hardcoded default every time Step 1 is revisited
    (e.g. via "← Back to Step 1" after already submitting once). Checks
    BOTH the "SI" and "FPS" lists (they're index-aligned - see
    engineering/rules.py) since `stored_value` may have been saved while
    the OTHER unit system was selected."""
    for lst in (options.get("SI", []), options.get("FPS", [])):
        if stored_value in lst:
            return lst.index(stored_value)
    return default_index

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    if not hasattr(st, "logo"):
        # Older Streamlit without st.logo() support - fall back to a plain
        # text brand header so the name/tagline still show up somewhere.
        st.title(config.APP_NAME)
    st.caption(f"v{config.APP_VERSION} \u00b7 MVP")

    # Optional user-supplied key (kept only in this browser session's
    # memory, never written to disk). It takes priority over the
    # deployment's own secret so a public demo doesn't have to spend the
    # owner's quota.
    user_key = st.text_input(
        "Groq API key (optional)",
        type="password",
        key="user_groq_api_key",
        help="Paste your own free key from https://console.groq.com/keys to use AI drawing analysis. "
        "Kept in session memory only. Leave blank to use the app's configured key, if any.",
    )
    st.session_state["groq_api_key"] = (user_key or "").strip() or (config.get_secret("GROQ_API_KEY", "") or "")

    st.markdown("---")
    st.markdown("### Progress")
    theme.render_sidebar_steps(STEP_LABELS, st.session_state["step"])

    st.markdown("---")
    if st.button("\U0001f504 Start New Project", width="stretch"):
        reset_project()
        st.rerun()

    st.markdown("---")
    st.caption(f"\u26a0\ufe0f {config.DISCLAIMER_TEXT_SHORT}")

theme.render_hero()


def _uploads_signature(files: list) -> tuple:
    """Content fingerprint of the uploaded drawings + their view tags."""
    return tuple((f["name"], hashlib.md5(f["bytes"]).hexdigest(), f["view_tag"]) for f in files)


# ---------------------------------------------------------------------------
# STEP 1 — Project setup + upload
# ---------------------------------------------------------------------------
def step_1():
    st.header("Step 1 \u00b7 Project Setup & Drawing Upload")
    st.write("Enter basic project details and upload a simple residential drawing (plan, structural layout, or section).")

    pi: ProjectInputs = st.session_state["project_inputs"]

    st.markdown("##### Units")
    unit_system_options = [units.SI, units.FPS]
    unit_system = st.selectbox(
        "Unit System",
        options=unit_system_options,
        format_func=lambda v: units.UNIT_SYSTEM_LABELS[v],
        index=unit_system_options.index(pi.unit_system) if pi.unit_system in unit_system_options else 1,
        help=(
            "FPS (default, standard Pakistani practice): every input, default dimension, calculation "
            "trace, MTO/BOQ quantity, rate and export is in feet/inches, sqft and cft, with psi concrete "
            "grades and Grade 40/60/75 steel. SI: everything in metres, m² and m³ with M-grades and "
            "Fe-grade steel. Conversions are exact; each system uses its own round standard details "
            "(e.g. 6\" lintels in FPS vs 150 mm in SI)."
        ),
        key="unit_system_selector",
    )

    # No st.form() here on purpose: a form batches every widget inside it
    # and only reruns on submit, which is exactly what breaks per-file
    # drawing tags (see below) - and the user also wants the Continue
    # button to visually sit AFTER the upload section, so the whole step
    # is simplest as one flat sequence of plain widgets with one button
    # at the very end. Streamlit reruns the whole script on every widget
    # interaction regardless of whether a form is used, so nothing here
    # loses functionality by not being wrapped in a form.
    c1, c2 = st.columns(2)
    with c1:
        project_name = st.text_input("Project Name", pi.project_name)
        client_name = st.text_input("Client Name (optional)", pi.client_name)
        location = st.text_input("Location / City", pi.location)
        soil_type = st.selectbox(
            "Soil Type", list(rules.SOIL_SIDE_SLOPE_FACTOR.keys()),
            index=list(rules.SOIL_SIDE_SLOPE_FACTOR.keys()).index(pi.soil_type) if pi.soil_type in rules.SOIL_SIDE_SLOPE_FACTOR else 1,
        )
        finish_level = st.selectbox(
            "Finish Level",
            ["Basic", "Standard", "Premium"],
            index=["Basic", "Standard", "Premium"].index(pi.finish_level),
            help=(
                "Controls the quality/cost grade of Flooring, Painting, Plaster, Doors, Windows, Electrical, "
                "Plumbing & Sanitary and Kitchen only - it never changes any quantity (the same area still "
                "gets floored/painted/plastered). Basic = economy ceramic tile, distemper, single-coat "
                "plaster, economy fittings. Standard = mid-range vitrified tile, plastic emulsion, smooth "
                "double-coat plaster, mid-range branded fittings (the rate book's default pricing). "
                "Premium = imported porcelain/marble, weathershield/texture paint, putty-finished plaster, "
                "premium/imported fittings. Adjusts the relevant BOQ rates automatically in Step 5 - see "
                "engineering/rules.py FINISH_LEVEL_RATE_MULTIPLIERS for the multipliers used."
            ),
        )
    with c2:
        grade_unit_key = units.FPS if unit_system == units.FPS else units.SI
        wall_material_options = list(rules.MASONRY_UNIT_SIZES_M.keys())
        wall_thickness_options = units.WALL_THICKNESS_OPTIONS_MM[grade_unit_key]
        concrete_grade = st.selectbox(
            "Concrete Grade (structural members)",
            rules.CONCRETE_GRADE_OPTIONS[grade_unit_key],
            index=_grade_select_index(rules.CONCRETE_GRADE_OPTIONS, pi.concrete_grade_footing, rules.CONCRETE_GRADE_DEFAULT_INDEX),
        )
        pcc_grade = st.selectbox(
            "PCC Grade",
            rules.PCC_GRADE_OPTIONS[grade_unit_key],
            index=_grade_select_index(rules.PCC_GRADE_OPTIONS, pi.pcc_grade, rules.PCC_GRADE_DEFAULT_INDEX),
        )
        steel_grade = st.selectbox(
            "Steel Grade",
            rules.STEEL_GRADE_OPTIONS[grade_unit_key],
            index=_grade_select_index(rules.STEEL_GRADE_OPTIONS, pi.steel_grade, rules.STEEL_GRADE_DEFAULT_INDEX),
        )
        wall_material = st.selectbox(
            "Wall Material",
            wall_material_options,
            index=wall_material_options.index(pi.wall_material) if pi.wall_material in wall_material_options else 0,
            format_func=lambda v: units.relabel_wall_material(v, unit_system),
        )
        # A value saved under the other unit system (e.g. 230 mm) maps to
        # the nearest option of this one (228.6 mm = 9").
        current_wall_mm = units.nearest_option(pi.wall_thickness_mm, wall_thickness_options)
        wall_thickness_mm = st.selectbox(
            "Wall Thickness",
            wall_thickness_options,
            index=wall_thickness_options.index(current_wall_mm) if current_wall_mm in wall_thickness_options else 3,
            format_func=lambda mm: units.wall_thickness_label(mm, unit_system),
        )

    st.markdown("##### Finishes & scope toggles")
    t1, t2, t3, t4, t5 = st.columns(5)
    include_flooring = t1.checkbox("Flooring", value=pi.include_flooring)
    include_waterproofing = t2.checkbox("Waterproofing", value=pi.include_waterproofing)
    include_painting = t3.checkbox("Painting", value=pi.include_painting)
    include_dpc = t4.checkbox("DPC", value=pi.include_dpc)
    include_anti_termite = t5.checkbox("Anti-termite", value=pi.include_anti_termite)
    u1, u2, u3, u4, _u5 = st.columns(5)
    include_mep = u1.checkbox(
        "MEP & sanitary", value=pi.include_mep,
        help="Electrical works, bathroom plumbing & sanitary fittings, kitchen, external water supply & drainage.",
    )
    include_staircase = u2.checkbox("Staircase", value=pi.include_staircase, help="RCC stair to every slab level incl. roof access.")
    include_parapet = u3.checkbox("Roof parapet", value=pi.include_parapet)
    include_roof_treatment = u4.checkbox(
        "Roof insulation/tiles", value=pi.include_roof_treatment, help="Mud/earth fill + brick or tuff tiles over the roof slab."
    )

    contingency_pct = st.slider("Contingency % (on total cost)", 0.0, 20.0, pi.contingency_pct, 0.5)

    st.markdown("##### Drawing Upload")
    st.caption(
        f"Upload up to {config.MAX_DRAWING_FILES} files - e.g. separate Plan, Elevation, and Section drawings. "
        "A Section view especially helps: it's the only view that shows floor height, footing depth, and slab "
        f"thickness. Up to {config.MAX_TOTAL_IMAGES} total pages/images are sent to the AI per analysis, to stay "
        "within free-tier limits."
    )
    raw_uploads = st.file_uploader(
        "Upload drawing(s) (PDF, PNG, or JPG)",
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
            view_tag = fc2.selectbox(
                "View type",
                config.DRAWING_VIEW_TYPES,
                index=min(i, len(config.DRAWING_VIEW_TYPES) - 1),
                key=f"view_tag_{i}",
                label_visibility="collapsed",
            )
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

    submitted = st.button("Continue to AI Analysis →", width="stretch", type="primary")

    if submitted:
        st.session_state["project_inputs"] = ProjectInputs(
            project_name=project_name or "Untitled Project",
            client_name=client_name,
            location=location,
            soil_type=soil_type,
            concrete_grade_footing=concrete_grade,
            concrete_grade_column=concrete_grade,
            concrete_grade_beam=concrete_grade,
            concrete_grade_slab=concrete_grade,
            pcc_grade=pcc_grade,
            steel_grade=steel_grade,
            wall_material=wall_material,
            wall_thickness_mm=wall_thickness_mm,
            finish_level=finish_level,
            include_flooring=include_flooring,
            include_waterproofing=include_waterproofing,
            include_painting=include_painting,
            include_dpc=include_dpc,
            include_anti_termite=include_anti_termite,
            include_mep=include_mep,
            include_staircase=include_staircase,
            include_parapet=include_parapet,
            include_roof_treatment=include_roof_treatment,
            contingency_pct=contingency_pct,
            unit_system=unit_system,
        )
        # If the drawings (or their view tags) changed since the last
        # analysis, drop every cached image/OCR/AI result derived from the
        # old ones - otherwise Step 2 would analyse the stale drawings.
        if unit_system != pi.unit_system:
            # Switch the Step 3 engineering-assumption defaults to the new
            # unit system's round values - unless the user edited them.
            if st.session_state["assumptions"] == EngineeringAssumptions.for_unit_system(pi.unit_system):
                st.session_state["assumptions"] = EngineeringAssumptions.for_unit_system(unit_system)
            # Parameters still at the old system's defaults are dropped so
            # the new system's defaults are used (e.g. 1.2 m -> 4'-0" footings).
            old_defaults = default_building_params(pi.wall_thickness_mm, pi.wall_material, pi.unit_system)
            if st.session_state.get("extracted_params") is not None and st.session_state["extracted_params"] == old_defaults:
                st.session_state["extracted_params"] = None
            # MTO/BOQ text (descriptions, traces) is produced in the unit
            # system it was calculated in - never show it under the other one.
            for k in ("mto_items", "boq_items", "cost_summary"):
                st.session_state[k] = None
            st.session_state["export_cache"] = {}
        signature = _uploads_signature(uploaded_files_with_tags)
        if signature != st.session_state.get("uploaded_signature"):
            clear_drawing_derived_state()
            st.session_state["uploaded_signature"] = signature
        st.session_state["uploaded_files"] = uploaded_files_with_tags
        go_to_step(2)
        st.rerun()


# ---------------------------------------------------------------------------
# STEP 2 — AI analysis
# ---------------------------------------------------------------------------
def _load_images_from_upload() -> tuple[list[Image.Image], list[str], str]:
    """Turns the tagged file list from Step 1 into a flat list of cleaned
    images plus a parallel list of view labels (one per image - every page
    of a multi-page PDF inherits that file's tag). Caps pages-per-file and
    the total image count (config.MAX_PAGES_PER_FILE / MAX_TOTAL_IMAGES) so
    a multi-file upload can't blow up the AI request size unbounded.

    Also returns the PDFs' embedded text layer (dimension strings, notes,
    schedules exported as real text by CAD) as a compact hint string for
    the AI - a free, far more reliable signal than reading tiny raster text.
    """
    uploaded_files = st.session_state.get("uploaded_files") or []
    images: list[Image.Image] = []
    labels: list[str] = []
    pdf_text_parts: list[str] = []

    for f in uploaded_files:
        if len(images) >= config.MAX_TOTAL_IMAGES:
            break
        name, file_bytes, view_tag = f["name"], f["bytes"], f["view_tag"]

        if name.lower().endswith(".pdf"):
            max_pages = min(config.MAX_PAGES_PER_FILE, config.MAX_TOTAL_IMAGES - len(images))
            result = process_pdf(file_bytes, dpi=200, max_pages=max_pages)
            file_images = [p.image for p in result.pages]
            text = " ".join(result.combined_text.split())
            if text:
                pdf_text_parts.append(f"[{view_tag} - {name}] {text}")
        else:
            file_images = [Image.open(BytesIO(file_bytes))]

        for img in file_images:
            if len(images) >= config.MAX_TOTAL_IMAGES:
                break
            images.append(clean_drawing_image(img))
            labels.append(f"{view_tag} ({name})")

    pdf_text_hint = ""
    if pdf_text_parts:
        joined = " | ".join(pdf_text_parts)[: config.MAX_PDF_TEXT_HINT_CHARS]
        pdf_text_hint = "PDF text-layer content (exact text embedded in the drawing PDF): " + joined
    return images, labels, pdf_text_hint


def step_2():
    st.header("Step 2 \u00b7 AI Drawing Analysis")

    uploaded_files = st.session_state.get("uploaded_files") or []
    if not uploaded_files:
        st.info("No drawing was uploaded. You can go back to upload one, or skip straight to manual entry with standard defaults.")
        if st.button("\u2190 Back to Step 1"):
            go_to_step(1)
            st.rerun()
        if st.button("Skip AI \u2014 enter parameters manually", type="primary"):
            st.session_state["extracted_params"] = default_building_params(
                wall_thickness_mm=st.session_state["project_inputs"].wall_thickness_mm,
                wall_material=st.session_state["project_inputs"].wall_material,
                unit_system=st.session_state["project_inputs"].unit_system,
            )
            st.session_state["used_ai"] = False
            go_to_step(3)
            st.rerun()
        return

    if "uploaded_images" not in st.session_state or not st.session_state["uploaded_images"]:
        with st.spinner("Processing uploaded drawing(s)..."):
            images, labels, pdf_text_hint = _load_images_from_upload()
            st.session_state["uploaded_images"] = images
            st.session_state["uploaded_image_labels"] = labels
            st.session_state["pdf_text_hint"] = pdf_text_hint

    images = st.session_state["uploaded_images"]
    labels = st.session_state.get("uploaded_image_labels") or []
    file_names = ", ".join(f["name"] for f in uploaded_files)
    st.write(f"**{len(images)} page/image(s)** processed from {len(uploaded_files)} file(s): `{file_names}`")
    if len(images) >= config.MAX_TOTAL_IMAGES:
        st.caption(f"Capped at {config.MAX_TOTAL_IMAGES} total images to stay within free-tier limits - some pages/files may have been left out.")

    cols = st.columns(min(len(images), 4) or 1)
    for i, img in enumerate(images):
        with cols[i % len(cols)]:
            st.image(img, caption=labels[i] if i < len(labels) else f"Page {i+1}", width="stretch")
            if not estimate_is_drawing_like(img):
                st.caption("\u26a0\ufe0f This doesn't look like a typical line drawing \u2014 results may be unreliable.")

    if ocr_available():
        with st.expander("OCR text hints (used to help the AI, not for calculations)"):
            if not st.session_state.get("ocr_hint_text"):
                with st.spinner("Running OCR..."):
                    hints = [build_ocr_hint_text(img) for img in images]
                    st.session_state["ocr_hint_text"] = "\n".join(h for h in hints if h)
            st.text(st.session_state["ocr_hint_text"] or "No text detected.")
    else:
        st.caption(
            "Optional OCR (EasyOCR) is not installed in this deployment \u2014 it is heavy for free hosting. "
            "Install it with `pip install -r requirements-ocr.txt` to enable. Vector PDFs still pass their "
            "embedded text to the AI below."
        )

    if st.session_state.get("pdf_text_hint"):
        with st.expander("PDF text-layer hints (used to help the AI, not for calculations)"):
            st.text(st.session_state["pdf_text_hint"])

    project_context = st.text_area(
        "Additional context for the AI (optional)",
        placeholder="e.g. 'This is a G+1 house, footings are isolated RCC pad footings, drawing is not to exact scale...'",
    )
    # Wall material/thickness are rarely labelled on a simple line drawing,
    # so the model has little to go on beyond a visual guess. Pass along
    # what was already chosen in Step 1 as a prior it can use UNLESS the
    # drawing clearly shows something else (see ai/prompts.py rule 1-3) -
    # this also keeps it from drifting from Step 1's selection for no
    # reason, which previously could leave the exported BOQ describing a
    # different wall material than the one shown in the project info table.
    _pi = st.session_state["project_inputs"]
    _wall_hint = (
        f"Unless the drawing clearly shows otherwise, assume wall material "
        f"'{_pi.wall_material}' and wall thickness {_pi.wall_thickness_mm}mm "
        "(both chosen in Step 1)."
    )
    project_context_for_ai = "\n".join(p for p in [project_context, _wall_hint] if p)

    c1, c2 = st.columns(2)
    with c1:
        analyze_clicked = st.button("\U0001f9e0 Analyze with Groq AI", type="primary", width="stretch")
    with c2:
        skip_clicked = st.button("Skip AI \u2014 use standard defaults", width="stretch")

    if skip_clicked:
        st.session_state["extracted_params"] = default_building_params(
            wall_thickness_mm=st.session_state["project_inputs"].wall_thickness_mm,
            wall_material=st.session_state["project_inputs"].wall_material,
            unit_system=st.session_state["project_inputs"].unit_system,
        )
        st.session_state["used_ai"] = False
        go_to_step(3)
        st.rerun()

    if analyze_clicked:
        if not st.session_state["groq_api_key"]:
            st.error(
                "No Groq API key is configured. Paste your own free key in the sidebar "
                "(console.groq.com/keys), or use 'Skip AI — use standard defaults'."
            )
        else:
            with st.spinner("Calling Groq vision model to interpret the drawing... this can take up to ~30s"):
                params, raw_text, errors = extract_building_params(
                    api_key=st.session_state["groq_api_key"],
                    images=images,
                    project_context=project_context_for_ai,
                    ocr_hint="\n".join(
                        h for h in [st.session_state.get("ocr_hint_text", ""), st.session_state.get("pdf_text_hint", "")] if h
                    ),
                    image_labels=labels,
                    wall_thickness_mm=st.session_state["project_inputs"].wall_thickness_mm,
                    wall_material=st.session_state["project_inputs"].wall_material,
                    unit_system=st.session_state["project_inputs"].unit_system,
                )
            st.session_state["extracted_params"] = params
            st.session_state["raw_ai_response"] = raw_text
            st.session_state["ai_errors"] = errors
            st.session_state["used_ai"] = True
            go_to_step(3)
            st.rerun()

    if st.button("\u2190 Back to Step 1"):
        go_to_step(1)
        st.rerun()


# ---------------------------------------------------------------------------
# STEP 3 — Verification / edit
# ---------------------------------------------------------------------------
def step_3():
    st.header("Step 3 \u00b7 Verify & Edit Extracted Parameters")
    params = st.session_state["extracted_params"]
    unit_system = st.session_state["project_inputs"].unit_system
    if units.is_fps(unit_system):
        st.caption(
            "Unit system: **FPS** (Pakistani practice) - enter lengths in feet, member sizes and thicknesses in "
            "inches, and areas in sqft. Every quantity, calculation trace and export is produced in FPS; "
            "switch to SI in Step 1 at any time."
        )

    if st.session_state.get("ai_errors"):
        for e in st.session_state["ai_errors"]:
            st.error(e)

    if st.session_state.get("used_ai") and params.extraction_warnings:
        with st.expander("\u26a0\ufe0f AI extraction warnings", expanded=True):
            for w in params.extraction_warnings:
                st.warning(w)

    if params.overall_notes:
        st.info(f"**AI notes:** {params.overall_notes}")

    legend = " ".join(confidence_badge(c) for c in [ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM, ConfidenceLevel.LOW])
    st.markdown(
        "Review every value below and edit anything that doesn't match your actual drawing. "
        f"Confidence levels: {legend}",
        unsafe_allow_html=True,
    )

    with st.expander("General", expanded=True):
        c1, c2 = st.columns(2)
        with c1:
            params.num_floors = render_estimate_input("Number of RCC slab levels (incl. roof)", params.num_floors, "num_floors_inp", "floors", step=1.0)
        with c2:
            params.plinth_area_per_floor_sqm = render_estimate_input("Plinth/built-up area per floor", params.plinth_area_per_floor_sqm, "plinth_area_inp", step=1.0, unit_system=unit_system, quantity_kind="area")

    with st.expander("Footings", expanded=True):
        footing_types = ["isolated", "strip", "raft", "combined"]
        current_type = params.footings.footing_type if params.footings.footing_type in footing_types else "isolated"
        params.footings.footing_type = st.selectbox(
            "Footing type", footing_types, index=footing_types.index(current_type),
            help="Quantities are calculated as isolated pad footings in this MVP.",
        )
        if params.footings.founding_depth_m is None:
            params.footings.founding_depth_m = founding_depth_estimate(params.footings, unit_system)
        c1, c2, c3, c4, c5 = st.columns(5)
        with c1:
            params.footings.count = render_estimate_input("Count", params.footings.count, "ftg_count", "nos", step=1.0)
        with c2:
            params.footings.length_m = render_estimate_input("Length", params.footings.length_m, "ftg_len", step=0.05, unit_system=unit_system, quantity_kind="length")
        with c3:
            params.footings.width_m = render_estimate_input("Width", params.footings.width_m, "ftg_wid", step=0.05, unit_system=unit_system, quantity_kind="length")
        with c4:
            params.footings.depth_m = render_estimate_input(
                "Footing thickness", params.footings.depth_m, "ftg_dep", step=0.05, unit_system=unit_system, quantity_kind="thickness",
                help_text=(
                    'Depth of the concrete pad itself (typically 12"-24"). Drives footing concrete volume.'
                    if units.is_fps(unit_system)
                    else "Depth of the concrete pad itself (typically 0.3-0.6 m). Drives footing concrete volume."
                ),
            )
        with c5:
            params.footings.founding_depth_m = render_estimate_input(
                "Founding depth", params.footings.founding_depth_m, "ftg_found", step=0.05, unit_system=unit_system, quantity_kind="length",
                help_text=(
                    "Natural ground level down to the UNDERSIDE of the footing (typically 4'-0\" to 6'-6\"). Drives excavation depth."
                    if units.is_fps(unit_system)
                    else "Natural ground level down to the UNDERSIDE of the footing (typically 1.2-2.0 m). Drives excavation depth."
                ),
            )

    with st.expander("Columns", expanded=True):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            params.columns.count = render_estimate_input("Count", params.columns.count, "col_count", "nos", step=1.0)
        with c2:
            params.columns.width_m = render_estimate_input("Width (b)", params.columns.width_m, "col_b", step=0.01, unit_system=unit_system, quantity_kind="thickness")
        with c3:
            params.columns.depth_m = render_estimate_input("Depth (d)", params.columns.depth_m, "col_d", step=0.01, unit_system=unit_system, quantity_kind="thickness")
        with c4:
            params.columns.height_per_floor_m = render_estimate_input("Height/floor", params.columns.height_per_floor_m, "col_h", step=0.05, unit_system=unit_system, quantity_kind="length")

    with st.expander("Beams", expanded=True):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            params.beams.count = render_estimate_input("Count per level", params.beams.count, "beam_count", "nos", step=1.0)
        with c2:
            params.beams.avg_length_m = render_estimate_input("Avg length", params.beams.avg_length_m, "beam_len", step=0.1, unit_system=unit_system, quantity_kind="length")
        with c3:
            params.beams.width_m = render_estimate_input("Width", params.beams.width_m, "beam_w", step=0.01, unit_system=unit_system, quantity_kind="thickness")
        with c4:
            params.beams.depth_m = render_estimate_input("Depth", params.beams.depth_m, "beam_d", step=0.01, unit_system=unit_system, quantity_kind="thickness")

    with st.expander("Slabs", expanded=True):
        c1, c2 = st.columns(2)
        with c1:
            params.slabs.area_per_floor_sqm = render_estimate_input("Area per floor", params.slabs.area_per_floor_sqm, "slab_area", step=1.0, unit_system=unit_system, quantity_kind="area")
        with c2:
            params.slabs.thickness_m = render_estimate_input("Thickness", params.slabs.thickness_m, "slab_t", step=0.005, unit_system=unit_system, quantity_kind="thickness")

    with st.expander("Walls / Masonry", expanded=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            params.walls.total_length_per_floor_m = render_estimate_input("Total wall length/floor", params.walls.total_length_per_floor_m, "wall_len", step=0.5, unit_system=unit_system, quantity_kind="length")
        with c2:
            params.walls.height_m = render_estimate_input("Wall height", params.walls.height_m, "wall_h", step=0.05, unit_system=unit_system, quantity_kind="length")
        with c3:
            params.walls.thickness_m = render_estimate_input("Wall thickness", params.walls.thickness_m, "wall_t", step=0.01, unit_system=unit_system, quantity_kind="thickness")
        if params.walls.external_perimeter_m is None:
            params.walls.external_perimeter_m = external_perimeter_estimate(params)
        params.walls.external_perimeter_m = render_estimate_input(
            "External wall perimeter/floor", params.walls.external_perimeter_m, "wall_ext_perim", step=0.5,
            unit_system=unit_system, quantity_kind="length",
            help_text="Outer building perimeter only (part of the total wall length). Splits internal vs external "
            "plaster/paint and sizes the roof parapet.",
        )
        params.walls.wall_material = st.selectbox(
            "Wall material", list(rules.MASONRY_UNIT_SIZES_M.keys()),
            format_func=lambda v: units.relabel_wall_material(v, unit_system),
            index=list(rules.MASONRY_UNIT_SIZES_M.keys()).index(params.walls.wall_material) if params.walls.wall_material in rules.MASONRY_UNIT_SIZES_M else 0,
        )

    with st.expander("Openings (doors/windows)", expanded=True):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            params.openings.door_count_per_floor = render_estimate_input("Doors/floor", params.openings.door_count_per_floor, "door_count", "nos", step=1.0)
        with c2:
            params.openings.avg_door_area_sqm = render_estimate_input("Avg door area", params.openings.avg_door_area_sqm, "door_area", step=0.05, unit_system=unit_system, quantity_kind="area")
        with c3:
            params.openings.window_count_per_floor = render_estimate_input("Windows/floor", params.openings.window_count_per_floor, "win_count", "nos", step=1.0)
        with c4:
            params.openings.avg_window_area_sqm = render_estimate_input("Avg window area", params.openings.avg_window_area_sqm, "win_area", step=0.05, unit_system=unit_system, quantity_kind="area")

    with st.expander("Services (drives MEP & sanitary lines)", expanded=True):
        c1, c2 = st.columns(2)
        with c1:
            params.services.bathroom_count_total = render_estimate_input("Bathrooms (whole building)", params.services.bathroom_count_total, "svc_baths", "nos", step=1.0)
        with c2:
            params.services.kitchen_count_total = render_estimate_input("Kitchens (whole building)", params.services.kitchen_count_total, "svc_kitchens", "nos", step=1.0)

    with st.expander("Engineering assumptions (thumb rules & key defaults)", expanded=False):
        st.session_state["assumptions"] = render_assumptions_editor(st.session_state["assumptions"], unit_system)

    st.session_state["extracted_params"] = params

    errors, warnings = validate_params(params, st.session_state["project_inputs"], st.session_state["assumptions"])
    if errors or warnings:
        st.markdown("##### Input checks")
        for e in errors:
            st.error(e)
        for w in warnings:
            st.warning(w)
        if errors:
            st.caption("Fix the errors above to continue - the calculation would otherwise produce meaningless quantities.")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("\u2190 Back to Step 2"):
            go_to_step(2)
            st.rerun()
    with c2:
        if st.button("Confirm & Calculate MTO \u2192", type="primary", width="stretch", disabled=bool(errors)):
            with st.spinner("Running deterministic engineering calculations..."):
                st.session_state["mto_items"] = generate_mto(
                    params, st.session_state["project_inputs"], st.session_state["assumptions"]
                )
            go_to_step(4)
            st.rerun()


# ---------------------------------------------------------------------------
# STEP 4 — MTO
# ---------------------------------------------------------------------------
def step_4():
    st.header("Step 4 \u00b7 Material Take-Off (MTO)")
    mto_items = st.session_state["mto_items"]
    unit_system = st.session_state["project_inputs"].unit_system

    summary = compute_reinforcement_summary(mto_items, unit_system)
    badge_color = "green" if summary["status"] == "OK" else "orange"
    st.markdown(f":{badge_color}[**Steel sanity check:** {summary['message']}]")

    st.markdown("##### \U0001f4e6 Procurement summary")
    st.caption(
        "Project-wide cement/sand/aggregate totals - already priced within the composite rates below, "
        "shown here purely as the quantities to hand to a supplier. Net theoretical figures; add your own "
        "site wastage margin (commonly 3-5% for cement, 5-10% for sand/aggregate) before ordering."
    )
    totals = compute_procurement_totals(mto_items)
    sand_qty, sand_unit = units.quantity_and_unit_for_display(totals["sand_m3"], "m3", unit_system)
    agg_qty, agg_unit = units.quantity_and_unit_for_display(totals["aggregate_m3"], "m3", unit_system)
    pc1, pc2, pc3 = st.columns(3)
    pc1.metric("Cement", f"{totals['cement_bags']:,.0f} bags")
    pc2.metric("Sand", f"{sand_qty:,.1f} {sand_unit}")
    pc3.metric("Aggregate/Crush", f"{agg_qty:,.1f} {agg_unit}")

    if units.is_fps(unit_system):
        st.caption(
            "Unit system: FPS - quantities, formulas, calculation inputs and assumptions below are all in "
            "feet/inches, sqft and cft (steel in kg, cement in bags)."
        )

    show_procurement_rows = st.checkbox(
        "Show cement/sand/aggregate & mortar breakdown rows in the table below",
        value=True,
        help="Uncheck to see just the main structural/finish items - the procurement breakdown rows are still fully counted above and in the export files either way.",
    )
    display_items = mto_items if show_procurement_rows else [i for i in mto_items if not i.informational]
    df = mto_to_dataframe(display_items, unit_system=unit_system)
    st.dataframe(df, width="stretch", hide_index=True)

    st.markdown("##### Calculation breakdown / traceability")
    grouped = group_by_category(mto_items)
    for category, items in grouped.items():
        with st.expander(f"{category} ({len(items)} item{'s' if len(items) != 1 else ''})"):
            for item in items:
                display_qty, display_unit = units.quantity_and_unit_for_display(item.quantity, item.unit, unit_system)
                st.markdown(f"**{item.item_code} \u2014 {item.description}**  {confidence_badge(item.confidence)}", unsafe_allow_html=True)
                st.write(f"Quantity: **{display_qty:,.3f} {display_unit}**")
                if item.informational:
                    st.caption(f"\U0001f4e6 Procurement reference only - already priced under **{item.parent_item_code}** above; do not add its cost again.")
                st.caption(f"Formula: {item.formula}" if units.is_fps(unit_system) else f"Formula (metric): {item.formula}")
                if item.inputs_used:
                    st.caption("Inputs used: " + ", ".join(f"{k}={v}" for k, v in item.inputs_used.items()))
                for a in item.assumptions:
                    st.caption(f"\u2022 {a}")
                st.markdown("---")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("\u2190 Back to Step 3 (edit parameters)"):
            go_to_step(3)
            st.rerun()
    with c2:
        if st.button("Continue to BOQ & Cost Estimate \u2192", type="primary", width="stretch"):
            go_to_step(5)
            st.rerun()


# ---------------------------------------------------------------------------
# STEP 5 — BOQ & export
# ---------------------------------------------------------------------------
def _cached_exports(pi: ProjectInputs, boq_items, cost_summary, preliminaries_pct: float) -> tuple[bytes, bytes]:
    """Builds the Excel/PDF exports only when their content changes (they
    used to be rebuilt on every single rerun of Step 5)."""
    h = hashlib.sha256()
    h.update(pi.model_dump_json().encode())
    h.update(st.session_state["extracted_params"].model_dump_json().encode())
    for item in st.session_state["mto_items"]:
        h.update(item.model_dump_json().encode())
    for item in boq_items:
        h.update(item.model_dump_json().encode())
    h.update(cost_summary.model_dump_json().encode())
    h.update(str(preliminaries_pct).encode())
    key = h.hexdigest()
    cache = st.session_state.get("export_cache") or {}
    if key not in cache:
        excel_bytes = build_excel_workbook(
            pi, st.session_state["extracted_params"], st.session_state["mto_items"], boq_items, cost_summary,
            preliminaries_pct=preliminaries_pct,
        )
        pdf_bytes = build_pdf_report(
            pi, st.session_state["extracted_params"], st.session_state["mto_items"], boq_items, cost_summary
        )
        cache = {key: (excel_bytes, pdf_bytes)}  # keep only the latest
        st.session_state["export_cache"] = cache
    return cache[key]


def step_5():
    st.header("Step 5 \u00b7 BOQ, Cost Estimate & Export")

    pi = st.session_state["project_inputs"]

    st.caption(
        f"Finish Level: **{pi.finish_level}** (set in Step 1) - Flooring, Painting, Plaster, Doors, Windows, "
        "Electrical, Plumbing & Sanitary and Kitchen rates below are automatically scaled for this grade; every "
        "other rate is unaffected. Change it in Step 1 and recalculate to compare tiers."
    )

    with st.expander("Wastage / allowance factors", expanded=False):
        st.session_state["wastage_factors"] = render_wastage_editor(st.session_state["wastage_factors"])

    with st.expander("Material & labour rates", expanded=False):
        st.caption(config.RATE_BOOK_NOTE)
        st.session_state["rate_book"] = render_rate_editor(
            st.session_state["rate_book"],
            unit_system=pi.unit_system,
            currency_symbol=config.DEFAULT_CURRENCY_SYMBOL,
        )

    pc1, pc2 = st.columns(2)
    with pc1:
        preliminaries_pct = st.slider(
            "Preliminaries & site overheads %", 0.0, 20.0, float(st.session_state["preliminaries_pct"]), 0.5,
            help="Lump-sum % of the subtotal of all priced items (site setup, supervision, water/power for works, transport).",
        )
        st.session_state["preliminaries_pct"] = preliminaries_pct
    with pc2:
        contingency_pct = st.slider("Contingency % (final)", 0.0, 20.0, pi.contingency_pct, 0.5)
    pi.contingency_pct = contingency_pct
    st.session_state["project_inputs"] = pi

    # The BOQ is recalculated on every run (it is pure, fast arithmetic),
    # so edits to rates / wastage / percentages can never leave a stale
    # BOQ or stale exports on screen.
    boq_items, cost_summary = generate_boq(
        mto_items=st.session_state["mto_items"],
        rate_book=st.session_state["rate_book"],
        wastage=st.session_state["wastage_factors"],
        project_inputs=pi,
        preliminaries_pct=preliminaries_pct,
    )
    st.session_state["boq_items"] = boq_items
    st.session_state["cost_summary"] = cost_summary
    st.caption("The BOQ and exports update automatically whenever you change rates, wastage, or percentages.")

    if st.session_state.get("boq_items"):
        boq_items = st.session_state["boq_items"]
        cost_summary = st.session_state["cost_summary"]

        if units.is_fps(pi.unit_system):
            st.caption("Unit system: FPS - quantities in cft/sqft/Nos/kg and rates per cft/sqft/Nos/kg. Amounts and totals are identical to the SI view.")

        df = boq_to_dataframe(boq_items, unit_system=pi.unit_system)
        st.dataframe(df, width="stretch", hide_index=True)

        m1, m2, m3 = st.columns(3)
        m1.metric("Subtotal", f"{config.DEFAULT_CURRENCY_SYMBOL}{cost_summary.subtotal:,.0f}")
        m2.metric(f"Contingency ({cost_summary.contingency_pct:.1f}%)", f"{config.DEFAULT_CURRENCY_SYMBOL}{cost_summary.contingency_amount:,.0f}")
        m3.metric("Grand Total", f"{config.DEFAULT_CURRENCY_SYMBOL}{cost_summary.grand_total:,.0f}")

        st.markdown("##### Cost by category")
        cat_df = cost_by_category(boq_items)
        if not cat_df.empty:
            st.bar_chart(cat_df.set_index("Category"))

        st.markdown("##### Export")
        excel_bytes, pdf_bytes = _cached_exports(pi, boq_items, cost_summary, preliminaries_pct)
        e1, e2 = st.columns(2)
        with e1:
            st.download_button(
                "\U0001f4c5 Download Excel (MTO + BOQ)",
                data=excel_bytes,
                file_name=f"{pi.project_name.replace(' ', '_')}_MTO_BOQ.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                width="stretch",
            )
        with e2:
            st.download_button(
                "\U0001f4c4 Download PDF Report",
                data=pdf_bytes,
                file_name=f"{pi.project_name.replace(' ', '_')}_Estimate_Report.pdf",
                mime="application/pdf",
                width="stretch",
            )

        st.caption(f"\u26a0\ufe0f {config.DISCLAIMER_TEXT_SHORT}")

    if st.button("\u2190 Back to Step 4 (MTO)"):
        go_to_step(4)
        st.rerun()


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
step = st.session_state["step"]
if step == 1:
    step_1()
elif step == 2:
    step_2()
elif step == 3:
    step_3()
elif step == 4:
    step_4()
elif step == 5:
    step_5()
else:
    st.session_state["step"] = 1
    st.rerun()
