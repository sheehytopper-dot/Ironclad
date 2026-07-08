"""Operating, non-operating, and capital expenses (spec §3.11)
[AE pp. 313-345].
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import Field, model_validator

from .common import InflationRef, Limits, Ref, StrictModel, Timing


class ExpenseCategory(str, Enum):
    operating = "operating"          # above NOI; recoverable by default
    non_operating = "non_operating"  # below the line
    capital = "capital"              # after NOI, before CFBDS


class ExpenseUnit(str, Enum):
    """Same amount/unit types as property revenues (spec §3.10/§3.11)."""

    dollars_per_year = "dollars_per_year"
    dollars_per_month = "dollars_per_month"
    dollars_per_area_per_year = "dollars_per_area_per_year"
    dollars_per_area_per_month = "dollars_per_area_per_month"
    pct_of_egr = "pct_of_egr"
    pct_of_pgr = "pct_of_pgr"
    pct_of_account = "pct_of_account"
    per_occupied_area = "per_occupied_area"
    per_available_area = "per_available_area"


class ExpenseGroup(StrictModel):
    """Named grouping of expenses for reporting rollups and recovery pool
    membership [AE pp. 343-345]."""

    name: str
    members: list[Ref] = []  # expense names


class AnnualOverride(StrictModel):
    """A known actual dollar amount for one fiscal year, used directly in
    place of the computed base × inflation for that year — a pragmatic escape
    hatch, not spec-derived ARGUS behavior (DEVIATIONS.md §12; same philosophy
    as ``RecoveryAssignment.base_year_amount``).

    ``year`` is the **fiscal-year label** (the calendar year the fiscal year
    ends in — identical to the calendar year for a December fiscal-year-end,
    the common case). ``amount`` is the full-year dollar figure; the override
    posts ``amount / 12`` per active month of that fiscal year, so a
    full-year-active expense yields exactly ``amount``. The override wins
    completely for its year — no blending with the formula, and it is not
    re-clamped by ``limits``.
    """

    year: int
    amount: float


class ExpenseItem(StrictModel):
    """One expense line (spec §3.11) [AE pp. 313-345].

    ``pct_fixed``: % fixed vs variable with occupancy; the variable portion =
    amount × occupancy%. Recovery structures may then gross variable expenses
    up to a stipulated occupancy (spec §3.14). Operating expenses default
    recoverable; capital/non-operating default not.

    Capital-only fields: ``amortization_years`` recovers the cost over N years
    in recoveries [AE p. 338]; ``refundable`` per [AE pp. 331-341].
    """

    name: str
    category: ExpenseCategory = ExpenseCategory.operating
    account: Optional[Ref] = None
    amount: float
    unit: ExpenseUnit
    account_ref: Optional[Ref] = None  # for pct_of_account
    timing: Timing = Timing()
    inflation: InflationRef = None
    pct_fixed: float = Field(default=100.0, ge=0, le=100)
    limits: Optional[Limits] = None
    annual_overrides: list[AnnualOverride] = []  # known per-year actuals (DEVIATIONS.md §12)
    recoverable: Optional[bool] = None  # None = category default (operating: True)
    expense_group: Optional[Ref] = None
    # capital only:
    amortization_years: Optional[int] = Field(default=None, ge=1)
    refundable: bool = False

    @model_validator(mode="after")
    def _check(self) -> "ExpenseItem":
        if self.unit == ExpenseUnit.pct_of_account and self.account_ref is None:
            raise ValueError("unit 'pct_of_account' requires account_ref")
        if self.category != ExpenseCategory.capital and (
            self.amortization_years is not None or self.refundable
        ):
            raise ValueError(
                "amortization_years/refundable apply to capital expenses only"
            )
        years = [o.year for o in self.annual_overrides]
        if len(years) != len(set(years)):
            raise ValueError(
                "annual_overrides has more than one amount for the same year"
            )
        return self

    @property
    def is_recoverable(self) -> bool:
        """Effective recoverability: explicit flag, else category default."""
        if self.recoverable is not None:
            return self.recoverable
        return self.category == ExpenseCategory.operating
