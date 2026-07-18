"""Market tab (Phase 5 Step 2; spec §6 tab 2 — §3.4-3.8).

Inflation + custom indices, General Vacancy, Credit Loss, the MLP grid +
per-MLP detail editor, and Free-Rent Profiles. Per Step 0 D2:

* **TI/LC categories are engine-refused** (DEVIATIONS §16) — rendered
  READ-ONLY with the engine's refusal wording, never editable.
* MLP ``percentage_rent`` / ``miscellaneous_items`` / ``security_deposit``
  (unexercised by any golden) render read-only with the raw-JSON escape
  hatch noted.
* **CPI has no top-level profile slice in the §3 schema** — ``CPISpec``
  lives per lease (§3.12 [AE p. 374]); the tab says so instead of
  inventing a schema field (Iron Rule 1: no engine/model changes).

``apply_*`` functions are pure (funnel → readable §5.4 errors);
``render`` is the Streamlit skin. Every successful Apply goes through
:func:`ui.session.set_model` (RunResult invalidated).
"""
from __future__ import annotations

from typing import Optional

import streamlit as st

from engine.calc.ledger import (
    CPI_ADJUSTMENT_REVENUE,
    EXPENSE_RECOVERY_REVENUE,
    MISC_TENANT_REVENUE,
    PERCENTAGE_RENT,
    PROPERTY_REVENUE,
    SCHEDULED_BASE_RENTAL_REVENUE,
)
from engine.models import (
    IntelligentRenewalRule,
    MoneyUnit,
    RecoverySystemMethod,
    TimingBasis,
    UponExpiration,
    VacancyMethod,
)
from ui import convert, session, state

TIMING_BASES = [t.value for t in TimingBasis]
VACANCY_METHODS = [m.value for m in VacancyMethod]
UPON_EXPIRATION = [u.value for u in UponExpiration]
RENEWAL_RULES = [r.value for r in IntelligentRenewalRule]
RECOVERY_METHODS = [m.value for m in RecoverySystemMethod]
#: Contract/market base-rent units (§3.6; pct_of_last_rent is renew-only).
RENT_UNITS = ["dollars_per_area_per_year", "dollars_per_area_per_month",
              "dollars_per_year", "dollars_per_month"]
RENEW_AMOUNT_UNITS = RENT_UNITS + [MoneyUnit.pct_of_last_rent.value]
TI_UNITS = ["dollars_per_area", "dollars"]
PGR_ACCOUNTS = [SCHEDULED_BASE_RENTAL_REVENUE, CPI_ADJUSTMENT_REVENUE,
                PERCENTAGE_RENT, EXPENSE_RECOVERY_REVENUE,
                MISC_TENANT_REVENUE, PROPERTY_REVENUE]

#: The engine's TI/LC-category refusal (engine/calc/run.py phase guard),
#: quoted so the read-only panel shows the real message the engine raises.
TI_LC_REFUSAL = ("lease <name>: TI/LC categories is not implemented until a "
                 "later phase (DEVIATIONS.md §16); remove the input or wait "
                 "for that phase")


# ------------------------------------------------------------------ #
# Pure commit functions                                               #
# ------------------------------------------------------------------ #

def apply_inflation(model, *, timing_basis: str, inflation_month,
                    general_rows, market_rows, expense_rows, cpi_rows):
    def mutate(data):
        inf = data["inflation"]
        inf["timing_basis"] = timing_basis
        inf["inflation_month"] = inflation_month or None
        inf["general_rate"] = convert.rows_to_year_rates(general_rows)
        inf["market_rent_rate"] = convert.rows_to_year_rates(market_rows) or None
        inf["expense_rate"] = convert.rows_to_year_rates(expense_rows) or None
        inf["cpi_rate"] = convert.rows_to_year_rates(cpi_rows) or None
    return state.updated_model(model, mutate)


def apply_custom_indices(model, indices: list[dict]):
    """``indices``: ``[{"name": str, "rows": [...]}]``; blank names drop."""
    def mutate(data):
        data["inflation"]["custom_indices"] = [
            {"name": ix["name"],
             "rates": convert.rows_to_year_rates(ix["rows"])}
            for ix in indices if (ix.get("name") or "").strip()]
    return state.updated_model(model, mutate)


