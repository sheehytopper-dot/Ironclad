"""Tenant reports (Phase 4 Step 4; spec §7 reports 11-12)
[AE pp. 573-579, 815-819]:

* **#11 Lease Summary** — the current rent-roll presentation: one row per
  resolved chain (tenant), from its contract lease (:func:`lease_summary`).
* **#12 Lease Expiration** — by fiscal year: count, SF, % of building, and
  expiring rent of the leases whose contract terms end that year
  (:func:`lease_expiration`).

Both are views over the resolved chains (``result.segments``) — each chain
has exactly one contract (non-speculative) segment carrying the lease's own
term and area, so the reports count each physical space once. **Lease
Expiration's SF sums to the total contract area** (:func:`
reconcile_expiration_area`), which for a fully-leased building with no
absorption/reabsorption phantom leases equals the rentable area (the
plan's acceptance). ``% of building`` uses the run's rentable area (spec
§3.2) as the denominator.

Count/area/percent reports — **not** monetary — so the $ unit toggle does
not apply (``monetary=False``); expiring rent is the contractual annual
base rent in force at expiration. The engine never imports UI code (Iron
Rule 1).
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from engine.calc.leases import segment_rent_level
from engine.calc.timeline import fiscal_year_of
from engine.reports.base import Report, ReportMeta

SUMMARY_COLUMNS = [
    "tenant", "suite", "status", "lease_type", "area", "lease_start",
    "lease_end", "term_months", "monthly_base_rent", "annual_base_rent",
    "base_rent_psf_yr", "upon_expiration",
]

EXPIRATION_COLUMNS = [
    "fiscal_year", "expiring_leases", "expiring_sf", "pct_of_building",
    "expiring_annual_rent",
]


def _contract_segment(segments):
    """The single contract (non-speculative) segment of a resolved chain —
    it carries the lease's own term and area (spec §4.1 pass 3). Absorption
    leases' own first term is a contract segment too; only the MLP rollover
    tail is speculative."""
    for segment in segments:
        if not segment.speculative:
            return segment
    return segments[0]  # a pure-speculative chain (defensive; unusual)


def lease_summary(result) -> Report:
    """Build the Lease Summary (#11): one row per chain (tenant), from the
    contract lease — tenant, suite, status, type, area, term, and the
    contractual base rent (monthly / annual / $ per SF per year)
    [AE pp. 573-579]."""
    rows = []
    for tenant, segments in result.segments.items():
        contract = _contract_segment(segments)
        lease = contract.lease
        monthly = segment_rent_level(contract, contract.start)
        annual = monthly * 12.0
        rows.append({
            "tenant": tenant,
            "suite": lease.suite or "",
            "status": lease.status.value,
            "lease_type": lease.lease_type.value,
            "area": float(lease.area),
            "lease_start": str(contract.start),
            "lease_end": str(contract.end),
            "term_months": (contract.end - contract.start).n + 1,
            "monthly_base_rent": monthly,
            "annual_base_rent": annual,
            "base_rent_psf_yr": (annual / lease.area if lease.area else float("nan")),
            "upon_expiration": lease.upon_expiration.value,
        })
    frame = pd.DataFrame(rows, columns=SUMMARY_COLUMNS)
    meta = ReportMeta(name="Lease Summary", number=11, monetary=False,
                      citation="[AE pp. 573-579]",
                      extra={"tenant_count": len(frame),
                             "total_area": float(frame["area"].sum())})
    return Report(frame=frame, meta=meta)


def reconcile_lease_summary(report: Report, result) -> pd.DataFrame:
    """Per-row area/date checks against the resolved chains — a frame of
    exact zeros (area diff) / booleans (dates match) when the summary
    faithfully echoes the segments. One row per tenant."""
    frame = report.frame.set_index("tenant")
    rows = {}
    for tenant, segments in result.segments.items():
        contract = _contract_segment(segments)
        row = frame.loc[tenant]
        rows[tenant] = {
            "area_diff": float(row["area"]) - contract.area,
            "start_matches": row["lease_start"] == str(contract.start),
            "end_matches": row["lease_end"] == str(contract.end),
        }
    return pd.DataFrame(rows).T


def lease_expiration(result, *, fiscal_year_end_month: int = 12) -> Report:
    """Build the Lease Expiration report (#12): one row per fiscal year in
    which a contract lease term ends, with the count of expiring leases,
    total expiring SF, that SF as a share of the building (rentable area),
    and the expiring contractual annual base rent [AE pp. 574, 815-819].

    Each chain contributes exactly one expiration (its contract term end),
    so the expiring SF counts each space once; leases whose terms end past
    the analysis timeline bucket into their true fiscal year."""
    rentable = float(result.rentable_area.iloc[0])
    by_year: dict[int, dict[str, float]] = {}
    for segments in result.segments.values():
        contract = _contract_segment(segments)
        year = fiscal_year_of(contract.end, fiscal_year_end_month)
        annual_rent = segment_rent_level(contract, contract.end) * 12.0
        bucket = by_year.setdefault(year, {"count": 0, "sf": 0.0, "rent": 0.0})
        bucket["count"] += 1
        bucket["sf"] += contract.area
        bucket["rent"] += annual_rent
    rows = []
    for year in sorted(by_year):
        b = by_year[year]
        rows.append({
            "fiscal_year": year,
            "expiring_leases": int(b["count"]),
            "expiring_sf": b["sf"],
            "pct_of_building": (b["sf"] / rentable if rentable else float("nan")),
            "expiring_annual_rent": b["rent"],
        })
    frame = pd.DataFrame(rows, columns=EXPIRATION_COLUMNS)
    meta = ReportMeta(name="Lease Expiration", number=12, monetary=False,
                      citation="[AE pp. 574, 815-819]",
                      extra={"rentable_area": rentable,
                             "fiscal_year_end_month": fiscal_year_end_month,
                             "total_expiring_sf": float(frame["expiring_sf"].sum())})
    return Report(frame=frame, meta=meta)


def reconcile_expiration_area(report: Report, result) -> float:
    """Total expiring SF minus the total contract area of the resolved
    chains — exactly zero when every space is counted once. For a
    building with no absorption/reabsorption phantom leases this total is
    the rentable area (the plan's "SF sums to rentable")."""
    contract_area = sum(_contract_segment(s).area
                        for s in result.segments.values())
    return float(report.frame["expiring_sf"].sum()) - contract_area
