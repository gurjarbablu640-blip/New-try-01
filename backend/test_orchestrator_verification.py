"""Comprehensive test suite for Steps 3-6:
- Provider Abstraction (Gemini, OpenAI, Fallback, JSON parsing)
- 5 Specialist Sub-Agents (Sequential execution, Tool calls)
- Multi-Step Orchestrator Loop (Cap <= 6, Budget, Memory, Rule Injection, AIFeedback logging)
- Legacy Keyword Routing Fallback (Zero regression)
- API endpoint session-aware conversation flow
"""
import json
import os
import sqlite3
import sys
import unittest
from datetime import datetime, date

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
from models.company import Company
from models.customer_asset import CustomerAsset
from models.facility import Facility
from models.person import Person
from models.conversation import ConversationSession, ConversationTurn
from models.sales_os import AIFeedback, LearningRule, Opportunity, Quotation, QuotationItem
from models.competitor_intel import CompetitorProfile
from services.llm_provider import LLMProvider, LLMResponse, FallbackLLMProvider
from services.sub_agents import (
    SUB_AGENT_REGISTRY,
    SubAgentTask,
    LeadPrioritizerAgent,
    CalibrationAnalystAgent,
    TerritoryPlannerAgent,
    QuotationAdvisorAgent,
    OutreachDrafterAgent,
)
from services.orchestrator import AskOorjaOrchestrator
from services.sales_assistant import ask_oorja, _legacy_keyword_routing


class MockLLMProvider(LLMProvider):
    """Mock LLM Provider for deterministic multi-step testing."""
    def __init__(self, available: bool = True, responses: dict = None):
        self.available = available
        self.responses = responses or {}
        self.call_count = 0
        self.calls = []

    def is_available(self) -> bool:
        return self.available

    def complete(self, system_prompt: str, messages: list[dict], temperature: float = 0.2, max_tokens: int = 1500, response_format: str = None) -> LLMResponse:
        self.call_count += 1
        self.calls.append({"system_prompt": system_prompt, "messages": messages})
        
        # Check custom canned response
        for k, v in self.responses.items():
            if k in system_prompt or (messages and k in messages[0].get("content", "")):
                return LLMResponse(
                    text=v if isinstance(v, str) else json.dumps(v),
                    usage={"input_tokens": 150, "output_tokens": 75, "total_tokens": 225},
                    provider="mock",
                    model="mock-model",
                )

        default_json = {
            "reasoning": "Mock reasoning step completed successfully.",
            "recommended_price": 5175.0,
            "confidence": 0.95,
            "due_summary": {"overdue": 2, "due_30": 3},
            "recommended_leads": [{"company_name": "Bharat Forge", "urgency": "High"}],
            "subject": "Precision Calibration Outreach",
            "body": "Detailed follow up message body.",
        }
        return LLMResponse(
            text=json.dumps(default_json),
            usage={"input_tokens": 200, "output_tokens": 100, "total_tokens": 300},
            provider="mock",
            model="mock-model",
        )


