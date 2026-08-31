"""Master Salesoorja Revenue Loop Verification Suite.

Tests the full closed-loop revenue lifecycle:
Inbound Reply Intelligence -> Opportunity Progression -> Calling Trigger & Brief ->
Call Transcript Parsing & Fact Extraction -> Deal Rescue -> Won/Lost Outcome ->
Structured AIFeedback & Rule Learning -> Account White-Space Expansion.
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
from models.sales_os import Opportunity, Quotation, AIFeedback, LearningRule
from models.call_record import CallRecord
from models.company_brain import CompanyIntelligenceFact, CompanyTimelineEvent, StakeholderIntelligence
from services.revenue_loop_coordinator import (
    process_incoming_email_reply_loop,
    process_deal_outcome_loop,
    execute_full_revenue_loop_audit,
)
from services.call_recorder_service import log_completed_call, get_sales_coaching_overview


class TestRevenueLoopSuite(unittest.TestCase):

    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(self.engine)
        Session = sessionmaker(bind=self.engine)
        self.db = Session()

        # Seed target company
        self.comp = Company(
            id=1,
            name="Tata Motors PV Ltd",
            city="Pune",
            state="Maharashtra",
            industry="Automotive",
            icp_score=94,
            buying_window="immediate",
        )
        self.person = Person(
            id=1,
            company_id=1,
            full_name="Sunil Kulkarni",
            designation="VP Quality Assurance",
            email="sunil.k@tatamotors.local",
            phone="+91-9890011223",
            department="Quality",
            is_decision_maker=True,
        )
        self.asset = CustomerAsset(
            id=1,
            company_id=1,
            instrument_name="Zeiss Prismo CMM",
            parameter="Dimensional",
            calibration_due_date=date.today() - timedelta(days=2),
            status="Active",
        )
        self.quote = Quotation(
            id=1,
            company_id=1,
            quotation_number="Q-2026-TATA-001",
            customer_name="Tata Motors PV Ltd",
            quotation_date=date.today() - timedelta(days=14),
            subtotal=145000.0,
            total=145000.0,
            status="Submitted",
        )
        self.db.add_all([self.comp, self.person, self.asset, self.quote])
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_01_reply_intelligence_advances_opportunity_and_generates_call_brief(self):
        res = process_incoming_email_reply_loop(
            db=self.db,
            company_id=1,
            reply_classification="Interested - Request Quotation",
            reply_body="Please share your NABL scope and pricing for CMM and pressure gauge calibration.",
            recipient_email="sunil.k@tatamotors.local",
            sender_name="Sunil Kulkarni",
        )
        self.assertEqual(res["status"], "revenue_accelerated")
        self.assertEqual(res["opportunity_stage"], "Proposal")
        self.assertTrue("Quality" in res["recommended_next_action"] or "Call" in res["recommended_next_action"])
        self.assertIsNotNone(res["call_brief"])
        self.assertIn("Tata Motors PV Ltd", res["call_brief"]["company_name"])

        # Verify timeline event was created
        timeline_events = self.db.query(CompanyTimelineEvent).filter(CompanyTimelineEvent.company_id == 1).all()
        types = [e.event_type for e in timeline_events]
        self.assertIn("email_reply_interested", types)

    def test_02_objection_reply_triggers_deal_rescue_and_feedback(self):
        res = process_incoming_email_reply_loop(
            db=self.db,
            company_id=1,
            reply_classification="Objection: Existing Vendor",
            reply_body="We already have an annual contract with another vendor for calibration.",
            recipient_email="sunil.k@tatamotors.local",
        )
        self.assertEqual(res["status"], "objection_logged_deal_rescue_active")
        self.assertIn("Quality", res["deal_rescue_action"])

        # Verify AIFeedback recorded
        fb = self.db.query(AIFeedback).filter(AIFeedback.entity_type == "email_objection").first()
        self.assertIsNotNone(fb)
        self.assertEqual(fb.human_value["objection_type"], "Objection: Existing Vendor")

    def test_03_call_logging_extracts_facts_and_timeline(self):
        transcript = (
            "Sales: Good morning Sunil sir, calling from Oorja Technical Services regarding your CMM calibration.\n"
            "Customer: Good morning. We have around 1,200 instruments in Pune plant and our annual calibration is due next month.\n"
            "Sales: Excellent. Are there any turnaround bottlenecks with your current setup?\n"
            "Customer: Yes, our current vendor takes 3 weeks. Please send your NABL scope and schedule a visit."
        )
        rec = log_completed_call(
            db=self.db,
            company_id=1,
            transcript_text=transcript,
            person_id=1,
            salesperson_name="Bablu Gurjar",
            duration_seconds=310,
            call_channel="Phone",
            call_objective="discovery",
        )
        self.assertIsNotNone(rec.id)
        self.assertTrue(rec.call_score >= 75)
        self.assertEqual(rec.outcome_status, "qualified")
        self.assertTrue(len(rec.buying_signals_detected) >= 2)

        # Verify Company Brain fact was extracted
        fact = self.db.query(CompanyIntelligenceFact).filter(CompanyIntelligenceFact.category == "sales_conversation").first()
        self.assertIsNotNone(fact)
        self.assertEqual(fact.confidence, 0.95)

        # Verify Coaching Overview
        coaching = get_sales_coaching_overview(self.db, salesperson_name="Bablu Gurjar")
        self.assertEqual(coaching["total_calls"], 1)
        self.assertTrue(coaching["average_call_score"] >= 75)

    def test_04_won_deal_outcome_triggers_whitespace_map_and_learning_rules(self):
        res = process_deal_outcome_loop(
            db=self.db,
            company_id=1,
            outcome="Won",
            quotation_id=1,
            instrument_category="CMM",
        )
        self.assertEqual(res["outcome"], "Won")
        self.assertIsNotNone(res["whitespace_expansion"])
        self.assertTrue(res["whitespace_expansion"]["expansion_opportunity_count"] >= 1)

        # Verify quote updated
        quote = self.db.query(Quotation).filter(Quotation.id == 1).first()
        self.assertEqual(quote.status, "Won")

        # Verify timeline event
        ev = self.db.query(CompanyTimelineEvent).filter(CompanyTimelineEvent.event_type == "deal_won").first()
        self.assertIsNotNone(ev)

    def test_05_lost_deal_outcome_records_isolated_subpattern_feedback(self):
        res = process_deal_outcome_loop(
            db=self.db,
            company_id=1,
            outcome="Lost",
            quotation_id=1,
            loss_reason="existing_vendor_contract",
            instrument_category="Pressure Gauge",
        )
        self.assertEqual(res["outcome"], "Lost")
        self.assertEqual(res["loss_reason"], "existing_vendor_contract")

        # Verify AIFeedback row created with instrument_category="Pressure Gauge"
        fb = self.db.query(AIFeedback).filter(AIFeedback.action_type == "loss").first()
        self.assertIsNotNone(fb)
        self.assertEqual(fb.human_value["instrument_category"], "Pressure Gauge")
        self.assertEqual(fb.human_value["adjustment_percent"], -5.0)

    def test_06_full_revenue_loop_360_audit(self):
        audit = execute_full_revenue_loop_audit(self.db, 1)
        self.assertEqual(audit["company_name"], "Tata Motors PV Ltd")
        self.assertEqual(audit["revenue_loop_stage"], "Active Revenue Pipeline")
        self.assertTrue(audit["composite_score"] >= 70)
        self.assertIsNotNone(audit["recommended_next_action"])
        self.assertIn("NABL", audit["personalized_pitch_subject"])
        self.assertIn("Oorja Technical Services", audit["pre_call_opening"])


if __name__ == "__main__":
    unittest.main()
