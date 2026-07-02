"""General vacancy and credit loss (spec §3.4-3.5) [AE pp. 224-232]."""
from __future__ import annotations

from enum import Enum

from .common import Ref, StrictModel, YearRate


class VacancyMethod(str, Enum):
    percent_of_pgr = "percent_of_pgr"
    percent_of_scheduled_base_plus = "percent_of_scheduled_base_plus"
    percent_of_total_tenant_revenue = "percent_of_total_tenant_revenue"
    none = "none"


class TenantOverride(StrictModel):
    """Exclude a specific tenant (e.g., a credit tenant) from the vacancy or
    credit-loss base. ``tenant_ref`` matches ``Lease.tenant_name`` (or its
    ``external_id``)."""

    tenant_ref: Ref
    exclude: bool = True


class GeneralVacancy(StrictModel):
    """General vacancy allowance (spec §3.4) [AE pp. 224-228].

    Critical, frequently misimplemented: when ``reduce_by_absorption_turnover``
    is true, monthly General Vacancy = max(0, target vacancy amount −
    absorption & turnover vacancy already in the ledger), so total vacancy
    equals the stated rate rather than stacking rollover downtime on top of it.
    Tenant overrides remove those tenants' revenue from the base before
    applying the percentage.
    """

    method: VacancyMethod = VacancyMethod.none
    rate: list[YearRate] = []
    include_in_pgr_accounts: list[Ref] = []  # which revenue lines the % applies to
    reduce_by_absorption_turnover: bool = True
    tenant_overrides: list[TenantOverride] = []


class CreditLoss(StrictModel):
    """Credit loss allowance (spec §3.5) [AE pp. 229-232].

    Same structure as General Vacancy; applied after General Vacancy on the
    reduced base. No interaction with absorption vacancy.
    """

    method: VacancyMethod = VacancyMethod.none
    rate: list[YearRate] = []
    include_in_pgr_accounts: list[Ref] = []
    tenant_overrides: list[TenantOverride] = []
