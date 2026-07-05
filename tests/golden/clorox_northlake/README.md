# Clorox Northlake — Golden Fixture #1

Single-tenant net-lease deal from a CBRE Offering Memorandum with a published
Argus-based cash flow — golden #1 of five (spec §9.1). Sources, tolerances, and
the fixture build steps are in
[NEXT_STEPS_TO_GATE1.md](../../../NEXT_STEPS_TO_GATE1.md) and CLAUDE.md
(Golden-File Strategy). Contents: `source/` (OM),
`clorox_northlake.icprop.json`, `expected_annual_cash_flow.csv`, and
`ASSUMPTIONS.md` — all owner-verified 2026-07-04. **There is no standing hand
model** (owner decision 2026-07-04): disputes are resolved by owner per-cell
adjudication — see the ladder below.

**Fixture-lock rule (standing policy):** the transcribed inputs here are
human-verified against the source pages and committed **before** any engine
comparison runs.

## Open calculation question — adjudication ladder

**The engine's inflation year-offset interpretation
([engine/calc/inflation.py:68-69](../../../engine/calc/inflation.py#L68-L69)) is
unvalidated against the manual.** The manual [AE pp. 219-223] fixes *when*
inflation steps (on the inflation month) but does not specify, for an analysis
that begins mid-year with an inflation month different from the analysis begin
month, **which year's rate from an analysis-year schedule applies at each
inflation-month anniversary**. The engine's docstring documents the
interpretation it chose; no manual page confirms it.

Adjudication, in order:

1. **The OM's published annual figures adjudicate if they discriminate the
   question** — i.e., if the competing interpretations produce fiscal-year
   totals that differ by more than the $500/line tolerance, the reading that
   matches the OM wins.
2. **If the annual data cannot discriminate it, owner per-cell adjudication
   does** (owner decision 2026-07-04): the owner recomputes the specific
   disputed cells in Excel from the source documents alone, **WITHOUT reading
   the engine's output or code first** — independence is the point
   (NEXT_STEPS_TO_GATE1.md Step 3). The owner's independently computed cells
   are the reference; Claude never produces them.

Note on step 1's power for this deal: the June-May fiscal year boundary gives
the annual OM comparison **monthly discriminating power** — a one-month
timing error on any major line (base rent ≈ $216K/mo, real estate taxes
≈ $63K/mo, CAM ≈ $28K/mo) shifts a fiscal-year total by far more than the
$500/line tolerance, so most timing mistakes are caught at step 1 without
reaching step 2.

If the engine and the adjudicating source then disagree, that disagreement is
the finding: investigate, report, and let the owner adjudicate. Do not "fix"
either side to match the other first.

### Basis note (2026-07-03, fixture build)

This fixture uses the **calendar-year inflation basis** per the OM ("All
market rates are stated on a calendar-year basis" [OM p. 25]; growth steps in
January), which **sidesteps the analysis-year mid-year question for this
deal** — the open question above cannot be exercised by Clorox's published
figures. It remains open for any future golden modeled on an analysis-year
basis, and the ladder above still governs it there.
