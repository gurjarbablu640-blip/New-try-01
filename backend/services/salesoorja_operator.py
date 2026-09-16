"""Resumable one-click orchestration for the existing Salesoorja pipeline."""

from __future__ import annotations

import contextlib
import importlib.util
import json
import logging
import os
import smtplib
import ssl
import threading
import time
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Callable, Mapping, Optional
from zoneinfo import ZoneInfo

from openpyxl import Workbook

from config import settings
from database import SessionLocal
from services.rediff_sender_adapter import DRY_RUN_READY, QUEUED, SENT, RediffSenderAdapter
from services.rediff_transport_bridge import (
    SUPPRESSED_DUPLICATE_TRANSPORT,
    RediffTransportBridge,
)
from services.sales_personalization import SalesPersonalizationPipeline

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    redis = None  # type: ignore
    REDIS_AVAILABLE = False

logger = logging.getLogger(__name__)

REDIS_KEY_OPERATOR_STATE = "salesoorja:operator:state"
REDIS_KEY_OPERATOR_STOP = "salesoorja:operator:stop"
REDIS_KEY_OPERATOR_LOCK = "salesoorja:operator:lock"

COUNTER_KEYS = (
    "companies_researched",
    "qualified_opportunities",
    "people_researched",
    "people_verified",
    "contacts_enriched",
    "emails_sent",
    "followups_sent",
    "replies",
    "enquiries",
    "held",
    "failed",
    "rediff_handoffs",
    "test_emails_sent",
    "production_emails_sent",
    "real_prospect_emails_sent",
    "pages_fetched",
    "pages_fetched_success",
    "followup_searches",
    "opportunities_deep_researched",
    "evidence_complete",
    "evidence_incomplete",
)
PROVIDER_KEYS = (
    "Serper",
    "Apollo Search",
    "Apollo Enrich",
    "Bright Profiles",
    "DeepSeek",
    "Gemini",
    "Rediff",
)
REPORT_SHEETS = (
    "SENT",
    "QUALIFIED_NOT_SENT",
    "HOLD",
    "REPLIES",
    "ENQUIRIES",
    "ERRORS",
)
DISCOVERY_REGIONS = (
    "PAN INDIA",
    "Maharashtra",
    "Gujarat",
    "Tamil Nadu",
    "Karnataka",
    "Haryana",
    "Telangana",
    "Uttar Pradesh",
    "Rajasthan",
)
BACKEND_ROOT = Path(__file__).resolve().parent.parent


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


def _safe_time(raw: str, fallback: str) -> tuple[int, int]:
    try:
        hours, minutes = str(raw).strip().split(":", 1)
        parsed = int(hours), int(minutes)
        if not (0 <= parsed[0] <= 23 and 0 <= parsed[1] <= 59):
            raise ValueError
        return parsed
    except (TypeError, ValueError):
        fallback_hours, fallback_minutes = fallback.split(":", 1)
        return int(fallback_hours), int(fallback_minutes)


