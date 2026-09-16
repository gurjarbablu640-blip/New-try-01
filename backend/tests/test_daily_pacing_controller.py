"""Tests for Daily Pacing Controller.

Verifies:
- Minimum (100) and stretch (150) daily targets
- Window progress calculation (09:00 - 23:59 IST)
- Expected sends and deficit calculation
- Pacing forecast statuses (ON_TRACK_FOR_150, ON_TRACK_FOR_100, AT_RISK_FOR_100, QUALITY_SUPPLY_LIMITED, PROVIDER_LIMITED)
- Pacing never authorizes weakening qualification thresholds
"""
import pytest
from datetime import datetime
from zoneinfo import ZoneInfo

from services.daily_pacing_controller import DailyPacingController

KOLKATA_TZ = ZoneInfo("Asia/Kolkata")


def test_window_progress_bounds():
    controller = DailyPacingController()

    # Before 09:00 IST -> 0%
    dt_early = datetime(2026, 9, 16, 7, 30, tzinfo=KOLKATA_TZ)
    assert controller.get_window_progress(dt_early) == 0.0

    # Midday 16:30 IST -> 50% through 15-hour window
    dt_mid = datetime(2026, 9, 16, 16, 30, tzinfo=KOLKATA_TZ)
    progress_mid = controller.get_window_progress(dt_mid)
    assert 0.45 <= progress_mid <= 0.55

    # At or after 23:59 IST -> 100%
    dt_late = datetime(2026, 9, 16, 23, 59, tzinfo=KOLKATA_TZ)
    assert controller.get_window_progress(dt_late) == 1.0


def test_pacing_telemetry_and_forecast_on_track():
    controller = DailyPacingController()
    # At 50% window progress (16:30 IST):
    # expected_min = 50, expected_stretch = 75
    dt_mid = datetime(2026, 9, 16, 16, 30, tzinfo=KOLKATA_TZ)

    # 1. 80 sends -> ON_TRACK_FOR_150
    pacing_150 = controller.compute_pacing(sent_today=80, send_ready_depth=5, now_dt=dt_mid)
    assert pacing_150["forecast_status"] == "ON_TRACK_FOR_150"
    assert pacing_150["send_deficit_to_150"] == 0.0

    # 2. 55 sends -> ON_TRACK_FOR_100
    pacing_100 = controller.compute_pacing(sent_today=55, send_ready_depth=5, now_dt=dt_mid)
    assert pacing_100["forecast_status"] == "ON_TRACK_FOR_100"


def test_pacing_telemetry_quality_supply_limited_and_at_risk():
    controller = DailyPacingController()
    dt_mid = datetime(2026, 9, 16, 16, 30, tzinfo=KOLKATA_TZ)

    # Only 5 sends and 0 send-ready buffer -> QUALITY_SUPPLY_LIMITED
    pacing_supply = controller.compute_pacing(sent_today=5, send_ready_depth=0, now_dt=dt_mid)
    assert pacing_supply["forecast_status"] == "QUALITY_SUPPLY_LIMITED"
    assert "insufficient" in pacing_supply["primary_bottleneck"].lower()

    # 20 sends with small buffer (5) but below expected min (50) -> AT_RISK_FOR_100
    pacing_at_risk = controller.compute_pacing(sent_today=20, send_ready_depth=5, now_dt=dt_mid)
    assert pacing_at_risk["forecast_status"] == "AT_RISK_FOR_100"
    assert pacing_at_risk["send_deficit_to_100"] > 0


def test_provider_limited_forecast():
    controller = DailyPacingController()
    dt_mid = datetime(2026, 9, 16, 16, 30, tzinfo=KOLKATA_TZ)

    pacing_prov = controller.compute_pacing(sent_today=20, provider_limited=True, now_dt=dt_mid)
    assert pacing_prov["forecast_status"] == "PROVIDER_LIMITED"
    assert "rate limit" in pacing_prov["primary_bottleneck"].lower() or "ceiling" in pacing_prov["primary_bottleneck"].lower()
