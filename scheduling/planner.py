"""
Plan to a target duration.

The owner only chooses "finish in N months". The planner starts every activity with ONE crew (the smallest,
cheapest team) and then, like a site planner "crashing" a programme, repeatedly adds a crew to the critical
activity that saves the most days per extra worker - until the house finishes by the target date, while

  * never putting more crews on an activity than can physically work on it (site space & crew limits), and
  * never exceeding the number of workers the plot can hold at once (site capacity).

Waiting times that cannot be bought with more workers - concrete curing before de-shuttering and loading,
plaster drying before paint - stay as they are. If the target is shorter than that physical minimum, the
planner says so and returns the fastest realistic programme with the reason.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from typing import Dict, List, Optional

from scheduling.engine import Schedule, ScheduleSettings, build_schedule
from scheduling.productivity import CREWS

MONTH_DAYS = 30.44
MAX_ITER = 600


@dataclass
class TargetPlan:
    schedule: Schedule
    months: float
    target_finish: date
    feasible: bool
    crews: Dict[str, float]
    site_capacity: int
    natural_months: float  # duration with one crew per activity (normal small-contractor pace)
    notes: List[str] = field(default_factory=list)

    @property
    def months_needed(self) -> float:
        return self.schedule.calendar_days / MONTH_DAYS if self.schedule.activities else 0.0

    @property
    def spare_days(self) -> int:
        return (self.target_finish - self.schedule.finish).days if self.schedule.finish else 0


def add_months(d: date, months: float) -> date:
    return d + timedelta(days=int(round(months * MONTH_DAYS)))


def site_capacity(res) -> int:
    """How many workers the plot can hold at once: about one per 55 sq ft of plot (space to work, stack
    bricks/steel, mix concrete), not less than 14 and not more than 35 for a 5-10 marla site."""
    p = res.project
    plot = (p.v("PLOT_W") or 0) * (p.v("PLOT_D") or 0)
    if plot <= 0:
        plot = max((f.covered_sft for f in p.floors), default=1200) * 1.25
    return int(min(35, max(14, plot // 55)))


def _duration_with(a, k: float, prod: float) -> int:
    days = 0.0
    for c in a.components:
        if c.rate and c.qty > 0:
            kk = max(1.0, min(k, float(CREWS.get(c.crew, ({}, 1))[1])))
            days += c.gang_days / kk
    days /= prod
    return max(int(math.ceil(days - 1e-6)), a.fixed_days, 1 if days > 0 else 0)


def _extra_workers(a, k: float) -> int:
    """Additional workers on site when this activity goes from k to k+1 crews (its largest part)."""
    add = 0
    for c in a.components:
        if c.rate and c.qty > 0:
            comp, cap = CREWS.get(c.crew, ({"Labourer": 2}, 1))
            if k + 1 <= cap:
                add = max(add, sum(comp.values()))
    return add


def plan_for_target(res, months: float, base: Optional[ScheduleSettings] = None,
                    locked: Optional[Dict[str, float]] = None) -> TargetPlan:
    """locked: crews the engineer fixed by hand for some activities (the planner will not change them)."""
    base = base or ScheduleSettings()
    locked = dict(locked or {})
    cap = site_capacity(res)
    s = replace(base, gang_overrides={}, rate_overrides=dict(base.rate_overrides), site_capacity=cap,
                duration_overrides=dict(base.duration_overrides), lag_overrides=dict(base.lag_overrides))
    target = add_months(s.start(), months)
    prod = max(float(s.productivity_pct or 100.0), 10.0) / 100.0
    notes: List[str] = []

    probe = build_schedule(res, replace(s, gang_overrides=dict(locked)))
    crews: Dict[str, float] = {a.id: 1.0 for a in probe.activities}
    crews.update(locked)
    s.gang_overrides = dict(crews)
    sched = build_schedule(res, s)
    natural_months = sched.calendar_days / MONTH_DAYS if sched.activities else 0.0
    tried_parallel = False
    for _ in range(MAX_ITER):
        if not sched.activities or sched.finish <= target:
            break
        # candidates: critical jobs that can take one more crew, best estimated days saved per extra worker first
        cands = []
        for a in sched.critical_path():
            if a.id in locked or a.overridden or crews.get(a.id, 1) >= a.max_gangs:
                continue
            k = crews.get(a.id, 1.0)
            gain = a.duration - _duration_with(a, k + 1, prod)
            extra = _extra_workers(a, k)
            if gain > 0 and extra > 0:
                cands.append((gain / extra, a))
        cands.sort(key=lambda x: -x[0])
        best = None
        for _score, a in cands[:6]:  # try the most promising few on the real (levelled) programme
            trial_crews = dict(crews)
            trial_crews[a.id] = trial_crews.get(a.id, 1.0) + 1
            trial = build_schedule(res, replace(s, gang_overrides=trial_crews))
            saved = (sched.finish - trial.finish).days
            if saved > 0:
                per_worker = saved / max(_extra_workers(a, crews.get(a.id, 1.0)), 1)
                if best is None or per_worker > best[0]:
                    best = (per_worker, trial_crews, trial)
        if best is not None:
            crews, sched = best[1], best[2]
            s.gang_overrides = dict(crews)
            continue
        if s.one_gang_per_trade and not tried_parallel:
            tried_parallel = True
            trial = build_schedule(res, replace(s, one_gang_per_trade=False))
            if trial.finish < sched.finish:
                s.one_gang_per_trade = False
                sched = trial
                notes.append("To save time, different floors are worked on at the same time by separate crews.")
                continue
        break
    feasible = bool(sched.activities) and sched.finish <= target
    if not feasible and sched.activities:
        waits = _waiting_on_critical_path(sched)
        notes.insert(0, f"{months:g} months is too fast for this house. The fastest realistic programme is about "
                        f"{sched.calendar_days / MONTH_DAYS:.1f} months: about {waits} days on the critical path are "
                        f"waiting for concrete to cure and plaster to dry (more workers cannot shorten that), and the plot "
                        f"can hold only about {cap} workers at once.")
    elif sched.activities and natural_months <= months:
        notes.insert(0, f"A small team (one crew per job) builds this house in about {natural_months:.1f} months - "
                        f"within your {months:g} months, so no extra crews are needed.")
    return TargetPlan(sched, months, target, feasible, crews, cap, natural_months, notes)


def _waiting_on_critical_path(sched: Schedule) -> int:
    """Calendar days of curing/drying waits along ONE driving chain from handover back to the start."""
    by = {a.id: a for a in sched.activities}
    cur = max(sched.activities, key=lambda a: a.ef)
    total, seen = 0, set()
    while cur is not None and cur.id not in seen:
        seen.add(cur.id)
        driving = None
        for pid, lag in cur.preds:
            p = by.get(pid)
            if p is None or not p.duration:
                continue
            if driving is None or p.ef > driving[0].ef or (p.ef == driving[0].ef and lag > driving[1]):
                driving = (p, lag)
        if driving is None:
            break
        total += driving[1]
        cur = driving[0]
    return total


def fastest_months(res, base: Optional[ScheduleSettings] = None) -> float:
    """Shortest realistic duration (months) for this house - used to offer sensible targets."""
    plan = plan_for_target(res, 0.5, base)
    return plan.months_needed
