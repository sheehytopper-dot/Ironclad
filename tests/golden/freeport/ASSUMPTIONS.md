# 8505 Freeport Parkway — Fixture Assumptions & Audit Trail

Every input in `freeport.icprop.json`, with its OM page cite if stated, or its
derivation if not. All page cites are to
`source/8505 Freeport Parkway - JLL Offering Memorandum.pdf` ("OM p. N" = the
printed page number in the page footer; the PDF renders each spread twice, so
some content appears on two consecutive PDF pages — the cite is to the first).
The published cash flow [OM p. 50] is JLL's Argus-based 11-year projection
("Terms modeled in the Argus reflect the latest draft" [OM p. 52] confirms the
underlying Argus model).

**Fixture-lock status: CONFIRMED — owner-verified and committed 2026-07-08.**

## 1. Property & analysis period — stated [OM pp. 20, 51, 53]

| Input | Value | Source |
|---|---|---|
| Property | 8505 Freeport Parkway, Irving (Las Colinas), TX 75063 — 6-story office, built 1982 | OM p. 20 |
| Analysis commencement | July 1, 2026 | OM p. 51 ("Projection Start Date of July 1st, 2026") |
| Analysis term | 11 years, through June 30, 2037 → `analysis_term_years: 11` | OM p. 51; cash flow columns FY2027–FY2037 [OM p. 50] |
| Fiscal year end | June 30 → `fiscal_year_end_month: 6` | OM p. 50 column headers ("Fiscal Year Ending June") |
| Rentable square feet | 123,099 SF (fixed) | OM pp. 20, 53, 63 |
| Property size | 123,099 SF (no separate gross area published — assumed = NRSF) | assumption |
| Vacant at 7/1/26 | 3,276 SF = Suite 450 (3,030, static) + building storage (167) + security office (79) — none modeled as leases, so the engine's day-1 occupied area is 119,823 SF + the 1 SF Verizon placeholder (§10 flag 6), matching the OM's "Occupied 119,823 / Vacant 3,276" | OM pp. 52-53, 63 |
| The global-assumptions box's "Term of Analysis 5" [OM p. 53] | The underwriting snapshot's hold period, not the projection length — the cash flow itself runs 11 years and the fixture follows the cash flow | reading noted for QA |

## 2. Inflation — stated [OM pp. 51, 53]

"Revenue & Expense Growth Rates: Assumed to be 3.0% annually on a calendar
year basis beginning in January 2027 and thereafter (analysis based on 2026
budget)" [OM p. 51]; "CPI / Global Growth Rate 3.0%", "Calendar Year Analysis"
[OM p. 53].

Encoding: `timing_basis: calendar_year`, `inflation_month: 1`, single entry
`{year: 2027, rate: 3.0}` on every index (years before the first entry
contribute 0% — CY2026 amounts are in CY2026 dollars; the last rate carries
forward).

Verification: the market rent ladder $24.00 → 24.72 → 25.46 → 26.23 → 27.01
[OM p. 53] is exactly $24.00 × 1.03ⁿ (24.72 / 25.4616→25.46 / 26.2254→26.23 /
27.0122→27.01), and the antenna ladder $3,000 → 3,090 → 3,182.70 → 3,278.18 →
3,376.53 is exact ✓. Like Clorox, **the calendar-year basis sidesteps the
engine's open analysis-year mid-year question** (Clorox README adjudication
ladder).

## 3. Rent roll — stated [OM pp. 54-63; cross-checked against the rollover schedule p. 64]

29 lease records across 27 distinct suites — the OM's 27 tenant leases, with
OKI (Suite 100) split into current-term + negotiated-renewal records and
Texian (Suite 390) split into base + signed-expansion records (§10 flags 5,
and the expansion in §3). Base rent is the rate in force at 7/1/26 (steps
dated on or before analysis begin are folded into `base_rent`; the superseded
"Current" rate is noted per tenant below). All step schedules are exact $/SF/yr amounts
from the rent roll. All office tenants' reimbursements read "OpEx: BY *year*,
95% GU, RET included in OpEx, Electricity: NNN"; janitorial is in OpEx except
where noted NNN (OKI, National). Recovery encodings are §5.

