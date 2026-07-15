"""Rent-roll intake (Phase 4 Step 7; spec §5.2 / §5.4).

The second of the application's two intake surfaces (the first is loading a
PropertyModel JSON, engine/models/io.py): importing the §5.2 rent-roll
template — the layout engine/export/rent_roll_export.py writes (Rent Roll +
Rent Steps + Misc Items sheets; CSV also supported). Validation errors are
translated to plain, row-level messages a non-programmer can act on.

**In-app OM / document ingestion is cancelled entirely (spec §1.2, §5.4).**
This importer reads ONLY the rent-roll template / CSV, never an OM or any
other document.
"""
from .rent_roll_import import (
    ImportResult,
    RentRollImportError,
    import_rent_roll,
    import_rent_roll_csv,
)

__all__ = [
    "import_rent_roll", "import_rent_roll_csv", "RentRollImportError",
    "ImportResult",
]
