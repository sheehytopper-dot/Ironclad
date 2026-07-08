# Cedar Alt Distribution Center — Golden Fixture #4

Two-building industrial NNN deal (Dallas, TX) from a CBRE Offering Memorandum
with a published Argus-based 11-year cash flow — golden #4 of five (spec §9.1).
Sources, tolerances, and the fixture-lock rule are in CLAUDE.md (Golden-File
Strategy) and [NEXT_STEPS_TO_GATE2.md](../../../NEXT_STEPS_TO_GATE2.md).

Contents: `source/` (OM), `cedar_alt.icprop.json`,
`expected_annual_cash_flow.csv`, `ASSUMPTIONS.md`, and this README.

**Fixture-lock status: CONFIRMED — owner-verified and committed 2026-07-08.**
The Real-estate-tax line, previously flagged as the fixture's #1 open item, is
now resolved: the Bldg-1 city-tax abatement is captured via `annual_overrides`
(the OM's own published RET figures for FY2027–FY2036, verified to reproduce
the published line to the penny; DEVIATIONS.md §12), so it is no longer a
modeling gap. As with goldens #1 and #2, there is no standing hand model:
remaining disputes (see Open questions below) resolve by owner per-cell
adjudication (Clorox README ladder — the OM's published annual figures
adjudicate if they discriminate the question by more than the $500/line
tolerance; otherwise the owner recomputes the disputed cells in Excel from the
source alone, without reading engine output or code first).

## Escalation checks (required before transcription) — BOTH PASSED

**1. Argus provenance — CONFIRMED in the PDF text layer.** The cash flow page
(printed p. 28) carries the explicit footnote **"Cash Flow Projections Based on
Argus Enterprise Version 14.0.2"**, extracted directly from the text layer (no
image render needed). This is a genuine Argus-based projection, not inferred
from the OM's polish.

**2. Both buildings covered — CONFIRMED.** The rent roll (printed p. 29) and
the cash flow both span **both** buildings:
- **Bldg 1 = Asset #01 (3486 Cedardale)** — 1,084,462 SF, a CONFIDENTIAL single
  tenant, NNN, lease Jan-2026 → May-2033.
- **Bldg 3 = Asset #02 (9016 Van Horn)** — 265,758 SF, Crane Worldwide
  Logistics, NNN, lease Mar-2025 → May-2030.

Total 1,350,220 SF (cash flow footnote [3] and rent-roll totals both confirm),
100% leased. The OM's "Asset #01 / #02" map to the cover pages' "Bldg 1 / Bldg
3". Both buildings are in scope, so the golden #4 slot's defined coverage is met.

## Where this fixture sits between golden #1 and golden #2

