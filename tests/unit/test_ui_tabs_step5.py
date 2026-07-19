"""Pure tests for the Step 5 Investment + Valuation tabs
(ui/tabs/investment_tab.py, ui/tabs/valuation_tab.py, ui/convert.py
additions — Phase 5; no browser).

Acceptance (NEXT_STEPS_TO_PHASE5.md Step 5, advisor directive):
1. Round-trip + §25 one-field discrimination; readable per-cell errors. No
   golden populates purchase/loans/valuation, so the fixture is the
   engineered flat 100k-NOI property (the valuation-demo shape) — its
   literals derive from real engine math, so the wrong answer genuinely
   differs from the right one.
2. THE HAND-CHECK ANCHORS, entered through the tabs' own apply functions
   and asserted as hard literals — the owner's Gate 3 Excel hand-checks,
   the only external truth this family has:
   - amortization payment 5,995.51 (and balance@12 987,719.88) on the
     $1M / 6.00% / 30-yr case;
   - resale: gross 1,250,000 / net 1,212,500 on the 100k-NOI / 8.00% exit
     cap / 3% selling-cost case;
   - PV/IRR self-consistency: price == unleveraged PV ⟹ IRR == 8.00%
     within 1bp.
3. The permanent refusals (pct_of_value sizing; derived price) are
   read-only: excluded/preserved/refused readably, with the UI's verbatim
   copy tied to the engine's ACTUAL message by a discrimination test.
"""
import datetime as dt

import pytest

from ui import convert, state
from ui.tabs import investment_tab, valuation_tab
from engine.models import (
    AreaMeasures,
    ExpenseItem,
    ExpenseUnit,
    Inflation,
    Lease,
    MoneyRate,
    MoneyUnit,
    PropertyInfo,
    PropertyModel,
    RentableAreaMode,
    TimingBasis,
    UponExpiration,
    YearRate,
)

BEGIN = dt.date(2026, 1, 1)
PSF_YR = MoneyUnit.dollars_per_area_per_year


def flat_model():
    """The valuation-demo shape: $10/SF on 12,000 SF, 20k non-recoverable
    OpEx → flat 100,000 NOI/yr; no purchase/loans/valuation until a test
    adds them through the tabs."""
    lease = Lease(tenant_name="T", area=12_000, lease_type="industrial",
                  start_date=BEGIN, term_months=240,
                  base_rent=MoneyRate(amount=10.0, unit=PSF_YR),
                  upon_expiration=UponExpiration.vacate)
    return PropertyModel(
        property=PropertyInfo(name="Demo", property_type="industrial",
                              analysis_begin=BEGIN, analysis_term_years=5),
        area_measures=AreaMeasures(
            property_size=12_000, rentable_area_mode=RentableAreaMode.fixed,
            rentable_area_fixed=12_000),
        inflation=Inflation(general_rate=[YearRate(year=1, rate=0.0)],
                            timing_basis=TimingBasis.analysis_year),
        rent_roll=[lease],
        expenses=[ExpenseItem(name="OpEx", amount=20_000.0,
                              unit=ExpenseUnit.dollars_per_year,
                              recoverable=False)])


MORTGAGE_ROW = {"name": "Mortgage", "amount_value": 1_000_000.0,
                "amount_basis": "amount", "rate": 6.0, "term_months": 360,
                "amortization": "fully_amortizing"}

VALUATION_PAYLOAD = {
    "discount_rate": 8.0, "discount_method": "annual",
    "period_convention": "end_of_period", "pv_start": None,
    "direct_cap": None,
    "resale": {"method": "cap_noi_current_year", "exit_cap_rate": 8.0,
               "resale_date": None, "apply_resale_to_cash_flow": True,
               "selling_costs_pct": 3.0, "adjustment_amounts": [],
               "noi_adjustments": {"exclude_capital": True,
                                   "stabilize_occupancy": None}},
    "sensitivity_intervals": {"discount_rate_step": 1.0,
                              "cap_rate_step": 1.0, "count": 5}}


def _assert_edit_roundtrips_and_discriminates(original, edited, tmp_path):
    assert edited is not None
    assert not state.models_equal(original, edited)
    saved = state.save_model(edited, tmp_path / "edited.icprop.json")
    reloaded, error = state.load_model(saved)
    assert error is None
    assert state.models_equal(edited, reloaded)


