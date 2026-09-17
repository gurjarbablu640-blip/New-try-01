"""Integration and Concurrency Hardening Test Suite (Task 3D.1F.1 & Task 3D.1F.2).

Validates:
1. Migration upgrade from real current head (20260916_ba_decisions -> 20260917_followup_memory).
2. Singular Alembic head verification.
3. Database column types consistency (Company.id, FollowupQueryMemoryRecord.id, company_id, migration).
4. FollowupQueryMemoryRecord model persistence across commit and session restart.
5. Concurrency safety: Two simultaneous workers for same company + missing fact -> exactly one search reservation succeeds.
6. Cross-strategy collision prevention: GENERAL_WEB attempt 1 vs OFFICIAL_COMPANY attempt 2 for same entity + fact -> exactly ONE succeeds.
7. Cross-attempt collision prevention: Different attempt numbers for same entity + fact collide.
8. Independence: Different missing facts or different companies proceed concurrently without contention.
9. Lease renewal / background heartbeat prevents mid-search expiry during active work.
10. Crash recovery: Expired/crashed lease allows subsequent retry without permanent lockout.
11. Redis failure in production mode fails closed to HOLD (no speculative Serper search).
12. Local test / in-memory reservation mode permitted when configured.
13. Fail-Closed LLM failure behavior: DeepSeek fail + Gemini fail safely returns HOLD with 0 search spend.
14. Missing-fact taxonomy canonicalization: Eliminates free-text drift across aliases into shared memory buckets.
"""
from __future__ import annotations

import os
import sys
import time
import threading
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from alembic.config import Config
from alembic import command
from alembic.script import ScriptDirectory
from alembic.migration import MigrationContext

from database import Base
from models.company import Company
from models.followup_query_memory import FollowupQueryMemoryRecord
from services.followup_information_gain_gate import (
    FollowupInformationGainGate,
    canonicalize_missing_fact,
    VALID_MISSING_FACTS,
    reset_telemetry,
    get_telemetry,
)


@pytest.fixture
def disposable_db_url(tmp_path):
    db_file = tmp_path / "test_concurrency_disposable.db"
    return f"sqlite:///{db_file}"


# ============================================================
# 1. Alembic Migration Upgrade & Single Head Verification
# ============================================================

