"""The IronClad API (NEXT_STEPS_WEB_FRONTEND.md §3; rollout step 2).

Thin serializers over EXISTING engine/report/export/intake functions —
**the API computes nothing**. It imports the engine and the pure
browser-free ``ui/`` modules (Step 0 W7); the engine imports neither
(Iron Rule 1 extended: `engine/` frozen, baseline ``62617f1``).

Run locally (Step 0 W2/W3 — single-user, localhost only):

    uvicorn api.main:app --host 127.0.0.1 --port 8000

The RunResult is cached SERVER-SIDE per property (Step 0 W4 — lazy
serialization: each endpoint reads the cache and sends only what its
screen needs) and **invalidated whenever the property is edited via
PUT** — the same stale-result discipline as the Streamlit session state.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import FastAPI, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import ValidationError

from engine.export import build_package, export_report
from engine.intake import RentRollImportError, import_rent_roll
from engine.models import PropertyModel
from engine.models.io import PROPERTY_FILE_SUFFIX, save_property
from engine.reports import Period, Unit, recovery_audit_report
from ui import reports_registry as registry
from ui import state
from ui.tabs import audit_tab
from api import serialize

app = FastAPI(title="IronClad API", docs_url="/api/docs",
              openapi_url="/api/openapi.json")

#: Server-side run cache: property name → (model, RunResult). PUT and
#: recalculation are the only writers; PUT invalidates.
_RUNS: dict[str, tuple] = {}


def _error(status: int, summary: str, problems=None) -> JSONResponse:
    return JSONResponse(status_code=status,
                        content=serialize.error_body(summary, problems))


def _path_for(name: str) -> Path:
    return state.properties_dir() / f"{name}{PROPERTY_FILE_SUFFIX}"


def _load(name: str):
    """(model, None) or (None, JSONResponse) for a property on disk."""
    path = _path_for(name)
    if not path.exists():
        return None, _error(404, f"No property named {name!r} in "
                                 f"{state.properties_dir()}.")
    model, error = state.load_model(path)
    if error:
        return None, _error(422, error)
    return model, None


def _cached(name: str):
    """(model, result, None) or (None, None, JSONResponse)."""
    if name not in _RUNS:
        return None, None, _error(
            409, f"Property {name!r} has no calculation yet — POST "
                 f"/api/calculate/{name} first (results are invalidated "
                 "by every edit).")
    model, result = _RUNS[name]
    return model, result, None


def _benchmark_csv_for(name: str):
    """The Benchmark #24 CSV for ``name``. The golden convention
    (``expected_annual_cash_flow.csv`` beside the JSON) assumes ONE
    property per directory — ``data/properties/`` is flat, so a shared
    directory CSV would silently benchmark every property against the
    same numbers. Here: a per-name CSV
    (``<name>.expected_annual_cash_flow.csv``) wins; the bare
    directory-level CSV counts only when the directory holds exactly one
    property."""
    per_name = (state.properties_dir()
                / f"{name}.{registry.BENCHMARK_CSV_NAME}")
    if per_name.exists():
        return per_name
    shared = registry.find_benchmark_csv(_path_for(name))
    if shared is not None and len(
            state.list_property_files(state.properties_dir())) == 1:
        return shared
    return None


# ------------------------------------------------------------------ #
# Properties                                                          #
# ------------------------------------------------------------------ #

@app.get("/api/properties")
def list_properties():
    files = state.list_property_files(state.properties_dir())
    return {"properties": [{"name": state.property_display_name(p),
                            "path": str(p)} for p in files]}


@app.get("/api/properties/{name}")
def get_property(name: str):
    model, failure = _load(name)
    if failure:
        return failure
    return {"name": name, "document": model.model_dump(mode="json")}


@app.put("/api/properties/{name}")
def put_property(name: str, document: dict):
    """Whole-document revalidation (the ``updated_model`` funnel
    semantics), then save; the cached RunResult is INVALIDATED."""
    try:
        model = PropertyModel.model_validate(document)
    except ValidationError as exc:
        return JSONResponse(
            status_code=422,
            content=serialize.validation_error_body(exc, "The document"))
    path = save_property(model, _path_for(name))
    _RUNS.pop(name, None)                    # every edit invalidates
    return {"name": name, "saved": str(path), "run_invalidated": True}


# ------------------------------------------------------------------ #
# Intake                                                              #
# ------------------------------------------------------------------ #

@app.post("/api/import/rent-roll")
async def import_rent_roll_endpoint(file: UploadFile):
    """The §5.2 template import: Contractual rows → leases;
    ``ImportResult.notes`` (the ignored-Speculative report) preserved —
    never a silent skip. Applying the leases to a property is the
    front-end's PUT."""
    with tempfile.NamedTemporaryFile(suffix=".xlsx",
                                     delete=False) as handle:
        handle.write(await file.read())
        temp_path = Path(handle.name)
    try:
        imported = import_rent_roll(temp_path)
    except RentRollImportError as exc:
        return _error(422, str(exc))         # the Step-7 text, verbatim
    finally:
        temp_path.unlink(missing_ok=True)
    return {"leases": [l.model_dump(mode="json") for l in imported.leases],
            "notes": list(imported.notes)}


# ------------------------------------------------------------------ #
# Calculate + the server-side cache                                   #
# ------------------------------------------------------------------ #

