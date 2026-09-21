"""
Reusable Streamlit widgets shared across app.py steps.
"""
from __future__ import annotations

import math
from typing import Dict, Optional

import pandas as pd
import streamlit as st

from engineering import rules
from models.schemas import ConfidenceLevel, EngineeringAssumptions, Estimate, MaterialRate, Source, WastageFactors
from utils import units

CONFIDENCE_COLORS = {
    ConfidenceLevel.HIGH: "#1a7f37",
    ConfidenceLevel.MEDIUM: "#9a6700",
    ConfidenceLevel.LOW: "#c0392b",
}
CONFIDENCE_BG = {
    ConfidenceLevel.HIGH: "#dafbe1",
    ConfidenceLevel.MEDIUM: "#fff8c5",
    ConfidenceLevel.LOW: "#ffebe9",
}


def confidence_badge(confidence: ConfidenceLevel) -> str:
    color = CONFIDENCE_COLORS.get(confidence, "#555")
    bg = CONFIDENCE_BG.get(confidence, "#eee")
    return (
        f'<span style="background-color:{bg};color:{color};padding:2px 8px;'
        f'border-radius:10px;font-size:0.75rem;font-weight:600;">{confidence.value}</span>'
    )


def render_estimate_input(
    label: str,
    estimate: Estimate,
    key: str,
    unit: str = "",
    step: float = 0.01,
    min_value: float = 0.0,
    help_text: str | None = None,
    unit_system: str = units.SI,
    quantity_kind: Optional[str] = None,
) -> Estimate:
    """Render one editable numeric field with its confidence badge + note,
    and return a (possibly updated) Estimate reflecting the user's edit.

    `estimate.value` is ALWAYS canonical SI (metres / sqm) - this is the
    single source of truth consumed by engineering/calculations.py.
    `quantity_kind` ("length" | "thickness" | "area" | None) tells this
    widget how to convert that SI value to/from the user's chosen
    `unit_system` for display only; pass None (the default) for
    unit-less fields such as counts, where `unit` is shown verbatim
    (e.g. "nos", "floors").
    """
    if quantity_kind is not None:
        display_value = units.to_display(estimate.value, quantity_kind, unit_system)
        display_step = units.to_display(step, quantity_kind, unit_system) or step
        display_min = units.to_display(min_value, quantity_kind, unit_system)
        display_unit = units.dimension_unit_label(quantity_kind, unit_system)
    else:
        display_value = estimate.value
        display_step = step
        display_min = min_value
        display_unit = unit

    col1, col2 = st.columns([3, 1])
    with col1:
        new_display_value = st.number_input(
            f"{label} ({display_unit})" if display_unit else label,
            value=float(display_value),
            step=float(display_step),
            min_value=float(display_min),
            key=key,
            help=help_text or estimate.note,
        )
    with col2:
        st.markdown("<div style='margin-top:1.8rem'></div>" + confidence_badge(estimate.confidence), unsafe_allow_html=True)

    if estimate.note:
        st.caption(f"\u2139\ufe0f {estimate.note}")

    new_value = units.to_si(new_display_value, quantity_kind, unit_system) if quantity_kind is not None else new_display_value

    # Use a tolerant comparison (not `!=`) because round-tripping through a
    # display unit conversion (e.g. metres -> feet -> metres) can leave a
    # sub-nanometre floating-point residue on an otherwise-unchanged field;
    # an exact-equality check would wrongly flag every FPS field as
    # "user-edited" on every rerun.
    if not math.isclose(new_value, estimate.value, rel_tol=1e-9, abs_tol=1e-9):
        return estimate.with_value(new_value)
    return estimate


def render_wastage_editor(wastage: WastageFactors) -> WastageFactors:
    st.caption("Adjust wastage/allowance percentages applied when converting MTO quantities into BOQ order quantities.")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        concrete_pct = st.slider("Concrete wastage %", 0.0, 15.0, wastage.concrete_pct, 0.5)
        steel_pct = st.slider("Steel wastage %", 0.0, 15.0, wastage.steel_pct, 0.5)
    with c2:
        brick_block_pct = st.slider("Brick/block wastage %", 0.0, 15.0, wastage.brick_block_pct, 0.5)
        plaster_pct = st.slider("Plaster wastage %", 0.0, 20.0, wastage.plaster_pct, 0.5)
    with c3:
        formwork_pct = st.slider("Formwork wastage %", 0.0, 15.0, wastage.formwork_pct, 0.5)
        flooring_pct = st.slider("Flooring wastage %", 0.0, 15.0, wastage.flooring_pct, 0.5)
    with c4:
        paint_pct = st.slider("Paint wastage %", 0.0, 15.0, wastage.paint_pct, 0.5)
        misc_pct = st.slider("Misc/other wastage %", 0.0, 15.0, wastage.misc_pct, 0.5)

    return WastageFactors(
        concrete_pct=concrete_pct,
        steel_pct=steel_pct,
        brick_block_pct=brick_block_pct,
        plaster_pct=plaster_pct,
        formwork_pct=formwork_pct,
        flooring_pct=flooring_pct,
        paint_pct=paint_pct,
        misc_pct=misc_pct,
    )


