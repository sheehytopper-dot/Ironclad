"""Investment: purchase & closing costs, debt (spec §3.16-3.17)
[AE pp. 435-449].
"""
from __future__ import annotations

import datetime as dt
from enum import Enum
from typing import Literal, Optional, Union

from pydantic import Field, model_validator

from .common import StrictModel, YearRate


class PriceDerivation(str, Enum):
    fixed = "fixed"                        # explicit price
    pv_at_discount_rate = "pv_at_discount_rate"  # price = PV at discount rate
    direct_cap = "direct_cap"


class ClosingCostTiming(str, Enum):
    at_purchase = "at_purchase"
    custom_date = "custom_date"


class ClosingCost(StrictModel):
    """Give exactly one of ``amount`` / ``pct_of_price``."""

    name: str
    amount: Optional[float] = None
    pct_of_price: Optional[float] = None
    timing: ClosingCostTiming = ClosingCostTiming.at_purchase
    date: Optional[dt.date] = None

    @model_validator(mode="after")
    def _check(self) -> "ClosingCost":
        if (self.amount is None) == (self.pct_of_price is None):
            raise ValueError("exactly one of amount / pct_of_price is required")
        if self.timing == ClosingCostTiming.custom_date and self.date is None:
            raise ValueError("custom_date timing requires date")
        return self


class Purchase(StrictModel):
    """Property purchase (spec §3.16) [AE pp. 435-437]. ``date`` of None
    means the analysis begin date."""

    price: Optional[float] = None  # required when derivation is fixed
    derivation: PriceDerivation = PriceDerivation.fixed
    date: Optional[dt.date] = None
    closing_costs: list[ClosingCost] = []

    @model_validator(mode="after")
    def _price(self) -> "Purchase":
        if self.derivation == PriceDerivation.fixed and self.price is None:
            raise ValueError("fixed price derivation requires price")
        return self


class LoanType(str, Enum):
    fixed = "fixed"
    floating = "floating"


class LoanAmountBasis(str, Enum):
    amount = "amount"
    pct_of_price = "pct_of_price"
    pct_of_value = "pct_of_value"


class LoanAmount(StrictModel):
    basis: LoanAmountBasis = LoanAmountBasis.amount
    value: float = Field(gt=0)  # $ amount or percent per basis


class FloatingRate(StrictModel):
    """Floating = index + spread, monthly reset (spec §3.17)."""

    index: list[YearRate]  # rate schedule
    spread: float = 0.0    # percent


class AdditionalPrincipal(StrictModel):
    """Additional principal payment [AE p. 444]."""

    date: dt.date
    amount: float = Field(gt=0)


class LoanCostHandling(str, Enum):
    amortize = "amortize"
    expense = "expense"


class LoanCosts(StrictModel):
    """Points and fees [AE pp. 445-446]."""

    points_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    fees: float = Field(default=0.0, ge=0.0)
    timing: Optional[dt.date] = None  # None = funding date
    handling: LoanCostHandling = LoanCostHandling.expense


class Loan(StrictModel):
    """One loan (spec §3.17) [AE pp. 438-449]. Multiple loans supported.

    Standard mortgage math: payment = P × r / (1 − (1+r)^−n), r = annual/12.
    ``amortization``: years, or "interest_only" / "fully_amortizing".
    "Other Debt" simple-interest lines [AE pp. 448-449] are modeled as
    fixed-payment loans.
    """

    name: str
    type: LoanType = LoanType.fixed
    amount: LoanAmount
    funding_date: Optional[dt.date] = None  # None = analysis begin / purchase date
    maturity_date: Optional[dt.date] = None
    term_months: Optional[int] = Field(default=None, ge=1)
    rate: Union[float, FloatingRate]  # fixed annual % or floating spec
    interest_only_months: int = Field(default=0, ge=0)
    amortization: Union[int, Literal["interest_only", "fully_amortizing"]] = (
        "fully_amortizing"
    )
    payment_frequency: Literal["monthly"] = "monthly"
    additional_principal: list[AdditionalPrincipal] = []  # [AE p. 444]
    loan_costs: Optional[LoanCosts] = None  # [AE pp. 445-446]

    @model_validator(mode="after")
    def _check(self) -> "Loan":
        if (self.maturity_date is None) == (self.term_months is None):
            raise ValueError("exactly one of maturity_date / term_months is required")
        if self.type == LoanType.fixed and not isinstance(self.rate, (int, float)):
            raise ValueError("fixed loans require a numeric rate")
        if self.type == LoanType.floating and not isinstance(self.rate, FloatingRate):
            raise ValueError("floating loans require a FloatingRate rate")
        # Economic sanity bounds (Codex finding #12): a fixed rate is an
        # annual percent in [0, 100]; a floating spread is a percent in
        # [-100, 100] (the index carries the base rate); an int
        # amortization is a positive number of years. These catch obvious
        # input errors (e.g. a rate typed as a decimal, a zero
        # amortization term) rather than computing silent nonsense.
        if isinstance(self.rate, (int, float)) and not 0.0 <= self.rate <= 100.0:
            raise ValueError(
                f"fixed loan rate {self.rate} is outside the sane range "
                "0-100 (enter an annual percent, e.g. 6.5 for 6.5%)"
            )
        if isinstance(self.rate, FloatingRate) and not -100.0 <= self.rate.spread <= 100.0:
            raise ValueError(
                f"floating loan spread {self.rate.spread} is outside the "
                "sane range -100 to 100 percent"
            )
        if isinstance(self.amortization, int) and self.amortization < 1:
            raise ValueError(
                f"integer amortization must be a positive number of years, "
                f"got {self.amortization} (use 'interest_only' or "
                "'fully_amortizing' for the non-amortizing / term cases)"
            )
        return self
