"""Unit tests for engine/calc/recoveries.py (Phase 1, Step 4 item 3).

The manual's recovery pages give normative definitions rather than numeric
worked examples: the net method [AE p. 405], the no-recovery method
[AE p. 406], no gross-up for system structures [AE p. 406], gross-up as a
user-structure, variable-portion-only feature [AE p. 407]. Each test cites
the statement it reproduces (Iron Rule 3); the Clorox-shape test mirrors
golden #1's single-tenant net pool including the %-of-EGR management fee.
"""
import datetime as dt

import pandas as pd
import pytest

from engine.calc.expenses import project_expense
from engine.calc.recoveries import (
    net_recoveries,
    project_recoveries,
    recoverable_pool,
)
from engine.calc.timeline import build_month_index
from engine.models import (
    ExpenseCategory,
    ExpenseItem,
    ExpenseUnit,
    Inflation,
    Lease,
    MoneyRate,
    MoneyUnit,
    RecoveryAssignment,
    RecoverySystemMethod,
    YearRate,
)

BEGIN = dt.date(2026, 1, 1)
MONTHS = build_month_index(BEGIN, 3)
FLAT = Inflation(general_rate=[YearRate(year=1, rate=0.0)])


def make_lease(area, method=RecoverySystemMethod.net, start=BEGIN,
               term_months=60, **recovery_kwargs):
    return Lease(
        tenant_name="Tenant", area=area, lease_type="industrial",
        start_date=start, term_months=term_months,
        base_rent=MoneyRate(amount=10.0, unit=MoneyUnit.dollars_per_area_per_year),
        recoveries=RecoveryAssignment(method=method, **recovery_kwargs),
    )


def project(item, **kwargs):
    return item, project_expense(item, MONTHS, BEGIN, FLAT, **kwargs)


def expense(name, amount, unit=ExpenseUnit.dollars_per_year, **kwargs):
    return ExpenseItem(name=name, amount=amount, unit=unit, **kwargs)


class TestNetMethod:
    """Net: "All recoverable expenses are paid by the tenant based on their
    proportionate share of the building area" [AE p. 405]."""

    def test_pro_rata_share_of_pool(self):
        """A tenant with 25% of the rentable area recovers 25% of the pool
        [AE p. 405]."""
        lease = make_lease(area=135_000)
        expenses = [project(expense("CAM", 120_000))]
        series = project_recoveries(lease, MONTHS, expenses, rentable_area=540_000)
        assert series.iloc[0] == pytest.approx(10_000 * 0.25)
        assert series.iloc[:12].sum() == pytest.approx(120_000 * 0.25)

    def test_clorox_shape_single_tenant_full_share(self):
        """Golden #1 shape: one tenant leasing 100% of rentable area recovers
        the entire recoverable pool — operating expenses at 100% share,
        management fee included, capital reserves excluded [AE p. 405;
        spec §3.11 defaults]. The management fee enters at the caller's
        fixed-point series (a stub here); resolving the %-of-EGR circularity
        is run.py's job (spec §4.1 step 9), not this module's."""
        area = 540_000
        lease = make_lease(area=area)
        mgmt_fee = expense("Management Fee", 3.0, ExpenseUnit.pct_of_egr)
        egr_stub = pd.Series(300_000.0, index=MONTHS)
        expenses = [
            project(expense("Common Area Maintenance", 327_480.49)),
            project(expense("Utilities", 0.10,
                            ExpenseUnit.dollars_per_area_per_year), area=area),
            project(mgmt_fee, reference=egr_stub),
            project(expense("Insurance", 71_761.98)),
            project(expense("Real Estate Taxes", 744_905.91)),
            project(expense("Capital Reserves", 0.10,
                            ExpenseUnit.dollars_per_area_per_year,
                            category=ExpenseCategory.capital), area=area),
        ]
        series = project_recoveries(lease, MONTHS, expenses, rentable_area=area)
        operating = 327_480.49 + 0.10 * area + 71_761.98 + 744_905.91
        fee = 300_000 * 0.03
        assert series.iloc[0] == pytest.approx(operating / 12 + fee)
        assert series.iloc[:12].sum() == pytest.approx(operating + 12 * fee)

    def test_zero_outside_lease_term(self):
        """Recoveries post only during the contract term (spec §4.1 step 6):
        nothing before the start month or after the end month."""
        lease = make_lease(area=540_000, start=dt.date(2026, 7, 1), term_months=12)
        expenses = [project(expense("CAM", 120_000))]
        series = project_recoveries(lease, MONTHS, expenses, rentable_area=540_000)
        assert series[pd.Period("2026-06", freq="M")] == 0.0
        assert series[pd.Period("2026-07", freq="M")] == pytest.approx(10_000)
        assert series[pd.Period("2027-06", freq="M")] == pytest.approx(10_000)
        assert series[pd.Period("2027-07", freq="M")] == 0.0

    def test_no_gross_up_for_system_net(self):
        """"Expenses recovered using system recovery structures will not be
        grossed up" [AE p. 406] (gross-up is a user-structure feature acting
        only on variable portions [AE p. 407]): a fully variable expense at
        50% occupancy is recovered at its actual occupancy-scaled amount,
        never inflated back toward full occupancy."""
        lease = make_lease(area=270_000)
        variable = expense("Utilities", 120_000, pct_fixed=0.0)
        expenses = [project(variable, occupancy=0.5)]
        series = project_recoveries(lease, MONTHS, expenses, rentable_area=540_000)
        assert series.iloc[0] == pytest.approx(10_000 * 0.5 * 0.5)


