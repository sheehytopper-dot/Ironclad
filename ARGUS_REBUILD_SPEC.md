# PROJECT IRONCLAD: Commercial Real Estate DCF Platform
## Complete Build Specification v1.0

**Purpose:** Recreate the single-asset commercial cash flow, valuation, and reporting engine of ARGUS Enterprise 11.0 (office, industrial, retail; US-style modeling) as a modern web application with a Python calculation engine, interactive dashboards, full audit reporting, and Excel export packages.

**Authoritative reference:** `reference/Argus_Training_Guide.pdf` (ARGUS Enterprise 11.0 Product User Manual, 1,056 pp). This spec cites manual page ranges throughout as `[AE pp. x-y]`. Where this spec and the manual conflict on calculation behavior, the manual governs. The manual is a reference for functional behavior only; do not copy its text into the product, its UI, or documentation.

**Naming/legal:** The product must not be named or marketed as "Argus." Functionality and financial-modeling conventions are not protected; the trademark and the manual's text are. Do not implement read/write of proprietary `.aeex`/`.aeix` binary formats; use our own open JSON schema.

---

# 1. SCOPE

## 1.1 In scope (v1)
- Single property assets: Office, Industrial, Retail (US-style DCF modeling)
- Monthly cash flow projection engine, analysis terms of 1 to 30 years (up to 100 years supported)
- Rent roll with full lease mechanics: base rent with steps, CPI increases, free rent, recoveries (all standard methods plus custom structures), percentage rent, miscellaneous tenant items, TIs, LCs, security deposits
- Market leasing profiles with renewal-probability blending ("intelligent renewals") and rollover chains
- Space absorption for vacant space lease-up
- General vacancy and credit loss with tenant overrides
- Miscellaneous, parking, and storage revenues
- Operating, non-operating, and capital expenses with all amount/unit/timing types
- Property purchase and closing costs
- Debt: multiple loans, fixed and floating rate, interest-only and amortizing, loan costs
- Valuation: DCF present value, unleveraged and leveraged IRR, direct capitalization, property resale with multiple calculation methods
- Sensitivity matrices: IRR matrix, value matrix, resale matrix
- Full report catalog (Section 7) with $/SF and per-unit toggles
- Excel export of every report and a combined "result package" workbook
- Scenario support: duplicate a property into scenario variants and compare
- Web UI with property editor, dashboards, and report viewers

## 1.2 Out of scope (v1) — do not build, do not scaffold
- Hotels (departmental revenues, ADR/RevPAR) [AE pp. 297-311, 346-359]
- Multifamily unit-based modeling [AE pp. 263-267, 414-419]
- UK/European Traditional Valuation (term & reversion, hardcore/layer, froth, sinking funds) [AE pp. 477-486]
- Ground leases with gearing [AE pp. 423-430] (flat ground rent may be modeled as a non-operating expense)
- Portfolio server infrastructure: check-in/check-out, permissions/security, workflow status, batch update, archiving [AE pp. 70-109]
- Budgeting and actuals / variance reforecasting [AE pp. 211-217, 487-503] (v2 candidate)
- Multi-currency (single currency per property; USD default)
- GAAP straight-line rent reporting [AE p. 375] (v1.1 candidate; trivial once cash rent ledger exists)
- **In-app OM/document ingestion — cancelled entirely (not deferred: no version target, ever).**
  Do not scaffold it or reference it as future work. The application has exactly two intake
  surfaces (§5.4): loading a PropertyModel JSON document and importing the rent roll template.
  How a PropertyModel JSON gets created is permanently outside the application's scope;
  extraction from OMs or other documents happens in external workflows the app knows nothing
  about, supported by the schema documentation in §5.1.

## 1.3 Design principles
1. **Engine before UI.** The calculation engine is a standalone, headless Python package with zero UI dependencies. The UI is a client of the engine.
2. **Everything is monthly.** The canonical ledger is monthly. Annual, quarterly, and fiscal-year views are aggregations of the monthly ledger, never separately computed.
3. **No silent numbers.** Every reported line item must be traceable to inputs via audit endpoints (the engine returns per-tenant, per-month detail for any account).
4. **Deterministic and testable.** Same inputs always produce identical outputs. Every calculation module ships with unit tests reproducing the manual's worked examples.
5. **Open data.** Property models serialize to human-readable JSON. Rent rolls import/export via a defined Excel/CSV template.

---

# 2. ARCHITECTURE

