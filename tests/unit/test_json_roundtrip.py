"""JSON round-trip tests for the §3 PropertyModel schema (Phase 0 gate).

Builds a PropertyModel exercising every §3 model, serializes it to JSON,
reloads it, and asserts equality — plus file round-trip, byte-stable output
(Git-diffable, spec §5.1), and validator behavior. No calculation logic is
tested here; that begins in Phase 1.
"""
import datetime as dt

import pytest
from pydantic import ValidationError

from engine.models import (
    AbsorptionSpec,
    Address,
    AreaMeasures,
    BreakpointLayer,
    ClosingCost,
    CPISpec,
    CustomIndex,
    DirectCap,
    ExpenseCategory,
    ExpenseGroup,
    ExpenseItem,
    ExpenseUnit,
    FloatingRate,
    FreeRent,
    FreeRentProfile,
    GeneralVacancy,
    Inflation,
    LCCategory,
    LCMethod,
    LCSpec,
    LCTier,
    Lease,
    LeaseType,
    LeasingCosts,
    Limits,
    Loan,
    LoanAmount,
    LoanAmountBasis,
    LoanCosts,
    LoanType,
    MarketLeasingProfile,
    MiscItemSpec,
    MoneyRate,
    MoneyUnit,
    PctOfNew,
    PercentRentSpec,
    PropertyInfo,
    PropertyModel,
    PropertyRevenue,
    PropertyType,
    Purchase,
    RecoveryAssignment,
    RecoveryPool,
    RecoveryStructure,
    RecoverySystemMethod,
    RentableAreaMode,
    RentStep,
    Resale,
    ResaleMethod,
    RevenueUnit,
    SalesVolume,
    SecurityDepositSpec,
    SecurityDepositUnit,
    SensitivityIntervals,
    TenantOverride,
    TICategory,
    Timing,
    TimingMethod,
    UponExpiration,
    VacancyMethod,
    ValuationInputs,
    YearRate,
    load_property,
    save_property,
)
from engine.models.investment import AdditionalPrincipal
from engine.models.profiles import PercentRentBreakpoint
from engine.models.recoveries import AdminFeeApplies, Denominator, PoolMethod
from engine.models.vacancy import CreditLoss


