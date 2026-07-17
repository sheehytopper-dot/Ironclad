"""Unit tests for the pure UI state helpers (Phase 5 Step 1;
ui/state.py — browser-free by design, NEXT_STEPS_TO_PHASE5.md).

DEVIATIONS §25 discipline: every check runs where the wrong behavior
differs from the right one — the model-identity check is flipped by a
single field edit; the dashboard literals are the Clorox fixture's known
engine outputs (a wrong year/frame read fails them); the readable-error
tests assert both presence of the §5.4 content AND absence of the raw
pydantic/traceback surface.
"""
import json
from pathlib import Path

import pytest

from engine.calc.ledger import NOI, to_annual
from engine.models import ExpenseItem, ExpenseUnit
from ui import state

CLOROX = (Path(__file__).resolve().parents[1] / "golden" /
          "clorox_northlake" / "clorox_northlake.icprop.json")


class TestNewMinimalModel:
    def test_validates_and_runs(self):
        model = state.new_minimal_model("Test Property")
        assert model.property.name == "Test Property"
        result, error = state.run_model(model)
        assert error is None and result is not None
        metrics = state.dashboard_metrics(result, model)
        # empty rent roll: zero NOI, zero occupancy — not NaN, not a crash
        assert metrics["year1_noi"] == 0.0
        assert metrics["year1_occupancy_pct"] == 0.0

    def test_blank_name_gets_default(self):
        assert state.new_minimal_model("  ").property.name == "New Property"


class TestPropertyFiles:
    def test_list_filters_and_sorts(self, tmp_path):
        (tmp_path / "b.icprop.json").write_text("{}")
        (tmp_path / "a.icprop.json").write_text("{}")
        (tmp_path / "notes.txt").write_text("x")
        (tmp_path / "c.json").write_text("{}")  # wrong suffix — excluded
        files = state.list_property_files(tmp_path)
        assert [f.name for f in files] == ["a.icprop.json", "b.icprop.json"]
        assert state.property_display_name(files[0]) == "a"

    def test_default_save_path_slug(self, tmp_path):
        model = state.new_minimal_model("Vista Tower #2")
        path = state.default_save_path(model, tmp_path)
        assert path.parent == tmp_path
        assert path.name == "vista-tower--2.icprop.json"


class TestRoundTripIdentity:
    def test_save_load_identity_and_discrimination(self, tmp_path):
        original, error = state.load_model(CLOROX)
        assert error is None
        saved = state.save_model(original, tmp_path / "copy.icprop.json")
        reloaded, error = state.load_model(saved)
        assert error is None
        assert state.models_equal(original, reloaded)          # identity
        # §25 discrimination: one edited field flips the identity check
        mutated = reloaded.model_copy(deep=True)
        mutated.rent_roll[0].area += 1.0
        assert not state.models_equal(original, mutated)

    def test_none_handling(self):
        model, _ = state.load_model(CLOROX)
        assert not state.models_equal(model, None)
        assert not state.models_equal(None, model)
        assert state.models_equal(None, None)


class TestReadableErrors:
    """§5.4: field path + offending value + a fix; never a pydantic dump."""

    def _assert_clean_surface(self, message):
        assert "Traceback" not in message
        assert "pydantic" not in message.lower()
        assert "validation error for" not in message  # the raw header

    def test_not_json(self):
        model, error = state.load_model_from_text("{not json", "upload.json")
        assert model is None
        assert "not valid JSON" in error and "line 1" in error
        self._assert_clean_surface(error)

    def test_schema_invalid_names_field_and_value(self):
        doc = json.loads(CLOROX.read_text(encoding="utf-8"))
        doc["property"]["analysis_term_years"] = 0
        model, error = state.load_model_from_text(json.dumps(doc), "upload.json")
        assert model is None
        assert "property.analysis_term_years" in error  # field path
        assert "0" in error                             # offending value
        assert "SCHEMA_GUIDE" in error                  # where to look
        self._assert_clean_surface(error)

    def test_missing_file(self, tmp_path):
        model, error = state.load_model(tmp_path / "ghost.icprop.json")
        assert model is None and "Could not read" in error
        self._assert_clean_surface(error)

    def test_engine_refusal_is_readable(self):
        model, _ = state.load_model(CLOROX)
        mutated = model.model_copy(deep=True)
        mutated.expenses.append(ExpenseItem(
            name="Weird", amount=1.0, unit=ExpenseUnit.pct_of_account,
            account_ref="CAM"))
        result, error = state.run_model(mutated)
        assert result is None
        assert "refuses" in error and "pct_of_account" in error
        self._assert_clean_surface(error)


class TestDashboardMetrics:
    def test_clorox_known_values(self):
        """The Clorox fixture's engine outputs, hardcoded (§25: a wrong
        year, wrong frame, or UI-side recomputation fails these)."""
        model, _ = state.load_model(CLOROX)
        result, error = state.run_model(model)
        assert error is None
        metrics = state.dashboard_metrics(result, model)
        assert metrics["year1_noi"] == pytest.approx(2_596_319.40, abs=0.01)
        assert metrics["year1_occupancy_pct"] == pytest.approx(100.0, abs=1e-9)
        # and it equals the ledger's own annual view (no UI-side math)
        annual = to_annual(result.ledger.frame, model.property.analysis_begin)
        assert metrics["year1_noi"] == pytest.approx(float(annual.loc[1, NOI]))

    def test_formatting(self):
        assert state.format_currency(2_596_319.40) == "$2,596,319"
        assert state.format_pct(100.0) == "100.0%"
