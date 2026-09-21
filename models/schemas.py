"""
Single source of truth for every data structure that flows through the
pipeline: AI extraction -> user edits -> engineering calculations ->
MTO -> BOQ -> export.

Keeping everything in Pydantic models (rather than loose dicts) means:
- The Groq JSON output is validated immediately (fail fast on bad AI output)
- Every numeric field can carry a confidence level + provenance note
- Streamlit forms, calculation functions, and exporters all share one
  contract, so a change here can't silently break one module without
  breaking the others too (Pydantic raises).
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class ConfidenceLevel(str, Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class Source(str, Enum):
    AI_EXTRACTED = "AI-extracted"
    DEFAULT_ASSUMPTION = "Default assumption"
    USER_EDITED = "User-edited"
    USER_INPUT = "User-input"


class UnitSystem(str, Enum):
    """Which unit system the user sees on input/output screens and in the
    exported MTO/BOQ. Every internal calculation in engineering/ and
    mto_boq/ ALWAYS operates in SI (m, m2, m3, kg) regardless of this
    setting - conversion happens only in the UI/export display layer
    (see utils/units.py)."""

    SI = "SI"
    FPS = "FPS"


class Estimate(BaseModel):
    """A single numeric field with confidence + provenance, editable by the user."""

    value: float
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM
    source: Source = Source.DEFAULT_ASSUMPTION
    note: str = ""

    def with_value(self, new_value: float) -> "Estimate":
        return Estimate(
            value=new_value,
            confidence=self.confidence,
            source=Source.USER_EDITED,
            note=self.note,
        )


# --------------------------------------------------------------------------
# Building parameters (populated by AI, then edited by the user)
# --------------------------------------------------------------------------


class FootingSpec(BaseModel):
    footing_type: str = "isolated"  # isolated | strip | raft | combined
    count: Estimate
    length_m: Estimate
    width_m: Estimate
    # Footing THICKNESS (depth of the concrete pad itself) - NOT the
    # excavation depth. Field name kept as `depth_m` for backward
    # compatibility with saved/AI JSON.
    depth_m: Estimate
    # Founding depth: natural ground level -> underside of the footing.
    # Drives excavation depth (plus PCC thickness below it). Optional for
    # backward compatibility; calculations fall back to
    # engineering.rules.DEFAULT_FOUNDING_DEPTH_M when it is None.
    founding_depth_m: Optional[Estimate] = None


class ColumnSpec(BaseModel):
    count: Estimate
    width_m: Estimate  # 'b'
    depth_m: Estimate  # 'd'
    height_per_floor_m: Estimate


class BeamSpec(BaseModel):
    count: Estimate
    avg_length_m: Estimate
    width_m: Estimate
    depth_m: Estimate


class SlabSpec(BaseModel):
    area_per_floor_sqm: Estimate
    thickness_m: Estimate


class WallSpec(BaseModel):
    total_length_per_floor_m: Estimate  # ALL walls (external + internal) on one floor
    height_m: Estimate
    thickness_m: Estimate
    # Must be a key of engineering.rules.MASONRY_UNIT_SIZES_M (the previous
    # default "Burnt clay brick (modular)" was not a valid key).
    wall_material: str = "Burnt clay brick (modular 190x90x90mm)"
    # External (building-perimeter) wall length per floor - used to split
    # internal vs external plaster/paint and for the roof parapet. Optional
    # for backward compatibility; calculations fall back to 4 x sqrt(plinth
    # area) (a square footprint, Low confidence) when it is None.
    external_perimeter_m: Optional[Estimate] = None


class OpeningsSpec(BaseModel):
    door_count_per_floor: Estimate
    avg_door_area_sqm: Estimate
    window_count_per_floor: Estimate
    avg_window_area_sqm: Estimate


class ServicesSpec(BaseModel):
    """Counts that drive the parametric MEP (plumbing/sanitary, kitchen)
    BOQ lines. Whole-building totals, not per floor."""

    bathroom_count_total: Estimate
    kitchen_count_total: Estimate


def _default_services() -> "ServicesSpec":
    return ServicesSpec(
        bathroom_count_total=Estimate(value=2, confidence=ConfidenceLevel.LOW, source=Source.DEFAULT_ASSUMPTION, note="Default: 2 bathrooms - please verify"),
        kitchen_count_total=Estimate(value=1, confidence=ConfidenceLevel.LOW, source=Source.DEFAULT_ASSUMPTION, note="Default: 1 kitchen - please verify"),
    )


class ExtractedBuildingParams(BaseModel):
    num_floors: Estimate
    plinth_area_per_floor_sqm: Estimate
    footings: FootingSpec
    columns: ColumnSpec
    beams: BeamSpec
    slabs: SlabSpec
    walls: WallSpec
    openings: OpeningsSpec
    services: ServicesSpec = Field(default_factory=_default_services)
    overall_notes: str = ""
    extraction_warnings: List[str] = Field(default_factory=list)


# --------------------------------------------------------------------------
# User-supplied project inputs (technical details, not read from drawing)
# --------------------------------------------------------------------------


class ProjectInputs(BaseModel):
    project_name: str = "Untitled Project"
    client_name: str = ""
    location: str = ""
    soil_type: str = "Ordinary soil"  # Soft/Ordinary/Hard/Murrum/Rock
    concrete_grade_footing: str = "M20"
    concrete_grade_column: str = "M20"
    concrete_grade_beam: str = "M20"
    concrete_grade_slab: str = "M20"
    pcc_grade: str = "M10"
    steel_grade: str = "Fe415"  # Fe415 ~ Grade 60 (see engineering/rules.py STEEL_GRADE_OPTIONS)
    wall_material: str = "Burnt clay brick (modular 190x90x90mm)"
    wall_thickness_mm: int = 230
    plaster_thickness_internal_mm: int = 12
    plaster_thickness_external_mm: int = 18
    finish_level: str = "Standard"  # Basic | Standard | Premium
    include_flooring: bool = True
    include_waterproofing: bool = True
    include_painting: bool = True
    include_dpc: bool = True
    include_anti_termite: bool = True
    include_mep: bool = True  # electrical, plumbing & sanitary, kitchen, external water/drainage
    include_staircase: bool = True
    include_parapet: bool = True
    include_roof_treatment: bool = True  # roof insulation (mud fill) + brick/tuff tiles
    contingency_pct: float = 5.0
    currency: str = "PKR"
    unit_system: str = UnitSystem.SI.value  # "SI" or "FPS" - see UnitSystem


class EngineeringAssumptions(BaseModel):
    """User-editable thumb rules and key default dimensions (Step 3,
    "Engineering assumptions" panel). Defaults mirror engineering/rules.py.
    Steel values are the kg of reinforcement per m3 of concrete applied to
    each member type (before the steel-grade quantity factor)."""

    steel_kg_per_m3_footing: float = 80.0
    steel_kg_per_m3_column: float = 170.0
    steel_kg_per_m3_beam: float = 135.0
    steel_kg_per_m3_slab: float = 85.0
    steel_kg_per_m3_stair: float = 100.0
    steel_kg_per_m3_lintel: float = 80.0
    pcc_thickness_m: float = 0.075
    plinth_height_m: float = 0.6
    excavation_working_space_m: float = 0.15
    parapet_height_m: float = 0.9


class WastageFactors(BaseModel):
    concrete_pct: float = 5.0
    steel_pct: float = 3.0
    brick_block_pct: float = 5.0
    plaster_pct: float = 10.0
    formwork_pct: float = 5.0
    flooring_pct: float = 5.0
    paint_pct: float = 5.0
    misc_pct: float = 5.0


# --------------------------------------------------------------------------
# Rates
# --------------------------------------------------------------------------


class MaterialRate(BaseModel):
    item_code: str
    description: str
    unit: str
    rate: float
    category: str


# --------------------------------------------------------------------------
# MTO / BOQ line items
# --------------------------------------------------------------------------


class QuantityLineItem(BaseModel):
    item_code: str
    description: str
    category: str
    unit: str
    quantity: float
    confidence: ConfidenceLevel
    formula: str
    inputs_used: Dict[str, float] = Field(default_factory=dict)
    assumptions: List[str] = Field(default_factory=list)
    # True for a derived procurement-reference line (e.g. the cement/sand/
    # aggregate that make up a concrete pour already priced as one composite
    # m3 rate) - its cost is already counted in `parent_item_code`'s BOQ
    # line, so generate_boq() must NOT create a separate priced line for it
    # (that would double-count the cost). Still shown in the MTO (Step 4)
    # because that's exactly the quantity someone needs to go buy cement/
    # sand/aggregate. See mto_boq/boq_generator.py and engineering/
    # calculations.py:concrete_material_breakdown()/mortar_material_breakdown().
    informational: bool = False
    parent_item_code: str = ""


class BOQLineItem(BaseModel):
    item_code: str
    description: str
    category: str
    unit: str
    quantity: float
    wastage_pct: float
    quantity_with_wastage: float
    rate: float
    amount: float
    confidence: ConfidenceLevel
    remarks: str = ""


class CostSummary(BaseModel):
    subtotal: float
    contingency_pct: float
    contingency_amount: float
    grand_total: float
    currency: str = "PKR"


class ProjectResult(BaseModel):
    project_inputs: ProjectInputs
    extracted_params: ExtractedBuildingParams
    mto_items: List[QuantityLineItem]
    boq_items: List[BOQLineItem]
    cost_summary: CostSummary
    generated_at: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
