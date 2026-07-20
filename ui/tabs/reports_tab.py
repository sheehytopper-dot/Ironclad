"""Reports tab (Phase 5 Step 6; spec §6 tab 8).

Picker over the built §7 reports (the ``ui.reports_registry``), global
unit/period toggles wired to the Step-1 report primitives, the date-range
column slice (presentation only), provenance captions on #11/#12,
export-this-view, and the §8 package export — **both exports reuse the
Phase 4 machinery** (``export_report`` / ``build_package``), nothing
rewritten. Benchmark #24 appears only when the loaded property has an
``expected_annual_cash_flow.csv`` beside it.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

from engine.export import build_package, export_report
from engine.reports import Period, Unit
from ui import format as fmt
from ui import reports_registry as registry
from ui import theme

UNITS = [u.value for u in Unit]
PERIODS = [p.value for p in Period]


def _download(label: str, path: Path, *, key: str) -> None:
    st.download_button(label, data=path.read_bytes(), file_name=path.name,
                       mime=("application/vnd.openxmlformats-officedocument"
                             ".spreadsheetml.sheet"), key=key)


def render() -> None:
    model = st.session_state.get("model")
    result = st.session_state.get("result")
    if model is None:
        st.info("Open or create a property in the sidebar first.")
        return
    if result is None:
        st.info("Press **Calculate** in the sidebar to render reports.")
        return
    st.subheader("Reports (§7)")

    csv_path = registry.find_benchmark_csv(
        st.session_state.get("model_path"))
    entries = registry.applicable_entries(result, model, csv_path)
    labels = [f"#{e.number} {e.label}" for e in entries]

    # one compact control row: picker + toggles side by side (the mockup's
    # terminal-style header strip)
    unit, period = Unit.total, Period.fiscal
    options: dict = {}
    pick_col, col1, col2, col3 = st.columns([2.4, 1, 1, 1.2])
    with pick_col:
        chosen = st.selectbox("Report", labels, key="report_pick")
    entry = entries[labels.index(chosen)]
    if entry.supports_unit:
        with col1:
            unit = Unit(st.selectbox("Unit ($)", UNITS, key="report_unit"))
    if entry.supports_period:
        with col2:
            period = Period(st.selectbox(
                "Period", PERIODS, index=PERIODS.index("fiscal"),
                key="report_period"))
    if entry.number in (11, 12):
        with col3:
            options["contractual_only"] = st.checkbox(
                "Contractual only", value=False, key="report_contractual")
    if entry.number == 20:
        with col3:
            options["loan_index"] = st.selectbox(
                "Loan", list(range(len(result.loan_schedules))),
                format_func=lambda i: f"{i}: "
                f"{result.loan_schedules[i].loan.name}",
                key="report_loan")
    if entry.number == 24:
        options["benchmark_csv"] = csv_path

    report = registry.build_entry(entry, result, model, unit=unit,
                                  period=period, options=options)
    if entry.note:
        st.caption(entry.note)
    if entry.number == 24:
        skipped = report.meta.extra.get("skipped_accounts") or []
        st.metric("Line-years beyond tolerance",
                  int(report.meta.extra["miss_count"]))
        if skipped:
            st.warning("CSV accounts with no matching ledger line, skipped "
                       f"and reported (never silently): {', '.join(skipped)}"
                       " — the golden test suites carry the per-golden name "
                       "bridges.")

    # display-only formatting (ui/format.py) — report.frame stays raw and
    # is what the exporters below receive
    if entry.number == 1 and len(report.frame.columns) > 1:
        columns = [str(c) for c in report.frame.columns]
        col1, col2 = st.columns(2)
        with col1:
            start = st.selectbox("From period", columns, index=0,
                                 key="report_from")
        with col2:
            end = st.selectbox("To period", columns,
                               index=len(columns) - 1, key="report_to")
        sliced = registry.slice_period_columns(
            report.frame, report.frame.columns[columns.index(start)],
            report.frame.columns[columns.index(end)])
        st.dataframe(fmt.cash_flow_display(report, columns=sliced.columns),
                     key="report_frame", width="stretch",
                     height=min(38 * (len(report.frame) + 1), 1400))
    else:
        st.dataframe(fmt.report_display(report), key="report_frame",
                     width="stretch", row_height=theme.DENSE_ROW_HEIGHT)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Export this view", key="export_view_btn"):
            path = (Path(tempfile.mkdtemp())
                    / f"{model.property.name}-{entry.label}.xlsx".replace(
                        " ", "-").lower())
            export_report(report, path=path)     # the Phase 4 exporter
            _download("Download report workbook", path, key="dl_view")
    with col2:
        if st.button("Export §8 package", key="export_pkg_btn"):
            path = (Path(tempfile.mkdtemp())
                    / f"{model.property.name}-package.xlsx".replace(
                        " ", "-").lower())
            build_package(result, model, path=path)  # the Phase 4 package
            _download("Download package workbook", path, key="dl_pkg")
