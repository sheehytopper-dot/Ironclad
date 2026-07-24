// Pure document-assembly helpers for the editors (rollout step 4).
// The front-end computes NO numbers — these reshape PropertyModel JSON;
// blanks become null so the API's own validators judge them, and the
// whole document is PUT for revalidation (docs/SCHEMA_GUIDE.md is the
// field reference).

export function deepClone(value) {
  return value === undefined ? undefined
    : JSON.parse(JSON.stringify(value));
}

/** "" -> null; numeric-looking text -> number for numeric columns;
    non-numeric text passes through so the API's 422 names it. */
export function coerceValue(text, kind) {
  if (text === "" || text === null || text === undefined) return null;
  if (kind === "number") {
    const value = Number(text);
    return Number.isNaN(value) ? text : value;
  }
  if (kind === "bool") return text === true || text === "true";
  return text;
}

/** Editor rows -> model rows: coerce each configured column, DROP rows
    blank in every configured column, and PRESERVE any unconfigured keys
    the original row carried (nested detail survives a grid edit). */
export function cleanRows(rows, columns) {
  const keys = columns.map((column) => column.key);
  return rows
    .filter((row) => keys.some((key) => {
      const value = row[key];
      return value !== null && value !== undefined && value !== "";
    }))
    .map((row) => {
      const next = { ...row };
      columns.forEach(({ key, kind }) => {
        next[key] = coerceValue(row[key] ?? null, kind);
      });
      return next;
    });
}

/** A flat single rate as a one-row YearRate schedule (the "flat" side of
    the flat/variable toggle); `year` keeps the schedule's existing first
    year so calendar-year models stay calendar-year. */
export function flatSchedule(rate, existing) {
  const year = existing?.length ? existing[0].year : 1;
  return [{ year, rate: coerceValue(rate, "number") }];
}

export function isFlat(schedule) {
  return Array.isArray(schedule) && schedule.length === 1;
}

// ---- schema enums (SCHEMA_GUIDE.md; presentation lists only) --------
export const RENT_UNITS = ["dollars_per_area_per_year",
                           "dollars_per_area_per_month", "dollars_per_year",
                           "dollars_per_month"];
export const STEP_UNITS = [...RENT_UNITS, "pct_of_market"];
export const RENEW_UNITS = [...RENT_UNITS, "pct_of_last_rent"];
export const TI_UNITS = ["dollars_per_area", "dollars"];
export const MISC_UNITS = ["dollars_per_month", "dollars_per_year",
                           "dollars_per_area_per_year",
                           "dollars_per_area_per_month"];
export const LEASE_TYPES = ["office", "industrial", "retail"];
export const LEASE_STATUSES = ["contract", "speculative", "mtm"];
export const UPON_EXPIRATION = ["market", "option", "renew", "vacate",
                                "reabsorb"];
export const CPI_METHODS = ["full_cpi", "pct_of_cpi", "cpi_plus_pct",
                            "min_max_banded"];
export const RECOVERY_METHODS = ["none", "net", "base_stop", "base_year",
                                 "base_year_plus_1", "fixed", "structure"];
export const DEPOSIT_UNITS = ["months_of_rent", "dollars",
                              "dollars_per_area"];
export const VACANCY_METHODS = ["none", "percent_of_pgr",
                                "percent_of_scheduled_base_plus",
                                "percent_of_total_tenant_revenue"];
export const TIMING_BASES = ["analysis_year", "calendar_year"];
export const RENEWAL_RULES = ["market", "prior", "lesser_of", "greater_of"];
//: the six PGR component account names (spec §2.3 ledger lines)
export const PGR_ACCOUNTS = [
  "Scheduled Base Rental Revenue", "CPI & Other Adjustment Revenue",
  "Percentage Rent", "Expense Recovery Revenue",
  "Miscellaneous Tenant Revenue",
  "Parking / Storage / Miscellaneous Property Revenue"];

export const STEP_COLUMNS = [
  { key: "date", label: "Date (YYYY-MM-DD)", kind: "text" },
  { key: "month_offset", label: "…or month #", kind: "number" },
  { key: "amount", label: "Amount", kind: "number" },
  { key: "pct_increase", label: "…or % incr.", kind: "number" },
  { key: "unit", label: "Unit", kind: "select", options: STEP_UNITS },
];
export const YEAR_RATE_COLUMNS = [
  { key: "year", label: "Year", kind: "number" },
  { key: "rate", label: "Rate %", kind: "number" },
];
export const MISC_ITEM_COLUMNS = [
  { key: "name", label: "Name", kind: "text" },
  { key: "amount", label: "Amount", kind: "number" },
  { key: "unit", label: "Unit", kind: "select", options: MISC_UNITS },
  { key: "free_rent_abates", label: "Abates w/ free rent", kind: "bool" },
];
export const OVERRIDE_COLUMNS = [
  { key: "tenant_ref", label: "Tenant", kind: "text" },
  { key: "exclude", label: "Exclude", kind: "bool" },
];
export const FREE_RENT_PROFILE_COLUMNS = [
  { key: "name", label: "Name", kind: "text" },
  { key: "abate_base_rent", label: "Abates base rent", kind: "bool" },
  { key: "abate_recoveries", label: "Abates recoveries", kind: "bool" },
  { key: "abate_miscellaneous", label: "Abates misc", kind: "bool" },
];

/** A minimal valid new MLP (the detail editor fills real economics). */
export function newMlpTemplate() {
  return {
    name: "New MLP", term_months: 60, renewal_probability: 50.0,
    months_vacant: 0.0,
    market_base_rent_new: { amount: 0.0,
                            unit: "dollars_per_area_per_year" },
    market_base_rent_renew: { pct_of_new: 100.0 },
  };
}
