"""Integration and Concurrency Hardening Test Suite (Task 3D.1F.1).

Validates:
1. Migration upgrade from real current head (20260916_ba_decisions -> 20260917_followup_memory).
2. FollowupQueryMemoryRecord model persistence across commit and session restart.
3. Concurrency safety: Two simultaneous workers for same company + missing fact -> exactly one search reservation succeeds.
4. Crash recovery: Expired/crashed lease allows subsequent retry without permanent lockout.
5. Independence: Different missing facts or different companies proceed concurrently without contention.
6. Fail-Closed LLM failure behavior: DeepSeek fail + Gemini fail safely returns HOLD with 0 search spend.
7. Missing-fact taxonomy canonicalization: Eliminates free-text drift across aliases into shared memory buckets.
"""
from __future__ import annotations

import os
import sys
import time
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
# 2. Memory Row Persistence & Session Restart
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

    # Update and commit
    found.new_evidence_found = True
    found.evidence_type_found = "COMMISSIONING_CERTIFICATE"
    found.result_count = 5
    found.funnel_state_after = "PASS"
    session1.commit()
    session1.close()

    # Restart session
    session2 = Session()
    reloaded = session2.query(FollowupQueryMemoryRecord).filter_by(id=rec_id).first()
    assert reloaded is not None
    assert reloaded.new_evidence_found is True
    assert reloaded.evidence_type_found == "COMMISSIONING_CERTIFICATE"
    assert reloaded.result_count == 5
    assert reloaded.funnel_state_after == "PASS"
    session2.close()
    engine.dispose()


# ============================================================
# 3. Concurrency Safety: Atomic Search Reservation
# ============================================================

def test_concurrent_workers_same_company_and_missing_fact():
    """Worker A and Worker B simultaneously attempt search on same entity+fact -> only one succeeds."""
    gate = FollowupInformationGainGate(primary_provider=None, fallback_provider=None)

    company = "Dharamsi Morarji Chemical Co"
    fact = "COMMISSIONING_STATUS"

    # Worker A acquires reservation
    acquired_a, token_a = gate.acquire_search_reservation(
        company_name=company,
        missing_fact=fact,
        strategy="GENERAL_WEB",
        worker_id="worker_fastapi_1",
    )
    assert acquired_a is True
    assert token_a == "worker_fastapi_1"

    # Worker B simultaneously attempts to acquire reservation for same company + fact
    acquired_b, token_b = gate.acquire_search_reservation(
        company_name=company,
        missing_fact=fact,
        strategy="GENERAL_WEB",
        worker_id="worker_celery_1",
    )
    assert acquired_b is False
    assert token_b is None

    # Gate evaluation for Worker B is immediately blocked with CONCURRENT_RESERVATION_BLOCKED
    decision_b = gate.evaluate_followup_search(
        company_name=company,
        missing_fact=fact,
    )
    assert decision_b.search_needed is False
    assert decision_b.decision_type == "CONCURRENT_RESERVATION_BLOCKED"
    assert decision_b.blocked_reason == "ACTIVE_SEARCH_RESERVATION"

    # Clean release by Worker A
    gate.release_search_reservation(company, fact, token_a)
    assert gate.is_search_reserved(company, fact) is False


# ============================================================
# 4. Crash Recovery: Expired Reservation Allows Retry
# ============================================================

def test_crashed_worker_reservation_lease_expires_and_allows_retry():
    """Worker crashes holding reservation; lease expires naturally; Worker B can acquire."""
    gate = FollowupInformationGainGate(primary_provider=None, fallback_provider=None)

    company = "Aether Industries Limited"
    fact = "FACILITY_LOCATION"

    # Worker A acquires short 0.1s lease, then "crashes" (never calls release)
    acquired_a, token_a = gate.acquire_search_reservation(
        company_name=company,
        missing_fact=fact,
        lease_seconds=0.1,
        worker_id="crashed_worker_99",
    )
    assert acquired_a is True

    # Immediately, Worker B is rejected
    acquired_b1, _ = gate.acquire_search_reservation(company, fact, worker_id="retry_worker_1")
    assert acquired_b1 is False

    # Wait for lease to expire
    time.sleep(0.15)

    # Worker B retries -> now succeeds!
    acquired_b2, token_b = gate.acquire_search_reservation(company, fact, worker_id="retry_worker_1")
    assert acquired_b2 is True
    assert token_b == "retry_worker_1"

    gate.release_search_reservation(company, fact, token_b)


# ============================================================
# 5. Independence: Different Missing Facts & Different Companies
# ============================================================

def test_different_missing_facts_proceed_independently():
    """Same company with different missing facts can be researched concurrently."""
    gate = FollowupInformationGainGate(primary_provider=None, fallback_provider=None)
    company = "Tata Chemicals Limited"

    acq1, tok1 = gate.acquire_search_reservation(company, "FACILITY_LOCATION")
    acq2, tok2 = gate.acquire_search_reservation(company, "COMMISSIONING_STATUS")

    assert acq1 is True
    assert acq2 is True

    gate.release_search_reservation(company, "FACILITY_LOCATION", tok1)
    gate.release_search_reservation(company, "COMMISSIONING_STATUS", tok2)


def test_different_companies_proceed_independently():
    """Different companies with same missing fact proceed concurrently without contention."""
    gate = FollowupInformationGainGate(primary_provider=None, fallback_provider=None)

    acq1, tok1 = gate.acquire_search_reservation("Company Alpha Limited", "CAPEX_EVENT")
    acq2, tok2 = gate.acquire_search_reservation("Company Beta Limited", "CAPEX_EVENT")

    assert acq1 is True
    assert acq2 is True

    gate.release_search_reservation("Company Alpha Limited", "CAPEX_EVENT", tok1)
    gate.release_search_reservation("Company Beta Limited", "CAPEX_EVENT", tok2)


