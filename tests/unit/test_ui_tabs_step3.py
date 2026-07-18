"""Pure tests for the Step 3 Revenues + Expenses tab commit functions
(ui/tabs/revenues_tab.py, ui/tabs/expenses_tab.py, ui/convert.py additions
— Phase 5; no browser).

Acceptance (NEXT_STEPS_TO_PHASE5.md Step 3, advisor directive):
1. Round-trip + §25 discrimination on the REAL goldens (one-field edits
   flip the identity check; edited models save→reload identically);
   per-cell errors readable (field path + offending value, no
   pydantic/Traceback).
2. THE FIXED-POINT END-TO-END CHECK: editing Clorox's %-of-EGR management
   fee 3% → 5% through the tab's own apply function and recalculating hits
   HARD LITERALS — fee 200,497.09 / EGR 4,009,941.72 (vs the 3% baseline
   117,817.88 / 3,927,262.51) with fee = exactly 5% of final EGR. NOI stays
   2,596,319.40 under BOTH (the fee is recoverable — a pass-through), so
   NOI is deliberately asserted as the invariant and the fee/EGR literals
   are the discriminators (§25: a wrong-behavior path fails them).
3. The engine-refused ``pct_of_account`` rows: excluded from the editable
   grid, preserved verbatim through unrelated applies, detail edits
   refused readably.
"""
from pathlib import Path

import pytest

from engine.calc.ledger import EGR, NOI, to_annual
from ui import convert, state
from ui.tabs import expenses_tab, revenues_tab

GOLDEN = Path(__file__).resolve().parents[1] / "golden"
CLOROX = GOLDEN / "clorox_northlake" / "clorox_northlake.icprop.json"
FREEPORT = GOLDEN / "freeport" / "freeport.icprop.json"

#: Clorox fixed-point literals (computed from the engine once; §25 anchors).
FEE_3PCT, EGR_3PCT = 117_817.88, 3_927_262.51
FEE_5PCT, EGR_5PCT = 200_497.09, 4_009_941.72
NOI_BOTH = 2_596_319.40          # recoverable fee → NOI pass-through


@pytest.fixture(scope="module")
def clorox():
    model, error = state.load_model(CLOROX)
    assert error is None
    return model


@pytest.fixture(scope="module")
def freeport():
    model, error = state.load_model(FREEPORT)
    assert error is None
    return model


def _assert_edit_roundtrips_and_discriminates(original, edited, tmp_path):
    assert edited is not None
    assert not state.models_equal(original, edited)
    saved = state.save_model(edited, tmp_path / "edited.icprop.json")
    reloaded, error = state.load_model(saved)
    assert error is None
    assert state.models_equal(edited, reloaded)


def _year1_fee_egr_noi(result, model):
    annual = to_annual(result.ledger.frame, model.property.analysis_begin)
    fee = float(next(s for item, s in result.expense_series
                     if item.name == "Management Fee").iloc[:12].sum())
    return fee, float(annual.loc[1, EGR]), float(annual.loc[1, NOI])


class TestFixedPointEndToEnd:
    def test_baseline_3pct_literals(self, clorox):
        result, error = state.run_model(clorox)
        assert error is None
        fee, egr, noi = _year1_fee_egr_noi(result, clorox)
        assert fee == pytest.approx(FEE_3PCT, abs=0.01)
        assert egr == pytest.approx(EGR_3PCT, abs=0.01)
        assert noi == pytest.approx(NOI_BOTH, abs=0.01)
        assert fee == pytest.approx(0.03 * egr, abs=1e-6)   # 3% of FINAL EGR

    def test_fee_edit_recalculates_through_the_fixed_point(self, clorox,
                                                           tmp_path):
        """The advisor's end-to-end check: the TAB's apply function edits
        the fee, Calculate re-runs, and the 5% literals land — a broken
        UI→engine recompute path fails these."""
        data = clorox.model_dump(mode="json")
        fee_index = next(i for i, e in enumerate(data["expenses"])
                         if e["name"] == "Management Fee")
        edited, error = expenses_tab.apply_expense_detail(
            clorox, fee_index, {"amount": 5.0})
        assert error is None
        _assert_edit_roundtrips_and_discriminates(clorox, edited, tmp_path)
        result, error = state.run_model(edited)
        assert error is None
        fee, egr, noi = _year1_fee_egr_noi(result, edited)
        assert fee == pytest.approx(FEE_5PCT, abs=0.01)      # discriminator
        assert egr == pytest.approx(EGR_5PCT, abs=0.01)      # discriminator
        assert fee == pytest.approx(0.05 * egr, abs=1e-6)    # the fixed point
        # the recoverable fee passes through recoveries: NOI unchanged —
        # asserted as the documented engine behavior, NOT the discriminator
        assert noi == pytest.approx(NOI_BOTH, abs=0.01)
        assert fee != pytest.approx(FEE_3PCT, abs=1.0)       # genuinely moved
        assert egr != pytest.approx(EGR_3PCT, abs=1.0)


