"""Unit tests for PV, IRR, and direct capitalization (Phase 3 Step 5;
engine/calc/valuation.py).

Cites per Iron Rule 3: the discount conventions and "Discount Rate (APR)"
[AE p. 472]; the spec §4.1 pass 14 PV/IRR formulas; direct cap
[AE pp. 453-454]. No manual worked-number table exists in this PDF (the
"Present Value Calculation Examples" reference is a hyperlink), so the PV
tests use closed-form textbook streams the owner can paste into Excel's
NPV()/IRR(); IRR is annualized nominally (periodic × p) — the only
convention self-consistent with APR/p discounting (DEVIATIONS.md §20).

Validation path: no golden populates valuation and none will — these
worked-example, engineered, and §9.3 self-consistency tests plus an owner
Excel hand-check are the only proof. The headline hand-check: a par
stream −1,000,000 then 80,000 × 4 and 1,080,000, annual end-of-period at
8% → PV 1,000,000, IRR 8.00%.
"""
import datetime as dt

import pandas as pd
import pytest

from engine.calc.valuation import (
    _period_buckets,
    _present_value,
    _solve_irr,
)
from engine.calc.run import run_property
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
from engine.models.investment import Loan, LoanAmount
from engine.models.valuation import (
    DirectCap,
    DiscountMethod,
    PeriodConvention,
    Resale,
    ValuationInputs,
)

BEGIN = dt.date(2026, 1, 1)
PSF_YR = MoneyUnit.dollars_per_area_per_year
FLAT = Inflation(general_rate=[YearRate(year=1, rate=0.0)],
                 timing_basis=TimingBasis.analysis_year)


def monthly_series(flows: dict[int, float], n_months: int = 72) -> pd.Series:
    """A Period[M] series from 2026-01 with ``flows`` keyed by 0-based
    month offset."""
    idx = pd.period_range("2026-01", periods=n_months, freq="M")
    s = pd.Series(0.0, index=idx)
    for offset, amount in flows.items():
        s.iloc[offset] = amount
    return s


# The par bond used across PV and IRR: 80k/yr coupon on 1,000,000 with
# principal returned in year 5, cash placed at each year-start month.
PAR_FLOWS = {0: 80_000, 12: 80_000, 24: 80_000, 36: 80_000, 48: 1_080_000}
PV_START = pd.Period("2026-01", freq="M")


class TestPresentValue:
    """Closed-form PV of the par stream under four conventions
    (spec §4.1 pass 14; DF at APR/p, mid-period shift −0.5)."""

    def pv(self, method, convention, rate=8.0):
        buckets = _period_buckets(monthly_series(PAR_FLOWS), PV_START,
                                  method, convention)
        return _present_value(buckets, rate, method)

    def test_annual_end_of_period(self):
        assert self.pv(DiscountMethod.annual,
                       PeriodConvention.end_of_period) == pytest.approx(
            1_000_000.0, abs=1e-4)

    def test_annual_mid_period(self):
        assert self.pv(DiscountMethod.annual,
                       PeriodConvention.mid_period) == pytest.approx(
            1_039_230.4845, abs=1e-3)

    def test_monthly_end_of_period(self):
        assert self.pv(DiscountMethod.monthly,
                       PeriodConvention.end_of_period) == pytest.approx(
            1_063_044.2618, abs=1e-3)

    def test_monthly_mid_period(self):
        assert self.pv(DiscountMethod.monthly,
                       PeriodConvention.mid_period) == pytest.approx(
            1_066_581.8565, abs=1e-3)

    def test_quarterly_end_of_period(self):
        assert self.pv(DiscountMethod.quarterly,
                       PeriodConvention.end_of_period) == pytest.approx(
            1_050_968.4281, abs=1e-3)

    def test_months_before_pv_start_excluded(self):
        """A specified late pv_start drops earlier cash flows and re-bases
        the exponents (Part A #4)."""
        buckets = _period_buckets(monthly_series(PAR_FLOWS, n_months=60),
                                  pd.Period("2027-01", freq="M"),
                                  DiscountMethod.annual,
                                  PeriodConvention.end_of_period)
        # only months 12,24,36,48 remain, now periods 1..4
        assert len(buckets) == 4
        assert buckets[0] == (1.0, 80_000.0)
        assert buckets[-1] == (4.0, 1_080_000.0)


