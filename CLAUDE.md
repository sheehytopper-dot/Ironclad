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

1. **Five OM-based goldens spanning complexity** — each an Offering Memorandum with a
   published Argus-based cash flow, each validated **annually at fiscal-year level, within
   $500 per line**:
   - **#1** single-tenant NNN — `tests/golden/clorox_northlake/` (CBRE OM; owner-verified)
   - **#2** multi-tenant with base-year or expense-stop recoveries
   - **#3** retail with percentage rent — **standing opportunistic intake** (owner decision
     2026-07-05; no deadline — see Known validation gaps below)
   - **#4, #5** chosen from deal triage for coverage of gross-ups, caps, or absorption
2. **Owner per-cell adjudication (standing):** when the engine and a golden's published
   figures disagree beyond tolerance, or a month-level timing question arises that annual
   data cannot discriminate, the owner recomputes the specific disputed cells in Excel
   from the source documents alone, **WITHOUT reading the engine's output or code first**.
   The owner's independently computed cells are the reference. Claude never produces
   these reference cells.
3. **The manual's worked examples as unit-level goldens** (Iron Rule 3): base rent examples
   [AE pp. 391-394], repeating payments [AE pp. 361-362], recovery gross-up [AE p. 407],
   resale methods [AE pp. 464-471], with page cites in test docstrings.

**Fixture-lock rule (standing policy): transcribed inputs are human-verified against the
source pages and committed before any engine comparison runs.** Every future deal validates
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
#2/#4/#5 fixture transcription there (Step 0) is owner-gated and gates the phase's
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
| 2 — Market machinery | MLPs, rollover blending, absorption, general vacancy/credit loss offsets, full recovery structures, % rent | **Goldens #2, #4, #5** (Freeport, Cedar Alt, Inland) cash flows match the OM within tolerance; Lease Audit + Recovery Audit reports built, reconciling exactly to the ledger, and owner-reviewed; % rent module built with manual worked-example tests (Iron Rule 3) but **externally unvalidated pending golden #3** |
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
- Run tests: `.venv\Scripts\python -m pytest` (Windows). Current status: **GATE 1 PASSED
  (owner declaration 2026-07-05); Phase 2 begins.** Phase 1 shipped 2026-07-05:
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
  full-occupancy revenue in downtime and occupied months alike. Suite 180 green
  (golden #1 regression intact; its General Vacancy = 0 transcribed).
- **Next session's first prompt:** "Continue Phase 2 (NEXT_STEPS_TO_GATE2.md Step 5,
  session 1 of 2): full recovery structures — system methods. Read [AE pp. 404-413]
  (recoveries; p. 407 gross-up; pp. 409-410 stops/denominators) and [AE pp. 517-520]
  (admin fees) first. Extend engine/calc/recoveries.py: system methods base_stop
  (stop_amount_per_area × tenant share denominator, recover the excess over the stop),
  base_year / base_year_plus_1 (stop = actual recoverable expenses of the base
  calendar year — frozen once computed, lease-start-relative per [AE pp. 405-406,
  240]; leases starting pre-analysis use analysis year 1), and fixed ($ or $/SF,
  inflatable on fixed_inflation). Honor RecoveryAssignment's base_year_gross_up_pct
  only if trivially separable — otherwise defer gross-up wholesale to session 2's
  user structures (it is a user-structure feature per [AE p. 406]; keep the guard
  loud). Recoveries floor at 0 (never pay the landlord's stop). Wire dispatch through
  project_segment_recoveries so contract and speculative segments both resolve; keep
  the %-of-EGR fixed point converging (stops make recoveries nonlinear — verify the
  loop still terminates and document why). Unit tests with page cites (Iron Rule 3),
  including a Clorox-shaped base-stop case computable by hand. Full suite green
  (golden #1 uses net — regression check). Commit, push, update the progress note and
  this prompt."
