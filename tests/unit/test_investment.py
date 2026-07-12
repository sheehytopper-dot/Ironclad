"""Unit tests for acquisition flows and security deposits (Phase 3
Step 2; engine/calc/investment.py).

Cites per Iron Rule 3: purchase information and its Enter Price default
[AE p. 435]; Total Price = Purchase Price + Closing Costs [AE p. 436];
closing costs as $ Amount or % Purchase Price [AE pp. 436-437]; security
deposit units — "Months: ... multiplied by the base rental revenue in
the first month of the lease", "$ / Area: ... multiplied by the lease
size in month one" [AE pp. 432-433]; on rollover "the input under the
leasing profile will be used" [AE p. 384].

EXTERNALLY UNVALIDATED: no golden fixture populates purchase or
security_deposit (DEVIATIONS.md §17) — these manual-definition and
engineered tests are the only proof.
"""
import datetime as dt

import pandas as pd
import pytest

from engine.calc.ledger import (
    CFBDS,
    CLOSING_COSTS,
    PURCHASE_PRICE,
    SECURITY_DEPOSITS,
)
from engine.calc.run import run_property
from engine.models import (
    AreaMeasures,
    Inflation,
    Lease,
    MarketLeasingProfile,
    MoneyRate,
    MoneyUnit,
    PctOfNew,
    PropertyInfo,
    PropertyModel,
    Purchase,
    RentableAreaMode,
    SecurityDepositSpec,
    SecurityDepositUnit,
    TimingBasis,
    UponExpiration,
    YearRate,
)
from engine.models.investment import ClosingCost, PriceDerivation

BEGIN = dt.date(2026, 1, 1)
PSF_YR = MoneyUnit.dollars_per_area_per_year
FLAT = Inflation(general_rate=[YearRate(year=1, rate=0.0)],
                 timing_basis=TimingBasis.analysis_year)


def month(text):
    return pd.Period(text, freq="M")


def build_model(leases, *, profiles=(), purchase=None, size=12_000, years=5):
    return PropertyModel(
        property=PropertyInfo(name="Inv", property_type="industrial",
                              analysis_begin=BEGIN,
                              analysis_term_years=years),
        area_measures=AreaMeasures(
            property_size=size,
            rentable_area_mode=RentableAreaMode.fixed,
            rentable_area_fixed=size,
        ),
        inflation=FLAT,
        market_leasing_profiles=list(profiles),
        rent_roll=list(leases),
        purchase=purchase,
    )


def basic_lease(**overrides):
    fields = dict(
        tenant_name="T", area=12_000, lease_type="industrial",
        start_date=BEGIN, term_months=24,
        base_rent=MoneyRate(amount=10.0, unit=PSF_YR),  # 10,000/mo
        upon_expiration=UponExpiration.vacate,
    )
    fields.update(overrides)
    return Lease(**fields)