class TestIRR:
    """Nominal-annualized IRR (periodic × p) — the Excel-checkable case."""

    def test_par_bond_irr_is_the_coupon(self):
        """−1,000,000 then the par stream, annual end-of-period → IRR
        8.00% (Excel: IRR({-1000000,80000,80000,80000,80000,1080000}))."""
        buckets = _period_buckets(monthly_series(PAR_FLOWS), PV_START,
                                  DiscountMethod.annual,
                                  PeriodConvention.end_of_period)
        irr = _solve_irr(buckets, -1_000_000.0, DiscountMethod.annual)
        assert irr == pytest.approx(8.0, abs=1e-6)

    def test_monthly_terminal_only(self):
        """−1,000,000 then a single 1,485,947.14 at month 60, monthly
        end-of-period: (1+irr/12)^60 = 1.485947 → irr = 8.00% nominal."""
        terminal = 1_000_000.0 * (1 + 0.08 / 12) ** 60
        buckets = _period_buckets(monthly_series({59: terminal}), PV_START,
                                  DiscountMethod.monthly,
                                  PeriodConvention.end_of_period)
        irr = _solve_irr(buckets, -1_000_000.0, DiscountMethod.monthly)
        assert irr == pytest.approx(8.0, abs=1e-6)

    def test_no_sign_change_returns_none(self):
        """An all-positive stream has no real IRR — None, not a wrong
        number."""
        buckets = _period_buckets(monthly_series({0: 100.0}), PV_START,
                                  DiscountMethod.annual,
                                  PeriodConvention.end_of_period)
        assert _solve_irr(buckets, 100.0, DiscountMethod.annual) is None


def flat_noi_model(*, price=None, discount_rate=8.0, method="annual",
                   convention="end_of_period", loans=(), direct_cap=None,
                   pv_start=None, resale_method="cap_noi_current_year"):
    """A flat property: $10/SF/yr on 12,000 SF, non-recoverable OpEx
    20,000/yr → NOI 100,000/yr; 8% exit cap resale at analysis end."""
    lease = Lease(
        tenant_name="T", area=12_000, lease_type="industrial",
        start_date=BEGIN, term_months=240,
        base_rent=MoneyRate(amount=10.0, unit=PSF_YR),
        upon_expiration=UponExpiration.vacate,
    )
    return PropertyModel(
        property=PropertyInfo(name="Val", property_type="industrial",
                              analysis_begin=BEGIN, analysis_term_years=5),
        area_measures=AreaMeasures(
            property_size=12_000,
            rentable_area_mode=RentableAreaMode.fixed,
            rentable_area_fixed=12_000),
        inflation=FLAT,
        rent_roll=[lease],
        expenses=[ExpenseItem(name="OpEx", amount=20_000.0,
                              unit=ExpenseUnit.dollars_per_year,
                              recoverable=False)],
        loans=list(loans),
        purchase=(Purchase(price=price) if price is not None else None),
        valuation=ValuationInputs(
            discount_rate=discount_rate, discount_method=method,
            period_convention=convention, pv_start=pv_start,
            direct_cap=direct_cap,
            resale=Resale(method=resale_method, exit_cap_rate=8.0)),
    )


class TestDirectCap:
    """[AE pp. 453-454]: value = NOI basis / cap rate, anchored at
    pv_start; year_1 vs forward_12 are distinct windows (Part A #5)."""

    def test_year_1_basis(self):
        model = flat_noi_model(direct_cap=DirectCap(cap_rate=8.0))
        result = run_property(model)
        # analysis year 1 NOI = 100,000 → 100,000 / 0.08 = 1,250,000
        assert result.valuation.direct_cap_value == pytest.approx(
            1_250_000.0)

    def test_forward_12_from_pv_start_shifts_with_pv_start(self):
        """forward_12 anchors at pv_start, not analysis begin — with a
        flat 100,000 NOI the value is the same 1,250,000, but the window
        starts at pv_start (distinct from year_1's fixed first year)."""
        model = flat_noi_model(
            direct_cap=DirectCap(cap_rate=8.0, noi_basis="forward_12"),
            pv_start=dt.date(2027, 1, 1))
        result = run_property(model)
        assert result.valuation.direct_cap_value == pytest.approx(
            1_250_000.0)