class TestHandCheckAnchors:
    """The owner's Gate 3 Excel hand-checks, reached THROUGH the tabs."""

    def test_amortization_payment_literal(self, tmp_path):
        model = flat_model()
        edited, error = investment_tab.apply_loan_grid(model, [MORTGAGE_ROW])
        assert error is None
        _assert_edit_roundtrips_and_discriminates(model, edited, tmp_path)
        result, error = state.run_model(edited)
        assert error is None
        frame = result.loan_schedules[0].frame
        assert frame["payment"].iloc[0] == pytest.approx(5_995.51, abs=0.005)
        assert frame["ending"].iloc[11] == pytest.approx(987_719.88, abs=0.005)

    def test_resale_literal(self, tmp_path):
        model = flat_model()
        edited, error = valuation_tab.apply_valuation(model,
                                                      VALUATION_PAYLOAD)
        assert error is None
        _assert_edit_roundtrips_and_discriminates(model, edited, tmp_path)
        result, error = state.run_model(edited)
        assert error is None
        assert result.resale.gross_sale_price == pytest.approx(1_250_000.0,
                                                               abs=0.01)
        assert result.resale.net_unleveraged == pytest.approx(1_212_500.0,
                                                              abs=0.01)

    def test_pv_irr_self_consistency_through_tabs(self):
        """price == unleveraged PV (set via apply_purchase) ⟹ IRR == the
        8% discount rate within 1bp — the §9.3 identity, driven end-to-end
        through both tabs."""
        model, error = valuation_tab.apply_valuation(flat_model(),
                                                     VALUATION_PAYLOAD)
        assert error is None
        first, error = state.run_model(model)
        assert error is None
        pv = first.valuation.unleveraged_pv
        priced, error = investment_tab.apply_purchase(
            model, {"price": pv, "date": None, "closing_costs": []})
        assert error is None
        result, error = state.run_model(priced)
        assert error is None
        assert result.valuation.unleveraged_irr == pytest.approx(8.0,
                                                                 abs=0.01)


class TestPurchase:
    def test_purchase_roundtrips(self, tmp_path):
        model = flat_model()
        # the renderer routes grid rows through rows_to_closing_costs —
        # same path here (blank-name rows drop in the converter)
        cost_rows = [{"name": "Legal", "amount": 25_000.0,
                      "pct_of_price": None, "timing": "at_purchase",
                      "date": None},
                     {"name": "", "amount": 1.0, "pct_of_price": None,
                      "timing": "at_purchase", "date": None}]
        edited, error = investment_tab.apply_purchase(
            model, {"price": 1_250_000.0, "date": "2026-01-01",
                    "closing_costs": convert.rows_to_closing_costs(
                        cost_rows)})
        assert error is None
        assert edited.purchase.price == 1_250_000.0
        assert len(edited.purchase.closing_costs) == 1   # blank name dropped
        assert edited.purchase.closing_costs[0].name == "Legal"
        _assert_edit_roundtrips_and_discriminates(model, edited, tmp_path)

    def test_clear_purchase(self):
        model, _ = investment_tab.apply_purchase(
            flat_model(), {"price": 1.0, "date": None, "closing_costs": []})
        cleared, error = investment_tab.apply_purchase(model, None)
        assert error is None and cleared.purchase is None

    def test_bad_date_readable(self):
        edited, error = investment_tab.apply_purchase(
            flat_model(), {"price": 1.0, "date": "not-a-date",
                           "closing_costs": []})
        assert edited is None
        assert "purchase.date" in error
        assert "Traceback" not in error and "pydantic" not in error.lower()

    def test_derived_purchase_read_only(self):
        model, error = state.updated_model(
            flat_model(),
            lambda d: d.update(purchase={"derivation": "pv_at_discount_rate"}))
        assert error is None
        edited, error = investment_tab.apply_purchase(model, {"price": 1.0})
        assert edited is None
        assert "permanently refused" in error and "read-only" in error
        assert "Traceback" not in error

    def test_derived_refusal_text_matches_engine(self):
        """§25 discrimination for the verbatim claim: the engine's ACTUAL
        message contains the UI copy — the post-Gate-5 wording pass will
        fail this and force the UI update (both stale 'OPEN' labels are on
        the stale-message list)."""
        model, _ = state.updated_model(
            flat_model(),
            lambda d: d.update(purchase={"derivation": "pv_at_discount_rate"}))
        result, error = state.run_model(model)
        assert result is None
        assert investment_tab.refusal_derived_price_text(
            "pv_at_discount_rate") in error


