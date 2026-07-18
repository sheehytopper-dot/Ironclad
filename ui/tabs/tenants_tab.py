"""Tenants tab (Phase 5 Step 4; spec §6 tab 5 — §3.12-3.15, §3.7).

The biggest tab: the rent-roll grid + the D5 **persistent split-pane lease
detail** (rent steps, CPI, free rent, misc items, security deposit, % rent,
recovery assignment, leasing costs), absorption specs, the recovery
structure builder, the §5.2 **rent-roll template import surface**
(``ImportResult.notes`` as an info banner — never a silent skip; row-level
errors verbatim), and the D6-amendment **"Rollover generations
(engine-projected)" READ-ONLY panel** — the Freeport E inspection surface,
straight off ``result.segments`` (no engine change; per-generation LC
pct/rate, TI, renewal weight, downtime, blended rent).

Engine-refused fields per Step 0 D2: lease TI/LC **categories**
(``leasing_costs.ti_category``/``lc_category``) show the engine's refusal
verbatim and are preserved untouched. Same funnel pattern as every tab.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

from engine.intake import RentRollImportError, import_rent_roll
from engine.models import LeaseStatus, LeaseType, UponExpiration
from engine.reports import CONTRACTUAL, SPECULATIVE
from ui import convert, session, state
from ui.tabs import common_widgets

LEASE_TYPES = [t.value for t in LeaseType]
LEASE_STATUSES = [s.value for s in LeaseStatus]
UPON_EXPIRATION = [u.value for u in UponExpiration]
RENT_UNITS = ["dollars_per_area_per_year", "dollars_per_area_per_month",
              "dollars_per_year", "dollars_per_month", "pct_of_market"]
CPI_METHODS = ["full_cpi", "pct_of_cpi", "cpi_plus_pct", "min_max_banded"]
POOL_METHODS = ["net", "stop", "base_year", "fixed"]
DENOMINATORS = ["rentable_area", "property_size", "occupied_area",
                "fixed_area"]
ADMIN_FEE_APPLIES = ["before_stop", "after_stop"]
DEPOSIT_UNITS = ["months_of_rent", "dollars", "dollars_per_area"]
SALES_UNITS = ["dollars_per_year", "dollars_per_area_per_year"]
BREAKPOINTS = ["natural", "fixed_amount", "zero"]


def ti_lc_category_refusal(tenant_name: str) -> str:
    """The engine's refusal, verbatim (engine/calc/run.py `_phase_guards`)."""
    return (f"lease {tenant_name!r}: TI/LC categories is not implemented "
            "until a later phase (DEVIATIONS.md §16); remove the input or "
            "wait for that phase")


# ------------------------------------------------------------------ #
# Pure commit functions                                               #
# ------------------------------------------------------------------ #

def apply_lease_grid(model, rows: list[dict]):
    def mutate(data):
        data["rent_roll"] = convert.apply_lease_grid_rows(data["rent_roll"],
                                                          rows)
    return state.updated_model(model, mutate)


def apply_lease_detail(model, index: int, payload: dict):
    """Merge a detail payload into lease ``index``. The payload never
    carries ``leasing_costs.ti_category``/``lc_category`` — those are
    engine-refused and preserved untouched (Step 0 D2)."""
    def mutate(data):
        data["rent_roll"][index].update(payload)
    return state.updated_model(model, mutate)


def apply_absorption(model, rows: list[dict]):
    def mutate(data):
        data["absorption"] = convert.rows_to_absorption(rows)
    return state.updated_model(model, mutate)


def apply_recovery_structure(model, index: int, payload: dict):
    def mutate(data):
        data["recovery_structures"][index].update(payload)
    return state.updated_model(model, mutate)


def add_recovery_structure(model, name: str):
    def mutate(data):
        data["recovery_structures"].append(
            {"name": name, "pools": [{"expenses": [], "method": "net"}]})
    return state.updated_model(model, mutate)


def delete_recovery_structure(model, index: int):
    def mutate(data):
        del data["recovery_structures"][index]
    return state.updated_model(model, mutate)


def apply_imported_rent_roll(model, leases):
    """Replace the rent roll with the Contractual leases an import
    produced (the §5.2 intake semantic); whole-document revalidation
    catches broken refs (e.g. an MLP name the model doesn't define)."""
    def mutate(data):
        data["rent_roll"] = [l.model_dump(mode="json") for l in leases]
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


