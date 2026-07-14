"""Unit tests for the Phase 4 Step 3 valuation report family:
IRR Matrix (#5), Value Matrix (#6), Valuation & Return Summary (#8),
Present Value (#9) — engine/reports/valuation_reports.py — and Loan
Amortization (#20) — engine/reports/loan_amortization.py.

These are thin views over data already on ``RunResult`` (sensitivity,
ValuationResult, loan schedules), so the acceptance (NEXT_STEPS_TO_PHASE4
Step 3) is reconciliation to that source: each report equals its
RunResult source; the IRR-matrix center cell equals the ValuationResult
IRR (the §21 cross-check — a model priced at the grid's base price/cap);
the Present Value column sums to the ValuationResult PV; the Loan Amort
schedule ties to the ledger's Interest / Principal / Loan Costs lines.

No golden populates ``valuation`` (verified 2026-07-11) — engineered
tests only, on the flat 100,000-NOI property the sensitivity/valuation
unit tests already hand-check.
"""
import datetime as dt

import numpy as np
import pandas as pd
import pytest

from engine.calc.ledger import (
    INTEREST_EXPENSE,
    LOAN_COSTS,
    PRINCIPAL_PAYMENTS,
)
from engine.calc.run import run_property
from engine.reports import (
    Report,
    irr_matrix,
    loan_amortization,
    present_value,
    reconcile_loan_amortization,
    reconcile_matrix_to_source,
    reconcile_present_value,
    reconcile_valuation_summary,
    valuation_summary,
    value_matrix,
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
from engine.models.investment import ClosingCost, Loan, LoanAmount
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


def flat_model(*, price=None, loans=(), direct_cap=None, closing_costs=(),
               count=5):
    """The sensitivity/valuation hand-check property: $10/SF/yr on 12,000
    SF, non-recoverable OpEx 20,000/yr → flat NOI 100,000/yr."""
    lease = Lease(tenant_name="T", area=12_000, lease_type="industrial",
                  start_date=BEGIN, term_months=240,
                  base_rent=MoneyRate(amount=10.0, unit=PSF_YR),
                  upon_expiration=UponExpiration.vacate)
    return PropertyModel(
        property=PropertyInfo(name="Val", property_type="industrial",
                              analysis_begin=BEGIN, analysis_term_years=5),
        area_measures=AreaMeasures(
            property_size=12_000, rentable_area_mode=RentableAreaMode.fixed,
            rentable_area_fixed=12_000),
        inflation=FLAT, rent_roll=[lease],
        expenses=[ExpenseItem(name="OpEx", amount=20_000.0,
                              unit=ExpenseUnit.dollars_per_year,
                              recoverable=False)],
        loans=list(loans),
        purchase=(Purchase(price=price, closing_costs=list(closing_costs))
                  if price is not None else None),
        valuation=ValuationInputs(
            discount_rate=8.0, discount_method="annual",
            period_convention="end_of_period",
            resale=Resale(method="cap_noi_current_year", exit_cap_rate=8.0,
                          selling_costs_pct=0.0),
            direct_cap=direct_cap,
            sensitivity_intervals=SensitivityIntervals(
                discount_rate_step=1.0, cap_rate_step=1.0, count=count)),
    )


def a_loan(**kw):
    kw.setdefault("name", "Mortgage")
    kw.setdefault("amount", LoanAmount(value=600_000.0))
    kw.setdefault("term_months", 360)
    kw.setdefault("rate", 6.0)
    kw.setdefault("amortization", "fully_amortizing")
    return Loan(**kw)


@pytest.fixture(scope="module")
def result():
    return run_property(flat_model(price=1_250_000.0, loans=[a_loan()],
                                   direct_cap=DirectCap(cap_rate=8.0)))


@pytest.fixture(scope="module")
def result_no_loans():
    return run_property(flat_model(price=1_250_000.0))


class TestValueMatrix:
    def test_thin_view_reconciles_to_sensitivity(self, result):
        report = value_matrix(result)
        assert isinstance(report, Report) and report.meta.number == 6
        diff = reconcile_matrix_to_source(report, result)
        assert diff.abs().to_numpy().max() == pytest.approx(0.0, abs=1e-9)

    def test_diagonal_is_noi_over_cap(self, result):
        """A flat 100,000 NOI: the discount==cap diagonal equals
        100,000/cap (the sensitivity hand-check, surfaced in the report)."""
        frame = value_matrix(result).frame
        for cap in frame.columns:
            assert frame.loc[cap, cap] == pytest.approx(
                100_000.0 / (cap / 100.0), abs=0.01)


class TestIRRMatrix:
    def test_unleveraged_thin_view_reconciles(self, result):
        report = irr_matrix(result)
        assert report.meta.number == 5 and report.meta.extra["leveraged"] is False
        diff = reconcile_matrix_to_source(report, result)
        assert diff.abs().to_numpy().max() == pytest.approx(0.0, abs=1e-9)

    def test_leveraged_thin_view_reconciles(self, result):
        report = irr_matrix(result, leveraged=True)
        assert report.meta.extra["leveraged"] is True
        diff = reconcile_matrix_to_source(report, result)
        assert diff.abs().to_numpy().max() == pytest.approx(0.0, abs=1e-9)

    def test_center_cell_equals_valuation_irr(self, result):
        """§21 cross-check: the model is priced at 1,250,000 = the base
        unleveraged PV (flat NOI 100k at 8%), which is the grid's center
        price. So the IRR-matrix center cell equals the ValuationResult's
        unleveraged IRR (both the discount rate, 8%)."""
        report = irr_matrix(result)
        center = report.frame.shape[0] // 2
        assert report.frame.iloc[center, center] == pytest.approx(
            result.valuation.unleveraged_irr, abs=1e-6)
        assert report.frame.iloc[center, center] == pytest.approx(8.0, abs=1e-6)

    def test_leveraged_center_matches_valuation_leveraged_irr(self, result):
        report = irr_matrix(result, leveraged=True)
        center = report.frame.shape[0] // 2
        assert report.frame.iloc[center, center] == pytest.approx(
            result.valuation.leveraged_irr, abs=1e-6)

    def test_leveraged_all_nan_without_loans(self, result_no_loans):
        report = irr_matrix(result_no_loans, leveraged=True)
        assert report.frame.isna().to_numpy().all()
        # ...and reconciliation still holds (NaN ↔ NaN matches)
        diff = reconcile_matrix_to_source(report, result_no_loans)
        assert diff.abs().to_numpy().max() == pytest.approx(0.0, abs=1e-9)


class TestValuationSummary:
    def test_echoes_valuation_result_exactly(self, result):
        report = valuation_summary(result)
        assert report.meta.number == 8
        diffs = reconcile_valuation_summary(report, result)
        assert diffs.abs().max() == pytest.approx(0.0, abs=1e-9)

    def test_none_metrics_render_as_nan(self, result_no_loans):
        """No loans → leveraged metrics are None → NaN (blank), never a
        misleading zero."""
        frame = valuation_summary(result_no_loans).frame.set_index("metric")
        assert np.isnan(frame.loc["Leveraged PV", "value"])
        assert np.isnan(frame.loc["Leveraged IRR (%)", "value"])
        # and the unleveraged figures are present
        assert frame.loc["Unleveraged PV", "value"] == pytest.approx(
            result_no_loans.valuation.unleveraged_pv)

    def test_direct_cap_value_present(self, result):
        frame = valuation_summary(result).frame.set_index("metric")
        # NOI 100k / 8% = 1,250,000
        assert frame.loc["Direct Cap Value", "value"] == pytest.approx(
            1_250_000.0, abs=0.01)


class TestPresentValue:
    def test_unleveraged_sums_to_valuation_pv(self, result):
        report = present_value(result)
        assert report.meta.number == 9
        assert reconcile_present_value(report, result) == pytest.approx(
            0.0, abs=1e-6)
        assert report.frame["present_value"].sum() == pytest.approx(
            result.valuation.unleveraged_pv, abs=1e-6)

    def test_leveraged_sums_to_leveraged_pv(self, result):
        report = present_value(result, leveraged=True)
        assert reconcile_present_value(report, result) == pytest.approx(
            0.0, abs=1e-6)

    def test_discount_factor_is_end_of_period(self, result):
        """Annual, end-of-period: factor for period k = 1/(1.08)^k."""
        frame = present_value(result).frame
        for row in frame.itertuples():
            assert row.discount_factor == pytest.approx(
                1.0 / 1.08 ** row.exponent, abs=1e-12)
            assert row.present_value == pytest.approx(
                row.cash_flow * row.discount_factor, abs=1e-9)

    def test_leveraged_requires_loans(self, result_no_loans):
        with pytest.raises(ValueError, match="leveraged Present Value needs"):
            present_value(result_no_loans, leveraged=True)


class TestLoanAmortization:
    def test_schedule_frame_and_metadata(self, result):
        report = loan_amortization(result)
        assert report.meta.number == 20
        assert report.meta.extra["loan_name"] == "Mortgage"
        assert list(report.frame.columns) == [
            "opening", "rate", "payment", "interest", "principal",
            "additional_principal", "ending"]
        assert len(report.frame) == 360  # full amortization term

    def test_reconciles_to_ledger_financing(self, result):
        diffs = reconcile_loan_amortization(result)
        assert diffs.abs().max() == pytest.approx(0.0, abs=1e-9)

    def test_two_loans_sum_reconciles(self):
        """With two loans the schedules SUMMED must tie to the single
        ledger financing line (the per-loan series the ledger was built
        from)."""
        loans = [a_loan(name="Senior"),
                 a_loan(name="Mezz", amount=LoanAmount(value=200_000.0),
                        rate=9.0)]
        res = run_property(flat_model(price=1_250_000.0, loans=loans))
        diffs = reconcile_loan_amortization(res)
        assert diffs.abs().max() == pytest.approx(0.0, abs=1e-9)
        # the report can address either loan
        assert loan_amortization(res, loan_index=1).meta.extra["loan_name"] == "Mezz"

    def test_no_loans_raises(self, result_no_loans):
        with pytest.raises(ValueError, match="no loans"):
            loan_amortization(result_no_loans)
        with pytest.raises(ValueError, match="no loans"):
            reconcile_loan_amortization(result_no_loans)


class TestScopeBoundaries:
    def test_matrix_builders_raise_without_sensitivity(self):
        """fixed_amount resale → no cap axis → no sensitivity → the matrix
        reports have nothing to view."""
        model = flat_model(price=1_250_000.0)
        model.valuation.resale = Resale(method="fixed_amount",
                                        fixed_amount=2_000_000.0)
        res = run_property(model)
        assert res.sensitivity is None
        with pytest.raises(ValueError, match="no sensitivity"):
            value_matrix(res)
        with pytest.raises(ValueError, match="no sensitivity"):
            irr_matrix(res)

    def test_valuation_reports_raise_without_valuation(self):
        model = PropertyModel(
            property=PropertyInfo(name="NoVal", property_type="industrial",
                                  analysis_begin=BEGIN, analysis_term_years=5),
            area_measures=AreaMeasures(
                property_size=12_000, rentable_area_mode=RentableAreaMode.fixed,
                rentable_area_fixed=12_000),
            inflation=FLAT,
            rent_roll=[Lease(tenant_name="T", area=12_000,
                             lease_type="industrial", start_date=BEGIN,
                             term_months=60,
                             base_rent=MoneyRate(amount=10.0, unit=PSF_YR),
                             upon_expiration=UponExpiration.vacate)])
        res = run_property(model)
        with pytest.raises(ValueError, match="no valuation"):
            valuation_summary(res)
        with pytest.raises(ValueError, match="no valuation"):
            present_value(res)
