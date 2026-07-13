"""Report builders (DataFrames; spec §7).

The Phase 4 Step 1 shared layer lives in :mod:`engine.reports.base`: the
:class:`~engine.reports.base.Report` contract every §7 report returns, the
Total $ / per-SF / per-month / per-occupied-SF unit toggle, the
monthly/quarterly/annual/fiscal period views, and :class:`
~engine.reports.base.ModelingPolicies` (report-level rounding, §4.3).

The Recovery Audit (report 18) and Lease Audit (report 16) arrived in
Phase 2 Steps 5-6 as Gate 2 debugging tools; the Property Resale Audit
(report 21) in Phase 3 Step 4. Each keeps its original bare-DataFrame
builder and reconciliation helper, plus a ``*_report`` wrapper conforming
to the Phase 4 contract. The full catalog is built out across Phase 4.
"""
from .base import (
    ModelingPolicies,
    Period,
    Report,
    ReportMeta,
    Rounding,
    Unit,
    aggregate_period,
    apply_rounding,
    apply_unit,
    assert_period_consistency,
    build_monetary_report,
    period_mean_area,
    period_month_counts,
)
from .lease_audit import lease_audit, lease_audit_report
from .lease_audit import reconcile_to_ledger as reconcile_lease_audit
from .recovery_audit import recovery_audit, recovery_audit_report
from .recovery_audit import reconcile_to_ledger as reconcile_recovery_audit
# backwards-compatible name for the Recovery Audit reconciliation
from .recovery_audit import reconcile_to_ledger
from .resale_audit import resale_audit, resale_audit_report
from .resale_audit import reconcile_to_ledger as reconcile_resale_audit

__all__ = [
    # Phase 4 contract + toggle/period engine
    "Report", "ReportMeta", "ModelingPolicies", "Unit", "Period", "Rounding",
    "aggregate_period", "apply_unit", "apply_rounding", "build_monetary_report",
    "period_month_counts", "period_mean_area", "assert_period_consistency",
    # audit builders (bare frame + reconciliation + contract wrapper)
    "lease_audit", "lease_audit_report", "reconcile_lease_audit",
    "recovery_audit", "recovery_audit_report", "reconcile_recovery_audit",
    "reconcile_to_ledger",
    "resale_audit", "resale_audit_report", "reconcile_resale_audit",
]
