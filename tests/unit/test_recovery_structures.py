"""Unit tests for user recovery structures + gross-up + the Recovery
Audit report (Phase 2, Step 5 session 2).

Cites per Iron Rule 3: the gross-up formula — fixed portion + variable
portion × (gross_up_pct / actual occupancy), never grossed down
[AE p. 407; formula p. 520]; variable-only applicability [AE p. 519];
double-counting warning [AE p. 408]; denominators [AE p. 410]; admin
fees as % of recoverable expenses [AE pp. 519-520]; caps/floors
[AE pp. 411-412]; expense adjustments [AE p. 410]; free-rent recovery
abatement elements [AE p. 254]. The audit report must reconcile exactly
to the ledger (spec §7 report 18; Gate 2)."""
import datetime as dt

import pandas as pd
import pytest

from engine.calc.expenses import project_expense
from engine.calc.recoveries import (
    RecoveryContext,
    project_recoveries,
)
from engine.calc.run import run_property
from engine.calc.timeline import build_month_index
from engine.models import (
    AreaMeasures,
    ExpenseGroup,
    ExpenseItem,
    ExpenseUnit,
    FreeRent,
    FreeRentProfile,
    Inflation,
    Lease,
    MoneyRate,
    MoneyUnit,
    PropertyInfo,
    PropertyModel,
    RecoveryAssignment,
    RecoveryPool,
    RecoveryStructure,
    RecoverySystemMethod,
    RentableAreaMode,
    YearRate,
)

BEGIN = dt.date(2026, 1, 1)
MONTHS = build_month_index(BEGIN, 2)
FLAT = Inflation(general_rate=[YearRate(year=1, rate=0.0)])


def make_lease(area=100_000, structure="S", **kwargs):
    fields = dict(
        tenant_name="Tenant", area=area, lease_type="industrial",
        start_date=BEGIN, term_months=60,
        base_rent=MoneyRate(amount=12.0,
                            unit=MoneyUnit.dollars_per_area_per_year),
        recoveries=RecoveryAssignment(
            method=RecoverySystemMethod.structure, structure_ref=structure,
        ),
        upon_expiration="vacate",
    )
    fields.update(kwargs)
    return Lease(**fields)


def expense(name, amount, **kwargs):
    return ExpenseItem(name=name, amount=amount,
                       unit=ExpenseUnit.dollars_per_year, **kwargs)


def project(item, occupancy=1.0):
    return item, project_expense(item, MONTHS, BEGIN, FLAT,
                                 occupancy=occupancy)


def make_context(structure, occupancy=1.0, groups=None,
                 property_size=100_000, occupied=None):
    occ = (occupancy if isinstance(occupancy, pd.Series)
           else pd.Series(float(occupancy), index=MONTHS))
    occupied = (occupied if occupied is not None
                else occ * property_size)
    return RecoveryContext(
        occupancy=occ, occupied_area=occupied, property_size=property_size,
        structures={structure.name: structure},
        expense_groups=groups or {},
    )


def structure_of(*pools, name="S"):
    return RecoveryStructure(name=name, pools=list(pools))


def run(structure, expenses, occupancy=1.0, lease=None, rentable=100_000,
        **ctx_kwargs):
    lease = lease or make_lease()
    context = make_context(structure, occupancy=occupancy, **ctx_kwargs)
    return project_recoveries(lease, MONTHS, expenses, rentable_area=rentable,
                              analysis_begin=BEGIN, inflation=FLAT,
                              context=context)