def _render_grid(model, data, rev: int) -> None:
    st.caption("Rent roll — scalars here; steps/CPI/free rent/misc/deposit/"
               "% rent/recoveries in the detail pane. Add a row to add a "
               "lease; delete a row to delete one.")
    grid = st.data_editor(
        convert.lease_grid_rows(data["rent_roll"])
        or [{c: None for c in convert.LEASE_GRID_COLUMNS}],
        num_rows="dynamic", key=f"rr_grid_{rev}",
        column_config={
            "lease_type": st.column_config.SelectboxColumn(options=LEASE_TYPES),
            "status": st.column_config.SelectboxColumn(options=LEASE_STATUSES),
            "base_rent_unit": st.column_config.SelectboxColumn(
                options=RENT_UNITS),
            "upon_expiration": st.column_config.SelectboxColumn(
                options=UPON_EXPIRATION),
        })
    if st.button("Apply rent roll grid", key=f"rr_grid_apply_{rev}"):
        _apply_and_report(*apply_lease_grid(model, grid),
                          "Rent roll updated.")


def _cpi_inputs(current, key: str):
    enabled = st.checkbox("CPI — set", value=current is not None,
                          key=f"{key}_on")
    if not enabled:
        return None
    current = current or {}
    method = st.selectbox("CPI method", CPI_METHODS,
                          index=CPI_METHODS.index(current.get("method",
                                                              "full_cpi")),
                          key=f"{key}_method")
    index_name = st.text_input("CPI index (blank = the cpi series)",
                               value=current.get("index") or "",
                               key=f"{key}_index")
    pct = st.number_input("Pct (for pct_of_cpi / cpi_plus_pct; 0 = n/a)",
                          value=float(current.get("pct") or 0.0),
                          key=f"{key}_pct")
    first = st.text_input("First increase month (# or 'anniversary')",
                          value=str(current.get("first_increase_month",
                                                "anniversary")),
                          key=f"{key}_first")
    frequency = st.number_input("Frequency (months)",
                                value=int(current.get("frequency_months", 12)),
                                step=1, key=f"{key}_freq")
    cap = st.number_input("Cap % (0 = none)",
                          value=float(current.get("cap_pct") or 0.0),
                          key=f"{key}_cap")
    floor = st.number_input("Floor % (0 = none)",
                            value=float(current.get("floor_pct") or 0.0),
                            key=f"{key}_floor")
    first_value = first.strip()
    return {"method": method, "index": index_name or None,
            "pct": pct or None,
            "first_increase_month": (first_value if first_value == "anniversary"
                                     else int(first_value or 0)),
            "frequency_months": int(frequency),
            "cap_pct": cap or None, "floor_pct": floor or None}


def _free_rent_inputs(current, key: str, profile_names: list[str]):
    enabled = st.checkbox("Free rent — set", value=current is not None,
                          key=f"{key}_on")
    if not enabled:
        return None
    current = current or {}
    months = st.number_input("Free months",
                             value=float(current.get("months", 0.0)),
                             key=f"{key}_months")
    timing = st.radio("Timing", ["front", "custom"],
                      index=0 if current.get("timing", "front") == "front"
                      else 1, horizontal=True, key=f"{key}_timing")
    custom = None
    if timing == "custom":
        text = st.text_input("Custom months (1-based offsets, e.g. 1,13)",
                             value=",".join(str(m) for m in
                                            current.get("custom_months")
                                            or []),
                             key=f"{key}_custom")
        custom = [int(m) for m in text.replace(" ", "").split(",") if m]
    options = [""] + profile_names
    profile = st.selectbox("Free-rent profile", options,
                           index=(options.index(current.get("profile"))
                                  if current.get("profile") in options else 0),
                           key=f"{key}_profile")
    return {"months": months, "timing": timing, "custom_months": custom,
            "profile": profile or None}


def _deposit_inputs(current, key: str):
    enabled = st.checkbox("Security deposit — set",
                          value=current is not None, key=f"{key}_on")
    if not enabled:
        return None
    current = current or {}
    amount = st.number_input("Deposit amount",
                             value=float(current.get("amount", 0.0)),
                             key=f"{key}_amt")
    unit = st.selectbox("Deposit unit", DEPOSIT_UNITS,
                        index=DEPOSIT_UNITS.index(
                            current.get("unit", "months_of_rent")),
                        key=f"{key}_unit")
    refunded = st.checkbox("Refunded at expiration",
                           value=bool(current.get("refunded_at_expiration",
                                                  True)),
                           key=f"{key}_ref")
    return {"amount": amount, "unit": unit,
            "refunded_at_expiration": refunded}


