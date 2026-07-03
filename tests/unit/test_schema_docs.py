"""Keep the external-producer schema docs in sync with the §3 models (spec §5.1;
CLAUDE.md "Intake Surfaces").

``docs/SCHEMA_GUIDE.md`` and ``docs/property_model.schema.json`` are the contract
for external extraction workflows: both are regenerated whenever ``engine/models/``
changes, and these tests fail while either is stale.
"""
import json
import re
from pathlib import Path

from engine.models import PropertyModel

DOCS = Path(__file__).resolve().parents[2] / "docs"


def test_exported_json_schema_is_current():
    """docs/property_model.schema.json must equal PropertyModel.model_json_schema().

    Regenerate with: .venv\\Scripts\\python scripts\\export_json_schema.py
    """
    exported = json.loads(
        (DOCS / "property_model.schema.json").read_text(encoding="utf-8")
    )
    assert exported == PropertyModel.model_json_schema(), (
        "docs/property_model.schema.json is stale — "
        "run scripts/export_json_schema.py and update docs/SCHEMA_GUIDE.md"
    )


def test_schema_guide_worked_example_validates():
    """The SCHEMA_GUIDE.md worked example must stay a valid PropertyModel document."""
    guide = (DOCS / "SCHEMA_GUIDE.md").read_text(encoding="utf-8")
    match = re.search(
        r"<!-- worked-example:start -->\s*```json\n(.*?)```\s*<!-- worked-example:end -->",
        guide,
        re.DOTALL,
    )
    assert match, "worked-example markers missing from docs/SCHEMA_GUIDE.md"
    PropertyModel.model_validate_json(match.group(1))
