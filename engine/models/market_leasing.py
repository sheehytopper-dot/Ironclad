"""Market Leasing Profiles — speculative renewal modeling (spec §3.6)
[AE pp. 233-252].

Blending ("Intelligent Renewals", weighted items) [AE pp. 235-236]: when a
lease expires with ``upon_expiration = market`` and renewal probability p:

- weighted market rent = p × renew + (1−p) × new
- weighted downtime   = (1−p) × months_vacant (renewals have zero downtime)
- weighted free rent  = p × free_renew + (1−p) × free_new
- weighted TI / LC    = p × renew + (1−p) × new

The speculative lease begins after weighted downtime, runs ``term_months``,
then chains per ``upon_expiration`` until analysis end + resale horizon.
Downtime posts as Absorption & Turnover Vacancy (negative revenue), not zero
revenue, so PGR reflects full occupancy (spec §2.3). See spec §4.2 for the
normative rollover algorithm.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional, Union

from pydantic import Field, model_validator

from .common import MoneyRate, PctOfNew, Ref, RentStep, StrictModel
from .profiles import MiscItemSpec, PercentRentSpec, SecurityDepositSpec
from .recoveries import RecoveryAssignment


class UponExpiration(str, Enum):
    """Behavior when a lease/segment expires [AE p. 385; spec §3.6, §3.12]."""

    market = "market"      # blend renew/new per this profile, repeat
    option = "option"      # chain to another profile
    renew = "renew"        # 100% renewal
    vacate = "vacate"      # 100% vacate
    reabsorb = "reabsorb"  # space returns to absorption


class LCSpec(StrictModel):
    """Leasing commission on a speculative lease: % of rent for given years,
    or a $/SF / $ amount [AE pp. 246-248]. Give exactly one of ``pct`` /
    ``rate`` (or ``category_ref`` to a named LC category)."""

    pct: Optional[float] = None                # % of rent
    pct_years: Optional[list[int]] = None      # which lease years the % applies to
    rate: Optional[MoneyRate] = None           # $/SF or $ amount
    category_ref: Optional[Ref] = None         # named LCCategory

    @model_validator(mode="after")
    def _one_of(self) -> "LCSpec":
        given = sum(x is not None for x in (self.pct, self.rate, self.category_ref))
        if given != 1:
            raise ValueError("exactly one of pct / rate / category_ref is required")
        return self


class MarketLeasingProfile(StrictModel):
    """One market leasing profile (spec §3.6) [AE pp. 233-252]."""

    name: str
    term_months: int = Field(ge=1)                    # market lease term
    renewal_probability: float = Field(ge=0, le=100)  # percent
    months_vacant: float = Field(ge=0)                # downtime before a NEW lease
    market_base_rent_new: MoneyRate
    market_base_rent_renew: Union[MoneyRate, PctOfNew]
    rent_increases: Optional[list[RentStep]] = None   # within the speculative term
    free_rent_months_new: float = 0.0
    free_rent_months_renew: float = 0.0
    free_rent_profile: Optional[Ref] = None           # which charges abate [AE pp. 253-254]
    recoveries: RecoveryAssignment = RecoveryAssignment()
    ti_new: Optional[MoneyRate] = None                # $/SF or $ [AE p. 245]
    ti_renew: Optional[MoneyRate] = None
    lc_new: Optional[LCSpec] = None                   # [AE pp. 246-248]
    lc_renew: Optional[LCSpec] = None
    security_deposit: Optional[SecurityDepositSpec] = None
    miscellaneous_items: list[MiscItemSpec] = []      # rollover-carried [AE pp. 240-244]
    percentage_rent: Optional[PercentRentSpec] = None # retail speculative [AE pp. 249-250]
    upon_expiration: UponExpiration = UponExpiration.market
    chained_profile: Optional[Ref] = None             # required for option
    term_growth: bool = True  # inflate market rents by the market-rent index
    intelligent_renewals: bool = False  # toggle behavior per [AE p. 235]

    @model_validator(mode="after")
    def _chain(self) -> "MarketLeasingProfile":
        if self.upon_expiration == UponExpiration.option and self.chained_profile is None:
            raise ValueError("upon_expiration 'option' requires chained_profile")
        return self
