"""Unit tests for the Phase 4 Step 7 rent-roll importer
(engine/intake/rent_roll_import.py; spec §5.2 / §5.4).

Acceptance (NEXT_STEPS_TO_PHASE4 Step 7):
1. ROUND-TRIP — export_rent_roll then import reproduces the rent roll; per
   the DEVIATIONS §25 standing rule the test DISCRIMINATES: every field the
   template carries is asserted, and corrupting/dropping any field breaks
   the round-trip (proving the importer actually reads that column).
2. READABLE ERRORS — a malformed template yields a plain, row-level message
   (sheet, row, column, offending value, the fix); the tests assert the
   MESSAGE CONTENT, not merely that an exception was raised, and that it is
   not a raw pydantic stack trace.
"""
import datetime as dt

import openpyxl
import pytest

from engine.export import export_rent_roll
from engine.export.rent_roll_export import RENT_ROLL_COLUMNS
from engine.intake import (
    RentRollImportError,
    import_rent_roll,
    import_rent_roll_csv,
)
from engine.models import Lease, MoneyRate, MoneyUnit, RentStep, UponExpiration
from engine.models.profiles import MiscItemSpec

PSF = MoneyUnit.dollars_per_area_per_year


class _RentRoll:
    """A stand-in for the rent-roll portion of a PropertyModel (export_rent_
    roll only reads ``.rent_roll``)."""

    def __init__(self, leases):
        self.rent_roll = leases


def _sample_leases():
    acme = Lease(
        tenant_name="Acme Co", suite="100", external_id="EXT1", area=12_000,
        lease_type="industrial", start_date=dt.date(2026, 1, 1),
        term_months=120, base_rent=MoneyRate(amount=10.0, unit=PSF),
        upon_expiration=UponExpiration.vacate, status="contract",
        notes="anchor",
        rent_steps=[RentStep(month_offset=24, amount=11.0, unit=PSF),
                    RentStep(month_offset=60, pct_increase=3.0)],
        miscellaneous_items=[MiscItemSpec(name="Storage", amount=100.0,
                                          unit=MoneyUnit.dollars_per_month,
                                          free_rent_abates=True)])
    beta = Lease(
        tenant_name="Beta LLC", area=5_000, lease_type="office",
        start_date=dt.date(2026, 6, 1), end_date=dt.date(2031, 5, 31),
        base_rent=MoneyRate(amount=25.0, unit=PSF),
        market_leasing_profile="Office MLA",
        upon_expiration=UponExpiration.market)
    return [acme, beta]


def _assert_roundtrip(originals, imported) -> None:
    """Every flat field the template carries, asserted — raises
    AssertionError on any divergence (so the round-trip check can fail)."""
    assert len(imported) == len(originals)
    for o, g in zip(originals, imported):
        assert g.tenant_name == o.tenant_name
        assert g.suite == o.suite
        assert g.external_id == o.external_id
        assert g.area == o.area
        assert g.lease_type == o.lease_type
        assert g.status == o.status
        assert g.start_date == o.start_date
        assert g.end_date == o.end_date
        assert g.term_months == o.term_months
        assert g.base_rent.amount == o.base_rent.amount
        assert g.base_rent.unit == o.base_rent.unit
        assert g.upon_expiration == o.upon_expiration
        assert g.market_leasing_profile == o.market_leasing_profile
        assert g.notes == o.notes
        assert len(g.rent_steps) == len(o.rent_steps)
        for so, sg in zip(o.rent_steps, g.rent_steps):
            assert (sg.amount, sg.pct_increase, sg.unit, sg.month_offset,
                    sg.date) == (so.amount, so.pct_increase, so.unit,
                                 so.month_offset, so.date)
        assert len(g.miscellaneous_items) == len(o.miscellaneous_items)
        for mo, mg in zip(o.miscellaneous_items, g.miscellaneous_items):
            assert (mg.name, mg.amount, mg.unit, mg.free_rent_abates) == (
                mo.name, mo.amount, mo.unit, mo.free_rent_abates)


def _col(name: str) -> int:
    return RENT_ROLL_COLUMNS.index(name) + 1  # 1-indexed


def _write_cell(path, sheet, row, col_name, value):
    wb = openpyxl.load_workbook(path)
    wb[sheet].cell(row=row, column=_col(col_name)).value = value
    wb.save(path)


@pytest.fixture
def exported(tmp_path):
    leases = _sample_leases()
    path = tmp_path / "rent_roll.xlsx"
    export_rent_roll(_RentRoll(leases), path=path)
    return leases, path


