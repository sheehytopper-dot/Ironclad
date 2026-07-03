"""Valuation inputs: DCF, direct cap, resale, sensitivity (spec §3.18)
[AE pp. 450-476].
"""
from __future__ import annotations

import datetime as dt
from enum import Enum
from typing import Literal, Optional, Union

from pydantic import Field, model_validator

from .common import StrictModel


class DiscountMethod(str, Enum):
    """Period discounting [AE pp. 472-473]."""

    annual = "annual"
    quarterly = "quarterly"
    monthly = "monthly"


class PeriodConvention(str, Enum):
    end_of_period = "end_of_period"
    mid_period = "mid_period"


class NOIBasis(str, Enum):
    year_1 = "year_1"
    forward_12 = "forward_12"


class DirectCap(StrictModel):
    """Direct capitalization [AE pp. 453-454]."""

    cap_rate: float = Field(gt=0)  # percent
    noi_basis: NOIBasis = NOIBasis.year_1


class ResaleMethod(str, Enum):
    """[AE pp. 464-471]."""

    cap_noi_forward_12 = "cap_noi_forward_12"
    cap_noi_current_year = "cap_noi_current_year"
    gross_value_less_costs = "gross_value_less_costs"
    fixed_amount = "fixed_amount"
    pct_increase_over_price = "pct_increase_over_price"


class StabilizedOccupancy(StrictModel):
    """Recompute the resale forward NOI with stabilized vacancy [AE p. 468]."""

    occupancy_pct: float = Field(gt=0, le=100)


class NOIAdjustments(StrictModel):
    exclude_capital: bool = True
    stabilize_occupancy: Optional[StabilizedOccupancy] = None


class ResaleAdjustment(StrictModel):
    """Dollar adjustment to resale proceeds [AE p. 469]."""

    name: str
    amount: float  # negative reduces proceeds


class Resale(StrictModel):
    """Property resale (spec §3.18) [AE pp. 464-471]. ``resale_date`` of
    None means end of the analysis term (the default)."""

    method: ResaleMethod = ResaleMethod.cap_noi_forward_12
    exit_cap_rate: Optional[float] = Field(default=None, gt=0)  # cap methods
    fixed_amount: Optional[float] = None                        # fixed_amount method
    pct_increase: Optional[float] = None                        # pct_increase_over_price
    resale_date: Optional[dt.date] = None
    noi_adjustments: NOIAdjustments = NOIAdjustments()
    selling_costs_pct: float = 0.0
    adjustment_amounts: list[ResaleAdjustment] = []  # [AE p. 469]
    apply_resale_to_cash_flow: bool = True

    @model_validator(mode="after")
    def _method_inputs(self) -> "Resale":
        cap_methods = (
            ResaleMethod.cap_noi_forward_12,
            ResaleMethod.cap_noi_current_year,
            ResaleMethod.gross_value_less_costs,
        )
        if self.method in cap_methods and self.exit_cap_rate is None:
            raise ValueError(
                f"the resale method '{self.method.value}' values the property by "
                "capitalizing income, so 'exit_cap_rate' is required. Enter the exit "
                "capitalization rate as a percent — for example 6.5 for 6.5%. There is "
                "no default: the exit cap rate must come from the deal."
            )
        if self.method == ResaleMethod.fixed_amount and self.fixed_amount is None:
            raise ValueError(
                "the resale method 'fixed_amount' requires 'fixed_amount': "
                "the gross sale price in dollars."
            )
        if self.method == ResaleMethod.pct_increase_over_price and self.pct_increase is None:
            raise ValueError(
                "the resale method 'pct_increase_over_price' requires 'pct_increase': "
                "the total percent increase over the purchase price, e.g. 20 for 20%."
            )
        return self


class SensitivityIntervals(StrictModel):
    """Sensitivity matrix grid steps [AE pp. 451-452]."""

    discount_rate_step: float = Field(default=0.25, gt=0)  # percentage points
    cap_rate_step: float = Field(default=0.25, gt=0)
    count: Union[Literal[5], Literal[7]] = 5


class ValuationInputs(StrictModel):
    """DCF valuation assumptions (spec §3.18) [AE pp. 450-476]. ``pv_start``
    of None means the analysis begin date.

    ``resale`` is required with no default — an exit assumption is a deal
    input, never a silent number (spec §1.3 principle 3).
    """

    discount_rate: float = Field(gt=0)  # unleveraged; annual nominal, percent
    discount_method: DiscountMethod = DiscountMethod.annual
    period_convention: PeriodConvention = PeriodConvention.end_of_period
    pv_start: Optional[dt.date] = None
    direct_cap: Optional[DirectCap] = None
    resale: Resale
    sensitivity_intervals: SensitivityIntervals = SensitivityIntervals()