def apply_vacancy_section(model, section: str, *, method: str, rate_rows,
                          include_accounts: list[str], override_rows,
                          reduce_by_absorption_turnover: Optional[bool] = None):
    """``section``: ``general_vacancy`` or ``credit_loss`` (the reduce flag
    exists only on general vacancy)."""
    def mutate(data):
        block = {"method": method,
                 "rate": convert.rows_to_year_rates(rate_rows),
                 "include_in_pgr_accounts": list(include_accounts),
                 "tenant_overrides": convert.rows_to_overrides(override_rows)}
        if section == "general_vacancy":
            block["reduce_by_absorption_turnover"] = (
                True if reduce_by_absorption_turnover is None
                else bool(reduce_by_absorption_turnover))
        data[section] = block
    return state.updated_model(model, mutate)


def apply_free_rent_profiles(model, rows: list[dict]):
    def mutate(data):
        data["free_rent_profiles"] = convert.rows_to_free_rent_profiles(rows)
    return state.updated_model(model, mutate)


def apply_mlp_grid(model, rows: list[dict]):
    """Scalar-grid edits merged by row order; nested detail preserved
    (see :func:`ui.convert.apply_mlp_grid_rows`)."""
    def mutate(data):
        data["market_leasing_profiles"] = convert.apply_mlp_grid_rows(
            data["market_leasing_profiles"], rows)
    return state.updated_model(model, mutate)


def apply_mlp_detail(model, index: int, detail: dict):
    """Merge a detail-editor payload into MLP ``index``. ``detail`` keys are
    already model-shaped (e.g. ``market_base_rent_new`` as an
    amount/unit dict, ``rent_increases`` as step dicts or None)."""
    def mutate(data):
        data["market_leasing_profiles"][index].update(detail)
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


def _year_rate_editor(label: str, rates, key: str):
    st.caption(label)
    return st.data_editor(
        convert.year_rates_to_rows(rates) or [{"year": None, "rate": None}],
        num_rows="dynamic", key=key)