class TestPurchaseAndClosing:
    """Purchase price + closing costs [AE pp. 435-437], below the line."""

    def test_fixed_price_with_dollar_and_pct_closing_costs(self):
        """The [AE pp. 436-437] shape: Enter Price 10,000,000 at the
        analysis begin (the manual's assumed purchase date [AE p. 435]),
        a $50,000 '$ Amount' cost and a 1.5% '% Purchase Price' cost
        (150,000). Total Price = Purchase Price + Closing Costs =
        10,200,000 [AE p. 436]."""
        purchase = Purchase(price=10_000_000.0, closing_costs=[
            ClosingCost(name="Legal", amount=50_000.0),
            ClosingCost(name="Transfer Tax", pct_of_price=1.5),
        ])
        result = run_property(build_model([basic_lease()], purchase=purchase))
        price = result.ledger.frame[PURCHASE_PRICE]
        closing = result.ledger.frame[CLOSING_COSTS]
        assert price[month("2026-01")] == pytest.approx(-10_000_000.0)
        assert closing[month("2026-01")] == pytest.approx(-200_000.0)
        assert price.drop(month("2026-01")).abs().sum() == 0.0
        assert closing.drop(month("2026-01")).abs().sum() == 0.0
        total_price = -(price.sum() + closing.sum())
        assert total_price == pytest.approx(10_200_000.0)

    def test_explicit_purchase_date_and_custom_date_closing_cost(self):
        """The schema's optional date is honored (ARGUS itself fixes the
        purchase at analysis begin [AE p. 435] — DEVIATIONS.md §17); a
        custom_date closing cost posts in its own month (spec §3.16)."""
        purchase = Purchase(
            price=5_000_000.0, date=dt.date(2026, 4, 1),
            closing_costs=[ClosingCost(name="Deferred Fee", amount=40_000.0,
                                       timing="custom_date",
                                       date=dt.date(2026, 9, 1))],
        )
        result = run_property(build_model([basic_lease()], purchase=purchase))
        assert result.ledger.frame[PURCHASE_PRICE][month("2026-04")] == (
            pytest.approx(-5_000_000.0))
        assert result.ledger.frame[CLOSING_COSTS][month("2026-09")] == (
            pytest.approx(-40_000.0))
        assert result.ledger.frame[CLOSING_COSTS][month("2026-04")] == 0.0

    def test_purchase_outside_timeline_raises(self):
        """No silent drops: an out-of-window purchase date is a modeling
        error, not a no-op."""
        purchase = Purchase(price=1.0, date=dt.date(2040, 1, 1))
        with pytest.raises(ValueError, match="outside the analysis timeline"):
            run_property(build_model([basic_lease()], purchase=purchase))

    @pytest.mark.parametrize("derivation", [
        PriceDerivation.pv_at_discount_rate, PriceDerivation.direct_cap,
    ])
    def test_derived_price_refuses_loudly(self, derivation):
        """The derived derivations (PV / direct cap [AE pp. 435-436])
        refuse loudly — live derivation is an open owner scope decision
        after Step 5 (DEVIATIONS.md §20), never a silent no-op or a wrong
        number."""
        purchase = Purchase(derivation=derivation)
        with pytest.raises(NotImplementedError,
                           match="OPEN OWNER SCOPE DECISION"):
            run_property(build_model([basic_lease()], purchase=purchase))

    def test_cfbds_and_noi_unaffected(self):
        """Acquisition flows are below the line — CFBDS/NOI identical
        with and without a purchase ([AE p. 435]: purchase feeds return
        metrics, not the cash flow rollups; the golden CSVs end at
        CFBDS)."""
        purchase = Purchase(price=10_000_000.0, closing_costs=[
            ClosingCost(name="Legal", amount=50_000.0)])
        bare = run_property(build_model([basic_lease()]))
        bought = run_property(build_model([basic_lease()],
                                          purchase=purchase))
        assert bought.ledger.frame[CFBDS].equals(bare.ledger.frame[CFBDS])


