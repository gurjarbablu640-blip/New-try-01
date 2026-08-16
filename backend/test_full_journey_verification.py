"""Comprehensive end-to-end simulation test suite verifying the complete Oorja Sales OS journey:

Apollo/Mock Lead
  ↓
Normalization & Deduplication
  ↓
Email RFC 5322 Validation
  ↓
Lead Qualification Gate
  ↓
Campaign Recipient & Outbound SMTP Test Dispatch
  ↓
IMAP Inbound Processing & Thread Matching
  ↓
Reply Classification (INTERESTED)
  ↓
Opportunity Auto-Creation
  ↓
Facility & CustomerAsset Calibration Due Tracking
  ↓
Buying Window & NABL Fit Matching
  ↓
Next Best Action Determination
  ↓
Quotation Generation from Plant Assets (v1)
  ↓
Quotation Revision (v2) & Side-by-Side Comparison
  ↓
Quotation Status Won → Opportunity & Customer Conversion
  ↓
AI Learning Feedback & Rule Approval Loop
  ↓
Territory Cluster & Visit Itinerary Generation
  ↓
Ask Oorja AI Multi-Intent Orchestration
"""
from decimal import Decimal
import json
import os
import sqlite3
import sys
import unittest
from datetime import date, datetime, timedelta

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
from models.facility import Facility
from models.customer_asset import CustomerAsset
from models.person import Person
from models.campaign import Campaign, CampaignRecipient, CampaignStep, CampaignEvent
from models.activity import CRMActivity
from models.sales_os import AIFeedback, LearningRule, Opportunity, Quotation, QuotationItem
from models.competitor_intel import CompetitorProfile

from services.apollo_adapter import search_apollo_leads
from services.deduplication import normalize_company_name, find_company_duplicate
from services.email_validator import validate_email_address
from services.lead_qualification import evaluate_lead_qualification
from services.smtp_service import dispatch_campaign_batch, send_email_message
from services.imap_service import process_incoming_email
from services.calibration_intelligence import (
    calculate_asset_due_status,
    calculate_company_asset_calibration_summary,
    match_nabl_service_fit,
)
from services.nextBestAction import get_next_best_action
from services.territory_intelligence import get_industrial_clusters, get_visit_recommendations
from services.sales_assistant import ask_oorja, record_feedback
from routes.sales_os import (
    revise_quotation_core,
    compare_quotations_core,
    generate_quotation_from_assets_core,
    update_quotation_status_core,
    QuotationReviseRequest,
    QuotationGenerateFromAssetsRequest,
    QuotationStatusUpdate,
)