def _pct_rent_inputs(current, key: str):
    enabled = st.checkbox("Percentage rent — set (externally unvalidated "
                          "pending golden #3)", value=current is not None,
                          key=f"{key}_on")
    if not enabled:
        return None
    current = current or {"sales_volume": {}, "breakpoint_layers": []}
    sales = current.get("sales_volume") or {}
    amount = st.number_input("Sales volume",
                             value=float(sales.get("amount", 0.0)),
                             key=f"{key}_sales")
    unit = st.selectbox("Sales unit", SALES_UNITS,
                        index=SALES_UNITS.index(
                            sales.get("unit", "dollars_per_year")),
                        key=f"{key}_salesunit")
    breakpoint = st.selectbox("Breakpoint", BREAKPOINTS,
                              index=BREAKPOINTS.index(
                                  current.get("breakpoint", "natural")),
                              key=f"{key}_bp")
    st.caption("Layers (up to 6; breakpoint_amount only for fixed_amount)")
    layer_rows = st.data_editor(
        convert.layers_to_rows(current.get("breakpoint_layers") or [])
        or [{"breakpoint_amount": None, "pct": None}],
        num_rows="dynamic", key=f"{key}_layers")
    return {"sales_volume": {"amount": amount, "unit": unit,
                             "growth": sales.get("growth")},
            "breakpoint": breakpoint,
            "breakpoint_layers": convert.rows_to_layers(layer_rows)}


def _leasing_costs_inputs(lease: dict, key: str):
    current = lease.get("leasing_costs") or {}
    enabled = st.checkbox("Contract-term TI/LC — set",
                          value=lease.get("leasing_costs") is not None,
                          key=f"{key}_on")
    if current.get("ti_category") or current.get("lc_category"):
        st.warning(ti_lc_category_refusal(lease["tenant_name"]))
    if not enabled:
        return None
    ti = common_widgets.money_rate_inputs("TI", current.get("ti"),
                                          common_widgets.TI_UNITS,
                                          f"{key}_ti", optional=True)
    lc = common_widgets.lc_spec_inputs("LC", current.get("lc"), f"{key}_lc")
    # categories preserved verbatim — engine-refused, never edited here
    return {"ti": ti, "ti_category": current.get("ti_category"),
            "lc": lc, "lc_category": current.get("lc_category")}


def _render_generations_panel(tenant: str) -> None:
    """The D6-amendment Freeport E surface: per-generation rollover
    economics, READ-ONLY, from result.segments."""
    st.markdown("**Rollover generations (engine-projected — read-only)**")
    result = st.session_state.get("result")
    if result is None:
        st.info("Calculate to view the engine-projected generations "
                "(rollover + absorption) for this lease.")
        return
    segments = result.segments.get(tenant)
    if not segments:
        st.caption("No resolved chain for this tenant in the last run "
                   "(recalculate after edits).")
        return
    rows = convert.segments_to_generation_rows(segments, CONTRACTUAL,
                                               SPECULATIVE)
    st.dataframe(rows, key="gen_df", width="stretch")
    st.caption("Per-generation renewal LC rates / TI / weights — the "
               "parked Freeport E inspection surface (DEVIATIONS §25; "
               "NEXT_STEPS_TO_PHASE5.md Step 0 D6 amendment).")


def _render_detail_pane(model, data, rev: int) -> None:
    leases = data["rent_roll"]
    if not leases:
        st.info("No leases yet — add one in the grid or import a template.")
        return
    options = [f"{i}: {l['tenant_name']}" for i, l in enumerate(leases)]
    chosen = st.selectbox("Lease", options, key=f"ld_pick_{rev}")
    index = int(chosen.split(":", 1)[0])
    lease = leases[index]
    key = f"ld_{index}_{rev}"
    profile_names = [p["name"] for p in data["free_rent_profiles"]]
    structure_names = [s["name"] for s in data["recovery_structures"]]

    with st.expander("Rent steps", expanded=False):
        step_rows = st.data_editor(
            convert.rent_steps_to_rows(lease["rent_steps"])
            or [{c: None for c in convert.RENT_STEP_COLUMNS}],
            num_rows="dynamic", key=f"{key}_steps",
            column_config={"unit": st.column_config.SelectboxColumn(
                options=RENT_UNITS)})
    with st.expander("CPI", expanded=False):
        cpi = _cpi_inputs(lease["cpi"], f"{key}_cpi")
    with st.expander("Free rent", expanded=False):
        free_rent = _free_rent_inputs(lease["free_rent"], f"{key}_fr",
                                      profile_names)
    with st.expander("Miscellaneous items", expanded=False):
        misc_rows = st.data_editor(
            convert.misc_items_to_rows(lease["miscellaneous_items"])
            or [{c: None for c in convert.MISC_ITEM_GRID_COLUMNS}],
            num_rows="dynamic", key=f"{key}_misc")
    with st.expander("Security deposit", expanded=False):
        deposit = _deposit_inputs(lease["security_deposit"], f"{key}_dep")
    with st.expander("Percentage rent", expanded=False):
        pct_rent = _pct_rent_inputs(lease["percentage_rent"], f"{key}_pr")
    with st.expander("Recoveries", expanded=False):
        recoveries = common_widgets.recovery_assignment_inputs(
            lease["recoveries"], f"{key}_rec", structure_names)
    with st.expander("Contract-term TI/LC", expanded=False):
        leasing_costs = _leasing_costs_inputs(lease, f"{key}_lc")

    if st.button("Apply lease detail", key=f"{key}_apply"):
        payload = {
            "rent_steps": convert.rows_to_rent_steps(step_rows) or [],
            "cpi": cpi, "free_rent": free_rent,
            "miscellaneous_items": convert.apply_misc_item_rows(
                lease["miscellaneous_items"], misc_rows),
            "security_deposit": deposit, "percentage_rent": pct_rent,
            "recoveries": recoveries, "leasing_costs": leasing_costs,
        }
        _apply_and_report(*apply_lease_detail(model, index, payload),
                          f"Lease '{lease['tenant_name']}' updated.")

    _render_generations_panel(lease["tenant_name"])


