# Discrepancy Log — 8505 Freeport Parkway (golden #2)

Engine vs `expected_annual_cash_flow.csv` (the OM's published Argus cash flow,
owner-verified 2026-07-08), tolerance **$500/line/fiscal-year** (spec §9.1),
scope FY2027–FY2037 revenue/vacancy/expense/NOI lines (Gate 2) plus, from
2026-07-11, the capital lines in their own test function (Gate 3 Step 1 —
root cause E below). Produced by `tests/golden/test_freeport.py`.

**These misses are logged for owner per-cell adjudication (CLAUDE.md
Golden-File Strategy). Claude does not resolve them and did not tune
`freeport.icprop.json` to reduce them, beyond the one structural fix noted
below.** Only Topper recomputes disputed cells independently from the source OM.

## Update 2026-07-08 — MLP "BY + Util" recovery structure landed

The MLP recovery assignments (previously the system `base_year` method over
*all* expenses) were replaced with a two-pool user structure — **OpEx on a
lease-start-relative base year + Electricity net (from dollar one)** — matching
the OM's stated "BY + Util (95% GU)" structure, using the new
`BaseYearSpec.lease_start_relative` schema field (DEVIATIONS.md §10, closing the
gap named in ASSUMPTIONS §5). **This is a structural correctness fix, not input
tuning.** Effect on the comparison:

- **Total misses 144 → 137** (105 of 242 in-scope cells now within $500, was 98).
- **Expense Recovery Revenue** rollover years closed most of the way — FY2031
  −$218,545 → −$24,895; FY2036 −$274,403 → −$6,542; FY2037 −$286,868 → +$6,718.
- **Margin Tax** dropped from 11 misses to **3** (FY2030–FY2037 now within
  tolerance as EGR moved closer).
- **The MLP electricity-split gap is closed;** the *residual* recovery gap is
  now concentrated in the early years (FY2027–FY2029), a **different** cause
  (root cause A1 below): contract tenants' pre-analysis base years falling back
  to analysis year 1 (DEVIATIONS.md §10), which this fix does not address and
  the OM's data cannot close.

## Summary

**105 of 242 in-scope line-years within $500; 137 miss.** Root causes:

| # | Root cause | Primary lines | Status |
|---|---|---|---|
| A1 | Contract tenants' pre-analysis base years fall back to analysis year 1 (the OM uses actual historical low bases) — residual recovery gap, early years | Expense Recovery Revenue FY2027–FY2029 | Open — DEVIATIONS.md §10; OM does not publish historical stops |
| A2 | MLP "BY + Util" electricity gap | Expense Recovery Revenue rollover years | **CLOSED** 2026-07-08 (this update) |
| B | General-vacancy basis undetermined from annual data (now on a larger PGR base, so slightly wider) | General Vacancy | Open — ASSUMPTIONS §8 |
| C | Gross-up-to-market presentation on two offsetting lines | Base Rental Revenue, A&T Vacancy | Open — DEVIATIONS.md §8 (nets out in Scheduled Base) |
| D | Variable-expense occupancy scaling (30%-fixed lines) | Electricity, Janitorial, Utilities | Open — ASSUMPTIONS §6 |
| — | Arithmetic cascade of A+B+D | Total PGR, EGR, Management Fees, Total Operating Expenses, NOI | consequence |

**Lines within $500 across all 11 fiscal years:** Free Rent; the three
property-revenue lines (Parking+Other+Pylon); and the fully-fixed operating
expenses — Personnel Expenses, Trash Removal, Supplies/R&M/Contract Services,
Administrative Expenses, Insurance, and Real Estate Tax.

---

## Root cause A — Expense Recovery Revenue (residual after the MLP fix)

The electricity split is now correct for speculative segments (recovered net
from dollar one), so the rollover years FY2031–FY2037 are within ~$7K–$25K. The
**residual** is A1: FY2027–FY2029, where most tenants are still on their
in-place contract term with a stated pre-analysis base year (2017–2025) that the
engine can only resolve to analysis year 1 (no pre-analysis ledger data;
DEVIATIONS.md §10). The OM recovers over the tenants' actual low historical
bases; the engine's analysis-year-1 stop leaves less to recover. The OM does not
publish those historical stops, so this cannot be closed without the seller's
Argus file or per-tenant operating history (the `known_amount` override exists
for exactly that, unpopulated here).

