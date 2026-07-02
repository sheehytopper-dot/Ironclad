"""Rent roll (contract leases) and space absorption (spec §3.12, §3.15)
[AE pp. 363-403].
"""
from __future__ import annotations

import datetime as dt
from enum import Enum
from typing import Optional

from pydantic import Field, model_validator

from .common import MoneyRate, Ref, RentStep, StrictModel
from .cpi import CPISpec
from .market_leasing import LCSpec, UponExpiration
from .profiles import MiscItemSpec, PercentRentSpec, SecurityDepositSpec
from .recoveries import RecoveryAssignment


class LeaseType(str, Enum):
    """Drives report grouping + cap valuation treatment (spec §3.12)."""

    office = "office"
    industrial = "industrial"
    retail = "retail"


class LeaseStatus(str, Enum):
    contract = "contract"
    speculative = "speculative"
    mtm = "mtm"  # month-to-month


class FreeRentTiming(str, Enum):
    front = "front"
    custom = "custom"


class FreeRent(StrictModel):
    """Free-rent months on a contract lease (spec §3.12). ``custom_months``
    are 1-based month offsets within the lease term."""

    months: float = Field(ge=0)
    timing: FreeRentTiming = FreeRentTiming.front
    custom_months: Optional[list[int]] = None
    profile: Optional[Ref] = None  # FreeRentProfile: which charges abate

    @model_validator(mode="after")
    def _custom(self) -> "FreeRent":
        if self.timing == FreeRentTiming.custom and not self.custom_months:
            raise ValueError("custom free-rent timing requires custom_months")
        return self


class LeasingCosts(StrictModel):
    """TIs/LCs for the contract term (usually zero; rollover costs come from
    the MLP). Inline specs or refs to named TI/LC categories (spec §3.9)."""

    ti: Optional[MoneyRate] = None
    ti_category: Optional[Ref] = None
    lc: Optional[LCSpec] = None
    lc_category: Optional[Ref] = None


class Lease(StrictModel):
    """One rent roll record per lease/suite (spec §3.12) [AE pp. 363-390].

    Base rent calc examples are normative [AE pp. 391-394]: each worked
    example (per SF/yr, per SF/mo, per yr, per mo, % of market, % of market
    with steps) becomes a unit test when ``engine/calc/leases.py`` is built.
    """

    tenant_name: str
    suite: Optional[str] = None
    external_id: Optional[str] = None
    area: float = Field(gt=0)  # SF (v1: single area for the term)
    lease_type: LeaseType
    start_date: dt.date
    end_date: Optional[dt.date] = None       # or start + term_months
    term_months: Optional[int] = Field(default=None, ge=1)
    status: LeaseStatus = LeaseStatus.contract
    base_rent: MoneyRate                      # [AE pp. 367-373; examples p. 391]
    rent_steps: list[RentStep] = []           # fixed steps or % bumps
    cpi: Optional[CPISpec] = None             # [AE p. 374]
    free_rent: Optional[FreeRent] = None
    recoveries: RecoveryAssignment = RecoveryAssignment()
    percentage_rent: Optional[PercentRentSpec] = None
    miscellaneous_items: list[MiscItemSpec] = []  # [AE pp. 378-382]
    leasing_costs: Optional[LeasingCosts] = None
    security_deposit: Optional[SecurityDepositSpec] = None  # [AE p. 384; pp. 431-433]
    market_leasing_profile: Optional[Ref] = None  # governs expiration [AE p. 385]
    upon_expiration: UponExpiration = UponExpiration.market
    option_profile: Optional[Ref] = None      # for upon_expiration == option
    tenant_classifications: dict[str, str] = {}
    notes: Optional[str] = None

    @model_validator(mode="after")
    def _check(self) -> "Lease":
        if (self.end_date is None) == (self.term_months is None):
            raise ValueError("exactly one of end_date / term_months is required")
        if self.end_date is not None and self.end_date <= self.start_date:
            raise ValueError("end_date must be after start_date")
        if self.upon_expiration == UponExpiration.option and self.option_profile is None:
            raise ValueError("upon_expiration 'option' requires option_profile")
        return self


class AbsorptionSpec(StrictModel):
    """Lease-up of currently vacant space (spec §3.15) [AE pp. 395-403].

    Generates synthetic leases on the schedule; each behaves like a rent roll
    lease thereafter (rollover chains etc.). Give exactly one of
    ``number_of_leases`` / ``area_per_lease``.
    """

    name: str
    total_area: float = Field(gt=0)
    number_of_leases: Optional[int] = Field(default=None, ge=1)
    area_per_lease: Optional[float] = Field(default=None, gt=0)
    start_date: dt.date
    interval_months: int = Field(default=1, ge=0)  # between lease starts
    lease_type: LeaseType = LeaseType.office
    market_leasing_profile: Ref  # or inline lease terms (v1: profile only)

    @model_validator(mode="after")
    def _one_of(self) -> "AbsorptionSpec":
        if (self.number_of_leases is None) == (self.area_per_lease is None):
            raise ValueError(
                "exactly one of number_of_leases / area_per_lease is required"
            )
        return self
