"""Target-duration planning, crews & manpower, resource levelling, progress tracking."""
from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest

from ai.extraction import default_building_params
from detailed_mto import build_project, compute
from engineering import plot_templates
from knowledge import load_knowledge_base
from models.schemas import ProjectInputs
from scheduling import ScheduleSettings, build_schedule
from scheduling.planner import MONTH_DAYS, add_months, plan_for_target, site_capacity
from scheduling.productivity import CREWS, TRADES, crew_of

START = "2026-10-05"


def _res(kb, marla):
    pi = ProjectInputs(project_name="plan", plot_marla=marla)
    params = plot_templates.build_template_params(pi) or default_building_params()
    return compute(build_project(pi, params, kb), kb)


@pytest.fixture(scope="module")
def kb():
    return load_knowledge_base()


@pytest.fixture(scope="module")
def res(kb):
    return _res(kb, 5)


def test_every_work_item_has_a_real_crew(kb):
    for wi in kb.work_items:
        crew = crew_of(wi)
        assert crew in CREWS, wi
        assert all(t in TRADES for t in CREWS[crew][0]), crew


def test_manpower_comes_from_crews(res):
    s = build_schedule(res, ScheduleSettings(start_date=START))
    days = s.manpower_by_day()
    assert len(days) == s.working_days and s.peak_workers() > 0
    trades = {r["trade"] for r in s.trade_summary()}
    assert {"Mason", "Labourer", "Steel fixer", "Electrician", "Plumber"} <= trades
    # worker-days add up across activities and the daily histogram
    assert abs(sum(a.worker_days() for a in s.activities) - s.total_worker_days()) / s.total_worker_days() < 0.02


def test_levelling_keeps_the_site_within_capacity(res):
    cap = site_capacity(res)
    free = build_schedule(res, ScheduleSettings(start_date=START))
    lev = build_schedule(res, ScheduleSettings(start_date=START, site_capacity=cap))
    biggest_single_job = max(a.workers() for a in lev.activities)
    assert lev.peak_workers() <= max(cap, biggest_single_job)
    assert lev.finish >= free.finish  # waiting for room on site can only delay
    for a in lev.activities:  # logic still respected
        for pid, _lag in a.preds:
            assert lev.by_id(pid).ef < a.es or lev.by_id(pid).duration == 0


def test_target_is_met_with_more_crews(res):
    relaxed = plan_for_target(res, 12, ScheduleSettings(start_date=START))
    fast = plan_for_target(res, 6.5, ScheduleSettings(start_date=START))
    assert relaxed.feasible and all(v == 1 for v in relaxed.crews.values())
    assert fast.feasible, fast.notes
    assert fast.schedule.finish <= add_months(date.fromisoformat(START), 6.5)
    assert fast.schedule.finish < relaxed.schedule.finish
    assert any(v > 1 for v in fast.crews.values())
    assert fast.schedule.peak_workers() >= relaxed.schedule.peak_workers()
    for a in fast.schedule.activities:
        assert a.gangs <= max(a.max_gangs, 1)


def test_impossible_target_is_explained(res):
    plan = plan_for_target(res, 2, ScheduleSettings(start_date=START))
    assert not plan.feasible
    assert plan.notes and "too fast" in plan.notes[0] and "cure" in plan.notes[0]
    assert plan.months_needed > 2


def test_bigger_house_needs_more_work(kb):
    small, big = _res(kb, 5), _res(kb, 10)
    ps = plan_for_target(small, 8, ScheduleSettings(start_date=START))
    pb = plan_for_target(big, 8, ScheduleSettings(start_date=START))
    assert pb.schedule.total_worker_days() > ps.schedule.total_worker_days()


def test_locked_crews_are_respected(res):
    plan = plan_for_target(res, 6.5, ScheduleSettings(start_date=START), locked={"PTI": 1})
    assert plan.crews["PTI"] == 1 and plan.schedule.by_id("PTI").gangs == 1


def test_progress_moves_the_forecast(res):
    s = ScheduleSettings(start_date=START)
    base = build_schedule(res, s)
    status = base.calendar[40].isoformat()
    # nothing done by day 40 -> everything that wasn't done shifts to start at/after the status date
    late = build_schedule(res, replace(s, progress={"PRE": 100.0}, status_date=status))
    assert late.finish > base.finish
    assert all(a.es >= 40 for a in late.activities if not a.done)
    assert late.by_id("PRE").done


def test_duration_scales_with_target_months(res):
    m6 = plan_for_target(res, 7, ScheduleSettings(start_date=START)).months_needed
    m10 = plan_for_target(res, 10, ScheduleSettings(start_date=START)).months_needed
    assert m6 <= 7 + 1e-6 and m6 <= m10 and m10 <= 10 + 1e-6
    assert abs(MONTH_DAYS - 30.44) < 0.01
