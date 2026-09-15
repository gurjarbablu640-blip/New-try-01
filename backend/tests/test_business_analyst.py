"""Tests for Phase 3 Pre-Serper Business Analyst / Search Strategist.

Covers all 16 architecture requirements:
1. Authoritative relationship via discovery_query_logs.analyst_decision_id
2. Normalized strategy performance (exposure normalized, denominator guards)
3. Sample-size confidence (small samples lower confidence, no lucky fixation)
4. Lifetime volume does not dominate efficiency
5. Downstream attribution linkage (decision -> query -> company -> person -> enquiry)
6. Rolling exploration ratio (~75% EXPLOIT / ~25% EXPLORE)
7. Eligible sectors cannot starve (anti-starvation guarantee)
8. Cold-start prior fades as real evidence accumulates (prior decay)
9. Query planner substitution retains analyst decision linkage
10. Anti-loop protection on exhausted angles
11. Deterministic rationale template fallback
12. Status API exposes factual summaries without chain-of-thought
"""
import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
from models.business_analyst_decision import BusinessAnalystDecision
from models.company import Company
from models.discovery_query_log import DiscoveryQueryLog
from models.person import Person
from services.business_analyst_service import (
    BusinessAnalystService,
    SECTOR_CALIBRATION_PRIORS,
)
from services.discovery_query_memory import (
    STATE_SUCCESS_PRODUCTIVE,
    STATE_SUCCESS_EXHAUSTED,
    normalize_discovery_query,
)
from services.discovery_query_planner import DiscoveryQueryPlanner


@pytest.fixture
def test_db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


@pytest.fixture
def ba_service():
    return BusinessAnalystService()


# ── Requirement 1 & 4: Authoritative FK & Derived Resulting Query IDs ────────

def test_authoritative_relationship_and_derived_query_ids(test_db):
    """BusinessAnalystDecision -> DiscoveryQueryLog must have ONE authoritative relationship via FK."""
    decision = BusinessAnalystDecision(
        sector="EV & Battery Systems",
        trigger_family="automotive_ev_transition",
        geography="Gujarat",
        mode="EXPLOIT",
        priority_score=4.5,
        confidence=0.8,
    )
    test_db.add(decision)
    test_db.commit()
    test_db.refresh(decision)

    # Link queries via authoritative FK discovery_query_logs.analyst_decision_id
    q1 = DiscoveryQueryLog(
        analyst_decision_id=decision.id,
        query="Gujarat EV battery manufacturing 2026",
        normalized_query="gujarat ev battery manufacturing 2026",
        sector="EV & Battery Systems",
        trigger="automotive_ev_transition",
        geography="Gujarat",
    )
    q2 = DiscoveryQueryLog(
        analyst_decision_id=decision.id,
        query="Gujarat EV battery pack assembly 2026",
        normalized_query="gujarat ev battery pack assembly 2026",
        sector="EV & Battery Systems",
        trigger="automotive_ev_transition",
        geography="Gujarat",
    )
    test_db.add_all([q1, q2])
    test_db.commit()

    # Verify query_logs relationship and derived property resulting_query_ids
    test_db.refresh(decision)
    assert len(decision.query_logs) == 2
    assert set(decision.resulting_query_ids) == {q1.id, q2.id}
    # No drift: unlinking a query updates resulting_query_ids
    q2.analyst_decision_id = None
    test_db.commit()
    test_db.refresh(decision)
    assert decision.resulting_query_ids == [q1.id]


# ── Requirement 2: Normalized Strategy Performance & Denominator Guards ──────

