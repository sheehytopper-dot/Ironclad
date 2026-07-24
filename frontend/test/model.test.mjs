// The document-assembly helpers (rollout step 4), §25-style: blanks
// become null (the API's validators judge them), blank rows drop, and
// unconfigured nested keys SURVIVE a grid edit.
import assert from "node:assert/strict";
import { test } from "node:test";
import {
  STEP_COLUMNS, YEAR_RATE_COLUMNS, cleanRows, coerceValue, flatSchedule,
  isFlat,
} from "../src/model.js";

test("coerceValue: blank -> null; numeric text -> number; junk passes", () => {
  assert.equal(coerceValue("", "number"), null);
  assert.equal(coerceValue("3.5", "number"), 3.5);
  assert.equal(coerceValue("soon", "number"), "soon"); // API names it
  assert.equal(coerceValue("true", "bool"), true);
});

test("cleanRows: blank rows drop, values coerce", () => {
  const rows = [
    { date: "2027-01-01", month_offset: "", amount: "27.5",
      pct_increase: "", unit: "dollars_per_area_per_year" },
    { date: "", month_offset: "", amount: "", pct_increase: "", unit: "" },
  ];
  const clean = cleanRows(rows, STEP_COLUMNS);
  assert.equal(clean.length, 1);
  assert.equal(clean[0].amount, 27.5);
  assert.equal(clean[0].month_offset, null);
});

test("cleanRows preserves unconfigured nested keys", () => {
  const rows = [{ year: "2027", rate: "3.0",
                  nested: { keep: "me" } }];
  const clean = cleanRows(rows, YEAR_RATE_COLUMNS);
  assert.equal(clean[0].year, 2027);
  assert.deepEqual(clean[0].nested, { keep: "me" });
});

test("flat/variable schedule toggle keeps the calendar year", () => {
  const calendar = [{ year: 2027, rate: 3.0 }, { year: 2028, rate: 3.5 }];
  const flat = flatSchedule("4.0", calendar);
  assert.deepEqual(flat, [{ year: 2027, rate: 4.0 }]);
  assert.equal(isFlat(flat), true);
  assert.equal(isFlat(calendar), false);
  assert.deepEqual(flatSchedule("2", null), [{ year: 1, rate: 2 }]);
});
