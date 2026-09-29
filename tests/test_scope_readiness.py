"""Scope of work, specification answers and the 'no silent assumptions' readiness gate."""
from __future__ import annotations

from dataclasses import replace

import pytest

from detailed_mto import build_project, compute
from detailed_mto.engine import ST_SCOPE
from detailed_mto.readiness import evaluate
from detailed_mto.scope import PRESETS, QUESTIONS, SCOPE_ITEMS, active_questions, compile_scope
from drawing_processing.package_analyzer import analyze_package, apply_package_facts
from ai.extraction import default_building_params
from knowledge import load_knowledge_base
from models.schemas import ProjectInputs
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE = os.path.join(ROOT, "sample_data", "sample_5_marla_package.pdf")


@pytest.fixture(scope="module")
def kb():
    return load_knowledge_base()


@pytest.fixture(scope="module")
def cad(kb):
    pi = ProjectInputs(project_name="scope", location="Islamabad")
    files = [{"name": "s.pdf", "bytes": open(SAMPLE, "rb").read(), "view_tag": "Plan"}]
    facts = analyze_package(files, None, "FPS")
    params, _, _ = apply_package_facts(default_building_params(), facts, pi)
    return pi, params, facts


def _project(kb, cad, selected, answers):
    pi, params, facts = cad
    s = compile_scope(set(selected), answers)
    opts = replace(build_project(pi, params, kb, facts=facts).options, **s.options)
    return build_project(pi, params, kb, facts=facts, options=opts, overrides=s.overrides)


def _all_answers(p, selected):
    return {q.id: q.options(p)[0][1] for q in active_questions(set(selected))}


def test_every_scope_item_references_real_items(kb):
    for it in SCOPE_ITEMS:
        assert all(w in kb.work_items for w in it.wis), it.key
        assert all(m in kb.materials for m in it.mats), it.key
    for q in QUESTIONS:
        assert q.scope == "core" or q.scope in {s.key for s in SCOPE_ITEMS}, q.id


def test_unselected_scope_is_not_estimated(kb, cad):
    p = _project(kb, cad, [], {})
    res = compute(p, kb)
    for mid in ("FLR-001", "PNT-003", "SAN-001", "DWG-009", "ELE-006", "KIT-004"):
        assert res.by_id(mid).status == ST_SCOPE, mid
    assert res.by_id("CON-001").included and res.by_id("MAS-001").included  # the core structure stays
    wis = {w.wi_id for w in res.scoped_work_items()}
    assert "WI-FL-01" not in wis and "WI-MS-02" in wis


def test_answers_drive_specifications(kb, cad):
    sel = PRESETS["typical"][1]
    base = _all_answers(build_project(cad[0], cad[1], kb, facts=cad[2]), sel)
    a = dict(base, floor_type="Porcelain", wc_type="wall", win_type="alu")
    b = dict(base, floor_type="Marble", wc_type="floor", win_type="upvc")
    ra, rb = compute(_project(kb, cad, sel, a), kb), compute(_project(kb, cad, sel, b), kb)
    assert ra.by_id("FLR-001").gross_qty > 0 and rb.by_id("FLR-001").gross_qty == 0
    assert rb.by_id("FLR-004").gross_qty > ra.by_id("FLR-004").gross_qty
    assert ra.by_id("SAN-001").included and rb.by_id("SAN-001").status == ST_SCOPE and rb.by_id("SAN-003").included
    assert rb.by_id("DWG-010").included and rb.by_id("DWG-009").status == ST_SCOPE


def test_readiness_blocks_until_answered(kb, cad):
    pi, params, facts = cad
    p = build_project(pi, params, kb, facts=facts)
    r = evaluate(p, set(), {}, scope_confirmed=False)
    assert not r.ready and any(m.key == "scope" for m in r.missing)
    sel = set(PRESETS["typical"][1])
    r = evaluate(p, sel, {}, scope_confirmed=True)
    missing = {m.key for m in r.missing}
    assert {"floor_type", "lights", "acs", "boundary_len"} <= missing  # nothing optional is guessed
    answers = _all_answers(p, sel)
    p2 = _project(kb, cad, sel, answers)
    r2 = evaluate(p2, sel, answers, scope_confirmed=True)
    assert r2.ready, [m.title for m in r2.missing]
    assert r2.assumptions and r2.assumptions_hash() == evaluate(p2, sel, answers, True).assumptions_hash()


def test_drawing_values_count_as_found(kb, cad):
    pi, params, facts = cad
    p = build_project(pi, params, kb, facts=facts)
    r = evaluate(p, {"doors"}, {}, scope_confirmed=True)
    found = {f.key for f in r.found}
    missing = {m.key for m in r.missing}
    assert "plot" in found or "plot" in missing  # the plot comes from the drawings or must be entered
    if p.doors() and all(o.confidence in ("High", "User") for o in p.doors()):
        assert "door_count" in found
