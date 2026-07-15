"""Rent-roll Excel export (Phase 4 Step 6 / polish pass; spec §5.2 / §8).

Writes ONE unified **Rent Roll** sheet with a provenance ``status`` column
— **Contractual** for the real rent-roll leases, **Speculative** for
engine-projected tenancy (MLP rollover generations + absorption lease-up) —
plus **Rent Steps** and **Misc Items** companion sheets (Contractual leases
only). Speculative tenancy lives in the ``RunResult`` (``result.segments``),
NOT in the model alone, so the export **consumes the RunResult**: building
speculative rows from ``model.absorption`` alone would miss every MLP
rollover generation (Freeport: 57 speculative segments vs 1 absorption
entry). Values-only; the engine never imports UI code (Iron Rule 1).

Provenance is keyed on the segment: a row is Speculative iff the segment is
a speculative rollover OR its lease is an absorption lease
(``status == speculative``) — the same rule as the Lease Audit [AE p. 398]
and reports #11/#12. The rent-roll leases are labeled Contractual.

**Round-trip (spec §5.2):** the Contractual rows carry the flat §3.12 fields
(+ rent steps + misc name/amount/unit/abatement) and re-import to the same
leases; Speculative rows appear in the export but produce NO lease on import
(they are engine projections, not intake). Nested structures (free rent,
recoveries, percentage rent, deposits, leasing costs, misc timing) live in
the JSON (§5.1) and are out of the flat template's scope (§5.2).

Named tradeoff (DEVIATIONS §25): Contractual rows reconcile to independent
MODEL input (``model.rent_roll``); Speculative rows can only reconcile to
``result.segments`` — the same lineage as this builder, a weaker check —
because engine-projected tenancy has no independent model source.
"""
from __future__ import annotations

import xlsxwriter

from engine.reports.lease_reports import CONTRACTUAL, SPECULATIVE

#: Rent Roll sheet columns. ``status`` is the provenance (Contractual /
#: Speculative); ``lease_status`` is the §3.12 lease status (contract / mtm /
#: speculative). The rest are the flat §3.12 fields.
RENT_ROLL_COLUMNS = [
    "status", "tenant_name", "suite", "external_id", "lease_status",
    "lease_type", "area", "start_date", "end_date", "term_months",
    "base_rent_amount", "base_rent_unit", "upon_expiration",
    "market_leasing_profile", "notes",
]
RENT_STEP_COLUMNS = [
    "tenant_name", "amount", "unit", "pct_increase", "date", "month_offset",
]
MISC_ITEM_COLUMNS = ["tenant_name", "name", "amount", "unit", "free_rent_abates"]

_HEADER_BG = "#3F3D8A"


def _segment_provenance(segment) -> str:
    """Speculative iff a rollover segment or an absorption lease's own term
    (status ``speculative``); else Contractual. Matches reports #11/#12 and
    the Lease Audit [AE p. 398]."""
    if segment.speculative or segment.lease.status.value == "speculative":
        return SPECULATIVE
    return CONTRACTUAL


def _contractual_row(tenant: str, lease) -> list:
    """A real rent-roll lease — full flat §3.12 fields (round-trips)."""
    return [
        CONTRACTUAL, tenant, lease.suite or "", lease.external_id or "",
        lease.status.value, lease.lease_type.value, float(lease.area),
        str(lease.start_date) if lease.start_date is not None else "",
        str(lease.end_date) if lease.end_date is not None else "",
        (lease.term_months if lease.term_months is not None else ""),
        float(lease.base_rent.amount), lease.base_rent.unit.value,
        lease.upon_expiration.value, lease.market_leasing_profile or "",
        lease.notes or "",
    ]


