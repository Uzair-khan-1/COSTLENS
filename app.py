"""
Drawing-based Material Take-Off for 5-10 marla houses - Streamlit entrypoint.

A 5-step wizard:
  1. Project setup + take-off specification + drawing upload
  2. Drawing analysis: CAD text/vector reading (free), label scan, optional AI
  3. Review drawing data: rooms, doors & windows, counts & dimensions, structure
  4. Material take-off: every material of the Master Material Database with
     status, confidence, stage and full traceability
  5. Export (Excel workbook + CSV)

Costs are intentionally excluded in this version (quantities only). The
legacy cost modules (mto_boq/, export/) are kept for the future pricing step.

See README.md for the full architecture rationale.
"""
from __future__ import annotations

import hashlib

import pandas as pd
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
from engineering import plot_templates
from drawing_processing.package_analyzer import analyze_package, apply_package_facts, pages_for_ai, render_pages
from detailed_mto import Options, scan_pdf_bytes
from knowledge import load_knowledge_base
from models.schemas import ConfidenceLevel, EngineeringAssumptions, Estimate, ProjectInputs, Source
from ui.components import confidence_badge, render_estimate_input
from ui import mto_views
from ui.state import clear_dmto_review, clear_drawing_derived_state, go_to_step, init_session_state, reset_project
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

