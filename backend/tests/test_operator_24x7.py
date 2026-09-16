"""Tests for Salesoorja 24x7 Production Mode and Midnight Rollover.

Verifies:
1. Continuous 24x7 operator eligibility at:
   - 00:00 IST
   - 00:01 IST
   - 02:00 IST
   - 08:59 IST
   - 09:00 IST
   - 12:00 IST
   - 23:58 IST
   - 23:59 IST
2. Day rollover at 23:59 -> 00:00 IST resets daily counters while preserving historical totals.
3. Month rollover at September 30 -> October 1 rolls over cleanly.
4. No transition to WAITING due solely to clock time in 24x7 mode.
5. Daily pacing controller calculates 24-hour progress accurately in 24x7 mode.
"""
from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from services.daily_pacing_controller import DailyPacingController
from services.salesoorja_operator import SalesoorjaOperator, COUNTER_KEYS, PROVIDER_KEYS

KOLKATA_TZ = ZoneInfo("Asia/Kolkata")


import tempfile

def _make_operator(mock_now: datetime, is_24x7: bool = True) -> SalesoorjaOperator:
    tmp_dir = Path(tempfile.mkdtemp())
    settings = SimpleNamespace(
        SALESOORJA_MODE="PRODUCTION",
        SALESOORJA_24X7=is_24x7,
        SALESOORJA_START_TIME="09:00",
        SALESOORJA_END_TIME="23:59",
        DAILY_SEND_TARGET=150,
        DAILY_SEND_MAX=250,
        MAX_SERPER_CALLS_PER_DAY=1500,
        SALESOORJA_CYCLE_INTERVAL_SECONDS=1,
        SALESOORJA_INBOX_INTERVAL_SECONDS=1,
        SALESOORJA_HEARTBEAT_TIMEOUT_SECONDS=600,
    )
    op = SalesoorjaOperator(
        settings_obj=settings,
        state_path=tmp_dir / "operator_state.json",
        report_dir=tmp_dir / "reports",
        now=lambda: mock_now,
    )
    op._get_redis = lambda: None
    op._state["historical_counters"] = {k: 0 for k in COUNTER_KEYS}
    op._state["historical_provider_usage"] = {k: 0 for k in PROVIDER_KEYS}
    return op