class TestGrossUp:
    """The gross-up formula [AE p. 407; formula p. 520]: fixed portion +
    variable portion × (gross_up_pct / actual occupancy), variable
    expenses only [AE p. 519], never grossed down."""

    def test_formula_at_70_pct_occupancy(self):
        """A 50%-fixed $120,000 expense at 70% occupancy posts 10,000 ×
        (0.5 + 0.5 × 0.7) = 8,500/mo; grossed to 95%: 10,000 ×
        (0.5 + 0.5 × 0.95) = 9,750/mo [AE pp. 407, 520]."""
        item = expense("CAM", 120_000, pct_fixed=50.0)
        structure = structure_of(RecoveryPool(expenses=["CAM"],
                                              gross_up_pct=95.0))
        series = run(structure, [project(item, occupancy=0.7)],
                     occupancy=0.7)
        assert series.iloc[0] == pytest.approx(9_750)

    def test_never_grosses_down(self):
        """Actual occupancy above the target leaves the expense untouched
        [AE p. 407 "never gross down"]."""
        item = expense("CAM", 120_000, pct_fixed=50.0)
        structure = structure_of(RecoveryPool(expenses=["CAM"],
                                              gross_up_pct=95.0))
        series = run(structure, [project(item, occupancy=0.98)],
                     occupancy=0.98)
        assert series.iloc[0] == pytest.approx(10_000 * (0.5 + 0.5 * 0.98))

    def test_fully_fixed_expense_unaffected(self):
        """Gross-up "will not affect recovery calculations for any
        recoverable operating expenses entered as 100% fixed"
        [AE p. 519]."""
        item = expense("Taxes", 120_000)  # pct_fixed defaults 100
        structure = structure_of(RecoveryPool(expenses=["Taxes"],
                                              gross_up_pct=95.0))
        series = run(structure, [project(item, occupancy=0.5)],
                     occupancy=0.5)
        assert series.iloc[0] == pytest.approx(10_000)

    def test_fully_variable_at_zero_occupancy_raises(self):
        """The pathological case (module docstring): a fully variable
        expense in a zero-occupancy month has no observable base to gross
        from — loud error, not a silent number."""
        occ = pd.Series(1.0, index=MONTHS)
        occ.iloc[3] = 0.0
        item = expense("Utilities", 120_000, pct_fixed=0.0)
        structure = structure_of(RecoveryPool(expenses=["Utilities"],
                                              gross_up_pct=95.0))
        with pytest.raises(ValueError, match="zero-occupancy"):
            run(structure, [project(item, occupancy=occ)], occupancy=occ)


class TestPoolsGroupsAdjustments:
    def test_group_membership_and_double_count_rejected(self):
        """Groups resolve to members; an expense reached twice — directly
        and via its group — is the double counting the manual warns about
        [AE p. 408]."""
        cam, tax = expense("CAM", 60_000), expense("Taxes", 60_000)
        good = structure_of(RecoveryPool(expenses=["Ops"]))
        series = run(good, [project(cam), project(tax)],
                     groups={"Ops": ["CAM", "Taxes"]})
        assert series.iloc[0] == pytest.approx(10_000)

        double = structure_of(RecoveryPool(expenses=["Ops", "CAM"]))
        with pytest.raises(ValueError, match="double counting"):
            run(double, [project(cam), project(tax)],
                groups={"Ops": ["CAM", "Taxes"]})

    def test_cross_pool_double_count_rejected(self):
        cam = expense("CAM", 60_000)
        structure = structure_of(RecoveryPool(expenses=["CAM"]),
                                 RecoveryPool(expenses=["CAM"]))
        with pytest.raises(ValueError, match="more than one pool"):
            run(structure, [project(cam)])

    def test_expense_adjustments_exclude_and_add(self):
        """Adjustments modify the pool basis by a percentage of a named
        expense [AE p. 410]: exclude 50% of Taxes, add 25% of Insurance
        (a non-member)."""
        cam, tax, ins = (expense("CAM", 60_000), expense("Taxes", 60_000),
                         expense("Insurance", 48_000))
        structure = structure_of(RecoveryPool(
            expenses=["CAM", "Taxes"],
            expense_adjustments=[
                {"expense": "Taxes", "action": "exclude", "pct": 50.0},
                {"expense": "Insurance", "action": "add", "pct": 25.0},
            ],
        ))
        series = run(structure, [project(cam), project(tax), project(ins)])
        # 5,000 + 5,000×0.5 + 4,000×0.25 = 8,500
        assert series.iloc[0] == pytest.approx(8_500)