class TestLoans:
    def test_grid_rate_edit_roundtrips(self, tmp_path):
        model, _ = investment_tab.apply_loan_grid(flat_model(),
                                                  [MORTGAGE_ROW])
        rows = convert.loans_to_grid_rows(model.model_dump(mode="json")
                                          ["loans"])
        rows[0]["rate"] = 5.5
        edited, error = investment_tab.apply_loan_grid(model, rows)
        assert error is None
        assert edited.loans[0].rate == 5.5
        _assert_edit_roundtrips_and_discriminates(model, edited, tmp_path)

    def test_balloon_amortization_years(self):
        row = dict(MORTGAGE_ROW, amortization="30", term_months=120)
        model, error = investment_tab.apply_loan_grid(flat_model(), [row])
        assert error is None
        assert model.loans[0].amortization == 30     # int years (balloon)
        result, error = state.run_model(model)
        assert error is None
        # the owner's balloon literal: amortized 30 due in 120 → 836,857.25
        assert result.loan_schedules[0].balloon == pytest.approx(
            836_857.25, abs=0.01)

    def test_floating_rate_detail_roundtrips(self, tmp_path):
        model, _ = investment_tab.apply_loan_grid(flat_model(),
                                                  [MORTGAGE_ROW])
        edited, error = investment_tab.apply_loan_detail(
            model, 0, {"rate": {"index": [{"year": 1, "rate": 5.0},
                                          {"year": 3, "rate": 7.0}],
                                "spread": 2.5},
                       "type": "floating", "interest_only_months": 0,
                       "additional_principal": [], "loan_costs": None})
        assert error is None
        assert edited.loans[0].rate.spread == 2.5
        result, error = state.run_model(edited)
        assert error is None
        frame = result.loan_schedules[0].frame
        assert frame["rate"].iloc[0] == pytest.approx(7.5)   # 5.0 + 2.5
        assert frame["rate"].iloc[26] == pytest.approx(9.5)  # 7.0 + 2.5
        _assert_edit_roundtrips_and_discriminates(model, edited, tmp_path)
        # the grid renders it as the floating placeholder
        rows = convert.loans_to_grid_rows(edited.model_dump(mode="json")
                                          ["loans"])
        assert rows[0]["rate"] == convert.FLOATING_LABEL

    def test_io_and_additional_principal_and_costs(self, tmp_path):
        model, _ = investment_tab.apply_loan_grid(flat_model(),
                                                  [MORTGAGE_ROW])
        edited, error = investment_tab.apply_loan_detail(
            model, 0, {"rate": 6.0, "type": "fixed",
                       "interest_only_months": 12,
                       "additional_principal": [{"date": "2027-06-01",
                                                 "amount": 50_000.0}],
                       "loan_costs": {"points_pct": 1.0, "fees": 2_500.0,
                                      "timing": None,
                                      "handling": "expense"}})
        assert error is None
        loan = edited.loans[0]
        assert loan.interest_only_months == 12
        assert loan.additional_principal[0].amount == 50_000.0
        assert loan.loan_costs.points_pct == 1.0
        _assert_edit_roundtrips_and_discriminates(model, edited, tmp_path)
        result, error = state.run_model(edited)
        assert error is None                       # runs clean end-to-end

    def test_bad_term_readable(self):
        row = dict(MORTGAGE_ROW, term_months=0)
        edited, error = investment_tab.apply_loan_grid(flat_model(), [row])
        assert edited is None
        assert "loans.0" in error and "term_months" in error
        assert "Traceback" not in error and "pydantic" not in error.lower()

    def test_refused_loan_lifecycle(self):
        model, _ = investment_tab.apply_loan_grid(flat_model(),
                                                  [MORTGAGE_ROW])
        with_refused, error = state.updated_model(
            model, lambda d: d["loans"].append(
                {"name": "ValueLoan",
                 "amount": {"basis": "pct_of_value", "value": 60.0},
                 "term_months": 360, "rate": 6.0}))
        assert error is None
        rows = convert.loans_to_grid_rows(
            with_refused.model_dump(mode="json")["loans"])
        assert all(row["name"] != "ValueLoan" for row in rows)  # excluded
        rows[0]["rate"] = 5.5
        edited, error = investment_tab.apply_loan_grid(with_refused, rows)
        assert error is None
        assert edited.loans[-1].name == "ValueLoan"             # preserved
        _, error = investment_tab.apply_loan_detail(with_refused, 1,
                                                    {"rate": 5.0})
        assert error is not None and "read-only" in error       # refused

    def test_pct_of_value_refusal_text_matches_engine(self):
        model, _ = investment_tab.apply_loan_grid(flat_model(),
                                                  [MORTGAGE_ROW])
        with_refused, _ = state.updated_model(
            model, lambda d: (d["loans"].append(
                {"name": "ValueLoan",
                 "amount": {"basis": "pct_of_value", "value": 60.0},
                 "term_months": 360, "rate": 6.0}),
                d.update(purchase={"derivation": "fixed",
                                   "price": 1_000_000.0}))[0])
        result, error = state.run_model(with_refused)
        assert result is None
        assert investment_tab.refusal_pct_of_value_text("ValueLoan") in error


