"""Unit tests for sensitivity matrices (Phase 3 Step 6;
engine/calc/sensitivity.py).

Cites per Iron Rule 3: the sensitivity intervals [AE pp. 451-452] (cap
rate interval applies to NOI-based resale methods); the grid is centered
on the base case (odd count → a center = base cell; DEVIATIONS.md §21).
The cross-check (Part C) proves every matrix cell equals a direct
single-point Step 4/5 computation with those substituted inputs.

Validation path: no golden populates valuation — engineered tests + the
cross-check only. Hand-check property: flat NOI 100,000/yr, so any
diagonal cell where discount rate == exit cap equals 100,000 / cap
(value = NOI / cap when you discount at the cap rate).
"""
import datetime as dt

import pandas as pd
import pytest

from engine.calc.resale import compute_resale
from engine.calc.run import run_property
from engine.calc.valuation import (
    _period_buckets,
    _present_value,
    _solve_irr,
    _pv_start_month,
    holding_stream,
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
    Resale,
    SensitivityIntervals,
    ValuationInputs,
)

BEGIN = dt.date(2026, 1, 1)
PSF_YR = MoneyUnit.dollars_per_area_per_year
FLAT = Inflation(general_rate=[YearRate(year=1, rate=0.0)],
                 timing_basis=TimingBasis.analysis_year)


def flat_model(*, discount_rate=8.0, exit_cap=8.0, method="annual",
               convention="end_of_period", count=5, dstep=1.0, cstep=1.0,
               loans=(), price=None, resale_method="cap_noi_current_year",
               selling_costs_pct=0.0, closing_costs=(), expenses=None):
    """Flat property: $10/SF/yr on 12,000 SF, non-recoverable OpEx
    20,000/yr → NOI 100,000/yr every year."""
    lease = Lease(
        tenant_name="T", area=12_000, lease_type="industrial",
        start_date=BEGIN, term_months=240,
        base_rent=MoneyRate(amount=10.0, unit=PSF_YR),
        upon_expiration=UponExpiration.vacate)
    return PropertyModel(
        property=PropertyInfo(name="Sens", property_type="industrial",
                              analysis_begin=BEGIN, analysis_term_years=5),
        area_measures=AreaMeasures(
            property_size=12_000,
            rentable_area_mode=RentableAreaMode.fixed,
            rentable_area_fixed=12_000),
        inflation=FLAT,
        rent_roll=[lease],
        expenses=(expenses if expenses is not None else
                  [ExpenseItem(name="OpEx", amount=20_000.0,
                               unit=ExpenseUnit.dollars_per_year,
                               recoverable=False)]),
        loans=list(loans),
        purchase=(Purchase(price=price, closing_costs=list(closing_costs))
                  if price is not None else None),
        valuation=ValuationInputs(
            discount_rate=discount_rate, discount_method=method,
            period_convention=convention,
            resale=Resale(method=resale_method, exit_cap_rate=exit_cap,
                          selling_costs_pct=selling_costs_pct),
            sensitivity_intervals=SensitivityIntervals(
                discount_rate_step=dstep, cap_rate_step=cstep, count=count)),
    )


