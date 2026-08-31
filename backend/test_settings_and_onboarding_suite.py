"""Unit and Integration Tests for Settings Management and Customer Onboarding.

Tests:
1. Masked secret retrieval (no plaintext secrets exposed)
2. Settings persistence and runtime override
3. Complete removal of Anthropic from settings
4. Diagnostic connection testers (OpenAI, Gemini, Apollo, SMTP, IMAP)
5. Apollo pilot hard limit enforcement (<= 6 contacts)
6. Manual prospect onboarding into CRM, CompanyBrain, BeliefState, and Guided Actions
7. Partial / Incomplete customer input handling
"""
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
from models.person import Person
from models.customer_asset import CustomerAsset
from models.company_brain import CompanyIntelligenceFact, CompanyTimelineEvent
from models.reasoning_engine import CompanyBeliefState, SignalEvidenceNode
from services.settings_manager import (
    get_masked_settings_status,
    update_settings,
    test_ai_provider_connection,
    test_apollo_connection,
    test_smtp_connection,
    test_imap_connection,
)
from services.customer_onboarding import onboard_manual_prospect


class TestSettingsAndOnboardingSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(cls.engine)
        cls.Session = sessionmaker(bind=cls.engine)

    def setUp(self):
        self.db = self.Session()

    def tearDown(self):
        self.db.query(SignalEvidenceNode).delete()
        self.db.query(CompanyBeliefState).delete()
        self.db.query(CompanyTimelineEvent).delete()
        self.db.query(CompanyIntelligenceFact).delete()
        self.db.query(CustomerAsset).delete()
        self.db.query(Person).delete()
        self.db.query(Company).delete()
        self.db.commit()
        self.db.close()

    def test_01_masked_settings_status_no_secrets(self):
        """Test that settings status returns masked strings and no plaintext secrets."""
        status = get_masked_settings_status()
        self.assertIn("ai_providers", status)
        self.assertIn("apollo", status)
        self.assertIn("smtp", status)
        self.assertIn("imap", status)

        # Check mask format
        openai_key = status["ai_providers"]["openai"]["masked_key"]
        self.assertTrue("••••" in openai_key or openai_key == "")
        self.assertNotIn("sk-proj-super-secret-key-12345", str(status))

    def test_02_update_settings_and_runtime_override(self):
        """Test updating settings persists runtime overrides and ignores masked values."""
        update_payload = {
            "OPENAI_API_KEY": "sk-proj-test-sample-key-9999",
            "SMTP_HOST": "smtp.testserver.local",
            "OUTBOUND_TEST_MODE": True,
        }
        res = update_settings(update_payload)
        self.assertTrue(res["ai_providers"]["openai"]["configured"])
        self.assertEqual(res["smtp"]["host"], "smtp.testserver.local")

        # Now test that submitting a masked placeholder does not clobber the real key
        clobber_attempt = {
            "OPENAI_API_KEY": "sk-p••••••••9999",
        }
        res_after = update_settings(clobber_attempt)
        self.assertTrue(res_after["ai_providers"]["openai"]["configured"])

    def test_03_no_anthropic_in_settings_schema(self):
        """Verify that Anthropic is completely absent from all settings schemas and providers."""
        status = get_masked_settings_status()
        self.assertNotIn("anthropic", status["ai_providers"])
        self.assertNotIn("claude", str(status).lower())
        
        # Test rejection of unsupported providers in connection tester
        test_res = test_ai_provider_connection("anthropic")
        self.assertEqual(test_res["status"], "UNSUPPORTED")
        self.assertIn("OpenAI or Google Gemini", test_res["message"])

    def test_04_diagnostic_connection_testers(self):
        """Test diagnostic connection testers for AI, Apollo, SMTP, and IMAP."""
        # AI Tester
        update_settings({"GOOGLE_API_KEY": "mock_gemini_key_123"})
        gemini_test = test_ai_provider_connection("gemini")
        self.assertEqual(gemini_test["status"], "CONNECTED")

        # Apollo Tester (verifies pilot limit message)
        update_settings({"APOLLO_API_KEY": "mock_apollo_key_123"})
        apollo_test = test_apollo_connection()
        self.assertEqual(apollo_test["status"], "CONNECTED")
        self.assertIn("≤ 6 contacts", apollo_test["message"])

        # SMTP & IMAP Testers
        update_settings({"SMTP_HOST": "localhost", "SMTP_USER": "sales@oorja.local"})
        smtp_test = test_smtp_connection()
        self.assertEqual(smtp_test["status"], "CONNECTED")

        update_settings({"IMAP_HOST": "localhost", "IMAP_USER": "sales@oorja.local"})
        imap_test = test_imap_connection()
        self.assertEqual(imap_test["status"], "CONNECTED")

    def test_05_manual_prospect_onboarding_full_loop(self):
        """Test manual customer onboarding seeds CRM, CompanyBrain, BeliefState, and Guided Actions."""
        res = onboard_manual_prospect(
            db=self.db,
            company_name="Godrej Aerospace Precision Division",
            industry="Aerospace & Defense",
            city="Mumbai",
            state="Maharashtra",
            country="India",
            facility="Vikhroli Aerospace Center",
            website="https://godrej.com/aerospace",
            contact_name="Commander K. Verma",
            contact_role="Head of Quality Assurance & AS9100 Metrology",
            contact_email="kverma@godrej.local",
            contact_phone="+91-9820011223",
            existing_vendor="Intertek / In-House",
            calibration_requirement="High-precision dimensional CMM, turbine blade profile, and vacuum pressure gauge calibration",
            instrument_categories=["Dimensional", "Pressure", "Thermal"],
            last_calibration_date=date(2025, 10, 15),
            next_calibration_due=date(2026, 10, 15),
            notes="Expanding precision machining facility with 4 new DMG MORI 5-axis machines.",
        )

        self.assertEqual(res["status"], "success")
        self.assertTrue(res["is_new_company"])
        self.assertEqual(res["company"]["name"], "Godrej Aerospace Precision Division")
        self.assertEqual(res["contact"]["name"], "Commander K. Verma")
        self.assertIsNotNone(res["asset"])

        # Verify CompanyBrain Fact was recorded
        facts = self.db.query(CompanyIntelligenceFact).filter(CompanyIntelligenceFact.company_id == res["company"]["id"]).all()
        self.assertGreaterEqual(len(facts), 1)
        self.assertIn("Vikhroli Aerospace Center", facts[0].evidence_text)

        # Verify Timeline event
        timeline = self.db.query(CompanyTimelineEvent).filter(CompanyTimelineEvent.company_id == res["company"]["id"]).all()
        self.assertGreaterEqual(len(timeline), 1)

        # Verify Belief State initialized
        belief_state = self.db.query(CompanyBeliefState).filter(CompanyBeliefState.company_id == res["company"]["id"]).first()
        self.assertIsNotNone(belief_state)
        self.assertGreaterEqual(belief_state.beliefs["calibration_need"]["value"], 0.70)

        # Verify guided actions
        workflow = res["guided_workflow"]
        self.assertEqual(len(workflow), 5)
        self.assertEqual(workflow[0]["action"], "RESEARCH_COMPANY")
        self.assertEqual(workflow[3]["action"], "APOLLO_PILOT_ENRICHMENT")

    def test_06_manual_prospect_with_incomplete_fields(self):
        """Test that incomplete customer entries are accepted without forcing fake data."""
        res = onboard_manual_prospect(
            db=self.db,
            company_name="Apex Precision Tools",
            industry=None,  # Unknown
            city=None,      # Unknown
        )
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["company"]["name"], "Apex Precision Tools")
        self.assertIsNone(res["contact"])
        self.assertIsNone(res["asset"])


if __name__ == "__main__":
    unittest.main()
