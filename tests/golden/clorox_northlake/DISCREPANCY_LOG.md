# Gate 1 Discrepancy Log — Clorox Northlake (golden #1)

Required by NEXT_STEPS_TO_GATE1.md Step 7: a short log of anything explained
within tolerance. Engine run of 2026-07-05 (`engine/calc/run.py`) vs
`expected_annual_cash_flow.csv` (owner-verified 2026-07-04), Gate 1 fiscal
years FY2027 and FY2028, tolerance $500/line (spec §9.1).

## Result: all 21 transcribed lines within $1 in both fiscal years

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