class TestRecoverablePool:
    """Pool membership follows ExpenseItem.is_recoverable (spec §3.11):
    operating default in; capital/non-operating default out; the explicit
    flag overrides either way."""

    def test_category_defaults_and_explicit_flags(self):
        expenses = [
            project(expense("CAM", 12_000)),                       # in (default)
            project(expense("Owner Legal", 12_000,
                            category=ExpenseCategory.non_operating)),  # out
            project(expense("Reserves", 12_000,
                            category=ExpenseCategory.capital)),        # out
            project(expense("Non-Recov Op", 12_000, recoverable=False)),  # out
            project(expense("Recov Capital", 12_000,
                            category=ExpenseCategory.capital,
                            recoverable=True)),                        # in
        ]
        pool = recoverable_pool(expenses, MONTHS)
        assert pool.iloc[0] == pytest.approx(2_000)  # 1,000 + 1,000

    def test_net_recoveries_uses_supplied_pool(self):
        """net_recoveries is pure share × pool [AE p. 405]."""
        lease = make_lease(area=100_000)
        pool = pd.Series(50_000.0, index=MONTHS)
        series = net_recoveries(lease, MONTHS, pool, rentable_area=400_000)
        assert series.iloc[0] == pytest.approx(12_500)


class TestDispatch:
    """Phase 1 method dispatch (spec §10, Iron Rule 2)."""

    def test_method_none_posts_nothing(self):
        """"None: No recoveries will be calculated for the tenant"
        [AE p. 406]."""
        lease = make_lease(area=540_000, method=RecoverySystemMethod.none)
        expenses = [project(expense("CAM", 120_000))]
        series = project_recoveries(lease, MONTHS, expenses, rentable_area=540_000)
        assert series.sum() == 0.0

    def test_user_structures_still_raise(self):
        """User recovery structures are Step 5 session 2; asking for them
        must fail loudly, not silently post zero."""
        lease = make_lease(area=540_000, method=RecoverySystemMethod.structure,
                           structure_ref="Custom CAM")
        expenses = [project(expense("CAM", 120_000))]
        with pytest.raises(NotImplementedError, match="structure"):
            project_recoveries(lease, MONTHS, expenses, rentable_area=540_000)


class TestBaseStop:
    """base_stop: a building $/SF stop — the tenant reimburses its share
    of recoverable expenses over the building stop amount [AE p. 409]."""

    def test_clorox_shaped_hand_case(self):
        """Hand-computable Clorox shape: pool $1,198,148.38/yr flat, stop
        $2.00/SF on 540,000 SF (building stop $90,000/mo), 100% share:
        recovery = 99,845.70 − 90,000 = 9,845.70/mo [AE p. 409]."""
        lease = make_lease(area=540_000,
                           method=RecoverySystemMethod.base_stop,
                           stop_amount_per_area=2.00)
        expenses = [project(expense("Operating", 1_198_148.38))]
        series = project_recoveries(lease, MONTHS, expenses,
                                    rentable_area=540_000)
        assert series.iloc[0] == pytest.approx(1_198_148.38 / 12 - 90_000)

    def test_pro_rata_share_of_the_excess(self):
        """The excess over the building stop is shared pro-rata
        [AE p. 409]: a 25% tenant recovers 25% of (pool − stop)."""
        lease = make_lease(area=135_000,
                           method=RecoverySystemMethod.base_stop,
                           stop_amount_per_area=1.00)
        expenses = [project(expense("CAM", 900_000))]
        series = project_recoveries(lease, MONTHS, expenses,
                                    rentable_area=540_000)
        # pool 75,000/mo − stop 45,000/mo = 30,000 × 25%
        assert series.iloc[0] == pytest.approx(7_500)

    def test_floors_at_zero_never_pays_the_stop(self):
        """A pool below the stop recovers nothing — the tenant never pays
        the landlord's stop (spec §3.14 floor)."""
        lease = make_lease(area=540_000,
                           method=RecoverySystemMethod.base_stop,
                           stop_amount_per_area=5.00)
        expenses = [project(expense("CAM", 120_000))]
        series = project_recoveries(lease, MONTHS, expenses,
                                    rentable_area=540_000)
        assert (series == 0.0).all()


