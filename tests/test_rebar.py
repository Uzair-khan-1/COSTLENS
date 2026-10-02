"""Steel from the drawings: bar callouts, bar bending schedules, member calculations, thumb-rule fallback."""
from __future__ import annotations

import io
import os

import pytest

from detailed_mto.rebar import (Bars, MemberSpec, Spaced, column_steel, footing_steel, kg_per_ft, linear_steel,
                                parse_callouts, read_rebar, slab_steel)

U = "/mnt/user-data/uploads/"
SQ = ["Artitectural_Drawing.pdf", "Servant_Quarter_Sectional_Drawings.pdf", "Servant_Quarter_Structural_Drawings.pdf"]


def test_unit_weights():
    assert kg_per_ft("#4") == pytest.approx(0.668 * 0.45359, rel=1e-3)
    assert kg_per_ft("12mm") == pytest.approx(144 / 162 / 3.28084, rel=1e-3)


@pytest.mark.parametrize("text,long_,spaced,both", [
    ("Column C1 (16) 6-#5 #3 rings @ 9 in c/c", ("#5", 6), [("#3", 9.0, "ties")], False),
    ("#4 @ 6 in c/c both ways", None, [("#4", 6.0, "mesh")], True),
    ("Roof slab #4 @ 6 in c/c (main) #4 @ 6 in c/c (distribution)", None, [("#4", 6.0, "main"), ("#4", 6.0, "distribution")], False),
    ("6-12mm, 8mm stirrups @ 150 c/c", ("12mm", 6), [("8mm", 150 / 25.4, "ties")], False),
    ("4 Nos 16 mm bars, T10 @ 200 mm c/c", ("16mm", 4), [("10mm", 200 / 25.4, "mesh")], False),
])
def test_callouts(text, long_, spaced, both):
    lb, sp, bw = parse_callouts(text)
    assert (lb.size, lb.count) == long_ if long_ else lb is None
    assert [(s.size, round(s.spacing_in, 3), s.role) for s in sp] == [(a, round(b, 3), c) for a, b, c in spaced]
    assert bw == both


def test_member_calculations():
    col = MemberSpec("column", long_bars=Bars(6, "#5"), ties=Spaced("#3", 9.0, "ties"))
    r = column_steel(col, 16, 8, 8, 12.0, 1)
    # 16 x 6 bars x (12 + 1.5) ft x 1.043 lb/ft = 1,352 lb + ties
    assert r.kg == pytest.approx(16 * 6 * 13.5 * kg_per_ft("#5") + 16 * (12 * 12 / 9 + 1) * (2 * 10 + 2 * 10 * 0.375) / 12 * kg_per_ft("#3"), rel=1e-6)
    ftg = MemberSpec("footing", mesh=[Spaced("#4", 6.0, "mesh")], both_ways=True)
    f = footing_steel(ftg, 16, 4.0, 4.0, 1.25)
    assert f.kg > 0 and "both" not in f.calc and f.calc.count("#4 @ 6") == 2  # both directions
    band = MemberSpec("lintel", long_bars=Bars(6, "#5"), ties=Spaced("#3", 9.0, "ties"))
    assert linear_steel("lintel", band, 100, 9, 6).kg > linear_steel("lintel", band, 50, 9, 6).kg
    slab = MemberSpec("slab", mesh=[Spaced("#4", 6.0, "main"), Spaced("#4", 6.0, "distribution")])
    s = slab_steel(slab, 1000)
    assert s.kg == pytest.approx(2 * 1000 * 2 * 1.12 * kg_per_ft("#4"), rel=1e-6)


def _pdf(lines):
    """A one-page PDF with the given text lines (x, y, text)."""
    import pymupdf
    doc = pymupdf.open()
    page = doc.new_page(width=842, height=595)
    for x, y, t in lines:
        page.insert_text((x, y), t, fontsize=9)
    return doc


def test_bar_bending_schedule_is_used_as_is():
    doc = _pdf([(40, 60, "BAR BENDING SCHEDULE"),
                (40, 80, "Bar mark"), (120, 80, "Member"), (220, 80, "Dia"), (280, 80, "No. of bars"), (360, 80, "Cutting length"),
                (40, 100, "COLUMNS"),
                (40, 115, "C1-a"), (120, 115, "Column"), (220, 115, "16mm"), (280, 115, "96"), (360, 115, "4.2"),
                (40, 130, "C1-b"), (120, 130, "Column ties"), (220, 130, "10mm"), (280, 130, "560"), (360, 130, "0.9"),
                (40, 150, "SLAB"),
                (40, 165, "S1"), (120, 165, "Slab"), (220, 165, "12mm"), (280, 165, "120"), (360, 165, "7.5")])
    facts = read_rebar(list(doc), "bbs.pdf")
    assert len(facts.bbs) == 3
    col = sum(r.kg for r in facts.bbs if r.member == "column")
    expect = 96 * 4.2 * 16 * 16 / 162 + 560 * 0.9 * 100 / 162
    assert col == pytest.approx(expect, rel=0.01)


@pytest.mark.skipif(not all(os.path.exists(U + n) for n in SQ), reason="servant quarter drawings not available")
def test_servant_quarter_steel_from_drawings():
    from ai.extraction import default_building_params
    from detailed_mto import build_project, compute, scan_pdf_bytes
    from drawing_processing.package_analyzer import analyze_package, apply_package_facts
    from knowledge import load_knowledge_base
    from models.schemas import ProjectInputs
    files = [{"name": n, "bytes": open(U + n, "rb").read(), "view_tag": "Other / not sure"} for n in SQ]
    pi = ProjectInputs(project_name="SQ", location="Islamabad")
    facts = analyze_package(files, None, "FPS")
    scan = scan_pdf_bytes(files)
    params, _, _ = apply_package_facts(default_building_params(), facts, pi)
    kb = load_knowledge_base()
    p = build_project(pi, params, kb, facts=facts, scan=scan)
    assert p.rebar is not None and p.v("COL_N") == 16 and p.v("COL_B_IN") == 8 and p.v("FTG_L") == 4.0
    m = p.rebar.members
    assert (m["column"].long_bars.count, m["column"].long_bars.size) == (6, "#5")
    assert (m["plinth"].long_bars.count, m["fdn_tie"].long_bars.count) == (4, 6)
    assert not p.mumty  # single-storey quarter: no invented mumty
    res = compute(p, kb)
    rf = {w.wi_id: w for w in res.work_items}
    assert "drawing" in rf["WI-RF-02"].calculation and "drawing" in rf["WI-RF-01"].calculation
    drawn = sum(rf[k].qty for k in ("WI-RF-01", "WI-RF-02", "WI-RF-03", "WI-RF-04", "WI-RF-06"))
    stated = p.rebar.stated_total_kg
    assert stated == pytest.approx(8720.54 * 0.45359237, rel=1e-4)
    assert abs(drawn / stated - 1) < 0.15  # within 15 % of the steel printed on the drawing
    assert any(c.startswith("Steel check:") for c in p.conflicts)


def test_without_details_the_thumb_rule_is_used():
    from ai.extraction import default_building_params
    from detailed_mto import build_project, compute
    from engineering import plot_templates
    from knowledge import load_knowledge_base
    from models.schemas import ProjectInputs
    pi = ProjectInputs(project_name="t", plot_marla=5)
    kb = load_knowledge_base()
    p = build_project(pi, plot_templates.build_template_params(pi) or default_building_params(), kb)
    res = compute(p, kb)
    rf2 = next(w for w in res.work_items if w.wi_id == "WI-RF-02")
    assert "thumb rule" in rf2.calculation
