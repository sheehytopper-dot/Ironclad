// The Tier-1 display rules ported from ui/format.py (the reference
// implementation). DISPLAY ONLY — the front-end computes no financial
// numbers; every value arrives from the API at full precision, and a
// null (the API's NaN) renders as a blank em-dash, never 0.

export const EM_DASH = "—";

/** Accounting style: thousands separators, negatives in parentheses. */
export function money(value, decimals = 0) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return EM_DASH;
  }
  const absText = Math.abs(value).toLocaleString("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
  return value < 0 ? `(${absText})` : absText;
}

export function percent(value, decimals = 1, fromFraction = false) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return EM_DASH;
  }
  const scaled = fromFraction ? value * 100 : value;
  return `${scaled.toFixed(decimals)}%`;
}

/** Monetary display decimals by report unit (ui/format.unit_decimals). */
export function unitDecimals(unit) {
  return !unit || unit === "total" ? 0 : 2;
}

// Column-name rules mirrored from ui/format.py.
const FRACTION_COLUMNS = new Set(["occupancy", "share", "renewal_weight"]);
const PERCENT_COLUMNS = new Set([
  "pct_of_building", "implied_rate_pct", "occupancy_pct", "rate",
  "gross_up_pct", "admin_fee_pct",
]);
const PLAIN_COLUMNS = new Set([
  "fiscal_year", "year", "month_offset", "term_months", "expiring_leases",
  "number_of_spaces", "loan_index", "frequency_months",
  "interest_only_months",
]);

/** Format one cell by its column name (non-monetary frames). */
export function cell(value, columnName, decimals = 0) {
  if (value === null || value === undefined) return EM_DASH;
  if (typeof value !== "number") return String(value);
  const name = String(columnName).toLowerCase();
  if (FRACTION_COLUMNS.has(name)) return percent(value, 1, true);
  if (PERCENT_COLUMNS.has(name) || name.endsWith("_pct") ||
      name.includes("(%)")) {
    return percent(value, 2);
  }
  if (PLAIN_COLUMNS.has(name) || Number.isInteger(value)) {
    return String(value);
  }
  const cellDecimals = Number.isInteger(value)
    ? decimals : Math.max(decimals, 2);
  return money(value, cellDecimals);
}

/** True when the raw value is negative (for the red-paren class). */
export function isNegative(value) {
  return typeof value === "number" && value < 0;
}
