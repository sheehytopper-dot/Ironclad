# UI TIER 2 — the institutional visual pass (Claude Design target)

**Presentation only.** Iron Rule 1 holds throughout: zero changes under
`engine/` (`git log 62617f1..HEAD -- engine/` stays EMPTY). No data
change anywhere: the Tier-1 display-formatting guarantees, the raw report
frames, and the Excel exports stay byte-identical; every existing test
stays green; the four by-design golden reds stay red (137/47 Gate 2,
33/12 Gate 3 capital).

**Design target** (the approved Claude Design mockup, `Ironclad.dc.html`):
an institutional financial terminal — dark sidebar, dense hairline
tables, IBM Plex Sans body + IBM Plex Mono numerics with tabular figures,
negatives in red parentheses (Tier 1 already parenthesizes; Tier 2 adds
the red), KPI metric cards, an indigo accent. Data-dense, precise, no
consumer chrome.

## Design tokens (single source of truth: `ui/theme.py`)

| Token | Value | Source |
|---|---|---|
| `INDIGO` (accent) | `#3F3D8A` | **READ FROM the Excel exporter** — `engine/export/package_builder.py::_HEADER_BG` (the spec §8 indigo title band). App and export match by construction; a unit test asserts the equality, so an exporter change breaks the build until the app follows. |
| `BG` (app background) | `#0E1117` | dark institutional base |
| `SURFACE` (cards/inputs) | `#171B26` | secondary background |
| `SIDEBAR_BG` | `#0A0D14` | darker-than-app sidebar |
| `HAIRLINE` | `#2A2F3E` | 1px table/card borders |
| `TEXT` | `#E6E8EE` | primary text |
| `TEXT_MUTED` | `#9AA0B0` | captions, labels |
| `NEGATIVE_RED` | `#E5484D` | negative numerics (parens already from Tier 1) |
| `POSITIVE` | `#46A758` | sparing positive accents |
| Body font | IBM Plex Sans | registered via `[[theme.fontFaces]]` + CSS fallback |
| Numeric font | IBM Plex Mono, `font-variant-numeric: tabular-nums` | metric values, table numerics |

## Where the styling lives (exactly two files)

1. **`.streamlit/config.toml`** — the base theme (dark, primaryColor =
   `INDIGO`, background/surface/text colors, IBM Plex font faces). This
   is what `st.dataframe`'s canvas grid actually obeys.
2. **`ui/theme.py`** — ALL custom CSS in one injected `<style>` block
   (`theme.inject()` called once in `ui/main.render`), plus the token
   constants and the shared Plotly layout helper. **No other module may
   contain CSS.**

**Honest limitation:** `st.dataframe` renders on a canvas (glide-data-grid)
— its cells are NOT reachable by CSS. Density comes from the
`row_height=` parameter and the config-toml theme; the Tier-1 Styler
(bold subtotals, top rules) is passed through the grid's own CSS-prop
mapping. Hairline styling via CSS applies to cards, metrics, containers,
and the sidebar — not inside the canvas grid.

## Brittleness note (standing)

Streamlit custom CSS keys off internal DOM attributes (`data-testid`
values, generated class names) that are NOT a stable API. Mitigations,
both mandatory: (1) every selector lives in `ui/theme.py` ONLY, so a
breaking Streamlit upgrade has a single file to fix; (2)
**`streamlit==1.58.0` is pinned in pyproject.toml** — upgrading is a
deliberate act that includes re-verifying `ui/theme.py` selectors, not a
side effect of `pip install`.

## Rollout order

1. **Foundation** (this pass): config.toml + `ui/theme.py` + the pin.
2. **Reference screens** (this pass): Dashboard (KPI cards, themed
   NOI/CFBDS bars, occupancy line, expiration bars, dense top-tenants
   table) + Reports (compact toggle row, dense report tables, the Cash
   Flow account-tree styling). **The other 8 tabs are NOT skinned yet** —
   the owner reacts to the reference screens against the mockup first.
3. Input tabs (Property → Valuation) in spec order — after owner review.
4. The Tenants split-pane (the densest screen; needs its own layout care).
5. Audit tab last (its tables inherit most styling for free).

## Acceptance model (stated honestly)

Pure CSS cannot be §25 unit-tested — a stylesheet has no wrong-answer
oracle a unit test can catch. What IS test-locked: the accent-equals-
export-indigo identity (`ui/theme.INDIGO == package_builder._HEADER_BG`),
the config-toml primaryColor matching the same hex, the CSS block
containing the token values it claims to, single-injection, and — the
real acceptance — **every existing functional/formatting/AppTest test
passing unchanged** (the theme must not alter behavior). The visual
judgment is the owner's: Topper opens the app beside `Ironclad.dc.html`
and reacts before the remaining tabs are skinned.

**Status:** foundation + reference screens land in this pass; STOP for
owner visual review afterward.
