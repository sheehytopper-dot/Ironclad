"""Shared primitive types used across the §3 input models.

Refs between models (market leasing profiles, free rent profiles, TI/LC
categories, recovery structures, custom inflation indices, accounts) are
plain strings naming the target; ``PropertyModel`` validates that every
ref resolves.
"""
from __future__ import annotations

import datetime as dt
from enum import Enum
from typing import Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    """Base for all input models: unknown fields are errors (catches typos
    in hand-edited ``.icprop.json`` files and import templates)."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


# A ref is the `name` of another model in the same PropertyModel document.
Ref = str


class YearRate(StrictModel):
    """One year's rate in an annual schedule (inflation, vacancy, floating
    index...). ``year`` is an analysis year (1-based) or a calendar year,
    per the owning model's timing basis. ``rate`` is a percent (3.0 = 3%)."""

    year: int = Field(ge=1)
    rate: float


class MoneyUnit(str, Enum):
    """Amount/unit types for rents, TIs, LCs and market rates
    [AE pp. 367-373; calc examples pp. 391-394]."""

    dollars_per_area_per_year = "dollars_per_area_per_year"    # $/SF/yr
    dollars_per_area_per_month = "dollars_per_area_per_month"  # $/SF/mo
    dollars_per_year = "dollars_per_year"                      # $/yr
    dollars_per_month = "dollars_per_month"                    # $/mo
    dollars_per_area = "dollars_per_area"                      # $/SF one-time (TI)
    dollars = "dollars"                                        # $ one-time
    pct_of_market = "pct_of_market"                            # % of market rent (MLP)
    pct_of_last_rent = "pct_of_last_rent"                      # % of prior contract rent


class MoneyRate(StrictModel):
    """An amount qualified by a unit, e.g. 25.0 $/SF/yr."""

    amount: float
    unit: MoneyUnit


class PctOfNew(StrictModel):
    """Renewal market rent expressed as a % of the new-lease market rent
    (spec §3.6 ``market_base_rent_renew``)."""

    pct_of_new: float = Field(gt=0)


class TimingMethod(str, Enum):
    """Payment frequency/timing patterns [AE pp. 278, 361-362]."""

    continuous = "continuous"
    date_range = "date_range"
    repeating = "repeating"


class Timing(StrictModel):
    """When a revenue/expense item applies [AE pp. 278, 361-362].

    ``repeating``: ``repeat_months`` lists calendar months (1-12) in which the
    amount posts, or ``repeat_every_months`` posts every N months from ``start``.
    """

    method: TimingMethod = TimingMethod.continuous
    start: Optional[dt.date] = None
    end: Optional[dt.date] = None
    repeat_months: Optional[list[int]] = None
    repeat_every_months: Optional[int] = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _check(self) -> "Timing":
        if self.method == TimingMethod.date_range and self.start is None:
            raise ValueError("date_range timing requires a start date")
        if self.method == TimingMethod.repeating and not (
            self.repeat_months or self.repeat_every_months
        ):
            raise ValueError(
                "repeating timing requires repeat_months or repeat_every_months"
            )
        if self.repeat_months and not all(1 <= m <= 12 for m in self.repeat_months):
            raise ValueError("repeat_months entries must be 1-12")
        return self


class Limits(StrictModel):
    """Per-period min/max clamps on a computed amount [AE p. 279]."""

    min: Optional[float] = None
    max: Optional[float] = None


# Inflation override on any monetary input (spec §3.3): a named index ref,
# an explicit annual rate schedule, or None (= item's default index).
InflationRef = Union[Ref, list[YearRate], None]


class RentStep(StrictModel):
    """One fixed step or % bump in a rent step schedule (spec §3.12
    ``rent_steps``; used by MLP ``rent_increases`` too).

    Exactly one of ``date`` / ``month_offset`` locates the step; exactly one
    of ``amount`` / ``pct_increase`` sizes it. ``unit`` is required with
    ``amount``.
    """

    date: Optional[dt.date] = None
    month_offset: Optional[int] = Field(default=None, ge=0)  # months from segment start
    amount: Optional[float] = None
    pct_increase: Optional[float] = None
    unit: Optional[MoneyUnit] = None

    @model_validator(mode="after")
    def _check(self) -> "RentStep":
        if (self.date is None) == (self.month_offset is None):
            raise ValueError("exactly one of date / month_offset is required")
        if (self.amount is None) == (self.pct_increase is None):
            raise ValueError("exactly one of amount / pct_increase is required")
        if self.amount is not None and self.unit is None:
            raise ValueError("unit is required when amount is given")
        return self


class Address(StrictModel):
    """Display-only property address (spec §3.1)."""

    street: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
