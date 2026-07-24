"""TestClient tests for the API core (api/main.py, api/serialize.py —
the web front-end pivot, rollout step 2; NEXT_STEPS_WEB_FRONTEND.md §4).

The point of building the API first: every report endpoint's payload is
deserialized and asserted EQUAL to the engine builder's frame for the
same toggles — the Step-6 frame-equality discipline through HTTP —
anchored on the known golden literals (Clorox NOI 2,596,319.40; Freeport
benchmark miss_count 170; the Freeport B GV-basis and Cedar Alt B
recovery-drill literals). §25 throughout: a toggle change must change the
payload; NaN must round-trip as null (never literal NaN — invalid JSON);
the structured errors must name field/offending value/fix and never
contain "Traceback"/"pydantic".
"""
import datetime as dt
import json
import shutil
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from engine.calc.run import run_property
from engine.export import export_rent_roll
from engine.models.io import load_property
from engine.reports import Period, Unit, cash_flow
from ui import state

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "tests" / "golden"


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    """A hermetic properties dir (clorox + freeport + cedar + the
    valuation demo) served by one TestClient; freeport gets a PER-NAME
    benchmark CSV (the flat-directory convention)."""
    props = tmp_path_factory.mktemp("apiprops")
    import os
    os.environ[state.PROPERTIES_DIR_ENV] = str(props)
    for golden, name in (("clorox_northlake", "clorox"),
                         ("freeport", "freeport"),
                         ("cedar_alt", "cedar")):
        shutil.copy(GOLDEN / golden / f"{golden}.icprop.json",
                    props / f"{name}.icprop.json")
    shutil.copy(GOLDEN / "freeport" / "expected_annual_cash_flow.csv",
                props / "freeport.expected_annual_cash_flow.csv")
    # the valuation demo (no golden has valuation): flat 100k NOI, 8% cap
    from tests.unit.test_ui_tabs_step5 import (VALUATION_PAYLOAD,
                                               flat_model)
    from ui.tabs import valuation_tab
    demo, error = valuation_tab.apply_valuation(flat_model(),
                                                VALUATION_PAYLOAD)
    assert error is None
    state.save_model(demo, props / "demo.icprop.json")

    from api import main as api_main
    api_main._RUNS.clear()
    test_client = TestClient(api_main.app)
    for name in ("clorox", "freeport", "cedar", "demo"):
        response = test_client.post(f"/api/calculate/{name}")
        assert response.status_code == 200, response.text
    return test_client


def _frame_from(payload: dict) -> pd.DataFrame:
    frame = pd.DataFrame(payload["data"], columns=payload["columns"])
    frame.index = payload["index"]
    return frame


class TestProperties:
    def test_list(self, client):
        names = {p["name"] for p in
                 client.get("/api/properties").json()["properties"]}
        assert names == {"clorox", "freeport", "cedar", "demo"}

    def test_get_document_matches_disk(self, client):
        document = client.get("/api/properties/clorox").json()["document"]
        disk = load_property(state.properties_dir()
                             / "clorox.icprop.json")
        assert document == disk.model_dump(mode="json")

    def test_unknown_property_404_structured(self, client):
        response = client.get("/api/properties/ghost")
        assert response.status_code == 404
        assert "ghost" in response.json()["error"]["summary"]
        assert "Traceback" not in response.text

    def test_put_bad_document_422_names_field_and_value(self, client):
        document = client.get("/api/properties/clorox").json()["document"]
        document["property"]["analysis_term_years"] = 0
        response = client.put("/api/properties/clorox", json=document)
        assert response.status_code == 422
        problems = response.json()["error"]["problems"]
        assert problems[0]["field"] == "property.analysis_term_years"
        assert problems[0]["got"] == "0"
        assert "greater than or equal to 1" in problems[0]["message"]
        assert "Traceback" not in response.text
        assert "pydantic" not in response.text.lower()
        # the file on disk is untouched (all-or-nothing)
        disk = load_property(state.properties_dir() / "clorox.icprop.json")
        assert disk.property.analysis_term_years == 5

    def test_put_saves_and_invalidates_run(self, client):
        document = client.get("/api/properties/clorox").json()["document"]
        response = client.put("/api/properties/clorox", json=document)
        assert response.json()["run_invalidated"] is True
        stale = client.get("/api/reports/cash-flow",
                           params={"name": "clorox"})
        assert stale.status_code == 409
        assert "no calculation yet" in stale.json()["error"]["summary"]
        # recalculate restores service (module fixture state)
        assert client.post("/api/calculate/clorox").status_code == 200