class TestCompleteOorjaSalesOSJourney(unittest.TestCase):

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

    def test_complete_end_to_end_sales_os_journey(self):
        today = date.today()

        # ============================================================
        # 1. Lead Generation & Ingestion
        # ============================================================
        search_res = search_apollo_leads(query="Aarti Industries", force_mock=True)
        self.assertGreater(len(search_res["results"]), 0)
        lead_data = search_res["results"][0]
        self.assertEqual(lead_data["company_name"], "Aarti Industries Ltd (Dahej Division)")
        self.assertEqual(lead_data["city"], "Dahej")

        # ============================================================
        # 2. Normalization & Deduplication
        # ============================================================
        norm_name = normalize_company_name(lead_data["company_name"])
        dup_match, reason, conf = find_company_duplicate(self.db, name=lead_data["company_name"], domain=lead_data.get("domain"))
        self.assertIsNone(dup_match)

        # Persist Company & Contact Person
        company = Company(
            name=lead_data["company_name"],
            normalized_name=norm_name,
            domain=lead_data.get("domain") or "aarti-industries.com",
            website="https://www.aarti-industries.com",
            city=lead_data["city"],
            state=lead_data["state"],
            industry="Chemical",
            has_nabl=True,
            headcount_bracket="500-1000",
            export_active=True,
            lead_status="New",
            icp_score=85.0,
            buying_window="next_30_days",
        )
        self.db.add(company)
        self.db.flush()

        contact = lead_data["contacts"][0]
        person = Person(
            company_id=company.id,
            full_name=contact["name"],
            email=contact["email"],
            designation=contact["title"],
            department=contact.get("department"),
            is_decision_maker=1 if contact.get("is_decision_maker") else 0,
            email_verification_status="valid",
            phone=contact.get("phone") or "+91 98250 11223",
        )
        self.db.add(person)
        self.db.commit()

        # ============================================================
        # 3. Email Validation (RFC 5322)
        # ============================================================
        email_val = validate_email_address(person.email)
        self.assertTrue(email_val["is_valid"])

        # ============================================================
        # 4. Lead Qualification Gate
        # ============================================================
        qual_res = evaluate_lead_qualification(self.db, company.id)
        self.assertIn(qual_res["qualification_status"], ["READY_FOR_OUTREACH", "QUALIFIED"])

        # ============================================================
        # 5. Outbound Campaign Dispatch (SMTP Test Mode)
        # ============================================================
        campaign = Campaign(
            name="Dahej Chemical Plants Q3 NABL Outreach",
            description="Targeted outreach to Dahej specialty chemical manufacturing units",
            channel="email",
            status="Active",
            approved=True,
            daily_limit=50,
        )
        self.db.add(campaign)
        self.db.flush()

        step = CampaignStep(
            campaign_id=campaign.id,
            step_number=1,
            channel="email",
            enabled=True,
            subject="NABL Calibration Support for {company_name}",
            body_template="Hi {first_name}, reaching out from Oorja regarding upcoming pressure calibration.",
        )
        self.db.add(step)
        self.db.flush()

        recipient = CampaignRecipient(
            campaign_id=campaign.id,
            company_id=company.id,
            person_id=person.id,
            status="Pending",
            email_status="Scheduled",
        )
        self.db.add(recipient)
        self.db.commit()

        dispatch_res = dispatch_campaign_batch(self.db, campaign_id=campaign.id, max_count=5)
        self.assertEqual(dispatch_res["dispatched"], 1)

        self.db.refresh(recipient)
        self.assertEqual(recipient.status, "Completed")
        self.assertEqual(recipient.email_status, "Sent")

        # Get sent event message_id
        event = self.db.query(CampaignEvent).filter(CampaignEvent.recipient_id == recipient.id).first()
        self.assertIsNotNone(event)
        msg_id = event.provider_message_id

        # ============================================================
        # 6 & 7. Inbound Reply & Classification → Opportunity Creation
        # ============================================================
        reply_res = process_incoming_email(
            db=self.db,
            email_data={
                "from": person.email,
                "subject": "Re: NABL Calibration Support for Aarti Industries Ltd (Dahej Division)",
                "body": "Thanks for reaching out. We have 15 pressure gauges and transmitters due next month at Dahej. Please send quotation.",
                "headers": {"in-reply-to": msg_id},
            },
        )
        self.assertEqual(reply_res["status"], "matched")
        self.assertEqual(reply_res["classification"]["category"], "REQUESTING_QUOTE")

        # Verify auto-created Opportunity
        opp = self.db.query(Opportunity).filter(Opportunity.company_id == company.id).first()
        self.assertIsNotNone(opp)
        self.assertEqual(opp.stage, "Proposal")
        self.assertGreater(opp.probability, 50.0)

        # ============================================================
        # 8 & 9. Facility & CustomerAsset Intelligence
        # ============================================================
        facility = Facility(
            company_id=company.id,
            name="Dahej Unit 2 Specialty Block",
            plant_code="AARTI-DHJ-U2",
            industrial_estate="Dahej GIDC",
            city="Dahej",
            state="Gujarat",
        )
        self.db.add(facility)
        self.db.flush()

        asset1 = CustomerAsset(
            company_id=company.id,
            facility_id=facility.id,
            instrument_name="Digital Pressure Transmitter 0-100 bar",
            parameter="Pressure",
            status="Active",
            calibration_due_date=today + timedelta(days=12),
        )
        asset2 = CustomerAsset(
            company_id=company.id,
            facility_id=facility.id,
            instrument_name="Duplex RTD Temperature Assembly (-50 to 400°C)",
            parameter="Thermal",
            status="Active",
            calibration_due_date=today + timedelta(days=18),
        )
        self.db.add_all([asset1, asset2])
        self.db.commit()

        calib_summary = calculate_company_asset_calibration_summary(company.id, self.db, reference_date=today)
        self.assertEqual(calib_summary["due_metrics"]["due_next_30_days"], 2)
        self.assertEqual(calib_summary["buying_window"], "next_30_days")

        # ============================================================
        # 10. Next Best Action Determination
        # ============================================================
        nba = get_next_best_action(company.id, self.db)
        self.assertTrue(bool(nba.get("action")))
        self.assertIn("timing", nba)

        # ============================================================
        # 11 & 12. Quotation Generation (v1) & Revision (v2)
        # ============================================================
        quote_req = QuotationGenerateFromAssetsRequest(
            company_id=company.id,
            facility_id=facility.id,
            calibration_type="NABL On-site Calibration",
        )
        q1_res = generate_quotation_from_assets_core(quote_req, self.db)
        self.assertEqual(q1_res["items_count"], 2)
        self.assertGreater(q1_res["total"], 0)

        # Revise to v2
        rev_req = QuotationReviseRequest(
            revision_notes="Applied 15% Dahej corridor corporate discount",
            discount=Decimal("300"),
        )
        q2_res = revise_quotation_core(q1_res["id"], rev_req, self.db)
        self.assertEqual(q2_res["version_number"], 2)

        # Compare v1 vs v2
        comp_diff = compare_quotations_core(q1_res["id"], q2_res["id"], self.db)
        self.assertEqual(comp_diff["quotation_1"]["version"], 1)
        self.assertEqual(comp_diff["quotation_2"]["version"], 2)

        # ============================================================
        # 13. Quotation Won Outcome Propagation
        # ============================================================
        won_req = QuotationStatusUpdate(status="Won")
        won_res = update_quotation_status_core(q2_res["id"], won_req, self.db)
        self.assertEqual(won_res["status"], "Won")

        self.db.refresh(company)
        self.assertTrue(company.order_received)
        self.assertEqual(company.lead_status, "Customer")

        # ============================================================
        # 14. Learning Feedback Loop
        # ============================================================
        fb = record_feedback(
            db=self.db,
            entity_type="Quotation",
            entity_id=q2_res["id"],
            action_type="Price Override",
            ai_value={"discount": 0},
            human_value={"discount": 300},
            reason="Special commercial discount for Dahej cluster batch",
        )
        self.assertEqual(fb["status"], "recorded")

        # ============================================================
        # 15. Territory Industrial Cluster & Visit Recommendations
        # ============================================================
        clusters = get_industrial_clusters(self.db)
        self.assertGreater(clusters["total_clusters"], 0)
        dahej_cluster = [c for c in clusters["clusters"] if "Dahej" in c["cluster_name"]][0]
        self.assertEqual(dahej_cluster["companies_count"], 1)
        self.assertEqual(dahej_cluster["total_assets"], 2)

        routes = get_visit_recommendations(self.db)
        self.assertGreater(routes["total_recommended_routes"], 0)

        # ============================================================
        # 16. Ask Oorja AI Multi-Intent Coordination
        # ============================================================
        ans_priority = ask_oorja("Which companies should I contact today?", self.db)
        self.assertEqual(ans_priority["intent"], "priority_outreach")

        ans_nabl = ask_oorja("Is this instrument within Oorja's NABL capability: Bourdon Tube Gauge 0-600 bar?", self.db)
        self.assertEqual(ans_nabl["intent"], "nabl_fit_check")
        self.assertEqual(ans_nabl["verified_facts"][0]["fit_status"], "FULL_SCOPE")

        ans_territory = ask_oorja("Recommend a visit itinerary for industrial clusters", self.db)
        self.assertEqual(ans_territory["intent"], "territory_visit_plan")


if __name__ == "__main__":
    unittest.main()