| Suite | Tenant | SF | Start | LXD | Rent at 7/1/26 | Steps ($/SF/yr) | BY | Notes |
|---|---|---|---|---|---|---|---|---|
| 100 | OKI Data Americas Inc. | 2,584 | 8/1/16 | **1/31/27** | $26.00 | — | 2017 | Current term of the split (below); janitorial NNN |
| 100 | OKI Data Americas Inc. (Renewal) | 2,584 | **2/1/27** | 6/30/32 | $22.00 | 7/1/28 22.66; 7/1/29 23.34; 7/1/30 24.04; 7/1/31 24.76 | 2026 | Negotiated 5-yr renewal per LOI [OM pp. 52, 54]; 5 months 100% abatement from start; janitorial NNN |
| 150 | Aqore LLC | 1,996 | 4/1/26 | 7/31/29 | $20.50 | 8/1/27 21.12; 8/1/28 21.75 | 2024 | 3-yr extension per LOI; 4 months abatement from 4/1/26 (only Jul-26 in window) |
| 160 | Traction First, LLC | 1,394 | 3/1/16 | 7/31/28 | $24.00 | 8/1/27 24.50 | 2019 | |
| 170 | Mid-America Overseas, Inc. | 1,556 | 6/1/25 | 6/30/28 | $22.00 | 7/1/27 22.50 | 2021 | 7/1/26 step = analysis begin → folded ($21.50 current superseded) |
| 190 | Burnco Texas, LLC. | 9,438 | 1/1/18 | 1/31/30 | $22.50 | 2/1/27 23.00; 2/1/28 23.50; 2/1/29 24.00 | 2017 | |
| 200 | Jetvia (LIN) | 4,340 | 6/1/26 | 8/31/31 | $22.50 | 9/1/27 23.18; 9/1/28 23.87; 9/1/29 24.59; 9/1/30 25.32 | 2026 | Lease in negotiation, modeled per OM; 3 months abatement from 6/1/26 (Jul+Aug-26 in window) |
| 205 | Volt Information Sciences, Inc. | 3,009 | 5/1/19 | 7/31/27 | $24.00 | 8/1/26 24.50 | 2024 | **Hard vacate** [OM p. 52] |
| 210 | MasVida Health Care Solutions, LLC | 3,720 | 12/1/25 | 2/29/28 | $21.50 | 3/1/27 22.00 | 2026 | |
| 250 | Peritus Portfolio Services II, LLC | 4,904 | 3/1/25 | 6/30/32 | $21.00 | 7/1/27 21.50; 7/1/28 22.00; 7/1/29 22.50; 7/1/30 23.00; 7/1/31 23.50 | 2025 | 7/1/26 step folded ($20.50 superseded) |
| 260 | Samaritan's Purse | 5,253 | 2/1/26 | 1/31/28 | $22.00 | 2/1/27 22.50 | 2026 | |
| 350 | Centrada Solutions, LLC | 2,951 | 9/1/23 | 12/31/26 | $21.50 | — | 2023 | |
| 355 | AT&T - Antenna (MTM) | 323 | 4/1/19 | 6/30/27 | $64.20 | — | none | MTM; OM holds through 6/30/27 then antenna market roll [OM pp. 52, 56]; no reimbursements |
| 370 | Clean Energy | 2,863 | 11/1/19 | 2/28/30 | $23.50 | 3/1/27 24.00; 3/1/28 24.50; 3/1/29 25.00 | 2020 | |
| 375 | The Persimmon Group, Inc. | 3,581 | 8/1/24 | 10/31/29 | $21.50 | 11/1/26 22.00; 11/1/27 22.50; 11/1/28 23.00 | 2024 | |
| 380 | Trellis Technology Solutions, LC | 1,409 | 5/16/22 | 11/30/28 | $20.50 | 12/1/26 21.00; 12/1/27 21.50 | 2025 | |
| 385 | Perk Systems, Inc. | 1,287 | 4/1/21 | 9/30/28 | $21.00 | 10/1/27 21.50 | 2023 | PRS printed on 122,960 RSF; fixture uses the 123,099 denominator (§10 flag 8) |
| 390 | Texian Operating Company, LLC | 2,888 | 1/1/25 | 12/31/29 | $21.00 | 5/1/27 21.50; 1/1/28 22.00; 1/1/29 22.50 | 2024 | 12/31/27 termination option **not** exercised in the OM analysis |
| 390E | Texian Operating Company, LLC (Expansion) | 3,369 | **5/1/27** | 12/31/29 | $21.50 | 1/1/28 22.00; 1/1/29 22.50 | 2024 | Signed early direct expansion into the ex-RSDS space [OM pp. 52, 58] |
| 395 | RSDS, LLC | 5,679 | 12/1/21 | 4/30/27 | $21.50 | — | 2022 | 5/1/26 step folded ($21.00 superseded). Chain **ends** at LXD: 3,369 SF → Texian expansion record; 2,310 SF → absorption item (§9) |
| 400 | Five Point Dental Specialists, Inc. | 12,440 | 11/25/24 | 6/30/35 | $20.50 | 7/1/27 21.00 then +$0.50 each 7/1 through 7/1/34 24.50 | 2024 | 7/1/26 step folded ($20.00 superseded). **Hard vacate** [OM p. 52] |
| 425 | RDO Equipment Co. | 5,756 | 12/1/24 | 2/28/30 | $21.00 | 3/1/27 21.50; 3/1/28 22.00; 3/1/29 22.50 | 2024 | |
| 500 | National Employee Benefit Co. | 6,640 | 10/1/21 | 2/29/28 | $21.00 | 3/1/27 21.50 | 2024 | **Hard vacate**; janitorial NNN |
| 505 | RXO Freight Forwarding, Inc. | 3,858 | 10/1/23 | 9/30/28 | $20.50 | 10/1/26 21.00; 10/1/27 21.50 | 2023 | |
| 510 | AFS Logistics. LLC | 5,653 | 2/1/19 | 9/30/29 | $21.00 | 10/1/26 21.50; 10/1/27 22.00; 10/1/28 22.50 | 2019 | OM's monthly columns for this tenant are misprinted; annual PSF schedule used |
| 520 | KONE, Inc. | 2,396 | 6/1/22 | 5/31/27 | $23.00 | 2/1/27 23.50 | 2021 | |
| 525 | Wright Consulting Engineers of Texas, LLC | 2,679 | 5/1/23 | 7/31/26 | $20.50 | — | 2023 | Expires one month in; two 1-yr FMV options not modeled (market roll) |
| 600 | Rodeo Dental Management, PLLC | 21,226 | 3/1/25 | 7/31/30 | $20.00 | 8/1/26 20.50; 8/1/27 21.00; 8/1/28 21.50; 8/1/29 22.00 | 2025 | Two 5-yr FMV options not modeled (market roll) |
| ROOF | Verizon - Roof | 0 → **1 SF placeholder** | 9/1/18 | 9/30/28 | $34,957/yr | 10/1/26 $35,657/yr; 10/1/27 $36,370/yr | none | Absolute-dollar rent; §10 flag 6 |

