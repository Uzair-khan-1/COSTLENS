"""Apply user edits (from the Streamlit review tables) to a DetailedProject."""
from __future__ import annotations

from typing import Dict, Iterable, List

from detailed_mto.model import USER, DetailedProject, OpeningGroup, Room


def rooms_to_rows(p: DetailedProject) -> List[dict]:
    return [{"Floor": r.floor, "Room": r.name, "Room type": r.room_type, "Length (ft)": round(r.length_ft, 2),
             "Width (ft)": round(r.width_ft, 2), "Source": r.source, "Confidence": r.confidence} for r in p.rooms]


def openings_to_rows(p: DetailedProject) -> List[dict]:
    return [{"Kind": o.kind, "Name": o.name, "Width (ft)": round(o.width_ft, 2), "Height (ft)": round(o.height_ft, 2),
             "Qty": int(o.qty), "Leaves": int(o.leaves), "Chogath (in)": o.chogath_in, "External": bool(o.external),
             "Source": o.source, "Confidence": o.confidence} for o in p.openings]


def _num(v, default=0.0) -> float:
    try:
        f = float(v)
        return f if f == f else default  # NaN guard
    except (TypeError, ValueError):
        return default


def apply_rooms(p: DetailedProject, rows: Iterable[dict], original: List[dict]) -> None:
    rows = [r for r in rows if str(r.get("Room", "") or "").strip()]
    orig = {(o["Floor"], o["Room"], o["Length (ft)"], o["Width (ft)"], o["Room type"]) for o in original}
    out = []
    for r in rows:
        key = (r.get("Floor"), r.get("Room"), _num(r.get("Length (ft)")), _num(r.get("Width (ft)")), r.get("Room type"))
        edited = key not in orig
        out.append(Room(str(r.get("Floor") or "ground"), str(r.get("Room")), str(r.get("Room type") or "Bedroom"),
                        _num(r.get("Length (ft)")), _num(r.get("Width (ft)")),
                        "User input" if edited else str(r.get("Source") or ""),
                        USER if edited else str(r.get("Confidence") or "Medium")))
    p.rooms = out


def apply_openings(p: DetailedProject, rows: Iterable[dict], original: List[dict]) -> None:
    rows = [r for r in rows if str(r.get("Name", "") or "").strip()]
    cols = ("Kind", "Name", "Width (ft)", "Height (ft)", "Qty", "Leaves", "External")
    orig = {tuple(o[c] for c in cols) for o in original}
    out = []
    for r in rows:
        vals = (r.get("Kind"), r.get("Name"), _num(r.get("Width (ft)")), _num(r.get("Height (ft)")), int(_num(r.get("Qty"))),
                int(_num(r.get("Leaves"), 1)), bool(r.get("External")))
        edited = vals not in orig
        out.append(OpeningGroup(str(r.get("Kind") or "window"), str(r.get("Name")), vals[2], vals[3], vals[4], max(vals[5], 1),
                                _num(r.get("Chogath (in)"), 5.0), vals[6],
                                "User input" if edited else str(r.get("Source") or ""),
                                USER if edited else str(r.get("Confidence") or "Assumed")))
    p.openings = out


def apply_overrides(p: DetailedProject, overrides: Dict[str, float]) -> None:
    for k, v in (overrides or {}).items():
        p.override(k, v)
