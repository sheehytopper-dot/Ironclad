"""Unit tests for engine/calc/percentage_rent.py (Phase 2 Step 8).

Iron Rule 3: the manual has no standalone numeric overage walkthrough, so
these tests pin its definitional statements — % rent due = (sales volume
− breakpoint) × sales % [AE p. 590], natural breakpoint = (base rent +
step rent + CPI) / overage % [AE pp. 250-251, 377, 590], zero breakpoint
= percentage of total sales [AE pp. 251, 377], fixed breakpoints on the
annual amount entered [AE pp. 250, 377], layers 1-6 [AE p. 250] — plus
the one worked number the manual does print, the % of Sales calculation
200,000 × 8% = 16,000 [AE p. 392].

STANDING GAP (CLAUDE.md): percentage rent is **externally unvalidated
pending golden #3** — these are manual-definition tests only; no
published Argus cash flow yet confirms the module end-to-end.
"""
import datetime as dt

import pandas as pd
import pytest

from engine.calc.leases import resolve_lease_chain
from engine.calc.percentage_rent import (
    annual_percentage_rent,
    project_segment_percentage_rent,
    sales_volume_series,
)
from engine.calc.run import run_property
from engine.calc.timeline import build_month_index
from engine.models import (
    AreaMeasures,
    BreakpointLayer,
    GeneralVacancy,
    Inflation,
    Lease,
    MoneyRate,
    MoneyUnit,
    PercentRentBreakpoint,
    PercentRentSpec,
    PropertyInfo,
    PropertyModel,
    RentableAreaMode,
    SalesVolume,
    SalesVolumeUnit,
    TimingBasis,
    VacancyMethod,
    YearRate,
)

BEGIN = dt.date(2026, 1, 1)
MONTHS = build_month_index(BEGIN, 2)  # through 2027-12
FLAT = Inflation(general_rate=[YearRate(year=1, rate=0.0)],
                 timing_basis=TimingBasis.analysis_year)
PSF_YR = MoneyUnit.dollars_per_area_per_year


def make_spec(breakpoint=PercentRentBreakpoint.natural, layers=None,
              sales=25_000_000.0, unit=SalesVolumeUnit.dollars_per_year,
              growth=None):
    return PercentRentSpec(
        sales_volume=SalesVolume(amount=sales, unit=unit, growth=growth),
        breakpoint=breakpoint,
        breakpoint_layers=layers or [BreakpointLayer(pct=6.0)],
    )


class TestAnnualFormula:
    """% rent due = Σ per layer max(0, sales − breakpoint) × pct
    [AE p. 590; spec §3.13]."""

    def test_zero_breakpoint_is_percent_of_total_sales(self):
        """Zero breakpoint: "percentage rent is calculated based on total
        sales volume" [AE pp. 251, 377]; the manual's % of Sales number:
        200,000 × 8% = 16,000 [AE p. 392]."""
        spec = make_spec(PercentRentBreakpoint.zero,
                         [BreakpointLayer(pct=8.0)])
        assert annual_percentage_rent(spec, 200_000.0, 0.0) == (
            pytest.approx(16_000.0)
        )

    def test_natural_breakpoint_is_rent_over_pct(self):
        """Natural breakpoint = base rent / overage percentage [AE p. 590]:
        annual rent 1,200,000 at 6% → break 20M; sales 40M pay
        (40M − 20M) × 6% = 1.2M."""
        spec = make_spec(PercentRentBreakpoint.natural,
                         [BreakpointLayer(pct=6.0)])
        assert annual_percentage_rent(spec, 40_000_000.0, 1_200_000.0) == (
            pytest.approx(1_200_000.0)
        )

    def test_no_percentage_rent_below_the_breakpoint(self):
        """"Calculates only after natural breakpoint is reached"
        [AE p. 250] — sales below the break owe nothing, never negative."""
        spec = make_spec(PercentRentBreakpoint.natural,
                         [BreakpointLayer(pct=6.0)])
        assert annual_percentage_rent(spec, 15_000_000.0, 1_200_000.0) == 0.0

    def test_fixed_amount_breakpoint(self):
        """Annual $: "calculated based on sales volume that exceeds the
        annual amount entered" [AE pp. 250, 377]."""
        spec = make_spec(
            PercentRentBreakpoint.fixed_amount,
            [BreakpointLayer(breakpoint_amount=1_000_000.0, pct=5.0)],
        )
        assert annual_percentage_rent(spec, 1_200_000.0, 0.0) == (
            pytest.approx(10_000.0)
        )
        assert annual_percentage_rent(spec, 900_000.0, 0.0) == 0.0

    def test_tiered_layers_sum(self):
        """Layer 1 - Layer 6 tiered overage [AE p. 250; spec §3.13]: each
        layer prices its own excess and the layers add."""
        spec = make_spec(
            PercentRentBreakpoint.fixed_amount,
            [BreakpointLayer(breakpoint_amount=1_000_000.0, pct=5.0),
             BreakpointLayer(breakpoint_amount=2_000_000.0, pct=3.0)],
        )
        # sales 3M: (3M − 1M) × 5% + (3M − 2M) × 3% = 100,000 + 30,000
        assert annual_percentage_rent(spec, 3_000_000.0, 0.0) == (
            pytest.approx(130_000.0)
        )

    def test_natural_layers_each_use_their_own_pct(self):
        """Natural breakpoint is per layer — rent / that layer's pct
        [AE p. 590 "base rent divided by the overage percentage"]."""
        spec = make_spec(
            PercentRentBreakpoint.natural,
            [BreakpointLayer(pct=6.0), BreakpointLayer(pct=4.0)],
        )
        # rent 1.2M: breaks 20M and 30M; sales 32M →
        # (32M − 20M) × 6% + (32M − 30M) × 4% = 720,000 + 80,000
        assert annual_percentage_rent(spec, 32_000_000.0, 1_200_000.0) == (
            pytest.approx(800_000.0)
        )