@pytest.fixture()
def full_property() -> PropertyModel:
    """A property exercising every §3 model: multi-tenant office + retail,
    MLP chain, base-year and structured recoveries, % rent, absorption,
    revenues, all three expense categories, fixed + floating debt, purchase,
    and full valuation inputs."""
    return PropertyModel(
        property=PropertyInfo(
            name="Ironhorse Plaza",
            external_id="IHP-001",
            property_type=PropertyType.office,
            address=Address(street="100 Main St", city="Birmingham", state="AL", zip="35203"),
            analysis_begin=dt.date(2026, 1, 1),
            analysis_term_years=10,
        ),
        area_measures=AreaMeasures(
            property_size=125_000,
            rentable_area_mode=RentableAreaMode.fixed,
            rentable_area_fixed=120_000,
        ),
        inflation=Inflation(
            general_rate=[YearRate(year=1, rate=3.0), YearRate(year=2, rate=2.5)],
            market_rent_rate=[YearRate(year=1, rate=3.5)],
            cpi_rate=[YearRate(year=1, rate=2.0)],
            custom_indices=[
                CustomIndex(name="utility_index", rates=[YearRate(year=1, rate=5.0)])
            ],
        ),
        general_vacancy=GeneralVacancy(
            method=VacancyMethod.percent_of_pgr,
            rate=[YearRate(year=1, rate=5.0)],
            tenant_overrides=[TenantOverride(tenant_ref="Anchor Credit Tenant")],
        ),
        credit_loss=CreditLoss(
            method=VacancyMethod.percent_of_total_tenant_revenue,
            rate=[YearRate(year=1, rate=0.5)],
        ),
        market_leasing_profiles=[
            MarketLeasingProfile(
                name="Office Market",
                term_months=60,
                renewal_probability=70.0,
                months_vacant=6.0,
                market_base_rent_new=MoneyRate(amount=28.0, unit=MoneyUnit.dollars_per_area_per_year),
                market_base_rent_renew=PctOfNew(pct_of_new=95.0),
                rent_increases=[
                    RentStep(month_offset=12, pct_increase=3.0),
                ],
                free_rent_months_new=3.0,
                free_rent_months_renew=1.0,
                free_rent_profile="Base Rent Only",
                recoveries=RecoveryAssignment(method=RecoverySystemMethod.net),
                ti_new=MoneyRate(amount=40.0, unit=MoneyUnit.dollars_per_area),
                ti_renew=MoneyRate(amount=10.0, unit=MoneyUnit.dollars_per_area),
                lc_new=LCSpec(pct=6.0, pct_years=[1]),
                lc_renew=LCSpec(pct=3.0),
                security_deposit=SecurityDepositSpec(amount=1.0, unit=SecurityDepositUnit.months_of_rent),
                miscellaneous_items=[
                    MiscItemSpec(name="Signage", amount=1200.0, unit=MoneyUnit.dollars_per_year)
                ],
                upon_expiration=UponExpiration.option,
                chained_profile="Office Market Downshift",
            ),
            MarketLeasingProfile(
                name="Office Market Downshift",
                term_months=36,
                renewal_probability=60.0,
                months_vacant=9.0,
                market_base_rent_new=MoneyRate(amount=25.0, unit=MoneyUnit.dollars_per_area_per_year),
                market_base_rent_renew=MoneyRate(amount=24.0, unit=MoneyUnit.dollars_per_area_per_year),
                upon_expiration=UponExpiration.market,
            ),
            MarketLeasingProfile(
                name="Retail Market",
                term_months=120,
                renewal_probability=75.0,
                months_vacant=12.0,
                market_base_rent_new=MoneyRate(amount=32.0, unit=MoneyUnit.dollars_per_area_per_year),
                market_base_rent_renew=PctOfNew(pct_of_new=90.0),
                percentage_rent=PercentRentSpec(
                    sales_volume=SalesVolume(amount=400.0, unit="dollars_per_area_per_year"),
                    breakpoint=PercentRentBreakpoint.natural,
                    breakpoint_layers=[BreakpointLayer(pct=6.0)],
                ),
            ),
        ],
        free_rent_profiles=[
            FreeRentProfile(name="Base Rent Only"),
            FreeRentProfile(
                name="Gross Abatement",
                abate_recoveries=True,
                abate_miscellaneous=True,
            ),
        ],
        ti_categories=[
            TICategory(
                name="Standard Office TI",
                new=MoneyRate(amount=50.0, unit=MoneyUnit.dollars_per_area),
                renew=MoneyRate(amount=15.0, unit=MoneyUnit.dollars_per_area),
                inflation="general",
            )
        ],
        lc_categories=[
            LCCategory(
                name="Tiered Commission",
                method=LCMethod.tiered_by_year,
                tiers=[LCTier(from_year=1, to_year=1, pct=6.0), LCTier(from_year=2, pct=3.0)],
            )
        ],
        recovery_structures=[
            RecoveryStructure(
                name="Office Base Year Stop",
                pools=[
                    RecoveryPool(
                        expenses=["CAM Group"],
                        method=PoolMethod.base_year,
                        gross_up_pct=95.0,
                        admin_fee_pct=10.0,
                        admin_fee_applies=AdminFeeApplies.before_stop,
                        denominator=Denominator.rentable_area,
                    ),
                    RecoveryPool(
                        expenses=["Real Estate Taxes"],
                        method=PoolMethod.net,
                    ),
                ],
            )
        ],
        miscellaneous_revenues=[
            PropertyRevenue(
                name="Antenna License",
                amount=24_000.0,
                unit=RevenueUnit.dollars_per_year,
                inflation="general",
            ),
            PropertyRevenue(
                name="Vending Override",
                amount=1.5,
                unit=RevenueUnit.pct_of_egr,
                pct_fixed=50.0,
                limits=Limits(max=30_000.0),
            ),
        ],
        parking_revenues=[
            PropertyRevenue(
                name="Structured Parking",
                amount=125.0,
                unit=RevenueUnit.spaces_times_rate,
                number_of_spaces=200,
                pct_fixed=25.0,
            )
        ],
        storage_revenues=[
            PropertyRevenue(
                name="Basement Storage",
                amount=0.75,
                unit=RevenueUnit.dollars_per_area_per_month,
            )
        ],
        expenses=[
            ExpenseItem(
                name="Cleaning",
                category=ExpenseCategory.operating,
                amount=2.10,
                unit=ExpenseUnit.dollars_per_area_per_year,
                pct_fixed=50.0,
                inflation="expense",
                expense_group="CAM Group",
            ),
            ExpenseItem(
                name="Utilities",
                category=ExpenseCategory.operating,
                amount=1.80,
                unit=ExpenseUnit.dollars_per_area_per_year,
                pct_fixed=20.0,
                inflation="utility_index",
                expense_group="CAM Group",
            ),
            ExpenseItem(
                name="Real Estate Taxes",
                category=ExpenseCategory.operating,
                amount=450_000.0,
                unit=ExpenseUnit.dollars_per_year,
                timing=Timing(
                    method=TimingMethod.repeating,
                    repeat_months=[6, 12],
                ),
            ),
            ExpenseItem(
                name="Ground Rent",
                category=ExpenseCategory.non_operating,
                amount=60_000.0,
                unit=ExpenseUnit.dollars_per_year,
            ),
            ExpenseItem(
                name="Roof Replacement",
                category=ExpenseCategory.capital,
                amount=350_000.0,
                unit=ExpenseUnit.dollars_per_year,
                timing=Timing(
                    method=TimingMethod.date_range,
                    start=dt.date(2028, 6, 1),
                    end=dt.date(2028, 6, 30),
                ),
                amortization_years=10,
            ),
        ],
        expense_groups=[
            ExpenseGroup(name="CAM Group", members=["Cleaning", "Utilities"])
        ],
        rent_roll=[
            Lease(
                tenant_name="Anchor Credit Tenant",
                suite="100",
                area=45_000,
                lease_type=LeaseType.office,
                start_date=dt.date(2024, 1, 1),
                end_date=dt.date(2033, 12, 31),
                base_rent=MoneyRate(amount=26.50, unit=MoneyUnit.dollars_per_area_per_year),
                rent_steps=[
                    RentStep(
                        date=dt.date(2029, 1, 1),
                        amount=29.0,
                        unit=MoneyUnit.dollars_per_area_per_year,
                    )
                ],
                cpi=CPISpec(method="pct_of_cpi", pct=50.0),
                free_rent=FreeRent(months=2.0, profile="Base Rent Only"),
                recoveries=RecoveryAssignment(
                    method=RecoverySystemMethod.structure,
                    structure_ref="Office Base Year Stop",
                ),
                leasing_costs=LeasingCosts(
                    ti_category="Standard Office TI",
                    lc_category="Tiered Commission",
                ),
                security_deposit=SecurityDepositSpec(
                    amount=100_000.0, unit=SecurityDepositUnit.dollars
                ),
                market_leasing_profile="Office Market",
                upon_expiration=UponExpiration.market,
                tenant_classifications={"credit": "investment_grade"},
                notes="Anchor tenant; excluded from general vacancy.",
            ),
            Lease(
                tenant_name="Corner Retail LLC",
                suite="R-1",
                area=8_000,
                lease_type=LeaseType.retail,
                start_date=dt.date(2025, 7, 1),
                term_months=120,
                base_rent=MoneyRate(amount=30.0, unit=MoneyUnit.dollars_per_area_per_year),
                percentage_rent=PercentRentSpec(
                    sales_volume=SalesVolume(amount=3_600_000.0, growth="general"),
                    breakpoint=PercentRentBreakpoint.fixed_amount,
                    breakpoint_layers=[
                        BreakpointLayer(breakpoint_amount=3_000_000.0, pct=5.0),
                        BreakpointLayer(breakpoint_amount=5_000_000.0, pct=3.0),
                    ],
                ),
                miscellaneous_items=[
                    MiscItemSpec(
                        name="Trash Surcharge",
                        amount=250.0,
                        unit=MoneyUnit.dollars_per_month,
                    )
                ],
                recoveries=RecoveryAssignment(method=RecoverySystemMethod.net),
                market_leasing_profile="Retail Market",
                upon_expiration=UponExpiration.market,
            ),
            Lease(
                tenant_name="Month-to-Month Kiosk",
                area=400,
                lease_type=LeaseType.retail,
                status="mtm",
                start_date=dt.date(2026, 1, 1),
                term_months=12,
                base_rent=MoneyRate(amount=1_500.0, unit=MoneyUnit.dollars_per_month),
                recoveries=RecoveryAssignment(method=RecoverySystemMethod.none),
                upon_expiration=UponExpiration.vacate,
            ),
        ],
        absorption=[
            AbsorptionSpec(
                name="Tower Lease-Up",
                total_area=20_000,
                number_of_leases=4,
                start_date=dt.date(2026, 7, 1),
                interval_months=3,
                market_leasing_profile="Office Market",
            )
        ],
        purchase=Purchase(
            price=52_000_000.0,
            date=dt.date(2026, 1, 1),
            closing_costs=[
                ClosingCost(name="Due Diligence", amount=150_000.0),
                ClosingCost(name="Transfer Tax", pct_of_price=0.5),
            ],
        ),
        loans=[
            Loan(
                name="Senior Mortgage",
                type=LoanType.fixed,
                amount=LoanAmount(basis=LoanAmountBasis.pct_of_price, value=60.0),
                term_months=120,
                rate=5.25,
                interest_only_months=24,
                amortization=30,
                additional_principal=[
                    AdditionalPrincipal(date=dt.date(2029, 1, 1), amount=1_000_000.0)
                ],
                loan_costs=LoanCosts(points_pct=1.0, fees=50_000.0),
            ),
            Loan(
                name="Mezzanine",
                type=LoanType.floating,
                amount=LoanAmount(value=5_000_000.0),
                maturity_date=dt.date(2031, 1, 1),
                rate=FloatingRate(
                    index=[YearRate(year=1, rate=4.3), YearRate(year=2, rate=4.0)],
                    spread=3.5,
                ),
                amortization="interest_only",
            ),
        ],
        valuation=ValuationInputs(
            discount_rate=7.5,
            discount_method="monthly",
            period_convention="mid_period",
            direct_cap=DirectCap(cap_rate=6.5, noi_basis="forward_12"),
            resale=Resale(
                method=ResaleMethod.cap_noi_forward_12,
                exit_cap_rate=7.0,
                selling_costs_pct=2.0,
            ),
            sensitivity_intervals=SensitivityIntervals(
                discount_rate_step=0.25, cap_rate_step=0.25, count=7
            ),
        ),
    )


