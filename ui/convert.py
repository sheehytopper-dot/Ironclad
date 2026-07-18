"""Pure grid↔model converters (Phase 5 Step 2; browser-free, unit-tested).

Streamlit's ``st.data_editor`` speaks lists-of-row-dicts; the model speaks
pydantic. These converters translate between them WITHOUT validating —
every commit goes through :func:`ui.state.updated_model`, which revalidates
the whole document and translates any failure into the §5.4 readable
per-cell error. Rows that are entirely blank are dropped (an empty grid row
is "no entry", not an error). Iron Rule 1: imports nothing from Streamlit
and nothing writes back to ``engine/``.
"""
from __future__ import annotations

from typing import Optional


def _is_blank(value) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _blank_row(row: dict) -> bool:
    return all(_is_blank(v) for v in row.values())


# ------------------------------------------------------------------ #
# YearRate schedules (inflation series, vacancy/credit-loss rates)    #
# ------------------------------------------------------------------ #

def year_rates_to_rows(rates: Optional[list]) -> list[dict]:
    """``[{year, rate}]`` rows for a data editor (empty list for None)."""
    return [{"year": r["year"], "rate": r["rate"]} for r in (rates or [])]


def rows_to_year_rates(rows: list[dict]) -> list[dict]:
    """Editor rows → YearRate dicts (blank rows dropped; values passed
    through untyped — pydantic validates in the funnel)."""
    return [{"year": row.get("year"), "rate": row.get("rate")}
            for row in rows if not _blank_row(row)]


# ------------------------------------------------------------------ #
# Area schedule (AreaMeasures.rentable_area_schedule)                 #
# ------------------------------------------------------------------ #

def schedule_to_rows(schedule: Optional[list]) -> list[dict]:
    return [{"date": e["date"], "area": e["area"]} for e in (schedule or [])]


def rows_to_schedule(rows: list[dict]) -> Optional[list[dict]]:
    """Editor rows → AreaScheduleEntry dicts; an empty grid → None (the
    schema's "no schedule"), never an empty list."""
    kept = [{"date": row.get("date"), "area": row.get("area")}
            for row in rows if not _blank_row(row)]
    return kept or None


# ------------------------------------------------------------------ #
# Tenant overrides (GeneralVacancy / CreditLoss)                      #
# ------------------------------------------------------------------ #

def overrides_to_rows(overrides: list) -> list[dict]:
    return [{"tenant_ref": o["tenant_ref"], "exclude": o["exclude"]}
            for o in overrides]


def rows_to_overrides(rows: list[dict]) -> list[dict]:
    return [{"tenant_ref": row.get("tenant_ref"),
             "exclude": bool(row.get("exclude", True))}
            for row in rows if not _is_blank(row.get("tenant_ref"))]


# ------------------------------------------------------------------ #
# Free-rent profiles                                                  #
# ------------------------------------------------------------------ #

FREE_RENT_COLUMNS = ["name", "abate_base_rent", "abate_recoveries",
                     "abate_miscellaneous"]


def free_rent_profiles_to_rows(profiles: list) -> list[dict]:
    return [{k: p[k] for k in FREE_RENT_COLUMNS} for p in profiles]


def rows_to_free_rent_profiles(rows: list[dict]) -> list[dict]:
    return [{"name": row.get("name"),
             "abate_base_rent": bool(row.get("abate_base_rent", True)),
             "abate_recoveries": bool(row.get("abate_recoveries", False)),
             "abate_miscellaneous": bool(row.get("abate_miscellaneous", False))}
            for row in rows if not _is_blank(row.get("name"))]


# ------------------------------------------------------------------ #
# MLP scalar grid (the nested economics live in the detail editor)    #
# ------------------------------------------------------------------ #

#: The scalar MLP columns the grid edits; everything nested (market rents,
#: TI/LC, recoveries, steps, refs) is per-profile detail.
MLP_GRID_COLUMNS = ["name", "term_months", "renewal_probability",
                    "months_vacant", "free_rent_months_new",
                    "free_rent_months_renew", "upon_expiration",
                    "term_growth", "intelligent_renewals"]


