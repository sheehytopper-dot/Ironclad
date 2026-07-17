"""IronClad — Streamlit entry point (Phase 5; spec §6).

Run with:  streamlit run app.py

Thin by design: everything lives in ``ui/`` (renderer) and ``ui/state.py``
(pure, unit-testable helpers). Iron Rule 1: the UI imports the engine;
the engine never imports the UI.
"""
from ui.main import render

render()
