# Clorox Northlake — Fixture Assumptions & Audit Trail

Every input in `clorox_northlake.icprop.json`, with its OM page cite if stated,
or its derivation if not. All page cites are to
`source/Clorox Distribution Center - Offering Memorandum.pdf` ("OM p. N" =
the printed page number, which equals the PDF page number in this document).
The published cash flow [OM p. 26] is footnoted "Cash Flow Projections Based
on Argus Enterprise Version 14.0.2.475".

**Fixture-lock status: DRAFT — awaiting owner QA against the source pages.
No engine comparison may run before owner verification and commit.**

## 1. Property & analysis period — stated [OM p. 25]

| Input | Value | Source |
|---|---|---|
| Analysis commencement | June 1, 2026 | OM p. 25 |
| Analysis end | May 31, 2031 (5-year term) | OM p. 25 |
| Fiscal year end | May 31 → `fiscal_year_end_month: 5` | OM p. 26 column headers |
| Rentable square feet | 540,000 SF (fixed) | OM p. 25 |
| Property size | 540,000 SF (no separate gross area published — assumed = NRSF) | assumption |
| Vacant at 6/1/26 | 0 SF; no absorption | OM p. 25 |
| General vacancy loss | None | OM p. 25 note [1] |
| Location | Northlake, TX (Denton CAD) | OM p. 25 note [2]b |

## 2. Inflation — stated [OM p. 25]

All growth categories (CPI, other revenue, operating expenses, real estate
taxes, market rent) are 3.00%. "All market rates are stated on a
calendar-year basis" [OM p. 25 notes], and the market rent table steps by
calendar year (CY2027 $7.36 … CY2032+ $8.54).

Encoding: `timing_basis: calendar_year`, `inflation_month: 1` (January
steps), single schedule entry `{year: 2027, rate: 3.0}` per index — years
before the first entry contribute 0% (CY2026 amounts are stated in CY2026
dollars), and the last rate carries forward (matches "CY2032+ 3.00%").

Verification: $7.15 × 1.03^n reproduces the OM's printed market rent ladder
exactly — 7.3645→$7.36, 7.5854→$7.59, 7.8130→$7.81, 8.0474→$8.05,
8.2888→$8.29, 8.5375→$8.54 [OM p. 25].

**This deal's calendar-year basis sidesteps the engine's open analysis-year
mid-year question** (see README adjudication ladder).

## 3. The Clorox lease — stated [OM pp. 27-28]

| Input | Value | Source |
|---|---|---|
| Tenant | The Clorox Sales Company (Guarantor: The Clorox Company) | OM pp. 27-28 |
| Suite / area | 100 / 540,000 SF (100%) | OM p. 27 |
| Original commencement | February 26, 2005 | OM p. 28 lease abstract |
| Expiration | August 31, 2028 | OM pp. 27-28 |
| Recovery type | NNN (net; tenant pays pro-rata share of CAM incl. utilities and management fee, insurance, taxes) | OM pp. 27, 28-29 |
| Renewal options | Two 5-year options at FMV — not separately modeled; the OM models expiration at market with 75% retention [OM p. 25], and the fixture follows the OM | OM p. 27 |
| Management fee cap | "MGT may not exceed 3% of property gross rents" (lease says "not to exceed five percent (3%)" — a source-document inconsistency; the OM models 3.0% of EGR, which this fixture follows) | OM pp. 27, 29, 25 |

**Base rent — exact dollar schedule from the lease abstract [OM p. 28]**,
encoded as `dollars_per_month` amounts, not percent steps:

| Period | Monthly | Annual PSF |
|---|---|---|
| 6/1/2026 – 5/31/2027 | $216,359.95 | $4.81 |
| 6/1/2027 – 5/31/2028 | $222,850.74 | $4.95 |
| 6/1/2028 – 8/31/2028 | $229,536.27 | $5.10 |

Pre-analysis steps (6/1/2023 $198,000.00; 6/1/2024 $203,940.00; 6/1/2025
$210,058.20 [OM p. 28]) precede the analysis window and are not encoded;
`base_rent` is the rate in force at analysis begin. The rent roll's rounded
monthly figures ($216,360 / $222,851 / $229,536 [OM p. 27]) are superseded by
the lease abstract's exact cents.

