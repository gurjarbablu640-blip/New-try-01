"""Automated verification suite for Step 4: Quotation Intelligence, Ask Oorja AI Orchestration, Knowledge RAG, Learning Feedback, and Complete Sales Journey."""
from decimal import Decimal
import json
import os
import sqlite3
import sys
import unittest
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.types import ARRAY
from sqlalchemy.dialects.postgresql import JSONB

# SQLite adapter for Python lists and PostgreSQL-specific types during tests
sqlite3.register_adapter(list, json.dumps)
sqlite3.register_adapter(dict, json.dumps)

@compiles(ARRAY, "sqlite")
def compile_array_sqlite(type_, compiler, **kw):
    return "TEXT"

@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "TEXT"

# Add backend directory to sys.path
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from database import Base
from models.company import Company
from models.facility import Facility
from models.customer_asset import CustomerAsset
from models.person import Person
from models.pipeline import PipelineStage
from models.sales_os import AIFeedback, LearningRule, Opportunity, Quotation, QuotationItem
from models.knowledge import KnowledgeDocument, KnowledgeChunk
from services.sales_assistant import (
    ask_oorja,
    get_calibration_due_tool,
    get_priority_leads_tool,
    match_nabl_fit_tool,
    search_companies,
    record_feedback,
)
from services.nextBestAction import get_next_best_action
from routes.sales_os import (
    revise_quotation_core,
    compare_quotations_core,
    generate_quotation_from_assets_core,
    update_quotation_status_core,
    QuotationReviseRequest,
    QuotationGenerateFromAssetsRequest,
    QuotationStatusUpdate,
)