## 2.1 Stack
| Layer | Technology | Rationale |
|---|---|---|
| Calculation engine | Python 3.11+, `numpy`, `pandas` | Vectorized monthly ledgers; testability |
| Data schema/validation | `pydantic` v2 | Typed input models, JSON serialization, validation errors surfaced to UI |
| Persistence | JSON files per property + SQLite index (via `sqlmodel`) | Simple, portable, Git-friendly; no server dependency |
| API | FastAPI | Clean engine/UI separation; enables future integrations |
| UI | Streamlit (v1) | Fastest path to grids, dashboards, toggles for a solo builder; swap to React possible later because the API layer isolates the engine |
| Charts | Plotly | Interactive dashboards inside Streamlit |
| Excel export | `xlsxwriter` (writing), `openpyxl` (templates/reading) | Formatted multi-tab packages |
| PDF export | Report HTML → `weasyprint` (v1.1; Excel export is the v1 requirement) | |
| Testing | `pytest`, golden-file fixtures | Validation against real ARGUS output exports |

## 2.2 Repository layout
```
ironclad/
  engine/                  # pure calculation package (no UI imports)
    models/                # pydantic input models (Section 3)
    calc/
      timeline.py          # month index, date math, fiscal handling
      inflation.py
      leases.py            # lease projection incl. rollover chains
      recoveries.py
      percentage_rent.py
      revenues.py          # misc/parking/storage
      expenses.py
      vacancy.py           # general vacancy + credit loss
      absorption.py
      debt.py
      resale.py
      valuation.py         # PV, IRR, direct cap
      sensitivity.py
      ledger.py            # account tree, monthly ledger assembly
      run.py               # orchestrates full property calculation
    reports/               # report builders returning DataFrames + metadata
    export/                # Excel package builder
  api/                     # FastAPI app
  ui/                      # Streamlit app
  data/
    properties/            # saved property JSON files
    templates/             # rent roll import template.xlsx
  docs/
    SCHEMA_GUIDE.md        # human-readable PropertyModel JSON guide (for external producers, §5.1)
    property_model.schema.json  # formal JSON Schema export (§5.1)
  scripts/
    export_json_schema.py  # regenerates property_model.schema.json
  reference/
    Argus_Training_Guide.pdf
  tests/
    unit/                  # per-module tests incl. manual worked examples
    golden/                # ARGUS export fixtures + comparison tests
  CLAUDE.md                # build instructions for Claude Code
```

## 2.3 The canonical ledger
The engine's central data structure is the **Monthly Ledger**: a pandas DataFrame indexed by month (Period[M]) from Analysis Begin Date through `analysis_end + 12 months` (extra year required for resale NOI look-forward), with one column per account. Accounts form a tree (Chart of Accounts [AE pp. 197-210]):

```
Potential Gross Revenue
  Base Rental Revenue          (sum of tenant base rent at market-implied full occupancy)
  Absorption & Turnover Vacancy  (negative: downtime months from rollover/absorption)
  Scheduled Base Rental Revenue
  CPI & Other Adjustment Revenue
  Free Rent                    (negative)
  Expense Recovery Revenue     (per structure detail retained)
  Percentage Rent
  Miscellaneous Tenant Revenue
  Parking / Storage / Miscellaneous Property Revenue
Total Potential Gross Revenue
  General Vacancy              (negative)
  Credit Loss                  (negative)
Effective Gross Revenue
  Operating Expenses           (one line per expense; groups supported)
Net Operating Income
  Tenant Improvements
  Leasing Commissions
  Capital Expenses
Cash Flow Before Debt Service
  Debt Funding / Draws
  Interest / Principal / Loan Costs (per loan)
Cash Flow After Debt Service
Non-Operating Expenses (below the line)
Cash Flow Available for Distribution
```
Line names and ordering must match the ARGUS Cash Flow report [AE pp. 535-539] so his existing Argus outputs diff cleanly against ours.

---

# 3. DATA MODEL (INPUT SCHEMA)

Every model below is a pydantic class serialized inside one `PropertyModel` JSON document. Field names given here are normative. Enumerations list all allowed values. Manual page cites identify the section a developer should read for edge-case behavior.

## 3.1 Property [AE pp. 182-187]
```
property:
  name: str
  external_id: str | None
  property_type: enum {office, industrial, retail, mixed}
  address: {street, city, state, zip}                # display only
  analysis_begin: date            # first day of a month; all timing snaps to months
  analysis_term_years: int        # 1-30 typical; engine supports up to 100
  fiscal_year_end_month: int = 12 # for fiscal-year report aggregation
  currency: "USD"
  area_unit: "SF"
```

## 3.2 Area Measures [AE pp. 188-196]
```
area_measures:
  property_size: float            # gross building area, SF
  alternate_size: float | None
  # Rentable Area: default = sum of rent roll + absorption areas ("Derive from tenants"),
  #   or user override (fixed schedule over time allowed: list[{date, area}])
  rentable_area_mode: enum {derived, fixed, schedule}
  rentable_area_fixed: float | None
  rentable_area_schedule: list[{date, area}] | None
  # Occupied Area is always computed by the engine (never input)
```
**Logic:** Pro-rata share denominators for recoveries reference either Property Size, Rentable Area, or an alternate measure per recovery structure (3.14). Occupancy % = occupied area / rentable area per month.

