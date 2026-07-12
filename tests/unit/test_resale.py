"""Unit tests for property resale (Phase 3 Step 4; engine/calc/resale.py
+ engine/reports/resale_audit.py).

Cites per Iron Rule 3: the method definitions [AE p. 465] (CAP NOI 12
Months After Sale / Year of Sale; CAP Effective Gross Rents = EGR −
recoveries; Enter Sale Price = gross AND net; Inflate Purchase Price);
the occupancy gross-up formula "NOI × Gross Up % / Average Occupancy %"
[AE p. 469]; the Deductions grid capital treatment [AE pp. 470-471]; the
adjustments-then-selling-costs order [AE p. 465].

Validation path: no golden populates valuation and none will (no OM
publishes a valuation result) — these worked-example and engineered
tests are the only proof (DEVIATIONS.md §19). The headline hand-check:
flat NOI 100,000/yr at an 8.00% exit cap = 1,250,000 gross; 3% selling
costs = 37,500; net proceeds 1,212,500.
"""
import datetime as dt

import pandas as pd
import pytest

from engine.calc.ledger import (
    CFBDS,
    LOAN_PAYOFF_AT_RESALE,
    NET_RESALE_PROCEEDS,
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
    RentStep,
    RentableAreaMode,
    TimingBasis,
    UponExpiration,
    YearRate,
)
from engine.models.investment import Loan, LoanAmount
from engine.models.valuation import (
    DirectCap,
    NOIAdjustments,
    Resale,
    ResaleAdjustment,
    StabilizedOccupancy,
    ValuationInputs,
)
from engine.reports import reconcile_resale_audit, resale_audit

BEGIN = dt.date(2026, 1, 1)
PSF_YR = MoneyUnit.dollars_per_area_per_year
FLAT = Inflation(general_rate=[YearRate(year=1, rate=0.0)],
                 timing_basis=TimingBasis.analysis_year)


def month(text):
    return pd.Period(text, freq="M")


def build_model(resale, *, rentable=12_000, loans=(), purchase=None,
                expenses=None, discount_rate=8.0):
    """Flat hand-checkable property: $10/SF/yr on 12,000 SF = 120,000/yr
    rent stepping to 132,000/yr from lease month 61 (2031-01 — the first
    look-forward month); OpEx 20,000/yr → NOI 100,000/yr through the
    5-year analysis and 112,000/yr in the look-forward year."""
    lease = Lease(
        tenant_name="T", area=12_000, lease_type="industrial",
        start_date=BEGIN, term_months=300,
        base_rent=MoneyRate(amount=10.0, unit=PSF_YR),
        rent_steps=[RentStep(month_offset=60, amount=11.0, unit=PSF_YR)],
        upon_expiration=UponExpiration.vacate,
    )
    return PropertyModel(
        property=PropertyInfo(name="Exit", property_type="industrial",
                              analysis_begin=BEGIN, analysis_term_years=5),
        area_measures=AreaMeasures(
            property_size=12_000,
            rentable_area_mode=RentableAreaMode.fixed,
            rentable_area_fixed=rentable,
        ),
        inflation=FLAT,
        rent_roll=[lease],
        expenses=(expenses if expenses is not None else
                  [ExpenseItem(name="OpEx", amount=20_000.0,
                               unit=ExpenseUnit.dollars_per_year,
                               recoverable=False)]),
        loans=list(loans),
        purchase=purchase,
        valuation=ValuationInputs(discount_rate=discount_rate,
                                  resale=resale),
    )