class TestDenominatorsAndShare:
    """Pro-rata denominators [AE p. 410] and the share override."""

    CAM = expense("CAM", 120_000)

    def structure_with(self, **pool_kwargs):
        return structure_of(RecoveryPool(expenses=["CAM"], **pool_kwargs))

    def test_property_size_denominator(self):
        lease = make_lease(area=25_000)
        series = run(self.structure_with(denominator="property_size"),
                     [project(self.CAM)], lease=lease,
                     property_size=125_000)
        assert series.iloc[0] == pytest.approx(10_000 * 25_000 / 125_000)

    def test_fixed_area_denominator(self):
        lease = make_lease(area=25_000)
        series = run(self.structure_with(denominator="fixed_area",
                                         denominator_fixed_area=50_000),
                     [project(self.CAM)], lease=lease)
        assert series.iloc[0] == pytest.approx(10_000 * 0.5)

    def test_occupied_area_denominator(self):
        lease = make_lease(area=25_000)
        occupied = pd.Series(50_000.0, index=MONTHS)
        series = run(self.structure_with(denominator="occupied_area"),
                     [project(self.CAM)], lease=lease, occupied=occupied)
        assert series.iloc[0] == pytest.approx(10_000 * 0.5)

    def test_pro_rata_share_override(self):
        lease = make_lease(area=25_000)
        series = run(self.structure_with(pro_rata_share_override=40.0),
                     [project(self.CAM)], lease=lease)
        assert series.iloc[0] == pytest.approx(4_000)


class TestAdminFee:
    """Admin fee as % of recoverable expenses [AE pp. 519-520], added to
    the basis before or after the stop subtraction (spec §3.14)."""

    CAM = expense("CAM", 120_000)  # 10,000/mo pool

    def test_before_stop(self):
        structure = structure_of(RecoveryPool(
            expenses=["CAM"], method="stop", base_amount_per_area=0.72,
            admin_fee_pct=5.0, admin_fee_applies="before_stop",
        ))
        series = run(structure, [project(self.CAM)])
        # (10,000 × 1.05 − 6,000) × 100% = 4,500
        assert series.iloc[0] == pytest.approx(4_500)

    def test_after_stop(self):
        structure = structure_of(RecoveryPool(
            expenses=["CAM"], method="stop", base_amount_per_area=0.72,
            admin_fee_pct=5.0, admin_fee_applies="after_stop",
        ))
        series = run(structure, [project(self.CAM)])
        # (10,000 − 6,000) × 1.05 = 4,200
        assert series.iloc[0] == pytest.approx(4_200)


class TestCapsFloors:
    """Per-pool caps/floors [AE pp. 411-412]: annual min/max inflating on
    the general rate by default; YoY and cumulative growth caps."""

    def rising_cam(self):
        return project(expense("CAM", 120_000,
                               inflation=[YearRate(year=1, rate=10.0)]))

    def test_ceiling_clamps_monthly(self):
        structure = structure_of(RecoveryPool(
            expenses=["CAM"], caps_floors={"max": 96_000.0},
        ))
        series = run(structure, [project(expense("CAM", 120_000))])
        assert series.iloc[0] == pytest.approx(8_000)  # 96,000 / 12

    def test_floor_raises_and_inflates_on_general(self):
        """"By default, the floor will inflate by the general inflation
        rate" [AE p. 412]."""
        structure = structure_of(RecoveryPool(
            expenses=["CAM"], caps_floors={"min": 60_000.0},
        ))
        lease = make_lease()
        context = make_context(structure)
        three_pct = Inflation(general_rate=[YearRate(year=1, rate=3.0)])
        item = expense("CAM", 24_000, inflation=[YearRate(year=1, rate=0.0)])
        series = project_recoveries(
            lease, MONTHS, [project(item)], rentable_area=100_000,
            analysis_begin=BEGIN, inflation=three_pct, context=context,
        )
        assert series.iloc[0] == pytest.approx(5_000)          # floored
        assert series.iloc[12] == pytest.approx(5_000 * 1.03)  # inflated floor

    def test_yearly_growth_cap(self):
        """The YoY cap limits each calendar year to the prior capped year
        × (1 + cap%) [AE p. 412]."""
        structure = structure_of(RecoveryPool(
            expenses=["CAM"], caps_floors={"yearly_cap_pct": 5.0},
        ))
        series = run(structure, [self.rising_cam()])
        year1 = series.iloc[:12].sum()
        year2 = series.iloc[12:24].sum()
        assert year1 == pytest.approx(120_000)
        assert year2 == pytest.approx(120_000 * 1.05)  # raw 132,000 capped

    def test_cumulative_growth_cap(self):
        """The cumulative cap compounds from the first year [AE p. 412]."""
        structure = structure_of(RecoveryPool(
            expenses=["CAM"], caps_floors={"cumulative_cap_pct": 4.0},
        ))
        series = run(structure, [self.rising_cam()])
        year3 = series.iloc[24:36].sum()
        assert year3 == pytest.approx(120_000 * 1.04**2)


