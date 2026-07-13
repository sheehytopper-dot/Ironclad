# NEXT STEPS TO PHASE 4 (Reports & Export)

**DRAFT — awaiting owner review. No Phase 4 engine/report/UI/export code
is written until Topper has seen this plan and resolved Step 0's
decisions (Iron Rule 2 applies to planning too — same as
NEXT_STEPS_TO_GATE3.md was reviewed before any Phase 3 code).**

The concrete path through Phase 4 — the full spec §7 report catalog, the
$/unit and period toggles (§4.3), and the formatted Excel export package
(§8) — to the Phase 4 gate. Companion to the closed
[NEXT_STEPS_TO_GATE1.md](NEXT_STEPS_TO_GATE1.md),
[NEXT_STEPS_TO_GATE2.md](NEXT_STEPS_TO_GATE2.md), and
[NEXT_STEPS_TO_GATE3.md](NEXT_STEPS_TO_GATE3.md); same standing rules
(fixture-lock, owner per-cell adjudication, Iron Rules, no input tuning).

**Where we are (2026-07-13):** Gate 3 passed (owner declaration
2026-07-12); the full calc engine (Phases 1-3) is complete. DEVIATIONS
§24 is fully closed — all eight Codex debt/resale/valuation findings
adjudicated (six fixed, two answered) and both sensitivity follow-ups
closed, owner-verified 2026-07-13. Suite: 425 passed + the four by-design
golden reds (137/47 Gate 2, 33/12 Gate 3 capital). Phase 4 is engine-side
report/export work only — no calc changes.

**Scope (spec §10 Phase 4 row):** "Reports & export: Full §7 catalog, PSF
toggles, Excel package." The v1 reports are DataFrame builders (spec §7:
"Every report is a builder function returning `(DataFrame, metadata)`; the
UI renders and the exporter writes it"); the Streamlit UI is Phase 5, not
this phase. Phase 4 also delivers the rent roll import template round-trip
(spec §5.2), the second of the two intake surfaces (PropertyModel JSON,
the first, already round-trips).

## The Phase 4 validation reality (read before the criteria)

Spec §10's Phase 4 gate says "side-by-side export review vs ARGUS
prints." **We have no ARGUS access** (the standing 2026-07-03 sourcing
note; DEVIATIONS §14) — no ARGUS prints are coming. As with Gate 3's
valuation reports, that gate is read through what we actually have:

1. **Exact reconciliation to the engine's own source of truth.** Every
   report is a *view* of the already-validated ledger / audit detail /
   RunResult. A report is correct when it reconciles to that source to
   floating-point tolerance (the pattern the Lease/Recovery/Resale audits
   already prove with their `reconcile_to_ledger` helpers). Toggles and
   period views must satisfy the §9.3 identity **sum(monthly) = annual =
   fiscal** for every account.
2. **The golden CSVs ARE the external ARGUS-based anchor — for the Cash
   Flow report specifically.** `expected_annual_cash_flow.csv` in each
   golden dir is a transcription of the OM's published Argus cash flow.
   The Cash Flow report (§7 report 1) and the Benchmark Comparison report
   (§7 report 24) validate directly against them — the golden comparison
   tests already do this line-by-line; Phase 4 refactors that logic into
   the report builder. The four by-design golden reds stay red by design
   and are not Phase 4 blockers.
3. **The Excel export package** is validated by (a) the tab data matching
   each report builder's DataFrame exactly (values-only export, no
   formulas in v1), (b) the rent-roll export → import round-trip, and
   (c) an **owner spot-check** of the formatted workbook (the Phase 4
   analogue of the Step 3/4/5 owner hand-checks — the owner opens the
   workbook and eyeballs formatting, signs, PSF math, and a couple of
   totals against a report view).

**Gate 4 criteria (checklist):**

1. **Report-builder contract in place and every v1 report conforms:**
   each report is a builder returning `(DataFrame, metadata)`; the
   already-built audit reports (Lease/Recovery/Resale) are harmonized to
   it.
2. **The Total $ / $ per SF / per-month / per-occupied-SF toggle and the
   annual/quarterly/fiscal period views** work on every monetary report,
   satisfying sum(monthly)=annual=fiscal (§9.3) and correct per-SF /
   per-occupied-SF denominators (spec §3.2 area measures).
3. **The v1 report set is built and reconciling** (the Step-0-confirmed
   scope; the §8 default-export set at minimum), each with an
   engineered reconciliation/round-trip test; the Cash Flow report and
   Benchmark Comparison validate against the golden CSVs.
4. **The formatted Excel package (§8) exports and round-trips:** one
   workbook, a tab per selected report, the §8 formatting standard,
   values-only; single-report export; rent-roll export matching the
   import template.
