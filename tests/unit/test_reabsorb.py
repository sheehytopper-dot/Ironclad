"""Unit tests for upon_expiration 'reabsorb' on contract leases (Phase 3 /
Step 1; DEVIATIONS.md §8).

**All tests here are engineered — no golden fixture exercises reabsorb**
(Freeport's RSDS partial reabsorption was deliberately encoded without it),
so the feature ships externally unvalidated until a deal uses it. The
authoritative behavior is the owner's 2026-07-11 description of ARGUS AE
mechanics: the lease line retires at expiration; the space returns to the
vacant pool; Potential Base Rent carries its market value with an equal
Absorption & Turnover Vacancy deduction (netting $0) until Space Absorption
re-leases it or the analysis ends.
"""
import datetime as dt

import pandas as pd
import pytest

from engine.calc.run import run_property
from engine.models import (
    AbsorptionSpec,
    AreaMeasures,
    GeneralVacancy,
    Inflation,
    Lease,
    MarketLeasingProfile,
    MoneyRate,
    MoneyUnit,
    PctOfNew,
    PropertyInfo,
    PropertyModel,
    RecoveryAssignment,
    RentableAreaMode,
    VacancyMethod,
    YearRate,
)

BEGIN = dt.date(2026, 1, 1)
PSF_YR = MoneyUnit.dollars_per_area_per_year
FLAT = Inflation(general_rate=[YearRate(year=1, rate=0.0)])


def mla(**overrides):
    fields = dict(
        name="MLA", term_months=60, renewal_probability=75.0,
        months_vacant=6.0,
        market_base_rent_new=MoneyRate(amount=12.0, unit=PSF_YR),
        market_base_rent_renew=PctOfNew(pct_of_new=100.0),
        recoveries=RecoveryAssignment(method="net"),
        upon_expiration="market", term_growth=False,
    )
    fields.update(overrides)
    return MarketLeasingProfile(**fields)


def reabsorb_lease(area=20_000, term_months=12, **overrides):
    fields = dict(
        tenant_name="Big", area=area, lease_type="industrial",
        start_date=BEGIN, term_months=term_months,
        base_rent=MoneyRate(amount=10.0, unit=PSF_YR),
        market_leasing_profile="MLA", upon_expiration="reabsorb",
    )
    fields.update(overrides)
    return Lease(**fields)


def make_model(rent_roll, absorption=(), years=4, **overrides):
    fields = dict(
        property=PropertyInfo(name="T", property_type="industrial",
                              analysis_begin=BEGIN, analysis_term_years=years),
        area_measures=AreaMeasures(property_size=20_000,
                                   rentable_area_mode=RentableAreaMode.derived),
        inflation=FLAT,
        market_leasing_profiles=[mla()],
        rent_roll=list(rent_roll),
        absorption=list(absorption),
    )
    fields.update(overrides)
    return PropertyModel(**fields)


class TestNoLinkedSpec:
    """Engineered (no golden exercises reabsorb): with no AbsorptionSpec the
    full area phantoms — market-in / A&T-out, $0 net — from the month after
    expiration to the end of the timeline (the owner's ARGUS mechanics:
    'netting to $0 ... until it is dealt with elsewhere', including never)."""

    def test_full_area_phantom_to_timeline_end(self):
        result = run_property(make_model([reabsorb_lease()]))
        frame = result.ledger.frame
        # market 12 $/SF/yr × 20,000 SF / 12 = 20,000/mo phantom
        first_vacant = pd.Period("2027-01", freq="M")
        last = result.months[-1]
        for period in (first_vacant, pd.Period("2028-06", freq="M"), last):
            assert frame.loc[period, "Base Rental Revenue"] == pytest.approx(20_000)
            assert frame.loc[period, "Absorption & Turnover Vacancy"] == pytest.approx(-20_000)
            assert frame.loc[period, "Scheduled Base Rental Revenue"] == pytest.approx(0.0)
            assert frame.loc[period, "Net Operating Income"] == pytest.approx(0.0)
        # during the contract term: real rent, no phantom
        occupied = pd.Period("2026-06", freq="M")
        assert frame.loc[occupied, "Base Rental Revenue"] == pytest.approx(20_000 * 10 / 12)
        assert frame.loc[occupied, "Absorption & Turnover Vacancy"] == 0.0
        # the space stays in rentable area, occupied drops to zero
        assert float(result.rentable_area[first_vacant]) == pytest.approx(20_000)
        assert float(result.occupied_area[first_vacant]) == pytest.approx(0.0)