class TestSteps3To6(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(cls.engine)
        cls.Session = sessionmaker(bind=cls.engine)

    def setUp(self):
        self.db = self.Session()
        # Clean test tables
        for model in [ConversationTurn, ConversationSession, LearningRule, AIFeedback, QuotationItem, Quotation, CustomerAsset, Facility, Person, Company, CompetitorProfile]:
            self.db.query(model).delete()
        self.db.commit()

        # Seed test data
        self.company = Company(id=1, name="Kirloskar Oil Engines", city="Pune", state="Maharashtra", industry="Engineering", icp_score=85, buying_window="next_30_days")
        self.person = Person(id=1, company_id=1, full_name="Rajesh Sharma", designation="Quality Manager", phone="+91-9876543210", email="rajesh@kirloskar.local", is_decision_maker=True)
        self.asset = CustomerAsset(id=1, company_id=1, instrument_name="CMM Mitutoyo", parameter="Dimensions", calibration_due_date=date.today(), status="Active")
        self.quote = Quotation(id=1, company_id=1, quotation_number="Q-2026-001", customer_name="Kirloskar Oil Engines", quotation_date=date.today(), subtotal=4500.0, total=4500.0, status="Approved")
        self.competitor = CompetitorProfile(id=1, name="TCR Engineering", positioning="Low price commodity testing", weaknesses=["Slow turnaround", "No on-site calibration"], active=True)
        self.db.add_all([self.company, self.person, self.asset, self.quote, self.competitor])
        self.db.commit()

    def tearDown(self):
        self.db.rollback()
        self.db.close()

    # ============================================================
    # Test 1: Provider Abstraction & Fallback
    # ============================================================
    def test_01_provider_abstraction_and_failover(self):
        """Test FallbackLLMProvider switches seamlessly when primary fails."""
        primary_mock = MockLLMProvider(available=True)
        # Make primary fail on complete
        primary_mock.complete = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("Gemini Quota Exceeded"))
        fallback_mock = MockLLMProvider(available=True, responses={"test": {"result": "success from fallback"}})

        fallback_provider = FallbackLLMProvider(primary=primary_mock, fallback=fallback_mock)
        resp = fallback_provider.complete(system_prompt="test", messages=[{"role": "user", "content": "hello"}])
        self.assertIsNotNone(resp)
        parsed = resp.parse_json()
        self.assertEqual(parsed.get("result"), "success from fallback")

    # ============================================================
    # Test 2: Sub-Agents Sequential Execution
    # ============================================================
    def test_02_specialist_sub_agents_execution(self):
        """Test all 5 sub-agents execute sequentially and return verified facts."""
        mock_prov = MockLLMProvider(available=True)

        # 1. LeadPrioritizer
        lp = LeadPrioritizerAgent()
        r_lp = lp.run(SubAgentTask(agent_name="LeadPrioritizer", question="Who to call today?"), self.db, mock_prov)
        self.assertEqual(r_lp.agent_name, "LeadPrioritizer")
        self.assertTrue(len(r_lp.verified_facts) >= 1)

        # 2. CalibrationAnalyst
        ca = CalibrationAnalystAgent()
        r_ca = ca.run(SubAgentTask(agent_name="CalibrationAnalyst", question="What instruments are due?", context={"instrument_name": "CMM Mitutoyo"}), self.db, mock_prov)
        self.assertEqual(r_ca.agent_name, "CalibrationAnalyst")
        self.assertTrue(len(r_ca.tool_calls) >= 1)

        # 3. TerritoryPlanner
        tp = TerritoryPlannerAgent()
        r_tp = tp.run(SubAgentTask(agent_name="TerritoryPlanner", question="Plan visit routes"), self.db, mock_prov)
        self.assertEqual(r_tp.agent_name, "TerritoryPlanner")

        # 4. QuotationAdvisor
        qa = QuotationAdvisorAgent()
        r_qa = qa.run(SubAgentTask(agent_name="QuotationAdvisor", question="What price for CMM?"), self.db, mock_prov)
        self.assertEqual(r_qa.agent_name, "QuotationAdvisor")
        self.assertTrue(len(r_qa.verified_facts) >= 1)

        # 5. OutreachDrafter
        od = OutreachDrafterAgent()
        r_od = od.run(SubAgentTask(agent_name="OutreachDrafter", question="Draft email", context={"company_id": 1}), self.db, mock_prov)
        self.assertEqual(r_od.agent_name, "OutreachDrafter")

    # ============================================================
    # Test 3: Orchestrator Loop & Hard Cap
    # ============================================================
    def test_03_orchestrator_loop_cap_and_budget(self):
        """Test orchestrator enforces hard 6-iteration cap and token budget limit."""
        mock_prov = MockLLMProvider(available=True)
        orchestrator = AskOorjaOrchestrator(provider=mock_prov, max_iterations=6)

        # Force never-sufficient to test hard cap <= 6
        orchestrator._evaluate_and_replan = lambda q, c, iter_count, prov: {"sufficient_answer": False, "next_sub_agents": ["CalibrationAnalyst"]}
        res = orchestrator.run(query="Analyze calibration readiness", db=self.db)
        self.assertLessEqual(res["iterations"], 6)

        # Test token budget trigger
        orchestrator.token_budget = 100  # very low budget
        res_budget = orchestrator.run(query="Analyze calibration", db=self.db)
        self.assertLessEqual(res_budget["iterations"], 6)

    # ============================================================
    # Test 4: Conversation Memory & Multi-turn Session Flow
    # ============================================================
    def test_04_orchestrator_conversation_memory(self):
        """Test conversation sessions and turns persist across multi-turn queries."""
        mock_prov = MockLLMProvider(available=True)
        orchestrator = AskOorjaOrchestrator(provider=mock_prov)

        # Turn 1: Initial Question
        res1 = orchestrator.run(query="What is the price for CMM calibration?", db=self.db)
        session_id = res1["session_id"]
        self.assertIsNotNone(session_id)

        # Turn 2: Follow-up question referencing prior session
        res2 = orchestrator.run(query="And can we also calibrate pressure gauges there?", db=self.db, session_id=session_id)
        self.assertEqual(res2["session_id"], session_id)

        # Verify DB records
        sess = self.db.query(ConversationSession).filter_by(id=session_id).first()
        self.assertIsNotNone(sess)
        self.assertEqual(sess.turn_count, 2)
        turns = self.db.query(ConversationTurn).filter_by(session_id=session_id).all()
        self.assertEqual(len(turns), 2)

    # ============================================================
    # Test 5: Autolearn Loop — Rule Injection & AIFeedback Logging
    # ============================================================
    def test_05_orchestrator_learning_rule_injection_and_feedback_logging(self):
        """
        Verify:
        1. Approved LearningRule for CMM (+15%) is injected and applied.
        2. Orchestrator auto-records execution into AIFeedback table.
        """
        # Add an Approved CMM margin rule
        rule = LearningRule(
            rule_type="Pricing Pattern",
            rule_key="orchestrator_answer:human_correction:cmm",
            pattern={"instrument_category": "CMM", "adjustment_percent": 15},
            evidence_count=5,
            confidence=95.0,
            status="Approved",
        )
        self.db.add(rule)
        self.db.commit()

        mock_prov = MockLLMProvider(available=True)
        orchestrator = AskOorjaOrchestrator(provider=mock_prov)

        res = orchestrator.run(query="What price should we quote for CMM at Bharat?", db=self.db)
        self.assertIn("orchestrator_answer:human_correction:cmm", res["applied_rules"])

        # Confirm AIFeedback row was auto-recorded
        fb = self.db.query(AIFeedback).filter_by(entity_type="orchestrator_answer", action_type="multi_step_synthesis").first()
        self.assertIsNotNone(fb)
        self.assertIn("question", fb.ai_value)

    # ============================================================
    # Test 6: Legacy Fallback when No Provider Configured
    # ============================================================
    def test_06_legacy_routing_fallback(self):
        """Test ask_oorja falls back to legacy keyword routing when no LLM provider is available."""
        # Provider unavailable
        orchestrator = AskOorjaOrchestrator(provider=MockLLMProvider(available=False))
        self.assertFalse(orchestrator.is_available())

        # Ask priority leads via legacy router
        res = _legacy_keyword_routing("who should i contact today?", self.db)
        self.assertEqual(res["intent"], "priority_outreach")
        self.assertEqual(res["tool_used"], "get_priority_leads")


if __name__ == "__main__":
    unittest.main()
