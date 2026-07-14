"""Report builders (DataFrames; spec §7).

The Phase 4 Step 1 shared layer lives in :mod:`engine.reports.base`: the
:class:`~engine.reports.base.Report` contract every §7 report returns, the
Total $ / per-SF / per-month / per-occupied-SF unit toggle, the
monthly/quarterly/annual/fiscal period views, and :class:`
~engine.reports.base.ModelingPolicies` (report-level rounding, §4.3).

The Cash Flow report (report 1) and Benchmark Comparison report (report
24) arrive in Phase 4 Step 2. The Recovery Audit (report 18) and Lease
Audit (report 16) arrived in Phase 2 Steps 5-6 as Gate 2 debugging tools;
the Property Resale Audit (report 21) in Phase 3 Step 4. Each audit keeps
its original bare-DataFrame builder and reconciliation helper, plus a
``*_report`` wrapper conforming to the Phase 4 contract. The full catalog
is built out across Phase 4.
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
from .benchmark import (
    benchmark_comparison,
    load_expected_cash_flow,
    miss_lines,
)
from .cash_flow import cash_flow
from .cash_flow import reconcile_to_ledger as reconcile_cash_flow
from .lease_reports import (
    assert_expiration_within_building,
    lease_expiration,
    lease_summary,
    reconcile_lease_expiration,
    reconcile_lease_summary,
)
from .occupancy import (
    assert_occupied_within_rentable,
    occupancy,
)
from .occupancy import reconcile_to_result as reconcile_occupancy
from .loan_amortization import loan_amortization
from .loan_amortization import reconcile_to_ledger as reconcile_loan_amortization
from .summary_reports import (
    assumptions_report,
    executive_summary,
    input_assumptions_listing,
    reconcile_executive_summary,
    reconcile_sources_and_uses,
    sources_and_uses,
)
from .valuation_reports import (
    irr_matrix,
    present_value,
    reconcile_matrix_to_source,
    reconcile_present_value,
    reconcile_resale_matrix,
    reconcile_valuation_summary,
    resale_matrix,
    valuation_summary,
    value_matrix,
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
    # Cash Flow (#1) + Benchmark Comparison (#24)
    "cash_flow", "reconcile_cash_flow",
    "benchmark_comparison", "load_expected_cash_flow", "miss_lines",
    # Valuation family (#5, #6, #8, #9) + Loan Amortization (#20)
    "irr_matrix", "value_matrix", "reconcile_matrix_to_source",
    "valuation_summary", "reconcile_valuation_summary",
    "present_value", "reconcile_present_value",
    "loan_amortization", "reconcile_loan_amortization",
    # Resale Matrix (#7)
    "resale_matrix", "reconcile_resale_matrix",
    # Summary / echo (#2, #3, #4, #23)
    "executive_summary", "reconcile_executive_summary",
    "sources_and_uses", "reconcile_sources_and_uses",
    "assumptions_report", "input_assumptions_listing",
    # Occupancy (#15) + Lease Summary (#11) + Lease Expiration (#12)
    "occupancy", "reconcile_occupancy", "assert_occupied_within_rentable",
    "lease_summary", "reconcile_lease_summary",
    "lease_expiration", "reconcile_lease_expiration",
    "assert_expiration_within_building",
    # audit builders (bare frame + reconciliation + contract wrapper)
    "lease_audit", "lease_audit_report", "reconcile_lease_audit",
    "recovery_audit", "recovery_audit_report", "reconcile_recovery_audit",
    "reconcile_to_ledger",
    "resale_audit", "resale_audit_report", "reconcile_resale_audit",
]