@pytest.fixture()
def minimal_property() -> PropertyModel:
    """The smallest valid document: property, areas, inflation only."""
    return PropertyModel(
        property=PropertyInfo(
            name="Bare Minimum",
            property_type=PropertyType.industrial,
            analysis_begin=dt.date(2026, 1, 1),
            analysis_term_years=1,
        ),
        area_measures=AreaMeasures(property_size=10_000),
        inflation=Inflation(general_rate=[YearRate(year=1, rate=0.0)]),
    )


class TestRoundTrip:
    def test_full_model_json_roundtrip(self, full_property):
        dumped = full_property.model_dump_json(indent=2)
        reloaded = PropertyModel.model_validate_json(dumped)
        assert reloaded == full_property

    def test_minimal_model_json_roundtrip(self, minimal_property):
        reloaded = PropertyModel.model_validate_json(minimal_property.model_dump_json())
        assert reloaded == minimal_property

    def test_python_dict_roundtrip(self, full_property):
        """model_dump → model_validate must also round-trip (API layer path)."""
        reloaded = PropertyModel.model_validate(full_property.model_dump(mode="json"))
        assert reloaded == full_property

    def test_file_roundtrip(self, full_property, tmp_path):
        path = save_property(full_property, tmp_path / "ironhorse_plaza.icprop.json")
        assert load_property(path) == full_property

    def test_serialization_is_byte_stable(self, full_property):
        """Same model must dump to identical bytes (Git-diffable, spec §5.1)."""
        first = full_property.model_dump_json(indent=2)
        second = PropertyModel.model_validate_json(first).model_dump_json(indent=2)
        assert first == second

    def test_schema_version_present(self, full_property):
        import json

        doc = json.loads(full_property.model_dump_json())
        assert doc["schema_version"] == "1.0"
        # Stable top-level key order: schema_version then property first.
        assert list(doc)[:2] == ["schema_version", "property"]

    def test_enums_serialize_as_strings(self, full_property):
        import json

        doc = json.loads(full_property.model_dump_json())
        assert doc["property"]["property_type"] == "office"
        assert doc["rent_roll"][0]["base_rent"]["unit"] == "dollars_per_area_per_year"


