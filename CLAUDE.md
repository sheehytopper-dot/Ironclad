# PROJECT IRONCLAD — Build Instructions for Claude Code

IronClad recreates the single-asset commercial cash flow, valuation, and reporting engine of
ARGUS Enterprise 11.0 (office / industrial / retail, US-style DCF) as a Python calculation
engine + FastAPI + Streamlit web app with Excel export.

**The full build specification is [ARGUS_REBUILD_SPEC.md](ARGUS_REBUILD_SPEC.md). Read it before
any non-trivial task. This file is the standing orders; the spec is the law.**

## The Three Iron Rules

1. **Engine code never imports UI code.** `engine/` is a standalone, headless calculation
   package. It must never import from `ui/`, `api/`, or Streamlit/FastAPI/Plotly. The UI and
   API are clients of the engine, never the reverse.
2. **No phase advances until its golden-file gate passes.** Each roadmap phase (spec §10) has
   an acceptance gate against golden fixtures in `tests/golden/` (sources and tolerances: see
   **Golden-File Strategy** below; spec §9.1 states the same strategy). Do not
   start work belonging to phase N+1 until phase N's gate passes. In particular: no UI work
   until golden test #1 passes end-to-end; no report work beyond Cash Flow until golden test
   #2 passes.
3. **Every calc module gets unit tests from the manual's worked examples.** Each module in
   `engine/calc/` ships with pytest tests reproducing the ARGUS manual's worked examples
   (base rent calc examples, rent reviews, repeating payments, recovery gross-up, resale
   methods — see spec §9.2), **with the manual page citation in each test's docstring**
   (e.g., `"""Rental Income worked example [AE p. 391]."""`).

## Authoritative Reference

`reference/Argus_Training_Guide.pdf` (ARGUS Enterprise 11.0 Product User Manual, 1,056 pp.)
is the **authoritative behavioral reference**. The spec cites it throughout as `[AE pp. x-y]`;
when the spec and the manual conflict on calculation behavior, **the manual governs**. Consult
the cited pages before implementing any calc module. The manual is a reference for functional
behavior only — never copy its text into the product, UI, or docs, and never name or market
the product as "Argus." Do not implement `.aeex`/`.aeix` binary formats; our format is open
JSON (`.icprop.json`, spec §5.1).

## Golden-File Strategy (revised 2026-07-03; spec §9.1 states the same strategy)

**We do not have ARGUS access — no ARGUS output exports are coming.** Validation instead
rests on three independent sources:

1. **Four OM-based goldens spanning complexity** (reduced from five 2026-07-09 —
   DEVIATIONS.md §14) — each an Offering Memorandum with a published Argus-based cash
   flow, each validated **annually at fiscal-year level, within $500 per line**:
   - **#1** single-tenant NNN — `tests/golden/clorox_northlake/` (CBRE OM; owner-verified)
   - **#2** multi-tenant with base-year or expense-stop recoveries
   - **#3** retail with percentage rent — **standing opportunistic intake** (owner decision
     2026-07-05; no deadline — see Known validation gaps below)
   - **#4** chosen from deal triage for coverage of gross-ups, caps, or absorption
   - *(#5, Inland Logistics, was staged and **permanently disqualified 2026-07-09** — its
     OM has no ARGUS attribution anywhere; no replacement pursued. DEVIATIONS.md §14.)*
2. **Owner per-cell adjudication (standing):** when the engine and a golden's published
   figures disagree beyond tolerance, or a month-level timing question arises that annual
   data cannot discriminate, the owner recomputes the specific disputed cells in Excel
   from the source documents alone, **WITHOUT reading the engine's output or code first**.
   The owner's independently computed cells are the reference. Claude never produces
   these reference cells.
3. **The manual's worked examples as unit-level goldens** (Iron Rule 3): base rent examples
   [AE pp. 391-394], repeating payments [AE pp. 361-362], recovery gross-up [AE p. 407],
   resale methods [AE pp. 464-471], with page cites in test docstrings.

**Fixture-lock rule (standing policy, revised 2026-07-07):** transcribed inputs are
verified before commit and before any engine comparison runs. Verification means either
(a) the owner reads the source pages himself, or (b) the owner reviews a written
verification pass — e.g. an independent cross-check of the transcription against the
source document, covering the highest-leverage inputs (the ones that move the most
dollars in the fixture) — and explicitly confirms or challenges it. A verification pass
that only re-derives the transcription using the same method and the same source excerpts
as the original transcription does not satisfy this rule on its own; it must be reviewed
and signed off by the owner before commit. Every future deal validates
against its source OM's published Argus output via the Benchmark Comparison report
(spec §7 report 24) before assumptions are toggled.

### Known validation gaps

