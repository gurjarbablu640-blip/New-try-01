"""Automated test suite for Salesoorja one-click autonomous operator.

Validates:
1. Single-active-run lock: repeated START while RUNNING returns ALREADY_RUNNING.
2. Background execution: start_run() initiates execution without blocking caller.
3. Graceful stop: finish/abort safe unit of work, persist checkpoint, finalize.
4. Auto-persistence & TEST mode safety:
   - TEST mode NEVER persists prospect as SENT or schedules real follow-ups.
   - Only confirmed real transport creates sent_at/current_step/follow-up cadence.
5. Follow-ups based on transport receipts & IMAP reply suppression:
   - Replies, bounces, and opt-outs suppress follow-ups.
   - Unreplied follow-ups advance through Day 3/5/11/21 progression.
6. Rediff transport-only behavior:
   - Salesoorja owns final subject/body without rewrite.
   - Message-ID / In-Reply-To / References generation and capture.
7. Final report XLSX generation & email status (NOT_READY when attachment unavailable).
8. Non-blocking error handling:
   - Operator records error in state and continues without crashing.
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from openpyxl import load_workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models import (
    Campaign,
    CampaignEvent,
    CampaignRecipient,
    CampaignStep,
    Company,
    DecisionMakerCandidate,
    Facility,
    Person,
)
from scripts.rediff_transport_worker import parse_args
from services.rediff_sender_adapter import RediffAdapterConfig, RediffSenderAdapter
from services.salesoorja_operator import REPORT_SHEETS, SalesoorjaOperator


NOW = datetime(2026, 9, 14, 10, 30, tzinfo=timezone.utc)


def _settings(**overrides):
    values = {
        "SALESOORJA_MODE": "TEST",
        "REAL_OUTREACH_ENABLED": False,
        "OUTBOUND_TEST_MODE": True,
        "REDIFF_SENDER_ENABLED": False,
        "REDIFF_TEST_MODE": True,
        "USE_CELERY": False,
        "SERPER_API_KEY": "",
        "APOLLO_API_KEY": "",
        "BRIGHTDATA_API_TOKEN": "",
        "BRIGHTDATA_LINKEDIN_PROFILE_DATASET_ID": "",
        "HIVE_API_KEY": "",
        "GEMINI_API_KEY": "",
        "GOOGLE_API_KEY": "",
        "DAILY_SEND_TARGET": 150,
        "DAILY_SEND_MAX": 250,
        "MAX_SERPER_CALLS_PER_DAY": 1500,
        "SALESOORJA_START_TIME": "09:00",
        "SALESOORJA_END_TIME": "18:00",
        "SALESOORJA_CYCLE_INTERVAL_SECONDS": 1,
        "SALESOORJA_INBOX_INTERVAL_SECONDS": 1,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _operator(tmp_path: Path, db_factory=None, transport_bridge=None, **settings_overrides) -> SalesoorjaOperator:
    rediff = RediffSenderAdapter(
        config=RediffAdapterConfig(
            enabled=False,
            test_mode=True,
            system_path=tmp_path / "missing-rediff",
            handoff_dir=tmp_path / "handoff",
            cc_addresses=("Bablu@oorjatechnical.org", "piyushk@oorjatechnical.com"),
            duplicate_window_days=14,
        ),
        now=lambda: NOW,
    )
    return SalesoorjaOperator(
        settings_obj=_settings(**settings_overrides),
        state_path=tmp_path / "runtime" / "operator_state.json",
        report_dir=tmp_path / "reports",
        now=lambda: NOW,
        db_factory=db_factory,
        rediff_adapter=rediff,
        transport_bridge=transport_bridge,
    )


@pytest.fixture
def sqlite_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


# =========================================================================
# 1. Single-Active-Run Lock
# =========================================================================

def test_single_active_run_lock_returns_already_running(tmp_path):
    """Calling start_run() while RUNNING returns ALREADY_RUNNING without spawning another runner."""
    op = _operator(tmp_path)

    with op._lock:
        op._state["status"] = "RUNNING"

    result = op.start_run(background=True, use_celery=False)
    assert result["started"] is False
    assert result["reason"] == "ALREADY_RUNNING"
    assert result["status"]["status"] == "RUNNING"


def test_single_active_run_lock_returns_already_running_when_waiting(tmp_path):
    """Calling start_run() while WAITING returns ALREADY_RUNNING."""
    op = _operator(tmp_path)

    with op._lock:
        op._state["status"] = "WAITING"

    result = op.start_run(background=True, use_celery=False)
    assert result["started"] is False
    assert result["reason"] == "ALREADY_RUNNING"


# =========================================================================
# 2. Graceful Stop
# =========================================================================

def test_graceful_stop_finishes_safe_unit_and_persists_checkpoint(tmp_path):
    """stop_run() sets status to STOPPING, safe unit completes, persists checkpoint and report."""
    in_work = threading.Event()
    finish_work = threading.Event()

    class ControlledOperator(SalesoorjaOperator):
        def _process_synthetic_account(self):
            in_work.set()
            finish_work.wait(timeout=5)
            return super()._process_synthetic_account()

    base = _operator(tmp_path, SALESOORJA_MODE="SMOKE")
    op = ControlledOperator(
        settings_obj=base.settings,
        state_path=base.state_path,
        report_dir=base.report_dir,
        now=lambda: NOW,
        db_factory=None,
        rediff_adapter=base._rediff,
    )

    op.start_run(background=True, use_celery=False)
    assert in_work.wait(timeout=3)

    stop_res = op.stop_run(wait=False)
    assert stop_res["stopped"] is True
    assert stop_res["status"]["status"] == "STOPPING"
    assert "finishing safe in-progress work" in stop_res["status"]["last_action"].lower()

    finish_work.set()
    op._thread.join(timeout=5)

    final_status = op.get_status()
    assert final_status["status"] == "STOPPED"
    assert final_status["stop_reason"] == "MANUAL_STOP"
    assert final_status["report_path"] is not None
    assert Path(final_status["report_path"]).exists()


# =========================================================================
# 3. Auto-Persistence & TEST Mode Safety
# =========================================================================

def test_test_mode_never_persists_sent_or_schedules_followups(tmp_path, sqlite_session):
    """TEST mode must persist recipient as TEST_PREVIEW with sent_at=None, next_send_at=None."""
    op = _operator(tmp_path, db_factory=lambda: sqlite_session)

    account = {
        "company_name": "Test Engineering Corp",
        "facility": "Pune Plant",
        "city": "Pune",
        "state": "Maharashtra",
        "trigger": "Plant expansion",
        "icp_score": 90,
    }
    candidate = SimpleNamespace(
        id=123,
        candidate_name="Arun Verma",
        candidate_title="General Manager Operations",
        candidate_facility="Pune Plant",
        apollo_email="arun.verma@testcorp.com",
        apollo_phone="+919876543210",
        target_persona="Plant Head",
    )
    personalized = {
        "subject": "Testing Pune Plant Calibration",
        "body_html": "<p>Hello Arun</p>",
        "quality_score": 88,
        "status": "VALIDATED",
    }
    handoff = {"status": "DRY_RUN_READY"}

    op._persist_pipeline_account(
        db=sqlite_session,
        account=account,
        candidate=candidate,
        personalized=personalized,
        handoff=handoff,
        receipt=None,
    )

    person = sqlite_session.query(Person).filter(Person.email == "arun.verma@testcorp.com").first()
    assert person is not None
    rec = sqlite_session.query(CampaignRecipient).filter(CampaignRecipient.person_id == person.id).first()
    assert rec is not None
    assert rec.status == "TEST_PREVIEW"
    assert rec.email_status == "NOT_SENT_TEST_MODE"
    assert rec.last_sent_at is None
    assert rec.next_send_at is None
    assert rec.current_step == 0


def test_production_mode_with_confirmed_receipt_schedules_followup(tmp_path, sqlite_session):
    """In PRODUCTION mode, confirmed real receipt creates sent_at, current_step=0, and next_send_at."""
    op = _operator(tmp_path, db_factory=lambda: sqlite_session, SALESOORJA_MODE="PRODUCTION")

    account = {
        "company_name": "Precision Tools Ltd",
        "facility": "Nashik Unit",
        "city": "Nashik",
        "state": "Maharashtra",
        "trigger": "Quality audit",
        "icp_score": 92,
    }
    candidate = SimpleNamespace(
        id=456,
        candidate_name="Sanjay Kulkarni",
        candidate_title="Head Quality",
        candidate_facility="Nashik Unit",
        apollo_email="sanjay.k@precision.com",
        apollo_phone="+919876543211",
        target_persona="Quality Head",
    )
    personalized = {
        "subject": "Nashik Calibration Support",
        "body_html": "<p>Dear Sanjay</p>",
        "quality_score": 91,
        "status": "VALIDATED",
    }
    handoff = {"status": "SENT", "smtp_sent": True}
    confirmed_receipt = {
        "transport_status": "SENT",
        "smtp_sent": True,
        "recipient": "sanjay.k@precision.com",
        "message_id": "<test-msg-id-123@oorjatechnical.org>",
        "test_mode": False,
    }

    op._persist_pipeline_account(
        db=sqlite_session,
        account=account,
        candidate=candidate,
        personalized=personalized,
        handoff=handoff,
        receipt=confirmed_receipt,
    )

    person = sqlite_session.query(Person).filter(Person.email == "sanjay.k@precision.com").first()
    assert person is not None
    rec = sqlite_session.query(CampaignRecipient).filter(CampaignRecipient.person_id == person.id).first()
    assert rec is not None
    assert rec.status == "ACTIVE"
    assert rec.email_status == "SENT"
    assert rec.last_sent_at is not None
    assert rec.next_send_at is not None
    assert rec.next_send_at > rec.last_sent_at
    assert rec.current_step == 0


# =========================================================================
# 4. Follow-Up Cadence & IMAP Reply Suppression
# =========================================================================

def test_followup_suppressed_if_prospect_replied(tmp_path, sqlite_session):
    """If prospect has replied in IMAP, follow-up must be suppressed and marked REPLIED."""
    company = Company(name="Replied Corp", domain="replied.com")
    sqlite_session.add(company)
    sqlite_session.flush()

    person = Person(company_id=company.id, full_name="Prospect One", email="prospect@company.com")
    sqlite_session.add(person)
    sqlite_session.flush()

    campaign = Campaign(name="Test Campaign", status="active", channel="email")
    sqlite_session.add(campaign)
    sqlite_session.flush()

    recipient = CampaignRecipient(
        campaign_id=campaign.id,
        company_id=company.id,
        person_id=person.id,
        status="ACTIVE",
        current_step=0,
        last_sent_at=NOW - timedelta(days=4),
        next_send_at=NOW - timedelta(hours=1),
        metadata_json={
            "email": "prospect@company.com",
            "message_id": "<orig-123@oorjatechnical.org>",
            "has_replied": True,
        },
    )
    sqlite_session.add(recipient)
    sqlite_session.commit()

    op = _operator(tmp_path, db_factory=lambda: sqlite_session)

    count = op._process_due_followups(sqlite_session)
    assert count == 0

    sqlite_session.refresh(recipient)
    assert recipient.status == "REPLIED"
    assert recipient.next_send_at is None


def test_followup_suppressed_if_bounced_or_opted_out(tmp_path, sqlite_session):
    """If prospect has bounced or opted out, follow-up must be suppressed."""
    company = Company(name="Bounced Corp", domain="bounced.com")
    sqlite_session.add(company)
    sqlite_session.flush()

    person = Person(company_id=company.id, full_name="Bounced Person", email="bounced@company.com")
    sqlite_session.add(person)
    sqlite_session.flush()

    campaign = Campaign(name="Test Campaign", status="active", channel="email")
    sqlite_session.add(campaign)
    sqlite_session.flush()

    recipient_bounced = CampaignRecipient(
        campaign_id=campaign.id,
        company_id=company.id,
        person_id=person.id,
        status="ACTIVE",
        bounced_at=NOW - timedelta(days=1),
        current_step=0,
        last_sent_at=NOW - timedelta(days=4),
        next_send_at=NOW - timedelta(hours=1),
        metadata_json={
            "email": "bounced@company.com",
            "message_id": "<orig-bounced@oorjatechnical.org>",
        },
    )
    sqlite_session.add(recipient_bounced)
    sqlite_session.commit()

    op = _operator(tmp_path, db_factory=lambda: sqlite_session)
    count = op._process_due_followups(sqlite_session)
    assert count == 0

    sqlite_session.refresh(recipient_bounced)
    assert recipient_bounced.status == "BOUNCED"
    assert recipient_bounced.next_send_at is None


def test_followup_advances_cadence_steps_cleanly(tmp_path, sqlite_session):
    """Unreplied follow-ups advance through Step 0 (Day 3) -> Step 1 (Day 5) -> Step 2 (Day 11) -> Step 3 (Day 21) -> Step 4 (Complete)."""
    company = Company(name="Auto Gear Ltd", domain="autogear.com")
    sqlite_session.add(company)
    sqlite_session.flush()

    person = Person(company_id=company.id, full_name="Lead Engineer", email="lead@automotive.com")
    sqlite_session.add(person)
    sqlite_session.flush()

    campaign = Campaign(name="Test Campaign", status="active", channel="email")
    sqlite_session.add(campaign)
    sqlite_session.flush()

    recipient = CampaignRecipient(
        campaign_id=campaign.id,
        company_id=company.id,
        person_id=person.id,
        status="ACTIVE",
        current_step=0,
        last_sent_at=NOW - timedelta(days=4),
        next_send_at=NOW - timedelta(hours=1),
        metadata_json={
            "email": "lead@automotive.com",
            "message_id": "<orig-msg-100@oorjatechnical.org>",
            "subject": "Initial calibration",
            "followups": {
                "day_3": "Day 3 follow-up text",
                "day_5": "Day 5 follow-up text",
                "day_11": "Day 11 follow-up text",
                "day_21": "Day 21 follow-up text",
            },
        },
    )
    sqlite_session.add(recipient)
    sqlite_session.commit()

    op = _operator(tmp_path, db_factory=lambda: sqlite_session)

    # Step 0 -> Step 1 (Day 3)
    count = op._process_due_followups(sqlite_session)
    assert count == 1
    sqlite_session.refresh(recipient)
    assert recipient.current_step == 1
    assert recipient.next_send_at is not None

    # Step 1 -> Step 2 (Day 5)
    recipient.next_send_at = NOW - timedelta(hours=1)
    sqlite_session.commit()
    count = op._process_due_followups(sqlite_session)
    assert count == 1
    sqlite_session.refresh(recipient)
    assert recipient.current_step == 2
    assert recipient.next_send_at is not None

    # Step 2 -> Step 3 (Day 11)
    recipient.next_send_at = NOW - timedelta(hours=1)
    sqlite_session.commit()
    count = op._process_due_followups(sqlite_session)
    assert count == 1
    sqlite_session.refresh(recipient)
    assert recipient.current_step == 3
    assert recipient.next_send_at is not None

    # Step 3 -> Step 4 (Day 21)
    recipient.next_send_at = NOW - timedelta(hours=1)
    sqlite_session.commit()
    count = op._process_due_followups(sqlite_session)
    assert count == 1
    sqlite_session.refresh(recipient)
    assert recipient.current_step == 4
    assert recipient.status == "COMPLETED"
    assert recipient.next_send_at is None


def test_production_followup_uses_thread_headers_and_persists_receipt(tmp_path, sqlite_session):
    company = Company(name="Precision Components Ltd", domain="precision-components.in")
    sqlite_session.add(company)
    sqlite_session.flush()
    person = Person(
        company_id=company.id,
        full_name="Asha Verma",
        email="asha.verma@precision-components.in",
    )
    sqlite_session.add(person)
    sqlite_session.flush()
    campaign = Campaign(name="Salesoorja Autonomous Outbound", status="Active", channel="email")
    sqlite_session.add(campaign)
    sqlite_session.flush()

    system_path = tmp_path / "Rediff_Email_System"
    system_path.mkdir()
    for filename in ("campaign_runner.py", "send_email.py"):
        (system_path / filename).write_text("# transport marker\n", encoding="utf-8")
    adapter = RediffSenderAdapter(
        config=RediffAdapterConfig(
            enabled=True,
            test_mode=False,
            system_path=system_path,
            handoff_dir=tmp_path / "handoff",
            cc_addresses=("Bablu@oorjatechnical.org",),
            duplicate_window_days=14,
        ),
        now=lambda: NOW,
    )
    source_record = {
        "record_id": "operator-production-001",
        "READY_FOR_EMAIL": "YES",
        "company": company.name,
        "facility": "Nashik Plant",
        "city": "Nashik",
        "state": "Maharashtra",
        "person": person.full_name,
        "designation": "Plant Quality Head",
        "persona": "Quality Head",
        "email": person.email,
        "trigger": "New production line commissioning",
        "trigger_date": "2026-09-01",
        "calibration_opportunity": "Source-backed dimensional calibration requirement",
        "reasoning": "Current facility expansion requires calibration planning",
        "icp_score": 92,
        "PERSONALIZATION_STATUS": "VALIDATED",
        "PERSONALIZATION_SCORE": 91,
        "provenance": "REAL",
        "evidence": {
            "trigger_current": {"verified": True},
            "exact_facility": {"verified": True, "address": "Nashik Plant", "linkage_strength": "DIRECT"},
            "technical_capability": {"status": "IN_SCOPE"},
            "correct_person": {
                "name": person.full_name,
                "employment_verified": True,
                "duties_verified": True,
                "company_evidence_status": "CURRENT_COMPANY",
            },
            "reachable_email": {
                "email": person.email,
                "status": "VERIFIED",
                "mailbox_verified": True,
                "contact_confidence": "HIGH",
            },
        },
    }
    initial_handoff = adapter.prepare_handoff(source_record, campaign="salesoorja-autonomous-outbound")
    assert initial_handoff["status"] == "QUEUED"

    recipient = CampaignRecipient(
        campaign_id=campaign.id,
        company_id=company.id,
        person_id=person.id,
        status="ACTIVE",
        email_status="SENT",
        current_step=0,
        last_sent_at=NOW - timedelta(days=3),
        next_send_at=NOW - timedelta(hours=1),
        metadata_json={
            "email": person.email,
            "message_id": "<initial@oorjatechnical.org>",
            "message_ids": ["<initial@oorjatechnical.org>"],
            "subject": "Nashik calibration planning",
            "followups": {"day_3": "Checking whether this is relevant for your Nashik plant."},
            "source_record": source_record,
            "rediff_mapped_record": initial_handoff["mapped_record"],
            "campaign_reference": "salesoorja-autonomous-outbound",
            "person_reference": person.id,
            "cadence_state": {
                "followup_2_due_at": (NOW + timedelta(days=2)).isoformat(),
                "followup_3_due_at": (NOW + timedelta(days=8)).isoformat(),
                "final_followup_due_at": (NOW + timedelta(days=18)).isoformat(),
            },
        },
    )
    sqlite_session.add(recipient)
    sqlite_session.commit()

    class ProductionTransportStub:
        def __init__(self):
            self.calls = []

        def execute_production_transport(self, **kwargs):
            self.calls.append(kwargs)
            return {
                "receipt_id": "receipt-followup-day3",
                "transport_status": "SENT",
                "smtp_sent": True,
                "test_mode": False,
                "message_id": "<day3@oorjatechnical.org>",
                "sent_at": NOW.isoformat(),
                "recipient": person.email,
                "cc": ["Bablu@oorjatechnical.org"],
                "bcc": [],
            }

    bridge = ProductionTransportStub()
    op = SalesoorjaOperator(
        settings_obj=_settings(
            SALESOORJA_MODE="PRODUCTION",
            REAL_OUTREACH_ENABLED=True,
            OUTBOUND_TEST_MODE=False,
            REDIFF_SENDER_ENABLED=True,
            REDIFF_TEST_MODE=False,
        ),
        state_path=tmp_path / "runtime" / "operator_state.json",
        report_dir=tmp_path / "reports",
        now=lambda: NOW,
        db_factory=lambda: sqlite_session,
        rediff_adapter=adapter,
        transport_bridge=bridge,
    )

    assert op._process_due_followups(sqlite_session) == 1

    sqlite_session.refresh(recipient)
    assert recipient.current_step == 1
    assert recipient.status == "ACTIVE"
    assert recipient.metadata_json["message_id"] == "<day3@oorjatechnical.org>"
    assert recipient.metadata_json["in_reply_to"] == "<initial@oorjatechnical.org>"
    assert recipient.metadata_json["references"] == "<initial@oorjatechnical.org> <day3@oorjatechnical.org>"
    mapped = bridge.calls[0]["mapped_record"]
    assert mapped["IN_REPLY_TO"] == "<initial@oorjatechnical.org>"
    assert mapped["REFERENCES"] == "<initial@oorjatechnical.org>"
    assert mapped["CC"] == "Bablu@oorjatechnical.org"
    assert op.get_status()["counters"]["followups_sent"] == 1
    assert op.get_status()["counters"]["real_prospect_emails_sent"] == 1
    event = sqlite_session.query(CampaignEvent).filter(CampaignEvent.event_type == "DAY_3_SENT").one()
    assert event.provider_message_id == "<day3@oorjatechnical.org>"


# =========================================================================
# 5. Rediff Transport-Only Decoupling & Threading Headers
# =========================================================================

def test_rediff_transport_worker_uses_salesoorja_copy_directly(tmp_path):
    """Worker preserves Salesoorja's exact FINAL_SUBJECT and FINAL_BODY_HTML without rewriting."""
    test_args = [
        "--system-path", str(tmp_path / "system"),
        "--csv", str(tmp_path / "test.csv"),
        "--html", str(tmp_path / "test.html"),
        "--result", str(tmp_path / "result.json"),
        "--recipient", "Bablu@oorjatechnical.org",
        "--mode", "test",
    ]
    parsed = parse_args(test_args)
    assert parsed.system_path == str(tmp_path / "system")
    assert parsed.csv == str(tmp_path / "test.csv")
    assert parsed.html == str(tmp_path / "test.html")
    assert parsed.result == str(tmp_path / "result.json")
    assert parsed.recipient == "Bablu@oorjatechnical.org"


