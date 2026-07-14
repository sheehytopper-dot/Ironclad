"""Tenant reports (Phase 4 Step 4; spec §7 reports 11-12)
[AE pp. 573-579, 574, 815-819]:

* **#11 Lease Summary** — the current rent-roll presentation: one row per
  included chain (tenant), from its contract lease (:func:`lease_summary`).
* **#12 Lease Expiration** — by fiscal year: count, SF, % of building, and
  expiring rent of the included leases whose contract terms end that year
  (:func:`lease_expiration`).

**Lease-status filter (`statuses`) — [AE p. 818].** ARGUS's Lease
Expiration report exposes lease status as a first-class, checkbox filter
("Contract, Speculative, Contract Renewal, Option, Month-to-Month,
Holdover" [AE p. 818]; printed p. 818 = PDF p. 819). Both reports mirror
that with an explicit **inclusion** set keyed on ``lease.status``. The §3
schema narrows status to ``contract`` / ``speculative`` / ``mtm``, so the
[AE p. 818] categories map: Contract / Contract Renewal / Option →
``contract`` (renewals and option terms are not separate statuses here);
Month-to-Month → ``mtm``; Speculative → ``speculative``; Holdover is not
modeled. **Default = contract only** (``DEFAULT_STATUSES``); speculative
and MTM are excluded by default but selectable. Keying on ``lease.status``
makes these reports agree with the Lease Audit's deliberate [AE p. 398]
speculative labeling (``lease_audit._phase`` reads the same
``lease.status``): an absorption lease's own first term is *speculative*,
so it is excluded from the default contract view rather than mislabeled as
contract (DEVIATIONS.md §25).

**No "SF sums to rentable" identity.** The Phase 4 Step 4 plan's original
acceptance "Lease Expiration SF sums to rentable" was **defective** — a
suite can turn over more than once over the term (legitimate turnover), so
cumulative expiring SF can exceed 100% of the building, and a stated
(fixed) rentable area need not equal the sum of demised suite areas
(DEVIATIONS.md §25, owner-adjudicated). It is replaced by
:func:`reconcile_lease_expiration` (a structural tie to the MODEL INPUT,
capable of failing) and :func:`assert_expiration_within_building` (a
per-fiscal-year SANITY BOUND, not an invariant).

Count/area/percent reports — **not** monetary — so the $ unit toggle does
not apply (``monetary=False``); expiring rent is the contractual annual
base rent in force at expiration. The engine never imports UI code (Iron
Rule 1).
"""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Union

import pandas as pd

from engine.calc.absorption import generate_absorption_leases
from engine.calc.leases import lease_term_periods, segment_rent_level
from engine.calc.timeline import fiscal_year_of
from engine.models import LeaseStatus
from engine.reports.base import Report, ReportMeta

#: Default inclusion set: contract only (contract family per [AE p. 818] —
#: Contract / Contract Renewal / Option all map to ``contract`` in the §3
#: schema). Speculative and MTM are excluded by default but selectable.
DEFAULT_STATUSES: tuple[LeaseStatus, ...] = (LeaseStatus.contract,)

StatusInput = Union[LeaseStatus, str]

SUMMARY_COLUMNS = [
    "tenant", "suite", "status", "lease_type", "area", "lease_start",
    "lease_end", "term_months", "monthly_base_rent", "annual_base_rent",
    "base_rent_psf_yr", "upon_expiration",
]

EXPIRATION_COLUMNS = [
    "fiscal_year", "expiring_leases", "expiring_sf", "pct_of_building",
    "expiring_annual_rent",
]


def _status_set(statuses: Iterable[StatusInput]) -> set[str]:
    """Normalize the inclusion filter to a set of status strings (accepts
    ``LeaseStatus`` members or their ``.value`` strings)."""
    return {s.value if isinstance(s, LeaseStatus) else str(s) for s in statuses}