class TestPoolBaseYearAndFixed:
    def rising_cam(self):
        return project(expense("CAM", 120_000,
                               inflation=[YearRate(year=1, rate=10.0)]))

    def test_pool_base_year_defaults_to_analysis_year_one(self):
        structure = structure_of(RecoveryPool(expenses=["CAM"],
                                              method="base_year"))
        series = run(structure, [self.rising_cam()])
        assert series.iloc[:12].abs().sum() == 0.0
        assert series.iloc[12] == pytest.approx(1_000)  # 11,000 − 10,000

    def test_base_year_spec_gross_up(self):
        """BaseYearSpec.gross_up_pct grosses the frozen base-year value
        (spec §3.14; formula [AE p. 407]): a fully variable pool at 80%
        occupancy grossed to 95% freezes a higher stop."""
        item = expense("CAM", 120_000, pct_fixed=0.0,
                       inflation=[YearRate(year=1, rate=10.0)])
        plain = structure_of(RecoveryPool(expenses=["CAM"],
                                          method="base_year"))
        grossed = structure_of(RecoveryPool(
            expenses=["CAM"], method="base_year",
            base_year={"gross_up_pct": 95.0},
        ))
        pair = [project(item, occupancy=0.8)]
        plain_series = run(plain, pair, occupancy=0.8)
        grossed_series = run(grossed, pair, occupancy=0.8)
        # year-2 pool 8,800/mo: plain stop 8,000/mo → 800; grossed stop
        # 9,500/mo (10,000 × 0.95) → floored at 0
        assert plain_series.iloc[12] == pytest.approx(800)
        assert grossed_series.iloc[12] == 0.0

    def test_fiscal_base_year_deferred(self):
        structure = structure_of(RecoveryPool(
            expenses=["CAM"], method="base_year",
            base_year={"year": 2026, "fiscal": True},
        ))
        with pytest.raises(NotImplementedError, match="fiscal"):
            run(structure, [self.rising_cam()])

    def test_pool_fixed_amount_with_index(self):
        structure = structure_of(RecoveryPool(
            expenses=["CAM"], method="fixed", fixed_amount=24_000,
            fixed_inflation=[YearRate(year=1, rate=3.0)],
        ))
        series = run(structure, [project(expense("CAM", 120_000))])
        assert series.iloc[0] == pytest.approx(2_000)
        assert series.iloc[12] == pytest.approx(2_060)


class TestSystemBaseYearGrossUpUnlocked:
    def test_grossed_frozen_base_year(self):
        """The system assignment's base_year_gross_up_pct (deferred in
        session 1) now computes: only the frozen base-year value grosses;
        the monthly pool stays ungrossed (system structures are never
        grossed up [AE p. 406])."""
        item = expense("CAM", 120_000, pct_fixed=0.0,
                       inflation=[YearRate(year=1, rate=10.0)])
        lease = make_lease(recoveries=RecoveryAssignment(
            method=RecoverySystemMethod.base_year,
            base_year_gross_up_pct=95.0,
        ))
        context = make_context(structure_of(RecoveryPool(expenses=["CAM"])),
                               occupancy=0.8)
        series = project_recoveries(
            lease, MONTHS, [project(item, occupancy=0.8)],
            rentable_area=100_000, analysis_begin=BEGIN, inflation=FLAT,
            context=context,
        )
        # stop 9,500/mo vs year-2 pool 8,800/mo → still under the stop
        assert series.iloc[12] == 0.0


