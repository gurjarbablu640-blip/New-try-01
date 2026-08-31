"""Verification Test Suite for Pan-India Autonomous Trigger Discovery & 5-Question Framework."""
import unittest
from database import Base, SessionLocal, sync_engine
from models.company import Company
from services.signal_discovery_engine import (
    reason_signal_causality,
    ingest_discovered_signal_lead,
    discover_new_calibration_opportunities,
)


class TestPanIndiaDiscovery(unittest.TestCase):
    def setUp(self):
        if SessionLocal is not None and sync_engine is not None:
            Base.metadata.create_all(sync_engine)
            self.db = SessionLocal()
        else:
            self.db = None

    def tearDown(self):
        if hasattr(self, 'db') and self.db:
            self.db.rollback()
            self.db.close()

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


if __name__ == "__main__":
    unittest.main()
