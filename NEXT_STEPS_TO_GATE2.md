# NEXT STEPS TO GATE 2

The concrete path from Gate 1 (**passed 2026-07-05**) through Phase 2 —
market machinery (spec §10) — to **Gate 2**. Companion to the closed
[NEXT_STEPS_TO_GATE1.md](NEXT_STEPS_TO_GATE1.md); same standing rules
(fixture-lock, owner per-cell adjudication, Iron Rules).

**Gate 2 criteria (spec §10, §9.1; CLAUDE.md):**

1. Goldens **#2 (8505 Freeport Parkway)**, **#4 (Cedar Alt Bldgs 1 & 3)**,
   **#5 (Inland Logistics)** — annual fiscal-year cash flows within
   $500/line of each OM's published Argus output.
2. Golden #1's **FY2029-FY2031 revenue/vacancy lines activate** (the
   owner-approved 2026-07-03 phasing deferred them to Gate 2; TI/LC/capital
   lines wait for Gate 3).
3. **Lease Audit and Recovery Audit reports** built, reconciling exactly to
   the ledger, and **owner-reviewed**.
4. **Percentage rent** built with the manual's worked-example unit tests
   (Iron Rule 3) but **externally unvalidated pending golden #3** (standing
   opportunistic intake, owner decision 2026-07-05).
5. **Turnover vacancy does not double-count against general vacancy** — a
   test verifies total vacancy % equals the stated rate (BUILD_SCHEDULE
   Gate 2).

**Sequencing rationale (owner-directed):** rollover blending first — golden
#1's FY2029-FY2031 columns give it immediate external validation with no
new fixture needed, and spec §4.2 calls it "the most common source of
divergence." Percentage rent last — it has no external reference until
golden #3 arrives, so nothing downstream should wait on it.

---

## Step 0 — Golden fixtures #2/#4/#5 (owner; runs in parallel)

