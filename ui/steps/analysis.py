"""Step 2 (drawing route) - CAD text/vector reading, label scan, optional AI."""
from __future__ import annotations

import hashlib

from io import BytesIO

import pandas as pd
import streamlit as st
from PIL import Image

import config
from ai.llm import keys_from_mapping
from ai.extraction import default_building_params, extract_building_params
from detailed_mto import scan_pdf_bytes
from drawing_processing.image_processor import clean_drawing_image, estimate_is_drawing_like
from drawing_processing.ocr_engine import build_ocr_hint_text, ocr_available
from drawing_processing.package_analyzer import analyze_package, apply_package_facts, pages_for_ai, render_pages
from drawing_processing.pdf_processor import process_pdf
from engineering import plot_templates
from models.schemas import ProjectInputs
from ui import mto_views
from ui.state import clear_dmto_review, clear_drawing_derived_state, go_to_step


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


@st.cache_resource(show_spinner=False)
def _analysis_cache() -> dict:
    """Process-wide cache of drawing analyses keyed by file content (re-uploading the same set is instant)."""
    return {}


def _analyze_cached(files: list, plot_width_ft, unit_system: str):
    key = (tuple((f["name"], hashlib.sha256(f["bytes"]).hexdigest(), f.get("view_tag", "")) for f in files),
           plot_width_ft, unit_system)
    cache = _analysis_cache()
    if key in cache:
        return cache[key]
    bar = st.progress(0.0, text="Reading the drawing set...")
    try:
        facts = analyze_package(files, plot_width_ft, unit_system,
                                progress=lambda frac, msg: bar.progress(frac * 0.9, text=msg))
        bar.progress(0.95, text="Reading plumbing labels, door schedule and tank details...")
        try:
            scan = scan_pdf_bytes(files)
        except Exception:  # noqa: BLE001 - the label scan is optional
            scan = None
    finally:
        bar.empty()
    if len(cache) >= 8:  # keep memory bounded on small hosts
        cache.pop(next(iter(cache)))
    cache[key] = (facts, scan)
    return facts, scan


def base_params(pi: ProjectInputs):
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


def _render_found_summary(facts, scan) -> None:
    """'What we found in your drawings' in plain words with big number cards."""
    from ui.illustrations import stat_cards_html
    floors = [f for k, f in facts.floors.items() if k != "roof"]
    rooms = [r for f in floors for r in f.rooms]
    area = sum(f.covered_sqft or 0 for f in floors)
    try:  # the same covered area Step 3 will show (the builder resolves area-statement vs measured footprint)
        from detailed_mto import build_project
        from ui import mto_views
        pi = st.session_state["project_inputs"]
        prm, _a, _f = apply_package_facts(base_params(pi), facts, pi)
        proj = build_project(pi, prm, mto_views.kb(), facts=facts, scan=st.session_state.get("dmto_scan"))
        area = sum(f.covered_sft for f in proj.floors) or area
    except Exception:  # noqa: BLE001 - fall back to the drawing figures
        pass
    from detailed_mto.builder import classify_room
    from knowledge import load_knowledge_base
    kb = load_knowledge_base()
    kinds = {"bedroom": 0, "bathroom": 0, "kitchen": 0}
    for r in rooms:
        t = classify_room(r[0], r[3], kb)
        key = {"Bedroom": "bedroom", "Bathroom": "bathroom", "Kitchen": "kitchen"}.get(t)
        if key:
            kinds[key] += 1
    doors = facts.openings.get("doors_total", (None,))[0]
    wins = sum(v[0] for k, v in facts.openings.items() if k.startswith("windows_"))
    cards = [("\U0001f3e0", "Floors", f"{len(floors)}" + (" + mumty" if "roof" in facts.floors else ""), "read from plans"),
             ("\U0001f4d0", "Covered area", f"{area:,.0f} sq ft", "all floors"),
             ("\U0001f6cf\ufe0f", "Rooms with sizes", f"{len(rooms)}", f"{kinds.get('bedroom', 0)} bedrooms"),
             ("\U0001f6bf", "Bathrooms", f"{kinds.get('bathroom', 0)}", "from room labels"),
             ("\U0001f373", "Kitchens", f"{kinds.get('kitchen', 0)}", "")]
    if doors:
        cards.append(("\U0001f6aa", "Doors", f"{doors:.0f}", "door schedule"))
    if wins:
        cards.append(("\U0001fa9f", "Windows", f"{wins:.0f}", "sizes to confirm"))
    if scan is not None and scan.get("FT"):
        cards.append(("\U0001f6b0", "Floor traps", f"{scan.get('FT')}", "plumbing sheets"))
    st.markdown("<div style='font-size:20px;font-weight:700;color:inherit;margin-top:6px'>\u2705 What we found in your drawings</div>",
                unsafe_allow_html=True)
    st.markdown(stat_cards_html(cards), unsafe_allow_html=True)
    st.caption("You can correct anything in the next step. Sizes that are not on the drawings (e.g. window widths) "
               "start from common standards and are marked for checking.")