class TestSalesVolume:
    """Sales volume units and growth [AE pp. 249-250; spec §3.13]."""

    def test_amount_per_area_times_tenant_area(self):
        """$/SF sales × tenant area [AE pp. 249-250]: 400 × 100,000 SF."""
        spec = make_spec(sales=400.0,
                         unit=SalesVolumeUnit.dollars_per_area_per_year)
        series = sales_volume_series(spec, 100_000.0, MONTHS, BEGIN, FLAT)
        assert float(series.iloc[0]) == pytest.approx(40_000_000.0)

    def test_growth_on_explicit_schedule(self):
        """Sales grow on their own index (spec §3.3/§3.13): 3% schedule →
        year 1 flat, year 2 × 1.03."""
        spec = make_spec(sales=1_000_000.0,
                         growth=[YearRate(year=1, rate=3.0)])
        series = sales_volume_series(spec, 0.0, MONTHS, BEGIN, FLAT)
        assert float(series[pd.Period("2026-06", freq="M")]) == (
            pytest.approx(1_000_000.0)
        )
        assert float(series[pd.Period("2027-06", freq="M")]) == (
            pytest.approx(1_030_000.0)
        )


class TestSegmentProjection:
    """Monthly posting over occupied months (spec §2.3; DEVIATIONS.md §11)."""

    def make_segment(self, spec):
        lease = Lease(
            tenant_name="Shop", area=100_000, lease_type="retail",
            start_date=BEGIN, term_months=24,
            base_rent=MoneyRate(amount=12.0, unit=PSF_YR),
            percentage_rent=spec, upon_expiration="vacate",
        )
        return resolve_lease_chain(lease, MONTHS, BEGIN, FLAT, {})[0]

    def test_monthly_is_annual_over_twelve(self):
        """Each month posts 1/12 of the annualized formula — the straight
        monthly accrual convention (spec §3.14 v1 policy; DEVIATIONS.md
        §11). Rent 100,000/mo → break 20M; sales 40M → 1.2M / 12."""
        segment = self.make_segment(make_spec(sales=40_000_000.0))
        base = pd.Series(100_000.0, index=MONTHS)
        series = project_segment_percentage_rent(
            segment, MONTHS, base_rent=base, cpi_adjustment=None,
            analysis_begin=BEGIN, inflation=FLAT,
        )
        assert float(series.iloc[0]) == pytest.approx(100_000.0)
        assert float(series.sum()) == pytest.approx(2_400_000.0)

    def test_step_rent_raises_the_natural_breakpoint(self):
        """Natural = base + STEP rent [AE pp. 250-251, 377]: when the base
        series steps from 100,000 to 150,000/mo, the break moves 20M → 30M
        and the overage on 40M sales drops from 1.2M to 600,000/yr."""
        segment = self.make_segment(make_spec(sales=40_000_000.0))
        base = pd.Series(100_000.0, index=MONTHS)
        base[pd.Period("2027-01", freq="M"):] = 150_000.0
        series = project_segment_percentage_rent(
            segment, MONTHS, base_rent=base, cpi_adjustment=None,
            analysis_begin=BEGIN, inflation=FLAT,
        )
        assert float(series[pd.Period("2026-06", freq="M")]) == (
            pytest.approx(100_000.0)
        )
        assert float(series[pd.Period("2027-06", freq="M")]) == (
            pytest.approx(50_000.0)
        )

    def test_cpi_joins_the_natural_breakpoint(self):
        """Natural = base + step + CPI [AE pp. 250-251, 377]: 2,500/mo of
        CPI adjustment annualizes to 30,000, lifting the break from 20M to
        20.5M — overage on 40M sales drops by 30,000/yr."""
        segment = self.make_segment(make_spec(sales=40_000_000.0))
        base = pd.Series(100_000.0, index=MONTHS)
        cpi = pd.Series(2_500.0, index=MONTHS)
        series = project_segment_percentage_rent(
            segment, MONTHS, base_rent=base, cpi_adjustment=cpi,
            analysis_begin=BEGIN, inflation=FLAT,
        )
        # rent 1,230,000/yr → break 20.5M; (40M − 20.5M) × 6% / 12
        assert float(series.iloc[0]) == pytest.approx(97_500.0)

    def test_nothing_outside_the_segment_or_without_a_spec(self):
        """Occupied months only (DEVIATIONS.md §11); a lease without a
        spec posts nothing."""
        segment = self.make_segment(make_spec(sales=40_000_000.0))
        segment.end = pd.Period("2026-12", freq="M")
        base = pd.Series(100_000.0, index=MONTHS)
        series = project_segment_percentage_rent(
            segment, MONTHS, base_rent=base, cpi_adjustment=None,
            analysis_begin=BEGIN, inflation=FLAT,
        )
        assert float(series[pd.Period("2027-06", freq="M")]) == 0.0
        no_spec = self.make_segment(None)
        assert float(project_segment_percentage_rent(
            no_spec, MONTHS, base_rent=base, cpi_adjustment=None,
            analysis_begin=BEGIN, inflation=FLAT,
        ).abs().sum()) == 0.0


