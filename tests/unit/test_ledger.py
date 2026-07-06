"""Unit tests for engine/calc/ledger.py (Phase 1, Step 4 item 4).

The Cash Flow report pages define the rollups this module implements
(Iron Rule 3 cites): Scheduled Base Rent = "the potential rent minus
vacancy and free rent" and EGR = PGR minus vacancy and credit loss
[AE p. 538]; NOI = EGR minus operating expenses and CFBDS = NOI minus
leasing and capital costs [AE p. 539]. Occupancy % = occupied / rentable
area (spec §3.2 [AE pp. 188-196]). Aggregation views and the §9.3
pre-valuation invariants (monthly sums = annual, occupied ≤ rentable) are
asserted here on a Clorox-shaped miniature property.
"""
import datetime as dt

import pandas as pd
import pytest

from engine.calc.expenses import project_expense
from engine.calc.ledger import (
    ABSORPTION_TURNOVER_VACANCY,
    BASE_RENTAL_REVENUE,
    CFBDS,
    EGR,
    EXPENSE_RECOVERY_REVENUE,
    FREE_RENT,
    NOI,
    SCHEDULED_BASE_RENTAL_REVENUE,
    TOTAL_CAPITAL_COSTS,
    TOTAL_OPERATING_EXPENSES,
    TOTAL_PGR,
    assemble_ledger,
    assert_invariants,
    occupancy_series,
    occupied_area_series,
    rentable_area_series,
    to_annual,
    to_fiscal_annual,
    to_quarterly,
)
from engine.calc.leases import project_contract_rent
from engine.calc.recoveries import project_recoveries
from engine.calc.timeline import build_month_index
from engine.models import (
    AreaMeasures,
    AreaScheduleEntry,
    ExpenseCategory,
    ExpenseItem,
    ExpenseUnit,
    FreeRent,
    Inflation,
    Lease,
    MoneyRate,
    MoneyUnit,
    RentableAreaMode,
    YearRate,
)

BEGIN = dt.date(2026, 6, 1)  # Clorox-shaped mid-year start
MONTHS = build_month_index(BEGIN, 2)
FLAT = Inflation(general_rate=[YearRate(year=1, rate=0.0)])


def make_lease(area=100_000, start=BEGIN, term_months=60, rent_psf=12.0,
               **kwargs):
    return Lease(
        tenant_name="Tenant", area=area, lease_type="industrial",
        start_date=start, term_months=term_months,
        base_rent=MoneyRate(amount=rent_psf,
                            unit=MoneyUnit.dollars_per_area_per_year),
        **kwargs,
    )


def expense(name, amount, unit=ExpenseUnit.dollars_per_year, **kwargs):
    return ExpenseItem(name=name, amount=amount, unit=unit, **kwargs)


def build_ledger(lease=None, expense_items=None):
    """Assemble a one-tenant, net-recovery miniature (the golden #1 shape)."""
    lease = lease or make_lease()
    items = expense_items if expense_items is not None else [
        expense("CAM", 60_000),
        expense("Taxes", 120_000),
        expense("Reserves", 12_000, category=ExpenseCategory.capital),
    ]
    projected = [(i, project_expense(i, MONTHS, BEGIN, FLAT, area=lease.area))
                 for i in items]
    rents = project_contract_rent(lease, MONTHS, BEGIN, FLAT)
    recovery = project_recoveries(lease, MONTHS, projected,
                                  rentable_area=lease.area)
    return assemble_ledger(
        MONTHS, lease_rents=[rents], recoveries=[recovery],
        expenses=projected,
    )


