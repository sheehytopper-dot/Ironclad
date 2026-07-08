# DEVIATIONS

Deliberate, owner-approved deviations and narrowings from
[ARGUS_REBUILD_SPEC.md](ARGUS_REBUILD_SPEC.md) and the ARGUS manual. Per the
standing transparency rule (CLAUDE.md, Conventions), nothing is dropped from the
spec silently — it is recorded here instead. Accidental deviations found in audit
are fixed, not listed.

## 1. Absorption: market-leasing-profile reference only (spec §3.15 narrowed)

- **Spec:** §3.15 allows an absorption spec to carry a `market_leasing_profile`
  ref **or** inline lease terms mirroring the rent roll fields.
- **As built:** `AbsorptionSpec` ([engine/models/leases.py](engine/models/leases.py))
  supports only the profile reference. Inline lease terms are **deferred
  deliberately** — a profile can express the same lease economics, and no golden
  fixture requires inline terms.
- **Revisit when:** a golden fixture or real deal needs absorption terms that a
  named profile cannot express.

## 2. Inflation: annual `YearRate` schedules only (spec §3.3 as written)

- **Manual:** [AE pp. 219-223] also supports monthly-detail inflation rates
  (1/12-per-month market rent inflation via Modeling Policies) and
  index-value-based inflation indices (date + index value or percent increase,
  with "Repeat Last Percentage").
- **Spec and as built:** spec §3.3 deliberately simplifies to annual percent
  schedules (`list[YearRate]`, analysis-year or calendar-year basis, stepping on
  `inflation_month`), and `engine/models/inflation.py` /
  `engine/calc/inflation.py` follow the spec. Monthly-detail rates and
  index-value indices are **not modeled**.
- **Revisit when:** a golden fixture's published cash flow demonstrably uses
  monthly inflation detail or index-value indices and cannot be matched within
  tolerance without them.

## 3. Below-the-line revenue: encoded as a negative capital expense

- **Gap:** the §3 schema has no capital-section revenue account.
- **As built:** the Clorox fixture's Amortized CAM Revenue ($3,956.91/mo
  through 12/2027, modeled below the line per the OM) is encoded as a
  **negative capital `ExpenseItem`** — same ledger placement and sign as the
  OM's capital-section credit line (ASSUMPTIONS.md §8, flag 1, in
  `tests/golden/clorox_northlake/`).
- **Revisit when:** a future golden needs true capital-section revenue that a
  negative expense cannot faithfully represent (e.g., its own account name in
  reports, or interaction with recoveries/valuation that sign-flipping would
  distort).

## 4. Free rent profiles: booleans vs the manual's per-component percentages

- **Manual:** [AE pp. 253-254] free rent "elements to include" are
  *percentages* per component — base rent 100%, fixed steps 100%, CPI 0%,
  percentage rent 0%, recoveries 0%, miscellaneous 0% by default — and free
  months may vary over time.
- **Spec §3.8 / as built:** `FreeRentProfile` has three booleans
  (`abate_base_rent`, `abate_recoveries`, `abate_miscellaneous`); fixed steps
  ride with base rent at 100% and CPI is fixed at 0% —
  `engine/calc/leases.py` implements exactly the manual's defaults.
- **Revisit when:** a golden requires partial-percentage abatement, a
  fixed-steps or CPI element different from the defaults, or time-varying
  free months.

## 5. Cash Flow line order: the manual's report layout over spec §2.3's sketch

- **Spec:** the §2.3 account tree lists Free Rent *after* Scheduled Base
  Rental Revenue, and Expense Recovery Revenue *before* Percentage Rent.
- **Manual:** the Cash Flow report [AE p. 538] defines Scheduled Base Rent as
  "the potential rent minus vacancy and free rent" — Free Rent is a component
  of (and printed above) the Scheduled Base Rent subtotal — and the Other
  Tenant Revenue section lists Percentage Rent before expense recoveries.
- **As built:** `engine/calc/ledger.py` follows the manual (which governs on
  behavior, CLAUDE.md): line order Base Rental Revenue → Absorption & Turnover
  Vacancy → Free Rent → Scheduled Base Rental Revenue (= sum of the three) →
  CPI → Percentage Rent → Expense Recovery Revenue. The Clorox golden's
  transcribed CSV confirms the rollup (FY2029: 3,760,710 − 682,689 − 256,008
  = 2,822,012 ≈ Total Scheduled Base Rent). The §9.3 "PGR identity" invariant
  is asserted in this manual-consistent form.
- **Revisit when:** never expected — this is the golden-file-confirmed ARGUS
  behavior; the spec sketch was simply imprecise.

