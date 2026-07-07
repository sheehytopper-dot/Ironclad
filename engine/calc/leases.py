"""Lease-domain calculations: contract-term rent (Phase 1; spec §4.1
step 4) and lease chain resolution into segments (Phase 2; spec §4.1
pass 3, §4.2).

Base rent calculation examples are normative [AE pp. 391-394]; free rent
profiles [AE pp. 253-254]; CPI increases [AE pp. 255-257]; market leasing
profiles and rollover blending [AE pp. 233-252]. Projection of speculative
segments into the ledger is Phase 2 Step 2 (NEXT_STEPS_TO_GATE2.md); this
module resolves the chains and their blended economics.

Conventions (spec §2.3): every output is a monthly pandas Series indexed by
the canonical Period[M] timeline, zero outside the lease term and analysis
window. Base rent + fixed/percent steps post to Base Rental Revenue; CPI
adjustments post separately (CPI & Other Adjustment Revenue); free rent
posts as negative amounts (Free Rent).

Free rent abates base rent and fixed steps at 100% and CPI at 0% — the
manual's element defaults [AE p. 254]. (The §3.8 schema cannot express
partial percentages per element; see DEVIATIONS.md.)

Out of scope here, with no §3 schema inputs: rent-review ratchets, %-of-sales
reviews, and average-prior-rent reviews [AE pp. 392-393] — v1 does not model
them (spec §3.12).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Mapping, Optional

import pandas as pd

from engine.calc.inflation import index_schedule, inflation_factors, rate_for_year
from engine.calc.timeline import snap_to_month_start
from engine.models import (
    CPIMethod,
    FreeRentProfile,
    FreeRentTiming,
    Inflation,
    IntelligentRenewalRule,
    LCSpec,
    Lease,
    MarketLeasingProfile,
    MoneyRate,
    MoneyUnit,
    PctOfNew,
    PercentRentSpec,
    RecoveryAssignment,
    RentStep,
    TimingBasis,
    UponExpiration,
)


def monthly_base_rent(rate: MoneyRate, area: float,
                      market_rent_annual: Optional[float] = None) -> float:
    """Convert a base-rent ``MoneyRate`` to dollars per month.

    Unit conversions per the normative calculation examples [AE p. 391]:
    $/SF/yr × area / 12; $/SF/mo × area; $/yr / 12; $/mo as entered;
    % of market × (annual market rent) / 12.
    """
    u = rate.unit
    if u == MoneyUnit.dollars_per_area_per_year:
        return rate.amount * area / 12.0
    if u == MoneyUnit.dollars_per_area_per_month:
        return rate.amount * area
    if u == MoneyUnit.dollars_per_year:
        return rate.amount / 12.0
    if u == MoneyUnit.dollars_per_month:
        return rate.amount
    if u == MoneyUnit.pct_of_market:
        if market_rent_annual is None:
            raise ValueError(
                "pct_of_market base rent requires market_rent_annual "
                "(the space's market rent in $/year)"
            )
        return market_rent_annual * rate.amount / 100.0 / 12.0
    raise ValueError(f"{u.value!r} is not a base rent unit")


def lease_term_periods(lease: Lease) -> tuple[pd.Period, pd.Period]:
    """First and last occupied month of the contract term. All timing snaps
    to months (spec §3.1): the start month is the month containing
    ``start_date``; the end month is the month containing ``end_date`` (or
    start + term_months − 1)."""
    start = pd.Period(snap_to_month_start(lease.start_date), freq="M")
    if lease.end_date is not None:
        end = pd.Period(snap_to_month_start(lease.end_date), freq="M")
    else:
        end = start + lease.term_months - 1
    return start, end


def _step_period(step: RentStep, lease_start: pd.Period) -> pd.Period:
    if step.date is not None:
        return pd.Period(snap_to_month_start(step.date), freq="M")
    return lease_start + step.month_offset


def rent_level(lease: Lease, period: pd.Period,
               market_rent_annual: Optional[float] = None) -> float:
    """Monthly base rent (including fixed and percent steps) in force during
    ``period``.

    Amount steps re-base the rent per their own unit [rent review examples,
    AE p. 392]; percent steps compound multiplicatively on the prior rent
    [% of market with step amounts, AE p. 391: 100,000 ×1.05 → 105,000,
    ×1.05 → 110,250].
    """
    start, _ = lease_term_periods(lease)
    level = monthly_base_rent(lease.base_rent, lease.area, market_rent_annual)
    for step in sorted(lease.rent_steps, key=lambda s: _step_period(s, start)):
        if _step_period(step, start) > period:
            break
        if step.amount is not None:
            level = monthly_base_rent(
                MoneyRate(amount=step.amount, unit=step.unit),
                lease.area, market_rent_annual,
            )
        else:
            level *= 1.0 + step.pct_increase / 100.0
    return level


def contract_base_rent(lease: Lease, months: pd.PeriodIndex,
                       market_rent_annual: Optional[float] = None) -> pd.Series:
    """Monthly contract base rent (incl. steps) over the analysis timeline;
    zero outside the lease term [AE pp. 391-392]."""
    start, end = lease_term_periods(lease)
    series = pd.Series(0.0, index=months, name="base_rent")
    for period in months:
        if start <= period <= end:
            series[period] = rent_level(lease, period, market_rent_annual)
    return series


# --------------------------------------------------------------------- #
# CPI increases [AE pp. 255-257; indexed review example AE p. 392]       #
# --------------------------------------------------------------------- #

def _cpi_schedule(inflation: Inflation, index_ref: Optional[str]):
    """Resolve a CPI spec's index ref to an annual rate schedule; a CPI spec
    with no index uses the cpi rate (spec §3.3/§3.7)."""
    return index_schedule(inflation, index_ref, default="cpi")


def _schedule_year(period: pd.Period, analysis_begin: dt.date,
                   timing_basis: TimingBasis) -> int:
    """Which schedule year applies to an increase falling in ``period``:
    the calendar year under calendar basis, else the 1-based analysis year
    (clamped to 1 for events preceding the analysis window — CPI on an
    in-place lease accrues from lease start)."""
    if timing_basis == TimingBasis.calendar_year:
        return period.year
    offset = (period.year - analysis_begin.year) * 12 + (period.month - analysis_begin.month)
    return max(1, offset // 12 + 1)


def cpi_adjustments(lease: Lease, months: pd.PeriodIndex,
                    analysis_begin: dt.date, inflation: Inflation,
                    market_rent_annual: Optional[float] = None) -> pd.Series:
    """Monthly CPI adjustment series for a contract lease [AE pp. 255-257].

    At each increase event (first on the lease anniversary or after
    ``first_increase_month`` months, then every ``frequency_months``), the
    increase is (rent + prior CPI) × effective rate — the manual defines
    minimum/maximum increases "over the prior rent (rent + prior CPI)"
    [AE p. 257], and the indexed-review example compounds a lease year's rent
    by (1 + CPI) at the start of the new lease year [AE p. 392]. Method
    scaling: ``pct_of_cpi`` takes pct% of the calculated CPI ("if calculated
    CPI is $1,000 … 57% … $570" [AE p. 257]); ``cpi_plus_pct`` adds pct
    points; ``cap_pct``/``floor_pct`` clamp the effective rate (the
    ``min_max_banded`` method is full CPI with both bounds set).
    Adjustments post to CPI & Other Adjustment Revenue, never into base rent
    (spec §2.3).
    """
    series = pd.Series(0.0, index=months, name="cpi_adjustment")
    spec = lease.cpi
    if spec is None:
        return series
    rates = _cpi_schedule(inflation, spec.index)
    start, end = lease_term_periods(lease)

    first_offset = 12 if spec.first_increase_month == "anniversary" else int(spec.first_increase_month)
    events = []
    event = start + first_offset
    while event <= end:
        events.append(event)
        event += spec.frequency_months

    level = 0.0
    levels: list[tuple[pd.Period, float]] = []
    for event in events:
        rate = rate_for_year(rates, _schedule_year(event, analysis_begin, inflation.timing_basis))
        if spec.method == CPIMethod.pct_of_cpi:
            rate *= (spec.pct or 0.0) / 100.0
        elif spec.method == CPIMethod.cpi_plus_pct:
            rate += spec.pct or 0.0
        if spec.cap_pct is not None:
            rate = min(rate, spec.cap_pct)
        if spec.floor_pct is not None:
            rate = max(rate, spec.floor_pct)
        base = rent_level(lease, event, market_rent_annual) + level
        level += base * rate / 100.0
        levels.append((event, level))

    for period in months:
        if start <= period <= end:
            applicable = [lvl for ev, lvl in levels if ev <= period]
            if applicable:
                series[period] = applicable[-1]
    return series


# --------------------------------------------------------------------- #
# Free rent [AE pp. 253-254]                                             #
# --------------------------------------------------------------------- #

def contract_free_fraction(lease: Lease, months: pd.PeriodIndex) -> pd.Series:
    """Fraction (0..1) of each month's charges the contract lease's
    free-rent spec abates: ``front`` timing abates the first N lease
    months with a fractional final month; ``custom`` abates the listed
    1-based lease months in full (spec §3.12 [AE pp. 253-254]). Which
    charge types the fraction applies to is the profile's decision
    [AE p. 254]."""
    series = pd.Series(0.0, index=months, name="free_fraction")
    fr = lease.free_rent
    if fr is None:
        return series
    start, end = lease_term_periods(lease)
    custom = set(fr.custom_months or [])
    for period in months:
        if not start <= period <= end:
            continue
        lease_month = (period.year - start.year) * 12 + (period.month - start.month)
        if fr.timing == FreeRentTiming.front:
            series[period] = min(1.0, max(0.0, fr.months - lease_month))
        else:
            series[period] = 1.0 if (lease_month + 1) in custom else 0.0
    return series


def segment_free_fraction(segment: "LeaseSegment",
                          months: pd.PeriodIndex) -> pd.Series:
    """Fraction (0..1) abated per month by a speculative segment's
    weighted free rent: front-loaded from segment start with a fractional
    final month ("free rent is applied at the beginning of the lease"
    [AE p. 239]; §4.2 weighting)."""
    series = pd.Series(0.0, index=months, name="free_fraction")
    for period in months:
        if not segment.start <= period <= segment.end:
            continue
        month_index = (period.year - segment.start.year) * 12 + (
            period.month - segment.start.month
        )
        series[period] = min(1.0, max(0.0, segment.free_rent_months - month_index))
    return series


def free_rent(lease: Lease, months: pd.PeriodIndex,
              market_rent_annual: Optional[float] = None,
              profile: Optional[FreeRentProfile] = None) -> pd.Series:
    """Monthly free-rent abatement (negative) for a contract lease.

    Elements to include follow the manual's defaults [AE p. 254]: base rent
    and fixed steps abate at 100%, CPI at 0% — so the abated amount is the
    stepped base rent level, never the CPI adjustment (fractions per
    :func:`contract_free_fraction`).
    """
    series = pd.Series(0.0, index=months, name="free_rent")
    if lease.free_rent is None or (
        profile is not None and not profile.abate_base_rent
    ):
        return series
    fractions = contract_free_fraction(lease, months)
    for period in months:
        fraction = float(fractions[period])
        if fraction:
            series[period] = -fraction * rent_level(lease, period, market_rent_annual)
    return series


# --------------------------------------------------------------------- #
# Orchestration                                                          #
# --------------------------------------------------------------------- #

@dataclass
class LeaseRentCashflows:
    """Contract-term rent series for one lease (spec §2.3 accounts)."""

    base_rent: pd.Series       # Base Rental Revenue (incl. fixed/% steps)
    cpi_adjustment: pd.Series  # CPI & Other Adjustment Revenue
    free_rent: pd.Series       # Free Rent (negative)


def project_contract_rent(lease: Lease, months: pd.PeriodIndex,
                          analysis_begin: dt.date,
                          inflation: Optional[Inflation] = None,
                          market_rent_annual: Optional[float] = None,
                          free_rent_profile: Optional[FreeRentProfile] = None,
                          ) -> LeaseRentCashflows:
    """Project one lease's contract-term rent onto the monthly timeline
    (spec §4.1 step 4, contract portion)."""
    if lease.cpi is not None and inflation is None:
        raise ValueError("lease has a CPI spec; inflation assumptions are required")
    base = contract_base_rent(lease, months, market_rent_annual)
    cpi = (
        cpi_adjustments(lease, months, analysis_begin, inflation, market_rent_annual)
        if lease.cpi is not None
        else pd.Series(0.0, index=months, name="cpi_adjustment")
    )
    free = free_rent(lease, months, market_rent_annual, free_rent_profile)
    return LeaseRentCashflows(base_rent=base, cpi_adjustment=cpi, free_rent=free)


# --------------------------------------------------------------------- #
# Lease chain resolution (spec §4.1 pass 3; §4.2) [AE pp. 233-252]       #
# --------------------------------------------------------------------- #

@dataclass
class LeaseSegment:
    """One resolved occupancy segment of a lease chain (spec §4.1 pass 3).

    The contract segment carries no economics of its own — its rent, steps,
    CPI, and free rent live on the ``Lease`` and project via
    ``project_contract_rent``. Speculative segments carry the §4.2 blended
    economics: ``initial_rent_monthly`` is the weighted market rent in
    dollars per month as of ``start``; ``rent_increases`` are the MLP's
    steps offset from segment start; ``free_rent_months`` / ``ti`` /
    ``lc_pct`` / ``lc_rate`` are probability-weighted (costs are recorded
    here and posted in Phase 3). ``downtime_months`` is the weighted vacant
    period immediately preceding ``start`` — Step 2 posts it as Absorption
    & Turnover Vacancy and reduces occupied area by ``(1 − renewal_weight)
    × area`` (spec §4.2).
    """

    lease: Lease
    profile: Optional[MarketLeasingProfile]  # None on the contract segment
    start: pd.Period
    end: pd.Period                           # inclusive
    speculative: bool
    renewal_weight: float                    # p used in blending (1.0 if n/a)
    downtime_months: int
    initial_rent_monthly: Optional[float]    # None on the contract segment
    rent_increases: list[RentStep] = field(default_factory=list)
    free_rent_months: float = 0.0
    free_rent_profile: Optional[str] = None
    recoveries: RecoveryAssignment = field(default_factory=RecoveryAssignment)
    percentage_rent: Optional[PercentRentSpec] = None  # lease's (contract) / MLP's (spec) [AE p. 376]
    ti: Optional[MoneyRate] = None           # weighted [AE p. 245; §4.2]
    lc_pct: Optional[float] = None           # weighted % of rent [AE pp. 246-248]
    lc_rate: Optional[MoneyRate] = None      # weighted $/SF or $ amount

    @property
    def area(self) -> float:
        return self.lease.area

    @property
    def downtime_start(self) -> Optional[pd.Period]:
        """First vacant month preceding this segment (None if no downtime)."""
        if self.downtime_months == 0:
            return None
        return self.start - self.downtime_months


def segment_rent_level(segment: LeaseSegment, period: pd.Period,
                       market_rent_annual: Optional[float] = None) -> float:
    """Monthly base rent (incl. steps) in force during ``period`` for a
    segment. Contract segments delegate to :func:`rent_level`; speculative
    segments apply the MLP's ``rent_increases`` to the blended initial rent
    (amount steps re-base per their unit, % steps compound — same semantics
    as contract steps [AE pp. 237, 391-392])."""
    if not segment.speculative:
        return rent_level(segment.lease, period, market_rent_annual)
    level = float(segment.initial_rent_monthly)
    for step in sorted(segment.rent_increases,
                       key=lambda s: _step_period(s, segment.start)):
        if _step_period(step, segment.start) > period:
            break
        if step.amount is not None:
            level = monthly_base_rent(
                MoneyRate(amount=step.amount, unit=step.unit), segment.area
            )
        else:
            level *= 1.0 + step.pct_increase / 100.0
    return level


def _market_factor(inflation: Inflation, period: pd.Period,
                   analysis_begin: dt.date) -> float:
    """Market-rent inflation factor as of ``period`` (MLP ``term_growth``:
    "This entry inflates with market inflation" [AE p. 235])."""
    rates = index_schedule(inflation, None, default="market_rent")
    begin = pd.Period(snap_to_month_start(analysis_begin), freq="M")
    idx = pd.period_range(begin, max(period, begin), freq="M")
    series = inflation_factors(rates, idx, analysis_begin,
                               inflation.inflation_month, inflation.timing_basis)
    return float(series.iloc[-1])


def _market_monthly(rate: MoneyRate, area: float, factor: float,
                    prior_rent: Optional[float], where: str) -> float:
    """A market base rent in dollars per month: unit conversion per the
    normative examples [AE p. 391], inflated by ``factor`` — except
    ``pct_of_last_rent``, which is a percent of the expiring rent and does
    not inflate (spec §3.6 "% of last rent")."""
    if rate.unit == MoneyUnit.pct_of_last_rent:
        if prior_rent is None:
            raise ValueError(f"{where}: pct_of_last_rent needs a prior rent")
        return prior_rent * rate.amount / 100.0
    if rate.unit in (MoneyUnit.pct_of_market, MoneyUnit.dollars_per_area,
                     MoneyUnit.dollars):
        raise ValueError(
            f"{where}: unit '{rate.unit.value}' is not a market base rent "
            "unit (the manual's Rental Value machinery is not modeled — "
            "spec §3.6 narrows market rents to $/SF/yr, $/SF/mo, $/yr, "
            "$/mo, and % of last rent)"
        )
    return monthly_base_rent(rate, area) * factor


def _blend_money(new: Optional[MoneyRate], renew: Optional[MoneyRate],
                 p: float, where: str) -> Optional[MoneyRate]:
    """Probability-weighted MoneyRate: p × renew + (1−p) × new, missing
    side = 0 in the other's unit (§4.2; TI example [AE p. 245])."""
    if new is None and renew is None:
        return None
    if new is not None and renew is not None and new.unit != renew.unit:
        raise ValueError(f"{where}: new/renew units differ; cannot blend")
    unit = (new or renew).unit
    amount = (p * (renew.amount if renew is not None else 0.0)
              + (1.0 - p) * (new.amount if new is not None else 0.0))
    return MoneyRate(amount=amount, unit=unit)


def _blend_lc(new: Optional[LCSpec], renew: Optional[LCSpec], p: float,
              where: str) -> tuple[Optional[float], Optional[MoneyRate]]:
    """Weighted leasing commission (§4.2) [AE pp. 246-248]: both sides %
    → weighted percent; both sides rate → weighted MoneyRate; missing side
    = 0. Category refs and mixed forms defer to Phase 3 posting."""
    if new is None and renew is None:
        return None, None
    for side in (new, renew):
        if side is not None and side.category_ref is not None:
            raise NotImplementedError(
                f"{where}: LC categories blend at posting time (Phase 3)"
            )
    pcts = [s.pct for s in (new, renew) if s is not None and s.pct is not None]
    rates = [s for s in (new, renew) if s is not None and s.rate is not None]
    if pcts and rates:
        raise ValueError(f"{where}: cannot blend a % LC with a $ LC")
    if pcts:
        pct = (p * (renew.pct if renew is not None and renew.pct is not None else 0.0)
               + (1.0 - p) * (new.pct if new is not None and new.pct is not None else 0.0))
        return pct, None
    return None, _blend_money(
        new.rate if new is not None else None,
        renew.rate if renew is not None else None, p, where,
    )


def _contract_prior_rent(lease: Lease, period: pd.Period,
                         months: pd.PeriodIndex, analysis_begin: dt.date,
                         inflation: Optional[Inflation],
                         market_rent_annual: Optional[float]) -> float:
    """The contract's "standard rent" in force at expiration — base rent +
    fixed steps + CPI [AE p. 236 Prior Rent] — used for pct_of_last_rent
    market rents and Intelligent Renewals comparisons."""
    prior = rent_level(lease, period, market_rent_annual)
    if lease.cpi is not None and inflation is not None:
        cpi = cpi_adjustments(lease, months, analysis_begin, inflation,
                              market_rent_annual)
        if period in cpi.index:
            prior += float(cpi[period])
    return prior


def resolve_lease_chain(lease: Lease, months: pd.PeriodIndex,
                        analysis_begin: dt.date,
                        inflation: Optional[Inflation],
                        profiles: Mapping[str, MarketLeasingProfile],
                        market_rent_annual: Optional[float] = None,
                        ) -> list[LeaseSegment]:
    """Resolve one rent roll lease into its full segment chain through the
    end of the timeline (spec §4.1 pass 3): the contract term, then
    speculative segments per its MLP, chaining per each profile's
    ``upon_expiration`` [AE pp. 233-252].

    §4.2 blending per rollover with renewal probability p: downtime =
    (1−p) × months_vacant rounded to whole months; blended rent =
    p × renewal-side + (1−p) × new, where the new/renew market rents
    inflate on the market index to segment start when ``term_growth``
    [AE p. 235] and the renewal side follows the profile's
    ``intelligent_renewals`` rule (market / prior / lesser_of / greater_of
    [AE pp. 235-236]). ``renew`` expirations are a 100%-probability
    renewal (no downtime, renewal terms); ``vacate`` and ``reabsorb`` end
    the chain (reabsorbed space returns via the absorption engine,
    Phase 2 Step 3). Speculative segments carry no CPI — DEVIATIONS.md §7.
    """
    start, end = lease_term_periods(lease)
    contract = LeaseSegment(
        lease=lease, profile=None, start=start, end=end, speculative=False,
        renewal_weight=1.0, downtime_months=0, initial_rent_monthly=None,
        rent_increases=list(lease.rent_steps),
        free_rent_months=(lease.free_rent.months if lease.free_rent else 0.0),
        free_rent_profile=(lease.free_rent.profile if lease.free_rent else None),
        recoveries=lease.recoveries,
        percentage_rent=lease.percentage_rent,
        ti=(lease.leasing_costs.ti if lease.leasing_costs else None),
    )
    if lease.leasing_costs is not None and lease.leasing_costs.lc is not None:
        contract.lc_pct, contract.lc_rate = _blend_lc(
            lease.leasing_costs.lc, lease.leasing_costs.lc, 1.0,
            f"lease {lease.tenant_name!r}",
        )
    segments = [contract]

    timeline_end = months[-1]
    behavior = lease.upon_expiration
    profile_ref = (lease.option_profile
                   if behavior == UponExpiration.option
                   else lease.market_leasing_profile)
    prior = _contract_prior_rent(lease, end, months, analysis_begin,
                                 inflation, market_rent_annual)
    prev_end = end

    while prev_end < timeline_end and behavior not in (
        UponExpiration.vacate, UponExpiration.reabsorb
    ):
        if profile_ref is None:
            raise ValueError(
                f"lease {lease.tenant_name!r}: upon_expiration "
                f"'{behavior.value}' requires a market leasing profile"
            )
        try:
            profile = profiles[profile_ref]
        except KeyError:
            raise ValueError(
                f"lease {lease.tenant_name!r}: unknown market leasing "
                f"profile {profile_ref!r}"
            ) from None
        where = f"lease {lease.tenant_name!r} / profile {profile.name!r}"

        p = 1.0 if behavior == UponExpiration.renew else (
            profile.renewal_probability / 100.0
        )
        downtime = int((1.0 - p) * profile.months_vacant + 0.5)  # §4.2 round
        seg_start = prev_end + 1 + downtime
        seg_end = seg_start + profile.term_months - 1

        factor = (
            _market_factor(inflation, seg_start, analysis_begin)
            if profile.term_growth and inflation is not None else 1.0
        )
        new_rent = _market_monthly(profile.market_base_rent_new, lease.area,
                                   factor, prior, where)
        if isinstance(profile.market_base_rent_renew, PctOfNew):
            renew_market = new_rent * profile.market_base_rent_renew.pct_of_new / 100.0
        else:
            renew_market = _market_monthly(profile.market_base_rent_renew,
                                           lease.area, factor, prior, where)
        rule = profile.intelligent_renewals
        if rule == IntelligentRenewalRule.prior:
            renew_side = prior
        elif rule == IntelligentRenewalRule.lesser_of:
            renew_side = min(prior, renew_market)
        elif rule == IntelligentRenewalRule.greater_of:
            renew_side = max(prior, renew_market)
        else:
            renew_side = renew_market
        blended = p * renew_side + (1.0 - p) * new_rent

        lc_pct, lc_rate = _blend_lc(profile.lc_new, profile.lc_renew, p, where)
        segment = LeaseSegment(
            lease=lease, profile=profile, start=seg_start, end=seg_end,
            speculative=True, renewal_weight=p, downtime_months=downtime,
            initial_rent_monthly=blended,
            rent_increases=list(profile.rent_increases or []),
            free_rent_months=(p * profile.free_rent_months_renew
                              + (1.0 - p) * profile.free_rent_months_new),
            free_rent_profile=profile.free_rent_profile,
            recoveries=profile.recoveries,
            percentage_rent=profile.percentage_rent,
            ti=_blend_money(profile.ti_new, profile.ti_renew, p, where),
            lc_pct=lc_pct, lc_rate=lc_rate,
        )
        segments.append(segment)

        prior = segment_rent_level(segment, seg_end)
        prev_end = seg_end
        behavior = profile.upon_expiration
        profile_ref = (profile.chained_profile
                       if behavior == UponExpiration.option else profile.name)
    return segments


# --------------------------------------------------------------------- #
# Speculative segment projection (Phase 2 Step 2; spec §4.2, §2.3)       #
# --------------------------------------------------------------------- #

@dataclass
class SegmentRentCashflows:
    """Monthly rent series for one speculative segment (spec §2.3 accounts).

    ``base_rent`` is the full-occupancy basis: during downtime months it
    posts the market rent the space would have earned, offset one-for-one
    by ``absorption_vacancy`` (negative), so Scheduled Base Rental Revenue
    nets to zero over downtime while PGR reflects full occupancy
    (spec §4.2/§2.3; "Absorption & Turnover Vacancy: loss in rent due to
    downtime between leases" [AE p. 538]).
    """

    base_rent: pd.Series
    free_rent: pd.Series           # negative
    absorption_vacancy: pd.Series  # negative


def project_segment_rent(segment: LeaseSegment, months: pd.PeriodIndex,
                         free_rent_profile: Optional[FreeRentProfile] = None,
                         ) -> SegmentRentCashflows:
    """Project one speculative segment's rent onto the monthly timeline
    (spec §4.1 step 4, speculative portion; §4.2).

    Downtime months post the segment's blended rent to Base Rental Revenue
    and its negative to Absorption & Turnover Vacancy. Occupied months post
    the blended rent with the MLP's steps. Weighted free rent abates the
    first ``free_rent_months`` of the term front-loaded ("free rent is
    applied at the beginning of the lease" [AE p. 239]) with a fractional
    final month, honoring the profile's elements — base rent abates unless
    the profile says otherwise [AE p. 254]. Speculative segments carry no
    CPI (DEVIATIONS.md §7).
    """
    if not segment.speculative:
        raise ValueError("project_segment_rent is for speculative segments; "
                         "contract terms project via project_contract_rent")
    base = pd.Series(0.0, index=months, name="base_rent")
    free = pd.Series(0.0, index=months, name="free_rent")
    absorption = pd.Series(0.0, index=months, name="absorption_vacancy")

    downtime_start = segment.downtime_start
    if downtime_start is not None:
        for period in months:
            if downtime_start <= period < segment.start:
                base[period] += segment.initial_rent_monthly
                absorption[period] -= segment.initial_rent_monthly

    abate = free_rent_profile is None or free_rent_profile.abate_base_rent
    fractions = segment_free_fraction(segment, months)
    for period in months:
        if not segment.start <= period <= segment.end:
            continue
        level = segment_rent_level(segment, period)
        base[period] += level
        if abate:
            fraction = float(fractions[period])
            if fraction:
                free[period] -= fraction * level
    return SegmentRentCashflows(base_rent=base, free_rent=free,
                                absorption_vacancy=absorption)