5. **The rent roll import template (§5.2) round-trips:** the template
   file exists, the importer validates via pydantic with non-programmer-
   readable row-level errors, and export→import reproduces the rent roll.
6. **Owner spot-check of the exported workbook recorded** (the §8
   review, per the validation reality above).

**Sequencing rationale (mirrors Phase 3's):** build the shared report
infrastructure once (the builder contract + toggle/period engine), then
each report is a thin view over data that already exists on RunResult.
Front-load the externally-anchored Cash Flow report and the
data-already-exists valuation/occupancy reports; the Excel exporter and
the rent-roll import come after enough builders exist to export.

---

## Report catalog status (all 24, spec §7)

"Built" = a DataFrame builder exists in `engine/reports/`. "Data ready" =
the numbers already live on `RunResult` (or the ledger); only a builder +
toggle wiring is needed. "Not built" = neither.

| # | Report (spec §7) | Cite | Status | Source on RunResult |
|---|---|---|---|---|
| 1 | Cash Flow | AE 535-539 | **Data ready** | `ledger.frame` + `to_annual`/`to_quarterly`/`to_fiscal_annual` |
| 2 | Executive Summary | AE 535-549 | Not built | ledger + valuation + assumptions |
| 3 | Assumptions Report | — | Not built | `model` echo (see docs/SCHEMA_GUIDE) |
| 4 | Sources & Uses | — | Not built | purchase/closing/debt/resale columns |
| 5 | IRR Matrix | AE 550-572 | **Data ready** | `sensitivity.unleveraged_irr_matrix` / `leveraged_irr_matrix` |
| 6 | Value Matrix | AE 550-572 | **Data ready** | `sensitivity.value_matrix` |
| 7 | Resale Matrix (exit cap × resale year) | AE 550-572 | Not built | needs a resale-year axis (re-run resale per year) |
| 8 | Valuation & Return Summary | AE 550-572 | **Data ready** | `valuation` (ValuationResult) |
| 9 | Present Value report | AE 550-572 | Partial | `valuation` PVs; per-period discount factors not yet exposed |
| 10 | Returns Over Time | AE 148-152, 568 | Not built | re-run valuation at each exit year |
| 11 | Lease Summary | AE 573-579 | Not built | `model.rent_roll` / resolved `segments` |
| 12 | Lease Expiration | AE 574, 815-819 | Not built | resolved `segments` |
| 13 | Leasing Activity | AE 573-579 | Not built | resolved `segments` (new/renewal per period) |
| 14 | Tenant Cash Flow / Lease PV | AE 573-579 | Not built | `lease_rents` + a tenant discount rate |
| 15 | Occupancy Report | AE 585-604 | **Data ready** | `occupied_area` / `rentable_area` / `occupancy` |
| 16 | Lease Audit | AE 535, 538 | **Built** | `engine/reports/lease_audit.py` |
| 17 | Percentage Rent Audit | AE 585-604 | Not built | `percentage_rent` per tenant (+ breakpoints) |
| 18 | Recovery Audit | AE 585-604 | **Built** | `engine/reports/recovery_audit.py` |
| 19 | Expense Group Audit | AE 585-604 | Not built | `expense_series` + `model.expense_groups` |
| 20 | Loan Amortization | AE 593 | **Data ready** | `loan_schedules[i].frame` per loan |
| 21 | Property Resale Audit | AE 595 | **Built** | `engine/reports/resale_audit.py` |
| 22 | Rent Schedule Audit | AE 597-599 | Not built | resolved `segments` monthly rent build-up |
| 23 | Input Assumptions listing | — | Not built | overlaps #3 |
| 24 | Benchmark Comparison | §9.1 | Partial (in test harness) | `_collect_misses` logic in the golden tests, not yet a reusable builder |

**Already built: 16, 18, 21** (the Gate 2/3 audit reports). **Data ready
(builder + toggles only): 1, 5, 6, 8, 15, 20.** Everything else is a new
builder.

---

## The toggles and period views (spec §4.3, §7 intro, §3.2)

- **Unit toggle:** every monetary report respects Total $ / $ per SF /
  per-month / per-occupied-SF (CLAUDE.md Conventions; spec §7 "All
  monetary reports respect the PSF/unit toggle"). $/SF uses rentable area
  (or Property Size per the report), per-occupied-SF uses the occupancy
  series, per-month divides the period figure by its month count. Full
  precision inside; **report-level rounding only** (§4.3 —
  `ModelingPolicies`, never round the ledger).
- **Period views:** annual / quarterly / fiscal already exist as ledger
  aggregations (`to_annual`, `to_quarterly`, `to_fiscal_annual`); Phase 4
  wires them into the report layer with the sum(monthly)=annual=fiscal
  invariant asserted (§9.3).
- **Which reports need them:** all monetary reports (Cash Flow, Sources &
  Uses, the audits, Loan Amort, PV). Count/percent reports (Occupancy,
  Lease Expiration) take the period view but not the $ unit toggle.

---

## Step 0 — Owner-gated inputs & decisions (runs in parallel; gates completion, not start)

**Owner: Topper (human). Not a Claude task — future sessions must not act
on these without his sign-off.** Flagged the way Phase 3's Step 0 was:

- **Report-scope trim.** 24 reports is the full v1 catalog, but the §8
  default-export set names the priority ~11 (Exec Summary, Annual CF,
  Monthly CF, Rent Roll/Lease Summary, Lease Expiration, IRR Matrix,
  Value Matrix, PV, Recovery Audit, Loan Amort, Assumptions). **Owner
  decision:** build all 24 in Phase 4, or defer the low-frequency tail
  (Expense Group Audit #19, Rent Schedule Audit #22, Leasing Activity
  #13, Returns Over Time #10, Tenant Cash Flow/Lease PV #14) to a later
  pass and ship the priority set as the Phase 4 gate?
- **The §8 export-gate comparison source.** The gate is "side-by-side vs
  ARGUS prints," which we don't have. **Owner decision:** confirm the
  substitute (owner spot-check of the formatted workbook + exact
  reconciliation + the golden-CSV anchor for Cash Flow), or does the
  owner have any real ARGUS print (from a prior engagement) to diff a
  single report against?
- **ModelingPolicies rounding defaults (§4.3).** Report-level rounding
  (none vs nearest dollar), and the other policy toggles' defaults must
  match ARGUS's stated defaults [AE pp. 504-527]. **Owner confirms** the
  default set (or defers policies to their own mini-step).
- **Tenant discount rate for report #14** (Tenant Cash Flow / Lease PV) —
  no schema field today; owner decides whether to add one or drop #14.

## Step 1 — Report infrastructure: the builder contract + toggle/period engine (session 1)

Spec §7 intro / §4.3. Build the shared layer every report sits on:
- A report-builder contract: `build(result, *, unit, period, rounding) ->
  (DataFrame, metadata)` (or a small `Report` dataclass). Define the unit
  toggle (Total $ / $ per SF / per-month / per-occupied-SF) and the
  period selector (monthly / quarterly / annual / fiscal) as reusable
  transforms over a monetary DataFrame, using the existing ledger
  aggregations and area series.
- `ModelingPolicies` (§4.3) with ARGUS-default rounding, applied at the
  report layer only.
- Harmonize the three existing audit builders (Lease/Recovery/Resale) to
  the contract without changing their reconciliation.
- **Acceptance:** unit/period transforms satisfy sum(monthly)=annual=
  fiscal and correct PSF/per-occupied denominators on an engineered
  property; the three audits still reconcile exactly.

## Step 2 — Cash Flow report (#1) + Benchmark Comparison (#24) (session 2)

The flagship, and the only reports with an external anchor. Spec §7
reports 1 and 24; AE 535-539.
- Cash Flow builder: the §2.3 account-tree order, expandable detail,
  monthly/annual/fiscal views, the unit toggle. It is a view of
  `ledger.frame` — must reconcile to it exactly.
- Benchmark Comparison builder: refactor the golden tests' `_collect_misses`
  into a reusable builder that loads an expected cash-flow CSV, runs the
  engine, and emits a per-line diff with tolerance flags (§9.1 default
  $500/line). The four goldens exercise it; the four by-design reds stay
  red.
- **Acceptance:** the Cash Flow report reproduces each golden's fiscal
  cash flow (Clorox green; Freeport/Cedar Alt within the documented
  deferred-B/E deltas), and Benchmark Comparison reproduces the golden
  tests' current pass/fail line counts exactly.

## Step 3 — Valuation report family (#5, #6, #8, #9, #20) (session 3)

Data already on RunResult (sensitivity, valuation, loan_schedules). Spec
§7 reports 5-6, 8-9, 20; AE 550-572, 593.
- IRR Matrix (#5) and Value Matrix (#6): thin builders over
  `sensitivity` (NaN cells render as blanks). Valuation & Return Summary
  (#8) over `valuation`. Present Value report (#9): expose the per-period
  discount factors from the valuation helpers. Loan Amortization (#20):
  per-loan schedule from `loan_schedules[i].frame`.
- **Acceptance:** each reconciles to its RunResult source; the IRR-matrix
  center cell equals the ValuationResult IRR (the §21 cross-check), the
  Loan Amort schedule reconciles to the ledger's financing lines.

## Step 4 — Occupancy + tenant/lease reports (#15, #11, #12) + audit tail (#17, #19, #22) (session 4)

Spec §7 reports 11-12, 15, 17, 19, 22; AE 573-604.
- Occupancy (#15) from the occupancy series. Lease Summary (#11) and
  Lease Expiration (#12) from the resolved segments. Percentage Rent
  Audit (#17), Expense Group Audit (#19), Rent Schedule Audit (#22) from
  the retained per-tenant/per-expense detail.
- **Acceptance:** Occupancy satisfies occupied ≤ rentable every month;
  Lease Expiration SF sums to rentable; the audits reconcile to their
  ledger lines. (Some of these are Step-0 trim candidates.)

## Step 5 — Summary/echo + remaining reports (#2, #3, #4, #7, #10, #13, #14, #23) (session 5)

Spec §7 reports 2-4, 7, 10, 13-14, 23. The lower-frequency tail —
Executive Summary, Assumptions Report / Input Assumptions listing,
Sources & Uses, Resale Matrix (new resale-year axis), Returns Over Time
(re-run valuation per exit year), Leasing Activity, Tenant Cash
Flow/Lease PV. **Several are Step-0 trim candidates** — build per the
owner's Step 0 scope decision.
- **Acceptance:** each reconciles to its source; Sources & Uses ties to
  the below-the-line ledger columns; Resale Matrix / Returns Over Time
  each cell equals a direct single-point valuation (the §21 pattern).

## Step 6 — Excel export package (§8) (session 6)

`engine/export/package_builder.py`. Spec §8.
- One workbook per property/scenario, a tab per selected report (default
  set per §8), the §8 formatting standard (indigo header band, tree
  indentation, negatives in red parens, $/% formats, frozen panes, auto
  widths, footer, unit noted in header). Values-only (no formulas) in v1.
  Single-report export from any report view.
- **Acceptance:** each tab's cell values equal the report builder's
  DataFrame exactly (values-only); an engineered test opens the written
  workbook and diffs it against the builders. The existing
  `scripts/dump_*.py` owner helpers are superseded/retired or rebased on
  the package builder.

## Step 7 — Rent roll import template round-trip (§5.2) (session 7)

`templates/rent_roll_template.xlsx` + the importer. Spec §5.2.
- The template: one row per lease (§3.12 flat fields), steps and misc
  items in companion sheets keyed by tenant; CSV also supported. The
  importer validates through the §3 pydantic models and returns row-level
  errors readable by a non-programmer.
- The rent-roll **export** (from Step 6) matches this template, so
  export→import round-trips.
- **Acceptance:** a property's rent roll exported then re-imported
  reproduces the same `PropertyModel` rent roll; a malformed row yields a
  readable error, not a stack trace. (Standing principle: any JSON/import
  produced externally is human-reviewed against the source before
  calculation.)

## Step 8 — Gate 4 review (owner)

Criteria 1-6 evidenced in one pytest run plus the owner's workbook
spot-check: the builder contract + toggle/period engine, the v1 report
set reconciling (Cash Flow + Benchmark against the goldens), the Excel
package exporting and round-tripping, the rent-roll import round-trip.
The four by-design golden reds stay red by design and are not Gate 4
blockers. Then — and only then — Phase 5 (UI, Iron Rule 2).

---

**Standing gaps carried into Phase 4 (unchanged; none a Phase 4
blocker):** percentage rent externally unvalidated pending golden #3
(standing opportunistic intake); tenant miscellaneous items and Step 2/3
purchase/deposits/debt and Step 4/5/6 resale/valuation/sensitivity
externally unvalidated (no golden exercises them — manual/engineered
tests + owner hand-checks only); Freeport B and Cedar Alt B (general-
vacancy basis / rollover recovery timing) and Freeport E (LC base) parked
for beta-stage GUI testing (owner decisions 2026-07-10/07-12 — their
Gate 2/3 assertions stay red by design, 137/47 and 33/12); Cedar Alt D
closed as C's sibling (not open); live price derivation
(`Purchase.derivation != fixed`, `pct_of_value` loans) permanently
refusing (DEVIATIONS §20 #6, owner decision 2026-07-11); no ARGUS access —
the Benchmark Comparison report (§7 report 24, built in Step 2) is the
future-deal validation path. In-app OM ingestion ("Phase 7") is cancelled
permanently and must not be scaffolded.

**Status:** drafted 2026-07-13 on the DEVIATIONS §24 full closure, per the
Phase 4 opening prompt. **Awaiting owner review — no Phase 4 engine/
report/UI/export code starts until Topper has seen this plan and resolved
Step 0's decisions.**