class TestCalculate:
    def test_summary_literals_and_flags(self, client):
        body = client.post("/api/calculate/clorox").json()
        assert body["summary"]["year1_noi"] == pytest.approx(
            2_596_319.40, abs=0.01)
        assert body["summary"]["year1_occupancy_pct"] == pytest.approx(100.0)
        flags = body["applicability"]
        assert flags["valuation"] is False and flags["loans"] is False
        demo_flags = client.post("/api/calculate/demo").json()[
            "applicability"]
        assert demo_flags["valuation"] is True
        assert demo_flags["sensitivity"] is True

    def test_refusal_verbatim_in_summary(self, client):
        document = client.get("/api/properties/clorox").json()["document"]
        document["expenses"].append({"name": "Weird", "amount": 1.0,
                                     "unit": "pct_of_account",
                                     "account_ref": "CAM"})
        assert client.put("/api/properties/refusal",
                          json=document).status_code == 200
        response = client.post("/api/calculate/refusal")
        assert response.status_code == 422
        summary = response.json()["error"]["summary"]
        # the engine's message verbatim — incl. the stale-list wording
        assert "pct_of_account' is not implemented until Phase 2" in summary
        assert "Traceback" not in response.text


class TestReportEndpoints:
    """Acceptance: endpoint numbers == the builder's frame, over HTTP."""

    def test_cash_flow_equals_builder_exactly(self, client):
        payload = client.get("/api/reports/cash-flow",
                             params={"name": "clorox",
                                     "period": "annual"}).json()
        got = _frame_from(payload["frame"])
        model = load_property(state.properties_dir()
                              / "clorox.icprop.json")
        result = run_property(model)
        direct = cash_flow(result, unit=Unit.total, period=Period.annual,
                           fiscal_year_end_month=model.property
                           .fiscal_year_end_month,
                           analysis_begin=model.property.analysis_begin)
        assert list(got.index) == list(direct.frame.index)
        # full precision through JSON: exact float equality, every cell
        assert (got.to_numpy() == direct.frame.to_numpy()).all()
        noi = got.loc["Net Operating Income"].iloc[0]
        assert noi == 2596319.4000000004          # the literal, unrounded
        assert "tree" in payload["meta"]["extra"]  # the front-end needs it

    def test_unit_toggle_changes_the_payload(self, client):
        total = _frame_from(client.get(
            "/api/reports/cash-flow",
            params={"name": "clorox", "period": "annual"}).json()["frame"])
        per_sf = _frame_from(client.get(
            "/api/reports/cash-flow",
            params={"name": "clorox", "period": "annual",
                    "unit": "per_sf"}).json()["frame"])
        noi_total = total.loc["Net Operating Income"].iloc[0]
        noi_psf = per_sf.loc["Net Operating Income"].iloc[0]
        assert noi_psf == pytest.approx(noi_total / 540_000.0, rel=1e-12)
        assert noi_total != noi_psf                # §25: the toggle bites

    def test_benchmark_literals(self, client):
        payload = client.get("/api/reports/benchmark-comparison",
                             params={"name": "freeport"}).json()
        assert payload["meta"]["extra"]["miss_count"] == 170
        assert payload["meta"]["extra"]["skipped_accounts"] == []

    def test_benchmark_not_offered_without_per_name_csv(self, client):
        """The flat-directory guard: clorox has NO per-name CSV in the
        multi-property dir, so #24 must NOT appear (it would otherwise
        silently benchmark clorox against freeport's numbers)."""
        keys = {e["key"] for e in client.get(
            "/api/reports", params={"name": "clorox"}).json()["reports"]}
        assert "benchmark-comparison" not in keys
        response = client.get("/api/reports/benchmark-comparison",
                              params={"name": "clorox"})
        assert response.status_code == 404

    def test_nan_round_trips_as_null(self, client):
        """Build-note 1: the demo has valuation but no loans — leveraged
        metrics are NaN in the frame and MUST arrive as null (literal NaN
        is invalid JSON; the browser's JSON.parse throws)."""
        response = client.get("/api/reports/valuation-and-return-summary",
                              params={"name": "demo"})
        assert "NaN" not in response.text          # strict-JSON guarantee
        payload = json.loads(response.text)        # parses cleanly
        frame = payload["frame"]
        value_column = frame["columns"].index("value")
        metric_column = frame["columns"].index("metric")
        by_metric = {row[metric_column]: row[value_column]
                     for row in frame["data"]}
        assert by_metric["Leveraged PV"] is None    # NaN → null
        assert by_metric["Unleveraged PV"] == pytest.approx(1_224_478.13,
                                                            abs=0.01)

    def test_invalid_unit_readable(self, client):
        response = client.get("/api/reports/cash-flow",
                              params={"name": "clorox",
                                      "unit": "per_acre"})
        assert response.status_code == 422
        assert "per_acre" in response.json()["error"]["summary"] or \
            "Invalid unit" in response.json()["error"]["summary"]
        assert "Traceback" not in response.text


