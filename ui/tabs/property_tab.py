"""Property tab (Phase 5 Step 2; spec §6 tab 1 — §3.1-3.2).

``PropertyInfo`` + ``AreaMeasures`` editors. The ``apply_*`` functions are
pure (model in → new model or readable §5.4 error out, via
:func:`ui.state.updated_model`); ``render`` is the Streamlit skin. Every
successful Apply installs the new model through :func:`ui.session.set_model`,
which invalidates the cached RunResult. Iron Rule 1: engine imports only.
"""
from __future__ import annotations

from typing import Optional

import streamlit as st

from engine.models import PropertyType, RentableAreaMode
from ui import convert, session, state

PROPERTY_TYPES = [t.value for t in PropertyType]
AREA_MODES = [m.value for m in RentableAreaMode]


# ------------------------------------------------------------------ #
# Pure commit functions                                               #
# ------------------------------------------------------------------ #

def apply_property_info(model, info: dict, address: dict):
    """Merge scalar PropertyInfo fields + address fields; full-document
    revalidation via the funnel (readable errors)."""
    def mutate(data):
        data["property"].update(info)
        data["property"]["address"].update(address)
    return state.updated_model(model, mutate)


def apply_area_measures(model, fields: dict,
                        schedule_rows: Optional[list] = None):
    def mutate(data):
        data["area_measures"].update(fields)
        if schedule_rows is not None:
            data["area_measures"]["rentable_area_schedule"] = (
                convert.rows_to_schedule(schedule_rows))
    return state.updated_model(model, mutate)


# ------------------------------------------------------------------ #
# Renderer                                                            #
# ------------------------------------------------------------------ #

def _apply_and_report(new_model, error, success_message: str) -> None:
    if error:
        st.error(error)
    else:
        session.set_model(new_model, reset_widgets=False)
        st.success(success_message)


def render() -> None:
    model = st.session_state.model
    if model is None:
        st.info("Open or create a property in the sidebar first.")
        return
    rev = session.rev()
    prop = model.property
    area = model.area_measures

    st.subheader("Property (§3.1)")
    col1, col2 = st.columns(2)
    with col1:
        name = st.text_input("Name", value=prop.name, key=f"pi_name_{rev}")
        external_id = st.text_input("External ID",
                                    value=prop.external_id or "",
                                    key=f"pi_ext_{rev}")
        ptype = st.selectbox("Property type", PROPERTY_TYPES,
                             index=PROPERTY_TYPES.index(prop.property_type.value),
                             key=f"pi_type_{rev}")
        currency = st.text_input("Currency", value=prop.currency,
                                 key=f"pi_curr_{rev}")
        area_unit = st.text_input("Area unit", value=prop.area_unit,
                                  key=f"pi_areaunit_{rev}")
    with col2:
        begin = st.date_input("Analysis begin", value=prop.analysis_begin,
                              key=f"pi_begin_{rev}")
        term = st.number_input("Analysis term (years)",
                               value=prop.analysis_term_years, step=1,
                               key=f"pi_term_{rev}")
        fye = st.number_input("Fiscal year end month (1-12)",
                              value=prop.fiscal_year_end_month, step=1,
                              key=f"pi_fye_{rev}")
    with st.expander("Address"):
        street = st.text_input("Street", value=prop.address.street or "",
                               key=f"pi_street_{rev}")
        city = st.text_input("City", value=prop.address.city or "",
                             key=f"pi_city_{rev}")
        state_ = st.text_input("State", value=prop.address.state or "",
                               key=f"pi_state_{rev}")
        zip_ = st.text_input("Zip", value=prop.address.zip or "",
                             key=f"pi_zip_{rev}")
    if st.button("Apply property changes", key=f"pi_apply_{rev}"):
        info = {"name": name, "external_id": external_id or None,
                "property_type": ptype, "analysis_begin": str(begin),
                "analysis_term_years": int(term),
                "fiscal_year_end_month": int(fye), "currency": currency,
                "area_unit": area_unit}
        address = {"street": street or None, "city": city or None,
                   "state": state_ or None, "zip": zip_ or None}
        _apply_and_report(*apply_property_info(model, info, address),
                          "Property updated.")

    st.subheader("Area measures (§3.2)")
    col1, col2 = st.columns(2)
    with col1:
        size = st.number_input("Property size (gross building area, SF)",
                               value=float(area.property_size),
                               key=f"am_size_{rev}")
        alternate = st.number_input("Alternate size (0 = none)",
                                    value=float(area.alternate_size or 0.0),
                                    key=f"am_alt_{rev}")
    with col2:
        mode = st.selectbox("Rentable area mode", AREA_MODES,
                            index=AREA_MODES.index(area.rentable_area_mode.value),
                            key=f"am_mode_{rev}")
        fixed = st.number_input("Rentable area — fixed (used when mode=fixed)",
                                value=float(area.rentable_area_fixed or 0.0),
                                key=f"am_fixed_{rev}")
    st.caption("Rentable area schedule (used when mode=schedule; blank rows "
               "are dropped)")
    schedule_rows = st.data_editor(
        convert.schedule_to_rows(
            model.model_dump(mode="json")["area_measures"]
            ["rentable_area_schedule"]) or [{"date": None, "area": None}],
        num_rows="dynamic", key=f"am_sched_{rev}",
        column_config={"date": st.column_config.TextColumn(
            "date (YYYY-MM-DD)")})
    if st.button("Apply area changes", key=f"am_apply_{rev}"):
        fields = {"property_size": size,
                  "alternate_size": alternate or None,
                  "rentable_area_mode": mode,
                  "rentable_area_fixed": fixed or None}
        _apply_and_report(
            *apply_area_measures(model, fields, schedule_rows),
            "Area measures updated.")
