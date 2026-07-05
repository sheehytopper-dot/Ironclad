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

    def test_phase2_methods_raise(self):
        """Stops, base years, fixed amounts, and user structures are Phase 2;
        asking for them must fail loudly, not silently post zero."""
        lease = make_lease(area=540_000, method=RecoverySystemMethod.base_stop,
                           stop_amount_per_area=2.50)
        expenses = [project(expense("CAM", 120_000))]
        with pytest.raises(NotImplementedError, match="base_stop"):
            project_recoveries(lease, MONTHS, expenses, rentable_area=540_000)
