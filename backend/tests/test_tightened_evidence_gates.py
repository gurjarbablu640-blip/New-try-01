"""Regression tests for tightened evidence gates:
A. 2-year-old announcement with no newer evidence -> trigger_current FAIL
B. old announcement + current commissioning evidence -> trigger_current PASS
C. company-level trigger + unrelated facility address -> trigger_facility_alignment FAIL/HOLD
D. company-wide person with no facility evidence -> facility ownership must not be invented
E. confirmed group functional owner -> may pass if evidence clearly establishes responsibility
F. unsupported Oorja technical scope -> must not be presented as confirmed capability
"""

import unittest
from datetime import datetime, timezone

from services.opportunity_gates import (
    BLOCKED,
    HOT,
    READY_FOR_EMAIL,
    classify_technical_scope,
    evaluate_opportunity_gates,
)


def base_evidence(**overrides):
    ev = {
        "trigger_current": {
            "trigger_date": "2026-08-01",
            "ongoing_activity_evidence": "Plant commissioning active",
            "trigger_facility_confidence": "DIRECT",
        },
        "exact_facility": {
            "verified": True,
            "address": "Sanand Plant, GIDC, Gujarat",
            "trigger_facility_confidence": "DIRECT",
        },
        "calibration_demand": True,
        "technical_capability": {
            "scope_items": ["3D CMM", "Vernier Caliper", "RTD Pt100 temperature sensor"],
        },
        "timing": True,
        "correct_person": {
            "employment_verified": True,
            "duties_verified": True,
            "facility_verified": True,
            "facility_classification": "FACILITY_OWNER",
        },
        "reachable_email": {
            "address": "head.qa@example.com",
            "status": "verified",
            "mailbox_verified": True,
            "contact_confidence": "HIGH",
        },
        "score": 95.0,
        "provenance": "REAL",
    }
    ev.update(overrides)
    return ev


class TightenedEvidenceGatesTests(unittest.TestCase):
    def test_case_a_2_year_old_announcement_fails(self):
        """Case A: 2-year-old announcement with no newer evidence -> trigger_current FAIL."""
        # 2 years prior to Sept 2026 is Sept 2024 (recency_days > 700)
        ev = base_evidence(
            trigger_current={
                "trigger_date": "2024-05-10",
                "ongoing_activity_evidence": "",  # Missing ongoing evidence!
                "trigger_facility_confidence": "DIRECT",
            }
        )
        res = evaluate_opportunity_gates(ev, production=True)
        self.assertFalse(res["gates"]["trigger_current"]["passed"])
        self.assertEqual(res["gates"]["trigger_current"]["recency_status"], "STALE")
        self.assertIn("STALE", res["gates"]["trigger_current"]["reason"])
        self.assertEqual(res["status"], BLOCKED)

    def test_case_b_old_announcement_with_current_evidence_passes(self):
        """Case B: Old announcement + current commissioning evidence -> trigger_current PASS."""
        ev = base_evidence(
            trigger_current={
                "trigger_date": "2024-05-10",
                "ongoing_activity_evidence": "BSE filing Aug 2026 confirms ongoing phase-2 equipment commissioning",
                "future_commissioning": True,
                "trigger_facility_confidence": "DIRECT",
            }
        )
        res = evaluate_opportunity_gates(ev, production=True)
        self.assertTrue(res["gates"]["trigger_current"]["passed"])
        self.assertEqual(res["gates"]["trigger_current"]["recency_status"], "STALE")
        self.assertIn("multi-year execution is confirmed active", res["gates"]["trigger_current"]["reason"])

    def test_case_c_weak_trigger_facility_linkage_fails(self):
        """Case C: Company-level trigger + unrelated facility address -> trigger_facility_alignment FAIL/HOLD."""
        ev = base_evidence(
            trigger_current={
                "trigger_date": "2026-08-01",
                "trigger_facility_confidence": "WEAK",
                "trigger_facility_evidence": "Corporate expansion mentioned generally, no Sanand plant reference",
            },
            exact_facility={
                "verified": True,
                "address": "Sanand Plant, Gujarat",
                "trigger_facility_confidence": "WEAK",
            }
        )
        res = evaluate_opportunity_gates(ev, production=True)
        self.assertFalse(res["gates"]["exact_facility"]["passed"])
        self.assertIn("Trigger-to-facility linkage is WEAK", res["gates"]["exact_facility"]["reason"])
        self.assertEqual(res["status"], BLOCKED)

    def test_case_d_company_wide_person_no_facility_fails(self):
        """Case D: Company-wide person with no facility evidence -> facility ownership must not be invented."""
        ev = base_evidence(
            correct_person={
                "employment_verified": True,
                "duties_verified": True,
                "facility_verified": False,
                "facility_classification": "COMPANY_ONLY",
            }
        )
        res = evaluate_opportunity_gates(ev, production=True)
        self.assertFalse(res["gates"]["correct_person"]["passed"])
        self.assertIn("company-level title only", res["gates"]["correct_person"]["reason"])
        self.assertEqual(res["status"], BLOCKED)

    def test_case_e_confirmed_group_functional_owner_passes(self):
        """Case E: Confirmed group functional owner -> may pass if evidence clearly establishes responsibility."""
        ev = base_evidence(
            correct_person={
                "employment_verified": True,
                "duties_verified": True,
                "facility_verified": False,
                "facility_classification": "GROUP_FUNCTION_OWNER",
                "group_ownership_verified": True,
            }
        )
        res = evaluate_opportunity_gates(ev, production=True)
        self.assertTrue(res["gates"]["correct_person"]["passed"])
        self.assertIn("GROUP_FUNCTION_OWNER", res["gates"]["correct_person"]["reason"])
        self.assertTrue(res["ready_for_email"])

    def test_case_f_unsupported_oorja_scope_fails(self):
        """Case F: Unsupported Oorja technical scope -> must not be presented as confirmed capability."""
        ev = base_evidence(
            technical_capability={
                "scope_items": [
                    "Optical Emission Spectrometer (OES)",
                    "Ultrasonic Flaw Detector",
                    "Metallurgical Chemical Assay",
                ],
            }
        )
        res = evaluate_opportunity_gates(ev, production=True)
        self.assertFalse(res["gates"]["technical_capability"]["passed"])
        self.assertIn("out-of-scope", res["gates"]["technical_capability"]["reason"])
        self.assertEqual(res["status"], BLOCKED)

    def test_case_f_supported_oorja_scope_passes(self):
        """Supported Oorja NABL mechanical and thermal calibration passes."""
        ev = base_evidence(
            technical_capability={
                "scope_items": [
                    "3D Coordinate Measuring Machine (CMM)",
                    "Pressure Transmitters (0-400 bar)",
                    "RTD Pt100 Sensors (-50C to 450C)",
                ],
            }
        )
        res = evaluate_opportunity_gates(ev, production=True)
        self.assertTrue(res["gates"]["technical_capability"]["passed"])
        self.assertIn("within Oorja certified NABL scope", res["gates"]["technical_capability"]["reason"])
        self.assertEqual(res["status"], HOT)


if __name__ == "__main__":
    unittest.main()
