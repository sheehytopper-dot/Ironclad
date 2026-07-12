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
