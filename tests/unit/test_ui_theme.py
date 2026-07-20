"""Tests for the Tier 2 theme foundation (ui/theme.py +
.streamlit/config.toml — NEXT_STEPS_UI_TIER2.md).

Stated honestly there: pure CSS has no wrong-answer oracle a unit test
can catch — the visual judgment is the owner's, against the mockup. What
IS test-locked here: the accent-equals-export-indigo identity (the app
accent is READ FROM the exporter, so an exporter change breaks the build
until the app follows), the config-toml pin of the same hex, the CSS
containing the tokens it claims, and the streamlit version pin the
brittleness rule requires. Behavioral acceptance = every existing
functional/formatting/AppTest test passing unchanged.
"""
import tomllib
from pathlib import Path

import streamlit

from engine.export.package_builder import _HEADER_BG
from ui import theme

ROOT = Path(__file__).resolve().parents[2]


class TestAccentIdentity:
    def test_app_accent_equals_export_indigo(self):
        """The one §25-style check CSS allows: the app accent IS the Excel
        exporter's spec §8 title-band indigo — change either alone and
        this fails."""
        assert theme.INDIGO == _HEADER_BG == "#3F3D8A"

    def test_config_toml_pins_the_same_hex(self):
        config = tomllib.loads(
            (ROOT / ".streamlit" / "config.toml").read_text("utf-8"))
        assert config["theme"]["primaryColor"] == theme.INDIGO
        assert config["theme"]["base"] == "dark"
        assert "IBM Plex Sans" in config["theme"]["font"]
        families = {f["family"] for f in config["theme"]["fontFaces"]}
        assert families == {"IBM Plex Sans", "IBM Plex Mono"}


class TestCssBlock:
    def test_css_contains_the_tokens_it_claims(self):
        css = theme.css()
        for token in (theme.INDIGO, theme.SIDEBAR_BG, theme.HAIRLINE,
                      theme.SURFACE, theme.NEGATIVE_RED):
            assert token in css
        assert "IBM Plex Mono" in css
        assert "tabular-nums" in css
        assert css.count("<style>") == 1        # one block, one injection

    def test_plotly_layout_uses_the_tokens(self):
        layout = theme.plotly_layout()
        assert theme.INDIGO in layout["colorway"]
        assert layout["xaxis"]["gridcolor"] == theme.HAIRLINE
        override = theme.plotly_layout(height=500)
        assert override["height"] == 500


class TestBrittlenessPin:
    def test_streamlit_version_pinned_and_running(self):
        """The brittleness rule: ui/theme.py selectors are verified against
        exactly this Streamlit; the pin lives in pyproject and the venv
        runs it."""
        pyproject = (ROOT / "pyproject.toml").read_text("utf-8")
        assert '"streamlit==1.58.0"' in pyproject
        assert streamlit.__version__ == "1.58.0"
