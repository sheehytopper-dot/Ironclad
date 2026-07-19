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


class TestStep2TabFlows:
    """Step 2 AppTest flows (additions 2026-07-17; nothing removed): the
    Property tab edits the model THROUGH the session (result invalidated),
    errors render readably, and the Market tab renders a real golden with
    the D2 read-only notes. Grid (data_editor) depth lives in the pure
    tests — AppTest cannot drive data_editor."""

    def test_property_edit_updates_model_and_invalidates_result(self,
                                                                props_dir):
        at = _app()
        at.run()
        _open_property(at, "clorox")
        at.button(key="calc_btn").click()
        at.run()
        assert at.session_state.result is not None
        rev = at.session_state.model_rev
        at.radio(key="active_tab").set_value("Property")
        at.run()
        at.text_input(key=f"pi_name_{rev}").set_value("Clorox Renamed")
        at.button(key=f"pi_apply_{rev}").click()
        at.run()
        assert not at.exception
        assert at.session_state.model.property.name == "Clorox Renamed"
        assert at.session_state.result is None          # edit invalidated it

    def test_property_bad_term_readable_error_model_unchanged(self,
                                                              props_dir):
        at = _app()
        at.run()
        _open_property(at, "clorox")
        rev = at.session_state.model_rev
        at.radio(key="active_tab").set_value("Property")
        at.run()
        at.number_input(key=f"pi_term_{rev}").set_value(0)
        at.button(key=f"pi_apply_{rev}").click()
        at.run()
        assert not at.exception
        errors = " ".join(e.value for e in at.error)
        assert "property.analysis_term_years" in errors
        assert "Traceback" not in errors
        assert at.session_state.model.property.analysis_term_years == 5

    def test_market_tab_renders_freeport_with_readonly_notes(self, props_dir):
        shutil.copy(ROOT / "tests" / "golden" / "freeport" /
                    "freeport.icprop.json", props_dir / "freeport.icprop.json")
        at = _app()
        at.run()
        _open_property(at, "freeport")
        at.radio(key="active_tab").set_value("Market")
        at.run()
        assert not at.exception
        warnings = " ".join(w.value for w in at.warning)
        assert "TI/LC categories" in warnings           # D2 read-only note
        captions = " ".join(c.value for c in at.caption)
        assert "per lease" in captions                  # the CPI pointer


class TestStep3TabFlows:
    """Step 3 AppTest flows (additions 2026-07-17; nothing removed): the
    fee edit drives the WIDGET path end-to-end through Calculate (the
    fixed-point literals land in session_state.result), and the Revenues
    tab renders a real golden. Grid depth lives in the pure tests."""

    def test_fee_edit_via_widgets_recalculates_fixed_point(self, props_dir):
        at = _app()
        at.run()
        _open_property(at, "clorox")
        rev = at.session_state.model_rev
        at.radio(key="active_tab").set_value("Expenses")
        at.run()
        # pick the Management Fee (model index 2) in the detail editor
        at.selectbox(key=f"exp_pick_{rev}").set_value("2: Management Fee")
        at.run()
        at.number_input(key=f"exp_2_{rev}_amt").set_value(5.0)
        at.button(key=f"exp_2_{rev}_apply").click()
        at.run()
        assert not at.exception
        assert at.session_state.model.expenses[2].amount == 5.0
        assert at.session_state.result is None           # edit invalidated
        at.button(key="calc_btn").click()
        at.run()
        assert not at.exception
        result = at.session_state.result
        assert result is not None
        # the 5% fixed-point literal, reached through the WIDGET path
        fee = float(next(s for item, s in result.expense_series
                         if item.name == "Management Fee").iloc[:12].sum())
        assert fee == pytest.approx(200_497.09, abs=0.01)

    def test_revenues_tab_renders_freeport(self, props_dir):
        shutil.copy(ROOT / "tests" / "golden" / "freeport" /
                    "freeport.icprop.json", props_dir / "freeport.icprop.json")
        at = _app()
        at.run()
        _open_property(at, "freeport")
        at.radio(key="active_tab").set_value("Revenues")
        at.run()
        assert not at.exception