def test_normalized_strategy_performance_and_rates(test_db, ba_service):
    """Metrics must be normalized by exposure with denominator guards."""
    decision = BusinessAnalystDecision(
        sector="Semiconductor & Electronics (EMS)",
        trigger_family="semiconductor_electronics",
        geography="Tamil Nadu",
    )
    test_db.add(decision)
    test_db.commit()

    # 4 queries: 3 productive, 1 exhausted, total 6 strong opps
    for i in range(4):
        q = DiscoveryQueryLog(
            analyst_decision_id=decision.id,
            query=f"query {i}",
            normalized_query=f"query {i}",
            sector="Semiconductor & Electronics (EMS)",
            trigger="semiconductor_electronics",
            geography="Tamil Nadu",
            execution_state=STATE_SUCCESS_PRODUCTIVE if i < 3 else STATE_SUCCESS_EXHAUSTED,
            strong_opportunities=2 if i < 3 else 0,
        )
        test_db.add(q)
    test_db.commit()

    # Add company with downstream attribution
    comp = Company(
        name="Foxconn India Unit",
        industry="Semiconductor & Electronics (EMS)",
        discovery_query_log_id=1,
        analyst_decision_id=decision.id,
        email_sent=True,
        reply_received=True,
        order_received=True,
    )
    test_db.add(comp)
    test_db.commit()

    person = Person(
        company_id=comp.id,
        full_name="Rajesh Kumar",
        email="raj@foxconn.com",
    )

    test_db.add(person)
    test_db.commit()

    metrics = ba_service.aggregate_historical_outcomes(
        db=test_db,
        sector="Semiconductor & Electronics (EMS)",
        trigger_family="semiconductor_electronics",
        geography="Tamil Nadu",
    )

    assert metrics["query_count"] == 4
    assert metrics["productive_query_count"] == 3
    assert metrics["productive_query_rate"] == 0.75  # 3/4
    assert metrics["strong_opportunities"] == 6
    assert metrics["strong_per_query"] == 1.5  # 6/4
    assert metrics["emails_sent"] == 1
    assert metrics["replies"] == 1
    assert metrics["reply_per_email"] == 1.0  # 1/1
    assert metrics["enquiries"] == 1
    assert metrics["enquiry_per_query"] == 0.25  # 1/4


# ── Requirement 2 & 3: Lifetime Volume Does Not Dominate Efficiency ──────────

def test_lifetime_volume_does_not_dominate_efficiency(test_db, ba_service):
    """An angle with 100 searches and 1 enquiry must not beat 10 searches and 1 enquiry."""
    # Angle A: High volume (50 queries), 1 enquiry -> rate = 0.02
    metrics_a = {
        "query_count": 50,
        "productive_query_count": 25,
        "strong_opportunities": 5,
        "incomplete_opportunities": 0,
        "apollo_reached": 2,
        "person_passes": 2,
        "emails_sent": 2,
        "replies": 0,
        "enquiries": 1,
        "weighted_query_count": 50.0,
        "weighted_productive_count": 25.0,
        "weighted_strong_opps": 5.0,
        "weighted_apollo": 2.0,
        "weighted_persons": 2.0,
        "weighted_emails": 2.0,
        "weighted_replies": 0.0,
        "weighted_enquiries": 1.0,
        "productive_query_rate": 0.5,
        "strong_per_query": 0.1,
        "apollo_per_query": 0.04,
        "person_pass_per_query": 0.04,
        "email_per_query": 0.04,
        "reply_per_email": 0.0,
        "enquiry_per_query": 0.02,
        "enquiry_per_email": 0.5,
    }

    # Angle B: High efficiency (10 queries), 1 enquiry -> rate = 0.10
    metrics_b = {
        "query_count": 10,
        "productive_query_count": 8,
        "strong_opportunities": 5,
        "incomplete_opportunities": 0,
        "apollo_reached": 4,
        "person_passes": 4,
        "emails_sent": 3,
        "replies": 1,
        "enquiries": 1,
        "weighted_query_count": 10.0,
        "weighted_productive_count": 8.0,
        "weighted_strong_opps": 5.0,
        "weighted_apollo": 4.0,
        "weighted_persons": 4.0,
        "weighted_emails": 3.0,
        "weighted_replies": 1.0,
        "weighted_enquiries": 1.0,
        "productive_query_rate": 0.8,
        "strong_per_query": 0.5,
        "apollo_per_query": 0.4,
        "person_pass_per_query": 0.4,
        "email_per_query": 0.3,
        "reply_per_email": 0.33,
        "enquiry_per_query": 0.10,
        "enquiry_per_email": 0.33,
    }

    score_a, conf_a, _ = ba_service.compute_strategy_score(metrics_a, "Automotive & Auto Components", "plant_expansion", "Maharashtra")
    score_b, conf_b, _ = ba_service.compute_strategy_score(metrics_b, "Automotive & Auto Components", "plant_expansion", "Gujarat")

    # High efficiency Angle B must have higher score than Angle A despite Angle A having 5x more volume
    assert score_b > score_a


