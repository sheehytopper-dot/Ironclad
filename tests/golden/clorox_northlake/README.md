# Clorox Northlake — Golden Fixture #1

Single-tenant net-lease deal from a CBRE Offering Memorandum with a published
Argus-based cash flow — golden #1 of five (spec §9.1). Sources, tolerances, and
the fixture build steps are in
[NEXT_STEPS_TO_GATE1.md](../../../NEXT_STEPS_TO_GATE1.md) and CLAUDE.md
(Golden-File Strategy). Contents when complete: `source/` (OM, staged),
`clorox_northlake.icprop.json`, `expected_annual_cash_flow.csv`,
`ASSUMPTIONS.md`, and the owner-built `hand_model.xlsx` — a **monthly-resolution
hand schedule** (base rent, steps, inflation application, expense growth; not a
full DCF), built without reading the engine. It is authoritative only on
month-level timing questions where the OM's annual data is silent.

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
2. **If the annual data cannot discriminate it, the monthly hand schedule
   adjudicates.** The hand-schedule builder should decide the mid-year rate
   question from the deal documents and their own reading of ARGUS behavior,
   **WITHOUT reading the engine's implementation or its docstrings** —
   independence is the point (NEXT_STEPS_TO_GATE1.md Step 3).

If the engine and the adjudicating source then disagree, that disagreement is
the finding: investigate, report, and let the owner adjudicate. Do not "fix"
either side to match the other first.
