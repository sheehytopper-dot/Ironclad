# NEXT STEPS TO GATE 3

**DRAFT — awaiting owner review. No Phase 3 engine code is written until
Topper has seen this plan (Iron Rule 2 applies to session planning too).**

The concrete path from Gate 2 (**passed 2026-07-10**) through Phase 3 —
capital & valuation (spec §10; BUILD_SCHEDULE.md Week 7) — to **Gate 3**.
Companion to the closed [NEXT_STEPS_TO_GATE1.md](NEXT_STEPS_TO_GATE1.md) and
[NEXT_STEPS_TO_GATE2.md](NEXT_STEPS_TO_GATE2.md); same standing rules
(fixture-lock, owner per-cell adjudication, Iron Rules, no input tuning).

**Scope (spec §10 / §4.1 passes 11-14):** TI/LC posting on rollover,
purchase & closing costs, the debt engine (fixed, floating, IO, amortizing,
additional principal, loan costs), resale methods, PV under all discounting
conventions, unleveraged and leveraged IRR, sensitivity matrices.

## The Gate 3 validation reality (read before the criteria)

**Verified 2026-07-11: none of the three golden OMs publishes any valuation
result.** Clorox and Cedar Alt are explicitly unpriced ("Ownership has not
established an asking price" — offer-requirements pages); Freeport publishes
no price, IRR, discount rate, or exit cap anywhere (keyword scan; the two
"irr" text hits are "IRREPLACEABLE"/"irrigation"). BUILD_SCHEDULE Week 7's
original gate ("PV, IRR, resale match all three goldens"; "matrices reproduce
ARGUS matrices") predates the loss of ARGUS access and, per the 2026-07-03
sourcing note, is read through the Golden-File Strategy instead. Phase 3's
validation therefore rests on:

1. **The goldens' published capital lines** — the one genuinely external
   anchor. All three CSVs already transcribe TI, LC, Capital Expenditures /
   Reserves, Total Capital Costs, and CFBDS (Clorox also Amortized CAM);
   they are currently Gate-3-skipped in every comparison test and activate
   in Step 1.
2. **The §9.3 invariants**, asserted on every run: debt ending balance
   rolls; loan payoff at resale = outstanding balance; price = PV at the
   discount rate → IRR = discount rate (±1bp self-consistency).
3. **The manual's worked examples** (Iron Rule 3, page cites in docstrings):
   resale methods [AE pp. 464-471], PV / discounting conventions
   [AE pp. 472-473 + the Present Value Calculation Examples], standard
   mortgage math (spec §3.17; Loan Amortization report [AE p. 593]),
   security deposits [AE pp. 384, 431-433].
4. **Owner hand-checks** (BUILD_SCHEDULE Week 7 "Your jobs"): one amort
   schedule vs any bank calculator; the 1bp self-consistency spot-check.

**Gate 3 criteria (checklist):**

1. **Golden capital lines within $500/line:** golden #1's FY2029-FY2031
   TI/LC/capital/CFBDS rows activate in `test_clorox_northlake.py`; goldens
   #2/#4's capital-section rows (TI, LC, Capital Expenditures/Reserves,
   Total Capital Costs, **and CFBDS**) activate as **separate new test
   functions** so the deferred-B red assertions stay isolated.
   *Original scoping (drafted 2026-07-11, superseded — kept as the
   historical record, mirroring BUILD_SCHEDULE Week 7):* ~~CFBDS asserts
   on #1 only (on #2/#4 it carries NOI's deferred-B cascade) — owner to
   confirm this scoping in Step 0.~~ **Superseded by owner decision
   2026-07-11:** CFBDS = NOI + Total Capital Costs is an exact linear
   identity in every published Cedar Alt year, FY2031 included
   (8,198,219 + (−1,641,866) = 6,556,353 — owner-verified), so a CFBDS
   miss on #2/#4 carries no independent information beyond its NOI
   cascade. **CFBDS asserts on all three goldens**; a #2/#4 CFBDS miss is
   logged in the DISCREPANCY_LOG as the arithmetic pass-through of the
   already-adjudicated NOI gaps, citing the specific root cause — never
   treated as a new engine defect.
   **Red-by-design note (owner decision 2026-07-12):** Freeport's
   `test_gate3_capital_lines_within_tolerance` stays red by design — its
   LC gap (DISCREPANCY_LOG root cause E) is **deferred to beta-stage GUI
   testing** and is **not a Gate 3 blocker**, mirroring exactly how this
   criterion's Gate 2 counterpart handles Freeport B / Cedar Alt B. Cedar
   Alt's capital test is likewise red only through root cause D, closed
   as C's sibling (its LC deltas = 6.75% × C's accepted free-rent deltas
   to the dollar). Golden #1's capital rows are green within $0.50/cell
   and carry this criterion's external validation.
