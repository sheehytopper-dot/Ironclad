"""The Tier 2 institutional theme — the ONLY module allowed to contain CSS
(NEXT_STEPS_UI_TIER2.md; brittleness rule: Streamlit custom CSS keys off
internal DOM attributes, so every selector lives here and
``streamlit==1.58.0`` is pinned — an upgrade means re-verifying this file).

Design tokens are the single source of truth for the app's look. The
accent ``INDIGO`` is the SAME hex as the Excel exporter's spec §8 title
band (``engine/export/package_builder._HEADER_BG``) — asserted equal by a
unit test so the app and the workbook can never drift apart.

Presentation only: nothing here touches data, report frames, or exports.
"""
from __future__ import annotations

import streamlit as st

# ------------------------------------------------------------------ #
# Design tokens (NEXT_STEPS_UI_TIER2.md)                              #
# ------------------------------------------------------------------ #

#: The accent — MUST equal engine/export/package_builder._HEADER_BG
#: (test-locked; read from the exporter, not guessed).
INDIGO = "#3F3D8A"
INDIGO_LIGHT = "#6B69C9"        # chart companion series on dark
BG = "#0E1117"
SURFACE = "#171B26"
SIDEBAR_BG = "#0A0D14"
HAIRLINE = "#2A2F3E"
TEXT = "#E6E8EE"
TEXT_MUTED = "#9AA0B0"
NEGATIVE_RED = "#E5484D"
POSITIVE = "#46A758"

MONO = "'IBM Plex Mono', ui-monospace, monospace"
SANS = "'IBM Plex Sans', 'Source Sans Pro', sans-serif"

#: Dense-grid row height (px) for st.dataframe on the reference screens.
DENSE_ROW_HEIGHT = 30

_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@400;600&display=swap');

html, body, [data-testid="stAppViewContainer"] {{
    font-family: {SANS};
}}

/* ---- sidebar: darker than the app, hairline edge ---- */
[data-testid="stSidebar"] {{
    background-color: {SIDEBAR_BG};
    border-right: 1px solid {HAIRLINE};
}}
[data-testid="stSidebar"] .stRadio label p {{
    font-size: 0.92rem;
}}

/* ---- KPI metric cards: surface + hairline + indigo keyline ---- */
[data-testid="stMetric"] {{
    background-color: {SURFACE};
    border: 1px solid {HAIRLINE};
    border-left: 3px solid {INDIGO};
    border-radius: 4px;
    padding: 0.65rem 0.9rem;
}}
[data-testid="stMetricLabel"] p {{
    color: {TEXT_MUTED};
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}}
[data-testid="stMetricValue"] {{
    font-family: {MONO};
    font-variant-numeric: tabular-nums;
    font-size: 1.45rem;
    font-weight: 600;
}}

/* ---- numerics everywhere text-rendered: mono + tabular figures ---- */
[data-testid="stTable"] td, code, .stMarkdown table td {{
    font-family: {MONO};
    font-variant-numeric: tabular-nums;
}}

/* ---- hairline dense text tables (st.table / markdown tables) ---- */
[data-testid="stTable"] table, .stMarkdown table {{
    border-collapse: collapse;
}}
[data-testid="stTable"] th, [data-testid="stTable"] td,
.stMarkdown th, .stMarkdown td {{
    border: 1px solid {HAIRLINE};
    padding: 2px 8px;
    font-size: 0.85rem;
}}

/* ---- expanders / containers: hairline surfaces, no chrome ---- */
[data-testid="stExpander"] details {{
    border: 1px solid {HAIRLINE};
    border-radius: 4px;
    background-color: {SURFACE};
}}

/* ---- negative numerics in red (Tier 1 already parenthesizes) ---- */
.ic-neg {{ color: {NEGATIVE_RED}; }}

/* ---- section headers: tighter, institutional ---- */
h2, h3 {{
    letter-spacing: -0.01em;
    font-weight: 600;
}}
</style>
"""


def inject() -> None:
    """Inject the app CSS exactly once per session run (idempotent within
    a rerun; called from ``ui.main.render``)."""
    st.markdown(_CSS, unsafe_allow_html=True)


def css() -> str:
    """The raw CSS block (for tests)."""
    return _CSS


def plotly_layout(**overrides) -> dict:
    """The shared institutional Plotly layout: transparent on the app
    background, hairline gridlines, Plex fonts, indigo series."""
    layout = dict(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="IBM Plex Sans, sans-serif", color=TEXT, size=12),
        colorway=[INDIGO_LIGHT, INDIGO, POSITIVE, NEGATIVE_RED],
        margin=dict(l=10, r=10, t=48, b=10),
        height=300,
        xaxis=dict(gridcolor=HAIRLINE, zerolinecolor=HAIRLINE),
        yaxis=dict(gridcolor=HAIRLINE, zerolinecolor=HAIRLINE),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    layout.update(overrides)
    return layout