### Owner adjudication (2026-07-10) — A1 closed

This residual was already decided by the **standing 2026-07-07 owner directive
recorded in ASSUMPTIONS.md §5**: every tenant carries its true stated base
year, **no fabricated base-year stop** is permitted, and the `known_amount`
override was **deliberately left unpopulated because no real historical figure
exists past 2020**. The gap is therefore unclosable without the seller's
actual Argus file (or per-tenant operating history), which is not available.
The engine's analysis-year-1 fallback is the manual-cited behavior
[AE pp. 377, 408] applied to inputs that honestly lack pre-analysis data. Its
misses (Expense Recovery Revenue FY2027–FY2029 and the residual tail, plus
their cascade) remain in the tables as accepted deltas. **Root cause A1 is
adjudicated — accepted, closed.**

### Expense Recovery Revenue — 11 misses (rollover years near tolerance; early years residual A1)
| FY | engine | published | delta |
|---|--:|--:|--:|
| 2027 | 259,079 | 410,783 | -151,704 |
| 2028 | 269,766 | 419,868 | -150,102 |
| 2029 | 309,648 | 442,041 | -132,393 |
| 2030 | 335,249 | 422,814 | -87,565 |
| 2031 | 356,093 | 380,988 | -24,895 |
| 2032 | 415,558 | 436,880 | -21,322 |
| 2033 | 429,153 | 448,132 | -18,979 |
| 2034 | 443,657 | 465,395 | -21,738 |
| 2035 | 471,215 | 492,643 | -21,428 |
| 2036 | 343,954 | 350,496 | -6,542 |
| 2037 | 431,061 | 424,343 | +6,718 |

---

## Root cause B — General Vacancy basis undetermined (ASSUMPTIONS §8)

Unchanged in nature; the deltas widened slightly because the fix raised PGR
(more recoveries) and the engine's `percent_of_pgr` vacancy is a percentage of
that larger base. Basis still an owner adjudication.

### General Vacancy — 11 misses
| FY | engine | published | delta |
|---|--:|--:|--:|
| 2027 | -60,175 | -40,747 | -19,428 |
| 2028 | -19,829 | -11 | -19,818 |
| 2029 | -80,732 | -37,968 | -42,764 |
| 2030 | -61,651 | -23,342 | -38,309 |
| 2031 | -136,283 | -67,721 | -68,562 |
| 2032 | -152,362 | -70,223 | -82,139 |
| 2033 | -118,319 | -46,996 | -71,323 |
| 2034 | -91,022 | -41,919 | -49,103 |
| 2035 | -148,700 | -68,308 | -80,392 |
| 2036 | -26,818 | -10,478 | -16,340 |
| 2037 | -184,513 | -88,329 | -96,184 |

---

## Root cause C — Base Rental Revenue / A&T Vacancy: offsetting gross-up (DEVIATIONS.md §8)

Unchanged by the recovery fix. The two lines miss by near-equal-and-opposite
amounts and net to the small Scheduled Base Rental Revenue residual (within
tolerance FY2027–FY2028; $1.2K–$5.7K FY2029–FY2037).

### Owner adjudication (2026-07-10) — C closed

The gross-up-to-market presentation is the **deliberate, manual-cited
convention recorded in DEVIATIONS.md §8** [AE p. 538]: vacant/downtime space
posts its market value to Base Rental Revenue with the offsetting Absorption
& Turnover Vacancy entry, and the §8 correction was **confirmed by test that
Scheduled/EGR/NOI are unaffected regardless of presentation** — the two big
gross-line deltas are two views of the same figure, not an economic
disagreement. The remaining Scheduled Base residual ($1.2K–$5.7K in
FY2029–FY2037) is a month-by-month market-rent timing nuance that annual OM
data cannot discriminate. Its misses remain in the tables as accepted deltas.
**Root cause C is adjudicated — correct as designed, closed.**

