"""Unit tests for the Lease Audit report (Phase 2, Step 6;
engine/reports/lease_audit.py).

Cites per Iron Rule 3: the report is the Cash Flow's tenant-level
drill-down — "clicking on Potential Base Rent leads to the Lease Audit
report, where you can examine potential rent on a tenant by tenant
basis" [AE p. 535] — and its columns follow the rental-revenue section
definitions [AE p. 538]: Scheduled Base Rent = potential rent minus
vacancy and free rent; CPI posts separately; recoveries join as other
tenant revenue. Reconciliation to the ledger must be exact (Gate 2)."""
import datetime as dt

import pandas as pd
import pytest

from engine.calc.run import run_property
from engine.reports import lease_audit, reconcile_lease_audit
from engine.models import (
    AbsorptionSpec,
    AreaMeasures,
    ExpenseItem,
    ExpenseUnit,
    Inflation,
    Lease,
    MarketLeasingProfile,
    MoneyRate,
    MoneyUnit,
    PctOfNew,
    PropertyInfo,
    PropertyModel,
    RentableAreaMode,
    TimingBasis,
    UponExpiration,
    YearRate,
)

BEGIN = dt.date(2026, 1, 1)
PSF_YR = MoneyUnit.dollars_per_area_per_year


@pytest.fixture(scope="module")
def result():
    """Multi-tenant property exercising every phase the report labels:
    a long-term anchor (contract), a roller with downtime and rollover
    free rent (downtime + speculative), and an absorption space
    (vacant-at-market, then speculative lease-up)."""
    profile = MarketLeasingProfile(
        name="Market", term_months=24, renewal_probability=50.0,
        months_vacant=4.0,  # downtime = 2 months on rollover
        market_base_rent_new=MoneyRate(amount=12.0, unit=PSF_YR),
        market_base_rent_renew=PctOfNew(pct_of_new=100.0),
        free_rent_months_new=2.0, free_rent_months_renew=0.0,
        upon_expiration=UponExpiration.market, term_growth=False,
    )
    anchor = Lease(
        tenant_name="Anchor", area=200_000, lease_type="industrial",
        start_date=BEGIN, term_months=120,
        base_rent=MoneyRate(amount=10.0, unit=PSF_YR),
        upon_expiration=UponExpiration.vacate,
    )
    roller = Lease(
        tenant_name="Roller", area=100_000, lease_type="industrial",
        start_date=BEGIN, term_months=12,  # expires 2026-12
        base_rent=MoneyRate(amount=12.0, unit=PSF_YR),
        market_leasing_profile="Market",
        upon_expiration=UponExpiration.market,
    )
    absorption = AbsorptionSpec(
        name="Vacant Bay", total_area=50_000, number_of_leases=2,
        start_date=dt.date(2026, 4, 1), interval_months=3,
        lease_type="industrial", market_leasing_profile="Market",
    )
    model = PropertyModel(
        property=PropertyInfo(name="LA", property_type="industrial",
                              analysis_begin=BEGIN, analysis_term_years=3),
        area_measures=AreaMeasures(
            property_size=350_000,
            rentable_area_mode=RentableAreaMode.fixed,
            rentable_area_fixed=350_000,
        ),
        inflation=Inflation(general_rate=[YearRate(year=1, rate=0.0)],
                            timing_basis=TimingBasis.analysis_year),
        market_leasing_profiles=[profile],
        expenses=[ExpenseItem(name="CAM", amount=420_000,
                              unit=ExpenseUnit.dollars_per_year)],
        rent_roll=[anchor, roller],
        absorption=[absorption],
    )
    return run_property(model)


@pytest.fixture(scope="module")
def report(result):
    return lease_audit(result)


