"""Tenant improvement and leasing commission posting (Phase 3 Step 1;
spec §3.9 / §4.1 pass 11) [AE pp. 245-248].

Both costs post as a **single lump sum in the month the segment starts**:
"All tenant improvements are paid at the beginning of the lease"
[AE p. 246]; "All leasing commissions are paid at the beginning of the
lease" [AE p. 247]. The manual's TI Timing / LC Timing distribution grids
[AE pp. 246, 248] and the named TI/LC category machinery (spread timing,
year tiers, escalation elements [AE pp. 258-262]) exist in the schema
(``TICategory``/``LCCategory``) but have no calculation consumer — they
are refused loudly at the run guards, and no spread logic is invented
here (DEVIATIONS.md §16).

Amount semantics per segment (contract and speculative are handled
uniformly through ``LeaseSegment.ti`` / ``lc_pct`` / ``lc_rate``, which
chain resolution fills for both — the contract segment via an identity
blend of ``Lease.leasing_costs``, speculative segments via the §4.2
probability weighting of the MLP's new/renew sides):

- **TI** [AE pp. 245-246]: ``$/SF × segment area`` or a flat ``$``
  amount. Speculative amounts inflate to segment start on the market
  index (the ``term_growth`` factor market rents use) — the manual pages
  name no index, but golden #1's published rollover TI equals the
  blended $/SF × area × the market factor exactly, so the golden is the
  evidence (DEVIATIONS.md §16).
- **LC, % form** [AE p. 247 "Fixed %"]: percent of the entire lease
  value over the segment's full term — base rent plus fixed steps less
  free rent, CPI excluded — even where the term runs past the analysis
  timeline. Free rent reduces the base only when the segment's free-rent
  profile abates base rent [AE p. 254]. ``pct_years`` restricts the base
  to the listed lease years (spec §3.9).
- **LC, $ form** [AE p. 247]: ``$/SF × segment area`` or a flat ``$``
  amount; speculative amounts inflate like TI.

A contract segment starting before the analysis window posts nothing —
the cost was paid at the (pre-analysis) lease start.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from engine.models import Inflation, MoneyRate, MoneyUnit
from engine.models.profiles import FreeRentProfile

from .leases import (
    LeaseSegment,
    _market_factor,
    contract_free_fraction,
    segment_free_fraction,
    segment_rent_level,
)


@dataclass
class SegmentCapital:
    """One segment's leasing costs (positive dollars) and posting month."""

    month: pd.Period
    ti: float
    lc: float


def _lump_sum(rate: MoneyRate, area: float, factor: float,
              where: str, what: str) -> float:
    """A one-time $ amount from a TI or $-form LC rate [AE pp. 245, 247]."""
    if rate.unit == MoneyUnit.dollars_per_area:
        return rate.amount * area * factor
    if rate.unit == MoneyUnit.dollars:
        return rate.amount * factor
    raise ValueError(
        f"{where}: {what} unit '{rate.unit.value}' is not a one-time cost "
        "unit (use dollars_per_area or dollars)"
    )


def _lc_pct_base(segment: LeaseSegment,
                 free_rent_profile: Optional[FreeRentProfile]) -> float:
    """The "entire lease value over the term": base rent plus fixed steps
    less free rent, CPI excluded [AE p. 247], over the segment's own full
    term (not clipped to the analysis timeline)."""
    term = pd.period_range(segment.start, segment.end, freq="M")
    if segment.speculative:
        fractions = segment_free_fraction(segment, term)
    else:
        fractions = contract_free_fraction(segment.lease, term)
    abates = free_rent_profile is None or free_rent_profile.abate_base_rent
    years: Optional[set[int]] = None
    if segment.lc_pct_years:
        years = set(segment.lc_pct_years)
    total = 0.0
    for i, period in enumerate(term):
        if years is not None and (i // 12 + 1) not in years:
            continue
        level = segment_rent_level(segment, period)
        occupied = 1.0 - float(fractions[period]) if abates else 1.0
        total += level * occupied
    return total


def segment_capital(segment: LeaseSegment, analysis_begin: dt.date,
                    inflation: Optional[Inflation],
                    free_rent_profile: Optional[FreeRentProfile] = None,
                    ) -> SegmentCapital:
    """One segment's TI and LC dollars, posted at segment start
    [AE pp. 245-248]. Speculative $-amounts inflate to segment start on
    the market index when the profile opts into ``term_growth``."""
    where = f"lease {segment.lease.tenant_name!r}"
    factor = 1.0
    if (segment.speculative and segment.profile is not None
            and segment.profile.term_growth and inflation is not None):
        factor = _market_factor(inflation, segment.start, analysis_begin)

    ti = 0.0
    if segment.ti is not None:
        ti = _lump_sum(segment.ti, segment.area, factor, where, "TI")

    lc = 0.0
    if segment.lc_pct is not None:
        lc = segment.lc_pct / 100.0 * _lc_pct_base(segment, free_rent_profile)
    elif segment.lc_rate is not None:
        lc = _lump_sum(segment.lc_rate, segment.area, factor, where, "LC")

    return SegmentCapital(month=segment.start, ti=ti, lc=lc)


def project_lease_capital(segments: list[LeaseSegment],
                          months: pd.PeriodIndex,
                          analysis_begin: dt.date,
                          inflation: Optional[Inflation],
                          free_rent_profiles: dict[str, FreeRentProfile],
                          ) -> tuple[pd.Series, pd.Series]:
    """Post one lease chain's TI/LC lump sums onto the timeline (positive
    dollars; run.py flips the report sign). Segments starting outside the
    timeline post nothing — a pre-analysis contract start paid its costs
    before the window."""
    ti = pd.Series(0.0, index=months, name="tenant_improvements")
    lc = pd.Series(0.0, index=months, name="leasing_commissions")
    for segment in segments:
        if segment.start < months[0] or segment.start > months[-1]:
            continue
        profile = (free_rent_profiles.get(segment.free_rent_profile)
                   if segment.free_rent_profile is not None else None)
        cap = segment_capital(segment, analysis_begin, inflation,
                              free_rent_profile=profile)
        ti[cap.month] += cap.ti
        lc[cap.month] += cap.lc
    return ti, lc