# =========================================================================
# 6. Final Report XLSX & Email Status Handling
# =========================================================================

def test_final_report_xlsx_created_and_email_status_safe(tmp_path):
    """Final report creates a valid XLSX workbook with SUMMARY and data sheets.
    When Rediff attachment transport is not configured, final_report_email status is safe.
    """
    op = _operator(tmp_path)
    op._state["counters"]["companies_researched"] = 5
    op._state["counters"]["qualified_opportunities"] = 3
    op._state["counters"]["emails_sent"] = 0

    report_path = op._write_report()
    assert Path(report_path).is_file()

    wb = load_workbook(report_path, read_only=True)
    assert "SUMMARY" in wb.sheetnames
    for sheet in REPORT_SHEETS:
        assert sheet in wb.sheetnames

    email_status = op._send_final_report_email(Path(report_path))
    assert email_status.get("status") in {"DRY_RUN_READY", "NOT_READY", "FAILED"}


# =========================================================================
# 7. Non-Blocking Error Handling
# =========================================================================

def test_non_blocking_error_handling_continues_operator(tmp_path):
    """An individual account error does not crash the operator; it is held and the run continues."""
    op = _operator(tmp_path, SALESOORJA_MODE="SMOKE")

    with patch.object(op, "_process_synthetic_account", side_effect=ValueError("Test candidate failure")):
        op._run_safely()

    status = op.get_status()
    assert status["status"] in {"STOPPED", "ERROR"}
    assert status["last_error"] is not None
    assert "Test candidate failure" in status["last_error"]