class TestRunIntegration:
    """Percentage Rent through run_property: the ledger line, PGR/EGR,
    vacancy bases, and the Lease Audit reconciliation."""

    def make_model(self, **overrides):
        fields = dict(
            property=PropertyInfo(
                name="Retail", property_type="retail",
                analysis_begin=BEGIN, analysis_term_years=2,
            ),
            area_measures=AreaMeasures(
                property_size=100_000,
                rentable_area_mode=RentableAreaMode.fixed,
                rentable_area_fixed=100_000,
            ),
            inflation=FLAT,
            expenses=[],
            rent_roll=[Lease(
                tenant_name="Shop", area=100_000, lease_type="retail",
                start_date=BEGIN, term_months=60,
                base_rent=MoneyRate(amount=12.0, unit=PSF_YR),
                percentage_rent=make_spec(
                    sales=400.0,
                    unit=SalesVolumeUnit.dollars_per_area_per_year,
                ),
                upon_expiration="vacate",
            )],
        )
        fields.update(overrides)
        return PropertyModel(**fields)

    def test_posts_to_the_percentage_rent_line_and_pgr(self):
        """Rent 1.2M/yr at 6% → break 20M; sales 40M → 100,000/mo on the
        Percentage Rent line, inside Total PGR and EGR (spec §2.3)."""
        frame = run_property(self.make_model()).ledger.frame
        month = frame.iloc[0]
        assert month["Percentage Rent"] == pytest.approx(100_000.0)
        assert month["Total Potential Gross Revenue"] == (
            pytest.approx(200_000.0)
        )
        assert month["Effective Gross Revenue"] == pytest.approx(200_000.0)

    def test_percentage_rent_joins_the_vacancy_base(self):
        """General vacancy on % of PGR sees percentage rent in its base
        (spec §3.4 [AE pp. 224-225]): 5% × (100,000 + 100,000)."""
        model = self.make_model(general_vacancy=GeneralVacancy(
            method=VacancyMethod.percent_of_pgr,
            rate=[YearRate(year=1, rate=5.0)],
        ))
        month = run_property(model).ledger.frame.iloc[0]
        assert month["General Vacancy"] == pytest.approx(-10_000.0)
        assert month["Effective Gross Revenue"] == pytest.approx(190_000.0)

    def test_lease_audit_carries_and_reconciles_percentage_rent(self):
        """The Lease Audit's percentage_rent column reconciles exactly to
        the ledger line (Gate 2 discipline; spec §7 report 16)."""
        from engine.reports.lease_audit import lease_audit, reconcile_to_ledger

        result = run_property(self.make_model())
        report = lease_audit(result)
        assert report["percentage_rent"].iloc[0] == pytest.approx(100_000.0)
        row = report.iloc[0]
        assert row["total_tenant_revenue"] == pytest.approx(
            row["scheduled"] + row["cpi"] + row["percentage_rent"]
            + row["recoveries"]
        )
        differences = reconcile_to_ledger(report, result)
        assert float(differences.abs().max().max()) < 1e-9
