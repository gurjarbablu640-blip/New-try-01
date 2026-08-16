"""Automated verification suite for Step 2: Outbound SMTP Dispatch, IMAP Ingestion, Thread Matching, and Reply Classification."""
import json
import os
import sqlite3
import sys
import unittest
from datetime import datetime, timezone
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
from models.activity import CRMActivity
from models.campaign import Campaign, CampaignEvent, CampaignRecipient, CampaignStep
from models.company import Company
from models.person import Person
from services.imap_service import match_incoming_thread, process_incoming_email
from services.reply_classifier import classify_reply_intent
from services.smtp_service import (
    dispatch_campaign_batch,
    generate_message_id,
    render_template,
    send_email_message,
)


class TestStep2OutboundAndReplyEngine(unittest.TestCase):

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
    # 1. Template Rendering & Message-ID Generation
    # ------------------------------------------------------------
    def test_template_rendering(self):
        template = "Dear {contact_name},\nWe can support your {city} plant with {industry} calibration."
        context = {
            "contact_name": "Rajesh Patel",
            "city": "Dahej",
            "industry": "Chemical",
        }
        rendered = render_template(template, context)
        self.assertEqual(rendered, "Dear Rajesh Patel,\nWe can support your Dahej plant with Chemical calibration.")

    def test_message_id_format(self):
        msg_id = generate_message_id(campaign_id=5, recipient_id=12)
        self.assertTrue(msg_id.startswith("<c5.r12."))
        self.assertTrue(msg_id.endswith(">"))

    # ------------------------------------------------------------
    # 2. Reply & Bounce Intent Classification
    # ------------------------------------------------------------
    def test_reply_classification_quote_request(self):
        res = classify_reply_intent(
            subject="Re: Calibration scope inquiry",
            body="Hello, please send us the quotation and scope of work for 50 pressure gauges.",
            from_email="rajesh@aarti-industries.com",
        )
        self.assertEqual(res["category"], "REQUESTING_QUOTE")
        self.assertEqual(res["sentiment"], "Positive")
        self.assertTrue(res["is_actionable"])

    def test_reply_classification_interested(self):
        res = classify_reply_intent(
            subject="Re: Partnership with Oorja",
            body="We are interested in your services. Let's schedule a call tomorrow at 3 PM.",
            from_email="anand@precisionauto.com",
        )
        self.assertEqual(res["category"], "INTERESTED")
        self.assertEqual(res["sentiment"], "Positive")
        self.assertTrue(res["is_actionable"])

    def test_reply_classification_objection(self):
        res = classify_reply_intent(
            subject="Re: Calibration support",
            body="We already have a vendor under annual contract. Contact us next year.",
            from_email="purchase@bharatforge.com",
        )
        self.assertEqual(res["category"], "OBJECTION")
        self.assertTrue(res["is_actionable"])

    def test_reply_classification_unsubscribe(self):
        res = classify_reply_intent(
            subject="Re: Outreach",
            body="Please unsubscribe and remove our email from your list.",
            from_email="info@trading.com",
        )
        self.assertEqual(res["category"], "NOT_INTERESTED")

    def test_reply_classification_bounce(self):
        res = classify_reply_intent(
            subject="Delivery Status Notification (Failure)",
            body="550 5.1.1 User unknown. Recipient address rejected: no such mailbox.",
            from_email="mailer-daemon@google.com",
        )
        self.assertEqual(res["category"], "BOUNCE")
        self.assertTrue(res["is_actionable"])

    def test_reply_classification_ooo(self):
        res = classify_reply_intent(
            subject="Automatic reply: Out of office",
            body="I am away from the office on leave until Monday. Contact my deputy for urgent items.",
            from_email="qa@tatasteel.com",
        )
        self.assertEqual(res["category"], "OUT_OF_OFFICE")
        self.assertFalse(res["is_actionable"])

    # ------------------------------------------------------------
    # 3. SMTP Outbound Message Creation
    # ------------------------------------------------------------
    def test_send_email_message_test_mode(self):
        send_res = send_email_message(
            to_email="rajesh.patel@aarti-industries.com",
            subject="Technical Calibration Proposal",
            body="Dear Rajesh,\n\nWe provide NABL accredited calibration services.",
            campaign_id=1,
            recipient_id=10,
        )
        self.assertTrue(send_res["success"])
        self.assertIn("message_id", send_res)
        self.assertEqual(send_res["original_recipient"], "rajesh.patel@aarti-industries.com")
        self.assertTrue(send_res["test_mode"])

    # ------------------------------------------------------------
    # 4. End-to-End Outbound Dispatch Flow
    # ------------------------------------------------------------
    def test_dispatch_campaign_batch_flow(self):
        # 1. Setup Company & Person
        company = Company(
            name="Aarti Industries Ltd",
            domain="aarti-industries.com",
            city="Dahej",
            state="Gujarat",
            industry="Chemical",
            lead_status="New",
            email_sent=False,
            reply_received=False,
            bounced_email=False,
        )
        self.db.add(company)
        self.db.flush()

        person = Person(
            company_id=company.id,
            full_name="Rajesh Patel",
            designation="Quality Head",
            email="rajesh.patel@aarti-industries.com",
            normalized_email="rajesh.patel@aarti-industries.com",
            is_decision_maker=1,
        )
        self.db.add(person)
        self.db.flush()

        # 2. Setup Campaign & Step
        campaign = Campaign(
            name="Dahej Chemical Cluster Sequence",
            approved=True,
            status="Approved",
            daily_limit=25,
        )
        self.db.add(campaign)
        self.db.flush()

        step1 = CampaignStep(
            campaign_id=campaign.id,
            step_number=1,
            subject="Calibration Support for {company_name} - Dahej Plant",
            body_template="Dear {first_name},\n\nWe would love to support {company_name} in {city}.",
            enabled=True,
        )
        self.db.add(step1)
        self.db.flush()

        # 3. Setup Recipient
        recipient = CampaignRecipient(
            campaign_id=campaign.id,
            company_id=company.id,
            person_id=person.id,
            status="Queued",
            email_status="Pending",
            current_step=0,
        )
        self.db.add(recipient)
        self.db.commit()

        # 4. Dispatch Campaign Step
        dispatch_res = dispatch_campaign_batch(self.db, campaign.id, max_count=10)
        self.assertEqual(dispatch_res["dispatched"], 1)

        # 5. Verify Recipient State
        self.db.refresh(recipient)
        self.assertEqual(recipient.email_status, "Sent")
        self.assertEqual(recipient.current_step, 1)
        self.assertEqual(recipient.status, "Completed")  # Max step reached
        self.assertIsNotNone(recipient.last_sent_at)

        # 6. Verify Campaign Event
        evt = self.db.query(CampaignEvent).filter(CampaignEvent.recipient_id == recipient.id).first()
        self.assertIsNotNone(evt)
        self.assertEqual(evt.event_type, "sent")
        sent_msg_id = evt.provider_message_id
        self.assertIsNotNone(sent_msg_id)

        # 7. Verify CRM Activity
        crm_act = self.db.query(CRMActivity).filter(CRMActivity.company_id == company.id).first()
        self.assertIsNotNone(crm_act)
        self.assertEqual(crm_act.activity_type, "Email Sent")
        self.assertEqual(crm_act.status, "Completed")

        # 8. Verify Company Status
        self.db.refresh(company)
        self.assertTrue(company.email_sent)
        self.assertEqual(company.lead_status, "Contacted")

        # ------------------------------------------------------------
        # 5. Inbound Reply Flow with Thread Matching
        # ------------------------------------------------------------
        incoming_reply = {
            "from": "Rajesh Patel <rajesh.patel@aarti-industries.com>",
            "subject": "Re: Calibration Support for Aarti Industries Ltd - Dahej Plant",
            "body": "Hi, we received your note. Please send quotation for our 200 pressure transmitters.",
            "message_id": "<reply.xyz123@aarti-industries.com>",
            "headers": {
                "in-reply-to": sent_msg_id,
                "references": sent_msg_id,
            },
        }

        reply_res = process_incoming_email(self.db, incoming_reply)
        self.assertEqual(reply_res["status"], "matched")
        self.assertEqual(reply_res["classification"]["category"], "REQUESTING_QUOTE")
        self.assertEqual(reply_res["recipient_id"], recipient.id)

        # Verify recipient updated to Replied
        self.db.refresh(recipient)
        self.assertEqual(recipient.status, "Replied")
        self.assertEqual(recipient.email_status, "Replied")
        self.assertIsNotNone(recipient.replied_at)

        # Verify company updated to Replied
        self.db.refresh(company)
        self.assertTrue(company.reply_received)
        self.assertEqual(company.lead_status, "Replied")

        # Verify Reply CampaignEvent
        reply_evt = (
            self.db.query(CampaignEvent)
            .filter(CampaignEvent.recipient_id == recipient.id, CampaignEvent.event_type == "replied")
            .first()
        )
        self.assertIsNotNone(reply_evt)

        # Verify Reply CRMActivity
        reply_crm = (
            self.db.query(CRMActivity)
            .filter(CRMActivity.company_id == company.id, CRMActivity.activity_type == "Email Reply Received")
            .first()
        )
        self.assertIsNotNone(reply_crm)
        self.assertIn("REQUESTING_QUOTE", reply_crm.remarks)

    # ------------------------------------------------------------
    # 6. Inbound Bounce Processing
    # ------------------------------------------------------------
    def test_inbound_bounce_flow(self):
        company = Company(
            name="Obsolete Plant Ltd",
            domain="obsolete-plant.com",
            city="Pune",
            lead_status="Contacted",
            bounced_email=False,
        )
        self.db.add(company)
        self.db.flush()

        person = Person(
            company_id=company.id,
            full_name="Old Contact",
            email="old.contact@obsolete-plant.com",
            normalized_email="old.contact@obsolete-plant.com",
            email_verification_status="valid",
        )
        self.db.add(person)
        self.db.flush()

        campaign = Campaign(name="Pune Campaign", approved=True, status="Approved")
        self.db.add(campaign)
        self.db.flush()

        recipient = CampaignRecipient(
            campaign_id=campaign.id,
            company_id=company.id,
            person_id=person.id,
            status="Active",
            email_status="Sent",
            current_step=1,
        )
        self.db.add(recipient)
        self.db.commit()

        sent_msg_id = "<c1.r999.test@oorja.local>"
        sent_evt = CampaignEvent(
            campaign_id=campaign.id,
            recipient_id=recipient.id,
            event_type="sent",
            provider_message_id=sent_msg_id,
        )
        self.db.add(sent_evt)
        self.db.commit()

        # Simulate DSN Bounce
        bounce_email = {
            "from": "Mail Delivery System <mailer-daemon@mail.server.com>",
            "subject": "Undelivered Mail Returned to Sender",
            "body": "550 5.1.1 <old.contact@obsolete-plant.com>: Recipient address rejected: User unknown",
            "headers": {
                "in-reply-to": sent_msg_id,
            },
        }

        bounce_res = process_incoming_email(self.db, bounce_email)
        self.assertEqual(bounce_res["status"], "matched")
        self.assertEqual(bounce_res["classification"]["category"], "BOUNCE")

        # Verify state updates
        self.db.refresh(recipient)
        self.assertEqual(recipient.status, "Bounced")
        self.assertIsNotNone(recipient.bounced_at)

        self.db.refresh(company)
        self.assertTrue(company.bounced_email)

        self.db.refresh(person)
        self.assertEqual(person.email_verification_status, "bounced")

        # Verify CRM Bounce Activity
        bounce_crm = (
            self.db.query(CRMActivity)
            .filter(CRMActivity.company_id == company.id, CRMActivity.activity_type == "Email Bounced")
            .first()
        )
        self.assertIsNotNone(bounce_crm)


if __name__ == "__main__":
    unittest.main()
