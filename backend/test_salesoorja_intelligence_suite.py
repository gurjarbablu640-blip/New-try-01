"""Comprehensive Salesoorja Intelligence Test Suite.

Verifies:
1. Company Brain & Timeline (Facts, provenance, chronological multi-source timeline)
2. Calibration Need Inference & Cost of Inaction (Equipment taxonomy, population tiers, risk exposure)
3. Multi-Dimensional Lead Scoring (Vector scoring, strategic segment, score change explainability)
4. Regulatory Radar (Legal Metrology, BIS, NABL matching, 5-question impact)
5. AI Lead Research Brief & Role-Specific Pitches (Quality vs Purchase vs Maintenance vs CFO)
6. Revenue Autopilot & Deal Rescue (Highest-probability next actions, white-space map)
7. Call Intelligence & Objection Playbook (Pre-call brief, transcript parsing, sales score)
8. Master Sales ML Dataset (Structured feature records, conversion metrics)
9. Orchestrator Sub-Agents (RegulatorySpecialist and RevenueAutopilot integration)
"""
from datetime import date, datetime, timedelta
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
from models.customer_asset import CustomerAsset
from models.person import Person
from models.sales_os import Quotation, QuotationItem
from models.company_brain import CompanyIntelligenceFact, CompanyTimelineEvent, StakeholderIntelligence, RegulatoryIntelligence
from services.company_brain import record_intelligence_fact, record_timeline_event, build_company_timeline, get_company_brain_dossier
from services.calibration_inference_engine import infer_calibration_need, estimate_instrument_population, calculate_cost_of_inaction
from services.lead_intelligence_scorer import evaluate_lead_intelligence
from services.regulatory_radar import seed_default_regulatory_intelligence, match_companies_for_regulation, scan_regulatory_radar_for_company
from services.lead_research_brief import generate_lead_research_brief, generate_role_specific_pitch
from services.revenue_autopilot import compute_next_best_revenue_action, generate_account_whitespace_map, diagnose_deal_rescue
from services.call_intelligence import generate_pre_call_brief, analyze_call_transcript
from services.sales_dataset_pipeline import extract_sales_ml_dataset
from services.orchestrator import AskOorjaOrchestrator
from services.llm_provider import LLMProvider, LLMResponse


