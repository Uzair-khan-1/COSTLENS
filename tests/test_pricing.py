"""Costing: rate book & provenance, contract types, cash flow, MRS import, government estimate, quotes, price agent."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from ai.extraction import default_building_params
from detailed_mto import build_project, compute
from engineering import plot_templates
from knowledge import load_knowledge_base
from models.schemas import ProjectInputs
from pricing.base_rates import LABOUR, LIVE_ITEMS, R
from pricing.costing import CostSettings, compute_cost, pkr, wi_market_costs
from pricing.ratebook import Proposal, RateBook
from scheduling import ScheduleSettings
from scheduling.planner import plan_for_target

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def kb():
    return load_knowledge_base()


@pytest.fixture(scope="module")
def res(kb):
    pi = ProjectInputs(project_name="cost", plot_marla=5)
    params = plot_templates.build_template_params(pi) or default_building_params()
    return compute(build_project(pi, params, kb), kb)


@pytest.fixture()
def book(tmp_path):
    return RateBook(tmp_path)


def test_every_material_and_work_item_has_a_rate(kb):
    assert set(kb.materials) <= set(R), set(kb.materials) - set(R)
    assert set(kb.work_items) <= set(LABOUR)
    for k, (t, lo, hi) in R.items():
        assert lo <= t <= hi, k


def test_rate_lookup_order_and_provenance(book):
    ind = book.rate("CON-001", "Lahore")
    assert ind.status == "indicative" and ind.source
    p = Proposal("Lahore", "CON-001", "Cement", ind.rate, 1500.0, 1480.0, 1520.0, "bag", 0.0,
                 [{"url": "https://www.dawn.com/x", "domain": "dawn.com", "quote": "cement Rs 1,500 per bag", "trusted": True}])
    book.approve(p)
    live = book.rate("CON-001", "Lahore")
    assert live.status == "live" and live.rate == 1500.0 and "dawn" in live.source
    assert book.rate("CON-001", "Faisalabad").rate == 1500.0  # Faisalabad uses Lahore rates
    assert book.rate("CON-001", "Lahore", {"CON-001": 1450.0}).status == "user"
    # followers move with their leader (#3 bar follows the #4 bar)
    p2 = Proposal("Lahore", "RBR-002", "Steel", 262.0, 250.0, 245.0, 255.0, "kg", -4.6, [{"url": "u", "domain": "d"}])
    book.approve(p2)
    assert book.rate("RBR-001", "Lahore").status == "live" and book.rate("RBR-001", "Lahore").follows == "RBR-002"
    book.save()
    again = RateBook(book.folder)
    assert again.rate("CON-001", "Lahore").rate == 1500.0 and again.history


def test_contract_types_and_extras(res, book):
    base = dict(city="Rawalpindi")
    lab = compute_cost(res, CostSettings(contract="labour", **base), book)
    grey = compute_cost(res, CostSettings(contract="grey", **base), book)
    turn = compute_cost(res, CostSettings(contract="turnkey", **base), book)
    assert lab.materials == grey.materials == turn.materials and lab.labour == turn.labour
    assert lab.profit < grey.profit < turn.profit and lab.total < grey.total < turn.total
    assert abs(lab.profit - lab.labour * 0.10) < 1
    assert lab.low < lab.total < lab.high
    ext = compute_cost(res, CostSettings(contract="labour", extras_on={"approval": True, "soil": True}, **base), book)
    assert ext.total > lab.total and len(ext.extras) == 2
    assert 3000 < lab.per_sft < 15000
    assert not any(ln.code == "MSC-008" for ln in lab.lines)  # approvals are an owner extra, not a material


def test_user_quote_changes_the_total(res, book):
    a = compute_cost(res, CostSettings(city="Lahore"), book)
    b = compute_cost(res, CostSettings(city="Lahore", user_rates={"CON-001": 2000.0}), book)
    cem = next(ln for ln in a.lines if ln.code == "CON-001")
    assert b.materials - a.materials == pytest.approx(cem.qty * (2000.0 - cem.rate), rel=1e-6)


def test_cash_flow_follows_the_schedule(res, book):
    plan = plan_for_target(res, 8, ScheduleSettings(start_date="2026-10-05"))
    c = compute_cost(res, CostSettings(escalation_pct_month=1.0), book, plan.schedule)
    assert c.cashflow and c.escalation > 0
    assert abs(sum(m["Total"] for m in c.cashflow) - c.total) / c.total < 0.01
    assert c.cashflow[-1]["Cumulative"] == pytest.approx(sum(m["Total"] for m in c.cashflow))
    flat = compute_cost(res, CostSettings(escalation_pct_month=0.0), book, plan.schedule)
    assert flat.escalation == 0 and flat.total < c.total


def test_mrs_import_and_government_estimate(res, book):
    from pricing.government import MRS_MAP, government_estimate, mrs_index, update_factors
    idx = mrs_index()
    assert "Rawalpindi" in idx and len(idx["Rawalpindi"]["items"]) > 3000
    keys = {f"{i['chapter']}-{i['item_no']}-{i['sub']}" for i in idx["Rawalpindi"]["items"]}
    missing = [k for v in MRS_MAP.values() for k, _m in v if k not in keys]
    assert not missing, missing
    c = compute_cost(res, CostSettings(city="Rawalpindi"), book)
    uf = update_factors(book)
    wc, loose = wi_market_costs(c, res)
    g = government_estimate(res, "Rawalpindi", uf, wc, loose_materials=loose)
    assert g.mapped_share > 0.3 and 0.5 < g.total / c.total < 1.6
    assert any("BST" in n for n, _v in g.extras)
    q = government_estimate(res, "Quetta", uf, wc, loose_materials=loose)
    assert any("CSR-2026" in ln["Source"] for ln in q.lines)


def test_mrs_parser_on_the_real_pdf():
    pdf = "/mnt/user-data/uploads/749929552-MRS-Rawalpindi-2nd-Bi-annual.pdf"
    if not os.path.exists(pdf):
        pytest.skip("MRS PDF not available")
    from pricing.mrs import parse_mrs
    d = parse_mrs(pdf)
    assert d["district"] == "Rawalpindi" and d["edition"] == "2024-2"
    brick = [i for i in d["items"] if i["chapter"] == 7 and i["item_no"] == "5" and i["sub"] == "i.4"][0]
    assert brick["unit"].startswith("100") and brick["labour"] == 11083.8 and brick["composite"] == 40207.0


def test_quote_reader_rules_and_units(kb):
    from pricing.quotes import convert, match_items, rule_items
    txt = ("Lucky Cement 50kg OPC   1,460 / bag\nAmreli Sarya G60 12mm   255,000 per ton\n"
           "Bricks A class awwal   17,500 per 1000\nPorcelain floor tiles 24x24   275 sft\nInvoice total 999,999")
    ms = match_items(rule_items(txt), kb.materials.values())
    got = {m.mat_id: m.rate_db_unit for m in ms}
    assert got["CON-001"] == 1460 and got["RBR-002"] == 255.0 and got["MAS-001"] == 17.5 and got["FLR-001"] == 275
    assert len(ms) == 4  # the 'total' line is ignored
    assert convert(40.0, "maund", "kg") is not None and convert(1.0, "sqm", "sft") == pytest.approx(1 / 10.7639)


def test_price_agent_auto_approves_and_queues(book):
    from pricing.agent import PriceAgent
    page = ("<html><body><p>Cement price in Lahore today: Rs 1,470 per bag (Lucky, DG Khan).</p>"
            "<p>Steel sarya rate in Lahore Rs 300 per kg</p></body></html>")
    from pricing.agent import html_to_text

    def search(q):
        return [{"url": "https://www.dawn.com/cement", "title": "rates"}, {"url": "https://unknown-blog.pk/steel", "title": "x"}]

    agent = PriceAgent(book, search=search, fetch=lambda u: html_to_text(page), pause_s=0)
    r1 = agent.update_item("CON-001", "Lahore")
    assert r1.status in ("auto-approved", "pending") and r1.new_rate == 1470
    before = book.rate("CON-001", "Lahore").rate
    if r1.status == "auto-approved":
        assert before == 1470 and book.rate("CON-001", "Lahore").status == "live"
    r2 = agent.update_item("RBR-002", "Lahore")
    assert r2.status in ("pending", "rejected")  # +15 % from the indicative rate: needs a human
    assert any(p.mat_id == "RBR-002" for p in book.pending)


def test_pkr_format():
    assert pkr(15_200_000) == "Rs 1.52 crore" and pkr(4_530_000) == "Rs 45.3 lakh" and pkr(12_500) == "Rs 12,500"


def test_cost_workbook_and_pdf(res, book):
    from pricing.export import build_cost_workbook, cost_pdf
    from openpyxl import load_workbook
    import io
    c = compute_cost(res, CostSettings(), book, plan_for_target(res, 8, ScheduleSettings(start_date="2026-10-05")).schedule)
    wb = load_workbook(io.BytesIO(build_cost_workbook(c, "T")))
    assert {"Cost_Summary", "Materials_Priced", "Labour_Priced", "Cash_Flow"} <= set(wb.sheetnames)
    assert str(wb["Materials_Priced"]["G5"].value).startswith("=E5*F5")
    assert cost_pdf(c, "T")[:4] == b"%PDF"
