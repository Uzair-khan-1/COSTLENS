"""
CostLens visual theme: CSS injection + small branded UI helpers layered on
top of the native Streamlit theme (.streamlit/config.toml). Kept in its own
module so app.py stays focused on app flow, not styling.

Everything here is additive and defensive:
- Selectors target stable `data-testid` attributes, not Streamlit's
  auto-generated/versioned class names, so a Streamlit upgrade that
  changes internal class names won't break this.
- If a selector ever stops matching in some version, the app just falls
  back to plain Streamlit styling - nothing here is load-bearing for
  functionality, only for visual polish.
- No JS, no external component libraries - pure CSS injected via
  st.markdown(unsafe_allow_html=True), which is the one supported
  "custom styling" escape hatch within Streamlit's platform limits.
"""
from __future__ import annotations

import base64

import streamlit as st

import config

_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"] {{
    font-family: 'Outfit', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}}

/* ---------------------------------------------------------------- *
 * App background
 * ---------------------------------------------------------------- */
[data-testid="stAppViewContainer"], [data-testid="stMain"] {{
    background: radial-gradient(1200px 500px at 70% -10%, #1B3157 0%, {config.BRAND_BG} 55%) !important;
}}

/* ---------------------------------------------------------------- *
 * Hero header banner (top of every step)
 * ---------------------------------------------------------------- */
.cl-hero {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 10px 24px;
    padding: 12px 24px;
    margin: -1rem -1rem 1.5rem -1rem;
    background: {config.CARD_BG};
    border-radius: 0 0 18px 18px;
    border-bottom: 4px solid transparent;
    border-image: linear-gradient(90deg, {config.BRAND_NAVY}, {config.BRAND_TEAL} 55%, #14B8A6, {config.BRAND_GOLD}) 1;
    box-shadow: 0 8px 28px rgba(0, 0, 0, 0.35);
}}
.cl-hero img {{ height: 74px; display: block; }}
.cl-hero-text p {{
    color: {config.TEXT_MUTED} !important;
    font-size: 1.02rem !important;
    max-width: 360px;
    text-align: right;
    margin: 0 !important;
    font-weight: 500;
    line-height: 1.35;
}}
@media (max-width: 640px) {{ .cl-hero img {{ height: 56px; }} .cl-hero-text {{ display: none; }} }}

/* ---------------------------------------------------------------- *
 * Headings
 * ---------------------------------------------------------------- */
h1, h2, h3 {{ font-weight: 700; }}

/* ---------------------------------------------------------------- *
 * Buttons
 * ---------------------------------------------------------------- */
.stButton button,
.stDownloadButton button,
[data-testid="stFormSubmitButton"] button {{
    border-radius: 10px;
    font-weight: 600;
    border: 1px solid rgba(255, 255, 255, 0.14);
    transition: transform 0.06s ease-in-out, box-shadow 0.15s ease-in-out;
}}
.stButton button:hover,
.stDownloadButton button:hover,
[data-testid="stFormSubmitButton"] button:hover {{
    transform: translateY(-1px);
    box-shadow: 0 4px 16px rgba(59, 155, 232, 0.35);
    border-color: {config.BRAND_TEAL};
}}
.stButton button[kind="primary"],
[data-testid="stFormSubmitButton"] button[kind="primary"] {{
    background: linear-gradient(120deg, {config.BRAND_TEAL} 0%, #14B8A6 100%);
    border: none;
}}

/* ---------------------------------------------------------------- *
 * Metric cards (Step 5: Subtotal / Contingency / Grand Total)
 * ---------------------------------------------------------------- */
[data-testid="stMetric"] {{
    background: rgba(127, 127, 127, 0.06);  /* neutral tint: readable in light and dark themes */
    border: 1px solid {config.CARD_BORDER};
    border-left: 4px solid {config.BRAND_TEAL};
    border-radius: 12px;
    padding: 14px 18px;
    box-shadow: 0 2px 10px rgba(11, 30, 61, 0.05);
}}
[data-testid="stMetricLabel"] {{ font-weight: 600; }}


/* ---------------------------------------------------------------- *
 * Expanders (Steps 3 / 4 / 5 rely on these heavily)
 * ---------------------------------------------------------------- */
[data-testid="stExpander"] {{
    border: 1px solid {config.CARD_BORDER};
    border-radius: 12px;
    background: rgba(23, 40, 67, 0.55);
}}
[data-testid="stVerticalBlockBorderWrapper"] {{ border-color: {config.CARD_BORDER} !important; }}

/* ---------------------------------------------------------------- *
 * Sidebar logo (st.logo) - Streamlit renders this quite small by
 * default (~24-32px tall) regardless of the source image's actual
 * resolution. Force it larger here so it reads clearly; `size="large"`
 * is passed in app.py too for versions that support that parameter,
 * but this CSS is what actually guarantees the size across versions.
 * ---------------------------------------------------------------- */
[data-testid="stSidebarHeader"] {{
    padding-top: 1rem !important;
    padding-bottom: 0.75rem !important;
    align-items: center !important;
}}
[data-testid="stSidebarHeader"] img,
[data-testid="stLogo"],
[data-testid="stLogo"] img,
.stLogo,
.stLogo img {{
    height: 3.2rem !important;
    max-height: none !important;
    width: auto !important;
}}

/* ---------------------------------------------------------------- *
 * Sidebar
 * ---------------------------------------------------------------- */
[data-testid="stSidebar"] {{
    background: linear-gradient(180deg, #13233F 0%, #0B1528 100%);
    border-right: 1px solid {config.CARD_BORDER};
}}
[data-testid="stSidebar"] * {{ color: #E8EEF5 !important; }}
[data-testid="stSidebar"] hr {{ border-color: rgba(255, 255, 255, 0.15); }}
[data-testid="stSidebar"] .stButton button {{
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.18);
    color: #FFFFFF !important;
}}
[data-testid="stSidebar"] .stButton button:hover {{
    background: {config.BRAND_TEAL};
    border-color: {config.BRAND_TEAL};
}}

/* ---------------------------------------------------------------- *
 * Sidebar step navigation (clickable step buttons)
 * ---------------------------------------------------------------- */
.st-key-cl_step_nav .stButton button {{
    width: 100%;
    display: flex !important;
    justify-content: flex-start !important;
    text-align: left !important;
    padding: 0.5rem 0.9rem !important;
    margin-bottom: 3px;
    border-radius: 10px;
}}
.st-key-cl_step_nav .stButton button * {{
    justify-content: flex-start !important;
    text-align: left !important;
    margin-left: 0 !important;
}}
.st-key-cl_step_nav .stButton button > div,
.st-key-cl_step_nav .stButton button [data-testid="stMarkdownContainer"] {{ width: 100% !important; display: flex !important; }}
.st-key-cl_step_nav [data-testid="stTooltipHoverTarget"] {{ justify-content: flex-start !important; }}
.st-key-cl_step_nav .stButton button p {{ font-weight: 600; white-space: nowrap; }}
.st-key-cl_step_nav .stButton button[kind="primary"] {{
    background: {config.BRAND_GOLD} !important;
    border: none !important;
}}
.st-key-cl_step_nav .stButton button[kind="primary"] p {{ color: {config.BRAND_NAVY} !important; }}
.st-key-cl_step_nav .stButton button:disabled {{ opacity: 0.55; }}
[data-testid="stMain"], section.main {{ overflow-anchor: none; }}
/* light buttons inside the dark sidebar (download / file uploader) need dark text */
[data-testid="stSidebar"] .stDownloadButton button p,
[data-testid="stSidebar"] [data-testid="stFileUploader"] button,
[data-testid="stSidebar"] [data-testid="stFileUploader"] button p,
[data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] span,
[data-testid="stSidebar"] [data-testid="stFileUploaderDropzone"] small {{ color: {config.BRAND_NAVY} !important; }}
.st-key-cl_scroll_top {{ height: 0 !important; min-height: 0 !important; overflow: hidden; margin: 0 !important; padding: 0 !important; }}

/* ---------------------------------------------------------------- *
 * Sidebar step tracker (replaces the plain emoji checklist)
 * ---------------------------------------------------------------- */
.cl-step {{
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 7px 10px;
    border-radius: 8px;
    margin-bottom: 4px;
    font-size: 0.88rem;
}}
.cl-step-done {{ opacity: 0.6; }}
.cl-step-current {{
    background: rgba(45, 212, 191, 0.16);
    border: 1px solid rgba(45, 212, 191, 0.4);
    font-weight: 700 !important;
}}
.cl-step-upcoming {{ opacity: 0.4; }}
.cl-step-dot {{
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 20px;
    height: 20px;
    border-radius: 50%;
    font-size: 0.72rem;
    font-weight: 700;
    flex-shrink: 0;
}}
.cl-step-done .cl-step-dot {{ background: {config.BRAND_TEAL}; color: #FFFFFF; }}
.cl-step-current .cl-step-dot {{ background: {config.BRAND_GOLD}; color: {config.BRAND_NAVY}; }}
.cl-step-upcoming .cl-step-dot {{ background: rgba(255, 255, 255, 0.15); color: #E8EEF5; }}
</style>
"""


def inject_theme() -> None:
    """Injects the CostLens CSS. Safe to call on every rerun - it's purely
    additive and idempotent (re-injecting the same <style> block has no
    side effects)."""
    st.markdown(_CSS, unsafe_allow_html=True)


def render_hero() -> None:
    """Branded header: the full-colour CostLens logo on a light card with the logo's blue-to-teal accent line."""
    logo_html = f"<h1 style='margin:0'>{config.APP_NAME}</h1>"
    try:
        with open(config.LOGO_HORIZONTAL_ON_DARK_PATH, "rb") as fh:
            b64 = base64.b64encode(fh.read()).decode("ascii")
        logo_html = f'<img src="data:image/png;base64,{b64}" alt="{config.APP_NAME} - materials, cost, schedule" />'
    except OSError:
        pass
    st.markdown(
        f"""
        <div class="cl-hero">
            {logo_html}
            <div class="cl-hero-text"><p>Your house plan in &rarr;<br><b style="color:#FFFFFF">what to buy, what it costs, when it&rsquo;s ready.</b></p></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar_steps(step_labels: list[str], current_step: int) -> None:
    """Branded HTML/CSS step tracker for the sidebar. Read-only by design -
    the wizard advances via its own Continue/Back buttons, not by clicking
    a step here."""
    rows = []
    for i, label in enumerate(step_labels, start=1):
        if current_step > i:
            state, dot = "cl-step-done", "✓"
        elif current_step == i:
            state, dot = "cl-step-current", str(i)
        else:
            state, dot = "cl-step-upcoming", str(i)
        rows.append(f'<div class="cl-step {state}"><span class="cl-step-dot">{dot}</span><span>{label}</span></div>')
    st.markdown("\n".join(rows), unsafe_allow_html=True)


def render_step_nav(step_labels: list[str], current_step: int, max_step: int, available=None):
    """Clickable step list for the sidebar. Steps up to the furthest one reached
    (and allowed by `available(step)`) are buttons; returns the clicked step or None."""
    clicked = None
    with st.container(key="cl_step_nav"):
        for i, label in enumerate(step_labels, start=1):
            done = i < current_step or (i <= max_step and i != current_step)
            icon = "\u25B6" if i == current_step else ("\u2713" if done else "\u25CB")
            enabled = i <= max_step and (available is None or available(i))
            if st.button(f"{icon}  {label}", key=f"nav_step_{i}", width="stretch",
                         type="primary" if i == current_step else "secondary",
                         disabled=not enabled and i != current_step,
                         help=None if (enabled or i == current_step) else "Complete the previous steps first"):
                if i != current_step:
                    clicked = i
    return clicked


def scroll_to_top() -> None:
    """Scroll the main page to the top (used when the wizard moves to another step).
    Streamlit keeps the scroll position between reruns, so without this a new step
    would open where the previous one was scrolled to."""
    html = """
        <script>
        (function () {
          const doc = window.parent.document;
          function up() {
            const sel = ['[data-testid="stMain"]', '[data-testid="stAppViewContainer"]', 'section.main',
                         '[data-testid="stAppScrollToBottomContainer"]', '.main'];
            sel.forEach(function (s) {
              doc.querySelectorAll(s).forEach(function (el) { try { el.scrollTop = 0; } catch (e) {} });
            });
            try { window.parent.scrollTo(0, 0); } catch (e) {}
            try { doc.documentElement.scrollTop = 0; doc.body.scrollTop = 0; } catch (e) {}
          }
          // Streamlit keeps rendering (tables, tabs, charts) after this runs, and browser scroll
          // anchoring can push the view down again - keep pinning to the top for ~2.5 s unless
          // the user starts scrolling themselves.
          let userScrolled = false;
          ['wheel', 'touchstart', 'keydown', 'mousedown'].forEach(function (ev) {
            doc.addEventListener(ev, function () { userScrolled = true; }, { once: true, passive: true });
          });
          up();
          [50, 150, 300, 500, 800, 1200, 1700, 2500].forEach(function (t) {
            setTimeout(function () { if (!userScrolled) up(); }, t);
          });
        })();
        </script>
        """
    # A unique marker forces the browser to reload the iframe (and re-run the script)
    # even when the previous step left an identical iframe at the same position.
    import time as _time

    html = f"<!-- scroll {_time.time_ns()} -->" + html
    with st.container(key="cl_scroll_top"):
        if hasattr(st, "iframe"):
            st.iframe(html, height=1)
        else:  # older Streamlit
            import streamlit.components.v1 as components

            components.html(html, height=0)