### Base Rental Revenue — 11 misses
| FY | engine | published | delta |
|---|--:|--:|--:|
| 2027 | 2,687,341 | 2,714,878 | -27,537 |
| 2028 | 2,740,027 | 2,815,095 | -75,068 |
| 2029 | 2,854,760 | 2,932,149 | -77,389 |
| 2030 | 2,992,443 | 3,071,407 | -78,964 |
| 2031 | 3,209,668 | 3,291,134 | -81,466 |
| 2032 | 3,314,721 | 3,398,241 | -83,520 |
| 2033 | 3,443,297 | 3,528,925 | -85,628 |
| 2034 | 3,543,606 | 3,630,629 | -87,023 |
| 2035 | 3,647,047 | 3,735,947 | -88,900 |
| 2036 | 3,844,406 | 3,929,714 | -85,308 |
| 2037 | 3,945,243 | 4,038,705 | -93,462 |

### Absorption & Turnover Vacancy — 11 misses (the offset to Base Rental Revenue)
| FY | engine | published | delta |
|---|--:|--:|--:|
| 2027 | -84,081 | -111,138 | +27,057 |
| 2028 | -182,043 | -257,139 | +75,096 |
| 2029 | -117,320 | -189,171 | +71,851 |
| 2030 | -159,017 | -239,203 | +80,186 |
| 2031 | -95,560 | -178,635 | +83,075 |
| 2032 | -32,920 | -118,487 | +85,567 |
| 2033 | -80,174 | -168,308 | +88,134 |
| 2034 | -141,209 | -224,387 | +83,178 |
| 2035 | -56,405 | -149,906 | +93,501 |
| 2036 | -551,275 | -641,738 | +90,463 |
| 2037 | -24,030 | -123,226 | +99,196 |

### Scheduled Base Rental Revenue — 9 misses (residual of C; FY2027-28 within tolerance)
| FY | engine | published | delta |
|---|--:|--:|--:|
| 2029 | 2,500,596 | 2,506,134 | -5,538 |
| 2030 | 2,550,662 | 2,549,441 | +1,221 |
| 2031 | 2,760,427 | 2,758,819 | +1,608 |
| 2032 | 3,218,692 | 3,216,646 | +2,046 |
| 2033 | 3,190,026 | 3,187,520 | +2,506 |
| 2034 | 3,207,521 | 3,211,367 | -3,846 |
| 2035 | 3,394,607 | 3,390,006 | +4,601 |
| 2036 | 2,625,365 | 2,620,210 | +5,155 |
| 2037 | 3,671,168 | 3,665,434 | +5,734 |

---

## Root cause D — Variable-expense occupancy scaling (ASSUMPTIONS §6)

Unchanged by the recovery fix.

### Owner adjudication (2026-07-10) — D closed

**Engine verification first (2026-07-10):** the variable-expense projection is
monthly-correct. `project_expense` evaluates each active month individually,
scaling the variable portion by that month's actual occupancy —
`scale = fixed + (1 − fixed) × occupancy[period]`
(`engine/calc/expenses.py:116`; `_occupancy_at` reads the specific month's
value at expenses.py:66-69), where run.py supplies the monthly
`occupancy_series(occupied_area_from_chains(…), rentable)` (run.py:224-226,
300). No annual-average or other non-monthly approximation exists in the path.
The residual is therefore **purely the CY2026 input-derivation limitation
recorded in ASSUMPTIONS.md §6**: JLL's real monthly budget is not published,
so the CY2026 bases for the three 30%-fixed lines were necessarily back-solved
from a single annual occupancy average (the published FY2027 96.3%), and
ASSUMPTIONS §6 already anticipated the outcome — "Owner QA may substitute
actual budget figures; otherwise the published lines adjudicate." Its misses
(Electricity/Janitorial/Utilities, hundreds to ~$10.6K) remain in the tables
as accepted deltas. **Root cause D is adjudicated — accepted, closed.**

### Electricity — 11 misses
| FY | engine | published | delta |
|---|--:|--:|--:|
| 2027 | -247,154 | -246,286 | -868 |
| 2028 | -247,129 | -245,540 | -1,589 |
| 2029 | -258,483 | -257,079 | -1,404 |
| 2030 | -268,794 | -262,173 | -6,621 |
| 2031 | -277,858 | -274,036 | -3,822 |
| 2032 | -287,160 | -286,124 | -1,036 |
| 2033 | -295,175 | -292,309 | -2,866 |
| 2034 | -303,192 | -297,724 | -5,468 |
| 2035 | -313,486 | -311,449 | -2,037 |
| 2036 | -302,638 | -292,029 | -10,609 |
| 2037 | -333,106 | -332,530 | -576 |

