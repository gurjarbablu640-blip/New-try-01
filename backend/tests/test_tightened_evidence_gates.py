"""Regression tests for tightened evidence gates:
Part 1 — Scope & Certificate Integrity:
A. Unknown certificate number cannot become confirmed NABL scope.
B. A generic plausible calibration instrument cannot become CONFIRMED_NABL_SCOPE without source evidence.
C. Known actual scope evidence can become CONFIRMED_NABL_SCOPE.

Part 2 — Baseline Demand vs Current Buying Timing Separation:
D. Annual/periodic calibration requirement alone does NOT pass timing.
E. Current commissioning/audit/procurement evidence CAN pass timing.
F. Baseline calibration demand can remain TRUE while timing is FAIL.

Part 3 — Core Evidence Gates:
- 2-year-old announcement with no newer evidence -> trigger_current FAIL
- old announcement + current commissioning evidence -> trigger_current PASS
- company-level trigger + unrelated facility address -> trigger_facility_alignment FAIL/HOLD
- company-wide person with no facility evidence -> facility ownership must not be invented
- confirmed group functional owner -> passes if evidence clearly establishes responsibility
- unsupported Oorja technical scope -> must not be presented as confirmed capability
"""

import unittest
from datetime import datetime, timezone

from services.oorja_capability_service import (
    CONFIRMED_NABL_SCOPE,
    KNOWN_OORJA_SERVICE_NON_SCOPE_VERIFIED,
    OORJA_OFFICIAL_CERTIFICATE_NO,
    OUT_OF_SCOPE,
    POSSIBLE,
    UNKNOWN,
    classify_capability,
    classify_technical_scope_batch,
)
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
        "calibration_demand": {
            "verified": True,
            "demand_basis": "IATF 16949 precision automotive manufacturing",
        },
        "technical_capability": {
            "scope_items": ["3D CMM", "Vernier Caliper", "RTD Pt100 temperature sensor"],
            "certificate_no": OORJA_OFFICIAL_CERTIFICATE_NO,
        },
        "timing": {
            "buying_window": "active plant commissioning and equipment installation",
            "is_buying_window_active": True,
        },
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
    # ─────────────────────────────────────────────────────────────────
    # Scope & Certificate Integrity Regression Tests (Cases A, B, C)
    # ─────────────────────────────────────────────────────────────────

    def test_case_a_unknown_certificate_cannot_become_confirmed_nabl_scope(self):
        """Rule A: Unknown certificate number cannot become confirmed NABL scope."""
        # Genuine instrument (Vernier Caliper) checked against unknown/fabricated certificate CC-2841
        res = classify_capability("Vernier Caliper", certificate_no="CC-2841")
        self.assertNotEqual(res["classification"], CONFIRMED_NABL_SCOPE)
        self.assertEqual(res["classification"], UNKNOWN)
        self.assertIn("not the verified Oorja NABL certificate", res["reason"])

        # Also verify through opportunity gates
        ev = base_evidence(
            technical_capability={
                "scope_items": ["Vernier Caliper", "3D CMM"],
                "certificate_no": "CC-2841",  # Fabricated cert number
            }
        )
        gate_res = evaluate_opportunity_gates(ev, production=True)
        self.assertFalse(gate_res["gates"]["technical_capability"]["passed"])
        self.assertIn("None of the requested instruments match Oorja's verified NABL scope", gate_res["gates"]["technical_capability"]["reason"])
        self.assertEqual(gate_res["status"], BLOCKED)

    def test_case_b_generic_plausible_instrument_cannot_become_confirmed_nabl_scope(self):
        """Rule B: Generic plausible calibration instrument cannot become CONFIRMED_NABL_SCOPE without source evidence."""
        # Sound level meter is plausible for generic metrology, but not in CC-3963 schedule
        res = classify_capability("Sound Level Meter", certificate_no=OORJA_OFFICIAL_CERTIFICATE_NO)
        self.assertEqual(res["classification"], POSSIBLE)
        self.assertNotEqual(res["classification"], CONFIRMED_NABL_SCOPE)
        self.assertIn("not confirmed in stored CC-3963 NABL schedule", res["reason"])

        # Flow meter is plausible, but not verified in CC-3963
        flow_res = classify_capability("Electromagnetic Flow Meter", certificate_no=OORJA_OFFICIAL_CERTIFICATE_NO)
        self.assertEqual(flow_res["classification"], POSSIBLE)
        self.assertNotEqual(flow_res["classification"], CONFIRMED_NABL_SCOPE)

        # Batch classification should isolate generic plausible items to POSSIBLE
        batch = classify_technical_scope_batch(["Sound Level Meter", "Flow Meter", "Lux Meter"])
        self.assertEqual(len(batch["CONFIRMED_NABL_SCOPE"]), 0)
        self.assertEqual(len(batch["POSSIBLE"]), 3)

    def test_case_c_known_actual_scope_evidence_becomes_confirmed_nabl_scope(self):
        """Rule C: Known actual scope evidence can become CONFIRMED_NABL_SCOPE with full parameter metadata."""
        res = classify_capability("Coordinate Measuring Machine (CMM)", certificate_no=OORJA_OFFICIAL_CERTIFICATE_NO)
        self.assertEqual(res["classification"], CONFIRMED_NABL_SCOPE)
        self.assertIsNotNone(res["entry"])
        self.assertEqual(res["entry"]["certificate_no"], OORJA_OFFICIAL_CERTIFICATE_NO)
        self.assertEqual(res["entry"]["discipline"], "Mechanical")
        self.assertEqual(res["entry"]["range_description"], "0 to 1200 mm")
        self.assertEqual(res["entry"]["cmc_uncertainty"], "±(2.5 + 3L/1000) µm")
        self.assertEqual(res["entry"]["service_capability"], "LAB_AND_ONSITE")
        self.assertTrue(res["entry"]["is_nabl_accredited"])

        # Pressure and thermal verified items
        p_res = classify_capability("Bourdon Tube Pressure Gauge", certificate_no=OORJA_OFFICIAL_CERTIFICATE_NO)
        self.assertEqual(p_res["classification"], CONFIRMED_NABL_SCOPE)
        self.assertEqual(p_res["entry"]["discipline"], "Mechanical")

        t_res = classify_capability("RTD Pt100 Temperature Sensor", certificate_no=OORJA_OFFICIAL_CERTIFICATE_NO)
        self.assertEqual(t_res["classification"], CONFIRMED_NABL_SCOPE)
        self.assertEqual(t_res["entry"]["discipline"], "Thermal")

    # ─────────────────────────────────────────────────────────────────
    # Demand vs Timing Separation Regression Tests (Cases D, E, F)
    # ─────────────────────────────────────────────────────────────────

    def test_case_d_annual_periodic_calibration_alone_does_not_pass_timing(self):
        """Rule D: Annual/periodic calibration requirement alone does NOT pass timing."""
        generic_timings = [
            "Annual calibration budgeting cycle",
            "periodic calibration requirement",
            "ISO requirement calendar cycle",
            "regular budgeting cycle",
            "standard recurring calibration",
        ]
        for gt in generic_timings:
            ev = base_evidence(
                timing={
                    "buying_window": gt,
                    "is_buying_window_active": False,
                }
            )
            res = evaluate_opportunity_gates(ev, production=True)
            self.assertFalse(
                res["gates"]["timing"]["passed"],
                f"Expected generic timing '{gt}' to fail timing gate",
            )
            self.assertIn("establishes baseline demand but does not prove a current buying window", res["gates"]["timing"]["reason"])
            self.assertEqual(res["status"], BLOCKED)

    def test_case_e_current_commissioning_audit_procurement_can_pass_timing(self):
        """Rule E: Current commissioning/audit/procurement evidence CAN pass timing."""
        active_timing_cases = [
            {"buying_window": "active commissioning of new forging press line", "is_buying_window_active": True},
            {"buying_window": "upcoming IATF surveillance audit scheduled in 45 days", "is_buying_window_active": True},
            {"buying_window": "active procurement RFQ for annual master calibration", "is_buying_window_active": True},
            {"buying_window": "scheduled plant maintenance shutdown next month", "is_buying_window_active": True},
            {"buying_window": "vendor contract renewal window", "is_buying_window_active": True},
        ]
        for tc in active_timing_cases:
            ev = base_evidence(timing=tc)
            res = evaluate_opportunity_gates(ev, production=True)
            self.assertTrue(
                res["gates"]["timing"]["passed"],
                f"Expected active timing '{tc['buying_window']}' to pass timing gate",
            )
            self.assertIn("Current buying timing confirmed", res["gates"]["timing"]["reason"])

    def test_case_f_baseline_calibration_demand_remains_true_while_timing_is_fail(self):
        """Rule F: Baseline calibration demand can remain TRUE while timing is FAIL."""
        ev = base_evidence(
            calibration_demand={
                "verified": True,
                "demand_basis": "IATF 16949 / ISO 9001 mandatory periodic calibration for manufacturing assets",
            },
            timing={
                "buying_window": "Annual calibration budgeting cycle",
                "is_buying_window_active": False,
            },
        )
        res = evaluate_opportunity_gates(ev, production=True)

        # Baseline calibration demand must be TRUE
        self.assertTrue(res["gates"]["calibration_demand"]["passed"])
        self.assertTrue(res["gates"]["calibration_demand"]["baseline_demand"])
        self.assertIn("Baseline calibration demand confirmed", res["gates"]["calibration_demand"]["reason"])

        # Current buying timing must be FALSE / HOLD
        self.assertFalse(res["gates"]["timing"]["passed"])
        self.assertIn("establishes baseline demand but does not prove a current buying window", res["gates"]["timing"]["reason"])

        # Overall gate status must be BLOCKED because timing failed
        self.assertFalse(res["ready_for_email"])
        self.assertEqual(res["status"], BLOCKED)

    # ─────────────────────────────────────────────────────────────────
    # Existing Core Evidence Gate Regression Tests
    # ─────────────────────────────────────────────────────────────────

    def test_2_year_old_announcement_fails(self):
        """2-year-old announcement with no newer evidence -> trigger_current FAIL."""
        ev = base_evidence(
            trigger_current={
                "trigger_date": "2024-05-10",
                "ongoing_activity_evidence": "",
                "trigger_facility_confidence": "DIRECT",
            }
        )
        res = evaluate_opportunity_gates(ev, production=True)
        self.assertFalse(res["gates"]["trigger_current"]["passed"])
        self.assertEqual(res["gates"]["trigger_current"]["recency_status"], "STALE")
        self.assertEqual(res["status"], BLOCKED)

    def test_old_announcement_with_commissioning_passes(self):
        """Old announcement + current commissioning evidence -> trigger_current PASS."""
        ev = base_evidence(
            trigger_current={
                "trigger_date": "2024-01-15",
                "future_commissioning": True,
                "ongoing_activity_evidence": "Phase 2 commissioning scheduled for Q4 2026",
                "trigger_facility_confidence": "DIRECT",
            }
        )
        res = evaluate_opportunity_gates(ev, production=True)
        self.assertTrue(res["gates"]["trigger_current"]["passed"])
        self.assertIn("multi-year execution is confirmed active", res["gates"]["trigger_current"]["reason"])

    def test_company_trigger_unrelated_facility_fails(self):
        """Company-level trigger + unrelated facility address -> trigger_facility_alignment FAIL/HOLD."""
        ev = base_evidence(
            trigger_current={
                "trigger_date": "2026-08-01",
                "trigger_facility_confidence": "WEAK",
                "trigger_facility_evidence": "Company-wide article without facility attribution",
            },
            exact_facility={
                "verified": True,
                "address": "Random Facility, Chennai",
                "trigger_facility_confidence": "WEAK",
            },
        )
        res = evaluate_opportunity_gates(ev, production=True)
        self.assertFalse(res["gates"]["trigger_current"]["passed"])
        self.assertFalse(res["gates"]["exact_facility"]["passed"])
        self.assertEqual(res["status"], BLOCKED)

    def test_company_wide_person_without_facility_fails(self):
        """Company-wide person with no facility evidence -> facility ownership must not be invented."""
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

    def test_confirmed_group_functional_owner_passes(self):
        """Confirmed group functional owner -> may pass if evidence clearly establishes responsibility."""
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

    def test_unsupported_oorja_scope_fails(self):
        """Unsupported Oorja technical scope -> must not be presented as confirmed capability."""
        ev = base_evidence(
            technical_capability={
                "scope_items": [
                    "Optical Emission Spectrometer (OES)",
                    "Ultrasonic Flaw Detector",
                    "Metallurgical Chemical Assay",
                ],
                "certificate_no": OORJA_OFFICIAL_CERTIFICATE_NO,
            }
        )
        res = evaluate_opportunity_gates(ev, production=True)
        self.assertFalse(res["gates"]["technical_capability"]["passed"])
        self.assertIn("out-of-scope", res["gates"]["technical_capability"]["reason"])
        self.assertEqual(res["status"], BLOCKED)

    # ─────────────────────────────────────────────────────────────────
    # Trigger Recency & Timing Semantics Regression Tests
    # ─────────────────────────────────────────────────────────────────

    def test_recency_364_days_is_recent(self):
        """364 days old trigger is classified as RECENT."""
        ev = base_evidence(
            trigger_current={
                "recency_days": 364,
                "ongoing_activity_evidence": "",
                "trigger_facility_confidence": "DIRECT",
            }
        )
        res = evaluate_opportunity_gates(ev, production=True)
        self.assertEqual(res["gates"]["trigger_current"]["recency_status"], "RECENT")
        self.assertFalse(res["gates"]["trigger_current"]["passed"])
        self.assertEqual(res["status"], BLOCKED)

    def test_recency_366_days_is_stale(self):
        """366 days old trigger is classified as STALE."""
        ev = base_evidence(
            trigger_current={
                "recency_days": 366,
                "ongoing_activity_evidence": "",
                "trigger_facility_confidence": "DIRECT",
            }
        )
        res = evaluate_opportunity_gates(ev, production=True)
        self.assertEqual(res["gates"]["trigger_current"]["recency_status"], "STALE")
        self.assertFalse(res["gates"]["trigger_current"]["passed"])
        self.assertEqual(res["status"], BLOCKED)

    def test_stale_without_ongoing_fails(self):
        """>365 days trigger without ongoing evidence fails timing."""
        ev = base_evidence(
            trigger_current={
                "recency_days": 400,
                "ongoing_activity_evidence": "",
                "trigger_facility_confidence": "DIRECT",
            }
        )
        res = evaluate_opportunity_gates(ev, production=True)
        self.assertFalse(res["gates"]["trigger_current"]["passed"])
        self.assertIn("STALE", res["gates"]["trigger_current"]["reason"])
        self.assertEqual(res["status"], BLOCKED)

    def test_stale_with_independent_ongoing_passes(self):
        """>365 days trigger with independent ongoing commissioning evidence passes timing."""
        ev = base_evidence(
            trigger_current={
                "recency_days": 450,
                "ongoing_activity_evidence": "Phase 2 commercial commissioning underway in FY26",
                "ongoing_source": "https://www.autocarpro.in/news/phase2-update",
                "ongoing_date": "2026-08-15",
                "trigger_facility_confidence": "DIRECT",
            }
        )
        res = evaluate_opportunity_gates(ev, production=True)
        self.assertTrue(res["gates"]["trigger_current"]["passed"])
        self.assertEqual(res["gates"]["trigger_current"]["recency_status"], "STALE")
        self.assertIn("multi-year execution is confirmed active", res["gates"]["trigger_current"]["reason"])
        self.assertTrue(res["ready_for_email"])

    def test_recent_181_to_365_without_ongoing_fails(self):
        """181-365 days trigger without ongoing evidence fails timing."""
        ev = base_evidence(
            trigger_current={
                "recency_days": 250,
                "ongoing_activity_evidence": "",
                "trigger_facility_confidence": "DIRECT",
            }
        )
        res = evaluate_opportunity_gates(ev, production=True)
        self.assertFalse(res["gates"]["trigger_current"]["passed"])
        self.assertEqual(res["gates"]["trigger_current"]["recency_status"], "RECENT")
        self.assertIn("lacks required evidence of ongoing activity", res["gates"]["trigger_current"]["reason"])
        self.assertEqual(res["status"], BLOCKED)

    def test_recent_181_to_365_with_ongoing_passes(self):
        """181-365 days trigger with independent ongoing evidence passes timing."""
        ev = base_evidence(
            trigger_current={
                "recency_days": 250,
                "ongoing_activity_evidence": "Active hiring and equipment installation for new line",
                "ongoing_source": "https://company.com/careers/quality-hiring",
                "ongoing_date": "2026-07-20",
                "trigger_facility_confidence": "DIRECT",
            }
        )
        res = evaluate_opportunity_gates(ev, production=True)
        self.assertTrue(res["gates"]["trigger_current"]["passed"])
        self.assertEqual(res["gates"]["trigger_current"]["recency_status"], "RECENT")
        self.assertIn("verified ongoing activity", res["gates"]["trigger_current"]["reason"])
        self.assertTrue(res["ready_for_email"])

    def test_prohibited_ongoing_patterns_fail(self):
        """Prohibited patterns like historical article, old inauguration, generic company existence must FAIL."""
        for prohibited in [
            "historical article about past capex",
            "old inauguration ceremony archive",
            "old plant launch in 2022",
            "generic company existence overview",
        ]:
            ev = base_evidence(
                trigger_current={
                    "recency_days": 250,
                    "ongoing_activity_evidence": prohibited,
                    "trigger_facility_confidence": "DIRECT",
                }
            )
            res = evaluate_opportunity_gates(ev, production=True)
            self.assertFalse(res["gates"]["trigger_current"]["passed"], f"Failed to reject prohibited ongoing pattern: {prohibited}")
            self.assertEqual(res["status"], BLOCKED)


if __name__ == "__main__":
    unittest.main()