class TestSecurityDeposits:
    """Deposit units and refunds [AE pp. 431-433]; below the line."""

    def run_with_deposit(self, spec, **lease_overrides):
        lease = basic_lease(security_deposit=spec, **lease_overrides)
        return run_property(build_model([lease]))

    def test_months_of_rent_collect_and_refund(self):
        """'Months: ... multiplied by the base rental revenue in the
        first month of the lease' [AE p. 432]: 2.0 × 10,000 = +20,000 at
        lease start, refunded −20,000 in the expiration month."""
        result = self.run_with_deposit(SecurityDepositSpec(
            amount=2.0, unit=SecurityDepositUnit.months_of_rent))
        deposits = result.ledger.frame[SECURITY_DEPOSITS]
        assert deposits[month("2026-01")] == pytest.approx(20_000.0)
        assert deposits[month("2027-12")] == pytest.approx(-20_000.0)
        assert deposits.sum() == pytest.approx(0.0)

    def test_months_basis_is_gross_of_free_rent(self):
        """The month-one basis is Base Rental Revenue, which posts gross
        of abatements — a free first month does not shrink the deposit
        [AE p. 432; p. 538 line definitions]."""
        result = self.run_with_deposit(
            SecurityDepositSpec(amount=2.0,
                                unit=SecurityDepositUnit.months_of_rent),
            free_rent={"months": 1.0},
        )
        deposits = result.ledger.frame[SECURITY_DEPOSITS]
        assert deposits[month("2026-01")] == pytest.approx(20_000.0)

    def test_dollars_per_area(self):
        """'$ / Area: ... multiplied by the lease size in month one'
        [AE p. 433]: 1.5 × 12,000 SF = 18,000."""
        result = self.run_with_deposit(SecurityDepositSpec(
            amount=1.5, unit=SecurityDepositUnit.dollars_per_area))
        deposits = result.ledger.frame[SECURITY_DEPOSITS]
        assert deposits[month("2026-01")] == pytest.approx(18_000.0)
        assert deposits[month("2027-12")] == pytest.approx(-18_000.0)

    def test_flat_dollars_non_refundable(self):
        """'$ Amount' unit [AE p. 433]; refunded_at_expiration=False is
        the manual's non-refundable section — no refund posts."""
        result = self.run_with_deposit(SecurityDepositSpec(
            amount=25_000.0, unit=SecurityDepositUnit.dollars,
            refunded_at_expiration=False))
        deposits = result.ledger.frame[SECURITY_DEPOSITS]
        assert deposits[month("2026-01")] == pytest.approx(25_000.0)
        assert deposits.sum() == pytest.approx(25_000.0)  # never returned

    def test_pre_analysis_start_refund_only(self):
        """A lease that started before the analysis collected its deposit
        pre-window; only the in-window refund posts (DEVIATIONS.md §17
        judgment call — the refund is a real cash event)."""
        result = self.run_with_deposit(
            SecurityDepositSpec(amount=2.0,
                                unit=SecurityDepositUnit.months_of_rent),
            start_date=dt.date(2025, 1, 1), term_months=24,  # ends 2026-12
        )
        deposits = result.ledger.frame[SECURITY_DEPOSITS]
        assert deposits[month("2026-12")] == pytest.approx(-20_000.0)
        assert deposits.sum() == pytest.approx(-20_000.0)

    def test_rollover_uses_the_profile_deposit(self):
        """'Once the lease expires, the input under the leasing profile
        will be used' [AE p. 384]: the contract deposit refunds at
        contract expiration; the speculative segment collects the MLP's
        deposit at segment start, sized on the blended month-one rent."""
        profile = MarketLeasingProfile(
            name="Market", term_months=36, renewal_probability=75.0,
            months_vacant=0.0,
            market_base_rent_new=MoneyRate(amount=12.0, unit=PSF_YR),
            market_base_rent_renew=PctOfNew(pct_of_new=100.0),
            security_deposit=SecurityDepositSpec(
                amount=1.0, unit=SecurityDepositUnit.months_of_rent),
            upon_expiration=UponExpiration.market, term_growth=False,
        )
        lease = basic_lease(
            security_deposit=SecurityDepositSpec(
                amount=2.0, unit=SecurityDepositUnit.months_of_rent),
            market_leasing_profile="Market",
            upon_expiration=UponExpiration.market,
        )
        result = run_property(build_model([lease], profiles=[profile]))
        deposits = result.ledger.frame[SECURITY_DEPOSITS]
        # contract: +20,000 at 2026-01, −20,000 at 2027-12
        assert deposits[month("2026-01")] == pytest.approx(20_000.0)
        # rollover month: contract refund lands 2027-12, spec collection
        # 2028-01 — blended rent 12 $/SF/yr × 12,000 SF / 12 = 12,000/mo
        assert deposits[month("2027-12")] == pytest.approx(-20_000.0)
        assert deposits[month("2028-01")] == pytest.approx(12_000.0)
        # spec segment ends 2030-12 (in-window): its refund posts there
        assert deposits[month("2030-12")] == pytest.approx(-12_000.0)

    def test_deposits_outside_noi_egr_cfbds(self):
        """Deposits are below the line: NOI/EGR/CFBDS identical with and
        without them."""
        bare = run_property(build_model([basic_lease()]))
        with_dep = self.run_with_deposit(SecurityDepositSpec(
            amount=2.0, unit=SecurityDepositUnit.months_of_rent))
        for line in (CFBDS, "Net Operating Income",
                     "Effective Gross Revenue"):
            assert with_dep.ledger.frame[line].equals(
                bare.ledger.frame[line])
        assert with_dep.security_deposits["T"].sum() == pytest.approx(0.0)