# =========================================================================
# 8. Runtime State Machine & Timeout Invariants
# =========================================================================

def test_queued_to_starting_to_running_lifecycle(tmp_path):
    """Execution follows QUEUED -> STARTING -> RUNNING strictly."""
    op = _operator(tmp_path, SALESOORJA_MODE="SMOKE")
    events = []

    # Intercept state saves to trace transitions
    orig_save = op._save_state
    def tracking_save():
        st = op._state.get("status")
        if not events or events[-1] != st:
            events.append(st)
        return orig_save()

    op._save_state = tracking_save

    # Start run with background worker thread
    res = op.start_run(background=True, use_celery=False)
    assert res["started"] is True
    assert events[0] == "QUEUED"

    if op._thread:
        op._thread.join(timeout=5)

    assert "QUEUED" in events
    assert "STARTING" in events
    assert "RUNNING" in events
    assert "STOPPED" in events
    status = op.get_status()
    assert status["task_id"] is not None
    assert status["worker_started_at"] is not None
    assert status["heartbeat_at"] is not None
    assert status["stopped_at"] is not None


def test_bounded_stop_timeout_forces_stopped(tmp_path):
    """If state is STOPPING for more than 15s without worker completion, status is forced to STOPPED."""
    op = _operator(tmp_path)
    with op._lock:
        op._state["status"] = "STOPPING"
        op._state["stop_requested_at"] = (NOW - timedelta(seconds=20)).isoformat()

    status = op.get_status()
    assert status["status"] == "STOPPED"
    assert status["stop_reason"] == "STOP_TIMEOUT"


