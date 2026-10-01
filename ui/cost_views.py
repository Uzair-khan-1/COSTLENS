"""
Step 6 "Cost & cash flow" - what the house will cost in the owner's city, and when the money is needed.

Owner view: city, how you'll build (contract type), total with range, cost per sq ft, where the money goes,
money needed each month (from the schedule), editable rates & supplier quotes, government estimate for
comparison, downloads. Admin: price updates (agent), approvals (password), MRS import.
"""
from __future__ import annotations

from dataclasses import replace

import altair as alt
import pandas as pd
import streamlit as st

import config
from pricing.base_rates import CITIES, LIVE_ITEMS
from pricing.costing import CONTRACTS, EXTRAS, CostSettings, compute_cost, pkr, wi_market_costs
from pricing.ratebook import RateBook

CITY_CHOICES = CITIES + ["Faisalabad", "Multan"]
STATUS_ICON = {"live": "\U0001f7e2 market (live)", "user": "\U0001f535 your quote", "indicative": "\U0001f7e1 rate book"}


def book() -> RateBook:
    b = st.session_state.get("_ratebook")
    if b is None:
        b = RateBook()
        st.session_state["_ratebook"] = b
    return b


def reload_book() -> None:
    st.session_state["_ratebook"] = RateBook()


def cost_settings() -> CostSettings:
    s = st.session_state.get("cost_settings")
    if not isinstance(s, CostSettings):
        pi = st.session_state.get("project_inputs")
        city = (pi.location if pi and pi.location in CITY_CHOICES else "Islamabad")
        s = CostSettings(city=city)
        st.session_state["cost_settings"] = s
    return s


def _set(**kw) -> None:
    st.session_state["cost_settings"] = replace(cost_settings(), **kw)


def current_cost(res):
    from ui.schedule_views import current_plan
    s = cost_settings()
    plan = current_plan(res)
    sched = plan.schedule if plan else None
    return compute_cost(res, s, book(), sched), sched


def government(res, cost):
    from pricing.government import government_estimate, update_factors
    s = cost.settings
    uf = update_factors(None, s.labour_update_pct, getattr(s, "material_update_pct", 0.0))
    wc, loose = wi_market_costs(cost, res)
    return government_estimate(res, s.city, uf, wc, s.gov_bst_pct, s.gov_consultancy_pct, s.gov_contingency_pct, loose), uf


# ---------------------------------------------------------------- building blocks
def _settings_bar() -> None:
    s = cost_settings()
    c1, c2 = st.columns([1, 3])
    city = c1.selectbox("City for prices", CITY_CHOICES, index=CITY_CHOICES.index(s.city) if s.city in CITY_CHOICES else 0,
                        key="cost_city", help="Faisalabad and Multan use Lahore rates.")
    labels = {k: v[0] for k, v in CONTRACTS.items()}
    contract = c2.radio("How will you build?", list(CONTRACTS), index=list(CONTRACTS).index(s.contract),
                        format_func=lambda k: labels[k], key="cost_contract")
    st.caption("\u2139\ufe0f " + CONTRACTS[contract][1])
    if city != s.city or contract != s.contract:
        _set(city=city, contract=contract)
        st.rerun()
    with st.expander("\u2699\ufe0f Profit, contingency, price rise & extra costs"):
        a, b, c = st.columns(3)
        profit = a.number_input("Contractor profit & overhead %", 0.0, 40.0, float(s.profit_pct), 1.0, key="cost_profit")
        cont = b.number_input("Contingency %", 0.0, 30.0, float(s.contingency_pct), 1.0, key="cost_cont",
                              help="Money kept aside for surprises.")
        esc = c.number_input("Price rise per month %", 0.0, 5.0, float(s.escalation_pct_month), 0.25, key="cost_esc",
                             help="Prices usually rise while you build. Applied to money spent in later months.")
        st.markdown("**Extra costs (tick what applies to you)**")
        on, val = dict(s.extras_on), dict(s.extras_value)
        for key, (label, kind, default, help_) in EXTRAS.items():
            e1, e2 = st.columns([2, 1])
            on[key] = e1.checkbox(label, value=bool(on.get(key)), key=f"cost_x_{key}", help=help_)
            unit = "% of materials" if kind == "pct_materials" else "% of construction" if kind == "pct_construction" else "Rs"
            val[key] = e2.number_input(unit, 0.0, 1e8 if unit == "Rs" else 20.0, float(val.get(key, default)),
                                       1000.0 if unit == "Rs" else 0.5, key=f"cost_xv_{key}", label_visibility="visible",
                                       disabled=not on[key])
        if (profit, cont, esc, on, val) != (s.profit_pct, s.contingency_pct, s.escalation_pct_month, s.extras_on, s.extras_value):
            _set(profit_pct=profit, contingency_pct=cont, escalation_pct_month=esc, extras_on=on, extras_value=val)
            st.rerun()


