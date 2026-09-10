"""Unit tests for the autonomous scheduler and 24-hour operational lifecycle."""

import json
import os
import shutil
import tempfile
import unittest
from datetime import time

from services.autonomous_scheduler import AutonomousScheduler


class TestAutonomousScheduler(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.report_dir = os.path.join(self.test_dir, "reports")
        self.state_dir = os.path.join(self.test_dir, "state")
        self.scheduler = AutonomousScheduler(report_dir=self.report_dir, state_dir=self.state_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_day_prospecting_window(self):
        # 11:30 AM should be daytime prospecting
        t_1130 = time(11, 30)
        window = self.scheduler.determine_time_window(t_1130)
        self.assertEqual(window, "DAY_PROSPECTING")
        self.assertTrue(self.scheduler.is_email_outreach_permitted(t_1130))
        self.assertTrue(self.scheduler.is_research_enrichment_permitted())

    def test_night_research_safety_lock(self):
        # 10:00 PM should be night research: NO prospect emails allowed!
        t_2200 = time(22, 0)
        window = self.scheduler.determine_time_window(t_2200)
        self.assertEqual(window, "NIGHT_RESEARCH")
        self.assertFalse(self.scheduler.is_email_outreach_permitted(t_2200))
        # But research and enrichment remain permitted overnight
        self.assertTrue(self.scheduler.is_research_enrichment_permitted())

        # 4:00 AM should also be night research
        t_0400 = time(4, 0)
        self.assertEqual(self.scheduler.determine_time_window(t_0400), "NIGHT_RESEARCH")
        self.assertFalse(self.scheduler.is_email_outreach_permitted(t_0400))

    def test_evening_cutoff_window(self):
        # 6:15 PM should be evening report window
        t_1815 = time(18, 15)
        window = self.scheduler.determine_time_window(t_1815)
        self.assertEqual(window, "EVENING_REPORT")
        self.assertFalse(self.scheduler.is_email_outreach_permitted(t_1815))

    def test_morning_discovery_execution(self):
        res = self.scheduler.execute_morning_discovery()
        self.assertEqual(res["status"], "started")
        self.assertEqual(res["cycle"], "MORNING_DISCOVERY")
        state = self.scheduler._load_state()
        self.assertIn("last_discovery_start", state)

    def test_restricted_inbox_checks(self):
        res_morning = self.scheduler.execute_inbox_check(slot="MORNING_1030")
        self.assertEqual(res_morning["status"], "completed")
        self.assertEqual(res_morning["readonly_mailbox"], "INBOX")

        res_afternoon = self.scheduler.execute_inbox_check(slot="AFTERNOON_1600")
        self.assertEqual(res_afternoon["status"], "completed")

        state = self.scheduler._load_state()
        self.assertIn("last_inbox_check_MORNING_1030", state)
        self.assertIn("last_inbox_check_AFTERNOON_1600", state)

    def test_evening_cutoff_produces_report(self):
        custom = {
            "discovered": 28,
            "qualified": 12,
            "staged": 8,
            "phones_enriched": 4,
            "apollo_credits": 3,
            "replies_processed": 5,
        }
        report = self.scheduler.execute_evening_cutoff_and_report(date_str="2026-09-10", custom_metrics=custom)
        self.assertEqual(report.date_str, "2026-09-10")
        self.assertEqual(report.discovered_leads, 28)
        self.assertEqual(report.qualified_opportunities, 12)
        self.assertEqual(report.staged_ready_for_email, 8)
        self.assertEqual(report.phones_enriched, 4)
        self.assertEqual(report.apollo_credits_used, 3)
        self.assertEqual(report.replies_processed, 5)

        # Check saved report file
        report_file = os.path.join(self.report_dir, "report_2026-09-10.json")
        self.assertTrue(os.path.exists(report_file))
        with open(report_file, "r") as f:
            data = json.load(f)
        self.assertEqual(data["discovered_leads"], 28)

    def test_runtime_summary(self):
        summary = self.scheduler.get_runtime_summary()
        self.assertEqual(summary["status"], "active")
        self.assertIn("schedule", summary)
        self.assertIn("10:00 AM", summary["schedule"])
        self.assertIn("6:00 PM", summary["schedule"])


if __name__ == "__main__":
    unittest.main()