class TestStaggeredReabsorption:
    """Engineered (no golden exercises reabsorb): the owner's example — one
    20,000 SF reabsorbed tenant split into four 5,000 SF suites via
    staggered absorption — proving the A&T step-down and the exact $0 net
    on Scheduled Base / EGR / NOI while space sits vacant."""

    def model(self):
        spec = AbsorptionSpec(
            name="Refill", total_area=20_000, number_of_leases=4,
            start_date=dt.date(2027, 4, 1), interval_months=3,
            lease_type="industrial", market_leasing_profile="MLA",
            reabsorbed_from="Big",
        )
        return make_model([reabsorb_lease()], [spec], years=4)

    def test_step_down_and_zero_net(self):
        result = run_property(self.model())
        frame = result.ledger.frame
        # suites start 2027-04 / 07 / 10 / 2028-01; market = 1,000/mo per
        # 1,000 SF → phantom area steps 20k, 15k, 10k, 5k, 0
        expectations = {
            "2027-01": 20_000,  # fully vacant
            "2027-04": 15_000,  # suite 1 of 4 occupied
            "2027-07": 10_000,
            "2027-10": 5_000,
            "2028-01": 0,       # fully re-leased
            "2028-06": 0,
        }
        for month, phantom in expectations.items():
            period = pd.Period(month, freq="M")
            occupied_rent = (20_000 - phantom) * 12 / 12  # 12 $/SF/yr market
            assert frame.loc[period, "Absorption & Turnover Vacancy"] == pytest.approx(-phantom)
            assert frame.loc[period, "Base Rental Revenue"] == pytest.approx(20_000.0)  # market on full area
            assert frame.loc[period, "Scheduled Base Rental Revenue"] == pytest.approx(occupied_rent)
        # phantom months net to exactly $0 in Scheduled/EGR/NOI terms:
        # EGR and NOI equal Scheduled here (net recoveries, no expenses)
        vacant = pd.Period("2027-02", freq="M")
        assert frame.loc[vacant, "Effective Gross Revenue"] == pytest.approx(0.0)
        assert frame.loc[vacant, "Net Operating Income"] == pytest.approx(0.0)

    def test_derived_rentable_area_not_double_counted(self):
        """Flag-1 decision: derived rentable area keeps the reabsorbed
        lease's stated area as the permanent SF anchor and excludes the
        linked specs' generated leases — 20,000 SF throughout, never
        40,000."""
        result = run_property(self.model())
        assert (result.rentable_area == 20_000).all()
        # fully re-leased months are 100% occupied again
        assert float(result.occupied_area[pd.Period("2028-06", freq="M")]) == pytest.approx(20_000)


class TestGeneralVacancyOffset:
    """Engineered (no golden exercises reabsorb): the DEVIATIONS §8
    interaction that forced the phantom convention — general vacancy's
    reduce_by_absorption_turnover offset must consume the reabsorbed
    space's A&T, so total vacancy equals the stated rate, not rate +
    reabsorbed downtime stacked."""

    def test_offset_consumes_reabsorbed_phantom(self):
        model = make_model(
            [reabsorb_lease()],
            general_vacancy=GeneralVacancy(
                method=VacancyMethod.percent_of_pgr,
                rate=[YearRate(year=1, rate=5.0)],
                reduce_by_absorption_turnover=True,
            ),
        )
        frame = run_property(model).ledger.frame
        # occupied month: PGR = 16,666.67 rent; GV = 5%
        occupied = pd.Period("2026-06", freq="M")
        assert frame.loc[occupied, "General Vacancy"] == pytest.approx(
            -0.05 * frame.loc[occupied, "Total Potential Gross Revenue"])
        # reabsorbed month: A&T (20,000) dwarfs the 5% target → GV = 0,
        # not 5% charged on top of an already fully vacant space
        vacant = pd.Period("2027-06", freq="M")
        assert frame.loc[vacant, "Absorption & Turnover Vacancy"] == pytest.approx(-20_000)
        assert frame.loc[vacant, "General Vacancy"] == pytest.approx(0.0)