class TestBaseYear:
    """base_year / base_year_plus_1: the stop is the actual recoverable
    expenses of the base year, frozen [AE pp. 405-406, 408-409]."""

    def rising_pool(self):
        """1,200,000/yr inflating 10% each analysis year."""
        item = expense("Operating", 1_200_000,
                       inflation=[YearRate(year=1, rate=10.0)])
        return [project(item)]

    def test_first_lease_year_stop_frozen(self):
        """A lease starting at analysis begin freezes year-1 expenses as
        its stop: year 1 recovers nothing; year 2 recovers the increase
        [AE p. 408 "pro-rata share of any increases over the amount of
        reimbursable expenses in the first year of the lease"]."""
        lease = make_lease(area=540_000,
                           method=RecoverySystemMethod.base_year)
        series = project_recoveries(lease, MONTHS, self.rising_pool(),
                                    rentable_area=540_000,
                                    analysis_begin=BEGIN)
        assert series.iloc[:12].abs().sum() == 0.0        # base year
        assert series.iloc[12] == pytest.approx(10_000)   # 110k − 100k
        assert series.iloc[24] == pytest.approx(21_000)   # 121k − 100k

    def test_pre_analysis_start_uses_analysis_year_one(self):
        """"Tenants with leases that begin before the analysis start will
        pay their pro-rata share of any increases over the amount of
        reimbursable expenses in the first year of the analysis"
        [AE p. 408]."""
        lease = make_lease(area=540_000, start=dt.date(2020, 3, 1),
                           term_months=120,
                           method=RecoverySystemMethod.base_year)
        series = project_recoveries(lease, MONTHS, self.rising_pool(),
                                    rentable_area=540_000,
                                    analysis_begin=BEGIN)
        assert series.iloc[:12].abs().sum() == 0.0
        assert series.iloc[12] == pytest.approx(10_000)

    def test_base_year_plus_one_shifts_the_window(self):
        """Base Year Stop +1: the stop is the recoverable expenses of the
        year following the lease-begin year [AE pp. 406, 409] — so
        recoveries begin in year 3."""
        lease = make_lease(area=540_000,
                           method=RecoverySystemMethod.base_year_plus_1)
        series = project_recoveries(lease, MONTHS, self.rising_pool(),
                                    rentable_area=540_000,
                                    analysis_begin=BEGIN)
        assert series.iloc[:24].abs().sum() == 0.0        # years 1-2
        assert series.iloc[24] == pytest.approx(11_000)   # 121k − 110k

    def test_explicit_base_year(self):
        """An explicit calendar base_year overrides the lease-start rule
        (spec §3.14 assignment)."""
        lease = make_lease(area=540_000,
                           method=RecoverySystemMethod.base_year,
                           base_year=2027)
        series = project_recoveries(lease, MONTHS, self.rising_pool(),
                                    rentable_area=540_000,
                                    analysis_begin=BEGIN)
        # stop = 2027 expenses (year 2: 110k/mo): year-1 pool is below it
        assert series.iloc[:24].abs().sum() == 0.0
        assert series.iloc[24] == pytest.approx(11_000)

    def test_base_year_gross_up_deferred_loudly(self):
        """Gross-up is a user-structure feature — "expenses recovered
        using system recovery structures will not be grossed up"
        [AE p. 406]; the assignment's gross-up field defers to Step 5
        session 2."""
        lease = make_lease(area=540_000,
                           method=RecoverySystemMethod.base_year,
                           base_year_gross_up_pct=95.0)
        with pytest.raises(NotImplementedError, match="gross-up"):
            project_recoveries(lease, MONTHS, self.rising_pool(),
                               rentable_area=540_000, analysis_begin=BEGIN)


