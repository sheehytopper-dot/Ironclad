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