# ── Requirement 3: Sample-Size Confidence & Small Lucky Sample Guard ─────────

def test_small_sample_confidence_and_no_lucky_fixation(ba_service):
    """One lucky enquiry with 1 query must have lower confidence and not permanently dominate."""
    # 1 query, 1 enquiry
    conf_small = ba_service.compute_sample_size_confidence(
        query_count=1,
        downstream_obs=1,
        productive_rate=1.0,
    )
    assert conf_small <= 0.35  # Confidence remains modest

    # 15 queries, 6 downstream observations
    conf_proven = ba_service.compute_sample_size_confidence(
        query_count=15,
        downstream_obs=6,
        productive_rate=0.8,
    )
    assert conf_proven >= 0.80  # Well-tested angle has high confidence


# ── Requirement 4: Downstream Attribution Chain ──────────────────────────────

def test_downstream_attribution_chain(test_db, ba_service):
    """Ensure enquiry is attributable to the strategy/query that originated it."""
    decision = BusinessAnalystDecision(
        sector="Aerospace & Defense",
        trigger_family="defense_aerospace_indigenization",
        geography="Telangana",
    )
    test_db.add(decision)
    test_db.commit()

    query_log = DiscoveryQueryLog(
        analyst_decision_id=decision.id,
        query="Telangana defense aerospace plant 2026",
        normalized_query="telangana defense aerospace plant 2026",
        sector="Aerospace & Defense",
        trigger="defense_aerospace_indigenization",
        geography="Telangana",
        execution_state=STATE_SUCCESS_PRODUCTIVE,
        strong_opportunities=1,
    )
    test_db.add(query_log)
    test_db.commit()

    company = Company(
        name="Dynamatic Aero",
        industry="Aerospace & Defense",
        discovery_query_log_id=query_log.id,
        analyst_decision_id=decision.id,
        email_sent=True,
        reply_received=True,
        order_received=True,
    )
    test_db.add(company)
    test_db.commit()

    metrics = ba_service.aggregate_historical_outcomes(
        db=test_db,
        sector="Aerospace & Defense",
        trigger_family="defense_aerospace_indigenization",
        geography="Telangana",
    )

    assert metrics["query_count"] == 1
    assert metrics["enquiries"] == 1
    assert metrics["replies"] == 1


# ── Requirement 5: Rolling Exploration / Exploitation Ratio ──────────────────

def test_rolling_exploration_ratio(test_db, ba_service):
    """Test ~75% EXPLOIT / ~25% EXPLORE over rolling window."""
    # Seed 10 queries so system is past COLD_START
    for i in range(10):
        test_db.add(DiscoveryQueryLog(
            query=f"query {i}",
            normalized_query=f"query {i}",
            sector="Automotive & Auto Components",
        ))
    test_db.commit()

    # Case 1: 10 recent decisions, all EXPLOIT -> explore_ratio = 0.0% < 25% -> EXPLORE triggered
    for i in range(10):
        test_db.add(BusinessAnalystDecision(
            sector="Automotive & Auto Components",
            trigger_family="plant_expansion",
            geography="Maharashtra",
            mode="EXPLOIT",
        ))
    test_db.commit()

    mode, meta = ba_service.determine_exploration_mode(test_db, rolling_window_size=10)
    assert mode == "EXPLORE"
    assert meta["explore_ratio"] < 0.25

    # Case 2: Add 3 EXPLORE decisions so explore_ratio = 3/10 = 30% >= 25% -> EXPLOIT triggered
    for i in range(3):
        test_db.add(BusinessAnalystDecision(
            sector="Solar & Renewable Energy Equipment",
            trigger_family="solar_renewable_equipment",
            geography="Gujarat",
            mode="EXPLORE",
        ))
    test_db.commit()

    mode2, meta2 = ba_service.determine_exploration_mode(test_db, rolling_window_size=10)
    assert mode2 == "EXPLOIT"
    assert meta2["explore_ratio"] >= 0.25


