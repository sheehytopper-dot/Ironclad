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
- **Revisit when:** a golden's published cash flow demonstrably uses
  speculative-term CPI or rental-value-driven renewal rents and cannot be
  matched within tolerance without them (then the §3.6 schema grows the
  fields, with SCHEMA_GUIDE/JSON-schema regeneration).
