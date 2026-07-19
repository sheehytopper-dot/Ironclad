"""Investment tab (Phase 5 Step 5; spec §6 tab 6 — §3.16-3.17).

``Purchase`` + closing costs and the ``Loan`` grid + per-loan detail
(fixed/floating rate, IO periods, balloon amortization, additional
principal, loan costs). The two **permanent refusals** (DEVIATIONS §20 #6,
owner decision 2026-07-12) render READ-ONLY with the engine's messages
verbatim — ``LoanAmountBasis.pct_of_value`` sizing and
``Purchase.derivation != fixed`` (derived price). NOTE both engine
messages still carry the stale "OPEN OWNER SCOPE DECISION" label (the
decision is closed); surfaced as-is per the stale-message list in
NEXT_STEPS_TO_PHASE5.md — engine-frozen. Same funnel pattern as every tab.
"""
from __future__ import annotations

import streamlit as st

from ui import convert, session, state
from ui.tabs import common_widgets

AMOUNT_BASES = ["amount", "pct_of_price"]      # pct_of_value is refused
LOAN_COST_HANDLING = ["expense", "amortize"]
CLOSING_TIMING = ["at_purchase", "custom_date"]


def refusal_pct_of_value_text(name: str) -> str:
    """The engine's refusal, verbatim (engine/calc/debt.py `_principal0`).
    Its "OPEN OWNER SCOPE DECISION" label is STALE — the decision closed
    2026-07-12 as permanent (DEVIATIONS §20 #6); on the stale-message
    list."""
    return (f"loan {name!r}: amount basis 'pct_of_value' (\"% of Adopted "
            "Valuation\" [AE p. 438]) is not implemented. Step 5 (PV/IRR) "
            "built the valuation this would size off, but a loan sized off "
            "the derived property value is an OPEN OWNER SCOPE DECISION "
            "(DEVIATIONS.md §20): debt is computed at pass 12 and valuation "
            "at pass 14, so a value-sized loan needs the (unleveraged) "
            "valuation reordered before debt — added architecture no golden "
            "or current deal needs. Use an amount or pct_of_price.")


def refusal_derived_price_text(derivation: str) -> str:
    """The engine's refusal, verbatim (engine/calc/investment.py). Same
    stale "OPEN" label; same stale-message-list entry."""
    return (f"purchase price derivation {derivation!r} (price backed out "
            "from computed valuation) is not implemented. Step 5 (PV/IRR) "
            "built the unleveraged PV this would derive from, but live "
            "derivation is an OPEN OWNER SCOPE DECISION (DEVIATIONS.md "
            "§20): deriving the price from the unleveraged PV is "
            "non-circular ONLY with no price-dependent loans and a resale "
            "method other than pct_increase_over_price, and even then needs "
            "the acquisition-flow posting deferred past valuation; a "
            "pct_of_price/pct_of_value loan sized off the derived price "
            "needs debt reordered after valuation. Use derivation 'fixed'.")


# ------------------------------------------------------------------ #
# Pure commit functions                                               #
# ------------------------------------------------------------------ #

def apply_purchase(model, payload):
    """``payload`` = {price, date, closing_costs} or None (no purchase).
    A derived-derivation purchase is engine-refused and read-only here."""
    def mutate(data):
        current = data.get("purchase")
        if current and current.get("derivation") != "fixed":
            raise ValueError(
                "this purchase uses a derived price derivation "
                f"({current['derivation']!r}) — permanently refused by the "
                "engine (DEVIATIONS §20 #6) and read-only here")
        if payload is None:
            data["purchase"] = None
            return
        block = dict(current or {"derivation": "fixed"})
        block.update(payload)
        data["purchase"] = block
    return state.updated_model(model, mutate)


def apply_loan_grid(model, rows: list[dict]):
    def mutate(data):
        data["loans"] = convert.apply_loan_grid_rows(data["loans"], rows)
    return state.updated_model(model, mutate)


def apply_loan_detail(model, index: int, payload: dict):
    """Merge a detail payload (rate / interest_only_months /
    additional_principal / loan_costs) into loan ``index``."""
    def mutate(data):
        if convert.is_refused_loan(data["loans"][index]):
            raise ValueError(
                "this loan is sized pct_of_value — permanently refused by "
                "the engine (DEVIATIONS §20 #6) and read-only here")
        data["loans"][index].update(payload)
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


def _render_purchase(model, data, rev: int) -> None:
    purchase = data.get("purchase")
    with st.expander("Purchase & closing costs (§3.16)", expanded=False):
        if purchase and purchase.get("derivation") != "fixed":
            st.warning(refusal_derived_price_text(purchase["derivation"]))
            st.caption("Decision closed 2026-07-12: a PERMANENT boundary "
                       "(DEVIATIONS §20 #6) — the engine message's 'OPEN' "
                       "label is stale (see the stale-message list). "
                       "Read-only:")
            st.json(purchase)
            return
        enabled = st.checkbox("Purchase — set", value=purchase is not None,
                              key=f"pur_on_{rev}")
        if not enabled:
            if st.button("Apply purchase", key=f"pur_apply_{rev}"):
                _apply_and_report(*apply_purchase(model, None),
                                  "Purchase cleared.")
            return
        current = purchase or {}
        price = st.number_input("Price (0 = none)",
                                value=float(current.get("price") or 0.0),
                                key=f"pur_price_{rev}")
        date = st.text_input("Purchase date (YYYY-MM-DD; blank = analysis "
                             "begin)", value=current.get("date") or "",
                             key=f"pur_date_{rev}")
        st.caption("Closing costs ($ amount or % of price; timing "
                   "at_purchase or custom_date + date)")
        cost_rows = st.data_editor(
            convert.closing_costs_to_rows(current.get("closing_costs") or [])
            or [{c: None for c in convert.CLOSING_COST_COLUMNS}],
            num_rows="dynamic", key=f"pur_costs_{rev}",
            column_config={"timing": st.column_config.SelectboxColumn(
                options=CLOSING_TIMING)})
        if st.button("Apply purchase", key=f"pur_apply_{rev}"):
            payload = {"price": price or None, "date": date or None,
                       "closing_costs": convert.rows_to_closing_costs(
                           cost_rows)}
            _apply_and_report(*apply_purchase(model, payload),
                              "Purchase updated.")


