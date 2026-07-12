"""Unit tests for lease chain resolution (Phase 2, Step 1;
engine/calc/leases.py §4.1-pass-3 section).

Cites per Iron Rule 3: MLP fields and defaults [AE pp. 233-235], blending
("Intelligent Renewals", weighted items) [AE pp. 235-236], fixed steps
within market leases [AE p. 237], free rent new/renew [AE p. 239], TI
weighting [AE pp. 245-246], LC forms [AE pp. 246-248], upon-expiration
chaining [AE p. 251]. The §4.2 hand-computed blending example uses the
Clorox golden's inputs, whose transcribed FY2029 lines corroborate the
arithmetic externally (asserted at Gate 2, Step 2 — not here).
"""
import datetime as dt

import pandas as pd
import pytest

from engine.calc.leases import (
    resolve_lease_chain,
    segment_rent_level,
)
from engine.calc.timeline import build_month_index
from engine.models import (
    Inflation,
    IntelligentRenewalRule,
    LCSpec,
    Lease,
    MarketLeasingProfile,
    MoneyRate,
    MoneyUnit,
    PctOfNew,
    RentStep,
    TimingBasis,
    UponExpiration,
    YearRate,
)

BEGIN = dt.date(2026, 6, 1)
MONTHS = build_month_index(BEGIN, 5)  # through 2032-05 (resale look-forward)
INFLATION = Inflation(
    general_rate=[YearRate(year=2027, rate=3.0)],
    market_rent_rate=[YearRate(year=2027, rate=3.0)],
    inflation_month=1,
    timing_basis=TimingBasis.calendar_year,
)

PSF_YR = MoneyUnit.dollars_per_area_per_year


def clorox_profile(**overrides):
    """The Clorox golden's MLP (tests/golden/clorox_northlake fixture)."""
    fields = dict(
        name="Industrial Market NNN",
        term_months=60,
        renewal_probability=75.0,
        months_vacant=9.0,
        market_base_rent_new=MoneyRate(amount=7.15, unit=PSF_YR),
        market_base_rent_renew=PctOfNew(pct_of_new=100.0),
        rent_increases=[
            RentStep(month_offset=off, pct_increase=3.5)
            for off in (12, 24, 36, 48)
        ],
        free_rent_months_new=3.0,
        free_rent_months_renew=0.0,
        ti_new=MoneyRate(amount=2.0, unit=MoneyUnit.dollars_per_area),
        ti_renew=MoneyRate(amount=0.5, unit=MoneyUnit.dollars_per_area),
        lc_new=LCSpec(pct=6.75),
        lc_renew=LCSpec(pct=6.75),
        upon_expiration=UponExpiration.market,
        term_growth=True,
    )
    fields.update(overrides)
    return MarketLeasingProfile(**fields)


def clorox_lease(**overrides):
    fields = dict(
        tenant_name="The Clorox Sales Company",
        area=540_000,
        lease_type="industrial",
        start_date=dt.date(2005, 2, 26),
        end_date=dt.date(2028, 8, 31),
        base_rent=MoneyRate(amount=216_359.95, unit=MoneyUnit.dollars_per_month),
        rent_steps=[
            RentStep(date=dt.date(2027, 6, 1), amount=222_850.74,
                     unit=MoneyUnit.dollars_per_month),
            RentStep(date=dt.date(2028, 6, 1), amount=229_536.27,
                     unit=MoneyUnit.dollars_per_month),
        ],
        market_leasing_profile="Industrial Market NNN",
        upon_expiration=UponExpiration.market,
    )
    fields.update(overrides)
    return Lease(**fields)


def resolve(lease, profile):
    return resolve_lease_chain(
        lease, MONTHS, BEGIN, INFLATION, {profile.name: profile}
    )


