import unittest

from services.opportunity_gates import BLOCKED, HOT, READY_FOR_EMAIL, evaluate_opportunity_gates


def evidence(**overrides):
    value = {
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