- **Percentage rent has no external Argus reference until golden #3 arrives** (standing
  opportunistic intake, owner decision 2026-07-05: the first retail OM with a published
  Argus-based cash flow including a Percentage Rent line that the owner obtains gets staged,
  transcribed under the fixture-lock rule, and back-tested via the Benchmark Comparison
  report). The Phase 2 percentage-rent module ships with the manual's worked-example unit
  tests (Iron Rule 3) but is **externally unvalidated pending golden #3**. The owner accepts
  this risk — percentage rent is rarely used in his practice. **Any retail underwriting
  before the golden #3 back-test treats the Percentage Rent line as unverified.**

**Gate 1 passed (owner declaration 2026-07-05)** — its path,
[NEXT_STEPS_TO_GATE1.md](NEXT_STEPS_TO_GATE1.md), is closed. The step-by-step path
through Phase 2 to Gate 2 is [NEXT_STEPS_TO_GATE2.md](NEXT_STEPS_TO_GATE2.md); golden
#2/#4 fixture transcription there (Step 0) is owner-gated and gates the phase's
completion, not its start.

## Intake Surfaces (standing policy)

**In-app OM ingestion ("Phase 7") is cancelled entirely.** Do not scaffold it, reference it
as future work, or reintroduce it in any planning document. The application has exactly two
intake surfaces:

1. **Loading a PropertyModel JSON file** (`.icprop.json`, spec §5.1)
2. **Importing the rent roll Excel template** (spec §5.2)

Both validate fully through the §3 pydantic models, and validation errors must be readable
by a non-programmer. How a PropertyModel JSON gets created is **permanently outside the
application's scope**: extraction from OMs or other documents happens in external workflows
the app knows nothing about.

To support those external workflows, the schema is documented for outside producers:
[docs/SCHEMA_GUIDE.md](docs/SCHEMA_GUIDE.md) (human-readable field-by-field guide — units,
enums, defaults, worked example) and `docs/property_model.schema.json` (formal JSON Schema,
exported by `scripts/export_json_schema.py`). **Regenerate both whenever `engine/models/`
changes** — `tests/unit/test_schema_docs.py` fails when either drifts.

**Standing principle: any JSON produced by an external extraction workflow is reviewed by a
human against the source document before it is used for calculation.**

## Architecture (spec §2)

- **Stack:** Python 3.11+ engine (`numpy`/`pandas`), `pydantic` v2 input models, JSON-per-property
  persistence + SQLite index (`sqlmodel`), FastAPI API layer, Streamlit UI (v1), Plotly charts,
  `xlsxwriter`/`openpyxl` Excel export, `pytest` + golden-file fixtures.
- **Layout:** `engine/models/` (§3 pydantic input schema) · `engine/calc/` (calculation passes,
  one module per domain: timeline, inflation, leases, recoveries, percentage_rent, revenues,
  expenses, vacancy, absorption, debt, resale, valuation, sensitivity, ledger, run) ·
  `engine/reports/` (DataFrame builders) · `engine/export/` (Excel packages) · `api/` · `ui/` ·
  `data/properties/` + `data/templates/` · `tests/unit/` + `tests/golden/` ·
  `docs/` (schema guide + JSON Schema export) · `scripts/` (doc/schema regeneration).
- **The canonical ledger (§2.3):** everything is computed monthly into one pandas DataFrame
  (Period[M] index, analysis begin → end + 12 months for the resale look-forward), one column
  per account in the Chart of Accounts tree. Annual/quarterly/fiscal views are aggregations of
  the monthly ledger, never separately computed. Line names/order must match the ARGUS Cash
  Flow report so exports diff cleanly.
- **Order of operations (§4.1):** timeline → inflation tables → lease chain resolution →
  base rent/adjustments → expenses → recoveries → % rent → tenant misc → property revenues
  (two-pass for %-of-EGR) → general vacancy & credit loss → capital lines → debt → resale →
  valuation → sensitivity (valuation re-runs must not recompute the ledger).
- **Design principles (§1.3):** engine before UI; everything monthly; no silent numbers (full
  per-tenant/per-month audit detail retained); deterministic; open data.

## Phased Roadmap & Gates (spec §10)

| Phase | Scope | Gate |
|---|---|---|
| 0 — Scaffold | Repo, §3 pydantic models, JSON round-trip, timeline + inflation modules + tests | Tests pass |
| 1 — Core ledger | Base rent (all unit types, steps, CPI, free rent), expenses, simple net recoveries, occupancy, NOI | **Golden #1** (Clorox Northlake): OM annual fiscal-year within $500/line (FY2027-FY2028 per gate phasing; disputes resolved by owner per-cell adjudication) |
| 2 — Market machinery | MLPs, rollover blending, absorption, general vacancy/credit loss offsets, full recovery structures, % rent | **Goldens #2, #4** (Freeport, Cedar Alt) cash flows match the OM within tolerance (reduced from three 2026-07-09 — #5 Inland disqualified, no ARGUS attribution; DEVIATIONS.md §14); Lease Audit + Recovery Audit reports built, reconciling exactly to the ledger, and owner-reviewed; % rent module built with manual worked-example tests (Iron Rule 3) but **externally unvalidated pending golden #3** |
| 3 — Capital & valuation | TIs/LCs, capex, purchase, debt, resale, PV/IRR, sensitivity | IRR/PV/Resale match goldens; §9.3 invariants pass |
| 4 — Reports & export | Full §7 catalog, PSF toggles, Excel package | Side-by-side export review vs ARGUS prints |
| 5 — UI | Streamlit per §6 | Full property built from scratch through UI only, calc, export |
| 6 — Hardening | Scenario compare, perf (<5s for 100-tenant/10-yr), errors, docs | — |