def _render_absorption(model, data, rev: int) -> None:
    with st.expander("Space absorption (§3.15)", expanded=False):
        rows = st.data_editor(
            convert.absorption_to_rows(data["absorption"])
            or [{c: None for c in convert.ABSORPTION_GRID_COLUMNS}],
            num_rows="dynamic", key=f"abs_grid_{rev}",
            column_config={"lease_type": st.column_config.SelectboxColumn(
                options=LEASE_TYPES)})
        if st.button("Apply absorption", key=f"abs_apply_{rev}"):
            _apply_and_report(*apply_absorption(model, rows),
                              "Absorption updated.")


def _render_structures(model, data, rev: int) -> None:
    structures = data["recovery_structures"]
    expense_names = [e["name"] for e in data["expenses"]]
    group_names = [g["name"] for g in data["expense_groups"]]
    member_options = expense_names + group_names
    with st.expander(f"Recovery structures ({len(structures)})",
                     expanded=False):
        new_name = st.text_input("New structure name", key=f"rs_new_{rev}")
        if st.button("Add structure", key=f"rs_add_{rev}") and new_name:
            _apply_and_report(*add_recovery_structure(model, new_name),
                              f"Structure '{new_name}' added.")
        if not structures:
            return
        names = [s["name"] for s in structures]
        chosen = st.selectbox("Structure", names, key=f"rs_pick_{rev}")
        s_index = names.index(chosen)
        structure = structures[s_index]
        key = f"rs_{s_index}_{rev}"
        name = st.text_input("Name", value=structure["name"],
                             key=f"{key}_name")
        pools = []
        for p_i, pool in enumerate(structure["pools"]):
            with st.container(border=True):
                st.markdown(f"**Pool {p_i + 1}**")
                pkey = f"{key}_p{p_i}"
                options = sorted(set(member_options)
                                 | set(pool["expenses"]))
                members = st.multiselect("Expenses / groups", options,
                                         default=pool["expenses"],
                                         key=f"{pkey}_members")
                method = st.selectbox("Method", POOL_METHODS,
                                      index=POOL_METHODS.index(pool["method"]),
                                      key=f"{pkey}_method")
                col1, col2, col3 = st.columns(3)
                with col1:
                    gross = st.number_input(
                        "Gross-up % (0 = none)",
                        value=float(pool["gross_up_pct"] or 0.0),
                        key=f"{pkey}_gross")
                    stop = st.number_input(
                        "Stop $/SF (0 = none)",
                        value=float(pool["base_amount_per_area"] or 0.0),
                        key=f"{pkey}_stop")
                with col2:
                    admin = st.number_input(
                        "Admin fee %", value=float(pool["admin_fee_pct"]),
                        key=f"{pkey}_admin")
                    applies = st.selectbox(
                        "Admin fee applies", ADMIN_FEE_APPLIES,
                        index=ADMIN_FEE_APPLIES.index(
                            pool["admin_fee_applies"]),
                        key=f"{pkey}_applies")
                with col3:
                    denominator = st.selectbox(
                        "Denominator", DENOMINATORS,
                        index=DENOMINATORS.index(pool["denominator"]),
                        key=f"{pkey}_den")
                    share = st.number_input(
                        "Pro-rata share override % (0 = none)",
                        value=float(pool["pro_rata_share_override"] or 0.0),
                        key=f"{pkey}_share")
                caps = pool["caps_floors"] or {}
                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    yearly = st.number_input("YoY cap % (0=none)",
                                             value=float(
                                                 caps.get("yearly_cap_pct")
                                                 or 0.0),
                                             key=f"{pkey}_ycap")
                with c2:
                    cumulative = st.number_input(
                        "Cumulative cap % (0=none)",
                        value=float(caps.get("cumulative_cap_pct") or 0.0),
                        key=f"{pkey}_ccap")
                with c3:
                    floor = st.number_input("Floor $ (0=none)",
                                            value=float(caps.get("min")
                                                        or 0.0),
                                            key=f"{pkey}_min")
                with c4:
                    cap_max = st.number_input("Cap $ (0=none)",
                                              value=float(caps.get("max")
                                                          or 0.0),
                                              key=f"{pkey}_max")
                st.caption("Expense adjustments (exclude / include pct)")
                adj_rows = st.data_editor(
                    convert.adjustments_to_rows(pool["expense_adjustments"])
                    or [{c: None for c in convert.ADJUSTMENT_COLUMNS}],
                    num_rows="dynamic", key=f"{pkey}_adj")
                caps_payload = None
                if yearly or cumulative or floor or cap_max:
                    caps_payload = {"yearly_cap_pct": yearly or None,
                                    "cumulative_cap_pct": cumulative or None,
                                    "min": floor or None,
                                    "max": cap_max or None}
                pools.append({
                    "expenses": members, "method": method,
                    "gross_up_pct": gross or None,
                    "base_amount_per_area": stop or None,
                    "base_year": pool["base_year"],
                    "fixed_amount": pool["fixed_amount"],
                    "fixed_inflation": pool["fixed_inflation"],
                    "admin_fee_pct": admin,
                    "admin_fee_applies": applies,
                    "denominator": denominator,
                    "denominator_fixed_area": pool["denominator_fixed_area"],
                    "pro_rata_share_override": share or None,
                    "caps_floors": caps_payload,
                    "expense_adjustments": convert.rows_to_adjustments(
                        adj_rows),
                })
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Apply structure", key=f"{key}_apply"):
                _apply_and_report(
                    *apply_recovery_structure(model, s_index,
                                              {"name": name, "pools": pools}),
                    f"Structure '{name}' updated.")
        with col2:
            if st.button("Delete structure", key=f"{key}_delete"):
                _apply_and_report(*delete_recovery_structure(model, s_index),
                                  f"Structure '{chosen}' deleted.")


