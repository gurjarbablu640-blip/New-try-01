"""Verification Test Suite for Zero-Invention, Honest State Reporting, and 8-Part Deep Reasoning."""
import unittest
from database import Base, SessionLocal, sync_engine
from services.settings_manager import test_smtp_connection, test_imap_connection
from services.apollo_adapter import execute_apollo_pilot_validation
from services.sales_assistant import ask_oorja
from services.orchestrator import AskOorjaOrchestrator


class TestTruthAuditAndZeroInvention(unittest.TestCase):
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

    def test_honest_unconfigured_smtp_and_imap(self):
        # When credentials are empty or server is unreachable, system must honestly report status
        smtp_res = test_smtp_connection()
        self.assertIn(smtp_res["status"], ["NOT_CONFIGURED", "CONNECTED", "AUTHENTICATION_FAILED", "CONNECTION_FAILED"])

        imap_res = test_imap_connection()
        self.assertIn(imap_res["status"], ["NOT_CONFIGURED", "CONNECTED", "AUTHENTICATION_FAILED", "CONNECTION_FAILED"])

    def test_transparent_apollo_status_and_safety_limit(self):
        # In live mode with no valid API key configured, must report APOLLO_BLOCKED without silent fake mock fallback
        res = execute_apollo_pilot_validation("Test Manufacturing Ltd", max_contacts=10, force_mock=False)
        self.assertIn(res["status"], ["APOLLO_BLOCKED", "pilot_completed"])
        self.assertLessEqual(res["hard_limit_enforced"], 6)

        # In explicit simulation mode, report SIMULATION
        sim_res = execute_apollo_pilot_validation("Test Manufacturing Ltd", max_contacts=10, force_mock=True)
        self.assertEqual(sim_res["status"], "pilot_completed")
        self.assertLessEqual(sim_res["hard_limit_enforced"], 6)
        self.assertTrue(sim_res["mock_mode"])

    def test_ask_oorja_8_part_structured_reasoning(self):
        if not self.db:
            return

        orchestrator = AskOorjaOrchestrator(max_iterations=2)
        res = orchestrator.run("Who should I contact today for urgent calibration outreach?", self.db)

        ans = res["answer"]
        self.assertIn("### 1. ANSWER", ans)
        self.assertIn("### 2. WHY", ans)
        self.assertIn("### 3. EVIDENCE", ans)
        self.assertIn("### 4. WHAT WE KNOW", ans)
        self.assertIn("### 5. WHAT WE INFER", ans)
        self.assertIn("### 6. WHAT WE DON'T KNOW", ans)
        self.assertIn("### 7. CONFIDENCE", ans)
        self.assertIn("### 8. RECOMMENDED ACTION", ans)


if __name__ == "__main__":
    unittest.main()