def _contract_segment(segments):
    """The single contract (non-speculative) segment of a resolved chain —
    it carries the lease's own term and area (spec §4.1 pass 3). An
    absorption lease's own first term is such a segment too; the chain is
    classified by its underlying ``lease.status`` (see the module
    docstring / [AE p. 398]), not by this flag."""
    for segment in segments:
        if not segment.speculative:
            return segment
    return segments[0]  # a pure-speculative chain (defensive; unusual)


def _included_chains(result, status_set: set[str]):
    """Yield ``(tenant, contract_segment, lease)`` for chains whose
    underlying lease status is in the inclusion set."""
    for tenant, segments in result.segments.items():
        contract = _contract_segment(segments)
        if contract.lease.status.value in status_set:
            yield tenant, contract, contract.lease


def lease_summary(result, *,
                  statuses: Iterable[StatusInput] = DEFAULT_STATUSES) -> Report:
    """Build the Lease Summary (#11): one row per included chain, from the
    contract lease — tenant, suite, status, type, area, term, and the
    contractual base rent (monthly / annual / $ per SF per year)
    [AE pp. 573-579]. ``statuses`` selects which lease statuses to include
    ([AE p. 818]; default contract only)."""
    status_set = _status_set(statuses)
    rows = []
    for tenant, contract, lease in _included_chains(result, status_set):
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
    # Distinct demised area: dedupe by suite so a physical space entered as
    # two sequential leases (a signed renewal — e.g. Freeport suite 100) is
    # NOT double-counted. This is DEMISED SF (sum of unique leased suites),
    # explicitly NOT the building rentable area (DEVIATIONS.md §25 fix — the
    # old ``total_area`` summed duplicates and overstated the building).
    demised: dict[str, float] = {}
    for row in rows:
        key = row["suite"] or row["tenant"]
        demised[key] = max(demised.get(key, 0.0), row["area"])
    meta = ReportMeta(name="Lease Summary", number=11, monetary=False,
                      citation="[AE pp. 573-579]",
                      extra={"lease_count": len(frame),
                             "included_statuses": sorted(status_set),
                             "distinct_demised_area": float(sum(demised.values()))})
    return Report(frame=frame, meta=meta)


def reconcile_lease_summary(report: Report, result, *,
                            statuses: Iterable[StatusInput] = DEFAULT_STATUSES
                            ) -> pd.DataFrame:
    """Per-row area/date checks against the resolved chains (included
    statuses only) — a frame of exact-zero area diffs and boolean date
    matches when the summary faithfully echoes the segments."""
    status_set = _status_set(statuses)
    frame = report.frame.set_index("tenant")
    rows = {}
    for tenant, contract, _lease in _included_chains(result, status_set):
        row = frame.loc[tenant]
        rows[tenant] = {
            "area_diff": float(row["area"]) - contract.area,
            "start_matches": row["lease_start"] == str(contract.start),
            "end_matches": row["lease_end"] == str(contract.end),
        }
    return pd.DataFrame(rows).T


def lease_expiration(result, *, fiscal_year_end_month: int = 12,
                     statuses: Iterable[StatusInput] = DEFAULT_STATUSES
                     ) -> Report:
    """Build the Lease Expiration report (#12): one row per fiscal year in
    which an included contract lease term ends, with the count of expiring
    leases, total expiring SF, that SF as a share of the building (rentable
    area), and the expiring contractual annual base rent
    [AE pp. 574, 815-819]. ``statuses`` selects which lease statuses to
    include ([AE p. 818]; default contract only).

    Each included chain contributes exactly one expiration (its contract
    term end); leases whose terms end past the analysis timeline bucket
    into their true fiscal year. Cumulative expiring SF may exceed the
    building when a suite turns over more than once — that is legitimate
    (DEVIATIONS.md §25); see :func:`assert_expiration_within_building` for
    the per-year sanity bound."""
    status_set = _status_set(statuses)
    rentable = float(result.rentable_area.iloc[0])
    by_year: dict[int, dict[str, float]] = {}
    for _tenant, contract, _lease in _included_chains(result, status_set):
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
                             "included_statuses": sorted(status_set),
                             "total_expiring_sf": float(frame["expiring_sf"].sum())})
    return Report(frame=frame, meta=meta)


