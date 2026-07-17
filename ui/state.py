"""Pure UI state helpers (Phase 5 Step 1; NEXT_STEPS_TO_PHASE5.md).

Every function here is browser-free and unit-testable: no Streamlit
import, no session state, no widgets — just the engine's public API in,
plain values out. The Streamlit layer (``ui/main.py``) is a thin renderer
over these helpers, which is what keeps the UI testable and Iron Rule 1
auditable: **this package imports the engine; the engine never imports
this package.** Zero code under ``engine/`` changes in Phase 5 (the Gate 5
git-log boundary check, baseline commit ``62617f1``).

Error surfaces follow the §5.4 intake standard set in Phase 4: plain
language, the field path, the offending value, and what a valid value
looks like — never a pydantic dump or a traceback.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from typing import Optional

from pydantic import ValidationError

from engine.calc.ledger import NOI, to_annual
from engine.calc.run import RunResult, run_property
from engine.models import (
    AreaMeasures,
    Inflation,
    PropertyInfo,
    PropertyModel,
    RentableAreaMode,
    YearRate,
)
from engine.models.io import PROPERTY_FILE_SUFFIX, load_property, save_property

#: Environment override for the properties directory (tests point this at a
#: tmp dir so AppTest flows are hermetic); default is the spec §2 layout.
PROPERTIES_DIR_ENV = "IRONCLAD_PROPERTIES_DIR"
_DEFAULT_PROPERTIES_DIR = Path(__file__).resolve().parents[1] / "data" / "properties"


def properties_dir() -> Path:
    """The directory the property selector scans (spec §2
    ``data/properties/``; env-overridable for tests). Created if absent."""
    directory = Path(os.environ.get(PROPERTIES_DIR_ENV,
                                    _DEFAULT_PROPERTIES_DIR))
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def list_property_files(directory: Path) -> list[Path]:
    """The ``.icprop.json`` files in ``directory``, sorted by name — the v1
    property selector (the spec §2 SQLite index is deferred, DEVIATIONS
    §26)."""
    return sorted(directory.glob(f"*{PROPERTY_FILE_SUFFIX}"))


def property_display_name(path: Path) -> str:
    """Selector label: the filename without the ``.icprop.json`` suffix."""
    return path.name.removesuffix(PROPERTY_FILE_SUFFIX)


def default_save_path(model: PropertyModel, directory: Path) -> Path:
    """Where Save writes a not-yet-saved property: kebab-ish slug of the
    property name in the properties directory."""
    slug = "".join(c if (c.isalnum() or c in "-_") else "-"
                   for c in model.property.name.strip().lower()).strip("-")
    return directory / f"{slug or 'property'}{PROPERTY_FILE_SUFFIX}"


def new_minimal_model(name: str) -> PropertyModel:
    """A minimal valid PropertyModel for New Property: empty rent roll, a
    fixed 10,000 SF building, zero inflation, 10-year term starting the
    first of the current month. Everything else is entered through the
    tabs (Steps 2-5)."""
    return PropertyModel(
        property=PropertyInfo(
            name=name.strip() or "New Property",
            property_type="office",
            analysis_begin=dt.date.today().replace(day=1),
            analysis_term_years=10,
        ),
        area_measures=AreaMeasures(
            property_size=10_000,
            rentable_area_mode=RentableAreaMode.fixed,
            rentable_area_fixed=10_000,
        ),
        inflation=Inflation(general_rate=[YearRate(year=1, rate=0.0)]),
        rent_roll=[],
    )


# ------------------------------------------------------------------ #
# Readable error translation (§5.4 standard — never a pydantic dump)  #
# ------------------------------------------------------------------ #

def _readable_validation_error(exc: ValidationError, source: str) -> str:
    """Translate a pydantic ValidationError into the §5.4 surface: one line
    per problem with the field path, the message, and the offending value."""
    lines = []
    for e in exc.errors():
        loc = ".".join(str(p) for p in e.get("loc", ())) or "(document)"
        got = e.get("input")
        got_text = f" (got {got!r})" if got is not None else ""
        lines.append(f"  - field '{loc}': {e['msg']}{got_text}")
    body = "\n".join(lines)
    return (f"{source} is not a valid PropertyModel "
            f"({len(exc.errors())} problem(s)):\n{body}\n"
            "Fix the value(s) and reload. Field-by-field reference: "
            "docs/SCHEMA_GUIDE.md.")


def load_model(path: Path) -> tuple[Optional[PropertyModel], Optional[str]]:
    """Load a ``.icprop.json`` file → ``(model, None)`` or ``(None, readable
    error)``. Never raises; never surfaces a traceback."""
    return load_model_from_text_source(lambda: Path(path).read_text(encoding="utf-8"),
                                       source=str(path))


def load_model_from_text(text: str, source: str
                         ) -> tuple[Optional[PropertyModel], Optional[str]]:
    """Validate uploaded JSON text (the load-JSON intake surface)."""
    return load_model_from_text_source(lambda: text, source=source)


def load_model_from_text_source(read, *, source: str
                                ) -> tuple[Optional[PropertyModel], Optional[str]]:
    try:
        text = read()
    except OSError as exc:
        return None, f"Could not read {source}: {exc}."
    try:
        json.loads(text)
    except json.JSONDecodeError as exc:
        return None, (f"{source} is not valid JSON: {exc.msg} at line "
                      f"{exc.lineno}, column {exc.colno}. A property file is "
                      "the pretty-printed JSON that Save writes "
                      "(docs/property_model.schema.json).")
    try:
        return PropertyModel.model_validate_json(text), None
    except ValidationError as exc:
        return None, _readable_validation_error(exc, source)


def save_model(model: PropertyModel, path: Path) -> Path:
    """Write the model via the engine's own writer (spec §5.1 format)."""
    return save_property(model, path)


