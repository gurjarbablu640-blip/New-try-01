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
                "trigger_current": {
                    "verified": True,
                    "trigger_date": "2026-08-15",
                    "recency_days": 25,
                    "trigger_facility_confidence": "DIRECT",
                    "ongoing_activity_evidence": "New EV powertrain line commissioning at Sanand",
                },
                "exact_facility": {
                    "verified": True,
                    "address": "GIDC Sanand, Ahmedabad, Gujarat, India",
                    "address_precision": "INDUSTRIAL_AREA",
                    "trigger_facility_confidence": "DIRECT",
                    "trigger_facility_evidence": "EV powertrain line commissioning at Sanand GIDC",
                },
                "calibration_demand": True,
                "technical_capability": True,
                "timing": {
                    "is_active_window": True,
                    "timing_evidence": "New EV Powertrain Line commissioning at Sanand facility",
                    "event_type": "commissioning",
                    "trigger_date": "2026-08-15",
                },
                "correct_person": {
                    "name": "Abhijit Biswal",
                    "employment_verified": True,
                    "facility_verified": True,
                    "duties_verified": True,
                    "facility_classification": "FACILITY_OWNER",
                    "authority_class": "FACILITY_OWNER",
                    "person_confidence": "HIGH",
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

    def test_20_point_mapped_fields_in_record_and_csv(self):
        candidate = self._valid_candidate()
        stage_res = self.bridge.stage_candidate(candidate)
        record = stage_res["record"]

        # Check all 20 required fields in mapped dict
        required_20_fields = [
            "READY_FOR_EMAIL", "COMPANY", "FACILITY", "CITY", "STATE",
            "CONTACT_NAME", "FIRST_NAME", "DESIGNATION", "PERSONA", "EMAIL", "PHONE",
            "TRIGGER_EVENT", "TRIGGER_DATE", "CALIBRATION_OPPORTUNITY", "REASON_FOR_OUTREACH",
            "LEAD_SCORE", "FACILITY_VERIFIED", "CONTACT_VERIFIED", "CONTACT_LOCATION", "NOTES"
        ]
        for f in required_20_fields:
            self.assertIn(f, record, f"Missing required 20-field mapping: {f}")

        self.assertEqual(record["READY_FOR_EMAIL"], "YES")
        self.assertEqual(record["COMPANY"], "Valeo India")
        self.assertEqual(record["FIRST_NAME"], "Abhijit")
        self.assertEqual(record["CONTACT_NAME"], "Abhijit Biswal")
        self.assertEqual(record["TRIGGER_EVENT"], "New EV Powertrain Line Commissioning")
        self.assertEqual(record["CALIBRATION_OPPORTUNITY"], "Automated CMM and Gauging Rig Calibration")

        # Check CSV export contains all 20 fields as header
        export_csv = self.bridge.export_batch([stage_res["record_id"]], export_format="csv")
        csv_header = export_csv["payload"].splitlines()[0]
        for f in required_20_fields:
            self.assertIn(f, csv_header)

    def test_generate_outreach_preview_quality_audit(self):
        candidate = self._valid_candidate()
        stage_res = self.bridge.stage_candidate(candidate)
        record = stage_res["record"]

        preview = self.bridge.generate_outreach_preview(record)
        self.assertEqual(preview["preview_status"], "READY_FOR_PREVIEW")
        self.assertTrue(preview["test_mode"])
        self.assertTrue(preview["no_send_enforced"])
        self.assertEqual(preview["to"], "abhijit.biswal@valeo.com")
        self.assertIn("Bablu@oorjatechnical.org", preview["cc"])
        self.assertIn("piyushk@oorjatechnical.com", preview["cc"])

        # Quality audit checks
        audit = preview["audit_checks"]
        self.assertTrue(audit["is_designation_aware"])
        self.assertTrue(audit["is_trigger_aware"])
        self.assertTrue(audit["is_facility_aware"])
        self.assertTrue(audit["is_consultative"])
        self.assertTrue(audit["asks_referral"])
        self.assertTrue(audit["cc_3963_scope_validated"])
        self.assertFalse(audit["has_unsupported_nabl_claims"])
        self.assertFalse(audit["fake_urgency_detected"])
        self.assertFalse(audit["ai_filler_detected"])

        # Body checks
        self.assertIn("CC-3963", preview["body_text"])
        self.assertIn("ISO/IEC 17025:2017", preview["body_text"])
        self.assertIn("Abhijit", preview["body_text"])
        self.assertIn("Sanand Plant", preview["body_text"])
        self.assertIn("New EV Powertrain Line Commissioning", preview["body_text"])
        self.assertIn("point me to the right lead", preview["body_text"].lower())

    def test_unverified_mailbox_sets_ready_for_email_no(self):
        candidate = self._valid_candidate()
        # Inferred email with mailbox unverified
        candidate["evidence"]["reachable_email"]["mailbox_verified"] = False
        res = self.bridge.stage_candidate(candidate, production=False)
        self.assertTrue(res["success"])
        record = res["record"]
        self.assertEqual(record["READY_FOR_EMAIL"], "NO")
        self.assertEqual(record["staging_status"], "STAGED_TEST")

    def test_export_batch_blocks_unverified_in_production(self):
        candidate = self._valid_candidate()
        candidate["evidence"]["reachable_email"]["mailbox_verified"] = False
        res = self.bridge.stage_candidate(candidate, production=False)
        record_id = res["record_id"]

        # In production mode, unverified email candidate cannot be exported
        prod_export = self.bridge.export_batch([record_id], production=True)
        self.assertEqual(prod_export["count"], 0)
        self.assertIsNone(prod_export["batch_id"])

    def test_export_batch_blocks_superseded(self):
        candidate = self._valid_candidate()
        res = self.bridge.stage_candidate(candidate)
        record_id = res["record_id"]

        # Supersede the record
        self.bridge.mark_superseded(record_id, "Newer candidate selected", superseded_by="Other Person")

        # Export attempt should yield 0 records
        export_res = self.bridge.export_batch([record_id], production=False)
        self.assertEqual(export_res["count"], 0)


if __name__ == "__main__":
    unittest.main()