The phase schedule and its status live in [BUILD_SCHEDULE.md](BUILD_SCHEDULE.md).

Refuse scope creep: no hotels, multifamily, UK valuation, portfolio server, budgeting,
multi-currency, GAAP rent, or live-formula Excel before Phase 6 completes (spec §1.2, §11).
In-app OM/document ingestion is not on that deferred list — it is **cancelled permanently**
(see Intake Surfaces above) and must not be built in any phase.

## Conventions

- Property invariants (spec §9.3) are asserted on every calc run — PGR identity, occupied ≤
  rentable SF, monthly sums = annual, debt balance rolls, PV/IRR self-consistency.
- Full precision inside the ledger; rounding is report-level only (§4.3).
- Every monetary report respects the Total $ / $ per SF / per-month / per-occupied-SF toggle.
- **When you restructure or summarize a planning document, list explicitly anything you
  removed or consolidated — every time.** Silent drops from plans are not acceptable.
- Run tests: `.venv\Scripts\python -m pytest` (Windows). Current status: **GATE 2 PASSED
  (owner declaration 2026-07-10); Phase 3 begins.** Phase 1 shipped 2026-07-05:
  `leases.py` ([AE pp. 391-394, 253-257]), `expenses.py` ([AE pp. 361-362]),
  `recoveries.py` (net/none, [AE pp. 404-407]), `ledger.py` (Cash Flow tree,
  [AE pp. 535-539]; DEVIATIONS.md §5), `run.py` (spec §4.1 passes 1-6; the recoverable
  %-of-EGR fee iterates to a fixed point through the recovery pool — DEVIATIONS.md §6;
  §9.3 pre-valuation invariants on every run). Golden #1 Gate 1 scope: FY2027-FY2028
  every line within $1 (tolerance $500; DISCREPANCY_LOG.md). Phase 2 session sequence:
  [NEXT_STEPS_TO_GATE2.md](NEXT_STEPS_TO_GATE2.md) (owner-corrected 2026-07-05:
  vacancy double-count criterion, Recovery Audit built early in Step 5, Step 0
  verification checks for Freeport/Inland). **Phase 2 Step 1 complete 2026-07-05:**
  lease chain resolution in `engine/calc/leases.py` ([AE pp. 233-252] read; §4.2
  blending with weighted rent/downtime/free/TI/LC; market/option/renew/vacate/reabsorb
  chaining; pct_of_last_rent; Intelligent Renewals as a four-way rule — schema field
  `intelligent_renewals` changed bool → enum [AE pp. 235-236], schema docs regenerated;
  MLP narrowings recorded in DEVIATIONS.md §7). **Phase 2 Step 2 complete 2026-07-06:**
  rollover projected into the ledger (project_segment_rent — downtime posts blended
  rent to Base Rental Revenue and negative A&T Vacancy; weighted free rent front-loaded
  with fractional final month; occupied_area_from_chains — downtime occupancy = p ×
  area; project_segment_recoveries — per-segment assignment, occupied months only,
  nothing during downtime; run.py wired to chains, MLP guards added for %-rent/misc/
  deposits). **Golden #1 FY2029-FY2031 revenue/vacancy/expense/NOI assertions active
  and green — worst deviation $0.86** (capital lines wait for Gate 3;
  DISCREPANCY_LOG.md updated). `scripts/dump_monthly.py` (owner request) dumps any
  .icprop.json's full monthly ledger + fiscal subtotals to .xlsx (`*.monthly.xlsx`
  gitignored). **Phase 2 Step 3 complete 2026-07-06:** space absorption
  (`engine/calc/absorption.py`, [AE pp. 395-403]) — synthetic leases on the schedule
  at MLP new-tenant economics (rent inflated to each lease's own start, "N of M"
  naming per [AE p. 403]; area_per_lease → ceil count with remainder final lease so
  areas sum exactly), joining the rent roll for chains/occupancy/expenses/recoveries;
  derived rentable area includes absorption. **Phase 2 Step 4 complete 2026-07-06:**
  general vacancy & credit loss (`engine/calc/vacancy.py`, [AE pp. 224-232]) — three
  % methods with the manual's p. 225 examples as tests, year-varying rates,
  include_in_pgr_accounts, exclusion-only tenant overrides (narrowings: DEVIATIONS.md
  §9), reduce_by_absorption_turnover computing the target on 100%-occupancy revenue
  and netting A&T from the allowance; credit loss after GV on the reduced base; both
  live inside run.py's fixed point (EGR = PGR + GV + CL). **Step 4's hand-model
  exposed that Step 3's silent pre-absorption vacancy would double-count against the
  A&T offset — corrected: pre-absorption space now grosses Base + A&T to market per
  [AE p. 538] (DEVIATIONS.md §8 revised; Scheduled/EGR/NOI confirmed unchanged by
  test).** Gate 2 criterion-5 test green: total vacancy = the stated 20% of
  full-occupancy revenue in downtime and occupied months alike. **Phase 2 Step 5
  session 1 complete 2026-07-06:** system recovery methods (`recoveries.py`,
  [AE pp. 404-413, 517-520] read) — base_stop (building $/SF stop, pro-rata excess
  [AE p. 409]), base_year/±1 (frozen base-year pool as the stop, lease-start-relative,
  pre-analysis → analysis year 1 [AE pp. 408-409]; truncated windows annualized),
  fixed ($ tenant amount or $/SF × tenant area [AE p. 409], flat unless
  fixed_inflation opts in); all floored at 0, dispatched through
  project_segment_recoveries for contract + speculative segments (a spec segment's
  base year = its own start year; Continue Prior not modeled — DEVIATIONS.md §7).
  base_year_gross_up_pct defers loudly to session 2 (gross-up is user-structure
  [AE p. 406]). Fixed-point convergence with stops verified and documented
  (max(0,·) is 1-Lipschitz; contraction factor ≤ 2 × share × pct) with a
  hand-computed base-stop + recoverable-fee test (fee = 5% of final EGR exactly).
  **Phase 2 Step 5 session 2 complete 2026-07-06:** user recovery structures
  (`recoveries.py`) — pools over refs/groups with double-count errors [AE p. 408],
  per-pool net/stop/base_year/fixed, the [AE p. 407] gross-up formula (bounded form:
  series × (f + (1−f)·max(occ, g)) / (f + (1−f)·occ); fully-variable-at-zero-occupancy
  raises loudly), denominators [AE p. 410], share override, admin fees before/after
  the stop [AE pp. 519-520], caps/floors incl. YoY + cumulative on calendar years
  [AE pp. 411-412], expense adjustments; base_year_gross_up_pct unlocked on system
  assignments; abate_recoveries live (Phase 1 deferral closed). **Convergence
  re-derived for gross-up:** %-of-revenue lines are never grossed (the [AE p. 519]
  policy fixed at 100%-Fixed), so gross-up ratios are fee-constants and the session-1
  contraction bound carries over; the 100%-Variable policy would be unbounded at low
  occupancy and stays unimplemented (DEVIATIONS.md §10, with anchor contributions and
  other narrowings). **Recovery Audit report built** (`engine/reports/recovery_audit.py`,
  spec §7 report 18) from per-tenant per-pool PoolAudit detail on every run;
  `reconcile_to_ledger` proves exact reconciliation (tested to 1e-9). **Phase 2 Step 6
  complete 2026-07-06:** Lease Audit report (`engine/reports/lease_audit.py`, spec §7
  report 16 — the [AE p. 535] Potential Base Rent drill-down): one row per active
  (tenant, month) with phase labels from the resolved chains (contract / speculative /
  downtime / vacant; absorption first generations labeled speculative per the lease
  status [AE p. 398]), the [AE p. 538] line decomposition with per-row Scheduled and
  total identities, reconciling exactly to the ledger's five revenue lines
  (`reconcile_lease_audit`, tested to 1e-9 on a multi-tenant rollover + absorption +
  free-rent property). `scripts/dump_audits.py` (owner review helper) writes both
  audit reports + a reconciliation sheet to .xlsx (`*.audits.xlsx` gitignored); run on
  Clorox: reconciliation exactly 0. Suite 226 green. **BOTH audit reports are ready
  for the Gate 2 owner review** (a Gate 2 criterion). Gate 2 remaining: owner review
  of the audits, Step 7 (goldens #2/#4 — owner-gated fixtures; #5 disqualified
  2026-07-09, DEVIATIONS.md §14), Step 8 (% rent).
  **Gate 2 audit-review follow-up complete 2026-07-06:** recoverable %-of-EGR fee
  with `limits.min` (owner request: a management fee must hold a dollar floor —
  e.g. $5,000/mo — through full vacancy) verified end-to-end: the existing
  `project_expense` clamp already produced the right numbers, now proven by
  tests/unit/test_run.py::TestFeeFloorInFixedPoint — floor holds in fully vacant
  months (fee = floor, no recovery, NOI = −floor), binding-floor occupied months
  flow through the net pool self-consistently (max(floor, pct × EGR) = floor),
  Recovery Audit reconciles exactly, slack floor is inert. Convergence with clamps
  re-derived against the actual iteration (map = clamp ∘ (pct × EGR(·)); min/max
  clamps are 1-Lipschitz, locally constant where binding — only tightens the
  session-1/session-2 bound) and documented beside those proofs in the
  recoveries.py module docstring. NOTE: golden #1 sets no limits, so only this
  test proves the behavior — green CI without it is not evidence.
  **Phase 2 Step 8 complete 2026-07-06:** percentage rent
  (`engine/calc/percentage_rent.py`, [AE pp. 249-251, 376-377, 590] read; spec
  §3.13) — % rent due = Σ per layer max(0, sales − breakpoint) × pct [AE p. 590];
  sales volume $/yr or $/SF/yr × tenant area growing on its index; breakpoints
  natural = (base + step + CPI) / layer pct [AE pp. 250-251, 377, 590] (free rent
  does not reduce it), fixed annual $, zero = % of total sales; up to 6 tiered
  layers. Projection is per segment over occupied months only (contract term
  carries the lease's spec, speculative terms the MLP's [AE p. 376]; nothing in
  downtime — Step 2 recovery convention), posting 1/12 of the month's annualized
  run rate (the spec §3.14 straight monthly accrual policy). Wired through
  run.py as a fee-independent constant in the fixed point (contraction bound
  untouched): Percentage Rent ledger line, Total PGR/EGR, both vacancy bases
  (percent_of_pgr / total_tenant_revenue), and the Lease Audit column with the
  reconciliation extended to six revenue lines. The [AE p. 413] recovery offset
  is schema-absent (it lives on recovery structures, §3.14 has no field) →
  deferred loudly with all narrowings in DEVIATIONS.md §11 (single sales
  category, no Continue Prior, no per-layer caps, no $/SF breakpoints, no
  property-type gate, blended-rent natural breakpoints on spec segments).
  Manual-definition unit tests incl. the [AE p. 392] % of Sales number
  (Iron Rule 3); suite 245 green (golden #1 untouched). **STANDING GAP: the
  module is externally unvalidated pending golden #3** — any retail
  underwriting before that back-test treats the Percentage Rent line as
  unverified.
  **GATE 2 PASSED (owner declaration 2026-07-10) — final path:** Cedar Alt's
  Step 7 comparison test built 2026-07-09 (47/165 line-years beyond $500,
  mirroring Freeport's 137/242). Freeport root causes A1/C/D and Cedar Alt
  A/C adjudicated closed 2026-07-10 — each citing its existing owner
  directive or manual-cited design decision (A1: the 2026-07-07 no-fabricated-
  stops directive; C: the [AE p. 538] gross-up presentation, EGR/NOI-neutral
  by test; D: monthly-correct scaling verified at expenses.py:116, residual =
  the ASSUMPTIONS §6 back-solve limitation; Cedar A: day-count immaterial;
  Cedar C: OM free-rent inconsistency), **not new engine work**. Freeport B
  (general-vacancy basis) and Cedar Alt B (rollover recovery timing — the
  [AE p. 520] Calculation Frequency candidate) explicitly deferred to
  beta-stage GUI testing; the two golden gate assertions stay red by design.
  Audit-report review satisfied 2026-07-09 (Freeport audits.xlsx,
  reconciliation clean); turnover/general-vacancy double-count criterion
  verified passing. Documentation synced across BUILD_SCHEDULE.md,
  NEXT_STEPS_TO_GATE2.md (closed), and both DISCREPANCY_LOG.md files.
  **Phase 3 planning session 2026-07-11:**
  [NEXT_STEPS_TO_GATE3.md](NEXT_STEPS_TO_GATE3.md) drafted (no engine code
  written — Iron Rule 2 applied to planning). Key planning finding, verified
  by keyword scan of all three OMs: **none publishes any valuation result**
  (Clorox/Cedar explicitly unpriced; Freeport none), so Gate 3's external
  anchor is the goldens' already-transcribed capital lines (TI/LC/capex/
  reserves/Total Capital/CFBDS, currently Gate-3-skipped in every comparison
  test), backed by §9.3 invariants (debt roll, payoff-at-resale, PV/IRR
  1bp self-consistency), manual worked examples ([AE pp. 464-471, 472-473,
  435-449]), and owner hand-checks. Plan: Step 0 owner-gated decisions
  (valuation assumption sets — exercise inputs with no external reference;
  CFBDS-on-#1-only assertion scoping; placement of carried-forward guards:
  tenant misc items [still refused with a stale "Phase 2" label], security
  deposits, reabsorb, pct_of_account) → Steps 1-6 (TI/LC posting + golden
  capital-line activation first, then purchase/closing/deposits, debt,
  resale, PV/IRR, sensitivity) → Step 7 gate review. **DRAFT — awaiting
  owner review before any Phase 3 engine work.**
  **Owner-directed builds 2026-07-11 (carried-forward items closed):**
  (1) `upon_expiration 'reabsorb'` for contract leases
  (`engine/calc/absorption.py` reabsorption_vacancy + available_from;
  `AbsorptionSpec.reabsorbed_from` linkage with three cross-ref
  validations; derived rentable area keeps the reabsorbed lease's area as
  the SF anchor; MLP-chain reabsorb stays guarded; DEVIATIONS.md §8;
  9 engineered tests — no golden exercises reabsorb). (2) **Tenant
  miscellaneous items** (spec §3.12/§4.1 pass 8; [AE pp. 378-381,
  240-244] read) — `engine/calc/misc_items.py`, per-segment over occupied
  months (lease's items on contract, MLP's on speculative), $/period
  units × Timing machinery, monthly Limits clamp, general-index default,
  free-rent abatement gated on item `free_rent_abates` AND profile
  `abate_miscellaneous`; Miscellaneous Tenant Revenue live in PGR/EGR,
  both vacancy bases, and the Lease Audit (reconciliation extended to
  seven lines); both stale "Phase 2" guards lifted; narrowings + the
  **externally-unvalidated flag** (no golden uses misc items) in
  DEVIATIONS.md §15; 13 manual-cited tests.
  **Phase 3 Step 1 complete 2026-07-11 (owner-directed Parts A-E):** TI/LC
  posting (`engine/calc/capital.py`, [AE pp. 245-248] read) — both post as
  a single lump sum in each segment's start month ("paid at the beginning
  of the lease" [AE pp. 246-247]); contract segments via the identity
  blend of `Lease.leasing_costs` (guard lifted — only a category guard
  remains), speculative segments §4.2-weighted with $-amounts inflated to
  segment start on the market index (manual names no index; golden #1's
  published TI proves the factor); LC Fixed % = pct × (term base rent +
  fixed steps − free rent, CPI excluded, over the full term even past
  timeline end [AE p. 247]), `pct_years` threaded onto LeaseSegment;
  absorption leases inflate TI/$-LC at generation to each lease's own
  start; TI/LC categories + timing grids refused loudly (schema-present,
  no consumer — DEVIATIONS.md §16); ledger TI/LC/Total Capital Costs/
  CFBDS live; 16 manual-cited tests (tests/unit/test_capital.py).
  **Golden #1 FY2029-FY2031 capital lines ACTIVE AND GREEN — every cell
  within $0.50** (TI 501,275 / LC 1,465,383 exact). Goldens #2/#4 capital
  lines active as separate test functions per criterion 1, **CFBDS on all
  three** (the CFBDS-on-#1-only scoping was superseded by owner decision
  2026-07-11 — NEXT_STEPS_TO_GATE3.md criterion 1), red as expected
  output: Freeport root cause E (LC understated by a stable ~×1.205
  base/rate difference, candidates logged; TI + capex/reserves clean all
  11 years) and Cedar Alt root cause D (LC misses = 6.75% × adjudicated
  root cause C's free-rent deltas to the dollar; TI + reserves clean;
  CFBDS = NOI-cascade pass-through, verified arithmetically). Suite:
  313 passed + 4 golden reds (Gate 2 pair unchanged at 137/47).
  **Step 1 CLOSED 2026-07-12 (owner adjudications):** **Cedar Alt D
  closed as C's sibling** (no independent engine question) and
  **Freeport E DEFERRED to beta-stage GUI testing** — owner's reason:
  brokers sometimes charge a reduced leasing commission on renewals
  (e.g. 3-4% instead of the OM's stated blended rate), undetectable from
  OM text or annual fiscal-year totals; vetting needs the GUI's
  lease-by-lease/rollover inspection against the deal's real files. Same
  evidentiary category as Freeport B — not an engine defect. Both Gate 3
  capital tests stay red by design (no allowlist mechanism); not Gate 3
  blockers (NEXT_STEPS_TO_GATE3.md criterion 1 + Step 7).
  **Phase 3 Step 2 complete 2026-07-12:** purchase, closing costs,
  security deposits (`engine/calc/investment.py`, spec §3.16/§3.12,
  [AE pp. 435-437, 384, 431-433] read) — fixed-derivation price posts at
  the purchase month (schema `date` honored; ARGUS pins analysis begin
  [AE p. 435]); closing costs $ or %-of-price at purchase or custom
  date; derived derivations (pv_at_discount_rate / direct_cap) refuse
  loudly naming Step 5 — this also closed a no-silent-numbers hole
  (`purchase` previously had no consumer AND no guard). Security
  deposits per segment (both guards lifted): collection + at segment
  start, refund − in the final month when `refunded_at_expiration`;
  months-of-rent = month-one base rental revenue [AE p. 432], gross of
  free rent; $/SF × area; flat $; contract terms use the lease's spec,
  speculative the MLP's [AE p. 384]. Three new below-the-line ledger
  columns (Purchase Price / Closing Costs / Security Deposits) after
  CFBDS, in no rollup — CFBDS/NOI/EGR proven unchanged by test; the
  golden CSVs end at CFBDS so gate assertions are untouched. Narrowings
  + judgment calls (per-segment refund/recollect churn on renewal;
  pre-analysis starts refund-only) in DEVIATIONS.md §17. 13 manual-cited
  tests (tests/unit/test_investment.py). **EXTERNALLY UNVALIDATED — no
  golden populates purchase or security_deposit** (same standing as
  reabsorb/misc items). Suite: 326 passed + the same 4 golden reds.
  **Phase 3 Step 3 complete 2026-07-12 (one session; planned as two):**
  debt engine (`engine/calc/debt.py`, spec §3.17, [AE pp. 438-449] read
  in full) — per-loan amortization schedules (funding through maturity;
  pre-analysis funding supported per [AE p. 442], window opens at the
  then-current balance); monthly rate = annual/12 ([AE p. 443] "12
  Months" Calc Method); IO periods re-level at amortization start;
  balloon ("amortized N years due in M"; balloon posts at maturity);
  floating = index YearRate + spread with payment re-level on each rate
  change (manual silent — the [AE p. 444] same-term recalc applied to
  rate changes); additional principal = the [AE p. 444] Recalc-Pmt-NO
  behavior (schema has no toggle); loan costs to the financing section
  [AE p. 446], expense-at-funding or straight-line-over-term; multiple
  loans; `pct_of_value` sizing refuses naming Step 5; "Other Debt" NOT
  built (the docstring's fixed-payment-loan suggestion recorded as
  insufficient — DEVIATIONS.md §18). Ledger financing section live:
  Debt Funding (display-only, OUTSIDE CFADS — [AE p. 447] + §4.1 pass
  14 equity), Interest/Principal/Loan Costs, Total Debt Service, CFADS
  = CFBDS + TDS; Step 2's below-the-line columns moved after it.
  **§9.3 debt invariants standing on every run** (balance roll,
  non-negative, IO-amortizes-nothing, fully-amortizing balloon ~$0);
  per-loan LoanSchedule detail on RunResult for §7 report 20. 19
  closed-form tests (tests/unit/test_debt.py). **Validation = worked
  examples + the owner's bank-calculator hand-check (Step 0) — for
  debt that IS the designed path; no golden has loans.** Hand-check
  case ready: $1M / 6.00% / 30-yr am → pmt 5,995.51, balance@12
  987,719.88, balloon@120 836,857.25. Suite: 337 passed + the same 4
  golden reds (137/47, 33/12).
  **Phase 3 Step 4 complete 2026-07-12:** property resale
  (`engine/calc/resale.py` + `engine/reports/resale_audit.py`, spec
  §3.18, [AE pp. 464-471] read in full) — all five methods per their
  [AE p. 465] definitions: `cap_noi_forward_12` (window resale +1..+12,
  relative to the resale date, capped at analysis end);
  `cap_noi_current_year` = the analysis year of sale; `gross_value_
  less_costs` = "CAP Effective Gross Rents" = EGR − recoveries (Part A
  finding — the schema name mislabels it); `fixed_amount` = Enter Sale
  Price (gross AND net, no selling costs — refused if populated);
  `pct_increase_over_price` = total % over purchase price. NOI
  adjustments: `exclude_capital=True` a real no-op (NOI already
  excludes capital), `False` adds the window's Total Capital Costs;
  `stabilize_occupancy` = "NOI × Gross Up % / Average Occupancy %"
  [AE p. 469] over the run's occupancy series (no ledger recompute).
  Adjustments before selling costs [AE p. 465]; leveraged net =
  unleveraged − Σ resale-month loan balances (Step 3's series). Two
  below-the-line ledger columns (Net Resale Proceeds, Loan Payoff at
  Resale) — leveraged net is their visible sum; CFBDS/NOI/CFADS
  unchanged (test-locked). `apply_resale_to_cash_flow=False` computes +
  retains but posts nothing. Property Resale Audit built (spec §7 report
  21) reconciling exactly (1e-9). `direct_cap` refuses loudly (Step 5);
  only `valuation.resale` consumed. **§9.3 payoff-at-resale invariant
  standing** on every run with resale + loans. 18 tests
  (tests/unit/test_resale.py). Narrowings in DEVIATIONS.md §19.
  **EXTERNALLY UNVALIDATED — no golden populates valuation, none will.**
  Hand-check: current-year NOI 100,000 at 8.00% exit cap = 1,250,000
  gross, 3% selling 37,500, net 1,212,500. Suite: 363 passed + the same
  4 golden reds (137/47, 33/12).
  **Phase 3 Step 5 complete 2026-07-12:** PV / IRR / direct cap
  (`engine/calc/valuation.py`, spec §3.18/§4.1 pass 14, [AE pp. 450-476,
  453-454, 472-473] read) — unleveraged/leveraged PV under all six
  conventions (annual/quarterly/monthly × end/mid) at APR/p nominal
  discounting; unleveraged/leveraged IRR by periodic bisection,
  **nominal-annualized** (periodic × p) — the spec's effective
  `((1+irr_m)^12−1)` clause is inconsistent with its own APR/p
  discounting and would break self-consistency, so overridden
  (DEVIATIONS.md §20 #3); direct cap [AE pp. 453-454] with year_1 vs
  pv_start-anchored forward_12 (distinct window from resale's). Streams:
  unleveraged = CFBDS + Net Resale Proceeds (t0 = price); leveraged =
  CFADS + leveraged net resale (t0 = equity = price − loan proceeds);
  below-line items excluded. Leveraged metrics = None (not silent zero)
  without loans/price. **§9.3 PV/IRR self-consistency now standing**
  (`assert_pv_irr_self_consistency`: price == unlev PV ⟹ IRR == discount
  rate within 1bp, every convention). `direct_cap` guard lifted; the
  `Purchase.derivation` + `pct_of_value` guard messages rewritten to
  name the real open question, not "Step 5". 18 tests
  (tests/unit/test_valuation.py). **EXTERNALLY UNVALIDATED — no golden
  populates valuation.** Excel hand-check: par stream −1,000,000 then
  80,000×4 and 1,080,000, annual EoP at 8% → PV 1,000,000, IRR 8.00%.
  **OPEN OWNER SCOPE DECISION — live price derivation + pct_of_value
  loans NOT built** (DEVIATIONS.md §20 #6): non-circular only for the
  no-loan / non-pct_increase-resale subset, and even that needs the
  acquisition posting deferred past valuation; value-sized loans need
  debt reordered after valuation. Nothing needs it today; the
  derivations refuse loudly. Suite: 381 passed + the same 4 golden reds
  (137/47, 33/12).
- **Next session's first prompt:** "Phase 3 Steps 1-5 are CLOSED
  (Step 1: TI/LC, golden #1 capital lines green within $0.50/cell,
  Freeport E deferred / Cedar Alt D closed as C's sibling; Step 2:
  purchase/closing/deposits, DEVIATIONS.md §17; Step 3: debt engine,
  DEVIATIONS.md §18, 'Other Debt' NOT built; Step 4: resale + Resale
  Audit, DEVIATIONS.md §19; Step 5: PV/IRR/direct cap shipped
  2026-07-12, `engine/calc/valuation.py`, DEVIATIONS.md §20 — all six
  discount conventions, nominal IRR annualization, §9.3 PV/IRR
  self-consistency invariant standing). **THREE owner hand-checks are
  now actionable** — ask whether he has run them and record outcomes in
  NEXT_STEPS_TO_GATE3.md Step 0: (1) Step 3 amort — $1,000,000 / 6.00% /
  30yr → pmt $5,995.51, balance@12 $987,719.88, balloon@120 $836,857.25;
  (2) Step 4 resale — current-year NOI $100,000 at 8.00% exit cap =
  $1,250,000 gross, 3% selling $37,500, net $1,212,500; (3) Step 5
  PV/IRR — par stream −1,000,000 then 80,000×4 and 1,080,000, annual
  end-of-period at 8% → PV $1,000,000, IRR 8.00% (Excel
  NPV()/IRR()-checkable). **ALSO put the OPEN OWNER SCOPE DECISION to
  Topper: live price derivation (`pv_at_discount_rate`/`direct_cap`
  price) + `pct_of_value` loans (DEVIATIONS.md §20 #6)** — build the
  clean no-loan derived-price subset (a post-valuation re-assembly) or
  leave the derivations permanently refusing? Nothing needs it today.
  Next build step is **Step 6: sensitivity matrices** — spec §3.18
  `sensitivity_intervals`, [AE pp. 451-452] — read first: IRR matrix
  (price × exit cap) and value matrix (discount rate × exit cap) as
  data builders (rendering is Phase 4), 5/7-point grids, each cell
  produced by **re-running valuation only, never the ledger** (spec §4.1
  note; the RunResult/ledger is the fixed input — resale + valuation
  already recompute cheaply from it). Cross-check test: every matrix
  cell equals a direct single-point valuation at those inputs. No golden
  exercises it — manual-structure + engineered tests only. After Step 6,
  Step 7 is the Gate 3 owner review. Remaining Step 0 decisions:
  valuation assumption sets for the goldens; pct_of_account stays
  guarded. REMEMBER the standing gaps: percentage rent + tenant misc
  items + purchase/deposits/debt/resale/valuation externally unvalidated
  (goldens can't exercise them); Freeport B, Cedar Alt B, Freeport E
  parked for beta-stage GUI testing — the 4 golden reds (137/47 Gate 2,
  33/12 Gate 3 capital) stay red by design, owner's queue, never tuning
  targets; Cedar Alt D closed, not open. Commit, push, update the
  progress note and this prompt."
