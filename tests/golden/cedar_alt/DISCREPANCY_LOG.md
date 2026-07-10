# Discrepancy Log — Cedar Alt Distribution Center (golden #4)

Engine vs `expected_annual_cash_flow.csv` (the OM's published Argus Enterprise
14.0.2 cash flow, owner-verified 2026-07-08), tolerance
**$500/line/fiscal-year** (spec §9.1), scope FY2027–FY2037
revenue/vacancy/expense/NOI lines (Gate 2; TI/LC/capital wait for Gate 3).
Produced by `tests/golden/test_cedar_alt.py`.

**These misses are logged for owner per-cell adjudication (CLAUDE.md
Golden-File Strategy). Claude does not resolve them and did not tune
`cedar_alt.icprop.json` to reduce them — the inputs are the owner-verified
transcription. Only Topper recomputes disputed cells independently from the
source OM.**

## Summary

**118 of 165 in-scope line-years within $500; 47 miss.** Far tighter than
Freeport's comparison: seven of the eleven fiscal years (FY2032, FY2035,
FY2037 fully; FY2029/2030 near-fully) have at most the small day-count
residual, and six lines are clean across all eleven years. The misses trace
to three root causes plus their arithmetic cascade:

| # | Root cause | Primary lines | Pre-flagged? |
|---|---|---|---|
| A | GPR day-count residual (Crane's April-1 steps; ARGUS actual/365 proration vs monthly posting) | Base Rental Revenue FY2027–FY2030 (+ FY2033 echo) | **Yes** — README open question 2 / ASSUMPTIONS §3, which predicted FY2027 ≈ $5,382 low; the engine's FY2027 delta is **exactly −5,382** |
| B | Rollover-year recovery timing during downtime | Expense Recovery Revenue FY2031/FY2034/FY2036 | **Yes** — README open question 1 / ASSUMPTIONS §5 (the three rollover years) |
| C | Rollover free rent: the OM abates only Crane's first rollover; the engine abates every rollover per the MLA | Free Rent FY2034/FY2036 | **No — new finding**, the largest single driver (−$950K FY2034) |
| — | Arithmetic cascade of A+B+C | Scheduled Base, Total PGR, EGR, Management Fee, Total OpEx, NOI | consequence, not independent |

**Lines within $500 across all 11 fiscal years (no miss):** Absorption &
Turnover Vacancy, General Vacancy, Common Area Maintenance, Utilities,
Insurance, and **Real Estate Taxes** — the `annual_overrides` RET line
(DEVIATIONS.md §12, the Bldg-1 abatement escape hatch) reproduces the
published figures exactly, as designed.

---

## Root cause A — GPR day-count residual (pre-flagged; ASSUMPTIONS §3)

ASSUMPTIONS §3 predicted this to the dollar: summing the two leases' stated
rents gives FY2027 GPR ≈ $8,035,228 vs the published $8,040,610 — "≈$5,382 /
0.07% low, consistent with ARGUS day-count (actual/365) proration against the
fixture's monthly posting." The engine posts **exactly 8,035,228** in FY2027.
The residual persists at ~0.07% while Crane's April-1 steps are in force
(FY2027–FY2030), disappears once Crane rolls to market terms (FY2031+ within
tolerance), and leaves a +$1,080 echo in FY2033 (speculative-term step timing
around Bldg 1's May-31 expiry). An adjudication of timing convention, not an
input to tune.

### Base Rental Revenue — 5 misses
| FY | engine | published | delta |
|---|--:|--:|--:|
| 2027 | 8,035,228 | 8,040,610 | -5,382 |
| 2028 | 8,316,512 | 8,322,071 | -5,559 |
| 2029 | 8,607,538 | 8,613,296 | -5,758 |
| 2030 | 8,908,794 | 8,914,751 | -5,957 |
| 2033 | 9,822,519 | 9,821,439 | +1,080 |

---

## Root cause B — Rollover-year recovery timing (pre-flagged; README open question 1)

Recoveries equal Total Operating Expenses exactly in every fully-occupied year
(all within tolerance) and diverge **only** in the three rollover years the
README named — FY2031 (Crane's first roll), FY2034 (Bldg 1's roll), FY2036
(Crane's second roll). The engine's weighted-downtime recovery gap
(probability-blended occupancy) differs from however ARGUS timed the discrete
vacancy in those years: the engine recovers **more** than the OM in FY2031
(+$81,836) and FY2036 (+$82,500) and **less** in FY2034 (−$145,660).
Directionally mixed — a timing-convention adjudication, not a one-sided model
gap like Freeport's base-year issue.

### Expense Recovery Revenue — 3 misses
| FY | engine | published | delta |
|---|--:|--:|--:|
| 2031 | 2,450,398 | 2,368,562 | +81,836 |
| 2034 | 2,204,426 | 2,350,086 | -145,660 |
| 2036 | 2,925,613 | 2,843,113 | +82,500 |

---

## Root cause C — Rollover free rent (NEW finding, not pre-flagged; the largest driver)

The OM's published Free Rent line is nonzero in **exactly one** year: FY2031
(−$261,724, Crane's first rollover) — which the engine **matches within
tolerance** using the MLA's stated abatements (3.0 months new / 1.0 renewal,
weighted 1.5). But the engine applies the same MLA abatements to **every**
rollover, so it also posts weighted free rent on Bldg 1's FY2034 rollover
(−$950,298 on 1,084,462 SF) and Crane's second rollover (FY2036, −$303,410),
where **the OM shows zero**. Same machinery, same inputs — the divergence is
*which* rollovers receive abatements, not how they are computed. Notably the
OM's Absorption & Turnover Vacancy matches the engine within tolerance in all
eleven years, so the two models agree on downtime and disagree only on the
abatement line. Whether ARGUS's model suppressed abatements on the later
rollovers (and why FY2031 alone carries them) is an **owner per-cell
adjudication** against the source OM; the fixture's MLA inputs are the OM's
stated "Free Rent (5FY Duration; BR Only) 3.0 / 1.0 / WA 1.50" [OM p. 27] and
were not tuned.

### Owner adjudication (2026-07-09)

The OM's published free rent is **zero** on the FY2034 and FY2036 rollovers
despite the OM's own stated MLA terms (3.0 months new / 1.0 renewal, weighted
1.5) calling for free rent on every rollover — which is what the engine
correctly applies. **Owner determination:** this is most likely a broker-side
override on the published pro forma (a common practice to present stronger NOI
in the year a large tenant's lease rolls, which is precisely FY2034's dollar
impact), or an unrecorded per-tenant renewal assumption not visible anywhere
in the OM's text — and it is **unconfirmable without the source Argus file,
which is not available**. **Do not tune the engine or the fixture to match
the OM's zero.** The engine's figures (−950,298 FY2034; −303,410 FY2036) are
treated as the mechanically correct output given the OM's own stated leasing
assumptions, and this divergence is logged as an **accepted, unconfirmable OM
inconsistency** rather than an open engine question. **Root cause C is
adjudicated — closed.**

### Free Rent — 2 misses
| FY | engine | published | delta |
|---|--:|--:|--:|
| 2034 | -950,298 | 0 | -950,298 |
| 2036 | -303,410 | 0 | -303,410 |

---

## Arithmetic cascade of A + B + C (not independent findings)

These lines carry the root-cause deltas by construction; adjudicating A/B/C
resolves them.

### Scheduled Base Rental Revenue — 7 misses (A in FY2027–30/33; C in FY2034/36)
| FY | engine | published | delta |
|---|--:|--:|--:|
| 2027 | 8,035,228 | 8,040,610 | -5,382 |
| 2028 | 8,316,512 | 8,322,071 | -5,559 |
| 2029 | 8,607,538 | 8,613,296 | -5,758 |
| 2030 | 8,908,794 | 8,914,751 | -5,957 |
| 2033 | 9,822,519 | 9,821,439 | +1,080 |
| 2034 | 7,053,287 | 8,003,585 | -950,298 |
| 2036 | 9,585,911 | 9,889,321 | -303,410 |

### Total Potential Gross Revenue — 8 misses
| FY | engine | published | delta |
|---|--:|--:|--:|
| 2027 | 10,374,037 | 10,379,556 | -5,519 |
| 2028 | 10,721,028 | 10,726,729 | -5,701 |
| 2029 | 11,079,185 | 11,085,090 | -5,905 |
| 2030 | 11,440,243 | 11,446,353 | -6,110 |
| 2031 | 10,852,354 | 10,770,518 | +81,836 |
| 2033 | 12,558,089 | 12,556,981 | +1,108 |
| 2034 | 9,257,714 | 10,353,671 | -1,095,957 |
| 2036 | 12,511,524 | 12,732,434 | -220,910 |

### Effective Gross Revenue — 8 misses (identical to Total PGR; General Vacancy is 0 both sides)
| FY | engine | published | delta |
|---|--:|--:|--:|
| 2027 | 10,374,037 | 10,379,556 | -5,519 |
| 2028 | 10,721,028 | 10,726,729 | -5,701 |
| 2029 | 11,079,185 | 11,085,090 | -5,905 |
| 2030 | 11,440,243 | 11,446,353 | -6,110 |
| 2031 | 10,852,354 | 10,770,518 | +81,836 |
| 2033 | 12,558,089 | 12,556,981 | +1,108 |
| 2034 | 9,257,714 | 10,353,671 | -1,095,957 |
| 2036 | 12,511,524 | 12,732,434 | -220,910 |

### Management Fee (2.5% of EGR) — 3 misses
| FY | engine | published | delta |
|---|--:|--:|--:|
| 2031 | -271,309 | -269,263 | -2,046 |
| 2034 | -231,443 | -258,842 | +27,399 |
| 2036 | -312,788 | -318,311 | +5,523 |

### Total Operating Expenses — 3 misses (the fee cascade; the other four expense lines are clean)
| FY | engine | published | delta |
|---|--:|--:|--:|
| 2031 | -2,574,344 | -2,572,299 | -2,045 |
| 2034 | -2,714,041 | -2,741,440 | +27,399 |
| 2036 | -3,073,778 | -3,079,300 | +5,522 |

### Net Operating Income — 8 misses
| FY | engine | published | delta |
|---|--:|--:|--:|
| 2027 | 8,035,228 | 8,040,610 | -5,382 |
| 2028 | 8,316,512 | 8,322,071 | -5,559 |
| 2029 | 8,607,538 | 8,613,296 | -5,758 |
| 2030 | 8,908,794 | 8,914,751 | -5,957 |
| 2031 | 8,278,010 | 8,198,219 | +79,791 |
| 2033 | 9,822,519 | 9,821,439 | +1,080 |
| 2034 | 6,543,672 | 7,612,231 | -1,068,559 |
| 2036 | 9,437,746 | 9,653,134 | -215,388 |

---

## Status

Golden #4 comparison **FAILS** — `test_cedar_alt.py`'s Gate 2 assertion fails
with the 47 line-years above (118 of 165 within tolerance); the two invariant
tests (monthly = fiscal annual; fiscal-year coverage) pass. Root-cause
standing after the 2026-07-09 adjudication:

- **C (rollover free rent) — ADJUDICATED, CLOSED (2026-07-09).** Owner
  determination: an accepted, unconfirmable OM inconsistency (likely a
  broker-side pro-forma override or an unrecorded per-tenant renewal
  assumption; unconfirmable without the source Argus file, which is not
  available). The engine's figures stand as the mechanically correct output
  of the OM's own stated MLA terms; neither the engine nor the fixture is to
  be tuned to match the OM's zero. Its misses (Free Rent FY2034/FY2036 and
  their cascade into Scheduled Base, Total PGR, EGR, Management Fee, Total
  OpEx, and NOI) remain in the tables above as accepted deltas, not open
  questions.
- **A (day-count residual, FY2027–FY2030) — OPEN**, awaiting owner per-cell
  adjudication (confirmed to the dollar against ASSUMPTIONS §3's prediction).
- **B (rollover-year recovery timing, FY2031/2034/2036) — OPEN**, awaiting
  owner per-cell adjudication.

Both pre-flagged README open questions clustered exactly where predicted, and
no other divergence exists: the seven non-rollover years miss only by the
day-count residual, and A&T Vacancy, General Vacancy, CAM, Utilities,
Insurance, and Real Estate Taxes (via `annual_overrides`) are clean in all
eleven years. No input was tuned; resolution of A and B is owner adjudication
(NEXT_STEPS_TO_GATE2.md; Clorox README ladder), not undertaken here.