def _headline(cost) -> None:
    from ui.illustrations import stat_cards_html
    s = cost.settings
    st.markdown(
        f"<div style='padding:14px 18px;border-radius:14px;background:linear-gradient(135deg,#0B1E3D,#0D9488);color:white;"
        f"margin:6px 0 10px 0'><div style='font-size:14px;opacity:.85'>Estimated cost of your house in {s.city}</div>"
        f"<div style='font-size:34px;font-weight:800;line-height:1.2'>{pkr(cost.total)}</div>"
        f"<div style='font-size:14px;opacity:.9'>Likely between {pkr(cost.low)} and {pkr(cost.high)} \u00b7 "
        f"Rs {cost.per_sft:,.0f} per sq ft of covered area ({cost.covered_sft:,.0f} sq ft)</div></div>",
        unsafe_allow_html=True)
    grey, fin = cost.grey_finishing()
    cards = [("\U0001f9f1", "Materials", pkr(cost.materials), "everything to buy"),
             ("\U0001f477", "Labour", pkr(cost.labour), "all the work"),
             ("\U0001f91d", "Paid to contractor", pkr(cost.contractor_part), f"incl. {s.profit_pct:g}% profit"),
             ("\U0001f6d2", "You buy yourself", pkr(cost.owner_buys), "materials you purchase"),
             ("\U0001f4c8", "Price rise", pkr(cost.escalation), f"{s.escalation_pct_month:g}% per month"),
             ("\U0001f3d7\ufe0f", "Grey structure / finishing", f"{grey / max(grey + fin, 1):.0%} / {fin / max(grey + fin, 1):.0%}",
              f"{pkr(grey)} / {pkr(fin)}")]
    st.markdown(stat_cards_html(cards), unsafe_allow_html=True)
    share = cost.rate_status_share()
    live, user = share.get("live", 0.0), share.get("user", 0.0)
    st.caption(f"Prices: {live:.0%} live market prices \u00b7 {user:.0%} your quotes \u00b7 "
               f"{1 - live - user:.0%} indicative rate book (Sep 2026, to confirm). "
               "Add your suppliers' quotes in 'Materials & rates' or 'Upload a quote' to firm up the estimate.")


def _where_money_goes(cost) -> None:
    rows = []
    for t, m, lab in cost.by_trade():
        name = t
        if m:
            rows.append({"Trade": name, "Part": "Materials", "Rs": m})
        if lab:
            rows.append({"Trade": name, "Part": "Labour", "Rs": lab})
    df = pd.DataFrame(rows)
    if df.empty:
        return
    tot = df.groupby("Trade")["Rs"].sum().sort_values(ascending=False)
    top = list(tot.index[:14])
    df = df[df["Trade"].isin(top)]
    df["Lakh"] = df["Rs"] / 1e5
    st.altair_chart(alt.Chart(df).mark_bar().encode(
        y=alt.Y("Trade:N", sort=top, title=None, axis=alt.Axis(labelLimit=240)),
        x=alt.X("sum(Lakh):Q", title="Rs lakh"), color=alt.Color("Part:N", legend=alt.Legend(orient="top", title=None),
                                                                 scale=alt.Scale(range=[config.BRAND_TEAL, "#F59E0B"])),
        tooltip=["Trade:N", "Part:N", alt.Tooltip("Lakh:Q", format=",.1f")]).properties(height=28 * len(top) + 40), width="stretch")