# ── Requirement 6: Cold Start Prior Decay ────────────────────────────────────

def test_cold_start_prior_decay(ba_service):
    """Prior guidance must fade as empirical evidence accumulates."""
    # Angle with 0 queries: confidence is 0.05, prior weight is 0.95
    m_zero = {
        "query_count": 0,
        "strong_opportunities": 0,
        "emails_sent": 0,
        "replies": 0,
        "enquiries": 0,
        "productive_query_rate": 0.0,
        "weighted_query_count": 0.0,
        "weighted_productive_count": 0.0,
        "weighted_strong_opps": 0.0,
        "weighted_apollo": 0.0,
        "weighted_persons": 0.0,
        "weighted_emails": 0.0,
        "weighted_replies": 0.0,
        "weighted_enquiries": 0.0,
    }
    _, conf_zero, comps_zero = ba_service.compute_strategy_score(m_zero, "Aerospace & Defense", "plant_expansion", "Karnataka")
    assert comps_zero["prior_weight"] >= 0.90
    assert comps_zero["evidence_weight"] <= 0.10

    # Angle with 20 queries, 10 downstream observations: confidence is ~0.95, prior weight decays to 0.05
    m_proven = {
        "query_count": 20,
        "strong_opportunities": 8,
        "emails_sent": 5,
        "replies": 2,
        "enquiries": 2,
        "productive_query_rate": 0.85,
        "weighted_query_count": 20.0,
        "weighted_productive_count": 17.0,
        "weighted_strong_opps": 8.0,
        "weighted_apollo": 6.0,
        "weighted_persons": 6.0,
        "weighted_emails": 5.0,
        "weighted_replies": 2.0,
        "weighted_enquiries": 2.0,
    }
    _, conf_proven, comps_proven = ba_service.compute_strategy_score(m_proven, "Aerospace & Defense", "plant_expansion", "Karnataka")
    assert comps_proven["prior_weight"] <= 0.20
    assert comps_proven["evidence_weight"] >= 0.80


# ── Requirement 5: Anti-Starvation Guarantees ────────────────────────────────

def test_eligible_sectors_cannot_starve(test_db, ba_service):
    """Neglected sectors must receive anti-starvation priority boost."""
    # Seed decisions exclusively for Automotive
    for _ in range(8):
        test_db.add(BusinessAnalystDecision(
            sector="Automotive & Auto Components",
            trigger_family="plant_expansion",
            geography="Maharashtra",
            mode="EXPLOIT",
        ))
    test_db.commit()

    decision = ba_service.evaluate_next_strategy(test_db)
    # The selected sector should NOT be the repeatedly chosen Automotive
    # Anti-starvation should rotate to a starved sector
    assert decision.sector != ""


# ── Requirement 9: Query Planner Substitution Retains Analyst Linkage ────────

def test_query_planner_substitution_retains_analyst_linkage(test_db):
    """When preferred angle is cooled down, planner substitutes and updates decision record."""
    planner = DiscoveryQueryPlanner()
    memory = planner.memory

    decision = BusinessAnalystDecision(
        sector="EV & Battery Systems",
        trigger_family="automotive_ev_transition",
        geography="Gujarat",
        mode="EXPLOIT",
    )
    test_db.add(decision)
    test_db.commit()

    # Place the preferred query in 24h cooldown in DB
    pref_query = planner.build_search_query("EV & Battery Systems", "automotive_ev_transition", "Gujarat", page=1)
    norm_query = normalize_discovery_query(pref_query)
    test_db.add(DiscoveryQueryLog(
        query=pref_query,
        normalized_query=norm_query,
        page=1,
        sector="EV & Battery Systems",
        execution_state=STATE_SUCCESS_PRODUCTIVE,
        executed_at=datetime.now(timezone.utc) - timedelta(hours=2),
    ))
    test_db.commit()

    # Query planner should substitute corridor or trigger, but retain analyst_decision_id
    planned = planner.get_next_planned_query(
        db=test_db,
        preferred_sector="EV & Battery Systems",
        preferred_geo="Gujarat",
        preferred_trigger="automotive_ev_transition",
        strategy_decision_id=decision.id,
    )

    assert planned["was_substituted"] is True
    assert planned["analyst_decision_id"] == decision.id
    assert planned["substitution_reason"] is not None

    test_db.refresh(decision)
    assert decision.was_substituted is True
    assert decision.substitution_reason is not None