Annual sanity check: $216,359.95 × 12 = $2,596,319.40 → OM prints $2,596,319 ✓.

## 4. Market leasing profile — stated [OM p. 25]

| Input | Value |
|---|---|
| Retention ratio | 75% |
| 2026 market rent | $7.15 PSF NNN |
| Rent adjustment (speculative term) | 3.50% annually → encoded as pct steps at months 12/24/36/48 |
| Speculative lease term | 5 years (60 months) |
| Downtime | 9 months new / 0 renewal (OM prints "Weighted Average 2 Month(s)" — 25% × 9 = 2.25, printed rounded; see §8 flag 5) |
| Free rent | 3.0 months new / none renewal, base rent only ("5FY Duration; BR Only"); WA printed 0.75 |
| TI | $2.00 new / $0.50 renewal (WA printed $0.88) |
| LC | 6.75% new and renewal, base rent only ("BR Only") |
| Renewal market rent | OM states one market rent — renewal encoded as 100% of new |

The OM's printed weighted averages (0.75 free months, $0.88 TI, 2 months
downtime) are blend outputs, not inputs; they cross-check the 75/25 weighting.

## 5. Operating expenses — derived from FY2027 [OM p. 26] per the fiscal back-solve

CY2026 budget amounts are not itemized in the OM (only "CY 2026 Budget" is
named as the source and "UTIL of $0.10 PSF" is stated [OM p. 25 note 2a]).
Bases are back-solved from the published FY2027 column via:

**FY2027 = CY2026 × (7 + 5 × 1.03) / 12 = CY2026 × 1.0125**

(7 months Jun–Dec 2026 at CY2026 level + 5 months Jan–May 2027 at CY2027
level, calendar-year 3% stepping in January.)

| Expense | Published FY2027 | Derived CY2026 base | PSF | Check |
|---|---|---|---|---|
| Utilities | $54,675 | **$54,000.00** = 54,675 / 1.0125 | $0.1000 | verifies the method exactly — matches the stated $0.10 PSF [OM p. 25 note 2a] |
| Common Area Maintenance | $331,574 | **$327,480.49** = 331,574 / 1.0125 | $0.6064 | |
| Insurance | $72,659 | **$71,761.98** = 72,659 / 1.0125 | $0.1329 | |

Forward verification (derived base × fiscal factor vs published), residuals
in dollars — all are sub-dollar rounding:

| FY | CAM resid. | Utilities resid. | Insurance resid. |
|---|---|---|---|
| 2028 | +0.22 | +0.25 | −0.23 |
| 2029 | +0.86 | −0.29 | −0.07 |
| 2030 | +0.86 | −0.15 | +0.45 |
| 2031 | +0.46 | +0.19 | +0.34 |
| 2032 | +0.14 | +0.31 | −0.31 |

**Management fee**: 3.0% of EGR [OM p. 25], encoded as `pct_of_egr`. Note the
published figures make the fee circular-but-consistent: EGR includes expense
recoveries, recoveries include the fee (FY2027: 3% × $3,927,262 = $117,818 ✓,
and recoveries $1,330,943 = the five operating expense lines summed ✓). The
engine's recovery/EGR pass ordering must resolve this fixed point.

## 6. Real estate taxes — derived [OM p. 25 note 2b]; residual recorded, inputs NOT adjusted

Stated basis: 2025 assessed value **$43,182,000** × 2025 tax rate
**1.725038%** (Denton CAD), growing 3% annually beginning CY2027.

**CY2026 base = 43,182,000 × 0.01725038 = $744,905.91** (PSF $1.3795)

Derived vs published, all six fiscal years:

| FY | Derived | Published | Residual |
|---|---|---|---|
| 2027 | 754,217.23 | 754,217 | +0.23 |
| 2028 | 776,843.75 | 776,844 | −0.25 |
| 2029 | 800,149.06 | 800,149 | +0.06 |
| 2030 | 824,153.53 | 824,154 | −0.47 |
| 2031 | 848,878.14 | 848,878 | +0.14 |
| 2032 | 874,344.48 | 874,345 | −0.52 |

