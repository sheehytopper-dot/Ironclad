"""Export the formal JSON Schema for PropertyModel to docs/property_model.schema.json.

Run whenever ``engine/models/`` changes (spec §5.1; CLAUDE.md "Intake Surfaces"):

    .venv\\Scripts\\python scripts\\export_json_schema.py

``tests/unit/test_schema_docs.py`` fails while the export is stale. Update
``docs/SCHEMA_GUIDE.md`` by hand in the same change.
"""
from __future__ import annotations

import json
from pathlib import Path

from engine.models import PropertyModel


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    out_path = repo_root / "docs" / "property_model.schema.json"
    out_path.parent.mkdir(exist_ok=True)
    schema = PropertyModel.model_json_schema()
    out_path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
