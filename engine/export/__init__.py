"""Excel result-package builder (Phase 4 Step 6; spec §8, §5.2).

``build_package`` writes one workbook with a tab per selected report (the
§8 default set), values-only; ``export_report`` writes a single report;
``export_rent_roll`` writes the §5.2 rent-roll template. The exporter
formats already-built report DataFrames — it recomputes nothing.
"""
from .package_builder import (
    DATA_START_ROW,
    DEFAULT_REPORTS,
    ReportSpec,
    build_package,
    export_report,
    report_cell_grid,
)
from .rent_roll_export import (
    MISC_ITEM_COLUMNS,
    RENT_ROLL_COLUMNS,
    RENT_STEP_COLUMNS,
    export_rent_roll,
)

__all__ = [
    "build_package", "export_report", "export_rent_roll",
    "report_cell_grid", "DEFAULT_REPORTS", "ReportSpec", "DATA_START_ROW",
    "RENT_ROLL_COLUMNS", "RENT_STEP_COLUMNS", "MISC_ITEM_COLUMNS",
]