2. **§9.3 invariants extended and passing on every calc run:** debt balance
   roll (Step 3, ✓), payoff-at-resale identity (Step 4, ✓ —
   `assert_resale_invariants`), PV/IRR self-consistency (±1bp — Step 5).
3. **Manual worked-example unit tests** with page cites for resale, PV
   conventions, loan math, and security deposits (Iron Rule 3).
4. **Sensitivity matrices** (IRR over price × exit cap; value over discount
   × exit cap — spec §7 reports 5-6 data) computed by **re-running valuation
   only, never the ledger** (spec §4.1 note; §1.3), each cell
   self-consistent with a direct single-point valuation run.
5. **Owner hand-checks recorded:** amort vs bank calculator; 1bp check.

**Sequencing rationale (mirrors Phase 2's):** TI/LC first — the goldens'
already-transcribed capital lines give it immediate external validation with
no new fixture work, exactly as golden #1's later years did for rollover.
Debt before resale/PV because leveraged IRR and payoff-at-exit consume the
amort schedule. Sensitivity last — it is purely derivative of PV/IRR.

---

## Step 0 — Owner-gated inputs & decisions (runs in parallel; gates completion, not start)

**Owner: Topper (human). Not a Claude task — future sessions must not act on
these.** Flagged the way golden fixture staging was flagged in Phase 2:

- **Valuation assumption sets for the goldens.** No OM publishes a discount
  rate, exit cap, resale method, selling-cost %, or loan terms. If Gate 3 is
  to exercise valuation on the real fixtures (rather than synthetic tests
  only), the owner supplies an assumption set per golden — discount rate,
  exit cap, resale method, selling costs, and (optionally) loan terms — as
  *exercise inputs*, understood to have **no external reference**; their
  validation is the §9.3 self-consistency identities, not an OM match.
  Alternatively the owner may declare valuation validated on invariants +
  manual examples + hand-checks alone, with fixtures staying debt-free and
  valuation-free. **Owner decision required.**
- **Capital-line assertion scoping** (criterion 1): ~~confirm
  CFBDS-on-#1-only and the separate-test isolation design, or direct
  otherwise.~~ **Resolved 2026-07-11 (owner decision):** CFBDS asserts on
  all three goldens (see criterion 1's supersession note); separate-test
  isolation confirmed.
- **Amort hand-check:** one loan schedule vs any bank amort calculator
  (Week 7 "Your jobs") — **Step 3 landed 2026-07-12; ready for the
  owner now.** The prepared case: $1,000,000 loan, 6.00% rate, 30-year
  amortization → monthly payment **$5,995.51**, balance after 12
  payments **$987,719.88**; if due in 120 months, balloon
  **$836,857.25** (tests/unit/test_debt.py locks the same numbers).
- **Carried-forward items placement** (transparency rule — none of these
  are silently dropped): (a) **tenant miscellaneous items** (spec §4.1 pass
  8, [AE pp. 378-382]) — **BUILT 2026-07-11** (`engine/calc/misc_items.py`;
  guards lifted, Miscellaneous Tenant Revenue live in PGR/EGR/vacancy bases
  and the Lease Audit; narrowings + the externally-unvalidated flag in
  DEVIATIONS.md §15 — no golden uses misc items). (b) **security deposits**
  ([AE pp. 384, 431-433]) — **BUILT 2026-07-12 in Step 2 as proposed**
  (guards lifted; DEVIATIONS.md §17; externally unvalidated — no golden
  uses them).
  (c) **`reabsorb` expirations** — **BUILT for contract leases 2026-07-11**
  (owner-directed; DEVIATIONS.md §8; speculative/MLP chains stay guarded).
  (d) **`pct_of_account` expense/revenue units** — no golden driver;
  proposed to stay guarded until a deal needs them. **Owner confirms (d)
  and the security-deposit placement.**

## Step 1 — TI/LC posting + golden capital lines (sessions 1-2) — **CLOSED 2026-07-12**

**Status: fully closed.** Built 2026-07-11 (owner-directed):
`engine/calc/capital.py` posts TI/LC lump sums at each segment start
(DEVIATIONS.md §16 for the narrowings); golden #1's FY2029-FY2031
capital lines are **green within $0.50/cell**; goldens #2/#4's
capital-line assertions activated as separate test functions. Both
resulting root causes are adjudicated (2026-07-12): **Cedar Alt D closed
as C's sibling** (LC deltas = 6.75% × C's accepted free-rent deltas to
the dollar; the predicted FY2034/36 sibling question materialized
exactly) and **Freeport E deferred to beta-stage GUI testing** (owner
decision 2026-07-12 — side-specific renewal commission structures are
undetectable from OM text or annual totals; see the DISCREPANCY_LOG's
adjudication subsection). Both capital tests stay red by design; no
allowlist mechanism, no input tuning.

Spec §3.9 / §4.1 pass 11 [AE pp. 245-248 read in Step 2 of Phase 2; re-read
alongside the §7 report-4 Sources & Uses shape]: post TIs and LCs in the
month each lease segment starts (or per spread rules if the spec's segment
data carries them) — the blended amounts have been recorded on segments
since Phase 2 Step 1 (`LeaseSegment.ti/lc_pct/lc_rate`), unposted. Contract
TI/LC (the `leasing_costs` guard lifts), absorption-lease costs at MLP
new-tenant economics, and the ledger's Tenant Improvements / Leasing
Commissions / Total Capital Costs / CFBDS lines go live. **Then activate the
golden capital-line assertions** (criterion 1): #1's FY2029-FY2031 rows in
the existing test; #2/#4 rows as new separate test functions; misses to the
DISCREPANCY_LOGs for owner per-cell adjudication — never input tuning.
(Expect Cedar Alt FY2034/36 TI/LC to inherit the adjudicated OM free-rent
inconsistency's sibling question — the OM's rollover TI/LC are published and
will adjudicate the blend directly.)

## Step 2 — Purchase, closing costs, security deposits (session 3) — **CLOSED 2026-07-12**

**Status: shipped 2026-07-12.** `engine/calc/investment.py` posts the
fixed-derivation purchase price and $/%-of-price closing costs (at the
purchase month or a custom date) and per-segment security deposits
(collection at segment start, refund in the final month when refundable;
months-of-rent sized on month-one base rental revenue per [AE p. 432];
contract terms use the lease's spec, speculative terms the MLP's per
[AE p. 384]). Three new **below-the-line** ledger columns (Purchase
Price / Closing Costs / Security Deposits) post after CFBDS, outside
every rollup — the original "ahead of CFBDS" phrasing is read as
"present before valuation consumes it," confirmed against [AE p. 435]
(purchase feeds return metrics; the Cash Flow report has no acquisition
rows) and test-proven CFBDS-neutral. Both security-deposit guards
lifted; derived price derivations refuse loudly naming Step 5.
Narrowings + judgment calls in DEVIATIONS.md §17; 13 manual-cited tests
(tests/unit/test_investment.py). **EXTERNALLY UNVALIDATED** — no golden
populates `purchase` or `security_deposit`, the same standing as
Step 0's carried-forward items (reabsorb, misc items).

## Step 3 — Debt engine (sessions 4-5) — **CLOSED 2026-07-12 (one session)**

**Status: shipped 2026-07-12, full planned scope except one deliberate
exclusion.** `engine/calc/debt.py`: fixed and floating (index YearRate
schedule + spread; payment re-levels on each rate change — the [AE
p. 444] "same term" recalc applied to rate changes, manual otherwise
silent), IO periods with re-level at amortization start, balloon
("amortized over N years due in M months"; balloon posts at maturity),
additional principal (the [AE p. 444] Recalc-Pmt-**No** behavior — the
schema has no toggle), loan costs (expense at funding / straight-line
amortize over term, posting to the financing section per [AE p. 446]),
multiple loans, per-loan `LoanSchedule` detail retained on RunResult for
the §7 report 20 builder. Ledger financing section live: Debt Funding
(display-only, **outside** CFADS — [AE p. 447] proceeds default-hidden;
§4.1 pass 14 equity at t0), Interest Expense, Principal Payments, Loan
Costs, Total Debt Service, CFADS = CFBDS + TDS. **§9.3 debt invariants
standing on every run**: balance roll, non-negative balances, IO months
amortize nothing, fully-amortizing balloon ~$0 (payoff-at-resale is
Step 4, as planned — the balance series is correct and retained for
it). `pct_of_value` loan sizing refuses loudly naming Step 5.
**Deliberate exclusion:** "Other Debt" [AE pp. 448-449] is NOT built —
the manual's Other Debt is inflated recurring streams, not
simple-interest loans; the Loan docstring's "fixed-payment loans"
suggestion is insufficient and is recorded as such (DEVIATIONS.md §18).
19 closed-form tests (tests/unit/test_debt.py). **Validation = worked
examples + the owner's bank-calculator hand-check (Step 0) — for debt
that IS the designed path; no golden has loans.** Hand-check case:
$1,000,000 / 6.00% / 30-year amortization → payment 5,995.51, balance
after 12 payments 987,719.88, balloon at month 120 836,857.25.

## Step 4 — Resale (session 6) — **CLOSED 2026-07-12**

**Status: shipped 2026-07-12, full planned scope.** `engine/calc/resale.py`
implements all five methods per their [AE p. 465] definitions — the Part A
adjudications (`gross_value_less_costs` = CAP Effective Gross Rents,
EGR − recoveries; `cap_noi_current_year` = the analysis year of sale;
forward-12 window relative to the resale date, capped at analysis end;
`exclude_capital=True` is a real no-op since NOI already excludes capital,
`False` adds the window's Total Capital Costs; `stabilize_occupancy` =
"NOI × Gross Up % / Average Occupancy %" [AE p. 469] over the run's
occupancy series, no ledger recompute; adjustments before selling costs;
payoff = the resale-month ending balance) are all in DEVIATIONS.md §19.
Two below-the-line ledger columns (Net Resale Proceeds, Loan Payoff at
Resale) — the leveraged net is their visible sum, CFBDS/NOI/CFADS
unchanged (test-locked). `apply_resale_to_cash_flow=False` computes and
retains everything but posts nothing. Property Resale Audit report built
(`engine/reports/resale_audit.py`, spec §7 report 21) with exact
ledger reconciliation (`reconcile_resale_audit`, tested to 1e-9),
mirroring the lease/recovery audits. `direct_cap` refuses loudly (Step 5);
only `valuation.resale` is consumed. **§9.3 payoff-at-resale invariant
standing** on every run with resale + loans. 18 tests
(tests/unit/test_resale.py). **EXTERNALLY UNVALIDATED** — no golden
populates `valuation`, none will (no OM publishes a valuation result);
worked examples + owner hand-checks only. Hand-check: current-year NOI
100,000 at 8.00% exit cap = 1,250,000 gross, 3% selling 37,500, net
1,212,500.

## Step 5 — PV & IRR (session 7)

Spec §3.18 / §4.1 pass 14 [AE pp. 472-473 + Present Value Calculation
Examples]: unleveraged PV under all discounting conventions (annual /
quarterly / monthly × end-of-period / mid-period), direct cap
[AE pp. 453-454], unleveraged and leveraged IRR (monthly solve, annualized),
price-derived-from-valuation closes the §3.16 toggle. **The §9.3
self-consistency test becomes a standing invariant: set price = computed PV,
assert IRR = discount rate within 1bp.** Valuation runs must not recompute
the ledger (spec §4.1; the RunResult is the input).

## Step 6 — Sensitivity matrices (session 8)

Spec §3.18 `sensitivity_intervals` [AE pp. 451-452]: IRR matrix (price ×
exit cap) and value matrix (discount rate × exit cap) as data builders
(report rendering is Phase 4), 5/7-point grids, each cell produced by
re-running valuation only. Cross-check: every matrix cell equals a direct
single-point valuation at those inputs (engineered test).

## Step 7 — Gate 3 review (owner)

Criteria 1-5 evidenced in one pytest run: golden capital lines within
tolerance (or misses adjudicated), invariants green, worked-example tests
green, matrices self-consistent, hand-checks done. Red by design and **not
Gate 3 blockers**: the Freeport/Cedar Alt Gate 2 assertions (deferred-B
items) and **Freeport's Gate 3 capital-line assertion (root cause E,
deferred to beta-stage GUI testing — owner decision 2026-07-12)**; Cedar
Alt's capital assertion is red only through root cause D, closed as C's
sibling with no independent engine question. Then — and only then —
Phase 4 (Iron Rule 2).

---

**Standing gaps carried into Phase 3:** percentage rent remains
externally unvalidated pending golden #3 (standing opportunistic intake);
Freeport B and Cedar Alt B stay parked for beta-stage GUI testing (owner
decision 2026-07-10), joined by **Freeport E** (owner decision
2026-07-12); no ARGUS access — the Benchmark Comparison report
(spec §7 report 24) remains the future-deal validation path.

**Status:** drafted 2026-07-11 on Gate 2 pass, per the Phase 3 opening
prompt. **Awaiting owner review — engine work does not start until Topper
has seen this plan and resolved Step 0's decisions.**