def _render_inflation(model, data, rev: int) -> None:
    inf = data["inflation"]
    with st.expander("Inflation & indices (§3.5)", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            timing = st.selectbox(
                "Timing basis", TIMING_BASES,
                index=TIMING_BASES.index(inf["timing_basis"]),
                key=f"inf_timing_{rev}")
        with col2:
            month = st.number_input(
                "Inflation month (0 = none)",
                value=int(inf["inflation_month"] or 0), step=1,
                key=f"inf_month_{rev}")
        col1, col2 = st.columns(2)
        with col1:
            general = _year_rate_editor("General rate (%)",
                                        inf["general_rate"],
                                        f"inf_general_{rev}")
            expense = _year_rate_editor("Expense rate (%) — blank = general",
                                        inf["expense_rate"],
                                        f"inf_expense_{rev}")
        with col2:
            market = _year_rate_editor("Market rent rate (%) — blank = general",
                                       inf["market_rent_rate"],
                                       f"inf_market_{rev}")
            cpi = _year_rate_editor("CPI rate (%) — blank = general",
                                    inf["cpi_rate"], f"inf_cpi_{rev}")
        if st.button("Apply inflation", key=f"inf_apply_{rev}"):
            _apply_and_report(
                *apply_inflation(model, timing_basis=timing,
                                 inflation_month=int(month),
                                 general_rows=general, market_rows=market,
                                 expense_rows=expense, cpi_rows=cpi),
                "Inflation updated.")

        st.markdown("**Custom indices**")
        indices = []
        for i, index in enumerate(inf["custom_indices"]):
            with st.container(border=True):
                name = st.text_input("Index name (blank = delete)",
                                     value=index["name"],
                                     key=f"ci_name_{i}_{rev}")
                rows = _year_rate_editor("Rates (%)", index["rates"],
                                         f"ci_rates_{i}_{rev}")
                indices.append({"name": name, "rows": rows})
        if st.checkbox("Add a custom index", key=f"ci_add_{rev}"):
            name = st.text_input("New index name", key=f"ci_newname_{rev}")
            rows = _year_rate_editor("New index rates (%)", None,
                                     f"ci_newrates_{rev}")
            indices.append({"name": name, "rows": rows})
        if st.button("Apply custom indices", key=f"ci_apply_{rev}"):
            _apply_and_report(*apply_custom_indices(model, indices),
                              "Custom indices updated.")


def _render_vacancy(model, data, section: str, title: str, rev: int) -> None:
    block = data.get(section) or {"method": "none", "rate": [],
                                  "include_in_pgr_accounts": [],
                                  "tenant_overrides": []}
    with st.expander(title, expanded=False):
        method = st.selectbox("Method", VACANCY_METHODS,
                              index=VACANCY_METHODS.index(block["method"]),
                              key=f"{section}_method_{rev}")
        rate_rows = _year_rate_editor("Rate (%) by year", block["rate"],
                                      f"{section}_rate_{rev}")
        include = st.multiselect(
            "Include in base (PGR accounts)", PGR_ACCOUNTS,
            default=[a for a in block["include_in_pgr_accounts"]
                     if a in PGR_ACCOUNTS],
            key=f"{section}_incl_{rev}")
        reduce_flag = None
        if section == "general_vacancy":
            reduce_flag = st.checkbox(
                "Reduce by absorption & turnover vacancy",
                value=bool(block.get("reduce_by_absorption_turnover", True)),
                key=f"{section}_reduce_{rev}")
        st.caption("Tenant overrides (exclusion-only — DEVIATIONS §9)")
        override_rows = st.data_editor(
            convert.overrides_to_rows(block["tenant_overrides"])
            or [{"tenant_ref": None, "exclude": True}],
            num_rows="dynamic", key=f"{section}_ovr_{rev}")
        if st.button(f"Apply {title.lower()}", key=f"{section}_apply_{rev}"):
            _apply_and_report(
                *apply_vacancy_section(model, section, method=method,
                                       rate_rows=rate_rows,
                                       include_accounts=include,
                                       override_rows=override_rows,
                                       reduce_by_absorption_turnover=reduce_flag),
                f"{title} updated.")


def _money_rate_inputs(label: str, current: Optional[dict], units: list[str],
                       key: str, *, optional: bool = False) -> Optional[dict]:
    """Amount + unit inputs → MoneyRate dict (or None when optional and
    disabled)."""
    enabled = True
    if optional:
        enabled = st.checkbox(f"{label} — set", value=current is not None,
                              key=f"{key}_on")
    if not enabled:
        return None
    amount = st.number_input(f"{label} amount",
                             value=float((current or {}).get("amount", 0.0)),
                             key=f"{key}_amt")
    unit_now = (current or {}).get("unit", units[0])
    unit = st.selectbox(f"{label} unit", units,
                        index=units.index(unit_now) if unit_now in units else 0,
                        key=f"{key}_unit")
    return {"amount": amount, "unit": unit}


def _lc_inputs(label: str, current: Optional[dict], key: str) -> Optional[dict]:
    """LCSpec editor: none | % of rent (+ years) | rate. ``category_ref`` is
    engine-refused and rendered read-only."""
    modes = ["none", "% of rent", "rate"]
    if current is None:
        mode_now = "none"
    elif current.get("pct") is not None:
        mode_now = "% of rent"
    else:
        mode_now = "rate"
    mode = st.selectbox(f"{label} method", modes, index=modes.index(mode_now),
                        key=f"{key}_mode")
    if current and current.get("category_ref"):
        st.warning(f"{label} references LC category "
                   f"'{current['category_ref']}' — engine-refused "
                   "(DEVIATIONS §16), read-only here.")
    if mode == "none":
        return None
    if mode == "% of rent":
        pct = st.number_input(f"{label} % of rent",
                              value=float((current or {}).get("pct") or 0.0),
                              key=f"{key}_pct")
        years_text = st.text_input(
            f"{label} % applies to lease years (blank = all; e.g. 1,2,3)",
            value=",".join(str(y) for y in (current or {}).get("pct_years")
                           or []),
            key=f"{key}_years")
        years = [int(y) for y in years_text.replace(" ", "").split(",")
                 if y] or None
        return {"pct": pct, "pct_years": years}
    rate = _money_rate_inputs(f"{label} rate", (current or {}).get("rate"),
                              TI_UNITS, f"{key}_rate")
    return {"rate": rate}


def _render_mlps(model, data, rev: int) -> None:
    profiles = data["market_leasing_profiles"]
    with st.expander("Market leasing profiles (§3.6)", expanded=False):
        st.caption("Scalar grid — nested economics (rents, TI/LC, recoveries,"
                   " steps) in the detail editor below. Add a row to add an "
                   "MLP; delete a row to delete one.")
        grid = st.data_editor(
            convert.mlp_grid_rows(profiles)
            or [{c: None for c in convert.MLP_GRID_COLUMNS}],
            num_rows="dynamic", key=f"mlp_grid_{rev}",
            column_config={
                "upon_expiration": st.column_config.SelectboxColumn(
                    options=UPON_EXPIRATION),
                "intelligent_renewals": st.column_config.SelectboxColumn(
                    options=RENEWAL_RULES),
            })
        if st.button("Apply MLP grid", key=f"mlp_grid_apply_{rev}"):
            _apply_and_report(*apply_mlp_grid(model, grid),
                              "MLP grid updated.")

        if not profiles:
            return
        names = [p["name"] for p in profiles]
        chosen = st.selectbox("Detail editor — profile", names,
                              key=f"mlp_pick_{rev}")
        i = names.index(chosen)
        profile = profiles[i]
        free_names = [""] + [p["name"] for p in data["free_rent_profiles"]]
        structure_names = [""] + [s["name"]
                                  for s in data["recovery_structures"]]
        key = f"mlp_{i}_{rev}"

        col1, col2 = st.columns(2)
        with col1:
            new_rent = _money_rate_inputs(
                "Market rent (new)", profile["market_base_rent_new"],
                RENT_UNITS, f"{key}_new")
            renew_now = profile["market_base_rent_renew"]
            renew_is_pct = isinstance(renew_now, dict) and \
                "pct_of_new" in renew_now
            renew_mode = st.radio("Market rent (renew)",
                                  ["% of new", "amount"],
                                  index=0 if renew_is_pct else 1,
                                  key=f"{key}_renewmode", horizontal=True)
            if renew_mode == "% of new":
                pct_of_new = st.number_input(
                    "Renew % of new",
                    value=float(renew_now.get("pct_of_new", 100.0)
                                if renew_is_pct else 100.0),
                    key=f"{key}_pctofnew")
                renew_rent = {"pct_of_new": pct_of_new}
            else:
                renew_rent = _money_rate_inputs(
                    "Renew rent", None if renew_is_pct else renew_now,
                    RENEW_AMOUNT_UNITS, f"{key}_renew")
            free_ref = st.selectbox(
                "Free-rent profile", free_names,
                index=(free_names.index(profile["free_rent_profile"])
                       if profile["free_rent_profile"] in free_names else 0),
                key=f"{key}_freeref")
            chained = st.text_input(
                "Chained profile (blank = none)",
                value=profile["chained_profile"] or "", key=f"{key}_chained")
        with col2:
            ti_new = _money_rate_inputs("TI (new)", profile["ti_new"],
                                        TI_UNITS, f"{key}_tinew",
                                        optional=True)
            ti_renew = _money_rate_inputs("TI (renew)", profile["ti_renew"],
                                          TI_UNITS, f"{key}_tirenew",
                                          optional=True)
            lc_new = _lc_inputs("LC (new)", profile["lc_new"], f"{key}_lcnew")
            lc_renew = _lc_inputs("LC (renew)", profile["lc_renew"],
                                  f"{key}_lcrenew")

        st.markdown("**Recoveries (speculative-term assignment)**")
        rec = profile["recoveries"]
        rec_method = st.selectbox(
            "Method", RECOVERY_METHODS,
            index=RECOVERY_METHODS.index(rec["method"]),
            key=f"{key}_recmethod")
        rcol1, rcol2, rcol3 = st.columns(3)
        with rcol1:
            stop = st.number_input(
                "Stop $/SF (base_stop)",
                value=float(rec["stop_amount_per_area"] or 0.0),
                key=f"{key}_recstop")
            structure = st.selectbox(
                "Structure ref", structure_names,
                index=(structure_names.index(rec["structure_ref"])
                       if rec["structure_ref"] in structure_names else 0),
                key=f"{key}_recstruct")
        with rcol2:
            base_year = st.number_input(
                "Base year (0 = segment default)",
                value=int(rec["base_year"] or 0), step=1,
                key=f"{key}_recbaseyear")
            gross_up = st.number_input(
                "Base-year gross-up % (0 = none)",
                value=float(rec["base_year_gross_up_pct"] or 0.0),
                key=f"{key}_recgross")
        with rcol3:
            fixed_amount = st.number_input(
                "Fixed $ (0 = none)", value=float(rec["fixed_amount"] or 0.0),
                key=f"{key}_recfixed")
            fixed_psf = st.number_input(
                "Fixed $/SF (0 = none)",
                value=float(rec["fixed_amount_per_area"] or 0.0),
                key=f"{key}_recfixedpsf")

        st.caption("Rent increases (steps; exactly one of month_offset/date "
                   "and one of amount/pct_increase per row)")
        step_rows = st.data_editor(
            convert.rent_steps_to_rows(profile["rent_increases"])
            or [{c: None for c in convert.RENT_STEP_COLUMNS}],
            num_rows="dynamic", key=f"{key}_steps",
            column_config={"unit": st.column_config.SelectboxColumn(
                options=RENT_UNITS)})

        for exotic in ("percentage_rent", "miscellaneous_items",
                       "security_deposit"):
            if profile.get(exotic):
                st.info(f"`{exotic}` is set on this MLP — unexercised by any "
                        "golden; read-only here (edit via JSON, Step 0 D2):")
                st.json(profile[exotic])

        if st.button("Apply MLP detail", key=f"{key}_apply"):
            detail = {
                "market_base_rent_new": new_rent,
                "market_base_rent_renew": renew_rent,
                "free_rent_profile": free_ref or None,
                "chained_profile": chained or None,
                "ti_new": ti_new, "ti_renew": ti_renew,
                "lc_new": lc_new, "lc_renew": lc_renew,
                "recoveries": {
                    "method": rec_method,
                    "stop_amount_per_area": stop or None,
                    "base_year": int(base_year) or None,
                    "base_year_gross_up_pct": gross_up or None,
                    "base_year_amount": rec["base_year_amount"],
                    "fixed_amount": fixed_amount or None,
                    "fixed_amount_per_area": fixed_psf or None,
                    "fixed_inflation": rec["fixed_inflation"],
                    "structure_ref": structure or None,
                },
                "rent_increases": convert.rows_to_rent_steps(step_rows),
            }
            _apply_and_report(*apply_mlp_detail(model, i, detail),
                              f"MLP '{chosen}' updated.")


def _render_free_rent_profiles(model, data, rev: int) -> None:
    with st.expander("Free-rent profiles (§3.8)", expanded=False):
        rows = st.data_editor(
            convert.free_rent_profiles_to_rows(data["free_rent_profiles"])
            or [{c: None for c in convert.FREE_RENT_COLUMNS}],
            num_rows="dynamic", key=f"frp_grid_{rev}")
        if st.button("Apply free-rent profiles", key=f"frp_apply_{rev}"):
            _apply_and_report(*apply_free_rent_profiles(model, rows),
                              "Free-rent profiles updated.")


def _render_read_only_notes(data) -> None:
    with st.expander("TI/LC categories — READ-ONLY (engine-refused)"):
        st.warning(
            "TI/LC categories are schema-present but the engine refuses any "
            "lease that references one (DEVIATIONS §16). The refusal reads:\n\n"
            f"`{TI_LC_REFUSAL}`\n\nThey render read-only until that changes "
            "(Step 0 D2).")
        if data["ti_categories"]:
            st.json(data["ti_categories"])
        if data["lc_categories"]:
            st.json(data["lc_categories"])
        if not data["ti_categories"] and not data["lc_categories"]:
            st.caption("None defined on this property.")
    st.caption("CPI profiles: the §3 schema has no top-level CPI profiles — "
               "CPI is configured per lease (`lease.cpi`, §3.12 "
               "[AE p. 374]); edit it on the Tenants tab (Step 4).")


def render() -> None:
    model = st.session_state.model
    if model is None:
        st.info("Open or create a property in the sidebar first.")
        return
    rev = session.rev()
    data = model.model_dump(mode="json")
    st.subheader("Market assumptions (§3.4-3.8)")
    _render_inflation(model, data, rev)
    _render_vacancy(model, data, "general_vacancy",
                    "General vacancy (§3.4)", rev)
    _render_vacancy(model, data, "credit_loss", "Credit loss (§3.4)", rev)
    _render_mlps(model, data, rev)
    _render_free_rent_profiles(model, data, rev)
    _render_read_only_notes(data)
