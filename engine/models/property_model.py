"""The single PropertyModel JSON document (spec §5.1, ``.icprop.json``).

Contains every §3 model plus ``schema_version``. Serialized pretty-printed
with stable key order (field-definition order) so files are Git-diffable.
This is our open replacement for the proprietary ``.aeex`` format.
"""
from __future__ import annotations

from typing import Optional

from pydantic import model_validator

from .common import StrictModel, YearRate
from .expenses import ExpenseGroup, ExpenseItem
from .inflation import Inflation
from .investment import Loan, Purchase
from .leases import AbsorptionSpec, Lease
from .market_leasing import MarketLeasingProfile, UponExpiration
from .profiles import FreeRentProfile, LCCategory, TICategory
from .property import AreaMeasures, PropertyInfo
from .recoveries import RecoveryAssignment, RecoverySystemMethod, RecoveryStructure
from .revenues import PropertyRevenue
from .vacancy import CreditLoss, GeneralVacancy
from .valuation import ValuationInputs

SCHEMA_VERSION = "1.0"

# Built-in inflation index names accepted anywhere an InflationRef string
# appears, alongside custom index names (spec §3.3).
BUILTIN_INDICES = {"general", "market_rent", "expense", "cpi"}


class PropertyModel(StrictModel):
    """One property: every §3 input model in a single JSON document."""

    schema_version: str = SCHEMA_VERSION
    property: PropertyInfo
    area_measures: AreaMeasures
    inflation: Inflation
    general_vacancy: GeneralVacancy = GeneralVacancy()
    credit_loss: CreditLoss = CreditLoss()
    market_leasing_profiles: list[MarketLeasingProfile] = []
    free_rent_profiles: list[FreeRentProfile] = []
    ti_categories: list[TICategory] = []
    lc_categories: list[LCCategory] = []
    recovery_structures: list[RecoveryStructure] = []
    miscellaneous_revenues: list[PropertyRevenue] = []
    parking_revenues: list[PropertyRevenue] = []
    storage_revenues: list[PropertyRevenue] = []
    expenses: list[ExpenseItem] = []       # operating/non-operating/capital via category
    expense_groups: list[ExpenseGroup] = []
    rent_roll: list[Lease] = []
    absorption: list[AbsorptionSpec] = []
    purchase: Optional[Purchase] = None
    loans: list[Loan] = []
    valuation: Optional[ValuationInputs] = None

    # ------------------------------------------------------------------ #
    # Cross-reference validation: every named ref must resolve.          #
    # ------------------------------------------------------------------ #

    @model_validator(mode="after")
    def _validate_refs(self) -> "PropertyModel":
        self._check_unique_names()
        mlp_names = {p.name for p in self.market_leasing_profiles}
        free_rent_names = {p.name for p in self.free_rent_profiles}
        ti_names = {c.name for c in self.ti_categories}
        lc_names = {c.name for c in self.lc_categories}
        structure_names = {s.name for s in self.recovery_structures}
        expense_names = {e.name for e in self.expenses}
        group_names = {g.name for g in self.expense_groups}
        index_names = BUILTIN_INDICES | {i.name for i in self.inflation.custom_indices}
        tenant_refs = {t.tenant_name for t in self.rent_roll} | {
            t.external_id for t in self.rent_roll if t.external_id
        }

        def require(ref: Optional[str], pool: set, what: str, where: str) -> None:
            if ref is not None and ref not in pool:
                raise ValueError(f"{where}: unknown {what} {ref!r}")

        def check_inflation(value, where: str) -> None:
            # InflationRef: str ref | explicit list[YearRate] | None
            if isinstance(value, str):
                require(value, index_names, "inflation index", where)

        def check_recovery(assignment: RecoveryAssignment, where: str) -> None:
            if assignment.method == RecoverySystemMethod.structure:
                require(
                    assignment.structure_ref, structure_names,
                    "recovery structure", where,
                )
            check_inflation(assignment.fixed_inflation, where)

        for p in self.market_leasing_profiles:
            where = f"market_leasing_profile {p.name!r}"
            require(p.chained_profile, mlp_names, "chained profile", where)
            require(p.free_rent_profile, free_rent_names, "free rent profile", where)
            check_recovery(p.recoveries, where)
            for lc in (p.lc_new, p.lc_renew):
                if lc is not None:
                    require(lc.category_ref, lc_names, "LC category", where)

        for lease in self.rent_roll:
            where = f"lease {lease.tenant_name!r}"
            require(lease.market_leasing_profile, mlp_names, "market leasing profile", where)
            require(lease.option_profile, mlp_names, "option profile", where)
            if lease.free_rent is not None:
                require(lease.free_rent.profile, free_rent_names, "free rent profile", where)
            check_recovery(lease.recoveries, where)
            if lease.leasing_costs is not None:
                require(lease.leasing_costs.ti_category, ti_names, "TI category", where)
                require(lease.leasing_costs.lc_category, lc_names, "LC category", where)
                if lease.leasing_costs.lc is not None:
                    require(lease.leasing_costs.lc.category_ref, lc_names, "LC category", where)
            if (
                lease.upon_expiration == UponExpiration.market
                and lease.market_leasing_profile is None
            ):
                raise ValueError(
                    f"{where}: upon_expiration 'market' requires market_leasing_profile"
                )

        for spec in self.absorption:
            require(
                spec.market_leasing_profile, mlp_names,
                "market leasing profile", f"absorption {spec.name!r}",
            )

        # reabsorbed_from linkage (spec §3.15 + reabsorb; DEVIATIONS.md §8):
        # each linked spec re-leases part of a reabsorbing lease's space, so
        # it must point at a real 'reabsorb' lease, start after that lease
        # expires, and the linked specs together may not exceed its area.
        def _month_index(d) -> int:
            return d.year * 12 + (d.month - 1)

        leases_by_name = {t.tenant_name: t for t in self.rent_roll}
        linked_area_by_lease: dict[str, float] = {}
        for spec in self.absorption:
            if spec.reabsorbed_from is None:
                continue
            where = f"absorption {spec.name!r}"
            lease = leases_by_name.get(spec.reabsorbed_from)
            if lease is None:
                raise ValueError(
                    f"{where}: reabsorbed_from names {spec.reabsorbed_from!r}, "
                    "but no rent roll lease has that tenant_name. Link the "
                    "spec to the lease whose space it re-leases."
                )
            if lease.upon_expiration != UponExpiration.reabsorb:
                raise ValueError(
                    f"{where}: reabsorbed_from names lease "
                    f"{spec.reabsorbed_from!r}, but that lease's "
                    f"upon_expiration is '{lease.upon_expiration.value}', not "
                    "'reabsorb'. Only a reabsorbed lease returns its space to "
                    "the absorption pool."
                )
            if lease.end_date is not None:
                lease_end = _month_index(lease.end_date)
            else:
                lease_end = _month_index(lease.start_date) + lease.term_months - 1
            if _month_index(spec.start_date) < lease_end + 1:
                raise ValueError(
                    f"{where}: start_date {spec.start_date.isoformat()} is "
                    f"before lease {spec.reabsorbed_from!r} has expired — the "
                    "space is not vacant yet. Absorption of reabsorbed space "
                    "can begin no earlier than the month after the lease's "
                    "last occupied month."
                )
            linked_area_by_lease[spec.reabsorbed_from] = (
                linked_area_by_lease.get(spec.reabsorbed_from, 0.0)
                + spec.total_area
            )
        for tenant_name, linked_total in linked_area_by_lease.items():
            lease_area = leases_by_name[tenant_name].area
            if linked_total > lease_area + 1e-9:
                raise ValueError(
                    f"absorption specs linked to lease {tenant_name!r} total "
                    f"{linked_total:,.0f} SF, more than the lease's "
                    f"{lease_area:,.0f} SF — the same space would be leased "
                    "twice. Reduce the linked specs' total_area to at most "
                    "the reabsorbed lease's area."
                )

        for coll_name in ("miscellaneous_revenues", "parking_revenues", "storage_revenues"):
            for rev in getattr(self, coll_name):
                check_inflation(rev.inflation, f"{coll_name} {rev.name!r}")

        for exp in self.expenses:
            where = f"expense {exp.name!r}"
            check_inflation(exp.inflation, where)
            require(exp.expense_group, group_names, "expense group", where)

        for group in self.expense_groups:
            for member in group.members:
                require(member, expense_names, "expense", f"expense_group {group.name!r}")

        for structure in self.recovery_structures:
            where = f"recovery_structure {structure.name!r}"
            for pool in structure.pools:
                for ref in pool.expenses:
                    if ref not in expense_names and ref not in group_names:
                        raise ValueError(f"{where}: unknown expense or group {ref!r}")
                check_inflation(pool.fixed_inflation, where)
                for adj in pool.expense_adjustments:
                    require(adj.expense, expense_names, "expense", where)

        for gv in (self.general_vacancy, self.credit_loss):
            for override in gv.tenant_overrides:
                require(override.tenant_ref, tenant_refs, "tenant", "vacancy/credit loss override")

        for cat in self.ti_categories:
            check_inflation(cat.inflation, f"ti_category {cat.name!r}")
        for cat in self.lc_categories:
            check_inflation(cat.inflation, f"lc_category {cat.name!r}")

        return self

    def _check_unique_names(self) -> None:
        collections = {
            "market_leasing_profiles": [p.name for p in self.market_leasing_profiles],
            "free_rent_profiles": [p.name for p in self.free_rent_profiles],
            "ti_categories": [c.name for c in self.ti_categories],
            "lc_categories": [c.name for c in self.lc_categories],
            "recovery_structures": [s.name for s in self.recovery_structures],
            "expenses": [e.name for e in self.expenses],
            "expense_groups": [g.name for g in self.expense_groups],
            "custom_indices": [i.name for i in self.inflation.custom_indices],
            "loans": [ln.name for ln in self.loans],
        }
        for coll, names in collections.items():
            dupes = {n for n in names if names.count(n) > 1}
            if dupes:
                raise ValueError(f"duplicate names in {coll}: {sorted(dupes)}")