class TestCapMethods:
    """[AE p. 465] method definitions with hand-checkable numbers."""

    def test_cap_noi_forward_12_at_default_resale_date(self):
        """Resale defaults to the analysis end (2030-12, NOT a
        look-forward month); forward 12 = 2031-01..2031-12 where the
        stepped NOI is 112,000; at an 8% exit cap = 1,400,000 gross; 3%
        selling costs 42,000; net 1,358,000."""
        resale = Resale(method="cap_noi_forward_12", exit_cap_rate=8.0,
                        selling_costs_pct=3.0)
        result = run_property(build_model(resale))
        r = result.resale
        assert r.resale_month == month("2030-12")
        assert r.noi_window[0] == month("2031-01")
        assert r.income_basis == pytest.approx(112_000.0)
        assert r.gross_sale_price == pytest.approx(1_400_000.0)
        assert r.selling_costs == pytest.approx(42_000.0)
        assert r.net_unleveraged == pytest.approx(1_358_000.0)
        posted = result.ledger.frame[NET_RESALE_PROCEEDS]
        assert posted[month("2030-12")] == pytest.approx(1_358_000.0)
        assert posted.drop(month("2030-12")).abs().sum() == 0.0

    def test_cap_noi_current_year_uses_the_year_of_sale(self):
        """'CAP NOI (Year of Sale)' [AE p. 465] — the analysis year
        containing the resale month (2030 rent is pre-step): 100,000 at
        8% = 1,250,000 gross; 3% selling = 37,500; net 1,212,500 — the
        headline hand-check."""
        resale = Resale(method="cap_noi_current_year", exit_cap_rate=8.0,
                        selling_costs_pct=3.0)
        result = run_property(build_model(resale))
        r = result.resale
        assert r.noi_window[0] == month("2030-01")
        assert r.noi_window[-1] == month("2030-12")
        assert r.income_basis == pytest.approx(100_000.0)
        assert r.gross_sale_price == pytest.approx(1_250_000.0)
        assert r.net_unleveraged == pytest.approx(1_212_500.0)

    def test_gross_value_less_costs_capitalizes_net_effective_rents(self):
        """'CAP Effective Gross Rents (12 Months After Sale): Capitalize
        net effective gross rents (effective gross revenue −
        recoveries)' [AE p. 465]: with no recoveries the forward-12
        basis is the 132,000 revenue, not the 112,000 NOI."""
        resale = Resale(method="gross_value_less_costs", exit_cap_rate=8.0,
                        selling_costs_pct=3.0)
        result = run_property(build_model(resale))
        r = result.resale
        assert r.income_basis == pytest.approx(132_000.0)
        assert r.gross_sale_price == pytest.approx(1_650_000.0)
        assert r.net_unleveraged == pytest.approx(1_650_000.0 * 0.97)

    def test_mid_analysis_resale_window_is_relative_to_resale_date(self):
        """A 2028-06 sale's forward 12 = 2028-07..2029-06 (pre-step NOI
        100,000) — the window follows the resale date, not analysis
        end."""
        resale = Resale(method="cap_noi_forward_12", exit_cap_rate=8.0,
                        resale_date=dt.date(2028, 6, 1))
        result = run_property(build_model(resale))
        r = result.resale
        assert r.noi_window[0] == month("2028-07")
        assert r.noi_window[-1] == month("2029-06")
        assert r.gross_sale_price == pytest.approx(1_250_000.0)
        assert result.ledger.frame[NET_RESALE_PROCEEDS][
            month("2028-06")] == pytest.approx(1_250_000.0)

    def test_resale_date_in_look_forward_raises(self):
        resale = Resale(method="cap_noi_forward_12", exit_cap_rate=8.0,
                        resale_date=dt.date(2031, 6, 1))
        with pytest.raises(ValueError, match="look-forward"):
            run_property(build_model(resale))


class TestFixedAndInflated:
    def test_fixed_amount_is_gross_and_net(self):
        """'Enter Sale Price ... used as the gross sale price and net
        sale price' [AE p. 465]."""
        resale = Resale(method="fixed_amount", fixed_amount=2_000_000.0)
        result = run_property(build_model(resale))
        r = result.resale
        assert r.gross_sale_price == pytest.approx(2_000_000.0)
        assert r.net_unleveraged == pytest.approx(2_000_000.0)
        assert r.selling_costs == 0.0

    def test_fixed_amount_with_selling_costs_refused(self):
        """No silent numbers: the manual's Enter Sale Price admits no
        selling costs [AE p. 465] — refuse, don't ignore."""
        resale = Resale(method="fixed_amount", fixed_amount=2_000_000.0,
                        selling_costs_pct=3.0)
        with pytest.raises(ValueError, match="gross AND the net"):
            run_property(build_model(resale))

    def test_pct_increase_over_price(self):
        """'Inflate Purchase Price' [AE p. 465], narrowed to a total
        increase: 1,000,000 + 25% = 1,250,000 gross; 2% selling = net
        1,225,000."""
        resale = Resale(method="pct_increase_over_price", pct_increase=25.0,
                        selling_costs_pct=2.0)
        purchase = Purchase(price=1_000_000.0)
        result = run_property(build_model(resale, purchase=purchase))
        r = result.resale
        assert r.gross_sale_price == pytest.approx(1_250_000.0)
        assert r.net_unleveraged == pytest.approx(1_225_000.0)

    def test_pct_increase_without_purchase_raises(self):
        resale = Resale(method="pct_increase_over_price", pct_increase=25.0)
        with pytest.raises(ValueError, match="no purchase price"):
            run_property(build_model(resale))