Day-1 occupied SF check: the 29 records minus the renewal/expansion/roof
records sum to **119,823 SF — exactly the OM's "Occupied"** [OM p. 53].
All start/expiration dates cross-check against the rollover schedule
[OM p. 64].

Renewal options at FMV throughout the rent roll are not separately modeled:
"Fair market value renewal options roll to JLL's market leasing assumptions"
[OM p. 51], which is what `upon_expiration: market` at 75% renewal does.

## 4. Market leasing profiles — stated [OM p. 53 "MLAS $24 BY + E" and "Antenna / Roof"]

| Input | Office MLA (JLL MLAS) | Antenna / Roof MLA |
|---|---|---|
| Market rent (2026) | $24.00 /SF/yr | $3,000 — encoded **per month** (Verizon pays $2,913/mo current; $3,000/yr would be a pay cut ~92%; QA flag) |
| Growth | 3.0% (ladder verified §2) | 3.0% (ladder verified §2) |
| Term | 5 yrs 5 mos → 65 months | 5 years → 60 months |
| Renewal probability | 75% | 75% |
| Downtime | 9 months | 9 months |
| Rent increases during term | 3.00% annually → pct steps at months 12/24/36/48/60 | 3.00% annually → months 12/24/36/48 |
| Abatements (new/renewal) | 5 / 5 months (the p. 53 table prints "5 / 5" every year) — base-rent-only assumed (§10 flag 3) | 0 / 0 |
| TI (new/renewal) | $20 / $10 PSF (blended $12.50 = 25%×20 + 75%×10 ✓) | $0 |
| LC | 6.75% / 6.75% | 0% |
| Reimbursement | "BY + Util (95% GU)" → user structure "MLA BY + Util": OpEx lease-start-relative base year + Electricity net (see §5) | None |
| Renewal market rent | One market rent printed → renewal = 100% of new | same |

