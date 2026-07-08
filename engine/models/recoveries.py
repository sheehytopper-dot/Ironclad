"""Expense recovery structures and per-lease assignments (spec §3.14)
[AE pp. 404-413, 517-520].
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import Field, model_validator

from .common import InflationRef, Ref, StrictModel


class RecoverySystemMethod(str, Enum):
    """System methods assignable directly on a lease (spec §3.14)."""

    none = "none"
    net = "net"                        # 100% pro-rata of recoverable expenses
    base_stop = "base_stop"            # recover over a $/SF stop
    base_year = "base_year"            # over actual expenses of a named year, frozen
    base_year_plus_1 = "base_year_plus_1"
    fixed = "fixed"                    # $ or $/SF amount, inflatable
    structure = "structure"            # user-defined RecoveryStructure by name


class RecoveryAssignment(StrictModel):
    """How a lease (or MLP speculative lease) recovers expenses."""

    method: RecoverySystemMethod = RecoverySystemMethod.net
    stop_amount_per_area: Optional[float] = None      # base_stop: $/SF stop
    base_year: Optional[int] = None                   # base_year methods: calendar year (None = year 1)
    base_year_gross_up_pct: Optional[float] = None    # optionally gross up the frozen base year
    base_year_amount: Optional[float] = None          # known frozen base-year pool TOTAL $/yr (see below)
    fixed_amount: Optional[float] = None              # fixed: $ or
    fixed_amount_per_area: Optional[float] = None     # fixed: $/SF
    fixed_inflation: InflationRef = None
    structure_ref: Optional[Ref] = None               # method == structure

    # ``base_year_amount`` is the known frozen base-year pool as a TOTAL annual
    # dollar figure (not $/SF), consistent with how the base_year methods
    # compute their stop — the reimbursable-expense pool summed over the base
    # year, before the tenant's pro-rata share is applied. Only ``base_stop``
    # is a $/SF quantity (``stop_amount_per_area``). When set, this value is
    # used directly as the frozen base-year pool and ``base_year`` stays purely
    # documentation of which calendar year the figure represents; the computed
    # window / pre-analysis fallback is bypassed entirely (spec §3.14).

    @model_validator(mode="after")
    def _method_inputs(self) -> "RecoveryAssignment":
        if self.method == RecoverySystemMethod.base_stop and self.stop_amount_per_area is None:
            raise ValueError("base_stop requires stop_amount_per_area")
        if self.method == RecoverySystemMethod.fixed and (
            self.fixed_amount is None and self.fixed_amount_per_area is None
        ):
            raise ValueError("fixed requires fixed_amount or fixed_amount_per_area")
        if self.method == RecoverySystemMethod.structure and self.structure_ref is None:
            raise ValueError("structure method requires structure_ref")
        if self.base_year_amount is not None and self.method not in (
            RecoverySystemMethod.base_year, RecoverySystemMethod.base_year_plus_1
        ):
            raise ValueError(
                "base_year_amount applies only to the base_year / "
                "base_year_plus_1 methods"
            )
        return self


class PoolMethod(str, Enum):
    net = "net"
    stop = "stop"
    base_year = "base_year"
    fixed = "fixed"


class AdminFeeApplies(str, Enum):
    """Whether the admin fee is added before or after the stop/base is
    subtracted [AE p. 520]."""

    before_stop = "before_stop"
    after_stop = "after_stop"


class Denominator(str, Enum):
    rentable_area = "rentable_area"
    property_size = "property_size"
    occupied_area = "occupied_area"
    fixed_area = "fixed_area"


class BaseYearSpec(StrictModel):
    """Base-year pool basis: expenses of a named calendar/fiscal year, value
    frozen, optionally grossed up.

    ``known_amount`` is the known frozen base-year pool as a TOTAL annual
    dollar figure (the pool's reimbursable expenses summed over the base year,
    before pro-rata division — the same quantity the computed base-year path
    produces). When set, it is used directly and ``year`` becomes pure
    documentation of which calendar year the figure represents; the computed
    window and the pre-analysis fallback are bypassed (spec §3.14).
    """

    year: Optional[int] = None  # None = analysis year 1
    fiscal: bool = False
    gross_up_pct: Optional[float] = None
    known_amount: Optional[float] = None  # known frozen base-year pool TOTAL $/yr


class CapsFloors(StrictModel):
    """Recovery caps/floors, applied per pool (spec §3.14) [AE pp. 411-412]."""

    yearly_cap_pct: Optional[float] = None      # YoY growth cap
    cumulative_cap_pct: Optional[float] = None
    min: Optional[float] = None
    max: Optional[float] = None


class ExpenseAdjustment(StrictModel):
    """Exclusion/addition applied to a pool's expenses (spec §3.14, per pool)
    [AE p. 410]."""

    expense: Ref
    action: str = "exclude"  # "exclude" | "add"
    pct: float = 100.0       # portion of the expense to exclude/add


class RecoveryPool(StrictModel):
    """One expense pool within a user-defined recovery structure.

    Gross-up formula [AE p. 407]: grossed expense = fixed portion + variable
    portion × (gross_up_pct / actual occupancy %) when actual < target; never
    gross down. Tenant recovery = (pool expense after adjustments − stop/base)
    × pro-rata share, floored at 0, capped per this pool's ``caps_floors``.
    Caps/floors and expense adjustments are per pool (spec §3.14), so e.g. a
    capped CAM pool can sit beside an uncapped tax pool in one structure.
    """

    expenses: list[Ref]  # expense account names or expense group names
    method: PoolMethod = PoolMethod.net
    gross_up_pct: Optional[float] = Field(default=None, gt=0, le=100)
    base_amount_per_area: Optional[float] = None      # stop method: $/SF
    base_year: Optional[BaseYearSpec] = None          # base_year method
    fixed_amount: Optional[float] = None              # fixed method
    fixed_inflation: InflationRef = None
    admin_fee_pct: float = 0.0
    admin_fee_applies: AdminFeeApplies = AdminFeeApplies.before_stop
    denominator: Denominator = Denominator.rentable_area
    denominator_fixed_area: Optional[float] = Field(default=None, gt=0)
    pro_rata_share_override: Optional[float] = None   # % override of tenant share
    caps_floors: Optional[CapsFloors] = None          # [AE pp. 411-412]
    expense_adjustments: list[ExpenseAdjustment] = [] # [AE p. 410]

    @model_validator(mode="after")
    def _method_inputs(self) -> "RecoveryPool":
        if self.method == PoolMethod.stop and self.base_amount_per_area is None:
            raise ValueError("stop pool requires base_amount_per_area")
        if self.method == PoolMethod.fixed and self.fixed_amount is None:
            raise ValueError("fixed pool requires fixed_amount")
        if self.denominator == Denominator.fixed_area and self.denominator_fixed_area is None:
            raise ValueError("fixed_area denominator requires denominator_fixed_area")
        return self


class RecoveryStructure(StrictModel):
    """User-defined recovery structure (spec §3.14) [AE pp. 404-413]: a named
    list of pools. Caps/floors and expense adjustments live on each pool.

    Recovery revenue posts monthly as 1/12 of the annualized computation; v1
    uses straight monthly accrual (true-up in a reconciliation month is a
    policy toggle, spec §3.14).
    """

    name: str
    pools: list[RecoveryPool] = Field(min_length=1)
