"""Serper Daily Hard Limit Budget & Telemetry Manager.

Enforces a hard ceiling of 1500 live Serper search API requests per day in production.
Guarantees atomic multi-process safety across FastAPI, Celery, and research workers.
Configurable reset timezone (default Asia/Kolkata, 00:00:00 to 23:59:59 IST).
Tracks live requests (successful vs failed), cache hits, remaining daily budget, and daily reset boundaries.
Cache hits and pre-blocked requests do NOT count against the Serper API quota.
Failed live network requests DO consume safety budget to protect against runaway API consumption.
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
from zoneinfo import ZoneInfo

from filelock import FileLock

logger = logging.getLogger(__name__)

DEFAULT_BUDGET_STATE_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "data", "runtime_state", "serper_budget_state.json")
)
DEFAULT_DAILY_LIMIT = 1500
DEFAULT_TIMEZONE = "Asia/Kolkata"


class SerperBudgetExhaustedError(RuntimeError):
    """Raised when the daily Serper request limit is reached."""


class SerperDailyBudgetManager:
    """Multi-process safe, persistent daily budget manager for Serper API calls."""

    def __init__(
        self,
        state_path: str = DEFAULT_BUDGET_STATE_PATH,
        daily_limit: Optional[int] = None,
        timezone_str: Optional[str] = None,
        lock_timeout: float = 15.0,
    ) -> None:
        self.state_path = state_path
        self.lock_path = f"{state_path}.lock"
        self._explicit_limit = daily_limit
        self._explicit_timezone = timezone_str
        self._lock_timeout = lock_timeout
        self._thread_lock = threading.Lock()

        os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
        self._file_lock = FileLock(self.lock_path, timeout=self._lock_timeout)

        # In-memory cached state (authoritatively synchronized with disk under lock)
        self.current_date = self._today_str()
        self.live_requests_today = 0
        self.successful_live_requests = 0
        self.failed_live_requests = 0
        self.cache_hits_today = 0
        self.companies_researched = 0
        self.searches_stopped_early = 0
        self.budget_exhausted_events = 0

        # Initial load or creation under cross-process lock
        with self._thread_lock:
            with self._file_lock:
                self._load_unlocked()

    @property
    def timezone_str(self) -> str:
        if self._explicit_timezone is not None:
            return self._explicit_timezone
        try:
            from config import settings
            return str(getattr(settings, "SERPER_BUDGET_TIMEZONE", DEFAULT_TIMEZONE))
        except Exception:
            return os.environ.get("SERPER_BUDGET_TIMEZONE", DEFAULT_TIMEZONE)

    def _get_zoneinfo(self) -> ZoneInfo:
        tz_name = self.timezone_str
        try:
            return ZoneInfo(tz_name)
        except Exception as e:
            logger.warning("Invalid timezone '%s', defaulting to '%s': %s", tz_name, DEFAULT_TIMEZONE, e)
            return ZoneInfo(DEFAULT_TIMEZONE)

    def _today_str(self, dt: Optional[datetime] = None) -> str:
        """Returns the current date string (YYYY-MM-DD) in the configured timezone.

        Default timezone is Asia/Kolkata (00:00:00 to 23:59:59 IST).
        """
        tz = self._get_zoneinfo()
        if dt is None:
            dt_zoned = datetime.now(tz)
        elif dt.tzinfo is None:
            # If naive, treat as UTC and convert to configured timezone
            dt_zoned = dt.replace(tzinfo=timezone.utc).astimezone(tz)
        else:
            dt_zoned = dt.astimezone(tz)
        return dt_zoned.strftime("%Y-%m-%d")

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
        with self._thread_lock:
            with self._file_lock:
                self._load_unlocked()
                self._check_and_reset_if_new_day_unlocked()
                return max(0, self.daily_limit - self.live_requests_today)

    def _check_and_reset_if_new_day_unlocked(self, dt: Optional[datetime] = None) -> bool:
        today = self._today_str(dt)
        if today != self.current_date:
            logger.info(
                "New day detected in timezone %s (%s -> %s). Resetting Serper daily counters.",
                self.timezone_str,
                self.current_date,
                today,
            )
            self.current_date = today
            self.live_requests_today = 0
            self.successful_live_requests = 0
            self.failed_live_requests = 0
            self.cache_hits_today = 0
            self.companies_researched = 0
            self.searches_stopped_early = 0
            self.budget_exhausted_events = 0
            self._save_unlocked()
            return True
        return False

    def check_and_reset_if_new_day(self, dt: Optional[datetime] = None) -> bool:
        with self._thread_lock:
            with self._file_lock:
                self._load_unlocked()
                return self._check_and_reset_if_new_day_unlocked(dt)

    def _check_and_reset_if_new_day(self, dt: Optional[datetime] = None) -> bool:
        return self.check_and_reset_if_new_day(dt)

    def _load_unlocked(self) -> None:
        if not os.path.exists(self.state_path):
            self._save_unlocked()
            return
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    self.current_date = data.get("date", self._today_str())
                    self.live_requests_today = int(data.get("live_requests_today", 0))
                    self.successful_live_requests = int(data.get("successful_live_requests", 0))
                    self.failed_live_requests = int(data.get("failed_live_requests", 0))
                    self.cache_hits_today = int(data.get("cache_hits_today", 0))
                    self.companies_researched = int(data.get("companies_researched", 0))
                    self.searches_stopped_early = int(data.get("searches_stopped_early", 0))
                    self.budget_exhausted_events = int(data.get("budget_exhausted_events", 0))
        except Exception as e:
            logger.warning("Could not load Serper budget state from %s: %s", self.state_path, e)
            self._save_unlocked()

    def _save_unlocked(self) -> None:
        os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
        tmp_path = f"{self.state_path}.tmp"
        tz = self._get_zoneinfo()
        payload = {
            "date": self.current_date,
            "timezone": self.timezone_str,
            "daily_limit": self.daily_limit,
            "live_requests_today": self.live_requests_today,
            "successful_live_requests": self.successful_live_requests,
            "failed_live_requests": self.failed_live_requests,
            "cache_hits_today": self.cache_hits_today,
            "remaining_daily_budget": max(0, self.daily_limit - self.live_requests_today),
            "companies_researched": self.companies_researched,
            "searches_stopped_early": self.searches_stopped_early,
            "budget_exhausted_events": self.budget_exhausted_events,
            "last_updated": datetime.now(tz).isoformat(),
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

    def _save(self) -> None:
        """Synchronized save helper."""
        with self._thread_lock:
            with self._file_lock:
                self._save_unlocked()

    def _load(self) -> None:
        """Synchronized load helper."""
        with self._thread_lock:
            with self._file_lock:
                self._load_unlocked()

    def can_request(self) -> bool:
        """Non-reserving check whether daily quota has room.

        Does NOT consume quota.
        """
        with self._thread_lock:
            with self._file_lock:
                self._load_unlocked()
                self._check_and_reset_if_new_day_unlocked()
                return self.live_requests_today < self.daily_limit

    def reserve_request(self, count: int = 1) -> bool:
        """Atomically check remaining budget and reserve `count` live requests.

        Guarantees that two concurrent workers competing for the final slot
        cannot both succeed.
        Raises SerperBudgetExhaustedError if remaining budget < count.
        """
        with self._thread_lock:
            with self._file_lock:
                self._load_unlocked()
                self._check_and_reset_if_new_day_unlocked()
                if self.live_requests_today + count > self.daily_limit:
                    self.budget_exhausted_events += 1
                    self._save_unlocked()
                    raise SerperBudgetExhaustedError(
                        f"Serper daily budget exhausted: {self.live_requests_today}/{self.daily_limit} used today. Request blocked."
                    )
                self.live_requests_today += count
                self._save_unlocked()
                return True

    def record_live_request(self, count: int = 1) -> None:
        """Alias for reserve_request to maintain full backward compatibility."""
        self.reserve_request(count)

    def record_successful_request(self, count: int = 1) -> None:
        """Record successful live HTTP request completed with status 200.

        Quota was already atomically reserved before sending network request.
        """
        with self._thread_lock:
            with self._file_lock:
                self._load_unlocked()
                self.successful_live_requests += count
                self._save_unlocked()

    def record_failed_request(self, count: int = 1) -> None:
        """Record failed live HTTP request (e.g. 4xx, 5xx, or network timeout/error).

        Quota was already reserved when the network call was sent; this records
        failure telemetry for auditing without refunding or double-counting.
        """
        with self._thread_lock:
            with self._file_lock:
                self._load_unlocked()
                self.failed_live_requests += count
                self._save_unlocked()

    def record_cache_hit(self, count: int = 1) -> None:
        """Record cache hit. Does NOT count towards daily live API request limit."""
        with self._thread_lock:
            with self._file_lock:
                self._load_unlocked()
                self._check_and_reset_if_new_day_unlocked()
                self.cache_hits_today += count
                self._save_unlocked()

    def record_company_researched(self, count: int = 1) -> None:
        with self._thread_lock:
            with self._file_lock:
                self._load_unlocked()
                self.companies_researched += count
                self._save_unlocked()

    def record_search_stopped_early(self, count: int = 1) -> None:
        with self._thread_lock:
            with self._file_lock:
                self._load_unlocked()
                self.searches_stopped_early += count
                self._save_unlocked()

    def record_budget_exhausted(self) -> None:
        with self._thread_lock:
            with self._file_lock:
                self._load_unlocked()
                self.budget_exhausted_events += 1
                self._save_unlocked()

    def get_telemetry(self) -> Dict[str, Any]:
        with self._thread_lock:
            with self._file_lock:
                self._load_unlocked()
                self._check_and_reset_if_new_day_unlocked()
                avg_req = (
                    round(self.live_requests_today / self.companies_researched, 2)
                    if self.companies_researched > 0
                    else 0.0
                )
                return {
                    "date": self.current_date,
                    "timezone": self.timezone_str,
                    "daily_limit": self.daily_limit,
                    "live_requests_today": self.live_requests_today,
                    "successful_live_requests": self.successful_live_requests,
                    "failed_live_requests": self.failed_live_requests,
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
        with self._thread_lock:
            with self._file_lock:
                self.live_requests_today = 0
                self.successful_live_requests = 0
                self.failed_live_requests = 0
                self.cache_hits_today = 0
                self.companies_researched = 0
                self.searches_stopped_early = 0
                self.budget_exhausted_events = 0
                self._save_unlocked()


# Default singleton
serper_budget_manager = SerperDailyBudgetManager()