def _cashflow(cost) -> None:
    if not cost.cashflow:
        st.info("Open the schedule (Step 5) to see when the money is needed.")
        return
    df = pd.DataFrame(cost.cashflow)
    long = df.melt(id_vars=["Month of"], value_vars=["Materials", "Labour", "Contractor, extras & contingency",
                                                   "Price rise (escalation)"], var_name="Part", value_name="Rs")
    long["Lakh"] = long["Rs"] / 1e5
    long["Month of"] = pd.to_datetime(long["Month of"])
    bars = alt.Chart(long).mark_bar().encode(
        x=alt.X("yearmonth(Month of):T", title=None, axis=alt.Axis(format="%b %Y", labelAngle=0)),
        y=alt.Y("sum(Lakh):Q", title="Rs lakh this month"),
        color=alt.Color("Part:N", legend=alt.Legend(orient="top", title=None),
                        scale=alt.Scale(domain=["Materials", "Labour", "Contractor, extras & contingency", "Price rise (escalation)"],
                                        range=[config.BRAND_TEAL, "#F59E0B", "#1F3864", "#F87171"])),
        tooltip=[alt.Tooltip("yearmonth(Month of):T", title="Month"), "Part:N", alt.Tooltip("sum(Lakh):Q", format=",.1f")])
    st.altair_chart(bars.properties(height=300), width="stretch")
    peak = max(cost.cashflow, key=lambda m: m["Total"])
    st.success(f"\U0001f4b0 The most money is needed in **{peak['Month of']:%B %Y}**: about **{pkr(peak['Total'])}**. "
               f"Keep **{pkr(cost.cashflow[0]['Total'] + (cost.cashflow[1]['Total'] if len(cost.cashflow) > 1 else 0))}** "
               "ready for the first two months.")
    show = df[["Month of", "Materials", "Labour", "Contractor, extras & contingency", "Price rise (escalation)", "Total", "Cumulative"]]
    show = show.assign(**{c: show[c].map(lambda v: pkr(v)) for c in show.columns if c != "Month of"})
    show["Month of"] = show["Month of"].map(lambda d: d.strftime("%b %Y"))
    st.dataframe(show, hide_index=True, width="stretch")


def _materials_editor(cost) -> None:
    s = cost_settings()
    ver = st.session_state.get("cost_ver", 0)
    mats = [ln for ln in cost.lines if ln.kind == "material"]
    trades = sorted({ln.trade for ln in mats})
    pick = st.multiselect("Trades", trades, default=[], placeholder="All trades", key="cost_trades")
    rows = [{"Code": ln.code, "Material": ln.name, "Trade": ln.trade, "Unit": ln.unit, "Qty": round(ln.qty, 2),
             "Rate (Rs)": round(ln.rate, 2), "Amount": round(ln.amount), "Price": STATUS_ICON.get(ln.status, ln.status),
             "Rate date": ln.as_of, "Source": ln.source} for ln in mats if not pick or ln.trade in pick]
    base = pd.DataFrame(rows)
    st.caption("Type your supplier's price in 'Rate (Rs)' (per the unit shown) - it becomes 'your quote' for this project.")
    with st.form(f"cost_mat_form_{ver}", border=False):
        ed = st.data_editor(base, key=f"cost_mat_ed_{ver}", hide_index=True, width="stretch", height=460,
                            disabled=[c for c in base.columns if c != "Rate (Rs)"],
                            column_config={"Material": st.column_config.TextColumn(width="large"),
                                           "Amount": st.column_config.NumberColumn(format="localized"),
                                           "Rate (Rs)": st.column_config.NumberColumn(min_value=0.0, format="%.2f")})
        ok = st.form_submit_button("Use my rates", type="primary")
    if ok:
        ur = dict(s.user_rates)
        for (_, a), (_, b) in zip(base.iterrows(), ed.iterrows()):
            if pd.notna(b["Rate (Rs)"]) and abs(float(b["Rate (Rs)"]) - float(a["Rate (Rs)"])) > 1e-6:
                ur[a["Code"]] = float(b["Rate (Rs)"])
        _set(user_rates=ur)
        st.session_state["cost_ver"] = ver + 1
        st.rerun()
    if s.user_rates and st.button(f"Remove my {len(s.user_rates)} quoted rate(s)", key=f"cost_clear_{ver}"):
        _set(user_rates={})
        st.session_state["cost_ver"] = ver + 1
        st.rerun()


