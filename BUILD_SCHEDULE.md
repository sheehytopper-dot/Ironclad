# BUILD SCHEDULE: Week-by-Week Plan with Hard Gates

Companion to ARGUS_REBUILD_SPEC.md. This schedule assumes 10 hours per week: three weeknight sessions of 1.5 to 2 hours plus one 4-hour weekend block. If your real capacity is 6 hours, multiply every duration by 1.6 and stop pretending otherwise. The schedule is gated, not dated: you advance when the gate passes, not when the week ends.

> **Current status (2026-07-05): GATE 1 PASSED — owner declaration 2026-07-05** after review of the Gate 1 evidence (`tests/golden/clorox_northlake/DISCREPANCY_LOG.md`, 126-test green suite, independent verification). Phase 1 complete: leases, expenses, net recoveries, ledger, run.py (spec §4.1 passes 1-6 incl. the %-of-EGR fixed point, DEVIATIONS.md §6); Clorox FY2027-FY2028 every line within $1 of the OM (tolerance $500/line). **Phase 2 begins** — session sequence in [NEXT_STEPS_TO_GATE2.md](NEXT_STEPS_TO_GATE2.md); goldens #2/#4 fixture transcription (Freeport, Cedar Alt) is owner-gated staging work that gates the phase's completion, not its start. **Scope reduction (owner decision 2026-07-09): golden #5 (Inland Logistics) is permanently disqualified — no ARGUS attribution anywhere in its OM — and no replacement is being pursued; Gate 2 requires two goldens (#2, #4), not three (DEVIATIONS.md §14).**
>
> **Current status (2026-07-10): GATE 2 PASSED — owner declaration 2026-07-10** after review of the Gate 2 evidence: goldens #2 (Freeport) and #4 (Cedar Alt) with all root causes adjudicated closed except Freeport B (general-vacancy basis) and Cedar Alt B (rollover recovery timing), both explicitly deferred to beta-stage GUI testing (owner decision 2026-07-10); golden #1's FY2029-FY2031 revenue/vacancy scope green; Lease Audit and Recovery Audit reports built, reconciling, and owner-reviewed; turnover/general-vacancy double-count verified; full suite 275 passed / 2 failed (the two golden gate assertions, red by design on the deferred items). **Phase 3 begins** (spec §10, capital and valuation).
>
> **Post-original sourcing note (2026-07-03, revised 2026-07-04):** the plan below predates the loss of ARGUS access. Wherever it says to export goldens from ARGUS or to reconcile against "the ARGUS export" (Week 1 jobs, Gates 0-3), read the **Golden-File Strategy in [CLAUDE.md](CLAUDE.md)** instead: **five OM-based goldens** spanning complexity, each validated annually at fiscal-year level within $500/line; **dispute-triggered owner per-cell adjudication** (the owner recomputes the specific disputed cells in Excel from the source documents alone, without reading the engine's output or code first); and the manual's worked examples. Everything else — week structure, job splits, gates as checklists, protocols — is authoritative as written. (This file was merged 2026-07-03 from BUILD_SCHEDULE_ORIGINAL.md.)

## Operating rules (read before every phase)

1. A gate is a pass/fail test result, never a feeling of doneness. If you cannot show the passing test output, the gate has not passed.
2. If a gate slips one week, fine. If it slips two, stop building and run the Stall Protocol (bottom of this doc).
3. Each week below lists YOUR jobs and CLAUDE CODE's jobs separately. If you find yourself doing Claude Code's jobs, stop. If Claude Code is doing your jobs (deciding what is acceptable), stop faster.
4. Sessions always end with: tests green, git commit, CLAUDE.md progress note updated, next session's first prompt written down. A session that ends mid-broken-state costs you the first 30 minutes of the next one.

---

## WEEK 1: Setup + Golden Files (Phase 0)

The most important week. Not because of the code, because of the golden files. Everything downstream is only as trustworthy as what you produce here.

**Your jobs:**
- Install VS Code, Python, Git, Node, Claude Code. Create private GitHub repo. (Session 1)
- Select three reference deals and export from ARGUS to Excel: Annual + Monthly Cash Flow, Lease Audit, Recovery Audit, Present Value, Resale/IRR summary for each. (Session 2, and this is on you alone; Claude Code cannot do it)
  - Golden 1: single-tenant NNN, no rollover inside the term. Dumbest deal you have.
  - Golden 2: multi-tenant office/industrial, base-year or stop recoveries, at least two lease expirations inside the term with market rollover assumptions.
  - Golden 3: retail with percentage rent and at least one custom recovery pool.
- Write a one-page README in tests/golden/ describing each deal's key assumptions in plain English (term, discount rate, exit cap, renewal probabilities). Claude Code will build the input JSONs from this plus the exports.

**Claude Code's jobs:**
- Phase 0 prompt from GETTING_STARTED: repo scaffold, pydantic models for all of spec section 3, JSON round-trip tests, timeline and inflation modules with unit tests.

**GATE 0 (end of week 1):**
- [ ] All three golden export sets sit in tests/golden/
- [ ] pydantic models serialize/deserialize a hand-built toy property
- [ ] Timeline and inflation unit tests pass, including a mid-year analysis start case
- [ ] Repo pushed to GitHub

If you skip the golden exports because setup ate the week, do not start Week 2. Week 2 without goldens is building a scale with no reference weights.

---

## WEEKS 2-3: Core Ledger (Phase 1)

**Scope:** Base rent all unit types, fixed steps, percent of market, CPI, free rent, operating/non-op/capital expenses with occupancy scaling, simple net recoveries, occupancy series, NOI assembly. No MLP rollover yet: Golden 1 is chosen precisely so leases run past the analysis end or terminate with vacate.

**Your jobs:**
- Direct one module per session in spec order (4.1 steps 1-6 simplified).
- Verify the manual worked-example tests exist and pass: every case on manual pages 391-394 and 361-362. Ask to see the test file; read the docstrings; confirm page citations.
- Week 3 weekend block: Golden 1 reconciliation. Have Claude Code export our cash flow beside the ARGUS export with a delta column. You review every non-zero delta in Excel yourself.

**Claude Code's jobs:** implement, test, produce the comparison workbook, trace any divergent cell on demand.

**GATE 1 (end of week 3): PASSED — owner declaration 2026-07-05.**
- [x] Golden 1 annual fiscal-year cash flow matches the OM transcription within $500/line for FY2027-FY2028 (criterion revised 2026-07-03 with the no-ARGUS-access golden strategy, spec §9.1/§10 — this line previously read "monthly within $1/month vs the ARGUS export", which is impossible without ARGUS exports; achieved 2026-07-05 at within $1/line)
- [x] All manual worked-example unit tests pass with page cites (2026-07-05)
- [x] Invariants from spec 9.3 asserted and passing (pre-valuation subset, on every run; 2026-07-05)
- Common slip cause: unit-type conversion and inflation timing (anniversary vs calendar). Budget the weekend block for exactly this.

---

## WEEKS 4-6: Market Machinery (Phase 2)

This is the hard phase and the reason the estimate says 6-12 and not 6. Rollover blending, general vacancy offset logic, and recovery structures are where every Argus clone attempt dies. Three weeks allocated; treat week 6 as expected, not as buffer.

**Week 4 scope:** Market leasing profiles, rollover blending algorithm (spec 4.2), lease chaining, absorption. 
**Week 5 scope:** Full recovery structures: pools, gross-up, base year/stop, caps, admin fees, denominators. Recovery Audit report built early because you need it to debug.
**Week 6 scope:** General vacancy with absorption/turnover offset, credit loss, tenant overrides, percentage rent with layered breakpoints. Goldens 2 and 4 reconciliation (golden 5 disqualified 2026-07-09, DEVIATIONS.md §14).

**Your jobs:**
- Week 4: sanity-check blended rollover economics by hand on one lease (you can do this math on a napkin: weighted rent, weighted downtime, weighted TI/LC). If the napkin disagrees with the engine, the engine is wrong until proven otherwise.
- Week 5: this is your home turf. Review the Recovery Audit output against the ARGUS Recovery Audit for Golden 2 tenant by tenant. You will find the discrepancies faster than any test will.
- Week 6: full Golden 2 and Golden 3 diffs, cell-level review.

**GATE 2 (end of week 6):**
- [x] Goldens #2, #4 cash flows match the OM within tolerance (scope reduced from three goldens 2026-07-09 — #5 Inland disqualified, DEVIATIONS.md §14) — satisfied 2026-07-10 with two explicit deferrals: all root causes adjudicated closed except Freeport B (general-vacancy basis) and Cedar Alt B (rollover recovery timing), both deferred to beta-stage GUI testing (owner decision 2026-07-10; DISCREPANCY_LOG Status sections). Fresh comparison counts: Freeport 137/242 line-years beyond $500, Cedar Alt 47/165 — the tests stay red on the deferred items by design
- [x] Lease Audit and Recovery Audit reports built, reconciling exactly to the ledger, and owner-reviewed (satisfied 2026-07-09 — reviewed via freeport.audits.xlsx, NEXT_STEPS_TO_GATE2.md criterion 3)
- [x] Percentage-rent module built with the manual's worked-example unit tests (Iron Rule 3) (2026-07-06); **externally unvalidated pending golden #3** (standing opportunistic intake — CLAUDE.md, Known validation gaps)
- [x] Turnover vacancy does not double-count against general vacancy (verify total vacancy % equals stated rate in a test) (verified passing — tests/unit/test_vacancy.py::TestGate2Criterion5, 2026-07-09)
- Slip risk is highest here. One week of slip is normal. Two triggers the Stall Protocol.

---

## WEEK 7: Capital and Valuation (Phase 3)

**Scope:** TIs/LCs posting on rollover, purchase and closing costs, debt engine (fixed, floating, IO, amortizing, additional principal, loan costs), resale methods, PV with all discounting conventions, unleveraged and leveraged IRR, sensitivity matrices.

**Your jobs:**
- Verify the self-consistency test: set price equal to computed PV, confirm IRR equals discount rate to within 1bp.
- Check one loan amortization schedule against any bank amort calculator.
- Reconcile Golden 1-3 valuation outputs: PV within $100, IRR within 1bp, resale exact.

**GATE 3 (end of week 7):**
- [ ] PV, IRR (both), resale match all three goldens
- [ ] IRR Matrix and Value Matrix reproduce ARGUS matrices for Golden 2
- [ ] Loan payoff at exit equals outstanding balance
- This phase is genuinely easier than Phase 2. It is standard finance math you already know cold. If it slips, the problem is upstream in the ledger, not in the valuation code.

---

## WEEKS 8-9: Reports and Excel Package (Phase 4)

**Scope:** The full report catalog (spec section 7), PSF/unit toggles, period toggles, the formatted Excel result package (spec section 8), rent roll import template round-trip.

**Your jobs:**
- Print or open the corresponding ARGUS report next to each of ours and mark layout and line-order differences. Match ARGUS conventions unless you consciously prefer otherwise, and write down each deliberate deviation in a DEVIATIONS.md.
- Test the PSF toggle on the Cash Flow and Executive Summary: totals divided by the right denominator (rentable vs occupied where specified).
- Import a real rent roll through the Excel template and confirm round-trip.

**GATE 4 (end of week 9):**
- [ ] All 23 reports render and export
- [ ] Result package workbook opens clean, formatted, correct units in headers
- [ ] Rent roll template imports with row-level validation errors on bad data

---

## WEEKS 10-11: UI (Phase 5)

**Scope:** Streamlit app per spec section 6: property editor tabs, editable grids, dashboard, report viewers with toggles, audit drill-down, export buttons.

**Your jobs:**
- The acceptance test is behavioral and only you can run it: build a complete property from scratch through the UI alone, no JSON editing, calculate, review dashboard, drill one recovery number to tenant level, export the package. Time yourself. If it takes over an hour for a 15-tenant deal, file the friction points as fixes for week 12.

**GATE 5 (end of week 11):**
- [ ] Full property built via UI only, calculated, exported
- [ ] Audit drill-down reaches per-tenant, per-month composition for any account
- [ ] No engine code was modified during UI development (git log proves it; if the UI forced engine changes, your API boundary leaked)

---

## WEEK 12: Hardening (Phase 6) + Buffer

Scenario duplicate/compare, performance pass (100-tenant, 10-year property calcs in under 5 seconds), input validation messages a normal human can read, and whatever slipped. If nothing slipped, spend the week stress-testing with your ugliest real deal, the one with the weird recovery language. That deal is the real final exam.

**SHIP CRITERIA (the definition of done from GETTING_STARTED, verbatim):** import a rent roll, set assumptions, calculate, dashboard, flip PSF toggles, drill an audit trail, export a formatted package, numbers match ARGUS within rounding.

---

## Stall Protocol

Trigger: any gate two weeks late, or the same test failing across three sessions.

1. Stop adding code. Freeze the branch.
2. Reduce to the smallest failing case: one tenant, one month, one account. Have Claude Code produce the full calculation trace for that cell with manual page citations at each step.
3. Recompute that cell yourself in Excel from the inputs. Yours is the reference, not the engine's.
4. If two focused sessions on the minimal case do not resolve it, hire a contract Python developer for exactly this: hand them the repo, the spec, the failing test, and the trace. Budget 10 to 20 hours of their time. This is a scoped surgical engagement, not a hand-off of the project.
5. Do not route around the failure by relaxing the test tolerance. A tolerance you widen to pass a gate is a lie you tell yourself with extra steps.

## Calendar honesty check

Before you commit to Week 1, look at the next 90 days: Archway transition mechanics, Bonnie View iterations, broker license work, family. If you cannot protect 10 hours weekly through at least Gate 2, start anyway but move the weekend block to the only slot you truly control and accept a 16-week runway. A slower schedule you keep beats a fast one you abandon in week 4, which is how every side-build like this actually dies: not from difficulty, from cadence collapse during a busy fortnight.

## Cancelled work — do not reintroduce

- **Phase 7 — in-app OM ingestion: cancelled entirely (2026-07-03).** Not deferred,
  not v2 — cancelled. Do not scaffold it, reference it as future work, or add it back
  to this schedule or any planning document. The application has exactly two intake
  surfaces (spec §5.4): loading a PropertyModel JSON file and importing the rent roll
  Excel template, both fully pydantic-validated with error messages readable by a
  non-programmer. How a PropertyModel JSON gets created is permanently outside the
  application's scope; extraction from OMs or other documents happens in external
  workflows the app knows nothing about, supported only by
  [docs/SCHEMA_GUIDE.md](docs/SCHEMA_GUIDE.md) and `docs/property_model.schema.json`.
  Any JSON produced by an external extraction workflow is reviewed by a human against
  the source document before it is used for calculation (CLAUDE.md, Intake Surfaces).