class TestNOIAdjustments:
    def test_exclude_capital_false_includes_window_capital_costs(self):
        """[AE pp. 470-471] Deductions: with a 1,200/yr capital reserve,
        exclude_capital=False bases the value on 112,000 − 1,200 =
        110,800 (the ledger NOI already excludes capital, so True is the
        as-is default)."""
        expenses = [
            ExpenseItem(name="OpEx", amount=20_000.0,
                        unit=ExpenseUnit.dollars_per_year,
                        recoverable=False),
            ExpenseItem(name="Reserves", amount=0.10,
                        unit=ExpenseUnit.dollars_per_area_per_year,
                        category="capital"),
        ]
        base = Resale(method="cap_noi_forward_12", exit_cap_rate=8.0)
        included = Resale(method="cap_noi_forward_12", exit_cap_rate=8.0,
                          noi_adjustments=NOIAdjustments(
                              exclude_capital=False))
        with_cap = run_property(build_model(base, expenses=expenses))
        without = run_property(build_model(included, expenses=expenses))
        assert with_cap.resale.adjusted_basis == pytest.approx(112_000.0)
        assert without.resale.capital_adjustment == pytest.approx(-1_200.0)
        assert without.resale.adjusted_basis == pytest.approx(110_800.0)
        assert without.resale.gross_sale_price == pytest.approx(
            110_800.0 / 0.08)

    def test_stabilize_occupancy_ratio(self):
        """The printed formula 'NOI × Gross Up % / Average Occupancy %'
        [AE p. 469]: 12,000 SF occupied of 16,000 rentable = 75%
        average; stabilizing to 90% scales the 112,000 forward NOI by
        0.90/0.75 = 1.2 → 134,400; at 8% = 1,680,000."""
        resale = Resale(
            method="cap_noi_forward_12", exit_cap_rate=8.0,
            noi_adjustments=NOIAdjustments(
                stabilize_occupancy=StabilizedOccupancy(occupancy_pct=90.0)),
        )
        result = run_property(build_model(resale, rentable=16_000))
        r = result.resale
        assert r.occupancy_factor == pytest.approx(1.2)
        assert r.adjusted_basis == pytest.approx(134_400.0)
        assert r.gross_sale_price == pytest.approx(1_680_000.0)


class TestAdjustmentsAndOrder:
    def test_adjustments_apply_before_selling_costs(self):
        """[AE p. 465] order: value → adjustments → gross sale price →
        selling costs on the ADJUSTED gross: (1,400,000 − 50,000) ×
        3% = 40,500; net 1,309,500."""
        resale = Resale(
            method="cap_noi_forward_12", exit_cap_rate=8.0,
            selling_costs_pct=3.0,
            adjustment_amounts=[ResaleAdjustment(
                name="Deferred maintenance credit", amount=-50_000.0)],
        )
        result = run_property(build_model(resale))
        r = result.resale
        assert r.gross_sale_price == pytest.approx(1_350_000.0)
        assert r.selling_costs == pytest.approx(40_500.0)
        assert r.net_unleveraged == pytest.approx(1_309_500.0)