def _labour_editor(cost) -> None:
    s = cost_settings()
    ver = st.session_state.get("cost_ver", 0)
    rows = [{"WI": ln.code, "Work": ln.name, "Unit": ln.unit, "Qty": round(ln.qty, 2), "Rate (Rs)": round(ln.rate, 2),
             "Amount": round(ln.amount), "Source": ln.source} for ln in cost.lines if ln.kind == "labour"]
    base = pd.DataFrame(rows)
    st.caption("Labour-only (thekedar) rates per unit of work. Type your thekedar's rate to use it.")
    with st.form(f"cost_lab_form_{ver}", border=False):
        ed = st.data_editor(base, key=f"cost_lab_ed_{ver}", hide_index=True, width="stretch", height=420,
                            disabled=[c for c in base.columns if c != "Rate (Rs)"],
                            column_config={"Work": st.column_config.TextColumn(width="large"),
                                           "Amount": st.column_config.NumberColumn(format="localized")})
        ok = st.form_submit_button("Use my labour rates", type="primary")
    if ok:
        ul = dict(s.user_labour)
        for (_, a), (_, b) in zip(base.iterrows(), ed.iterrows()):
            if pd.notna(b["Rate (Rs)"]) and abs(float(b["Rate (Rs)"]) - float(a["Rate (Rs)"])) > 1e-6:
                ul[a["WI"]] = float(b["Rate (Rs)"])
        _set(user_labour=ul)
        st.session_state["cost_ver"] = ver + 1
        st.rerun()


