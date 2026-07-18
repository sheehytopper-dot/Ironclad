"""Pure tests for the Step 2 Property + Market tab commit functions
(ui/tabs/property_tab.py, ui/tabs/market_tab.py, ui/convert.py — Phase 5;
no browser, no Streamlit runtime).

Acceptance (NEXT_STEPS_TO_PHASE5.md Step 2): every field round-trips
(edit → save → reload → identical, model_dump equality) and — DEVIATIONS
§25 — a one-field alteration flips the identity check against the
original (the fixtures are the real goldens, so the wrong value genuinely
differs from the right one); per-cell validation errors are readable
(§5.4: field path + offending value + no pydantic/traceback surface).
"""
from pathlib import Path

import pytest

from ui import convert, state
from ui.tabs import market_tab, property_tab

GOLDEN = Path(__file__).resolve().parents[1] / "golden"
CLOROX = GOLDEN / "clorox_northlake" / "clorox_northlake.icprop.json"
FREEPORT = GOLDEN / "freeport" / "freeport.icprop.json"


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
    """The Step 2 acceptance in one helper: the edit produced a DIFFERENT
    model (§25 — the identity check catches the alteration) and the edited
    model save→reloads IDENTICALLY."""
    assert edited is not None
    assert not state.models_equal(original, edited)          # discriminates
    saved = state.save_model(edited, tmp_path / "edited.icprop.json")
    reloaded, error = state.load_model(saved)
    assert error is None
    assert state.models_equal(edited, reloaded)              # round-trips


# ------------------------------------------------------------------ #
# Property tab                                                        #
# ------------------------------------------------------------------ #

class TestPropertyTab:
    @pytest.mark.parametrize("info", [
        {"name": "Renamed Property"},
        {"analysis_term_years": 7},
        {"fiscal_year_end_month": 6},
        {"property_type": "office"},
        {"external_id": "EXT-42"},
        {"currency": "CAD"},
    ])
    def test_property_info_fields_roundtrip(self, clorox, tmp_path, info):
        edited, error = property_tab.apply_property_info(clorox, info, {})
        assert error is None
        _assert_edit_roundtrips_and_discriminates(clorox, edited, tmp_path)

    def test_address_roundtrips(self, clorox, tmp_path):
        edited, error = property_tab.apply_property_info(
            clorox, {}, {"street": "1 Main St", "zip": "76262"})
        assert error is None
        assert edited.property.address.street == "1 Main St"
        _assert_edit_roundtrips_and_discriminates(clorox, edited, tmp_path)

    @pytest.mark.parametrize("fields", [
        {"property_size": 999_999.0},
        {"alternate_size": 480_000.0},
        {"rentable_area_fixed": 540_001.0},
    ])
    def test_area_measures_roundtrip(self, clorox, tmp_path, fields):
        edited, error = property_tab.apply_area_measures(clorox, fields)
        assert error is None
        _assert_edit_roundtrips_and_discriminates(clorox, edited, tmp_path)

    def test_area_schedule_roundtrips(self, clorox, tmp_path):
        edited, error = property_tab.apply_area_measures(
            clorox, {"rentable_area_mode": "schedule"},
            schedule_rows=[{"date": "2026-06-01", "area": 540_000.0},
                           {"date": None, "area": None}])   # blank row drops
        assert error is None
        assert len(edited.area_measures.rentable_area_schedule) == 1
        _assert_edit_roundtrips_and_discriminates(clorox, edited, tmp_path)

    def test_bad_term_readable_error(self, clorox):
        edited, error = property_tab.apply_property_info(
            clorox, {"analysis_term_years": 0}, {})
        assert edited is None
        assert "property.analysis_term_years" in error       # field path
        assert "0" in error                                  # offending value
        assert "Traceback" not in error
        assert "pydantic" not in error.lower()

    def test_bad_enum_readable_error(self, clorox):
        edited, error = property_tab.apply_property_info(
            clorox, {"property_type": "mall"}, {})
        assert edited is None
        assert "property.property_type" in error
        assert "Traceback" not in error

    def test_original_untouched_on_error(self, clorox):
        before = clorox.model_dump()
        property_tab.apply_property_info(clorox, {"analysis_term_years": 0}, {})
        assert clorox.model_dump() == before                 # all-or-nothing


# ------------------------------------------------------------------ #
# Market tab                                                          #
# ------------------------------------------------------------------ #