class TestGridConstruction:
    def test_centered_axes_and_shape_count_5(self):
        s = run_property(flat_model(count=5)).sensitivity
        assert s.discount_rate_axis == [6.0, 7.0, 8.0, 9.0, 10.0]
        assert s.cap_rate_axis == [6.0, 7.0, 8.0, 9.0, 10.0]
        assert s.value_matrix.shape == (5, 5)
        assert s.unleveraged_irr_matrix.shape == (5, 5)
        # base case sits at the center (index 2)
        assert s.discount_rate_axis[2] == 8.0
        assert s.cap_rate_axis[2] == 8.0

    def test_count_7_shape_and_spacing(self):
        s = run_property(flat_model(count=7, dstep=0.5, cstep=0.25)).sensitivity
        assert len(s.discount_rate_axis) == 7
        assert s.discount_rate_axis[3] == 8.0            # center = base
        assert s.discount_rate_axis == pytest.approx(
            [6.5, 7.0, 7.5, 8.0, 8.5, 9.0, 9.5])
        assert s.cap_rate_axis == pytest.approx(
            [7.25, 7.5, 7.75, 8.0, 8.25, 8.5, 8.75])
        assert s.value_matrix.shape == (7, 7)

    def test_diagonal_value_equals_noi_over_cap(self):
        """A flat 100,000 NOI: the diagonal cell where discount == cap
        equals 100,000 / cap (value = NOI / cap when discounting at the
        cap rate) — an owner hand-check."""
        s = run_property(flat_model(count=5)).sensitivity
        for rate in s.cap_rate_axis:
            assert s.value_matrix.loc[rate, rate] == pytest.approx(
                100_000.0 / (rate / 100.0), abs=0.01)

    def test_center_cell_is_self_consistent(self):
        """Center IRR cell (price = base PV, base exit cap) = the base
        discount rate — the §9.3 identity showing up in the matrix."""
        s = run_property(flat_model(count=5)).sensitivity
        center = len(s.price_axis) // 2
        assert s.unleveraged_irr_matrix.iloc[center, center] == pytest.approx(
            8.0, abs=1e-6)

    def test_price_axis_is_base_cap_column_of_value_matrix(self):
        s = run_property(flat_model(count=5)).sensitivity
        base_cap = s.cap_rate_axis[len(s.cap_rate_axis) // 2]
        assert s.price_axis == pytest.approx(
            list(s.value_matrix[base_cap].to_numpy()))


class TestCrossCheck:
    """Part C: each matrix cell equals a from-scratch single-point Step
    4/5 computation with those exact substituted inputs — proving the
    sweep isn't drifting from the functions it reuses."""

    def direct_value(self, model, result, discount_rate, exit_cap):
        """Independent single-point unleveraged PV at (discount, cap):
        recompute the resale at that cap (Step 4), build the truncated
        holding stream, discount at that rate (Step 5)."""
        v = model.valuation
        resale = compute_resale(
            v.resale.model_copy(update={"exit_cap_rate": exit_cap}),
            result.ledger, result.months, result.occupancy, model,
            result.loan_schedules)
        stream = holding_stream(result.ledger.frame["Cash Flow Before Debt "
                                                    "Service"],
                                resale.net_unleveraged, resale.resale_month)
        pv_start = _pv_start_month(v, model.property.analysis_begin,
                                   result.months)
        buckets = _period_buckets(stream, pv_start, v.discount_method,
                                  v.period_convention)
        return _present_value(buckets, discount_rate, v.discount_method)

    def test_value_cells_match_direct_computation(self):
        model = flat_model(count=5)
        result = run_property(model)
        s = result.sensitivity
        for rate in [s.discount_rate_axis[0], s.discount_rate_axis[2],
                     s.discount_rate_axis[4]]:
            for cap in [s.cap_rate_axis[1], s.cap_rate_axis[3]]:
                assert s.value_matrix.loc[rate, cap] == pytest.approx(
                    self.direct_value(model, result, rate, cap), abs=1e-6)

    def test_irr_cells_match_direct_computation(self):
        model = flat_model(count=5)
        result = run_property(model)
        s = result.sensitivity
        v = model.valuation
        pv_start = _pv_start_month(v, model.property.analysis_begin,
                                   result.months)
        for price in [s.price_axis[0], s.price_axis[3]]:
            for cap in [s.cap_rate_axis[0], s.cap_rate_axis[4]]:
                resale = compute_resale(
                    v.resale.model_copy(update={"exit_cap_rate": cap}),
                    result.ledger, result.months, result.occupancy, model,
                    result.loan_schedules)
                stream = holding_stream(
                    result.ledger.frame["Cash Flow Before Debt Service"],
                    resale.net_unleveraged, resale.resale_month)
                buckets = _period_buckets(stream, pv_start, v.discount_method,
                                          v.period_convention)
                direct = _solve_irr(buckets, -price, v.discount_method)
                assert s.unleveraged_irr_matrix.loc[price, cap] == (
                    pytest.approx(direct, abs=1e-6))


class TestLeverage:
    def loan(self):
        return Loan(name="Mortgage", amount=LoanAmount(value=600_000.0),
                    term_months=360, rate=6.0,
                    amortization="fully_amortizing")

    def test_leveraged_matrix_populated_with_loans(self):
        s = run_property(flat_model(loans=[self.loan()])).sensitivity
        assert not s.leveraged_irr_matrix.isna().all().all()
        # leverage lifts the return above the unleveraged IRR at the
        # center price/cap
        c = len(s.price_axis) // 2
        assert (s.leveraged_irr_matrix.iloc[c, c]
                > s.unleveraged_irr_matrix.iloc[c, c])

    def test_leveraged_matrix_all_nan_without_loans(self):
        """Part D #11: no loans → leveraged IRR isn't computable → NaN
        cells (right shape), never a silent zero or crash."""
        s = run_property(flat_model()).sensitivity
        assert s.leveraged_irr_matrix.shape == s.unleveraged_irr_matrix.shape
        assert s.leveraged_irr_matrix.isna().all().all()


class TestScopeBoundary:
    def test_none_when_no_valuation(self):
        lease = Lease(
            tenant_name="T", area=12_000, lease_type="industrial",
            start_date=BEGIN, term_months=60,
            base_rent=MoneyRate(amount=10.0, unit=PSF_YR),
            upon_expiration=UponExpiration.vacate)
        model = PropertyModel(
            property=PropertyInfo(name="NoVal", property_type="industrial",
                                  analysis_begin=BEGIN, analysis_term_years=5),
            area_measures=AreaMeasures(
                property_size=12_000,
                rentable_area_mode=RentableAreaMode.fixed,
                rentable_area_fixed=12_000),
            inflation=FLAT, rent_roll=[lease])
        assert run_property(model).sensitivity is None

    def test_none_for_non_cap_resale_method(self):
        """fixed_amount / pct_increase resales have no exit cap, so no
        cap axis and no sensitivity matrices [AE p. 451]."""
        model = flat_model()
        model.valuation.resale = Resale(method="fixed_amount",
                                        fixed_amount=2_000_000.0)
        assert run_property(model).sensitivity is None


def t0_loan():
    return Loan(name="Mortgage", amount=LoanAmount(value=600_000.0),
                term_months=360, rate=6.0, amortization="fully_amortizing")


class TestT0ReframeMirrorsValuation:
    """§24 sensitivity follow-up: the IRR grids reflect closing costs and
    staged-draw timing exactly the way compute_valuation does (they now
    share `_t0_costs` / `_apply_loan_proceeds`)."""

    def test_closing_costs_lower_the_unleveraged_irr_grid(self):
        """#2 in the grid: the unleveraged IRR grid's t0 is price + closing
        costs, so every cell is below the no-cost case (the price axis, a
        PV grid, is unchanged by closing costs). A price must be set for
        closing costs to post, but the grid's axis is PV-derived
        regardless of the model price."""
        no_cost = run_property(flat_model(price=1_000_000.0,
                                          loans=[t0_loan()])).sensitivity
        with_cost = run_property(flat_model(
            price=1_000_000.0, loans=[t0_loan()],
            closing_costs=[ClosingCost(name="Legal", amount=50_000.0)],
        )).sensitivity
        # price axis identical (derived from PV, cost-independent)
        assert with_cost.price_axis == pytest.approx(no_cost.price_axis)
        c = len(with_cost.price_axis) // 2
        assert (with_cost.unleveraged_irr_matrix.iloc[c, c]
                < no_cost.unleveraged_irr_matrix.iloc[c, c])

    def test_leveraged_grid_base_cell_matches_compute_valuation(self):
        """Cross-check (Step 6 / §21 pattern): the leveraged IRR grid's
        base price/cap cell equals compute_valuation's own leveraged IRR
        for a model priced at that same base price. Flat $ closing costs
        keep the ledger price-independent so the two coincide exactly."""
        closing = [ClosingCost(name="Legal", amount=50_000.0)]
        s = run_property(flat_model(price=1.0, loans=[t0_loan()],
                                    closing_costs=closing)).sensitivity
        c = len(s.price_axis) // 2
        base_price = s.price_axis[c]
        base_cap = s.cap_rate_axis[c]
        # a model priced exactly at the grid's base price/cap
        v = run_property(flat_model(price=base_price, exit_cap=base_cap,
                                    loans=[t0_loan()],
                                    closing_costs=closing)).valuation
        assert v.leveraged_irr == pytest.approx(
            s.leveraged_irr_matrix.iloc[c, c], abs=1e-9)

    def test_staged_draw_not_netted_lowers_leveraged_grid(self):
        """#1 in the grid: a loan funding 12 months post-close is not
        netted against day-one equity, so the leveraged IRR grid is lower
        than the same loan funded at close (larger equity base)."""
        at_close = run_property(flat_model(loans=[t0_loan()])).sensitivity
        staged_loan = Loan(name="Staged", amount=LoanAmount(value=600_000.0),
                           term_months=360, rate=6.0,
                           amortization="fully_amortizing",
                           funding_date=dt.date(2027, 1, 1))
        staged = run_property(flat_model(loans=[staged_loan])).sensitivity
        c = len(at_close.price_axis) // 2
        assert (staged.leveraged_irr_matrix.iloc[c, c]
                < at_close.leveraged_irr_matrix.iloc[c, c])


class TestAmbiguousIrrCellNaN:
    """§24 follow-up (Fix 3): a non-conventional stream (multiple sign
    changes) NaNs that cell rather than raising and killing the matrix."""

    def test_mid_hold_capital_event_nans_cells_without_raising(self):
        """A large one-time capital expense mid-hold (2028) drives that
        year's CFBDS negative, so the unleveraged stream has an interior
        negative (multiple sign changes). The matrix still computes, with
        the ambiguous IRR cells NaN — no exception."""
        expenses = [
            ExpenseItem(name="OpEx", amount=20_000.0,
                        unit=ExpenseUnit.dollars_per_year, recoverable=False),
            # $2M capital event only in 2028 (a mid-hold year)
            ExpenseItem(name="Reroof", amount=0.0,
                        unit=ExpenseUnit.dollars_per_year, category="capital",
                        annual_overrides=[{"year": 2028, "amount": 2_000_000.0}]),
        ]
        s = run_property(flat_model(expenses=expenses)).sensitivity
        assert s is not None                       # computed, did not raise
        # at least one ambiguous IRR cell was NaN'd rather than crashing
        assert s.unleveraged_irr_matrix.isna().to_numpy().any()