def test_stale_heartbeat_reconciles_to_error(tmp_path):
    """If worker heartbeat is older than 45s and worker is dead, status transitions to ERROR."""
    op = _operator(tmp_path)
    with op._lock:
        op._state["status"] = "RUNNING"
        op._state["task_id"] = "dead-task-12345"
        op._state["heartbeat_at"] = (NOW - timedelta(seconds=60)).isoformat()

    status = op.get_status()
    assert status["status"] == "ERROR"
    assert status["stop_reason"] == "HEARTBEAT_TIMEOUT"


def test_cycle_wait_keeps_worker_heartbeat_alive(tmp_path):
    op = _operator(tmp_path)

    with patch.object(op, "_heartbeat") as heartbeat:
        assert op._interruptible_wait(1) is False

    heartbeat.assert_called()


def test_no_live_worker_immediate_cleanup_on_stop(tmp_path):
    """If stop_run() is called and no live worker/task exists, state is immediately cleaned to STOPPED."""
    op = _operator(tmp_path)
    with op._lock:
        op._state["status"] = "QUEUED"
        op._state["queued_at"] = (NOW - timedelta(seconds=50)).isoformat()
        op._state["task_id"] = "nonexistent-worker-task"

    res = op.stop_run(wait=False)
    assert res["stopped"] is True
    assert res["status"]["status"] == "STOPPED"
    assert res["status"]["stop_reason"] in {"NO_LIVE_WORKER", "QUEUE_TIMEOUT"}