class TestAreaSeries:
    """Occupied/rentable/occupancy series (spec §3.2 [AE pp. 188-196])."""

    def test_occupied_area_tracks_lease_terms(self):
        a = make_lease(area=60_000, start=dt.date(2026, 6, 1), term_months=12)
        b = make_lease(area=40_000, start=dt.date(2027, 1, 1), term_months=24)
        occupied = occupied_area_series([a, b], MONTHS)
        assert occupied[pd.Period("2026-06", freq="M")] == 60_000
        assert occupied[pd.Period("2027-01", freq="M")] == 100_000
        assert occupied[pd.Period("2027-06", freq="M")] == 40_000  # a expired

    def test_rentable_modes(self):
        leases = [make_lease(area=60_000), make_lease(area=40_000)]
        derived = AreaMeasures(property_size=120_000)
        fixed = AreaMeasures(property_size=120_000,
                             rentable_area_mode=RentableAreaMode.fixed,
                             rentable_area_fixed=110_000)
        schedule = AreaMeasures(
            property_size=120_000,
            rentable_area_mode=RentableAreaMode.schedule,
            rentable_area_schedule=[
                AreaScheduleEntry(date=dt.date(2027, 1, 1), area=130_000),
            ],
        )
        assert rentable_area_series(derived, leases, MONTHS).iloc[0] == 100_000
        assert rentable_area_series(fixed, leases, MONTHS).iloc[0] == 110_000
        stepped = rentable_area_series(schedule, leases, MONTHS)
        assert stepped[pd.Period("2026-06", freq="M")] == 130_000  # first entry
        assert stepped[pd.Period("2027-06", freq="M")] == 130_000

    def test_occupancy_pct(self):
        """Occupancy % = occupied area / rentable area per month (spec §3.2)."""
        lease = make_lease(area=75_000)
        occupied = occupied_area_series([lease], MONTHS)
        rentable = pd.Series(100_000.0, index=MONTHS)
        assert occupancy_series(occupied, rentable).iloc[0] == pytest.approx(0.75)


class TestRollups:
    """Cash Flow report subtotal definitions [AE pp. 538-539]."""

    def test_scheduled_base_is_potential_minus_vacancy_and_free(self):
        """"Scheduled Base Rent ... is the potential rent minus vacancy and
        free rent" [AE p. 538] — Free Rent and A&T Vacancy are components of
        the Scheduled Base subtotal (DEVIATIONS.md §5)."""
        lease = make_lease(free_rent=FreeRent(months=2))
        ledger = build_ledger(lease=lease).frame
        month1 = ledger.iloc[0]
        assert month1[BASE_RENTAL_REVENUE] == pytest.approx(100_000)
        assert month1[FREE_RENT] == pytest.approx(-100_000)
        assert month1[SCHEDULED_BASE_RENTAL_REVENUE] == pytest.approx(0.0)
        month3 = ledger.iloc[2]
        assert month3[SCHEDULED_BASE_RENTAL_REVENUE] == pytest.approx(100_000)

    def test_total_pgr_and_egr(self):
        """PGR totals all revenue; EGR = PGR minus vacancy and credit loss
        [AE p. 538] (both zero in Phase 1, so EGR = PGR)."""
        frame = build_ledger().frame
        month1 = frame.iloc[0]
        pool = (60_000 + 120_000) / 12  # operating only; reserves are capital
        assert month1[EXPENSE_RECOVERY_REVENUE] == pytest.approx(pool)
        assert month1[TOTAL_PGR] == pytest.approx(100_000 + pool)
        assert month1[EGR] == pytest.approx(month1[TOTAL_PGR])

    def test_noi_is_egr_minus_operating_expenses(self):
        """"Net operating income is the effective gross revenue minus the
        operating expenses" [AE p. 539]; expense lines post negative under
        their own names (spec §2.3 report signs)."""
        frame = build_ledger().frame
        month1 = frame.iloc[0]
        assert month1["CAM"] == pytest.approx(-5_000)
        assert month1["Taxes"] == pytest.approx(-10_000)
        assert month1[TOTAL_OPERATING_EXPENSES] == pytest.approx(-15_000)
        assert month1[NOI] == pytest.approx(month1[EGR] - 15_000)

    def test_cfbds_subtracts_leasing_and_capital(self):
        """"Cash flow before debt service is calculated by subtracting the
        total leasing and operating costs from the net operating income"
        [AE p. 539]: capital reserves sit below NOI."""
        frame = build_ledger().frame
        month1 = frame.iloc[0]
        assert month1["Reserves"] == pytest.approx(-1_000)
        assert month1[TOTAL_CAPITAL_COSTS] == pytest.approx(-1_000)
        assert month1[CFBDS] == pytest.approx(month1[NOI] - 1_000)

    def test_negative_capital_expense_posts_as_credit(self):
        """A negative capital ExpenseItem (the Clorox Amortized CAM Revenue
        shape, DEVIATIONS.md §3) posts as a positive capital-section line."""
        items = [expense("CAM", 60_000),
                 expense("Amortized CAM Revenue", -1_200,
                         unit=ExpenseUnit.dollars_per_month,
                         category=ExpenseCategory.capital)]
        frame = build_ledger(expense_items=items).frame
        assert frame.iloc[0]["Amortized CAM Revenue"] == pytest.approx(1_200)
        assert frame.iloc[0][TOTAL_CAPITAL_COSTS] == pytest.approx(1_200)

    def test_line_order_matches_cash_flow_report(self):
        """Line order follows the ARGUS Cash Flow report [AE p. 538] so
        exports diff cleanly (spec §2.3): revenue block, operating detail,
        NOI, capital block, CFBDS."""
        columns = list(build_ledger().frame.columns)
        expected_order = [
            BASE_RENTAL_REVENUE, ABSORPTION_TURNOVER_VACANCY, FREE_RENT,
            SCHEDULED_BASE_RENTAL_REVENUE, EXPENSE_RECOVERY_REVENUE,
            TOTAL_PGR, EGR, "CAM", "Taxes", TOTAL_OPERATING_EXPENSES,
            NOI, "Reserves", TOTAL_CAPITAL_COSTS, CFBDS,
        ]
        positions = [columns.index(name) for name in expected_order]
        assert positions == sorted(positions)

    def test_expense_account_override_accumulates(self):
        """Two items sharing an ``account`` sum into one ledger line
        (spec §2.3: groups supported)."""
        items = [expense("Gas", 6_000, account="Utilities"),
                 expense("Electric", 18_000, account="Utilities")]
        frame = build_ledger(expense_items=items).frame
        assert frame.iloc[0]["Utilities"] == pytest.approx(-2_000)