def _speculative_row(tenant: str, segment) -> list:
    """One engine-projected generation (rollover or absorption) — segment-
    derived fields, informational only (NO lease on import)."""
    lease = segment.lease
    term = (segment.end - segment.start).n + 1
    if segment.speculative:                      # rollover: blended $/month
        amount, unit = float(segment.initial_rent_monthly), "dollars_per_month"
    else:                                        # absorption own term
        amount, unit = float(lease.base_rent.amount), lease.base_rent.unit.value
    profile = (segment.profile.name if segment.profile is not None
               else (lease.market_leasing_profile or ""))
    return [
        SPECULATIVE, tenant, lease.suite or "", "", "speculative",
        lease.lease_type.value, float(segment.area),
        str(segment.start.to_timestamp().date()), "", term,
        amount, unit, lease.upon_expiration.value, profile, "",
    ]


def _step_rows(tenant: str, lease) -> list[list]:
    rows = []
    for step in lease.rent_steps:
        rows.append([
            tenant,
            (float(step.amount) if step.amount is not None else ""),
            (step.unit.value if step.unit is not None else ""),
            (float(step.pct_increase) if step.pct_increase is not None else ""),
            (str(step.date) if step.date is not None else ""),
            (step.month_offset if step.month_offset is not None else ""),
        ])
    return rows


def _misc_rows(tenant: str, lease) -> list[list]:
    rows = []
    for item in lease.miscellaneous_items:
        rows.append([
            tenant, item.name, float(item.amount),
            item.unit.value, bool(item.free_rent_abates),
        ])
    return rows


def _write_sheet(workbook, name: str, columns: list[str],
                 rows: list[list]) -> None:
    worksheet = workbook.add_worksheet(name)
    header = workbook.add_format({"bold": True, "font_color": "white",
                                  "bg_color": _HEADER_BG, "border": 1})
    for c, col in enumerate(columns):
        worksheet.write_string(0, c, col, header)
    for r, row in enumerate(rows, start=1):
        for c, value in enumerate(row):
            if value == "" or value is None:
                worksheet.write_blank(r, c, None)
            elif isinstance(value, bool):
                worksheet.write_boolean(r, c, value)
            elif isinstance(value, (int, float)):
                worksheet.write_number(r, c, value)
            else:
                worksheet.write_string(r, c, str(value))
    widths = [max([len(str(columns[c]))]
                  + [len(str(row[c])) for row in rows if row[c] not in ("", None)],
                  default=10) for c in range(len(columns))]
    for c, w in enumerate(widths):
        worksheet.set_column(c, c, min(max(w + 2, 10), 40))
    worksheet.freeze_panes(1, 0)


def export_rent_roll(result, *, path) -> dict[str, int]:
    """Write the rent roll to ``path`` in the §5.2 template layout from a
    ``RunResult``. Contractual rows are the real leases (full flat fields +
    steps + misc); Speculative rows are the engine-projected generations
    from ``result.segments`` (rollover + absorption). Returns
    ``{sheet_name: row_count}`` (excluding headers). Recomputes nothing —
    a faithful echo of the resolved chains."""
    lease_rows: list[list] = []
    step_rows: list[list] = []
    misc_rows: list[list] = []
    for tenant, segments in result.segments.items():
        for segment in segments:
            if _segment_provenance(segment) == CONTRACTUAL:
                lease = segment.lease
                lease_rows.append(_contractual_row(tenant, lease))
                step_rows.extend(_step_rows(tenant, lease))
                misc_rows.extend(_misc_rows(tenant, lease))
            else:
                lease_rows.append(_speculative_row(tenant, segment))
    workbook = xlsxwriter.Workbook(str(path), {"in_memory": True})
    try:
        _write_sheet(workbook, "Rent Roll", RENT_ROLL_COLUMNS, lease_rows)
        _write_sheet(workbook, "Rent Steps", RENT_STEP_COLUMNS, step_rows)
        _write_sheet(workbook, "Misc Items", MISC_ITEM_COLUMNS, misc_rows)
    finally:
        workbook.close()
    contractual = sum(1 for r in lease_rows if r[0] == CONTRACTUAL)
    return {"Rent Roll": len(lease_rows), "Contractual": contractual,
            "Speculative": len(lease_rows) - contractual,
            "Rent Steps": len(step_rows), "Misc Items": len(misc_rows)}