class TestAuditEndpoints:
    def test_composition_ties_to_ledger(self, client):
        payload = client.get("/api/audit/composition",
                             params={"name": "freeport",
                                     "account": "Expense Recovery Revenue",
                                     "month": "2026-07"}).json()
        rows = _frame_from(payload["rows"])
        assert rows["recoveries"].sum() == pytest.approx(20_840.57,
                                                         abs=0.01)
        assert "Lease Audit" in payload["caption"]

    def test_gv_basis_literals(self, client):
        """The Freeport B surface over HTTP (Gate 5 criterion 6)."""
        payload = client.get("/api/audit/gv-basis",
                             params={"name": "freeport",
                                     "month": "2026-07"}).json()
        summary = payload["summary"]
        assert summary["gv_posted"] == pytest.approx(-7_071.48, abs=0.01)
        assert summary["basis_total"] == pytest.approx(229_209.66,
                                                       abs=0.01)
        assert summary["implied_rate_pct"] == pytest.approx(3.09, abs=0.01)
        assert summary["method"] == "percent_of_pgr"

    def test_recovery_drill_literals(self, client):
        """The Cedar Alt B surface over HTTP (Gate 5 criterion 6)."""
        tenant = "Bldg 1 Tenant (Confidential)"
        payload = client.get("/api/audit/recovery-drill",
                             params={"name": "cedar", "tenant": tenant,
                                     "segment_start": "2033-09"}).json()
        assert tenant in payload["tenants"]
        rows = _frame_from(payload["rows"])
        assert len(rows) > 0
        assert set(rows["tenant"]) == {tenant}
        first = rows.iloc[0]
        assert first["recovery"] == pytest.approx(173_504.82, abs=0.01)
        assert first["share"] == pytest.approx(0.803174, abs=1e-6)


class TestIntake:
    def test_import_returns_leases_and_notes(self, client, tmp_path):
        model = load_property(state.properties_dir()
                              / "freeport.icprop.json")
        template = tmp_path / "template.xlsx"
        export_rent_roll(run_property(model), path=template)
        with open(template, "rb") as handle:
            response = client.post(
                "/api/import/rent-roll",
                files={"file": ("template.xlsx", handle)})
        body = response.json()
        assert len(body["leases"]) == 29           # the Contractual subset
        assert len(body["notes"]) == 1
        assert "speculative" in body["notes"][0]   # never a silent skip

    def test_malformed_row_verbatim_readable(self, client, tmp_path):
        import openpyxl
        from engine.export.rent_roll_export import RENT_ROLL_COLUMNS
        model = load_property(state.properties_dir()
                              / "freeport.icprop.json")
        template = tmp_path / "bad.xlsx"
        export_rent_roll(run_property(model), path=template)
        wb = openpyxl.load_workbook(template)
        column = RENT_ROLL_COLUMNS.index("lease_type") + 1
        wb["Rent Roll"].cell(row=2, column=column).value = "offce"
        wb.save(template)
        with open(template, "rb") as handle:
            response = client.post(
                "/api/import/rent-roll",
                files={"file": ("bad.xlsx", handle)})
        assert response.status_code == 422
        summary = response.json()["error"]["summary"]
        assert "row 2" in summary and "'offce'" in summary   # Step-7 text
        assert "Traceback" not in response.text
        assert "pydantic" not in response.text.lower()


class TestGenerationsEndpoint:
    """The Freeport E surface over HTTP (owner-approved additive endpoint,
    rollout step 4) — the same literals the Streamlit panel test locks."""

    def test_freeport_e_literals(self, client):
        body = client.get("/api/tenants/generations",
                          params={"name": "freeport",
                                  "tenant": "Aqore LLC"}).json()
        rows = body["rows"]
        assert len(rows) == 3                      # contract + 2 rollovers
        contract, spec1, spec2 = rows
        assert contract["provenance"] == "Contractual"
        assert contract["renewal_weight"] == 1.0
        assert contract["lc"] == "" and contract["ti"] == ""
        for spec in (spec1, spec2):
            assert spec["provenance"] == "Speculative"
            assert spec["renewal_weight"] == 0.75
            assert spec["lc"] == "6.75% of rent"
            assert spec["ti"] == "12.5 dollars_per_area"

    def test_vacate_chain_single_contractual(self, client):
        body = client.get("/api/tenants/generations",
                          params={"name": "freeport",
                                  "tenant": "OKI Data Americas Inc."}).json()
        assert len(body["rows"]) == 1
        assert body["rows"][0]["provenance"] == "Contractual"

    def test_tenant_list_and_unknown_tenant(self, client):
        body = client.get("/api/tenants/generations",
                          params={"name": "freeport"}).json()
        assert "Aqore LLC" in body["tenants"] and body["rows"] == []
        response = client.get("/api/tenants/generations",
                              params={"name": "freeport",
                                      "tenant": "Nobody Inc."})
        assert response.status_code == 404
        assert "Nobody Inc." in response.json()["error"]["summary"]


