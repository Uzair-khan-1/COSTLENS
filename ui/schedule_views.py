"""
Step 5 "Schedule & workers": the construction programme for THIS house.

Homeowner view  - pick a target (e.g. 6 months) and the app plans everything: activities from the BOQ
                  quantities, crews and workers needed to meet the date (scheduling/planner.py), a colourful
                  timeline with milestones, "who to hire and when", month-by-month plan and material timing.
Engineer mode   - calendar & curing, productivity rates, crews per activity (locked against the planner),
                  dependency lags, detailed Gantt with critical path & float, daily manpower, progress tracking
                  against a saved baseline (S-curve).
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from typing import Dict, List, Optional

import altair as alt
import pandas as pd
import streamlit as st

import config
from scheduling.engine import PHASES, WEEKDAY_NAMES, Schedule, ScheduleSettings, material_delivery_plan
from scheduling.export import build_schedule_workbook, schedule_csv
from scheduling.planner import TargetPlan, plan_for_target
from scheduling.productivity import TRADES, default_rate

CRIT_COLOR, NORMAL_COLOR, FLOAT_COLOR = "#C0392B", config.BRAND_TEAL, "#CBD5E1"
SCHEDULE_WIDGET_KEYS = ["sched_start", "sched_days", "sched_hol", "sched_prod", "sched_chain", "sched_ftg", "sched_col",
                        "sched_dsh", "sched_dry", "sched_view", "sched_color", "sched_float", "sched_lead", "sched_ver",
                        "sched_target", "sched_engineer"]
PHASE_ICONS = {"PRE": "\U0001f6a7", "SUB": "\U0001f3d7\ufe0f", "STR": "\U0001f9f1", "MEP": "\U0001f50c", "PLS": "\U0001faa3",
               "FIN": "\U0001f3a8", "FIT": "\U0001f6bd", "EXT": "\U0001f333", "HND": "\U0001f511"}
OWNER_PHASE = {"PRE": "Getting started", "SUB": "Foundations", "STR": "Walls, columns & roof slabs", "MEP": "Pipes & wiring in walls",
               "PLS": "Plaster & roof", "FIN": "Floors, tiles & paint", "FIT": "Doors, fittings & lights", "EXT": "Outside works",
               "HND": "Final checks & handover"}
TRADE_ORDER = list(TRADES)
TRADE_COLORS = ["#1f77b4", "#aec7e8", "#ff7f0e", "#ffbb78", "#2ca02c", "#98df8a", "#d62728", "#ff9896", "#9467bd", "#c5b0d5",
                "#8c564b", "#c49c94", "#e377c2", "#f7b6d2", "#7f7f7f", "#bcbd22", "#17becf", "#9edae5"]


def settings() -> ScheduleSettings:
    s = st.session_state.get("sched_settings")
    if not isinstance(s, ScheduleSettings):
        s = ScheduleSettings(start_date=(date.today() + timedelta(days=7)).isoformat())
        st.session_state["sched_settings"] = s
    return s


def _plan_key(res, months) -> tuple:
    return (id(res), repr(settings()), float(months))


def current_plan(res, months: Optional[float] = None) -> Optional[TargetPlan]:
    """The planned programme for the chosen target (cached per result + settings + target)."""
    if res is None:
        return None
    months = float(months or st.session_state.get("sched_target") or 0) or natural_months(res)
    key = _plan_key(res, months)
    cache = st.session_state.get("sched_plan_cache")
    if cache and cache[0] == key:
        return cache[1]
    s = settings()
    plan = plan_for_target(res, months, s, locked=dict(s.gang_overrides))
    st.session_state["sched_plan_cache"] = (key, plan)
    return plan


def _speeds(res) -> tuple:
    """(normal pace with one crew per job, fastest realistic) in months - cached per result + calendar settings."""
    base = replace(settings(), progress={}, status_date="", gang_overrides={})
    key = ("speeds", id(res), repr(base))
    c = st.session_state.get("sched_speed_cache")
    if c and c[0] == key:
        return c[1]
    val = (plan_for_target(res, 1000, base).natural_months, plan_for_target(res, 0.5, base).months_needed)
    st.session_state["sched_speed_cache"] = (key, val)
    return val


def natural_months(res) -> float:
    return _speeds(res)[0]


def fastest_months(res) -> float:
    return _speeds(res)[1]


def schedule_for(res) -> Optional[Schedule]:
    plan = current_plan(res)
    return plan.schedule if plan else None


def workbook_bytes(res, project_name: str) -> bytes:
    plan = current_plan(res)
    sched = plan.schedule
    lead = int(st.session_state.get("sched_lead", 3) or 3)
    return build_schedule_workbook(sched, project_name, material_delivery_plan(res, sched, lead))


# ---------------------------------------------------------------- settings panel
def _seed(key: str, value) -> None:
    if key not in st.session_state:
        st.session_state[key] = value


def _render_settings() -> ScheduleSettings:
    s = settings()
    _seed("sched_days", [WEEKDAY_NAMES[d] for d in s.work_weekdays])
    _seed("sched_hol", "\n".join(s.holidays))
    _seed("sched_prod", int(s.productivity_pct))
    _seed("sched_chain", s.one_gang_per_trade)
    _seed("sched_ftg", s.footing_curing_days)
    _seed("sched_col", s.column_curing_days)
    _seed("sched_dsh", s.deshuttering_days)
    _seed("sched_dry", s.plaster_drying_days)

    c2, c3 = st.columns([2, 1])
    start = s.start()
    days = c2.multiselect("Working days", WEEKDAY_NAMES, key="sched_days",
                          help="Typical Pakistani sites work Monday to Saturday (Sunday off).")
    prod = c3.slider("Site productivity", 50, 150, step=5, key="sched_prod", format="%d%%",
                     help="100% = the listed norms. Lower it for a slow site, summer heat, Ramadan or an "
                          "inexperienced contractor; raise it for a large, well-managed team.")
    with st.expander("⚙️ Calendar, curing & sequencing", expanded=False):
        a1, a2 = st.columns([1, 2])
        hol_txt = a1.text_area("Holidays / no-work days (one date per line, YYYY-MM-DD)", key="sched_hol", height=150,
                               help="Add Eid-ul-Fitr and Eid-ul-Adha breaks (usually 3-7 days each), 14 August, "
                                    "and any other days the site will be closed.")
        with a2:
            chain = st.toggle("One gang per trade (finish a floor before moving to the next)", key="sched_chain",
                              help="On = the same masonry / plaster / tile / electrician / plumber gang goes floor by floor "
                                   "(usual for a small contractor). Off = floors can overlap if you have extra gangs.")
            b1, b2 = st.columns(2)
            ftg = b1.number_input("Footing / plinth-beam curing (calendar days)", 0, 28, key="sched_ftg")
            col = b2.number_input("Slab pour → next-floor columns (calendar days)", 0, 28, key="sched_col")
            dsh = b1.number_input("Slab pour → de-shuttering & masonry below (calendar days)", 7, 28, key="sched_dsh",
                                  help="Props under slabs are normally kept 14 days (ACI/PEC practice 14-21 days).")
            dry = b2.number_input("Plaster curing & drying before putty/paint (calendar days)", 0, 45, key="sched_dry")
    holidays: List[str] = []
    bad = []
    for line in (hol_txt or "").replace(",", "\n").splitlines():
        t = line.strip()
        if not t:
            continue
        try:
            holidays.append(date.fromisoformat(t).isoformat())
        except ValueError:
            bad.append(t)
    if bad:
        st.warning("Ignored holiday entries that are not dates (use YYYY-MM-DD): " + ", ".join(bad[:5]))
    if not days:
        st.warning("Select at least one working day - using Monday to Saturday.")
    new = replace(s, start_date=start.isoformat() if start else "", productivity_pct=float(prod),
                  work_weekdays=[WEEKDAY_NAMES.index(d) for d in days] or [0, 1, 2, 3, 4, 5],
                  holidays=sorted(set(holidays)), one_gang_per_trade=bool(chain), footing_curing_days=int(ftg),
                  column_curing_days=int(col), deshuttering_days=int(dsh), plaster_drying_days=int(dry))
    st.session_state["sched_settings"] = new
    return new


# ---------------------------------------------------------------- gantt
def _gantt(sched: Schedule, level: str, color_by: str, show_float: bool) -> alt.Chart:
    acts = sched.activities
    if level == "Phases":
        rows = [{"Label": name, "Start": pd.Timestamp(s), "End": pd.Timestamp(f + timedelta(days=1)),
                 "Phase": name, "Critical": "Critical" if any(a.critical and a.phase_name == name for a in acts) else "Has float",
                 "Days": sum(1 for d in sched.calendar if s <= d <= f), "Float": 0,
                 "LateEnd": pd.Timestamp(f + timedelta(days=1)), "Floor": "", "Work": ""}
                for name, s, f in sorted(sched.phase_spans())]
    else:
        rows = []
        for i, a in enumerate(acts, 1):
            late = sched.calendar[a.lf] if a.lf < len(sched.calendar) else a.finish
            rows.append({"Label": f"{i:02d}  {a.name}", "Start": pd.Timestamp(a.start),
                         "End": pd.Timestamp(a.finish + timedelta(days=1)), "Phase": a.phase_name,
                         "Critical": "Critical" if a.critical else "Has float", "Days": a.duration,
                         "Float": a.total_float, "LateEnd": pd.Timestamp(late + timedelta(days=1)), "Floor": a.floor,
                         "Work": a.work_text()[:160]})
    df = pd.DataFrame(rows)
    order = list(df["Label"])
    y = alt.Y("Label:N", sort=order, title=None, axis=alt.Axis(labelLimit=380, labelFontSize=11))
    x = alt.X("Start:T", title=None, axis=alt.Axis(format="%b %Y", labelAngle=0, grid=True, tickCount="month", orient="top"))
    tip = [alt.Tooltip("Label:N", title="Activity"), alt.Tooltip("Start:T", title="Start", format="%a %d %b %Y"),
           alt.Tooltip("End:T", title="Ends before", format="%a %d %b %Y"), alt.Tooltip("Days:Q", title="Working days"),
           alt.Tooltip("Float:Q", title="Total float (wd)"), alt.Tooltip("Phase:N")]
    if level != "Phases":
        tip.append(alt.Tooltip("Work:N", title="Work"))
    if color_by == "Critical path":
        color = alt.Color("Critical:N", scale=alt.Scale(domain=["Critical", "Has float"], range=[CRIT_COLOR, NORMAL_COLOR]),
                          legend=alt.Legend(title=None, orient="top"))
    else:
        color = alt.Color("Phase:N", sort=list(PHASES.values()), legend=alt.Legend(title=None, orient="top", columns=3),
                          scale=alt.Scale(scheme="tableau10"))
    height = max(120, 26 * len(df))
    base = alt.Chart(df)
    layers = []
    if show_float and level != "Phases":
        fl = df[df["Float"] > 0]
        if not fl.empty:
            layers.append(alt.Chart(fl).mark_bar(color=FLOAT_COLOR, height=6, opacity=0.9)
                          .encode(y=y, x=alt.X("End:T"), x2="LateEnd:T",
                                  tooltip=[alt.Tooltip("Label:N", title="Activity"), alt.Tooltip("Float:Q", title="Float (wd)")]))
    layers.append(base.mark_bar(cornerRadius=3, height=16).encode(y=y, x=x, x2="End:T", color=color, tooltip=tip))
    today = pd.Timestamp(date.today())
    if sched.start <= date.today() <= sched.finish:
        layers.append(alt.Chart(pd.DataFrame({"t": [today]})).mark_rule(color=config.BRAND_GOLD, strokeWidth=2, strokeDash=[4, 3])
                      .encode(x="t:T"))
    return alt.layer(*layers).properties(height=height)


# ---------------------------------------------------------------- editors
def apply_activity_edits(s: ScheduleSettings, base: pd.DataFrame, edited: pd.DataFrame) -> ScheduleSettings:
    """Turn edits in the activity table into gang / duration overrides (pure - unit tested)."""
    gangs, durs = dict(s.gang_overrides), dict(s.duration_overrides)
    for (_, old), (_, new) in zip(base.iterrows(), edited.iterrows()):
        aid = old["ID"]
        if pd.notna(new["Gangs"]) and float(new["Gangs"]) > 0 and float(new["Gangs"]) != float(old["Gangs"]):
            gangs[aid] = float(new["Gangs"])
            durs.pop(aid, None)  # a new gang count recalculates the duration
        if pd.notna(new["Duration (wd)"]) and int(new["Duration (wd)"]) >= 1 and \
                int(new["Duration (wd)"]) != int(old["Duration (wd)"]):
            durs[aid] = int(new["Duration (wd)"])
    return replace(s, gang_overrides=gangs, duration_overrides=durs)


def apply_rate_edits(s: ScheduleSettings, base: pd.DataFrame, edited: pd.DataFrame) -> ScheduleSettings:
    """Turn edits in the productivity table into rate overrides; a value equal to the default removes the override."""
    rates = dict(s.rate_overrides)
    for (_, old), (_, new) in zip(base.iterrows(), edited.iterrows()):
        v = new["Output per gang-day"]
        if pd.isna(v) or float(v) <= 0 or float(v) == float(old["Output per gang-day"]):
            continue
        if abs(float(v) - float(old["Default"])) < 1e-9:
            rates.pop(old["Key"], None)
        else:
            rates[old["Key"]] = float(v)
    return replace(s, rate_overrides=rates)


def _rates_editor(sched: Schedule) -> None:
    s = settings()
    ver = st.session_state.get("sched_ver", 0)
    seen = {}
    names = {}
    for a in sched.activities:
        names.setdefault(a.template, a.name.split(" - ")[0])
        for c in a.components:
            if c.rate is None:
                continue
            k = f"{a.template}|{c.wi_id}"
            if k not in seen:
                seen[k] = {"Key": k, "Activity type": names[a.template], "Work item": c.wi_id,
                           "Description": c.description, "Unit": c.unit, "Total qty": 0.0,
                           "Output per gang-day": float(c.rate), "Default": default_rate(a.template, c.wi_id)[0],
                           "Gang / basis": c.gang_basis}
            seen[k]["Total qty"] += c.qty
    base = pd.DataFrame(list(seen.values()))
    if base.empty:
        return
    base["Total qty"] = base["Total qty"].round(1)
    st.caption("Output of ONE gang in ONE 8-hour working day, in the BOQ unit. Defaults are typical for private "
               "contractors on 5-10 marla houses in Pakistan (manual excavation, site-mixed concrete, hired steel "
               "shuttering). Replace them with your contractor's figures.")
    with st.form(f"sched_rate_form_{ver}", border=False):
        edited = st.data_editor(
            base, key=f"sched_rate_editor_{ver}", hide_index=True, width="stretch", height=420,
            column_order=["Activity type", "Work item", "Description", "Unit", "Total qty", "Output per gang-day",
                          "Default", "Gang / basis"],
            disabled=[c for c in base.columns if c != "Output per gang-day"],
            column_config={"Output per gang-day": st.column_config.NumberColumn(min_value=0.05, step=1.0, format="%.2f"),
                           "Description": st.column_config.TextColumn(width="large")})
        applied = st.form_submit_button("Apply rates", type="primary")
    reset = st.button("↺ Restore default rates", key=f"sched_rate_reset_{ver}")
    if applied:
        st.session_state["sched_settings"] = apply_rate_edits(s, base, edited)
        st.session_state["sched_ver"] = ver + 1
        st.rerun()
    if reset:
        st.session_state["sched_settings"] = replace(s, rate_overrides={})
        st.session_state["sched_ver"] = ver + 1
        st.rerun()



# ---------------------------------------------------------------- homeowner visuals
def _weekly_manpower(sched: Schedule) -> pd.DataFrame:
    """Workers to have on site each week, per trade (the most needed on any day of that week)."""
    days = sched.manpower_by_day()
    rows: Dict[tuple, int] = {}
    for i, d in enumerate(days):
        wk = sched.calendar[i] - timedelta(days=sched.calendar[i].weekday())
        for t, n in d.items():
            rows[(wk, t)] = max(rows.get((wk, t), 0), n)
    df = pd.DataFrame([{"Week": pd.Timestamp(w), "Trade": TRADES.get(t, t), "Workers": n} for (w, t), n in rows.items()])
    return df


def _manpower_chart(sched: Schedule) -> Optional[alt.Chart]:
    df = _weekly_manpower(sched)
    if df.empty:
        return None
    order = [TRADES[t] for t in TRADE_ORDER if TRADES[t] in set(df["Trade"])]
    return alt.Chart(df).mark_bar(width={"band": 0.85}).encode(
        x=alt.X("Week:T", title=None, axis=alt.Axis(format="%d %b", labelAngle=0, tickCount="month")),
        y=alt.Y("sum(Workers):Q", title="Workers on site"),
        color=alt.Color("Trade:N", sort=order, scale=alt.Scale(domain=order, range=TRADE_COLORS[:len(order)]),
                        legend=alt.Legend(title=None, orient="bottom", columns=4)),
        order=alt.Order("Trade:N"),
        tooltip=[alt.Tooltip("Week:T", title="Week of", format="%d %b %Y"), "Trade:N", "Workers:Q"]).properties(height=300)


def _milestones(sched: Schedule) -> List[tuple]:
    by = {a.id: a for a in sched.activities}
    out = []
    if "DPC" in by:
        out.append(("\U0001f9f1", "Foundations complete", by["DPC"].finish))
    for a in sched.activities:
        if a.template == "SLB":
            out.append(("\U0001f3d7\ufe0f", f"Roof slab cast over {a.floor.lower()}", a.finish))
    grey = max((a.finish for a in sched.activities if a.phase in ("SUB", "STR")), default=None)
    if grey:
        out.append(("\u2705", "Grey structure complete", grey))
    pl = max((a.finish for a in sched.activities if a.template in ("PLI", "EXP")), default=None)
    if pl:
        out.append(("\U0001faa3", "All plaster done", pl))
    fin = max((a.finish for a in sched.activities if a.phase == "FIN"), default=None)
    if fin:
        out.append(("\U0001f3a8", "Floors, tiles & paint done", fin))
    if sched.finish:
        out.append(("\U0001f511", "Ready to move in", sched.finish))
    return sorted(out, key=lambda x: x[2])


def _timeline(sched: Schedule) -> alt.Chart:
    rows = []
    spans: Dict[str, List] = {}
    for a in sched.activities:
        spans.setdefault(a.phase, []).append(a)
    for ph, acts in spans.items():
        s, f = min(a.start for a in acts), max(a.finish for a in acts)
        label = f"{PHASE_ICONS.get(ph, '')} {OWNER_PHASE.get(ph, PHASES.get(ph, ph))}"
        rows.append({"Stage": label, "Start": pd.Timestamp(s), "End": pd.Timestamp(f + timedelta(days=1)), "Key": ph,
                     "Weeks": round((f - s).days / 7 + 0.14, 1),
                     "Workers": max(a.workers() for a in acts)})
    df = pd.DataFrame(rows).sort_values("Start")
    order = list(df["Stage"])
    y = alt.Y("Stage:N", sort=order, title=None, axis=alt.Axis(labelLimit=260, labelFontSize=13))
    bars = alt.Chart(df).mark_bar(cornerRadius=6, height=22).encode(
        y=y, x=alt.X("Start:T", title=None, axis=alt.Axis(format="%b %Y", labelAngle=0, tickCount="month", orient="top", grid=True)),
        x2="End:T", color=alt.Color("Key:N", legend=None, scale=alt.Scale(scheme="tableau10")),
        tooltip=[alt.Tooltip("Stage:N"), alt.Tooltip("Start:T", format="%d %b %Y"), alt.Tooltip("End:T", title="Until", format="%d %b %Y"),
                 alt.Tooltip("Weeks:Q"), alt.Tooltip("Workers:Q", title="Largest crew in this stage")])
    ms = pd.DataFrame([{"t": pd.Timestamp(d), "m": f"{i} {n}"} for i, n, d in _milestones(sched)])
    rules = alt.Chart(ms).mark_rule(color=config.BRAND_GOLD, strokeDash=[4, 3], strokeWidth=1.5).encode(
        x="t:T", tooltip=[alt.Tooltip("m:N", title="Milestone"), alt.Tooltip("t:T", title="Date", format="%d %b %Y")])
    return alt.layer(bars, rules).properties(height=46 * len(df) + 30)


def _hire_table(sched: Schedule) -> pd.DataFrame:
    rows = []
    for r in sched.trade_summary():
        rows.append({"Who": TRADES.get(r["trade"], r["trade"]), "Most at once": r["peak"], "Needed from": r["from"],
                     "Until": r["to"], "Total worker-days": int(round(r["worker_days"]))})
    return pd.DataFrame(rows)


def _month_by_month(sched: Schedule) -> None:
    days = sched.manpower_by_day()
    months: Dict[tuple, dict] = {}
    for a in sched.activities:
        d = a.start.replace(day=1)
        while d <= a.finish:
            months.setdefault((d.year, d.month), {"acts": [], "peak": 0})["acts"].append(a)
            d = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
    for i, dd in enumerate(days):
        k = (sched.calendar[i].year, sched.calendar[i].month)
        if k in months:
            months[k]["peak"] = max(months[k]["peak"], sum(dd.values()))
    for n, ((y, m), info) in enumerate(sorted(months.items()), 1):
        title = date(y, m, 1).strftime("%B %Y")
        stages = list(dict.fromkeys(OWNER_PHASE.get(a.phase, a.phase_name) for a in info["acts"]))
        with st.expander(f"Month {n} \u00b7 {title} \u2014 {', '.join(stages[:3])}{'...' if len(stages) > 3 else ''} "
                         f"\u00b7 up to {info['peak']} workers"):
            for a in sorted(info["acts"], key=lambda x: x.start):
                crew = ", ".join(f"{v} {TRADES.get(t, t).split(' (')[0].lower()}{'s' if v > 1 else ''}"
                                 for t, v in a.daily_profile()[0].items()) if a.duration else ""
                st.markdown(f"- **{a.name}** \u2014 {a.start:%d %b} to {a.finish:%d %b} ({a.duration} working days)"
                            + (f" \u00b7 _{crew}_" if crew else ""))


def _owner_view(res, plan: TargetPlan) -> None:
    from ui.illustrations import stat_cards_html
    sched = plan.schedule
    peak = sched.peak_workers()
    skilled = [r for r in sched.trade_summary() if r["trade"] not in ("Labourer", "Helper")]
    cards = [("\U0001f4c5", "Start", f"{sched.start:%d %b %Y}", "work begins on site"),
             ("\U0001f511", "Ready to move in", f"{sched.finish:%d %b %Y}", f"{plan.months_needed:.1f} months"),
             ("\U0001f477", "Most workers at once", f"{peak}", f"site holds about {plan.site_capacity}"),
             ("\U0001f4aa", "Total work", f"{sched.total_worker_days():,.0f}", "worker-days"),
             ("\U0001f6e0\ufe0f", "Skilled trades", f"{len(skilled)}", "masons, fixers, electricians ...")]
    st.markdown(stat_cards_html(cards), unsafe_allow_html=True)
    t1, t2, t3, t4 = st.tabs(["\U0001f5d3\ufe0f Timeline", "\U0001f477 Workers needed", "\U0001f4c6 Month by month",
                              "\U0001f69a When to buy materials"], key="sched_owner_tabs")
    with t1:
        st.altair_chart(_timeline(sched), width="stretch")
        ms = _milestones(sched)
        cols = st.columns(min(len(ms), 4) or 1)
        for i, (ic, name, d) in enumerate(ms):
            with cols[i % len(cols)].container(border=True):
                st.markdown(f"<div style='font-size:22px'>{ic}</div><b>{name}</b><br>"
                            f"<span style='opacity:.75'>{d:%d %b %Y}</span>", unsafe_allow_html=True)
    with t2:
        st.caption("How many workers of each kind should be on site each week to finish on time. Worked out from the "
                   "quantities of your house and normal output per crew per day.")
        ch = _manpower_chart(sched)
        if ch is not None:
            st.altair_chart(ch, width="stretch")
        st.markdown("**Who to hire, and when**")
        st.dataframe(_hire_table(sched), hide_index=True, width="stretch",
                     column_config={"Needed from": st.column_config.DateColumn(format="DD MMM YY"),
                                    "Until": st.column_config.DateColumn(format="DD MMM YY")})
    with t3:
        st.caption("What happens each month and the most workers needed on site.")
        _month_by_month(sched)
    with t4:
        lead = st.number_input("Order this many days before the material is needed", 0, 60, value=3, key="sched_lead")
        rows = material_delivery_plan(res, sched, int(lead))
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", height=420,
                     column_order=["Order by", "Needed on site", "Material", "Quantity to buy", "Buy unit", "First used in"],
                     column_config={"Order by": st.column_config.DateColumn(format="DD MMM YY"),
                                    "Needed on site": st.column_config.DateColumn(format="DD MMM YY"),
                                    "Material": st.column_config.TextColumn(width="large"),
                                    "Quantity to buy": st.column_config.NumberColumn(format="localized")})


# ---------------------------------------------------------------- engineer mode
def _activity_editor(sched: Schedule, plan: TargetPlan) -> None:
    s = settings()
    ver = st.session_state.get("sched_ver", 0)
    rows = [{"#": i, "ID": a.id, "Activity": a.name, "Gangs": float(a.gangs), "Max": a.max_gangs,
             "Lock": "\U0001f512" if a.id in s.gang_overrides else "", "Duration (wd)": int(a.duration),
             "Workers": a.workers(), "Start": a.start, "Finish": a.finish, "Float (wd)": a.total_float,
             "Critical": "\U0001f534" if a.critical else "",
             "Predecessors": ", ".join(p + (f" +{lag}d" if lag else "") for p, lag in a.preds),
             "How the duration was estimated": a.basis_text()}
            for i, a in enumerate(sched.activities, 1)]
    base = pd.DataFrame(rows)
    st.caption("Crews are chosen by the planner to meet the target. Change a crew number to fix it yourself (\U0001f512 = "
               "locked, the planner works around it); type a duration to override the calculation.")
    with st.form(f"sched_act_form_{ver}", border=False):
        edited = st.data_editor(
            base, key=f"sched_act_editor_{ver}", hide_index=True, width="stretch", height=520,
            disabled=[c for c in base.columns if c not in ("Gangs", "Duration (wd)")],
            column_config={
                "#": st.column_config.NumberColumn(width="small"), "ID": st.column_config.TextColumn(width="small"),
                "Activity": st.column_config.TextColumn(width="large"),
                "Gangs": st.column_config.NumberColumn("Crews", min_value=0.5, max_value=10, step=1, width="small",
                                                       help="Crews working in parallel on this activity"),
                "Max": st.column_config.NumberColumn("Max crews", width="small", help="Most crews that fit (site space)"),
                "Duration (wd)": st.column_config.NumberColumn(min_value=1, max_value=365, step=1, width="small"),
                "Start": st.column_config.DateColumn(format="DD MMM YY"), "Finish": st.column_config.DateColumn(format="DD MMM YY"),
                "How the duration was estimated": st.column_config.TextColumn(width="large")})
        applied = st.form_submit_button("Apply changes", type="primary")
    reset = st.button("\u21ba Let the planner choose all crews & durations", key=f"sched_reset_{ver}")
    if applied:
        st.session_state["sched_settings"] = apply_activity_edits(s, base, edited)
        st.session_state["sched_ver"] = ver + 1
        st.rerun()
    if reset:
        st.session_state["sched_settings"] = replace(s, gang_overrides={}, duration_overrides={})
        st.session_state["sched_ver"] = ver + 1
        st.rerun()


def _dependency_editor(sched: Schedule) -> None:
    s = settings()
    ver = st.session_state.get("sched_ver", 0)
    names = {a.id: a.name for a in sched.activities}
    rows = [{"Key": f"{a.id}|{p}", "Activity": f"{a.id} \u00b7 {a.name}", "Waits for": f"{p} \u00b7 {names.get(p, p)}",
             "Lag (calendar days)": int(lag), "Critical link": "\U0001f534" if a.critical and next(
                 (b.critical for b in sched.activities if b.id == p), False) else ""}
            for a in sched.activities for p, lag in a.preds]
    base = pd.DataFrame(rows)
    if base.empty:
        return
    st.caption("Finish-to-start links. The lag is the waiting time after the predecessor finishes (e.g. concrete curing).")
    with st.form(f"sched_dep_form_{ver}", border=False):
        edited = st.data_editor(base, key=f"sched_dep_editor_{ver}", hide_index=True, width="stretch", height=420,
                                column_order=["Activity", "Waits for", "Lag (calendar days)", "Critical link"],
                                disabled=["Activity", "Waits for", "Critical link"],
                                column_config={"Lag (calendar days)": st.column_config.NumberColumn(min_value=0, max_value=60, step=1)})
        applied = st.form_submit_button("Apply lags", type="primary")
    if applied:
        st.session_state["sched_settings"] = apply_lag_edits(s, base, edited)
        st.session_state["sched_ver"] = ver + 1
        st.rerun()


def apply_lag_edits(s: ScheduleSettings, base: pd.DataFrame, edited: pd.DataFrame) -> ScheduleSettings:
    lags = dict(s.lag_overrides)
    for (_, old), (_, new) in zip(base.iterrows(), edited.iterrows()):
        v = new["Lag (calendar days)"]
        if pd.notna(v) and int(v) != int(old["Lag (calendar days)"]):
            lags[old["Key"]] = int(v)
    return replace(s, lag_overrides=lags)


def _progress_tracking(res, sched: Schedule) -> None:
    s = settings()
    ver = st.session_state.get("sched_ver", 0)
    base_line = st.session_state.get("sched_baseline")
    c1, c2, c3 = st.columns([1, 1, 2])
    status = c1.date_input("Progress as of", value=date.fromisoformat(s.status_date) if s.status_date else date.today(),
                           key=f"sched_status_{ver}", format="DD/MM/YYYY")
    if c2.button("\U0001f4cc Save current plan as baseline", key="sched_base_btn",
                 help="Freeze today's plan to compare progress against it."):
        st.session_state["sched_baseline"] = _baseline_of(sched)
        st.rerun()
    if base_line:
        c3.caption(f"Baseline saved {base_line['saved']}: finish {base_line['finish']:%d %b %Y}.")
    rows = [{"ID": a.id, "Activity": a.name, "Planned start": a.start, "Planned finish": a.finish,
             "% complete": float(s.progress.get(a.id, 0.0))} for a in sched.activities]
    base = pd.DataFrame(rows)
    with st.form(f"sched_prog_form_{ver}", border=False):
        edited = st.data_editor(base, key=f"sched_prog_editor_{ver}", hide_index=True, width="stretch", height=380,
                                disabled=["ID", "Activity", "Planned start", "Planned finish"],
                                column_config={"% complete": st.column_config.NumberColumn(min_value=0, max_value=100, step=5),
                                               "Planned start": st.column_config.DateColumn(format="DD MMM YY"),
                                               "Planned finish": st.column_config.DateColumn(format="DD MMM YY")})
        applied = st.form_submit_button("Update progress & forecast", type="primary")
    if applied:
        prog = {r["ID"]: float(r["% complete"]) for _, r in edited.iterrows() if pd.notna(r["% complete"]) and float(r["% complete"]) > 0}
        st.session_state["sched_settings"] = replace(s, progress=prog, status_date=status.isoformat() if prog else "")
        st.session_state["sched_ver"] = ver + 1
        st.rerun()
    if s.progress and base_line:
        earned = sum(base_line["wd"].get(aid, 0) * pct / 100 for aid, pct in s.progress.items())
        planned = sum(v for d, v in base_line["curve"] if d <= status)
        total = base_line["total"] or 1
        delta = (earned - planned) / total * 100
        m1, m2, m3 = st.columns(3)
        m1.metric("Work done", f"{earned / total * 100:.0f}%")
        m2.metric("Planned by now", f"{planned / total * 100:.0f}%", f"{delta:+.0f}% {'ahead' if delta >= 0 else 'behind'}",
                  delta_color="normal")
        m3.metric("Forecast finish", f"{sched.finish:%d %b %Y}",
                  f"{(sched.finish - base_line['finish']).days:+d} days vs baseline", delta_color="inverse")
        cum, acc = [], 0.0
        for d, v in base_line["curve"]:
            acc += v
            cum.append({"Date": pd.Timestamp(d), "Percent": acc / total * 100, "Line": "Planned (baseline)"})
        cum.append({"Date": pd.Timestamp(status), "Percent": earned / total * 100, "Line": "Actual"})
        st.altair_chart(alt.Chart(pd.DataFrame(cum)).mark_line(point=True).encode(
            x=alt.X("Date:T", title=None), y=alt.Y("Percent:Q", title="% of work"), color=alt.Color("Line:N", legend=alt.Legend(orient="top")))
            .properties(height=260), width="stretch")
    elif s.progress:
        st.info("Save a baseline first to compare progress with the plan (S-curve).")


def _baseline_of(sched: Schedule) -> dict:
    days = sched.manpower_by_day()
    curve = [(sched.calendar[i], float(sum(d.values()))) for i, d in enumerate(days)]
    return {"saved": date.today().strftime("%d %b %Y"), "finish": sched.finish,
            "wd": {a.id: a.worker_days() for a in sched.activities}, "curve": curve, "total": sum(v for _, v in curve)}


def _daily_manpower_chart(sched: Schedule) -> alt.Chart:
    days = sched.manpower_by_day()
    df = pd.DataFrame([{"Day": pd.Timestamp(sched.calendar[i]), "Trade": TRADES.get(t, t), "Workers": n}
                       for i, d in enumerate(days) for t, n in d.items()])
    return alt.Chart(df).mark_area().encode(x=alt.X("Day:T", title=None), y=alt.Y("sum(Workers):Q", title="Workers per day"),
                                            color=alt.Color("Trade:N", legend=alt.Legend(orient="bottom", columns=4, title=None)),
                                            tooltip=["Day:T", "Trade:N", "Workers:Q"]).properties(height=280)


def _engineer_view(res, plan: TargetPlan) -> None:
    sched = plan.schedule
    _render_settings()
    g1, g2, g3 = st.columns([1, 1, 1])
    level = g1.radio("Show", ["Activities", "Phases"], horizontal=True, key="sched_view")
    color_by = g2.radio("Colour by", ["Critical path", "Phase"], horizontal=True, key="sched_color")
    show_float = g3.toggle("Show float", value=True, key="sched_float")
    rows = len(sched.phase_spans()) if level == "Phases" else len(sched.activities)
    st.altair_chart(_gantt(sched, level, color_by, show_float), width="stretch",
                    height=max(120, 26 * rows) + (150 if color_by == "Phase" else 90))
    crit = sched.critical_path()
    with st.expander(f"\U0001f534 Critical path ({len(crit)} activities)", expanded=False):
        st.markdown("  \u2192  ".join(f"**{a.name}** ({a.duration} d)" for a in crit))
    t1, t2, t3, t4, t5 = st.tabs(["\U0001f5c2\ufe0f Activities & crews", "\U0001f517 Dependencies", "\u2699\ufe0f Productivity",
                                  "\U0001f4ca Daily manpower", "\U0001f4c8 Progress tracking"], key="sched_eng_tabs")
    with t1:
        _activity_editor(sched, plan)
    with t2:
        _dependency_editor(sched)
    with t3:
        _rates_editor(sched)
    with t4:
        st.altair_chart(_daily_manpower_chart(sched), width="stretch")
        st.caption(f"Site capacity used by the planner: {plan.site_capacity} workers at once (about one per 55 sq ft of plot). "
                   "Activities are delayed automatically when the site is full (resource levelling).")
    with t5:
        _progress_tracking(res, sched)


# ---------------------------------------------------------------- the step
def render_schedule_tab(res) -> None:
    from ui.guide import section
    s = settings()
    nat = natural_months(res)
    fast = fastest_months(res)
    section("\U0001f3af When do you want to move in?",
            f"A small team builds your house in about {nat:.1f} months. With more crews the fastest realistic time is about "
            f"{fast:.1f} months (concrete must cure and plaster must dry - that cannot be rushed).")
    c1, c2 = st.columns([4, 1])
    opts = [4, 5, 6, 7, 8, 10, 12]
    default = st.session_state.get("sched_target") or min(opts, key=lambda m: abs(m - round(nat)))
    months = c1.segmented_control("Target duration", opts, default=default, required=True,
                                  format_func=lambda m: f"{m} months" + (" \u26a1" if m < fast else ""), key="sched_target")
    start = c2.date_input("Start date", value=s.start(), key="sched_start_simple", format="DD/MM/YYYY")
    if start and start.isoformat() != s.start_date:
        st.session_state["sched_settings"] = replace(s, start_date=start.isoformat())
        st.rerun()
    plan = current_plan(res, months)
    if plan is None or not plan.schedule.activities:
        st.info("No quantified work items in the selected scope - nothing to schedule.")
        return
    sched = plan.schedule
    if plan.feasible:
        extra = "" if plan.spare_days < 7 else f" ({plan.spare_days} days to spare)"
        st.success(f"\u2705 **Your house can be ready by {sched.finish:%d %B %Y}**{extra} \u2014 with at most "
                   f"**{sched.peak_workers()} workers** on site at once.")
    else:
        st.warning(f"\u26a1 {plan.notes[0] if plan.notes else 'This target is too fast.'}  \nWe planned the fastest realistic "
                   f"programme: **ready by {sched.finish:%d %B %Y}**.")
    for n in plan.notes[1:] if not plan.feasible else plan.notes:
        st.caption("\u2139\ufe0f " + n)
    engineer = st.toggle("\U0001f6e0\ufe0f Engineer mode (dependencies, productivity, crews, critical path, progress)",
                         key="sched_engineer")
    if engineer:
        _engineer_view(res, plan)
    else:
        _owner_view(res, plan)
    pi = st.session_state.get("project_inputs")
    name = ((pi.project_name if pi else "") or "Project")
    fn = name.replace(" ", "_")
    d1, d2 = st.columns(2)
    d1.download_button("\U0001f4c5 Schedule, Gantt & manpower (Excel)", data=lambda: workbook_bytes(res, name),
                       file_name=f"{fn}_Schedule.xlsx", type="primary", width="stretch",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="sched_dl_xlsx")
    d2.download_button("Schedule (CSV)", data=schedule_csv(sched), file_name=f"{fn}_Schedule.csv", mime="text/csv",
                       width="stretch", key="sched_dl_csv")
