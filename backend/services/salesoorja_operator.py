"""Resumable one-click orchestration for the existing Salesoorja pipeline."""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from copy import deepcopy
from datetime import datetime, timezone
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

logger = logging.getLogger(__name__)

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
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._state = self._load_state()

    def _mode(self) -> str:
        return str(getattr(self.settings, "SALESOORJA_MODE", "TEST") or "TEST").strip().upper()

    def _new_state(self, *, preserve_history: bool = False) -> dict[str, Any]:
        now = self._now()
        previous = self._state if preserve_history else {}
        previous_day = str(previous.get("business_date") or "")
        business_date = now.astimezone(ZoneInfo("Asia/Kolkata")).date().isoformat()
        same_day = preserve_history and previous_day == business_date
        return {
            "version": 1,
            "run_id": previous.get("run_id") if same_day else f"operator-{uuid.uuid4().hex[:12]}",
            "business_date": business_date,
            "mode": self._mode(),
            "status": "STOPPED",
            "started_at": previous.get("started_at") if same_day else None,
            "ended_at": None,
            "last_checkpoint": previous.get("last_checkpoint") if same_day else None,
            "current_company": None,
            "last_action": "Ready",
            "last_error": None,
            "stop_reason": None,
            "report_path": previous.get("report_path") if same_day else None,
            "final_report_email": previous.get("final_report_email") if same_day else None,
            "counters": deepcopy(previous.get("counters")) if same_day else {key: 0 for key in COUNTER_KEYS},
            "provider_usage": deepcopy(previous.get("provider_usage")) if same_day else {key: 0 for key in PROVIDER_KEYS},
            "processed_accounts": list(previous.get("processed_accounts") or []) if same_day else [],
            "records": deepcopy(previous.get("records")) if same_day else {sheet: [] for sheet in REPORT_SHEETS},
            "transport_receipts": deepcopy(previous.get("transport_receipts")) if same_day else [],
        }

    def _load_state(self) -> dict[str, Any]:
        if self.state_path.is_file():
            try:
                loaded = json.loads(self.state_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    loaded.setdefault("counters", {key: 0 for key in COUNTER_KEYS})
                    loaded.setdefault("provider_usage", {key: 0 for key in PROVIDER_KEYS})
                    loaded.setdefault("processed_accounts", [])
                    loaded.setdefault("records", {sheet: [] for sheet in REPORT_SHEETS})
                    loaded.setdefault("transport_receipts", [])
                    for key in COUNTER_KEYS:
                        loaded["counters"].setdefault(key, 0)
                    for key in PROVIDER_KEYS:
                        loaded["provider_usage"].setdefault(key, 0)
                    for sheet in REPORT_SHEETS:
                        loaded["records"].setdefault(sheet, [])
                    if loaded.get("status") in {"RUNNING", "STOPPING", "WAITING"}:
                        loaded["status"] = "STOPPED"
                        loaded["last_action"] = "Recovered interrupted run; safe to resume"
                    return loaded
            except (OSError, ValueError, TypeError):
                logger.warning("Operator state could not be loaded; starting with a clean state")
        self._state = {}
        return self._new_state()

    def _save_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self._state, indent=2, default=str), encoding="utf-8")
        temporary.replace(self.state_path)

    def _update(self, **values: Any) -> None:
        with self._lock:
            self._state.update(values)
            self._state["last_checkpoint"] = _iso(self._now())
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

    def start_run(self, *, background: bool = True) -> dict[str, Any]:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return {"started": False, "reason": "ALREADY_RUNNING", "status": self.get_status()}
            mode = self._mode()
            if mode not in {"TEST", "PRODUCTION"}:
                return {"started": False, "reason": "INVALID_MODE", "errors": ["SALESOORJA_MODE must be TEST or PRODUCTION"]}
            production_errors = self._production_errors()
            if production_errors:
                return {"started": False, "reason": "PRODUCTION_GUARD_FAILED", "errors": production_errors}
            self._state = self._new_state(preserve_history=True)
            self._state.update(
                status="RUNNING",
                mode=mode,
                started_at=self._state.get("started_at") or _iso(self._now()),
                ended_at=None,
                stop_reason=None,
                last_error=None,
                last_action="Operator started",
            )
            self._stop_event.clear()
            self._save_state()
            if background:
                self._thread = threading.Thread(target=self._run_safely, name="salesoorja-operator", daemon=True)
                self._thread.start()
            else:
                self._run_safely()
        return {"started": True, "status": self.get_status()}

    def stop_run(self, *, wait: bool = False, timeout: float = 30.0) -> dict[str, Any]:
        self._stop_event.set()
        with self._lock:
            active = self._state.get("status") in {"RUNNING", "WAITING", "STOPPING"}
            if active:
                self._state["status"] = "STOPPING"
                self._state["last_action"] = "Stop requested; finishing safe in-progress work"
                self._save_state()
        thread = self._thread
        if wait and thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=timeout)
        if not active:
            return {"stopped": False, "reason": "NOT_RUNNING", "status": self.get_status()}
        return {"stopped": True, "status": self.get_status()}

    def get_status(self) -> dict[str, Any]:
        with self._lock:
            state = deepcopy(self._state)
        state.pop("records", None)
        receipts = state.pop("transport_receipts", [])
        state["transport_receipt_count"] = len(receipts)
        state["last_transport_receipt"] = receipts[-1] if receipts else None
        state["daily_send_target"] = int(getattr(self.settings, "DAILY_SEND_TARGET", 150))
        state["daily_send_max"] = int(getattr(self.settings, "DAILY_SEND_MAX", 250))
        state["start_time"] = str(getattr(self.settings, "SALESOORJA_START_TIME", "09:00"))
        state["end_time"] = str(getattr(self.settings, "SALESOORJA_END_TIME", "18:00"))
        state["production_guard_errors"] = self._production_errors()
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
            if self._mode() == "TEST":
                self._run_test_mode()
            else:
                self._run_production_loop()
        except Exception as exc:
            logger.exception("Salesoorja operator stopped after fatal error")
            self._append_record("ERRORS", {"stage": "operator", "error": type(exc).__name__, "detail": str(exc)})
            self._increment("failed")
            self._update(last_error=f"{type(exc).__name__}: {exc}")
            self.finalize_run(reason="FATAL_ERROR", status="ERROR")

    def _run_test_mode(self) -> None:
        max_cycles = max(1, int(getattr(self.settings, "SALESOORJA_TEST_MAX_CYCLES", 1)))
        for cycle in range(max_cycles):
            if self._stop_event.is_set():
                break
            self._update(last_action=f"Running synthetic dry-run cycle {cycle + 1}")
            self._process_synthetic_account()
        reason = "MANUAL_STOP" if self._stop_event.is_set() else "TEST_COMPLETE"
        self.finalize_run(reason=reason)

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
        with self._lock:
            self._state["processed_accounts"].append(account_key)
            self._state["current_company"] = None
            self._state["last_action"] = "Synthetic Rediff handoff verified with zero SMTP"
            self._save_state()

    def _local_now(self) -> datetime:
        return self._now().astimezone(ZoneInfo("Asia/Kolkata"))

    def _before_start(self) -> bool:
        start_hour, start_minute = _safe_time(getattr(self.settings, "SALESOORJA_START_TIME", "09:00"), "09:00")
        return self._local_now().time() < self._local_now().replace(hour=start_hour, minute=start_minute, second=0, microsecond=0).time()

    def _after_end(self) -> bool:
        end_hour, end_minute = _safe_time(getattr(self.settings, "SALESOORJA_END_TIME", "18:00"), "18:00")
        return self._local_now().time() >= self._local_now().replace(hour=end_hour, minute=end_minute, second=0, microsecond=0).time()

    def _outbound_total(self) -> int:
        counters = self._state["counters"]
        return int(counters.get("emails_sent", 0)) + int(counters.get("rediff_handoffs", 0))

    def _stop_reason(self) -> Optional[str]:
        if self._stop_event.is_set():
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
        return self._stop_event.wait(max(1, seconds))

    def _run_production_loop(self) -> None:
        last_inbox_poll = 0.0
        while True:
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
            processed = self._run_discovery_cycle()
            if not processed:
                self._update(last_action="No new qualifying accounts; waiting for next cycle")
            if self._interruptible_wait(int(getattr(self.settings, "SALESOORJA_CYCLE_INTERVAL_SECONDS", 300))):
                continue

    def _resolve_runtime_functions(self) -> tuple[Callable[..., dict[str, Any]], Callable[..., dict[str, Any]]]:
        if self._discovery_fn is None:
            from services.signal_discovery_engine import discover_new_calibration_opportunities

            self._discovery_fn = discover_new_calibration_opportunities
        if self._person_pipeline_fn is None:
            from services.decision_maker_discovery import run_full_discovery_pipeline

            self._person_pipeline_fn = run_full_discovery_pipeline
        return self._discovery_fn, self._person_pipeline_fn

    def _run_discovery_cycle(self) -> bool:
        if self._db_factory is None:
            raise RuntimeError("Synchronous database session is unavailable")
        discovery_fn, _ = self._resolve_runtime_functions()
        db = self._db_factory()
        processed = False
        try:
            self._update(last_action="Discovering fresh production opportunities")
            self._provider_call("Serper")
            discovery = discovery_fn(db=db, geography="PAN INDIA", limit=10)
            candidates = [
                item
                for item in discovery.get("candidates", [])
                if item.get("data_provenance") == "LIVE_SEARCH_DISCOVERED"
            ]
            for account in candidates:
                if self._stop_reason():
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
        self._update(current_company=company_name, last_action=f"Qualifying {company_name}")
        self._increment("companies_researched")
        try:
            if float(account.get("icp_score") or 0) < 85:
                self._hold_account(account, "ICP score below 85")
                return
            self._increment("qualified_opportunities")
            _, pipeline_fn = self._resolve_runtime_functions()
            result = pipeline_fn(
                company_id=int(account["company_id"]),
                db=db,
                signal_type=account.get("signal_type"),
                max_apollo_enrichments=3,
                max_queries=6,
                before_apollo=lambda: not self._after_end() and self._outbound_total() < int(getattr(self.settings, "DAILY_SEND_MAX", 250)),
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
                self._hold_account(account, "No candidate passed current-employment, facility, authority, and verified-email gates")
                return
            record = self._build_production_record(account, candidate, result)
            personalized = self._personalization.personalize_record(record, force_provider="AUTO")
            provider = str(personalized.get("llm_provider_used") or "")
            if provider.startswith("DEEPSEEK"):
                self._provider_call("DeepSeek")
            elif provider.startswith("GEMINI"):
                self._provider_call("Gemini")
            quality_score = float(personalized.get("quality_score") or 0)
            if personalized.get("status") != "VALIDATED" or quality_score < 85:
                self._hold_account(account, f"Personalization quality {quality_score:.1f} below 85")
                return
            record = self._personalization.enrich_record_for_rediff(record, personalized)
            record["PERSONALIZATION_STATUS"] = personalized["status"]
            record["PERSONALIZATION_SCORE"] = quality_score
            self._provider_call("Rediff")
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
            if handoff.get("status") == SENT and handoff.get("smtp_sent"):
                self._increment("emails_sent")
                self._append_record("SENT", row)
            elif handoff.get("status") == QUEUED:
                self._increment("rediff_handoffs")
                self._append_record("QUALIFIED_NOT_SENT", row)
            else:
                self._append_record("QUALIFIED_NOT_SENT", row)
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
        facility = candidate.candidate_facility or raw.get("location") or account.get("city") or ""
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
            "trigger_date": self._state["business_date"],
            "calibration_opportunity": opportunity,
            "reasoning": opportunity,
            "icp_score": float(account.get("icp_score") or 0),
            "facility_verified": True,
            "contact_verified": True,
            "provenance": "REAL",
            "evidence": {
                "trigger_current": {"verified": True},
                "exact_facility": {"verified": True, "address": facility, "linkage_strength": "DIRECT"},
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
        if self._mode() != "PRODUCTION" or self._db_factory is None:
            return
        if self._imap_poll_fn is None:
            from services.imap_service import poll_imap_inbox

            self._imap_poll_fn = poll_imap_inbox
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
        finally:
            db.close()

    def finalize_run(self, *, reason: str = "MANUAL_STOP", status: str = "STOPPED") -> dict[str, Any]:
        with self._lock:
            if self._state.get("status") == "STOPPED" and self._state.get("report_path"):
                return {"finalized": False, "reason": "ALREADY_FINALIZED", "status": self.get_status()}
            self._state.update(
                status="STOPPING" if status == "STOPPED" else status,
                ended_at=_iso(self._now()),
                current_company=None,
                stop_reason=reason,
                last_action="Generating final daily report",
            )
            self._save_state()
        report_path = self._write_report()
        final_email = self._build_final_email_dry_run(report_path)
        self._update(
            status=status,
            report_path=str(report_path),
            final_report_email=final_email,
            last_action="Run finalized; report email prepared in dry-run only",
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


salesoorja_operator = SalesoorjaOperator()


def start_run(*, background: bool = True) -> dict[str, Any]:
    return salesoorja_operator.start_run(background=background)


def stop_run(*, wait: bool = False) -> dict[str, Any]:
    return salesoorja_operator.stop_run(wait=wait)


def get_status() -> dict[str, Any]:
    return salesoorja_operator.get_status()


def finalize_run(*, reason: str = "MANUAL_STOP") -> dict[str, Any]:
    return salesoorja_operator.finalize_run(reason=reason)