class TestValuation:
    def test_full_payload_roundtrips(self, tmp_path):
        model = flat_model()
        edited, error = valuation_tab.apply_valuation(model,
                                                      VALUATION_PAYLOAD)
        assert error is None
        v = edited.valuation
        assert v.discount_rate == 8.0
        assert v.resale.exit_cap_rate == 8.0
        assert v.sensitivity_intervals.count == 5
        _assert_edit_roundtrips_and_discriminates(model, edited, tmp_path)

    def test_clear_valuation(self):
        model, _ = valuation_tab.apply_valuation(flat_model(),
                                                 VALUATION_PAYLOAD)
        cleared, error = valuation_tab.apply_valuation(model, None)
        assert error is None and cleared.valuation is None

    def test_fixed_amount_method(self, tmp_path):
        payload = dict(VALUATION_PAYLOAD,
                       resale={"method": "fixed_amount",
                               "fixed_amount": 2_000_000.0,
                               "resale_date": None,
                               "apply_resale_to_cash_flow": True})
        model = flat_model()
        edited, error = valuation_tab.apply_valuation(model, payload)
        assert error is None
        result, error = state.run_model(edited)
        assert error is None
        # Enter Sale Price: gross AND net, no selling costs [AE p. 465]
        assert result.resale.net_unleveraged == pytest.approx(2_000_000.0)
        _assert_edit_roundtrips_and_discriminates(model, edited, tmp_path)

    def test_pct_increase_method_needs_purchase(self):
        payload = dict(VALUATION_PAYLOAD,
                       resale={"method": "pct_increase_over_price",
                               "pct_increase": 20.0, "resale_date": None,
                               "apply_resale_to_cash_flow": True,
                               "selling_costs_pct": 0.0,
                               "adjustment_amounts": []})
        model, error = valuation_tab.apply_valuation(flat_model(), payload)
        assert error is None                     # schema-legal
        result, error = state.run_model(model)   # engine needs the price
        assert result is None
        assert "purchase price" in error and "Traceback" not in error

    def test_missing_cap_rate_readable(self):
        payload = dict(VALUATION_PAYLOAD,
                       resale={"method": "cap_noi_forward_12",
                               "resale_date": None,
                               "apply_resale_to_cash_flow": True,
                               "selling_costs_pct": 0.0,
                               "adjustment_amounts": []})
        edited, error = valuation_tab.apply_valuation(flat_model(), payload)
        assert edited is None
        assert "exit_cap_rate" in error or "exit cap" in error
        assert "Traceback" not in error and "pydantic" not in error.lower()

    def test_bad_sensitivity_count_readable(self):
        payload = dict(VALUATION_PAYLOAD,
                       sensitivity_intervals={"discount_rate_step": 1.0,
                                              "cap_rate_step": 1.0,
                                              "count": 6})
        edited, error = valuation_tab.apply_valuation(flat_model(), payload)
        assert edited is None
        assert "count" in error
        assert "Traceback" not in error


class TestConverters:
    def test_closing_cost_blank_name_drops(self):
        rows = [{"name": "Legal", "amount": 1.0, "pct_of_price": None,
                 "timing": None, "date": None},
                {"name": "", "amount": 2.0, "pct_of_price": None,
                 "timing": None, "date": None}]
        kept = convert.rows_to_closing_costs(rows)
        assert len(kept) == 1 and kept[0]["timing"] == "at_purchase"

    def test_amortization_parse(self):
        assert convert._parse_amortization("30") == 30
        assert convert._parse_amortization("fully_amortizing") == \
            "fully_amortizing"
        assert convert._parse_amortization("interest_only") == "interest_only"
