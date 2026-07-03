# Clorox Northlake — Golden Fixture #1

Single-tenant net-lease deal from a CBRE Offering Memorandum with a published
Argus-based cash flow. Sources, tolerances, and the fixture build steps are in
[NEXT_STEPS_TO_GATE1.md](../../../NEXT_STEPS_TO_GATE1.md) and CLAUDE.md
(Golden-File Strategy). Contents when complete: `source/` (OM, staged),
`clorox_northlake.icprop.json`, `expected_annual_cash_flow.csv`,
`ASSUMPTIONS.md`, and the owner-built `hand_model.xlsx`.

## Open calculation question — hand model adjudicates

**The engine's inflation year-offset interpretation
([engine/calc/inflation.py:68-69](../../../engine/calc/inflation.py#L68-L69)) is
unvalidated against the manual.** The manual [AE pp. 219-223] fixes *when*
inflation steps (on the inflation month) but does not specify, for an analysis
that begins mid-year with an inflation month different from the analysis begin
month, **which year's rate from an analysis-year schedule applies at each
inflation-month anniversary**. The engine's docstring documents the
interpretation it chose; no manual page confirms it.

This must be adjudicated by the independent hand model:

- **The hand-model builder should decide the mid-year rate question from the
  deal documents and their own reading of ARGUS behavior, WITHOUT reading the
  engine's implementation or its docstrings** — independence is the point
  (NEXT_STEPS_TO_GATE1.md Step 3).
- If the engine and the hand model then disagree on inflated amounts, that
  disagreement is the finding: investigate, report, and let the owner
  adjudicate. Do not "fix" either side to match the other first.