**Office MLA (Hard Vacate)** is the same profile with `renewal_probability: 0`
for the three hard-vacate tenants (Volt, Five Point, National — "space is
subleased / on sublease market" [OM p. 52]): the expiring tenant never renews,
the space re-leases at new-tenant terms after 9 months, and subsequent
generations revert to the normal 75% profile via
`upon_expiration: option → chained_profile` (§10 flag 4).

## 5. Recoveries — stated methods, TRUE stated base years [OM pp. 51, 54-63]

Stated: "Expense recoveries are modeled per existing leases and current
billing methodology. Available suites are leased up on Base Year Stop +
Electricity recovery structures." [OM p. 51]. Per tenant the rent roll states
OpEx: BY *year* with 95% GU, RET (and janitorial, except OKI/National)
included in OpEx, and Electricity NNN.

Encoding: one user `RecoveryStructure` per base-year cohort — pool 1 "OpEx"
(all operating expenses except Electricity; the +J variants also exclude
Janitorial), `method: base_year` with `base_year: {year: <stated>,
gross_up_pct: 95}`; pool 2 "Electricity" net, 95% gross-up; (+J variants add a
Janitorial net pool). Denominator = rentable area (123,099, matching the
printed PRS percentages).

**Each tenant carries its TRUE stated base year (2017–2026, exactly as
printed) — no fabricated stop, no placeholder** (standing principle, owner
directive 2026-07-07). The frozen base-year pool is left to the engine:

- **2017–2025 (pre-analysis).** The engine's timeline starts 7/1/26, so these
  base years have no ledger data. The engine's base-year fallback [AE pp. 377,
  408] resolves each to **analysis year 1** — "increases over the ... first
  year of the analysis" — computed from the projected FY2027-window expenses.
  The stated year stays the recorded input. (This behavior was extended this
  session so an explicit stated pre-analysis year triggers the same fallback
  the manual describes for a pre-analysis lease start; see DEVIATIONS §10.)
  All eight of these cohorts therefore freeze the *same* analysis-year-1 pool;
  the separate structures exist to record each tenant's real stated year.
- **2026.** Window (2026-01…2026-12) overlaps the timeline; the engine
  annualizes from the 6 available months (Jul–Dec 2026) — the CY2026 stop.

**This is now the fixture's honest position, not a derivation.** The earlier
draft manufactured a `$`/SF stop by deflating the CY2026 OpEx pool at 3%/yr
(assuming an unstated historical growth path); that is removed entirely.
Replacing it: the OM never publishes the tenants' base-year stop dollars and
no real historical figure exists past 2020, so the fixture states the real
year and lets the documented fallback compute the frozen pool. **The
new-this-session known-amount override** (`BaseYearSpec.known_amount` /
`RecoveryAssignment.base_year_amount`, a total annual dollar figure) is a
**capability for future deals where the real stop is known** — it is
deliberately *not* populated here, because Freeport has no such data.

Whether ARGUS itself used analysis-year-1 stops for these pre-analysis
leases (it should, per [AE p. 377]) is confirmed at Step 7 against the
published **Expense Reimbursement** line, which adjudicates per the ladder.

