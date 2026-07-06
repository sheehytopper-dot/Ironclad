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
- **Revisit when:** goldens #2/#4/#5 — Freeport (#2) is the base-year/
  stop coverage deal and will exercise most of this section within
  tolerance or drive corrections.