class MockTestProvider(LLMProvider):
    def is_available(self) -> bool:
        return True

    def complete(self, system_prompt: str, messages: list[dict], temperature: float = 0.2, max_tokens: int = 1500, response_format: str = None) -> LLMResponse:
        return LLMResponse(
            text=json.dumps({"reasoning": "Synthesized intelligence", "answer": "Analysis complete", "confidence": 0.95}),
            usage={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
            provider="mock-test",
            model="mock",
        )


class TestSalesoorjaIntelligenceSuite(unittest.TestCase):

    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(self.engine)
        Session = sessionmaker(bind=self.engine)
        self.db = Session()

        # Seed realistic target company
        self.comp = Company(
            id=1,
            name="Mahindra Auto Components Ltd",
            city="Chakan",
            state="Maharashtra",
            industry="Automotive",
            icp_score=88,
            buying_window="30_days",
            created_at=datetime.utcnow() - timedelta(days=60),
        )
        self.person_qa = Person(
            id=1,
            company_id=1,
            full_name="Rajesh Verma",
            designation="Head of Quality Assurance",
            email="rajesh.verma@mahindra-ac.local",
            phone="+91-9823001122",
            department="Quality",
            is_decision_maker=True,
        )
        self.person_pur = Person(
            id=2,
            company_id=1,
            full_name="Amit Shinde",
            designation="Procurement Manager",
            email="amit.shinde@mahindra-ac.local",
            phone="+91-9823003344",
            department="Purchase",
            is_decision_maker=False,
        )
        self.asset1 = CustomerAsset(
            id=1,
            company_id=1,
            instrument_name="Mitutoyo CNC CMM",
            parameter="Dimensional",
            calibration_due_date=date.today() - timedelta(days=5),  # Overdue
            status="Active",
        )
        self.asset2 = CustomerAsset(
            id=2,
            company_id=1,
            instrument_name="Yokogawa Digital Power Meter",
            parameter="Electrical",
            calibration_due_date=date.today() + timedelta(days=20),
            status="Active",
        )
        self.quote = Quotation(
            id=1,
            company_id=1,
            quotation_number="Q-2026-MAC-001",
            customer_name="Mahindra Auto Components Ltd",
            quotation_date=date.today() - timedelta(days=12),
            subtotal=85000.0,
            total=85000.0,
            status="Submitted",
        )

        self.db.add_all([self.comp, self.person_qa, self.person_pur, self.asset1, self.asset2, self.quote])
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_01_company_brain_and_timeline(self):
        # 1. Add verifiable intelligence facts
        f1 = record_intelligence_fact(
            db=self.db,
            company_id=1,
            category="equipment",
            fact_key="cnc_chakan_line_3",
            fact_value={"machine_count": 8, "type": "5-Axis VMC"},
            source="website_scrape",
            source_url="https://mahindra-ac.local/facilities",
            confidence=0.92,
            evidence_text="Expanded Chakan facility with 8 new 5-Axis VMCs.",
        )
        self.assertEqual(f1.category, "equipment")
        self.assertTrue(f1.confidence > 0.90)

        # 2. Add Timeline Event
        ev = record_timeline_event(
            db=self.db,
            company_id=1,
            event_type="plant_expansion",
            title="Chakan Facility Expansion Inauguration",
            event_date=date.today() - timedelta(days=20),
            impact_level="high",
            buying_window_impact="immediate_window",
            source="industry_news",
        )
        self.assertEqual(ev.impact_level, "high")

        # 3. Verify Compiled Timeline
        timeline = build_company_timeline(self.db, 1)
        self.assertTrue(len(timeline) >= 3)  # event + quotation + assets
        types = [t["event_type"] for t in timeline]
        self.assertIn("plant_expansion", types)
        self.assertIn("quotation_submitted", types)
        self.assertIn("calibration_overdue", types)

        # 4. Verify Company Brain Dossier
        dossier = get_company_brain_dossier(self.db, 1)
        self.assertEqual(dossier["company_name"], "Mahindra Auto Components Ltd")
        self.assertEqual(len(dossier["stakeholder_network"]), 2)
        self.assertIn("equipment", dossier["facts"])

    def test_02_calibration_inference_and_cost_of_inaction(self):
        # 1. Calibration Need Inference
        inference = infer_calibration_need(self.comp, self.db)
        params = [p["parameter"] for p in inference["parameter_inferences"]]
        self.assertIn("Dimensional", params)
        self.assertIn("Torque", params)
        self.assertIn("Pressure", params)
        self.assertTrue(inference["parameter_inferences"][0]["probability"] >= 0.85)

        # 2. Multi-Tier Population Estimation
        pop = estimate_instrument_population(self.comp, self.db)
        self.assertEqual(pop["known_instruments_count"], 2)
        self.assertTrue(pop["estimated_total_instruments"] > 50)
        self.assertTrue(pop["estimated_annual_calibration_market_inr"] > 100000.0)

        # 3. Cost of Inaction
        coi = calculate_cost_of_inaction(self.comp, self.db)
        self.assertTrue(coi["total_estimated_exposure_inr"] > 200000.0)
        self.assertIn("₹", coi["premium_justification"]["value_statement"])

    def test_03_multi_dimensional_lead_scoring_and_explainability(self):
        # Record expansion event
        record_timeline_event(self.db, 1, "plant_expansion", "Plant expansion", event_date=date.today())

        scorecard = evaluate_lead_intelligence(self.comp, self.db)
        self.assertTrue(scorecard.composite_score >= 80)
        self.assertTrue(scorecard.buy_probability >= 0.80)
        self.assertEqual(scorecard.price_sensitivity, "Low")
        self.assertIn(scorecard.premium_potential, ["High", "Very High"])
        self.assertEqual(scorecard.strategic_segment, "Premium Margin Target")

        # Verify score reasons explainability
        factor_names = [r["factor"] for r in scorecard.score_reasons]
        self.assertTrue(any("expansion" in f.lower() for f in factor_names))
        self.assertTrue(any("overdue" in f.lower() for f in factor_names))

    def test_04_regulatory_radar_and_5_question_engine(self):
        seed_count = seed_default_regulatory_intelligence(self.db)
        self.assertTrue(seed_count >= 3)

        matches = scan_regulatory_radar_for_company(self.comp, self.db)
        self.assertTrue(len(matches) >= 2)
        codes = [m["regulation_code"] for m in matches]
        self.assertIn("LM-GATC-2026", codes)
        self.assertIn("NABL-133-TRACEABILITY-2026", codes)

        # Verify Mandatory 5-Question Structure in Commercial Impact
        lm_match = next(m for m in matches if m["regulation_code"] == "LM-GATC-2026")
        impact = lm_match["commercial_impact"]
        self.assertIn("what_changed", impact)
        self.assertIn("affected_processes", impact)
        self.assertIn("calibration_requirement", impact)
        self.assertIn("buying_window", impact)
        self.assertIn("sales_opportunity", impact)
        self.assertIn("premium_justification", impact)

    def test_05_lead_research_brief_and_role_specific_pitches(self):
        brief = generate_lead_research_brief(self.comp, self.db)
        self.assertEqual(brief.company_name, "Mahindra Auto Components Ltd")
        self.assertTrue(len(brief.target_stakeholders) >= 4)
        self.assertIn("google_queries", brief.search_instructions)

        # Generate differentiated pitches
        pitch_qa = generate_role_specific_pitch(self.comp, "Quality", self.db, contact_name="Rajesh Verma")
        pitch_pur = generate_role_specific_pitch(self.comp, "Purchase", self.db, contact_name="Amit Shinde")
        pitch_maint = generate_role_specific_pitch(self.comp, "Maintenance", self.db)
        pitch_mgmt = generate_role_specific_pitch(self.comp, "Management", self.db)

        self.assertIn("NABL", pitch_qa["body"])
        self.assertIn("traceability", pitch_qa["body"].lower())
        self.assertIn("consolidate", pitch_pur["body"].lower())
        self.assertIn("downtime", pitch_maint["body"].lower())
        self.assertIn("uncertainty", pitch_mgmt["body"].lower())

    def test_06_revenue_autopilot_deal_rescue_and_whitespace(self):
        # 1. Deal Rescue (Quotation open 12 days)
        diag = diagnose_deal_rescue(self.quote, self.db)
        self.assertTrue(diag["requires_action"])
        self.assertIn("Quality", diag["recommended_action"])

        # 2. Next Best Revenue Action
        action = compute_next_best_revenue_action(self.comp, self.db)
        self.assertEqual(action["priority"], "Critical")
        self.assertEqual(action["category"], "deal_rescue")

        # 3. Account White-Space Mapping
        ws = generate_account_whitespace_map(self.comp, self.db)
        self.assertIn("Dimensional", ws["served_parameters"])
        self.assertIn("Thermal", ws["whitespace_map"])
        self.assertEqual(ws["whitespace_map"]["Thermal"]["status"], "Unserved / Competitor Opportunity")

    def test_07_call_intelligence_and_objection_playbook(self):
        # 1. Pre-Call Brief
        brief = generate_pre_call_brief(self.comp, self.db, person_id=1)
        self.assertEqual(brief["contact_name"], "Rajesh Verma")
        self.assertIn("Good morning Rajesh Verma", brief["opening_script"])
        self.assertTrue(len(brief["suggested_questions"]) >= 3)

        # 2. Call Transcript Analysis with Objections and Signals
        transcript = (
            "Sales: Good morning Rajesh sir, calling from Oorja Technical Services regarding your CMM calibration.\n"
            "Customer: We already have a calibration vendor, but our annual calibration is due next month.\n"
            "Sales: Understood sir. Are there any parameters where turnaround is causing a production issue?\n"
            "Customer: Can you send your NABL scope and rate card?"
        )
        analysis = analyze_call_transcript(transcript, company=self.comp)
        self.assertTrue(analysis["call_score"] >= 70)
        self.assertTrue(len(analysis["buying_signals_detected"]) >= 2)
        self.assertIn("Existing Vendor Relationship", analysis["objections_detected"])
        self.assertTrue(len(analysis["playbook_coaching_advice"]) >= 1)

    def test_08_master_sales_ml_dataset(self):
        dataset = extract_sales_ml_dataset(self.db)
        self.assertEqual(dataset["total_dataset_rows"], 1)
        rec = dataset["records"][0]
        self.assertEqual(rec["company_name"], "Mahindra Auto Components Ltd")
        self.assertEqual(rec["industry"], "Automotive")
        self.assertEqual(rec["has_overdue_assets"], 1)
        self.assertIn("N >= 100", dataset["status_message"])

    def test_09_orchestrator_with_new_sub_agents(self):
        provider = MockTestProvider()
        orch = AskOorjaOrchestrator(provider=provider, max_iterations=2)

        # Query triggering RegulatorySpecialist
        res_reg = orch.run(query="What are the latest Legal Metrology and BIS regulations affecting our leads?", db=self.db)
        self.assertIn("RegulatorySpecialist", res_reg["sub_agents_used"])
        self.assertTrue(len(res_reg["answer"]) > 0)

        # Query triggering RevenueAutopilot
        res_rev = orch.run(query="What is the next best revenue action and deal rescue strategy for Mahindra?", db=self.db)
        self.assertIn("RevenueAutopilot", res_rev["sub_agents_used"])
        self.assertTrue(len(res_rev["answer"]) > 0)


if __name__ == "__main__":
    unittest.main()
