"""Pure serialization helpers for the API (NEXT_STEPS_WEB_FRONTEND.md §3).

The two build-notes folded in here:

1. **NaN → null.** Report frames legitimately contain NaN (blank
   valuation metrics, zero-area per-SF cells). Literal ``NaN`` is invalid
   JSON — the browser's ``JSON.parse`` throws on it — so every payload is
   sanitized recursively (NaN/±inf → ``None``); the front-end renders
   null as blank.
2. **Full precision.** Frames serialize via split-orient
   columns/index/data with raw float64 values — the API NEVER rounds;
   display formatting is the front-end's job (the Tier-1 rules move
   there).

Errors are the §5.4 readable surface as STRUCTURED JSON
(``{"error": {"summary", "problems": [{"field", "message", "got"}],
"reference"}}``) — never a pydantic dump or a traceback; engine refusals
go verbatim into ``summary``.
"""
from __future__ import annotations

import math
import numbers
import re
from typing import Optional

import pandas as pd
from pydantic import ValidationError

from engine.reports import Report

SCHEMA_REFERENCE = "docs/SCHEMA_GUIDE.md"

#: meta.extra keys forwarded to the front-end (JSON-safe, screen-relevant:
#: the Cash Flow tree, the benchmark counts, the provenance scopes).
META_EXTRA_KEYS = ("tree", "miss_count", "skipped_accounts",
                   "included_statuses", "distinct_demised_area",
                   "tolerance")


def jsonable(value):
    """Recursively make ``value`` strict-JSON-safe: NaN/±inf → None;
    numpy scalars → Python; Periods/timestamps/enums → str."""
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, numbers.Integral):
        return int(value)
    if isinstance(value, numbers.Real):
        value = float(value)
        return None if (math.isnan(value) or math.isinf(value)) else value
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable(item) for item in value]
    return str(value)          # Period, Timestamp, enum, Path, date …


def frame_payload(frame: pd.DataFrame) -> dict:
    """Split-orient full-precision frame JSON (NaN → null)."""
    return {
        "columns": [jsonable(column) for column in frame.columns],
        "index": [jsonable(label) for label in frame.index],
        "data": [[jsonable(cell) for cell in row]
                 for row in frame.itertuples(index=False, name=None)],
    }


def report_payload(report: Report) -> dict:
    """A Report over the wire: the builder's frame (full precision) + the
    meta the front-end needs."""
    meta = report.meta
    extra = {key: jsonable(meta.extra[key]) for key in META_EXTRA_KEYS
             if key in meta.extra}
    return {
        "frame": frame_payload(report.frame),
        "meta": {
            "name": meta.name, "number": meta.number,
            "unit": getattr(meta.unit, "value", None),
            "period": getattr(meta.period, "value", None),
            "monetary": meta.monetary, "citation": meta.citation,
            "extra": extra,
        },
    }


# ------------------------------------------------------------------ #
# The §5.4 structured readable-error surface                          #
# ------------------------------------------------------------------ #

def error_body(summary: str, problems: Optional[list] = None) -> dict:
    return {"error": {"summary": summary, "problems": problems or [],
                      "reference": SCHEMA_REFERENCE}}


def validation_error_body(exc: ValidationError, source: str) -> dict:
    """The structured twin of ui.state's readable translation: one problem
    per pydantic error with the field path and the offending value (repr
    truncated at 120 chars — a document-level validator reports the whole
    model as its input, and dumping that would itself violate §5.4)."""
    problems = []
    for e in exc.errors():
        field = ".".join(str(p) for p in e.get("loc", ())) or "(document)"
        got = e.get("input")
        got_repr = repr(got) if got is not None else ""
        problems.append({
            "field": field,
            "message": e["msg"],
            "got": got_repr if 0 < len(got_repr) <= 120 else None,
        })
    summary = (f"{source} is not a valid PropertyModel "
               f"({len(problems)} problem(s)). Fix the value(s) and retry.")
    return error_body(summary, problems)


def report_key(label: str) -> str:
    """A stable URL slug for a registry entry label (exposed by
    ``GET /api/reports`` so the front-end never guesses)."""
    slug = label.lower().replace("&", "and")
    return re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