class TestExpenseGrid:
    def test_scalar_edit_preserves_nested_detail(self, clorox, tmp_path):
        data = clorox.model_dump(mode="json")
        rows = convert.items_to_grid_rows(data["expenses"],
                                          convert.EXPENSE_GRID_COLUMNS)
        rows[0]["amount"] = 999.0
        edited, error = expenses_tab.apply_expense_grid(clorox, rows)
        assert error is None
        # Amortized CAM's date_range timing + custom inflation untouched
        assert edited.expenses[-1].timing == clorox.expenses[-1].timing
        assert edited.expenses[-1].inflation == clorox.expenses[-1].inflation
        _assert_edit_roundtrips_and_discriminates(clorox, edited, tmp_path)

    def test_add_row_uses_template(self, clorox):
        data = clorox.model_dump(mode="json")
        rows = convert.items_to_grid_rows(data["expenses"],
                                          convert.EXPENSE_GRID_COLUMNS)
        rows.append({"name": "Landscaping", "category": "operating",
                     "amount": 12_000.0, "unit": "dollars_per_year"})
        edited, error = expenses_tab.apply_expense_grid(clorox, rows)
        assert error is None
        added = edited.expenses[-1]
        assert added.name == "Landscaping" and added.amount == 12_000.0

    def test_bad_category_readable(self, clorox):
        data = clorox.model_dump(mode="json")
        rows = convert.items_to_grid_rows(data["expenses"],
                                          convert.EXPENSE_GRID_COLUMNS)
        rows[0]["category"] = "capex"          # not a valid ExpenseCategory
        edited, error = expenses_tab.apply_expense_grid(clorox, rows)
        assert edited is None
        assert "expenses.0.category" in error
        assert "Traceback" not in error and "pydantic" not in error.lower()

    def test_all_or_nothing_on_error(self, clorox):
        before = clorox.model_dump()
        data = clorox.model_dump(mode="json")
        rows = convert.items_to_grid_rows(data["expenses"],
                                          convert.EXPENSE_GRID_COLUMNS)
        rows[0]["category"] = "capex"
        expenses_tab.apply_expense_grid(clorox, rows)
        assert clorox.model_dump() == before


class TestExpenseDetail:
    def test_timing_date_range_edit(self, clorox, tmp_path):
        data = clorox.model_dump(mode="json")
        index = next(i for i, e in enumerate(data["expenses"])
                     if e["name"] == "Amortized CAM Revenue")
        edited, error = expenses_tab.apply_expense_detail(
            clorox, index, {"timing": {"method": "date_range",
                                       "start": "2026-06-01",
                                       "end": "2028-06-30",
                                       "repeat_months": None,
                                       "repeat_every_months": None}})
        assert error is None
        assert str(edited.expenses[index].timing.end) == "2028-06-30"
        _assert_edit_roundtrips_and_discriminates(clorox, edited, tmp_path)

    def test_limits_and_annual_overrides(self, clorox, tmp_path):
        edited, error = expenses_tab.apply_expense_detail(
            clorox, 0, {"limits": {"min": 5_000.0, "max": None},
                        "annual_overrides": [{"year": 2028,
                                              "amount": 400_000.0}]})
        assert error is None
        assert edited.expenses[0].limits.min == 5_000.0
        assert edited.expenses[0].annual_overrides[0].year == 2028
        _assert_edit_roundtrips_and_discriminates(clorox, edited, tmp_path)

    def test_inflation_custom_schedule(self, clorox, tmp_path):
        edited, error = expenses_tab.apply_expense_detail(
            clorox, 0, {"inflation": [{"year": 1, "rate": 2.0},
                                      {"year": 2, "rate": 4.0}]})
        assert error is None
        assert len(edited.expenses[0].inflation) == 2
        _assert_edit_roundtrips_and_discriminates(clorox, edited, tmp_path)

    def test_bad_override_year_readable(self, clorox):
        edited, error = expenses_tab.apply_expense_detail(
            clorox, 0, {"annual_overrides": [{"year": "soon",
                                              "amount": 1.0}]})
        assert edited is None
        assert "annual_overrides" in error
        assert "Traceback" not in error and "pydantic" not in error.lower()