### Janitorial — 10 misses (FY2037 within tolerance: −$402)
| FY | engine | published | delta |
|---|--:|--:|--:|
| 2027 | -172,369 | -171,764 | -605 |
| 2028 | -172,352 | -171,244 | -1,108 |
| 2029 | -180,270 | -179,291 | -979 |
| 2030 | -187,462 | -182,844 | -4,618 |
| 2031 | -193,783 | -191,118 | -2,665 |
| 2032 | -200,270 | -199,548 | -722 |
| 2033 | -205,860 | -203,861 | -1,999 |
| 2034 | -211,451 | -207,638 | -3,813 |
| 2035 | -218,630 | -217,210 | -1,420 |
| 2036 | -211,065 | -203,666 | -7,399 |

### Utilities — 5 misses (other 6 years within tolerance)
| FY | engine | published | delta |
|---|--:|--:|--:|
| 2030 | -48,864 | -47,660 | -1,204 |
| 2031 | -50,511 | -49,817 | -694 |
| 2033 | -53,659 | -53,138 | -521 |
| 2034 | -55,117 | -54,123 | -994 |
| 2036 | -55,016 | -53,087 | -1,929 |

---

## Arithmetic cascade of A + B + C + D (not independent findings)

- **Total Potential Gross Revenue** carries the residual recovery gap: −$152K
  (FY2027) shrinking to −$1.4K (FY2036), +$12.5K (FY2037).
- **Effective Gross Revenue** = Total PGR + General Vacancy: carries A1 + B.
- **Management Fees** (3% of EGR): now +$0.5K to +$5.4K (much closer than before
  the fix); FY2036 +$532 just over tolerance.
- **Margin Tax** (0.331% of EGR): only **3 misses** now (FY2027–FY2029), the
  rest within tolerance.
- **Total Operating Expenses**: small, −$19.3K to +$4.1K.
- **Net Operating Income**: carries the EGR gap net of the OpEx offset,
  −$37K to −$177K.

### Total Potential Gross Revenue — 11 misses
| FY | engine | published | delta |
|---|--:|--:|--:|
| 2027 | 2,801,052 | 2,953,237 | -152,185 |
| 2028 | 2,745,393 | 2,895,467 | -150,074 |
| 2029 | 2,845,457 | 2,983,387 | -137,930 |
| 2030 | 2,922,179 | 3,008,522 | -86,343 |
| 2031 | 3,153,877 | 3,177,164 | -23,287 |
| 2032 | 3,672,728 | 3,692,003 | -19,275 |
| 2033 | 3,658,810 | 3,675,283 | -16,473 |
| 2034 | 3,691,999 | 3,717,582 | -25,583 |
| 2035 | 3,907,867 | 3,924,693 | -16,826 |
| 2036 | 3,012,626 | 3,014,012 | -1,386 |
| 2037 | 4,146,835 | 4,134,382 | +12,453 |

### Effective Gross Revenue — 11 misses
| FY | engine | published | delta |
|---|--:|--:|--:|
| 2027 | 2,740,877 | 2,912,490 | -171,613 |
| 2028 | 2,725,564 | 2,895,456 | -169,892 |
| 2029 | 2,764,725 | 2,945,419 | -180,694 |
| 2030 | 2,860,528 | 2,985,180 | -124,652 |
| 2031 | 3,017,594 | 3,109,443 | -91,849 |
| 2032 | 3,520,366 | 3,621,780 | -101,414 |
| 2033 | 3,540,491 | 3,628,288 | -87,797 |
| 2034 | 3,600,977 | 3,675,663 | -74,686 |
| 2035 | 3,759,167 | 3,856,385 | -97,218 |
| 2036 | 2,985,808 | 3,003,534 | -17,726 |
| 2037 | 3,962,322 | 4,046,053 | -83,731 |