class TestStep4CompleteSalesOS(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(cls.engine)
        cls.Session = sessionmaker(bind=cls.engine)

    def setUp(self):
        self.db = self.Session()

    def tearDown(self):
        self.db.rollback()
        self.db.close()

    # ------------------------------------------------------------
    # 1. Quotation Versioning & Revision Management
    # ------------------------------------------------------------
    def test_quotation_versioning_and_comparison(self):
        today = date.today()

        # 1. Create Initial Quotation (v1)
        q1 = Quotation(
            quotation_number="Q-2026-001",
            version_number=1,
            is_latest=True,
            quotation_date=today,
            customer_name="Deepak Nitrite Ltd",
            location="Dahej",
            calibration_type="NABL Calibration",
            subtotal=Decimal("2400"),
            discount=Decimal("0"),
            tax=Decimal("432"),
            total=Decimal("2832"),
            status="Draft",
        )
        self.db.add(q1)
        self.db.flush()

        item1 = QuotationItem(
            quotation_id=q1.id,
            instrument_name="Digital Pressure Calibrator",
            parameter="Pressure",
            quantity=Decimal("2"),
            unit_price=Decimal("1200"),
            total_price=Decimal("2400"),
            nabl_applicable=1,
            nabl_validated=1,
            nabl_fit_status="FULL_SCOPE",
        )
        self.db.add(item1)
        self.db.commit()

        # 2. Revise to v2 with discount
        revise_payload = QuotationReviseRequest(
            revision_notes="Customer requested 10% commercial discount on 2+ items",
            discount=Decimal("240"),
            tax=Decimal("388.80"),
        )
        rev_res = revise_quotation_core(q1.id, revise_payload, self.db)
        self.assertEqual(rev_res["version_number"], 2)
        self.assertEqual(rev_res["parent_quotation_id"], q1.id)

        # Verify parent (v1) is now Revised & is_latest=False
        self.db.refresh(q1)
        self.assertEqual(q1.status, "Revised")
        self.assertFalse(q1.is_latest)

        # 3. Compare v1 vs v2
        cmp_res = compare_quotations_core(q1.id, rev_res["id"], self.db)
        self.assertEqual(cmp_res["quotation_1"]["version"], 1)
        self.assertEqual(cmp_res["quotation_2"]["version"], 2)
        self.assertEqual(len(cmp_res["line_item_diffs"]), 1)
        self.assertEqual(cmp_res["line_item_diffs"][0]["instrument_name"], "Digital Pressure Calibrator")

    # ------------------------------------------------------------
    # 2. Quotation Generation from Physical Customer Assets
    # ------------------------------------------------------------
    def test_quotation_generation_from_assets(self):
        today = date.today()

        company = Company(name="Gujarat Alkalies and Chemicals Ltd", city="Dahej", state="Gujarat")
        self.db.add(company)
        self.db.flush()

        facility = Facility(company_id=company.id, name="Chlor-Alkali Complex", plant_code="GACL-DHJ")
        self.db.add(facility)
        self.db.flush()

        a1 = CustomerAsset(
            company_id=company.id,
            facility_id=facility.id,
            instrument_name="Bourdon Tube Pressure Gauge 0-40 bar",
            parameter="Pressure",
            status="Active",
            calibration_due_date=today + timedelta(days=20),
        )
        a2 = CustomerAsset(
            company_id=company.id,
            facility_id=facility.id,
            instrument_name="RTD Temperature Sensor with Indicator",
            parameter="Thermal",
            status="Active",
            calibration_due_date=today + timedelta(days=15),
        )
        self.db.add_all([a1, a2])
        self.db.commit()

        # Generate quotation from plant assets
        payload = QuotationGenerateFromAssetsRequest(
            company_id=company.id,
            facility_id=facility.id,
            calibration_type="NABL On-site Calibration",
        )
        res = generate_quotation_from_assets_core(payload, self.db)
        self.assertEqual(res["items_count"], 2)
        self.assertGreater(res["total"], 0)
        self.assertEqual(res["status"], "Draft")

    # ------------------------------------------------------------
    # 3. Ask Oorja Tool Registry & Natural Language Coordination
    # ------------------------------------------------------------
    def test_ask_oorja_tool_registry(self):
        today = date.today()

        comp = Company(
            name="Anupam Rasayan India Ltd",
            city="Surat",
            state="Gujarat",
            industry="Agrochemicals",
            buying_window="next_30_days",
            icp_score=88.0,
            lead_status="New",
        )
        self.db.add(comp)
        self.db.flush()

        asset = CustomerAsset(
            company_id=comp.id,
            instrument_name="Pressure Transmitter 0-100 bar",
            parameter="Pressure",
            calibration_due_date=today + timedelta(days=10),
            status="Active",
        )
        self.db.add(asset)
        self.db.commit()

        # 1. Ask: "Which companies should I contact today?"
        ans1 = ask_oorja("Which companies should I contact today?", self.db)
        self.assertEqual(ans1["intent"], "priority_outreach")
        self.assertIn("Anupam Rasayan", ans1["answer"])

        # 2. Ask: "Which customers have calibration due within 45 days?"
        ans2 = ask_oorja("Which customers have calibration due within 45 days?", self.db)
        self.assertEqual(ans2["intent"], "calibration_due_lookup")
        self.assertIn("Pressure Transmitter", ans2["answer"])

        # 3. Ask: "Is this instrument within Oorja's NABL capability: Vernier Caliper 0-300mm?"
        ans3 = ask_oorja("Is this instrument within Oorja's NABL capability: Vernier Caliper 0-300mm?", self.db)
        self.assertEqual(ans3["intent"], "nabl_fit_check")
        self.assertEqual(ans3["verified_facts"][0]["fit_status"], "FULL_SCOPE")

    # ------------------------------------------------------------
    # 4. Learning Loop: AI Feedback -> Candidate Rule -> Approval
    # ------------------------------------------------------------
    def test_learning_feedback_and_rule_approval(self):
        # 1. Record AI correction feedback
        fb = record_feedback(
            db=self.db,
            entity_type="Quotation",
            entity_id=101,
            action_type="Price Override",
            ai_value={"unit_price": 1500},
            human_value={"unit_price": 1200},
            reason="Volume calibration discount applied for chemical plant batch",
        )
        self.assertEqual(fb["status"], "recorded")

        # 2. Verify AIFeedback in DB
        db_fb = self.db.query(AIFeedback).filter(AIFeedback.id == fb["id"]).first()
        self.assertIsNotNone(db_fb)
        self.assertEqual(db_fb.action_type, "Price Override")

        # 3. Create candidate learning rule
        rule = LearningRule(
            rule_type="Commercial Optimization",
            rule_key="Quotation:Price Override",
            pattern={"entity_type": "Quotation", "action_type": "Price Override"},
            evidence_count=1,
            confidence=70.0,
            status="Candidate",
        )
        self.db.add(rule)
        self.db.commit()

        # 4. Approve learning rule
        rule.status = "Approved"
        rule.approved_by = "admin"
        rule.approved_at = datetime.utcnow()
        self.db.commit()
        self.assertEqual(rule.status, "Approved")

    # ------------------------------------------------------------
    # 5. Deal Won Propagation to Opportunity and Company Order
    # ------------------------------------------------------------
    def test_deal_won_propagation(self):
        today = date.today()

        comp = Company(name="Navin Fluorine International", city="Surat", lead_status="Contacted")
        self.db.add(comp)
        self.db.flush()

        opp = Opportunity(company_id=comp.id, name="Annual Calibration Contract", stage="Proposal", estimated_value=Decimal("50000"))
        self.db.add(opp)
        self.db.flush()

        quote = Quotation(
            company_id=comp.id,
            opportunity_id=opp.id,
            quotation_number="Q-2026-NAV-01",
            quotation_date=today,
            customer_name=comp.name,
            total=Decimal("50000"),
            status="Approved",
        )
        self.db.add(quote)
        self.db.commit()

        # Mark Quote as Won
        status_payload = QuotationStatusUpdate(status="Won")
        update_quotation_status_core(quote.id, status_payload, self.db)

        # Verify Opportunity and Company are updated
        self.db.refresh(opp)
        self.db.refresh(comp)
        self.assertEqual(opp.stage, "Won")
        self.assertEqual(opp.probability, 100.0)
        self.assertTrue(comp.order_received)
        self.assertEqual(comp.lead_status, "Customer")
        self.assertEqual(comp.order_value, 50000.0)


if __name__ == "__main__":
    unittest.main()
