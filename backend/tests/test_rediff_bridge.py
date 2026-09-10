"""Unit tests for RediffBridge staging and handoff to Rediff_Email_System."""

import json
import os
import shutil
import tempfile
import unittest

from services.rediff_bridge import RediffBridge, RediffHandoffRecord


class TestRediffBridge(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.bridge = RediffBridge(staging_dir=self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _valid_candidate(self):
        return {
            "company": "Valeo India",
            "facility": "Sanand Plant",
            "person": "Abhijit Biswal",
            "designation": "Manager - Quality & Metrology",
            "persona": "Quality Head",
            "email": "abhijit.biswal@valeo.com",
            "phone": "+91-9876543210",
            "trigger": "New EV Powertrain Line Commissioning",
            "trigger_date": "2026-08-15",
            "calibration_opportunity": "Automated CMM and Gauging Rig Calibration",
            "reasoning": "Direct ownership of Sanand plant metrology lab following capacity ramp-up",
            "icp_score": 96.5,
            "provenance": "REAL",
            "evidence": {
                "trigger_current": True,
                "exact_facility": True,
                "calibration_demand": True,
                "technical_capability": True,
                "timing": True,
                "correct_person": {
                    "employment_verified": True,
                    "facility_verified": True,
                    "duties_verified": True,
                },
                "reachable_email": {
                    "status": "verified",
                    "mailbox_verified": True,
                    "contact_confidence": "HIGH",
                    "email": "abhijit.biswal@valeo.com",
                },
            },
        }

    def test_stage_fully_qualified_candidate(self):
        candidate = self._valid_candidate()
        result = self.bridge.stage_candidate(candidate)
        self.assertTrue(result["success"])
        self.assertEqual(result["action"], "staged")
        record = result["record"]
        self.assertEqual(record["company"], "Valeo India")
        self.assertEqual(record["person"], "Abhijit Biswal")
        self.assertEqual(record["verification_status"], "7_GATES_PASSED_VERIFIED")
        self.assertTrue(record["test_mode"])

        staged_list = self.bridge.list_staged("STAGED")
        self.assertEqual(len(staged_list), 1)
        self.assertEqual(staged_list[0]["email"], "abhijit.biswal@valeo.com")

    def test_rejection_when_gates_fail(self):
        candidate = self._valid_candidate()
        # Person fails verification
        candidate["evidence"]["correct_person"] = {
            "employment_verified": True,
            "facility_verified": False,  # Missing facility verification
            "duties_verified": True,
        }
        result = self.bridge.stage_candidate(candidate)
        self.assertFalse(result["success"])
        self.assertIn("correct_person", result.get("failed_gates", []))
        self.assertEqual(len(self.bridge.list_staged()), 0)

    def test_mock_isolation_in_production(self):
        candidate = self._valid_candidate()
        candidate["provenance"] = "MOCK"
        result = self.bridge.stage_candidate(candidate, production=True)
        self.assertFalse(result["success"])
        self.assertIn("production", result["reason"])
        self.assertEqual(len(self.bridge.list_staged()), 0)

    def test_export_batch_json_and_csv(self):
        candidate = self._valid_candidate()
        stage_res = self.bridge.stage_candidate(candidate)
        record_id = stage_res["record_id"]

        # Export JSON
        export_json = self.bridge.export_batch([record_id], export_format="json")
        self.assertEqual(export_json["count"], 1)
        data = json.loads(export_json["payload"])
        self.assertEqual(data["records"][0]["company"], "Valeo India")
        self.assertTrue(export_json["test_mode"])

        # Staging status should now be EXPORTED
        staged = self.bridge.list_staged()
        self.assertEqual(staged[0]["staging_status"], "EXPORTED")


if __name__ == "__main__":
    unittest.main()