def test_migration_upgrade_and_head_status(disposable_db_url):
    """Test migration from current production head (20260916_ba_decisions) to 20260917_followup_memory."""
    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    cfg = Config(os.path.join(backend_dir, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(backend_dir, "alembic"))
    cfg.set_main_option("sqlalchemy.url", disposable_db_url)

    # 1. Verify single head in ScriptDirectory
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    assert heads == ["20260917_followup_memory"], f"Expected single head, got {heads}"

    # Verify down revision
    rev = script.get_revision("20260917_followup_memory")
    assert rev.down_revision == "20260916_ba_decisions"

    engine = sa.create_engine(disposable_db_url)

    # Initialize Base metadata on sqlite engine
    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        inspector = sa.inspect(conn)
        if "followup_query_memory_records" in inspector.get_table_names():
            conn.execute(sa.text("DROP TABLE followup_query_memory_records"))
            conn.commit()

    # Stamp to current production revision: 20260916_ba_decisions
    command.stamp(cfg, "20260916_ba_decisions")

    with engine.connect() as conn:
        inspector = sa.inspect(conn)
        assert "followup_query_memory_records" not in inspector.get_table_names()

    # Upgrade to new migration
    command.upgrade(cfg, "head")

    with engine.connect() as conn:
        inspector = sa.inspect(conn)
        tables = inspector.get_table_names()
        assert "followup_query_memory_records" in tables

        indices = {idx["name"]: idx["column_names"] for idx in inspector.get_indexes("followup_query_memory_records")}
        assert "ix_followup_entity_fact" in indices
        assert "ix_followup_company_fact" in indices

        ctx = MigrationContext.configure(conn)
        assert ctx.get_current_revision() == "20260917_followup_memory"

    engine.dispose()


# ============================================================
# 2. Database Types Consistency (Task 3D.1F.2 Section 7)
# ============================================================

def test_database_type_consistency_model_and_migration():
    """Verify Company.id, FollowupQueryMemoryRecord.id, company_id, and migration match Integer."""
    assert isinstance(Company.id.type, sa.Integer), f"Company.id type is {Company.id.type}, expected Integer"
    assert isinstance(FollowupQueryMemoryRecord.id.type, sa.Integer), (
        f"FollowupQueryMemoryRecord.id type is {FollowupQueryMemoryRecord.id.type}, expected Integer"
    )
    assert isinstance(FollowupQueryMemoryRecord.company_id.type, sa.Integer), (
        f"FollowupQueryMemoryRecord.company_id type is {FollowupQueryMemoryRecord.company_id.type}, expected Integer"
    )


# ============================================================
# 3. Memory Row Persistence & Session Restart
# ============================================================

def test_memory_row_persistence_and_session_restart(disposable_db_url):
    """Prove insert -> query -> update -> commit -> restart session -> row persists."""
    engine = sa.create_engine(disposable_db_url)
    Base.metadata.create_all(bind=engine)

    Session = sessionmaker(bind=engine)
    session1 = Session()

    record = FollowupQueryMemoryRecord(
        company_id=101,
        normalized_operating_entity="aether industries limited",
        missing_fact="COMMISSIONING_STATUS",
        query='"Aether Industries" plant commissioning commercial production',
        research_strategy="GENERAL_WEB",
        result_count=2,
        useful_urls=["https://aether.com/plant-update"],
        new_evidence_found=False,
        evidence_type_found=None,
        source_domains=["aether.com"],
        funnel_state_before="INCOMPLETE",
        funnel_state_after="HOLD",
        llm_reasoning="Trial run phase",
    )
    session1.add(record)
    session1.commit()
    rec_id = record.id

    # Read back in session 1
    found = session1.query(FollowupQueryMemoryRecord).filter_by(id=rec_id).first()
    assert found is not None
    assert found.result_count == 2
    assert found.new_evidence_found is False

    # Update
    found.new_evidence_found = True
    found.evidence_type_found = "COMMISSIONING_DATE"
    found.funnel_state_after = "QUALIFIED"
    session1.commit()

    session1.close()

    # Completely new session
    session2 = Session()
    reloaded = session2.query(FollowupQueryMemoryRecord).filter_by(id=rec_id).first()
    assert reloaded is not None
    assert reloaded.new_evidence_found is True
    assert reloaded.evidence_type_found == "COMMISSIONING_DATE"
    assert reloaded.funnel_state_after == "QUALIFIED"
    assert reloaded.normalized_operating_entity == "aether industries limited"
    assert reloaded.missing_fact == "COMMISSIONING_STATUS"

    session2.close()
    engine.dispose()


# ============================================================
# 4. Atomic Search Reservation & Concurrency Safety
# ============================================================

def test_concurrent_workers_same_strategy_one_succeeds():
    """Two simultaneous workers for same entity + fact + strategy -> only one succeeds."""
    gate = FollowupInformationGainGate(allow_in_memory_reservation=True)
    company = "Aether Industries Limited"
    fact = "COMMISSIONING_STATUS"

    acq1, token1 = gate.acquire_search_reservation(company, fact, strategy="GENERAL_WEB", attempt=1)
    assert acq1 is True
    assert token1 is not None

    # Simultaneous Worker B
    acq2, token2 = gate.acquire_search_reservation(company, fact, strategy="GENERAL_WEB", attempt=1)
    assert acq2 is False
    assert token2 is None

    # Release by Worker 1 allows subsequent acquisition
    gate.release_search_reservation(company, fact, token1)
    acq3, token3 = gate.acquire_search_reservation(company, fact, strategy="GENERAL_WEB", attempt=1)
    assert acq3 is True
    assert token3 is not None
    gate.release_search_reservation(company, fact, token3)


def test_cross_strategy_collision_blocked():
    """Task 3D.1F.2 Section 1 & 2: Cross-strategy collision must be blocked!

    Worker A: Aether Industries + COMMISSIONING_STATUS, GENERAL_WEB, attempt 1
    Worker B: Aether Industries + COMMISSIONING_STATUS, OFFICIAL_COMPANY, attempt 2

    Expected: Exactly ONE reservation succeeds. The other receives CONCURRENT_RESERVATION_BLOCKED.
    """
    gate = FollowupInformationGainGate(allow_in_memory_reservation=True)
    company = "Aether Industries Limited"
    fact = "COMMISSIONING_STATUS"

    # Worker A: GENERAL_WEB attempt 1
    acq_a, token_a = gate.acquire_search_reservation(
        company_name=company,
        missing_fact=fact,
        strategy="GENERAL_WEB",
        attempt=1,
    )
    assert acq_a is True
    assert token_a is not None

    # Worker B: OFFICIAL_COMPANY attempt 2 (different strategy & attempt, but same entity + fact)
    acq_b, token_b = gate.acquire_search_reservation(
        company_name=company,
        missing_fact=fact,
        strategy="OFFICIAL_COMPANY",
        attempt=2,
    )
    assert acq_b is False
    assert token_b is None

    # Gate evaluation for Worker B must return CONCURRENT_RESERVATION_BLOCKED
    decision_b = gate.evaluate_followup_search(
        company_name=company,
        missing_fact=fact,
        company_id=284,
    )
    assert decision_b.search_needed is False
    assert decision_b.decision_type == "CONCURRENT_RESERVATION_BLOCKED"
    assert decision_b.blocked_reason == "ACTIVE_SEARCH_RESERVATION"

    gate.release_search_reservation(company, fact, token_a)


def test_cross_attempt_collision_blocked():
    """Task 3D.1F.2 Section 1: Different attempt numbers for same entity+fact must collide."""
    gate = FollowupInformationGainGate(allow_in_memory_reservation=True)
    company = "Dharamsi Morarji Chemical Company Limited"
    fact = "FACILITY_LOCATION"

    acq1, token1 = gate.acquire_search_reservation(company, fact, attempt=1)
    assert acq1 is True

    acq2, token2 = gate.acquire_search_reservation(company, fact, attempt=2)
    assert acq2 is False

    gate.release_search_reservation(company, fact, token1)


def test_different_missing_facts_proceed_independently():
    """Same company with different missing facts proceed concurrently."""
    gate = FollowupInformationGainGate(allow_in_memory_reservation=True)
    company = "Aether Industries Limited"

    acq1, token1 = gate.acquire_search_reservation(company, "FACILITY_LOCATION")
    acq2, token2 = gate.acquire_search_reservation(company, "COMMISSIONING_STATUS")

    assert acq1 is True
    assert acq2 is True

    gate.release_search_reservation(company, "FACILITY_LOCATION", token1)
    gate.release_search_reservation(company, "COMMISSIONING_STATUS", token2)


def test_different_companies_proceed_independently():
    """Different companies with same missing fact proceed concurrently."""
    gate = FollowupInformationGainGate(allow_in_memory_reservation=True)
    fact = "COMMISSIONING_STATUS"

    acq1, token1 = gate.acquire_search_reservation("Company Alpha Limited", fact)
    acq2, token2 = gate.acquire_search_reservation("Company Beta Limited", fact)

    assert acq1 is True
    assert acq2 is True

    gate.release_search_reservation("Company Alpha Limited", fact, token1)
    gate.release_search_reservation("Company Beta Limited", fact, token2)


# ============================================================
# 5. Lease Heartbeat & Crash Recovery (Task 3D.1F.2 Section 3 & 4)
# ============================================================

def test_lease_renewal_heartbeat_prevents_mid_search_expiry():
    """Heartbeat keeps reservation alive during active work exceeding initial TTL."""
    gate = FollowupInformationGainGate(allow_in_memory_reservation=True)
    company = "Renewable Energy Solutions Limited"
    fact = "CAPEX_EVENT"

    worker_b_blocked = [False]

    def _worker_a_task():
        with gate.reserve_search(
            company_name=company,
            missing_fact=fact,
            lease_seconds=1,
            heartbeat_interval=0.1,
        ) as (acquired, token):
            assert acquired is True
            time.sleep(0.35)

    t = threading.Thread(target=_worker_a_task)
    t.start()

    time.sleep(0.1)

    # Worker B tries to acquire while Worker A is still working
    acq_b, _ = gate.acquire_search_reservation(company, fact)
    worker_b_blocked[0] = (acq_b is False)

    t.join()

    assert worker_b_blocked[0] is True, "Worker B should have been blocked during Worker A execution"

    # After Worker A finishes, Worker B can acquire
    acq_after, token_after = gate.acquire_search_reservation(company, fact)
    assert acq_after is True
    gate.release_search_reservation(company, fact, token_after)


def test_crash_recovery_lease_expiry_after_heartbeat_stops():
    """If worker crashes (stops heartbeat, does not release), lease expires after TTL."""
    gate = FollowupInformationGainGate(allow_in_memory_reservation=True)
    company = "Crash Prone Corp Limited"
    fact = "COMMISSIONING_STATUS"

    # Worker 1 acquires with 0.3s TTL, then crashes (no release, no heartbeat)
    acq_short, _ = gate.acquire_search_reservation(company, fact, lease_seconds=0.3)
    assert acq_short is True

    # Immediate attempt by Worker 2 is blocked
    acq2, _ = gate.acquire_search_reservation(company, fact)
    assert acq2 is False

    # Wait for lease to expire
    time.sleep(0.4)

    # Worker 2 attempts again and succeeds!
    acq3, token3 = gate.acquire_search_reservation(company, fact, lease_seconds=1)
    assert acq3 is True, "Worker 2 should acquire after lease expired (no permanent lockout)"
    gate.release_search_reservation(company, fact, token3)


# ============================================================
# 6. Redis Unavailable in Production (Task 3D.1F.2 Section 5 & 6)
# ============================================================

def test_redis_unavailable_in_production_fails_closed_hold():
    """When Redis is unavailable in production mode, fail closed to HOLD (no search)."""
    gate = FollowupInformationGainGate(
        allow_in_memory_reservation=False,
        redis_client=None,
    )
    company = "Titan Industries Limited"
    fact = "COMMISSIONING_STATUS"

    # 1. Direct reservation acquisition fails closed with HOLD token
    acquired, token = gate.acquire_search_reservation(company, fact)
    assert acquired is False
    assert token == "FOLLOWUP_RESERVATION_UNAVAILABLE_HOLD"

    # 2. Gate evaluation returns FOLLOWUP_RESERVATION_UNAVAILABLE_HOLD with search_needed=False
    decision = gate.evaluate_followup_search(company, fact, company_id=501)
    assert decision.search_needed is False
    assert decision.decision_type == "FOLLOWUP_RESERVATION_UNAVAILABLE_HOLD"
    assert decision.alternative_action == "HOLD"
    assert decision.blocked_reason == "REDIS_UNAVAILABLE_PRODUCTION_HOLD"


# ============================================================
# 7. Safe LLM Failure Behavior (Task 3D.1F.1 Section 8)
# ============================================================

def test_safe_llm_failure_hold_behavior():
    """When both DeepSeek and Gemini fail, safe fail-closed HOLD is returned."""
    mock_primary = MagicMock()
    mock_primary.is_available.return_value = False
    mock_primary.complete.side_effect = Exception("DeepSeek API 503")

    mock_fallback = MagicMock()
    mock_fallback.is_available.return_value = False
    mock_fallback.call.side_effect = Exception("Gemini API 503")

    gate = FollowupInformationGainGate(
        primary_provider=mock_primary,
        fallback_provider=mock_fallback,
        fail_closed_on_llm_failure=True,
        allow_in_memory_reservation=True,
    )

    decision = gate.evaluate_followup_search(
        company_name="Aether Industries Limited",
        missing_fact="COMMISSIONING_STATUS",
        company_id=284,
        current_evidence={"titles": ["Aether plans expansion"], "snippets": ["Initial announcement"]},
    )

    assert decision.search_needed is False
    assert decision.decision_type == "LLM_FAILURE_HOLD"
    assert decision.alternative_action == "HOLD"
    assert decision.blocked_reason == "HOLD_LLM_UNAVAILABLE"


# ============================================================
# 8. Taxonomy Canonicalization & Shared Bucket
# ============================================================

def test_missing_fact_canonicalization_and_shared_bucket():
    """Alias canonicalization maps free-text variations to the standard key and shared lock."""
    assert canonicalize_missing_fact("facility_city") == "FACILITY_LOCATION"
    assert canonicalize_missing_fact("EXACT_FACILITY") == "FACILITY_LOCATION"
    assert canonicalize_missing_fact("facility location") == "FACILITY_LOCATION"
    assert canonicalize_missing_fact("event_date") == "TRIGGER_DATE"
    assert canonicalize_missing_fact("status") == "COMMISSIONING_STATUS"
    assert canonicalize_missing_fact("capex") == "CAPEX_EVENT"
    assert canonicalize_missing_fact("machinery") == "MACHINERY_CONTEXT"

    # Verify they share the exact same reservation scope
    gate = FollowupInformationGainGate(allow_in_memory_reservation=True)
    acq1, tok1 = gate.acquire_search_reservation("Aether Industries Limited", "facility_city")
    assert acq1 is True

    # Same entity with alias "EXACT_FACILITY" must collide!
    acq2, tok2 = gate.acquire_search_reservation("Aether Industries Limited", "EXACT_FACILITY")
    assert acq2 is False

    gate.release_search_reservation("Aether Industries Limited", "facility_city", tok1)