def _quote_reader(res) -> None:
    from ai.llm import keys_from_mapping
    from pricing.quotes import ai_items, file_text, match_items, rule_items
    s = cost_settings()
    st.caption("Upload a quotation or bill from your supplier (PDF, photo, Excel) or paste its text. We read the items "
               "and prices, match them to your materials and convert the units - you confirm before anything changes.")
    up = st.file_uploader("Quotation / bill", type=["pdf", "png", "jpg", "jpeg", "xlsx", "csv", "txt"], key="quote_file")
    txt = st.text_area("...or paste the quotation text", height=120, key="quote_text",
                       placeholder="Lucky cement 50kg  1,460 / bag\nSarya G60 12mm  255,000 per ton")
    if st.button("\U0001f50d Read the quote", type="primary", disabled=not (up or txt.strip()), key="quote_read"):
        keys = keys_from_mapping(st.session_state)
        text = txt
        images = []
        if up is not None:
            data = up.getvalue()
            text = (text + "\n" + file_text(up.name, data)).strip()
            if up.name.lower().endswith((".png", ".jpg", ".jpeg")) or (up.name.lower().endswith(".pdf") and len(text) < 40):
                from ai.sketch_reader import files_to_images
                images = files_to_images([{"name": up.name, "bytes": data}])
        items, err = ([], "")
        if keys.any():
            items, err = ai_items(text, images, keys)
        if not items and text:
            items = rule_items(text)
        if err and not items:
            st.error(err)
        if images and not items and not keys.any():
            st.warning("Reading photos needs an AI key (sidebar). For now, paste the quote text.")
        st.session_state["quote_matches"] = match_items(items, [m.material for m in res.purchase_list()])
    matches = st.session_state.get("quote_matches") or []
    if not matches:
        return
    names = {m.material.mat_id: m.material.description for m in res.purchase_list()}
    opts = ["(skip)"] + list(names)
    rows = [{"Use": bool(m.mat_id and m.rate_db_unit), "Quote item": m.item.text, "Quoted price": m.item.price,
             "Per": m.item.unit, "Your material": m.mat_id or "(skip)", "Rate per material unit": m.rate_db_unit,
             "Material unit": m.db_unit, "Match": f"{m.score:.0%}", "Note": m.note} for m in matches]
    base = pd.DataFrame(rows)
    ed = st.data_editor(base, key="quote_editor", hide_index=True, width="stretch",
                        column_config={"Your material": st.column_config.SelectboxColumn(options=opts, width="large",
                                                                                         help="Change if the match is wrong"),
                                       "Rate per material unit": st.column_config.NumberColumn(min_value=0.0, format="%.2f")},
                        disabled=["Quote item", "Quoted price", "Per", "Material unit", "Match", "Note"])
    st.caption("Check each match - change 'Your material' where needed, untick 'Use' to skip a line.")
    if st.button("\u2705 Use these prices for my project", type="primary", key="quote_apply"):
        ur = dict(s.user_rates)
        n = 0
        for _, r in ed.iterrows():
            if r["Use"] and r["Your material"] != "(skip)" and pd.notna(r["Rate per material unit"]) and r["Rate per material unit"] > 0:
                ur[r["Your material"]] = float(r["Rate per material unit"])
                n += 1
        _set(user_rates=ur)
        st.session_state["quote_matches"] = []
        st.success(f"{n} price(s) from your quote are now used in the estimate.")
        st.rerun()


def _government(res, cost) -> None:
    from pricing.government import CITY_BOOK, edition_age_years, mrs_index
    s = cost_settings()
    books = mrs_index()
    district = CITY_BOOK.get(s.city if s.city in CITY_BOOK else "Lahore" if s.city in ("Faisalabad", "Multan") else "Islamabad")[0]
    bk = books.get(district, {})
    src = ("Balochistan CSR-2026 rates from real estimates (other items: Rawalpindi MRS +5%)" if s.city == "Quetta"
           else f"{bk.get('book', 'government rate book')} {bk.get('district', '')} {bk.get('edition', '')}")
    age = edition_age_years(bk) if bk else 0.0
    st.caption(f"How a government engineer would price the same BOQ (for PC-Is), using **{src}**"
               + (f" - this edition is {age:.1f} years old, so rates are brought to today." if age > 0.05 else " - the current edition.")
               + " Owners usually pay market prices - see the main figure.")
    c1, c2, c3, c4, c5 = st.columns(5)
    lab = c1.number_input("Labour increase / year %", 0.0, 30.0, float(s.labour_update_pct), 0.5, key="gov_lab",
                          help="Used only for older editions. Punjab MRS 2024 -> 2026 showed about +4% per year.")
    mat = c2.number_input("Materials increase / year %", -10.0, 30.0, float(getattr(s, "material_update_pct", 0.0)), 0.5, key="gov_mat")
    bst = c3.number_input("BST %", 0.0, 20.0, float(s.gov_bst_pct), 0.5, key="gov_bst")
    cons = c4.number_input("Consultancy %", 0.0, 10.0, float(s.gov_consultancy_pct), 0.5, key="gov_cons")
    cont = c5.number_input("Contingency %", 0.0, 10.0, float(s.gov_contingency_pct), 0.5, key="gov_cont")
    if (lab, mat, bst, cons, cont) != (s.labour_update_pct, getattr(s, "material_update_pct", 0.0), s.gov_bst_pct,
                                       s.gov_consultancy_pct, s.gov_contingency_pct):
        _set(labour_update_pct=lab, material_update_pct=mat, gov_bst_pct=bst, gov_consultancy_pct=cons, gov_contingency_pct=cont)
        st.rerun()
    gov, _uf = government(res, cost)
    m1, m2, m3 = st.columns(3)
    m1.metric("Government estimate", pkr(gov.total), f"{(gov.total / cost.total - 1) * 100:+.0f}% vs market" if cost.total else None,
              delta_color="off")
    m2.metric("Per sq ft", f"Rs {gov.total / max(cost.covered_sft, 1):,.0f}")
    m3.metric("Priced from the government book", f"{gov.mapped_share:.0%}")
    df = pd.DataFrame(gov.lines)
    st.dataframe(df, hide_index=True, width="stretch", height=420,
                 column_config={"Description": st.column_config.TextColumn(width="large"),
                                "Item": st.column_config.TextColumn("Book item", width="large"),
                                "Amount": st.column_config.NumberColumn(format="localized")})
    for label, v in gov.extras:
        st.caption(f"+ {label}: {pkr(v)}")