## 3.3 Inflation [AE pp. 219-223]
```
inflation:
  general_rate: list[YearRate]        # annual %; per-analysis-year or calendar-year
  market_rent_rate: list[YearRate] | None    # defaults to general
  expense_rate: list[YearRate] | None
  cpi_rate: list[YearRate] | None
  custom_indices: list[{name, rates: list[YearRate]}]   # assignable anywhere an inflation picker exists
  inflation_month: int = analysis_begin month   # month in which annual inflation compounds
  timing_basis: enum {analysis_year, calendar_year}
```
**Logic:** Inflation factor for month m = Π(1 + rate_y) over completed inflation anniversaries before m. Mid-year analysis starts must respect `inflation_month` (rates step on that month, not necessarily January). Any monetary input can override its inflation index with a named index or explicit rate.

## 3.4 General Vacancy [AE pp. 224-228]
```
general_vacancy:
  method: enum {percent_of_pgr, percent_of_scheduled_base_plus, percent_of_total_tenant_revenue, none}
  rate: list[YearRate]                       # can vary by year
  include_in_pgr_accounts: list[account_id]  # which revenue lines the % applies to
  reduce_by_absorption_turnover: bool = true # avoid double-counting downtime vacancy
  tenant_overrides: list[{tenant_ref, exclude: bool}]   # exclude specific tenants (e.g., credit tenants)
```
**Logic (critical, frequently misimplemented):** When `reduce_by_absorption_turnover` is true, monthly General Vacancy = max(0, target_vacancy_amount − absorption_and_turnover_vacancy_already_in_ledger). This mirrors ARGUS's default so total vacancy equals the stated rate rather than stacking rollover downtime on top of the general rate. Tenant overrides remove those tenants' revenue from the base before applying the %.

## 3.5 Credit Loss [AE pp. 229-232]
Same structure as General Vacancy (method, rate schedule, tenant overrides). Applied after General Vacancy on the reduced base. No interaction with absorption vacancy.

## 3.6 Market Leasing Profiles (MLP) [AE pp. 233-252]
The heart of speculative renewal modeling. Each profile:
```
market_leasing_profile:
  name: str
  term_months: int                       # market lease term
  renewal_probability: float             # 0-100%
  months_vacant: float                   # downtime before a NEW lease (weighted: see blending)
  market_base_rent_new: MoneyRate        # unit types: $/SF/yr, $/SF/mo, $/yr, $/mo, % of last rent
  market_base_rent_renew: MoneyRate | {pct_of_new: float}
  rent_increases: RentStepSpec | None    # applied within the speculative lease term
  free_rent_months_new: float
  free_rent_months_renew: float
  free_rent_profile: ref | None          # which charges free rent abates [AE pp. 253-254]
  recoveries: {method: recovery assignment for speculative leases}
  ti_new: MoneyRate; ti_renew: MoneyRate           # $/SF or $ amounts [AE pp. 245]
  lc_new: MoneyRate|pct; lc_renew: MoneyRate|pct   # % of rent (which years) or $/SF [AE pp. 246-248]
  security_deposit: spec | None
  miscellaneous_items: list[MiscItemSpec]          # rollover-carried tenant misc [AE pp. 240-244]
  percentage_rent: PercentRentSpec | None          # for retail speculative leases [AE pp. 249-250]
  upon_expiration: enum {market(reuse this profile), option(chain to another profile), renew, vacate, reabsorb}
  chained_profile: ref | None
  term_growth: inflate market rents by market_rent inflation index
```
**Blending logic ("Intelligent Renewals," weighted items) [AE pp. 235-236]:** When a lease expires with `upon_expiration = market` and renewal probability p:
- Weighted market rent = p × renew_rent + (1−p) × new_rent
- Weighted downtime = (1−p) × months_vacant (renewals have zero downtime)
- Weighted free rent = p × free_new? No: p × free_renew + (1−p) × free_new
- Weighted TI = p × ti_renew + (1−p) × ti_new; same for LC
- The speculative lease begins after weighted downtime, runs `term_months`, then chains per `upon_expiration` (repeating until analysis end + resale horizon).
- Intelligent Renewals option: if enabled and the contract rent at expiration exceeds weighted market, ARGUS can force renew at market or apply modified behavior; implement the manual's stated toggle behavior [AE p. 235].
Downtime months post as Absorption & Turnover Vacancy (negative revenue at the rate the space would have earned), not as zero revenue, so PGR reflects full occupancy [ledger design, Section 2.3].