## 6. %-of-EGR expenses: fixed-point iteration, not the spec's single second pass

- **Spec:** §4.1 step 9 says %-of-EGR items "reference EGR excluding
  themselves; a single second pass suffices, no fixed-point iteration
  needed."
- **Reality:** that holds only for %-of-EGR *revenue* items, which exclude
  themselves directly. A **recoverable %-of-EGR expense** (the Clorox
  management fee) re-enters EGR indirectly: the fee joins the net recovery
  pool, recoveries join EGR, and the fee is a percent of EGR. A single
  second pass computes the fee off pre-fee EGR and understates it — for
  Clorox FY2027 by ≈$3,535, seven times the $500 golden tolerance.
- **As built:** `engine/calc/run.py` iterates fee → recoveries → EGR → fee
  to convergence (a contraction with factor pro-rata share × fee pct, so a
  handful of rounds; non-convergent inputs — percentages ≥100% of revenue —
  raise). Golden #1 confirms the converged behavior is ARGUS's: Management
  Fee = 3.0000% of **final** EGR in both Gate 1 fiscal years, equal to the
  closed form pct/(1−pct) × (EGR excluding the fee) at 100% share.
- **Revisit when:** never expected — golden-confirmed ARGUS behavior; the
  spec's single-pass claim stays true for the §3.10 revenue items it was
  written about.

## 7. Market leasing profiles: no speculative CPI, no Rental Value machinery

- **Manual:** MLPs carry CPI increase options for market leases [AE
  pp. 237-238] and a Rental Value section (rental value + inflation,
  Continue Prior renewal rents, Renewal Override, % of Prior Rent) [AE
  pp. 235, 238].
- **Spec:** §3.6's schema lists neither a CPI field nor rental-value
  fields (renewal rent is `MoneyRate | {pct_of_new}` only) — though §3.7
  says CPI "applies to ... speculative leases (via MLP)", a spec-internal
  inconsistency resolved here on the §3.6 side.
- **As built:** speculative segments carry no CPI, and market base rents
  accept $/SF/yr, $/SF/mo, $/yr, $/mo, and % of last rent only —
  `pct_of_market` (the manual's "% of Market" against Rental Value) is
  rejected with a readable error. Intelligent Renewals compares prior rent
  against the renewal market rent directly (the manual's rental-value
  substitution cases [AE p. 236] cannot arise without Rental Value).
  Likewise the manual's **Continue Prior** recovery default [AE
  pp. 239-240] (carry the expiring lease's recovery method forward, base
  year stops not reset) is not modeled: the MLP's `RecoveryAssignment` is
  explicit, and a base-year assignment on a speculative segment uses the
  segment's own start year as its base year (each rollover is a new
  lease).
- **Revisit when:** a golden's published cash flow demonstrably uses
  speculative-term CPI or rental-value-driven renewal rents and cannot be
  matched within tolerance without them (then the §3.6 schema grows the
  fields, with SCHEMA_GUIDE/JSON-schema regeneration).

## 8. Absorption: pre-absorption vacancy grosses PGR to market (corrected 2026-07-06); reabsorb deferred

- **Manual:** the Cash Flow's Potential Base Rent "is derived from the
  combination of in-place rent and the market value of the currently
  vacant spaces," with Absorption & Turnover Vacancy carrying the
  offsetting "loss in rent due to downtime between leases and current
  vacant space" [AE p. 538].
- **History:** the original Step 3 call (2026-07-06, same day) had
  pre-absorption vacant months post nothing to revenue, reasoning that
  Scheduled Base, EGR, and NOI are identical under either convention.
  That held only while nothing consumed the A&T ledger line. Step 4's
  hand-model showed the divergence: general vacancy's
  ``reduce_by_absorption_turnover`` offset (spec §3.4, the ARGUS default)
  subtracts A&T from the vacancy allowance — with pre-absorption A&T
  missing, the engine would charge full general vacancy *on top of* the
  economically-vacant space and run EGR/NOI materially below ARGUS for
  every absorption month (≈ rate × grossed base, uncapped by the A&T
  already suffered). Owner-directed correction, same day.
- **As built:** ``pre_absorption_vacancy`` posts each not-yet-absorbed
  space's market value to Base Rental Revenue with the offsetting
  negative A&T entry, exactly like rollover downtime (spec §4.2) —
  confirmed by test that Scheduled Base, EGR, and NOI are unchanged by
  the gross-up; only Potential Base Rent, A&T, and the vacancy-offset
  base move. Month-level convention: the vacant space is valued at the
  then-current market rent, inflating month-by-month under
  ``term_growth`` (annual golden data cannot discriminate this against
  freeze-at-start; a dispute goes to owner per-cell adjudication).