**Lighter than Freeport (#2), heavier than Clorox (#1).** Clorox was one
net-leased tenant that simply expires inside the window; Freeport was 27
tenants with base-year/stop recoveries, gross-ups, and caps. Cedar Alt is
**two single-tenant NNN leases** (one per building) — so, like Clorox, it uses
plain `net` recoveries with no base-year machinery and no gross-ups, and the
same June/May fiscal calendar that sidesteps the analysis-year inflation
question. But unlike Clorox it exercises real **rollover inside the window**:

- Crane (265,758 SF) expires end-FY2030 → downtime/free-rent in FY2031.
- Bldg 1 (1,084,462 SF) expires end-FY2033 → large TI/LC + vacancy in FY2034.
- Crane's speculative renewal expires again ≈ FY2036.

So it validates the MLP rollover chain, the two-profile blend (different market
rent + TI per building), and — usefully — the **recovery gap during downtime**:
Expense Recoveries equals Total Operating Expenses exactly in the seven
fully-occupied years and drops below it in the three rollover years (FY2031
−$203,737; FY2034 −$391,354; FY2036 −$236,187). It also repeats the
recoverable %-of-EGR management-fee fixed point (2.5% here).

It is **not** the gross-up/base-year coverage deal (that is Freeport). Its
distinctive stressors are the two-tenant rollover and the Bldg-1 tax abatement
(resolved via the new `annual_overrides` escape hatch — see below).

## Open calculation / engine questions this transcription surfaced

Flagged now so Step 7 starts with eyes open.

1. **Real-estate-tax abatement — resolved directly from the OM's figures
   (ASSUMPTIONS §6).** The OM applies a Bldg-1 city-tax abatement (0.6988% ×
   90% × improvement-value-over-$1M, through Feb 2036), but the **Bldg-1
   improvement value is never stated** and reverse-solving the abatement from
   the published RET implies ≈5–6%/yr growth, inconsistent with the stated 3%
   — so the abatement is not computable from the OM. Rather than invent the
   improvement value, the fixture uses the new **`annual_overrides`** escape
   hatch (engine feature added this session; DEVIATIONS.md §12): the abated
   years FY2027–FY2036 take the OM's **own published fiscal RET figures**
   directly, and FY2037 (unabated) falls through to the gross stated-basis
   formula ($65,271,360 × 2.226710% × 3%), which reproduces it exactly. Verified
   end-to-end: the engine-computed fiscal RET line now equals the published
   figure **to the penny** for every overridden year (e.g. FY2027 −$1,213,076,
   FY2036 −$1,630,558; before the override the gross basis gave −$1,471,571 and
   −$1,920,067). This is a transcription of the OM's published RET, not a
   derivation — the RET line is no longer an open modeling gap. (If the owner
   later obtains the improvement value, RET can be re-modeled from first
   principles.)

2. **Rollover-year recovery timing (ASSUMPTIONS §5).** In the three rollover
   years (FY2031/2034/2036) the engine's Expense Recoveries drop below Total
   OpEx as vacant space stops recovering during downtime; the exact split vs
   the OM's Argus is a Step-7 machinery question (how ARGUS phases recovery
   during the weighted downtime), independent of RET.

3. **GPR month-count / day-count convention (ASSUMPTIONS §3).** Crane's rent
   steps on April 1 (mid-fiscal-year); summing the two leases' stated rents
   gives FY2027 GPR ≈ $8,035,228 vs the published $8,040,610 (≈$5,382 / 0.07%),
   consistent with ARGUS actual/365 proration vs the fixture's monthly posting.
   An adjudication point, not an input to tune.

4. **Downtime rounding** (weighted 2.5 → 3 months) is the same Phase 2
   adjudication point noted for Clorox.

5. **Which fiscal years Gate 2 asserts** is a Step 7 decision. All 11 published
   years are transcribed; revenue/vacancy/expense/NOI are Gate 2, TI/LC/capital
   Gate 3. With RET now resolved (item 1), the rollover-year recovery timing
   (item 2) is the main Gate-2 open question.

## Files & provenance

- `cedar_alt.icprop.json` (340 lines) — validated through the §3 pydantic
  models (`PropertyModel.model_validate`). Every input traces to
  `ASSUMPTIONS.md`. The RET line's `annual_overrides` were confirmed end-to-end
  (engine-computed fiscal RET = published, to the penny) for this report;
  no golden comparison test is written yet (fixture stays DRAFT).
- `expected_annual_cash_flow.csv` (21 lines) — the OM's published Argus cash
  flow [OM p. 28] transcribed line-for-line, FY2027–FY2037, account names
  matching the spec §2.3 ledger tree. All internal identities (scheduled-base,
  gross-revenue, EGR, opex, NOI, capital, cash-flow, and management-fee =
  2.5%×EGR) reconcile within ≤ $5 rounding on every year — the transcription is
  self-consistent.
- Whole-dollar published figures and the back-solved CY2026 bases mean small
  (< $1) rounding residuals are expected everywhere even when the model is
  exactly right; the $500/line tolerance absorbs them. The RET line is exact
  (published figures used via `annual_overrides`, item 1 above).