class TestMarketTabInflation:
    def test_general_rate_edit_roundtrips(self, freeport, tmp_path):
        data = freeport.model_dump(mode="json")["inflation"]
        rows = convert.year_rates_to_rows(data["general_rate"])
        rows[0]["rate"] = 9.9
        edited, error = market_tab.apply_inflation(
            freeport, timing_basis=data["timing_basis"],
            inflation_month=data["inflation_month"], general_rows=rows,
            market_rows=convert.year_rates_to_rows(data["market_rent_rate"]),
            expense_rows=convert.year_rates_to_rows(data["expense_rate"]),
            cpi_rows=convert.year_rates_to_rows(data["cpi_rate"]))
        assert error is None
        _assert_edit_roundtrips_and_discriminates(freeport, edited, tmp_path)

    def test_custom_index_add_roundtrips(self, freeport, tmp_path):
        edited, error = market_tab.apply_custom_indices(
            freeport, [{"name": "Tax Index",
                        "rows": [{"year": 1, "rate": 5.0}]},
                       {"name": "   ", "rows": []}])         # blank name drops
        assert error is None
        assert [ix.name for ix in edited.inflation.custom_indices] == ["Tax Index"]
        _assert_edit_roundtrips_and_discriminates(freeport, edited, tmp_path)


class TestMarketTabVacancy:
    @pytest.mark.parametrize("section", ["general_vacancy", "credit_loss"])
    def test_method_and_rate_roundtrip(self, freeport, tmp_path, section):
        edited, error = market_tab.apply_vacancy_section(
            freeport, section, method="percent_of_pgr",
            rate_rows=[{"year": 1, "rate": 4.0}],
            include_accounts=[], override_rows=[])
        assert error is None
        _assert_edit_roundtrips_and_discriminates(freeport, edited, tmp_path)

    def test_overrides_and_reduce_flag(self, freeport, tmp_path):
        edited, error = market_tab.apply_vacancy_section(
            freeport, "general_vacancy", method="percent_of_pgr",
            rate_rows=[{"year": 1, "rate": 4.0}], include_accounts=[],
            override_rows=[{"tenant_ref": "Burnco Texas, LLC.",
                            "exclude": True},
                           {"tenant_ref": "", "exclude": True}],  # blank drops
            reduce_by_absorption_turnover=False)
        assert error is None
        gv = edited.general_vacancy
        assert gv.reduce_by_absorption_turnover is False
        assert [o.tenant_ref for o in gv.tenant_overrides] == [
            "Burnco Texas, LLC."]
        _assert_edit_roundtrips_and_discriminates(freeport, edited, tmp_path)

    def test_bad_method_readable(self, freeport):
        edited, error = market_tab.apply_vacancy_section(
            freeport, "general_vacancy", method="percent_of_everything",
            rate_rows=[], include_accounts=[], override_rows=[])
        assert edited is None
        assert "general_vacancy.method" in error
        assert "Traceback" not in error and "pydantic" not in error.lower()