class TestStep4TabFlows:
    """Step 4 AppTest flows (additions 2026-07-18; nothing removed): the
    Tenants tab renders a real golden with the split pane, the
    rollover-generations panel shows the Freeport E literals after
    Calculate, and the import-by-path surface lands the Contractual subset
    with the Speculative note displayed. Grid depth lives in the pure
    tests."""

    def _open_freeport(self, at, props_dir):
        shutil.copy(ROOT / "tests" / "golden" / "freeport" /
                    "freeport.icprop.json", props_dir / "freeport.icprop.json")
        at.run()
        _open_property(at, "freeport")

    def test_tenants_renders_freeport_split_pane(self, props_dir):
        at = _app()
        self._open_freeport(at, props_dir)
        at.radio(key="active_tab").set_value("Tenants")
        at.run()
        assert not at.exception
        # pre-Calculate, the generations panel prompts instead of guessing
        infos = " ".join(i.value for i in at.info)
        assert "Calculate to view" in infos

    def test_generations_panel_shows_freeport_e_literals(self, props_dir):
        at = _app()
        self._open_freeport(at, props_dir)
        at.button(key="calc_btn").click()
        at.run()
        rev = at.session_state.model_rev
        at.radio(key="active_tab").set_value("Tenants")
        at.run()
        at.selectbox(key=f"ld_pick_{rev}").set_value("2: Aqore LLC")
        at.run()
        assert not at.exception
        # data_editor grids register as dataframes too — the generations
        # panel is the one carrying the provenance column
        frames = [f for f in at.dataframe
                  if "provenance" in list(f.value.columns)]
        assert frames, "the generations panel dataframe did not render"
        rows = frames[0].value
        # the Freeport E literals through the WIDGET path (§25)
        speculative = [r for r in list(rows.to_dict("records"))
                       if r["provenance"] == "Speculative"]
        assert len(speculative) == 2
        assert all(r["lc"] == "6.75% of rent" for r in speculative)
        assert all(r["renewal_weight"] == 0.75 for r in speculative)

    def test_import_by_path_lands_contractual_with_note(self, props_dir,
                                                        tmp_path):
        from engine.calc.run import run_property
        from engine.export import export_rent_roll
        from engine.models.io import load_property
        freeport = load_property(ROOT / "tests" / "golden" / "freeport" /
                                 "freeport.icprop.json")
        template = tmp_path / "template.xlsx"
        export_rent_roll(run_property(freeport), path=template)

        at = _app()
        self._open_freeport(at, props_dir)
        rev = at.session_state.model_rev
        at.radio(key="active_tab").set_value("Tenants")
        at.run()
        at.text_input(key=f"imp_path_{rev}").set_value(str(template))
        at.button(key=f"imp_btn_{rev}").click()
        at.run()
        assert not at.exception
        infos = " ".join(i.value for i in at.info)
        assert "speculative" in infos and "ignored" in infos   # the note
        assert len(at.session_state.model.rent_roll) == 29     # Contractual


class TestStep5TabFlows:
    """Step 5 AppTest flows (additions 2026-07-19; nothing removed): the
    Investment + Valuation tabs render an engineered demo (no golden has
    purchase/loans/valuation), and a selling-costs edit through the WIDGET
    path recalculates to the 0%-selling literal. Grid depth lives in the
    pure tests."""

    def _save_demo(self, props_dir):
        import datetime as dt
        from engine.models import (AreaMeasures, ExpenseItem, ExpenseUnit,
                                   Inflation, Lease, MoneyRate, MoneyUnit,
                                   PropertyInfo, PropertyModel,
                                   RentableAreaMode, UponExpiration, YearRate)
        from ui.tabs import investment_tab, valuation_tab
        psf = MoneyUnit.dollars_per_area_per_year
        begin = dt.date(2026, 1, 1)
        lease = Lease(tenant_name="T", area=12_000, lease_type="industrial",
                      start_date=begin, term_months=240,
                      base_rent=MoneyRate(amount=10.0, unit=psf),
                      upon_expiration=UponExpiration.vacate)
        model = PropertyModel(
            property=PropertyInfo(name="Demo", property_type="industrial",
                                  analysis_begin=begin,
                                  analysis_term_years=5),
            area_measures=AreaMeasures(
                property_size=12_000,
                rentable_area_mode=RentableAreaMode.fixed,
                rentable_area_fixed=12_000),
            inflation=Inflation(general_rate=[YearRate(year=1, rate=0.0)]),
            rent_roll=[lease],
            expenses=[ExpenseItem(name="OpEx", amount=20_000.0,
                                  unit=ExpenseUnit.dollars_per_year,
                                  recoverable=False)])
        model, _ = investment_tab.apply_loan_grid(model, [
            {"name": "Mortgage", "amount_value": 1_000_000.0,
             "amount_basis": "amount", "rate": 6.0, "term_months": 360,
             "amortization": "fully_amortizing"}])
        model, _ = valuation_tab.apply_valuation(model, {
            "discount_rate": 8.0, "discount_method": "annual",
            "period_convention": "end_of_period", "pv_start": None,
            "direct_cap": None,
            "resale": {"method": "cap_noi_current_year",
                       "exit_cap_rate": 8.0, "resale_date": None,
                       "apply_resale_to_cash_flow": True,
                       "selling_costs_pct": 3.0, "adjustment_amounts": [],
                       "noi_adjustments": {"exclude_capital": True,
                                           "stabilize_occupancy": None}},
            "sensitivity_intervals": {"discount_rate_step": 1.0,
                                      "cap_rate_step": 1.0, "count": 5}})
        state.save_model(model, props_dir / "demo.icprop.json")

    def test_investment_and_valuation_render_demo(self, props_dir):
        self._save_demo(props_dir)
        at = _app()
        at.run()
        _open_property(at, "demo")
        at.radio(key="active_tab").set_value("Investment")
        at.run()
        assert not at.exception
        at.radio(key="active_tab").set_value("Valuation")
        at.run()
        assert not at.exception

    def test_selling_costs_edit_via_widgets_recalculates(self, props_dir):
        self._save_demo(props_dir)
        at = _app()
        at.run()
        _open_property(at, "demo")
        rev = at.session_state.model_rev
        at.radio(key="active_tab").set_value("Valuation")
        at.run()
        at.number_input(key=f"val_res_{rev}_selling").set_value(0.0)
        at.button(key=f"val_apply_{rev}").click()
        at.run()
        assert not at.exception
        assert at.session_state.result is None          # edit invalidated
        at.button(key="calc_btn").click()
        at.run()
        assert not at.exception
        result = at.session_state.result
        # 0% selling on the 1,250,000 gross → net == gross (§25 literal;
        # the 3% baseline was 1,212,500)
        assert result.resale.net_unleveraged == pytest.approx(1_250_000.0,
                                                              abs=0.01)


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
