"""Daily Pacing Controller for Salesoorja Production Funnel.

Production Operating Window: 09:00 - 23:59 Asia/Kolkata (15 hours = 900 minutes).
Targets:
- MINIMUM_TARGET = 100 qualified initial emails/day (~6.67 sends/hour)
- STRETCH_TARGET = 150 qualified initial emails/day (~10.00 sends/hour)
- HARD_MAX = 250 sends/day

Forecast Statuses:
- ON_TRACK_FOR_150
- ON_TRACK_FOR_100
- AT_RISK_FOR_100
- QUALITY_SUPPLY_LIMITED
- PROVIDER_LIMITED
"""
from __future__ import annotations

import logging
from datetime import datetime, time, timezone
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo
from sqlalchemy import func
from sqlalchemy.orm import Session

from models.campaign import CampaignEvent

logger = logging.getLogger(__name__)

KOLKATA_TZ = ZoneInfo("Asia/Kolkata")

MINIMUM_TARGET = 100
STRETCH_TARGET = 150
HARD_MAX = 250

WINDOW_START_HOUR = 9
WINDOW_START_MINUTE = 0
WINDOW_END_HOUR = 23
WINDOW_END_MINUTE = 59
WINDOW_DURATION_HOURS = 15.0  # 09:00 to 24:00 approx


class DailyPacingController:
    """Controls daily sending pace and computes throughput forecasts."""

    def __init__(
        self,
        min_target: int = MINIMUM_TARGET,
        stretch_target: int = STRETCH_TARGET,
        hard_max: int = HARD_MAX,
    ):
        self.min_target = min_target
        self.stretch_target = stretch_target
        self.hard_max = hard_max

    def get_window_progress(self, now_dt: Optional[datetime] = None, is_24x7: bool = False) -> float:
        """Return fraction of the daily operating window elapsed (0.0 to 1.0).
        
        If is_24x7: 24-hour continuous window (00:00 to 24:00 IST).
        Otherwise: standard 15-hour window (09:00 to 23:59 IST).
        """
        if now_dt is None:
            now_dt = datetime.now(KOLKATA_TZ)
        elif now_dt.tzinfo is None:
            now_dt = now_dt.replace(tzinfo=timezone.utc).astimezone(KOLKATA_TZ)
        else:
            now_dt = now_dt.astimezone(KOLKATA_TZ)

        cur_time = now_dt.time()
        if is_24x7:
            elapsed_seconds = cur_time.hour * 3600 + cur_time.minute * 60 + cur_time.second
            return min(1.0, max(0.0, elapsed_seconds / 86400.0))

        start_time = time(WINDOW_START_HOUR, WINDOW_START_MINUTE)
        end_time = time(WINDOW_END_HOUR, WINDOW_END_MINUTE)

        if cur_time < start_time:
            return 0.0
        if cur_time >= end_time:
            return 1.0

        elapsed_seconds = (
            (cur_time.hour - start_time.hour) * 3600
            + (cur_time.minute - start_time.minute) * 60
            + cur_time.second
        )
        total_window_seconds = WINDOW_DURATION_HOURS * 3600
        return min(1.0, max(0.0, elapsed_seconds / total_window_seconds))

    def compute_pacing(
        self,
        sent_today: int,
        send_ready_depth: int = 0,
        provider_limited: bool = False,
        now_dt: Optional[datetime] = None,
        is_24x7: bool = False,
    ) -> Dict[str, Any]:
        """Compute real-time pacing telemetry and forecast status."""
        progress = self.get_window_progress(now_dt, is_24x7=is_24x7)

        expected_min_by_now = round(self.min_target * progress, 1)
        expected_stretch_by_now = round(self.stretch_target * progress, 1)

        deficit_100 = max(0.0, expected_min_by_now - sent_today)
        deficit_150 = max(0.0, expected_stretch_by_now - sent_today)

        # Determine forecast status
        if provider_limited:
            forecast_status = "PROVIDER_LIMITED"
            bottleneck = "External API rate limit or Serper daily ceiling reached"
        elif sent_today + send_ready_depth >= expected_stretch_by_now:
            forecast_status = "ON_TRACK_FOR_150"
            bottleneck = "None (Pacing healthy)"
        elif sent_today + send_ready_depth >= expected_min_by_now:
            forecast_status = "ON_TRACK_FOR_100"
            bottleneck = "Send-ready buffer supporting minimum target"
        elif send_ready_depth == 0 and sent_today < expected_min_by_now:
            forecast_status = "QUALITY_SUPPLY_LIMITED"
            bottleneck = "Top-of-funnel discovery or qualification gates producing insufficient send-ready supply"
        else:
            forecast_status = "AT_RISK_FOR_100"
            bottleneck = f"Send deficit of {deficit_100:.1f} emails relative to elapsed operating window"

        return {
            "daily_min_target": self.min_target,
            "daily_stretch_target": self.stretch_target,
            "daily_hard_max": self.hard_max,
            "operating_window_progress_pct": round(progress * 100, 1),
            "sent_today": sent_today,
            "expected_min_by_now": expected_min_by_now,
            "expected_stretch_by_now": expected_stretch_by_now,
            "send_deficit_to_100": round(deficit_100, 1),
            "send_deficit_to_150": round(deficit_150, 1),
            "send_ready_depth": send_ready_depth,
            "forecast_status": forecast_status,
            "primary_bottleneck": bottleneck,
        }

    def get_real_sends_today(self, db: Session, business_date: Optional[str] = None) -> int:
        """Count actual non-test, non-simulated outbound emails sent today."""
        if business_date is None:
            business_date = datetime.now(KOLKATA_TZ).strftime("%Y-%m-%d")

        events = (
            db.query(CampaignEvent)
            .filter(CampaignEvent.event_type.in_(["sent", "INITIAL_SENT"]))
            .all()
        )

        real_count = 0
        for e in events:
            dt = getattr(e, "occurred_at", None) or getattr(e, "created_at", None)
            if not dt:
                continue
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc).astimezone(KOLKATA_TZ)
            else:
                dt = dt.astimezone(KOLKATA_TZ)
            if dt.strftime("%Y-%m-%d") != business_date:
                continue
            p = e.payload if isinstance(e.payload, dict) else {}
            if not p.get("simulated") and not p.get("test_mode"):
                real_count += 1
        return real_count


daily_pacing_controller = DailyPacingController()
