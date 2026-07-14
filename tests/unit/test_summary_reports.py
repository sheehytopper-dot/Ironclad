"""Unit tests for the Phase 4 Step 5 summary / echo + Resale Matrix reports:
Executive Summary (#2), Assumptions Report (#3), Sources & Uses (#4),
Resale Matrix (#7), Input Assumptions listing (#23) —
engine/reports/summary_reports.py and engine/reports/valuation_reports.py.

Acceptance (NEXT_STEPS_TO_PHASE4 Step 5): each reconciles to its source;
Sources & Uses ties to the below-the-line ledger columns; the Resale Matrix
each cell equals a direct single-point resale (the §21 cross-check).
Building area is the run's rentable area, never a summed-contract-area
(DEVIATIONS §25). Engineered valuation property (no golden populates
valuation).
"""
import datetime as dt

import numpy as np
import pandas as pd
import pytest

from engine.calc.ledger import NOI, to_annual
from engine.calc.resale import compute_resale
from engine.calc.run import run_property
from engine.reports import (
    Report,
    assumptions_report,
    executive_summary,
    input_assumptions_listing,
    reconcile_executive_summary,
    reconcile_resale_matrix,
    reconcile_sources_and_uses,
    resale_matrix,
    sources_and_uses,
)
from engine.models import (
    AreaMeasures,
    ExpenseItem,
    ExpenseUnit,
    Inflation,
    Lease,
    MoneyRate,
    MoneyUnit,
    PropertyInfo,
    PropertyModel,
    Purchase,
    RentableAreaMode,
    TimingBasis,
    UponExpiration,
    YearRate,
)
from engine.models.investment import ClosingCost, Loan, LoanAmount, LoanCosts
from engine.models.valuation import (
    DirectCap,
    Resale,
    SensitivityIntervals,
    ValuationInputs,
)

BEGIN = dt.date(2026, 1, 1)
PSF_YR = MoneyUnit.dollars_per_area_per_year
FLAT = Inflation(general_rate=[YearRate(year=1, rate=0.0)],
                 timing_basis=TimingBasis.analysis_year)


def val_model(*, price=1_250_000.0, loans=True, closing=25_000.0,
              direct_cap=False, resale_method="cap_noi_current_year",
              exit_cap=8.0):
    lease = Lease(tenant_name="T", area=12_000, lease_type="industrial",
                  start_date=BEGIN, term_months=240,
                  base_rent=MoneyRate(amount=10.0, unit=PSF_YR),
                  upon_expiration=UponExpiration.vacate)
    loan_list = [Loan(name="Mortgage", amount=LoanAmount(value=600_000.0),
                      term_months=360, rate=6.0,
                      amortization="fully_amortizing",
                      loan_costs=LoanCosts(points_pct=1.0))] if loans else []
    return PropertyModel(
        property=PropertyInfo(name="Vista Tower", property_type="industrial",
                              analysis_begin=BEGIN, analysis_term_years=5),
        area_measures=AreaMeasures(
            property_size=12_000, rentable_area_mode=RentableAreaMode.fixed,
            rentable_area_fixed=12_000),
        inflation=FLAT, rent_roll=[lease],
        expenses=[ExpenseItem(name="OpEx", amount=20_000.0,
                              unit=ExpenseUnit.dollars_per_year,
                              recoverable=False)],
        loans=loan_list,
        purchase=(Purchase(price=price,
                           closing_costs=[ClosingCost(name="Legal",
                                                      amount=closing)])
                  if price is not None else None),
        valuation=ValuationInputs(
            discount_rate=8.0, discount_method="annual",
            period_convention="end_of_period",
            direct_cap=(DirectCap(cap_rate=8.0) if direct_cap else None),
            resale=Resale(method=resale_method, exit_cap_rate=exit_cap,
                          selling_costs_pct=3.0),
            sensitivity_intervals=SensitivityIntervals(
                discount_rate_step=1.0, cap_rate_step=1.0, count=5)))


@pytest.fixture(scope="module")
def model():
    return val_model(direct_cap=True)


@pytest.fixture(scope="module")
def result(model):
    return run_property(model)