## 3.7 CPI Increases [AE pp. 255-257]
```
cpi_spec:
  index: ref (cpi_rate or custom)
  method: enum {full_cpi, pct_of_cpi, cpi_plus_pct, min_max_banded}
  first_increase_month: int | anniversary
  frequency_months: int = 12
  cap_pct: float | None; floor_pct: float | None
```
Applies to contract leases (rent roll flag) and speculative leases (via MLP). Posts to "CPI & Other Adjustment Revenue."

## 3.8 Free Rent Profiles [AE pp. 253-254]
Named profiles defining which charge types abate during free months: base rent only, or base + recoveries + misc. Rent roll and MLPs reference by name.

## 3.9 TI and LC Categories [AE pp. 258-262]
Named specs for improvement allowances ($/SF new/renew, inflated by chosen index, paid at lease start or spread) and commission categories (% of first-year rent, % of total lease value, fixed $/SF, tiered by year: e.g., 6% yr 1, 3% yrs 2+; payable timing: lease start, split start/occupancy). Elements-to-include flags define whether commissions calculate on base rent only or base + escalations.

## 3.10 Miscellaneous / Parking / Storage Revenues [AE pp. 273-296]
Common structure (three named collections):
```
property_revenue:
  name; account: ref
  amount: float
  unit: enum {dollars_per_year, dollars_per_month, dollars_per_area_per_year, dollars_per_area_per_month,
              pct_of_egr, pct_of_pgr, pct_of_account(ref), per_occupied_area, per_available_area,
              number_of_spaces × rate (parking)}
  frequency/timing: enum {continuous, date_range(start,end), repeating(pattern)} [AE pp. 278, 361-362]
  inflation: index ref | explicit rates | none
  pct_fixed: float = 100     # variable portion scales with occupancy
  limits: {min, max per period} [AE p. 279]
```
Percent-of-account types create calculation dependencies; the ledger resolves via ordered passes (Section 4.1).

## 3.11 Operating / Non-Operating / Capital Expenses [AE pp. 313-345]
Same amount/unit/timing/inflation structure as 3.10 plus:
```
  pct_fixed: float           # % fixed vs variable with occupancy; variable portion = amount × occupancy%
  recoverable: bool + recovery pool membership (default: operating expenses recoverable, capital/non-op not)
  expense_groups: for reporting rollups [AE pp. 343-345]
  capex only: amortization option (recover over N years in recoveries) [AE p. 338]
  capex only: refundable/timing nuances [AE pp. 331-341]
```
**Occupancy gross-up interaction:** the variable portion responds to physical occupancy; recovery structures may then gross variable expenses up to a stipulated occupancy (3.14).

## 3.12 Rent Roll (contract leases) [AE pp. 363-390]
One record per lease/suite:
```
lease:
  tenant_name; suite; external_id
  area: float                # SF; area changes over time via linked records allowed (v1: single area)
  lease_type: enum {office, industrial, retail}   # drives report grouping + cap valuation treatment
  start_date; end_date       # or start + term months
  status: enum {contract, speculative, mtm}
  base_rent: {amount, unit: {$/SF/yr, $/SF/mo, $/yr, $/mo, pct_of_market}}   # [AE pp. 367-373; calc examples p. 391]
  rent_steps: list[{date | month_offset, amount|pct_increase, unit}]         # fixed steps or % bumps
  cpi: cpi_spec | None [AE p. 374]
  free_rent: {months, timing: front|custom list of months, profile ref} 
  recoveries: recovery_assignment (Section 3.14)
  percentage_rent: PercentRentSpec | None (Section 3.13)
  miscellaneous_items: list[MiscItemSpec]     # per-tenant charges/abatements [AE pp. 378-382]
  leasing_costs: {ti: spec|ref, lc: spec|ref} # for the contract term (usually zero; costs on rollover come from MLP)
  security_deposit: spec | None [AE p. 384; pp. 431-433]
  market_leasing_profile: ref                 # governs behavior at expiration [AE p. 385]
  upon_expiration: enum {market, renew, vacate, reabsorb, option(ref)} 
  tenant_classifications: dict                # custom tags for grouping/reports
  notes: str
```
**Base rent calc examples are normative** [AE pp. 391-394]: implement each worked example as a unit test (amount per SF/yr, per SF/mo, per yr, per mo, % of market, % of market with steps).

## 3.13 Percentage Rent (retail) [AE pp. 249-250, 376]
```
percent_rent:
  sales_volume: {amount, unit: $/yr | $/SF/yr, growth: index ref}
  breakpoint: enum {natural, fixed_amount, zero}
  breakpoint_layers: up to 6 {breakpoint_amount, pct}   # tiered overage
  natural_breakpoint = annual base rent / layer pct
  offset/recapture rules: pct rent payable = Σ max(0, sales − breakpoint) × pct per layer
```

