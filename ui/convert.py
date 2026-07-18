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
