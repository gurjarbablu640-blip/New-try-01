"""Signal Discovery, Business Causality, Cadence Strategy, and Email Template Test Suite.

Verifies:
1. 5-Question Signal Causality reasoning
2. Signal-driven lead discovery and Company Brain ingestion
3. 15-day non-response cadence evaluation (Call escalation vs Stakeholder pivot)
4. Dynamic HTML email composition across 4 industrial roles
5. Apollo live pilot safety guard enforcing strict 5-6 contacts limit
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
from models.sales_os import Opportunity, Quotation
from models.company_brain import CompanyIntelligenceFact, CompanyTimelineEvent
from services.signal_discovery_engine import reason_signal_causality, ingest_discovered_signal_lead
from services.cadence_orchestrator import evaluate_non_response_cadence
from services.email_template_engine import render_html_email
from services.apollo_adapter import execute_apollo_pilot_validation


class TestSignalAndCadenceSuite(unittest.TestCase):

    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(self.engine)
        Session = sessionmaker(bind=self.engine)
        self.db = Session()

        # Seed test company
        self.comp = Company(
            id=1,
            name="Endurance Technologies Ltd",
            city="Aurangabad",
            state="Maharashtra",
            industry="Automotive",
            icp_score=85,
            buying_window="30_days",
        )
        self.person = Person(
            id=1,
            company_id=1,
            full_name="Rajesh Sharma",
            designation="Purchase Manager",
            email="rajesh.s@endurance.local",
            department="Purchase",
            is_decision_maker=True,
        )
        self.asset = CustomerAsset(
            id=1,
            company_id=1,
            instrument_name="Mitutoyo CMM",
            parameter="Dimensional",
            calibration_due_date=date.today() - timedelta(days=5),
            status="Active",
        )
        self.db.add_all([self.comp, self.person, self.asset])
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_01_signal_causality_5_questions_reasoning(self):
        causality = reason_signal_causality(
            signal_type="plant_expansion",
            raw_event_title="₹350 Cr Green Field Transmission Plant",
            raw_event_description="Setting up 4 new CNC machining and leak testing lines in Chakan Pune.",
            company_name="Endurance Technologies Ltd",
            industry="Automotive",
        )
        self.assertEqual(causality["signal_type"], "plant_expansion")
        self.assertEqual(causality["buying_window"], "30_days")
        self.assertEqual(causality["price_sensitivity"], "Low")
        self.assertTrue(len(causality["likely_parameters"]) >= 3)

        q = causality["five_question_reasoning"]
        self.assertIn("Plant Expansion", q["q1_what_changed"])
        self.assertIn("Endurance Technologies Ltd", q["q2_affected_entity"])
        self.assertIn("NABL", q["q3_calibration_impact"])
        self.assertIn("Premium", q["q4_buying_behavior_change"])
        self.assertIn("Plant Operations Head", q["q5_oorja_action_strategy"])

    def test_02_ingest_signal_creates_company_fact_and_timeline(self):
        res = ingest_discovered_signal_lead(
            db=self.db,
            company_name="Sona Comstar Ltd",
            city="Manesar",
            state="Haryana",
            industry="Automotive",
            signal_type="ev_battery_manufacturing",
            event_title="Commissioning EV Traction Motor Line",
            event_description="Expanding production capacity for EV motors and sensor assemblies.",
            evidence_url="https://industry-news.local/sona-ev",
        )
        self.assertEqual(res["status"], "lead_discovered")
        self.assertEqual(res["buying_window"], "60_days")

        # Verify company in DB
        comp = self.db.query(Company).filter(Company.name == "Sona Comstar Ltd").first()
        self.assertIsNotNone(comp)
        self.assertTrue(comp.icp_score >= 85)

        # Verify fact in Company Brain
        fact = self.db.query(CompanyIntelligenceFact).filter(CompanyIntelligenceFact.company_id == comp.id).first()
        self.assertIsNotNone(fact)
        self.assertEqual(fact.category, "business_signal")

        # Verify timeline event
        ev = self.db.query(CompanyTimelineEvent).filter(CompanyTimelineEvent.company_id == comp.id).first()
        self.assertIsNotNone(ev)
        self.assertIn("EV", ev.title)

    def test_03_cadence_evaluator_high_value_escalates_to_call(self):
        # Company has overdue CMM and high opportunity value
        res = evaluate_non_response_cadence(
            company=self.comp,
            db=self.db,
            days_since_outbound=16,
            non_response_threshold_days=15,
            last_contacted_role="Quality Head",
        )
        self.assertEqual(res["action_type"], "escalate_to_call")
        self.assertIn("Quality", res["target_role"])
        self.assertIsNotNone(res["call_brief"])
        self.assertIn("Endurance Technologies Ltd", res["call_brief"]["company_name"])

    def test_04_cadence_evaluator_purchase_stalled_pivots_to_quality(self):
        # Set company to moderate score without immediate overdue asset
        self.asset.calibration_due_date = date.today() + timedelta(days=120)
        self.comp.icp_score = 65
        self.db.commit()

        res = evaluate_non_response_cadence(
            company=self.comp,
            db=self.db,
            days_since_outbound=15,
            non_response_threshold_days=15,
            last_contacted_role="Purchase Manager",
        )
        self.assertEqual(res["action_type"], "pivot_stakeholder")
        self.assertIn("Quality", res["target_role"])
        self.assertIn("Pivot directly to Quality Head", res["reasoning"])

    def test_05_html_email_template_engine_renders_clean_tokens_and_roles(self):
        q_email = render_html_email(
            company_name="Tata Motors Ltd",
            contact_name="Sunil Kulkarni",
            target_role="Quality",
            likely_parameters=["Dimensional", "Torque", "Pressure"],
        )
        self.assertIn("NABL Calibration Traceability", q_email["subject"])
        self.assertIn("Sunil Kulkarni", q_email["html_content"])
        self.assertIn("Tata Motors Ltd", q_email["html_content"])
        self.assertIn("ISO/IEC 17025:2017", q_email["html_content"])
        self.assertIn("Unsubscribe", q_email["html_content"])

        p_email = render_html_email(
            company_name="Tata Motors Ltd",
            contact_name="Ramesh Nair",
            target_role="Purchase",
        )
        self.assertIn("Consolidated Calibration Vendor", p_email["subject"])
        self.assertIn("procurement overhead", p_email["html_content"])

    def test_06_apollo_pilot_safety_guard_enforces_strict_limit(self):
        # Request 50 contacts — safety guard MUST strictly cap at 5-6 contacts
        pilot_res = execute_apollo_pilot_validation(
            company_name="Bharat Forge Ltd",
            max_contacts=50,
        )
        self.assertEqual(pilot_res["status"], "pilot_completed")
        self.assertTrue(pilot_res["hard_limit_enforced"] <= 6)
        self.assertTrue(pilot_res["returned_contacts"] <= 6)
        self.assertIn("strict hard limit", pilot_res["governance_note"])
        self.assertIsNotNone(pilot_res["processing_time_seconds"])


if __name__ == "__main__":
    unittest.main()