def _switch_to_questions() -> None:
    """Drawings can't be read (or none uploaded): continue with the guided questions - never a 'typical house'."""
    clear_drawing_derived_state()
    st.session_state["input_mode"] = "sketch"
    st.session_state["ui_choice"] = "sketch"
    st.session_state["uploaded_files"] = []
    st.session_state["uploaded_signature"] = None
    st.session_state["brief"] = None
    go_to_step(2)
    st.rerun()


def _render_plot_check(facts, pi) -> bool:
    """Plot size is read from the drawings (site plan / area statement). If it isn't there, the owner must enter it."""
    from ui.guide import section
    w = facts.plot.get("plot_width_ft")
    d = facts.plot.get("plot_depth_ft")
    msq = pi.marla_sqft or 272.25
    if w and d:
        st.session_state.pop("plot_dims_user", None)
        area = w[0] * d[0]
        st.success(f"\U0001f4d0 **Plot size read from your drawings:** {w[0]:g} ft x {d[0]:g} ft = {area:,.0f} sq ft "
                   f"\u2248 **{area / msq:.1f} marla** (1 marla = {msq:g} sq ft in {pi.location or 'your city'}). "
                   f"Source: {w[1]}.")
        return True
    section("\U0001f4d0 Plot size", "We could not find the plot dimensions on the drawings. Please enter them (in feet).")
    prev = st.session_state.get("plot_dims_user") or (None, None)
    c1, c2, c3 = st.columns([1, 1, 2])
    pw = c1.number_input("Plot width at the road (ft)", min_value=10.0, max_value=300.0, value=prev[0], step=0.5,
                         placeholder="e.g. 30", key="plot_w_in")
    pd_ = c2.number_input("Plot depth (ft)", min_value=10.0, max_value=400.0, value=prev[1], step=0.5, placeholder="e.g. 45",
                          key="plot_d_in")
    if pw and pd_:
        st.session_state["plot_dims_user"] = (float(pw), float(pd_))
        c3.markdown(f"<div style='padding-top:30px'>= {pw * pd_:,.0f} sq ft \u2248 <b>{pw * pd_ / msq:.1f} marla</b></div>",
                    unsafe_allow_html=True)
        return True
    c3.markdown("<div style='padding-top:30px;color:#C2410C'>Both values are needed to continue.</div>", unsafe_allow_html=True)
    return False


