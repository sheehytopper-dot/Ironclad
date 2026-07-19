"""Tests for the display-only formatting layer (ui/format.py — Phase 5
usability pass, Tier 1; pure, browser-free).

THE CRITICAL GUARDRAIL, §25-discriminating: every formatter test asserts
BOTH the display string AND that ``report.frame`` stays byte-identical
(``assert_frame_equal(check_exact=True)`` + the exact full-precision
float) — the test fails if formatting corrupts, rounds, or mutates the
underlying data the builders/exporters operate on.
"""
from pathlib import Path

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from engine.reports import Period, Unit, cash_flow, occupancy
from ui import format as fmt
from ui import state

CLOROX = (Path(__file__).resolve().parents[1] / "golden" /
          "clorox_northlake" / "clorox_northlake.icprop.json")


@pytest.fixture(scope="module")
def clorox():
    model, error = state.load_model(CLOROX)
    assert error is None
    result, error = state.run_model(model)
    assert error is None
    return model, result


def _cash_flow(model, result, unit=Unit.total):
    return cash_flow(result, unit=unit, period=Period.fiscal,
                     fiscal_year_end_month=model.property
                     .fiscal_year_end_month,
                     analysis_begin=model.property.analysis_begin)


class TestScalars:
    def test_money_accounting_style(self):
        assert fmt.money(2_596_319.4000000004) == "2,596,319"
        assert fmt.money(-54_675.4) == "(54,675)"
        assert fmt.money(4.8083, 2) == "4.81"
        assert fmt.money(None) == ""
        assert fmt.money(float("nan")) == ""

    def test_percent(self):
        assert fmt.percent(3.0864, 2) == "3.09%"
        assert fmt.percent(0.803174, 1, from_fraction=True) == "80.3%"
        assert fmt.percent(None) == ""


class TestReportDisplayGuardrail:
    def test_total_display_and_frame_untouched(self, clorox):
        """The §25 pair: right display string AND byte-identical frame."""
        model, result = clorox
        report = _cash_flow(model, result)
        before = report.frame.copy(deep=True)
        display = fmt.report_display(report)
        # display: 0 decimals, thousands, parens
        assert display.loc["Net Operating Income"].iloc[0] == "2,596,319"
        assert display.loc["Common Area Maintenance"].iloc[0] == "(331,574)"
        # the underlying frame: byte-identical, full precision intact
        assert_frame_equal(report.frame, before, check_exact=True)
        assert report.frame.loc["Net Operating Income"].iloc[0] == \
            2596319.4000000004
        # and the display is a DIFFERENT object holding strings
        assert display is not report.frame
        assert all(isinstance(v, str) for v in display.iloc[:, 0])

    def test_per_sf_two_decimals(self, clorox):
        model, result = clorox
        report = _cash_flow(model, result, unit=Unit.per_sf)
        before = report.frame.copy(deep=True)
        display = fmt.report_display(report)
        assert display.loc["Net Operating Income"].iloc[0] == "4.81"
        assert_frame_equal(report.frame, before, check_exact=True)

    def test_occupancy_percent_and_sf(self, clorox):
        model, result = clorox
        report = occupancy(result, period=Period.annual,
                           fiscal_year_end_month=model.property
                           .fiscal_year_end_month)
        before = report.frame.copy(deep=True)
        display = fmt.report_display(report)
        row = display.iloc[0]
        assert row["occupancy"] == "100.0%"          # fraction ×100, display
        assert row["rentable_area"] == "540,000"
        assert_frame_equal(report.frame, before, check_exact=True)
        assert report.frame.iloc[0]["occupancy"] == 1.0   # still a fraction

    def test_frame_display_generic(self):
        frame = pd.DataFrame({"tenant": ["A"], "area": [12_000.0],
                              "share": [0.803174],
                              "fiscal_year": [2027],
                              "base_rent_psf_yr": [7.1512]})
        before = frame.copy(deep=True)
        display = fmt.frame_display(frame)
        assert display.iloc[0]["area"] == "12,000"
        assert display.iloc[0]["share"] == "80.3%"
        assert display.iloc[0]["fiscal_year"] == "2027"   # plain, no comma
        assert display.iloc[0]["base_rent_psf_yr"] == "7.15"
        assert_frame_equal(frame, before, check_exact=True)


class TestCashFlowStyler:
    def test_tree_indent_bold_and_guardrail(self, clorox):
        model, result = clorox
        report = _cash_flow(model, result)
        before = report.frame.copy(deep=True)
        styler = fmt.cash_flow_display(report)
        data = styler.data
        tree = report.meta.extra["tree"]
        # detail rows indented by level (NBSP), subtotals flush left
        base_i = next(i for i, n in enumerate(tree)
                      if n["account"] == "Base Rental Revenue")
        noi_i = next(i for i, n in enumerate(tree)
                     if n["account"] == "Net Operating Income")
        assert data.index[base_i] == " " * 4 + "Base Rental Revenue"
        assert data.index[noi_i] == "Net Operating Income"   # level 0
        # values formatted at the unit's decimals
        assert data.iloc[noi_i, 0] == "2,596,319"
        # bold styling applied to subtotal rows (rendering smoke)
        html = styler.to_html()
        assert "font-weight: bold" in html
        # the guardrail: report.frame untouched by building the styler
        assert_frame_equal(report.frame, before, check_exact=True)

    def test_column_slice_is_display_only(self, clorox):
        model, result = clorox
        report = _cash_flow(model, result)
        before = report.frame.copy(deep=True)
        styler = fmt.cash_flow_display(report,
                                       columns=report.frame.columns[1:3])
        assert list(styler.data.columns) == list(report.frame.columns[1:3])
        assert_frame_equal(report.frame, before, check_exact=True)
