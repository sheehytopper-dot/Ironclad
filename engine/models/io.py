"""Save/load PropertyModel documents as ``.icprop.json`` files (spec §5.1).

Pretty-printed, stable key order (pydantic field-definition order), UTF-8 —
Git-diffable by design.
"""
from __future__ import annotations

from pathlib import Path
from typing import Union

from .property_model import PropertyModel

PROPERTY_FILE_SUFFIX = ".icprop.json"


def save_property(model: PropertyModel, path: Union[str, Path]) -> Path:
    """Write ``model`` to ``path`` as pretty-printed JSON. Returns the path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(model.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


def load_property(path: Union[str, Path]) -> PropertyModel:
    """Read and validate a ``.icprop.json`` document."""
    return PropertyModel.model_validate_json(Path(path).read_text(encoding="utf-8"))
