// The ported Tier-1 display rules, §25-style: the display string is
// right AND null (the API's NaN) renders as an em-dash, never 0.
// Run: npm test (node --test; no test-framework dependency).
import assert from "node:assert/strict";
import { test } from "node:test";
import { cell, isNegative, money, percent, unitDecimals }
  from "../src/format.js";

test("money: thousands + accounting negatives (the Clorox literal)", () => {
  assert.equal(money(2596319.4000000004), "2,596,319");
  assert.equal(money(-331574.4), "(331,574)");
  assert.equal(money(4.8083, 2), "4.81");
});

test("null renders as em-dash, never 0", () => {
  assert.equal(money(null), "—");
  assert.equal(money(undefined), "—");
  assert.equal(percent(null), "—");
  assert.equal(cell(null, "anything"), "—");
});

test("percent incl. fraction scaling", () => {
  assert.equal(percent(3.0864, 2), "3.09%");
  assert.equal(percent(0.803174, 1, true), "80.3%");
});

test("unit decimals: total 0, per-SF 2", () => {
  assert.equal(unitDecimals("total"), 0);
  assert.equal(unitDecimals("per_sf"), 2);
});

test("cell column rules (fraction/percent/plain-year)", () => {
  assert.equal(cell(1.0, "occupancy"), "100.0%");
  assert.equal(cell(6.75, "gross_up_pct"), "6.75%");
  assert.equal(cell(2027, "fiscal_year"), "2027");   // no thousands comma
  assert.equal(cell(123099.0, "area"), "123099");    // integer-valued
  assert.equal(cell(7.1512, "base_rent"), "7.15");
});

test("negative detection for the red-paren class", () => {
  assert.equal(isNegative(-1), true);
  assert.equal(isNegative(1), false);
  assert.equal(isNegative(null), false);
});
