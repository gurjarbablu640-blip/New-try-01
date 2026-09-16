"""Tests for PostgreSQL Funnel Workflow Manager.

Verifies:
- Durable PostgreSQL state and stage transitions
- Worker lease acquisition and expiration recovery (worker crash recovery)
- Idempotent enqueue (duplicate prevention)
- Atomic stage transitions
- Stage backpressure enforcement
- Send-ready buffer retrieval
"""
import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models.company import Company
from models.funnel_work_item import (
    FunnelWorkItem,
    STAGE_DISCOVERY_CANDIDATE,
    STAGE_FACILITY_VERIFICATION,
    STAGE_PERSON_RESEARCH,
    STAGE_SEND_READY,
    STAGE_HOLD,
    STATUS_PENDING,
    STATUS_IN_PROGRESS,
    STATUS_HELD,
)
from services.funnel_workflow_manager import FunnelWorkflowManager


@pytest.fixture
def workflow_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        yield db
    finally:
        db.close()


def test_enqueue_candidate_idempotency(workflow_db):
    mgr = FunnelWorkflowManager()
    item1, created1 = mgr.enqueue_candidate(
        workflow_db,
        company_id=101,
        source_query_id=1,
        payload={"company_name": "Acme Motors"},
    )
    assert created1 is True
    assert item1.current_stage == STAGE_DISCOVERY_CANDIDATE
    assert item1.status == STATUS_PENDING

    # Duplicate enqueue with same key must return existing item and created=False
    item2, created2 = mgr.enqueue_candidate(
        workflow_db,
        company_id=101,
        source_query_id=1,
        payload={"company_name": "Acme Motors"},
    )
    assert created2 is False
    assert item2.id == item1.id


def test_acquire_lease_and_atomicity(workflow_db):
    mgr = FunnelWorkflowManager()
    item, _ = mgr.enqueue_candidate(
        workflow_db,
        company_id=102,
        source_query_id=2,
        payload={"company_name": "Bharat EV"},
    )

    leased = mgr.acquire_lease(workflow_db, stage=STAGE_DISCOVERY_CANDIDATE, worker_id="worker-1", limit=1)
    assert len(leased) == 1
    assert leased[0].id == item.id
    assert leased[0].status == STATUS_IN_PROGRESS
    assert leased[0].locked_by == "worker-1"
    assert leased[0].attempt_count == 1

    # Second worker trying to lease same item must find 0 available items
    leased_second = mgr.acquire_lease(workflow_db, stage=STAGE_DISCOVERY_CANDIDATE, worker_id="worker-2", limit=1)
    assert len(leased_second) == 0


def test_worker_crash_lease_recovery(workflow_db):
    mgr = FunnelWorkflowManager()
    item, _ = mgr.enqueue_candidate(
        workflow_db,
        company_id=103,
        source_query_id=3,
        payload={"company_name": "Tata Precision"},
    )

    # Worker acquires lease with past expiry (simulating crash + timeout)
    mgr.acquire_lease(workflow_db, stage=STAGE_DISCOVERY_CANDIDATE, worker_id="crashed-worker", limit=1, lease_duration_seconds=-10)

    # Expired lease must be auto-recovered on next acquisition
    recovered = mgr.recover_expired_leases(workflow_db)
    assert recovered == 1

    refreshed = workflow_db.query(FunnelWorkItem).filter(FunnelWorkItem.id == item.id).first()
    assert refreshed.status == STATUS_PENDING
    assert refreshed.locked_by is None

    # New worker can now lease the item
    new_leased = mgr.acquire_lease(workflow_db, stage=STAGE_DISCOVERY_CANDIDATE, worker_id="new-worker", limit=1)
    assert len(new_leased) == 1
    assert new_leased[0].id == item.id


def test_transactional_stage_transition(workflow_db):
    mgr = FunnelWorkflowManager()
    item, _ = mgr.enqueue_candidate(
        workflow_db,
        company_id=104,
        source_query_id=4,
        payload={"company_name": "Mahindra Aerospace"},
    )
    mgr.acquire_lease(workflow_db, stage=STAGE_DISCOVERY_CANDIDATE, worker_id="worker-1")

    # Transition to FACILITY_VERIFICATION
    updated = mgr.transition_stage(
        workflow_db,
        item.id,
        next_stage=STAGE_FACILITY_VERIFICATION,
        status=STATUS_PENDING,
        payload_updates={"facility_verified": True},
    )
    assert updated.current_stage == STAGE_FACILITY_VERIFICATION
    assert updated.status == STATUS_PENDING
    assert updated.locked_by is None
    assert updated.payload_json.get("facility_verified") is True


def test_hold_item(workflow_db):
    mgr = FunnelWorkflowManager()
    item, _ = mgr.enqueue_candidate(
        workflow_db,
        company_id=105,
        source_query_id=5,
        payload={"company_name": "Generic Portal"},
    )

    held = mgr.hold_item(workflow_db, item.id, reason="Entity truth validation failed")
    assert held.current_stage == STAGE_HOLD
    assert held.status == STATUS_HELD
    assert held.payload_json.get("hold_reason") == "Entity truth validation failed"


def test_stage_backpressure(workflow_db):
    custom_limits = {STAGE_DISCOVERY_CANDIDATE: 2}
    mgr = FunnelWorkflowManager(stage_limits=custom_limits)

    # 0 items -> backpressure inactive
    assert mgr.is_backpressure_active(workflow_db, STAGE_DISCOVERY_CANDIDATE) is False

    mgr.enqueue_candidate(workflow_db, company_id=1, payload={"company_name": "Co1"}, idempotency_key="k1")
    assert mgr.is_backpressure_active(workflow_db, STAGE_DISCOVERY_CANDIDATE) is False

    mgr.enqueue_candidate(workflow_db, company_id=2, payload={"company_name": "Co2"}, idempotency_key="k2")
    # 2 items reached threshold -> backpressure active
    assert mgr.is_backpressure_active(workflow_db, STAGE_DISCOVERY_CANDIDATE) is True


def test_send_ready_buffer_retrieval(workflow_db):
    mgr = FunnelWorkflowManager()
    item, _ = mgr.enqueue_candidate(
        workflow_db,
        company_id=106,
        source_query_id=6,
        payload={"company_name": "RenewSys India"},
    )
    mgr.transition_stage(workflow_db, item.id, next_stage=STAGE_SEND_READY, status=STATUS_PENDING)

    buffer_items = mgr.get_send_ready_buffer(workflow_db, limit=5)
    assert len(buffer_items) == 1
    assert buffer_items[0].id == item.id
    assert buffer_items[0].current_stage == STAGE_SEND_READY
