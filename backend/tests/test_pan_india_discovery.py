"""Verification Test Suite for Pan-India Autonomous Trigger Discovery & 5-Question Framework."""
import unittest
from unittest.mock import patch
from database import Base
from models.company import Company
from models.facility import Facility
from models.intent_signal import CompanyIntentSignal
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from services.signal_discovery_engine import (
    reason_signal_causality,
    ingest_discovered_signal_lead,
    discover_new_calibration_opportunities,
)


class TestPanIndiaDiscovery(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()

    def tearDown(self):
        if hasattr(self, 'db') and self.db:
            self.db.rollback()
            self.db.close()
        self.engine.dispose()

    def test_5_question_causality_framework(self):
        res = reason_signal_causality(
            signal_type="plant_expansion",
            raw_event_title="₹300 Cr Machining Bay Expansion",
            raw_event_description="Commissioned 12 new CNC horizontal machining centers with automated pallet changers.",
            company_name="Kirloskar Pneumatic Co Ltd",
            industry="Industrial Machinery",
        )

        q = res["five_question_reasoning"]
        self.assertIn("q1_what_changed", q)
        self.assertIn("q2_affected_entity", q)
        self.assertIn("q3_calibration_impact", q)
        self.assertIn("q4_buying_behavior_change", q)
        self.assertIn("q5_oorja_action_strategy", q)

        self.assertIn("Dimensional", res["likely_parameters"])
        self.assertEqual(res["urgency"], "high")
        self.assertIn("Plant Head", res["recommended_target_role"])

    def test_pan_india_autonomous_discovery_engine(self):
        if not self.db:
            return

        res = discover_new_calibration_opportunities(self.db, geography="PAN INDIA", limit=10)

        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["geography_scope"], "PAN INDIA")
        self.assertGreaterEqual(res["total_discovered"], 5)

        states = {c["state"] for c in res["candidates"]}
        self.assertIn("Maharashtra", states)
        self.assertIn("Tamil Nadu", states)

        top_candidate = res["candidates"][0]
        self.assertIn("causality_chain", top_candidate)
        self.assertGreaterEqual(top_candidate["icp_score"], 75)
        self.assertIn(top_candidate["buying_window"], ["immediate", "30_days", "60_days"])

        # Verify company was created in CRM database
        comp = self.db.query(Company).filter(Company.name == top_candidate["company_name"]).first()
        self.assertIsNotNone(comp)
        self.assertEqual(comp.city, top_candidate["city"])

    def test_fresh_serper_result_persists_current_trigger_and_facility(self):
        if not self.db:
            return
        response = {
            "provider": "serper",
            "provider_status": "LIVE",
            "cache_hit": False,
            "results": [{
                "title": "Jabil Expands Manufacturing Capacity in India",
                "snippet": "Jabil's new facility in Pune, India, was inaugurated on 16 June 2026.",
                "url": "https://investors.jabil.com/news/2026/jabil-expands-pune",
                "metadata": {"date": "17 June 2026"},
            }],
        }

        with patch("services.research_provider.ResearchProviderRouter.search", return_value=response):
            result = discover_new_calibration_opportunities(
                self.db,
                geography="PAN INDIA",
                limit=1,
                use_cache=False,
            )

        candidate = result["candidates"][0]
        self.assertTrue(result["source_status"]["current_run_live"])
        self.assertTrue(candidate["trigger_valid"])
        self.assertTrue(candidate["facility_verified"])
        self.assertTrue(candidate["opportunity_qualified"])
        company = self.db.query(Company).filter(Company.id == candidate["company_id"]).one()
        self.assertEqual(company.source, "autonomous_discovery_live_search_serper")
        self.assertIsNotNone(self.db.query(Facility).filter(Facility.company_id == company.id).first())
        signal = self.db.query(CompanyIntentSignal).filter(CompanyIntentSignal.company_id == company.id).first()
        self.assertIsNotNone(signal)
        self.assertTrue(signal.source_url)
        self.assertTrue(signal.source_snippet)

    def test_no_cache_discovery_never_falls_back_to_pilot_catalog(self):
        if not self.db:
            return
        response = {
            "provider": "database_cache",
            "provider_status": "FALLBACK",
            "cache_hit": False,
            "results": [{"title": "Old cached item", "snippet": "old", "url": "https://example.test"}],
        }

        with patch("services.research_provider.ResearchProviderRouter.search", return_value=response):
            result = discover_new_calibration_opportunities(self.db, use_cache=False)

        self.assertEqual(result["candidates"], [])
        self.assertFalse(result["source_status"]["current_run_live"])
        self.assertEqual(self.db.query(Company).count(), 0)


if __name__ == "__main__":
    unittest.main()