class TestSourcesAndUses:
    def test_ties_to_ledger_columns_and_balances(self, result):
        report = sources_and_uses(result)
        assert isinstance(report, Report) and report.meta.number == 4
        diffs = reconcile_sources_and_uses(report, result)
        assert diffs.abs().max() == pytest.approx(0.0, abs=1e-6)

    def test_acquisition_sources_equal_uses(self, result):
        report = sources_and_uses(result)
        acq = report.frame[report.frame["phase"] == "Acquisition"]
        sources = acq[acq["category"] == "source"]["amount"].sum()
        uses = acq[acq["category"] == "use"]["amount"].sum()
        assert sources == pytest.approx(uses)
        # equity = uses − loan proceeds = (1.25M + 25k + 6k) − 600k
        by_item = report.frame.set_index("item")["amount"]
        assert by_item["Equity"] == pytest.approx(1_281_000.0 - 600_000.0)

    def test_disposition_lines_tie_to_resale(self, result):
        report = sources_and_uses(result)
        by_item = report.frame.set_index("item")["amount"]
        assert by_item["Net Resale Proceeds"] == pytest.approx(
            result.resale.net_unleveraged)
        assert by_item["Loan Payoff at Resale"] == pytest.approx(
            sum(result.resale.loan_payoffs.values()))

    def test_no_purchase_no_debt_still_reconciles(self):
        res = run_property(val_model(price=None, loans=False))
        report = sources_and_uses(res)
        diffs = reconcile_sources_and_uses(report, res)
        assert diffs.abs().max() == pytest.approx(0.0, abs=1e-9)
        # no negative-zero purchase line
        by_item = report.frame.set_index("item")["amount"]
        assert by_item["Purchase Price"] == 0.0
        assert str(by_item["Purchase Price"]) != "-0.0"


class TestExecutiveSummary:
    def test_reconciles_to_ledger_and_valuation(self, result, model):
        report = executive_summary(result, model)
        assert report.meta.number == 2
        diffs = reconcile_executive_summary(report, result, model)
        assert diffs.abs().max() == pytest.approx(0.0, abs=1e-6)

    def test_year1_and_going_in_cap(self, result, model):
        frame = executive_summary(result, model).frame.set_index("metric")
        y1_noi = float(to_annual(result.ledger.frame, BEGIN).loc[1, NOI])
        assert frame.loc["Year-1 NOI", "value"] == pytest.approx(y1_noi)
        # going-in cap = 100,000 / 1,250,000 = 8.0%
        assert frame.loc["Going-in Cap Rate (%)", "value"] == pytest.approx(8.0)
        assert frame.loc["Year-1 Occupancy (%)", "value"] == pytest.approx(100.0)

    def test_building_area_is_rentable_not_summed_contract(self):
        """DEVIATIONS §25 regression — run on a fixture where the RIGHT
        answer differs from the WRONG one, so the test can actually fail.
        Freeport's rentable area (123,099, fixed) ≠ its summed contract area
        (128,087) — a 4,988 SF gap (suite-100 OKI double-entry + the fixed-
        rentable gap). The synthetic 12,000/12,000 fixture cannot detect a
        switch to summed-contract-area (both numbers are 12,000); Freeport
        can. The assertions below FAIL if executive_summary is changed to sum
        the contract-segment areas."""
        from pathlib import Path
        from engine.models.io import load_property
        fixture = (Path(__file__).resolve().parents[1] / "golden" /
                   "freeport" / "freeport.icprop.json")
        fp_model = load_property(fixture)
        res = run_property(fp_model)
        rentable = float(res.rentable_area.iloc[0])
        summed_contract = sum(
            next(s for s in segs if not s.speculative).area
            for segs in res.segments.values())
        # the fixture MUST discriminate — the two answers genuinely differ
        assert rentable == pytest.approx(123_099.0)
        assert summed_contract == pytest.approx(128_087.0)
        assert rentable != pytest.approx(summed_contract)
        reported = float(executive_summary(res, fp_model).frame
                         .set_index("metric").loc["Rentable Area (SF)", "value"])
        assert reported == pytest.approx(rentable)          # the right answer
        assert reported != pytest.approx(summed_contract)   # NOT the wrong one

    def test_none_valuation_metrics_are_nan(self, result, model):
        """direct_cap present here → a number; but a no-direct-cap /
        no-loan model must render those blank, never zero."""
        no_dc = run_property(val_model(direct_cap=False, loans=False))
        frame = executive_summary(no_dc, val_model(direct_cap=False,
                                                   loans=False)).frame
        by = frame.set_index("metric")["value"]
        assert np.isnan(by["Direct Cap Value"])
        assert np.isnan(by["Leveraged PV"])

    def test_no_valuation_section_when_unset(self):
        """A model with no valuation/purchase yields the property + year-1
        rows only (no valuation rows), and still builds."""
        model = PropertyModel(
            property=PropertyInfo(name="Bare", property_type="industrial",
                                  analysis_begin=BEGIN, analysis_term_years=3),
            area_measures=AreaMeasures(
                property_size=12_000, rentable_area_mode=RentableAreaMode.fixed,
                rentable_area_fixed=12_000),
            inflation=FLAT,
            rent_roll=[Lease(tenant_name="T", area=12_000,
                             lease_type="industrial", start_date=BEGIN,
                             term_months=60,
                             base_rent=MoneyRate(amount=10.0, unit=PSF_YR),
                             upon_expiration=UponExpiration.vacate)])
        report = executive_summary(run_property(model), model)
        assert report.meta.extra["has_valuation"] is False
        metrics = set(report.frame["metric"])
        assert "Unleveraged PV" not in metrics
        assert "Year-1 NOI" in metrics


