# NEXT STEPS TO GATE 5 (Phase 5 — Streamlit UI)

**DRAFT — awaiting owner review. No UI code, no Streamlit scaffolding, and
no engine changes until Topper has seen this plan and resolved Step 0's
decisions (Iron Rule 2 applies to planning — same as every prior
NEXT_STEPS doc).**

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

---

## Step 0 — Owner-gated decisions (D1-D2 gate the build's start; D3-D6 gate completion)

**Owner: Topper (human). Future sessions must not act on these without his
sign-off.**

- **D1 — Client architecture: in-process engine import vs FastAPI.** Spec
  §2 lists a FastAPI layer in the stack, but the Phase 5 gate needs none
  of it. **Recommendation:** Streamlit imports the engine in-process for
  v1 (simpler, faster to Gate 5, Iron Rule 1 fully preserved — the UI is
  still a pure client); the FastAPI layer is deferred until something
  real needs it (a second client), recorded in DEVIATIONS as a conscious
  sequencing choice, not a cancellation.
- **D2 — v1 editable-input scope.** The §3 schema is large. Options:
  (a) full editors for every §3 field; (b) **recommended:** full editors
  for the §3 surface the goldens + demo properties actually exercise
  (which is nearly everything: rent roll incl. steps/CPI/free rent/misc/
  deposits/% rent/recovery assignments, MLPs, absorption, recovery
  structures, vacancy/credit loss, revenues, expenses+groups, purchase,
  loans, valuation), with the engine-refused schema fields (TI/LC
  categories, pct_of_value, derived price, pct_of_account) shown
  read-only with their refusal messages, and a raw-JSON view (read-only +
  "reload from disk") as the escape hatch for anything exotic. The Gate 5
  from-scratch build defines the floor either way.
- **D3 — the Gate 5 from-scratch property.** **Recommendation:** rebuild
  **Clorox Northlake** from scratch through the UI (real OM deal;
  known-good fixture) with acceptance = the UI-built model's fiscal cash
  flow is **identical** to the fixture's engine output (engine-to-engine,
  ~$0 — a §25-discriminating check: any mis-entered field fails it), plus
  a **Freeport load-and-drive timing exercise** (open the 29-lease golden,
  calculate, drill, export — the "15-tenant deal under an hour" friction
  test on something real). Owner may substitute a different deal.
- **D4 — scenario semantics for v1.** The sidebar has a scenario selector;
  scenario COMPARE is Phase 6. **Recommendation:** v1 scenario = "duplicate
  property JSON under a new name, edit independently" (pure file
  operation); the selector lists them; compare waits for Phase 6.
- **D5 — the two mockup layout choices.** Confirm (or override) adopting
  from the Claude Design exploration: Dashboard as the default-active tab;
  Tenants lease detail as a persistent split pane rather than a drawer.
- **D6 — beta-testing scope for the parked items.** Freeport B
  (general-vacancy basis), Cedar Alt B (rollover recovery timing,
  [AE p. 520] Calculation Frequency), and Freeport E (renewal LC rates)
  were parked FOR beta-stage GUI testing — Phase 5 builds the GUI that
  finally enables that lease-by-lease inspection. **Recommendation:** that
  investigation is a **post-Gate-5 / Phase 6 activity** (it is deal
  forensics, not UI acceptance) — schedule it explicitly then; it is NOT
  a Gate 5 criterion. The three assertions stay red by design meanwhile.
- **(Deferred-index note, no decision needed now):** spec §2 also lists a
  SQLite property index (sqlmodel). v1's property selector scans
  `data/properties/` directly; the index joins when the property count
  makes scanning slow — recorded as sequencing, not scope change.

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
- **Record the Phase 5 baseline commit hash here for the Gate 5 git-log
  check.**
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
as returned).
- **Acceptance:** round-trip + discrimination; import the Phase 4 template
  export of a golden and confirm the Contractual subset lands identically;
  the Speculative-rows note displays; a malformed row shows the readable
  error text verbatim.

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
series).
- **Acceptance:** every rendered report's frame equals the builder's
  output for the same toggles (no UI-side math); the drill-down reproduces
  a Recovery Audit row for a golden tenant-month; exports open and match
  (the Phase 4 cell-by-cell machinery is reused, not rewritten).

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

**Status:** drafted 2026-07-16 on the Gate 4 pass, per the Phase 5
opening directive. **Awaiting owner review — no UI code starts until
Topper has seen this plan and resolved Step 0's decisions.**