**Owner: Topper (human). Not a Claude task — future sessions must not act
on this.** For each of Freeport (#2), Cedar Alt (#4), Inland (#5), from the
2026-07-03 `OM/` triage: stage source pages under
`tests/golden/<deal>/source/`, transcribe inputs to `.icprop.json` +
`expected_annual_cash_flow.csv` + `ASSUMPTIONS.md` with OM page cites, and
human-verify before any engine comparison runs (fixture-lock rule).
Transcription sessions can be Claude-assisted like Clorox was, but owner
QA seals each fixture. **These gate the phase's completion, not its
start** — Steps 1-6 proceed against golden #1's later years and the
manual's worked examples.

Two verification checks during staging (owner-approved 2026-07-05):

- **Freeport (#2):** confirm when staged that the deal is genuinely
  multi-tenant with base-year or expense-stop recoveries — golden #2's
  slot requires exactly that coverage. **If it is not, escalate to the
  owner immediately** (a replacement deal must be triaged before Step 7
  plans around it).
- **Inland (#5):** confirm the cash flow's Argus provenance **from the
  page image** — no Argus attribution exists in the document's text
  layer, so text search cannot settle it.

## Step 1 — Lease chain resolution & market rent machinery (session 1)

Spec §4.1 pass 3 in full + §3.6 [AE pp. 233-252]: resolve every rent roll
lease into a segment chain — contract term → weighted speculative segments
per MLP → chained profiles (`market`/`option`/`renew`/`vacate`/`reabsorb`)
— through analysis end + resale horizon. Market rent series per unit type
with `term_growth` inflation; §4.2 weighted blending (rent, downtime, free
rent, TI/LC — costs recorded on segments now, **posted** in Phase 3);
Intelligent Renewals toggle per the manual's stated behavior [AE p. 235].
Read [AE pp. 233-252] before implementing; worked-example unit tests with
page cites (Iron Rule 3).

## Step 2 — Rollover into the ledger + golden #1 FY2029-31 (session 2)

Project speculative segments into Base Rental Revenue at blended rent;
downtime posts **Absorption & Turnover Vacancy** negatives at the rate the
space would have earned (never zero revenue — PGR stays full-occupancy,
spec §2.3/§4.2) and reduces occupied area by (1−p) × lease area; weighted
free rent; MLP recovery assignments on speculative segments. Then
**activate golden #1's FY2029-FY2031 revenue/vacancy assertions** in
`tests/golden/test_clorox_northlake.py` (Base, A&T Vacancy, Free Rent,
Scheduled, Recoveries, PGR, EGR, opex, NOI — capital lines stay Gate 3).
Spec §4.2's own warning applies: validate against a golden early. Misses
go to owner per-cell adjudication — inputs are never tuned.

## Step 3 — Space absorption (session 3)

Spec §3.15 [AE pp. 395-403]: synthetic leases generated on the schedule
(count/area, start, interval), each behaving as a rent roll lease
thereafter (chains, recoveries, occupancy effects). `reabsorb` expiration
behavior joins here.

## Step 4 — General vacancy & credit loss with offsets (session 4)

Spec §3.4/§3.5 [AE pp. 224-232]: the three percentage methods,
`include_in_pgr_accounts`, tenant overrides, and — critical, frequently
misimplemented — `reduce_by_absorption_turnover`: monthly General Vacancy
= max(0, target − A&T vacancy already in the ledger). Credit loss applies
after general vacancy on the reduced base. The %-of-EGR fixed point in
run.py gains the vacancy terms (EGR no longer equals Total PGR).

## Step 5 — Full recovery structures (sessions 5-6)

Spec §3.14 [AE pp. 404-413, 517-520]: system methods `base_stop`,
`base_year` (±1, frozen, optional gross-up), `fixed`; user structures —
pools over expenses/groups, **gross-up** (variable portions only, worked
example test [AE p. 407]), denominators, admin fees before/after stop
[AE p. 520], caps/floors [AE pp. 411-412], expense adjustments
[AE p. 410], pro-rata overrides; free-rent abatement of recoveries
(`abate_recoveries`, deferred from Phase 1); per-tenant per-pool audit
detail retained. **The Recovery Audit report (spec §7 report 18 — per
tenant per pool: expenses, gross-up, stop, share, caps, fee) is built at
the end of this step's second session**, not later: BUILD_SCHEDULE Week 5
requires it early as the debugging tool for everything recovery-shaped
that follows. It must reconcile exactly to the ledger.

## Step 6 — Lease Audit report (session 7)

`engine/reports/`: Lease Audit (spec §7 report 16 — per-tenant monthly
rent build-up: base, steps, CPI, free, recoveries, % rent as built so
far), reconciling exactly to the ledger. **Owner review of both audit
reports — this one and Step 5's Recovery Audit — is a Gate 2 criterion.**

## Step 7 — Golden comparisons #2, #4, #5 (sessions 8+; needs Step 0)

One comparison test per fixture as each lands (fixture-lock verified
first), same shape as the Clorox Gate 1 test: fiscal-year, $500/line,
misses reported for owner per-cell adjudication with a discrepancy log.
Expect Freeport (#2) to exercise base-year/stop recoveries, Cedar Alt and
Inland (#4/#5) gross-ups, caps, or absorption per the triage.

## Step 8 — Percentage rent, last (session 9)

Spec §3.13 [AE pp. 249-250, 376]: sales volume growth, natural / fixed /
zero breakpoints, up to 6 layers, offset/recapture. Manual worked-example
unit tests with page cites (Iron Rule 3). **Externally unvalidated pending
golden #3** (standing intake): the module ships, but any retail
underwriting before the golden #3 back-test treats the Percentage Rent
line as unverified (CLAUDE.md, Known validation gaps).

## Step 9 — Gate 2 review (owner)

All three golden comparisons green in the same pytest run alongside golden
#1 (FY2027-FY2031 revenue scope), audit reports owner-reviewed, discrepancy
logs written. Then — and only then — Phase 3 (Iron Rule 2).

---

**Status:** created 2026-07-05 on Gate 1 pass. Step 0 is owner-scheduled;
Step 1 is the next engine session.