def mlp_grid_rows(profiles: list) -> list[dict]:
    return [{k: p[k] for k in MLP_GRID_COLUMNS} for p in profiles]


def apply_mlp_grid_rows(profiles: list, rows: list[dict]) -> list[dict]:
    """Merge edited scalar columns back into the profile dicts **by row
    order**. A new grid row (beyond the existing profiles) becomes a new
    profile from a minimal template; deleting a grid row deletes the
    profile. Nested detail on surviving rows is preserved untouched."""
    kept_rows = [row for row in rows if not _blank_row(row)]
    merged: list[dict] = []
    for i, row in enumerate(kept_rows):
        base = (dict(profiles[i]) if i < len(profiles)
                else _new_mlp_template())
        for column in MLP_GRID_COLUMNS:
            if column in row:
                base[column] = row[column]
        merged.append(base)
    return merged


def _new_mlp_template() -> dict:
    """A minimal new MLP for a freshly added grid row: $0 market rent (the
    user fills real economics in the detail editor); renew = 100% of new."""
    return {
        "name": "New MLP", "term_months": 60, "renewal_probability": 50.0,
        "months_vacant": 0.0,
        "market_base_rent_new": {"amount": 0.0,
                                 "unit": "dollars_per_area_per_year"},
        "market_base_rent_renew": {"pct_of_new": 100.0},
    }


# ------------------------------------------------------------------ #
# Revenues + Expenses (§3.10-3.11; Step 3)                            #
# ------------------------------------------------------------------ #

#: Scalar grid columns; nested detail (timing, limits, annual overrides,
#: inflation schedules) lives in the per-item detail editor.
REVENUE_GRID_COLUMNS = ["name", "account", "amount", "unit",
                        "number_of_spaces", "pct_fixed"]
EXPENSE_GRID_COLUMNS = ["name", "category", "account", "amount", "unit",
                        "pct_fixed", "recoverable", "expense_group",
                        "amortization_years", "refundable"]
EXPENSE_GROUP_COLUMNS = ["name", "members"]
ANNUAL_OVERRIDE_COLUMNS = ["year", "amount"]

#: The engine-refused unit (run.py phase guards) — rows carrying it are
#: excluded from the editable grid and rendered read-only (Step 0 D2).
REFUSED_UNIT = "pct_of_account"


def is_refused_item(item: dict) -> bool:
    return item.get("unit") == REFUSED_UNIT


def items_to_grid_rows(items: list, columns: list[str]) -> list[dict]:
    """Editable grid rows — refused (pct_of_account) items excluded."""
    return [{c: item.get(c) for c in columns}
            for item in items if not is_refused_item(item)]


def refused_items(items: list) -> list[dict]:
    return [item for item in items if is_refused_item(item)]


def apply_grid_rows_with_refused(items: list, rows: list[dict],
                                 columns: list[str], template: dict
                                 ) -> list[dict]:
    """Merge edited scalar grid rows back over the EDITABLE items by row
    order (add = ``template`` + row; delete = drop), preserving nested
    detail on survivors; refused (pct_of_account) items are re-inserted at
    their original positions untouched — read-only means read-only."""
    refused = [(i, item) for i, item in enumerate(items)
               if is_refused_item(item)]
    editable = [item for item in items if not is_refused_item(item)]
    kept_rows = [row for row in rows if not _blank_row(row)]
    merged: list[dict] = []
    for i, row in enumerate(kept_rows):
        base = dict(editable[i]) if i < len(editable) else dict(template)
        for column in columns:
            if column in row:
                base[column] = row[column]
        merged.append(base)
    for original_index, item in refused:
        merged.insert(min(original_index, len(merged)), item)
    return merged


NEW_REVENUE_TEMPLATE = {"name": "New Revenue", "amount": 0.0,
                        "unit": "dollars_per_year"}
NEW_EXPENSE_TEMPLATE = {"name": "New Expense", "category": "operating",
                        "amount": 0.0, "unit": "dollars_per_year"}


def overrides_to_override_rows(overrides: list) -> list[dict]:
    return [{"year": o["year"], "amount": o["amount"]} for o in overrides]


def rows_to_annual_overrides(rows: list[dict]) -> list[dict]:
    return [{"year": row.get("year"), "amount": row.get("amount")}
            for row in rows if not _blank_row(row)]


