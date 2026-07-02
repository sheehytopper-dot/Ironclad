"""Named profiles referenced by leases and MLPs: free rent profiles, TI/LC
categories, security deposits, and tenant miscellaneous items
(spec §3.8-3.9; misc items per §3.6/§3.12).
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import Field, model_validator

from .common import (
    InflationRef,
    Limits,
    MoneyRate,
    MoneyUnit,
    Ref,
    StrictModel,
    Timing,
)


class FreeRentProfile(StrictModel):
    """Which charge types abate during free-rent months (spec §3.8)
    [AE pp. 253-254]: base rent only, or base + recoveries + misc."""

    name: str
    abate_base_rent: bool = True
    abate_recoveries: bool = False
    abate_miscellaneous: bool = False


class TIPaymentTiming(str, Enum):
    lease_start = "lease_start"
    spread = "spread"  # spread over months from lease start


class TICategory(StrictModel):
    """Named tenant-improvement allowance spec (spec §3.9) [AE pp. 258-262]."""

    name: str
    new: MoneyRate            # typically $/SF
    renew: MoneyRate
    inflation: InflationRef = None
    payment_timing: TIPaymentTiming = TIPaymentTiming.lease_start
    spread_months: Optional[int] = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _spread(self) -> "TICategory":
        if self.payment_timing == TIPaymentTiming.spread and self.spread_months is None:
            raise ValueError("payment_timing 'spread' requires spread_months")
        return self


class LCMethod(str, Enum):
    pct_of_first_year_rent = "pct_of_first_year_rent"
    pct_of_total_lease_value = "pct_of_total_lease_value"
    fixed_per_area = "fixed_per_area"  # $/SF
    tiered_by_year = "tiered_by_year"  # e.g., 6% yr 1, 3% yrs 2+


class LCTier(StrictModel):
    """One tier of a year-tiered commission: ``pct`` applies from
    ``from_year`` through ``to_year`` (None = through end of lease)."""

    from_year: int = Field(ge=1)
    to_year: Optional[int] = Field(default=None, ge=1)
    pct: float


class LCPayableTiming(str, Enum):
    lease_start = "lease_start"
    split_start_occupancy = "split_start_occupancy"


class LCCategory(StrictModel):
    """Named leasing-commission spec (spec §3.9) [AE pp. 246-248, 258-262].

    ``include_escalations`` flags whether commissions calculate on base rent
    only or base + escalations (elements-to-include).
    """

    name: str
    method: LCMethod
    pct: Optional[float] = None                  # for the pct_* methods
    amount_per_area: Optional[float] = None      # for fixed_per_area
    tiers: Optional[list[LCTier]] = None         # for tiered_by_year
    payable_timing: LCPayableTiming = LCPayableTiming.lease_start
    include_escalations: bool = False
    inflation: InflationRef = None

    @model_validator(mode="after")
    def _method_inputs(self) -> "LCCategory":
        if self.method in (LCMethod.pct_of_first_year_rent, LCMethod.pct_of_total_lease_value):
            if self.pct is None:
                raise ValueError(f"method '{self.method.value}' requires pct")
        elif self.method == LCMethod.fixed_per_area:
            if self.amount_per_area is None:
                raise ValueError("method 'fixed_per_area' requires amount_per_area")
        elif self.method == LCMethod.tiered_by_year:
            if not self.tiers:
                raise ValueError("method 'tiered_by_year' requires tiers")
        return self


class SecurityDepositUnit(str, Enum):
    dollars = "dollars"
    dollars_per_area = "dollars_per_area"
    months_of_rent = "months_of_rent"


class SecurityDepositSpec(StrictModel):
    """Tenant security deposit (spec §3.12) [AE p. 384; pp. 431-433]."""

    amount: float
    unit: SecurityDepositUnit = SecurityDepositUnit.months_of_rent
    refunded_at_expiration: bool = True


class MiscItemSpec(StrictModel):
    """Per-tenant miscellaneous charge or abatement (negative amount)
    (spec §3.12) [AE pp. 378-382]; also carried on rollover via MLPs
    [AE pp. 240-244]. Posts to Miscellaneous Tenant Revenue."""

    name: str
    amount: float
    unit: MoneyUnit
    timing: Timing = Timing()
    inflation: InflationRef = None
    limits: Optional[Limits] = None
    free_rent_abates: bool = False  # abated by free rent when the profile says so


class PercentRentBreakpoint(str, Enum):
    natural = "natural"  # annual base rent / layer pct
    fixed_amount = "fixed_amount"
    zero = "zero"


class SalesVolumeUnit(str, Enum):
    dollars_per_year = "dollars_per_year"
    dollars_per_area_per_year = "dollars_per_area_per_year"


class SalesVolume(StrictModel):
    amount: float
    unit: SalesVolumeUnit = SalesVolumeUnit.dollars_per_year
    growth: InflationRef = None


class BreakpointLayer(StrictModel):
    """One tiered-overage layer: pct of sales above breakpoint_amount.
    ``breakpoint_amount`` is None for natural/zero breakpoints."""

    breakpoint_amount: Optional[float] = None
    pct: float = Field(gt=0)


class PercentRentSpec(StrictModel):
    """Retail percentage rent (spec §3.13) [AE pp. 249-250, 376].

    Pct rent payable = Σ max(0, sales − breakpoint) × pct per layer; natural
    breakpoint = annual base rent / layer pct. Up to 6 layers.
    """

    sales_volume: SalesVolume
    breakpoint: PercentRentBreakpoint = PercentRentBreakpoint.natural
    breakpoint_layers: list[BreakpointLayer] = Field(min_length=1, max_length=6)

    @model_validator(mode="after")
    def _fixed_needs_amounts(self) -> "PercentRentSpec":
        if self.breakpoint == PercentRentBreakpoint.fixed_amount:
            if any(layer.breakpoint_amount is None for layer in self.breakpoint_layers):
                raise ValueError(
                    "fixed_amount breakpoint requires breakpoint_amount on every layer"
                )
        return self
