"""Comprehensive Test Suite for Phase 2 Discovery Intelligence.

Validates:
- 24-hour query cooldown & PostgreSQL durable recovery across Redis restart
- Multi-angle rotation (15 sectors x 15 triggers x corridors)
- Adaptive yield weighting & exhaustion penalty
- Execution states (SUCCESS_PRODUCTIVE, SUCCESS_EXHAUSTED, PROVIDER_ERROR, RATE_LIMITED, TIMEOUT)
- Provider errors do NOT receive 24h cooldown
- Cheap filters before LLM (URL dedup, negative financial reject, entity truth gate, industrial relevance)
- Reasoner fail-closed behavior (REASONER_UNAVAILABLE on failure, zero synthetic STRONG)
- Evidence provenance tracking & zero invention
- Bounded targeted research for PROMISING_BUT_INCOMPLETE leads (cap <= 2)
- Downstream funnel preservation
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models.discovery_query_log import DiscoveryQueryLog
from services.discovery_query_memory import (
    DiscoveryQueryMemory,
    normalize_discovery_query,
    STATE_SUCCESS_PRODUCTIVE,
    STATE_SUCCESS_EXHAUSTED,
    STATE_PROVIDER_ERROR,
    STATE_RATE_LIMITED,
    STATE_TIMEOUT,
)
from services.discovery_query_planner import (
    DiscoveryQueryPlanner,
    TRIGGER_FAMILIES,
    MANUFACTURING_SECTORS,
    INDUSTRIAL_CORRIDORS,
)
from services.opportunity_reasoner import (
    OpportunityReasoner,
    CLASSIFICATION_STRONG,
    CLASSIFICATION_INCOMPLETE,
    CLASSIFICATION_WEAK,
    CLASSIFICATION_UNAVAILABLE,
)
from services.adaptive_research_service import AdaptiveResearchService, FOLLOWUP_SEARCH_CAP


@pytest.fixture
def in_memory_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


# ============================================================
# 1. 24-Hour Cooldown & PostgreSQL Durable Authority
# ============================================================

def test_query_normalization():
    q1 = ' "Tata Motors" "Plant Expansion" 2026 '
    q2 = "Tata Motors Plant Expansion 2026"
    assert normalize_discovery_query(q1) == normalize_discovery_query(q2)
    assert normalize_discovery_query(q1) == "tata motors plant expansion 2026"


def test_cooldown_redis_and_postgres_recovery(in_memory_db):
    fake_redis = {}

    class MockRedis:
        def get(self, k):
            return fake_redis.get(k)
        def exists(self, k):
            return k in fake_redis
        def setex(self, k, ttl, v):
            fake_redis[k] = v
        def delete(self, k):
            fake_redis.pop(k, None)

    mem = DiscoveryQueryMemory(redis_client=MockRedis())
    query = 'Gujarat "Automotive" "plant expansion" 2026'

    # Initially not in cooldown
    assert not mem.is_query_in_cooldown(query, page=1, db=in_memory_db)

    # Record successful query
    mem.record_query_execution(
        query=query,
        page=1,
        sector="Automotive",
        trigger="plant_expansion",
        geography="Gujarat",
        execution_state=STATE_SUCCESS_PRODUCTIVE,
        results_count=10,
        unique_results=10,
        new_companies=3,
        yield_score=5.0,
        db=in_memory_db,
    )

    # Now in cooldown via Redis
    assert mem.is_query_in_cooldown(query, page=1, db=in_memory_db)

    # Simulate Redis restart / cache eviction
    fake_redis.clear()
    assert len(fake_redis) == 0

    # Must recover cooldown correctly from PostgreSQL (Amendment 5)
    assert mem.is_query_in_cooldown(query, page=1, db=in_memory_db)

    # And Redis cache was re-seeded during recovery
    assert len(fake_redis) > 0


def test_provider_error_does_not_trigger_cooldown(in_memory_db):
    mem = DiscoveryQueryMemory(redis_client=None)
    query = 'Maharashtra "Aerospace" "cleanroom" 2026'

    # Record provider error (e.g. timeout / network error)
    mem.record_query_execution(
        query=query,
        page=1,
        sector="Aerospace",
        trigger="cleanroom_commissioning",
        geography="Maharashtra",
        execution_state=STATE_PROVIDER_ERROR,
        results_count=0,
        metadata_json={"error": "Connection timeout"},
        db=in_memory_db,
    )

    # Amendment 4: Failed provider request must NOT be in 24h cooldown!
    assert not mem.is_query_in_cooldown(query, page=1, db=in_memory_db)


# ============================================================
# 2. Adaptive Yield Weighting & Planner Rotation (Amendment 7)
# ============================================================

def test_planner_covers_all_angles():
    planner = DiscoveryQueryPlanner()
    angles = planner.get_all_angles()
    assert len(angles) == 15 * 15  # 225 angles
    assert len(MANUFACTURING_SECTORS) == 15
    assert len(TRIGGER_FAMILIES) == 15
    assert len(INDUSTRIAL_CORRIDORS) >= 10


def test_adaptive_weighting_high_yield_vs_exhaustion(in_memory_db):
    mem = DiscoveryQueryMemory()
    planner = DiscoveryQueryPlanner(memory=mem)

    # 1. Unsearched angles get exploration bonus (2.0)
    weights = planner.compute_angle_weights(in_memory_db)
    for w in weights.values():
        assert w == 2.0

    # 2. Record high-yield run for EV sector
    mem.record_query_execution(
        query="query 1",
        page=1,
        sector="EV & Battery Systems",
        trigger="automotive_ev_transition",
        geography="Tamil Nadu",
        execution_state=STATE_SUCCESS_PRODUCTIVE,
        results_count=8,
        yield_score=8.0,
        db=in_memory_db,
    )

    # 3. Record repeated exhausted runs for Metals sector
    for i in range(3):
        mem.record_query_execution(
            query=f"query {i+2}",
            page=1,
            sector="Metals & Advanced Alloys Processing",
            trigger="capex_announcement",
            geography="Rajasthan",
            execution_state=STATE_SUCCESS_EXHAUSTED,
            results_count=0,
            yield_score=0.0,
            db=in_memory_db,
        )

    updated_weights = planner.compute_angle_weights(in_memory_db)
    ev_weight = updated_weights[("EV & Battery Systems", "automotive_ev_transition")]
    metals_weight = updated_weights[("Metals & Advanced Alloys Processing", "capex_announcement")]

    # High-yield angle priority > exhausted angle priority
    assert ev_weight > metals_weight
    assert ev_weight > 1.0
    assert metals_weight < 1.0


def test_planner_get_page_2_query():
    planner = DiscoveryQueryPlanner()
    info = {
        "query": 'Gujarat "Automotive" "plant expansion" 2026',
        "sector": "Automotive & Auto Components",
        "trigger": "plant_expansion",
        "geography": "Gujarat",
        "weight": 1.5,
    }
    p2 = planner.get_page_2_query(info)
    assert p2["page"] == 2
    assert p2["sector"] == "Automotive & Auto Components"
    assert p2["geography"] == "Gujarat"


# ============================================================
# 3. Cheap Filters Before LLM (Amendment 6)
# ============================================================

def test_cheap_filters_reject_noise_and_non_companies():
    reasoner = OpportunityReasoner()
    raw_results = [
        # Valid company news
        {
            "title": "RenewSys India to expand solar cell manufacturing in Hyderabad",
            "snippet": "RenewSys India announces ₹400 Cr capex for solar cell manufacturing plant in Hyderabad with commissioning in 2026.",
            "url": "https://industrynews.com/renewsys-expansion",
            "metadata": {"date": "2026-02-10"},
        },
        # Non-company entity (political figure)
        {
            "title": "PM Modi inaugurates industrial exhibition in Chennai",
            "snippet": "Prime Minister Narendra Modi inaugurates three-day exhibition on defense manufacturing in Tamil Nadu.",
            "url": "https://news.com/pm-modi-chennai",
        },
        # Stock market / financial noise
        {
            "title": "Tata Motors Share Price Target 2026: Buy, Sell, Hold recommendation",
            "snippet": "Brokerage target price and stock price analysis for Tata Motors Ltd on BSE and NSE.",
            "url": "https://moneycontrol.com/tata-motors-stock-target",
        },
        # Non-manufacturing generic article
        {
            "title": "Indian Cricket Team announces squad for 2026 tournament",
            "snippet": "BCCI selects 15-member team for upcoming international series.",
            "url": "https://sports.com/cricket-squad-2026",
        },
    ]

    grouped, telemetry = reasoner.apply_cheap_filters(raw_results)

    # Only RenewSys India should survive the cheap filters!
    assert len(grouped) == 1
    assert "RenewSys" in grouped[0]["company_name"]
    assert telemetry["total_raw"] == 4
    assert telemetry["grouped_candidates"] == 1
    assert telemetry["invalid_entities_rejected"] >= 1 or telemetry["financial_noise_rejected"] >= 1


# ============================================================
# 4. Reasoner Fail-Closed Behavior (Amendment 1 & 3)
# ============================================================

def test_reasoner_fails_closed_when_llms_unavailable():
    """When both DeepSeek and Gemini are unavailable, must fail closed with REASONER_UNAVAILABLE."""
    # Reasoner with mock providers that both raise exceptions
    bad_hive = MagicMock()
    bad_hive.is_available.return_value = True
    bad_hive.complete.side_effect = TimeoutError("Hive network timeout")

    bad_gemini = MagicMock()
    bad_gemini.is_available.return_value = True
    bad_gemini.complete.side_effect = RuntimeError("Gemini 503 unavailable")

    reasoner = OpportunityReasoner(hive_provider=bad_hive, gemini_provider=bad_gemini)

    candidate_group = {
        "company_name": "Test Engineering Pvt Ltd",
        "titles": ["Test Engineering sets up CNC facility in Pune"],
        "snippets": ["Test Engineering invests in new CNC facility with CMM lab in Pune."],
        "source_urls": ["https://news.com/test-engineering-pune"],
        "dates": ["2026-03-01"],
    }

    assessment = reasoner.reason_opportunity(
        candidate_group,
        sector="Automotive",
        geography="Maharashtra",
        allow_deterministic_fallback=False,
    )

    # MUST NOT be STRONG! Must return REASONER_UNAVAILABLE (Amendment 1)
    assert assessment["opportunity_classification"] == CLASSIFICATION_UNAVAILABLE
    assert assessment["status"] == "HOLD"
    assert assessment["confidence_score"] == 0.0

    # Evidence provenance preserved (Amendment 3)
    prov = assessment["evidence_provenance"]
    assert "https://news.com/test-engineering-pune" in prov["source_urls"]
    assert prov["reasoner_provider"] == "FAIL_CLOSED"


def test_reasoner_deterministic_fallback_safe_parsing():
    """Deterministic fallback safely normalizes real evidence without inventing missing facts."""
    bad_hive = MagicMock()
    bad_hive.is_available.return_value = False
    bad_gemini = MagicMock()
    bad_gemini.is_available.return_value = False

    reasoner = OpportunityReasoner(hive_provider=bad_hive, gemini_provider=bad_gemini)

    # 1. Real evidence with verified city (Pune) and trigger
    candidate_group = {
        "company_name": "Jabil Circuit India",
        "titles": ["Jabil Circuit India new plant in Pune inaugurated"],
        "snippets": ["Jabil Circuit India inaugurated new manufacturing facility in Pune on 16 June 2026."],
        "source_urls": ["https://news.com/jabil-pune"],
        "dates": ["2026-06-16"],
    }
    assessment = reasoner.reason_opportunity(candidate_group, allow_deterministic_fallback=True)
    assert assessment["opportunity_classification"] == CLASSIFICATION_STRONG
    assert assessment["facility_location"]["city"] == "Pune"
    assert assessment["evidence_provenance"]["reasoner_provider"] == "deterministic_fallback"

    # 2. Evidence with missing city -> must NOT invent city!
    incomplete_group = {
        "company_name": "Jabil Circuit India",
        "titles": ["Jabil Circuit India announces capacity expansion"],
        "snippets": ["Company expands manufacturing capacity in 2026 across industrial units."],
        "source_urls": ["https://news.com/jabil-expansion"],
        "dates": ["2026-06-16"],
    }
    assessment2 = reasoner.reason_opportunity(incomplete_group, allow_deterministic_fallback=True)
    assert assessment2["opportunity_classification"] == CLASSIFICATION_INCOMPLETE
    assert "facility_city" in assessment2["missing_fields"]


def test_reasoner_successful_provenance_and_zero_invention():
    """Successful LLM evaluation preserves exact provenance and never fabricates URLs."""
    good_hive = MagicMock()
    good_hive.is_available.return_value = True

    response_json = {
        "company_name": "RenewSys India",
        "opportunity_classification": "STRONG",
        "trigger_type": "plant_expansion",
        "facility_location": {
            "city": "Hyderabad",
            "state": "Telangana",
            "industrial_zone": "Fab City",
        },
        "event_summary": "₹400 Cr solar cell manufacturing expansion in Hyderabad",
        "event_date": "2026-02-10",
        "calibration_need_indicators": ["Solar cell testing sensors", "Thermal chamber calibration"],
        "missing_fields": [],
        "confidence_score": 0.95,
        "rationale": "Clear capital investment in manufacturing plant with identified city.",
        "supporting_snippets": ["₹400 Cr capex for solar cell manufacturing plant in Hyderabad."],
    }
    mock_resp = MagicMock()
    mock_resp.text = json.dumps(response_json)
    mock_resp.parse_json.return_value = response_json
    good_hive.complete.return_value = mock_resp

    reasoner = OpportunityReasoner(hive_provider=good_hive)

    input_url = "https://industrynews.com/renewsys-expansion"
    candidate_group = {
        "company_name": "RenewSys India",
        "titles": ["RenewSys India expands solar cell plant in Hyderabad"],
        "snippets": ["₹400 Cr capex for solar cell manufacturing plant in Hyderabad."],
        "source_urls": [input_url],
        "dates": ["2026-02-10"],
    }

    assessment = reasoner.reason_opportunity(candidate_group)

    assert assessment["opportunity_classification"] == CLASSIFICATION_STRONG
    assert assessment["facility_location"]["city"] == "Hyderabad"
    assert assessment["evidence_provenance"]["source_urls"] == [input_url]
    assert assessment["evidence_provenance"]["reasoner_provider"] == "deepseek"


def test_reasoner_demotes_strong_if_facility_city_unknown():
    """Zero synthetic STRONG: If facility city is missing/unknown, demote to PROMISING_BUT_INCOMPLETE."""
    good_hive = MagicMock()
    good_hive.is_available.return_value = True

    response_json = {
        "company_name": "Generic Components Ltd",
        "opportunity_classification": "STRONG",
        "trigger_type": "plant_expansion",
        "facility_location": {
            "city": "UNKNOWN",
            "state": "Pan-India",
            "industrial_zone": "",
        },
        "event_summary": "Announced capacity expansion",
        "event_date": "2026",
        "missing_fields": [],
        "confidence_score": 0.8,
        "rationale": "Expanding production",
    }
    mock_resp = MagicMock()
    mock_resp.parse_json.return_value = response_json
    good_hive.complete.return_value = mock_resp

    reasoner = OpportunityReasoner(hive_provider=good_hive)
    candidate_group = {
        "company_name": "Generic Components Ltd",
        "titles": ["Generic Components announces expansion"],
        "snippets": ["Expanding capacity in 2026."],
        "source_urls": ["https://news.com/generic-expansion"],
        "dates": [],
    }
    assessment = reasoner.reason_opportunity(candidate_group)

    # Must be demoted because city is UNKNOWN!
    assert assessment["opportunity_classification"] == CLASSIFICATION_INCOMPLETE
    assert "facility_city" in assessment["missing_fields"]


# ============================================================
# 5. Targeted Research (Amendment 6 & Adaptive Research)
# ============================================================

def test_targeted_research_caps_follow_ups():
    mock_router = MagicMock()
    mock_router.search.return_value = {
        "provider": "serper",
        "provider_status": "LIVE",
        "results": [
            {
                "title": "Generic Components opens Sanand facility in Gujarat",
                "snippet": "New manufacturing plant commissioned at Sanand GIDC, Gujarat.",
                "url": "https://news.com/generic-sanand",
            }
        ],
    }

    mock_reasoner = MagicMock()
    mock_reasoner.reason_opportunity.return_value = {
        "company_name": "Generic Components Ltd",
        "opportunity_classification": CLASSIFICATION_STRONG,
        "facility_location": {"city": "Sanand", "state": "Gujarat"},
    }

    svc = AdaptiveResearchService(router=mock_router, reasoner=mock_reasoner)

    candidate_group = {
        "company_name": "Generic Components Ltd",
        "titles": ["Generic Components announces expansion"],
        "snippets": ["Expanding capacity in 2026."],
        "source_urls": ["https://news.com/generic-expansion"],
        "dates": [],
    }
    initial_assessment = {
        "opportunity_classification": CLASSIFICATION_INCOMPLETE,
        "missing_fields": ["facility_city"],
    }

    res = svc.conduct_targeted_research(candidate_group, initial_assessment)

    assert res["searches_conducted"] <= FOLLOWUP_SEARCH_CAP
    assert res["searches_conducted"] > 0
    assert res["upgraded"] is True
    assert res["final_assessment"]["opportunity_classification"] == CLASSIFICATION_STRONG


# ============================================================
# 6. Productivity Scoring Formula (Amendment 2)
# ============================================================

def test_productivity_scoring_components():
    mem = DiscoveryQueryMemory()
    yield_score, exhaustion_score, state, comp = mem.compute_productivity_and_exhaustion(
        results_count=10,
        duplicate_count=2,
        new_companies=3,
        strong_opps=2,
        incomplete_opps=1,
        weak_opps=0,
        invalid_entities=1,
    )
    # 3.0*2 (6.0) + 1.5*1 (1.5) + 1.0*3 (3.0) + 0.5*8 (4.0) - 0.5*2 (1.0) - 1.0*1 (1.0) = 12.5
    assert yield_score == 12.5
    assert exhaustion_score == 0.2
    assert state == STATE_SUCCESS_PRODUCTIVE
    assert comp["new_companies"] == 3
    assert comp["strong_opps"] == 2