def expense_groups_to_rows(groups: list) -> list[dict]:
    return [{"name": g["name"], "members": ", ".join(g["members"])}
            for g in groups]


def rows_to_expense_groups(rows: list[dict]) -> list[dict]:
    out = []
    for row in rows:
        if _is_blank(row.get("name")):
            continue
        members_text = row.get("members") or ""
        members = [m.strip() for m in str(members_text).split(",")
                   if m.strip()]
        out.append({"name": str(row["name"]).strip(), "members": members})
    return out


# ------------------------------------------------------------------ #
# Tenants tab (§3.12-3.15; Step 4)                                    #
# ------------------------------------------------------------------ #

#: Rent-roll scalar grid; base_rent is flattened to amount+unit columns
#: (the §5.2 template convention). Nested detail (steps, CPI, free rent,
#: misc, deposit, % rent, recoveries, leasing costs) lives in the D5
#: split-pane detail editor.
LEASE_GRID_COLUMNS = ["tenant_name", "suite", "external_id", "area",
                      "lease_type", "status", "start_date", "end_date",
                      "term_months", "base_rent_amount", "base_rent_unit",
                      "upon_expiration", "market_leasing_profile", "notes"]

#: A new grid row's defaults. ``upon_expiration: vacate`` so the row is
#: valid BEFORE the user links an MLP (``market`` requires one — the §3.12
#: cross-field rule); switching to market in the grid then demands the ref.
NEW_LEASE_TEMPLATE = {
    "tenant_name": "New Tenant", "area": 1_000.0, "lease_type": "office",
    "start_date": "2026-01-01", "term_months": 60,
    "base_rent": {"amount": 0.0, "unit": "dollars_per_area_per_year"},
    "upon_expiration": "vacate",
}


def lease_grid_rows(leases: list) -> list[dict]:
    rows = []
    for lease in leases:
        row = {c: lease.get(c) for c in LEASE_GRID_COLUMNS
               if c not in ("base_rent_amount", "base_rent_unit")}
        row["base_rent_amount"] = lease["base_rent"]["amount"]
        row["base_rent_unit"] = lease["base_rent"]["unit"]
        rows.append(row)
    return rows


def apply_lease_grid_rows(leases: list, rows: list[dict]) -> list[dict]:
    """Merge scalar grid edits by row order (add = template + row; delete =
    drop), unflattening base_rent and preserving nested detail on
    survivors."""
    kept_rows = [row for row in rows if not _blank_row(row)]
    merged: list[dict] = []
    for i, row in enumerate(kept_rows):
        base = (dict(leases[i]) if i < len(leases)
                else dict(NEW_LEASE_TEMPLATE))
        for column in LEASE_GRID_COLUMNS:
            if column in ("base_rent_amount", "base_rent_unit"):
                continue
            if column in row:
                value = row[column]
                base[column] = None if _is_blank(value) else value
        rent = dict(base.get("base_rent") or {})
        if not _is_blank(row.get("base_rent_amount")):
            rent["amount"] = row["base_rent_amount"]
        if not _is_blank(row.get("base_rent_unit")):
            rent["unit"] = row["base_rent_unit"]
        base["base_rent"] = rent
        merged.append(base)
    return merged


#: Misc-item grid (the §5.2 flat columns); nested timing/inflation/limits
#: preserved by row order.
MISC_ITEM_GRID_COLUMNS = ["name", "amount", "unit", "free_rent_abates"]


def misc_items_to_rows(items: list) -> list[dict]:
    return [{c: item.get(c) for c in MISC_ITEM_GRID_COLUMNS}
            for item in items]


def apply_misc_item_rows(items: list, rows: list[dict]) -> list[dict]:
    kept = [row for row in rows if not _is_blank(row.get("name"))]
    merged = []
    for i, row in enumerate(kept):
        base = dict(items[i]) if i < len(items) else {}
        for column in MISC_ITEM_GRID_COLUMNS:
            if column in row:
                base[column] = row[column]
        base["free_rent_abates"] = bool(base.get("free_rent_abates", False))
        merged.append(base)
    return merged


