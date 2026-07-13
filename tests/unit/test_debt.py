"""Unit tests for the debt engine (Phase 3 Step 3; engine/calc/debt.py).

Cites per Iron Rule 3: monthly rate = annual / 12 (the default "12
Months" Calc Method [AE p. 443]); the closed-form level payment is spec
§3.17's normative statement; additional-principal fixed-payment behavior
is the [AE p. 444] "Recalc Pmt: No" option; loan costs post to the Cash
Flow's financing section [AE p. 446]; loan proceeds are display-only by
default [AE p. 447].

Validation path: no golden has loans — these closed-form tests plus the
owner's bank-amortization-calculator hand-check (NEXT_STEPS_TO_GATE3.md
Step 0) ARE the designed validation. The headline hand-check case:
$1,000,000 at 6.00% amortized over 30 years → monthly payment $5,995.51,
balance after 12 payments $987,719.88, balloon if due in 120 months
$836,857.25.
"""
import datetime as dt

import pandas as pd
import pytest

from engine.calc.debt import (
    assert_debt_invariants,
    build_loan_schedule,
    level_payment,
)
from engine.calc.ledger import (
    CFADS,
    CFBDS,
    DEBT_FUNDING,
    INTEREST_EXPENSE,
    LOAN_COSTS,
    PRINCIPAL_PAYMENTS,
    TOTAL_DEBT_SERVICE,
)
from engine.calc.run import run_property
from engine.calc.timeline import build_month_index
from engine.models import (
    AreaMeasures,
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
from engine.models.investment import (
    AdditionalPrincipal,
    FloatingRate,
    Loan,
    LoanAmount,
    LoanCosts,
)

BEGIN = dt.date(2026, 1, 1)
MONTHS = build_month_index(BEGIN, 5)  # 60 + 12 look-forward
FLAT = Inflation(general_rate=[YearRate(year=1, rate=0.0)],
                 timing_basis=TimingBasis.analysis_year)


def month(text):
    return pd.Period(text, freq="M")


def build(loan, purchase=None, months=MONTHS):
    return build_loan_schedule(loan, months, BEGIN, purchase, FLAT)


def thirty_year(**overrides):
    fields = dict(
        name="Mortgage", amount=LoanAmount(value=1_000_000.0),
        term_months=360, rate=6.0, amortization="fully_amortizing",
    )
    fields.update(overrides)
    return Loan(**fields)


class TestStandardAmortization:
    """The owner's Step 0 hand-check case [AE p. 443; spec §3.17]:
    $1,000,000, 6.00%, 30-year amortization."""

    def test_level_payment_formula(self):
        assert level_payment(1_000_000.0, 0.06 / 12, 360) == pytest.approx(
            5_995.51, abs=0.01)

    def test_first_month_split_and_year_one_balance(self):
        """Month 1: interest = 1,000,000 × 0.005 = 5,000.00, principal =
        995.51. Balance after 12 payments = 987,719.88 — the number to
        put into any bank amortization calculator."""
        schedule = build(thirty_year())
        first = schedule.frame.iloc[0]
        assert first["payment"] == pytest.approx(5_995.51, abs=0.01)
        assert first["interest"] == pytest.approx(5_000.00, abs=0.005)
        assert first["principal"] == pytest.approx(995.51, abs=0.01)
        assert schedule.frame.iloc[11]["ending"] == pytest.approx(
            987_719.88, abs=0.01)
        assert_debt_invariants(schedule)

    def test_fully_amortizing_reaches_zero_at_maturity(self):
        """§9.3: ending balance at maturity ~$0 for fully_amortizing."""
        short = build(thirty_year(term_months=60, amortization=60 // 12))
        # 5-year term amortized over 5 years = fully amortizing shape
        assert short.frame.iloc[-1]["ending"] == pytest.approx(0.0,
                                                               abs=0.01)
        assert short.balloon == pytest.approx(0.0, abs=0.01)

    def test_balloon_amortized_30_due_in_120(self):
        """'Amortized over N years, due in M months' [AE p. 438 Quick
        Start — Balloon Payments]: payment sized to the 30-year
        amortization (5,995.51); the month-120 balance, 836,857.25,
        posts as the balloon."""
        schedule = build(thirty_year(term_months=120, amortization=30))
        assert schedule.frame.iloc[0]["payment"] == pytest.approx(
            5_995.51, abs=0.01)
        assert schedule.balloon == pytest.approx(836_857.25, abs=0.01)
        assert schedule.frame.iloc[-1]["ending"] == 0.0
        assert_debt_invariants(schedule)

    def test_interest_only_loan_balloons_full_principal(self):
        """[AE p. 438] 'Interest Only: Calculate only interest loan
        payments' — principal untouched, the whole amount balloons."""
        schedule = build(thirty_year(term_months=60,
                                     amortization="interest_only"))
        assert (schedule.frame["principal"] == 0.0).all()
        assert (schedule.frame["interest"] - 5_000.0).abs().max() < 1e-9
        assert schedule.balloon == pytest.approx(1_000_000.0)
        assert_debt_invariants(schedule)

    def test_io_period_then_relevel(self):
        """interest_only_months = 24 on a 360-month fully-amortizing
        loan: 24 months of 5,000.00 interest-only, then the payment
        levels to amortize 1,000,000 over the remaining 336 months =
        6,151.24."""
        schedule = build(thirty_year(interest_only_months=24))
        frame = schedule.frame
        assert (frame.iloc[:24]["principal"] == 0.0).all()
        assert frame.iloc[0]["payment"] == pytest.approx(5_000.0)
        assert frame.iloc[24]["payment"] == pytest.approx(6_151.24,
                                                          abs=0.01)
        assert_debt_invariants(schedule)


class TestFloatingRate:
    """Floating = index + spread [spec §3.17; the manual's varying-rate
    Interest Rate Editor, AE pp. 441-442]; the payment re-levels on each
    effective-rate change over the remaining horizon (the [AE p. 444]
    'recalculate over the same term' behavior applied to rate
    changes)."""

    def test_reset_relevels_and_still_amortizes_to_zero(self):
        """$1,000,000 fully amortizing over 24 months; index 6% in
        analysis year 1, 7% in year 2 (no spread). Payments start the
        month after the 2026-01 funding, so 11 payments of 44,320.61
        fall in year 1 (balance 556,496.29 after 2026-12); at 2027-01
        the rate steps to 7% and the payment re-levels over the
        remaining 13 months to 44,575.71; the loan still reaches
        zero."""
        loan = thirty_year(
            type="floating", term_months=24,
            rate=FloatingRate(index=[YearRate(year=1, rate=6.0),
                                     YearRate(year=2, rate=7.0)]),
        )
        schedule = build(loan)
        frame = schedule.frame
        assert frame.iloc[0]["payment"] == pytest.approx(44_320.61,
                                                         abs=0.01)
        assert frame.iloc[10]["ending"] == pytest.approx(556_496.29,
                                                         abs=0.01)
        assert frame.iloc[11]["rate"] == 7.0  # 2027-01, analysis yr 2
        assert frame.iloc[11]["payment"] == pytest.approx(44_575.71,
                                                          abs=0.01)
        assert frame.iloc[-1]["ending"] == pytest.approx(0.0, abs=0.01)
        assert schedule.balloon == pytest.approx(0.0, abs=0.01)
        assert_debt_invariants(schedule)

    def test_spread_adds_to_index(self):
        loan = thirty_year(
            type="floating", term_months=24,
            rate=FloatingRate(index=[YearRate(year=1, rate=4.0)],
                              spread=2.0),
        )
        schedule = build(loan)
        assert (schedule.frame["rate"] == 6.0).all()
        assert schedule.frame.iloc[0]["payment"] == pytest.approx(
            44_320.61, abs=0.01)


class TestAdditionalPrincipal:
    """[AE p. 444] 'Recalc Pmt: No' behavior (the schema has no toggle —
    DEVIATIONS.md §18): originally scheduled payments continue, payoff
    shortens."""

    def test_payment_unchanged_and_early_payoff(self):
        loan = thirty_year(
            term_months=360,
            additional_principal=[AdditionalPrincipal(
                date=dt.date(2027, 1, 1), amount=500_000.0)],
        )
        schedule = build(loan)
        frame = schedule.frame
        paydown_month = month("2027-01")
        assert frame.loc[paydown_month, "additional_principal"] == (
            pytest.approx(500_000.0))
        # payment does NOT re-level
        assert frame.loc[month("2027-02"), "payment"] == pytest.approx(
            5_995.51, abs=0.01)
        # payoff shortens: with half the balance gone, the loan
        # extinguishes long before month 360
        payoff = frame[frame["ending"] <= 0.01].index[0]
        assert payoff < schedule.maturity_month
        assert (frame.loc[frame.index > payoff, "payment"] == 0.0).all()
        assert_debt_invariants(schedule)

    def test_total_principal_returned_equals_draw(self):
        """Across scheduled principal + paydown + balloon, exactly the
        original draw comes back (maturity in-window)."""
        loan = thirty_year(
            term_months=48, amortization=30,
            additional_principal=[AdditionalPrincipal(
                date=dt.date(2027, 1, 1), amount=200_000.0)],
        )
        schedule = build(loan)
        assert -schedule.principal.sum() == pytest.approx(1_000_000.0,
                                                          abs=0.01)


class TestLoanCosts:
    """[AE pp. 445-446]: points/fees post to the financing section."""

    def test_expense_lump_at_funding(self):
        loan = thirty_year(loan_costs=LoanCosts(points_pct=1.0,
                                                fees=10_000.0))
        schedule = build(loan)
        assert schedule.loan_costs[month("2026-01")] == pytest.approx(
            -20_000.0)
        assert schedule.loan_costs.sum() == pytest.approx(-20_000.0)

    def test_amortize_posts_full_cost_at_funding_like_expense(self):
        """Codex #3 fix (DEVIATIONS.md §24): amortize/expense are the same
        for cash timing — the fee is paid in full at funding in both cases
        (the amortize/expense distinction is tax-basis, not modeled here).
        OLD behavior spread 12,000 over 120 months at 100/month; NEW posts
        the full 12,000 at funding (2026-01)."""
        loan = thirty_year(
            term_months=120,
            loan_costs=LoanCosts(points_pct=0.0, fees=12_000.0,
                                 handling="amortize"),
        )
        schedule = build(loan)
        assert schedule.loan_costs[month("2026-01")] == pytest.approx(
            -12_000.0)
        assert schedule.loan_costs.sum() == pytest.approx(-12_000.0)

    def test_amortize_and_expense_have_identical_cash_timing(self):
        """The two handling values now produce byte-identical loan-cost
        series for the same loan."""
        base = dict(term_months=120)
        amort = build(thirty_year(
            loan_costs=LoanCosts(points_pct=1.0, fees=5_000.0,
                                 handling="amortize"), **base))
        exp = build(thirty_year(
            loan_costs=LoanCosts(points_pct=1.0, fees=5_000.0,
                                 handling="expense"), **base))
        assert amort.loan_costs.equals(exp.loan_costs)
        assert amort.loan_costs[month("2026-01")] == pytest.approx(-15_000.0)


class TestAmountBases:
    def test_pct_of_price(self):
        purchase = Purchase(price=2_000_000.0)
        loan = thirty_year(amount=LoanAmount(basis="pct_of_price",
                                             value=65.0))
        schedule = build(loan, purchase=purchase)
        assert schedule.principal0 == pytest.approx(1_300_000.0)

    def test_pct_of_price_without_purchase_raises(self):
        loan = thirty_year(amount=LoanAmount(basis="pct_of_price",
                                             value=65.0))
        with pytest.raises(ValueError, match="needs a purchase price"):
            build(loan)

    def test_pct_of_value_refuses_as_open_scope(self):
        """'% of Adopted Valuation' [AE p. 438]: after Step 5 built
        valuation, a value-sized loan is an open owner scope decision
        (debt at pass 12 needs the valuation from pass 14 —
        DEVIATIONS.md §20), refused loudly."""
        loan = thirty_year(amount=LoanAmount(basis="pct_of_value",
                                             value=65.0))
        with pytest.raises(NotImplementedError,
                           match="OPEN OWNER SCOPE DECISION"):
            build(loan)


class TestInvariants:
    """§9.3 debt invariants (Part C) — positive on every built schedule
    (asserted in run_property too), negative on a corrupted one."""

    def test_corrupted_balance_roll_raises(self):
        schedule = build(thirty_year())
        schedule.frame.iloc[10, schedule.frame.columns.get_loc(
            "opening")] += 1_000.0
        with pytest.raises(ValueError, match="does not roll"):
            assert_debt_invariants(schedule)

    def test_pre_window_funding_carries_balance_in(self):
        """Existing loans 'modeled back to their original start date'
        [AE p. 442]: only in-window months post; the window opens at the
        loan's then-current balance."""
        loan = thirty_year(funding_date=dt.date(2025, 1, 1))
        schedule = build(loan)
        assert schedule.funding.sum() == 0.0  # proceeds pre-window
        # payments run 2025-02..2026-01 = 12 by the window's first month:
        # ending balance 987,719.88 (the same year-one hand-check number)
        assert schedule.balance[month("2026-01")] == pytest.approx(
            987_719.88, abs=0.01)
        assert schedule.interest[month("2026-01")] < 0.0


class TestLedgerWiring:
    """The financing section (spec §2.3 tree): Total Debt Service =
    Interest + Principal + Loan Costs; CFADS = CFBDS + Total Debt
    Service; Debt Funding is display-only, outside CFADS [AE p. 447
    'Show Loan Proceeds' default No; spec §4.1 pass 14 equity at t0]."""

    def build_model(self, loans):
        lease = Lease(
            tenant_name="T", area=12_000, lease_type="industrial",
            start_date=BEGIN, term_months=60,
            base_rent=MoneyRate(
                amount=10.0, unit=MoneyUnit.dollars_per_area_per_year),
            upon_expiration=UponExpiration.vacate,
        )
        return PropertyModel(
            property=PropertyInfo(name="Debt", property_type="industrial",
                                  analysis_begin=BEGIN,
                                  analysis_term_years=5),
            area_measures=AreaMeasures(
                property_size=12_000,
                rentable_area_mode=RentableAreaMode.fixed,
                rentable_area_fixed=12_000,
            ),
            inflation=FLAT,
            rent_roll=[lease],
            loans=list(loans),
        )

    def test_two_loans_aggregate_and_cfads_identity(self):
        first = thirty_year(name="A")
        second = thirty_year(
            name="B", amount=LoanAmount(value=500_000.0), rate=5.0,
            term_months=120, amortization="interest_only",
            loan_costs=LoanCosts(points_pct=1.0, fees=0.0),
        )
        result = run_property(self.build_model([first, second]))
        frame = result.ledger.frame
        m1 = month("2026-02")
        # loan A month-1: interest 5,000; loan B: 500,000 × 5%/12
        assert frame[INTEREST_EXPENSE][m1] == pytest.approx(
            -(5_000.0 + 500_000.0 * 0.05 / 12), abs=0.01)
        assert frame[DEBT_FUNDING][month("2026-01")] == pytest.approx(
            1_500_000.0)
        assert frame[LOAN_COSTS][month("2026-01")] == pytest.approx(
            -5_000.0)
        tds = (frame[INTEREST_EXPENSE] + frame[PRINCIPAL_PAYMENTS]
               + frame[LOAN_COSTS])
        assert (frame[TOTAL_DEBT_SERVICE] - tds).abs().max() < 1e-9
        cfads = frame[CFBDS] + frame[TOTAL_DEBT_SERVICE]
        assert (frame[CFADS] - cfads).abs().max() < 1e-9
        # Debt Funding is OUTSIDE the CFADS rollup
        assert frame[CFADS][month("2026-01")] != pytest.approx(
            cfads[month("2026-01")] + 1_500_000.0)
        # per-loan detail retained for the §7 report 20 builder
        assert [s.loan.name for s in result.loan_schedules] == ["A", "B"]

    def test_noi_and_cfbds_unaffected_by_debt(self):
        bare = run_property(self.build_model([]))
        levered = run_property(self.build_model([thirty_year()]))
        assert levered.ledger.frame[CFBDS].equals(bare.ledger.frame[CFBDS])


class TestValidationFixes:
    """Regression tests for the 2026-07-12 Codex-review direct fixes
    (DEVIATIONS.md §22): loan-name uniqueness (#4), additional-principal
    window (#11), economic sanity bounds (#12)."""

    def model_with_loans(self, loans):
        lease = Lease(
            tenant_name="T", area=12_000, lease_type="industrial",
            start_date=BEGIN, term_months=60,
            base_rent=MoneyRate(
                amount=10.0, unit=MoneyUnit.dollars_per_area_per_year),
            upon_expiration=UponExpiration.vacate)
        return PropertyModel(
            property=PropertyInfo(name="Debt", property_type="industrial",
                                  analysis_begin=BEGIN, analysis_term_years=5),
            area_measures=AreaMeasures(
                property_size=12_000,
                rentable_area_mode=RentableAreaMode.fixed,
                rentable_area_fixed=12_000),
            inflation=FLAT, rent_roll=[lease], loans=list(loans))

    def test_duplicate_loan_names_refused(self):
        """#4: two loans with the same name would collapse in the
        payoff dict, understating debt payoff. Refuse at model
        validation, like every other named collection."""
        with pytest.raises(ValueError, match="duplicate names in loans"):
            self.model_with_loans([thirty_year(name="Senior"),
                                   thirty_year(name="Senior")])

    def test_additional_principal_before_window_refused(self):
        """#11: an additional-principal date before the first payment
        month would be silently dropped — refuse loudly instead."""
        loan = thirty_year(additional_principal=[AdditionalPrincipal(
            date=dt.date(2025, 6, 1), amount=100_000.0)])  # before funding
        with pytest.raises(ValueError, match="outside the loan's active window"):
            build(loan)

    def test_additional_principal_after_maturity_refused(self):
        loan = thirty_year(term_months=60, additional_principal=[
            AdditionalPrincipal(date=dt.date(2040, 1, 1), amount=100_000.0)])
        with pytest.raises(ValueError, match="outside the loan's active window"):
            build(loan)

    def test_additional_principal_inside_window_still_works(self):
        """The guard doesn't reject valid in-window paydowns."""
        loan = thirty_year(additional_principal=[AdditionalPrincipal(
            date=dt.date(2027, 1, 1), amount=100_000.0)])
        schedule = build(loan)
        assert schedule.frame.loc[month("2027-01"),
                                  "additional_principal"] == pytest.approx(
            100_000.0)

    def test_negative_fixed_rate_refused(self):
        with pytest.raises(ValueError, match="outside the sane range 0-100"):
            thirty_year(rate=-1.0)

    def test_absurd_fixed_rate_refused(self):
        """A rate typed as 650 (meaning 6.5%) is caught."""
        with pytest.raises(ValueError, match="outside the sane range 0-100"):
            thirty_year(rate=650.0)

    def test_zero_amortization_years_refused(self):
        with pytest.raises(ValueError, match="positive number of years"):
            thirty_year(amortization=0, term_months=60)

    def test_negative_loan_cost_fields_refused(self):
        with pytest.raises(ValueError):
            LoanCosts(points_pct=-1.0)
        with pytest.raises(ValueError):
            LoanCosts(fees=-500.0)