class TestRoundTrip:
    def test_every_field_reproduced(self, exported):
        leases, path = exported
        _assert_roundtrip(leases, import_rent_roll(path))

    @pytest.mark.parametrize("col,new_value", [
        ("suite", "999"),
        ("external_id", "OTHER"),
        ("area", 99_999.0),
        ("lease_type", "office"),
        ("status", "speculative"),
        ("start_date", "2027-03-15"),
        ("term_months", 60),
        ("base_rent_amount", 12.5),
        ("base_rent_unit", "dollars_per_year"),
        ("upon_expiration", "market"),
        ("notes", "changed"),
    ])
    def test_corrupting_any_field_breaks_roundtrip(self, exported, col,
                                                   new_value):
        """DEVIATIONS §25 discrimination: change one field in the written
        template (Acme, row 2) to a different VALID value — the round-trip
        must no longer hold. Proves the importer actually reads that
        column (a check that passed regardless would not)."""
        leases, path = exported
        _write_cell(path, "Rent Roll", 2, col, new_value)
        with pytest.raises(AssertionError):
            _assert_roundtrip(leases, import_rent_roll(path))

    def test_dropping_optional_column_breaks_roundtrip(self, exported):
        """Deleting the 'notes' column header (optional) makes the importer
        read notes as blank → the round-trip fails on notes."""
        leases, path = exported
        wb = openpyxl.load_workbook(path)
        ws = wb["Rent Roll"]
        ws.cell(row=1, column=_col("notes")).value = None  # drop the header
        for r in (2, 3):
            ws.cell(row=r, column=_col("notes")).value = None
        wb.save(path)
        with pytest.raises(AssertionError):
            _assert_roundtrip(leases, import_rent_roll(path))

    def test_rent_step_corruption_breaks_roundtrip(self, exported):
        """The rent-step companion sheet is read: change Acme's first step
        amount and the round-trip fails."""
        leases, path = exported
        wb = openpyxl.load_workbook(path)
        wb["Rent Steps"].cell(row=2, column=2).value = 99.0  # amount col
        wb.save(path)
        with pytest.raises(AssertionError):
            _assert_roundtrip(leases, import_rent_roll(path))


class TestCsvRoundTrip:
    def test_csv_rent_roll_reproduces_flat_fields(self, tmp_path):
        leases = _sample_leases()
        rr = tmp_path / "rr.csv"
        steps = tmp_path / "steps.csv"
        misc = tmp_path / "misc.csv"
        import csv
        with open(rr, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(RENT_ROLL_COLUMNS)
            for lease in leases:
                w.writerow([
                    lease.tenant_name, lease.suite or "", lease.external_id or "",
                    lease.area, lease.lease_type.value, lease.status.value,
                    str(lease.start_date),
                    str(lease.end_date) if lease.end_date else "",
                    lease.term_months if lease.term_months else "",
                    lease.base_rent.amount, lease.base_rent.unit.value,
                    lease.upon_expiration.value,
                    lease.market_leasing_profile or "", lease.notes or ""])
        with open(steps, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["tenant_name", "amount", "unit", "pct_increase",
                        "date", "month_offset"])
            w.writerow(["Acme Co", 11.0, PSF.value, "", "", 24])
            w.writerow(["Acme Co", "", "", 3.0, "", 60])
        with open(misc, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["tenant_name", "name", "amount", "unit",
                        "free_rent_abates"])
            w.writerow(["Acme Co", "Storage", 100.0, "dollars_per_month",
                        "true"])
        imported = import_rent_roll_csv(rr, steps_path=steps, misc_path=misc)
        _assert_roundtrip(leases, imported)


class TestReadableErrors:
    def _errors(self, exported, edits) -> list[str]:
        _leases, path = exported
        for row, col, value in edits:
            _write_cell(path, "Rent Roll", row, col, value)
        with pytest.raises(RentRollImportError) as excinfo:
            import_rent_roll(path)
        return excinfo.value.errors

    def test_bad_enum_message_names_row_column_value_and_fix(self, exported):
        errors = self._errors(exported, [(2, "lease_type", "offce")])
        assert len(errors) == 1
        msg = errors[0]
        assert "Rent Roll sheet" in msg and "row 2" in msg
        assert "lease_type" in msg
        assert "'offce'" in msg                       # the offending value
        assert "office, industrial, retail" in msg    # the valid values / fix

    def test_negative_area_message(self, exported):
        errors = self._errors(exported, [(2, "area", -500)])
        assert any("area" in m and "positive" in m and "row 2" in m
                   for m in errors)

    def test_non_numeric_area_message(self, exported):
        errors = self._errors(exported, [(3, "base_rent_amount", "abc")])
        assert any("base_rent_amount" in m and "not a number" in m
                   and "row 3" in m for m in errors)

    def test_all_errors_collected_not_just_first(self, exported):
        errors = self._errors(exported, [(2, "lease_type", "bad"),
                                         (3, "area", -1)])
        assert len(errors) >= 2  # both rows reported, not first-fail

    def test_missing_required_column_named(self, exported):
        _leases, path = exported
        wb = openpyxl.load_workbook(path)
        wb["Rent Roll"].cell(row=1, column=_col("area")).value = None  # drop
        wb.save(path)
        with pytest.raises(RentRollImportError) as excinfo:
            import_rent_roll(path)
        assert any("area" in m and "missing" in m for m in excinfo.value.errors)

    def test_cross_field_rule_translated_readably(self, exported):
        """A row with neither term_months nor end_date trips the Lease
        cross-field validator — its message must be translated to a
        row-level line, not surfaced as a pydantic dump."""
        _leases, path = exported
        _write_cell(path, "Rent Roll", 2, "term_months", None)  # Acme had term
        with pytest.raises(RentRollImportError) as excinfo:
            import_rent_roll(path)
        joined = "\n".join(excinfo.value.errors)
        assert "row 2" in joined
        assert "end_date" in joined and "term_months" in joined

    def test_error_surface_is_readable_not_a_stack_trace(self, exported):
        errors = self._errors(exported, [(2, "lease_type", "offce")])
        text = str(RentRollImportError(errors))
        assert "Traceback" not in text
        assert "pydantic" not in text.lower()
        assert "could not be imported" in text
        assert "- Rent Roll sheet" in text  # the bulleted, human list