class TestBlendingHandExample:
    """The §4.2 blending algorithm, hand-computed on the Clorox inputs
    [AE pp. 234-236; spec §4.2].

    p = 75%, months_vacant = 9 → downtime = round(0.25 × 9) = 2 months.
    Lease expires 2028-08 → downtime 2028-09/10, segment starts 2028-11.
    Market rent 7.15 $/SF/yr × 540,000 SF / 12 = 321,750/mo, inflated on
    the market index (3% stepping each January, calendar basis: Jan 2027
    and Jan 2028 precede 2028-11) → 321,750 × 1.03² = 341,344.575/mo.
    Renew = 100% of new → blended = 341,344.575. Weighted free rent =
    0.75 × 0 + 0.25 × 3 = 0.75 months. (The golden's transcribed FY2029
    corroborates: Free Rent 256,008 ≈ 0.75 × 341,344.575; A&T Vacancy
    682,689 ≈ 2 × 341,344.575.)
    """

    def test_segment_chain_shape(self):
        segments = resolve(clorox_lease(), clorox_profile())
        assert len(segments) == 2  # contract + one 5-yr rollover fills timeline
        contract, spec = segments
        assert not contract.speculative
        assert contract.end == pd.Period("2028-08", freq="M")
        assert spec.speculative
        assert spec.downtime_months == 2
        assert spec.downtime_start == pd.Period("2028-09", freq="M")
        assert spec.start == pd.Period("2028-11", freq="M")
        assert spec.end == pd.Period("2033-10", freq="M")  # 60 months
        assert spec.renewal_weight == pytest.approx(0.75)

    def test_blended_rent_inflated_to_segment_start(self):
        """New rent inflates with market inflation [AE p. 235]; renew =
        pct_of_new [AE p. 235 "Same as New"]; blend p×renew + (1−p)×new
        (spec §4.2)."""
        spec = resolve(clorox_lease(), clorox_profile())[1]
        assert spec.initial_rent_monthly == pytest.approx(321_750 * 1.03**2)

    def test_weighted_free_rent_ti_lc(self):
        """Weighted free rent [AE p. 239], TI [AE pp. 245-246], and LC
        [AE pp. 246-248] per §4.2: p×renew + (1−p)×new."""
        spec = resolve(clorox_lease(), clorox_profile())[1]
        assert spec.free_rent_months == pytest.approx(0.75)
        assert spec.ti.amount == pytest.approx(0.75 * 0.5 + 0.25 * 2.0)
        assert spec.ti.unit == MoneyUnit.dollars_per_area
        assert spec.lc_pct == pytest.approx(6.75)
        assert spec.lc_rate is None

    def test_no_term_growth_freezes_market_rent(self):
        """term_growth off → market rents do not inflate (spec §3.6)."""
        spec = resolve(clorox_lease(), clorox_profile(term_growth=False))[1]
        assert spec.initial_rent_monthly == pytest.approx(321_750.0)

    def test_market_steps_apply_within_segment(self):
        """MLP fixed % steps compound on each anniversary within the market
        lease term [AE p. 237]."""
        spec = resolve(clorox_lease(), clorox_profile())[1]
        initial = spec.initial_rent_monthly
        assert segment_rent_level(spec, spec.start) == pytest.approx(initial)
        assert segment_rent_level(spec, spec.start + 12) == pytest.approx(
            initial * 1.035
        )
        assert segment_rent_level(spec, spec.end) == pytest.approx(
            initial * 1.035**4
        )


class TestChaining:
    """Upon-expiration chaining [AE p. 251; spec §3.6]."""

    def test_market_repeats_until_timeline_end(self):
        profile = clorox_profile(term_months=12, months_vacant=4.0,
                                 renewal_probability=50.0)
        segments = resolve(clorox_lease(), profile)
        specs = [s for s in segments if s.speculative]
        assert len(specs) >= 3
        for i, seg in enumerate(specs):
            assert seg.downtime_months == 2  # round(0.5 × 4)
            # every rollover repeats: 12-month term + 2 months downtime
            assert seg.start == specs[0].start + 14 * i
        # each later segment starts later, so market inflation is larger
        assert specs[1].initial_rent_monthly > specs[0].initial_rent_monthly
        # chain covers the timeline and stops
        assert specs[-1].end >= MONTHS[-1]

    def test_vacate_ends_the_chain(self):
        segments = resolve(
            clorox_lease(upon_expiration=UponExpiration.vacate,
                         market_leasing_profile=None),
            clorox_profile(),
        )
        assert len(segments) == 1

    def test_reabsorb_ends_the_chain_for_absorption(self):
        """Reabsorbed space returns via the absorption engine (Step 3);
        the chain itself ends (spec §3.6). Since Phase 3 / Step 1 a
        reabsorb lease must carry a market_leasing_profile — it prices the
        post-expiration phantom (DEVIATIONS.md §8) — but the profile does
        NOT generate a successor segment."""
        segments = resolve(
            clorox_lease(upon_expiration=UponExpiration.reabsorb),
            clorox_profile(),
        )
        assert len(segments) == 1

    def test_renew_is_certain_renewal_on_renewal_terms(self):
        """'Renew: 100% renewal' (spec §3.6): no downtime, renewal-side
        economics at p = 1 [AE pp. 234-235]."""
        profile = clorox_profile(term_months=48)
        segments = resolve(
            clorox_lease(upon_expiration=UponExpiration.renew), profile
        )
        spec = segments[1]
        assert spec.downtime_months == 0
        assert spec.start == pd.Period("2028-09", freq="M")
        assert spec.renewal_weight == 1.0
        assert spec.free_rent_months == 0.0  # renew free rent
        assert spec.ti.amount == pytest.approx(0.5)  # renew TI only

    def test_option_chains_to_another_profile(self):
        option_term = clorox_profile(
            name="Option Terms", term_months=24,
            market_base_rent_new=MoneyRate(amount=6.0, unit=PSF_YR),
            upon_expiration=UponExpiration.vacate, term_growth=False,
        )
        lease = clorox_lease(upon_expiration=UponExpiration.option,
                             option_profile="Option Terms",
                             market_leasing_profile=None)
        segments = resolve_lease_chain(
            lease, MONTHS, BEGIN, INFLATION,
            {"Option Terms": option_term},
        )
        assert len(segments) == 2  # option term, then vacate
        assert segments[1].profile.name == "Option Terms"
        assert segments[1].end == segments[1].start + 23

    def test_pct_of_last_rent_uses_prior_stepped_rent(self):
        """'% of last rent' market rent = percent of the expiring contract
        rent including steps (spec §3.6; prior rent = standard rent
        [AE p. 236]), uninflated."""
        profile = clorox_profile(
            market_base_rent_new=MoneyRate(
                amount=50.0, unit=MoneyUnit.pct_of_last_rent
            ),
        )
        spec = resolve(clorox_lease(), profile)[1]
        # contract rent at 2028-08 after both steps: 229,536.27
        assert spec.initial_rent_monthly == pytest.approx(229_536.27 * 0.5)


