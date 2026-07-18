"""Tab renderers (Phase 5; spec §6). Each module exposes pure ``apply_*``
commit functions (browser-free, unit-tested) and a ``render()`` that is a
thin Streamlit skin over them. The engine never imports from here."""