### Management Fees — 11 misses (FY2036 +$532, the rest +$2.2K–$5.4K)
| FY | engine | published | delta |
|---|--:|--:|--:|
| 2027 | -82,226 | -87,375 | +5,149 |
| 2028 | -81,767 | -86,864 | +5,097 |
| 2029 | -82,942 | -88,363 | +5,421 |
| 2030 | -85,816 | -89,555 | +3,739 |
| 2031 | -90,528 | -93,283 | +2,755 |
| 2032 | -105,611 | -108,653 | +3,042 |
| 2033 | -106,215 | -108,849 | +2,634 |
| 2034 | -108,029 | -110,270 | +2,241 |
| 2035 | -112,775 | -115,692 | +2,917 |
| 2036 | -89,574 | -90,106 | +532 |
| 2037 | -118,870 | -121,382 | +2,512 |

### Margin Tax — 3 misses (FY2030–FY2037 now within tolerance)
| FY | engine | published | delta |
|---|--:|--:|--:|
| 2027 | -9,072 | -9,640 | +568 |
| 2028 | -9,022 | -9,584 | +562 |
| 2029 | -9,151 | -9,749 | +598 |

### Total Operating Expenses — 11 misses
| FY | engine | published | delta |
|---|--:|--:|--:|
| 2027 | -1,555,204 | -1,559,289 | +4,085 |
| 2028 | -1,584,632 | -1,587,304 | +2,672 |
| 2029 | -1,638,155 | -1,641,534 | +3,379 |
| 2030 | -1,692,533 | -1,684,241 | -8,292 |
| 2031 | -1,747,561 | -1,743,439 | -4,122 |
| 2032 | -1,815,536 | -1,816,966 | +1,430 |
| 2033 | -1,866,028 | -1,863,565 | -2,463 |
| 2034 | -1,918,910 | -1,911,122 | -7,788 |
| 2035 | -1,980,400 | -1,979,810 | -590 |
| 2036 | -1,972,236 | -1,952,888 | -19,348 |
| 2037 | -2,101,140 | -2,102,847 | +1,707 |

### Net Operating Income — 11 misses
| FY | engine | published | delta |
|---|--:|--:|--:|
| 2027 | 1,185,672 | 1,353,201 | -167,529 |
| 2028 | 1,140,932 | 1,308,152 | -167,220 |
| 2029 | 1,126,570 | 1,303,885 | -177,315 |
| 2030 | 1,167,995 | 1,300,939 | -132,944 |
| 2031 | 1,270,033 | 1,366,004 | -95,971 |
| 2032 | 1,704,830 | 1,804,814 | -99,984 |
| 2033 | 1,674,464 | 1,764,723 | -90,259 |
| 2034 | 1,682,067 | 1,764,541 | -82,474 |
| 2035 | 1,778,767 | 1,876,576 | -97,809 |
| 2036 | 1,013,572 | 1,050,645 | -37,073 |
| 2037 | 1,861,182 | 1,943,206 | -82,024 |

---

## Root cause E — Leasing Commissions understated by a stable ~17% (Gate 3 capital lines, activated 2026-07-11)

Phase 3 Step 1 activated the capital-section assertion
(`test_gate3_capital_lines_within_tolerance`, its own test function —
33 line-years beyond tolerance, separate from the Gate 2 count above).
What passes is as informative as what misses:

- **Tenant Improvements: clean in all 11 years** — the §4.2 blend
  (75% × $10 renew + 25% × $20 new) inflated to each segment's start on
  the market index matches the OM within $500 everywhere, the same
  formula golden #1 validated to the dollar.
- **Capital Expenditures and Capital Reserves: clean in all 11 years.**
- **Leasing Commissions: 11 misses, engine below the OM by a strikingly
  stable multiplicative factor** — OM/engine = 1.201–1.212 with no trend
  across the years (e.g. FY2027 1.2035, FY2032 1.2056, FY2037 1.2013). A
  stable ratio on every rollover cohort indicates a **base or rate
  difference, not a timing difference** (timing would move dollars
  between years, not scale all of them equally).

The engine computes the manual's "Fixed %" definition: 6.75% × (blended
term rent incl. steps, less the 5.0 weighted free months) [AE p. 247
"applied to base rent plus fixed steps less free rent"], the exact
formula golden #1 confirmed within $1 at the same 6.75%. Best-evidence
candidates for the OM's larger base, unconfirmable without the seller's
Argus file (owner per-cell adjudication):