class TestExpenseGroups:
    def test_create_and_roundtrip(self, clorox, tmp_path):
        edited, error = expenses_tab.apply_expense_groups(
            clorox, [{"name": "CAM Pool",
                      "members": "Common Area Maintenance, Utilities"},
                     {"name": "", "members": "x"}])       # blank name drops
        assert error is None
        assert len(edited.expense_groups) == 1
        assert edited.expense_groups[0].members == [
            "Common Area Maintenance", "Utilities"]
        _assert_edit_roundtrips_and_discriminates(clorox, edited, tmp_path)


class TestRevenues:
    def _kind_with_items(self, model):
        data = model.model_dump(mode="json")
        return next(k for k, _ in revenues_tab.KINDS if data[k])

    def test_grid_edit_roundtrips(self, freeport, tmp_path):
        kind = self._kind_with_items(freeport)
        data = freeport.model_dump(mode="json")
        rows = convert.items_to_grid_rows(data[kind],
                                          convert.REVENUE_GRID_COLUMNS)
        rows[0]["amount"] = 12_345.0
        edited, error = revenues_tab.apply_revenue_grid(freeport, kind, rows)
        assert error is None
        _assert_edit_roundtrips_and_discriminates(freeport, edited, tmp_path)

    def test_detail_limits_edit(self, freeport, tmp_path):
        kind = self._kind_with_items(freeport)
        edited, error = revenues_tab.apply_revenue_detail(
            freeport, kind, 0, {"limits": {"min": None, "max": 5_000.0}})
        assert error is None
        assert getattr(edited, kind)[0].limits.max == 5_000.0
        _assert_edit_roundtrips_and_discriminates(freeport, edited, tmp_path)

    def test_bad_unit_readable(self, freeport):
        kind = self._kind_with_items(freeport)
        data = freeport.model_dump(mode="json")
        rows = convert.items_to_grid_rows(data[kind],
                                          convert.REVENUE_GRID_COLUMNS)
        rows[0]["unit"] = "dollars_per_smile"
        edited, error = revenues_tab.apply_revenue_grid(freeport, kind, rows)
        assert edited is None
        assert f"{kind}.0.unit" in error
        assert "Traceback" not in error


class TestRefusedLifecycle:
    """pct_of_account rows: out of the grid, preserved through applies,
    detail-refused readably (Step 0 D2 — read-only means read-only)."""

    @pytest.fixture()
    def with_refused(self, clorox):
        def add(data):
            data["expenses"].append({"name": "Weird", "amount": 1.0,
                                     "unit": "pct_of_account",
                                     "account_ref": "CAM"})
        model, error = state.updated_model(clorox, add)
        assert error is None
        return model

    def test_grid_excludes_refused(self, with_refused):
        data = with_refused.model_dump(mode="json")
        rows = convert.items_to_grid_rows(data["expenses"],
                                          convert.EXPENSE_GRID_COLUMNS)
        assert all(row["name"] != "Weird" for row in rows)

    def test_apply_preserves_refused_at_position(self, with_refused):
        data = with_refused.model_dump(mode="json")
        rows = convert.items_to_grid_rows(data["expenses"],
                                          convert.EXPENSE_GRID_COLUMNS)
        rows[0]["amount"] = 111.0
        edited, error = expenses_tab.apply_expense_grid(with_refused, rows)
        assert error is None
        assert edited.expenses[-1].name == "Weird"       # still last, intact
        assert edited.expenses[-1].unit.value == "pct_of_account"
        assert edited.expenses[0].amount == 111.0

    def test_detail_edit_on_refused_refuses_readably(self, with_refused):
        index = len(with_refused.expenses) - 1
        edited, error = expenses_tab.apply_expense_detail(
            with_refused, index, {"amount": 2.0})
        assert edited is None
        assert "read-only" in error and "pct_of_account" in error
        assert "Traceback" not in error

    def test_refusal_texts_verbatim(self):
        """The UI shows the engine's messages verbatim — including the
        STALE 'until Phase 2' expense wording (deliberately surfaced
        as-is; on the post-Gate-5 wording-pass list)."""
        assert expenses_tab.refusal_text("Weird") == (
            "expense 'Weird': unit 'pct_of_account' is not implemented "
            "until Phase 2; remove the input or wait for that phase")
        assert revenues_tab.refusal_text("Parking") == (
            "property revenue 'Parking': unit 'pct_of_account' is not "
            "implemented until a later phase (DEVIATIONS.md §13); remove "
            "the input or wait for that phase")

    def test_refusal_text_matches_engine_exactly(self, with_refused):
        """§25 discrimination for the verbatim claim: run the engine on the
        refused model and assert its message CONTAINS the exact text the UI
        displays — if the engine wording ever changes (the post-Gate-5
        pass), this fails and the UI copy gets updated."""
        result, error = state.run_model(with_refused)
        assert result is None
        assert expenses_tab.refusal_text("Weird") in error