def _admin(res) -> None:
    pw = config.get_secret("ADMIN_PASSWORD", "") or ""
    if not pw:
        st.info("Price approvals are protected. Set **ADMIN_PASSWORD** in Streamlit secrets (or an environment variable) "
                "to use this page.")
        return
    if not st.session_state.get("admin_ok"):
        typed = st.text_input("Admin password", type="password", key="admin_pw")
        if st.button("Unlock", key="admin_unlock"):
            if typed == pw:
                st.session_state["admin_ok"] = True
                st.rerun()
            st.error("Wrong password.")
        return
    b = book()
    s = cost_settings()
    st.success("Admin unlocked.")
    fr = b.freshness(s.city)
    st.markdown(f"**Frequently changing materials in {s.city}** - {fr['n_live']} of {fr['n_items']} have live prices"
                + (f", latest {fr['latest']}" if fr["latest"] else "") + (f", {fr['n_stale']} older than 45 days" if fr["n_stale"] else ""))
    st.dataframe(pd.DataFrame([{"Item": r["name"], "Rate": r["rate"], "Unit": r["unit"], "Status": r["status"], "As of": r["as_of"],
                                "Source": r["source"]} for r in fr["rows"]]), hide_index=True, width="stretch")
    st.markdown(f"**Waiting for approval ({len(b.pending)})**")
    for p in list(b.pending):
        with st.container(border=True):
            c1, c2, c3 = st.columns([4, 1, 1])
            src = "; ".join(f"[{x.get('domain')}]({x.get('url')}): \u201c{x.get('quote', '')[:90]}\u201d" for x in p.sources[:3])
            c1.markdown(f"**{p.name}** \u00b7 {p.city}: Rs {p.old_rate:,.2f} \u2192 **Rs {p.new_rate:,.2f}** per {p.unit} "
                        f"({p.change_pct:+.1f}%) \u00b7 {p.reason}  \n{src}")
            if c2.button("Approve", key=f"ap_{p.key}"):
                b.approve(p, by="admin")
                b.save()
                reload_book()
                st.rerun()
            if c3.button("Reject", key=f"rj_{p.key}"):
                b.reject(p.key)
                b.save()
                reload_book()
                st.rerun()
    st.markdown("**Refresh prices now**")
    c1, c2 = st.columns(2)
    cities = c1.multiselect("Cities", CITIES, default=[s.city if s.city in CITIES else "Islamabad"], key="adm_cities")
    items = c2.multiselect("Items", list(LIVE_ITEMS), default=["CON-001", "RBR-002", "MAS-001"],
                           format_func=lambda k: LIVE_ITEMS[k]["name"], key="adm_items")
    if st.button("\U0001f504 Search the web for these prices", key="adm_run", disabled=not (cities and items)):
        from ai.llm import keys_from_mapping
        from pricing.agent import PriceAgent, default_search
        keys = keys_from_mapping(st.session_state)
        log = st.empty()
        agent = PriceAgent(b, keys=keys if keys.any() else None,
                           search=default_search(config.get_secret("TAVILY_API_KEY", "") or "", config.get_secret("BRAVE_API_KEY", "") or ""),
                           log=lambda m: log.caption(m))
        with st.spinner("The price agent is searching and reading pages..."):
            rep = agent.run(cities=cities, items=items)
        reload_book()
        st.session_state["adm_report"] = rep.markdown()
        st.rerun()
    if st.session_state.get("adm_report"):
        with st.expander("Last run report", expanded=True):
            st.markdown(st.session_state["adm_report"])
    st.caption("The weekly GitHub Action (.github/workflows/update-prices.yml) runs the same agent and commits the rates. "
               "On Streamlit Cloud, changes made here last until the app restarts.")
    st.markdown("**Import a new rate book** - Punjab MRS (any district), KP MRS or Sindh CSR PDF. The newest edition per city is used.")
    mrs = st.file_uploader("MRS PDF", type=["pdf"], key="adm_mrs")
    if mrs is not None and st.button("Import this MRS", key="adm_mrs_go"):
        import tempfile
        from pathlib import Path

        from pricing.government import RATES_DIR
        from pricing.mrs import parse_mrs, save
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as fh:
            fh.write(mrs.getvalue())
        with st.spinner("Reading the MRS tables..."):
            data = parse_mrs(fh.name)
            path = save(data, Path(RATES_DIR))
        st.success(f"Imported {len(data['items']):,} rates: {data.get('book', 'MRS')} {data['district']} {data['edition']} ({path.name}).")