## 3.14 Recovery Structures [AE pp. 404-413, 517-520]
System methods (assignable directly on a lease): `none`, `net` (100% pro-rata of recoverable expenses), `base_stop` (recover over a $/SF stop), `base_year` (recover over actual expenses of a named calendar/fiscal year, with base-year value frozen and optionally grossed up), `base_year_plus_1`, `fixed` ($ or $/SF amount, inflatable).
User-defined structures:
```
recovery_structure:
  name
  pools: list[{expenses: list[account refs] | expense groups,
               method: {net, stop, base_year, fixed},
               gross_up_pct: float | None,        # gross variable expenses to e.g. 95% occupancy [AE p. 407]
               base_amount | base_year: spec,
               admin_fee_pct: float, admin_fee_applies: {before|after stop} [AE p. 520],
               denominator: enum {rentable_area, property_size, occupied_area, fixed_area},
               pro_rata_share_override: float | None}]
  caps_floors: {yearly_cap_pct (YoY), cumulative_cap_pct, min, max} per pool [AE pp. 411-412]
  expense_adjustments: exclusions/additions per pool [AE p. 410]
```
**Gross-up formula:** grossed expense = fixed_portion + variable_portion × (gross_up_pct / actual_occupancy_pct) when actual < gross_up target; never gross down. Tenant recovery = (pool expense after adjustments − tenant's stop/base) × pro-rata share, floored at 0, capped per caps. Recovery revenue posts monthly as 1/12 of the annualized computation with a true-up in the reconciliation month (v1: straight monthly accrual is acceptable; flag as a policy toggle).

## 3.15 Space Absorption [AE pp. 395-403]
Lease-up of currently vacant space:
```
absorption:
  total_area; number_of_leases | area_per_lease
  start_date; interval_months between lease starts
  market_leasing_profile: ref     # or inline lease terms mirroring rent roll fields
```
Generates synthetic leases on the schedule; each behaves like a rent roll lease thereafter (rollover chains etc.).

## 3.16 Investment: Purchase & Closing [AE pp. 435-437]
```
purchase:
  price: float | derived_from_valuation (toggle: price = PV at discount rate, or direct cap)
  date: date = analysis_begin
  closing_costs: list[{name, amount|pct_of_price, timing}]
```

## 3.17 Debt [AE pp. 438-449]
```
loan:
  name; type: enum {fixed, floating}
  amount: float | pct_of_price | pct_of_value
  funding_date; maturity: date | term_months
  rate: float | {index: rate_schedule list[YearRate], spread}   # floating = index + spread, monthly reset
  interest_only_months: int
  amortization_years: int | interest_only | fully_amortizing
  payment_frequency: monthly
  additional_principal: list[{date, amount}] [AE p. 444]
  loan_costs: {points_pct, fees, timing, amortize_or_expense} [AE pp. 445-446]
  # Standard mortgage math: payment = P × r / (1 − (1+r)^−n), r = annual/12
```
Multiple loans supported; "Other Debt" simple interest lines [AE pp. 448-449] as fixed payment streams.

## 3.18 Valuation Inputs [AE pp. 450-476]
```
valuation:
  discount_rate: float                     # unleveraged; annual nominal
  discount_method: enum {annual, monthly, quarterly}   # period discounting [AE pp. 472-473]
  period_convention: enum {end_of_period, mid_period}
  pv_start: date = analysis_begin
  direct_cap: {cap_rate, noi_basis: enum {year_1, forward_12}, results} [AE pp. 453-454]
  resale: 
    method: enum {cap_noi_forward_12, cap_noi_current_year, gross_value_less_costs, fixed_amount, pct_increase_over_price} [AE pp. 464-471]
    exit_cap_rate: float
    resale_date: end_of_term (default) | custom
    noi_adjustments: {exclude_capital: bool=true, stabilize_occupancy: spec | None [AE p. 468]}
    selling_costs_pct: float
    adjustment_amounts: list [AE p. 469]
    apply_resale_to_cash_flow: bool
  sensitivity_intervals: {discount_rate_step, cap_rate_step, count: 5|7} [AE pp. 451-452]
```

---

# 4. CALCULATION ENGINE LOGIC

## 4.1 Order of operations (per property calculation run)
Dependencies force this sequence. Implement as discrete passes over the monthly timeline; each pass writes accounts to the ledger.

1. **Timeline construction.** Build month index: analysis_begin → analysis_end + 12 months (resale look-forward). All dates snap to first-of-month.
2. **Inflation factor tables.** Precompute monthly factor series for every index (general, market, expense, CPI, custom).
3. **Lease timeline resolution.** For each rent roll lease + each absorption-generated lease: resolve the full chain of lease "segments" (contract term → weighted speculative renewals per MLP → chained profiles) through end of timeline. Output: per-lease segment list with dates, area, rent spec, costs, recovery assignment, and a `speculative: bool` + `renewal_weight` on each segment.
4. **Base rent + adjustments per lease.** For each segment: monthly base rent (unit conversion per §3.12 examples), fixed steps, % of market resolution (requires market rent series from MLP + inflation), CPI adjustments, free rent abatement. Post: Base Rental Revenue (full-occupancy basis), Absorption & Turnover Vacancy (downtime negatives), Free Rent, CPI Adjustment.
5. **Expenses.** Compute all operating/non-op/capital expenses that do NOT depend on revenue percentages: unit conversion, inflation, %-fixed occupancy scaling (requires occupancy series from step 3/4), limits, timing patterns. (Occupancy% for month m = occupied SF / rentable SF.)
6. **Recoveries per lease.** For each lease-month, per assigned structure: pool expenses → adjustments → gross-up → subtract stop/base → pro-rata share → caps/floors → admin fee. Post Expense Recovery Revenue (retain per-tenant, per-pool detail for the Recovery Audit report).
7. **Percentage rent per lease.** Sales volume growth → breakpoints → overage. Post Percentage Rent.
8. **Tenant miscellaneous items.** Post per spec.
9. **Property revenues (misc/parking/storage).** Two-pass: (a) absolute-amount types; (b) percent-of-account/EGR types after step 10 produces a provisional EGR — implement as iterative resolution: compute EGR excluding %-based items, then compute %-based items, then finalize EGR (ARGUS behavior: %-of-EGR items reference EGR excluding themselves; a single second pass suffices, no fixed-point iteration needed).
10. **General vacancy & credit loss.** Per §3.4/3.5 including absorption/turnover offset and tenant overrides. Finalize EGR and NOI.
11. **Capital lines.** TIs and LCs post in the month of each lease segment start (or per spread rules); capital expenses per spec. Compute Cash Flow Before Debt Service.
12. **Debt.** Amortization schedules per loan (funding, IO period, amortizing payments, floating resets, additional principal, loan costs). Post debt lines; compute CFADS.
13. **Resale.** Per method: e.g., cap_noi_forward_12 → resale gross = NOI(months resale_date+1 … +12) / exit_cap; apply adjustments and selling costs; if stabilized-occupancy option set, recompute the forward NOI with stabilized vacancy. Net resale posts in resale month. Compute loan payoffs (outstanding balances) for leveraged net proceeds.
14. **Valuation.** 
    - Unleveraged PV = Σ CF_before_debt_m × DF_m + NetResale × DF_resale, with DF per discount_method/period_convention (monthly: DF_m = (1+r/12)^−m; mid-period: exponent m−0.5; annual: aggregate CF to years then discount).
    - Unleveraged IRR: solve on the monthly CF vector including price at t0 and net resale at exit; report annualized ((1+irr_m)^12 − 1). Leveraged versions use CFADS + equity at t0 + net leveraged resale.
    - Direct cap value per §3.18.
15. **Sensitivity matrices.** Re-run only steps 13-14 across the discount-rate × exit-cap grid (engine must be structured so valuation re-runs don't recompute the ledger).

## 4.2 Rollover blending: normative algorithm
For a lease expiring at month E with MLP P (renewal prob p), upon_expiration = market:
```
downtime      = round_to_months((1 − p) × P.months_vacant)
segment_start = E + downtime
rent_new      = P.market_base_rent_new inflated to segment_start (market index)
rent_renew    = P.market_base_rent_renew (or pct_of_new × rent_new)
rent          = p × rent_renew + (1 − p) × rent_new
free_months   = p × P.free_renew + (1 − p) × P.free_new     (revenue-weighted abatement)
ti_psf        = p × P.ti_renew + (1 − p) × P.ti_new         (posted at segment_start)
lc            = p × P.lc_renew + (1 − p) × P.lc_new
term          = P.term_months; then chain per P.upon_expiration
```
During `downtime` months, post Absorption & Turnover Vacancy = −(weighted rent × area / 12 equivalent) and reduce occupied area by (1 − p) × lease area (partial-occupancy weighting; ARGUS default treats downtime area as fully vacant weighted by (1−p)). Validate this against a golden file early — it is the most common source of divergence.

## 4.3 Rounding & policies [AE pp. 504-527 Modeling Policies]
Implement a `ModelingPolicies` object: rounding (none vs nearest dollar at report level; engine always computes full precision), vacancy interaction toggles, recovery admin-fee application, %-of-market timing. Defaults must match ARGUS defaults stated in the manual. Report-level rounding only; never round inside the ledger.

---

# 5. FILE FORMATS

## 5.1 Property JSON (`.icprop.json`)
Single document containing every §3 model plus schema_version. Pretty-printed, stable key order (Git-diffable). This is our `.aeex` replacement.

The format is documented for external producers by `docs/SCHEMA_GUIDE.md` (human-readable field-by-field guide: units, enums, defaults, worked example) and `docs/property_model.schema.json` (formal JSON Schema, exported by `scripts/export_json_schema.py`). Both are regenerated whenever the §3 models change; `tests/unit/test_schema_docs.py` enforces this.

## 5.2 Rent Roll Import Template (`templates/rent_roll_template.xlsx`)
One row per lease, columns matching §3.12 flat fields; steps and misc items in companion sheets keyed by tenant. Import validates via pydantic and returns row-level errors readable by a non-programmer [import validation concept: AE pp. 62, 171]. Also support CSV.

## 5.3 Excel Result Package (Section 8) and per-report exports.

## 5.4 Intake surfaces (normative)
The application has **exactly two** intake surfaces: loading a PropertyModel JSON document (§5.1) and importing the rent roll template (§5.2). Both validate fully through the §3 pydantic models, and validation errors must be readable by a non-programmer (plain language, the field path, the offending value, and what a valid value looks like). No other ingestion path exists or may be added; in-app OM/document ingestion is cancelled entirely (§1.2). External extraction workflows that produce `.icprop.json` files are outside the application and are supported only by the schema documentation in §5.1. **Any JSON produced by an external extraction workflow is reviewed by a human against the source document before it is used for calculation.**

---

# 6. UI SPECIFICATION (Streamlit v1)

Navigation mirrors the ARGUS Property Editor tab structure [AE pp. 48-58] so the user's mental model transfers:

**Sidebar:** Property selector, Scenario selector, Calculate button, Save/Load, Export Package.

**Tabs:**
1. **Property** — description, timing, area measures
2. **Market** — inflation, general vacancy, credit loss, MLPs (grid + detail editor), CPI profiles, free rent profiles, TI/LC categories
3. **Revenues** — misc/parking/storage grids
4. **Expenses** — opex/capex/non-op grids, expense groups
5. **Tenants** — rent roll grid (Excel-like editing via st.data_editor), lease detail drawer, absorption, recovery structure builder, tenant groups
6. **Investment** — purchase, loans
7. **Valuation** — DCF assumptions, direct cap, resale, sensitivity intervals
8. **Reports** — report picker rendering every §7 report with:
   - **Units toggle: Total $ / $ per SF / $ per SF per month / $ per occupied SF** (global control applied to any monetary report)
   - Period toggle: Monthly / Quarterly / Annual / Fiscal Annual
   - Date range selector
   - Per-report options mirroring ARGUS Report Options where meaningful [AE pp. 627-737]
   - Export-this-view-to-Excel button on every report
9. **Dashboard** — Property Summary: KPI cards (value, IRR unlev/lev, equity multiple, year-1 NOI, cap rate on cost, occupancy), NOI/CF chart, occupancy line, lease expiration bar chart, top tenants table [AE pp. 532-534]
10. **Audit** — drill-down: pick any account + month → per-tenant/per-item composition (engine detail retained per §2.3 principle 3)

Grids: editable, add/delete rows, duplicate row, per-cell validation errors displayed inline.

---

# 7. REPORT CATALOG (v1 required)

Every report is a builder function returning `(DataFrame, metadata)`; the UI renders and the exporter writes it. Column definitions follow the manual sections cited. All monetary reports respect the PSF/unit toggle.

**Property reports** [AE pp. 535-549]
1. Cash Flow — monthly/annual, account tree order per §2.3, expandable detail
2. Executive Summary — key assumptions, year-1 metrics, valuation results
3. Assumptions Report — full input echo
4. Sources & Uses — acquisition through disposition

**Valuation reports** [AE pp. 550-572]
5. IRR Matrix — IRR grid over price × exit cap (rows: prices at PV of rate grid; per manual layout)
6. Value Matrix — PV grid over discount rate × exit cap
7. Resale Matrix — net resale over exit cap × resale year
8. Valuation & Return Summary
9. Present Value report — per-period CF, discount factors, PV by year, resale PV
10. Returns Over Time — rolling IRRs/values by exit year [AE pp. 148-152, 568]

**Tenant reports** [AE pp. 573-579]
11. Lease Summary (current rent roll presentation)
12. Lease Expiration — by year: count, SF, % of building, expiring rent [AE pp. 574, 815-819]
13. Leasing Activity — new/renewal deals per period with economics
14. Tenant Cash Flow / Lease PV — single-tenant ledger + PV at tenant discount rate

**Audit reports** [AE pp. 585-604]
15. Occupancy Report — monthly occupied/vacant SF and %
16. Lease Audit — per-tenant monthly rent build-up (base, steps, CPI, free, recoveries, % rent)
17. Percentage Rent Audit — sales, breakpoints, overage per tenant
18. Recovery Audit — per tenant per pool: expenses, gross-up, stop, share, caps, fee (the make-or-break audit report)
19. Expense Group Audit
20. Loan Amortization — per loan schedule [AE p. 593]
21. Property Resale Audit — forward NOI build-up to net proceeds [AE p. 595]
22. Rent Schedule Audit [AE pp. 597-599]
23. Input Assumptions listing

---

# 8. EXCEL RESULT PACKAGE

`export/package_builder.py` produces one workbook per property/scenario:
- **Tab per report** (user selects which; default: Exec Summary, Annual CF, Monthly CF, Rent Roll, Lease Expiration, IRR Matrix, Value Matrix, PV, Recovery Audit, Loan Amort, Assumptions)
- Formatting standard: bold indigo header band, account tree indentation, negative in parens red, $ and % number formats, frozen panes, column widths auto, footer with property/scenario/timestamp, units noted in header (respects the PSF toggle state at export)
- Values only (no formulas) in v1; a "live Excel" formula-driven export is v2
- Also: single-report export from any report view; rent roll export matching the import template (round-trip)

---

# 9. VALIDATION & ACCEPTANCE

## 9.1 Golden-file testing (the credibility gate)
The user has access to real ARGUS Enterprise outputs. For each of 3+ reference properties (simple single-tenant net lease; multi-tenant office with base-year recoveries and rollover; retail with % rent):
1. Export from ARGUS: Annual + Monthly Cash Flow, Recovery Audit, Lease Audit, PV report, Resale, IRR — to Excel; place in `tests/golden/<property>/`
2. Recreate inputs in our JSON schema
3. `pytest` comparison: every line item within $1 per month (rounding tolerance); IRR within 1bp; PV within $100
4. **No UI work begins until golden test #1 (simple property) passes end-to-end. No report work beyond Cash Flow until golden test #2 passes.**

## 9.2 Unit tests from the manual
Every worked example in the manual becomes a test: Rental Income examples [AE p. 391], Rent Review calcs [AE p. 392], Rental Value Unit [AE p. 394], Repeating Payments [AE pp. 361-362], recovery gross-up [AE p. 407], resale methods [AE pp. 464-471].

## 9.3 Property-level invariants (assert on every calc run)
- PGR = Scheduled Base + Absorption/Turnover Vacancy reversal identity per §2.3
- Occupied SF ≤ Rentable SF every month
- Sum(monthly) = Annual for every account and every report aggregation
- Debt: ending balance rolls, payoff at resale = outstanding balance
- PV at discount rate = price → IRR = discount rate (self-consistency check)

---

# 10. PHASED ROADMAP (acceptance-gated)

**Phase 0 — Scaffold (days):** Repo, pydantic models for §3 complete, JSON round-trip, timeline + inflation modules + tests.
**Phase 1 — Core ledger (1-2 wks of sessions):** Rent roll base rent (all unit types, steps, CPI, free rent), expenses, simple net recoveries, occupancy, NOI. GATE: golden test property #1 cash flow matches.
**Phase 2 — Market machinery:** MLPs, rollover blending, absorption, general vacancy/credit loss with offsets, full recovery structures, % rent. GATE: golden #2 (office w/ rollover + base-year) and #3 (retail) match; Recovery Audit and Lease Audit reports built and matching.
**Phase 3 — Capital & valuation:** TIs/LCs, capex, purchase, debt, resale, PV/IRR, sensitivity. GATE: IRR/PV/Resale match goldens; invariants pass.
**Phase 4 — Reports & export:** Full §7 catalog, PSF toggles, Excel package. GATE: side-by-side export review vs ARGUS prints.
**Phase 5 — UI:** Streamlit per §6. GATE: full property built from scratch through UI only, calc, export.
**Phase 6 — Hardening:** Scenario compare, performance (<5s calc for 100-tenant/10-yr property), error messages, docs.

---

# 11. NON-GOALS RESTATED
No multi-user server, no permissions, no hotels/multifamily/UK valuation, no `.aeex` compatibility, no budgeting module, no GAAP rent (v1.1), no live-formula Excel (v2). Any request to add these before Phase 6 completes should be refused by the builder. **No in-app OM/document ingestion — ever** (§1.2, §5.4): unlike the deferred items above, it is cancelled entirely and must be refused in every phase, not reintroduced as a future phase.
