# Discrepancy Log — Clorox Northlake (golden #1)

Short log of anything explained within tolerance (NEXT_STEPS_TO_GATE1.md
Step 7 for Gate 1; carried forward for the Gate 2 scope). Engine vs
`expected_annual_cash_flow.csv` (owner-verified 2026-07-04), tolerance
$500/line (spec §9.1).

## Gate 2 scope activation (2026-07-06): FY2029-FY2031, worst deviation $0.86

With rollover projection (Phase 2 Step 2), the FY2029-FY2031 revenue,
vacancy, expense, and NOI lines are asserted (capital lines wait for
Gate 3). Every line lands within $1: the largest deviation is $0.86
(FY2029 CAM), the same OM whole-dollar-rounding effect as Gate 1's.
Notable confirmations of the §4.2 rollover model against the OM's Argus
output: downtime months post no recoveries and no management fee (FY2029
Expense Recoveries within $1); free rent (0.75 weighted months,
$256,008) reduces EGR before the fee; A&T Vacancy = 2 downtime months at
the blended market rent ($682,689 exactly). Nothing rises to owner
per-cell adjudication.

## Gate 1 (2026-07-05): FY2027-FY2028, all lines within $1

All 21 transcribed lines within $1 in both fiscal years.

The only non-zero deltas are **+$1 on Total Potential Gross Revenue and
Effective Gross Revenue in FY2027** (engine 3,927,263 vs OM 3,927,262).

**Explanation:** whole-dollar rounding in the OM's published report. The OM
prints each line rounded to dollars and its subtotals are computed from
unrounded values; the transcription necessarily carries those printed
roundings. The engine computes full precision and rounds nothing inside the
ledger (spec §4.3), so a subtotal can differ from the sum of the printed
detail lines by up to ±$0.5 × (number of detail lines). No engine/OM
methodological disagreement is present or suspected; nothing rises to
owner per-cell adjudication.

## Supporting relationships verified

- Management Fee = 3.0000% of final EGR in both years (FY2027: 117,818 /
  3,927,263), confirming the %-of-EGR fixed point through the net recovery
  pool (run.py docstring; OM p. 27's 3%-of-gross-rents cap).
- NOI = Scheduled Base Rental Revenue in both years — the NNN identity for
  a 100%-share net-recovery single tenant (recoveries exactly offset
  operating expenses).
- Sum(monthly) = fiscal annual for every account (spec §9.3, asserted in
  `test_clorox_northlake.py` and on every run).

## Status

Gate 1 comparison green in the full pytest run (126 tests). **Owner Gate 1
review (Step 7) pending** — Phase 2 does not begin until the owner declares
the gate passed (Iron Rule 2).