**MLP "BY + Util" gap — CLOSED 2026-07-08.** Speculative rollover leases get a
base-year stop frozen at each segment's own start year **plus** electricity NNN
from dollar one. This previously had no user-pool encoding (a pool base year was
a fixed calendar year only), so the fixture fell back to the **system**
`{method: base_year}` over *all* recoverable expenses, recovering electricity
only above its start-year level instead of from dollar one. The schema now
carries `BaseYearSpec.lease_start_relative` (DEVIATIONS.md §10), and both office
MLPs use a two-pool user structure **"MLA BY + Util"** — OpEx pool on a
lease-start-relative base year (95% GU) beside an Electricity net pool (95% GU),
matching the OM's stated structure. This closed the rollover-year recovery gap
(FY2031–FY2037 Expense Reimbursement now within ~$7K–$25K of the OM, was
$200K+); see DISCREPANCY_LOG.md. **A separate residual remains and is NOT this
gap:** the *contract* tenants' stated pre-analysis base years (2017–2025) still
resolve to analysis year 1 (no pre-analysis ledger data; §5 above,
DEVIATIONS.md §10), so FY2027–FY2029 recoveries stay understated — resolvable
only with the seller's actual historical stops (the `known_amount` override,
unpopulated), not with this fix.

**Cross-check impact of this recovery change on §2 and §6:**
- **§2 (inflation)** — unaffected. The market-rent and antenna ladders verify
  independently of recoveries; nothing here touches them.
- **§6 (operating-expense budgets)** — the derived CY2026 budgets are
  **unchanged**; they remain the expense *inputs* and their back-solve
  residuals (≤ $0.96) stand. What changed is that §6's figures are no longer
  also consumed to fabricate a deflated recovery stop — that intermediate
  ("CY2026 OpEx pool → $/SF stop") is deleted. The frozen base-year pool is
  now the engine's own projection of those same §6 expenses over the
  analysis-year-1 (or 2026) window, so the recovery side is derived from the
  expense inputs by the engine rather than by a hand formula in this document.

## 6. Operating expenses — derived from FY2027 [OM p. 50] per the fiscal back-solve

Stated basis: "Modeled per Seller's 2026 Budget, grown by 3.0% annually
beginning in 2027" [OM p. 51]; the budget itself is not itemized in the OM.
With calendar-year 3% stepping in January and a July–June fiscal year:

**FY2027 = CY2026 × (6 + 6 × 1.03) / 12 = CY2026 × 1.015**

**Fully fixed lines** (back-solve verified: derived base × fiscal factor
reproduces all 11 published years within ≤ $0.96):

| Expense | Published FY2027 | Derived CY2026 base | Worst residual (11 FYs) |
|---|---|---|---|
| Personnel Expenses | $158,614 | **$156,269.95** | $0.55 |
| Trash Removal | $26,796 | **$26,400.00** (round ✓) | $0.42 |
| Supplies/R&M/Contract Services | $433,908 | **$427,495.57** | $0.93 |
| Administrative Expenses | $27,919 | **$27,506.40** | $0.96 |
| Insurance | $60,127 | **$59,238.42** | $0.81 |
| Real Estate Tax | $292,089 | **$287,772.41** | $0.89 |

The round-number bases that fall out (Trash $26,400; §7 Parking $27,600,
Pylon $3,600; §8 Capital Reserves 0.20 PSF exact) confirm the 1.015 method.

**Variable lines** — "grossed up to 95% in most cases and … assumed to be 30%
fixed" [OM p. 51] → `pct_fixed: 30`; the published years move with occupancy
(FY2028 Electricity *falls* while fixed lines grow 3%), so the 100%-occupancy
budget cannot be back-solved exactly from annual data. Derived using the
published FY2027 average "Percent Leased" of 96.3% [OM p. 50]:

**base = FY2027 ÷ (1.015 × (0.30 + 0.70 × 0.963)) = FY2027 ÷ (1.015 × 0.9741)**

| Expense | Published FY2027 | Derived CY2026 base (100% occ.) |
|---|---|---|
| Electricity | $246,286 | **$249,097.94** |
| Utilities (Water & Sewer per OM p. 51) | $44,772 | **$45,283.18** |
| Janitorial | $171,764 | **$173,725.10** |

**These three are now the fixture's weakest inputs** (the derived recovery
stops that previously topped that list are gone — §5) — the true scaling uses
month-by-month occupancy inside JLL's model, not the annual average. Owner QA
may substitute actual budget figures; otherwise the published lines
adjudicate.

**Management Fees**: 3.0% of EGR [OM pp. 51, 53] → `pct_of_egr` (FY2027:
3% × $2,912,490 = $87,374.70 → published $87,375 ✓ — the fee is again a
recoverable %-of-EGR fixed point, as in Clorox).
**Margin Tax**: 0.331% of EGR [OM p. 51] (FY2027: 0.331% × 2,912,490 =
$9,640.34 → published $9,640 ✓).