class TestIntelligentRenewals:
    """"Use Market or Prior" renewal-rate rules [AE pp. 235-236]."""

    PRIOR = 229_536.27  # contract rent at expiration (stepped)

    def market_450(self, rule):
        """Profile whose renewal market rent is 450,000/mo (10 $/SF/yr on
        540,000 SF), far above the 229,536.27 prior rent."""
        return clorox_profile(
            market_base_rent_new=MoneyRate(amount=10.0, unit=PSF_YR),
            term_growth=False, intelligent_renewals=rule,
        )

    def blended(self, rule):
        spec = resolve(clorox_lease(), self.market_450(rule))[1]
        return spec.initial_rent_monthly

    def test_market_default_is_plain_blend(self):
        """Market (default): renewal side = renewal market rent
        [AE p. 236] — identical to Intelligent Renewals off."""
        assert self.blended(IntelligentRenewalRule.market) == pytest.approx(
            450_000.0  # renew = 100% of new = new → blend = new
        )

    def test_prior_uses_expiring_rent(self):
        """Prior: renewal rate is the prior rent [AE p. 236]."""
        assert self.blended(IntelligentRenewalRule.prior) == pytest.approx(
            0.75 * self.PRIOR + 0.25 * 450_000.0
        )

    def test_lesser_of_takes_the_smaller(self):
        """Use Lesser of: the smaller of prior rent and the renewal market
        rate [AE p. 236]."""
        assert self.blended(IntelligentRenewalRule.lesser_of) == pytest.approx(
            0.75 * min(self.PRIOR, 450_000.0) + 0.25 * 450_000.0
        )

    def test_greater_of_takes_the_larger(self):
        """Use Greater of: the larger of the two [AE p. 236]."""
        assert self.blended(IntelligentRenewalRule.greater_of) == pytest.approx(
            0.75 * max(self.PRIOR, 450_000.0) + 0.25 * 450_000.0
        )


class TestGuards:
    def test_pct_of_market_market_rent_rejected(self):
        """The manual's Rental Value machinery is not modeled; spec §3.6
        narrows market rent units (DEVIATIONS.md §7)."""
        profile = clorox_profile(
            market_base_rent_new=MoneyRate(amount=90.0,
                                           unit=MoneyUnit.pct_of_market),
        )
        with pytest.raises(ValueError, match="market base rent"):
            resolve(clorox_lease(), profile)

    def test_unknown_profile_ref_raises(self):
        with pytest.raises(ValueError, match="unknown market leasing profile"):
            resolve_lease_chain(clorox_lease(), MONTHS, BEGIN, INFLATION, {})

    def test_mixed_ti_units_rejected(self):
        profile = clorox_profile(
            ti_renew=MoneyRate(amount=100_000, unit=MoneyUnit.dollars),
        )
        with pytest.raises(ValueError, match="units differ"):
            resolve(clorox_lease(), profile)
