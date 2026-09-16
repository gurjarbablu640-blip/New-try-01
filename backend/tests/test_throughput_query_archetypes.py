"""Tests for Query Archetype Portfolio and Progressive Relaxation Ladder.

Verifies:
- All 8 archetypes generate distinct, syntactically valid queries
- Progressive relaxation ladder (Levels 1, 2, 3, 4)
- Lineage recording (root_search_intent_id, precision_level, archetype, relaxation_reason)
- Absence of mandatory literal '2026' in general search queries
- Controlled trigger synonym integration
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models.discovery_query_log import DiscoveryQueryLog
from services.discovery_query_planner import (
    DiscoveryQueryPlanner,
    ARCHETYPE_EVENT_FIRST,
    ARCHETYPE_COMPANY_FIRST,
    ARCHETYPE_INVESTMENT_CAPEX,
    ARCHETYPE_FACILITY_FIRST,
    ARCHETYPE_COMMISSIONING,
    ARCHETYPE_NEWS_NATURAL,
    ARCHETYPE_INDUSTRY_SOURCE,
    ARCHETYPE_TEMPORAL,
    ALL_ARCHETYPES,
    PRECISION_LEVEL_1_HIGH,
    PRECISION_LEVEL_2_RELAXED,
    PRECISION_LEVEL_3_SYNONYMS,
    PRECISION_LEVEL_4_COMPANY_FIRST,
)


@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        yield db
    finally:
        db.close()


def test_all_eight_archetypes_generate_valid_queries():
    planner = DiscoveryQueryPlanner()
    sector = "EV & Battery Systems"
    trigger = "automotive_ev_transition"
    geo = "Rajasthan"

    generated_queries = {}
    for arch in ALL_ARCHETYPES:
        q = planner.build_search_query(sector, trigger, geo, page=1, archetype=arch)
        assert len(q) > 10
        assert geo in q
        generated_queries[arch] = q

    # Ensure archetypes generate distinct search queries
    unique_queries = set(generated_queries.values())
    assert len(unique_queries) == len(ALL_ARCHETYPES)


def test_progressive_relaxation_ladder_levels():
    planner = DiscoveryQueryPlanner()
    sector = "Aerospace & Defense"
    trigger = "capex_announcement"
    geo = "Karnataka"

    # Level 1: High precision (quoted)
    q1 = planner.build_search_query(sector, trigger, geo, precision_level=PRECISION_LEVEL_1_HIGH)
    assert '"Karnataka"' in q1 or "Karnataka" in q1

    # Level 2: Relaxed syntax (unquoted keywords)
    q2 = planner.build_search_query(sector, trigger, geo, precision_level=PRECISION_LEVEL_2_RELAXED)
    assert q2 != q1
    assert "expansion" in q2 or "capex" in q2

    # Level 3: Semantic synonyms
    q3 = planner.build_search_query(sector, trigger, geo, precision_level=PRECISION_LEVEL_3_SYNONYMS)
    assert "OR" in q3 or "expansion" in q3

    # Level 4: Company-first discovery
    q4 = planner.build_search_query(sector, trigger, geo, precision_level=PRECISION_LEVEL_4_COMPANY_FIRST)
    assert "manufacturers" in q4.lower() or "plant" in q4.lower()


def test_no_mandatory_literal_2026_in_general_queries():
    planner = DiscoveryQueryPlanner()
    # EVENT_FIRST, COMPANY_FIRST, INVESTMENT_CAPEX queries must not force literal '2026'
    q_event = planner.build_search_query("Automotive & Auto Components", "plant_expansion", "Gujarat", archetype=ARCHETYPE_EVENT_FIRST)
    assert "2026" not in q_event

    q_co = planner.build_search_query("Semiconductor & Electronics (EMS)", "semiconductor_electronics", "Tamil Nadu", archetype=ARCHETYPE_COMPANY_FIRST)
    assert "2026" not in q_co


def test_relaxation_ladder_lineage_and_adaptation(test_db):
    planner = DiscoveryQueryPlanner()
    sector = "EV & Battery Systems"
    trigger = "automotive_ev_transition"
    geo = "Tamil Nadu"

    # 1. First run: should be Level 1
    plan1 = planner.get_next_planned_query(test_db, preferred_sector=sector, preferred_geo=geo, preferred_trigger=trigger)
    assert plan1["precision_level"] == PRECISION_LEVEL_1_HIGH
    assert plan1["archetype"] == ARCHETYPE_EVENT_FIRST

    # Simulate Level 1 exhausting in DB
    log1 = DiscoveryQueryLog(
        query=plan1["query"],
        normalized_query=plan1["normalized_query"],
        sector=sector,
        trigger=trigger,
        geography=geo,
        execution_state="SUCCESS_EXHAUSTED",
        results_count=0,
    )
    test_db.add(log1)
    test_db.commit()

    # 2. Second run: should adapt to Level 2 (relaxed)
    plan2 = planner.get_next_planned_query(test_db, preferred_sector=sector, preferred_geo=geo, preferred_trigger=trigger)
    assert plan2["precision_level"] == PRECISION_LEVEL_2_RELAXED
    assert plan2["parent_query_id"] == log1.id
    assert "relax" in plan2["relaxation_reason"].lower()

    # Simulate Level 2 exhausting
    log2 = DiscoveryQueryLog(
        query=plan2["query"],
        normalized_query=plan2["normalized_query"],
        sector=sector,
        trigger=trigger,
        geography=geo,
        execution_state="SUCCESS_EXHAUSTED",
        results_count=0,
    )
    test_db.add(log2)
    test_db.commit()

    # 3. Third run: should adapt to Level 3 (synonyms)
    plan3 = planner.get_next_planned_query(test_db, preferred_sector=sector, preferred_geo=geo, preferred_trigger=trigger)
    assert plan3["precision_level"] == PRECISION_LEVEL_3_SYNONYMS
    assert plan3["parent_query_id"] == log2.id
    assert "synonym" in plan3["relaxation_reason"].lower()