The build instruction anticipated a residual of roughly $40/year; the actual
computed residuals are **≤ $0.52/year** (whole-dollar rounding). Recorded
as instructed; inputs were not adjusted to absorb anything. "Real Estate
Taxes Reassessed: No" [OM p. 25] — no reassessment on the FY2029 rollover.

## 7. Capital section

- **Capital reserves**: $0.10 PSF (CY2026 value) growing 3% [OM p. 25],
  encoded as a capital expense, $0.10/SF/yr on the expense index. Derived
  FY2027 $54,675 matches published exactly; later-year residuals ≤ $0.31.
- **Amortized CAM revenue**: tenant contribution for exterior painting,
  **$3,956.91/mo through 12/2027, modeled below the line** [OM p. 25 note 3].
  Encoded as a **negative capital expense** (`-3,956.91 dollars_per_month`,
  date range 6/1/2026–12/31/2027, zero-rate inflation schedule) to reproduce
  the OM's capital-section placement. Check: 12 × 3,956.91 = $47,482.92 → OM
  prints $47,483 (FY2027); 7 × 3,956.91 = $27,698.37 → $27,698 (FY2028) ✓.

## 8. Schema-encoding flags (approximations avoided; choices disclosed)

1. **Below-the-line revenue**: the §3 schema has no capital-section revenue
   account, so Amortized CAM Revenue is a negative capital `ExpenseItem`.
   Same ledger placement, sign conventions identical to the OM.
2. **"No inflation"**: the schema's `InflationRef: null` means *default
   index*, not zero; the flat amortized CAM payment carries an explicit
   zero-rate schedule (`[{year: 2026, rate: 0.0}]`) instead.
3. **LC "BR Only"**: the inline `LCSpec.pct` has no base-rent-only flag (only
   named `LCCategory` has `include_escalations`). Encoded as `pct: 6.75`;
   the engine's default LC base must be base rent only for this to be exact.
4. **Speculative "3.50% annually"** encoded as four anniversary `pct_increase`
   steps (months 12/24/36/48) within the 60-month speculative term.
5. **Downtime rounding**: 25% × 9 months = 2.25 months weighted downtime; the
   OM prints "2 Month(s)" and FY2029 physical occupancy 83.33% (= 2.0 vacant
   months on the full building). Spec §4.2 `round_to_months` matches, but
   this is a Phase 2 adjudication point, not a Gate 1 input.
6. **Renewal options** (two 5-yr FMV) have no contract-option encoding; the
   OM itself models market rollover at 75% retention, which the fixture
   follows.
7. **Historical rent steps** before 6/1/2026 are intentionally not encoded
   (see §3).

## 9. Published statistics rows [OM p. 26] — reference only, not asserted

| Row | FY2027 | FY2028 | FY2029 | FY2030 | FY2031 | FY2032 |
|---|---|---|---|---|---|---|
| Physical occupancy | 100.00% | 100.00% | 83.33% | 100.00% | 100.00% | 100.00% |
| Overall economic occupancy | 100.00% | 100.00% | 81.06% | 100.00% | 100.00% | 100.00% |
| Wtd avg market rent | $7.24 | $7.46 | $7.68 | $7.91 | $8.15 | $8.39 |
| Wtd avg in-place rent | $4.81 | $4.95 | $6.27 | $7.74 | $8.01 | $8.29 |
| Total opex PSF/yr | $2.46 | $2.54 | $2.61 | $2.77 | $2.85 | $2.94 |
| Lease SF expiring | 0 | 0 | 540,000 | 0 | 0 | 0 |

## 10. Gate phasing (NEXT_STEPS Step 5, owner-approved 2026-07-03)

The lease expires 8/31/2028 inside the window, so FY2029+ depends on Phase
2/3 machinery. **Gate 1 asserts FY2027 and FY2028 only** (every line within
$500/FY). FY2029–FY2031 revenue/vacancy lines activate at Gate 2; TI/LC/
capital lines at Gate 3. FY2032 is the resale look-forward year — transcribed
but not asserted before Phase 3.
