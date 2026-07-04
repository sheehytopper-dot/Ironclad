# NEXT STEPS TO GATE 1

The concrete path from Phase 0 (complete) to passing **Gate 1**: the engine's
cash flow for the first golden property matches its validation targets.

**Context:** We do not have ARGUS access, so no ARGUS output exports are
coming. Spec §9.1's sourcing is superseded by the three-source golden-file
strategy in [CLAUDE.md](CLAUDE.md#golden-file-strategy-supersedes-spec-91-sourcing).
The first golden property is **Clorox Northlake** — a single-tenant net-lease
deal from a CBRE Offering Memorandum with a published Argus-based cash flow.

---

## Step 0 — Repo privacy

**Owner: Topper (human). Not a Claude task — future sessions must not act on this.**

The repo must be verified **Private** before any confidential OM material is
committed. **Verified Private by Topper on 2026-07-03.** If a collaborator is
ever added to the repo, `tests/golden/` moves to `.gitignore` *first* —
before the invitation goes out.

## Step 1 — Source documents

Place the CBRE OM (or at minimum its cash flow pages) in
`tests/golden/clorox_northlake/source/`. Deal documents are reference
material, same rules as the manual: never copy their text into the product.

## Step 2 — Build the Clorox fixture  ← Phase 1 begins when this lands

In `tests/golden/clorox_northlake/`:

1. `clorox_northlake.icprop.json` — the deal's inputs recreated in our §3
   schema (property, areas, inflation, the Clorox lease with its steps and
   recovery method, expenses, and any absorption/vacancy assumptions the OM
   states).
2. `expected_annual_cash_flow.csv` — the OM's published Argus cash flow
   transcribed line-for-line, fiscal-year columns, account names matching the
   spec §2.3 ledger tree.
3. `ASSUMPTIONS.md` — every input the OM states, with OM page cites; every
   input the OM does *not* state, with the assumption made and why. This is
   the audit trail when a line item disagrees.

Fixture-building is transcription and schema work, not calc work — it needs
no engine code and can start immediately.

## Step 3 — Independent monthly hand schedule (owner-built; descoped 2026-07-03)

Topper builds `tests/golden/clorox_northlake/hand_model.xlsx` — a
**monthly-resolution schedule for Clorox only**, covering base rent, steps,
inflation timing, and expense growth (not a full DCF) — **independently,
without reading the engine**. Independence is the point: its purpose is
adjudicating month-level timing mechanics that the OM's annual figures cannot
discriminate, and it is authoritative only on those questions (CLAUDE.md,
Golden-File Strategy). Claude must never create, edit, or "fix" this file; if
the engine and the hand schedule disagree, investigate and report, and let
the owner adjudicate.

**Due within 48 hours of Topper's QA pass on the Clorox fixture (Step 2)** —
recorded as a standing convention in CLAUDE.md.

## Step 4 — Phase 1 engine work (spec §10)

Implement, in dependency order, each with manual worked-example unit tests
(page cites in docstrings — Iron Rule 3):

1. `engine/calc/leases.py` — contract-term base rent: all unit types
   [AE pp. 391-394, normative examples], fixed steps and % bumps, CPI
   [AE pp. 255-257], free rent [AE pp. 253-254]
2. `engine/calc/expenses.py` — amount/unit/timing types, inflation,
   %-fixed occupancy scaling, repeating payments [AE pp. 361-362]
3. `engine/calc/recoveries.py` — simple net (100% pro-rata) recoveries only
4. `engine/calc/ledger.py` — account tree + monthly ledger assembly,
   occupancy series, NOI (spec §2.3)
5. `engine/calc/run.py` — orchestration passes 1-6 of spec §4.1 (through
   recoveries; no % rent, vacancy blending, debt, or valuation yet)
6. Property-level invariants from spec §9.3 asserted on every run (those
   that apply pre-valuation)

## Step 5 — Golden comparison tests (Gate 1)

`tests/golden/test_clorox_northlake.py`:

- Engine annual (fiscal-year) cash flow vs `expected_annual_cash_flow.csv`:
  **every line within $500 per fiscal year** — the standard for all five OM
  goldens (spec §9.1)
- Engine monthly ledger vs the `hand_model.xlsx` monthly hand schedule, on
  the lines it covers (base rent, steps, inflation timing, expense growth):
  adjudicates **month-level timing questions the annual OM data cannot
  discriminate** — authoritative only there
- Sum(monthly) = annual for every account (spec §9.3)

## Step 6 — Source additional OM goldens (parallel; due end of week 2)

**Owner: Topper (human). Not a Claude task — future sessions must not act on this.**

The strategy is **five OM goldens**, each validated annually at fiscal-year
level **within $500 per line** (spec §9.1). Per the 2026-07-03 triage of the
`OM/` pile:

1. **#2 multi-tenant base-year/stop** → 8505 Freeport Parkway (in `OM/`)
2. **#3 retail with percentage rent** → **not in the pile — the outstanding
   broker ask** (ideally also covering recovery admin fees and/or absorption)
3. **#4, #5 coverage picks** → Cedar Alt Bldgs 1 & 3 and Inland Logistics
   (in `OM/`)

Remaining sourcing (the retail % rent OM) **by end of week 2 (target:
2026-07-17)** — Phase 2's gate depends on goldens #2-#5, and fixture
transcription takes time, so late sourcing stalls Phase 2 directly. Runs in
parallel with Steps 2-5.

## Step 7 — Gate 1 review

Both comparisons green in the same pytest run, invariants passing, and a
short discrepancy log for anything explained within tolerance. Then — and
only then — Phase 2 work may begin (Iron Rule 2).

---

**Status:** Step 0 verified 2026-07-03. Step 1 done — the Clorox OM is staged
in `tests/golden/clorox_northlake/source/`. Steps 3 and 6 are owner work
(human-owned; not Claude tasks). Steps 2 and 4 can start now and run in
parallel.