ABSORPTION_GRID_COLUMNS = ["name", "total_area", "number_of_leases",
                           "area_per_lease", "start_date", "interval_months",
                           "lease_type", "market_leasing_profile",
                           "reabsorbed_from"]


def absorption_to_rows(specs: list) -> list[dict]:
    return [{c: s.get(c) for c in ABSORPTION_GRID_COLUMNS} for s in specs]


def rows_to_absorption(rows: list[dict]) -> list[dict]:
    kept = []
    for row in rows:
        if _is_blank(row.get("name")):
            continue
        kept.append({c: (None if _is_blank(row.get(c)) else row.get(c))
                     for c in ABSORPTION_GRID_COLUMNS})
    return kept


#: %-rent breakpoint layers (up to 6, spec §3.13).
BREAKPOINT_LAYER_COLUMNS = ["breakpoint_amount", "pct"]


def layers_to_rows(layers: list) -> list[dict]:
    return [{c: l.get(c) for c in BREAKPOINT_LAYER_COLUMNS} for l in layers]


def rows_to_layers(rows: list[dict]) -> list[dict]:
    return [{"breakpoint_amount": (None if _is_blank(row.get("breakpoint_amount"))
                                   else row.get("breakpoint_amount")),
             "pct": row.get("pct")}
            for row in rows if not _blank_row(row)]


#: Recovery-pool expense adjustments.
ADJUSTMENT_COLUMNS = ["expense", "action", "pct"]


def adjustments_to_rows(adjustments: list) -> list[dict]:
    return [{c: a.get(c) for c in ADJUSTMENT_COLUMNS} for a in adjustments]


def rows_to_adjustments(rows: list[dict]) -> list[dict]:
    return [{"expense": row.get("expense"),
             "action": row.get("action") or "exclude",
             "pct": row.get("pct") if not _is_blank(row.get("pct")) else 100.0}
            for row in rows if not _is_blank(row.get("expense"))]


def segments_to_generation_rows(segments, contractual_label: str,
                                speculative_label: str) -> list[dict]:
    """The D6-amendment Freeport E surface (READ-ONLY): one row per
    resolved segment of a chain, straight off ``result.segments`` — no
    engine change, pure presentation. LC / TI / renewal weight are the
    per-generation rollover economics the parked Freeport E investigation
    needs."""
    rows = []
    for segment in segments:
        speculative = (segment.speculative
                       or segment.lease.status.value == "speculative")
        if segment.lc_pct is not None:
            years = (f" (yrs {','.join(str(y) for y in segment.lc_pct_years)})"
                     if segment.lc_pct_years else "")
            lc = f"{segment.lc_pct}% of rent{years}"
        elif segment.lc_rate is not None:
            lc = f"{segment.lc_rate.amount} {segment.lc_rate.unit.value}"
        else:
            lc = ""
        ti = (f"{segment.ti.amount} {segment.ti.unit.value}"
              if segment.ti is not None else "")
        rows.append({
            "start": str(segment.start), "end": str(segment.end),
            "provenance": (speculative_label if speculative
                           else contractual_label),
            "renewal_weight": segment.renewal_weight,
            "downtime_months": segment.downtime_months,
            "free_rent_months": segment.free_rent_months,
            "initial_rent_monthly": segment.initial_rent_monthly,
            "ti": ti, "lc": lc,
        })
    return rows


# ------------------------------------------------------------------ #
# RentStep rows (MLP rent_increases; reused by later steps)           #
# ------------------------------------------------------------------ #

RENT_STEP_COLUMNS = ["month_offset", "date", "amount", "unit", "pct_increase"]


def rent_steps_to_rows(steps: Optional[list]) -> list[dict]:
    return [{k: s.get(k) for k in RENT_STEP_COLUMNS} for s in (steps or [])]


def rows_to_rent_steps(rows: list[dict]) -> Optional[list[dict]]:
    """Editor rows → RentStep dicts (blank cells → None so the schema's
    exactly-one-of validators judge them); empty grid → None."""
    kept = []
    for row in rows:
        if _blank_row(row):
            continue
        kept.append({k: (None if _is_blank(row.get(k)) else row.get(k))
                     for k in RENT_STEP_COLUMNS})
    return kept or None
