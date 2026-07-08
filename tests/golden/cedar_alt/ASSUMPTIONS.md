# Cedar Alt Distribution Center — Fixture Assumptions & Audit Trail

Every input in `cedar_alt.icprop.json`, with its OM page cite if stated, or its
derivation if not. All page cites are to
`source/Cedar Alt Distribution Center - Offering Memorandum.pdf` ("OM p. N" =
the printed page number in the page footer). The published cash flow [OM p. 28]
is footnoted **"Cash Flow Projections Based on Argus Enterprise Version
14.0.2"** (text layer, confirmed — see README escalation check 1).

**Fixture-lock status: CONFIRMED — owner-verified and committed 2026-07-08.**
The RET line is resolved via `annual_overrides` (§6; DEVIATIONS.md §12), no
longer an open item.

## 1. Property & analysis period — stated [OM pp. 27, 28, 29]

| Input | Value | Source |
|---|---|---|
| Property | Cedar Alt Distribution Center, Dallas, TX — two industrial buildings | OM pp. 2, 29 |
| — Bldg 1 (Asset #01) | 3486 Cedardale Rd — 1,084,462 SF | OM p. 29 |
| — Bldg 3 (Asset #02) | 9016 Van Horn Dr — 265,758 SF | OM p. 29 |
| Analysis commencement | June 1, 2026 | OM p. 27 |
| Analysis term | 10 years, end May 31, 2036 → `analysis_term_years: 10` | OM p. 27 |
| Fiscal year end | May 31 → `fiscal_year_end_month: 5` | OM p. 28 column headers |
| Rentable square feet | 1,350,220 SF (fixed) | OM pp. 27, 28 [3], 29 |
| Property size | 1,350,220 SF (no separate gross area published — assumed = NRSF) | assumption |
| Vacant at 6/1/26 | 0 SF; 100% leased | OM pp. 27, 29 |
| Property type | industrial (distribution center) | OM p. 5 |

**Published cash flow spans FY2027–FY2037 (11 columns) for a 10-year term:**
FY2027–FY2036 are the ten analysis years; **FY2037 is the resale
look-forward** year (as with Clorox's FY2032). The expected CSV transcribes all
eleven; which years Gate 2 asserts is a Step 7 decision (§13).

## 2. Inflation — stated [OM p. 27]

All growth categories 3.00% on a **calendar-year basis** ("All market rates are
stated on a calendar-year basis" [OM p. 27]): CPI 3.00%, Other Revenue 3.00%,
Operating Expenses 3.00%, Real Estate Taxes 3.00%, and the CY2027–CY2036+
market-rent ladder each 3.00%.

Encoding: `timing_basis: calendar_year`, `inflation_month: 1`, single entry
`{year: 2027, rate: 3.0}` on every index (years before the first entry
contribute 0% — CY2026 amounts are in CY2026 dollars; the last rate carries
forward). **Same June-1/May-31 fiscal structure as Clorox**, so the calendar
basis again sidesteps the engine's open analysis-year mid-year question (Clorox
README ladder).

## 3. Rent roll — stated [OM pp. 29, 30, 35, 36] (lease abstracts govern the cents)

Two single-tenant NNN leases, one per building, both 100% of their building,
together 100% of the property. Base rent is the rate in force at 6/1/26; steps
dated on/before analysis begin are folded into `base_rent`.

### Bldg 1 (Asset #01) — CONFIDENTIAL tenant, 1,084,462 SF [OM pp. 29, 30, 34, 35]

- Original commencement Jan 16, 2026; expiration **May 31, 2033**. NNN.
- Base rent schedule (lease abstract [OM p. 30], exact cents; `dollars_per_month`):

  | Period | Monthly | PSF/yr |
  |---|---|---|
  | 1/16/2026 – 5/30/2027 | $515,119.45 | $5.700 |
  | 6/1/2027 – 5/31/2028 | $533,148.63 | $5.900 |
  | 6/1/2028 – 5/31/2029 | $551,808.83 | $6.106 |
  | 6/1/2029 – 5/31/2030 | $571,122.14 | $6.320 |
  | 6/1/2030 – 5/31/2031 | $591,111.41 | $6.541 |
  | 6/1/2031 – 5/31/2032 | $611,800.31 | $6.770 |
  | 6/1/2032 – 5/31/2033 | $633,213.32 | $7.007 |

  Base rent at 6/1/26 = **$515,119.45/mo** (the $5.70 rate). **Discrepancy
  flagged:** the rent-roll summary [OM p. 29] prints the final step as
  $633,123; the lease abstract [OM p. 30] prints **$633,213.32** — a digit
  transposition in the summary. The fixture uses the abstract's exact cents.
- Notes: Two 5-yr FMV renewal options (→ market rollover at 75%, §4). A 64th-
  month termination option [OM p. 35] is **not** exercised in the OM analysis.

### Bldg 3 (Asset #02) — Crane Worldwide Logistics LLC, 265,758 SF [OM pp. 29, 36, 37]

- Original commencement Mar 15, 2025; expiration **May 31, 2030**. NNN.
- Base rent schedule (lease abstract [OM p. 36], exact cents; `dollars_per_month`):

  | Period | Monthly | PSF/yr |
  |---|---|---|
  | 3/15/2025 – 3/31/2026 | $148,381.55 | $6.700 |
  | 4/1/2026 – 3/31/2027 | $153,585.98 | $6.935 |
  | 4/1/2027 – 3/31/2028 | $158,967.58 | $7.178 |
  | 4/1/2028 – 3/31/2029 | $164,526.35 | $7.429 |
  | 4/1/2029 – 3/31/2030 | $170,284.44 | $7.689 |
  | 4/1/2030 – 5/31/2030 | $176,241.85 | $7.958 |

  Base rent at 6/1/26 = **$153,585.98/mo** (the 4/1/2026–3/31/2027 rate). The
  $148,381.55 opening rate precedes the analysis window. Caps: N/A; MGT Fee
  Cap: N/A [OM p. 37].

**GPR month-count note (for Step 7):** Crane's steps fall on April 1 (mid-
fiscal-year), so each fiscal year blends two rates. Summing the two leases'
stated rents gives FY2027 GPR ≈ $8,035,228 vs the published $8,040,610 (≈
$5,382 / 0.07% low), consistent with ARGUS day-count (actual/365) proration
against the fixture's monthly posting. The inputs are the OM's exact base
rents; the small delta is a timing-convention question for adjudication, not
an input to tune.

## 4. Market leasing profiles — stated [OM p. 27] (two, one per building)

Because the two buildings carry different market rents and TIs, the fixture
uses **two MLPs** with otherwise identical terms:

| Input | Bldg 1 Market NNN | Bldg 3 Market NNN |
|---|---|---|
| 2026 market rent | $5.70 /SF/yr NNN | $7.00 /SF/yr NNN |
| TI new / renewal | $3.00 / $1.50 PSF | $4.00 / $2.00 PSF |
| Retention ratio | 75% | 75% |
| Lease term | 5 years (60 mo) | 5 years (60 mo) |
| Rent adjustment (intra-term) | 3.50% annually → pct steps at mo 12/24/36/48 | same |
| Market-rent growth (to rollover) | 3.00% (§2) | 3.00% |
| Downtime | 10 mo new (weighted 0.25×10 = 2.5 → engine rounds 3; OM prints WA 3) | same |
| Free rent | 3.0 mo new / 1.0 renewal, base-rent-only (WA 0.75×1+0.25×3 = 1.5 ✓) | same |
| LC new / renewal | 6.75% / 6.75% | 6.75% / 6.75% |
| Renewal market rent | one rate printed → renewal = 100% of new | same |

Both leases carry `upon_expiration: market` (FMV renewal options roll to these
assumptions at 75% retention, per the rent-roll notes and [OM p. 27]). Blended
TI cross-check: Bldg 1 WA = 0.75×1.50 + 0.25×3.00 = $1.875; Bldg 3 WA =
0.75×2.00 + 0.25×4.00 = $2.50 (OM prints TI "Weighted Average Varies" because
the two profiles differ).

## 5. Recoveries — NNN net [OM pp. 27, 29]

"Expense Recovery Type NNN" [OM p. 27]; both leases "NNN" on the rent roll
[OM p. 29]. Encoded as the system `{method: net}` for both — each tenant
recovers 100% of operating expenses pro-rata (its building = its share; the two
together = the whole property). No base-year stops, no gross-up (single-tenant
NNN industrial).

**Cross-check confirming rollover recovery behavior:** Expense Recoveries =
Total Operating Expenses **exactly** in every fully-occupied year (FY2027–30,
FY2032–33, FY2035, FY2037), and falls **below** it in the three rollover years
(FY2031 by $203,737; FY2034 by $391,354; FY2036 by $236,187) — vacant space
stops recovering during downtime. This is the signature of the deal's rollover
and is a positive validation target, not a discrepancy.

The **8% cumulative-compounding OpEx cap on Bldg 1** (excluding WAGES, SNOW,
UTIL, MGT, INS, RET [OM p. 29]) is **not modeled**: controllable expenses grow
3%/yr, never approaching an 8% cumulative-compounding ceiling, so the cap never
binds. Bldg 1's **2.5%-of-gross-revenues management-fee cap** [OM pp. 29, 30]
equals the modeled 2.5% fee, so it is also non-binding. Both flagged (§11).

## 6. Operating expenses — five lines [OM p. 28], CY2026 back-solved from FY2027

"Operating Expense Source: 2025 Actuals Grown 3%" [OM p. 27]; the CY2026
budget is not itemized. With calendar-year 3% stepping in January and a
June–May fiscal year:

**FY2027 = CY2026 × (7 + 5 × 1.03) / 12 = CY2026 × 1.0125**

(7 months Jun–Dec 2026 at CY2026 + 5 months Jan–May 2027 at CY2027; same
fiscal factor as Clorox.) Every fiscal year then grows exactly 3% over the
prior (any 12-month window over a uniformly-3% calendar series does).

**Clean lines** (back-solve verified: derived base × fiscal factor reproduces
all 11 published years within ≤ $0.71):

| Expense | Published FY2027 | Derived CY2026 base | Worst residual |
|---|---|---|---|
| Common Area Maintenance | $553,489 | **$546,655.80** | $0.69 |
| Utilities | $115,685 | **$114,256.79** | $0.70 |
| Insurance | $197,208 | **$194,773.33** | $0.71 |

- **Management Fee**: 2.50% of EGR [OM p. 27] → `pct_of_egr` (FY2027: 2.5% ×
  $10,379,556 = $259,488.9 → published $259,489 ✓). A recoverable %-of-EGR
  fixed point, as in Clorox/Freeport.
- **Capital Reserves**: $0.10 PSF (CY2026) grown 3% [OM p. 27] → capital
  expense, `$0.10/SF/yr` on the expense index (0.10 × 1,350,220 × 1.0125 =
  $136,709.8 → published $136,710 ✓).

### Real Estate Taxes — gross stated basis + per-year overrides for the abated years

Stated basis [OM p. 27 note 2b]: 2025 total assessed value **$65,271,360** ×
2025 tax rate **2.226710%** (Dallas CAD), growing 3% annually from CY2027.
**CY2026 gross tax = 65,271,360 × 0.0222671 = $1,453,403.90** — the RET line's
base `amount`, `dollars_per_year` on the expense index. This gross basis
reproduces the **unabated FY2037 to the penny** (engine-computed $1,977,669 vs
published $1,977,669) — confirming the assessed-value × rate × 3% basis is
exactly right for the year with no abatement.

The OM applies a **Bldg-1 city-tax abatement** [OM p. 27 note 2b] ("through
February 2036, of city taxes (tax rate of 0.6988%) on 90% of the increased
improvement value over the 2016 base year improvement value of $1,000,000"),
which the gross basis does not reflect. That abatement **cannot be computed
from the stated inputs**: the Bldg-1 improvement value (needed for 0.6988% ×
90% × (IV − $1M)) is never given, and reverse-solving it from the published RET
implies ≈5–6%/yr growth — inconsistent with the stated 3%, so no faithful
single-input reconstruction exists.

Rather than invent the improvement value, the fixture uses the **`annual_overrides`
escape hatch** (DEVIATIONS.md §12): FY2027–FY2036 take the **OM's own published
fiscal RET figures** [OM p. 28] directly (the same numbers in
`expected_annual_cash_flow.csv`), and **FY2037 falls through to the gross
formula** above (already exact). Encoded on the Real Estate Taxes expense as

```
"annual_overrides": [ {"year": 2027, "amount": 1213076}, {"year": 2028, "amount": 1244117},
                      … {"year": 2036, "amount": 1630558} ]   # FY2037 omitted -> formula
```

(`year` is the fiscal-year label; each posts amount/12 per month, and the
June–May fiscal aggregation returns the figure exactly.) **Verified
end-to-end through the engine:** the computed fiscal RET line now equals the
published figure to the penny for every overridden year — e.g. FY2027
−$1,213,076.00 and FY2036 −$1,630,558.00, both exact (before the override, the
gross basis gave −$1,471,571 and −$1,920,067). This **resolves the RET line
directly from the OM's published figures**; it is no longer an open modeling
gap. What remains for Step 7 is only the ordinary rollover-year recovery timing
(FY2031/2034/2036), where recoveries drop below OpEx during downtime — a
machinery question, not a RET question.

The published RET figures used as overrides (ledger sign positive here; the
CSV/ledger carry them negative):

| FY | 2027 | 2028 | 2029 | 2030 | 2031 | 2032 | 2033 | 2034 | 2035 | 2036 | 2037 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| RET | 1,213,076 | 1,244,117 | 1,275,522 | 1,298,724 | 1,327,915 | 1,357,384 | 1,387,112 | 1,417,058 | 1,447,193 | 1,630,558 | *formula* |

(FY2037 = gross formula = $1,977,669, unabated.) **This is a transcription of
the OM's own published RET, not a derivation** — the abatement mechanics stay
opaque, but the fixture reproduces the deal's actual tax line without inventing
the improvement value. If the owner later obtains the Bldg-1 improvement value
or the abatement schedule, RET can be re-modeled from first principles; until
then the published figures are authoritative for these years.

## 7. Miscellaneous / property revenues — none

The published cash flow [OM p. 28] has no parking / other-income lines: Total
Gross Revenue = Scheduled Base Rent + Expense Recoveries only. None encoded.

## 8. Vacancy — none general; rollover downtime only [OM p. 27]

- **General Vacancy Loss: None** [OM p. 27 note 1] ("General Vacancy Loss
  factor includes losses attributable to projected lease-up or rollover
  downtime" — i.e., the only vacancy modeled is the physical rollover
  downtime, which the MLP machinery produces directly). No `general_vacancy`
  block. The published General Vacancy Loss line is $0 every year, matching.
- **No static vacancy** (property is 100% leased, no available suites).
- Credit loss: none stated.

## 9. Absorption — none (no currently-vacant space) [OM p. 27]

"Currently Vacant as of 6/1/26: 0 SF" [OM p. 27] — no `AbsorptionSpec`. All
vacancy in the projection is rollover turnover produced by the two leases'
`upon_expiration: market` chains (Crane FY2031, Bldg 1 FY2034, Crane-2 FY2036;
§12), not lease-up of day-one vacant space.

## 10. Schema-encoding flags (approximations avoided; choices disclosed)

1. **RET gross basis + per-year overrides** (§6) — the base amount is OM-cited
   (assessed value × rate × 3%, exact for the unabated FY2037); the abated
   years FY2027–FY2036 use the OM's own published RET via `annual_overrides`
   (DEVIATIONS.md §12), since the Bldg-1 abatement is not computable from the
   stated inputs. Transcribed from the OM, not invented.
2. **Two MLPs** (one per building) because market rent and TI differ by
   building; all other rollover terms identical (§4).
3. **Downtime rounding**: weighted 0.25 × 10 = 2.5 months → engine
   `round_to_months` gives 3; OM prints WA "3 Month(s)" [OM p. 27]. A Phase 2
   adjudication point, as in Clorox.
4. **Renewal options** (two 5-yr FMV per lease) have no contract-option
   encoding; the OM itself models market rollover at 75% retention, which the
   fixture follows (`upon_expiration: market`).
5. **Base rent as exact `dollars_per_month`** from the lease abstracts (not
   PSF or percent steps), matching Clorox's treatment; pre-analysis steps are
   folded into `base_rent`.
6. **Capital section**: only Capital Reserves ($0.10 PSF) is a modeled input;
   TI/LC on rollover come from the MLPs (posted in Phase 3). The published
   TI/LC and their capital totals are transcribed in the CSV for Gate 3.

## 11. Stated in the OM but NOT modeled in this draft (owner QA decisions)

| Item | Where stated | Why deferred |
|---|---|---|
| Bldg-1 city-tax abatement *mechanics* (through Feb 2036) | OM p. 27 note 2b | Improvement value unstated; implied abatement inconsistent with 3% growth (§6). The abatement's effect on the RET line is captured via `annual_overrides` (published figures used directly); only the underlying formula/improvement value stays opaque. |
| 8% cumulative-compounding OpEx cap (Bldg 1) | OM p. 29 | Controllable expenses grow 3% « 8% cumulative — non-binding. |
| 2.5%-of-gross-revenue MGT fee cap (Bldg 1) | OM pp. 29, 30 | Equals the modeled 2.5% fee — non-binding. |
| Bldg-1 64-month termination option | OM p. 35 | Not exercised in the OM's own analysis. |
| Texas Margin Tax | OM p. 27 note 2c | OM explicitly excludes it ("Analysis does not factor in the Texas Margin Tax"). |
| Renewal options at FMV | OM pp. 34, 36 | The OM rolls them to market (§4). |

## 12. Published statistics rows [OM p. 28] — reference only, not asserted

| Row | FY27 | FY28 | FY29 | FY30 | FY31 | FY32 | FY33 | FY34 | FY35 | FY36 | FY37 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Physical Occupancy | 100% | 100% | 100% | 100% | 95.08% | 100% | 100% | 79.92% | 100% | 95.08% | 100% |
| Lease SF Expiring (initial) | 0 | 0 | 0 | 265,758 | 0 | 0 | 1,084,462 | 0 | 0 | 0 | 0 |
| WA Market Rent | $6.03 | $6.21 | $6.40 | $6.59 | $6.79 | $6.99 | $7.20 | $7.42 | $7.64 | $7.87 | $8.10 |
| WA In-Place Rent | $5.96 | $6.16 | $6.38 | $6.60 | $6.54 | $7.03 | $7.27 | $7.42 | $7.54 | $7.70 | $8.02 |

Rollover reading: Crane (265,758 SF) expires end-FY2030 → downtime/vacancy in
FY2031 (A&T −523,448, free rent −261,724). Bldg 1 (1,084,462 SF) expires
end-FY2033 → FY2034 (A&T −1,900,596, TI −2,500,784, LC −2,751,808). Crane's
first speculative renewal then expires ≈ FY2036 (A&T −606,819). These drive the
rollover recovery gaps in §5.

## 13. Gate phasing

Gate 2 scope is the **revenue/vacancy/expense/NOI lines**; TI/LC/capital lines
wait for Gate 3 (as with Clorox and Freeport). The expected CSV transcribes all
11 published fiscal years. Which years Gate 2 asserts is a Step 7 decision with
the owner. With the RET line now resolved via `annual_overrides` (§6), the
remaining Step-7 question is the ordinary rollover-year recovery timing
(FY2031/2034/2036), where recoveries drop below OpEx during downtime —
absorption + recovery-gap machinery, not a RET question. The fully-occupied
years are expected within tolerance across the revenue/expense lines.