class TestLeveragedProceeds:
    """First test exercising resale + debt together; the §9.3
    payoff-at-resale invariant asserts inside run_property on this
    exact case."""

    def loan(self):
        return Loan(name="Mortgage", amount=LoanAmount(value=1_000_000.0),
                    term_months=360, rate=6.0,
                    amortization="fully_amortizing")

    def test_payoff_at_resale(self):
        """$1M 6%/30yr funded 2026-01: 59 payments by the 2030-12 resale
        → outstanding balance 931,879.68. Net leveraged = 1,358,000 −
        931,879.68 = 426,120.32; the ledger posts the proceeds and the
        payoff as separate below-the-line lines whose sum is the
        leveraged net."""
        resale = Resale(method="cap_noi_forward_12", exit_cap_rate=8.0,
                        selling_costs_pct=3.0)
        result = run_property(build_model(resale, loans=[self.loan()]))
        r = result.resale
        assert r.loan_payoffs["Mortgage"] == pytest.approx(931_879.68,
                                                           abs=0.01)
        assert r.net_leveraged == pytest.approx(426_120.32, abs=0.01)
        frame = result.ledger.frame
        m = month("2030-12")
        assert frame[NET_RESALE_PROCEEDS][m] == pytest.approx(1_358_000.0)
        assert frame[LOAN_PAYOFF_AT_RESALE][m] == pytest.approx(
            -931_879.68, abs=0.01)
        assert (frame[NET_RESALE_PROCEEDS][m]
                + frame[LOAN_PAYOFF_AT_RESALE][m]) == pytest.approx(
            r.net_leveraged, abs=0.01)

    def test_unleveraged_when_no_loans(self):
        resale = Resale(method="cap_noi_forward_12", exit_cap_rate=8.0)
        result = run_property(build_model(resale))
        assert result.resale.loan_payoffs == {}
        assert result.resale.net_leveraged == pytest.approx(
            result.resale.net_unleveraged)


class TestApplyToggleAndAudit:
    def test_apply_false_posts_nothing_but_audit_populates(self):
        resale = Resale(method="cap_noi_forward_12", exit_cap_rate=8.0,
                        selling_costs_pct=3.0,
                        apply_resale_to_cash_flow=False)
        result = run_property(build_model(resale))
        frame = result.ledger.frame
        assert frame[NET_RESALE_PROCEEDS].abs().sum() == 0.0
        assert frame[LOAN_PAYOFF_AT_RESALE].abs().sum() == 0.0
        assert result.resale.net_unleveraged == pytest.approx(1_358_000.0)
        audit = resale_audit(result)
        assert not audit.empty
        differences = reconcile_resale_audit(audit, result)
        assert differences.abs().max() == pytest.approx(0.0, abs=1e-9)

    def test_audit_reconciles_exactly_when_applied(self):
        """Mirrors the lease/recovery audit exact-reconciliation
        pattern: posted ledger columns equal the audit cascade to
        1e-9, and nothing posts outside the resale month."""
        resale = Resale(
            method="cap_noi_forward_12", exit_cap_rate=8.0,
            selling_costs_pct=3.0,
            adjustment_amounts=[ResaleAdjustment(name="Fee",
                                                 amount=-10_000.0)],
        )
        loan = Loan(name="Mortgage", amount=LoanAmount(value=1_000_000.0),
                    term_months=360, rate=6.0,
                    amortization="fully_amortizing")
        result = run_property(build_model(resale, loans=[loan]))
        audit = resale_audit(result)
        differences = reconcile_resale_audit(audit, result)
        assert differences.abs().max() == pytest.approx(0.0, abs=1e-9)
        lines = list(audit["line"])
        assert "Net unleveraged proceeds" in lines
        assert "Loan payoff: Mortgage" in lines
        assert "Net leveraged proceeds" in lines

    def test_cfbds_unaffected_by_resale(self):
        """Resale is below the line — CFBDS identical with and without
        it (the golden CSVs end at CFBDS; nothing there may move)."""
        resale = Resale(method="cap_noi_forward_12", exit_cap_rate=8.0)
        with_resale = run_property(build_model(resale))
        model = build_model(resale)
        model.valuation = None
        without = run_property(model)
        assert with_resale.ledger.frame[CFBDS].equals(
            without.ledger.frame[CFBDS])

    def test_direct_cap_refused_until_step_5(self):
        resale = Resale(method="cap_noi_forward_12", exit_cap_rate=8.0)
        model = build_model(resale)
        model.valuation.direct_cap = DirectCap(cap_rate=7.0)
        with pytest.raises(NotImplementedError, match="Phase 3 Step 5"):
            run_property(model)
