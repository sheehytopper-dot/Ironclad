# NEXT STEPS TO GATE 1

The concrete path from Phase 0 (complete) to passing **Gate 1**: the engine's
cash flow for the first golden property matches its validation targets.

**Context:** We do not have ARGUS access, so no ARGUS output exports are
coming. Spec §9.1's sourcing is superseded by the three-source golden-file
strategy in [CLAUDE.md](CLAUDE.md#golden-file-strategy-supersedes-spec-91-sourcing).
The first golden property is **Clorox Northlake** — a single-tenant net-lease
deal from a CBRE Offering Memorandum with a published Argus-based cash flow.

---

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

## Step 3 — Independent hand model (owner-built)

Topper builds `tests/golden/clorox_northlake/hand_model.xlsx` — a monthly
Excel model of the same deal — **independently, without Claude's
involvement**. Independence is the point: it cross-checks both the engine and
the OM transcription. Claude must never create, edit, or "fix" this file; if
the engine and the hand model disagree, investigate and report, and let the
owner adjudicate. Can proceed in parallel with Steps 2 and 4.

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
  **every line within $500 per fiscal year**
- Engine monthly ledger vs `hand_model.xlsx`: **every line within $1 per
  month**
- Sum(monthly) = annual for every account (spec §9.3)

## Step 6 — Gate 1 review

Both comparisons green in the same pytest run, invariants passing, and a
short discrepancy log for anything explained within tolerance. Then — and
only then — Phase 2 work may begin (Iron Rule 2).

---

**Status:** Step 1 pending source documents. Step 3 is owner work. Steps 2
and 4 can start now and run in parallel.