- **Still deferred:** ``upon_expiration = 'reabsorb'`` (space returning
  to the absorption pool). The manual does not define the re-pooling
  mechanics (which schedule, what timing), so v1 refuses it loudly in
  run.py rather than letting the space sit silently vacant;
  ``resolve_lease_chain`` itself simply ends the chain.
- **Revisit when:** goldens #4/#5 (triaged for absorption coverage)
  back-test the corrected treatment against published Argus output;
  reabsorb waits for a deal that needs it.

## 9. General vacancy / credit loss: schema narrowings vs the manual

- **Manual [AE pp. 224-231]:** an Annual Amount method (inflatable
  currency schedules) alongside the three percentage methods; a
  "Gross-Up Revenue by Absorption & Turnover Vacancy" base toggle
  independent of the "Reduce General Vacancy Result by Absorption &
  Turnover" checkbox; tenant overrides with adjust / increment / replace
  methods and per-tenant override percentages, plus an After Expiration
  reversion option.
- **Spec §3.4/§3.5 / as built:** percentage methods only (no annual
  amount); overrides are **exclusion-only** (`{tenant_ref, exclude}` —
  the credit-tenant case; an excluded tenant leaves both the base and
  the A&T offset). The two manual toggles are paired as one flag:
  ``reduce_by_absorption_turnover = true`` computes the target on
  revenue grossed to 100% occupancy ("calculations based on potential
  revenue with 100% Occupancy" [AE p. 226]) and reduces the allowance by
  A&T; ``false`` computes on as-scheduled revenue with no reduction
  (separate line items [AE p. 226]). The manual's mixed pairings
  (gross-up without reduction, reduction without gross-up) cannot be
  expressed.
- **Revisit when:** a golden's published cash flow needs an annual-amount
  vacancy, a rate-modifying tenant override, or an unpaired
  gross-up/reduce combination and cannot be matched within tolerance
  without it.

## 10. Recovery structures: v1 narrowings and fixed policies

- **Anchor contributions not modeled (schema-absent):** the manual's
  "Reimburse After" machinery — deducting an anchor tenant group's
  recovery contribution from an in-line pool via the common expense
  factor [AE pp. 410-411] — has no spec §3.14 field and cannot be
  requested. First golden needing it drives the schema addition.
- **Admin fee flavor:** % of recoverable expenses only (the ARGUS
  default), applied before or after the stop per the schema flag; the
  "% of Recovery" alternative [AE p. 520] is not modeled. The default
  policy pairing holds: the base-year stop basis includes the admin fee
  when the fee applies before the stop ("Calculate Base Year Stop Before
  Admin Fees" unchecked [AE p. 520]).
- **Gross-up of %-of-revenue lines:** the manual's "Gross Up Percent of
  Line" policy [AE p. 519] is fixed at its no-adjustment (100% Fixed)
  setting — %-of-EGR/PGR expenses pass through pools ungrossed. This is
  also what keeps the %-of-EGR fixed point a contraction with gross-up
  active (recoveries.py docstring): every gross-up ratio is constant
  with respect to the fee. The 100%-Variable setting would amplify the
  fee feedback by gross_up/occupancy — unbounded at low occupancy — so
  any future policy toggle must re-derive the convergence bound first.
- **Zero-occupancy gross-up:** a fully variable expense (pct_fixed = 0)
  in a zero-occupancy month cannot be grossed from its occupancy-scaled
  series (observed 0; base unrecoverable) — loud ValueError, remedy in
  the message.
- **Caps/floors conventions:** min/max are annual $ amounts (the
  manual's amount/area units are not modeled), inflating on the general
  rate by default [AE p. 412]; YoY and cumulative growth caps apply to
  calendar-year totals — the v1 stand-in for ARGUS recovery years, like
  the straight monthly accrual policy (spec §3.14).
- **Fiscal base-year windows:** ``BaseYearSpec.fiscal`` raises
  (calendar windows only until a golden needs fiscal).
- **Pre-analysis base years fall back to analysis year 1, computed —
  not the stated year's actuals.** The engine's timeline begins at the
  analysis start, so a stated base year that ends before it (Freeport's
  2017–2025 OpEx stops on a 7/1/26 analysis) has no ledger data. Per the
  manual [AE pp. 377, 408] such a lease "pay[s] their pro-rata share of
  any increases over the ... first year of the analysis", so the frozen
  stop is computed from analysis year 1. **The stated year is always kept
  as the input** (never overwritten with a placeholder): the fallback
  lives in ``_resolve_base_year_window``, shared by the system methods
  and user pools, and triggers off the stated year's window ending before
  the analysis start (previously it triggered only off a pre-analysis
  lease *start*, and an explicit pre-analysis year raised on an empty
  window — that gap is now closed). A partially-in-window year (a 2026
  stop on a mid-2026 analysis) is kept and annualized from its available
  months; a future-dated window still raises (input error, not missing
  history).
- **Known base-year override** (``RecoveryAssignment.base_year_amount``;
  ``BaseYearSpec.known_amount``): when the real frozen base-year figure is
  known (operating statements, the seller's Argus file), it is supplied as
  a **total annual dollar** figure and used directly, bypassing the
  computed window and the fallback; the year field then documents which
  calendar year it represents. Chosen as a total (not a $/SF quantity like
  ``base_stop``'s ``stop_amount_per_area``) because base-year math freezes
  the whole reimbursable pool and divides by pro-rata share afterward — a
  $/SF override would force a spurious re-multiplication by the
  denominator. Both overrides are frozen constants w.r.t. the management
  fee, so the %-of-EGR contraction bound is untouched (§6; recoveries.py
  docstring). Freeport uses the year-only path (no real historical dollars
  exist past 2020); the override is a capability for future deals where the
  figure is actually known.
- **Revisit when:** goldens #2/#4/#5 — Freeport (#2) is the base-year/
  stop coverage deal and will exercise most of this section within
  tolerance or drive corrections.

## 11. Percentage rent: v1 narrowings and fixed policies (Phase 2 Step 8)

**Standing gap first (CLAUDE.md):** the whole module is **externally
unvalidated pending golden #3** — the manual supplies definitions
[AE pp. 249-251, 376-377, 590] and one worked number (% of Sales:
200,000 × 8% = 16,000 [AE p. 392]) but no published Argus cash flow yet
confirms it. Any retail underwriting before the golden #3 back-test
treats the Percentage Rent line as unverified.

- **Recovery offset deferred (schema-absent):** the manual's Offset % —
  a percentage of recoveries deducted from percentage rent, entered per
  recovery method on the recovery structure [AE p. 413] — has no field
  in spec §3.13 (percent rent) or §3.14 (recovery structures) and cannot
  be requested. The first golden or deal needing it drives the schema
  addition; until then the Percentage Rent line is gross of any offset.
- **Monthly accrual convention:** ARGUS computes % rent due annually
  ("the amount ... in a given year" [AE p. 590]) with a Modeling
  Policies monthly/annual toggle [AE p. 413]. v1 prices each month's
  annualized run rate (that month's sales volume and rent × 12) through
  the annual formula and posts 1/12 — the same straight monthly accrual
  policy as recoveries (spec §3.14). Identical to the annual figure
  whenever sales, rent, and breakpoints are constant within the year; a
  mid-year rent step shifts timing within the year, not the level.
- **Occupied months only:** percentage rent posts over a segment's
  occupied months — nothing during rollover downtime (the Step 2
  recovery convention; the downtime gross-to-market [AE p. 538] covers
  base rent + A&T only). The renewal-weighted "p × renewing tenant's
  sales" a probability purist might post in downtime is not modeled.
- **Speculative natural breakpoints use blended rent:** an MLP's spec
  rides its speculative segments [AE p. 376 "Market" sales basis]; the
  natural breakpoint reads the §4.2 blended market rent (and no CPI —
  §7). ARGUS would compute each branch (new vs renew) separately before
  weighting; with both branches on the same MLP economics the difference
  is zero, and it is second-order otherwise.
- **Single sales category, single flat spec:** the manual's
  Detailed/Multiple tenant sales categories [AE p. 249], Continue Prior
  sales basis [AE p. 376], varying-over-time sales/percent/breakpoint
  detail windows [AE pp. 250, 377], per-layer caps [AE p. 250], and the
  $/SF breakpoint unit ("Amount/Area" [AE p. 250]) are not modeled:
  spec §3.13 carries one spec per lease — annual $ or $/SF sales volume
  growing on an inflation index, one breakpoint method, up to 6
  (breakpoint, pct) layers with fixed annual $ breakpoints.
- **No property-type gate:** ARGUS enables percentage rent only for
  Retail / Mixed Use property types [AE p. 249]; the engine computes it
  for any lease carrying a spec (the schema is the gate — user intent
  governs, matching the recovery-pool membership stance in §10).
- **Free rent does not reduce the natural breakpoint:** the manual
  defines natural = base + step + CPI [AE pp. 250-251, 377] — potential
  rent components only — so abatements leave the breakpoint unchanged.
- **Revisit when:** golden #3 arrives (standing opportunistic intake) —
  its back-test either confirms these policies within tolerance or
  drives corrections; any offset/multi-category need surfaces there.
