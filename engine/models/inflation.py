"""Inflation rate schedules and custom indices (spec §3.3) [AE pp. 219-223]."""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import Field

from .common import StrictModel, YearRate


class TimingBasis(str, Enum):
    analysis_year = "analysis_year"
    calendar_year = "calendar_year"


class CustomIndex(StrictModel):
    """A named inflation index assignable anywhere an inflation picker exists."""

    name: str
    rates: list[YearRate]


class Inflation(StrictModel):
    """Inflation assumptions (spec §3.3) [AE pp. 219-223].

    Inflation factor for month m = Π(1 + rate_y) over completed inflation
    anniversaries before m. Rates step on ``inflation_month`` (defaults to the
    analysis begin month when None), not necessarily January.
    """

    general_rate: list[YearRate]
    market_rent_rate: Optional[list[YearRate]] = None  # defaults to general
    expense_rate: Optional[list[YearRate]] = None      # defaults to general
    cpi_rate: Optional[list[YearRate]] = None          # defaults to general
    custom_indices: list[CustomIndex] = []
    inflation_month: Optional[int] = Field(default=None, ge=1, le=12)  # None = analysis begin month
    timing_basis: TimingBasis = TimingBasis.analysis_year
