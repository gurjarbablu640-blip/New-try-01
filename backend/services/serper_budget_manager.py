"""Serper Daily Hard Limit Budget & Telemetry Manager.

Enforces a hard ceiling of 1500 live Serper search API requests per day in production.
Tracks live requests, cache hits, remaining daily budget, and daily reset boundaries.
Cache hits do NOT count against the Serper API quota.
Never exposes or logs API credentials.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

DEFAULT_BUDGET_STATE_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "data", "runtime_state", "serper_budget_state.json")
)
DEFAULT_DAILY_LIMIT = 1500


class SerperBudgetExhaustedError(RuntimeError):
    """Raised when the daily Serper request limit is reached."""


class SerperDailyBudgetManager:
    """Thread-safe persistent daily budget manager for Serper API calls."""

    def __init__(
        self,
        state_path: str = DEFAULT_BUDGET_STATE_PATH,
        daily_limit: Optional[int] = None,
    ) -> None:
        self.state_path = state_path
        self._explicit_limit = daily_limit
        self._lock = threading.Lock()
        self.current_date = self._utc_today_str()
        self.live_requests_today = 0
        self.cache_hits_today = 0
        self.companies_researched = 0
        self.searches_stopped_early = 0
        self.budget_exhausted_events = 0
        self._load()

    def _utc_today_str(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    @property
    def daily_limit(self) -> int:
        if self._explicit_limit is not None:
            return int(self._explicit_limit)
        try:
            from config import settings
            return int(getattr(settings, "SERPER_DAILY_HARD_LIMIT", DEFAULT_DAILY_LIMIT))
        except Exception:
            return int(os.environ.get("SERPER_DAILY_HARD_LIMIT", DEFAULT_DAILY_LIMIT))

    @property
    def remaining_daily_budget(self) -> int:
        self._check_and_reset_if_new_day()
        return max(0, self.daily_limit - self.live_requests_today)

    def _check_and_reset_if_new_day(self) -> bool:
        today = self._utc_today_str()
        if today != self.current_date:
            logger.info("New day detected (%s -> %s). Resetting Serper daily counters.", self.current_date, today)
            self.current_date = today
            self.live_requests_today = 0
            self.cache_hits_today = 0
            self.companies_researched = 0
            self.searches_stopped_early = 0
            self.budget_exhausted_events = 0
            self._save()
            return True
        return False

    def _load(self) -> None:
        if not os.path.exists(self.state_path):
            self._save()
            return
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    saved_date = data.get("date", self._utc_today_str())
                    if saved_date == self._utc_today_str():
                        self.current_date = saved_date
                        self.live_requests_today = int(data.get("live_requests_today", 0))
                        self.cache_hits_today = int(data.get("cache_hits_today", 0))
                        self.companies_researched = int(data.get("companies_researched", 0))
                        self.searches_stopped_early = int(data.get("searches_stopped_early", 0))
                        self.budget_exhausted_events = int(data.get("budget_exhausted_events", 0))
                    else:
                        self.current_date = self._utc_today_str()
                        self.live_requests_today = 0
                        self.cache_hits_today = 0
                        self.companies_researched = 0
                        self.searches_stopped_early = 0
                        self.budget_exhausted_events = 0
                        self._save()
        except Exception as e:
            logger.warning("Could not load Serper budget state from %s: %s", self.state_path, e)
            self._save()

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
        tmp_path = f"{self.state_path}.tmp"
        payload = {
            "date": self.current_date,
            "daily_limit": self.daily_limit,
            "live_requests_today": self.live_requests_today,
            "cache_hits_today": self.cache_hits_today,
            "remaining_daily_budget": max(0, self.daily_limit - self.live_requests_today),
            "companies_researched": self.companies_researched,
            "searches_stopped_early": self.searches_stopped_early,
            "budget_exhausted_events": self.budget_exhausted_events,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        for attempt in range(5):
            try:
                os.replace(tmp_path, self.state_path)
                break
            except PermissionError:
                if attempt == 4:
                    logger.warning("Failed to atomically replace %s", self.state_path)
                time.sleep(0.02)

    def can_request(self) -> bool:
        with self._lock:
            self._check_and_reset_if_new_day()
            return self.live_requests_today < self.daily_limit

    def record_live_request(self, count: int = 1) -> None:
        with self._lock:
            self._check_and_reset_if_new_day()
            if self.live_requests_today + count > self.daily_limit:
                self.budget_exhausted_events += 1
                self._save()
                raise SerperBudgetExhaustedError(
                    f"Serper daily budget exhausted: {self.live_requests_today}/{self.daily_limit} used today. Request blocked."
                )
            self.live_requests_today += count
            self._save()

    def record_cache_hit(self, count: int = 1) -> None:
        """Record cache hit. Does NOT count towards daily live API request limit."""
        with self._lock:
            self._check_and_reset_if_new_day()
            self.cache_hits_today += count
            self._save()

    def record_company_researched(self, count: int = 1) -> None:
        with self._lock:
            self.companies_researched += count
            self._save()

    def record_search_stopped_early(self, count: int = 1) -> None:
        with self._lock:
            self.searches_stopped_early += count
            self._save()

    def record_budget_exhausted(self) -> None:
        with self._lock:
            self.budget_exhausted_events += 1
            self._save()

    def get_telemetry(self) -> Dict[str, Any]:
        with self._lock:
            self._check_and_reset_if_new_day()
            avg_req = (
                round(self.live_requests_today / self.companies_researched, 2)
                if self.companies_researched > 0
                else 0.0
            )
            return {
                "date": self.current_date,
                "daily_limit": self.daily_limit,
                "live_requests_today": self.live_requests_today,
                "cache_hits_today": self.cache_hits_today,
                "remaining_daily_budget": max(0, self.daily_limit - self.live_requests_today),
                "companies_researched": self.companies_researched,
                "searches_stopped_early": self.searches_stopped_early,
                "budget_exhausted_events": self.budget_exhausted_events,
                "average_live_requests_per_company": avg_req,
                "quota_exhausted": self.live_requests_today >= self.daily_limit,
            }

    def reset_counters(self) -> None:
        """Explicit reset for testing and maintenance."""
        with self._lock:
            self.live_requests_today = 0
            self.cache_hits_today = 0
            self.companies_researched = 0
            self.searches_stopped_early = 0
            self.budget_exhausted_events = 0
            self._save()


# Default singleton
serper_budget_manager = SerperDailyBudgetManager()