STEP_LABELS = ["1. Project Setup", "2. Drawing Analysis", "3. Review Data", "4. Material Take-Off", "5. Export"]
TIERS = ["Economy", "Standard", "Premium"]
TIER_TO_FINISH = {"Economy": "Basic", "Standard": "Standard", "Premium": "Premium"}
RCC_MIXES = {"MX_RCC124": "1:2:4 (drawing spec, ~2500 psi)", "MX_RCC1153": "1:1.5:3 (~3000 psi, recommended zone 2B)"}


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    if not hasattr(st, "logo"):
        # Older Streamlit without st.logo() support - fall back to a plain
        # text brand header so the name/tagline still show up somewhere.
        st.title(config.APP_NAME)
    st.caption(f"v{config.APP_VERSION} \u00b7 Material Take-Off")

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
    st.write("Enter the project details, choose the take-off specification and upload the complete drawing set "
             "(architectural, structural, plumbing and electrical sheets).")

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

    # ---- Plot (the app's 5-10 marla scope) --------------------------------
    st.markdown("##### Plot (5-10 marla)")
    plot_options = [None] + plot_templates.PLOT_SIZES_MARLA
    pc1, pc2, pc3, pc4 = st.columns(4)
    plot_marla = pc1.selectbox(
        "Plot size",
        plot_options,
        index=plot_options.index(pi.plot_marla) if pi.plot_marla in plot_options else 0,
        format_func=lambda m: "Not specified" if m is None else f"{m} marla",
        help="Choosing a plot size gives a complete typical house as the starting point (even with no drawing) "
        "and lets the app flag values that are implausible for that plot.",
    )
    marla_options = list(plot_templates.MARLA_STANDARDS)
    marla_sqft = pc2.selectbox(
        "Marla standard",
        marla_options,
        index=marla_options.index(pi.marla_sqft) if pi.marla_sqft in marla_options else 0,
        format_func=lambda v: plot_templates.MARLA_STANDARDS[v],
        disabled=plot_marla is None,
        help="Housing societies (LDA/DHA/Bahria style) use 225 sqft per marla; traditional measurement uses 272.25 sqft - a ~21% difference.",
    )
    storey_labels = {1: "Single storey", 2: "G+1 (double storey)", 3: "G+2"}
    plot_storeys = pc3.selectbox(
        "Storeys",
        plot_templates.STOREY_OPTIONS,
        index=plot_templates.STOREY_OPTIONS.index(pi.plot_storeys) if pi.plot_storeys in plot_templates.STOREY_OPTIONS else 1,
        format_func=lambda n: storey_labels[n],
        disabled=plot_marla is None,
    )
    typical_w, _ = plot_templates.plot_dimensions_ft(plot_marla or 5, marla_sqft)
    current_w = pi.plot_width_ft or typical_w
    fps_units = units.is_fps(unit_system)
    shown_w = current_w if fps_units else current_w * 0.3048
    entered_w = pc4.number_input(
        f"Plot width / frontage ({'ft' if fps_units else 'm'})",
        min_value=1.0,
        value=float(round(shown_w, 2)),
        step=1.0 if fps_units else 0.5,
        disabled=plot_marla is None,
        key=f"plot_width_{plot_marla}_{marla_sqft}_{unit_system}",
        help="Typical frontage for this plot size is pre-filled - change it to match your plot.",
    )
    entered_w_ft = entered_w if fps_units else entered_w / 0.3048
    plot_width_ft = None if abs(entered_w_ft - typical_w) < 0.01 else entered_w_ft
    if plot_marla:
        W, D = plot_templates.plot_dimensions_ft(plot_marla, marla_sqft, plot_width_ft)
        cw, cd = plot_templates.covered_footprint_ft(plot_marla, marla_sqft, plot_width_ft)
        L = lambda ft: units.length_text(ft * 0.3048, unit_system, f"{ft * 0.3048:.2f} m")  # noqa: E731
        Ar = lambda sq: units.area_text(sq * 0.09290304, unit_system, f"{sq * 0.09290304:,.1f} m²", 0)  # noqa: E731
        st.caption(
            f"Plot {L(W)} x {L(D)} = {Ar(W * D)}. Typical covered footprint {L(cw)} x {L(cd)} = {Ar(cw * cd)} per floor "
            "(front/rear open space as typical - edit in Step 3 if different)."
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
    with c2:
        location = st.text_input("Location / City", pi.location)
        grade_unit_key = units.FPS if unit_system == units.FPS else units.SI
        wall_thickness_options = units.WALL_THICKNESS_OPTIONS_MM[grade_unit_key]
        # A value saved under the other unit system (e.g. 230 mm) maps to
        # the nearest option of this one (228.6 mm = 9").
        current_wall_mm = units.nearest_option(pi.wall_thickness_mm, wall_thickness_options)
        wall_thickness_mm = st.selectbox(
            "Main (external/load-bearing) wall thickness",
            wall_thickness_options,
            index=wall_thickness_options.index(current_wall_mm) if current_wall_mm in wall_thickness_options else 3,
            format_func=lambda mm: units.wall_thickness_label(mm, unit_system),
            help="Used only when the drawings are scanned images (CAD PDFs give measured wall thicknesses).",
        )

    # ---- Take-off specification (drives which materials are quantified) ----
    opts: Options = st.session_state["dmto_options"]
    kb = load_knowledge_base()
    st.markdown("##### Take-off scope & specification")
    st.caption(
        "These choices decide WHICH materials are quantified (e.g. traditional roof = bitumen + earth + brick tiles; "
        "insulated roof = EPS/XPS + membrane). Quantities always come from the drawings. Costs are not part of this version."
    )
    s1, s2, s3, s4 = st.columns(4)
    scope = s1.selectbox("Scope", kb.scope_names, index=kb.scope_names.index(opts.scope) if opts.scope in kb.scope_names else 0,
                         help="Complete Project, a single discipline, or the Pakistani 'Grey Structure' / 'Finishing' contract packages.")
    tier = s2.selectbox("Finish tier", TIERS, index=TIERS.index(opts.finish_tier) if opts.finish_tier in TIERS else 1,
                        help="Economy skips false ceilings/cornices and built-in kitchen appliances; Premium adds items such as "
                        "linear shower drains, recirculation pump and built-in oven.")
    mix_keys = list(RCC_MIXES)
    rcc_mix = s3.selectbox("Structural RCC mix", mix_keys, index=mix_keys.index(opts.rcc_mix) if opts.rcc_mix in mix_keys else 0,
                           format_func=lambda k: RCC_MIXES[k],
                           help="Applies to footings, columns, beams, slabs and stairs. Tanks, lintels and DPC keep their drawing mixes.")
    roof = s4.selectbox("Roof treatment", ["Traditional", "Insulated"], index=["Traditional", "Insulated"].index(opts.roof_system),
                        help="Traditional = 2 coats bitumen + polythene + earth + mud plaster + brick tiles. "
                        "Insulated = EPS/XPS board + membrane + screed.")
    s5, s6, s7, s8 = st.columns(4)
    masonry = s5.selectbox("Walling", ["Brick", "Block"], index=["Brick", "Block"].index(opts.masonry))
    gas = s6.selectbox("Gas supply", ["SNGPL", "LPG", "None"], index=["SNGPL", "LPG", "None"].index(opts.gas_source),
                       help="New SNGPL domestic connections are restricted - choose LPG if the house will use cylinders.")
    fc = s7.checkbox("False ceilings", value=opts.include_false_ceiling)
    rwh = s7.checkbox("Rainwater recharge well", value=opts.include_rwh, help="CDA requires rainwater harvesting/recharge (not shown in most drawing sets).")
    bands = s8.checkbox("Seismic lintel bands", value=opts.seismic_bands, help="Recommended for load-bearing masonry in Islamabad/Rawalpindi (BCP zone 2B).")
    include_opt = s8.checkbox("Quantify optional items too", value=opts.include_options,
                              help="Also include Optional/Alternative/Premium materials in the take-off.")

    st.markdown("##### Drawing Upload")
    st.caption(
        f"Upload the whole drawing set - up to {config.MAX_DRAWING_FILES} files (floor plans, sections, elevations, "
        "foundation/structural sheets), as multi-page PDFs or images. CAD-exported PDFs are read directly, free and "
        "without AI: sheets are sorted automatically, and room sizes, levels, schedules and wall lengths are taken "
        f"from the drawing itself. Only the {config.MAX_TOTAL_IMAGES} most useful pages are ever sent to the AI, for "
        "whatever is still missing."
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

    submitted = st.button("Continue to Drawing Analysis →", width="stretch", type="primary")

    if submitted:
        st.session_state["project_inputs"] = pi.model_copy(update=dict(
            project_name=project_name or "Untitled Project",
            client_name=client_name,
            location=location,
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
            if st.session_state.get("extracted_params") is not None and st.session_state["extracted_params"] == _base_params(pi):
                st.session_state["extracted_params"] = None
            # The drawing analysis text is unit-formatted and uses the plot
            # width as a hint - redo it for the new settings.
            st.session_state["package_facts"] = None
            st.session_state["uploaded_images"] = []
            clear_dmto_review()
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
def _load_images_from_upload(facts=None) -> tuple[list[Image.Image], list[str], str]:
    """Images to show/send to the AI, their labels, and a text hint.

    With a drawing package (PDFs), every page has already been sorted by
    drawing_processing.package_analyzer, so only the most useful pages
    (ground plan, section, other plans, elevation, then unrecognised/scanned
    pages) are rendered - at most config.MAX_TOTAL_IMAGES, the AI's
    per-request image limit. Plain image uploads fill any remaining slots.
    """
    uploaded_files = st.session_state.get("uploaded_files") or []
    images: list[Image.Image] = []
    labels: list[str] = []
    pdf_text_parts: list[str] = []
    selected = pages_for_ai(facts, config.MAX_TOTAL_IMAGES) if facts is not None else []

    for fi, f in enumerate(uploaded_files):
        name, file_bytes, view_tag = f["name"], f["bytes"], f["view_tag"]
        if name.lower().endswith(".pdf"):
            wanted = [pg for (i, pg) in selected if i == fi]
            if facts is None:
                wanted = list(range(config.MAX_PAGES_PER_FILE))
            if not wanted:
                continue
            for pg, img in zip(wanted, render_pages(file_bytes, wanted[: config.MAX_TOTAL_IMAGES])):
                if len(images) >= config.MAX_TOTAL_IMAGES:
                    break
                kind = (facts.page_kinds.get((fi, pg), "") if facts is not None else "").split(":")
                label = f"{kind[1].title() + ' floor ' if len(kind) > 1 and kind[1] else ''}{kind[0] if kind[0] and kind[0] != 'unknown' else view_tag} ({name} p{pg + 1})"
                images.append(clean_drawing_image(img))
                labels.append(label)
            result = process_pdf(file_bytes, dpi=72, max_pages=1)
            text = " ".join(result.combined_text.split())
            if text:
                pdf_text_parts.append(f"[{name}] {text}")
        elif len(images) < config.MAX_TOTAL_IMAGES:
            images.append(clean_drawing_image(Image.open(BytesIO(file_bytes))))
            labels.append(f"{view_tag} ({name})")

    hint_parts = []
    if facts is not None:
        from drawing_processing.package_analyzer import ai_hint_from_facts

        hint_parts.append(ai_hint_from_facts(facts))
    if pdf_text_parts:
        joined = " | ".join(pdf_text_parts)[: config.MAX_PDF_TEXT_HINT_CHARS]
        hint_parts.append("PDF text-layer content (exact text embedded in the drawing PDF): " + joined)
    return images, labels, "\n".join(h for h in hint_parts if h)


def _base_params(pi: ProjectInputs):
    """Starting parameters: the 5-10 marla plot template when a plot size is
    chosen, else the generic defaults of the unit system."""
    return plot_templates.build_template_params(pi) or default_building_params(
        wall_thickness_mm=pi.wall_thickness_mm, wall_material=pi.wall_material, unit_system=pi.unit_system
    )


def _finish_step_2(params, used_ai: bool) -> None:
    """Values read from the drawings override AI/template/default values;
    section levels also update the plinth/parapet assumptions."""
    pi = st.session_state["project_inputs"]
    facts = st.session_state.get("package_facts")
    filled: list[str] = []
    if facts is not None and facts.has_facts():
        params, asm_updates, filled = apply_package_facts(params, facts, pi)
        if asm_updates:
            st.session_state["assumptions"] = st.session_state["assumptions"].model_copy(update=asm_updates)
    st.session_state["drawing_filled"] = filled
    st.session_state["extracted_params"] = params
    st.session_state["used_ai"] = used_ai
    clear_dmto_review()  # rooms/openings/counts are re-seeded from this analysis in Step 3
    go_to_step(3)


def step_2():
    st.header("Step 2 \u00b7 Drawing Analysis")
    pi: ProjectInputs = st.session_state["project_inputs"]

    uploaded_files = st.session_state.get("uploaded_files") or []
    if not uploaded_files:
        if pi.plot_marla:
            st.info(
                f"No drawing uploaded - a typical {pi.plot_marla:g} marla house will be used as the starting point. "
                "You can review and edit every value in Step 3, or go back and upload the drawings."
            )
        else:
            st.info("No drawing was uploaded. You can go back to upload one, or skip straight to manual entry with standard defaults.")
        if st.button("\u2190 Back to Step 1"):
            go_to_step(1)
            st.rerun()
        if st.button("Skip AI \u2014 enter parameters manually", type="primary"):
            _finish_step_2(_base_params(pi), used_ai=False)
            st.rerun()
        return

    # ---- 1. Free analysis of the whole package (text + vectors, no AI) ----
    if st.session_state.get("package_facts") is None:
        with st.spinner("Reading the drawing set (sheet titles, room sizes, levels, schedules, wall geometry)..."):
            st.session_state["package_facts"] = analyze_package(uploaded_files, pi.plot_width_ft, pi.unit_system)
    facts = st.session_state["package_facts"]
    if st.session_state.get("dmto_scan") is None:
        with st.spinner("Reading plumbing labels, door schedule and tank details..."):
            try:
                st.session_state["dmto_scan"] = scan_pdf_bytes(uploaded_files)
            except Exception:
                st.session_state["dmto_scan"] = None

    if "uploaded_images" not in st.session_state or not st.session_state["uploaded_images"]:
        with st.spinner("Preparing the most useful pages for the AI..."):
            images, labels, pdf_text_hint = _load_images_from_upload(facts)
            st.session_state["uploaded_images"] = images
            st.session_state["uploaded_image_labels"] = labels
            st.session_state["pdf_text_hint"] = pdf_text_hint

    images = st.session_state["uploaded_images"]
    labels = st.session_state.get("uploaded_image_labels") or []

    st.markdown("##### \U0001f4d0 Drawing set analysis (free \u2014 no AI)")
    st.caption("CAD-exported PDFs are read directly: sheet types, room names and sizes, wall lengths by thickness, levels, "
               "foundation sections, schedules and service labels. The AI is optional.")
    if facts.has_facts():
        _, _, preview = apply_package_facts(_base_params(pi), facts, pi)
        st.success(
            f"Read {len(preview)} value(s) directly from the drawings: {', '.join(preview)}. "
            "These override AI and template values and are marked 'From drawings' in Step 3."
        )
    else:
        st.info(
            "No CAD text or vector data found (scanned drawings or photos). The AI will read the pages below; "
            + ("the plot template fills anything it misses." if pi.plot_marla else "standard defaults fill anything it misses.")
        )
    sheet_rows = [
        {"File": sh.file_name, "Page": sh.page_no, "Detected views": ", ".join(sh.views),
         "Read from drawing": " | ".join(sh.findings) if sh.findings else "-"}
        for sh in facts.sheets
    ]
    if sheet_rows:
        st.dataframe(pd.DataFrame(sheet_rows), width="stretch", hide_index=True)
    for c in facts.conflicts:
        st.warning(c)
    mto_views.render_scan_summary(st.session_state.get("dmto_scan"))

    if images:
        st.markdown(f"##### Pages the AI will read ({len(images)} of max {config.MAX_TOTAL_IMAGES})")
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
            "Install it with `pip install -r requirements-ocr.txt` to enable. Vector PDFs are read directly (above)."
        )

    if st.session_state.get("pdf_text_hint"):
        with st.expander("Hints passed to the AI (known values + PDF text)"):
            st.text(st.session_state["pdf_text_hint"])

    project_context = st.text_area(
        "Additional context for the AI (optional)",
        placeholder="e.g. 'This is a G+1 house, footings are isolated RCC pad footings, drawing is not to exact scale...'",
    )
    # Wall material/thickness are rarely labelled on a simple line drawing;
    # pass the Step 1 choice as a prior the AI uses unless the drawing
    # clearly shows otherwise (see ai/prompts.py rules 1-3).
    _wall_hint = (
        f"Unless the drawing clearly shows otherwise, assume wall material "
        f"'{pi.wall_material}' and wall thickness {pi.wall_thickness_mm}mm "
        "(both chosen in Step 1)."
    )
    plot_hint = (
        f"The house is on a {pi.plot_marla:g} marla plot ({pi.plot_marla * pi.marla_sqft:,.0f} sqft), {pi.plot_storeys} storey(s)."
        if pi.plot_marla else ""
    )
    project_context_for_ai = "\n".join(p for p in [project_context, plot_hint, _wall_hint] if p)

    c1, c2 = st.columns(2)
    with c1:
        skip_clicked = st.button("Continue with drawing data \u2192", type="primary", width="stretch",
                                 help="Recommended for CAD PDFs: everything read from the drawings is used; defaults fill the rest.")
    with c2:
        analyze_clicked = st.button("\U0001f9e0 Also ask the AI for missing values", width="stretch",
                                    help="Optional. Sends the most useful pages to the Groq vision model for values not read from the drawings.")

    if skip_clicked:
        _finish_step_2(_base_params(pi), used_ai=False)
        st.rerun()

    if analyze_clicked:
        if not st.session_state["groq_api_key"]:
            st.error(
                "No Groq API key is configured. Paste your own free key in the sidebar "
                "(console.groq.com/keys), or use 'Continue without AI' - values read from the drawings are still used."
            )
        elif not images:
            st.error("No pages to send to the AI - use 'Continue without AI'.")
        else:
            with st.spinner("Calling the vision model for the values not already read from the drawings... up to ~30s"):
                params, raw_text, errors = extract_building_params(
                    api_key=st.session_state["groq_api_key"],
                    images=images,
                    project_context=project_context_for_ai,
                    ocr_hint="\n".join(
                        h for h in [st.session_state.get("ocr_hint_text", ""), st.session_state.get("pdf_text_hint", "")] if h
                    ),
                    image_labels=labels,
                    wall_thickness_mm=pi.wall_thickness_mm,
                    wall_material=pi.wall_material,
                    unit_system=pi.unit_system,
                    fallback_params=_base_params(pi),
                )
            st.session_state["raw_ai_response"] = raw_text
            st.session_state["ai_errors"] = errors
            _finish_step_2(params, used_ai=True)
            st.rerun()

    if st.button("\u2190 Back to Step 1"):
        go_to_step(1)
        st.rerun()


# ---------------------------------------------------------------------------
# STEP 3 — Review drawing data
# ---------------------------------------------------------------------------
def _render_structure_inputs(params, unit_system):
    """Structural parameters (columns, beams, slab, footings) and fallbacks for
    scanned drawings. Rooms, walls, doors and services read from CAD PDFs take
    precedence in the material take-off."""
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
            help="isolated = RCC frame on pad footings; strip = load-bearing brick walls on stepped strip foundations "
            "(typical for many 5-10 marla houses). raft/combined are calculated as isolated pads.",
        )
        if params.footings.founding_depth_m is None:
            params.footings.founding_depth_m = founding_depth_estimate(params.footings, unit_system)
        if params.footings.footing_type != st.session_state.get("_last_footing_type", params.footings.footing_type) and "strip" in (
            params.footings.footing_type, st.session_state.get("_last_footing_type")
        ):
            # switching to/from strip: swap in that system's standard sizes
            det = rules.detailing(unit_system)
            low = lambda v, n: Estimate(value=v, confidence=ConfidenceLevel.LOW, source=Source.DEFAULT_ASSUMPTION, note=n)  # noqa: E731
            if params.footings.footing_type == "strip":
                params.footings.width_m = low(det["strip_width_m"], "Typical strip foundation width")
                params.footings.depth_m = low(det["strip_pcc_thickness_m"], "Typical PCC bed thickness")
                params.footings.founding_depth_m = low(det["strip_founding_depth_m"], "Typical strip foundation depth")
            else:
                params.footings.width_m = low(det["footing_thickness_m"] * 0 + params.footings.length_m.value, "Square footing")
                params.footings.depth_m = low(det["footing_thickness_m"], "Typical footing thickness")
                params.footings.founding_depth_m = low(det["founding_depth_m"], "Typical founding depth")
        st.session_state["_last_footing_type"] = params.footings.footing_type
        strip = params.footings.footing_type == "strip"
        if strip:
            st.caption(
                "Strip foundations (load-bearing walls): a PCC bed and stepped brick footing run under every "
                "ground-floor wall (length = total wall length). Width = PCC/trench width; thickness = PCC bed; "
                "Count and Length are not used."
            )
        c1, c2, c3, c4, c5 = st.columns(5)
        with c1:
            params.footings.count = render_estimate_input("Count", params.footings.count, "ftg_count", "nos", step=1.0)
        with c2:
            params.footings.length_m = render_estimate_input("Length", params.footings.length_m, "ftg_len", step=0.05, unit_system=unit_system, quantity_kind="length")
        with c3:
            params.footings.width_m = render_estimate_input("Strip (PCC) width" if strip else "Width", params.footings.width_m, "ftg_wid", step=0.05, unit_system=unit_system, quantity_kind="length")
        with c4:
            params.footings.depth_m = render_estimate_input(
                "PCC bed thickness" if strip else "Footing thickness", params.footings.depth_m, "ftg_dep", step=0.05, unit_system=unit_system, quantity_kind="thickness",
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

    with st.expander("Walls / Masonry (fallback when walls are not measured from CAD)", expanded=False):
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

    with st.expander("Fallback: doors & windows (used only when the drawings give no schedule)", expanded=False):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            params.openings.door_count_per_floor = render_estimate_input("Doors/floor", params.openings.door_count_per_floor, "door_count", "nos", step=1.0)
        with c2:
            params.openings.avg_door_area_sqm = render_estimate_input("Avg door area", params.openings.avg_door_area_sqm, "door_area", step=0.05, unit_system=unit_system, quantity_kind="area")
        with c3:
            params.openings.window_count_per_floor = render_estimate_input("Windows/floor", params.openings.window_count_per_floor, "win_count", "nos", step=1.0)
        with c4:
            params.openings.avg_window_area_sqm = render_estimate_input("Avg window area", params.openings.avg_window_area_sqm, "win_area", step=0.05, unit_system=unit_system, quantity_kind="area")

    with st.expander("Fallback: bathrooms & kitchens (used only when no room list is read)", expanded=False):
        c1, c2 = st.columns(2)
        with c1:
            params.services.bathroom_count_total = render_estimate_input("Bathrooms (whole building)", params.services.bathroom_count_total, "svc_baths", "nos", step=1.0)
        with c2:
            params.services.kitchen_count_total = render_estimate_input("Kitchens (whole building)", params.services.kitchen_count_total, "svc_kitchens", "nos", step=1.0)

    return params


def step_3():
    st.header("Step 3 \u00b7 Review Drawing Data")
    pi: ProjectInputs = st.session_state["project_inputs"]
    params = st.session_state["extracted_params"]
    unit_system = pi.unit_system

    if st.session_state.get("ai_errors"):
        for e in st.session_state["ai_errors"]:
            st.error(e)
    facts = st.session_state.get("package_facts")
    n_rooms = sum(len(f.rooms) for f in facts.floors.values()) if (facts is not None and facts.has_facts()) else 0
    if n_rooms:
        st.success(
            f"\u2705 Read from the drawings: {n_rooms} rooms with sizes, wall lengths by thickness, levels and "
            f"{len(st.session_state.get('drawing_filled') or [])} structural value(s). Check the tabs below - values marked "
            "\u26aa are defaults, \U0001f7e2 come from the drawings."
        )
    else:
        st.info("No CAD room data was read (scanned drawings or no upload). Rooms and counts below are generated from the "
                "plot template / Step 3 values - please correct them.")
    if (st.session_state.get("used_ai") or st.session_state.get("drawing_filled") or pi.plot_marla) and params.extraction_warnings:
        with st.expander("\u26a0\ufe0f Extraction warnings", expanded=False):
            for w in params.extraction_warnings:
                st.warning(w)
    if params.overall_notes:
        st.info(f"**AI notes:** {params.overall_notes}")
    st.caption(mto_views.options_summary(st.session_state["dmto_options"]) + " (change in Step 1)")

    mto_views.seed_review_rows(pi, params)
    t_rooms, t_open, t_counts, t_struct, t_coef = st.tabs(
        ["\U0001f3e0 Rooms", "\U0001f6aa Doors & windows", "\U0001f522 Counts & dimensions", "\U0001f3d7\ufe0f Structure",
         "\U0001f4da Coefficients"])
    with t_struct:
        if units.is_fps(unit_system):
            st.caption("FPS units: lengths in feet, member sizes in inches, areas in sqft.")
        legend = " ".join(confidence_badge(c) for c in [ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM, ConfidenceLevel.LOW])
        st.markdown(f"Columns, beams, slab and footings used for concrete, steel and formwork. Confidence: {legend}",
                    unsafe_allow_html=True)
        params = _render_structure_inputs(params, unit_system)
        st.session_state["extracted_params"] = params
    with t_rooms:
        room_rows = mto_views.render_rooms_editor()
    with t_open:
        opening_rows = mto_views.render_openings_editor()
    with t_counts:
        mto_views.render_counts_editor(pi, params, room_rows, opening_rows)
    with t_coef:
        mto_views.render_coefficients()

    errors, warnings = validate_params(params, pi, st.session_state["assumptions"])
    if errors or warnings:
        with st.expander(f"Input checks ({len(errors)} error(s), {len(warnings)} warning(s))", expanded=bool(errors)):
            for e in errors:
                st.error(e)
            for w in warnings:
                st.warning(w)

    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        if st.button("\u2190 Back to Step 2"):
            mto_views.save_review(room_rows, opening_rows)
            go_to_step(2)
            st.rerun()
    with c2:
        if st.button("\U0001f504 Apply table edits", help="Saves the Rooms / Doors & windows tables and refreshes the counts derived from them."):
            mto_views.save_review(room_rows, opening_rows)
            st.rerun()
    with c3:
        if st.button("Calculate Material Take-Off \u2192", type="primary", width="stretch", disabled=bool(errors)):
            mto_views.save_review(room_rows, opening_rows)
            with st.spinner("Calculating every material from the drawing data..."):
                mto_views.run_takeoff(pi, params)
            go_to_step(4)
            st.rerun()


# ---------------------------------------------------------------------------
# STEP 4 — Material take-off
# ---------------------------------------------------------------------------
def step_4():
    st.header("Step 4 \u00b7 Material Take-Off")
    pi: ProjectInputs = st.session_state["project_inputs"]
    res = st.session_state.get("dmto_result")
    if res is None:
        if st.session_state.get("extracted_params") is None:
            st.info("Complete Steps 1-3 first.")
            if st.button("\u2190 Back to Step 1"):
                go_to_step(1)
                st.rerun()
            return
        res = mto_views.run_takeoff(pi, st.session_state["extracted_params"])
    st.caption(mto_views.options_summary(st.session_state["dmto_options"]) +
               " \u00b7 All quantities in Pakistani FPS units (cft, sft, rft, bags, kg, Nos). Costs are not included in this version.")
    mto_views.render_takeoff(res)

    c1, c2 = st.columns(2)
    with c1:
        if st.button("\u2190 Back to Step 3 (review data)"):
            go_to_step(3)
            st.rerun()
    with c2:
        if st.button("Continue to Export \u2192", type="primary", width="stretch"):
            go_to_step(5)
            st.rerun()


# ---------------------------------------------------------------------------
# STEP 5 — Export
# ---------------------------------------------------------------------------
def step_5():
    st.header("Step 5 \u00b7 Export")
    pi: ProjectInputs = st.session_state["project_inputs"]
    res = st.session_state.get("dmto_result")
    if res is None:
        st.info("Calculate the material take-off first (Step 3).")
        if st.button("\u2190 Back to Step 3"):
            go_to_step(3)
            st.rerun()
        return
    counts = res.status_counts()
    st.markdown(
        f"**{pi.project_name}** \u2014 {len(res.materials)} materials listed, "
        f"{sum(v for k, v in counts.items() if k in ('Calculated', 'Calculated (assumed inputs)', 'Provisional'))} quantified, "
        f"{counts.get('Needs input', 0)} need input."
    )
    name = (pi.project_name or "Project").replace(" ", "_")
    e1, e2 = st.columns(2)
    with e1:
        st.download_button(
            "\U0001f4e6 Download Material Take-Off (Excel)", data=mto_views.export_bytes(res),
            file_name=f"{name}_Material_TakeOff.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", width="stretch", type="primary",
        )
    with e2:
        st.download_button("\U0001f4c4 Download material schedule (CSV)", data=mto_views.schedule_csv(res),
                           file_name=f"{name}_Material_Schedule.csv", mime="text/csv", width="stretch")
    st.markdown(
        "The Excel workbook contains: **Summary** (key quantities, lines by status), **Material_Schedule** (every material "
        "with net qty, wastage, qty incl. wastage, purchase units, status, confidence, stage and calculation), "
        "**Procurement_by_Stage**, **BOQ_Work_Items** (measured quantities), **Material_Breakdown** (work item \u00d7 "
        "coefficient for every material), **Project_Inputs** (every input with its source), **Rooms**, **Openings**, "
        "**Assumptions_Gaps** and **Benchmarks**."
    )
    st.caption("Costs are intentionally excluded - pricing will be added as a separate step. "
               f"\u26a0\ufe0f {config.DISCLAIMER_TEXT_SHORT}")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("\u2190 Back to Step 4 (Material Take-Off)"):
            go_to_step(4)
            st.rerun()
    with c2:
        if st.button("\U0001f504 Start a new project", width="stretch"):
            reset_project()
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