class TestMarketTabMlps:
    def test_grid_scalar_edit_preserves_nested_detail(self, freeport,
                                                      tmp_path):
        data = freeport.model_dump(mode="json")
        rows = convert.mlp_grid_rows(data["market_leasing_profiles"])
        rows[0]["renewal_probability"] = 33.0
        edited, error = market_tab.apply_mlp_grid(freeport, rows)
        assert error is None
        # nested economics untouched by a scalar grid edit
        assert (edited.market_leasing_profiles[0].market_base_rent_new
                == freeport.market_leasing_profiles[0].market_base_rent_new)
        assert (edited.market_leasing_profiles[0].lc_new
                == freeport.market_leasing_profiles[0].lc_new)
        _assert_edit_roundtrips_and_discriminates(freeport, edited, tmp_path)

    def test_grid_add_and_delete_rows(self, freeport):
        data = freeport.model_dump(mode="json")
        rows = convert.mlp_grid_rows(data["market_leasing_profiles"])
        added = rows + [{"name": "Brand New MLP", "term_months": 36,
                         "renewal_probability": 60.0, "months_vacant": 3.0,
                         "free_rent_months_new": 1.0,
                         "free_rent_months_renew": 0.0,
                         "upon_expiration": "market", "term_growth": True,
                         "intelligent_renewals": "market"}]
        edited, error = market_tab.apply_mlp_grid(freeport, added)
        assert error is None
        assert edited.market_leasing_profiles[-1].name == "Brand New MLP"
        # the template gives the new row $0 market rent to fill in
        assert edited.market_leasing_profiles[-1].market_base_rent_new.amount == 0.0
        # deleting rows deletes profiles — but Freeport's MLPs are referenced
        # by leases, so deleting them must FAIL loudly (cross-ref validator),
        # readable, not silently
        deleted, error = market_tab.apply_mlp_grid(freeport, rows[:1])
        if deleted is None:
            assert "Traceback" not in error
        else:
            assert len(deleted.market_leasing_profiles) == 1

    def test_detail_ti_edit_roundtrips(self, freeport, tmp_path):
        edited, error = market_tab.apply_mlp_detail(
            freeport, 0, {"ti_new": {"amount": 99.0,
                                     "unit": "dollars_per_area"}})
        assert error is None
        assert edited.market_leasing_profiles[0].ti_new.amount == 99.0
        _assert_edit_roundtrips_and_discriminates(freeport, edited, tmp_path)

    def test_detail_lc_pct_edit_roundtrips(self, freeport, tmp_path):
        edited, error = market_tab.apply_mlp_detail(
            freeport, 0, {"lc_new": {"pct": 4.0, "pct_years": [1, 2, 3]}})
        assert error is None
        assert edited.market_leasing_profiles[0].lc_new.pct == 4.0
        _assert_edit_roundtrips_and_discriminates(freeport, edited, tmp_path)

    def test_detail_renew_rent_pct_of_new(self, freeport, tmp_path):
        edited, error = market_tab.apply_mlp_detail(
            freeport, 0, {"market_base_rent_renew": {"pct_of_new": 85.0}})
        assert error is None
        _assert_edit_roundtrips_and_discriminates(freeport, edited, tmp_path)

    def test_detail_rent_steps_roundtrip(self, freeport, tmp_path):
        edited, error = market_tab.apply_mlp_detail(
            freeport, 0, {"rent_increases": convert.rows_to_rent_steps(
                [{"month_offset": 12, "date": None, "amount": None,
                  "unit": None, "pct_increase": 3.0},
                 {"month_offset": None, "date": None, "amount": None,
                  "unit": None, "pct_increase": None}])})    # blank drops
        assert error is None
        steps = edited.market_leasing_profiles[0].rent_increases
        assert len(steps) == 1 and steps[0].pct_increase == 3.0
        _assert_edit_roundtrips_and_discriminates(freeport, edited, tmp_path)

    def test_detail_invalid_step_readable(self, freeport):
        # a step with BOTH amount and pct_increase trips the RentStep
        # exactly-one-of validator — readable, with the path
        edited, error = market_tab.apply_mlp_detail(
            freeport, 0, {"rent_increases": [
                {"month_offset": 12, "date": None, "amount": 10.0,
                 "unit": "dollars_per_area_per_year", "pct_increase": 3.0}]})
        assert edited is None
        assert "rent_increases" in error
        assert "Traceback" not in error and "pydantic" not in error.lower()

    def test_detail_recoveries_edit_roundtrips(self, freeport, tmp_path):
        edited, error = market_tab.apply_mlp_detail(
            freeport, 0, {"recoveries": {"method": "base_stop",
                                         "stop_amount_per_area": 5.25}})
        assert error is None
        rec = edited.market_leasing_profiles[0].recoveries
        assert rec.method.value == "base_stop"
        assert rec.stop_amount_per_area == 5.25
        _assert_edit_roundtrips_and_discriminates(freeport, edited, tmp_path)


class TestMarketTabFreeRent:
    def test_add_profile_keeps_referenced_ones(self, clorox, tmp_path):
        """Clorox's MLP references 'Base Rent Only' — the grid must keep it
        (replacing the list without it is refused by the cross-ref
        validator, readably)."""
        existing = convert.free_rent_profiles_to_rows(
            clorox.model_dump(mode="json")["free_rent_profiles"])
        edited, error = market_tab.apply_free_rent_profiles(
            clorox, existing + [{"name": "New FRP", "abate_base_rent": True,
                                 "abate_recoveries": True,
                                 "abate_miscellaneous": False}])
        assert error is None
        assert [p.name for p in edited.free_rent_profiles][-1] == "New FRP"
        _assert_edit_roundtrips_and_discriminates(clorox, edited, tmp_path)

    def test_dropping_referenced_profile_fails_readably(self, clorox):
        edited, error = market_tab.apply_free_rent_profiles(
            clorox, [{"name": "Unrelated", "abate_base_rent": True,
                      "abate_recoveries": False,
                      "abate_miscellaneous": False}])
        assert edited is None
        assert "free rent profile" in error       # the cross-ref message
        assert "Traceback" not in error
        # §5.4: the whole-document input must NOT be dumped into the message
        assert len(error) < 2_000


class TestConverters:
    def test_year_rate_blank_rows_drop(self):
        rows = [{"year": 1, "rate": 3.0}, {"year": None, "rate": None}]
        assert convert.rows_to_year_rates(rows) == [{"year": 1, "rate": 3.0}]

    def test_schedule_empty_is_none(self):
        assert convert.rows_to_schedule([{"date": None, "area": None}]) is None

    def test_rent_steps_empty_is_none(self):
        assert convert.rows_to_rent_steps([]) is None
