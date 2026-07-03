"""Unit tests for engine/calc/timeline.py (Phase 0) [AE pp. 182-187]."""
import datetime as dt

import pandas as pd
import pytest

from engine.calc.timeline import (
    analysis_year_of,
    build_month_index,
    fiscal_year_of,
    month_offset,
    snap_to_month_start,
)


class TestMonthIndex:
    def test_index_spans_term_plus_resale_lookforward(self):
        """Timeline runs analysis begin → end + 12 months for the resale NOI
        look-forward (spec §2.3, §4.1 step 1)."""
        idx = build_month_index(dt.date(2026, 1, 1), 10)
        assert len(idx) == 11 * 12
        assert idx[0] == pd.Period("2026-01", freq="M")
        assert idx[-1] == pd.Period("2036-12", freq="M")

    def test_one_year_term(self):
        idx = build_month_index(dt.date(2026, 7, 1), 1)
        assert len(idx) == 24
        assert idx[0] == pd.Period("2026-07", freq="M")

    def test_begin_date_snaps_to_month(self):
        """All timing snaps to first-of-month (spec §3.1) [AE pp. 182-187]."""
        assert build_month_index(dt.date(2026, 3, 15), 1)[0] == pd.Period("2026-03", freq="M")
        assert snap_to_month_start(dt.date(2026, 3, 15)) == dt.date(2026, 3, 1)

    def test_invalid_term_rejected(self):
        with pytest.raises(ValueError):
            build_month_index(dt.date(2026, 1, 1), 0)


class TestDateMath:
    def test_month_offset(self):
        begin = dt.date(2026, 7, 1)
        assert month_offset(begin, dt.date(2026, 7, 31)) == 0
        assert month_offset(begin, dt.date(2027, 7, 1)) == 12
        assert month_offset(begin, dt.date(2026, 6, 1)) == -1

    def test_analysis_year_of_mid_year_start(self):
        """Analysis years are 12-month blocks from the begin month, not
        calendar years — a July 2026 start puts June 2027 in year 1 and
        July 2027 in year 2."""
        begin = dt.date(2026, 7, 1)
        assert analysis_year_of(begin, pd.Period("2026-07", freq="M")) == 1
        assert analysis_year_of(begin, pd.Period("2027-06", freq="M")) == 1
        assert analysis_year_of(begin, pd.Period("2027-07", freq="M")) == 2

    def test_analysis_year_rejects_pre_begin_months(self):
        with pytest.raises(ValueError):
            analysis_year_of(dt.date(2026, 7, 1), pd.Period("2026-06", freq="M"))


class TestFiscalYear:
    def test_calendar_year_end(self):
        """Default December year-end: fiscal year == calendar year."""
        assert fiscal_year_of(pd.Period("2026-01", freq="M"), 12) == 2026
        assert fiscal_year_of(pd.Period("2026-12", freq="M"), 12) == 2026

    def test_june_year_end(self):
        """Fiscal years are named for the calendar year in which they end
        (spec §3.1 fiscal_year_end_month): with a June year-end, July 2026
        belongs to FY2027."""
        assert fiscal_year_of(pd.Period("2026-06", freq="M"), 6) == 2026
        assert fiscal_year_of(pd.Period("2026-07", freq="M"), 6) == 2027