def _render_import(model, rev: int) -> None:
    with st.expander("Import rent-roll template (§5.2)", expanded=False):
        st.caption("The Rent Roll + Rent Steps + Misc Items template the "
                   "exporter writes. Contractual rows become leases; "
                   "Speculative rows are engine projections and are "
                   "reported, never silently skipped.")
        uploaded = st.file_uploader("Template (.xlsx)", type=["xlsx"],
                                    key=f"imp_upload_{rev}")
        path_text = st.text_input("…or a path to a template file",
                                  key=f"imp_path_{rev}")
        if st.button("Import", key=f"imp_btn_{rev}"):
            try:
                if uploaded is not None:
                    with tempfile.NamedTemporaryFile(
                            suffix=".xlsx", delete=False) as handle:
                        handle.write(uploaded.getvalue())
                        temp_path = Path(handle.name)
                    imported = import_rent_roll(temp_path)
                    temp_path.unlink(missing_ok=True)
                elif path_text.strip():
                    imported = import_rent_roll(Path(path_text.strip()))
                else:
                    st.error("Choose a file or enter a path first.")
                    return
            except RentRollImportError as exc:
                st.error(str(exc))          # the Step-7 readable text verbatim
                return
            except OSError as exc:
                st.error(f"Could not read the template: {exc}.")
                return
            for note in imported.notes:
                st.info(note)               # ignored Speculative rows — stated
            _apply_and_report(
                *apply_imported_rent_roll(model, imported.leases),
                f"Imported {len(imported.leases)} lease(s).")


def render() -> None:
    model = st.session_state.model
    if model is None:
        st.info("Open or create a property in the sidebar first.")
        return
    rev = session.rev()
    data = model.model_dump(mode="json")
    st.subheader("Tenants (§3.12-3.15)")
    grid_col, detail_col = st.columns([5, 3])   # D5 persistent split pane
    with grid_col:
        _render_grid(model, data, rev)
        _render_absorption(model, data, rev)
        _render_structures(model, data, rev)
        _render_import(model, rev)
    with detail_col:
        _render_detail_pane(model, data, rev)