def step_2():
    from ui.guide import step_header
    step_header(2)
    pi: ProjectInputs = st.session_state["project_inputs"]

    uploaded_files = st.session_state.get("uploaded_files") or []
    if not uploaded_files:
        st.info("No drawings were uploaded. Go back and upload them - or answer a few questions about your house instead "
                "(we never make up a 'typical house').")
        c1, c2 = st.columns(2)
        if c1.button("\u2190 Back to Step 1"):
            go_to_step(1)
            st.rerun()
        if c2.button("\u270f\ufe0f Answer questions about my house \u2192", type="primary"):
            _switch_to_questions()
        return

    # ---- 1. Free analysis of the whole package (text + vectors, no AI) ----
    if st.session_state.get("package_facts") is None or st.session_state.get("dmto_scan") is None:
        facts, scan = _analyze_cached(uploaded_files, pi.plot_width_ft, pi.unit_system)
        st.session_state["package_facts"] = facts
        st.session_state["dmto_scan"] = scan
    facts = st.session_state["package_facts"]

    if "uploaded_images" not in st.session_state or not st.session_state["uploaded_images"]:
        with st.spinner("Preparing the most useful pages for the AI..."):
            images, labels, pdf_text_hint = _load_images_from_upload(facts)
            st.session_state["uploaded_images"] = images
            st.session_state["uploaded_image_labels"] = labels
            st.session_state["pdf_text_hint"] = pdf_text_hint

    images = st.session_state["uploaded_images"]
    labels = st.session_state.get("uploaded_image_labels") or []

    # ---- friendly summary of what was read -------------------------------------
    if facts.has_facts():
        _render_found_summary(facts, st.session_state.get("dmto_scan"))
    else:
        mto_views.render_drawing_mode_banner("scanned")

    with st.expander("\U0001f50e Sheet-by-sheet details (for engineers)"):
        if facts.has_facts():
            _, _, preview = apply_package_facts(base_params(pi), facts, pi)
            st.caption(f"Read {len(preview)} value(s) directly from the drawings: {', '.join(preview)}.")
        sheet_rows = [
            {"File": sh.file_name, "Page": sh.page_no, "Detected views": ", ".join(sh.views),
             "Read from drawing": " | ".join(sh.findings) if sh.findings else "-"}
            for sh in facts.sheets
        ]
        if sheet_rows:
            st.dataframe(pd.DataFrame(sheet_rows), width="stretch", hide_index=True)
        mto_views.render_scan_summary(st.session_state.get("dmto_scan"))
        if images:
            st.markdown(f"**Pages the AI would read** ({len(images)} of max {config.MAX_TOTAL_IMAGES})")
            cols = st.columns(min(len(images), 4) or 1)
            for i, img in enumerate(images):
                with cols[i % len(cols)]:
                    st.image(img, caption=labels[i] if i < len(labels) else f"Page {i+1}", width="stretch")
                    if not estimate_is_drawing_like(img):
                        st.caption("\u26a0\ufe0f This doesn't look like a typical line drawing \u2014 results may be unreliable.")
        if ocr_available():
            if not st.session_state.get("ocr_hint_text"):
                with st.spinner("Running OCR..."):
                    hints = [build_ocr_hint_text(img) for img in images]
                    st.session_state["ocr_hint_text"] = "\n".join(h for h in hints if h)
            st.text(st.session_state["ocr_hint_text"] or "No OCR text detected.")
        if st.session_state.get("pdf_text_hint"):
            st.markdown("**Hints passed to the AI**")
            st.text(st.session_state["pdf_text_hint"])
    if facts.conflicts:
        with st.expander(f"\U0001f4dd Notes from reading your drawings ({len(facts.conflicts)}) - where sheets disagree, "
                         "we used the safer value"):
            for c in facts.conflicts:
                st.markdown("\u2022 " + c)
    with st.expander("\U0001f9e0 Optional: ask the AI to read the drawings too"):
        project_context = st.text_area(
            "Anything the AI should know? (optional)",
            placeholder="e.g. 'This is a G+1 house, footings are isolated RCC pad footings, drawing is not to exact scale...'",
        )
        st.caption("Needs a free AI key in the sidebar. Press 'Also ask the AI to fill gaps' below.")
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

    _readable = facts.has_facts() and any(f.rooms for k, f in facts.floors.items() if k != "roof")
    plot_ok = _render_plot_check(facts, pi) if _readable else False
    c1, c2 = st.columns(2)
    with c1:
        if _readable:
            skip_clicked = st.button("\u2705 Looks right - continue \u2192", type="primary", width="stretch", disabled=not plot_ok,
                                     help="Everything read from the drawings is used; in the next step you choose what you want "
                                          "in the house and we ask only for what is missing.")
        else:
            st.warning("We could not read rooms and sizes from these drawings (scanned images or photos). "
                       "Ask the AI to read them, or answer a few questions about your house instead.")
            if st.button("\u270f\ufe0f Answer questions about my house \u2192", type="primary", width="stretch"):
                _switch_to_questions()
            skip_clicked = False
    with c2:
        analyze_clicked = st.button("\U0001f9e0 Also ask the AI to fill gaps (optional)", width="stretch",
                                    help="Optional. Sends the most useful pages (automatically resized to fit the free AI limits) to the vision model "
                                         "for values not read from the drawings.")

    if skip_clicked:
        _finish_step_2(base_params(pi), used_ai=False)
        st.rerun()

    if analyze_clicked:
        if not keys_from_mapping(st.session_state).any():
            st.error(
                "No AI key is configured. Paste a free Groq key (console.groq.com/keys) or a Gemini key in the sidebar, "
                "or continue with the drawing data - values read from the drawings are still used."
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
                    fallback_params=base_params(pi),
                    keys=keys_from_mapping(st.session_state),
                )
            st.session_state["raw_ai_response"] = raw_text
            st.session_state["ai_errors"] = errors
            _finish_step_2(params, used_ai=True)
            st.rerun()

    if st.button("\u2190 Back to Step 1"):
        go_to_step(1)
        st.rerun()
