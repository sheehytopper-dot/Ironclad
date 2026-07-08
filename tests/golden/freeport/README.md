# 8505 Freeport Parkway — Golden Fixture #2

Multi-tenant suburban office deal (Las Colinas / Irving, TX) from a JLL
Offering Memorandum with a published Argus-based 11-year cash flow — golden #2
of five (spec §9.1). This is the phase's **base-year / expense-stop recovery**
coverage deal (Phase 2 Gate 2, NEXT_STEPS_TO_GATE2.md Step 7). Sources,
tolerances, and the fixture-lock rule are in CLAUDE.md (Golden-File Strategy)
and [NEXT_STEPS_TO_GATE2.md](../../../NEXT_STEPS_TO_GATE2.md).

Contents: `source/` (OM), `freeport.icprop.json`,
`expected_annual_cash_flow.csv`, `ASSUMPTIONS.md`, and this README.

**Fixture-lock status: CONFIRMED — owner-verified and committed 2026-07-08.** As with
golden #1, there is no standing hand model: disputes resolve by owner per-cell
adjudication (Clorox README ladder — the OM's published annual figures
adjudicate if they discriminate the question by more than the $500/line
tolerance; otherwise the owner recomputes the disputed cells in Excel from the
source alone, without reading engine output or code first).

## Escalation check (NEXT_STEPS_TO_GATE2.md Step 7) — PASSED

Golden #2's slot requires a genuinely multi-tenant deal with base-year or
expense-stop recoveries. Confirmed from the source:

- **27 tenant leases across 27 suites** (29 fixture records — OKI and Texian
  each split into two, §3), ranging 323 SF (AT&T antenna) to 21,226 SF (Rodeo
  Dental, 17% of NRA); no single tenant dominates [OM pp. 53-63].
- **Every office tenant recovers on a base-year method**: the rent roll
  states "OpEx: BY *year* / 95% GU" per tenant, and the general assumptions
  confirm "Available suites are leased up on Base Year Stop + Electricity
  recovery structures" [OM pp. 51, 54-63]. Base years span 2017–2026.

The deal is the intended coverage. It also exercises, beyond the minimum:
rollover with 75% renewal + 9-month downtime, three hard vacates, a
contractual expansion + partial reabsorption, general + static vacancy, a
recoverable %-of-EGR management fee (the Clorox fixed point again), and
FY2029 lumpy capital ($1.39M elevator/curtain-wall). No percentage rent
(office) — that stays golden #3's job.

## Why this fixture is heavier than golden #1

Clorox was one net-leased tenant on a calendar-aligned analysis with an
all-contract early window (Gate 1 asserted FY2027-28 before any rollover).
Freeport has **no all-contract window** — leases roll in every fiscal year
from FY2027 on — so the comparison exercises the full Phase 2 machinery from
year one. Two consequences for Step 7:

1. **Base years are the true stated years; the engine computes the frozen
   pool** (ASSUMPTIONS §5). Each tenant records its real OM base year
   (2017–2026, never a placeholder — owner directive 2026-07-07). The engine's
   pre-analysis fallback [AE pp. 377, 408] resolves 2017–2025 to analysis
   year 1 (no ledger data exists earlier), and 2026 annualizes from its
   in-window months. This session **removed the earlier draft's fabricated
   `$`/SF stops** (CY2026 OpEx pool deflated at an unstated 3%/yr) — the
   fixture no longer manufactures a recovery basis. The engine was extended so
   an explicit pre-analysis base year triggers that documented fallback, and a
   new **known-amount override** (`base_year_amount` / `known_amount`, a total
   annual dollar figure) lets a future deal supply a real stop when one exists;
   Freeport leaves it unpopulated. Whether ARGUS used analysis-year-1 stops
   here is confirmed at Step 7 against the published Expense Reimbursement line.

2. **The expense budgets are back-solved from FY2027** (ASSUMPTIONS §6). The
   fully fixed lines back-solve cleanly (÷1.015; residuals ≤ $0.96 across all
   11 years, and round-number bases fall out — Trash $26,400, Parking
   $27,600). The three variable lines (Electricity, Utilities, Janitorial;
   30% fixed, 95% gross-up) cannot be pinned exactly from annual data because
   they scale on month-by-month occupancy — with the derived stops gone, these
   are now the fixture's weakest inputs.

## Open calculation / engine questions this transcription surfaced

These are flagged now so Step 7 starts with eyes open; none is resolved in the
draft (that is calc work, out of scope here).

1. **Property-revenue pass is phase-guarded.** `run.py` currently refuses
   `parking_revenues` / `miscellaneous_revenues` (Phase 2 guard). This deal
   has Parking, Other Income, and Pylon/Sign lines, so the §4.1 property-
   revenue pass (two-pass for %-of-EGR) must be built before the comparison
   runs. This is real Phase 2 scope, not a fixture question.

2. **MLP base-year + electricity-NNN split has no exact encoding**
   (ASSUMPTIONS §5). A user structure's pool base year is a fixed calendar
   year, not lease-start-relative, so speculative rollover leases can't get a
   per-lease base-year stop *and* electricity-from-dollar-one in a user
   structure. The draft uses the system `base_year` method (lease-start-
   relative, correct per-segment) over all recoverable expenses — meaning
   rollover tenants recover electricity only above its start-year level. A
   small schema addition (lease-start-relative `BaseYearSpec` on a pool)
   likely closes this; decide at Step 7.

3. **General-vacancy basis is unconfirmed** (ASSUMPTIONS §8). The OM states
   the 5% rate and the near-zero FY2028 value implies the A&T offset, but the
   annual data does not discriminate percent-of-PGR vs
   percent-of-total-tenant-revenue at 5%. Adjudication point.

4. **Antenna market rent unit** (ASSUMPTIONS §4). Verizon pays ~$2,913/mo;
   the OM's "$3,000" rollover market is read as per-month (per-year would be a
   ~92% cut). Cheap to verify against the OM's antenna cash-flow contribution
   at QA.

5. **Which fiscal years Gate 2 asserts** is a Step 7 decision with the owner.
   All 11 published years are transcribed in the CSV; revenue/vacancy/
   expense/NOI lines are Gate 2, TI/LC/capital lines Gate 3 (as with Clorox's
   phasing). Because rollover touches every year, there is no clean
   contract-only subset to assert early.

## Files & provenance

- `freeport.icprop.json` — validated through the §3 pydantic models
  (`PropertyModel.model_validate`, schema only, no calc). Every input traces
  to `ASSUMPTIONS.md`.
- `expected_annual_cash_flow.csv` — the OM's published Argus cash flow
  [OM p. 50] transcribed line-for-line, FY2027–FY2037, account names matching
  the spec §2.3 ledger tree. The three property-revenue lines are separate
  CSV rows mapped to the single ledger account (they sum for comparison).
  All seven of the OM's internal identities (scheduled-base, PGR, EGR, opex,
  NOI, capital, cash-flow) reconcile within ≤ $3 rounding on every year — the
  transcription is self-consistent.
- The OM's whole-dollar cash flow and the fixture's back-solved bases mean
  small (< $1) rounding residuals are expected everywhere even when the model
  is exactly right; the $500/line tolerance absorbs them.