## 7. Miscellaneous property revenues — derived [OM pp. 50-51]

"Modeled per Seller's 2026 Budget, grown by 3.0% annually beginning in 2027"
[OM p. 51]. Back-solved at ÷1.015 (worst residual $1.10 over 11 years):

| Line | Published FY2027 | Derived CY2026 base | Encoding |
|---|---|---|---|
| Parking Income | $28,014 | **$27,600.00** (round ✓) | `parking_revenues` |
| Other Income | $1,523 | **$1,500.49** (≈ $1,500 budget; kept at the exact back-solve) | `miscellaneous_revenues` |
| Pylon / Facia Sign Rental | $3,654 | **$3,600.00** (round ✓) | `miscellaneous_revenues` |

All three post to the ledger's single "Parking / Storage / Miscellaneous
Property Revenue" line; the expected CSV carries them as three rows mapped to
that account (they sum for comparison). **Engine note:** property revenues
are currently phase-guarded in `run.py` — the §4.1 property-revenue pass must
be built before this fixture's comparison can run (README).

## 8. Vacancy — stated rates [OM pp. 51, 53]; method assumed

- **Static vacancy 2.5%** = Suite 450 (3,030 SF = 2.46% of NRA), "modeled as
  static" [OM pp. 51-52] — encoded physically: no lease, no absorption, the
  suite simply stays vacant (with storage/security, structural vacancy =
  3,276 SF, the OM's "Vacant" figure ✓). The p. 53 lease-up table's terms for
  Suite 450 are moot under "Static" and are not encoded.
- **General vacancy 5.0%** "applied through the length of the analysis"
  [OM p. 51] — encoded `percent_of_pgr`, rate 5.0 from 2026,
  `reduce_by_absorption_turnover: true`. **The OM states neither the
  percentage basis nor the offset behavior**; the near-zero published FY2028
  value ($11) implies the A&T offset, but annual data could not pin the
  basis (percent-of-PGR vs total-tenant-revenue reproduce neither year
  exactly at 5%). QA / adjudication point.
- **Credit loss**: none stated separately; the published line is combined
  "General Vacancy / Credit Loss" and maps to the General Vacancy account.

## 9. Absorption — stated [OM pp. 52, 58]

RSDS (Suite 395) expires 4/30/27; 3,369 SF is absorbed by the Texian
expansion record (§3), and "the remainder (2,310 SF) is modeled to lease up 6
months after expiration at JLL MLA terms" [OM p. 52] → one `AbsorptionSpec`:
2,310 SF, one lease, start **11/1/2027**, Office MLA (JLL MLAS).

## 10. Schema-encoding flags (approximations avoided; choices disclosed)

1. **Pre-analysis base years kept as the true stated year** (§5) — each
   tenant records its real BY (2017–2026); the engine's documented fallback
   [AE pp. 377, 408] resolves the pre-analysis ones to analysis year 1. No
   fabricated stop; the known-amount override is left unpopulated (no real
   historical figure exists).
2. **MLP "BY + Util" split** — closed 2026-07-08: encoded as the user
   structure "MLA BY + Util" (OpEx lease-start-relative base year + Electricity
   net), via the new `BaseYearSpec.lease_start_relative` field (§5;
   DEVIATIONS.md §10). Rollover-year electricity now recovers from dollar one.
3. **MLA abatements "5 / 5"** [OM p. 53] read as 5 months new / 5 months
   renewal; base-rent-only abatement assumed (the OM does not specify which
   charges abate). Contract abatements (OKI/Aqore/Jetvia) are stated as
   "100% of Base Rent" [OM pp. 52, 54] → same "Base Rent Only" profile.
4. **Hard vacates** (Volt, Five Point, National): 0%-renewal profile whose
   `upon_expiration: option` chains back to the 75% profile — `option` is the
   only expiration that follows `chained_profile`, so this encodes "vacate
   once, then normal rollover".
5. **OKI split into two records** (current term to 1/31/27 + renewal from
   2/1/27): one lease carries one recovery assignment, and OKI's base year
   resets 2017 → 2026 at the renewal [OM p. 54]; the split also places the
   5-month abatement and the LOI rent schedule on the renewal term.
6. **Verizon - Roof at 1 SF** (schema requires `area > 0`; the OM lists 0
   SF): rent in absolute dollars, recoveries none — the placeholder SF
   touches only occupied area (1/123,099).
7. **Free rent straddling analysis begin** (Aqore 4 months from 4/1/26,
   Jetvia 3 months from 6/1/26): encoded as contract free rent from lease
   start; only the in-window months abate. QA: confirm the engine posts the
   straddle months correctly at comparison time.
8. **PRS denominators**: printed shares are on 123,099 RSF (OKI and Perk
   print a legacy 122,960 variant); the fixture uses the rentable-area
   denominator throughout.
9. **Capital Expenditures**: Curtain Wall Reseal $140,000 (Jan-29) and
   Elevator Mod $1,250,000 (Mar-29) [OM pp. 51, 53] encoded as one-month
   `dollars_per_month` capital items on a zero-rate schedule, sharing the
   "Capital Expenditures" account; both land in FY2029 = published
   $1,390,000 ✓. Capital Reserves $0.20 PSF grown 3% (0.20 × 123,099 ×
   1.015 = $24,989.10 → published $24,989 ✓).
10. **Statuses**: AT&T carries `status: mtm` (informational); Jetvia is a
    lease-in-negotiation modeled as contract per the OM.

## 11. Stated in the OM but NOT modeled in this draft (owner QA decisions)

| Item | Where stated | Why deferred |
|---|---|---|
| Controllable-OpEx recovery caps (6%/7%/9% cumulative or YoY, per tenant) | rent roll pp. 54-63 | The OM defines neither the "controllable" expense set nor the cap base amounts. Expressible via per-tenant pool `caps_floors` once the controllable set is decided — listed per tenant in §3 notes. Cumulative caps compound from the lease base year, so early-year impact is likely small; the reimbursement line adjudicates. |
| Management-fee recovery caps (Volt 4% of EGR; RDO/RXO 5% of base rent) | pp. 56, 60 | Per-tenant caps on one pool member; no schema field. Small dollars; flagged. |
| Texian termination option (effective 12/31/27) | p. 58 | Not exercised in the OM's own analysis. |
| Renewal options at FMV | throughout | The OM itself rolls them to MLAS (§3). |
| "Contractual renewal leasing costs borne by Seller" | p. 51 | No TI/LC modeled on the OKI/Aqore negotiated terms — matches. |
| Rollover schedule / WALT statistics | p. 64 | Reference cross-check only (dates verified ✓). |

## 12. Published statistics rows [OM p. 50] — reference only, not asserted

| Row | FY27 | FY28 | FY29 | FY30 | FY31 | FY32 | FY33 | FY34 | FY35 | FY36 | FY37 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Percent Leased | 96.3% | 91.9% | 94.0% | 92.7% | 94.7% | 96.6% | 95.4% | 93.9% | 96.1% | 83.6% | 97.0% |
| Leases Expiring SF | 16,916 | 20,178 | 7,948 | 29,287 | 21,226 | 11,828 | 0 | 0 | 12,440 | 0 | 0 |
| WTD Avg Market Rent | $24.89 | $25.64 | $26.41 | $27.20 | $28.01 | $28.86 | $29.72 | $30.61 | $31.53 | $32.48 | $33.45 |
| WTD Avg In-Place Rent | $21.75 | $22.51 | $22.87 | $23.41 | $24.28 | $27.63 | $28.61 | $28.98 | $29.66 | $29.50 | $31.42 |

(The rollover schedule's Year-1 expiring 14,028 SF vs the cash flow's 16,916
differ in the source itself — the cash flow page governs the fixture.)

## 13. Gate phasing

Gate 2 scope is the **revenue/vacancy/expense/NOI lines**; TI/LC/capital
lines wait for Gate 3 (as with golden #1's FY2029+ capital columns). The
expected CSV transcribes all 11 published fiscal years; which years the Gate
2 test asserts is decided at Step 7 with the owner (rollover machinery
touches every year here — there is no all-contract early window like
Clorox's FY2027-28).