# ============================================================
# 6. Safe Fail-Closed LLM Failure Behavior (Section 8)
# ============================================================

def test_safe_llm_failure_fail_closed_hold_behavior():
    """When both DeepSeek and Gemini fail, gate safely HOLDS without speculative Serper credit spend."""
    mock_deepseek = MagicMock()
    mock_deepseek.is_available.return_value = False
    mock_gemini = MagicMock()
    mock_gemini.is_available.return_value = False

    gate = FollowupInformationGainGate(
        primary_provider=mock_deepseek,
        fallback_provider=mock_gemini,
        fail_closed_on_llm_failure=True,
    )

    decision = gate.evaluate_followup_search(
        company_name="Specialty Chemicals Manufacturer Limited",
        missing_fact="CAPEX_EVENT",
        company_id=450,
        current_evidence={"titles": [], "snippets": []},
    )

    assert decision.search_needed is False
    assert decision.alternative_action == "HOLD"
    assert decision.decision_type == "LLM_FAILURE_HOLD"
    assert decision.blocked_reason == "HOLD_LLM_UNAVAILABLE"


# ============================================================
# 7. Missing-Fact Taxonomy & Alias Canonicalization (Section 9)
# ============================================================

def test_missing_fact_taxonomy_and_alias_canonicalization():
    """All aliases canonicalize to exact standard keys, mapping to shared memory buckets."""
    # Facility Location
    for alias in ["facility_city", "EXACT_FACILITY", "facility location", "facility_name", "location", "city"]:
        assert canonicalize_missing_fact(alias) == "FACILITY_LOCATION"

    # Trigger Date
    for alias in ["CURRENT_EVENT_DATE", "event_date", "date", "trigger_date"]:
        assert canonicalize_missing_fact(alias) == "TRIGGER_DATE"

    # Commissioning / Operating Status
    for alias in ["commissioning", "status", "commissioning_status"]:
        assert canonicalize_missing_fact(alias) == "COMMISSIONING_STATUS"
    for alias in ["operating_status", "operational_status"]:
        assert canonicalize_missing_fact(alias) == "OPERATING_STATUS"

    # Machinery Context
    for alias in ["machinery", "equipment", "machinery_context"]:
        assert canonicalize_missing_fact(alias) == "MACHINERY_CONTEXT"

    # Capex Event
    for alias in ["capex", "expansion", "capex_event"]:
        assert canonicalize_missing_fact(alias) == "CAPEX_EVENT"

    # Plant Ownership
    for alias in ["ownership", "plant_ownership"]:
        assert canonicalize_missing_fact(alias) == "PLANT_OWNERSHIP"


def test_alias_shared_memory_bucket_in_gate():
    """Searches recorded under alias 'facility_city' are retrievable under 'FACILITY_LOCATION'."""
    gate = FollowupInformationGainGate(primary_provider=None, fallback_provider=None)
    company = "Gujarat Fluorochemicals Limited"

    # Record search using alias 'facility_city'
    gate.record_search_outcome(
        company_name=company,
        missing_fact="facility_city",
        query='"Gujarat Fluorochemicals" Dahej plant location',
        result_count=3,
        new_evidence_found=True,
        evidence_type_found="FACILITY_LOCATION_CONFIRMED",
    )

    # Query gate using canonical name 'FACILITY_LOCATION'
    priors = gate.get_prior_searches(company_name=company, missing_fact="FACILITY_LOCATION")
    assert len(priors) == 1
    assert priors[0]["missing_fact"] == "FACILITY_LOCATION"
    assert priors[0]["new_evidence_found"] is True

    # Gate evaluation recognizes already resolved fact and reuses existing evidence
    decision = gate.evaluate_followup_search(
        company_name=company,
        missing_fact="facility_name",
        company_id=500,
    )
    assert decision.search_needed is False
    assert decision.alternative_action == "USE_EXISTING_EVIDENCE"
    assert decision.decision_type == "MEMORY_ALREADY_RESOLVED"


# ============================================================
# 8. Redis Distributed Reservation Simulation
# ============================================================

def test_redis_distributed_reservation_when_available():
    """When Redis is available, atomic SET NX EX is used for multi-process safety."""
    fake_redis = {}

    class MockRedis:
        def set(self, key, val, nx=False, ex=None):
            if nx and key in fake_redis:
                return False
            fake_redis[key] = val
            return True

        def get(self, key):
            return fake_redis.get(key)

        def delete(self, key):
            fake_redis.pop(key, None)

        def exists(self, key):
            return key in fake_redis

    gate = FollowupInformationGainGate(
        primary_provider=None,
        fallback_provider=None,
        redis_client=MockRedis(),
    )

    company = "Coromandel International Limited"
    fact = "CAPEX_EVENT"

    acq1, tok1 = gate.acquire_search_reservation(company, fact, worker_id="celery_worker_A")
    assert acq1 is True
    assert tok1 == "celery_worker_A"

    # Second worker blocked via Redis NX
    acq2, tok2 = gate.acquire_search_reservation(company, fact, worker_id="fastapi_worker_B")
    assert acq2 is False
    assert tok2 is None

    # Release frees key in Redis
    gate.release_search_reservation(company, fact, tok1)
    assert len(fake_redis) == 0

    # Next attempt succeeds
    acq3, tok3 = gate.acquire_search_reservation(company, fact, worker_id="fastapi_worker_B")
    assert acq3 is True
    assert tok3 == "fastapi_worker_B"