class TestValidation:
    """Engineered: the schema refuses inconsistent reabsorb inputs loudly
    (intake-surface standard — readable by a non-programmer)."""

    def test_reabsorb_requires_market_leasing_profile(self):
        with pytest.raises(ValueError, match="requires a market_leasing_profile"):
            reabsorb_lease(market_leasing_profile=None)

    def test_reabsorbed_from_must_name_a_reabsorb_lease(self):
        vacate = reabsorb_lease(upon_expiration="vacate",
                                market_leasing_profile=None)
        spec = AbsorptionSpec(
            name="Refill", total_area=5_000, number_of_leases=1,
            start_date=dt.date(2027, 1, 1), lease_type="industrial",
            market_leasing_profile="MLA", reabsorbed_from="Big",
        )
        with pytest.raises(ValueError, match="not 'reabsorb'"):
            make_model([vacate], [spec])
        spec_unknown = spec.model_copy(update={"reabsorbed_from": "Nobody"})
        with pytest.raises(ValueError, match="no rent roll lease"):
            make_model([reabsorb_lease()], [spec_unknown])

    def test_linked_spec_cannot_start_before_expiration(self):
        spec = AbsorptionSpec(
            name="Early", total_area=5_000, number_of_leases=1,
            start_date=dt.date(2026, 9, 1),  # lease runs through 2026-12
            lease_type="industrial", market_leasing_profile="MLA",
            reabsorbed_from="Big",
        )
        with pytest.raises(ValueError, match="not vacant yet"):
            make_model([reabsorb_lease()], [spec])

    def test_linked_area_cannot_exceed_lease_area(self):
        specs = [
            AbsorptionSpec(name=f"Part {i}", total_area=12_000,
                           number_of_leases=1,
                           start_date=dt.date(2027, 1 + i, 1),
                           lease_type="industrial",
                           market_leasing_profile="MLA",
                           reabsorbed_from="Big")
            for i in range(2)  # 24,000 SF against a 20,000 SF lease
        ]
        with pytest.raises(ValueError, match="leased twice"):
            make_model([reabsorb_lease()], specs)


class TestLeaseAuditWithReabsorb:
    """Engineered: the Lease Audit reconciles exactly (1e-9) on a
    multi-tenant property mixing a reabsorbed lease, its staggered linked
    absorption, and an ordinary market-rollover tenant; post-expiration
    months carry the 'reabsorbed' phase label."""

    def test_reconciles_and_labels(self):
        from engine.reports.lease_audit import lease_audit, reconcile_to_ledger

        other = Lease(
            tenant_name="Steady", area=10_000, lease_type="industrial",
            start_date=BEGIN, term_months=120,
            base_rent=MoneyRate(amount=15.0, unit=PSF_YR),
            upon_expiration="vacate",
        )
        spec = AbsorptionSpec(
            name="Refill", total_area=10_000, number_of_leases=2,
            start_date=dt.date(2027, 7, 1), interval_months=6,
            lease_type="industrial", market_leasing_profile="MLA",
            reabsorbed_from="Big",
        )
        model = make_model([reabsorb_lease(), other], [spec], years=4)
        result = run_property(model)
        report = lease_audit(result)
        differences = reconcile_to_ledger(report, result)
        assert float(differences.abs().max().max()) < 1e-9
        big = report[(report["tenant"] == "Big")
                     & (report["month"] == pd.Period("2027-03", freq="M"))]
        assert list(big["phase"]) == ["reabsorbed"]