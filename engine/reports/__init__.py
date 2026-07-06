"""Report builders (DataFrames; spec §7). The Recovery Audit (report 18)
and Lease Audit (report 16) arrive in Phase 2 Steps 5-6 as Gate 2
debugging tools; the full catalog is Phase 4."""
from .lease_audit import lease_audit
from .lease_audit import reconcile_to_ledger as reconcile_lease_audit
from .recovery_audit import recovery_audit
from .recovery_audit import reconcile_to_ledger as reconcile_recovery_audit
# backwards-compatible name for the Recovery Audit reconciliation
from .recovery_audit import reconcile_to_ledger

__all__ = [
    "lease_audit", "reconcile_lease_audit",
    "recovery_audit", "reconcile_recovery_audit", "reconcile_to_ledger",
]