@app.post("/api/calculate/{name}")
def calculate(name: str):
    model, failure = _load(name)
    if failure:
        return failure
    result, error = state.run_model(model)
    if error:
        return _error(422, error)            # refusals/invariants verbatim
    _RUNS[name] = (model, result)
    metrics = state.dashboard_metrics(result, model)
    return serialize.jsonable({
        "name": name,
        "summary": {"year1_noi": metrics["year1_noi"],
                    "year1_occupancy_pct": metrics["year1_occupancy_pct"],
                    "months": len(result.months)},
        "applicability": {
            "valuation": result.valuation is not None,
            "sensitivity": result.sensitivity is not None,
            "loans": bool(result.loan_schedules),
            "resale": result.resale is not None,
            "benchmark_csv": _benchmark_csv_for(name) is not None,
        },
    })


# ------------------------------------------------------------------ #
# Reports                                                             #
# ------------------------------------------------------------------ #

def _entries_for(name: str, model, result):
    csv_path = _benchmark_csv_for(name)
    return registry.applicable_entries(result, model, csv_path), csv_path


@app.get("/api/reports")
def list_reports(name: str):
    model, result, failure = _cached(name)
    if failure:
        return failure
    entries, _csv = _entries_for(name, model, result)
    return {"reports": [{
        "key": serialize.report_key(entry.label), "label": entry.label,
        "number": entry.number, "supports_unit": entry.supports_unit,
        "supports_period": entry.supports_period, "note": entry.note,
    } for entry in entries]}


@app.get("/api/reports/{key}")
def get_report(key: str, name: str, unit: str = "total",
               period: str = "fiscal", contractual_only: bool = False,
               loan_index: int = 0):
    model, result, failure = _cached(name)
    if failure:
        return failure
    entries, csv_path = _entries_for(name, model, result)
    entry = next((e for e in entries
                  if serialize.report_key(e.label) == key), None)
    if entry is None:
        keys = ", ".join(serialize.report_key(e.label) for e in entries)
        return _error(404, f"No applicable report {key!r} for {name!r}. "
                           f"Available: {keys}.")
    try:
        unit_value, period_value = Unit(unit), Period(period)
    except ValueError as exc:
        return _error(422, f"Invalid unit/period: {exc}. Units: "
                           f"{[u.value for u in Unit]}; periods: "
                           f"{[p.value for p in Period]}.")
    options = {"contractual_only": contractual_only,
               "loan_index": loan_index}
    if entry.number == 24:
        options["benchmark_csv"] = csv_path
    report = registry.build_entry(entry, result, model, unit=unit_value,
                                  period=period_value, options=options)
    return serialize.report_payload(report)


# ------------------------------------------------------------------ #
# Audit drill-down + the two D6 panels                                #
# ------------------------------------------------------------------ #

@app.get("/api/audit/composition")
def audit_composition(name: str, account: str, month: str):
    model, result, failure = _cached(name)
    if failure:
        return failure
    if account not in result.ledger.frame.columns:
        return _error(404, f"No ledger account {account!r}.")
    rows, caption = audit_tab.audit_composition(result, model, account,
                                                month)
    return {"caption": caption,
            "rows": serialize.frame_payload(rows)
            if rows is not None else None}


@app.get("/api/audit/gv-basis")
def gv_basis(name: str, month: str):
    """The Freeport B inspection surface over HTTP."""
    model, result, failure = _cached(name)
    if failure:
        return failure
    rows, summary = audit_tab.gv_basis_rows(result, model, month)
    return {"rows": serialize.frame_payload(rows),
            "summary": serialize.jsonable(summary)}


@app.get("/api/audit/recovery-drill")
def recovery_drill(name: str, tenant: str = "", segment_start: str = "",
                   month: str = ""):
    """The Cedar Alt B inspection surface over HTTP; with no filters it
    also returns the filter options."""
    model, result, failure = _cached(name)
    if failure:
        return failure
    frame = recovery_audit_report(result).frame
    tenants, starts = audit_tab.recovery_drill_options(result)
    drilled = audit_tab.filter_recovery_audit(
        frame, tenant=tenant or None,
        segment_start=segment_start or None, month=month or None)
    return {"tenants": tenants, "segment_starts": starts,
            "rows": serialize.frame_payload(drilled)}


# ------------------------------------------------------------------ #
# Exports (the Phase 4 machinery — nothing rewritten)                 #
# ------------------------------------------------------------------ #

_XLSX = ("application/vnd.openxmlformats-officedocument"
         ".spreadsheetml.sheet")


@app.get("/api/export/package")
def export_package(name: str):
    model, result, failure = _cached(name)
    if failure:
        return failure
    path = Path(tempfile.mkdtemp()) / f"{name}-package.xlsx"
    build_package(result, model, path=path)
    return FileResponse(path, media_type=_XLSX, filename=path.name)


@app.get("/api/export/report/{key}")
def export_report_endpoint(key: str, name: str, unit: str = "total",
                           period: str = "fiscal"):
    model, result, failure = _cached(name)
    if failure:
        return failure
    entries, csv_path = _entries_for(name, model, result)
    entry = next((e for e in entries
                  if serialize.report_key(e.label) == key), None)
    if entry is None:
        return _error(404, f"No applicable report {key!r} for {name!r}.")
    options = {"benchmark_csv": csv_path} if entry.number == 24 else {}
    report = registry.build_entry(entry, result, model, unit=Unit(unit),
                                  period=Period(period), options=options)
    path = Path(tempfile.mkdtemp()) / f"{name}-{key}.xlsx"
    export_report(report, path=path)         # the Phase 4 exporter
    return FileResponse(path, media_type=_XLSX, filename=path.name)
