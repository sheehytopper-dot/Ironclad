"""Miscellaneous, parking, and storage property revenues (spec §3.10)
[AE pp. 273-296].
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import Field, model_validator

from .common import InflationRef, Limits, Ref, StrictModel, Timing


class RevenueUnit(str, Enum):
    dollars_per_year = "dollars_per_year"
    dollars_per_month = "dollars_per_month"
    dollars_per_area_per_year = "dollars_per_area_per_year"
    dollars_per_area_per_month = "dollars_per_area_per_month"
    pct_of_egr = "pct_of_egr"
    pct_of_pgr = "pct_of_pgr"
    pct_of_account = "pct_of_account"
    per_occupied_area = "per_occupied_area"
    per_available_area = "per_available_area"
    spaces_times_rate = "spaces_times_rate"  # parking: number_of_spaces × rate


class PropertyRevenue(StrictModel):
    """One misc/parking/storage revenue line (spec §3.10) [AE pp. 273-296].

    Percent-of-account types create calculation dependencies; the ledger
    resolves them via ordered passes (spec §4.1 step 9): %-of-EGR items
    reference EGR excluding themselves — one second pass, no fixed-point
    iteration. ``pct_fixed``: the variable portion scales with occupancy.
    """

    name: str
    account: Optional[Ref] = None            # ledger account; defaults by collection
    amount: float
    unit: RevenueUnit
    account_ref: Optional[Ref] = None        # for pct_of_account
    number_of_spaces: Optional[int] = Field(default=None, ge=0)  # parking
    timing: Timing = Timing()                # [AE pp. 278, 361-362]
    inflation: InflationRef = None
    pct_fixed: float = Field(default=100.0, ge=0, le=100)
    limits: Optional[Limits] = None          # [AE p. 279]

    @model_validator(mode="after")
    def _unit_inputs(self) -> "PropertyRevenue":
        if self.unit == RevenueUnit.pct_of_account and self.account_ref is None:
            raise ValueError("unit 'pct_of_account' requires account_ref")
        if self.unit == RevenueUnit.spaces_times_rate and self.number_of_spaces is None:
            raise ValueError("unit 'spaces_times_rate' requires number_of_spaces")
        return self
