# NEXT STEPS TO GATE 5 (Phase 5 — Streamlit UI)

**OWNER-REVIEWED AND APPROVED 2026-07-16 — Step 0 D1-D6 resolved as
recommended, including the D6 amendment (see Step 0). The Phase 5 build is
authorized per this plan; Iron Rule 1 governs it (the UI imports the
engine, never the reverse — zero changes under `engine/` during UI
development, git-log-checked from the baseline recorded in Step 1).**

The concrete path through Phase 5 — the Streamlit application per spec §6
— to Gate 5 (spec §10: "full property built from scratch through UI only,
calc, export"). Companion to the closed
[NEXT_STEPS_TO_GATE1.md](NEXT_STEPS_TO_GATE1.md),
[NEXT_STEPS_TO_GATE2.md](NEXT_STEPS_TO_GATE2.md),
[NEXT_STEPS_TO_GATE3.md](NEXT_STEPS_TO_GATE3.md), and
[NEXT_STEPS_TO_PHASE4.md](NEXT_STEPS_TO_PHASE4.md); same standing rules
(Iron Rules, owner-gated decisions, the DEVIATIONS §25 test-discipline
rules, no input tuning).

**Where we are (2026-07-16):** Gate 4 passed (owner declaration
2026-07-16). The engine (Phases 1-3) and the report/export/intake layer
(Phase 4) are complete: 18 of 24 report builders (the Step-0-deferred six
#10/#13/#14/#17/#19/#22 stay deferred), the values-only §8 Excel package,
and both intake surfaces (PropertyModel JSON; the §5.2 rent-roll template
round-trip with readable errors and Contractual/Speculative provenance).
Suite: 573 passed + the four by-design golden reds (137/47 Gate 2, 33/12
Gate 3 capital). Phase 5 adds a UI **client** over all of it — no new
calculation anywhere in this phase.

## The two Iron Rules that govern this phase (read first)

1. **Iron Rule 1 is the architecture.** The UI imports the engine; the
   engine never imports the UI. Everything the UI needs already exists as
   an engine API (inventory below). If a screen seems to need an engine
   change, STOP and flag it as an owner decision — do not "just add a
   field." Gate 5's checklist makes this auditable: **"No engine code was
   modified during UI development (git log proves it; if the UI forced
   engine changes, your API boundary leaked)"** (BUILD_SCHEDULE Gate 5).
   The Phase 5 baseline commit is recorded at Step 1 so the git-log check
   is mechanical.
2. **Iron Rule 2 already applied:** this plan precedes all code. Each step
   below lands only after the prior step's acceptance passes.

## The engine API the UI consumes (already built — the client contract)

| UI need | Engine surface |
|---|---|
| Open / save a property | `engine.models.io.load_property` / `save_property` (`.icprop.json`, spec §5.1); readable pydantic validation errors |
| Import a rent roll | `engine.intake.import_rent_roll` / `import_rent_roll_csv` → `ImportResult(leases, notes)` — Contractual rows only; Speculative rows reported in `notes`, never silently skipped |
| Calculate | `engine.calc.run.run_property(model)` → `RunResult` (ledger, areas/occupancy, segments, audits, loan schedules, resale, valuation, sensitivity) — §9.3 invariants assert on every run |
| Render reports | the 18 `engine.reports` builders, each returning `Report(frame, meta)`; unit toggle (Total $ / $ per SF / per-month / per-occupied-SF) + period (monthly/quarterly/annual/fiscal) via the Step-1 primitives; `meta.monetary=False` reports ignore the unit toggle |
| Provenance | #11/#12 default to the full view with a Contractual/Speculative `status` per row (`CONTRACTUAL_STATUSES` selectable); the rent-roll export carries the same labels |
| Audit drill-down | Lease Audit (#16), Recovery Audit (#18), Resale Audit (#21) + the per-tenant series retained on `RunResult` ("no silent numbers") |
| Export | `engine.export.build_package` (the §8 workbook), `export_report` (single view), `export_rent_roll` (takes the **RunResult**) |
| Refusals | the engine's loud `NotImplementedError`/`ValueError` messages (pct_of_value loans, derived price, TI/LC categories, `pct_of_account`) — the UI renders them as readable notices, never a traceback |

**A date-range selector (spec §6 tab 8) is a UI-side column slice of the
already-built report frame — presentation, not an engine change.** Same
for everything else on the Reports tab: the builders are done.

## Screen / flow inventory (spec §6, [AE pp. 48-58])

**Sidebar:** property selector (from `data/properties/*.icprop.json`),
scenario selector (Step 0 decision D4), **Calculate** button (explicit —
never recalc-on-every-keystroke; the Phase 6 perf target doesn't exist
yet), Save / Load, Export Package.

**Tabs** (each maps to its §3 model slice; grids are editable with
add/delete/duplicate row and per-cell readable validation errors):

| # | Tab | §3 slice / engine surface |
|---|---|---|
| 1 | Property | `PropertyInfo`, `AreaMeasures` (§3.1-3.2) |
| 2 | Market | `Inflation` + custom indices, `GeneralVacancy`, `CreditLoss`, MLP grid + detail editor, `CPISpec` profiles, `FreeRentProfile`s (§3.4-3.8); TI/LC categories are schema-present but engine-refused — read-only with the refusal note |
| 3 | Revenues | misc / parking / storage `PropertyRevenue` grids (§3.10) |
| 4 | Expenses | opex/capex/non-op `ExpenseItem` grids + `ExpenseGroup`s (§3.11) |
| 5 | Tenants | rent roll grid (`st.data_editor`), lease detail as a **persistent split pane** (mockup decision, Step 0 D5), rent steps / CPI / free rent / misc items / security deposit / % rent / recovery assignment per lease, `AbsorptionSpec`s, recovery structure builder (§3.12-3.15, §3.7); **rent-roll template import lives here** with `ImportResult.notes` shown as an info banner |
| 6 | Investment | `Purchase` + closing costs, `Loan` grid + detail (§3.16-3.17); pct_of_value / derived price surfaced as the engine's permanent-refusal notices |
| 7 | Valuation | `ValuationInputs`: DCF, direct cap, `Resale`, `SensitivityIntervals` (§3.18) |
| 8 | Reports | picker over the 18 built reports; unit + period toggles (global); date-range slice; provenance labels on #11/#12; export-this-view; Benchmark Comparison (#24) renders only when an expected CSV exists |
| 9 | Dashboard | KPI cards (value, IRR unlev/lev, equity multiple, year-1 NOI, cap rate on cost, occupancy), NOI/CF chart, occupancy line, lease-expiration bar, top-tenants table [AE pp. 532-534] — every number read off `RunResult`/reports, never recomputed; **default-active tab on load** (mockup decision, Step 0 D5) |
| 10 | Audit | pick any account + month → per-tenant / per-item composition from the audit reports + RunResult detail (spec §2.3 principle 3) |

**Not in any tab, ever:** in-app OM/document ingestion ("Phase 7") is
cancelled permanently (spec §1.2/§5.4). The two intake surfaces above are
the only ones. Also not in Phase 5: the deferred six reports, scenario
COMPARE (Phase 6), performance work (Phase 6), multi-user/auth (never).

**The Claude Design mockup is reference input, not a spec.** It is an
exploratory prototype (separate repo, no code imported from it). Two
layout choices made during that exploration are adopted into this plan
pending Step 0 confirmation (D5): Dashboard as the default-active tab, and
the Tenants split-pane lease detail (chosen deliberately because it is
buildable natively in Streamlit — `st.columns` + `session_state` — with
full editability, unlike a drawer overlay).

## Phase 5 validation reality (read before the criteria)

The UI has no golden and computes nothing, so its acceptance is fidelity,
not tolerance:

1. **Round-trip fidelity:** UI edits → `PropertyModel` → saved JSON →
   reload → identical UI state and identical model (`model_dump()`
   equality). Per DEVIATIONS §25 these tests must discriminate — a
   deliberately altered field must fail them.
2. **Engine-output identity:** a property rebuilt from scratch through the
   UI produces the same ledger as its known-good fixture (engine-to-engine
   comparison, exact — not the $500 OM tolerance, which already passed at
   its gate).
3. **The owner behavioral test** (BUILD_SCHEDULE Gate 5, only Topper can
   run it): build a complete property from scratch through the UI alone —
   no JSON editing — calculate, review the dashboard, drill one recovery
   number to tenant level, export the package. Time it; if a 15-tenant
   deal takes over an hour, the friction points are filed as Phase 6
   fixes.
4. **The git-log boundary check:** zero commits touching `engine/` between
   the Phase 5 baseline commit and Gate 5 (report/export/intake fixes, if
   any are needed, are owner-flagged exceptions recorded in DEVIATIONS —
   never silent).

**Gate 5 criteria (checklist; spec §10 + BUILD_SCHEDULE):**

1. Full property built via UI only, calculated, exported (the Step 0 D3
   property).
2. Audit drill-down reaches per-tenant, per-month composition for any
   account.
3. No engine code modified during UI development (git log from the Step 1
   baseline proves it).
4. Both intake surfaces work from the UI with readable errors (load
   PropertyModel JSON; import the rent-roll template, Speculative rows
   reported not silently skipped).
5. Every rendered monetary report honors the unit/period toggles; #11/#12
   show the Contractual/Speculative provenance.
6. **The three D6-amendment inspection surfaces exist and render on the
   goldens** (GV basis decomposition; per-lease rollover recovery timing;
   per-generation rollover economics incl. renewal LC rates). The
   investigation itself stays post-Gate-5 (Step 0 D6).

---

## Step 0 — Owner-gated decisions — **RESOLVED 2026-07-16 (owner approval, D1-D6 as recommended + the D6 amendment)**

- **D1 — RESOLVED 2026-07-16: in-process engine import for v1.** Streamlit
  imports the engine directly; the FastAPI layer is **deferred, not
  cancelled** — recorded in DEVIATIONS §26 as a conscious sequencing
  choice. Iron Rule 1 fully preserved: the UI is still a pure client.
- **D2 — RESOLVED 2026-07-16: full editors for the §3 surface the goldens
  + demo properties exercise** (rent roll incl. steps/CPI/free rent/misc/
  deposits/% rent/recovery assignments, MLPs, absorption, recovery
  structures, vacancy/credit loss, revenues, expenses+groups, purchase,
  loans, valuation); engine-refused schema fields (TI/LC categories,
  pct_of_value, derived price, pct_of_account) shown **read-only with
  their refusal messages**; a **raw-JSON view (read-only + reload-from-
  disk)** as the escape hatch for anything exotic.
- **D3 — RESOLVED 2026-07-16: Gate 5 from-scratch property = Clorox
  Northlake rebuilt through the UI**, acceptance = the UI-built model's
  fiscal cash flow is engine-to-engine **IDENTICAL** to the committed
  fixture output (§25-discriminating: any mis-entered field fails it);
  plus the **Freeport load-and-drive timing exercise** (open the 29-lease
  golden, calculate, drill, export — the friction test).
- **D4 — RESOLVED 2026-07-16: v1 scenario = duplicate property JSON under
  a new name**, edited independently; scenario COMPARE deferred to
  Phase 6.
- **D5 — RESOLVED 2026-07-16: both mockup layout choices adopted** —
  Dashboard as the default-active tab; Tenants lease detail as a
  persistent split pane (not a drawer).
- **D6 — RESOLVED 2026-07-16 with an owner-approved AMENDMENT.** The
  Freeport B / Cedar Alt B / Freeport E **investigation** is a
  post-Gate-5 / Phase 6 activity, NOT a Gate 5 criterion (the three
  assertions stay red by design meanwhile). **AMENDMENT — Phase 5 must
  still BUILD the inspection surfaces that investigation requires** (see
  "Phase 5 UI requirement (D6 amendment)" below, wired into Steps 4/6 and
  Gate 5 criterion 6).
- **(Deferred-index note, no decision needed):** spec §2 also lists a
  SQLite property index (sqlmodel). v1's property selector scans
  `data/properties/` directly; the index joins when the property count
  makes scanning slow — sequencing, not scope change.

### Phase 5 UI requirement (D6 amendment, owner-approved 2026-07-16)

The UI must surface, to lease/generation level, the three parked
inspection targets — **all from data the RunResult already retains; no
engine change is needed for any of them:**

1. **Freeport B — general-vacancy basis:** an Audit-tab General Vacancy
   panel decomposing the month's GV against its revenue basis, composed
   from the per-tenant series `RunResult` retains (lease_rents,
   recoveries, percentage_rent, misc, absorption_vacancy) plus the model's
   `GeneralVacancy` method — presentation over existing detail. (Step 6.)
2. **Cedar Alt B — per-lease rollover recovery timing:** the Recovery
   Audit drill-down already carries one row per (tenant, **segment_start**,
   pool, month) — the Audit tab renders it filterable by tenant and
   segment so downtime/rollover months are inspectable per lease. (Step 6.)
3. **Freeport E — renewal LC rates per rollover generation:** **CONFIRMED
   GAP in the original tab inventory — no tab showed it.** The data exists
   per generation on `result.segments` (each speculative `LeaseSegment`
   carries `lc_pct` / `lc_pct_years` / `lc_rate`, `ti`, and
   `renewal_weight` — verified on Freeport: e.g. lc_pct 6.75, renewal
   weight 0.75). **Closure: a read-only "Rollover generations
   (engine-projected)" section in the Tenants tab's split-pane lease
   detail**, listing every resolved segment of the selected chain —
   start/end, provenance, renewal weight, blended initial rent, downtime,
   weighted free months, TI, and the **LC pct/rate** — sourced from
   `result.segments`. (Step 4; also reachable from the Audit tab's
   Leasing Commissions drill.)

Gate 5 criterion 6 (added below): these three surfaces exist and render
on the goldens. The **investigation** using them stays post-Gate-5 (D6).

## Stale engine messages — running list for the post-Gate-5 wording pass

The engine is FROZEN during Phase 5 (Iron Rule 1), so user-surfacing
engine messages with stale wording are LISTED here, not fixed. The UI
shows them verbatim. One batched, owner-approved wording pass happens
after Gate 5:

1. **`engine/calc/run.py` `_phase_guards`** — the `pct_of_account` expense
   refusal says *"not implemented until Phase 2"*; Phase 2 is long done
   (the deferral is real, the label is stale). Surfaced by the Calculate
   error panel and the Expenses tab's read-only refused-row display.
   (Flagged Step 1; carried Step 3.)
2. **`engine/calc/debt.py` `_principal0`** — the `pct_of_value` loan-sizing
   refusal says *"an OPEN OWNER SCOPE DECISION (DEVIATIONS.md §20)"*; that
   decision CLOSED 2026-07-12 as a **permanent** refusal (DEVIATIONS §20
   #6). The refusal itself is correct; the "open" label is stale. Surfaced
   by the Investment tab's read-only refused-loan display. (Flagged
   Step 5.)
3. **`engine/calc/investment.py`** (derived-price guard) — the
   `Purchase.derivation != fixed` refusal has the same stale *"OPEN OWNER
   SCOPE DECISION"* label; same closed decision, same fix. Surfaced by the
   Investment tab's read-only purchase display. (Flagged Step 5.)

*(Append here as found; do not fix in-phase.)*

## Step 1 — App shell, persistence, Calculate pipe (session 1)

`ui/` package + `app.py` entry point (`streamlit run app.py`); add
`streamlit` + `plotly` to the environment (already in the spec §2 stack).
- Sidebar: property selector over `data/properties/`, open/save via
  `load_property`/`save_property`, New Property (minimal valid model),
  **Calculate** button → `run_property` with the RunResult cached in
  `st.session_state` and invalidated on any model edit.
- Load-JSON intake surface with pydantic errors rendered readably (§5.4
  standard — field path, offending value, what a valid value looks like).
- Engine exceptions (refusals, invariant failures) rendered as readable
  error panels, never tracebacks.
- Minimal Dashboard (year-1 NOI, occupancy) to prove the pipe end-to-end;
  Dashboard default-active per D5.
- **Phase 5 baseline commit for the Gate 5 git-log boundary check:
  `62617f1`** (the Step 0 resolution commit — the last commit before any
  UI code). Gate 5 verifies `git log 62617f1..HEAD -- engine/` is empty.
- UI state helpers live in pure functions (`ui/state.py` etc.) so they are
  unit-testable without a browser; flow smoke tests via Streamlit's
  `AppTest` (`streamlit.testing.v1`). All §25 rules apply to every test.
- **Acceptance:** open → edit nothing → calculate → dashboard shows the
  fixture's known numbers; save → reload → identical model; a corrupted
  JSON yields the readable error, not a stack trace.

## Step 2 — Property + Market tabs (session 2)

`PropertyInfo`/`AreaMeasures`; inflation + custom indices; general
vacancy; credit loss; MLP grid + detail editor; CPI profiles; free-rent
profiles. Engine-refused fields per D2.
- **Acceptance:** every field round-trips (edit → save → reload →
  identical); per-cell validation errors are inline and readable; a §25
  discrimination test alters one field and the round-trip test fails.

## Step 3 — Revenues + Expenses tabs (session 3)

Misc/parking/storage revenue grids; opex/capex/non-op expense grids with
annual overrides, limits, units; expense groups.
- **Acceptance:** round-trip + discrimination as Step 2; a %-of-EGR fee
  edited in the UI recalculates through the fixed point (Calculate) to the
  known fixture value.

## Step 4 — Tenants tab (session 4; the big one)

Rent roll grid + split-pane lease detail (D5): term, base rent, steps,
CPI, free rent, misc items, security deposit, % rent, recovery
assignment, upon-expiration + MLP link; absorption specs; the recovery
structure builder (pools/gross-up/caps/fees — the owner's home turf);
**the rent-roll template import surface** (`ImportResult.notes` as an
info banner listing ignored Speculative rows; row-level errors rendered
as returned); **the D6-amendment "Rollover generations (engine-projected)"
read-only section in the split pane** — every resolved segment of the
selected chain from `result.segments` with start/end, provenance, renewal
weight, blended initial rent, downtime, weighted free months, TI, and
**LC pct/rate per generation** (the Freeport E surface).
- **Acceptance:** round-trip + discrimination; import the Phase 4 template
  export of a golden and confirm the Contractual subset lands identically;
  the Speculative-rows note displays; a malformed row shows the readable
  error text verbatim; **the rollover-generations panel shows Freeport's
  known per-generation LC pct (6.75) and renewal weight (0.75)** —
  §25-discriminating against a wrong-field read.

## Step 5 — Investment + Valuation tabs (session 5)

Purchase + closing costs; loan grid + detail (fixed/floating, IO,
balloon, additional principal, loan costs); DCF assumptions, direct cap,
resale (all five methods with method-appropriate field visibility),
sensitivity intervals. Permanent refusals (pct_of_value, derived price)
shown as the engine's own messages.
- **Acceptance:** round-trip + discrimination; the valuation demo property
  entered through these tabs reproduces the known hand-check numbers
  (amort payment 5,995.51; resale 1,212,500; PV/IRR self-consistency).

## Step 6 — Reports, Dashboard, Audit tabs (session 6)

Report picker over the 18 builders; global unit/period toggles; date-range
slice; provenance labels; export-this-view (`export_report`) and the
sidebar package export (`build_package`); full Dashboard (KPI cards +
Plotly charts off RunResult/reports); Audit tab drill-down (account +
month → composition via the audit reports and RunResult per-tenant
series), **including the two remaining D6-amendment surfaces: the General
Vacancy basis-decomposition panel (Freeport B) and the Recovery Audit
drill filterable by tenant + segment_start (Cedar Alt B).**
- **Acceptance:** every rendered report's frame equals the builder's
  output for the same toggles (no UI-side math); the drill-down reproduces
  a Recovery Audit row for a golden tenant-month; exports open and match
  (the Phase 4 cell-by-cell machinery is reused, not rewritten); **the GV
  panel's basis ties to the RunResult per-tenant series and the recovery
  drill isolates a Cedar Alt rollover month per lease** (Gate 5
  criterion 6).

## Step 7 — Gate 5 acceptance run (owner, session 7)

The D3 from-scratch build + the behavioral test, timed; the git-log
boundary check from the Step 1 baseline; friction list filed for Phase 6.
Then — and only then — Phase 6 (hardening), Iron Rule 2 again.

---

**Standing gaps carried into Phase 5 (unchanged; none a Phase 5
blocker):** percentage rent externally unvalidated pending golden #3
(standing opportunistic intake); tenant misc items + purchase/deposits/
debt/resale/valuation/sensitivity externally unvalidated (no golden
exercises them — manual/engineered tests + owner hand-checks only);
Freeport B, Cedar Alt B, and Freeport E parked for beta-stage GUI testing
(their Gate 2/3 assertions stay red by design — 137/47 Gate 2, 33/12 Gate
3 capital; scheduling is Step 0 D6); Cedar Alt D closed as C's sibling
(not open); live price derivation permanently refusing (DEVIATIONS §20
#6); the two named reconciler blind spots (`_SU_LEDGER_ROWS` shared
mapping; resale-matrix monotonicity-preserving non-anchor corruption);
the DEVIATIONS §25 standing rules (a regression test must run on a
fixture where the wrong answer differs from the right; a test-file
rewrite must list every test removed). The Step-0-deferred six reports
(#10/#13/#14/#17/#19/#22) stay deferred. In-app OM ingestion ("Phase 7")
is cancelled permanently and must not be scaffolded in any tab.

**Status:** drafted 2026-07-16 on the Gate 4 pass; **Step 0 resolved and
the plan APPROVED by the owner 2026-07-16** (D1-D6 as recommended + the D6
amendment). The Phase 5 build proceeds step by step per this plan; each
step stops for owner + advisor review before the next.
