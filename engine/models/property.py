"""Property description, timing, and area measures (spec §3.1-3.2).

[AE pp. 182-196]
"""
from __future__ import annotations

import datetime as dt
from enum import Enum
from typing import Optional

from pydantic import Field, field_validator, model_validator

from .common import Address, StrictModel


class PropertyType(str, Enum):
    office = "office"
    industrial = "industrial"
    retail = "retail"
    mixed = "mixed"


class PropertyInfo(StrictModel):
    """Property description and analysis timing (spec §3.1) [AE pp. 182-187]."""

    name: str
    external_id: Optional[str] = None
    property_type: PropertyType
    address: Address = Address()
    analysis_begin: dt.date  # first day of a month; all timing snaps to months
    analysis_term_years: int = Field(ge=1, le=100)  # 1-30 typical; engine supports 100
    fiscal_year_end_month: int = Field(default=12, ge=1, le=12)
    currency: str = "USD"
    area_unit: str = "SF"

    @field_validator("analysis_begin")
    @classmethod
    def _first_of_month(cls, v: dt.date) -> dt.date:
        if v.day != 1:
            raise ValueError("analysis_begin must be the first day of a month")
        return v


class RentableAreaMode(str, Enum):
    derived = "derived"  # sum of rent roll + absorption areas ("Derive from tenants")
    fixed = "fixed"
    schedule = "schedule"


class AreaScheduleEntry(StrictModel):
    date: dt.date
    area: float = Field(gt=0)


class AreaMeasures(StrictModel):
    """Building and rentable area measures (spec §3.2) [AE pp. 188-196].

    Occupied Area is always computed by the engine, never input. Pro-rata
    denominators for recoveries reference Property Size, Rentable Area, or an
    alternate measure per recovery structure (spec §3.14).
    """

    property_size: float = Field(gt=0)  # gross building area, SF
    alternate_size: Optional[float] = Field(default=None, gt=0)
    rentable_area_mode: RentableAreaMode = RentableAreaMode.derived
    rentable_area_fixed: Optional[float] = Field(default=None, gt=0)
    rentable_area_schedule: Optional[list[AreaScheduleEntry]] = None

    @model_validator(mode="after")
    def _mode_inputs(self) -> "AreaMeasures":
        if self.rentable_area_mode == RentableAreaMode.fixed and self.rentable_area_fixed is None:
            raise ValueError("rentable_area_mode 'fixed' requires rentable_area_fixed")
        if self.rentable_area_mode == RentableAreaMode.schedule and not self.rentable_area_schedule:
            raise ValueError("rentable_area_mode 'schedule' requires rentable_area_schedule")
        return self