class TestAssumptions:
    def test_sectioned_and_flat_echo_same_count(self, model):
        a3 = assumptions_report(model)
        a23 = input_assumptions_listing(model)
        assert a3.meta.number == 3 and a23.meta.number == 23
        assert len(a3.frame) == len(a23.frame)  # same underlying echo

    def test_echoes_model_inputs(self, model):
        frame = assumptions_report(model).frame
        by = frame.set_index("assumption")["value"]
        assert by["Name"] == "Vista Tower"
        assert by["Analysis Term (years)"] == "5"
        assert by["Discount Rate (%)"] == "8.0"
        assert by["Exit Cap Rate (%)"] == "8.0"

    def test_flat_listing_prefixes_section(self, model):
        frame = input_assumptions_listing(model).frame
        assert "Property · Name" in set(frame["assumption"])


class TestResaleMatrix:
    def test_cross_check_each_cell_is_direct_single_point(self, result, model):
        """§21 cross-check (the acceptance): every cell equals a direct
        single-point compute_resale at that resale year and exit cap."""
        report = resale_matrix(result, model)
        assert report.meta.number == 7
        base = model.valuation.resale
        for cap in report.frame.columns:
            for year in report.frame.index:
                end = result.months[0] + 12 * year - 1
                direct = compute_resale(
                    base.model_copy(update={
                        "exit_cap_rate": cap,
                        "resale_date": end.to_timestamp().date()}),
                    result.ledger, result.months, result.occupancy, model,
                    result.loan_schedules).net_unleveraged
                assert report.frame.loc[year, cap] == pytest.approx(
                    direct, abs=1e-6)

    def test_independent_anchor_and_monotonicity(self, result, model):
        report = resale_matrix(result, model)
        checks = reconcile_resale_matrix(report, result, model)
        # base cap / run's resale year cell == the RunResult's own resale
        assert checks["anchor_diff"] == pytest.approx(0.0, abs=1e-6)
        # net resale strictly decreases as exit cap rises (value = income/cap)
        assert checks["monotonicity_violations"] == 0.0

    def test_axes_shape_and_base_cap_centered(self, result, model):
        report = resale_matrix(result, model)
        assert report.frame.shape == (5, 5)          # 5 years × 5 caps
        assert list(report.frame.index) == [1, 2, 3, 4, 5]
        assert report.frame.columns[2] == pytest.approx(8.0)  # base cap centered

    def test_requires_cap_method(self):
        model = val_model()  # valid cap model, then swap in a fixed sale price
        model.valuation.resale = Resale(method="fixed_amount",
                                        fixed_amount=2_000_000.0)
        res = run_property(model)
        with pytest.raises(ValueError, match="cap-rate resale method"):
            resale_matrix(res, model)