class TestFixedMethod:
    """fixed: a tenant amount, not a building amount [AE p. 409]."""

    def test_fixed_amount_posts_regardless_of_pool(self):
        lease = make_lease(area=540_000, method=RecoverySystemMethod.fixed,
                           fixed_amount=24_000)
        series = project_recoveries(lease, MONTHS, [], rentable_area=540_000)
        assert series.iloc[0] == pytest.approx(2_000)
        assert series.iloc[30] == pytest.approx(2_000)

    def test_fixed_amount_per_area_is_tenant_area(self):
        """$/SF fixed recoveries apply to the tenant's area, "not a
        building amount/area" [AE p. 409]."""
        lease = make_lease(area=30_000, method=RecoverySystemMethod.fixed,
                           fixed_amount_per_area=0.50)
        series = project_recoveries(lease, MONTHS, [], rentable_area=540_000)
        assert series.iloc[0] == pytest.approx(0.50 * 30_000 / 12)

    def test_flat_unless_inflation_opted_in(self):
        """The fixed amount is flat by default; fixed_inflation opts into
        an explicit schedule (spec §3.14 "inflatable")."""
        flat = make_lease(area=100_000, method=RecoverySystemMethod.fixed,
                          fixed_amount=12_000)
        inflated = make_lease(area=100_000,
                              method=RecoverySystemMethod.fixed,
                              fixed_amount=12_000,
                              fixed_inflation=[YearRate(year=1, rate=3.0)])
        flat_series = project_recoveries(flat, MONTHS, [],
                                         rentable_area=100_000)
        infl_series = project_recoveries(inflated, MONTHS, [],
                                         rentable_area=100_000,
                                         analysis_begin=BEGIN)
        assert flat_series.iloc[12] == pytest.approx(1_000)
        assert infl_series.iloc[12] == pytest.approx(1_030)


class TestStopsInsideTheFixedPoint:
    """Stops make recoveries piecewise-linear in the fee; the %-of-EGR
    loop must still converge (recoveries.py docstring bound: contraction
    factor ≤ 2 × share × pct)."""

    def test_base_stop_with_recoverable_fee_converges(self):
        """Hand-computable: SB 100,000/mo, CAM 10,000/mo, stop 5,000/mo
        building, 100% share, 5% recoverable fee. rec = pool − 5,000 =
        5,000 + fee; EGR = 105,000 + fee; fee = 5% × EGR → fee =
        5,250/0.95 = 5,526.32; fee = 5% of final EGR exactly."""
        from engine.calc.run import run_property
        from engine.models import (
            AreaMeasures,
            PropertyInfo,
            PropertyModel,
            RentableAreaMode,
        )

        lease = Lease(
            tenant_name="Tenant", area=100_000, lease_type="industrial",
            start_date=BEGIN, term_months=60,
            base_rent=MoneyRate(amount=12.0,
                                unit=MoneyUnit.dollars_per_area_per_year),
            recoveries=RecoveryAssignment(
                method=RecoverySystemMethod.base_stop,
                stop_amount_per_area=0.60,
            ),
            upon_expiration="vacate",
        )
        model = PropertyModel(
            property=PropertyInfo(name="Stop", property_type="industrial",
                                  analysis_begin=BEGIN,
                                  analysis_term_years=2),
            area_measures=AreaMeasures(
                property_size=100_000,
                rentable_area_mode=RentableAreaMode.fixed,
                rentable_area_fixed=100_000,
            ),
            inflation=FLAT,
            expenses=[
                ExpenseItem(name="CAM", amount=120_000,
                            unit=ExpenseUnit.dollars_per_year),
                ExpenseItem(name="Management Fee", amount=5.0,
                            unit=ExpenseUnit.pct_of_egr),
            ],
            rent_roll=[lease],
        )
        month = run_property(model).ledger.frame.iloc[0]
        expected_fee = 5_250 / 0.95
        assert month["Management Fee"] == pytest.approx(-expected_fee)
        assert -month["Management Fee"] == pytest.approx(
            0.05 * month["Effective Gross Revenue"]
        )
        assert month["Expense Recovery Revenue"] == pytest.approx(
            5_000 + expected_fee
        )
