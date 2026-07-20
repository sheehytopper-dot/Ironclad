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
- Run tests: `.venv\Scripts\python -m pytest` (Windows). Current status: **GATE 4
  PASSED (owner declaration 2026-07-16) — Phase 5 (UI) IN PROGRESS: Step 0
  resolved (owner approval 2026-07-16, incl. the D6 amendment) and Step 1
  shipped (app shell + Calculate pipe; baseline `62617f1` — zero engine/
  changes, git-log-checked).** Phase 4
  complete: Steps 1 report-builder contract + toggle/period engine; 2 Cash Flow
  #1 + Benchmark #24; 3 valuation family #5/#6/#8/#9 + Loan Amort #20; 4
  Occupancy #15 + Lease Summary #11 + Lease Expiration #12 (with the #12
  correction — DEVIATIONS §25 — approved & pushed); 5 Exec Summary #2 +
  Assumptions #3 + Sources & Uses #4 + Resale Matrix #7 + Input Assumptions #23;
  6 Excel export package §8 + rent-roll export §5.2; 7 rent-roll import
  round-trip §5.2; plus the provenance polish pass and the restored
  readable-error coverage. **Phase 5 builds per the owner-approved
  [NEXT_STEPS_TO_PHASE5.md](NEXT_STEPS_TO_PHASE5.md) (Step 0 D1-D6 resolved
  2026-07-16, incl. the D6 amendment: the UI must surface the Freeport B /
  Cedar Alt B / Freeport E inspection detail); Iron Rule 1 boundary: ZERO
  changes under engine/ during UI work (Gate 5 git-log check from baseline
  `62617f1`).** Gate 3 passed 2026-07-12. Phase 1 shipped 2026-07-05:
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
  .icprop.json's full monthly ledger + fiscal subtotals to .xlsx (`*-monthly.xlsx`
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
  audit reports + a reconciliation sheet to .xlsx (`*-audits.xlsx` gitignored); run on
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
  **Phase 3 Step 6 complete 2026-07-12 — ALL SIX BUILD STEPS DONE:**
  sensitivity matrices (`engine/calc/sensitivity.py`, spec §3.18/§7
  reports 5-6, [AE pp. 451-452] read) — value matrix (unleveraged PV over
  discount rate × exit cap) + unleveraged/leveraged IRR matrices (price ×
  exit cap) as DataFrames on `RunResult.sensitivity`. Grids `count` ∈
  {5,7} centered on the base case; price axis = unleveraged PV at the
  discount-rate grid at the base cap ("prices at PV of rate grid" — a
  pure sweep, NOT live price derivation, Step 5 refusal untouched). Pure
  re-computation over the RunResult — ledger never recomputed; columns
  reuse `compute_resale` at a substituted cap, cells reuse the Step 5
  PV/IRR primitives; the cross-check test proves every cell equals a
  direct single-point Step 4/5 call. Leveraged IRR NaN without loans
  (no silent zero); sensitivity None for non-cap resale methods.
  **Also fixed a Step 5 holding-stream bug surfaced here** (PV had
  discounted the resale look-forward year the seller never owns; now
  truncated at the resale month via shared `valuation.holding_stream`,
  which also fixes apply_resale=False — DEVIATIONS.md §21; no golden
  affected). 11 tests (tests/unit/test_sensitivity.py). **EXTERNALLY
  UNVALIDATED — no golden populates valuation.** Hand-check: flat NOI
  100,000 → any diagonal value cell where discount == cap equals
  100,000/cap. Suite: 392 passed + the same 4 golden reds (137/47,
  33/12).
  **GATE 3 PASSED (owner declaration 2026-07-12).** All six Phase 3 build
  steps shipped 2026-07-11/07-12, one line each: (1) TI/LC posting —
  golden #1 capital lines green within $0.50/cell (DEVIATIONS.md §16);
  (2) purchase / closing costs / security deposits (§17); (3) debt engine
  — fixed/floating, IO, balloon, additional principal, loan costs;
  "Other Debt" deliberately excluded (§18); (4) property resale — all
  five methods + Property Resale Audit reconciling to 1e-9 (§19); (5)
  PV / IRR / direct cap — all six discount conventions, nominal IRR
  annualization, plus the holding-stream truncation fix (§20, §21); (6)
  sensitivity matrices — value + unleveraged/leveraged IRR grids,
  cross-checked cell-by-cell (§21). §9.3 invariant set extended and
  standing (debt balance roll, payoff-at-resale, PV/IRR 1bp
  self-consistency). Suite 392 passed / 4 by-design golden reds
  (Freeport Gate 2 137 deferred-B; Cedar Gate 2 47 deferred-B; Freeport
  Gate 3 capital 33 root cause E deferred; Cedar Gate 3 capital 12 root
  cause D closed as C's sibling) — none a blocker; the three owner
  hand-checks (amort, resale, PV/IRR) confirmed.
  **Price-derivation scope decision (owner decision 2026-07-12,
  DEVIATIONS.md §20 #6): `Purchase.derivation != fixed` and
  `LoanAmountBasis.pct_of_value` refuse permanently — no current deal
  backs out price from valuation or sizes a loan off it, and building it
  now is real architecture with zero current pull; a permanent boundary,
  not an open gap.** **Phase 4 begins** (spec §10: full §7 report catalog
  + Excel export).
  **DEVIATIONS §24 FULLY CLOSED (owner-verified 2026-07-13):** all eight
  Codex debt/resale/valuation findings adjudicated — **six fixed** (#1
  leveraged-IRR funding timing, #2 closing costs in returns, #3
  amortized-loan-cost cash timing, #5 one-time capital costs no longer
  capitalized in resale, #7 multiple-IRR guard, #8 convention-aware IRR
  floor; commit 33057f7) and **two answered as documentation** (#6
  stabilize-occupancy whole-NOI scaling, #10 end-of-month sale
  convention). The two sensitivity-module follow-ups (grid t0 reframe via
  shared `valuation._t0_costs`/`_apply_loan_proceeds`; per-cell NaN on
  ambiguous IRR) are **also CLOSED** (commit 5268c64). Suite 425 passed +
  the same 4 by-design golden reds (137/47, 33/12).
  **NEXT_STEPS_TO_PHASE4.md Step 0 RESOLVED (owner-confirmed 2026-07-13)**
  and recorded in-line in that file: (1) build the priority report set
  now, defer six low-frequency reports (#10 Returns Over Time, #13 Leasing
  Activity, #14 Tenant Cash Flow/Lease PV, #17 Percentage Rent Audit, #19
  Expense Group Audit, #22 Rent Schedule Audit); (2) §8 export gate =
  owner workbook spot-check + exact reconciliation + golden-CSV anchor (no
  ARGUS print available); (3) ModelingPolicies rounding default = **none**
  ([AE p. 508] — every Rounding option defaults to None), adjacent ARGUS
  policy defaults documented in `engine/reports/base.py` (monthly GV/CL
  [AE p. 506], % of Recoverable Expenses admin fee [AE p. 520], nominal
  growth inflation [AE p. 507], Rent-in-Prior-12-Months CPI [AE p. 514]);
  (4) tenant discount rate moot (#14 deferred).
  **Phase 4 Step 1 complete 2026-07-13:** the report-builder contract +
  toggle/period engine (`engine/reports/base.py`; spec §7 intro, §4.3).
  `Report(frame, meta)` dataclass (unpackable as the spec's `(DataFrame,
  metadata)` tuple); `Unit` toggle (Total $ / $ per SF / per-month /
  per-occupied-SF), `Period` toggle (monthly/quarterly/annual/fiscal) as
  reusable transforms over a monthly Total-$ frame — `aggregate_period`
  delegates to the ledger's own `to_annual`/`to_quarterly`/
  `to_fiscal_annual` (never separately computed, spec §2.3); `apply_unit`
  divides by the period's **mean rentable/occupied area** (per-SF /
  per-occupied) or **month count** (per-month), zero-area → NaN not a
  silent zero; `apply_rounding` report-level only. `ModelingPolicies`
  (rounding default none). `build_monetary_report` ties them together for
  §7 monetary reports. The three existing audits (Lease/Recovery/Resale)
  harmonized via additive `*_report` wrappers returning `Report`
  (monetary=False, unit/period pass-through) — the bare builders and
  `reconcile_*` helpers are UNCHANGED, their tests green. 24 new tests
  (tests/unit/test_report_base.py): aggregate matches the ledger exactly,
  sum(monthly)=annual=quarterly=fiscal (§9.3), correct PSF/per-occupied/
  per-month denominators, audits still reconcile to 1e-9. Suite: **449
  passed + the same 4 by-design golden reds (137/47 Gate 2, 33/12 Gate 3
  capital)** — counts unchanged.
  **Phase 4 Step 2 complete 2026-07-13:** Cash Flow report #1
  (`engine/reports/cash_flow.py`) + Benchmark Comparison report #24
  (`engine/reports/benchmark.py`); spec §7 reports 1/24, [AE pp. 535-539],
  §9.1. `cash_flow(result, *, unit, period, fiscal_year_end_month,
  analysis_begin)` is a **pure view of `ledger.frame`** — reuses Step 1's
  `build_monetary_report` (period aggregation + unit toggle + rounding),
  then transposes to accounts-as-rows in ledger (Cash Flow tree) order
  with per-row `tree` metadata (indent level / is_subtotal / section) in
  `meta.extra` for expandable detail; `reconcile_cash_flow` proves it ties
  to the ledger's own aggregation to 1e-9 across monthly/quarterly/annual/
  fiscal (Total-$ view; non-Total raises). `benchmark_comparison(fiscal,
  expected, *, fiscal_years, tolerance, account_to_column, skip_accounts)`
  is the reusable form of the golden tests' `_collect_misses` — emits a
  per-(account, fiscal-year) diff DataFrame with a `within_tolerance` flag
  at $500/line and a `miss_count`; `load_expected_cash_flow` loads a
  golden's CSV (summing rows that share an account), `miss_lines` formats
  the out-of-tolerance rows. **All three golden tests refactored to
  delegate `_collect_misses` to the builder** — identical comparison and
  miss-line formatting, the four by-design reds unchanged at 137/47/33/12
  (Clorox green). 20 new tests (tests/unit/test_cash_flow_report.py): Cash
  Flow reconciles to the ledger every period, subtotals tie, tree metadata,
  per-SF = total/rentable, non-Total reconcile raises; Benchmark tolerance
  flags / account_to_column / skip / miss-line formatting; the four goldens
  reproduce their exact counts through the builder. Suite: **469 passed +
  the same 4 by-design golden reds (137/47 Gate 2, 33/12 Gate 3 capital)**
  — counts unchanged. No engine/calc code touched; no Excel exporter, no
  deferred reports, no UI scaffolded.
  **Phase 4 Step 3 complete 2026-07-13:** the valuation report family
  (`engine/reports/valuation_reports.py`: #5 IRR Matrix, #6 Value Matrix,
  #8 Valuation & Return Summary, #9 Present Value) + Loan Amortization
  (`engine/reports/loan_amortization.py`: #20); spec §7 reports 5-6/8-9/20,
  [AE pp. 550-572, 593]. All **thin views over data already on
  `RunResult`** — no calculation added, ledger never recomputed. `value_
  matrix(result)` / `irr_matrix(result, *, leveraged)` view
  `result.sensitivity` (NaN cells render blank; `reconcile_matrix_to_
  source` ties to 1e-9, NaN↔NaN matches); `valuation_summary(result)` is
  the ValuationResult metrics as a (metric, value, detail) cascade with
  None→NaN so no-loan/no-price/no-direct-cap metrics render blank not zero
  (`reconcile_valuation_summary` to 1e-9); `present_value(result, *,
  leveraged)` exposes per-period cash flow / discount factor / PV via the
  valuation helpers (`_period_buckets`/`holding_stream`/`_apply_loan_
  proceeds`) and its `present_value` column **sums to the ValuationResult
  PV** (`reconcile_present_value` ~0, unlev + lev); `loan_amortization(
  result, loan_index)` is a loan's schedule frame, and `reconcile_loan_
  amortization` proves the schedules SUMMED over all loans tie to the
  ledger's Interest Expense / Principal Payments / Loan Costs exactly. §21
  cross-check surfaced in the report: the IRR-matrix center cell equals the
  ValuationResult IRR for a model priced at the grid's base (both 8% on the
  flat 100k-NOI property). 20 new tests (tests/unit/test_valuation_reports.
  py). **EXTERNALLY UNVALIDATED** — no golden populates valuation (none
  will); validated by RunResult reconciliation + the §21 cross-check +
  owner Excel hand-checks (DEVIATIONS §20/§21). Suite: **489 passed + the
  same 4 by-design golden reds (137/47 Gate 2, 33/12 Gate 3 capital)** —
  counts unchanged. No engine/calc code touched; no Excel exporter, no
  deferred reports, no UI scaffolded.
  **Phase 4 Step 4 complete 2026-07-13:** Occupancy #15
  (`engine/reports/occupancy.py`) + Lease Summary #11 & Lease Expiration
  #12 (`engine/reports/lease_reports.py`); spec §7 reports 11-12/15,
  [AE pp. 573-604]. All views over the run's occupancy series / resolved
  chains — count/area/percent reports, so `monetary=False` (no $ unit
  toggle). `occupancy(result, *, period, fiscal_year_end_month)` gives
  occupied / rentable / available SF + occupancy fraction per period;
  areas are stock quantities so a period figure is the **mean** over its
  months (via Step 1's `period_mean_area`), occupancy = mean-occupied ÷
  mean-rentable; `reconcile_occupancy` ties the monthly view to the run's
  series exactly (non-monthly raises), `assert_occupied_within_rentable`
  re-checks the §9.3 occupied ≤ rentable invariant. `lease_summary(result)`
  is one row per chain from its single contract segment (tenant / suite /
  status / type / area / term / contractual base rent monthly-annual-PSF),
  `reconcile_lease_summary` checks area+dates vs the segments.
  `lease_expiration(result, *, fiscal_year_end_month, statuses)` buckets
  each included chain's contract-term end by fiscal year → count / SF / %
  of building / expiring annual rent. **Its original "SF sums to rentable"
  acceptance was WRONG and is corrected (see the §25 note below).**
  17 → 27 tests (tests/unit/test_occupancy_lease_reports.py). **EXTERNALLY
  UNVALIDATED** — occupancy/lease reports have no golden CSV anchor;
  validated by RunResult reconciliation + occupied≤rentable + the corrected
  Lease-Expiration checks. Suite: **506 passed + the same 4 by-design golden
  reds** — counts unchanged. No engine/calc code touched.
  **Phase 4 Step 4 §12 CORRECTION 2026-07-13 (owner-directed; DEVIATIONS
  §25, diagnosis approved with amendments):** the shipped Lease Expiration
  criterion "SF sums to rentable" was **defective — the plan's criterion,
  not the engine** (a suite legitimately turns over more than once →
  cumulative expiring SF exceeds 100% of the building; a fixed rentable need
  not equal summed demised area — Freeport 128,087 vs 123,099). The
  tautological `reconcile_expiration_area` (subtracted the contract areas
  from themselves; never failed) is **deleted** and replaced: (1) a
  `statuses` inclusion filter on `lease_expiration`/`lease_summary` mirroring
  [AE p. 818]'s Lease Status checkboxes, keyed on `lease.status`, default
  contract-only (speculative + MTM excluded but selectable), agreeing with
  the Lease Audit's [AE p. 398] speculative labeling; (2)
  `reconcile_lease_expiration(report, model, …)` — a structural tie to the
  MODEL INPUT (`model.rent_roll` + `model.absorption`, rebuilt via
  `lease_term_periods`/`fiscal_year_of` — a source the builder never reads),
  diffing count + total SF + per-year count/SF, **capable of failing**; (3)
  `assert_expiration_within_building` — a per-year SANITY BOUND (labelled,
  not an invariant) asserted across FYE ∈ {3,6,9,12} (Freeport contract-only
  worst single year 28.9% at FYE=6, 39.9% at FYE=9 — conventions always
  named). Lease Summary's double-counting `total_area` is replaced by
  `distinct_demised_area` (deduped by suite; Freeport contract-only 122,870,
  honestly under the 123,099 building). Suite: **516 passed + the same 4
  by-design golden reds (137/47 Gate 2, 33/12 Gate 3 capital)**. No
  engine/calc code touched. **Fix reviewed & APPROVED by owner 2026-07-14,
  pushed (69b3d45).**
  **Phase 4 Step 5 complete 2026-07-14:** summary / echo + Resale Matrix
  (`engine/reports/summary_reports.py`: #2 Executive Summary, #3 Assumptions
  Report, #4 Sources & Uses, #23 Input Assumptions; `engine/reports/
  valuation_reports.py`: #7 Resale Matrix); spec §7 reports 2-4/7/23,
  [AE pp. 535-549, 550-572]. All views over RunResult + the input model — no
  new calculation. `sources_and_uses(result)` ties each dollar line to a
  below-the-line ledger column (purchase / closing / financing / debt
  funding / net resale / loan payoff) with **Equity** the balancing plug
  (acquisition sources = uses); `reconcile_sources_and_uses` ties to the
  ledger columns to 1e-6. `executive_summary(result, model)` = property +
  year-1 metrics (NOI/EGR/CFBDS from the ledger annual view, occupancy from
  the corrected series) + valuation results (None→NaN blanks); building area
  is the run's **rentable area, never a summed-contract-area** (DEVIATIONS
  §25); `reconcile_executive_summary` ties year-1 NOI/EGR + PV + rentable to
  their independent sources. `assumptions_report(model)` (#3, sectioned) /
  `input_assumptions_listing(model)` (#23, flat) echo the model's scalar
  inputs (collections summarized by count — detail lives in Lease Summary
  #11 / Loan Amort #20). `resale_matrix(result, model)` (#7) = net
  unleveraged resale over **resale year × exit cap** — a NEW resale-year
  axis re-running `compute_resale` per analysis-year-end and cap against the
  existing ledger (no recompute); `reconcile_resale_matrix` is
  non-tautological (independent anchor = the base-cap/run-resale-year cell
  equals `result.resale.net_unleveraged`; + cap-monotonicity), and the §21
  cross-check (each cell == a direct single-point `compute_resale`) is the
  test's acceptance. 16 new tests (tests/unit/test_summary_reports.py).
  **EXTERNALLY UNVALIDATED** — valuation/resale reports have no golden;
  validated by RunResult/ledger reconciliation + the §21 cross-check. Suite:
  **532 passed + the same 4 by-design golden reds (137/47 Gate 2, 33/12 Gate
  3 capital)** — counts unchanged. No engine/calc touched.
  **Step 5 test-defect fix 2026-07-14 (DEVIATIONS §25, owner-approved &
  pushed b3496b8):** the building-area regression test ran on a synthetic
  12,000/12,000 fixture where rentable == summed-contract, so it could not
  detect the §25 regression; it now runs on **Freeport** (123,099 vs 128,087)
  and fails if switched to summed-contract-area. DEVIATIONS §25 also records
  a failability audit of the three Step 5 reconcilers (all failable; two
  named coverage gaps: `reconcile_sources_and_uses` shares `_SU_LEDGER_ROWS`
  with its builder, `reconcile_resale_matrix` misses monotonicity-preserving
  non-anchor corruption — the §21 cross-check covers it) and the **STANDING
  RULE: a regression test must run on a fixture where the WRONG answer
  differs from the RIGHT answer** (applies through Phase 6).
  **Phase 4 Step 6 complete 2026-07-14:** the Excel export package
  (`engine/export/package_builder.py` + `engine/export/rent_roll_export.py`;
  spec §8, §5.2). `build_package(result, model, *, path, reports?, scenario,
  timestamp)` writes one workbook, a tab per applicable report (the §8
  11-report default: Executive Summary / Annual + Monthly Cash Flow / Lease
  Summary / Lease Expiration / IRR + Value Matrix / Present Value / Recovery
  Audit / Loan Amortization / Assumptions), values-only, §8 formatting
  (indigo title band, Cash-Flow tree indentation + bold subtotals, negatives
  in red parens via `#,##0;[Red](#,##0)`, frozen panes, auto widths, footer
  with property/scenario/timestamp, unit/period noted under the title).
  Reports needing valuation / sensitivity / loans are **skipped when
  inapplicable, never fabricated**. `export_report` does single-report
  export; `export_rent_roll(model, *, path)` writes the §5.2 template (Rent
  Roll + Rent Steps + Misc Items sheets) for the Step 7 round-trip. **The
  exporter formats already-built Report DataFrames — it recomputes NOTHING**
  (no ledger/valuation/area recomputation; building area is the run's
  rentable area, never a summed-contract-area — verified on Freeport at the
  export layer). `report_cell_grid(report)` is the single source of the grid
  written; `_cellify` normalizes cells (NaN→blank, Period→str). 7 new tests
  (tests/unit/test_export.py): every default tab's cells equal its builder
  DataFrame (openpyxl read-back, cell-by-cell); a **corrupt-a-written-cell
  discrimination test** proves the diff can fail (DEVIATIONS §25 rule);
  applicability (bare model omits loan/valuation tabs); the Freeport
  Executive-Summary tab surfaces 123,099 not 128,087; single-report export;
  rent-roll template layout + a step round-trips to the companion sheet.
  Suite: **539 passed + the same 4 by-design golden reds (137/47 Gate 2,
  33/12 Gate 3 capital)** — counts unchanged. No engine/calc touched.
  **Phase 4 Step 7 complete 2026-07-14 (the LAST Phase 4 build step):** the
  rent-roll importer (`engine/intake/rent_roll_import.py`; spec §5.2/§5.4) —
  the second intake surface. Reads the template `rent_roll_export.py` writes
  (Rent Roll + Rent Steps + Misc Items sheets; CSV also via
  `import_rent_roll_csv`), validates through the §3 pydantic
  Lease/RentStep/MiscItemSpec models, returns a validated `list[Lease]`.
  Reads ONLY the rent-roll template — never an OM (§1.2/§5.4). **Readable
  errors:** every message names sheet / row / column / offending value / the
  fix; ALL rows validated and every error collected before raising
  `RentRollImportError`; pydantic cross-field errors translated to row-level
  lines (no stack trace). Flat §3.12 fields + steps + misc name/amount/unit/
  abatement round-trip; nested structures (free rent/recoveries/pct rent/
  deposits/misc timing) live in the JSON, out of the flat template's scope
  (§5.2). 31 tests (tests/unit/test_rent_roll_import.py): round-trip
  reproduces every flat field (xlsx + CSV); **DEVIATIONS §25 discrimination**
  — corrupting any of 11 fields (or dropping the notes column, or a rent
  step) breaks the round-trip; readable-error tests assert MESSAGE CONTENT
  (row/column/value/fix), all-errors-collected, missing-column named,
  cross-field rule translated, surface is not a pydantic dump. engine/calc
  untouched. **Step-7 blank-cell fix 2026-07-15 (owner review; commit
  c8e0ec3):** blank REQUIRED cells (base_rent_amount / lease_type /
  base_rent_unit / area / start_date, and misc `unit`) previously leaked raw
  pydantic/ValueError dumps — the §5.4-forbidden surface; now routed through
  the readable RentRollImportError (required-field check + a translating
  guard over all model/enum construction catching ValidationError AND
  ValueError). Confirmed a blank optional column is the §3 schema default
  (status → contract, upon_expiration → market), asserted by tests. +9 tests.
  Suite: **570 passed + the same 4 by-design golden reds** — counts
  unchanged.
  **GATE 4 PASSED — owner declaration 2026-07-16** (evidence prepared
  2026-07-14; the §8 workbook spot-check — criterion 6, the one owner action —
  completed 2026-07-16 on the regenerated workbooks). Criteria 1-6
  (NEXT_STEPS_TO_PHASE4.md Step 8) were evidenced by: (1) builder contract —
  engine/reports/base.py + the builders conform, test_report_base.py; (2)
  unit/period toggles + sum(monthly)=annual=fiscal + PSF/per-occupied
  denominators — test_report_base.py; (3) the §8 default report set built +
  reconciling, Cash Flow + Benchmark against the golden CSVs —
  test_cash_flow_report.py (reproduces 137/33/47/12 + Clorox 0) + the
  per-report reconcile tests; (4) Excel package values-only, a tab per report,
  §8 formatting, single-report + rent-roll export — test_export.py
  (cell-by-cell + corrupt-a-cell discrimination); (5) rent-roll import
  round-trip + readable errors — test_rent_roll_import.py; (6) the owner
  workbook spot-check via `scripts/build_gate4_workbook.py`. **18 of 24
  report builders exist** (the Step-0-deferred six #10/#13/#14/#17/#19/#22
  stay deferred); the §8 default set (11 reports) is complete. The four
  by-design golden reds stay red by design (not Gate 4 blockers).
  **Report/export/intake POLISH PASS 2026-07-15 (owner-directed; Gate 4 still
  HELD; DEVIATIONS §25):** report/export/intake layer only — engine/calc and
  engine/models untouched, four golden reds unchanged. Provenance
  (Contractual vs Speculative, keyed on lease.status / segment.speculative =
  the [AE p. 398] rule): (1) `export_rent_roll(result, *, path)` now takes the
  **RunResult** and emits one unified Rent Roll sheet with a `status`
  (Contractual/Speculative) + `lease_status` column — Speculative rows are the
  engine-projected rollover+absorption generations from `result.segments`
  (Freeport 58 vs 1 model.absorption), which `model.absorption` alone would
  miss; (2) the importer reads ONLY Contractual rows, blank provenance stays
  Contractual, and returns an `ImportResult(leases, notes)` reporting the
  ignored Speculative rows (not a silent skip) — Step-7 readable errors
  preserved; (3) reports #11/#12 default to the full view (contract+mtm+
  speculative) with an explicit provenance label per row, contractual-only
  selectable (`CONTRACTUAL_STATUSES`), #12 rows per (fiscal year, provenance),
  reconcilers + sanity bound still failable; (4) Cash Flow subtotal bolding
  refined (grand totals EGR/NOI/CFBDS/CFADS get a rule line — values
  unchanged, Step-6 tests still pass). **NAMED TRADEOFF (DEVIATIONS §25):**
  Contractual rows reconcile to independent model input (model.rent_roll /
  model.absorption); MLP-rollover Speculative rows in the EXPORT reconcile
  only to result.segments — a weaker check, because engine-projected tenancy
  has no independent model source. Percentage rent on speculative tenancy
  stays externally unvalidated pending golden #3. **Readable-error test
  coverage restored 2026-07-15** (the pass initially dropped ~8 tests
  570→560; restored to 32 in test_rent_roll_import.py — DEVIATIONS §25, plus
  the standing rule "a test-file rewrite MUST list every test removed").
  Suite: **573 passed + the same 4 by-design golden reds (137/47 Gate 2,
  33/12 Gate 3 capital)**. The Gate 4 workbooks were regenerated for the
  owner re-spot-check.
  **Phase 5 Step 0 RESOLVED + Step 1 complete 2026-07-16/17:** Step 0 D1-D6
  approved as recommended (D1 in-process engine import, FastAPI deferred —
  DEVIATIONS §26; D2 full editors for the exercised §3 surface + read-only
  refusals + raw-JSON escape hatch; D3 Gate 5 = Clorox rebuilt through the
  UI, engine-to-engine IDENTICAL fiscal cash flow, + the Freeport timing
  exercise; D4 scenario = duplicate JSON; D5 Dashboard default-active +
  Tenants split pane; D6 investigation post-Gate-5 **with the amendment**:
  Phase 5 must BUILD the three inspection surfaces — GV basis decomposition
  [Freeport B, Audit tab, Step 6], recovery timing drill by tenant +
  segment_start [Cedar Alt B, Audit tab, Step 6], and the **confirmed-gap**
  per-generation rollover economics incl. renewal LC rates [Freeport E,
  Tenants split-pane "Rollover generations" panel, Step 4 — data already on
  `result.segments`: lc_pct/lc_rate/renewal_weight per segment; no engine
  change needed]; Gate 5 criterion 6 added). **Step 1 (app shell)**:
  `app.py` + `ui/main.py` (thin renderer) + `ui/state.py` (pure,
  browser-free helpers — Iron Rule 1: ui imports engine only). Sidebar:
  property selector over `data/properties/` (env-overridable for tests),
  Open/Save, New Property (minimal valid model), upload-JSON intake,
  **Calculate** → `run_property` with the RunResult cached in session state
  and invalidated on every model change (`_set_model`). §5.4 readable
  errors everywhere (JSON/pydantic translated with field path + offending
  value + SCHEMA_GUIDE pointer; engine refusals framed verbatim; never a
  traceback). Nav = spec §6 tab order with Dashboard default-active (D5;
  horizontal radio because st.tabs cannot set an active tab); minimal
  Dashboard (year-1 NOI + occupancy off the ledger's own annual view — no
  UI-side math). 18 new tests (test_ui_state.py 12 pure + test_ui_app.py 6
  AppTest flows), all §25-discriminating: Clorox literals ($2,596,319 /
  100.0%), model_dump identity flipped by a one-field edit, corrupted-JSON
  readable content + no-traceback assertions, D5 default-tab check, engine
  refusal panel. **Known nit flagged, NOT fixed (engine boundary): the
  engine's pct_of_account refusal message still says "until Phase 2" — a
  stale label inside engine/calc/run.py; owner call whether to batch an
  engine wording pass later.** Suite: **591 passed + the same 4 by-design
  golden reds (137/47 Gate 2, 33/12 Gate 3 capital)**; `git log
  62617f1..HEAD -- engine/` is EMPTY.
  **Phase 5 Step 2 complete 2026-07-17:** the Property + Market tabs.
  `ui/session.py` (the one place a model is installed: RunResult
  invalidated on EVERY change, `model_rev` nonce resets editor widgets on
  document switch); `ui/state.updated_model(model, mutate)` — the single
  edit funnel: mutate the `model_dump(mode="json")` dict, revalidate the
  WHOLE document, §5.4 readable per-field errors (all-or-nothing; the
  original model untouched on error; the "got …" clause truncated at 120
  chars so a document-level validator can't dump the whole model into the
  message — found and fixed in-session); `ui/convert.py` pure grid↔model
  converters (YearRate rows, area schedule, tenant overrides, free-rent
  profiles, MLP scalar grid merge-by-row-order preserving nested detail,
  RentStep rows; blank rows drop; empty grids → None). `ui/tabs/
  property_tab.py` (PropertyInfo + Address + AreaMeasures incl. the
  schedule editor) and `ui/tabs/market_tab.py` (Inflation + the four
  series + custom indices; GV/CL with method/rates/PGR-account
  multiselect/overrides/reduce-flag; MLP scalar grid + per-MLP detail
  editor — market rents new/renew incl. %-of-new vs amount vs
  %-of-last-rent, TI new/renew, LC pct+years vs rate, recovery
  assignment, free-rent/chained refs, rent-increase steps; free-rent
  profile grid). Per D2: TI/LC categories READ-ONLY with the engine's
  refusal wording; MLP percentage_rent / misc_items / security_deposit
  read-only JSON (unexercised by goldens); an honest CPI note — the §3
  schema has NO top-level CPI profiles (per-lease, Tenants tab Step 4).
  Plain widgets + explicit Apply buttons (AppTest cannot drive
  st.form_submit_button / st.data_editor; grid depth is covered by the
  pure tests). 36 new tests: tests/unit/test_ui_tabs.py (33 pure —
  parametrized round-trip + §25 one-field discrimination on the real
  goldens, readable per-cell errors incl. cross-ref breaks like dropping
  a referenced free-rent profile, MLP grid add/delete preserving nested
  detail, converters) + 3 AppTest flows ADDED to test_ui_app.py (nothing
  removed): Property edit → model updated + result invalidated; bad term
  → readable panel + model unchanged; Market renders Freeport with the
  read-only notes. Suite: **627 passed + the same 4 by-design golden reds
  (137/47 Gate 2, 33/12 Gate 3 capital)**; `git log 62617f1..HEAD --
  engine/` EMPTY.
  **Phase 5 Step 3 complete 2026-07-17:** the Revenues + Expenses tabs.
  `ui/convert.py` additions (revenue/expense scalar grids, annual-override
  + expense-group rows, and the **refused-row lifecycle**:
  `pct_of_account` items are excluded from the editable grid, re-inserted
  UNTOUCHED at their original positions on apply, and detail-edits on them
  refuse readably — read-only means read-only); `ui/tabs/common_widgets.py`
  (shared Timing / Limits / Inflation editors — inflation as
  general-default | named index | custom YearRate schedule);
  `ui/tabs/revenues_tab.py` (misc/parking/storage grids + per-item detail)
  and `ui/tabs/expenses_tab.py` (grid + per-item detail incl. amount/unit/
  timing/limits/annual overrides/inflation + ExpenseGroups with CSV
  members). Engine-refused rows show the refusal VERBATIM — including the
  stale "until Phase 2" expense wording, deliberately surfaced as-is and
  now on the **stale-message list in NEXT_STEPS_TO_PHASE5.md** (post-Gate-5
  wording pass; a §25 test asserts the UI copy matches the engine's actual
  message, so the wording pass will fail it and force the UI copy update).
  **The fixed-point end-to-end check:** editing Clorox's management fee
  3%→5% through the tab's own apply fn + Calculate lands the HARD literals
  fee 200,497.09 / EGR 4,009,941.72 (vs 3% baseline 117,817.88 /
  3,927,262.51), fee = exactly 5% of final EGR — and the §25 catch: NOI
  stays 2,596,319.40 under BOTH (the fee is recoverable — pass-through),
  so NOI was deliberately NOT used as the discriminator; the fee/EGR
  literals are. 21 new tests: tests/unit/test_ui_tabs_step3.py (19 pure)
  + 2 AppTest flows ADDED to test_ui_app.py (nothing removed): the fee
  edit through the WIDGET path → Calculate → the 5% literal in
  session_state.result; Revenues renders Freeport. Suite: **648 passed +
  the same 4 by-design golden reds (137/47 Gate 2, 33/12 Gate 3
  capital)**; `git log 62617f1..HEAD -- engine/` EMPTY.
  **Phase 5 Step 4 complete 2026-07-18:** the Tenants tab — the biggest.
  Rent-roll grid (base_rent flattened to amount+unit columns, merge by row
  order preserving nested detail; the new-row template defaults
  `upon_expiration: vacate` so a fresh row is valid BEFORE an MLP link —
  the §3.12 market-requires-MLP rule then fires readably on switch) + the
  D5 **persistent split-pane lease detail** (rent steps, CPI, free rent,
  misc items grid, security deposit, a compact % rent editor
  [sales volume + breakpoint + layers; flagged externally unvalidated
  pending golden #3], recovery assignment via the shared
  `common_widgets.recovery_assignment_inputs`, contract-term TI/LC with
  the **category refusal shown verbatim** and categories preserved
  untouched); `AbsorptionSpec` grid; the **recovery structure builder**
  (add/delete structures; per-pool: expense/group multiselect members,
  method, gross-up, stop, admin fee + applies, denominator, share
  override, caps/floors, expense adjustments — exercised against
  Freeport's 13 real structures); the **§5.2 template import surface**
  (uploader + AppTest-able path field; `ImportResult.notes` as info
  banners — never a silent skip; Step-7 readable errors verbatim; apply
  revalidates the whole document so an unknown-MLP import refuses
  readably); and **the D6-amendment 'Rollover generations
  (engine-projected)' READ-ONLY panel** (the Freeport E surface) —
  per-generation start/end, provenance, renewal weight, blended rent,
  downtime, free months, TI, LC pct/rate off `result.segments`
  (`convert.segments_to_generation_rows`; prompts "Calculate to view"
  when no result). 24 new tests: tests/unit/test_ui_tabs_step4.py (21
  pure — grid/detail/absorption/structures round-trips + §25
  discrimination on Freeport, readable errors incl. the real
  market-requires-MLP + both-end-and-term rules, template import
  [Contractual subset identical, note present, malformed row verbatim,
  unknown-MLP apply refused], and the generations literals: **LC '6.75%
  of rent', renewal weight 0.75, TI '12.5 dollars_per_area', vacate chain
  = single Contractual generation, absorption first term = Speculative**)
  + 3 AppTest flows ADDED to test_ui_app.py (nothing removed): Tenants
  renders Freeport (pre-Calculate prompt), the generations panel shows
  the Freeport E literals through the WIDGET path (dataframe located by
  its provenance column — data_editors register as dataframes too), and
  import-by-path lands 29 Contractual leases with the note displayed.
  Suite: **672 passed + the same 4 by-design golden reds (137/47 Gate 2,
  33/12 Gate 3 capital)**; `git log 62617f1..HEAD -- engine/` EMPTY.
  **Phase 5 Step 5 complete 2026-07-19:** the Investment + Valuation tabs.
  `ui/convert.py` additions (closing-cost rows, loan scalar grid with
  base_rent-style flatten [amount value+basis, rate as fixed % or the
  '(floating)' placeholder, amortization as text→int-years parse],
  additional-principal + resale-adjustment rows; **pct_of_value loans get
  the refused-row lifecycle** — excluded from the grid, preserved at
  position, detail-refused readably); `ui/tabs/investment_tab.py`
  (Purchase + closing-costs grid [fixed derivation only — a derived-price
  purchase renders READ-ONLY with the engine's refusal verbatim]; loan
  grid + per-loan detail: fixed/floating rate [the §3.17 `Loan.type` must
  track the rate shape — found via the 'fixed loans require a numeric
  rate' validator, the payload/converter set it automatically], IO months,
  additional principal, loan costs incl. the DEVIATIONS §18/§24
  handling-is-accounting note); `ui/tabs/valuation_tab.py` (DCF, direct
  cap, `Resale` with method-appropriate field visibility across all five
  methods [cap methods → exit cap + NOI adjustments + stabilize;
  fixed_amount → sale price only, selling/adjustments hidden per
  [AE p. 465]; pct_increase → pct + selling + adjustments],
  `SensitivityIntervals`; whole block optional). **Both permanent-refusal
  messages carry the STALE 'OPEN OWNER SCOPE DECISION' label** (the
  decision closed 2026-07-12) — added as items 2-3 on the stale-message
  list in NEXT_STEPS_TO_PHASE5.md, surfaced verbatim with a
  decision-closed caption. **The hand-check anchors land through the
  tabs' own apply fns as hard literals:** amort payment 5,995.51 +
  balance@12 987,719.88 ($1M/6%/30yr), balloon 836,857.25 (30-due-in-120),
  resale gross 1,250,000 / net 1,212,500 (100k-NOI/8%-cap/3%-selling),
  and price==PV ⟹ IRR 8.00% within 1bp. 25 new tests:
  tests/unit/test_ui_tabs_step5.py (23 pure — the three anchors,
  purchase/loan/valuation round-trips + §25 discrimination on the
  engineered flat-100k fixture, floating-rate end-to-end (7.5/9.5),
  refused lifecycles for BOTH permanent refusals with engine-message
  containment tests [the wording pass will fail them and force the UI
  copy update], readable errors, fixed_amount = gross AND net,
  pct_increase-needs-purchase) + 2 AppTest flows ADDED to test_ui_app.py
  (nothing removed): Investment + Valuation render the engineered demo;
  the selling-costs edit through the WIDGET path → Calculate → net
  1,250,000 (vs the 3% baseline 1,212,500). Suite: **697 passed + the
  same 4 by-design golden reds (137/47 Gate 2, 33/12 Gate 3 capital)**;
  `git log 62617f1..HEAD -- engine/` EMPTY.
  **Phase 5 Step 6 complete 2026-07-19 — ALL SIX BUILD STEPS DONE; every
  spec §6 tab renders:** the Reports + Dashboard + Audit tabs.
  `ui/reports_registry.py` (pure): one entry per built report with
  applicability gates (valuation/sensitivity/loans/resale) + the global
  unit/period toggles wired straight to the builders — **frame equality
  against the builders asserted per report** (assert_frame_equal; the
  unit toggle §25-discriminates: Clorox NOI $2,596,319.40 total vs /540k
  per-SF); the date-range slice is a pure column selection (values
  untouched, test-locked); Benchmark #24 gated on the golden-convention
  `expected_annual_cash_flow.csv` beside the loaded JSON — **CSV accounts
  with no ledger match are SKIPPED AND REPORTED** in meta (Clorox: 0
  misses with 'Capital Expenses' reported-skipped [the name bridge is
  golden-test knowledge]; Freeport: **170 = exactly the 137 Gate-2 + 33
  Gate-3 by-design reds** — the UI reproduces the known counts).
  `ui/tabs/reports_tab.py`: picker + toggles + provenance captions +
  contractual-only checkbox + loan picker + **export-this-view and the §8
  package export via the Phase 4 machinery** (export_report /
  build_package — nothing rewritten; the UI-exported view matches the
  builder frame via the engine's own report_cell_grid, test-locked).
  `ui/tabs/dashboard_tab.py`: KPI cards (Year-1 NOI/Occupancy [Step-1
  labels preserved], Purchase Price + Going-in Cap from exec-summary #2,
  PV/IRRs/Direct Cap off result.valuation, None→'—') + Plotly charts
  (annual NOI/CFBDS off the ledger's own annual view; monthly occupancy;
  expirations by fiscal year colored by provenance; top-tenants from
  #11). **Equity multiple deliberately ABSENT — no engine surface
  computes it and UI-side recomputation is banned; FLAGGED as a
  post-Gate-5 engine candidate** (NEXT_STEPS_TO_PHASE5.md "Flagged engine
  candidates", with the per-item property-revenue drill as the second
  entry). `ui/tabs/audit_tab.py`: account+month → composition (ledger
  revenue lines → per-tenant Lease Audit rows [tie to the ledger to the
  cent: recoveries 20,840.57 at Freeport 2026-07]; expense accounts →
  per-item series; TI/LC → per-tenant postings; loan lines → per-loan
  schedules; subtotals/GV say so honestly) + **the two remaining
  D6-amendment surfaces (Gate 5 criterion 6): the Freeport B GV
  basis-decomposition panel** (candidate bases read from the LEDGER,
  method/include/overrides from the model, implied rate per basis —
  Freeport 2026-07 literals: GV −7,071.48, A&T −4,620.00, basis
  229,209.66, implied 3.09% on percent_of_pgr) **and the Cedar Alt B
  recovery-timing drill** (pure filter over the Recovery Audit's
  (tenant, segment_start, pool, month) rows — isolates 'Bldg 1 Tenant
  (Confidential)' seg 2033-09: recovery 173,504.82, share 0.803174).
  24 new tests: tests/unit/test_ui_tabs_step6.py (21 pure) + 3 AppTest
  flows ADDED to test_ui_app.py (nothing removed): Reports renders #1,
  the full Dashboard renders with the Step-1 labels intact + '—' for
  no-valuation, Audit renders both D6 panels. Suite: **721 passed + the
  same 4 by-design golden reds (137/47 Gate 2, 33/12 Gate 3 capital)**;
  `git log 62617f1..HEAD -- engine/` EMPTY.
  **UI usability pass Tier 1 complete 2026-07-19 (owner-directed Gate 5
  prerequisite; Tier 2 visual redesign is a separate planned pass):**
  `ui/format.py` — a pure DISPLAY-ONLY formatting layer (thousands
  separators, accounting negatives in parens, Total-$ 0dp / per-SF 2dp
  keyed off report.meta, percent/fraction columns as X.X%); **the
  guardrail is test-locked §25-style: each formatter test asserts the
  display string AND that report.frame stays byte-identical at full
  precision** (assert_frame_equal check_exact + the literal
  2596319.4000000004) — builders, frame-equality tests, and the Excel
  exporters keep operating on raw frames. Cash Flow #1 renders
  ARGUS-style via the tree metadata already in meta.extra['tree'] (NBSP
  indent by level, bold subtotals, top-rule grand totals — a pandas
  Styler over a display COPY; the date slice stays a pure column
  selection). Formatter applied across Reports / Dashboard top-tenants /
  Audit composition+GV+drill (the pure fns still return RAW frames;
  render wraps). Navigation moved to a LEFT-SIDEBAR vertical list grouped
  ✏️ Inputs / 📊 Outputs via format_func DISPLAY labels — the radio key
  (`active_tab`) and raw option values unchanged, so every existing
  AppTest flow passes untouched; Dashboard default-active (D5). 10 new
  tests (test_ui_format.py 8 pure + 2 AppTest), and TWO existing nav
  assertions MODIFIED (not removed, noted in-file): AppTest `options`
  reflect format_func labels, so the two option-list checks now strip the
  display glyph and additionally assert raw-value set_value still works.
  Suite: **731 passed + the same 4 by-design golden reds (137/47 Gate 2,
  33/12 Gate 3 capital)**; `git log 62617f1..HEAD -- engine/` EMPTY.
  **Owner re-review of readability precedes the Step 7 Gate 5 run.**
  **UI Tier 2 foundation + reference screens complete 2026-07-19
  (presentation only; plan: [NEXT_STEPS_UI_TIER2.md](NEXT_STEPS_UI_TIER2.md)):**
  design tokens + rollout order + the honest acceptance model (pure CSS
  has no §25 oracle — owner visual review vs the Claude Design mockup is
  the judgment; what IS test-locked: **the app accent == the Excel
  exporter's spec §8 indigo `#3F3D8A`** — `theme.INDIGO ==
  package_builder._HEADER_BG`, read not guessed, breaks the build if
  either drifts — plus the config-toml hex pin, CSS-contains-tokens,
  single-injection, and `streamlit==1.58.0` pinned in pyproject per the
  brittleness rule with ALL custom CSS centralized in `ui/theme.py`).
  `.streamlit/config.toml` (dark institutional base, IBM Plex Sans/Mono
  fontFaces) + `ui/theme.py` (tokens, hairline/KPI-card/sidebar/
  tabular-figures CSS, the shared `plotly_layout`) injected once in
  `ui.main.render`. Reference screens ONLY (the other 8 tabs are
  deliberately unskinned pending owner reaction): Dashboard — the
  mockup's 6 KPI cards in a 3×2 grid (IRR-leveraged + Direct Cap moved
  to the caption line; every test-asserted label kept), themed
  side-by-side NOI/CFBDS + occupancy charts, themed expiration bars,
  dense top-tenants grid (`row_height=30`); Reports — compact
  terminal-style control row (picker + toggles inline), dense report
  grids. 5 new tests (test_ui_theme.py). Suite: **736 passed + the same
  4 by-design golden reds**; `git log 62617f1..HEAD -- engine/` EMPTY.
  **Owner reviews Dashboard + Reports beside the mockup before the
  remaining tabs are skinned (Tier 2 rollout steps 3-5).**
  **MAJOR DIRECTION CHANGE (owner decision 2026-07-19): the WEB FRONT-END
  PIVOT.** The Streamlit UI cannot reproduce the Claude Design mockup's
  layout/functionality. The application moves to a real web front-end
  (built from the mockup export `design/Ironclad.dc.html`, to be dropped
  in by the owner) talking to the FROZEN engine through a FastAPI API —
  activating the spec §2.1 FastAPI layer that Step 0 D1 deferred (the
  "second client" has arrived; DEVIATIONS §26 gets an addendum when the
  API lands). **Plan drafted:
  [NEXT_STEPS_WEB_FRONTEND.md](NEXT_STEPS_WEB_FRONTEND.md) — PLAN ONLY,
  awaiting owner review + its Step 0 (W1-W7) sign-off + the mockup file;
  no api/ or frontend/ code before that.** Key terms: Iron Rule 1
  extends (engine/ frozen, boundary check from 62617f1 unchanged; api/ +
  frontend/ import the engine, never the reverse); **Streamlit is
  FROZEN, NOT deleted** — runnable fallback + behavioral reference until
  the new front-end passes the RELOCATED Gate 5 (Clorox from-scratch
  identity + Freeport load-and-drive, same rigor, owner-declared), then
  retired in a separate owner-approved commit; the API is a thin
  serializer over EXISTING engine/report/export/intake functions
  (full-precision split-orient frames; §5.4 errors as structured JSON —
  field path + offending value + fix, never a traceback); API⇄builder
  reconciliation tests with §25 discrimination + the golden literals;
  the front-end itself judged by API-correctness + relocated Gate 5 +
  owner visual review (no pixel oracle — stated honestly); rollout =
  API core → the mockup's three designed screens end-to-end (Dashboard,
  Reports, Tenants) → the other seven tabs.
  **Pivot plan APPROVED (owner + advisor, 2026-07-20): W2-W7 as
  recommended; W1 (framework) DEFERRED to the mockup-export inspection —
  do NOT default to vanilla JS (the editable grids span ~6 tabs; choose
  on the real export). API CORE BUILT (rollout step 2, 2026-07-20;
  DEVIATIONS §26 addendum — the FastAPI layer is ACTIVE):** `api/main.py`
  + `api/serialize.py` — thin serializers over EXISTING functions (the
  API computes nothing; imports the engine + the pure `ui/` modules per
  W7). Endpoints: properties list/GET/PUT (whole-document revalidation;
  422 = structured readable JSON {summary, problems:[{field, message,
  got≤120chars}], reference} — never a traceback; PUT saves AND
  invalidates the server-side RunResult cache), rent-roll import
  (Contractual leases + `ImportResult.notes`, Step-7 errors verbatim),
  calculate (cache + compact summary + applicability flags incl.
  benchmark-CSV), reports list/GET (registry-driven; unit/period/
  contractual_only/loan_index params; split-orient FULL-PRECISION frames
  with **NaN→null** — literal NaN is invalid JSON; meta.extra whitelist
  incl. the Cash Flow tree), the audit composition + BOTH D6 panels
  (gv-basis, recovery-drill incl. filter options), package/report export
  (FileResponse via the Phase 4 machinery). **API-side judgment call
  (DEVIATIONS §26 addendum): the golden benchmark-CSV convention is
  per-DIRECTORY and `data/properties/` is flat — a shared CSV would
  silently benchmark every property against the same numbers (caught in
  the smoke: clorox picked up freeport's CSV) — so the API requires
  `<name>.expected_annual_cash_flow.csv`, directory-level only in
  single-property dirs; #24 is NOT offered otherwise (test-locked).**
  19 new tests (tests/unit/test_api.py, TestClient): endpoint==builder
  frame equality EXACT through JSON (full-precision literal
  2596319.4000000004 over HTTP), the §25 unit-toggle discrimination, the
  golden literals (benchmark 170/[]; GV −7,071.48 / 229,209.66 / 3.09%;
  drill 173,504.82 / 0.803174; composition 20,840.57), NaN→null
  round-trip on the demo's leveraged metrics, structured 422s
  (field/got/no-Traceback/no-pydantic; refusals verbatim incl. the stale
  "until Phase 2" wording), PUT-invalidates-cache → 409 → recalculate,
  import 29-leases + note + malformed-row verbatim, xlsx downloads.
  Deps: uvicorn + python-multipart added; httpx as a dev dep.
  `ui/`+`app.py` UNTOUCHED (frozen fallback). Suite: **755 passed + the
  same 4 by-design golden reds**; `git log 62617f1..HEAD -- engine/`
  EMPTY.
  **W1 RESOLVED (owner-approved 2026-07-20): React + Vite**, styled from
  the mockup's design language — the export
  (`design/Ironclad_dc.html`, 607KB) turned out to be a COMPILED VUE
  BUNDLE, so the literal stylesheet is not liftable; the palette/layout
  tokens were extracted (dark chrome #101826 + light panels
  #eef1f5/#f6f8fb, hairlines #dbe2ec, red #c0392b, green #1f8a5b) with
  the accent fixed at the owner-directed #3F3D8A. **ROLLOUT STEP 3
  BUILT (2026-07-20): the three designed screens end-to-end.**
  `frontend/` (Vite+React; node v24; `npm run dev` proxies /api→:8000
  per W2; `frontend/README.md` has the two-terminal run):
  `src/format.js` = the Tier-1 display rules ported from ui/format.py
  (null→em-dash never 0; 6 node-test cases green incl. the Clorox
  literal "2,596,319"); `src/api.js` = structured-error fetch (ApiError
  carries summary/problems/reference; the App error banner renders them
  readably, never a dump); `App.jsx` = dark-chrome sidebar (Inputs/
  Outputs groups, the 7 unbuilt tabs disabled, Dashboard default-active),
  property picker + Calculate + the edited→invalidated stale marker;
  `Dashboard.jsx` = 6 KPI cards + hand-rolled SVG charts (NOI/CFBDS
  grouped bars, occupancy line, expirations by provenance) + top-tenants
  (client-side SORT only — presentation); `Reports.jsx` = picker from
  GET /api/reports + unit/period/scope toggles + the dense FrameTable
  (Cash Flow indented/bold via meta.extra.tree, NBSP indents, red-paren
  negatives) + benchmark banner + export buttons → /api/export/*;
  `Tenants.jsx` = the split pane — editable rent-roll grid (base-rent
  flatten, blank→null so the API's validators judge it) + lease detail
  (terms/steps/recoveries/notes) + Apply = PUT whole document → 422
  problems rendered per-field → success reloads + marks the run stale.
  **REAL-SERVER smoke green** (uvicorn on :8123): the full call flow with
  the exact literal 2596319.4000000004 over the wire, 37 tree rows,
  freeport GV −7,071.48. data/properties/ now stages freeport + its
  per-name benchmark CSV beside clorox. **TWO FLAGGED api/ DECISIONS
  (not built — the API is treated as fixed): (1) the Tenants
  rollover-generations panel needs a small additive endpoint exposing
  result.segments (the Freeport E surface — currently a flagged
  placeholder in the UI, not fabricated); (2) the W2 production
  StaticFiles mount (serve frontend/dist at /).** Suite: **755 passed +
  the same 4 by-design golden reds**; `git log 62617f1..HEAD -- engine/`
  EMPTY; ui/ + app.py untouched.
- **Next session's first prompt:** "The web-front-end rollout step 3 is
  BUILT (Dashboard/Reports/Tenants end-to-end vs the real API; React+
  Vite per W1; frontend/README.md has the run commands) and is AWAITING
  OWNER VISUAL REVIEW beside design/Ironclad_dc.html — do not build the
  other seven tabs until Topper reacts. TWO FLAGGED api/ decisions await
  the owner: (1) a small additive endpoint exposing result.segments for
  the Tenants rollover-generations panel (the Freeport E surface;
  currently an honest flagged placeholder); (2) the W2 production
  StaticFiles mount serving frontend/dist from uvicorn. If the owner
  approves either, implement additively with TestClient tests
  (endpoint==engine-data equality, the Freeport E literals lc 6.75/
  weight 0.75); api/ is otherwise treated as FIXED. Boundaries every
  session: engine/ FROZEN (`git log 62617f1..HEAD -- engine/` EMPTY);
  ui/ + app.py untouched (Streamlit = frozen fallback until the
  relocated Gate 5 passes); the four by-design golden reds stay red
  (137/47 Gate 2, 33/12 Gate 3 capital). The relocated Gate 5 (plan §5)
  = Clorox from-scratch through the NEW front-end (engine-to-engine
  identical) + the Freeport drive — owner-declared, after all ten
  screens exist. REMEMBER the standing gaps, all carried forward
  unchanged: percentage rent externally unvalidated pending golden #3;
  tenant misc items + purchase/deposits/debt/resale/valuation/
  sensitivity externally unvalidated; Freeport B / Cedar Alt B /
  Freeport E investigations post-Gate-5; Cedar Alt D closed as C's
  sibling; live price derivation permanently refusing (DEVIATIONS §20
  #6); the two named reconciler blind spots; the stale-message list
  (surfacing through API summaries verbatim) + the flagged engine
  candidates in NEXT_STEPS_TO_PHASE5.md. When a step lands: commit,
  push, update this prompt, STOP for owner + advisor review."