class TestAggregations:
    """Annual/quarterly/fiscal views are aggregations of the monthly ledger,
    never separately computed (spec §2.3); sums must reconcile (spec §9.3)."""

    def test_annual_and_quarterly_sum_monthly(self):
        frame = build_ledger().frame
        annual = to_annual(frame, BEGIN)
        quarterly = to_quarterly(frame)
        for view in (annual, quarterly):
            for account in frame.columns:
                assert view[account].sum() == pytest.approx(frame[account].sum())
        assert annual.loc[1, BASE_RENTAL_REVENUE] == pytest.approx(1_200_000)

    def test_fiscal_years_label_ending_calendar_year(self):
        """With a May fiscal year end and a June analysis start (the Clorox
        phasing), the first 12 months land in the fiscal year labeled by the
        calendar year it ends in — FY2027 (spec §3.1)."""
        frame = build_ledger().frame
        fiscal = to_fiscal_annual(frame, fiscal_year_end_month=5)
        assert list(fiscal.index) == [2027, 2028, 2029]
        assert fiscal.loc[2027, BASE_RENTAL_REVENUE] == pytest.approx(1_200_000)
        assert fiscal.loc[2028, BASE_RENTAL_REVENUE] == pytest.approx(1_200_000)


class TestInvariants:
    """§9.3 pre-valuation invariants: rollup identities, occupied ≤ rentable,
    sum(monthly) = annual for every account and aggregation."""

    def test_pass_on_consistent_ledger(self):
        lease = make_lease(free_rent=FreeRent(months=2))
        ledger = build_ledger(lease=lease)
        occupied = occupied_area_series([lease], MONTHS)
        rentable = pd.Series(float(lease.area), index=MONTHS)
        assert_invariants(ledger, analysis_begin=BEGIN,
                          fiscal_year_end_month=5,
                          occupied_area=occupied, rentable_area=rentable)

    def test_broken_rollup_raises(self):
        ledger = build_ledger()
        ledger.frame.iloc[0, ledger.frame.columns.get_loc(NOI)] += 1.0
        with pytest.raises(ValueError, match="Net Operating Income"):
            assert_invariants(ledger, analysis_begin=BEGIN)

    def test_occupied_exceeding_rentable_raises(self):
        ledger = build_ledger()
        occupied = pd.Series(120_000.0, index=MONTHS)
        rentable = pd.Series(100_000.0, index=MONTHS)
        with pytest.raises(ValueError, match="occupied"):
            assert_invariants(ledger, analysis_begin=BEGIN,
                              occupied_area=occupied, rentable_area=rentable)

    def test_mixed_category_account_rejected(self):
        items = [expense("Shared", 12_000),
                 expense("Shared 2", 12_000, account="Shared",
                         category=ExpenseCategory.capital)]
        with pytest.raises(ValueError, match="more than one category"):
            build_ledger(expense_items=items)