def models_equal(a: Optional[PropertyModel], b: Optional[PropertyModel]) -> bool:
    """Full-model equality via ``model_dump()`` — the round-trip identity
    check (§25-discriminating: any changed field flips it)."""
    if a is None or b is None:
        return a is b
    return a.model_dump() == b.model_dump()


def run_model(model: PropertyModel
              ) -> tuple[Optional[RunResult], Optional[str]]:
    """Calculate → ``(result, None)`` or ``(None, readable error)``. Engine
    refusals (NotImplementedError) and invariant/validation failures
    (ValueError) already carry readable messages by project convention —
    they are passed through verbatim, framed, never as a traceback."""
    try:
        return run_property(model), None
    except NotImplementedError as exc:
        return None, f"This property uses an input the engine refuses:\n{exc}"
    except (ValueError, ValidationError) as exc:
        return None, f"The calculation could not run:\n{exc}"


# ------------------------------------------------------------------ #
# Dashboard metrics (Step 1 minimal set — read off RunResult only)    #
# ------------------------------------------------------------------ #

def dashboard_metrics(result: RunResult, model: PropertyModel) -> dict:
    """Year-1 NOI and year-1 average occupancy, read off the RunResult (the
    ledger's own annual aggregation; the run's area series). No UI-side
    math beyond the mean — the UI never recomputes the ledger."""
    annual = to_annual(result.ledger.frame,
                       model.property.analysis_begin)
    year1_noi = float(annual.loc[1, NOI])
    occupied = float(result.occupied_area.iloc[:12].mean())
    rentable = float(result.rentable_area.iloc[:12].mean())
    occupancy_pct = (occupied / rentable * 100.0) if rentable else float("nan")
    return {"year1_noi": year1_noi, "year1_occupancy_pct": occupancy_pct}


def format_currency(value: float) -> str:
    return f"${value:,.0f}"


def format_pct(value: float) -> str:
    return f"{value:.1f}%"
