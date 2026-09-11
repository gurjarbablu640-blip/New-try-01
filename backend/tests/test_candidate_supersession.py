"""Regression tests for candidate supersession and stale-record invalidation.

Validates:
1. Candidate A staged → new evidence invalidates A → A becomes SUPERSEDED.
2. SUPERSEDED records cannot be exported (export_batch excludes them).
3. Candidate B must independently pass gates (does NOT inherit A's contact/score).
4. Person-change invalidation correctly marks all person-specific fields invalid.
5. SUPERSEDED records preserve audit history (not deleted).
6. Old person's email cannot appear in new person's staged record.
"""
import json
import os
import shutil
import tempfile
import unittest

from services.rediff_bridge import RediffBridge
from services.qualification_state_machine import (
    QualificationState,
    invalidate_for_person_change,
)


class TestCandidateSupersession(unittest.TestCase):
    """Regression: candidate replacement must invalidate old staging records."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.bridge = RediffBridge(staging_dir=self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _make_candidate(self, person, email, designation="Plant Head", score=90.0):
        return {
            "company": "Dixon Technologies (India) Ltd",
            "facility": "Oragadam Industrial Corridor, Near Chennai, Tamil Nadu",
            "person": person,
            "designation": designation,
            "persona": "Operations Head",
            "email": email,
            "phone": "+91-120-4737200",
            "trigger": "MoU with TN Government for Laptop Plant",
            "trigger_date": "2026-01-02",
            "calibration_opportunity": "Multi-parameter test equipment calibration",
            "reasoning": "Direct manufacturing oversight at Oragadam",
            "icp_score": score,
            "provenance": "REAL",
            "evidence": {
                "trigger_current": {
                    "verified": True,
                    "trigger_date": "2026-01-02",
                    "recency_days": 10,
                    "trigger_facility_confidence": "DIRECT",
                    "ongoing_activity_evidence": "MoU with TN Government for Laptop Plant at Oragadam",
                },
                "exact_facility": {
                    "verified": True,
                    "address": "Oragadam Industrial Corridor, Near Chennai, Tamil Nadu, India",
                    "address_precision": "INDUSTRIAL_AREA",
                    "trigger_facility_confidence": "DIRECT",
                    "trigger_facility_evidence": "MoU signing names Oragadam Industrial Corridor as site",
                },
                "calibration_demand": True,
                "technical_capability": True,
                "timing": {
                    "is_active_window": True,
                    "timing_evidence": "Laptop plant commissioning at Oragadam per MoU",
                    "event_type": "commissioning",
                    "trigger_date": "2026-01-02",
                },
                "correct_person": {
                    "name": person,
                    "employment_verified": True,
                    "facility_verified": True,
                    "duties_verified": True,
                    "facility_classification": "FACILITY_OWNER",
                },
                "reachable_email": {
                    "status": "verified",
                    "mailbox_verified": True,
                    "contact_confidence": "HIGH",
                    "email": email,
                },
            },
        }

    def test_supersede_marks_old_record_and_preserves_audit(self):
        """Stage candidate A, then supersede. A must be SUPERSEDED with audit trail."""
        cand_a = self._make_candidate("Rakesh Sharma", "rakesh.sharma@dixoninfo.com")
        res_a = self.bridge.stage_candidate(cand_a)
        self.assertTrue(res_a["success"])

        # Supersede
        result = self.bridge.supersede_candidate(
            company="Dixon Technologies (India) Ltd",
            old_person="Rakesh Sharma",
            new_person="Abhinav Tiwaari",
            reason="Forensic audit: Rakesh Sharma is OTHER_COMPANY/ambiguous; Abhinav Tiwaari is Head of Quality",
        )
        self.assertEqual(result["superseded_count"], 1)
        self.assertIn(res_a["record_id"], result["superseded_record_ids"])

        # Verify record still exists (preserved) but is SUPERSEDED
        all_records = self.bridge.list_staged()
        self.assertEqual(len(all_records), 1)
        superseded = all_records[0]
        self.assertEqual(superseded["staging_status"], "SUPERSEDED")
        self.assertEqual(superseded["READY_FOR_EMAIL"], "NO")
        self.assertEqual(superseded["ready_for_email"], "NO")
        self.assertEqual(superseded["superseded_by"], "Abhinav Tiwaari")
        self.assertIn("Forensic audit", superseded["supersession_reason"])

    def test_superseded_records_excluded_from_export(self):
        """SUPERSEDED records must never appear in export batches."""
        cand_a = self._make_candidate("Rakesh Sharma", "rakesh.sharma@dixoninfo.com")
        cand_b = self._make_candidate("Abhinav Tiwaari", "abhinav.tiwaari@dixoninfo.com", "Head of Quality", 92.0)
        self.bridge.stage_candidate(cand_a)
        self.bridge.stage_candidate(cand_b)

        # Supersede A
        self.bridge.supersede_candidate(
            company="Dixon Technologies (India) Ltd",
            old_person="Rakesh Sharma",
            new_person="Abhinav Tiwaari",
            reason="Replaced by forensic audit",
        )

        # Export all
        export = self.bridge.export_batch(export_format="json")
        self.assertEqual(export["count"], 1)
        data = json.loads(export["payload"])
        exported_persons = [r.get("person") or r.get("CONTACT_NAME") for r in data["records"]]
        self.assertNotIn("Rakesh Sharma", exported_persons)
        self.assertIn("Abhinav Tiwaari", exported_persons)

    def test_new_candidate_does_not_inherit_old_contact(self):
        """Candidate B must have its own email, not inherit A's."""
        cand_a = self._make_candidate("Rakesh Sharma", "rakesh.sharma@dixoninfo.com")
        cand_b = self._make_candidate("Abhinav Tiwaari", "abhinav.tiwaari@dixoninfo.com", "Head of Quality")

        res_a = self.bridge.stage_candidate(cand_a)
        res_b = self.bridge.stage_candidate(cand_b)

        self.assertTrue(res_b["success"])
        record_b = res_b["record"]
        self.assertEqual(record_b["email"], "abhinav.tiwaari@dixoninfo.com")
        self.assertNotEqual(record_b["email"], "rakesh.sharma@dixoninfo.com")
        self.assertEqual(record_b["person"], "Abhinav Tiwaari")

    def test_person_change_invalidation_flags(self):
        """invalidate_for_person_change must flag all person-specific fields."""
        result = invalidate_for_person_change(
            company="Dixon Technologies (India) Ltd",
            old_person="Rakesh Sharma",
            new_person="Abhinav Tiwaari",
            reason="Forensic audit disqualified Rakesh Sharma",
        )
        self.assertTrue(result.must_invalidate_contact)
        self.assertTrue(result.must_invalidate_score)
        self.assertTrue(result.must_invalidate_staging)
        self.assertTrue(result.must_invalidate_outreach)
        self.assertEqual(result.new_state, QualificationState.REJECTED)
        self.assertEqual(result.old_person, "Rakesh Sharma")
        self.assertEqual(result.new_person, "Abhinav Tiwaari")

    def test_supersede_is_idempotent(self):
        """Superseding an already-superseded record does not double-process."""
        cand_a = self._make_candidate("Rakesh Sharma", "rakesh.sharma@dixoninfo.com")
        self.bridge.stage_candidate(cand_a)

        res1 = self.bridge.supersede_candidate(
            company="Dixon Technologies (India) Ltd",
            old_person="Rakesh Sharma",
            new_person="Abhinav Tiwaari",
            reason="First supersession",
        )
        self.assertEqual(res1["superseded_count"], 1)

        res2 = self.bridge.supersede_candidate(
            company="Dixon Technologies (India) Ltd",
            old_person="Rakesh Sharma",
            new_person="Someone Else",
            reason="Second attempt",
        )
        self.assertEqual(res2["superseded_count"], 0)  # Already superseded

    def test_supersede_does_not_affect_other_companies(self):
        """Supersession for company X must not touch company Y."""
        cand_dixon = self._make_candidate("Rakesh Sharma", "rakesh.sharma@dixoninfo.com")
        cand_valeo = self._make_candidate("Rakesh Sharma", "rakesh.sharma@valeo.com")
        cand_valeo["company"] = "Valeo India"
        cand_valeo["facility"] = "Sanand Plant"

        self.bridge.stage_candidate(cand_dixon)
        self.bridge.stage_candidate(cand_valeo)

        result = self.bridge.supersede_candidate(
            company="Dixon Technologies (India) Ltd",
            old_person="Rakesh Sharma",
            new_person="Abhinav Tiwaari",
            reason="Dixon-specific supersession",
        )
        self.assertEqual(result["superseded_count"], 1)

        # Valeo record should be untouched
        records = self.bridge.list_staged()
        valeo_records = [r for r in records if r.get("company") == "Valeo India"]
        self.assertEqual(len(valeo_records), 1)
        self.assertNotEqual(valeo_records[0]["staging_status"], "SUPERSEDED")


if __name__ == "__main__":
    unittest.main()
