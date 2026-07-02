"""CPI increase specifications (spec §3.7) [AE pp. 255-257].

Applies to contract leases (rent roll ``cpi``) and speculative leases (via
MLP). Posts to "CPI & Other Adjustment Revenue".
"""
from __future__ import annotations

from enum import Enum
from typing import Literal, Optional, Union

from pydantic import Field

from .common import Ref, StrictModel


class CPIMethod(str, Enum):
    full_cpi = "full_cpi"
    pct_of_cpi = "pct_of_cpi"
    cpi_plus_pct = "cpi_plus_pct"
    min_max_banded = "min_max_banded"


class CPISpec(StrictModel):
    index: Optional[Ref] = None  # cpi_rate (None) or a custom index name
    method: CPIMethod = CPIMethod.full_cpi
    pct: Optional[float] = None  # the % for pct_of_cpi / cpi_plus_pct methods
    first_increase_month: Union[int, Literal["anniversary"]] = "anniversary"
    frequency_months: int = Field(default=12, ge=1)
    cap_pct: Optional[float] = None
    floor_pct: Optional[float] = None
