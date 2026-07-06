"""Pydantic input models for the §3 data schema (ARGUS_REBUILD_SPEC.md).

Everything serializes inside one :class:`PropertyModel` JSON document
(``.icprop.json``, spec §5.1). Field names are normative per the spec.
"""
from .common import (
    Address,
    InflationRef,
    Limits,
    MoneyRate,
    MoneyUnit,
    PctOfNew,
    Ref,
    RentStep,
    StrictModel,
    Timing,
    TimingMethod,
    YearRate,
)
from .cpi import CPIMethod, CPISpec
from .expenses import ExpenseCategory, ExpenseGroup, ExpenseItem, ExpenseUnit
from .inflation import CustomIndex, Inflation, TimingBasis
from .investment import (
    AdditionalPrincipal,
    ClosingCost,
    ClosingCostTiming,
    FloatingRate,
    Loan,
    LoanAmount,
    LoanAmountBasis,
    LoanCostHandling,
    LoanCosts,
    LoanType,
    PriceDerivation,
    Purchase,
)
from .io import PROPERTY_FILE_SUFFIX, load_property, save_property
from .leases import (
    AbsorptionSpec,
    FreeRent,
    FreeRentTiming,
    Lease,
    LeaseStatus,
    LeaseType,
    LeasingCosts,
)
from .market_leasing import (
    IntelligentRenewalRule,
    LCSpec,
    MarketLeasingProfile,
    UponExpiration,
)
from .profiles import (
    BreakpointLayer,
    FreeRentProfile,
    LCCategory,
    LCMethod,
    LCPayableTiming,
    LCTier,
    MiscItemSpec,
    PercentRentBreakpoint,
    PercentRentSpec,
    SalesVolume,
    SalesVolumeUnit,
    SecurityDepositSpec,
    SecurityDepositUnit,
    TICategory,
    TIPaymentTiming,
)
from .property import (
    AreaMeasures,
    AreaScheduleEntry,
    PropertyInfo,
    PropertyType,
    RentableAreaMode,
)
from .property_model import BUILTIN_INDICES, SCHEMA_VERSION, PropertyModel
from .recoveries import (
    AdminFeeApplies,
    BaseYearSpec,
    CapsFloors,
    Denominator,
    ExpenseAdjustment,
    PoolMethod,
    RecoveryAssignment,
    RecoveryPool,
    RecoveryStructure,
    RecoverySystemMethod,
)
from .revenues import PropertyRevenue, RevenueUnit
from .vacancy import CreditLoss, GeneralVacancy, TenantOverride, VacancyMethod
from .valuation import (
    DirectCap,
    DiscountMethod,
    NOIAdjustments,
    NOIBasis,
    PeriodConvention,
    Resale,
    ResaleAdjustment,
    ResaleMethod,
    SensitivityIntervals,
    StabilizedOccupancy,
    ValuationInputs,
)

__all__ = [
    # common
    "Address", "InflationRef", "Limits", "MoneyRate", "MoneyUnit", "PctOfNew",
    "Ref", "RentStep", "StrictModel", "Timing", "TimingMethod", "YearRate",
    # property
    "AreaMeasures", "AreaScheduleEntry", "PropertyInfo", "PropertyType",
    "RentableAreaMode",
    # inflation
    "CustomIndex", "Inflation", "TimingBasis",
    # vacancy / credit loss
    "CreditLoss", "GeneralVacancy", "TenantOverride", "VacancyMethod",
    # market leasing
    "IntelligentRenewalRule", "LCSpec", "MarketLeasingProfile", "UponExpiration",
    # cpi
    "CPIMethod", "CPISpec",
    # profiles
    "BreakpointLayer", "FreeRentProfile", "LCCategory", "LCMethod",
    "LCPayableTiming", "LCTier", "MiscItemSpec", "PercentRentBreakpoint",
    "PercentRentSpec", "SalesVolume", "SalesVolumeUnit", "SecurityDepositSpec",
    "SecurityDepositUnit", "TICategory", "TIPaymentTiming",
    # revenues / expenses
    "PropertyRevenue", "RevenueUnit",
    "ExpenseCategory", "ExpenseGroup", "ExpenseItem", "ExpenseUnit",
    # leases / absorption
    "AbsorptionSpec", "FreeRent", "FreeRentTiming", "Lease", "LeaseStatus",
    "LeaseType", "LeasingCosts",
    # recoveries
    "AdminFeeApplies", "BaseYearSpec", "CapsFloors", "Denominator",
    "ExpenseAdjustment", "PoolMethod", "RecoveryAssignment", "RecoveryPool",
    "RecoveryStructure", "RecoverySystemMethod",
    # investment
    "AdditionalPrincipal", "ClosingCost", "ClosingCostTiming", "FloatingRate",
    "Loan", "LoanAmount", "LoanAmountBasis", "LoanCostHandling", "LoanCosts",
    "LoanType", "PriceDerivation", "Purchase",
    # valuation
    "DirectCap", "DiscountMethod", "NOIAdjustments", "NOIBasis",
    "PeriodConvention", "Resale", "ResaleAdjustment", "ResaleMethod",
    "SensitivityIntervals", "StabilizedOccupancy", "ValuationInputs",
    # document + io
    "BUILTIN_INDICES", "SCHEMA_VERSION", "PropertyModel",
    "PROPERTY_FILE_SUFFIX", "load_property", "save_property",
]