1. **LC-category "elements to include" beyond base rent** [AE pp.
   258-262; spec §3.9 `include_escalations`]: an Argus LC category can
   commission base + escalations; Freeport's office leases carry
   substantial base-year recovery income later in term, of roughly the
   observed magnitude. The OM states "6.75%" with no base definition.
2. **No free-rent deduction** (the sibling of Cedar Alt root cause D /
   its C): explains only ≈ ×1.08 of the ×1.205 (5 free months of 65,
   front-loaded at the lowest rent) — insufficient alone.
3. **"% by Lease Year" tiered rates** [AE p. 247] behind the OM's
   single stated 6.75% — not visible anywhere in the OM's text.

No input was tuned; the fixture's 6.75% new/renew is the OM's stated
assumption.

### Owner adjudication (2026-07-12) — E deferred to beta-stage GUI testing

**Owner decision 2026-07-12: root cause E is DEFERRED to beta-stage GUI
testing**, the same disposition as root cause B and Cedar Alt's B.
Owner's stated reason (recorded verbatim): brokers sometimes charge a
reduced leasing commission on renewals — e.g. 3-4% instead of the OM's
stated blended rate — and that isn't detectable from OM text or annual
fiscal-year totals. Vetting it requires inspecting the actual
lease-by-lease/rollover detail against the deal's real files, which
needs the GUI, not something resolvable from the current fixture. Same
evidentiary category as Freeport B: **unconfirmable without tools that
don't exist yet, not an engine defect.** The candidate mechanisms above
(including the owner's side-specific renewal-rate structure) remain the
investigation menu for that stage. The
`test_gate3_capital_lines_within_tolerance` assertion is deliberately
unmodified and stays red, documenting the real open item — no allowlist
mechanism, no input tuning.

### Leasing Commissions — 11 misses
| FY | engine | published | delta | OM/engine |
|---|--:|--:|--:|--:|
| 2027 | -49,799 | -59,933 | +10,134 | 1.2035 |
| 2028 | -152,908 | -184,116 | +31,208 | 1.2041 |
| 2029 | -149,539 | -181,147 | +31,608 | 1.2114 |
| 2030 | -346,193 | -417,318 | +71,125 | 1.2054 |
| 2031 | -208,042 | -252,205 | +44,163 | 1.2123 |
| 2032 | -71,670 | -86,406 | +14,736 | 1.2056 |
| 2033 | -158,948 | -191,438 | +32,490 | 1.2044 |
| 2034 | -160,871 | -194,350 | +33,479 | 1.2081 |
| 2035 | -168,228 | -202,600 | +34,372 | 1.2043 |
| 2036 | -775,186 | -935,635 | +160,449 | 1.2070 |
| 2037 | -52,316 | -62,843 | +10,527 | 1.2013 |

### Total Capital Costs — 11 misses (pure E pass-through; deltas equal LC's to the dollar)
| FY | engine | published | delta |
|---|--:|--:|--:|
| 2027 | -146,269 | -156,403 | +10,134 |
| 2028 | -439,920 | -471,127 | +31,207 |
| 2029 | -1,833,533 | -1,865,141 | +31,608 |
| 2030 | -870,429 | -941,554 | +71,125 |
| 2031 | -534,793 | -578,956 | +44,163 |
| 2032 | -203,516 | -218,252 | +14,736 |
| 2033 | -416,943 | -449,433 | +32,490 |
| 2034 | -422,521 | -455,999 | +33,478 |
| 2035 | -441,360 | -475,732 | +34,372 |
| 2036 | -2,045,889 | -2,206,338 | +160,449 |
| 2037 | -160,994 | -171,521 | +10,527 |

### Cash Flow Before Debt Service — 11 misses (arithmetic pass-through, no independent information)

Per NEXT_STEPS_TO_GATE3.md criterion 1 (owner decision 2026-07-11): CFBDS
= NOI + Total Capital Costs is an exact identity, so each CFBDS delta
below is the **already-adjudicated NOI cascade (root causes A1 + B + C +
D, dominated by deferred-B's general-vacancy basis) plus root cause E's
LC delta** — e.g. FY2027: −167,529 (NOI) + 10,134 (E) = −157,395 ✓. Not
a new engine question.

| FY | engine | published | delta |
|---|--:|--:|--:|
| 2027 | 1,039,403 | 1,196,797 | -157,394 |
| 2028 | 701,013 | 837,025 | -136,012 |
| 2029 | -706,963 | -561,256 | -145,707 |
| 2030 | 297,566 | 359,385 | -61,819 |
| 2031 | 735,240 | 787,048 | -51,808 |
| 2032 | 1,501,314 | 1,586,562 | -85,248 |
| 2033 | 1,257,521 | 1,315,290 | -57,769 |
| 2034 | 1,259,546 | 1,308,542 | -48,996 |
| 2035 | 1,337,407 | 1,400,844 | -63,437 |
| 2036 | -1,032,316 | -1,155,693 | +123,377 |
| 2037 | 1,700,188 | 1,771,685 | -71,497 |

---

## Status

Golden #2 comparison **not reconciled** — `test_freeport.py`'s Gate 2 assertion
fails with the 137 line-years above (down from 144); the two invariant tests
(monthly = fiscal annual; fiscal-year coverage) pass. Root-cause standing
after the 2026-07-10 adjudications:

- **A2 (MLP "BY + Util" electricity split) — CLOSED (2026-07-08)** via the
  lease-start-relative pool structure (DEVIATIONS.md §10).
- **A1 (contract pre-analysis base years) — ADJUDICATED, CLOSED
  (2026-07-10).** Already decided by the standing 2026-07-07 directive
  (ASSUMPTIONS §5): true stated years, no fabricated stops, `known_amount`
  deliberately unpopulated; unclosable without the seller's Argus file.
  Accepted deltas.
- **C (Base/A&T offsetting gross-up) — ADJUDICATED, CLOSED (2026-07-10).**
  Deliberate manual-cited presentation (DEVIATIONS.md §8 [AE p. 538]),
  test-confirmed EGR/NOI-neutral; the small Scheduled Base residual is
  undiscriminable from annual data. Correct as designed.
- **D (variable-expense inputs) — ADJUDICATED, CLOSED (2026-07-10).** Engine
  scaling verified monthly-correct (expenses.py:116 against the monthly
  occupancy series); the residual is the ASSUMPTIONS §6 CY2026 back-solve
  limitation (JLL's monthly budget unpublished). Accepted deltas.
- **B (general-vacancy basis, ASSUMPTIONS §8) — DEFERRED to beta-stage GUI
  testing (owner decision 2026-07-10).** B is a **basis ambiguity**, not a
  timing question: the OM states neither the general-vacancy percentage basis
  nor the A&T offset behavior (ASSUMPTIONS §8), and every `VacancyMethod`
  variant plus the `reduce_by_absorption_turnover` toggle was tried this
  session without a clean match to the published line. The owner defers it to
  beta-stage testing once the GUI exists — faster interactive iteration across
  assumption combinations than editing JSON and rerunning pytest by hand —
  **not because a GUI resolves the ambiguity by itself**. The comparison test
  is deliberately unmodified and stays red, documenting the real open item
  (owner instruction: no new engine/test-infrastructure work).

- **E (Leasing Commissions base, Gate 3 capital lines) — DEFERRED to
  beta-stage GUI testing (owner decision 2026-07-12), alongside B.**
  Owner's reason (verbatim in the adjudication subsection above): brokers
  sometimes charge a reduced leasing commission on renewals — e.g. 3-4%
  instead of the OM's stated blended rate — undetectable from OM text or
  annual fiscal-year totals; vetting it requires inspecting the actual
  lease-by-lease/rollover detail against the deal's real files, which
  needs the GUI. Same evidentiary category as B: unconfirmable without
  tools that don't exist yet, not an engine defect. The
  `test_gate3_capital_lines_within_tolerance` assertion is deliberately
  unmodified and stays red with its 33 line-years: 11 LC (the stable
  ~×1.205 base/rate difference; candidates above), 11 Total Capital
  Costs (pure LC pass-through), 11 CFBDS (adjudicated-NOI cascade + LC,
  per criterion 1's supersession — no independent information). TI,
  Capital Expenditures, and Capital Reserves are clean in all 11 years.

All 137 Gate 2 misses trace to closed/accepted causes plus deferred-B and
their cascade; the Gate 3 capital assertion's 33 misses trace to
deferred-E (plus the adjudicated NOI cascade inside CFBDS). No input was
tuned to reduce them; nothing in this log alters the fixture or the
engine.