def render_rate_editor(
    rate_book: Dict[str, MaterialRate],
    unit_system: str = units.SI,
    currency_symbol: str = "",
) -> Dict[str, MaterialRate]:
    """Rates are always stored canonically per SI unit (PKR/m3, PKR/m2,
    PKR/kg, ...) - exactly what generate_boq() expects. When FPS is
    selected, this editor only *displays* and *accepts* the equivalent
    rate per cft/sqft, converting silently in both directions, so the
    stored MaterialRate never changes meaning regardless of which unit
    system the user is looking at.
    """
    if units.is_fps(unit_system):
        st.caption(
            "Edit unit rates below (shown per cft / sqft - Pakistani FPS practice) to match your local market "
            "before generating the final BOQ cost. Rates are still stored/calculated per metric unit internally, "
            "so switching unit systems never changes the total cost."
        )
    else:
        st.caption("Edit unit rates below to match your local market before generating the final BOQ cost.")

    rate_col_label = f"Rate ({currency_symbol.strip()})" if currency_symbol else "Rate"
    df = pd.DataFrame(
        [
            {
                "Item Code": r.item_code,
                "Description": r.description,
                "Unit": units.display_unit(r.unit, unit_system),
                "Category": r.category,
                rate_col_label: round(units.display_rate(r.rate, r.unit, unit_system), 4),
            }
            for r in rate_book.values()
        ]
    )
    edited = st.data_editor(
        df,
        key="rate_editor",
        num_rows="fixed",
        width="stretch",
        hide_index=True,
        column_config={
            "Item Code": st.column_config.TextColumn(disabled=True),
            "Description": st.column_config.TextColumn(disabled=True),
            "Unit": st.column_config.TextColumn(disabled=True),
            "Category": st.column_config.TextColumn(disabled=True),
            rate_col_label: st.column_config.NumberColumn(min_value=0.0, step=0.01, format="%.2f"),
        },
    )
    updated: Dict[str, MaterialRate] = {}
    for _, row in edited.iterrows():
        code = row["Item Code"]
        original = rate_book[code]
        si_rate = units.rate_to_si(float(row[rate_col_label]), original.unit, unit_system)
        updated[code] = MaterialRate(
            item_code=code,
            description=original.description,
            unit=original.unit,
            category=original.category,
            rate=si_rate,
        )
    return updated


def render_assumptions_editor(assumptions: EngineeringAssumptions, unit_system: str = units.SI) -> EngineeringAssumptions:
    """Editable thumb rules and key default dimensions used by the
    deterministic calculations (engineering/calculations.py)."""
    st.caption(
        "Thumb-rule steel allowances (kg of steel per m³ of concrete) and key default dimensions. "
        "Typical ranges are shown in each field's help. Values are stored in SI."
    )

    def rng(member: str) -> str:
        lo, mid, hi = rules.STEEL_THUMB_RULE_KG_PER_M3[member]
        return f"Typical {lo:g}-{hi:g} kg/m³ (default {mid:g})."

    c1, c2, c3 = st.columns(3)
    with c1:
        ftg = st.number_input("Footing steel (kg/m³)", 0.0, 400.0, float(assumptions.steel_kg_per_m3_footing), 5.0, help=rng("footing"), key="asm_ftg")
        col = st.number_input("Column steel (kg/m³)", 0.0, 400.0, float(assumptions.steel_kg_per_m3_column), 5.0, help=rng("column"), key="asm_col")
    with c2:
        beam = st.number_input("Beam steel (kg/m³)", 0.0, 400.0, float(assumptions.steel_kg_per_m3_beam), 5.0, help=rng("beam"), key="asm_beam")
        slab = st.number_input("Slab steel (kg/m³)", 0.0, 400.0, float(assumptions.steel_kg_per_m3_slab), 5.0, help=rng("slab"), key="asm_slab")
    with c3:
        stair = st.number_input("Stair steel (kg/m³)", 0.0, 400.0, float(assumptions.steel_kg_per_m3_stair), 5.0, help=rng("stair"), key="asm_stair")
        lintel = st.number_input("Lintel steel (kg/m³)", 0.0, 400.0, float(assumptions.steel_kg_per_m3_lintel), 5.0, help=rng("lintel"), key="asm_lintel")

    def dim(label: str, value_si: float, key: str, kind: str, step_si: float, help_text: str) -> float:
        shown = units.to_display(value_si, kind, unit_system)
        unit = units.dimension_unit_label(kind, unit_system)
        new = st.number_input(
            f"{label} ({unit})", min_value=0.0, value=float(shown),
            step=float(units.to_display(step_si, kind, unit_system)), key=key, help=help_text,
        )
        new_si = units.to_si(new, kind, unit_system)
        return value_si if math.isclose(new_si, value_si, rel_tol=1e-9, abs_tol=1e-9) else new_si

    d1, d2, d3, d4 = st.columns(4)
    with d1:
        pcc_t = dim("PCC thickness", assumptions.pcc_thickness_m, "asm_pcc", "thickness", 0.005, "Lean concrete bed under footings (default 75 mm).")
    with d2:
        plinth_h = dim("Plinth height", assumptions.plinth_height_m, "asm_plinth", "length", 0.05, "Natural ground level to ground-floor level (default 0.6 m).")
    with d3:
        ws = dim("Excavation working space", assumptions.excavation_working_space_m, "asm_ws", "thickness", 0.01, "Added on each side of a footing (default 150 mm).")
    with d4:
        parapet_h = dim("Parapet height", assumptions.parapet_height_m, "asm_parapet", "length", 0.05, "Roof parapet wall height (default 0.9 m).")

    return EngineeringAssumptions(
        steel_kg_per_m3_footing=ftg,
        steel_kg_per_m3_column=col,
        steel_kg_per_m3_beam=beam,
        steel_kg_per_m3_slab=slab,
        steel_kg_per_m3_stair=stair,
        steel_kg_per_m3_lintel=lintel,
        pcc_thickness_m=pcc_t,
        plinth_height_m=plinth_h,
        excavation_working_space_m=ws,
        parapet_height_m=parapet_h,
    )