class TestReconciliation:
    """The report must reconcile exactly to the ledger's revenue lines
    (Gate 2; same standard as the Recovery Audit)."""

    def test_every_line_reconciles_exactly(self, report, result):
        differences = reconcile_lease_audit(report, result)
        assert differences.abs().to_numpy().max() == pytest.approx(0.0,
                                                                   abs=1e-9)

    def test_row_identity_scheduled_and_total(self, report):
        """Per row: Scheduled = base + A&T + free ("the potential rent
        minus vacancy and free rent" [AE p. 538]); total tenant revenue
        adds CPI and recoveries."""
        scheduled = (report["base_rent"] + report["absorption_vacancy"]
                     + report["free_rent"])
        assert (report["scheduled"] - scheduled).abs().max() < 1e-9
        total = report["scheduled"] + report["cpi"] + report["recoveries"]
        assert (report["total_tenant_revenue"] - total).abs().max() < 1e-9


class TestPhaseLabels:
    """Phase labels from the resolved chains (contract / downtime /
    speculative / vacant [AE pp. 535, 538])."""

    def row(self, report, tenant, month):
        period = pd.Period(month, freq="M")
        match = report[(report["tenant"] == tenant)
                       & (report["month"] == period)]
        assert len(match) == 1, f"expected one row for {tenant} {month}"
        return match.iloc[0]

    def test_contract_months(self, report):
        row = self.row(report, "Anchor", "2026-06")
        assert row["phase"] == "contract"
        assert row["base_rent"] == pytest.approx(10.0 * 200_000 / 12)

    def test_downtime_months_net_to_zero_scheduled(self, report):
        """Roller expires 2026-12; downtime 2027-01/02 posts market rent
        to base and its negative to A&T — Scheduled nets to zero
        [AE p. 538; spec §4.2]."""
        row = self.row(report, "Roller", "2027-01")
        assert row["phase"] == "downtime"
        assert row["base_rent"] == pytest.approx(100_000)
        assert row["absorption_vacancy"] == pytest.approx(-100_000)
        assert row["scheduled"] == pytest.approx(0.0)
        assert row["recoveries"] == 0.0  # vacant space recovers nothing

    def test_speculative_months_with_rollover_free_rent(self, report):
        """The speculative segment starts 2027-03 with one weighted free
        month (0.5 × 2 new); month one is half-abated... (weighted free =
        1.0 month → month one fully abated)."""
        row = self.row(report, "Roller", "2027-03")
        assert row["phase"] == "speculative"
        assert row["base_rent"] == pytest.approx(100_000)
        assert row["free_rent"] == pytest.approx(-100_000)  # 1.0 weighted month
        assert row["scheduled"] == pytest.approx(0.0)

    def test_pre_absorption_vacant_at_market(self, report):
        """A not-yet-absorbed space is 'vacant' but still carries its
        market value in base rent with the offsetting A&T [AE p. 538]."""
        row = self.row(report, "Vacant Bay 2 of 2", "2026-03")
        assert row["phase"] == "vacant"
        assert row["base_rent"] == pytest.approx(12.0 * 25_000 / 12)
        assert row["absorption_vacancy"] == pytest.approx(-25_000)
        assert row["scheduled"] == pytest.approx(0.0)

    def test_absorbed_space_becomes_speculative(self, report):
        row = self.row(report, "Vacant Bay 1 of 2", "2026-08")
        assert row["phase"] == "speculative"
        # past its 2 new-tenant free months (Apr-May): full rent
        assert row["scheduled"] == pytest.approx(25_000)
        assert row["recoveries"] > 0.0


class TestShape:
    def test_columns_and_no_dead_rows(self, report):
        assert list(report.columns) == [
            "tenant", "month", "phase", "base_rent", "absorption_vacancy",
            "free_rent", "scheduled", "cpi", "percentage_rent", "misc",
            "recoveries", "total_tenant_revenue",
        ]
        # zero-activity months are omitted; every kept row has something
        activity = report[["base_rent", "absorption_vacancy", "free_rent",
                           "cpi", "recoveries"]].abs().sum(axis=1)
        assert (activity > 0).all()
        assert set(report["tenant"]) == {
            "Anchor", "Roller", "Vacant Bay 1 of 2", "Vacant Bay 2 of 2",
        }