class TestUiEditFlows:
    """The rollout-step-4 acceptance, proven at the API layer the UI
    drives: edit -> PUT -> reload identical -> recalculate changes the
    engine numbers (§25: the edit genuinely bites)."""

    def _year1_noi(self, client, name):
        body = client.post(f"/api/calculate/{name}").json()
        return body["summary"]["year1_noi"]

    def test_rent_step_edit_roundtrips_and_recalculates(self, client):
        document = client.get("/api/properties/clorox").json()["document"]
        baseline = self._year1_noi(client, "clorox")
        # the UI flow: add a rent step to the Clorox lease (month 13,
        # +50% — deliberately large so year-1 NOI must move)
        lease = document["rent_roll"][0]
        lease["rent_steps"].append({"date": "2027-01-01",
                                    "month_offset": None,
                                    "amount": 324_539.93,
                                    "pct_increase": None,
                                    "unit": "dollars_per_month"})
        assert client.put("/api/properties/clorox",
                          json=document).status_code == 200
        reloaded = client.get("/api/properties/clorox").json()["document"]
        assert reloaded == document                # round-trip identical
        edited = self._year1_noi(client, "clorox")
        assert edited != pytest.approx(baseline, abs=1.0)   # the edit bites
        # restore the fixture state for the other tests
        lease["rent_steps"].pop()
        client.put("/api/properties/clorox", json=document)
        assert self._year1_noi(client, "clorox") == pytest.approx(
            baseline, abs=1e-6)

    def test_variable_inflation_edit_recalculates(self, client):
        """The owner's 'variable rent growth': switch the general series
        to a per-year schedule and the out-year numbers move."""
        document = client.get("/api/properties/clorox").json()["document"]
        original = [dict(r) for r in document["inflation"]["general_rate"]]
        original_expense = [dict(r) for r in
                            document["inflation"]["expense_rate"]]
        baseline = client.get(
            "/api/reports/cash-flow",
            params={"name": "clorox", "period": "annual"}).json()
        noi_row = baseline["frame"]["index"].index("Net Operating Income")
        baseline_y3 = baseline["frame"]["data"][noi_row][2]
        document["inflation"]["expense_rate"] = [
            {"year": 2027, "rate": 3.0}, {"year": 2028, "rate": 12.0}]
        assert client.put("/api/properties/clorox",
                          json=document).status_code == 200
        client.post("/api/calculate/clorox")
        edited = client.get(
            "/api/reports/cash-flow",
            params={"name": "clorox", "period": "annual"}).json()
        edited_y3 = edited["frame"]["data"][noi_row][2]
        assert edited_y3 != pytest.approx(baseline_y3, abs=1.0)
        # restore
        document["inflation"]["general_rate"] = original
        document["inflation"]["expense_rate"] = original_expense
        client.put("/api/properties/clorox", json=document)
        client.post("/api/calculate/clorox")

    def test_bad_nested_edit_names_the_field(self, client):
        document = client.get("/api/properties/clorox").json()["document"]
        document["rent_roll"][0]["rent_steps"].append(
            {"date": "2027-01-01", "month_offset": None, "amount": 1.0,
             "pct_increase": 3.0, "unit": "dollars_per_month"})
        response = client.put("/api/properties/clorox", json=document)
        assert response.status_code == 422
        problems = response.json()["error"]["problems"]
        assert any("rent_steps" in p["field"] for p in problems)
        assert "Traceback" not in response.text


class TestStaticMount:
    def test_frontend_served_when_built(self, client):
        """The one-command launch (W2): / serves the built bundle."""
        dist = ROOT / "frontend" / "dist"
        if not (dist / "index.html").exists():
            pytest.skip("frontend/dist not built in this checkout")
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        # the API always wins over the static mount
        assert client.get("/api/properties").status_code == 200


class TestExports:
    def test_package_and_report_downloads(self, client):
        package = client.get("/api/export/package",
                             params={"name": "clorox"})
        assert package.status_code == 200
        assert package.content[:2] == b"PK"        # a real xlsx zip
        report = client.get("/api/export/report/cash-flow",
                            params={"name": "clorox"})
        assert report.status_code == 200
        assert report.content[:2] == b"PK"
