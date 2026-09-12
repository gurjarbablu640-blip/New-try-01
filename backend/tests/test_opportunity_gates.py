import unittest

from services.opportunity_gates import (
    BLOCKED,
    HOT,
    HOLD_LOW_SCORE,
    P1_HOT,
    P2_STRONG,
    P3_QUALIFIED,
    READY_FOR_EMAIL,
    READY_FOR_CONTACT_ENRICHMENT,
    classify_icp_score,
    evaluate_apollo_credit_gate,
    evaluate_opportunity_gates,
)


def evidence(**overrides):
    value = {
        "trigger_current": {
            "verified": True,
            "trigger_date": "2025-08-01",
            "recency_days": 40,
            "trigger_facility_confidence": "DIRECT",
            "ongoing_activity_evidence": "Plant commissioning new manufacturing line",
        },
        "exact_facility": {
            "verified": True,
            "address": "MIDC Chakan, Pune, Maharashtra, India",
            "address_precision": "INDUSTRIAL_AREA",
            "trigger_facility_confidence": "DIRECT",
            "trigger_facility_evidence": "Company commissioning at MIDC Chakan",
        },
        "calibration_demand": True,
        "technical_capability": True,
        "timing": {
            "is_active_window": True,
            "timing_evidence": "Plant commissioning expansion at Chakan facility",
            "event_type": "commissioning",
            "trigger_date": "2025-08-01",
        },
        "correct_person": {
            "name": "Anil Patil",
            "employment_verified": True,
            "current_employment": "VERIFIED",
            "facility_verified": True,
            "duties_verified": True,
            "facility_classification": "FACILITY_OWNER",
            "authority_class": "FACILITY_OWNER",
            "person_confidence": "HIGH",
        },
        "reachable_email": {
            "address": "quality@example.test",
            "status": "verified",
            "mailbox_verified": True,
            "contact_confidence": "VERIFIED",
        },
        "score": 90,
        "source": "nabl",
    }
    value.update(overrides)
    return value


class OpportunityGateTests(unittest.TestCase):
    def test_all_gates_at_90_are_ready(self):
        result = evaluate_opportunity_gates(evidence())
        self.assertEqual(result["status"], READY_FOR_EMAIL)
        self.assertTrue(result["ready_for_email"])

    def test_95_is_hot(self):
        self.assertEqual(evaluate_opportunity_gates(evidence(score=95))["status"], HOT)

    def test_canonical_icp_bands(self):
        self.assertEqual(classify_icp_score(95), P1_HOT)
        self.assertEqual(classify_icp_score(90), P2_STRONG)
        self.assertEqual(classify_icp_score(85), P3_QUALIFIED)
        self.assertEqual(classify_icp_score(84.99), HOLD_LOW_SCORE)

    def test_p3_with_all_person_gates_is_ready(self):
        result = evaluate_opportunity_gates(evidence(score=85))
        self.assertEqual(result["icp_band"], P3_QUALIFIED)
        self.assertTrue(result["ready_for_email"])

    def test_p3_without_high_person_confidence_is_not_sendable(self):
        person = dict(evidence()["correct_person"])
        person["person_confidence"] = "MEDIUM"
        result = evaluate_opportunity_gates(evidence(score=85, correct_person=person))
        self.assertFalse(result["ready_for_email"])
        self.assertIn("HIGH is required", result["gates"]["correct_person"]["reason"])

    def test_p3_verified_person_is_eligible_for_contact_enrichment(self):
        enrichment_evidence = evidence(
            score=85,
            reachable_email={"address": "", "status": "not_found"},
        )
        result = evaluate_apollo_credit_gate(enrichment_evidence)
        self.assertTrue(result["passed"])
        self.assertEqual(result["status"], READY_FOR_CONTACT_ENRICHMENT)
        self.assertEqual(result["criteria"]["icp_score"]["band"], P3_QUALIFIED)

    def test_contact_enrichment_ready_is_not_email_ready(self):
        enrichment_evidence = evidence(
            reachable_email={"address": "", "status": "not_found"},
        )

        enrichment = evaluate_apollo_credit_gate(enrichment_evidence)
        outbound = evaluate_opportunity_gates(enrichment_evidence)

        self.assertEqual(enrichment["status"], READY_FOR_CONTACT_ENRICHMENT)
        self.assertFalse(outbound["ready_for_email"])

    def test_missing_gate_blocks(self):
        result = evaluate_opportunity_gates(evidence(timing=False))
        self.assertEqual(result["status"], BLOCKED)
        self.assertIn("timing", result["reason"])

    def test_mx_only_and_legacy_valid_do_not_pass(self):
        for email in (
            {"address": "a@example.test", "status": "mx_only"},
            {"address": "a@example.test", "status": "valid"},
            {"address": "a@example.test", "status": "verified", "mailbox_verified": True, "contact_confidence": "LOW"},
        ):
            result = evaluate_opportunity_gates(evidence(reachable_email=email))
            self.assertFalse(result["ready_for_email"])

    def test_person_requires_employment_facility_and_duties(self):
        result = evaluate_opportunity_gates(evidence(correct_person={"employment_verified": True, "facility_verified": True}))
        self.assertFalse(result["gates"]["correct_person"]["passed"])

    def test_synthetic_fixture_is_blocked_in_production(self):
        result = evaluate_opportunity_gates(evidence(synthetic=True))
        self.assertEqual(result["status"], BLOCKED)
        self.assertIn("Synthetic", result["reason"])

    def test_synthetic_fixture_can_be_used_by_unit_tests(self):
        result = evaluate_opportunity_gates(evidence(synthetic=True), production=False)
        self.assertEqual(result["status"], READY_FOR_EMAIL)


if __name__ == "__main__":
    unittest.main()