# ---------------------------------------------------------------- the step
def render_cost_step(res) -> None:
    _settings_bar()
    cost, _sched = current_cost(res)
    if not cost.lines:
        st.info("Nothing to price in the selected scope.")
        return
    _headline(cost)
    tabs = st.tabs(["\U0001f4ca Where the money goes", "\U0001f4c5 Money needed each month", "\U0001f6d2 Materials & rates",
                    "\U0001f477 Labour rates", "\U0001f4c4 Upload a quote", "\U0001f3db\ufe0f Government estimate",
                    "\U0001f504 Price updates (admin)"], key="cost_tabs")
    with tabs[0]:
        _where_money_goes(cost)
    with tabs[1]:
        _cashflow(cost)
    with tabs[2]:
        _materials_editor(cost)
    with tabs[3]:
        _labour_editor(cost)
    with tabs[4]:
        _quote_reader(res)
    with tabs[5]:
        _government(res, cost)
    with tabs[6]:
        _admin(res)
    from pricing.export import build_cost_workbook, cost_pdf
    pi = st.session_state.get("project_inputs")
    name = (pi.project_name if pi and pi.project_name not in ("", "Untitled Project") else "My house")
    fn = name.replace(" ", "_")
    gov, _uf = government(res, cost)
    d1, d2 = st.columns(2)
    d1.download_button("\U0001f4b0 Cost estimate (Excel)", data=lambda: build_cost_workbook(cost, name, gov),
                       file_name=f"{fn}_Cost_Estimate.xlsx", type="primary", width="stretch", key="cost_dl_xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    d2.download_button("\U0001f5a8\ufe0f Cost summary (PDF)", data=lambda: cost_pdf(cost, name, gov),
                       file_name=f"{fn}_Cost_Summary.pdf", mime="application/pdf", width="stretch", key="cost_dl_pdf")