class SalesoorjaOperator:
    """Own a single autonomous run while delegating all intelligence decisions."""

    def __init__(
        self,
        *,
        settings_obj: Any = settings,
        state_path: Optional[Path] = None,
        report_dir: Optional[Path] = None,
        now: Callable[[], datetime] = _utc_now,
        db_factory: Any = SessionLocal,
        discovery_fn: Optional[Callable[..., dict[str, Any]]] = None,
        person_pipeline_fn: Optional[Callable[..., dict[str, Any]]] = None,
        personalization_pipeline: Optional[SalesPersonalizationPipeline] = None,
        rediff_adapter: Optional[RediffSenderAdapter] = None,
        imap_poll_fn: Optional[Callable[..., dict[str, Any]]] = None,
        transport_bridge: Optional[RediffTransportBridge] = None,
        redis_client: Optional[Any] = None,
    ) -> None:
        self.settings = settings_obj
        self.state_path = state_path or BACKEND_ROOT / "data" / "runtime_state" / "operator_state.json"
        self.report_dir = report_dir or BACKEND_ROOT / "data" / "daily_reports"
        self._now = now
        self._db_factory = db_factory
        self._discovery_fn = discovery_fn
        self._person_pipeline_fn = person_pipeline_fn
        self._personalization = personalization_pipeline or SalesPersonalizationPipeline()
        self._rediff = rediff_adapter or RediffSenderAdapter()
        self._imap_poll_fn = imap_poll_fn
        self._transport_bridge = transport_bridge or RediffTransportBridge()
        self._redis = redis_client
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._stop_signal_path = (state_path or BACKEND_ROOT / "data" / "runtime_state" / "operator_state.json").parent / "operator_stop.signal"
        self._thread: Optional[threading.Thread] = None
        self._state = self._load_state()

    def _get_redis(self) -> Optional[Any]:
        """Return connected Redis client for authoritative live operator state."""
        if self._redis is not None:
            return self._redis
        if not REDIS_AVAILABLE:
            return None
        try:
            url = str(
                getattr(self.settings, "REDIS_URL", None)
                or getattr(self.settings, "CELERY_BROKER_URL", None)
                or "redis://localhost:6379/0"
            )
            client = redis.Redis.from_url(url, decode_responses=True, socket_timeout=1.5)
            client.ping()
            self._redis = client
            return self._redis
        except Exception as exc:
            logger.debug("Redis connection unavailable for operator: %s", exc)
            return None

    def _mode(self) -> str:
        return str(getattr(self.settings, "SALESOORJA_MODE", "TEST") or "TEST").strip().upper()

    def _normalize_state(self, loaded: dict[str, Any]) -> dict[str, Any]:
        """Ensure all required counters, provider usage, and lifecycle keys are present."""
        loaded.setdefault("counters", {key: 0 for key in COUNTER_KEYS})
        loaded.setdefault("historical_counters", {key: 0 for key in COUNTER_KEYS})
        loaded.setdefault("provider_usage", {key: 0 for key in PROVIDER_KEYS})
        loaded.setdefault("historical_provider_usage", {key: 0 for key in PROVIDER_KEYS})
        loaded.setdefault("processed_accounts", [])
        loaded.setdefault("discovery_region_index", 0)
        loaded.setdefault("records", {sheet: [] for sheet in REPORT_SHEETS})
        loaded.setdefault("transport_receipts", [])
        for k in ("task_id", "queued_at", "worker_started_at", "heartbeat_at", "stop_requested_at", "stopped_at"):
            loaded.setdefault(k, None)
        for key in COUNTER_KEYS:
            loaded["counters"].setdefault(key, 0)
            loaded["historical_counters"].setdefault(key, 0)
        for key in PROVIDER_KEYS:
            loaded["provider_usage"].setdefault(key, 0)
            loaded["historical_provider_usage"].setdefault(key, 0)
        for sheet in REPORT_SHEETS:
            loaded["records"].setdefault(sheet, [])
        return loaded

    def _new_state(self, *, preserve_history: bool = False) -> dict[str, Any]:
        now = self._now()
        previous = self._state if preserve_history else {}
        previous_day = str(previous.get("business_date") or "")
        business_date = now.astimezone(ZoneInfo("Asia/Kolkata")).date().isoformat()
        same_day = preserve_history and previous_day == business_date

        # Preserve cumulative historical totals separately
        historical_counters = deepcopy(previous.get("historical_counters") or {key: 0 for key in COUNTER_KEYS})
        if same_day and previous.get("counters"):
            for key, val in previous["counters"].items():
                historical_counters[key] = int(historical_counters.get(key, 0)) + int(val)

        historical_provider_usage = deepcopy(previous.get("historical_provider_usage") or {key: 0 for key in PROVIDER_KEYS})
        if same_day and previous.get("provider_usage"):
            for key, val in previous["provider_usage"].items():
                historical_provider_usage[key] = int(historical_provider_usage.get(key, 0)) + int(val)

        return {
            "version": 2,
            "run_id": f"operator-{uuid.uuid4().hex[:12]}",
            "business_date": business_date,
            "mode": self._mode(),
            "status": "STOPPED",
            "task_id": None,
            "queued_at": None,
            "worker_started_at": None,
            "heartbeat_at": None,
            "stop_requested_at": None,
            "stopped_at": None,
            "started_at": None,
            "ended_at": None,
            "last_checkpoint": None,
            "current_company": None,
            "last_action": "Ready",
            "last_error": None,
            "stop_reason": None,
            "report_path": None,
            "final_report_email": None,
            "counters": {key: 0 for key in COUNTER_KEYS},  # CURRENT RUN COUNTERS ALWAYS RESET
            "historical_counters": historical_counters,
            "provider_usage": {key: 0 for key in PROVIDER_KEYS},  # CURRENT RUN PROVIDER USAGE RESET
            "historical_provider_usage": historical_provider_usage,
            "processed_accounts": [],
            "discovery_region_index": previous.get("discovery_region_index", 0) if preserve_history else 0,
            "records": {sheet: [] for sheet in REPORT_SHEETS},
            "transport_receipts": deepcopy(previous.get("transport_receipts")) if same_day else [],
        }

    def _load_state(self) -> dict[str, Any]:
        # 1. Authoritative check from Redis
        r = self._get_redis()
        if r is not None:
            try:
                raw = r.get(REDIS_KEY_OPERATOR_STATE)
                if raw:
                    loaded = json.loads(raw)
                    if isinstance(loaded, dict):
                        self._normalize_state(loaded)
                        if loaded.get("status") in {"RUNNING", "STOPPING", "WAITING", "STARTING", "QUEUED"}:
                            loaded["status"] = "STOPPED"
                            loaded["last_action"] = "Recovered interrupted run; safe to resume"
                            loaded["stopped_at"] = _iso(self._now())
                        return loaded
            except Exception as exc:
                logger.debug("Redis state load fallback: %s", exc)

        # 2. Check disk snapshot fallback
        if self.state_path.is_file():
            try:
                loaded = json.loads(self.state_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    self._normalize_state(loaded)
                    if loaded.get("status") in {"RUNNING", "STOPPING", "WAITING", "STARTING", "QUEUED"}:
                        loaded["status"] = "STOPPED"
                        loaded["last_action"] = "Recovered interrupted run; safe to resume"
                        loaded["stopped_at"] = _iso(self._now())
                    return loaded
            except (OSError, ValueError, TypeError):
                logger.warning("Operator state could not be loaded from disk; starting clean")
        self._state = {}
        return self._new_state()

    def _save_state(self) -> None:
        """Persist state to Redis (authoritative) and write optional disk snapshot (non-fatal)."""
        payload = json.dumps(self._state, indent=2, default=str)
        # 1. Authoritative cross-process state saved to Redis
        r = self._get_redis()
        if r is not None:
            try:
                r.set(REDIS_KEY_OPERATOR_STATE, payload)
            except Exception as exc:
                logger.warning("Failed to save operator state to Redis: %s", exc)

        # 2. Optional disk snapshot / history (failure must NEVER crash operator)
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            self.state_path.write_text(payload, encoding="utf-8")
        except Exception as exc:
            logger.debug("Failed to write operator state disk snapshot (non-fatal): %s", exc)

    def _sync_state(self) -> None:
        """Reload shared state from Redis (authoritative) or disk snapshot (fallback)."""
        r = self._get_redis()
        if r is not None:
            try:
                raw = r.get(REDIS_KEY_OPERATOR_STATE)
                if raw:
                    loaded = json.loads(raw)
                    if isinstance(loaded, dict):
                        self._normalize_state(loaded)
                        with self._lock:
                            self._state = loaded
                        return
            except Exception as exc:
                logger.debug("Could not sync operator state from Redis: %s", exc)

        if self.state_path.is_file():
            try:
                loaded = json.loads(self.state_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    self._normalize_state(loaded)
                    with self._lock:
                        self._state = loaded
            except Exception as exc:
                logger.debug("Could not sync operator state from disk: %s", exc)

    def _set_stop_signal(self) -> None:
        self._stop_event.set()
        r = self._get_redis()
        if r is not None:
            try:
                r.set(REDIS_KEY_OPERATOR_STOP, _iso(self._now()))
            except Exception as exc:
                logger.warning("Could not set Redis stop signal: %s", exc)
        try:
            self._stop_signal_path.parent.mkdir(parents=True, exist_ok=True)
            self._stop_signal_path.write_text(
                json.dumps({"stop_requested_at": _iso(self._now()), "pid": os.getpid()}),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _clear_stop_signal(self) -> None:
        self._stop_event.clear()
        r = self._get_redis()
        if r is not None:
            try:
                r.delete(REDIS_KEY_OPERATOR_STOP)
            except Exception:
                pass
        try:
            if self._stop_signal_path.exists():
                self._stop_signal_path.unlink()
        except Exception:
            pass

    def _is_stop_requested(self) -> bool:
        if self._stop_event.is_set():
            return True
        r = self._get_redis()
        if r is not None:
            try:
                if r.get(REDIS_KEY_OPERATOR_STOP):
                    return True
            except Exception:
                pass
        status = self._state.get("status")
        if status == "STOPPING" or self._state.get("stop_requested_at"):
            return True
        try:
            if self._stop_signal_path.exists():
                return True
        except Exception:
            pass
        return False

    def _heartbeat(self, action: Optional[str] = None) -> None:
        now_iso = _iso(self._now())
        with self._lock:
            self._state["heartbeat_at"] = now_iso
            self._state["last_checkpoint"] = now_iso
            if action:
                self._state["last_action"] = action
            self._save_state()

    def _heartbeat_timeout_seconds(self) -> float:
        configured = getattr(self.settings, "SALESOORJA_HEARTBEAT_TIMEOUT_SECONDS", None)
        if configured is not None:
            return float(configured)
        return 180.0 if self._mode() == "PRODUCTION" else 45.0

    def _is_worker_alive(self) -> bool:
        """Check whether the active execution worker/task is genuinely alive."""
        if self._thread is not None:
            return self._thread.is_alive() and self._thread is not threading.current_thread()

        task_id = self._state.get("task_id")
        if not task_id:
            # Active in-memory state without thread/task (e.g. test lock or waiting)
            return self._state.get("status") in {"QUEUED", "STARTING", "RUNNING", "WAITING", "STOPPING"}

        if str(task_id).startswith("thread-") or str(task_id).startswith("sync-"):
            return bool(self._thread and self._thread.is_alive())

        # Check Celery task status if applicable
        try:
            from celery_app import CELERY_AVAILABLE, celery_app
            if CELERY_AVAILABLE:
                from celery.result import AsyncResult
                res = AsyncResult(task_id, app=celery_app)
                if res.state in {"FAILURE", "REVOKED"}:
                    return False
        except Exception as exc:
            logger.debug("Celery task status check error: %s", exc)

        # Check heartbeat or queue recency
        now = self._now()
        heartbeat_iso = self._state.get("heartbeat_at")
        queued_iso = self._state.get("queued_at")
        stop_req_iso = self._state.get("stop_requested_at")

        if self._state.get("status") == "STOPPING" and stop_req_iso:
            try:
                if (now - datetime.fromisoformat(stop_req_iso)).total_seconds() > 15.0:
                    return False
            except Exception:
                pass

        if heartbeat_iso:
            try:
                hb_time = datetime.fromisoformat(heartbeat_iso)
                return (now - hb_time).total_seconds() < self._heartbeat_timeout_seconds()
            except Exception:
                return False
        elif queued_iso:
            try:
                q_time = datetime.fromisoformat(queued_iso)
                return (now - q_time).total_seconds() < 30.0
            except Exception:
                return False

        return self._state.get("status") in {"QUEUED", "STARTING", "RUNNING", "WAITING", "STOPPING"}

    def _force_stopped(self, reason: str = "STOP_TIMEOUT") -> None:
        now_iso = _iso(self._now())
        self._clear_stop_signal()
        r = self._get_redis()
        if r is not None:
            try:
                r.delete(REDIS_KEY_OPERATOR_LOCK)
            except Exception:
                pass
        task_id = self._state.get("task_id")
        if task_id and not str(task_id).startswith("thread-") and not str(task_id).startswith("sync-"):
            try:
                from celery_app import CELERY_AVAILABLE, celery_app
                if CELERY_AVAILABLE:
                    celery_app.control.revoke(task_id, terminate=True)
            except Exception as exc:
                logger.debug("Failed to revoke celery task %s: %s", task_id, exc)
        with self._lock:
            self._state.update(
                status="STOPPED",
                stopped_at=now_iso,
                ended_at=now_iso,
                stop_reason=reason,
                last_action=f"Operator stopped ({reason})",
            )
            self._save_state()

    def _force_error(self, reason: str, message: str) -> None:
        now_iso = _iso(self._now())
        self._clear_stop_signal()
        r = self._get_redis()
        if r is not None:
            try:
                r.delete(REDIS_KEY_OPERATOR_LOCK)
            except Exception:
                pass
        with self._lock:
            self._state.update(
                status="ERROR",
                last_error=message,
                stopped_at=now_iso,
                ended_at=now_iso,
                stop_reason=reason,
                last_action=f"Error: {message}",
            )
            self._save_state()

    def _reconcile_runtime_state(self) -> None:
        """Heal stale state, enforce bounded timeouts, and prevent stuck STOPPING states."""
        status = self._state.get("status")
        if status not in {"QUEUED", "STARTING", "RUNNING", "WAITING", "STOPPING"}:
            return

        now = self._now()

        # 1. Bounded stop timeout: never remain STOPPING forever
        if status == "STOPPING":
            stop_requested_at = self._state.get("stop_requested_at")
            if not stop_requested_at:
                with self._lock:
                    self._state["stop_requested_at"] = _iso(now)
                    self._save_state()
                return
            try:
                elapsed = max(0.0, (now - datetime.fromisoformat(stop_requested_at)).total_seconds())
            except (TypeError, ValueError):
                with self._lock:
                    self._state["stop_requested_at"] = _iso(now)
                    self._save_state()
                logger.warning("Reconciliation: repaired invalid STOPPING timestamp")
                return
            if elapsed > 15.0:
                logger.warning("Reconciliation: STOPPING exceeded 15s timeout (%.1fs); forcing STOPPED", elapsed)
                self._force_stopped(reason="STOP_TIMEOUT")
            return

        # 2. Heartbeat stale check for RUNNING/STARTING
        if status in {"STARTING", "RUNNING", "WAITING"}:
            heartbeat_at = self._state.get("heartbeat_at")
            if heartbeat_at:
                try:
                    hb_time = datetime.fromisoformat(heartbeat_at)
                    elapsed_hb = (now - hb_time).total_seconds()
                    hb_timeout = self._heartbeat_timeout_seconds()
                    if elapsed_hb > hb_timeout and not self._is_worker_alive():
                        logger.warning("Reconciliation: Heartbeat stale (%.1fs) and worker dead; setting ERROR", elapsed_hb)
                        self._force_error(reason="HEARTBEAT_TIMEOUT", message=f"Worker heartbeat timed out after {int(hb_timeout)}s")
                        return
                except Exception:
                    pass
            elif not self._is_worker_alive():
                self._force_stopped(reason="NO_LIVE_WORKER")
                return

        # 3. Queue timeout for QUEUED
        if status == "QUEUED":
            queued_at = self._state.get("queued_at")
            if queued_at:
                try:
                    q_time = datetime.fromisoformat(queued_at)
                    if (now - q_time).total_seconds() > 30.0 and not self._is_worker_alive():
                        logger.warning("Reconciliation: Task stayed in QUEUED > 30s without worker pickup; setting ERROR")
                        self._force_error(reason="QUEUE_TIMEOUT", message="Worker did not accept queued task within 30s")
                        return
                except Exception:
                    pass

    def _update(self, **values: Any) -> None:
        with self._lock:
            self._state.update(values)
            now_iso = _iso(self._now())
            self._state["last_checkpoint"] = now_iso
            if "heartbeat_at" not in values and self._state.get("status") in {"STARTING", "RUNNING"}:
                self._state["heartbeat_at"] = now_iso
            self._save_state()

    def _increment(self, counter: str, amount: int = 1) -> None:
        with self._lock:
            self._state["counters"][counter] = int(self._state["counters"].get(counter, 0)) + amount
            self._state["last_checkpoint"] = _iso(self._now())
            self._save_state()

    def _provider_call(self, provider: str, amount: int = 1) -> None:
        with self._lock:
            self._state["provider_usage"][provider] = int(self._state["provider_usage"].get(provider, 0)) + amount
            self._save_state()

    def _append_record(self, sheet: str, row: Mapping[str, Any]) -> None:
        with self._lock:
            self._state["records"][sheet].append(dict(row))
            self._save_state()

    def _production_errors(self) -> list[str]:
        if self._mode() != "PRODUCTION":
            return []
        daily_target = int(getattr(self.settings, "DAILY_SEND_TARGET", 150))
        daily_max = int(getattr(self.settings, "DAILY_SEND_MAX", 250))
        llm_configured = bool(
            str(getattr(self.settings, "HIVE_API_KEY", "") or "").strip()
            or str(getattr(self.settings, "GEMINI_API_KEY", "") or "").strip()
            or str(getattr(self.settings, "GOOGLE_API_KEY", "") or "").strip()
        )
        checks = {
            "REAL_OUTREACH_ENABLED=true": bool(getattr(self.settings, "REAL_OUTREACH_ENABLED", False)),
            "OUTBOUND_TEST_MODE=false": not bool(getattr(self.settings, "OUTBOUND_TEST_MODE", True)),
            "REDIFF_SENDER_ENABLED=true": bool(getattr(self.settings, "REDIFF_SENDER_ENABLED", False)),
            "REDIFF_TEST_MODE=false": not bool(getattr(self.settings, "REDIFF_TEST_MODE", True)),
            "SERPER_API_KEY configured": bool(str(getattr(self.settings, "SERPER_API_KEY", "") or "").strip()),
            "APOLLO_API_KEY configured": bool(str(getattr(self.settings, "APOLLO_API_KEY", "") or "").strip()),
            "BRIGHTDATA_API_TOKEN configured": bool(str(getattr(self.settings, "BRIGHTDATA_API_TOKEN", "") or "").strip()),
            "Bright Data profile dataset configured": bool(str(getattr(self.settings, "BRIGHTDATA_LINKEDIN_PROFILE_DATASET_ID", "") or "").strip()),
            "DeepSeek or Gemini configured": llm_configured,
            "Rediff system available": self._rediff.system_available(),
            "DAILY_SEND_TARGET is positive": daily_target > 0,
            "DAILY_SEND_MAX is at least target": daily_max >= daily_target,
        }
        return [name for name, passed in checks.items() if not passed]

    def start_run(self, *, background: bool = True, use_celery: Optional[bool] = None) -> dict[str, Any]:
        self._sync_state()
        self._reconcile_runtime_state()
        with self._lock:
            active = self._state.get("status") in {"QUEUED", "STARTING", "RUNNING", "WAITING", "STOPPING"}
            r = self._get_redis()
            if r is not None:
                try:
                    if r.get(REDIS_KEY_OPERATOR_LOCK) and active and self._is_worker_alive():
                        return {"started": False, "reason": "ALREADY_RUNNING", "status": self.get_status()}
                except Exception:
                    pass
            if active:
                if self._is_worker_alive():
                    return {"started": False, "reason": "ALREADY_RUNNING", "status": self.get_status()}
                # Worker is not alive; heal stale state and proceed
                logger.warning("Previous active status %s had no live worker; clearing stale state", self._state.get("status"))
                self._force_stopped(reason="CLEARED_STALE_RUN")

            mode = self._mode()
            if mode not in {"SMOKE", "TEST", "PRODUCTION"}:
                return {
                    "started": False,
                    "reason": "INVALID_MODE",
                    "errors": ["SALESOORJA_MODE must be SMOKE, TEST, or PRODUCTION"],
                }

            if mode == "PRODUCTION":
                prod_errors = self._production_errors()
                if prod_errors:
                    return {
                        "started": False,
                        "reason": "PRODUCTION_GUARD_FAILED",
                        "errors": prod_errors,
                    }

            now = self._now()
            now_iso = _iso(now)
            self._state = self._new_state(preserve_history=True)
            self._clear_stop_signal()

            # START state starts at QUEUED! Broker acceptance alone must not set RUNNING.
            self._state.update(
                status="QUEUED",
                mode=mode,
                queued_at=now_iso,
                started_at=now_iso,
                ended_at=None,
                stop_reason=None,
                last_error=None,
                last_action="Operator queued in worker",
            )
            self._save_state()

            if background:
                celery_dispatched = False
                allow_celery = use_celery if use_celery is not None else getattr(self.settings, "USE_CELERY", getattr(self.settings, "CELERY_ENABLED", False))
                if allow_celery:
                    try:
                        from celery_app import CELERY_AVAILABLE, celery_app
                        if CELERY_AVAILABLE:
                            async_result = celery_app.send_task("salesoorja.operator_run")
                            task_id = str(async_result.id)
                            self._state["task_id"] = task_id
                            self._state["last_action"] = f"Queued Celery task {task_id}"
                            self._save_state()
                            celery_dispatched = True
                    except Exception as exc:
                        logger.warning("Celery dispatch unavailable: %s; falling back to daemon thread", exc)

                if not celery_dispatched:
                    task_id = f"thread-{uuid.uuid4().hex[:10]}"
                    self._state["task_id"] = task_id
                    self._save_state()
                    self._thread = threading.Thread(
                        target=self.execute_worker_run,
                        args=(task_id,),
                        name="salesoorja-operator",
                        daemon=True,
                    )
                    self._thread.start()
            else:
                task_id = f"sync-{uuid.uuid4().hex[:10]}"
                self.execute_worker_run(task_id=task_id)

            # Set authoritative Redis run lock for active task
            r = self._get_redis()
            if r is not None and self._state.get("task_id"):
                try:
                    r.set(REDIS_KEY_OPERATOR_LOCK, str(self._state["task_id"]), ex=86400)
                except Exception:
                    pass

        return {"started": True, "status": self._status_payload()}

    def execute_worker_run(self, task_id: Optional[str] = None) -> dict[str, Any]:
        """Dedicated execution entrypoint for Celery worker or worker thread."""
        task_id = str(task_id or f"worker-{uuid.uuid4().hex[:10]}")
        logger.info("Salesoorja operator execute_worker_run started: task_id=%s", task_id)
        self._sync_state()

        # Check if stop was requested while in QUEUED state
        if self._is_stop_requested():
            logger.info("Stop requested before worker execution for task %s", task_id)
            self._clear_stop_signal()
            now_iso = _iso(self._now())
            with self._lock:
                self._state.update(
                    task_id=task_id,
                    status="STOPPED",
                    stopped_at=now_iso,
                    ended_at=now_iso,
                    stop_reason="STOPPED_WHILE_QUEUED",
                    last_action="Run cancelled while queued",
                )
                self._save_state()
            return self.get_status()

        # Transition to STARTING
        now_iso = _iso(self._now())
        with self._lock:
            self._state.update(
                task_id=task_id,
                status="STARTING",
                worker_started_at=now_iso,
                heartbeat_at=now_iso,
                last_checkpoint=now_iso,
                last_action="Worker started; validating runtime environment",
            )
            self._save_state()

        if self._is_stop_requested():
            self.finalize_run(reason="MANUAL_STOP")
            return self.get_status()

        # Send heartbeat acknowledgement and allow STARTING state visibility
        time.sleep(1.0)
        if self._is_stop_requested():
            self.finalize_run(reason="MANUAL_STOP")
            return self.get_status()

        # Transition to RUNNING strictly after worker heartbeat acknowledgement
        now_iso = _iso(self._now())
        with self._lock:
            self._state.update(
                status="RUNNING",
                heartbeat_at=now_iso,
                last_checkpoint=now_iso,
                last_action="Operator running",
            )
            self._save_state()

        try:
            self._run_safely()
        except Exception as exc:
            logger.exception("Salesoorja operator worker run encountered fatal error: %s", exc)
            now_iso = _iso(self._now())
            with self._lock:
                self._state.update(
                    status="ERROR",
                    last_error=f"{type(exc).__name__}: {exc}",
                    stopped_at=now_iso,
                    ended_at=now_iso,
                    stop_reason="FATAL_ERROR",
                )
                self._save_state()
        finally:
            self._clear_stop_signal()

        return self.get_status()

    def stop_run(self, *, wait: bool = False, timeout: float = 15.0) -> dict[str, Any]:
        self._sync_state()
        now = self._now()
        now_iso = _iso(now)

        status = self._state.get("status")
        active = status in {"QUEUED", "STARTING", "RUNNING", "WAITING", "STOPPING"}
        if not active:
            self._clear_stop_signal()
            return {"stopped": False, "reason": "NOT_RUNNING", "status": self.get_status()}

        worker_alive = self._is_worker_alive()
        if not worker_alive:
            # If no live worker/task exists, immediately clean stale state, release run lock, and transition to STOPPED.
            logger.info("stop_run: No live worker found for active status %s; immediately cleaning stale state", status)
            self._clear_stop_signal()
            with self._lock:
                self._state.update(
                    status="STOPPED",
                    stopped_at=now_iso,
                    ended_at=now_iso,
                    stop_reason="NO_LIVE_WORKER",
                    last_action="Cleaned stale run; no live worker active",
                )
                self._save_state()
            return {"stopped": True, "status": self.get_status()}

        # Live worker exists: set stop_requested and wait for acknowledgement
        self._set_stop_signal()
        with self._lock:
            self._state.update(
                status="STOPPING",
                stop_requested_at=self._state.get("stop_requested_at") or now_iso,
                last_action="Stop requested; finishing safe in-progress work",
            )
            self._save_state()

        # Bounded stop wait
        if wait:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                self._sync_state()
                if self._state.get("status") in {"STOPPED", "ERROR"}:
                    break
                if self._thread and not self._thread.is_alive():
                    break
                time.sleep(0.1)

            self._sync_state()
            if self._state.get("status") not in {"STOPPED", "ERROR"}:
                logger.warning("Stop did not complete within bounded timeout %.1fs; forcing STOPPED", timeout)
                self._force_stopped(reason="STOP_TIMEOUT")

        return {"stopped": True, "status": self._status_payload()}

    def get_status(self) -> dict[str, Any]:
        self._sync_state()
        self._reconcile_runtime_state()
        return self._status_payload()

    def _status_payload(self) -> dict[str, Any]:
        with self._lock:
            state = deepcopy(self._state)
        state.pop("records", None)
        receipts = state.pop("transport_receipts", [])
        state["transport_receipt_count"] = len(receipts)
        state["last_transport_receipt"] = receipts[-1] if receipts else None
        state["daily_send_target"] = int(getattr(self.settings, "DAILY_SEND_TARGET", 150))
        state["daily_send_max"] = int(getattr(self.settings, "DAILY_SEND_MAX", 250))
        is_24x7 = self._is_24x7()
        state["production_24x7"] = is_24x7
        state["start_time"] = "00:00" if is_24x7 else str(getattr(self.settings, "SALESOORJA_START_TIME", "09:00"))
        state["end_time"] = "23:59" if is_24x7 else str(getattr(self.settings, "SALESOORJA_END_TIME", "23:59"))
        state["production_guard_errors"] = self._production_errors()

        # Throughput & Pacing Telemetry
        try:
            from services.daily_pacing_controller import daily_pacing_controller
            from services.funnel_workflow_manager import funnel_workflow_manager

            db = self._db_factory() if self._db_factory else None
            real_sends_today = 0
            queue_depths = {}
            send_ready_depth = 0
            if db is not None:
                try:
                    real_sends_today = daily_pacing_controller.get_real_sends_today(db, business_date=state.get("business_date"))
                    queue_depths = funnel_workflow_manager.get_stage_depths(db)
                    send_ready_depth = queue_depths.get("SEND_READY", 0)
                finally:
                    db.close()

            serper_calls = int((state.get("provider_usage") or {}).get("Serper", 0))
            pacing = daily_pacing_controller.compute_pacing(
                sent_today=real_sends_today,
                send_ready_depth=send_ready_depth,
                provider_limited=bool(serper_calls >= 1500),
                is_24x7=is_24x7,
            )
            state["daily_min_target"] = pacing["daily_min_target"]
            state["daily_stretch_target"] = pacing["daily_stretch_target"]
            state["sent_today"] = real_sends_today
            state["expected_min_by_now"] = pacing["expected_min_by_now"]
            state["expected_stretch_by_now"] = pacing["expected_stretch_by_now"]
            state["send_deficit_to_100"] = pacing["send_deficit_to_100"]
            state["send_deficit_to_150"] = pacing["send_deficit_to_150"]
            state["send_ready_depth"] = send_ready_depth
            state["queue_depths"] = queue_depths
            state["forecast_status"] = pacing["forecast_status"]
            state["primary_bottleneck"] = pacing["primary_bottleneck"]
            state["pacing"] = pacing
        except Exception as p_err:
            logger.debug("Could not compute pacing for status payload: %s", p_err)

        # Evidence Deep-Dive & Research Depth Telemetry
        try:
            pages_fetched_today = 0
            pages_success_today = 0
            db = self._db_factory() if self._db_factory else None
            if db is not None:
                try:
                    from models.research_evidence import ResearchEvidenceRecord
                    from sqlalchemy import func
                    b_date_str = state.get("business_date")
                    if b_date_str:
                        start_of_day = datetime.fromisoformat(b_date_str).replace(tzinfo=timezone.utc)
                    else:
                        start_of_day = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
                    pages_fetched_today = db.query(func.count(ResearchEvidenceRecord.id)).filter(
                        ResearchEvidenceRecord.retrieved_at >= start_of_day
                    ).scalar() or 0
                    pages_success_today = db.query(func.count(ResearchEvidenceRecord.id)).filter(
                        ResearchEvidenceRecord.retrieved_at >= start_of_day,
                        ResearchEvidenceRecord.fetch_status == "FETCH_SUCCESS",
                    ).scalar() or 0
                finally:
                    db.close()

            cnt = state.get("counters") or {}
            c_fetched = cnt.get("pages_fetched", 0)
            c_success = cnt.get("pages_fetched_success", 0)
            pages_fetched_today = max(pages_fetched_today, c_fetched)
            pages_success_today = max(pages_success_today, c_success)

            rate = (pages_success_today / pages_fetched_today * 100.0) if pages_fetched_today > 0 else 0.0
            state["pages_fetched_today"] = pages_fetched_today
            state["pages_fetched_success_today"] = pages_success_today
            state["page_fetch_success_rate"] = round(rate, 1)
            state["opportunities_deep_researched"] = cnt.get("opportunities_deep_researched", 0)
            state["followup_searches_today"] = cnt.get("followup_searches", 0)
            state["evidence_complete_count"] = cnt.get("evidence_complete", 0)
            state["evidence_incomplete_count"] = cnt.get("evidence_incomplete", 0)
            state["current_research_stage"] = state.get("current_research_stage") or "Idle"

            # Cost control metrics
            qual_opps = max(1, cnt.get("qualified_opportunities", 0))
            serper_calls = int((state.get("provider_usage") or {}).get("Serper", 0))
            state["searches_per_qualified_opportunity"] = round(serper_calls / qual_opps, 2)
            state["pages_read_per_qualified_opportunity"] = round(pages_success_today / qual_opps, 2)
            state["followups_per_qualified_opportunity"] = round(cnt.get("followup_searches", 0) / qual_opps, 2)
        except Exception as r_err:
            logger.debug("Could not compute research telemetry for status payload: %s", r_err)

        return state

    def get_transport_receipts(self) -> list[dict[str, Any]]:
        with self._lock:
            return deepcopy(self._state.get("transport_receipts") or [])

    def record_single_live_transport(self, receipt: Mapping[str, Any], *, quality_score: float) -> None:
        if receipt.get("test_type") != "SINGLE_LIVE_CUSTOMER_TEST":
            raise ValueError("INVALID_SINGLE_LIVE_RECEIPT")
        with self._lock:
            receipt_id = receipt.get("receipt_id")
            if receipt_id and any(item.get("receipt_id") == receipt_id for item in self._state["transport_receipts"]):
                return
            self._state["transport_receipts"].append(dict(receipt))
            if receipt.get("transport_status") == "SENT" and receipt.get("smtp_sent") is True:
                self._state["counters"]["emails_sent"] += 1
                self._state["counters"]["production_emails_sent"] += 1
                self._state["counters"]["real_prospect_emails_sent"] += 1
                self._state["records"]["SENT"].append({
                    "company": receipt.get("company_reference"),
                    "person": receipt.get("person_reference"),
                    "recipient": receipt.get("recipient"),
                    "cc": receipt.get("cc"),
                    "quality_score": quality_score,
                    "transport_status": "SENT",
                    "test_type": "SINGLE_LIVE_CUSTOMER_TEST",
                    "touch": "INITIAL",
                })
            elif receipt.get("transport_status") == "FAILED":
                self._state["counters"]["failed"] += 1
            self._state["last_checkpoint"] = _iso(self._now())
            self._state["last_action"] = f"Single live customer test: {receipt.get('transport_status')}"
            self._save_state()

    def execute_controlled_transport_test(self, *, authorization: str, dispatch: bool = True) -> dict[str, Any]:
        if self._mode() != "TEST":
            raise PermissionError("CONTROLLED_TRANSPORT_REQUIRES_TEST_MODE")
        with self._lock:
            if self._thread and self._thread.is_alive():
                raise RuntimeError("OPERATOR_RUN_ALREADY_ACTIVE")
            self._state = self._new_state(preserve_history=True)
            self._state.update(
                status="RUNNING",
                mode="TEST",
                started_at=self._state.get("started_at") or _iso(self._now()),
                ended_at=None,
                stop_reason=None,
                last_error=None,
                last_action="Preparing controlled Rediff transport test",
            )
            self._save_state()

        record = self._synthetic_record()
        record["record_id"] = "operator-rediff-transport-control-v1"
        personalized = self._personalization.personalize_record(record, force_provider="DETERMINISTIC")
        quality_score = float(personalized.get("quality_score") or 0)
        if personalized.get("status") != "VALIDATED" or quality_score < 85:
            raise RuntimeError("CONTROLLED_TEST_PERSONALIZATION_FAILED")
        prepared_record = self._personalization.enrich_record_for_rediff(record, personalized)
        prepared_record["PERSONALIZATION_STATUS"] = personalized["status"]
        prepared_record["PERSONALIZATION_SCORE"] = quality_score
        handoff = self._rediff.prepare_handoff(
            prepared_record,
            campaign="salesoorja-operator-transport-test",
            followup_stage="INITIAL",
        )
        if handoff.get("status") != DRY_RUN_READY:
            raise RuntimeError(f"CONTROLLED_TEST_HANDOFF_FAILED:{handoff.get('reason')}")
        self._update(last_action="Rediff handoff created; invoking authorized TEST transport")
        with self._lock:
            receipts = deepcopy(self._state.get("transport_receipts") or [])
            run_id = str(self._state["run_id"])
        receipt = self._transport_bridge.execute_test_transport(
            mapped_record=handoff["mapped_record"],
            run_id=run_id,
            company_reference=prepared_record.get("company"),
            person_reference=prepared_record.get("person"),
            campaign_reference="salesoorja-operator-transport-test",
            initial_or_followup="INITIAL",
            authorization=authorization,
            existing_receipts=receipts,
            mode="TEST",
            dispatch=dispatch,
        )
        if dispatch and receipt.get("transport_status") != SUPPRESSED_DUPLICATE_TRANSPORT:
            with self._lock:
                self._state["transport_receipts"].append(receipt)
                self._save_state()
        if receipt.get("transport_status") == "SENT" and receipt.get("smtp_sent") is True:
            self._increment("emails_sent")
            self._increment("test_emails_sent")
            self._append_record(
                "SENT",
                {
                    "company": prepared_record.get("company"),
                    "person": prepared_record.get("person"),
                    "recipient": receipt.get("recipient"),
                    "original_prospect_email": receipt.get("original_prospect_email"),
                    "quality_score": quality_score,
                    "transport_status": "SENT",
                    "test_mode": True,
                },
            )
        elif dispatch and receipt.get("transport_status") == "FAILED":
            self._increment("failed")
            self._append_record(
                "ERRORS",
                {
                    "stage": "rediff_transport",
                    "error": receipt.get("error"),
                    "attempt_number": receipt.get("attempt_number"),
                },
            )
        self._update(
            status="STOPPED",
            ended_at=_iso(self._now()),
            stop_reason="CONTROLLED_TRANSPORT_TEST" if dispatch else "CONTROLLED_TRANSPORT_PREVIEW",
            last_error=receipt.get("error"),
            last_action=(
                "Duplicate transport blocked from persisted receipt"
                if receipt.get("transport_status") == SUPPRESSED_DUPLICATE_TRANSPORT
                else f"Controlled Rediff transport {'finished' if dispatch else 'preview'}: {receipt.get('transport_status')}"
            ),
        )
        return {
            "quality_score": quality_score,
            "handoff_status": "HANDOFF_CREATED",
            "receipt": receipt,
            "status": self.get_status(),
        }

    def _run_safely(self) -> None:
        try:
            if self._mode() == "SMOKE":
                self._run_smoke_mode()
            elif self._mode() == "TEST":
                self._run_test_mode()
            else:
                self._run_production_loop()
        except Exception as exc:
            logger.exception("Salesoorja operator stopped after fatal error")
            self._append_record("ERRORS", {"stage": "operator", "error": type(exc).__name__, "detail": str(exc)})
            self._increment("failed")
            self._update(last_error=f"{type(exc).__name__}: {exc}")
            self.finalize_run(reason="FATAL_ERROR", status="ERROR")

    def _run_smoke_mode(self) -> None:
        self._heartbeat("Running bounded smoke diagnostic")
        if self._db_factory is not None and not self._is_stop_requested():
            self._run_discovery_cycle(smoke_mode=True)
        elif not self._is_stop_requested():
            self._process_synthetic_account()
        reason = "MANUAL_STOP" if self._is_stop_requested() else "SMOKE_COMPLETE"
        self.finalize_run(reason=reason)

    def _run_test_mode(self) -> None:
        cycle = 0
        last_inbox_poll = 0.0
        while not self._is_stop_requested():
            cycle += 1
            self._heartbeat(f"Running autonomous TEST cycle {cycle}")
            now_monotonic = time.monotonic()
            if now_monotonic - last_inbox_poll >= int(getattr(self.settings, "SALESOORJA_INBOX_INTERVAL_SECONDS", 1800)):
                self._poll_inbox()
                last_inbox_poll = now_monotonic
            try:
                processed = self._run_discovery_cycle()
            except Exception as exc:
                logger.warning("TEST discovery cycle failed without synthetic fallback: %s", exc)
                self._increment("failed")
                self._append_record(
                    "ERRORS",
                    {"stage": "test_discovery", "error": type(exc).__name__, "detail": str(exc)},
                )
                self._update(last_error=f"{type(exc).__name__}: {exc}")
                processed = False
            if self._db_factory and not self._is_stop_requested():
                db = self._db_factory()
                try:
                    self._process_due_followups(db)
                except Exception as exc:
                    logger.warning("Test mode follow-up processing error: %s", exc)
                finally:
                    db.close()
            if not processed and not self._is_stop_requested():
                self._update(current_company=None, last_action="No new qualifying accounts; waiting for next TEST cycle")
            if self._interruptible_wait(int(getattr(self.settings, "SALESOORJA_CYCLE_INTERVAL_SECONDS", 300))):
                break
        self.finalize_run(reason="MANUAL_STOP")

    def _synthetic_record(self) -> dict[str, Any]:
        return {
            "record_id": "operator-synthetic-control",
            "READY_FOR_EMAIL": "YES",
            "company": "Synthetic Precision Components",
            "facility": "Test Plant V, Pune, Maharashtra",
            "city": "Pune",
            "state": "Maharashtra",
            "person": "Asha Verma",
            "first_name": "Asha",
            "designation": "Plant Quality Head",
            "persona": "Quality Head",
            "email": "asha.verma@synthetic.test",
            "phone": "+91-9000000000",
            "trigger": "Synthetic precision line commissioning",
            "trigger_date": self._state["business_date"],
            "calibration_opportunity": "Dimensional and thermal calibration planning",
            "reasoning": "Synthetic source-backed operator verification",
            "icp_score": 95,
            "facility_verified": True,
            "contact_verified": True,
            "provenance": "SYNTHETIC",
            "evidence": {
                "trigger_current": {"verified": True},
                "exact_facility": {"verified": True, "address": "Test Plant V, Pune", "linkage_strength": "DIRECT"},
                "technical_capability": {"status": "IN_SCOPE"},
                "correct_person": {
                    "name": "Asha Verma",
                    "employment_verified": True,
                    "duties_verified": True,
                    "company_evidence_status": "CURRENT_COMPANY",
                },
                "reachable_email": {
                    "email": "asha.verma@synthetic.test",
                    "status": "VERIFIED",
                    "mailbox_verified": True,
                    "contact_confidence": "HIGH",
                },
            },
        }

    def _process_synthetic_account(self) -> None:
        account_key = "synthetic:operator-control"
        if account_key in self._state["processed_accounts"]:
            self._update(last_action="Synthetic account already processed; duplicate safely skipped")
            return
        self._update(current_company="Synthetic Precision Components", last_action="Applying deterministic qualification gates")
        self._increment("companies_researched")
        self._increment("qualified_opportunities")
        self._increment("people_researched")
        self._increment("people_verified")
        self._increment("contacts_enriched")
        record = self._synthetic_record()
        personalized = self._personalization.personalize_record(record, force_provider="DETERMINISTIC")
        quality_score = float(personalized.get("quality_score") or 0)
        if personalized.get("status") != "VALIDATED" or quality_score < 85:
            raise RuntimeError("Synthetic personalization failed the quality threshold")
        record = self._personalization.enrich_record_for_rediff(record, personalized)
        record["PERSONALIZATION_STATUS"] = personalized["status"]
        record["PERSONALIZATION_SCORE"] = quality_score
        self._provider_call("Rediff")
        handoff = self._rediff.prepare_handoff(record, campaign="salesoorja-operator-test")
        if handoff.get("status") != DRY_RUN_READY or handoff.get("smtp_sent") is not False:
            raise RuntimeError(f"Synthetic Rediff dry run failed: {handoff.get('reason')}")
        self._append_record(
            "QUALIFIED_NOT_SENT",
            {
                "company": record["company"],
                "facility": record["facility"],
                "person": record["person"],
                "email": record["email"],
                "quality_score": quality_score,
                "status": handoff["status"],
                "reason": "TEST mode never sends prospect email",
            },
        )
        if self._db_factory:
            db = self._db_factory()
            try:
                self._persist_pipeline_account(
                    db=db,
                    account={
                        "company_name": record["company"],
                        "facility": record["facility"],
                        "city": record["city"],
                        "state": record["state"],
                        "trigger": record["trigger"],
                        "icp_score": record["icp_score"],
                    },
                    candidate=type("SyntheticCandidate", (), {
                        "id": None,
                        "candidate_name": record["person"],
                        "candidate_title": record["designation"],
                        "candidate_facility": record["facility"],
                        "apollo_email": record["email"],
                        "apollo_phone": record["phone"],
                        "target_persona": record["persona"],
                    })(),
                    personalized=personalized,
                    handoff=handoff,
                    receipt=None,
                )
            except Exception as exc:
                logger.warning("Synthetic account DB persistence error: %s", exc)
            finally:
                db.close()
        with self._lock:
            self._state["processed_accounts"].append(account_key)
            self._state["current_company"] = None
            self._state["last_action"] = "Synthetic Rediff handoff verified with zero SMTP"
            self._save_state()

    def _local_now(self) -> datetime:
        return self._now().astimezone(ZoneInfo("Asia/Kolkata"))

    def _is_24x7(self) -> bool:
        return bool(getattr(self.settings, "SALESOORJA_24X7", True))

    def _before_start(self) -> bool:
        if self._is_24x7():
            return False
        start_hour, start_minute = _safe_time(getattr(self.settings, "SALESOORJA_START_TIME", "09:00"), "09:00")
        return self._local_now().time() < self._local_now().replace(hour=start_hour, minute=start_minute, second=0, microsecond=0).time()

    def _after_end(self) -> bool:
        if self._is_24x7():
            return False
        end_hour, end_minute = _safe_time(getattr(self.settings, "SALESOORJA_END_TIME", "18:00"), "18:00")
        return self._local_now().time() >= self._local_now().replace(hour=end_hour, minute=end_minute, second=0, microsecond=0).time()

    def _check_midnight_rollover(self) -> bool:
        """Check if local Asia/Kolkata date has crossed into a new calendar day.

        If date changed:
        1. Write final daily report for the completed business date.
        2. Send final daily report email if configured.
        3. Accumulate day's counters and provider usage into historical totals.
        4. Reset current-day counters and provider usage to 0.
        5. Advance business_date to new IST calendar day.
        6. Reset day-scoped working arrays.
        7. Save state and return True.
        """
        current_date_str = self._local_now().date().isoformat()
        current_business_date = str(self._state.get("business_date") or "")
        if not current_business_date:
            with self._lock:
                self._state["business_date"] = current_date_str
                self._save_state()
            return False

        if current_date_str == current_business_date:
            return False

        logger.info(
            "Midnight date rollover detected: advancing business_date from %s to %s",
            current_business_date,
            current_date_str,
        )

        with self._lock:
            # 1. Generate daily report for the completed business date
            try:
                report_path = self._write_report()
                self._send_final_report_email(report_path)
            except Exception as r_err:
                logger.warning("Error generating midnight report for %s: %s", current_business_date, r_err)

            # 2. Accumulate current day counters into historical totals
            for key, val in self._state.get("counters", {}).items():
                self._state["historical_counters"][key] = int(self._state["historical_counters"].get(key, 0)) + int(val)
            for key, val in self._state.get("provider_usage", {}).items():
                self._state["historical_provider_usage"][key] = int(self._state["historical_provider_usage"].get(key, 0)) + int(val)

            # 3. Reset daily counters and provider usage for new calendar day
            self._state["counters"] = {key: 0 for key in COUNTER_KEYS}
            self._state["provider_usage"] = {key: 0 for key in PROVIDER_KEYS}

            # 4. Advance business date
            self._state["business_date"] = current_date_str

            # 5. Reset day-scoped working arrays
            self._state["processed_accounts"] = []
            self._state["transport_receipts"] = []
            self._state["records"] = {sheet: [] for sheet in REPORT_SHEETS}
            self._state["last_checkpoint"] = _iso(self._now())
            self._state["last_action"] = f"Rolled over to business date {current_date_str}; daily counters reset"
            self._save_state()

        return True

    def _outbound_total(self) -> int:
        counters = self._state["counters"]
        return int(counters.get("emails_sent", 0)) + int(counters.get("rediff_handoffs", 0))

    def _stop_reason(self) -> Optional[str]:
        if self._is_stop_requested():
            return "MANUAL_STOP"
        if self._after_end():
            return "END_TIME"
        if self._outbound_total() >= max(1, int(getattr(self.settings, "DAILY_SEND_TARGET", 150))):
            return "DAILY_SEND_TARGET"
        if self._outbound_total() >= max(1, int(getattr(self.settings, "DAILY_SEND_MAX", 250))):
            return "DAILY_SEND_MAX"
        if int(self._state["provider_usage"].get("Serper", 0)) >= max(1, int(getattr(self.settings, "MAX_SERPER_CALLS_PER_DAY", 1500))):
            return "SERPER_DAILY_MAX"
        return None

    def _interruptible_wait(self, seconds: int) -> bool:
        deadline = time.monotonic() + max(1, seconds)
        next_heartbeat = time.monotonic()
        while time.monotonic() < deadline:
            if self._is_stop_requested():
                return True
            if time.monotonic() >= next_heartbeat:
                self._heartbeat()
                next_heartbeat = time.monotonic() + 10.0
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(max(0.0, min(1.0, remaining)))
        return self._is_stop_requested()

    def _run_production_loop(self) -> None:
        last_inbox_poll = 0.0
        while True:
            self._check_midnight_rollover()
            reason = self._stop_reason()
            if reason:
                self.finalize_run(reason=reason)
                return
            if self._before_start():
                self._update(status="WAITING", last_action="Waiting for configured working hours")
                if self._interruptible_wait(60):
                    continue
                self._update(status="RUNNING")
                continue
            now_monotonic = time.monotonic()
            if now_monotonic - last_inbox_poll >= int(getattr(self.settings, "SALESOORJA_INBOX_INTERVAL_SECONDS", 1800)):
                self._poll_inbox()
                last_inbox_poll = now_monotonic
            try:
                processed = self._run_discovery_cycle()
            except Exception as exc:
                logger.warning("Production discovery cycle failed; continuing after controlled delay: %s", exc)
                self._increment("failed")
                self._append_record(
                    "ERRORS",
                    {"stage": "production_discovery", "error": type(exc).__name__, "detail": str(exc)},
                )
                self._update(last_error=f"{type(exc).__name__}: {exc}")
                processed = False
            if self._db_factory is not None and not self._is_stop_requested():
                db = self._db_factory()
                try:
                    self._process_due_followups(db)
                except Exception as exc:
                    logger.warning("Production follow-up cycle failed; next cycle will continue: %s", exc)
                    self._increment("failed")
                    self._append_record(
                        "ERRORS",
                        {"stage": "production_followups", "error": type(exc).__name__, "detail": str(exc)},
                    )
                finally:
                    db.close()
            wait_seconds = int(getattr(self.settings, "SALESOORJA_CYCLE_INTERVAL_SECONDS", 300))
            if not processed:
                self._update(current_company=None, last_action=f"No new qualifying accounts; waiting {wait_seconds}s for next discovery cycle")
            else:
                self._update(current_company=None, last_action=f"Waiting {wait_seconds}s for next discovery cycle")
            if self._interruptible_wait(wait_seconds):
                continue

    def _resolve_runtime_functions(self) -> tuple[Callable[..., dict[str, Any]], Callable[..., dict[str, Any]]]:
        if self._discovery_fn is None:
            from services.signal_discovery_engine import discover_new_calibration_opportunities

            self._discovery_fn = discover_new_calibration_opportunities
        if self._person_pipeline_fn is None:
            from services.decision_maker_discovery import run_full_discovery_pipeline

            self._person_pipeline_fn = run_full_discovery_pipeline
        return self._discovery_fn, self._person_pipeline_fn

    def _serper_live_request_count(self) -> Optional[int]:
        try:
            from services.serper_budget_manager import serper_budget_manager

            return int(serper_budget_manager.get_telemetry().get("live_requests_today", 0))
        except Exception:
            return None

    def _run_discovery_cycle(self, *, smoke_mode: bool = False) -> bool:
        if self._db_factory is None:
            raise RuntimeError("Synchronous database session is unavailable")
        discovery_fn, _ = self._resolve_runtime_functions()
        db = self._db_factory()
        processed = False
        try:
            region_idx = int(self._state.get("discovery_region_index", 0) or 0)
            target_geo = DISCOVERY_REGIONS[region_idx % len(DISCOVERY_REGIONS)]
            with self._lock:
                self._state["discovery_region_index"] = (region_idx + 1) % len(DISCOVERY_REGIONS)
                self._save_state()

            self._update(last_action=f"Discovering fresh opportunities via Serper ({target_geo})")
            self._heartbeat(f"Serper live discovery search initiated ({target_geo})")
            serper_before = self._serper_live_request_count()
            try:
                discovery = discovery_fn(
                    db=db,
                    geography=target_geo,
                    limit=10,
                    use_cache=False,
                )
            finally:
                serper_after = self._serper_live_request_count()
                if serper_before is not None and serper_after is not None and serper_after > serper_before:
                    self._provider_call("Serper", serper_after - serper_before)
            self._heartbeat(f"Serper live discovery search completed ({target_geo})")

            planned = discovery.get("planned_query") or {}
            exec_state = discovery.get("execution_state")
            sec_name = planned.get("sector") or "Manufacturing"
            trig_name = planned.get("trigger") or "Expansion"
            geo_name = planned.get("geography") or target_geo
            y_score = float(discovery.get("yield_score") or 0.0)

            strat = discovery.get("strategy_decision") or {}
            strat_mode = strat.get("mode", "EXPLOIT")
            strat_sec = strat.get("sector") or sec_name
            strat_geo = strat.get("geography") or geo_name
            strat_trig = strat.get("trigger_family") or trig_name
            was_sub = planned.get("was_substituted", False)
            sub_reason = planned.get("substitution_reason")

            if was_sub and sub_reason:
                logger.info("[STRATEGY] Substitution: %s", sub_reason)
                self._update(last_action=f"Planner substitution: {strat_sec} in {geo_name} ({trig_name})")
            else:
                logger.info("[STRATEGY] %s | %s | %s | %s", strat_mode, strat_sec, strat_geo, strat_trig)
                if exec_state == "SUCCESS_EXHAUSTED":
                    self._update(last_action=f"{strat_mode} | {sec_name} | {trig_name} exhausted — rotating")
                elif exec_state == "SUCCESS_PRODUCTIVE":
                    self._update(last_action=f"{strat_mode} | {sec_name} in {geo_name} — yield: {y_score:.1f}")
                else:
                    self._update(last_action=f"{strat_mode} | {sec_name} | {geo_name} | {trig_name}")


            source_status = discovery.get("source_status") or {}
            current_run_live = bool(source_status.get("current_run_live"))
            candidates = [
                item
                for item in discovery.get("candidates", [])
                if current_run_live
                and item.get("current_run_live") is True
                and item.get("data_provenance") == "LIVE_SEARCH_DISCOVERED"
            ]
            for item in candidates:
                logger.info(
                    "[DISCOVERED] Company: %s | Source: %s | ICP: %s | Geo: %s",
                    item.get("company_name"),
                    item.get("data_provenance"),
                    item.get("icp_score"),
                    target_geo,
                )
            if smoke_mode:
                discovered_count = len(candidates)
                if candidates:
                    top_company = candidates[0].get("company_name")
                    qualified = [item for item in candidates if float(item.get("icp_score") or 0) >= 85]
                    qualified_count = len(qualified)
                    self._update(
                        current_company=top_company,
                        last_action=f"Serper SMOKE discovery completed ({discovered_count} leads): {top_company}",
                    )
                    self._increment("companies_researched", discovered_count)
                    if qualified_count > 0:
                        self._increment("qualified_opportunities", qualified_count)
                    processed = True
                else:
                    self._update(
                        current_company=None,
                        last_action="Serper SMOKE discovery completed (0 leads found)",
                    )
                    processed = False
                return processed

            for account in candidates:
                if self._is_stop_requested() or (self._mode() == "PRODUCTION" and self._stop_reason()):
                    break
                account_key = str(account.get("company_id") or account.get("company_name") or "").strip().casefold()
                if not account_key or account_key in self._state["processed_accounts"]:
                    continue
                processed = True
                self._process_production_account(db, account, account_key)
        finally:
            db.close()
        return processed

    def _process_production_account(self, db: Any, account: Mapping[str, Any], account_key: str) -> None:
        company_name = str(account.get("company_name") or "Unknown company")
        ev_packets = account.get("evidence_packets") or []
        packet_count = len(ev_packets)
        if packet_count > 0:
            self._update(
                current_company=company_name,
                last_action=f"Deep research completed ({packet_count} sources): {company_name}",
                current_research_stage=f"Synthesizing evidence for {company_name}",
            )
            self._increment("opportunities_deep_researched")
            self._increment("pages_fetched", packet_count)
            self._increment("pages_fetched_success", sum(1 for p in ev_packets if p.get("extracted_text")))
            if account.get("opportunity_classification") == "STRONG":
                self._increment("evidence_complete")
            else:
                self._increment("evidence_incomplete")
        else:
            self._update(
                current_company=company_name,
                last_action=f"Validating trigger and facility for {company_name}",
                current_research_stage=f"Verifying facility location for {company_name}",
            )
        self._increment("companies_researched")
        try:
            # 1. Entity Truth Gate: Discovered entity must be an actual organization/company
            from services.entity_truth_gate import validate_company_entity
            is_valid_entity, entity_reason = validate_company_entity(company_name, str(account.get("event_title") or ""))
            if not is_valid_entity:
                logger.info("[ENTITY_GATE_HOLD] Company: %s | Reason: %s", company_name, entity_reason)
                self._hold_account(account, f"Entity validation failed: {entity_reason}")
                return
            logger.info("[ENTITY_GATE_PASS] Company: %s", company_name)

            # 2. Trigger Validation Gate
            if account.get("trigger_valid") is not True:
                recency = str((account.get("trigger_recency") or {}).get("recency_tier") or "UNKNOWN")
                logger.info("[TRIGGER_HOLD] Company: %s | Valid: False | Recency: %s", company_name, recency)
                self._hold_account(account, f"Current trigger validation failed ({recency})")
                return
            logger.info("[TRIGGER_VALIDATED] Company: %s | Valid: True | Recency: %s", company_name, (account.get("trigger_recency") or {}).get("recency_tier"))

            # 3. Facility Truth Gate: Physical manufacturing or operational facility
            facility_evidence = account.get("facility_evidence") or {}
            target_facility = (
                account.get("target_facility")
                or account.get("facility")
                or facility_evidence.get("facility_name")
                or facility_evidence.get("trigger_facility")
                or facility_evidence.get("target_facility")
            )
            if not target_facility and account.get("facility_verified") is True and facility_evidence.get("linkage_confidence") in {"DIRECT", "STRONG"}:
                target_facility = f"{company_name} Facility"
            if (
                account.get("facility_verified") is not True
                or facility_evidence.get("linkage_confidence") not in {"DIRECT", "STRONG"}
                or not target_facility
                or str(target_facility).strip().casefold() in {"", "none", "unknown", "null"}
            ):
                reason = facility_evidence.get("linkage_evidence") or "Trigger is not bound to an exact physical facility"
                if not target_facility or str(target_facility).strip().casefold() in {"", "none", "unknown", "null"}:
                    reason = "Facility name is unresolved or None"
                logger.info("[FACILITY_HOLD] Company: %s | Verified: %s | Linkage: %s | Reason: %s", company_name, account.get("facility_verified"), facility_evidence.get("linkage_confidence"), reason)
                logger.info("[FACILITY_GATE_HOLD] Company: %s | Reason: %s", company_name, reason)
                self._hold_account(account, f"Facility validation failed: {reason}")
                return
            logger.info("[FACILITY_VALIDATED] Company: %s | Verified: True | Linkage: %s | Facility: %s", company_name, facility_evidence.get("linkage_confidence"), target_facility)
            logger.info("[FACILITY_GATE_PASS] Company: %s | Facility: %s | Linkage: %s", company_name, target_facility, facility_evidence.get("linkage_confidence"))

            if float(account.get("icp_score") or 0) < 85:
                logger.info("[OPPORTUNITY_HOLD] Company: %s | ICP: %s below 85", company_name, account.get("icp_score"))
                self._hold_account(account, "ICP score below 85")
                return
            logger.info("[OPPORTUNITY_QUALIFIED] Company: %s | ICP Score: %s | Signal: %s", company_name, account.get("icp_score"), account.get("signal_type"))
            self._increment("qualified_opportunities")

            _, pipeline_fn = self._resolve_runtime_functions()
            result = pipeline_fn(
                company_id=int(account["company_id"]),
                db=db,
                signal_type=account.get("signal_type"),
                max_apollo_enrichments=3,
                max_queries=6,
                before_apollo=lambda: self._mode() != "PRODUCTION" or (
                    not self._after_end()
                    and self._outbound_total() < int(getattr(self.settings, "DAILY_SEND_MAX", 250))
                ),
                progress_callback=lambda stage, detail="": self._pipeline_activity(company_name, stage, detail),
            )
            summary = result.get("summary", {})
            self._increment("people_researched", int(summary.get("candidates_found") or 0))
            self._increment("people_verified", int(summary.get("candidates_verified") or 0))
            self._increment("contacts_enriched", int(summary.get("apollo_enriched") or 0))
            stages = result.get("stages", {})
            self._provider_call("Apollo Search", int(stages.get("person_search", {}).get("queries_executed") or 0))
            self._provider_call("Bright Profiles", len(stages.get("person_search", {}).get("verification_attempts") or []))
            self._provider_call("Apollo Enrich", len(stages.get("apollo", {}).get("attempts") or []))
            candidate = self._select_send_candidate(db, result)
            if candidate is None:
                logger.info("[PERSON_GATE_HOLD] Company: %s | Reason: No candidate passed current-employment, facility, authority, and verified-email gates", company_name)
                self._hold_account(account, "No candidate passed current-employment, facility, authority, and verified-email gates")
                return
            logger.info("[PERSON_GATE_PASS] Company: %s | Candidate: %s | Title: %s | Score: %s", company_name, candidate.candidate_name, candidate.candidate_title, candidate.score_composite)

            record = self._build_production_record(account, candidate, result)
            self._update(last_action=f"Generating outreach for {company_name} with DeepSeek")
            logger.info("[PERSONALIZATION_STARTED] Company: %s | Candidate: %s | Role: %s", company_name, record.get("person"), record.get("title"))
            personalized = self._personalization.personalize_record(record, force_provider="AUTO")
            provider = str(personalized.get("llm_provider_used") or "")
            if provider.startswith("DEEPSEEK"):
                self._provider_call("DeepSeek")
            elif provider.startswith("GEMINI"):
                self._provider_call("Gemini")
            quality_score = float(personalized.get("quality_score") or 0)
            logger.info("[PERSONALIZATION_RESULT] Company: %s | Provider: %s | Quality Score: %s", company_name, provider, quality_score)
            self._update(last_action=f"Claim validation completed for {company_name}: {personalized.get('status', 'UNKNOWN')}")
            if personalized.get("status") != "VALIDATED" or quality_score < 85:
                logger.info("[CLAIM_VALIDATION_HOLD] Company: %s | Status: %s | Quality: %s", company_name, personalized.get("status"), quality_score)
                self._hold_account(account, f"Personalization quality {quality_score:.1f} below 85")
                return
            logger.info("[CLAIM_VALIDATION_PASS] Company: %s | Status: %s | Quality: %s", company_name, personalized.get("status"), quality_score)

            record = self._personalization.enrich_record_for_rediff(record, personalized)
            record["PERSONALIZATION_STATUS"] = personalized["status"]
            record["PERSONALIZATION_SCORE"] = quality_score
            approved_subject = str(personalized.get("subject") or "").strip()
            approved_body = str(personalized.get("body") or "").strip()
            record["FINAL_SUBJECT"] = approved_subject
            record["SUBJECT"] = approved_subject
            record["subject"] = approved_subject
            record["FINAL_BODY_HTML"] = approved_body
            record["BODY_HTML"] = approved_body
            record["body_html"] = approved_body
            record["FINAL_BODY_TEXT"] = approved_body
            record["BODY_TEXT"] = approved_body
            record["body_text"] = approved_body
            handoff = self._rediff.prepare_handoff(record, outreach_state=self._outreach_state(db, int(account["company_id"])))
            row = {
                "company": company_name,
                "facility": record["facility"],
                "person": record["person"],
                "email": record["email"],
                "quality_score": quality_score,
                "status": handoff.get("status"),
                "reason": handoff.get("reason"),
            }
            receipt = None
            if self._mode() == "PRODUCTION" and handoff.get("status") == QUEUED:
                self._update(last_action=f"Sending {company_name} via Rediff")
                logger.info("[REDIFF_SEND_STARTED] Company: %s | Recipient: %s", company_name, record["person"])
                self._provider_call("Rediff")
                with self._lock:
                    existing_receipts = deepcopy(self._state.get("transport_receipts") or [])
                receipt = self._transport_bridge.execute_production_transport(
                    mapped_record=handoff["mapped_record"],
                    run_id=str(self._state.get("run_id") or ""),
                    company_reference=account.get("company_id") or company_name,
                    person_reference=getattr(candidate, "id", None) or record.get("person"),
                    existing_receipts=existing_receipts,
                    dispatch=True,
                )
                if receipt.get("transport_status") != SUPPRESSED_DUPLICATE_TRANSPORT:
                    with self._lock:
                        self._state["transport_receipts"].append(dict(receipt))
                        self._save_state()
                if receipt.get("transport_status") == SENT and receipt.get("smtp_sent") is True:
                    logger.info("[REDIFF_SENT] Company: %s | MessageId: %s", company_name, receipt.get("message_id"))
                    handoff = {**handoff, "status": SENT, "smtp_sent": True, "transport_called": True}
                else:
                    logger.info("[REDIFF_FAILED] Company: %s | Status: %s | Reason: %s", company_name, receipt.get("transport_status"), receipt.get("error"))
                    handoff = {
                        **handoff,
                        "status": str(receipt.get("transport_status") or "FAILED"),
                        "smtp_sent": False,
                        "reason": receipt.get("error") or receipt.get("transport_status"),
                    }
                row["status"] = handoff.get("status")
                row["reason"] = handoff.get("reason")

            if handoff.get("status") == SENT and handoff.get("smtp_sent") and receipt and receipt.get("smtp_sent"):
                self._increment("emails_sent")
                self._increment("production_emails_sent")
                self._increment("real_prospect_emails_sent")
                self._append_record("SENT", row)
            elif handoff.get("status") == QUEUED:
                self._increment("rediff_handoffs")
                self._append_record("QUALIFIED_NOT_SENT", row)
            else:
                if self._mode() == "PRODUCTION":
                    self._increment("held")
                self._append_record("QUALIFIED_NOT_SENT", row)

            self._persist_pipeline_account(
                db=db,
                account=account,
                candidate=candidate,
                personalized=personalized,
                handoff=handoff,
                receipt=receipt,
                source_record=record,
            )
        except Exception as exc:
            logger.exception("Production account failed: %s", company_name)
            self._increment("failed")
            self._append_record("ERRORS", {"company": company_name, "stage": "account", "error": type(exc).__name__, "detail": str(exc)})
            self._update(last_error=f"{company_name}: {type(exc).__name__}")
        finally:
            with self._lock:
                if account_key not in self._state["processed_accounts"]:
                    self._state["processed_accounts"].append(account_key)
                self._state["current_company"] = None
                self._state["last_action"] = f"Finished {company_name}"
                self._save_state()

    def _pipeline_activity(self, company_name: str, stage: str, detail: str = "") -> None:
        messages = {
            "apollo_search": f"Searching Apollo candidates for {company_name}",
            "bright_verification": f"Verifying candidates for {company_name} with Bright",
            "apollo_enrichment": f"Enriching qualified contact for {company_name} with Apollo",
        }
        message = messages.get(stage, detail or f"Processing {company_name}: {stage}")
        logger.info("Production pipeline stage: %s", message)
        self._update(current_company=company_name, last_action=message)
        self._heartbeat(message)

    def _select_send_candidate(self, db: Any, result: Mapping[str, Any]) -> Any:
        from models.decision_maker_candidate import DecisionMakerCandidate

        raw_by_id = {int(item["id"]): item for item in result.get("candidates", []) if item.get("id") is not None}
        candidate_ids = list(raw_by_id)
        if not candidate_ids:
            return None
        candidates = (
            db.query(DecisionMakerCandidate)
            .filter(DecisionMakerCandidate.id.in_(candidate_ids))
            .order_by(DecisionMakerCandidate.score_composite.desc())
            .all()
        )
        for candidate in candidates[:3]:
            raw = raw_by_id.get(candidate.id, {})
            apollo_person = (candidate.apollo_response_json or {}).get("person") or {}
            email_verified = str(apollo_person.get("email_status") or "").casefold() == "verified"
            if (
                raw.get("current_employment") == "VERIFIED"
                and raw.get("facility_relationship") in {"FACILITY_OWNER", "FACILITY_FUNCTION_OWNER"}
                and raw.get("authority_class") in {"DECISION_MAKER", "FUNCTION_OWNER", "FACILITY_OWNER", "GROUP_FUNCTION_OWNER"}
                and float(raw.get("person_score") or 0) >= 85
                and candidate.apollo_email
                and candidate.apollo_email_confidence == "HIGH"
                and email_verified
            ):
                return candidate
        return None

    def _build_production_record(self, account: Mapping[str, Any], candidate: Any, result: Mapping[str, Any]) -> dict[str, Any]:
        raw = next((item for item in result.get("candidates", []) if item.get("id") == candidate.id), {})
        causality = account.get("causality_chain") or {}
        facility_evidence = account.get("facility_evidence") or {}
        trigger_recency = account.get("trigger_recency") or {}
        facility = (
            candidate.candidate_facility
            or facility_evidence.get("facility_name")
            or raw.get("location")
            or account.get("city")
            or ""
        )
        opportunity = causality.get("calibration_impact") or "Source-backed calibration requirement"
        return {
            "record_id": f"operator-{account['company_id']}-{candidate.id}",
            "READY_FOR_EMAIL": "YES",
            "company": account.get("company_name"),
            "facility": facility,
            "city": account.get("city"),
            "state": account.get("state"),
            "person": candidate.candidate_name,
            "first_name": str(candidate.candidate_name or "").split()[0],
            "designation": candidate.candidate_title,
            "persona": candidate.target_persona,
            "email": candidate.apollo_email,
            "phone": candidate.apollo_phone,
            "trigger": account.get("event_title"),
            "trigger_date": trigger_recency.get("trigger_date") or trigger_recency.get("event_date") or "",
            "trigger_source": account.get("evidence_url"),
            "facility_activity": account.get("event_title"),
            "calibration_opportunity": opportunity,
            "reasoning": opportunity,
            "icp_score": float(account.get("icp_score") or 0),
            "facility_verified": account.get("facility_verified") is True,
            "contact_verified": True,
            "provenance": "REAL",
            "evidence": {
                "trigger_current": {
                    "verified": account.get("trigger_valid") is True,
                    "source_url": account.get("evidence_url"),
                    "event_date": trigger_recency.get("event_date"),
                    "recency_tier": trigger_recency.get("recency_tier"),
                },
                "exact_facility": {
                    "verified": account.get("facility_verified") is True,
                    "address": facility_evidence.get("facility_address") or facility,
                    "linkage_strength": facility_evidence.get("linkage_confidence"),
                    "evidence": facility_evidence.get("linkage_evidence"),
                },
                "technical_capability": {"status": "IN_SCOPE"},
                "correct_person": {
                    "name": candidate.candidate_name,
                    "employment_verified": True,
                    "duties_verified": True,
                    "company_evidence_status": "CURRENT_COMPANY",
                },
                "reachable_email": {
                    "email": candidate.apollo_email,
                    "status": "VERIFIED",
                    "mailbox_verified": True,
                    "contact_confidence": "HIGH",
                },
            },
        }

    def _outreach_state(self, db: Any, company_id: int) -> dict[str, Any]:
        from models.campaign import CampaignRecipient
        from models.company import Company

        company = db.query(Company).filter(Company.id == company_id).first()
        recipient = (
            db.query(CampaignRecipient)
            .filter(CampaignRecipient.company_id == company_id)
            .order_by(CampaignRecipient.updated_at.desc())
            .first()
        )
        metadata = dict(recipient.metadata_json or {}) if recipient else {}
        return {
            "last_sent_at": _iso(recipient.last_sent_at if recipient else getattr(company, "last_contact_date", None)),
            "replied_at": _iso(recipient.replied_at) if recipient else None,
            "bounced_at": _iso(recipient.bounced_at) if recipient else None,
            "email_status": recipient.email_status if recipient else None,
            "reply_classification": metadata.get("reply_classification"),
            "meaningful_reply": metadata.get("meaningful_reply", False),
            "opted_out": metadata.get("opted_out", False),
        }

    def _hold_account(self, account: Mapping[str, Any], reason: str) -> None:
        self._increment("held")
        self._append_record(
            "HOLD",
            {
                "company": account.get("company_name"),
                "facility": ", ".join(value for value in (account.get("city"), account.get("state")) if value),
                "icp_score": account.get("icp_score"),
                "reason": reason,
            },
        )

    def _poll_inbox(self) -> None:
        if self._db_factory is None:
            return
        if self._imap_poll_fn is None:
            try:
                from services.imap_service import poll_imap_inbox

                self._imap_poll_fn = poll_imap_inbox
            except Exception as exc:
                logger.debug("IMAP service unavailable: %s", exc)
                return
        db = self._db_factory()
        try:
            result = self._imap_poll_fn(db=db, folder="INBOX", limit=50)
            for item in result.get("processed_results", []):
                classification = str(item.get("classification") or "").upper()
                if classification and classification not in {"IRRELEVANT", "OUT_OF_OFFICE"}:
                    self._increment("replies")
                    self._append_record("REPLIES", item)
                if classification in {"ENQUIRY", "INTERESTED", "REFERRAL", "FUTURE_REQUIREMENT"}:
                    self._increment("enquiries")
                    self._append_record("ENQUIRIES", item)
        except Exception as exc:
            logger.warning("IMAP inbox poll caught non-fatal exception: %s", exc)
        finally:
            db.close()

    def _persist_pipeline_account(
        self,
        db: Any,
        account: Mapping[str, Any],
        candidate: Any,
        personalized: Mapping[str, Any],
        handoff: Mapping[str, Any],
        receipt: Optional[Mapping[str, Any]] = None,
        source_record: Optional[Mapping[str, Any]] = None,
    ) -> dict[str, Any]:
        from models.campaign import Campaign, CampaignEvent, CampaignRecipient, CampaignStep
        from models.company import Company
        from models.decision_maker_candidate import DecisionMakerCandidate
        from models.facility import Facility
        from models.intent_signal import CompanyIntentSignal
        from models.person import Person
        from services.follow_up_engine import calculate_cadence_schedule, FollowUpEngine

        company_name = str(account.get("company_name") or "Unknown Company").strip()
        from services.pre_persistence_entity_gate import pre_persistence_entity_gate
        from services.entity_truth_gate import get_normalized_comparison_key
        cls_check = pre_persistence_entity_gate.resolve_pre_persistence_decision(
            candidate_name=company_name,
            industry=str(account.get("industry") or ""),
            facility_info={"facility_name": str(account.get("facility") or "")},
        )
        if not cls_check.is_target_industrial or not cls_check.canonical_company_name:
            logger.warning(
                "[OPERATOR_PERSISTENCE_GUARD] Skipping non-target candidate '%s' (type=%s, reason=%s)",
                company_name,
                cls_check.entity_type,
                cls_check.reason,
            )
            return None
        company_name = cls_check.canonical_company_name.strip()

        norm_key = get_normalized_comparison_key(company_name)
        company = db.query(Company).filter((Company.name == company_name) | (Company.normalized_name == norm_key)).first()
        if not company:
            company = Company(
                name=company_name,
                normalized_name=norm_key,
                domain=str(account.get("domain") or ""),
                city=str(account.get("city") or ""),
                state=str(account.get("state") or ""),
                industry=str(account.get("industry") or "Manufacturing"),
                qualification_status="QUALIFIED",
                qualification_reason="Passed deterministic discovery and qualification gates",
                source="autonomous_operator",
            )
            db.add(company)
            db.flush()

        facility_name = str(account.get("facility") or getattr(candidate, "candidate_facility", "") or "").strip()
        if facility_name:
            fac = db.query(Facility).filter(
                Facility.company_id == company.id,
                Facility.name == facility_name,
            ).first()
            if not fac:
                fac = Facility(
                    company_id=company.id,
                    name=facility_name,
                    city=str(account.get("city") or ""),
                    state=str(account.get("state") or ""),
                )
                db.add(fac)
                db.flush()

        signal_title = str(account.get("event_title") or account.get("trigger") or "Manufacturing expansion signal").strip()
        signal_type = str(account.get("signal_type") or "EXPANSION").strip()
        if signal_type:
            sig = db.query(CompanyIntentSignal).filter(
                CompanyIntentSignal.company_id == company.id,
                CompanyIntentSignal.signal_type == signal_type,
            ).first()
            if not sig:
                sig = CompanyIntentSignal(
                    company_id=company.id,
                    signal_type=signal_type,
                    opportunity_note=signal_title,
                    weight_applied=float(account.get("icp_score") or 90.0),
                )
                db.add(sig)
                db.flush()

        cand_name = str(getattr(candidate, "candidate_name", None) or account.get("person") or "").strip()
        cand_email = str(getattr(candidate, "apollo_email", None) or account.get("email") or "").strip()
        cand_phone = str(getattr(candidate, "apollo_phone", None) or account.get("phone") or "").strip()
        cand_title = str(getattr(candidate, "candidate_title", None) or account.get("designation") or "").strip()

        person = None
        if cand_email:
            person = db.query(Person).filter(
                Person.company_id == company.id,
                Person.email == cand_email,
            ).first()
            if not person:
                person = Person(
                    company_id=company.id,
                    full_name=cand_name,
                    designation=cand_title,
                    email=cand_email,
                    phone=cand_phone,
                    is_decision_maker=1,
                    discovery_status="APOLLO_ENRICHED",
                )
                db.add(person)
                db.flush()

        cand_record = None
        cand_id = getattr(candidate, "id", None)
        if cand_id and isinstance(candidate, DecisionMakerCandidate):
            cand_record = candidate
            candidate.verification_status = "VERIFIED"
            db.add(candidate)
            db.flush()
        elif cand_name:
            cand_record = db.query(DecisionMakerCandidate).filter(
                DecisionMakerCandidate.company_id == company.id,
                DecisionMakerCandidate.candidate_name == cand_name,
            ).first()
            if not cand_record:
                cand_record = DecisionMakerCandidate(
                    company_id=company.id,
                    candidate_name=cand_name,
                    candidate_title=cand_title,
                    apollo_email=cand_email,
                    apollo_phone=cand_phone,
                    target_persona=str(getattr(candidate, "target_persona", None) or account.get("persona") or "Quality"),
                    score_composite=float(account.get("icp_score") or 95.0),
                    verification_status="VERIFIED",
                )
                db.add(cand_record)
                db.flush()

        campaign = db.query(Campaign).filter(Campaign.name == "Salesoorja Autonomous Outbound").first()
        if not campaign:
            campaign = Campaign(
                name="Salesoorja Autonomous Outbound",
                description="Autonomous 5-touch outreach sequence (Day 1, 3, 5, 11, 21)",
                channel="email",
                status="Active",
                approved=True,
            )
            db.add(campaign)
            db.flush()
            for idx, delay in enumerate([0, 2, 4, 10, 20]):
                step = CampaignStep(
                    campaign_id=campaign.id,
                    step_number=idx,
                    delay_days=delay,
                    channel="email",
                    subject=f"Touch {idx + 1}",
                    enabled=True,
                )
                db.add(step)
            db.flush()

        rec = db.query(CampaignRecipient).filter(
            CampaignRecipient.campaign_id == campaign.id,
            CampaignRecipient.company_id == company.id,
        ).first()

        is_real_confirmed_send = bool(
            self._mode() == "PRODUCTION"
            and handoff.get("status") == SENT
            and handoff.get("smtp_sent") is True
            and receipt
            and receipt.get("smtp_sent") is True
            and not receipt.get("test_mode")
        )

        now = self._now()
        followup_engine = FollowUpEngine()
        message_id = (receipt.get("message_id") if receipt else None) or ""

        if is_real_confirmed_send:
            cadence = followup_engine.initialize_cadence(
                record_id=f"cadence-{company.id}-{person.id if person else 0}",
                company=company_name,
                facility=facility_name,
                contact_name=cand_name,
                email=cand_email,
                initial_sent_at=now,
                message_id=message_id,
                original_subject=str(personalized.get("subject") or ""),
            )
            sched = calculate_cadence_schedule(now)
            recipient_status = "ACTIVE"
            email_status = "SENT"
            last_sent_at = now
            next_send_at = sched["followup_1_due"]
            current_step = 0
            cadence_state_dict = cadence.to_dict()
        elif self._mode() != "PRODUCTION":
            recipient_status = "TEST_PREVIEW"
            email_status = "NOT_SENT_TEST_MODE"
            last_sent_at = None
            next_send_at = None
            current_step = 0
            cadence_state_dict = None
        else:
            recipient_status = "HOLD"
            email_status = str(handoff.get("status") or "NOT_SENT")
            last_sent_at = None
            next_send_at = None
            current_step = 0
            cadence_state_dict = None

        meta = {
            "subject": personalized.get("subject"),
            "body_html": personalized.get("body_html"),
            "body_text": personalized.get("body_text"),
            "followups": personalized.get("followups"),
            "quality_score": personalized.get("quality_score"),
            "message_id": message_id,
            "message_ids": [message_id] if message_id else [],
            "references": message_id,
            "in_reply_to": "",
            "sent_at": receipt.get("sent_at") if receipt else None,
            "email": cand_email,
            "lead_id": str((handoff.get("mapped_record") or {}).get("LEAD_ID") or ""),
            "person_reference": getattr(candidate, "id", None) or cand_name,
            "campaign_reference": "salesoorja-autonomous-outbound",
            "rediff_mapped_record": dict(handoff.get("mapped_record") or {}),
            "source_record": dict(source_record or {}),
            "cadence_state": cadence_state_dict,
            "test_mode": self._mode() != "PRODUCTION",
        }

        if not rec:
            rec = CampaignRecipient(
                campaign_id=campaign.id,
                company_id=company.id,
                person_id=person.id if person else None,
                current_step=current_step,
                status=recipient_status,
                email_status=email_status,
                last_sent_at=last_sent_at,
                next_send_at=next_send_at,
                metadata_json=meta,
            )
            db.add(rec)
            db.flush()
        else:
            rec.status = recipient_status
            rec.email_status = email_status
            rec.current_step = current_step
            rec.last_sent_at = last_sent_at
            rec.next_send_at = next_send_at
            rec.metadata_json = meta
            db.add(rec)
            db.flush()

        event = CampaignEvent(
            campaign_id=campaign.id,
            recipient_id=rec.id,
            event_type="INITIAL_SENT" if is_real_confirmed_send else "TEST_PREVIEW",
            channel="email",
            provider_message_id=message_id,
            payload={"receipt": receipt, "test_mode": not is_real_confirmed_send},
        )
        db.add(event)
        db.commit()

        return {"company_id": company.id, "recipient_id": rec.id, "status": recipient_status}

    def _process_due_followups(self, db: Any) -> int:
        from models.campaign import CampaignEvent, CampaignRecipient
        from models.company import Company
        from models.person import Person
        from services.follow_up_engine import calculate_cadence_schedule

        now = self._now()
        due_recipients = (
            db.query(CampaignRecipient)
            .filter(
                CampaignRecipient.status == "ACTIVE",
                CampaignRecipient.next_send_at.isnot(None),
                CampaignRecipient.next_send_at <= now,
            )
            .all()
        )
        if not due_recipients:
            return 0

        processed = 0
        step_due_keys = {
            1: "followup_2_due",
            2: "followup_3_due",
            3: "final_followup_due",
        }
        for rec in due_recipients:
            rec_meta = dict(rec.metadata_json or {})
            if (
                getattr(rec, "has_replied", False)
                or rec_meta.get("has_replied")
                or getattr(rec, "replied_at", None)
                or getattr(rec, "status", None) == "REPLIED"
            ):
                rec.status = "REPLIED"
                rec.pause_reason = "REPLIED"
                rec.next_send_at = None
                db.add(rec)
                db.commit()
                continue

            if (
                getattr(rec, "status", None) in {"BOUNCED", "OPTED_OUT"}
                or getattr(rec, "bounced_at", None)
                or rec_meta.get("bounced")
                or rec_meta.get("opted_out")
            ):
                rec.status = "BOUNCED" if (getattr(rec, "bounced_at", None) or rec_meta.get("bounced")) else "OPTED_OUT"
                rec.next_send_at = None
                db.add(rec)
                db.commit()
                continue

            rec_company_id = getattr(rec, "company_id", None)
            company = db.query(Company).filter(Company.id == rec_company_id).first() if rec_company_id else None
            company_name = company.name if company else (getattr(rec, "company_name", None) or f"Company {rec_company_id}")
            outreach_state = self._outreach_state(db, rec_company_id) if rec_company_id else {}
            suppression = self._rediff.evaluate_suppression(
                {
                    "READY_FOR_EMAIL": "YES",
                    "EMAIL": outreach_state.get("email") or rec_meta.get("email") or getattr(rec, "email", ""),
                    "is_followup": True,
                },
                {**outreach_state, "is_followup": True},
                is_followup=True,
            )
            if not suppression.get("allowed"):
                rec.status = "SUPPRESSED"
                rec.next_send_at = None
                db.add(rec)
                event = CampaignEvent(
                    campaign_id=rec.campaign_id,
                    recipient_id=rec.id,
                    event_type="SUPPRESSED",
                    channel="email",
                    payload={"reason": suppression.get("reason")},
                )
                db.add(event)
                db.commit()
                self._increment("held")
                self._append_record("HOLD", {
                    "company": company_name,
                    "reason": f"Follow-up suppressed: {suppression.get('reason')}",
                })
                continue

            next_step = int(rec.current_step or 0) + 1
            step_keys = {1: "day_3", 2: "day_5", 3: "day_11", 4: "day_21"}
            if next_step > 4 or next_step not in step_keys:
                rec.status = "COMPLETED"
                rec.next_send_at = None
                db.add(rec)
                db.commit()
                continue

            meta = dict(rec.metadata_json or {})
            followups = meta.get("followups") or {}
            touch_key = step_keys[next_step]
            touch_body = followups.get(touch_key) or "Following up regarding our earlier correspondence on calibration support."
            orig_subject = meta.get("subject") or "Calibration Planning"
            subject = f"Re: {orig_subject}" if not orig_subject.lower().startswith("re:") else orig_subject

            if self._mode() != "PRODUCTION":
                logger.info("TEST mode: follow-up %s for %s simulated with zero prospect dispatch", touch_key, company_name)
                rec.current_step = next_step
                rec.last_sent_at = now
                sched = calculate_cadence_schedule(now)
                rec.next_send_at = sched.get(step_due_keys.get(next_step)) if next_step < 4 else None
                if next_step >= 4:
                    rec.status = "COMPLETED"
                    rec.next_send_at = None
                db.add(rec)
                db.commit()
                self._increment("followups_sent")
                processed += 1
                continue

            if not getattr(self.settings, "REAL_OUTREACH_ENABLED", False):
                logger.warning("Production follow-up skipped: REAL_OUTREACH_ENABLED is False")
                continue

            source_record = dict(meta.get("source_record") or {})
            mapped_record = dict(meta.get("rediff_mapped_record") or {})
            if not source_record or not mapped_record:
                rec.status = "HOLD"
                rec.pause_reason = "MISSING_QUALIFIED_SOURCE_RECORD"
                rec.next_send_at = None
                db.add(rec)
                db.commit()
                self._increment("held")
                self._append_record("HOLD", {
                    "company": company_name,
                    "reason": "Follow-up held: persisted qualification evidence is missing",
                })
                continue

            person = db.query(Person).filter(Person.id == rec.person_id).first() if rec.person_id else None
            recipient_email = str(meta.get("email") or mapped_record.get("EMAIL") or getattr(person, "email", "") or "").strip()
            source_record.update({
                "email": recipient_email,
                "subject": subject,
                "body_html": touch_body,
                "body_text": touch_body,
                "followup_stage": touch_key.upper(),
                "is_followup": True,
            })
            message_ids = [value for value in meta.get("message_ids", []) if value]
            prior_message_id = str(meta.get("message_id") or (message_ids[-1] if message_ids else ""))
            references = " ".join(dict.fromkeys([*message_ids, prior_message_id]))
            handoff = self._rediff.prepare_handoff(
                source_record,
                outreach_state={**outreach_state, "is_followup": True},
                campaign=str(meta.get("campaign_reference") or "salesoorja-autonomous-outbound"),
                followup_stage=touch_key.upper(),
                in_reply_to=prior_message_id,
                references=references,
            )
            if handoff.get("status") != QUEUED:
                self._increment("held")
                self._append_record("HOLD", {
                    "company": company_name,
                    "reason": f"Follow-up held: {handoff.get('reason')}",
                })
                continue

            with self._lock:
                existing_receipts = deepcopy(self._state.get("transport_receipts") or [])
            receipt = self._transport_bridge.execute_production_transport(
                mapped_record=handoff["mapped_record"],
                run_id=str(self._state.get("run_id") or ""),
                company_reference=rec_company_id or company_name,
                person_reference=rec.person_id or meta.get("person_reference") or recipient_email,
                campaign_reference=str(meta.get("campaign_reference") or "salesoorja-autonomous-outbound"),
                initial_or_followup=touch_key.upper(),
                existing_receipts=existing_receipts,
                dispatch=True,
            )
            if receipt.get("transport_status") != SUPPRESSED_DUPLICATE_TRANSPORT:
                with self._lock:
                    self._state["transport_receipts"].append(dict(receipt))
                    self._save_state()
            if receipt.get("transport_status") != SENT or receipt.get("smtp_sent") is not True:
                self._increment("failed")
                self._append_record("ERRORS", {
                    "company": company_name,
                    "stage": touch_key.upper(),
                    "error": receipt.get("error") or receipt.get("transport_status"),
                })
                continue

            sent_at = self._now()
            new_message_id = str(receipt.get("message_id") or "")
            if new_message_id:
                message_ids.append(new_message_id)
            cadence_state = dict(meta.get("cadence_state") or {})
            next_due_fields = {1: "followup_2_due_at", 2: "followup_3_due_at", 3: "final_followup_due_at"}
            next_due = cadence_state.get(next_due_fields.get(next_step, ""))
            try:
                rec.next_send_at = datetime.fromisoformat(str(next_due)) if next_step < 4 and next_due else None
            except ValueError:
                sched = calculate_cadence_schedule(sent_at)
                rec.next_send_at = sched.get(step_due_keys.get(next_step)) if next_step < 4 else None
            rec.current_step = next_step
            rec.last_sent_at = sent_at
            rec.email_status = "SENT"
            if next_step >= 4:
                rec.status = "COMPLETED"
                rec.next_send_at = None
            meta.update({
                "message_id": new_message_id or prior_message_id,
                "message_ids": message_ids,
                "references": " ".join(dict.fromkeys(message_ids)),
                "in_reply_to": prior_message_id,
                "sent_at": receipt.get("sent_at") or sent_at.isoformat(),
                "rediff_mapped_record": dict(handoff.get("mapped_record") or mapped_record),
                "source_record": source_record,
            })
            rec.metadata_json = meta
            db.add(rec)
            db.add(CampaignEvent(
                campaign_id=rec.campaign_id,
                recipient_id=rec.id,
                event_type=f"{touch_key.upper()}_SENT",
                channel="email",
                provider_message_id=new_message_id,
                payload={"receipt": receipt, "test_mode": False},
            ))
            db.commit()
            self._increment("followups_sent")
            self._increment("emails_sent")
            self._increment("production_emails_sent")
            self._increment("real_prospect_emails_sent")
            self._append_record("SENT", {
                "company": company_name,
                "person": getattr(person, "full_name", "") if person else "",
                "email": recipient_email,
                "status": SENT,
                "touch": touch_key.upper(),
            })
            processed += 1

        return processed

    def _send_final_report_email(self, report_path: Path) -> dict[str, Any]:
        """Send final report XLSX to internal email using existing Rediff transport."""
        to_addr = "Bablu@oorjatechnical.org"
        cc_addr = "piyushk@oorjatechnical.com"
        counters = self._state["counters"]
        subject = f"Salesoorja Daily Report - {self._state['business_date']} - {counters['enquiries']} Enquiries / {counters['emails_sent']} Sent"

        if not self._rediff.system_available():
            if self._mode() != "PRODUCTION":
                return self._build_final_email_dry_run(report_path)
            logger.info("Rediff transport unavailable; final report email marked NOT_READY")
            return {"status": "NOT_READY", "reason": "REDIFF_SYSTEM_UNAVAILABLE"}

        try:
            config_path = Path(self.settings.REDIFF_SYSTEM_PATH) / "config.py"
            spec = importlib.util.spec_from_file_location("salesoorja_rediff_external_config", config_path)
            if spec is None or spec.loader is None:
                return {"status": "NOT_READY", "reason": "REDIFF_CONFIG_LOAD_FAILED"}
            rediff_cfg = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(rediff_cfg)

            smtp_server = getattr(rediff_cfg, "SMTP_SERVER", None)
            smtp_port = getattr(rediff_cfg, "SMTP_PORT", 465)
            email_addr = getattr(rediff_cfg, "EMAIL_ADDRESS", None)
            email_pwd = getattr(rediff_cfg, "EMAIL_PASSWORD", None)

            if not smtp_server or not email_addr or not email_pwd:
                return {"status": "NOT_READY", "reason": "SMTP_CREDENTIALS_MISSING"}

            msg = MIMEMultipart()
            msg["From"] = email_addr
            msg["To"] = to_addr
            msg["CC"] = cc_addr
            msg["Subject"] = subject

            body = (
                f"Salesoorja Operator Run Completed.\n\n"
                f"Run ID: {self._state.get('run_id')}\n"
                f"Mode: {self._state.get('mode')}\n"
                f"Stop Reason: {self._state.get('stop_reason')}\n"
                f"Companies Researched: {counters['companies_researched']}\n"
                f"Qualified: {counters['qualified_opportunities']}\n"
                f"Emails Sent: {counters['emails_sent']}\n"
                f"Replies: {counters['replies']}\n"
                f"Enquiries: {counters['enquiries']}\n"
                f"Errors: {counters['failed']}\n\n"
                f"Daily report attached: {report_path.name}"
            )
            msg.attach(MIMEText(body, "plain"))

            if report_path.is_file():
                part = MIMEApplication(report_path.read_bytes(), Name=report_path.name)
                part["Content-Disposition"] = f'attachment; filename="{report_path.name}"'
                msg.attach(part)

            envelope = [to_addr, cc_addr]
            server = smtplib.SMTP_SSL(
                smtp_server,
                smtp_port,
                context=ssl.create_default_context(),
                timeout=15,
            )
            try:
                server.login(email_addr, email_pwd)
                server.sendmail(email_addr, envelope, msg.as_string())
            finally:
                with contextlib.suppress(Exception):
                    server.quit()

            return {
                "status": "SENT",
                "to": to_addr,
                "cc": [cc_addr],
                "subject": subject,
                "attachment": str(report_path),
                "smtp_sent": True,
            }
        except Exception as exc:
            logger.warning("Final report email could not be sent: %s", exc)
            return {"status": "NOT_READY", "reason": f"{type(exc).__name__}: {exc}"}

    def finalize_run(self, *, reason: str = "MANUAL_STOP", status: str = "STOPPED") -> dict[str, Any]:
        self._sync_state()
        now_iso = _iso(self._now())
        with self._lock:
            if self._state.get("status") == "STOPPED" and self._state.get("report_path"):
                return {"finalized": False, "reason": "ALREADY_FINALIZED", "status": self.get_status()}
            self._state.update(
                status="STOPPING" if status == "STOPPED" else status,
                ended_at=now_iso,
                stopped_at=now_iso,
                current_company=None,
                stop_reason=reason,
                last_action="Generating final daily report",
            )
            self._save_state()
        report_path = self._write_report()
        final_email = self._send_final_report_email(report_path)
        self._clear_stop_signal()
        r = self._get_redis()
        if r is not None:
            try:
                r.delete(REDIS_KEY_OPERATOR_LOCK)
            except Exception:
                pass
        self._update(
            status=status,
            stopped_at=now_iso,
            report_path=str(report_path),
            final_report_email=final_email,
            last_action=f"Run finalized ({reason}); daily report generated",
        )
        return {"finalized": True, "status": self.get_status()}

    def _write_report(self) -> Path:
        self.report_dir.mkdir(parents=True, exist_ok=True)
        report_path = self.report_dir / f"Salesoorja_Daily_Report_{self._state['business_date']}.xlsx"
        workbook = Workbook()
        summary = workbook.active
        summary.title = "SUMMARY"
        summary.append(["Metric", "Value"])
        start = self._state.get("started_at")
        end = self._state.get("ended_at")
        duration = ""
        if start and end:
            duration = str(datetime.fromisoformat(end) - datetime.fromisoformat(start))
        summary_rows = [
            ("Run ID", self._state.get("run_id")),
            ("Mode", self._state.get("mode")),
            ("Run start", start),
            ("Run end", end),
            ("Run duration", duration),
            ("Stop reason", self._state.get("stop_reason")),
            ("Companies discovered", self._state["counters"]["companies_researched"]),
            ("Accounts qualified", self._state["counters"]["qualified_opportunities"]),
            ("People researched", self._state["counters"]["people_researched"]),
            ("People verified", self._state["counters"]["people_verified"]),
            ("Contacts enriched", self._state["counters"]["contacts_enriched"]),
            ("Emails sent", self._state["counters"]["emails_sent"]),
            ("Rediff handoffs queued", self._state["counters"]["rediff_handoffs"]),
            ("Follow-ups sent", self._state["counters"]["followups_sent"]),
            ("Replies", self._state["counters"]["replies"]),
            ("Enquiries", self._state["counters"]["enquiries"]),
            ("Reply rate", self._reply_rate()),
            ("Top opportunities", self._top_opportunities()),
            ("Reasons for HOLD", self._hold_reasons()),
            ("Provider usage", json.dumps(self._state["provider_usage"], sort_keys=True)),
            ("Errors", self._state["counters"]["failed"]),
            ("Recommendations for next run", self._recommendation()),
        ]
        for row in summary_rows:
            summary.append(row)
        for sheet_name in REPORT_SHEETS:
            sheet = workbook.create_sheet(sheet_name)
            rows = self._state["records"].get(sheet_name) or []
            headers = sorted({key for row in rows for key in row}) or ["status"]
            sheet.append(headers)
            for row in rows:
                sheet.append([self._excel_value(row.get(header)) for header in headers])
        workbook.save(report_path)
        return report_path

    def _reply_rate(self) -> float:
        sent = int(self._state["counters"].get("emails_sent", 0))
        return round((int(self._state["counters"].get("replies", 0)) / sent * 100), 2) if sent else 0.0

    def _top_opportunities(self) -> str:
        rows = self._state["records"].get("SENT", []) + self._state["records"].get("QUALIFIED_NOT_SENT", [])
        return "; ".join(str(row.get("company")) for row in rows[:5] if row.get("company")) or "None"

    def _hold_reasons(self) -> str:
        reasons: dict[str, int] = {}
        for row in self._state["records"].get("HOLD", []):
            reason = str(row.get("reason") or "Unknown")
            reasons[reason] = reasons.get(reason, 0) + 1
        return "; ".join(f"{reason}: {count}" for reason, count in reasons.items()) or "None"

    def _recommendation(self) -> str:
        if self._state["counters"].get("enquiries"):
            return "Prioritize enquiry response and pause normal follow-ups for meaningful replies."
        if self._state["counters"].get("held"):
            return "Resolve facility, person, or contact evidence gaps before the next run."
        return "Continue with unchanged deterministic quality gates."

    @staticmethod
    def _excel_value(value: Any) -> Any:
        if isinstance(value, (dict, list, tuple)):
            return json.dumps(value, default=str, sort_keys=True)
        return value

    def _build_final_email_dry_run(self, report_path: Path) -> dict[str, Any]:
        counters = self._state["counters"]
        return {
            "status": "DRY_RUN_READY",
            "to": "Bablu@oorjatechnical.org",
            "cc": ["piyushk@oorjatechnical.com"],
            "subject": (
                f"Salesoorja Daily Report - {self._state['business_date']} - "
                f"{counters['enquiries']} Enquiries / {counters['emails_sent']} Sent"
            ),
            "body": (
                f"Run completed with {counters['qualified_opportunities']} qualified opportunities, "
                f"{counters['emails_sent']} sent emails, {counters['replies']} replies, and "
                f"{counters['enquiries']} enquiries."
            ),
            "attachment": str(report_path),
            "smtp_sent": False,
        }

    _generate_final_report = _write_report


salesoorja_operator = SalesoorjaOperator()


def start_run(*, background: bool = True, use_celery: Optional[bool] = None) -> dict[str, Any]:
    return salesoorja_operator.start_run(background=background, use_celery=use_celery)


def stop_run(*, wait: bool = False) -> dict[str, Any]:
    return salesoorja_operator.stop_run(wait=wait)


def get_status() -> dict[str, Any]:
    return salesoorja_operator.get_status()


def finalize_run(*, reason: str = "MANUAL_STOP") -> dict[str, Any]:
    return salesoorja_operator.finalize_run(reason=reason)
