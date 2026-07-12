"""Tenant miscellaneous items (spec §3.12; §4.1 pass 8) — contract-term
items [AE pp. 378-381] and rollover items carried via the MLP
[AE pp. 240-244].

The manual "link[s] miscellaneous rent, expenses, and other items to
tenants" [AE pp. 378, 240]: per-tenant charges (or, with a negative
amount, abatements — spec §3.12) posting to the Miscellaneous Tenant
Revenue ledger line. Inputs per the manual's Detail grid [AE p. 379;
pp. 241-242]: a currency amount or an amount per tenant area, at annual or
monthly frequency — the §3 schema states the frequency in the ``MoneyUnit``
($/yr, $/mo, $/SF/yr, $/SF/mo) and generalizes the schedule through the
shared ``Timing`` machinery [AE pp. 278, 361-362]. Amounts inflate on a
selectable index [AE p. 380] (general by default — revenue-side convention,
like property revenues); ``Limits`` clamp the projected **monthly** amount
[AE pp. 380-381]. The manual's "% of Rent" input method (with Rent
Components) and the separate owner-cost **Incentives** grid
[AE pp. 381-382] are not modeled — DEVIATIONS.md §15.

Projection is per segment over **occupied months only** — nothing during
rollover downtime, the Step 2 convention recoveries and percentage rent
already follow: the contract term carries the lease's own items, each
speculative segment its MLP's [AE pp. 240-244]. Free rent suppresses an
item only when both sides opt in — the item's ``free_rent_abates`` AND the
governing free-rent profile's ``abate_miscellaneous`` [AE pp. 253-254] —
applied as the same fractional free-month series ``abate_recoveries``
uses.

**EXTERNALLY UNVALIDATED** (checked 2026-07-11): no golden fixture uses
``miscellaneous_items``, so this module has only the manual's definitional
statements as references — the same standing as percentage rent pending
golden #3. Everything returns monthly Period[M] Series (spec §2.3); the
engine never imports UI code (Iron Rule 1).
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

import pandas as pd

from engine.calc.expenses import _repeat_postings, _timing_window
from engine.calc.inflation import index_schedule, inflation_factors
from engine.models import Inflation, MiscItemSpec, MoneyUnit, TimingMethod

#: Units the manual's misc grid expresses: a currency amount or an amount
#: per tenant area, annually or monthly [AE p. 379; pp. 241-242].
_SUPPORTED_UNITS = {
    MoneyUnit.dollars_per_year,
    MoneyUnit.dollars_per_month,
    MoneyUnit.dollars_per_area_per_year,
    MoneyUnit.dollars_per_area_per_month,
}


def _monthly_equivalent(item: MiscItemSpec, area: float, factor: float,
                        where: str) -> float:
    unit = item.unit
    if unit not in _SUPPORTED_UNITS:
        raise ValueError(
            f"{where}: miscellaneous item {item.name!r} uses unit "
            f"'{unit.value}', which is not supported for tenant "
            "miscellaneous items. Use a dollar amount per year or month, "
            "or an amount per SF per year or month (the manual's '% of "
            "Rent' input method is not modeled — DEVIATIONS.md §15)."
        )
    if unit == MoneyUnit.dollars_per_year:
        base = item.amount / 12.0
    elif unit == MoneyUnit.dollars_per_month:
        base = item.amount
    elif unit == MoneyUnit.dollars_per_area_per_year:
        base = item.amount * area / 12.0
    else:  # dollars_per_area_per_month
        base = item.amount * area
    return base * factor


def project_segment_misc_items(
        segment, months: pd.PeriodIndex, *,
        analysis_begin: dt.date,
        inflation: Inflation,
        abatement: Optional[pd.Series] = None) -> pd.Series:
    """One segment's monthly Miscellaneous Tenant Revenue over its occupied
    months (spec §4.1 pass 8).

    Each item projects through the shared Timing machinery (continuous /
    date-range / repeating [AE pp. 361-362]) intersected with the segment's
    occupied window, inflates on its index [AE p. 380], and is clamped per
    month by its ``Limits`` [AE pp. 380-381]. ``abatement`` is the
    fractional free-month series (as used for recoveries [AE p. 254]);
    it suppresses only items with ``free_rent_abates`` — run.py passes it
    only when the governing free-rent profile abates miscellaneous items.
    Negative amounts post as abatements (spec §3.12).
    """
    total = pd.Series(0.0, index=months, name="misc_tenant_revenue")
    items = segment.miscellaneous_items
    if not items:
        return total
    where = f"lease {segment.lease.tenant_name!r} segment {segment.start}"
    for item in items:
        if isinstance(item.inflation, list):
            rates = item.inflation
        else:
            rates = index_schedule(inflation, item.inflation,
                                   default="general")
        factors = inflation_factors(
            rates, months, analysis_begin,
            inflation.inflation_month, inflation.timing_basis,
        )
        series = pd.Series(0.0, index=months)
        window = _timing_window(item.timing, months)
        start, end = window
        if item.timing.method == TimingMethod.repeating:
            active = []
            for period, interval in _repeat_postings(item.timing, window,
                                                     months):
                if segment.start <= period <= segment.end:
                    series[period] = _monthly_equivalent(
                        item, segment.area, float(factors[period]), where
                    ) * interval
                    active.append(period)
        else:
            active = [p for p in months
                      if start <= p <= end
                      and segment.start <= p <= segment.end]
            for period in active:
                series[period] = _monthly_equivalent(
                    item, segment.area, float(factors[period]), where
                )
        if item.limits is not None:
            for period in active:
                value = series[period]
                if item.limits.min is not None:
                    value = max(value, item.limits.min)
                if item.limits.max is not None:
                    value = min(value, item.limits.max)
                series[period] = value
        if item.free_rent_abates and abatement is not None:
            series = series * (
                1.0 - abatement.reindex(months, fill_value=0.0)
            ).clip(lower=0.0)
        total = total + series
    return total
