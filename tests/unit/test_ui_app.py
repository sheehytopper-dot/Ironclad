"""AppTest flow tests for the Step 1 app shell (Phase 5;
app.py + ui/main.py via streamlit.testing.v1 — no browser).

Step 1 acceptance (NEXT_STEPS_TO_PHASE5.md): open a fixture → edit
nothing → Calculate → the Dashboard shows the fixture's known year-1 NOI
and occupancy; save → reload → identical model; a corrupted JSON yields
the readable error, not a stack trace. §25 discipline: the dashboard
assertions are hardcoded Clorox literals (wrong-year / UI-side-math bugs
fail them); the corrupted-file test asserts message content AND the
absence of a traceback; the default-tab test fails if D5 regresses.

The properties directory is pointed at a tmp dir via
IRONCLAD_PROPERTIES_DIR, so flows are hermetic (no repo data/ touched).
"""
import json
import shutil
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from ui import state

ROOT = Path(__file__).resolve().parents[2]
CLOROX = (ROOT / "tests" / "golden" / "clorox_northlake" /
          "clorox_northlake.icprop.json")


@pytest.fixture
def props_dir(tmp_path, monkeypatch):
    shutil.copy(CLOROX, tmp_path / "clorox.icprop.json")
    monkeypatch.setenv(state.PROPERTIES_DIR_ENV, str(tmp_path))
    return tmp_path


def _app():
    # generous timeout: Calculate runs the full Clorox engine pass
    return AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)


def _open_property(at, name):
    at.selectbox(key="property_select").set_value(name)
    at.button(key="open_btn").click()
    at.run()


class TestShell:
    def test_dashboard_is_default_active_and_order_preserved(self, props_dir):
        at = _app()
        at.run()
        nav = at.radio(key="active_tab")
        assert nav.value == "Dashboard"                    # D5 default
        assert list(nav.options) == [
            "Property", "Market", "Revenues", "Expenses", "Tenants",
            "Investment", "Valuation", "Reports", "Dashboard", "Audit"]
        assert not at.exception

    def test_open_calculate_shows_known_clorox_metrics(self, props_dir):
        at = _app()
        at.run()
        _open_property(at, "clorox")
        assert not at.exception
        at.button(key="calc_btn").click()
        at.run()
        assert not at.exception
        values = {m.label: m.value for m in at.metric}
        # the fixture's known engine outputs, formatted (§25 literals)
        assert values["Year-1 NOI"] == "$2,596,319"
        assert values["Year-1 Occupancy"] == "100.0%"

    def test_save_reload_identity(self, props_dir):
        at = _app()
        at.run()
        _open_property(at, "clorox")
        original, error = state.load_model(props_dir / "clorox.icprop.json")
        assert error is None
        at.button(key="save_btn").click()
        at.run()
        assert not at.exception
        reloaded, error = state.load_model(props_dir / "clorox.icprop.json")
        assert error is None
        assert state.models_equal(original, reloaded)      # identity holds

    def test_new_property_pipe(self, props_dir):
        at = _app()
        at.run()
        at.text_input(key="new_name").set_value("Fresh Deal")
        at.button(key="create_btn").click()
        at.run()
        at.button(key="calc_btn").click()
        at.run()
        assert not at.exception
        values = {m.label: m.value for m in at.metric}
        assert values["Year-1 NOI"] == "$0"                # empty rent roll
        assert values["Year-1 Occupancy"] == "0.0%"


class TestReadableErrorsInApp:
    def test_corrupted_property_file_readable_not_traceback(self, props_dir):
        doc = json.loads(CLOROX.read_text(encoding="utf-8"))
        doc["property"]["analysis_term_years"] = 0
        (props_dir / "broken.icprop.json").write_text(json.dumps(doc),
                                                      encoding="utf-8")
        at = _app()
        at.run()
        _open_property(at, "broken")
        assert not at.exception                            # app never crashes
        errors = " ".join(e.value for e in at.error)
        assert "property.analysis_term_years" in errors    # field path
        assert "Traceback" not in errors
        assert "pydantic" not in errors.lower()

    def test_engine_refusal_renders_readable_panel(self, props_dir):
        from engine.models import ExpenseItem, ExpenseUnit
        model, _ = state.load_model(CLOROX)
        mutated = model.model_copy(deep=True)
        mutated.expenses.append(ExpenseItem(
            name="Weird", amount=1.0, unit=ExpenseUnit.pct_of_account,
            account_ref="CAM"))
        state.save_model(mutated, props_dir / "refusal.icprop.json")
        at = _app()
        at.run()
        _open_property(at, "refusal")
        at.button(key="calc_btn").click()
        at.run()
        assert not at.exception
        errors = " ".join(e.value for e in at.error)
        assert "refuses" in errors and "pct_of_account" in errors
        assert "Traceback" not in errors
