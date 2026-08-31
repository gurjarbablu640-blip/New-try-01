"""Verification test suite for Checkpoint 1 (Step 1 & Step 2).

Verifies:
1. Conversation memory models (ConversationSession, ConversationTurn) persist, query, and cascade correctly.
2. Sub-pattern extraction in generate_candidate_rules:
   - < 3 orchestrator_answer feedback items does NOT trigger rule creation.
   - >= 3 orchestrator_answer feedback items with sub-patterns (e.g. CMM pricing correction)
     generates a clean, isolated 'Pricing Pattern' rule with evidence_count >= 3.
   - Preserves >= 1 threshold for non-orchestrator entity_types.
   - Ensures rules are properly isolated and not lumped together.
"""
import json
import os
import sqlite3
import sys
import unittest
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.types import ARRAY
from sqlalchemy.dialects.postgresql import JSONB

# SQLite adapter for Python dicts/lists and JSONB in tests
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
from models.conversation import ConversationSession, ConversationTurn
from models.sales_os import AIFeedback, LearningRule
from routes.learning_analytics import generate_candidate_rules_core, _extract_feedback_group_key


class TestCheckpoint1(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(cls.engine)
        cls.Session = sessionmaker(bind=cls.engine)

    def setUp(self):
        self.db = self.Session()
        # Clean test tables
        self.db.query(ConversationTurn).delete()
        self.db.query(ConversationSession).delete()
        self.db.query(LearningRule).delete()
        self.db.query(AIFeedback).delete()
        self.db.commit()

    def tearDown(self):
        self.db.rollback()
        self.db.close()

    def test_01_conversation_memory_models(self):
        """Test ConversationSession and ConversationTurn CRUD and cascading."""
        session = ConversationSession(
            id="test-session-uuid-1",
            turn_count=2,
            summary="Discussion about CMM calibration in Pune",
            context_snapshot={"company_id": 10, "last_intent": "pricing_inquiry"},
            status="active"
        )
        self.db.add(session)
        self.db.commit()

        turn1 = ConversationTurn(
            session_id=session.id,
            turn_number=1,
            role="user",
            content="What is the price for CMM calibration?",
            iteration_count=1,
        )
        turn2 = ConversationTurn(
            session_id=session.id,
            turn_number=2,
            role="orchestrator",
            agent_name="QuotationAdvisor",
            content="Estimated price for CMM calibration is INR 5,175.",
            tool_calls=[{"tool": "get_quotation_history", "args": {"instrument": "CMM"}}],
            reasoning_trace=[{"step": "analyze_cues", "confidence": 0.95}],
            iteration_count=2,
            tokens_used={"input": 450, "output": 120, "provider": "gemini"},
        )
        self.db.add_all([turn1, turn2])
        self.db.commit()

        # Query session back
        loaded = self.db.query(ConversationSession).filter_by(id="test-session-uuid-1").first()
        self.assertIsNotNone(loaded)
        self.assertEqual(len(loaded.turns), 2)
        self.assertEqual(loaded.turns[0].content, "What is the price for CMM calibration?")
        self.assertEqual(loaded.turns[1].agent_name, "QuotationAdvisor")
        self.assertEqual(loaded.turns[1].iteration_count, 2)

        # Test cascading deletion
        self.db.delete(loaded)
        self.db.commit()
        turns_count = self.db.query(ConversationTurn).filter_by(session_id="test-session-uuid-1").count()
        self.assertEqual(turns_count, 0)

    def test_02_orchestrator_sub_pattern_extraction(self):
        """Test _extract_feedback_group_key properly isolates CMM instrument corrections."""
        fb_cmm = AIFeedback(
            entity_type="orchestrator_answer",
            action_type="human_correction",
            ai_value={"recommended_price": 4500, "instrument_category": "CMM"},
            human_value={"corrected_price": 5175, "adjustment_percent": 15, "instrument_category": "CMM"},
            reason="CMM requires 15% margin premium for special setup jigs",
        )
        rule_key, rule_type, pattern = _extract_feedback_group_key(fb_cmm)
        self.assertEqual(rule_key, "orchestrator_answer:human_correction:cmm")
        self.assertEqual(rule_type, "Pricing Pattern")
        self.assertEqual(pattern["instrument_category"], "CMM")
        self.assertEqual(pattern["adjustment_percent"], 15)

    def test_03_generate_candidate_rules_thresholds_and_isolation(self):
        """
        Verify:
        1. 2 orchestrator feedback items for CMM -> 0 candidate rules (< 3 threshold).
        2. 3rd orchestrator feedback item for CMM -> 1 Candidate rule created with evidence_count=3.
        3. 1 non-orchestrator feedback item (e.g. quotation) -> 1 Candidate rule created (>= 1 threshold).
        4. CMM and Vernier feedback are isolated into separate rules, not lumped!
        """
        # Step 1: Add 2 CMM corrections
        for i in range(2):
            self.db.add(AIFeedback(
                entity_type="orchestrator_answer",
                action_type="human_correction",
                ai_value={"recommended_price": 4500, "instrument": "CMM"},
                human_value={"corrected_price": 5175, "adjustment_percent": 15, "instrument_category": "CMM"},
                reason="CMM margin +15%",
            ))
        self.db.commit()

        # Run generate-rules -> Should produce 0 rules because threshold is 3 for orchestrator_answer
        res1 = generate_candidate_rules_core(self.db)
        self.assertEqual(res1["new_candidate_rules"], 0)
        self.assertEqual(self.db.query(LearningRule).count(), 0)

        # Step 2: Add 3rd CMM correction
        self.db.add(AIFeedback(
            entity_type="orchestrator_answer",
            action_type="human_correction",
            ai_value={"recommended_price": 4500, "instrument": "CMM"},
            human_value={"corrected_price": 5175, "adjustment_percent": 15, "instrument_category": "CMM"},
            reason="CMM margin +15%",
        ))
        self.db.commit()

        # Run generate-rules -> Now triggers clean CMM rule
        res2 = generate_candidate_rules_core(self.db)
        self.assertEqual(res2["new_candidate_rules"], 1)

        cmm_rule = self.db.query(LearningRule).filter_by(rule_key="orchestrator_answer:human_correction:cmm").first()
        self.assertIsNotNone(cmm_rule)
        self.assertEqual(cmm_rule.rule_type, "Pricing Pattern")
        self.assertEqual(cmm_rule.evidence_count, 3)
        self.assertEqual(cmm_rule.status, "Candidate")
        self.assertEqual(cmm_rule.pattern["instrument_category"], "CMM")
        self.assertEqual(cmm_rule.pattern["adjustment_percent"], 15)

        # Step 3: Add 1 legacy quotation feedback item -> should immediately create rule (min_threshold=1)
        self.db.add(AIFeedback(
            entity_type="quotation",
            action_type="discount_override",
            ai_value={"discount": 5},
            human_value={"discount": 10},
            reason="Volume discount for corporate client",
        ))
        self.db.commit()

        res3 = generate_candidate_rules_core(self.db)
        self.assertEqual(res3["new_candidate_rules"], 1)

        legacy_rule = self.db.query(LearningRule).filter_by(rule_key="quotation:discount_override").first()
        self.assertIsNotNone(legacy_rule)
        self.assertEqual(legacy_rule.evidence_count, 1)
        self.assertEqual(legacy_rule.rule_type, "Heuristic Optimization")

        # Step 4: Verify CMM rule and legacy rule are strictly separated
        total_rules = self.db.query(LearningRule).all()
        self.assertEqual(len(total_rules), 2)
        keys = [r.rule_key for r in total_rules]
        self.assertIn("orchestrator_answer:human_correction:cmm", keys)
        self.assertIn("quotation:discount_override", keys)

    def test_04_sub_pattern_isolation_within_same_entity_action_type(self):
        """
        Verify that multiple instrument sub-patterns within the same entity_type:action_type
        are strictly isolated into separate Candidate rules without cross-contamination.
        """
        # 3 feedback items for CMM (+15%)
        for i in range(3):
            self.db.add(AIFeedback(
                entity_type="orchestrator_answer",
                action_type="human_correction",
                ai_value={"recommended_price": 4500, "instrument_category": "CMM"},
                human_value={"corrected_price": 5175, "adjustment_percent": 15, "instrument_category": "CMM"},
                reason="CMM requires 15% margin premium for special setup jigs",
            ))

        # 3 feedback items for Pressure Gauge (+8%)
        for i in range(3):
            self.db.add(AIFeedback(
                entity_type="orchestrator_answer",
                action_type="human_correction",
                ai_value={"recommended_price": 800, "instrument_category": "Pressure Gauge"},
                human_value={"corrected_price": 864, "adjustment_percent": 8, "instrument_category": "Pressure Gauge"},
                reason="Pressure Gauge requires 8% margin adjustment",
            ))

        self.db.commit()

        # Run generate-rules once with all 6 present
        res = generate_candidate_rules_core(self.db)
        self.assertEqual(res["new_candidate_rules"], 2)

        total_rules = self.db.query(LearningRule).all()
        self.assertEqual(len(total_rules), 2)

        # Assert CMM rule
        cmm_rule = self.db.query(LearningRule).filter_by(rule_key="orchestrator_answer:human_correction:cmm").first()
        self.assertIsNotNone(cmm_rule)
        self.assertEqual(cmm_rule.evidence_count, 3)
        self.assertEqual(cmm_rule.status, "Candidate")
        self.assertEqual(cmm_rule.rule_type, "Pricing Pattern")
        self.assertEqual(cmm_rule.pattern["instrument_category"], "CMM")
        self.assertEqual(cmm_rule.pattern["adjustment_percent"], 15)
        self.assertIn("special setup jigs", cmm_rule.pattern["sample_reason"])

        # Assert Pressure Gauge rule
        pg_rule = self.db.query(LearningRule).filter_by(rule_key="orchestrator_answer:human_correction:pressure_gauge").first()
        self.assertIsNotNone(pg_rule)
        self.assertEqual(pg_rule.evidence_count, 3)
        self.assertEqual(pg_rule.status, "Candidate")
        self.assertEqual(pg_rule.rule_type, "Pricing Pattern")
        self.assertEqual(pg_rule.pattern["instrument_category"], "Pressure Gauge")
        self.assertEqual(pg_rule.pattern["adjustment_percent"], 8)
        self.assertIn("8% margin adjustment", pg_rule.pattern["sample_reason"])

    def test_05_orchestrator_fallback_without_sub_fields(self):
        """
        Verify that orchestrator feedback lacking specific sub-fields (e.g. territory/visit questions)
        safely falls back to generic entity_type:action_type without throwing.
        """
        fb_territory = AIFeedback(
            entity_type="orchestrator_answer",
            action_type="territory_reroute",
            ai_value={"cluster": "Chakan", "stops": 3},
            human_value={"cluster": "Bhosari", "stops": 4},
            reason="Prioritize Bhosari cluster due to higher urgent asset count",
        )
        rule_key, rule_type, pattern = _extract_feedback_group_key(fb_territory)
        self.assertEqual(rule_key, "orchestrator_answer:territory_reroute")
        self.assertEqual(rule_type, "Heuristic Optimization")
        self.assertIn("Prioritize Bhosari", pattern["sample_reason"])


if __name__ == "__main__":
    unittest.main()
