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
  lease) — whether that assignment is the system `base_year` method or a
  user structure with a `lease_start_relative` pool (§10, added 2026-07-08),
  which resolve through the same shared window logic.
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
- **Reabsorb shipped for contract leases (2026-07-11; Phase 3 / Step 1),
  per the owner's authoritative description of AE's mechanics** (the
  manual itself does not define the re-pooling; the owner's 2026-07-11
  spec governs): a contract lease with ``upon_expiration = 'reabsorb'``
  retires at expiration (``resolve_lease_chain`` ends the chain, as it
  always did) and its space returns to the vacant pool. From the month
  after expiration the space is carried at its market value in Potential
  Base Rent with the equal offsetting A&T entry — netting $0 in
  Scheduled/EGR/NOI — until absorption re-leases it or the timeline ends.
  The market rate comes from the lease's own ``market_leasing_profile``
  (required by the schema for reabsorb), valued month-by-month under
  ``term_growth`` (this section's standing convention). Re-leasing is
  connected explicitly: ``AbsorptionSpec.reabsorbed_from`` names the
  reabsorbed lease; linked specs' phantom windows start at the lease's
  expiration + 1 (not timeline start), the lease itself phantoms only the
  uncovered remainder, and the ARGUS step-down is the emergent sum.
  Cross-validated loudly: the ref must name a 'reabsorb' lease, linked
  specs start after expiration, and linked areas sum to at most the
  lease's area. Derived rentable area keeps the reabsorbed lease's stated
  area as the permanent SF anchor and excludes linked specs' generated
  leases from the sum (owner decision 2026-07-11 — no double count).
  **Externally unvalidated:** no golden exercises reabsorb (Freeport's
  RSDS partial reabsorption was deliberately encoded without it);
  engineered tests only (tests/unit/test_reabsorb.py), flagged in each
  docstring.
- **Still deferred: reabsorb on speculative/MLP chains**
  (``MarketLeasingProfile.upon_expiration = 'reabsorb'`` stays refused in
  run.py). A speculative chain segment has no fixed, known expiration
  date for the ``reabsorbed_from`` linkage validations to anchor on — the
  v1 narrowing scoped 2026-07-11, same pattern as other v1 narrowings.
  The engine cannot know at input-validation time when (or whether) a
  probabilistically-rolled segment ends.
- **Not enforced (documented, user responsibility):** nothing prevents
  staging another rent-roll lease on a reabsorbed space — the schema has
  no suite-occupancy model, so "can no longer be leased from the Rent
  Roll" is staging discipline, the same stance as AbsorptionSpec sizing
  generally.
- **Revisit when:** a golden or real deal exercises reabsorb (back-test
  via the Benchmark Comparison report), or a deal needs speculative-chain
  reabsorb (then the linkage needs a resolved-chain anchor, a genuinely
  new design).

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
- **Lease-start-relative user pools — GAP CLOSED (2026-07-08).** Previously
  a user structure's pool base year could only be a fixed calendar
  ``BaseYearSpec.year`` (or None → analysis year 1), while the *system*
  ``base_year`` method already resolved each speculative segment's base year
  to its own start year (§7 [AE pp. 405-406, 408-409]). So a two-pool
  "BY + Util" structure (OpEx on a base year, Electricity net from dollar
  one) could not be expressed on speculative/MLP segments, and Freeport's MLP
  recoveries fell back to the system ``base_year`` method over *all* expenses
  — recovering electricity only above its start-year level, not from dollar
  one (named in Freeport ASSUMPTIONS §5 and README). ``BaseYearSpec`` now
  carries ``lease_start_relative: bool`` (mutually exclusive with a fixed
  ``year``); when set, ``_pool_recovery`` resolves the window through the same
  shared ``_resolve_base_year_window(lease_start=segment_start)`` the system
  method uses — architectural parity, no new manual-derived logic. Freeport's
  MLPs now use a two-pool user structure (OpEx lease-start-relative +
  Electricity net). See the before/after in that fixture's DISCREPANCY_LOG.
- **Revisit when:** goldens #2/#4 (#5 disqualified 2026-07-09, §14) —
  Freeport (#2) is the base-year/stop coverage deal and will exercise
  most of this section within tolerance or drive corrections.

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

## 12. Expense per-year known-amount override (`annual_overrides`)

- **What it is:** an optional `ExpenseItem.annual_overrides` — a list of
  `{year, amount}` entries — that, for a given fiscal year, uses a known
  actual dollar figure directly in place of the computed base × inflation
  index. The override wins completely for that year (posted as
  ``amount / 12`` per active month, applied after and unaffected by the
  ``limits`` clamp); years without an override compute exactly as before.
  ``year`` is the fiscal-year label (the calendar year the fiscal year ends
  in, matching the ledger's ``fiscal_year_of`` aggregation — identical to the
  calendar year for the default December fiscal-year-end).
- **Why it exists (not spec-derived):** this is a pragmatic escape hatch,
  the same philosophy as the recovery `base_year_amount` / `known_amount`
  override (§10, commit 558fdf2). Real deals carry known actual figures the
  formula cannot reproduce cleanly — **real-estate-tax abatements,
  reassessments, or any line where the analyst has the real number and
  should not have to reverse-engineer a `base × index` formula to hit it.**
  The motivating case is **Cedar Alt (golden #4): its Bldg-1 city-tax
  abatement runs through Feb 2036 on 90% of the improvement value over a
  2016 base, but the OM never states the improvement value and the implied
  abatement is inconsistent with 3% growth — so the RET line cannot be
  computed from the stated inputs.** With this feature the fixture uses the
  OM's own published RET figures [Cedar Alt OM p. 28] for FY2027–FY2036
  directly and lets FY2037 (unabated) fall through to the gross stated-basis
  formula (already exact). It has engineered unit tests (a synthetic expense
  overridden in one year, surrounding years growing off the base) but no
  manual worked-example citation, by nature.
- **Precedence:** override → nothing else. It is not blended with the
  formula and not re-clamped by `limits`; a per-year duplicate is a
  validation error. A `pct_of_*` expense that carries an override posts the
  fixed override amount in that year — a constant, so it does not perturb the
  %-of-EGR fixed-point contraction (§6).
- **Revisit when:** never expected to be removed; if a future need is to
  override at monthly rather than annual granularity, extend rather than
  replace.

## 13. Property revenues: v1 narrowings (spec §4.1 step 9)

The misc / parking / storage property-revenue pass (`engine/calc/revenues.py`)
shares the expense projection machinery. Three choices worth recording:

- **%-of-EGR / %-of-PGR resolves self-consistently in the fixed point, not
  as a single excluding-itself pass.** Spec §4.1 step 9 describes a
  %-of-EGR revenue line as referencing "EGR excluding themselves … a single
  second pass suffices," and §6 repeats that the single pass holds for
  revenue items. A property-revenue line *is* part of PGR/EGR, so it is
  genuinely self-referential; rather than build a second, subtly different
  resolution path, it joins run.py's existing %-of-revenue fixed point (the
  management-fee loop). The converged value is therefore rev = pct × *final*
  EGR (i.e. pct/(1−pct) × EGR-excluding-the-line), the self-consistent
  figure — not pct × EGR-excluding-the-line. The two differ only for a
  %-of-EGR/PGR property-revenue line, of which **no golden fixture has one**
  (Freeport's parking/other/pylon are all absolute-dollar lines), so the
  choice is **externally unvalidated** until a deal uses it; the fixed-point
  form is the established engine pattern and the contraction bound already
  covers it (its pct adds to the Σ share×pct factor of §6).
- **`pct_of_account` property revenue is deferred.** It references another
  ledger account, the same dependency the expense `pct_of_account` unit
  defers; run.py refuses it loudly and the module raises as a backstop. No
  fixture needs it. First deal that does drives the account-reference
  threading.
- **`spaces_times_rate` (parking) treats the rate as an annual amount per
  space** — monthly = number_of_spaces × amount / 12, occupancy-scaled by
  `pct_fixed` like the other absolute units. The manual gives no numeric
  example and no golden uses this unit (Freeport's parking is a
  `dollars_per_year` line), so the annual-per-space convention is a
  documented assumption to confirm against the first deal that uses it.
- **General vacancy / credit loss apply to property revenue in the
  percent-of-PGR base** (the vacancy module's existing contract — property
  revenue is added to the PGR base unless `include_in_pgr_accounts` narrows
  it). Whether a given OM subjects parking/misc income to general vacancy is
  a golden-comparison (Step 7) question; the engine follows the spec's
  PGR-inclusive definition by default.
- **Revisit when:** the Freeport golden #2 comparison (Step 7) exercises the
  absolute-dollar path against published figures; a future retail/mixed deal
  with a %-of-EGR misc line or a `spaces_times_rate` parking line validates
  the remaining choices.

## 14. Golden #5 (Inland Logistics Center) disqualified; Gate 2 reduced to two goldens (owner decision 2026-07-09)

**This is the permanent record of a deliberate, documented scope
reduction — not a silent drop.**

- **What happened:** golden #5 was to be the Inland Logistics Center
  (NMRK OM, staged untracked at `tests/golden/inland/source/` from the
  2026-07-03 deal triage). The Golden-File Strategy requires each golden
  to carry a **published Argus-based cash flow** — that provenance is what
  makes a golden a valid external reference for the engine. Inland's own
  Step 0 verification check (NEXT_STEPS_TO_GATE2.md, owner-approved
  2026-07-05) anticipated the risk: no Argus attribution exists in the
  document's text layer, so the check required confirming provenance from
  the page images. **The check failed (2026-07-09): full-text search plus
  visual inspection of the cover, cash flow, and assumptions pages found
  zero ARGUS attribution anywhere, and no outside evidence exists that
  the OM's cash flow is Argus-based.** (Contrast: Freeport's and Cedar
  Alt's OMs both carry explicit Argus footnotes — Cedar Alt's names
  "Argus Enterprise Version 14.0.2" on its cash flow page.)
- **Decision:** golden #5 is **permanently disqualified**. **No
  replacement deal is being pursued right now** (owner resource
  constraint). **Gate 2 is formally reduced from three required goldens
  (#2, #4, #5) to two (#2 Freeport, #4 Cedar Alt).**
- **Coverage consequence:** #4/#5 were the triage slots for gross-ups,
  caps, and absorption coverage. That coverage now rests on #2 (Freeport:
  base-year stops, 95% gross-ups, absorption, general/static vacancy) and
  #4 (Cedar Alt: two-building NNN rollover, non-binding caps) alone; the
  overall validation basis is four goldens (#1, #2, #3 standing intake,
  #4) rather than five. If a qualifying deal with confirmed Argus
  provenance surfaces later, re-opening a fifth slot is an owner
  decision, not a standing intake.
- **Artifacts:** the Inland OM stays at `tests/golden/inland/source/`
  (untracked, never committed) with a README marking it
  staged-then-disqualified so it is not mistaken for active work. No
  fixture, transcription, or comparison test was ever built for it.
- **Documents updated with this decision (2026-07-09):** CLAUDE.md
  (Golden-File Strategy list + Phase 2 gate row), BUILD_SCHEDULE.md
  (status note, Week 6 scope, GATE 2 checklist), NEXT_STEPS_TO_GATE2.md
  (criteria, Steps 0/7/9, status), ARGUS_REBUILD_SPEC.md (§9.1 golden
  list, §10 Phase 2 gate), this section. NEXT_STEPS_TO_GATE1.md's Inland
  references are a closed historical record and stand as written.
- **Revisit when:** never expected — the disqualification is evidence-
  based and permanent for this OM. A future fifth golden requires a new
  deal with confirmed Argus provenance and a fresh owner decision.

## 15. Tenant miscellaneous items: v1 narrowings (spec §3.12; §4.1 pass 8)

Built 2026-07-11 (`engine/calc/misc_items.py`) — the carried-forward item
NEXT_STEPS_TO_GATE3.md Step 0 flagged (run.py's guard had a stale "Phase 2"
label; Phase 2 closed without it because no golden needed it). Contract
terms carry the lease's items [AE pp. 378-381], speculative segments their
MLP's [AE pp. 240-244], occupied months only (the Step 2 convention), on the
Miscellaneous Tenant Revenue line, inside PGR/EGR and both general-vacancy
bases, with the Lease Audit reconciliation extended. Narrowings:

- **"% of Rent" input method not modeled** (with its Rent Components picker
  [AE p. 379; pp. 241-242]): `MoneyUnit` pct units fail loudly. The four
  $/period units cover the manual's Amount-1 and $/Tenant-Area methods at
  both frequencies; the schedule generalizes through the shared `Timing`
  machinery [AE pp. 278, 361-362] rather than the manual's two-value
  frequency picker.
- **Incentives not modeled (schema-absent):** the manual's separate
  owner-cost grid [AE pp. 381-382] (moving expenses, lease-break fees,
  recoverable %, spread-over-remaining-term recovery) has no §3.12 field
  and cannot be requested. First deal needing it drives the schema.
- **Tenant-group linking not modeled:** items attach per lease / per MLP,
  not to "pre-defined tenant groups" [AE p. 379].
- **Limits are absolute monthly $ min/max** (the shared `Limits` clamp
  [AE p. 279 convention]); the manual's per-area limit bases
  ($/SF-or-tenant-area per year/month [AE pp. 380-381]) are not modeled.
- **Inflation defaults to the general index** (revenue-side convention,
  matching property revenues); the manual's per-item index picker
  [AE p. 380] maps to `InflationRef`.
- **Free-rent abatement requires both opt-ins:** the item's
  `free_rent_abates` AND the profile's `abate_miscellaneous`
  [AE pp. 253-254], applied as the same fractional free-month series as
  `abate_recoveries`.
- **EXTERNALLY UNVALIDATED** (checked 2026-07-11): no golden fixture uses
  miscellaneous_items — manual-definition unit tests only
  (tests/unit/test_misc_items.py), the same standing as percentage rent
  pending golden #3.
- **Revisit when:** a deal with tenant misc items back-tests via the
  Benchmark Comparison report, or needs % of Rent / incentives / per-area
  limits.

## 16. TI/LC posting: v1 narrowings (spec §3.9; §4.1 pass 11)

Built 2026-07-11 (Phase 3 Step 1, `engine/calc/capital.py`). Both costs
post as a single lump sum in the month each lease segment starts — "All
tenant improvements are paid at the beginning of the lease" [AE p. 246],
"All leasing commissions are paid at the beginning of the lease"
[AE p. 247] — for contract and speculative segments alike (the contract
segment carries `Lease.leasing_costs` via an identity blend; speculative
segments the §4.2 probability-weighted MLP sides). LC "Fixed %" applies to
the entire lease value over the segment's full term — base rent plus fixed
steps less free rent, CPI excluded — even past the analysis end
[AE p. 247]; free rent reduces the base only when the segment's free-rent
profile abates base rent [AE p. 254]. Narrowings:

- **Timing distribution not modeled:** the manual's TI Timing / LC Timing
  grids (percentages across lease years, incl. years −2/−1 [AE pp. 246,
  248]) and `TICategory.payment_timing = spread` post nothing; lump-sum at
  segment start is the only shape (the manual's stated default: 100% in
  month/year one).
- **TI/LC categories refused loudly (schema-present, no calc consumer):**
  `TICategory`/`LCCategory` (spread timing, year tiers,
  `include_escalations` [AE pp. 258-262]) validate refs but
  `run_property` refuses `ti_category`/`lc_category` and chain resolution
  refuses `LCSpec.category_ref` — never silently dropped.
- **LC forms narrowed to Fixed % and $ forms:** the manual's
  "1st Month + %", "% by Lease Year" (per-year rates), and "# of Months at
  Initial Base Rent" [AE p. 247] are not representable; `LCSpec.pct_years`
  (spec §3.9) restricts the single-pct base to listed lease years instead.
  Blending % LCs whose `pct_years` differ between new/renew is refused (no
  defined weighting).
- **Speculative amounts inflate to segment start on the market index**
  (the `term_growth` factor market rents use; absorption leases inflate at
  generation to each lease's own start [AE p. 395]). The manual pages name
  no index for MLP TI/LC; golden #1's published rollover TI equals blended
  $/SF × area × the market factor exactly, so the golden is the evidence.
  Contract-side amounts are literal dollars; a contract segment starting
  before the analysis window posts nothing (paid pre-analysis).
- **TI units narrowed to $ Amount and $/SF:** "% of Rent (Year 1)" and
  custom categories [AE p. 245] are refused; any per-period `MoneyUnit` on
  a TI/$-LC fails loudly (not a one-time cost).
- **Revisit when:** a deal needs spread timing, category machinery, or the
  other LC forms; Gate 3's golden capital-line assertions are the external
  back-test (Clorox FY2029-FY2031; Freeport/Cedar Alt capital rows).

## 17. Purchase, closing costs, security deposits: v1 narrowings (spec §3.16/§3.12; Phase 3 Step 2)

Built 2026-07-12 (`engine/calc/investment.py`, [AE pp. 435-437, 384,
431-433] read). All three lines post **below the line** — new ledger
columns Purchase Price / Closing Costs / Security Deposits after CFBDS,
outside every NOI/EGR/CFBDS rollup: the ARGUS Cash Flow report carries no
acquisition rows (all three golden CSVs end at CFBDS) and the manual
frames purchase inputs as feeding "cash-on-cash metrics and returns, such
as the internal rate of return" [AE p. 435]; spec §4.1 pass 14 consumes
the price at t0 on the valuation side. The plan's "posting acquisition
flows ahead of CFBDS" is read accordingly: present in the ledger before
valuation consumes it, never inside the CFBDS rollup (test-proven: CFBDS
byte-identical with and without a purchase). Narrowings and judgment
calls:

- **Only the `fixed` price derivation is built.** `pv_at_discount_rate`
  and `direct_cap` (the manual's PV Net of Costs / Net Value /
  Capitalization / Direct Cap methods [AE pp. 435-436]) refuse loudly
  naming Phase 3 Step 5 — never a silent no-op.
- **Purchase date:** ARGUS fixes it at the Analysis Begin Date ("You
  cannot change this date" [AE p. 435]); the schema's optional `date` is
  honored when given (posts in that month). An out-of-window purchase or
  custom-date closing cost raises rather than silently dropping.
- **Closing-cost methods narrowed to $ Amount and % Purchase Price:**
  the manual's "% Total Price" (a percentage of purchase + closing —
  self-referential) is schema-absent; Vendors Fees % and Stamp Duty %
  are `pct_of_price` with a label [AE pp. 436-437].
- **Months-of-rent deposit basis (not a judgment call — manual-pinned):**
  "multiplied by the base rental revenue in the first month of the
  lease" [AE p. 432] — the segment's month-one base-rent level, gross of
  free rent (Base Rental Revenue posts gross of abatements; test-locked).
  Speculative segments size on the blended month-one rent.
- **Schema narrower than the manual's deposit profile:** no interest
  income on deposits, no "% to Refund" split, no paired
  refundable/non-refundable sections [AE pp. 431-433] —
  `refunded_at_expiration` is the 100%/0% poles. The MLP carries one
  deposit spec (the manual has New/Renew picks [AE p. 248]) — no
  new/renew blending is possible or performed.
- **Per-segment convention (judgment call):** each segment collects its
  own deposit at segment start and refunds in its final month
  ([AE p. 384]: "once the lease expires, the input under the leasing
  profile will be used") — a rollover refunds the expiring deposit and
  collects the successor's in adjacent months, not netted. A 100%
  renewal therefore shows a refund/recollect pair; accepted v1 churn.
- **Pre-analysis lease starts (judgment call):** the collection predates
  the window and posts nothing, but an in-window refund still posts —
  the refund is a real cash event regardless of when the deposit was
  taken. Test-locked.
- **EXTERNALLY UNVALIDATED** (checked 2026-07-12): no golden fixture
  populates `purchase` or `security_deposit` — manual-definition and
  engineered tests only (tests/unit/test_investment.py), the same
  standing as percentage rent, misc items, and reabsorb. Note: before
  this step, a populated `purchase` was **silently ignored** (no calc
  consumer, no guard); Step 2 closes that no-silent-numbers hole by
  consuming it.
- **Revisit when:** Step 5 builds the derived price paths; a deal needs
  deposit interest, partial refunds, or the % Total Price closing
  method; any future golden publishes below-the-line rows to back-test.

## 18. Debt engine: conventions and v1 narrowings (spec §3.17; Phase 3 Step 3)

Built 2026-07-12 (`engine/calc/debt.py`, [AE pp. 438-449] read in full).
**Validation path, stated plainly:** no golden fixture populates `loans`
and none will — validation is the closed-form worked-example tests
(tests/unit/test_debt.py) plus the **owner's bank-amortization-calculator
hand-check** (NEXT_STEPS_TO_GATE3.md Step 0), which for debt IS the
designed path, not a placeholder pending future data: standard mortgage
math is universal and externally checkable in a way OM cash flows are
not. Headline hand-check case: $1,000,000 at 6.00% amortized over 30
years → payment 5,995.51/mo, balance after 12 payments 987,719.88,
balloon if due in 120 months 836,857.25.

Part A adjudications (citation or manual-silent reasoning per item):

- **Monthly rate = annual/12**: the manual's default "12 Months" Calc
  Method [AE p. 443]. The closed form P × r / (1 − (1+r)^−n) is spec
  §3.17's normative statement — the manual never prints it. The 360-day
  and semi-annual Calc Methods [AE pp. 443-444] are schema-absent.
- **Floating resets (manual silent — chosen convention):** the manual
  models varying rates via the Interest Rate Editor [AE pp. 441-442] and
  never states payment behavior on a change. Chosen: on each
  effective-rate change (index YearRate + spread; year keyed per
  `inflation.timing_basis` like every other YearRate schedule), the
  payment re-levels to amortize the current balance over the remaining
  amortization horizon — the [AE p. 444] "recalculate ... over the same
  term" behavior applied to rate changes, and the only convention under
  which a floating fully-amortizing loan reaches zero at maturity.
- **Additional principal — manual answers directly [AE p. 444]:**
  Recalc Pmt Yes/No; the schema has no toggle, so the **"No"** behavior
  is modeled (payments unchanged, payoff shortens; paydowns clamp to the
  balance; a paid-off loan posts nothing further). First deal needing
  "Yes" drives a schema field.
- **Loan costs post to the financing section** ("These costs will appear
  on the Cash Flow report in the Financing section" [AE p. 446]) — not
  with Step 2's acquisition lines. The fee is a lump sum at funding (or
  the `timing` date). _**Superseded 2026-07-13 by §24 #3:**_ ~~`amortize`
  = straight-line over the loan term.~~ **Now:** `amortize` and `expense`
  post identically (the full cost at funding) — the distinction is an
  accounting (tax-basis) treatment this pre-tax cash model does not
  apply, so it is currently a no-op; the field is retained for a future
  tax module. The manual's Include-in-Loan financing, fee-frequency grid,
  and %-of-drawn/undrawn/max fee bases [AE pp. 445-446] are schema-absent.
- **"Other Debt" [AE pp. 448-449] is NOT modeled, and the Loan
  docstring's "modeled as fixed-payment loans" suggestion is
  insufficient:** the manual's Other Debt is recurring amount ×
  frequency × inflation streams listed in the debt-service section — a
  fixed-payment loan can represent only a level stream and would
  misreport it as interest + principal. No schema this session; a deal
  needing an inflated debt-section stream drives one.
- **Ledger financing section (spec §2.3 tree):** Debt Funding /
  Interest Expense / Principal Payments / Loan Costs / Total Debt
  Service (= the three payment lines) / Cash Flow After Debt Service
  (= CFBDS + Total Debt Service). **Debt Funding is display-only,
  outside the CFADS rollup** — ARGUS's "Show Loan Proceeds" defaults to
  No [AE p. 447], and spec §4.1 pass 14 builds leveraged IRR from
  "CFADS + equity at t0"; proceeds inside CFADS would double-count
  against that equity. Step 2's Purchase Price / Closing Costs /
  Security Deposits columns moved after the financing section (still
  below the line, still in no rollup).
- **Funding default:** purchase date if a purchase exists, else analysis
  begin ([AE p. 442] Loan Date default is Analysis Begin; Step 2's
  `Purchase.date` default is also analysis begin, so they coincide
  unless the owner moved the purchase). Pre-analysis funding is
  supported ("modeled back to their original start date" [AE p. 442]):
  the schedule computes from funding, only in-window months post, and
  the window opens at the loan's then-current balance. Payments run
  from the month after funding through maturity.
- **Balloon posting:** a balloon (amortization horizon > term, or
  interest_only) posts as a principal repayment in the maturity month
  ([AE p. 438] Quick Start — Balloon Payments); after maturity the
  balance is zero. Payoff-at-resale netting is Step 4's work — this
  step only guarantees the balance series is correct and retained.
- **`pct_of_value` loan amounts refuse loudly naming Step 5** ("% of
  Adopted Valuation" [AE p. 438] needs valuation), like the derived
  purchase price. Schema-absent manual features: Cap Rate/LTV% sizing,
  take-out loans, max loan amount/draws, Fund Operating Deficits
  [AE pp. 438-444], quarterly/semi-annual/annual payment schedules
  [AE p. 442] (schema is monthly-only), Amortize Start offsets, and the
  Item-to-Calc payment-solve [AE p. 443].
- **§9.3 debt invariants (standing from this step):** per-loan on every
  run — opening balance rolls from prior ending; balances never
  negative; interest-only months amortize nothing; a fully-amortizing
  loan's balloon is ~$0 (1¢ tolerance). Closed-form balloon/IO/floating
  values are locked in tests, not re-derived at runtime.
- **Revisit when:** Step 4 consumes the balance series for
  payoff-at-resale; Step 5 unlocks pct_of_value; a deal needs Other
  Debt, deficit funding, non-monthly schedules, or the Recalc-Pmt-Yes
  paydown behavior.

## 19. Property resale: conventions and v1 narrowings (spec §3.18; Phase 3 Step 4)

Built 2026-07-12 (`engine/calc/resale.py` + `engine/reports/resale_audit.py`,
[AE pp. 464-471] read in full). **Validation path, stated plainly:** no
golden fixture populates `valuation` and none ever will — no OM publishes
a valuation result (verified 2026-07-11). Validation is the manual's
worked-example tests (tests/unit/test_resale.py) plus engineered tests
and owner hand-checks; there is no external golden. Headline hand-check:
flat current-year NOI 100,000 at an 8.00% exit cap = 1,250,000 gross;
3% selling costs 37,500; net proceeds 1,212,500.

Part A adjudications (citation or manual-silent reasoning per item):

1. **`gross_value_less_costs` = "CAP Effective Gross Rents (12 Months
   After Sale)" [AE p. 465]**, the only other cap-rate-required method in
   the manual's list [AE p. 467 note]. It differs from the CAP NOI
   methods in the **income basis**, not the inputs: it capitalizes "net
   effective gross rents (effective gross revenue − recoveries)"
   [AE p. 465] over the same forward-12 window, not NOI. The schema name
   is a poor label for that definition; mapping recorded here so a reader
   isn't misled by "less costs" (it is EGR less recoveries, not a
   gross-value-less-selling-costs method).
2. **`cap_noi_current_year` = "CAP NOI (Year of Sale)" [AE p. 465]**; the
   "year of sale" is the reporting-year bucket ("the resale year"
   [AE p. 469]), implemented as the **analysis year** (12-month block
   from analysis begin) containing the resale month — not a trailing-12
   or fiscal window (the manual frames every resale-year figure in
   reporting-year terms).
3. **`cap_noi_forward_12` window is resale month +1..+12, relative to the
   resale date**, not fixed to analysis end. The ledger already extends
   analysis end + 12 months (spec §2.3) so a default (analysis-end)
   resale's window is fully materialized; a mid-analysis resale's window
   is earlier and equally available. `analysis_end_month()` derives the
   true final analysis month as `months[-13]` and the resale date is
   **capped there** — the look-forward months are not saleable (a resale
   in them would have no 12-month NOI window). Confirmed the existing
   timeline supports an arbitrary forward-12 slice (it is a plain
   PeriodIndex range), so no new machinery was needed.
4. **`exclude_capital` [AE pp. 470-471] default=True is a genuine no-op
   here, by construction:** the ledger's NOI line already excludes TI/LC/
   capex (Step 1: CFBDS = NOI + Total Capital Costs, so capital sits
   *below* NOI). Using the NOI line as-is is exactly "exclude capital."
   `False` deducts the window's Total Capital Costs. _**Superseded
   2026-07-13 by §24 #5:**_ ~~`False` **adds** the window's Total Capital
   Costs back into the basis (then divides by the cap) — the all-or-
   nothing Deductions grid.~~ **Now:** `False` subtracts the window's
   Total Capital Costs from the sale VALUE **once**, after capitalization
   (not from the NOI basis) — a one-time deduction per [AE p. 471], not a
   perpetual capitalization (§24 #5). The schema (a single bool, no
   per-line #Months) still cannot express the per-line grid in full. The
   manual's warning that TIs/LCs treated as operating expenses
   double-count [AE p. 471] does not apply — the engine never posts them
   as operating.
5. **`stabilize_occupancy` uses the printed ratio "NOI × Gross Up % /
   Average Occupancy %" [AE p. 469]** (the "% of Occupancy" gross-up
   basis), where Average Occupancy % is the mean of the run's occupancy
   series over the method's own NOI window. This is faithful to the
   manual's stated formula and touches only the resale basis — the ledger
   is never recomputed (spec §4.1). The manual's more elaborate
   "Lag Vacancy" basis [AE p. 470] (market value of downtime + vacant
   space + GV add-back) is schema-absent; `StabilizedOccupancy` carries
   only a target percent, so the simple % of Occupancy ratio is the
   correct match. **Scaling the WHOLE NOI — including fixed,
   non-occupancy-sensitive expenses — is the inherent behavior of the
   "% of Occupancy" formula [AE p. 469], not a defect; the more granular
   Lag Vacancy method [AE p. 470], which grosses up only the
   occupancy-sensitive tenant revenue, is the schema-absent alternative
   (Codex #6, ANSWERED — DEVIATIONS.md §24).**
6. **`adjustment_amounts` apply to the capitalized value BEFORE selling
   costs [AE pp. 465, 471]:** the manual's Capitalization Valuation
   Results pane subtracts adjustments to reach "the gross sale price",
   then subtracts selling costs from the gross to reach the net. So
   selling costs are a percent of the *adjusted* gross, not the
   pre-adjustment value. Signed dollars (negative reduces proceeds).
7. **Loan payoff uses the resale month's month-end ending balance**
   (`LoanSchedule.balance[resale_month]`, Step 3's series) — the balance
   *after* that month's scheduled payment, consistent with how Step 3
   indexes the schedule (payments run funding+1..maturity; the balance
   series holds each month's ending balance). Leveraged net = unleveraged
   net − Σ payoffs.
8. **End-of-month sale convention (Codex #10, ANSWERED — DEVIATIONS.md
   §24):** the model is monthly-granularity, so a resale date snaps to
   its month (`_resale_month`) and the sale is treated as occurring at
   that month-end — the investor owns the property through the resale
   month (its operating CFBDS/CFADS is included in the holding stream),
   collects the sale proceeds, and pays off each loan at the month-end
   balance (item 7). This is internally coherent; intra-month timing is
   not representable and is not modeled.

Other narrowings / decisions:

- **Ledger placement:** two new below-the-line columns after Step 2/3's
  columns — **Net Resale Proceeds** (net *unleveraged*, positive in the
  resale month) and **Loan Payoff at Resale** (Σ payoffs, negative,
  same month). The leveraged net is their visible sum, not a silent
  netting. In no rollup: the ARGUS Cash Flow report carries no resale
  row and the PV analysis consumes resale separately (spec §4.1 pass 14);
  CFBDS/NOI/CFADS are unchanged (test-locked).
- **`apply_resale_to_cash_flow=False`** computes the full cascade and
  retains the `ResaleResult` (and the Resale Audit reconciles) but posts
  nothing to the ledger.
- **`fixed_amount` ("Enter Sale Price") admits no selling costs or
  adjustments** — "used as the gross sale price AND net sale price"
  [AE p. 465]; populating them is refused loudly, not silently ignored.
- **`pct_increase_over_price` ("Inflate Purchase Price")** is narrowed to
  the schema's single TOTAL percent over the purchase price, not ARGUS's
  annual inflation-rate-over-hold-years field [AE p. 466]; requires a
  purchase price.
- **Only `valuation.resale` is consumed this step.** `direct_cap` is
  optional-with-no-consumer and is **refused loudly** (Step 5), closing
  the silent-numbers hole the way `purchase` was closed in Step 2; the
  discount_rate/method/convention/sensitivity machinery is untouched and
  read nowhere yet (Step 5).
- **Schema-absent manual features:** multiple named resale methods with a
  default pick [AE p. 464]; Gross Income Multiplier / Traditional /
  Capitalization / Leasehold calc methods [AE p. 465]; Add Back Free Rent
  [AE p. 469]; the Lag Vacancy gross-up basis and the per-line Deductions
  #Months grid [AE pp. 470-471]; varying exit cap over time [AE p. 466].
- **§9.3 payoff-at-resale invariant (standing from this step):** on every
  run with both a resale and loans, each payoff equals that loan's
  resale-month balance and leveraged net = unleveraged net − Σ balances
  (`assert_resale_invariants`).
- **Revisit when:** Step 5 unlocks direct cap and consumes resale in PV/
  IRR; a deal needs a multiplier/traditional method, Add Back Free Rent,
  the Lag Vacancy basis, or per-line deduction months.

## 20. PV / IRR / direct cap: conventions and the price-derivation scope decision (spec §3.18/§4.1 pass 14; Phase 3 Step 5)

Built 2026-07-12 (`engine/calc/valuation.py`, [AE pp. 450-476, 453-454,
472-473] read). **Validation path, stated plainly:** no golden populates
`valuation` and none ever will (no OM publishes a valuation result,
verified 2026-07-11) — proven by closed-form worked-example tests
(tests/unit/test_valuation.py), engineered tests, the §9.3
self-consistency invariant, and an owner Excel NPV()/IRR() hand-check.
Headline hand-check: the par stream −1,000,000 then 80,000 × 4 and
1,080,000, annual end-of-period at 8% → PV 1,000,000, IRR 8.00%.

Part A adjudications:

1. **Cash-flow basis (spec §4.1 pass 14).** _**Partly superseded
   2026-07-13 by §24 #1/#2** — the t0 construction below changed; the
   stream basis (CFBDS/CFADS + resale) did not._ ~~unleveraged =
   ledger CFBDS per month + Net Resale Proceeds (unleveraged) in the
   resale month, t0 = purchase price; leveraged = CFADS + leveraged net
   resale (Net Resale Proceeds + Loan Payoff at Resale), t0 = equity =
   price − loan funding proceeds. Below-the-line items (closing costs,
   deposits) are NOT in the stream ... folding closing costs into t0
   would break the §9.3 identity.~~ **Now:** t0 (both streams) = price +
   t0 closing/financing costs; leveraged equity nets only day-one-funded
   loan proceeds, with later draws posting at their funding month; the
   §9.3 identity is restated around "value net of costs" (§24 #1/#2).
   The stream basis is still CFBDS/CFADS + resale.
2. **Six conventions:** {annual, quarterly, monthly} × {end_of_period,
   mid_period}. The rate is an APR [AE p. 472]; periodic = APR/p. The
   monthly stream aggregates into p-per-year buckets from pv_start, each
   discounted at (1 + APR/p)^(−e), e = 1-based period index (end) or
   index − 0.5 (mid, the [AE p. 472] half-period). t0 price at exponent
   0. The manual's "Present Value Calculation Examples" is a hyperlink
   with NO inline printed worked-number table in this PDF; the spec §4.1
   DF formulas are the normative source, and the tests use closed-form
   textbook streams (owner-verifiable in Excel).
3. **IRR annualization — the spec is internally inconsistent, decision
   recorded:** spec §4.1 says both "(1+r/12)^−m" (nominal APR/12
   discounting) AND "annualized ((1+irr_m)^12−1)" (effective). These
   cannot both hold for self-consistency: with nominal discounting,
   price = PV forces the periodic IRR to APR/p, which annualizes back to
   the APR only under **nominal (periodic × p)** annualization. Effective
   annualization would report (1+APR/12)^12−1 ≠ APR and break the §9.3
   "IRR = discount rate" invariant (and ARGUS's core "value = PV such
   that IRR = discount rate" identity). **Chosen: nominal annualization**,
   matching the manual's APR label and the spec's DF formula; the spec's
   effective clause is overridden. This changes the reported IRR
   materially at any real rate — flagged, not silent.
4. **pv_start (default analysis begin)** is the discounting anchor and
   t0; cash flows before it are excluded and exponents measured from it.
   The resale month (≤ analysis end, Step 4) is discounted at its own
   period index relative to pv_start; a specified late pv_start shortens
   the horizon but the resale still lands in its actual month's bucket.
5. **direct_cap NOI basis [AE pp. 453-454]:** value = NOI / (cap_rate),
   anchored at pv_start. `year_1` = analysis year 1 (the first 12 ledger
   months); `forward_12` = the 12 months forward from pv_start. They
   coincide when pv_start = analysis begin and are a DISTINCT window from
   resale's `cap_noi_forward_12` (anchored at the resale date, Step 4) —
   implemented as logically separate derivations.

Leveraged metrics return **None** (not a silent zero) when their inputs
are absent: leveraged PV/IRR require loans; leveraged and unleveraged IRR
require a purchase price (the t0 investment). Only-price-absent still
yields the unleveraged PV.

### Part A #6 — price derivation / pct_of_value: OPEN OWNER SCOPE DECISION (not built)

The finding, plainly: this is **not uniformly circular, but not
uniformly clean**:
- **Unleveraged PV depends on neither the purchase price nor debt** (CFBDS
  is pre-debt-service; the purchase is below-the-line). So deriving the
  purchase price from the unleveraged PV / direct cap is **non-circular**
  — EXCEPT the `pct_increase_over_price` resale method, which reads the
  purchase price (price → resale → unleveraged PV → price is genuinely
  circular).
- **A `pct_of_price` or `pct_of_value` loan sized off a derived price**
  needs that value **before pass-12 debt** runs, while valuation is
  pass 14 — a pass **reordering** (compute unleveraged valuation before
  debt), not a fixed point. Only fixed-$ loans avoid it.

So a clean subset exists: derive price from unleveraged PV / direct cap
when there are no price-dependent loans and the resale method isn't
`pct_increase_over_price`. But even that clean subset needs Step 2's
acquisition-flow posting deferred past valuation and the below-line
columns re-assembled — real architecture for a path **no golden and no
current deal needs**. **Decision (2026-07-12): NOT built this step.** The
three derivations stay refusing, with messages rewritten to name this
actual open question (not "Step 5", which has happened):
`Purchase.derivation != fixed` (engine/calc/investment.py),
`LoanAmountBasis.pct_of_value` (engine/calc/debt.py). The §9.3
self-consistency invariant is proven **without** live derivation (Part C:
a fixed price set equal to a first run's computed PV). This is the
owner's scope call — recorded recommendation: the no-loan derived-price
subset is cleanly buildable as a post-valuation re-assembly if a deal
needs it; the loan-participation cases need the pass reorder. Nothing is
half-built; the whole derivation surface is a single loud refusal.

- **Schema-absent / not modeled:** Increment Discount Rate adjustments
  (separate unlev/lev cash-flow and resale rate deltas [AE p. 473]);
  Semi-Annual and "Monthly in Advance" discount methods [AE p. 472]
  (schema has annual/quarterly/monthly × end/mid only); Traditional and
  Capitalization Valuation calc paths and their overrides
  [AE pp. 474-475]; leveraged Increment rates.
- **§9.3 self-consistency invariant (standing from this step):** whenever
  a purchase price equals the computed unleveraged PV (within 1¢), the
  unleveraged IRR equals the discount rate within 1bp
  (`assert_pv_irr_self_consistency`), across every discount convention.
- **Revisit when:** the owner decides to build live price derivation (per
  the finding above); a deal needs Semi-Annual discounting, the Increment
  rates, or a Traditional/Cap valuation path.

## 21. Sensitivity matrices + a valuation holding-stream correction (spec §3.18/§7 reports 5-6; Phase 3 Step 6)

Built 2026-07-12 (`engine/calc/sensitivity.py`, [AE pp. 451-452] read).
**EXTERNALLY UNVALIDATED:** no golden populates `valuation`; proven by
engineered tests and the plan's cross-check — every matrix cell equals a
direct single-point Step 4/5 call with those substituted inputs
(tests/unit/test_sensitivity.py::TestCrossCheck). Pure re-computation
over the assembled RunResult; the ledger is never recomputed (spec §4.1).

Part A adjudications:

1. **Axes (spec §7 reports 5-6):** value matrix = unleveraged PV over
   discount rate (rows) × exit cap (columns); IRR matrix = IRR over
   price (rows) × exit cap (columns). The manual [AE pp. 451-452] gives
   only the interval/step sizes, not the grid layout (that is the report
   rendering, Phase 4). **Which IRR:** the spec says only "IRR"; built as
   **both** an unleveraged IRR matrix (primary — the price axis is an
   unleveraged-PV concept) and a parallel leveraged IRR matrix on the
   same axes, the latter all-NaN without loans (Part D #11; never a
   silent zero).
2. **Grid centered on the base case (manual silent — chosen):** the
   manual states the step but not the arrangement; `count` ∈ {5, 7} is
   odd, so the grid is centered on the base with `±k × step` points — the
   standard sensitivity-matrix convention, and the odd count guarantees a
   center cell equal to the exact base case (where the §9.3
   self-consistency appears: center IRR = the base discount rate).
3. **Price axis = unleveraged PV at the discount-rate grid, at the BASE
   exit cap** ("prices at PV of rate grid", spec §7 report 5) = the
   base-cap column of the value matrix. This is a pure sensitivity axis
   computed by arithmetic on the existing streams — it never sets
   `model.purchase.price`, calls `run_property`, or touches
   `acquisition_flows`, so Step 5's price-derivation refusal
   (DEVIATIONS.md §20 #6) is untouched. Consequence: the IRR matrix is
   computable even with no fixed purchase price.
4. **No ledger recompute:** each column reuses `compute_resale` (Step 4)
   with a `model_copy` substituting the exit cap (reads the existing NOI
   window only); each cell reuses Step 5's `_period_buckets` /
   `_present_value` / `_solve_irr`. The exit-cap axis applies only to
   cap-NOI resale methods [AE p. 451]; for fixed/pct-increase resales
   there is no cap axis and sensitivity is `None` (not a fabricated grid).

### Valuation holding-stream correction (Step 5 fix surfaced here)

Building Step 6's hand-check exposed that Step 5's `compute_valuation`
discounted the ledger's CFBDS/CFADS over **all** timeline months —
including the 12-month resale look-forward beyond analysis end — when the
property is sold at the resale month (≤ analysis end). Post-resale cash
flows belong to the buyer; the look-forward exists only to value the
terminal cap-NOI (spec §2.3). Step 5's self-consistency tests passed
regardless (price = PV ⟹ IRR = discount holds for any stream shape), so
the error was latent. **Fixed (2026-07-12):** a shared
`valuation.holding_stream` truncates the operating series at the resale
month and adds the net resale proceeds there, taken from the
`ResaleResult` directly (not the posted ledger column — so it values
correctly even when `apply_resale_to_cash_flow` is False). Both
`compute_valuation` (Step 5) and the sensitivity streams use it, so PV
and the sensitivity value matrix agree. Effect: e.g. a flat NOI 100,000
property at an 8% discount/8% exit cap now values 1,250,000 (= NOI/cap)
rather than 1,313,017 (which had folded in a sixth year of ownership the
seller never had). No golden is affected (none set `valuation`).

- **Schema-absent / not modeled:** Purchase Price Interval and IRR
  Target [AE p. 452] (the schema has discount_rate_step / cap_rate_step /
  count only — the price axis is derived from the discount grid, not a
  price step); Resale Amount / Gross Income Multiplier intervals
  [AE pp. 451-452] (apply to non-cap resale methods, which have no
  sensitivity here).
- **Revisit when:** Phase 4 renders these as the §7 report 5-6 grids; a
  deal needs a price-step or GIM-interval axis.

## 22. Codex-review direct fixes (2026-07-12): loan-name uniqueness, additional-principal window, pv_start-vs-disposition, loan input bounds

An independent Codex review of `engine/calc/{debt,resale,valuation}.py`
surfaced 12 findings. Four are validation/guard fixes with no design
ambiguity — applied 2026-07-12 (tests in `tests/unit/test_debt.py`
::TestValidationFixes and `test_valuation.py`::TestPvStartAfterDisposition).
The other eight touch already-adjudicated cash-flow-basis or
numerical-method definitions and were written up for owner decision
(not implemented) — see the review hand-off, not this section.

- **#4 Duplicate loan names (`engine/models/property_model.py`
  `_check_unique_names`).** `resale.py` keys loan payoffs by
  `loan.name`; two loans sharing a name silently collapsed to one
  payoff entry, understating total debt payoff and overstating leveraged
  proceeds (the §9.3 payoff invariant caught it only when the two
  balances differed). `loans` now joins the other named collections in
  the uniqueness validator — duplicate loan names are refused at model
  load.
- **#11 Additional principal outside the loan's active window
  (`engine/calc/debt.py` `build_loan_schedule`).** An
  `additional_principal` dated before the first payment month
  (`funding + 1`) or after `maturity` never occurred in the schedule
  loop and was silently dropped. It now raises, naming the valid window
  — no silent numbers.
- **#9 `pv_start` after disposition (`engine/calc/valuation.py`
  `compute_valuation`).** `pv_start` was validated only against the full
  timeline (which includes the 12-month resale look-forward), not
  against the resale month. A `pv_start` after the resale month left the
  truncated holding stream empty, yielding a meaningless PV of 0. It now
  raises when `pv_start > resale_month`; `pv_start == resale_month` (a
  degenerate one-month hold) is still allowed. This also prevents the
  direct-cap `forward_12` window from overflowing the timeline.
- **#12 Economic sanity bounds on loan inputs
  (`engine/models/investment.py`).** A fixed rate is now constrained to
  0-100 percent (catching a rate typed as a decimal or as 650 for 6.5%);
  a floating spread to ±100; an integer amortization to ≥ 1 year; and
  `LoanCosts.points_pct`/`fees` to ≥ 0 (points ≤ 100). These reject
  obvious input errors rather than computing silent nonsense. The JSON
  Schema was regenerated (`scripts/export_json_schema.py`).

**Revisit when:** the eight scope-decision findings (leveraged-IRR
funding timing, closing costs in returns, amortized-loan-cost cash
timing, capital-cost capitalization in resale, multiple-IRR handling,
the IRR bracket's negative-rate floor, the end-of-month sale convention,
and the stabilize-occupancy whole-NOI scaling) are adjudicated by the
owner.

## 23. Codex-review corrections (2026-07-12): revenue-name uniqueness, recovery-cap partial-year baseline, vacancy exclusion by external_id

Three real bugs a second Codex review found in Phase 1/2 code. Each is a
**correction to previously wrong behavior** (not a narrowing), so the OLD
behavior and the NEW behavior are both stated, per the transparency rule.
No golden fixture exercises any of the three (verified: none uses growth
caps, tenant overrides, external_ids, or duplicate revenue names), so no
golden number moves.

**(1) Duplicate property-revenue names silently discarded revenue.**
`_check_unique_names` (engine/models/property_model.py) validated names
within each collection but never checked the three property-revenue lists
(`miscellaneous_revenues`, `parking_revenues`, `storage_revenues`).
`run.py`'s `rev_pct_series` keys the %-of-revenue fixed point by name
across all three combined, so two revenues sharing a name — even across
different lists — collapsed to one series entry.
- *Old:* two 10%-of-PGR revenues both named "Fee" on a $100 base solved
  to PGR = 100 + 10%×PGR = $111.11 (one silently dropped), cascading into
  EGR, vacancy, and recoverable %-fees.
- *New:* names must be unique across the three lists combined (a single
  "property revenues (miscellaneous/parking/storage)" entry in the
  uniqueness validator); the collision is refused at intake. Two
  distinctly-named 10%-of-PGR revenues correctly solve to $125.00.
- A pre-existing unit test that summed three same-named revenues onto the
  one ledger line was updated to give them distinct names (its real
  intent — three items on one line — is unchanged).

**(2) Recovery growth caps used an unannualized partial first year as the
baseline.** In `_apply_caps_floors` (engine/calc/recoveries.py), when a
segment started mid-calendar-year, the first calendar year's raw dollar
total (e.g. one month) became the baseline against which the next FULL
year was capped.
- *Old:* a segment starting December 2026 at $1,000/mo with a 5% yearly
  cap set the baseline to $1,000 (one month), so 2027's $12,000 was
  capped to $1,000 × 1.05 = $1,050 — a 91% understatement.
- *New:* the growth-cap comparison is done in annualized run-rate terms.
  Each calendar year's total is annualized to a 12-month run rate
  (`raw × 12 / months_in_block`) — the same convention as the base-year
  stop (`_frozen_stop_annual`, DEVIATIONS.md §10, which the review noted
  and which stays) — before comparison. The December baseline annualizes
  to $12,000/yr, so 2027's $12,000 flows through uncapped; a genuine
  overshoot (2027 at $2,000/mo) is still capped to $12,600. For
  full-year (January-start) segments the run rate equals the raw total,
  so behavior is byte-identical — the existing YoY/cumulative cap tests
  are unchanged. Note §10's calendar-year-as-recovery-year convention is
  itself unchanged; this fixes only the missing annualization of a
  partial first/last year.

**(3) Vacancy/credit-loss tenant exclusion silently ignored external_id
refs.** `TenantOverride.tenant_ref` is documented and validated
(property_model `_validate_refs`) as either a `Lease.tenant_name` OR its
`external_id`, but `engine/calc/vacancy.py` `_excluded` collected raw ref
strings and compared them against the `tenants` dict, which is keyed by
`tenant_name` only.
- *Old:* an override whose `tenant_ref` was an external_id passed intake
  validation and then matched no tenant, so the exclusion had zero effect
  on general vacancy, credit loss, or anything downstream — a silent
  no-op.
- *New:* `run.py` builds a `tenant_name_by_ref` map (every tenant_name
  and external_id → tenant_name) once and threads it through
  `general_vacancy_series` / `credit_loss_series` → `_base_and_at` →
  `_excluded`, which resolves each ref to its canonical tenant_name
  before comparison. An external_id override now excludes the tenant, the
  same as the tenant_name form.
- **Bug-class sweep (as requested):** the only schema field accepting a
  tenant by name-OR-external_id is this `override.tenant_ref` (the sole
  field validated against the combined `tenant_refs` set at
  property_model.py). Recovery assignments reference expenses/structures
  by their own name sets (resolved consistently); the Lease Audit and
  Recovery Audit builders iterate the already-canonical `tenant_name`
  keys. No other instance of this name-vs-external_id resolution gap
  exists.

**Revisit when:** n/a — these are corrections, not deferrals.

## 24. Codex-review debt/resale/valuation findings — NEEDS-SCOPE-DECISION hand-off (2026-07-12)

The debt/resale/valuation Codex review (§22) produced 12 findings. Four
were validation/guard fixes with no design ambiguity and were implemented
(§22: #4 loan-name uniqueness, #9 pv_start-vs-disposition, #11
additional-principal window, #12 loan input bounds). The remaining **eight**
touch an already-adjudicated cash-flow-basis, numerical-method, or resale
convention (DEVIATIONS §18/§19/§20) and were reported for owner decision
rather than implemented. §22 pointed at a "review hand-off" for them; that
hand-off was never committed (it existed only in session terminal output).
This section is that write-up, recovered verbatim from the session report
and preserved here. **Nothing below is implemented — each item is OPEN for
owner adjudication before Phase 4.** No golden populates `loans` or
`valuation`, so none of these affects a golden number.

Per item: (a) file/function, (b) what the review flagged, (c) the existing
DEVIATIONS convention that governs it, (d) recommendation — real bug to fix,
or convention already answers it.

---

### #1 — Leveraged IRR treats all loan proceeds as day-one financing
- **(a)** `engine/calc/run.py:672` (`loan_proceeds = sum(s.funding.sum())`)
  and `engine/calc/valuation.py:257` (`equity = price - loan_funding_proceeds`,
  applied at t0 exponent 0).
- **(b)** The leveraged IRR nets *all* loan proceeds against the day-one
  equity, even for a loan scheduled to fund later (a construction/earn-out
  draw). The loan's monthly service is timed correctly in CFADS, but its
  cash proceeds are pulled forward to t0.
- **(c)** DEVIATIONS §20 item 1: "t0 outflow = equity = purchase price −
  loan funding proceeds" — this baked in the all-loans-fund-at-t0 assumption.
- **(d) REAL BUG for deferred/staged (and pre-window/assumed) funding.**
  Proposed fix: add each loan's proceeds as a positive cash inflow at its
  actual funding month; net only day-one-funded proceeds against t0 equity
  (fold in the assumed-existing-loan case in the same change). The common
  "loan funds at closing" case is already correct. **Dollar impact:** a $7M
  loan on a $10M deal funding 12 months post-close makes the engine report
  $3M day-one equity when the investor really puts in $10M and draws $7M a
  year later — understating the equity base enough to **overstate leveraged
  IRR by 10+ percentage points.**

### #2 — Closing costs (and upfront financing costs) excluded from returns
- **(a)** `engine/calc/valuation.py` `compute_valuation` / `holding_stream`
  (`holding_stream` line 134): the unleveraged t0 outflow is the purchase
  price alone; the stream is CFBDS/CFADS + resale only.
- **(b)** A real investor's day-one outlay is price + closing costs (+ any
  upfront financing costs), not price alone, so reported returns are
  overstated.
- **(c)** DEVIATIONS §20 item 1: "Below-the-line items (closing costs,
  deposits) are NOT in the stream ... folding closing costs into t0 would
  break the §9.3 identity." (Deliberate and documented — the owner asked
  that the *decision itself* be re-examined, not just noted.)
- **(d) DELIBERATE, but the decision is worth revisiting — the finding is
  economically right.** Why it's excluded: the §9.3 self-consistency check
  ("the value that makes IRR = the discount rate") is defined around price
  alone; adding closing costs to t0 breaks that identity as written.
  Proposed fix: include price + closing (+ upfront financing) in t0 and
  restate the self-consistency identity around "value net of costs" — which
  is what ARGUS's "PV Net of Costs" actually means. This redefines a shipped
  invariant, so it is the owner's call. **Dollar impact:** on a $10M deal
  with 2% closing costs ($200k), unleveraged IRR is overstated by roughly
  **0.3–0.5 percentage points** over a 5-year hold; leveraged IRR is more
  sensitive (smaller equity base) — often **0.5–1.0+ points.**

### #3 — "Amortized" loan costs modeled as monthly cash installments
- **(a)** `engine/calc/debt.py:312-313` (the `amortize` branch:
  `monthly = cost / term`, spread as negative cash over the loan term).
- **(b)** Amortization is an accounting treatment — the cash is paid upfront
  at funding; the spreading is a non-cash bookkeeping entry (relevant only
  to taxable income, which this pre-tax model does not track). Posting the
  amortized amount as monthly cash misstates CFADS and leveraged IRR.
- **(c)** DEVIATIONS §18: "`amortize` = straight-line over the loan term
  (manual silent on the schedule)."
- **(d) REAL issue for a pre-tax cash model.** Proposed fix: in a pre-tax
  cash model both `expense` and `amortize` should post the cash at funding
  (they would behave identically), or the amortized amount should be
  excluded from cash flow entirely. **Dollar impact:** modest — $100k of
  loan costs on a 10-year loan defers ~$833/month of cash that was really
  spent on day one, shifting leveraged IRR by a few tenths of a point.

### #5 — One-time capital costs capitalized as perpetual NOI reductions
- **(a)** `engine/calc/resale.py:175` (`capital_adjustment` = the window's
  Total Capital Costs) and `:186` (`adjusted_basis = income_basis ×
  occupancy_factor + capital_adjustment`, then `/ exit_cap_rate`), on the
  `exclude_capital=False` path.
- **(b)** The capital spend in the resale window is added to the annual NOI
  basis and then divided by the exit cap rate — capitalizing a one-time cost
  into perpetuity, treating it as if it recurs every year forever.
- **(c)** DEVIATIONS §20 item 4: "`exclude_capital=False` adds the window's
  Total Capital Costs into the basis."
- **(d) REAL BUG, and it contradicts the manual — NOT the same as any §22
  direct fix.** (Explicit check per the owner's note: this is the
  `exclude_capital=False` path, and it was classified NEEDS-SCOPE-DECISION,
  *not* one of the four implemented direct fixes (§22: #4/#9/#11/#12); it
  remains open.) The manual (AE p. 471) deducts these costs from the resale
  *value* once, not from the income basis. Proposed fix: subtract the
  capital costs from the gross sale value directly (one-time), not from the
  NOI basis before capitalizing. **Dollar impact (highest of the eight):** a
  $500,000 one-time TI/LC in the resale window at an 8% exit cap currently
  reduces the sale value by **$6.25M** ($500k ÷ 0.08) instead of the correct
  **$500,000** — a ~$5.75M error per deal, in the conservative direction
  (it understates the sale price).

### #6 — Occupancy stabilization scales all NOI, including fixed expenses
- **(a)** `engine/calc/resale.py:185` (`occupancy_factor` = target ÷ average
  occupancy) applied to the whole `income_basis` at `:186`.
- **(b)** The gross-up scales the entire NOI — including fixed,
  non-occupancy-sensitive expenses — not just the occupancy-sensitive
  revenue.
- **(c)** DEVIATIONS §19 item 5: `stabilize_occupancy` implements the
  manual's "% of Occupancy" formula, NOI × Gross-Up% ÷ Average-Occupancy%
  [AE p. 469]; the granular "Lag Vacancy" basis [AE p. 470] is schema-absent.
- **(d) NOT a bug — the convention already answers it; ANSWERED, not open.**
  The engine implements the manual's "% of Occupancy" formula literally, and
  that formula by definition scales the whole NOI. The more granular "Lag
  Vacancy" method (which grosses up only tenant revenue) is the alternative,
  is schema-absent, and is already documented in §19 item 5. Recommendation:
  sharpen §19 item 5 with one line stating explicitly that whole-NOI scaling
  is the inherent crudeness of "% of Occupancy" versus Lag Vacancy — a
  documentation tweak, no code change. **Dollar impact:** n/a (faithful to
  the chosen method).

### #7 — IRR solver can miss or mishandle multiple IRRs
- **(a)** `engine/calc/valuation.py:149` (`_solve_irr`): bisection on a fixed
  bracket, returns `None` when the endpoints do not bracket a sign change.
- **(b)** The solver assumes a conventional cash-flow pattern (money out
  once, money in thereafter). Deals with interim negative cash flows (a large
  mid-hold capital event, or the deferred-funding case #1) can have zero,
  one, or several valid IRRs; the solver may return one arbitrary root or
  return `None` even when IRRs exist, without flagging the ambiguity.
- **(c)** DEVIATIONS §20 (IRR method): "one sign change → a unique root,
  bisection" — assumes conventionality.
- **(d) REAL robustness gap.** Proposed fix: count sign changes in the
  stream; if more than one, flag the result as potentially non-unique or
  refuse with an explanation, rather than silently returning one root or
  `None`. **Dollar impact:** not a single number — when it bites, the
  reported IRR could be a misleading single value or an unexplained `None`.

### #8 — The IRR bracket's negative-rate floor excludes valid large-loss IRRs
- **(a)** `engine/calc/valuation.py:85` (`_IRR_LOW_PCT = -99.0`, an annual
  percent) used by `_solve_irr`.
- **(b)** The search floor of −99% annual is far above the mathematically
  valid floor for the monthly/quarterly conventions (the periodic rate need
  only exceed −100%, so annual nominal extends to −1200% monthly). Valid
  very-negative IRRs below −99% annual are excluded — the solver returns
  `None` for a catastrophic-loss deal that does have an IRR.
- **(c)** DEVIATIONS §20 item 3 (nominal IRR annualization; the bracket is
  not convention-aware).
- **(d) REAL, low practical impact, and the cleanest of the eight to fix.**
  Confirmed with a worked example: a deal returning 0.5% of the investment
  over 5 years (monthly convention) has a valid IRR of **−101.42%**, but the
  solver returns `None`. Proposed fix: make the bracket floor convention-aware
  (just above −100 × periods-per-year %). **Dollar impact:** none directly —
  it is "no answer" vs. "correct very-negative answer," and few real deals
  lose >99%/year. This one could reasonably be applied as a direct fix; it
  was held here only because it is entangled with #7 and both are
  numerical-method changes.

### #10 — End-of-month sale timing assumed but not enforced
- **(a)** `engine/calc/resale.py` (`_resale_month`, which snaps the resale
  date to a month) and `engine/calc/valuation.py` `holding_stream` (the
  resale month keeps its operating CFBDS/CFADS, plus the sale proceeds, plus
  the loan payoff at the month-end balance).
- **(b)** The model assumes the sale happens at month-end (collect the resale
  month's income, sell at the month-end balance) without enforcing it; a
  mid-month sale date just snaps to the whole month.
- **(c)** Not explicitly documented — implicit in "resale posts in the resale
  month" (§19/§20).
- **(d) PARTIALLY accurate but NOT a bug — ANSWERED (documentation).** The
  model is monthly, so intra-month timing is not representable, and the
  convention (own the property through month-end, collect that month's
  income, sell at the month-end balance) is internally coherent.
  Recommendation: document the end-of-month convention explicitly (a doc
  note); no code change, and no scope decision unless intra-month timing is
  wanted (a large change with no current demand). **Dollar impact:** none for
  a monthly model.

---

**Adjudication priority (recommended):** #5 first (largest dollar error,
clear manual guidance), then #1 and #2 (return accuracy on leveraged and
closing-cost deals), then #3 / #7 / #8 (smaller or lower-frequency), with #6
and #10 as documentation touch-ups. Each has a specific proposed fix above;
none is implemented pending owner decision.

---

### Owner adjudication (2026-07-13) — six FIX, two ANSWERED

Topper adjudicated all eight items 2026-07-13. Six are fixed (with tests);
two are answered as documentation-only. No golden populates `loans` or
`valuation`, so the four pre-existing golden reds (137/47 Gate 2; 33/12
Gate 3 capital) are unchanged.

- **#5 — CLOSED (fixed 2026-07-13).** `resale.py` now deducts the resale
  window's Total Capital Costs from the sale VALUE once, after
  capitalization, instead of adding them to the NOI basis (which
  capitalized a one-time cost). §20 item 4 superseded. Tests:
  `test_resale.py::TestNOIAdjustments::test_exclude_capital_false_deducts_capital_from_value_once`
  and `::test_capital_deduction_is_dollar_for_dollar_500k` ($500k cost →
  $500k value reduction, not $6.25M). The audit report shows the deduction
  as "Capital costs deducted".
- **#3 — CLOSED (fixed 2026-07-13).** `debt.py`: `amortize` and `expense`
  loan-cost handling now post identically — the full cost at funding. The
  amortize/expense distinction is a tax-basis accounting treatment this
  pre-tax model does not apply, so it is a no-op for cash; the schema field
  is retained for a future tax module. §18 amortize line superseded.
  Tests: `test_debt.py::TestLoanCosts::test_amortize_posts_full_cost_at_funding_like_expense`
  and `::test_amortize_and_expense_have_identical_cash_timing`.
- **#1 + #2 — CLOSED (fixed together 2026-07-13, coupled).** `valuation.py`:
  the t0 outflow (both unleveraged and leveraged) now includes price + t0
  closing/financing costs, not price alone (owner reframe: "the numbers LP
  cares about is the actual return including closing costs"); each loan's
  proceeds post at its ACTUAL funding month, and leveraged equity nets only
  day-one-funded proceeds (plus any assumed pre-window balance), with later
  draws posting as stream inflows. `assert_pv_irr_self_consistency` restated
  around the total t0 outlay ("value net of costs = PV ⟹ IRR = discount
  rate"); the identity logic is unchanged. §20 item 1 superseded.
  `ValuationResult` gains `unleveraged_t0` and `leveraged_equity`. Tests:
  `test_valuation.py::TestT0Reframe` (closing/financing costs in t0;
  self-consistency net of costs; day-one nets, later-funding does not).
  No prior test encoded the old t0-is-price-alone convention (every
  existing valuation test used cost-free, t0-funded models where old and
  new t0 coincide); only the manual `ValuationResult` construction in
  `test_invariant_raises_on_inconsistent_irr` was updated for the two new
  fields, with a comment noting why.
- **#8 — CLOSED (fixed 2026-07-13).** `valuation.py` `_solve_irr`: the
  bisection floor is now convention-aware — a periodic floor of −99% × p
  (−1188% annual for monthly), so valid deeply-negative (large-loss) IRRs
  are reachable. Test:
  `test_valuation.py::TestIRR::test_large_loss_below_minus_99pct_now_solves`
  (0.5% returned over 5 years, monthly → IRR ≈ −101.42%, not None).
- **#7 — CLOSED (fixed 2026-07-13).** `valuation.py` `_solve_irr` counts
  sign changes on the input stream and RAISES when there is more than one
  (multiple IRRs may exist) rather than returning one arbitrary root or
  None (no silent numbers). Tests:
  `test_valuation.py::TestIRR::test_multiple_sign_changes_raises` and
  `::test_single_sign_change_still_solves`.
- **#6 — ANSWERED (documentation, 2026-07-13).** Whole-NOI scaling is the
  inherent behavior of the manual's "% of Occupancy" formula [AE p. 469],
  not a defect; the granular Lag Vacancy method [AE p. 470] is
  schema-absent. One sentence added to §19 item 5. No code change.
- **#10 — ANSWERED (documentation, 2026-07-13).** The end-of-month sale
  convention (monthly granularity; own through month-end; loan payoff at
  the month-end balance) is now stated explicitly in §19 item 8. No code
  change.

**Sensitivity-module follow-ups surfaced by these fixes — BOTH CLOSED
(fixed 2026-07-13):**
1. **CLOSED.** `sensitivity.py`'s IRR grids were reframed to match the
   corrected `valuation.py` t0 construction. The t0-cost and
   day-one-vs-staged-draw logic was extracted into two shared helpers,
   `valuation._t0_costs` and `valuation._apply_loan_proceeds`, which BOTH
   `compute_valuation` and `compute_sensitivity` now call (so they cannot
   drift again). The unleveraged IRR grid's t0 is now `−(price + t0
   costs)`; the leveraged grid's is `−(price + t0 costs − day-one
   proceeds)` with staged draws added as inflows per cap — identical to
   `compute_valuation`. Tests:
   `test_sensitivity.py::TestT0ReframeMirrorsValuation`
   (closing costs lower the unleveraged grid; the leveraged base cell
   equals `compute_valuation`'s own leveraged IRR — the §21 cross-check
   pattern; a staged draw is not netted at t0). Cost-free, t0-funded
   models are byte-identical to the prior behavior (existing grid tests
   unchanged).
2. **CLOSED.** The #7 multiple-IRR guard is now caught per cell in the
   grid builder (`sensitivity._safe_irr` wraps `_solve_irr`): a
   non-conventional stream NaNs that one cell instead of raising and
   killing the whole matrix. Test:
   `test_sensitivity.py::TestAmbiguousIrrCellNaN::test_mid_hold_capital_event_nans_cells_without_raising`
   (a $2M mid-hold capital event drives an interior-negative stream; the
   matrix computes with NaN cells, no exception). Neither item was a
   golden concern (no golden populates valuation).
## 25. Lease Expiration report (#12): the "SF sums to rentable" acceptance criterion was WRONG — diagnosis & correction (Phase 4 Step 4; spec §7 report 12) — DIAGNOSIS APPROVED 2026-07-13, CORRECTION IMPLEMENTED, AWAITING OWNER REVIEW OF THE FIX

**Status: diagnosis owner-approved 2026-07-13 with two amendments (folded
in below); the correction is implemented in one commit; no `engine/calc`
touched; no inputs tuned; the four by-design golden reds stay red (137/47
Gate 2, 33/12 Gate 3 capital).**

**The plan's acceptance criterion itself was defective — not the engine.**
Phase 4 Step 4 (commit 7796eb9) shipped the Lease Expiration report with
the acceptance criterion "Lease Expiration SF sums to rentable." That
criterion is **wrong**: a suite can turn over more than once over the
analysis term (legitimate turnover → cumulative expiring SF legitimately
exceeds 100% of the building), and a stated (fixed) rentable area need not
equal the sum of demised suite areas. The reconciler that "verified" it
(`reconcile_expiration_area`) was **tautological** — it subtracted the sum
of the contract-segment areas from the sum of the same contract-segment
areas, returning 0.0 on every input, incapable of failing. The defect was
in the plan's criterion (NEXT_STEPS_TO_PHASE4.md Step 4), which is hereby
withdrawn; the engine's numbers were never wrong.

**Owner verification (2026-07-13):** the [AE p. 818] Lease Status filter
quote is accurate (printed p. 818 = **PDF p. 819**); the suite-100 OKI
double-entry, the 123,193 distinct demised area (all 29 rent-roll chains),
and the 94 SF fixed-rentable gap all reproduce exactly.

### The observed fact (tests/golden/freeport/freeport.icprop.json)

`lease_expiration()` totals **128,087 expiring SF** against **123,099**
rentable — 104.1% of the building; the `pct_of_building` column sums to
1.041. The overage decomposes **exactly**:

| source | SF | nature |
|---|---:|---|
| suite 100 double-entry (OKI Data current + OKI Data (Renewal)) | +2,584 | legitimate turnover (two sequential contract leases, one suite) |
| absorption chain "Suite 395 remainder lease-up" (status speculative) | +2,310 | wrong status bucket — should not be lumped with contract |
| fixed-rentable vs summed-distinct-demised-area gap | +94 | OM load-factor/rounding; rentable is an independent input |
| **total overage (128,087 − 123,099)** | **+4,988** | |

### Q1 — why the 29 real chains sum to 125,777 vs 123,099 rentable

Two independent causes; the "derived rentable understating the building"
hypothesis is **false** — `area_measures.rentable_area_mode` is **`fixed`**
at 123,099 (freeport.icprop.json), an independent stated building metric,
not a sum of chains.

1. **A physical space is represented by two chains.** Suite 100 appears
   twice on the rent roll: `"OKI Data Americas Inc."` (suite 100, 2,584 SF,
   `upon_expiration=vacate`, contract 2016-08..**2027-01**) and `"OKI Data
   Americas Inc. (Renewal)"` (suite 100, 2,584 SF, contract
   **2027-02**..2032-06). These are the same physical 2,584 SF suite,
   re-leased back-to-back — a pre-signed second-generation lease entered as
   its own rent-roll row. Summing all contract-chain areas double-counts
   suite 100 (+2,584). Verified: both rows carry `suite='100'`, both
   `status=contract`, and their contract terms are exactly sequential
   (vacate 2027-01 -> renewal 2027-02).
2. **Fixed rentable != summed demised area.** After de-duping suite 100 the
   29 chains' distinct demised area is 123,193 SF — still **94 SF over**
   the stated fixed rentable (123,099). Rentable is an input, not the sum
   of suite areas, so a small load-factor/rounding gap across 29 suites is
   normal and expected in a real OM. (Suites 390 "Texian Operating" and
   390E "Texian Operating (Expansion)" are **distinct** physical spaces —
   not a duplicate.)

Evidence: `freeport.icprop.json` rent roll (the two suite-100 rows;
`rentable_area_mode: "fixed"`, `rentable_area_fixed: 123099`); confirmed by
loading the model and resolving the chains.

### Q2 — does ARGUS Lease Expiration include speculative / absorption leases?

**The manual treats lease status as a first-class, filterable dimension —
speculative is a separate, selectable category, not lumped into contract.**
[AE p. 818] Lease Expiration report parameters include an explicit **Lease
Status** filter: "Select the lease status categories you want to include in
the report. Choose from: **Contract, Speculative, Contract Renewal, Option,
Month-to-Month, Holdover**," plus a **Lease Period** filter ("Base Only /
Base and Options Only / All Leases"). [AE p. 574] (single-property report)
presents expirations by year with per-period sub-totals and per-lease
metrics; it does not lump statuses together. [AE p. 817] (WALE) further
shows the analysis is anchored on leases *in place* — "only leases
currently in place as of the PV/IRR date are included; leases that start in
the future are not included."

Consequence for our report: the current builder's `_contract_segment`
treats an absorption lease's own first term as a **contract** segment
(because the chain-resolution `speculative` flag is False on a lease's own
term), so the speculative-status absorption chain "Suite 395 remainder
lease-up" is mislabeled and summed with contract. This is **the opposite of
the Lease Audit's deliberate [AE p. 398] labeling**, where an absorption
lease's first generation is labeled **speculative** by reading
`segment.lease.status.value == "speculative"` (`engine/reports/
lease_audit.py::_phase`). The two reports must be consistent: **Lease
Expiration should read `lease.status`**, carry it as a column, and by
default separate/exclude speculative (matching [AE p. 818] and the Lease
Audit), not treat absorption first terms as contract. Note the OKI
double-entry is NOT fixed by this — both OKI rows are `status=contract`; a
signed renewal on an occupied suite is a legitimate second contract lease.

### Q3 — is >100% of the building expiring over the term legitimate?

**Yes — cumulative expiring SF over a multi-year term legitimately exceeds
100% of the building whenever a suite turns over more than once.** Suite
100 is exactly this case: OKI's current lease expires FY2027 and its
renewal expires FY2032 — two genuine expiration events for one physical
suite, and ARGUS's Lease Expiration presents expirations "by fiscal or
calendar year ... as well as sub-totals for the lease expiration period"
[AE p. 574], per year, never claiming the grand total equals the building.
Therefore **"total expiring SF == rentable" is fundamentally the wrong
invariant** — it contradicts legitimate turnover. (The current report only
counts one contract expiration per chain, so its 104.1% is the
data-structure artifact decomposed above, not yet even the rollover
turnover ARGUS would additionally show — reinforcing that a grand-total
identity is meaningless here.)

### The correction as implemented (2026-07-13)

The tautological `reconcile_expiration_area` is **removed** and replaced by
**two** checks, each capable of failing on a real bug; the report now keys
on `lease.status` with an explicit inclusion filter. All in
`engine/reports/lease_reports.py` (+ tests); no `engine/calc` touched.

1. **`statuses` inclusion filter — [AE p. 818].** Both `lease_expiration()`
   and `lease_summary()` take a `statuses` parameter mirroring ARGUS's
   Lease Status checkboxes (Contract / Speculative / Contract Renewal /
   Option / Month-to-Month / Holdover). The §3 schema narrows status to
   `contract` / `speculative` / `mtm`, so the mapping is: Contract /
   Contract Renewal / Option → `contract`; Month-to-Month → `mtm`;
   Speculative → `speculative`; Holdover not modeled. **Default =
   `(LeaseStatus.contract,)`** — speculative and MTM excluded by default,
   selectable. The filter keys on `lease.status`, so it **agrees with the
   Lease Audit's [AE p. 398] speculative labeling** (`lease_audit._phase`
   reads the same `lease.status`): an absorption lease's own first term is
   *speculative* and is excluded from the default contract view, not
   mislabeled as contract. Verified on Freeport: default = 28 contract
   chains (the MTM AT&T antenna and the speculative absorption chain
   excluded).
2. **Structural report↔model-input reconciliation
   (`reconcile_lease_expiration(report, model, *, statuses,
   fiscal_year_end_month)`).** Rebuilds the expected expiration table
   independently from `model.rent_roll` (+ `model.absorption` expanded via
   `generate_absorption_leases` when speculative is included) using
   `lease_term_periods` + `fiscal_year_of` — **a source the builder never
   reads** (it builds from `result.segments`). Diffs overall lease count,
   overall SF, and per-fiscal-year count and SF; all ~0 when the builder
   emits each included lease once at the right area and year. **Capable of
   failing** on a dropped / duplicated / mis-aread / mis-bucketed lease —
   not a self-subtraction.
3. **Per-year SANITY BOUND (`assert_expiration_within_building`), labelled
   as a bound, not an invariant.** Asserts no single fiscal year's expiring
   SF exceeds rentable. A building with heavy short-term turnover could
   legitimately roll >100% in one year and trip it, so it is a smoke check
   for gross within-year double-counting, **not** a guaranteed identity.
   The figure is **fiscal-year-end dependent** and is asserted across FYE ∈
   {3, 6, 9, 12}; the §25 draft's "35,544 / 28.9%" is the **FYE = 6** view
   and its predecessor did not name the convention. Freeport's contract-only
   worst single year, by convention: **FYE = 3 → 28.9%; FYE = 6 → 28.9%;
   FYE = 9 → 39.9%; FYE = 12 → 31.9%** (all well under 100%). The **grand
   total across years is deliberately NOT bounded by rentable** (legitimate
   turnover — suite 100 expires twice over the term).

### Lease Summary (#11) area fix

`meta.extra["total_area"]` previously summed the double-counted chains
(128,087 on Freeport, overstating the 123,099 building by 4,988). It is
**removed** and replaced by `distinct_demised_area` — the sum of demised
area deduped by suite (a physical space entered as two sequential leases,
e.g. the suite-100 signed renewal, is counted once). On Freeport contract-
only this is **122,870 SF**, honestly **under** the 123,099 building; it is
labelled demised area, never "building" or "rentable." `meta.extra` also
carries `lease_count` and `included_statuses`.

### Narrowing recorded

- The Phase 4 Step 4 acceptance criterion "Lease Expiration SF sums to
  rentable" is **withdrawn as invalid** (the plan's criterion was
  defective, not the engine); the tautological `reconcile_expiration_area`
  is deleted.
- `lease_expiration` / `lease_summary` default to **contract-only**
  (`statuses=(LeaseStatus.contract,)`); MTM and speculative are excluded by
  default but selectable, keyed on `lease.status` consistent with the Lease
  Audit [AE p. 398] and [AE p. 818].
- The report remains **externally unvalidated** (no golden publishes a
  Lease Expiration schedule) — validation is the structural report↔input
  reconciliation plus the FYE-spanning sanity bound on engineered + golden
  fixtures, never input tuning.
- **Step 5 has NOT been started.** This commit is the §12 correction only;
  it stops for owner review of the fix (Iron Rule 2 applied to a
  correction).