class TestSelfConsistency:
    """§9.3 (Part C): set the purchase price to the computed unleveraged
    PV; the unleveraged IRR must equal the discount rate within 1bp. The
    invariant fires inside run_property; covered across two conventions.
    The reference PV is read from a first run (the engine never derives
    it live) and hard-set as the fixed price of the asserting run."""

    @pytest.mark.parametrize("method,convention", [
        ("annual", "end_of_period"),
        ("monthly", "end_of_period"),
    ])
    def test_price_equals_pv_gives_irr_equals_discount_rate(self, method,
                                                            convention):
        probe = run_property(flat_noi_model(method=method,
                                            convention=convention))
        pv = probe.valuation.unleveraged_pv
        # second run with price fixed at the computed PV — the standing
        # assert_pv_irr_self_consistency fires here and must not raise
        result = run_property(flat_noi_model(price=pv, method=method,
                                             convention=convention))
        assert result.valuation.unleveraged_irr == pytest.approx(
            8.0, abs=0.01)
        assert result.valuation.unleveraged_pv == pytest.approx(pv, abs=1e-6)

    def test_invariant_raises_on_inconsistent_irr(self):
        """A corrupted result with price == PV but IRR ≠ rate raises —
        proving the standing assertion has teeth."""
        from engine.calc.valuation import (
            ValuationResult,
            assert_pv_irr_self_consistency,
        )
        model = flat_noi_model(price=1_000_000.0)
        bad = ValuationResult(
            discount_rate=8.0, discount_method=DiscountMethod.annual,
            period_convention=PeriodConvention.end_of_period,
            pv_start=PV_START, unleveraged_pv=1_000_000.0,
            unleveraged_irr=6.0, leveraged_pv=None, leveraged_irr=None,
            direct_cap_value=None)
        with pytest.raises(ValueError, match="self-consistency violated"):
            assert_pv_irr_self_consistency(bad, model)


class TestLeveraged:
    """Leveraged PV/IRR need loans (and a price for IRR); absent, None —
    not a silent zero (Part A #1, task #10)."""

    def loan(self):
        return Loan(name="Mortgage", amount=LoanAmount(value=600_000.0),
                    term_months=360, rate=6.0,
                    amortization="fully_amortizing")

    def test_leveraged_present_when_loans(self):
        result = run_property(flat_noi_model(price=1_250_000.0,
                                             loans=[self.loan()]))
        v = result.valuation
        assert v.leveraged_pv is not None
        assert v.leveraged_irr is not None
        # leverage amplifies return above the 8% unleveraged discount rate
        assert v.leveraged_irr > v.unleveraged_irr

    def test_leveraged_none_without_loans(self):
        result = run_property(flat_noi_model(price=1_250_000.0))
        assert result.valuation.leveraged_pv is None
        assert result.valuation.leveraged_irr is None


class TestPvStartAfterDisposition:
    """Codex finding #9 (DEVIATIONS.md §22): a valuation date after the
    resale month leaves no holding period — refuse, don't return zero."""

    def test_pv_start_after_resale_refused(self):
        # resale defaults to analysis end 2030-12; pv_start 2031-06 (a
        # look-forward month, within the timeline) is after it.
        model = flat_noi_model(pv_start=dt.date(2031, 6, 1))
        with pytest.raises(ValueError, match="after the resale month"):
            run_property(model)

    def test_pv_start_at_resale_month_allowed(self):
        """A same-month buy/sell is degenerate but valid — pv_start ==
        resale month must not raise (the guard is strict `>`)."""
        model = flat_noi_model(pv_start=dt.date(2030, 12, 1))
        result = run_property(model)
        assert result.valuation.unleveraged_pv is not None

    def test_unleveraged_irr_none_without_price(self):
        result = run_property(flat_noi_model())
        assert result.valuation.unleveraged_pv is not None
        assert result.valuation.unleveraged_irr is None


class TestNoValuationNoResult:
    def test_valuation_none_when_absent(self):
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
        assert run_property(model).valuation is None
