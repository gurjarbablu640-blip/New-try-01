"""Unit and Integration Test Suite for Salesoorja Reasoning Foundation.

Tests:
1. Epistemic Classification (FACT / INFERENCE / HYPOTHESIS)
2. Temporal Decay & Staleness Computation
3. Domain Causal Graph Execution & Belief Shifting
4. Contradiction Detection & Adaptive Research Task Spawning
5. Scoring vs Decision Policy Engine Separation
6. Case-Based Reasoning (CBR) Archetype Matching
"""
from datetime import datetime, timedelta
import json
import os
import sqlite3
import sys
import unittest

from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.types import ARRAY
from sqlalchemy.dialects.postgresql import JSONB

sqlite3.register_adapter(list, json.dumps)
sqlite3.register_adapter(dict, json.dumps)

@compiles(ARRAY, "sqlite")
def compile_array_sqlite(type_, compiler, **kw):
    return "TEXT"

@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "TEXT"

backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from database import Base
from models.company import Company
from models.reasoning_engine import CompanyBeliefState, SignalEvidenceNode
from services.reasoning_engine import (
    EpistemicType,
    calculate_temporal_decay,
    get_or_create_belief_state,
    update_belief_with_evidence,
    execute_decision_policy,
    find_similar_customer_cases,
    CAUSAL_TEMPLATES,
)


class TestReasoningFoundationSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(cls.engine)
        cls.Session = sessionmaker(bind=cls.engine)

    def setUp(self):
        self.db = self.Session()
        self.company = Company(
            name="Endurance Technologies Ltd",
            domain="endurancegroup.com",
            industry="Automotive Components",
            city="Pune",
            country="India",
            icp_score=82,
            buying_window="immediate",
        )
        self.db.add(self.company)
        self.db.commit()
        self.db.refresh(self.company)

    def tearDown(self):
        self.db.query(SignalEvidenceNode).delete()
        self.db.query(CompanyBeliefState).delete()
        self.db.query(Company).delete()
        self.db.commit()
        self.db.close()

    def test_01_epistemic_tagging_and_initial_prior(self):
        """Test initial belief state creation with explicit epistemic tags."""
        state = get_or_create_belief_state(self.company, self.db)
        self.assertIsNotNone(state)
        self.assertEqual(state.company_id, self.company.id)
        
        beliefs = state.beliefs
        self.assertIn("calibration_need", beliefs)
        self.assertIn("buy_probability", beliefs)
        self.assertIn("price_sensitivity", beliefs)
        self.assertIn("premium_potential", beliefs)
        
        # Check epistemic distinction
        self.assertIn(beliefs["calibration_need"]["epistemic_type"], [EpistemicType.INFERENCE.value, EpistemicType.FACT.value])
        self.assertEqual(beliefs["buying_window"]["epistemic_type"], EpistemicType.HYPOTHESIS.value)
        self.assertEqual(beliefs["price_sensitivity"]["epistemic_type"], EpistemicType.HYPOTHESIS.value)

    def test_02_temporal_decay_and_staleness(self):
        """Test exponential decay on stale vs fresh signal evidence."""
        # Fresh signal (0 days elapsed)
        fresh = calculate_temporal_decay(
            initial_confidence=0.90,
            event_time=datetime.utcnow(),
            detection_time=datetime.utcnow(),
            staleness_days=90,
            daily_decay_rate=0.01,
        )
        self.assertEqual(fresh["temporal_status"], "active")
        self.assertFalse(fresh["is_stale"])
        self.assertAlmostEqual(fresh["effective_confidence"], 0.90, delta=0.02)

        # Stale signal (120 days elapsed vs 90-day threshold)
        stale_time = datetime.utcnow() - timedelta(days=120)
        stale = calculate_temporal_decay(
            initial_confidence=0.90,
            event_time=stale_time,
            detection_time=stale_time,
            staleness_days=90,
            daily_decay_rate=0.01,
        )
        self.assertEqual(stale["temporal_status"], "stale")
        self.assertTrue(stale["is_stale"])
        self.assertLess(stale["effective_confidence"], 0.35)

    def test_03_causal_template_execution_and_belief_shift(self):
        """Test causal template execution shifting calibration need and logging trace."""
        res = update_belief_with_evidence(
            company=self.company,
            db=self.db,
            epistemic_type=EpistemicType.FACT,
            signal_type="plant_expansion",
            title="₹300 Cr Machining Plant Inauguration in Chakan",
            description="Commissioning 12 new 5-axis CNC machining bays and CMM inspection cell.",
            source="Press Release & Stock Exchange Filing",
            source_reliability=0.95,
            causal_template_key="plant_expansion",
        )
        self.assertEqual(res["epistemic_type"], EpistemicType.FACT.value)
        self.assertFalse(res["contradiction_detected"])
        
        # Check resulting belief shift
        need = res["belief_state"]["calibration_need"]
        self.assertGreaterEqual(need["value"], 0.80)
        self.assertIn("Press Release", str(need["supporting_evidence"]))
        
        # Check inspectable causal trace
        trace = res["reasoning_trace"]
        self.assertIn("Facility Expansion Announcement", trace["causal_path"])
        self.assertIn("Mandatory NABL Calibration Schedule", trace["causal_path"])

    def test_04_contradiction_handling_and_adaptive_research(self):
        """Test contradiction recording, confidence penalty, and research task spawning."""
        res = update_belief_with_evidence(
            company=self.company,
            db=self.db,
            epistemic_type=EpistemicType.INFERENCE,
            signal_type="plant_expansion",
            title="New Plant Commissioned",
            description="Article states Chakan unit is active.",
            source="Industry News",
            source_reliability=0.70,
            contradicting_statement="Procurement officer noted plant civil work delayed by 9 months.",
        )
        self.assertTrue(res["contradiction_detected"])
        
        state = get_or_create_belief_state(self.company, self.db)
        self.assertEqual(len(state.contradictions), 1)
        self.assertEqual(len(state.active_research_tasks), 1)
        
        # Verify research task structure
        task = state.active_research_tasks[0]
        self.assertIn("Verify whether", task["question_to_answer"])
        self.assertEqual(task["priority"], "High")

    def test_05_decision_policy_separation_from_scoring(self):
        """Test decision policy enforcing research when contradictions exist vs calling when clear."""
        # Case A: Clear High-Value Opportunity -> Priority Call
        policy_clear = execute_decision_policy(self.company, self.db)
        self.assertEqual(policy_clear["decision"], "PRIORITY_PHONE_CALL")
        self.assertIn("Phone", policy_clear["channel"])

        # Case B: Introduce Contradiction -> Policy switches to Adaptive Research
        update_belief_with_evidence(
            company=self.company,
            db=self.db,
            epistemic_type=EpistemicType.INFERENCE,
            signal_type="plant_expansion",
            title="Expansion Reported",
            description="Reported expansion",
            source="News",
            contradicting_statement="Contact stated plant on hold.",
        )
        policy_contra = execute_decision_policy(self.company, self.db)
        self.assertEqual(policy_contra["decision"], "ADAPTIVE_RESEARCH")
        self.assertEqual(policy_contra["policy_rule_fired"], "POLICY_CONTRADICTION_SAFETY_GUARD")

    def test_06_case_based_reasoning_archetypes(self):
        """Test Case-Based Reasoning (CBR) archetype matching."""
        cases = find_similar_customer_cases(self.company)
        self.assertGreater(len(cases), 0)
        
        top_match = cases[0]
        self.assertEqual(top_match["industry"], "Automotive")
        self.assertGreaterEqual(top_match["similarity_score"], 0.85)
        self.assertIn("Dimensional", top_match["typical_parameters"])
        self.assertIn("Quality Head", top_match["winning_pitch_role"])


if __name__ == "__main__":
    unittest.main()
