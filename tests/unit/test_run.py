"""Unit tests for engine/calc/run.py (Phase 1, Step 4 items 5-6).

The %-of-EGR fixed point has no numeric worked example in the manual; its
reference relationship is the Clorox golden's Management Fee = pct × final
EGR (spec §4.1 step 9, run.py module docstring), which at 100% pro-rata
share has the closed form fee = pct/(1−pct) × (EGR excluding the fee).
These tests pin that algebra on a small synthetic property; the golden test
(tests/golden/test_clorox_northlake.py) asserts the real thing.
"""
import datetime as dt

import pytest

from engine.calc.run import run_property
from engine.models import (
    AreaMeasures,
    ExpenseItem,
    ExpenseUnit,
    GeneralVacancy,
    Inflation,
    Lease,
    MoneyRate,
    MoneyUnit,
    PropertyInfo,
    PropertyModel,
    RentableAreaMode,
    VacancyMethod,
    YearRate,
)

BEGIN = dt.date(2026, 1, 1)


def make_lease(**kwargs):
    defaults = dict(
        tenant_name="Tenant", area=100_000, lease_type="industrial",
        start_date=BEGIN, term_months=120,
        base_rent=MoneyRate(amount=12.0,
                            unit=MoneyUnit.dollars_per_area_per_year),
        upon_expiration="vacate",
    )
    defaults.update(kwargs)
    return Lease(**defaults)


def make_model(expenses, **kwargs):
    defaults = dict(
        property=PropertyInfo(
            name="Test", property_type="industrial",
            analysis_begin=BEGIN, analysis_term_years=2,
        ),
        area_measures=AreaMeasures(
            property_size=100_000,
            rentable_area_mode=RentableAreaMode.fixed,
            rentable_area_fixed=100_000,
        ),
        inflation=Inflation(general_rate=[YearRate(year=1, rate=0.0)]),
        expenses=expenses,
        rent_roll=[make_lease()],
    )
    defaults.update(kwargs)
    return PropertyModel(**defaults)


CAM = ExpenseItem(name="CAM", amount=60_000,
                  unit=ExpenseUnit.dollars_per_year)


class TestFixedPoint:
    """%-of-EGR expense resolution (spec §4.1 step 9; run.py docstring)."""

    def test_recoverable_fee_reaches_the_golden_relationship(self):
        """A recoverable 5% fee at 100% share converges to fee = 5% of final
        EGR — equivalently pct/(1−pct) × (base + other recoveries): 0.05 ×
        105,000 / 0.95 = 5,526.32/mo (the Clorox Management Fee shape)."""
        fee = ExpenseItem(name="Management Fee", amount=5.0,
                          unit=ExpenseUnit.pct_of_egr)
        frame = run_property(make_model([CAM, fee])).ledger.frame
        month = frame.iloc[0]
        expected_fee = 0.05 * (100_000 + 5_000) / 0.95
        assert month["Management Fee"] == pytest.approx(-expected_fee)
        assert month["Effective Gross Revenue"] == pytest.approx(
            100_000 + 5_000 + expected_fee
        )
        # the defining relationship: fee = pct × final EGR
        assert -month["Management Fee"] == pytest.approx(
            0.05 * month["Effective Gross Revenue"]
        )
        assert month["Expense Recovery Revenue"] == pytest.approx(
            5_000 + expected_fee
        )

    def test_non_recoverable_fee_needs_no_feedback(self):
        """A non-recoverable fee never re-enters EGR: fee = 5% × (base +
        recoveries of the others) exactly, recoveries exclude it."""
        fee = ExpenseItem(name="Management Fee", amount=5.0,
                          unit=ExpenseUnit.pct_of_egr, recoverable=False)
        frame = run_property(make_model([CAM, fee])).ledger.frame
        month = frame.iloc[0]
        assert month["Management Fee"] == pytest.approx(-5_250.0)
        assert month["Expense Recovery Revenue"] == pytest.approx(5_000.0)

    def test_pct_of_pgr_references_total_pgr(self):
        """A %-of-PGR item references Total Potential Gross Revenue (equal
        to EGR here — no vacancy in Phase 1), so it converges identically."""
        fee = ExpenseItem(name="Admin Fee", amount=5.0,
                          unit=ExpenseUnit.pct_of_pgr)
        frame = run_property(make_model([CAM, fee])).ledger.frame
        month = frame.iloc[0]
        assert -month["Admin Fee"] == pytest.approx(
            0.05 * month["Total Potential Gross Revenue"]
        )

    def test_diverging_percentages_raise(self):
        """Fees summing to ≥100% of revenue have no fixed point — the run
        must fail loudly, not return a runaway number."""
        fee = ExpenseItem(name="Impossible Fee", amount=100.0,
                          unit=ExpenseUnit.pct_of_egr)
        with pytest.raises(ValueError, match="did not converge"):
            run_property(make_model([fee]))


class TestPhaseGuards:
    """Inputs needing Phase 2/3 passes raise instead of silently posting
    nothing (Iron Rule 2; no silent numbers)."""

    def test_general_vacancy_now_computes(self):
        """The Step 4 guard is lifted: 5% of PGR posts to the General
        Vacancy line and reduces EGR (spec §3.4 [AE pp. 224-225])."""
        model = make_model(
            [CAM],
            general_vacancy=GeneralVacancy(
                method=VacancyMethod.percent_of_pgr,
                rate=[YearRate(year=1, rate=5.0)],
            ),
        )
        month = run_property(model).ledger.frame.iloc[0]
        # PGR = 100,000 rent + 5,000 recoveries; GV = 5%
        assert month["General Vacancy"] == pytest.approx(-5_250.0)
        assert month["Effective Gross Revenue"] == pytest.approx(99_750.0)

    def test_pct_of_account_expense_raises(self):
        item = ExpenseItem(name="Linked", amount=10.0,
                           unit=ExpenseUnit.pct_of_account,
                           account_ref="CAM")
        with pytest.raises(NotImplementedError, match="pct_of_account"):
            run_property(make_model([CAM, item]))


class TestRunResult:
    """Audit detail retained (spec §1.3); invariants asserted on every run."""

    def test_detail_and_occupancy(self):
        result = run_property(make_model([CAM]))
        assert result.occupancy.iloc[0] == pytest.approx(1.0)
        assert set(result.recoveries) == {"Tenant"}
        assert set(result.lease_rents) == {"Tenant"}
        assert [item.name for item, _ in result.expense_series] == ["CAM"]
        # ledger passed assert_invariants inside run_property; spot-check NOI
        month = result.ledger.frame.iloc[0]
        assert month["Net Operating Income"] == pytest.approx(100_000.0)
