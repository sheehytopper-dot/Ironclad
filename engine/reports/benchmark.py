"""Benchmark Comparison report (spec §7 report 24; §9.1) — the engine's
fiscal cash flow diffed line-by-line against an OM's published Argus-based
cash flow.

This is the reusable form of the ``_collect_misses`` logic the three
golden comparison tests grew independently (Clorox/Freeport/Cedar Alt).
It loads a golden's ``expected_annual_cash_flow.csv`` (the transcription
of the OM's published Argus figures — the only external ARGUS-based anchor
we have, spec §9.1 / CLAUDE.md Golden-File Strategy), aggregates the
engine's monthly ledger to the fiscal-year view, and emits a per-(account,
fiscal-year) diff with a ``within_tolerance`` flag at the §9.1 default of
$500/line.

**Misses are output, not bugs.** Per the fixture-lock rule inputs are
never tuned to force a match; a line beyond tolerance goes to owner
per-cell adjudication. The four by-design golden reds (Freeport/Cedar Alt
Gate 2/3) reproduce their exact current miss counts through this builder.

DataFrame-only (a comparison table, not a monetary report — the unit
toggle does not apply, ``monetary=False``). The engine never imports UI
code (Iron Rule 1).
"""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Mapping, Optional

import pandas as pd

from engine.reports.base import Report, ReportMeta

#: §9.1 default per-line-per-year tolerance.
DEFAULT_TOLERANCE = 500.0

#: Benchmark Comparison columns (one row per compared account × fiscal year).
COLUMNS = ["account", "column", "fiscal_year", "engine", "published",
           "diff", "abs_diff", "within_tolerance"]


def load_expected_cash_flow(csv_path, fiscal_years: Iterable[int]
                            ) -> dict[str, dict[int, float]]:
    """Load a golden's ``expected_annual_cash_flow.csv`` into
    ``{account: {fiscal_year: published $}}``, **summing rows that share an
    account** (e.g. Freeport's three property-revenue lines map to the one
    ledger column). CSV columns are ``account``, ``om_line``, and one
    ``FY<year>`` per published fiscal year."""
    fiscal_years = list(fiscal_years)
    totals: dict[str, dict[int, float]] = defaultdict(
        lambda: defaultdict(float))
    with open(Path(csv_path), encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            for year in fiscal_years:
                totals[row["account"]][year] += float(row[f"FY{year}"])
    return totals


def benchmark_comparison(fiscal: pd.DataFrame,
                         expected: Mapping[str, Mapping[int, float]], *,
                         fiscal_years: Iterable[int],
                         tolerance: float = DEFAULT_TOLERANCE,
                         account_to_column: Optional[Mapping[str, str]] = None,
                         skip_accounts: Iterable[str] = frozenset()) -> Report:
    """Diff the engine's fiscal cash flow against the published figures.

    ``fiscal`` is the engine's fiscal-year cash flow (years × accounts, e.g.
    ``engine.calc.ledger.to_fiscal_annual`` or
    ``aggregate_period(..., Period.fiscal)``). ``expected`` is
    ``{account: {year: $}}`` from :func:`load_expected_cash_flow`.
    ``account_to_column`` bridges a published account name to its ledger
    column where the two differ (e.g. Clorox's ``"Capital Expenses"`` →
    ``"Capital Reserves"``). ``skip_accounts`` excludes accounts scoped to a
    different gate.

    Returns a :class:`Report` whose frame has one row per compared
    (account, fiscal year) with ``engine``/``published``/``diff`` and the
    ``within_tolerance`` flag; ``meta.extra`` records the tolerance and the
    miss count. The comparison matches the golden tests' ``_collect_misses``
    exactly: ``abs(engine − published) > tolerance``."""
    account_to_column = dict(account_to_column or {})
    skip_accounts = set(skip_accounts)
    fiscal_years = list(fiscal_years)
    rows = []
    for account, by_year in expected.items():
        if account in skip_accounts:
            continue
        column = account_to_column.get(account, account)
        if column not in fiscal.columns:
            raise ValueError(f"ledger is missing line {column!r}")
        for year in fiscal_years:
            published = float(by_year[year])
            engine = float(fiscal.loc[year, column])
            diff = engine - published
            rows.append({
                "account": account,
                "column": column,
                "fiscal_year": year,
                "engine": engine,
                "published": published,
                "diff": diff,
                "abs_diff": abs(diff),
                "within_tolerance": abs(diff) <= tolerance,
            })
    frame = pd.DataFrame(rows, columns=COLUMNS)
    miss_count = int((~frame["within_tolerance"]).sum()) if not frame.empty else 0
    meta = ReportMeta(
        name="Benchmark Comparison", number=24, monetary=False,
        citation="spec §9.1",
        extra={"tolerance": tolerance, "miss_count": miss_count,
               "line_years": len(frame)},
    )
    return Report(frame=frame, meta=meta)


def miss_lines(report: Report) -> list[str]:
    """The out-of-tolerance rows formatted as the golden tests' miss lines —
    ``"  <account> FY<year>: engine X vs OM Y (diff ±Z)"`` — so a caller can
    build the same assertion message. Empty when every line is within
    tolerance."""
    frame = report.frame
    misses = frame[~frame["within_tolerance"]]
    return [
        f"  {r.account} FY{int(r.fiscal_year)}: engine {r.engine:,.0f} vs "
        f"OM {r.published:,.0f} (diff {r.diff:+,.0f})"
        for r in misses.itertuples()
    ]