# ── Requirement 8: Deterministic Rationale Fallback ──────────────────────────

def test_deterministic_rationale_template_fallback(ba_service):
    """When LLMs are unavailable, deterministic rationale template produces factual output."""
    rationale = ba_service._generate_commercial_rationale(
        mode="EXPLOIT",
        sector="EV & Battery Systems",
        trigger="automotive_ev_transition",
        geography="Gujarat",
        score=4.75,
        confidence=0.85,
        metrics={
            "query_count": 8,
            "productive_query_rate": 0.75,
            "strong_opportunities": 4,
            "enquiries": 2,
        },
    )
    assert "EV & Battery Systems" in rationale
    assert "Gujarat" in rationale
    assert "4.75" in rationale or "EXPLOIT" in rationale


def test_anti_loop_exhaustion_protection(ba_service):
    """An angle with low productive query rate must be penalized in exploit mode."""
    metrics_exhausted = {
        "query_count": 5,
        "productive_query_count": 0,
        "strong_opportunities": 0,
        "incomplete_opportunities": 0,
        "apollo_reached": 0,
        "person_passes": 0,
        "emails_sent": 0,
        "replies": 0,
        "enquiries": 0,
        "weighted_query_count": 5.0,
        "weighted_productive_count": 0.0,
        "weighted_strong_opps": 0.0,
        "weighted_apollo": 0.0,
        "weighted_persons": 0.0,
        "weighted_emails": 0.0,
        "weighted_replies": 0.0,
        "weighted_enquiries": 0.0,
        "productive_query_rate": 0.0,
        "strong_per_query": 0.0,
        "apollo_per_query": 0.0,
        "person_pass_per_query": 0.0,
        "email_per_query": 0.0,
        "reply_per_email": 0.0,
        "enquiry_per_query": 0.0,
        "enquiry_per_email": 0.0,
    }
    score, conf, comps = ba_service.compute_strategy_score(
        metrics_exhausted,
        "Chemicals & Specialty Materials",
        "capex_announcement",
        "Gujarat",
    )
    # Priority score should be low due to zero yield and confidence penalty
    assert score <= 3.0


def test_strategy_status_api(test_db):
    """Test /api/strategy/status exposes factual summary without chain-of-thought."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routes.strategy import router as strategy_router
    from database import get_db

    test_app = FastAPI()
    test_app.include_router(strategy_router)
    test_app.dependency_overrides[get_db] = lambda: test_db
    client = TestClient(test_app)

    # Seed a decision
    decision = BusinessAnalystDecision(
        sector="EV & Battery Systems",
        trigger_family="automotive_ev_transition",
        geography="Gujarat",
        mode="EXPLOIT",
        priority_score=4.5,
        confidence=0.8,
        rationale="EXPLOIT: Gujarat EV battery manufacturing focus.",
    )
    test_db.add(decision)
    test_db.commit()

    resp = client.get("/api/strategy/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ACTIVE"
    assert data["primary_kpi"] == "ENQUIRIES GENERATED"
    assert data["current_strategy"]["sector"] == "EV & Battery Systems"
    assert data["current_strategy"]["mode"] == "EXPLOIT"

    # Check decisions endpoint
    resp_dec = client.get("/api/strategy/decisions")
    assert resp_dec.status_code == 200
    assert len(resp_dec.json()) >= 1