class TestAbateRecoveriesEndToEnd:
    """Free-rent abatement of recoveries (deferred since Phase 1): the
    profile's elements govern [AE p. 254]."""

    def model(self, abate: bool):
        lease = Lease(
            tenant_name="T", area=100_000, lease_type="industrial",
            start_date=BEGIN, term_months=60,
            base_rent=MoneyRate(amount=12.0,
                                unit=MoneyUnit.dollars_per_area_per_year),
            free_rent=FreeRent(months=2.0, profile="Deal"),
            upon_expiration="vacate",
        )
        return PropertyModel(
            property=PropertyInfo(name="FR", property_type="industrial",
                                  analysis_begin=BEGIN, analysis_term_years=2),
            area_measures=AreaMeasures(
                property_size=100_000,
                rentable_area_mode=RentableAreaMode.fixed,
                rentable_area_fixed=100_000,
            ),
            inflation=FLAT,
            free_rent_profiles=[FreeRentProfile(
                name="Deal", abate_base_rent=True, abate_recoveries=abate,
            )],
            expenses=[ExpenseItem(name="CAM", amount=120_000,
                                  unit=ExpenseUnit.dollars_per_year)],
            rent_roll=[lease],
        )

    def test_profile_abates_recoveries(self):
        frame = run_property(self.model(abate=True)).ledger.frame
        assert frame.iloc[0]["Expense Recovery Revenue"] == pytest.approx(0.0)
        assert frame.iloc[2]["Expense Recovery Revenue"] == pytest.approx(10_000)

    def test_default_keeps_recoveries(self):
        """Recoveries abate at 0% by default [AE p. 254]."""
        frame = run_property(self.model(abate=False)).ledger.frame
        assert frame.iloc[0]["Expense Recovery Revenue"] == pytest.approx(10_000)


class TestRecoveryAuditReport:
    """Spec §7 report 18: per tenant per pool, reconciling exactly to the
    ledger (the Gate 2 requirement; BUILD_SCHEDULE Week 5)."""

    def rich_model(self):
        anchor = Lease(
            tenant_name="Anchor", area=60_000, lease_type="industrial",
            start_date=BEGIN, term_months=60,
            base_rent=MoneyRate(amount=12.0,
                                unit=MoneyUnit.dollars_per_area_per_year),
            recoveries=RecoveryAssignment(method=RecoverySystemMethod.net),
            upon_expiration="vacate",
        )
        inline = Lease(
            tenant_name="Inline", area=40_000, lease_type="industrial",
            start_date=BEGIN, term_months=60,
            base_rent=MoneyRate(amount=15.0,
                                unit=MoneyUnit.dollars_per_area_per_year),
            recoveries=RecoveryAssignment(
                method=RecoverySystemMethod.structure, structure_ref="CAM+Tax",
            ),
            upon_expiration="vacate",
        )
        structure = RecoveryStructure(name="CAM+Tax", pools=[
            RecoveryPool(expenses=["Ops"], gross_up_pct=95.0,
                         admin_fee_pct=5.0),
            RecoveryPool(expenses=["Real Estate Taxes"], method="stop",
                         base_amount_per_area=1.00),
        ])
        return PropertyModel(
            property=PropertyInfo(name="Audit", property_type="industrial",
                                  analysis_begin=BEGIN, analysis_term_years=2),
            area_measures=AreaMeasures(
                property_size=100_000,
                rentable_area_mode=RentableAreaMode.fixed,
                rentable_area_fixed=100_000,
            ),
            inflation=FLAT,
            recovery_structures=[structure],
            expense_groups=[ExpenseGroup(name="Ops",
                                         members=["CAM", "Utilities"])],
            expenses=[
                ExpenseItem(name="CAM", amount=120_000,
                            unit=ExpenseUnit.dollars_per_year,
                            pct_fixed=50.0),
                ExpenseItem(name="Utilities", amount=60_000,
                            unit=ExpenseUnit.dollars_per_year),
                ExpenseItem(name="Real Estate Taxes", amount=180_000,
                            unit=ExpenseUnit.dollars_per_year),
                ExpenseItem(name="Management Fee", amount=3.0,
                            unit=ExpenseUnit.pct_of_egr),
            ],
            rent_roll=[anchor, inline],
        )

    def test_report_reconciles_exactly_to_the_ledger(self):
        from engine.reports import reconcile_to_ledger, recovery_audit

        result = run_property(self.rich_model())
        report = recovery_audit(result)
        assert not report.empty
        assert set(report["pool"]) == {"system: net", "pool 1 (net)",
                                       "pool 2 (stop)"}
        difference = reconcile_to_ledger(report, result)
        assert difference.abs().max() == pytest.approx(0.0, abs=1e-9)

    def test_fee_converges_with_structures_active(self):
        """The fixed point stays a contraction with structures + gross-up
        active (recoveries.py docstring bound): fee = 3% of final EGR."""
        result = run_property(self.rich_model())
        month = result.ledger.frame.iloc[0]
        assert -month["Management Fee"] == pytest.approx(
            0.03 * month["Effective Gross Revenue"]
        )