class TestValidation:
    def test_analysis_begin_must_be_first_of_month(self):
        with pytest.raises(ValidationError, match="first day of a month"):
            PropertyInfo(
                name="Bad",
                property_type=PropertyType.office,
                analysis_begin=dt.date(2026, 1, 15),
                analysis_term_years=10,
            )

    def test_unknown_fields_rejected(self, minimal_property):
        doc = minimal_property.model_dump(mode="json")
        doc["property"]["ground_lease_gearing"] = True  # out of scope, spec §1.2
        with pytest.raises(ValidationError):
            PropertyModel.model_validate(doc)

    def test_more_than_six_breakpoint_layers_rejected(self):
        with pytest.raises(ValidationError):
            PercentRentSpec(
                sales_volume=SalesVolume(amount=1_000_000.0),
                breakpoint=PercentRentBreakpoint.fixed_amount,
                breakpoint_layers=[
                    BreakpointLayer(breakpoint_amount=float(i), pct=1.0)
                    for i in range(1, 8)
                ],
            )

    def test_unknown_mlp_ref_rejected(self, minimal_property):
        doc = minimal_property.model_dump(mode="json")
        doc["rent_roll"] = [
            Lease(
                tenant_name="Orphan",
                area=1_000,
                lease_type=LeaseType.office,
                start_date=dt.date(2026, 1, 1),
                term_months=60,
                base_rent=MoneyRate(amount=20.0, unit=MoneyUnit.dollars_per_area_per_year),
                market_leasing_profile="No Such Profile",
            ).model_dump(mode="json")
        ]
        with pytest.raises(ValidationError, match="No Such Profile"):
            PropertyModel.model_validate(doc)

    def test_market_expiration_requires_mlp(self, minimal_property):
        doc = minimal_property.model_dump(mode="json")
        doc["rent_roll"] = [
            {
                "tenant_name": "No Profile",
                "area": 1_000,
                "lease_type": "office",
                "start_date": "2026-01-01",
                "term_months": 60,
                "base_rent": {"amount": 20.0, "unit": "dollars_per_area_per_year"},
                "upon_expiration": "market",
            }
        ]
        with pytest.raises(ValidationError, match="requires market_leasing_profile"):
            PropertyModel.model_validate(doc)

    def test_lease_requires_exactly_one_of_end_date_or_term(self):
        with pytest.raises(ValidationError, match="end_date / term_months"):
            Lease(
                tenant_name="Both",
                area=1_000,
                lease_type=LeaseType.office,
                start_date=dt.date(2026, 1, 1),
                end_date=dt.date(2031, 1, 1),
                term_months=60,
                base_rent=MoneyRate(amount=20.0, unit=MoneyUnit.dollars_per_area_per_year),
                upon_expiration=UponExpiration.vacate,
            )

    def test_duplicate_profile_names_rejected(self, minimal_property):
        doc = minimal_property.model_dump(mode="json")
        profile = MarketLeasingProfile(
            name="Twin",
            term_months=60,
            renewal_probability=50.0,
            months_vacant=6.0,
            market_base_rent_new=MoneyRate(amount=20.0, unit=MoneyUnit.dollars_per_area_per_year),
            market_base_rent_renew=PctOfNew(pct_of_new=100.0),
        ).model_dump(mode="json")
        doc["market_leasing_profiles"] = [profile, profile]
        with pytest.raises(ValidationError, match="duplicate names"):
            PropertyModel.model_validate(doc)

    def test_fixed_rentable_area_requires_value(self):
        with pytest.raises(ValidationError, match="rentable_area_fixed"):
            AreaMeasures(property_size=10_000, rentable_area_mode=RentableAreaMode.fixed)

    def test_floating_loan_requires_floating_rate(self):
        with pytest.raises(ValidationError, match="FloatingRate"):
            Loan(
                name="Bad Float",
                type=LoanType.floating,
                amount=LoanAmount(value=1_000_000.0),
                term_months=60,
                rate=5.0,
            )