class TestOperator24x7(unittest.TestCase):
    def test_24x7_hourly_eligibility(self):
        """Operator must remain eligible to run at all hours of day in 24x7 mode."""
        test_times = [
            (0, 0),    # 00:00 IST
            (0, 1),    # 00:01 IST
            (2, 0),    # 02:00 IST
            (8, 59),   # 08:59 IST
            (9, 0),    # 09:00 IST
            (12, 0),   # 12:00 IST
            (23, 58),  # 23:58 IST
            (23, 59),  # 23:59 IST
        ]

        for hour, minute in test_times:
            dt_ist = datetime(2026, 9, 17, hour, minute, 0, tzinfo=KOLKATA_TZ)
            dt_utc = dt_ist.astimezone(timezone.utc)
            op = _make_operator(mock_now=dt_utc, is_24x7=True)

            self.assertFalse(
                op._before_start(),
                f"At {hour:02d}:{minute:02d} IST, _before_start should be False in 24x7 mode",
            )
            self.assertFalse(
                op._after_end(),
                f"At {hour:02d}:{minute:02d} IST, _after_end should be False in 24x7 mode",
            )
            self.assertNotEqual(
                op._stop_reason(),
                "END_TIME",
                f"At {hour:02d}:{minute:02d} IST, _stop_reason must not return END_TIME in 24x7 mode",
            )

    def test_legacy_mode_respects_time_window_when_24x7_disabled(self):
        """When 24x7 is explicitly False, operator respects configured window."""
        # 07:30 IST is before 09:00 start
        dt_early = datetime(2026, 9, 17, 7, 30, 0, tzinfo=KOLKATA_TZ).astimezone(timezone.utc)
        op_early = _make_operator(mock_now=dt_early, is_24x7=False)
        self.assertTrue(op_early._before_start())

        # 12:00 IST is within 09:00 - 23:59 window
        dt_mid = datetime(2026, 9, 17, 12, 0, 0, tzinfo=KOLKATA_TZ).astimezone(timezone.utc)
        op_mid = _make_operator(mock_now=dt_mid, is_24x7=False)
        self.assertFalse(op_mid._before_start())
        self.assertFalse(op_mid._after_end())

    def test_midnight_day_rollover(self):
        """Crossing 23:59 into 00:00 IST resets daily counters and advances business_date."""
        # 1. Start operator on day 1 (2026-09-16) at 23:50 IST
        dt_day1 = datetime(2026, 9, 16, 23, 50, 0, tzinfo=KOLKATA_TZ).astimezone(timezone.utc)
        op = _make_operator(mock_now=dt_day1, is_24x7=True)

        # Simulate day 1 activity
        op._state["business_date"] = "2026-09-16"
        op._state["counters"]["emails_sent"] = 42
        op._state["counters"]["qualified_opportunities"] = 15
        op._state["provider_usage"]["Serper"] = 120
        op._state["historical_counters"]["emails_sent"] = 100

        # No rollover yet while still on 2026-09-16
        rolled = op._check_midnight_rollover()
        self.assertFalse(rolled)
        self.assertEqual(op._state["business_date"], "2026-09-16")
        self.assertEqual(op._state["counters"]["emails_sent"], 42)

        # 2. Advance time to day 2 (2026-09-17) at 00:01 IST
        dt_day2 = datetime(2026, 9, 17, 0, 1, 0, tzinfo=KOLKATA_TZ).astimezone(timezone.utc)
        op._now = lambda: dt_day2

        with patch.object(op, "_write_report", return_value=Path("/tmp/dummy.xlsx")), \
             patch.object(op, "_send_final_report_email", return_value={"status": "SENT"}):
            rolled = op._check_midnight_rollover()

        self.assertTrue(rolled)
        # Business date updated to day 2
        self.assertEqual(op._state["business_date"], "2026-09-17")
        # Daily counters reset to 0 for new day
        self.assertEqual(op._state["counters"]["emails_sent"], 0)
        self.assertEqual(op._state["counters"]["qualified_opportunities"], 0)
        self.assertEqual(op._state["provider_usage"]["Serper"], 0)
        # Historical counters preserved and incremented by day 1 total (100 + 42 = 142)
        self.assertEqual(op._state["historical_counters"]["emails_sent"], 142)
        self.assertEqual(op._state["historical_counters"]["qualified_opportunities"], 15)
        self.assertEqual(op._state["historical_provider_usage"]["Serper"], 120)

    def test_month_rollover(self):
        """Crossing month boundary (September 30 -> October 1) rolls over cleanly."""
        dt_sep30 = datetime(2026, 9, 30, 23, 59, 0, tzinfo=KOLKATA_TZ).astimezone(timezone.utc)
        op = _make_operator(mock_now=dt_sep30, is_24x7=True)
        op._state["business_date"] = "2026-09-30"
        op._state["counters"]["emails_sent"] = 55

        # Move to Oct 1
        dt_oct1 = datetime(2026, 10, 1, 0, 0, 30, tzinfo=KOLKATA_TZ).astimezone(timezone.utc)
        op._now = lambda: dt_oct1

        with patch.object(op, "_write_report", return_value=Path("/tmp/dummy.xlsx")), \
             patch.object(op, "_send_final_report_email", return_value={"status": "SENT"}):
            rolled = op._check_midnight_rollover()

        self.assertTrue(rolled)
        self.assertEqual(op._state["business_date"], "2026-10-01")
        self.assertEqual(op._state["counters"]["emails_sent"], 0)
        self.assertEqual(op._state["historical_counters"]["emails_sent"], 55)

    def test_daily_pacing_controller_24x7_progress(self):
        """DailyPacingController computes 24-hour progress accurately when is_24x7=True."""
        pacer = DailyPacingController(min_target=100, stretch_target=150)

        # 00:00 IST -> 0.0%
        dt_0000 = datetime(2026, 9, 17, 0, 0, 0, tzinfo=KOLKATA_TZ)
        prog_0000 = pacer.get_window_progress(dt_0000, is_24x7=True)
        self.assertAlmostEqual(prog_0000, 0.0, places=2)

        # 12:00 IST -> 50.0%
        dt_1200 = datetime(2026, 9, 17, 12, 0, 0, tzinfo=KOLKATA_TZ)
        prog_1200 = pacer.get_window_progress(dt_1200, is_24x7=True)
        self.assertAlmostEqual(prog_1200, 0.5, places=2)

        # 18:00 IST -> 75.0%
        dt_1800 = datetime(2026, 9, 17, 18, 0, 0, tzinfo=KOLKATA_TZ)
        prog_1800 = pacer.get_window_progress(dt_1800, is_24x7=True)
        self.assertAlmostEqual(prog_1800, 0.75, places=2)

        # Pacing telemetry at 12:00 IST with 60 sends:
        # expected_min = 50, expected_stretch = 75
        pacing = pacer.compute_pacing(sent_today=60, send_ready_depth=10, now_dt=dt_1200, is_24x7=True)
        self.assertEqual(pacing["expected_min_by_now"], 50.0)
        self.assertEqual(pacing["expected_stretch_by_now"], 75.0)
        self.assertEqual(pacing["forecast_status"], "ON_TRACK_FOR_100")


if __name__ == "__main__":
    unittest.main()