def _render_loans(model, data, rev: int) -> None:
    loans = data["loans"]
    with st.expander(f"Loans (§3.17) — {len(loans)}", expanded=False):
        st.caption("Scalar grid — floating rates, additional principal, and "
                   "loan costs in the detail editor. Rate: a number is a "
                   "fixed annual %; '(floating)' loans are edited below. "
                   "Amortization: 'fully_amortizing', 'interest_only', or a "
                   "year count (balloon).")
        grid = st.data_editor(
            convert.loans_to_grid_rows(loans)
            or [{c: None for c in convert.LOAN_GRID_COLUMNS}],
            num_rows="dynamic", key=f"loan_grid_{rev}",
            column_config={"amount_basis": st.column_config.SelectboxColumn(
                options=AMOUNT_BASES)})
        if st.button("Apply loan grid", key=f"loan_grid_apply_{rev}"):
            _apply_and_report(*apply_loan_grid(model, grid),
                              "Loans updated.")

        refused = convert.refused_loans(loans)
        if refused:
            st.markdown("**Engine-refused loans — READ-ONLY (permanent, "
                        "DEVIATIONS §20 #6)**")
            for loan in refused:
                st.warning(refusal_pct_of_value_text(loan["name"]))
                st.json(loan)

        editable_indices = [i for i, l in enumerate(loans)
                            if not convert.is_refused_loan(l)]
        if not editable_indices:
            return
        options = [f"{i}: {loans[i]['name']}" for i in editable_indices]
        chosen = st.selectbox("Detail editor — loan", options,
                              key=f"loan_pick_{rev}")
        index = int(chosen.split(":", 1)[0])
        loan = loans[index]
        key = f"loan_{index}_{rev}"

        floating_now = isinstance(loan["rate"], dict)
        mode = st.radio("Rate", ["fixed", "floating"],
                        index=1 if floating_now else 0, horizontal=True,
                        key=f"{key}_ratemode")
        if mode == "fixed":
            rate = st.number_input(
                "Annual rate %",
                value=float(loan["rate"]) if not floating_now else 6.0,
                key=f"{key}_rate")
        else:
            current = loan["rate"] if floating_now else {}
            st.caption("Floating = index schedule + spread ([AE pp. "
                       "441-442]; payment re-levels on each rate change)")
            index_rows = st.data_editor(
                convert.year_rates_to_rows(current.get("index"))
                or [{"year": None, "rate": None}],
                num_rows="dynamic", key=f"{key}_frate")
            spread = st.number_input("Spread %",
                                     value=float(current.get("spread", 0.0)),
                                     key=f"{key}_spread")
            rate = {"index": convert.rows_to_year_rates(index_rows),
                    "spread": spread}
        io_months = st.number_input("Interest-only months",
                                    value=int(loan["interest_only_months"]),
                                    step=1, key=f"{key}_io")
        st.caption("Additional principal (Recalc-Pmt-No behavior "
                   "[AE p. 444])")
        extra_rows = st.data_editor(
            convert.additional_principal_to_rows(loan["additional_principal"])
            or [{c: None for c in convert.ADDITIONAL_PRINCIPAL_COLUMNS}],
            num_rows="dynamic", key=f"{key}_extra")
        costs_on = st.checkbox("Loan costs — set",
                               value=loan["loan_costs"] is not None,
                               key=f"{key}_costs_on")
        loan_costs = None
        if costs_on:
            current = loan["loan_costs"] or {}
            col1, col2 = st.columns(2)
            with col1:
                points = st.number_input("Points % of principal",
                                         value=float(current.get("points_pct",
                                                                 0.0)),
                                         key=f"{key}_points")
                fees = st.number_input("Fees $",
                                       value=float(current.get("fees", 0.0)),
                                       key=f"{key}_fees")
            with col2:
                timing = st.text_input("Timing (YYYY-MM-DD; blank = at "
                                       "funding)",
                                       value=current.get("timing") or "",
                                       key=f"{key}_ctiming")
                handling = st.selectbox(
                    "Handling (cash timing identical — DEVIATIONS §18/§24)",
                    LOAN_COST_HANDLING,
                    index=LOAN_COST_HANDLING.index(
                        current.get("handling", "expense")),
                    key=f"{key}_handling")
            loan_costs = {"points_pct": points, "fees": fees,
                          "timing": timing or None, "handling": handling}
        if st.button("Apply loan detail", key=f"{key}_apply"):
            payload = {"rate": rate,
                       # Loan.type must track the rate shape (the §3.17
                       # validator: fixed loans need a numeric rate)
                       "type": ("floating" if isinstance(rate, dict)
                                else "fixed"),
                       "interest_only_months": int(io_months),
                       "additional_principal":
                           convert.rows_to_additional_principal(extra_rows),
                       "loan_costs": loan_costs}
            _apply_and_report(*apply_loan_detail(model, index, payload),
                              f"Loan '{loan['name']}' updated.")


def render() -> None:
    model = st.session_state.model
    if model is None:
        st.info("Open or create a property in the sidebar first.")
        return
    rev = session.rev()
    data = model.model_dump(mode="json")
    st.subheader("Investment (§3.16-3.17)")
    _render_purchase(model, data, rev)
    _render_loans(model, data, rev)