def reconcile_lease_expiration(report: Report, model, *,
                               fiscal_year_end_month: int = 12,
                               statuses: Iterable[StatusInput] = DEFAULT_STATUSES
                               ) -> pd.Series:
    """Structural reconciliation of the report against the **model input** —
    a source the builder never reads (it builds from ``result.segments``),
    so this is NOT a self-subtraction and CAN fail (DEVIATIONS.md §25).

    Rebuilds the expected expiration table independently from
    ``model.rent_roll`` (+ ``model.absorption`` when speculative is
    included) via :func:`lease_term_periods` and :func:`fiscal_year_of`,
    then diffs it against the report: overall lease count, overall expiring
    SF, and the per-fiscal-year count and SF. All four diffs are ~0 when the
    builder emits each included lease exactly once at the right area and
    year; a dropped, duplicated, mis-aread, or mis-bucketed lease makes one
    nonzero."""
    status_set = _status_set(statuses)
    included = [l for l in model.rent_roll if l.status.value in status_set]
    if LeaseStatus.speculative.value in status_set:
        profiles = {p.name: p for p in model.market_leasing_profiles}
        begin = model.property.analysis_begin
        for spec in model.absorption:
            included.extend(
                generate_absorption_leases(spec, profiles, begin, model.inflation))

    expected: dict[int, dict[str, float]] = defaultdict(
        lambda: {"count": 0, "sf": 0.0})
    for lease in included:
        _start, end = lease_term_periods(lease)
        year = fiscal_year_of(end, fiscal_year_end_month)
        expected[year]["count"] += 1
        expected[year]["sf"] += float(lease.area)

    rep = report.frame.set_index("fiscal_year")
    max_year_sf_diff = 0.0
    max_year_count_diff = 0.0
    for year in set(expected) | set(rep.index):
        r_sf = float(rep.loc[year, "expiring_sf"]) if year in rep.index else 0.0
        r_n = int(rep.loc[year, "expiring_leases"]) if year in rep.index else 0
        e_sf = expected[year]["sf"]
        e_n = expected[year]["count"]
        max_year_sf_diff = max(max_year_sf_diff, abs(r_sf - e_sf))
        max_year_count_diff = max(max_year_count_diff, abs(r_n - e_n))
    return pd.Series({
        "lease_count_diff": float(
            report.frame["expiring_leases"].sum()
            - sum(v["count"] for v in expected.values())),
        "total_sf_diff": float(
            report.frame["expiring_sf"].sum()
            - sum(v["sf"] for v in expected.values())),
        "max_year_count_diff": float(max_year_count_diff),
        "max_year_sf_diff": float(max_year_sf_diff),
    })


def assert_expiration_within_building(report: Report, result, *,
                                      tolerance: float = 0.0) -> None:
    """**SANITY BOUND, not an invariant** (DEVIATIONS.md §25): assert no
    single fiscal year's expiring SF exceeds the rentable area. A building
    with heavy short-term turnover could legitimately roll >100% of its
    area in one year and trip this — it is a smoke check for gross
    within-year double-counting, not a guaranteed identity, and the figure
    is fiscal-year-end dependent (assert it across conventions, never citing
    a single convention's number as if universal). Raises naming the first
    breaching year and the convention in force."""
    rentable = float(result.rentable_area.iloc[0])
    limit = rentable * (1.0 + tolerance)
    breach = report.frame[report.frame["expiring_sf"] > limit]
    if not breach.empty:
        row = breach.iloc[0]
        fye = report.meta.extra.get("fiscal_year_end_month")
        raise ValueError(
            f"lease-expiration sanity bound tripped: FY{int(row['fiscal_year'])} "
            f"expiring SF {row['expiring_sf']:,.0f} exceeds rentable "
            f"{rentable:,.0f} (fiscal_year_end_month={fye}); inspect for a "
            f"within-year double-count (DEVIATIONS.md §25)")
