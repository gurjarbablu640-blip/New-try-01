"""Test Suite for Qualification State Separation & Integrity.

Validates:
1. 17 explicit lifecycle states exist and have distinct semantics.
2. APOLLO_ELIGIBLE != READY_FOR_PRODUCTION_SEND.
3. Inferred email with mailbox_verified=False can stage TEST preview (STAGED_TEST) but CANNOT be READY_FOR_PRODUCTION_SEND.
4. AMBIGUOUS_COMPANY maps to HOLD.
5. OTHER_COMPANY and FORMER_COMPANY map to REJECTED.
6. Non-human names map to REJECTED.
"""
import unittest
from services.qualification_state_machine import (
    QualificationState,
    determine_qualification_state,
    validate_transition,
)


class TestQualificationStateIntegrity(unittest.TestCase):

    def test_all_17_lifecycle_states_exist(self):
        expected_states = {
            "DISCOVERED", "RESEARCHING", "OPPORTUNITY_VERIFIED",
            "PERSON_CANDIDATE_FOUND", "PERSON_VERIFIED", "CONTACT_MISSING",
            "APOLLO_ELIGIBLE", "CONTACT_FOUND_UNVERIFIED", "CONTACT_VERIFIED",
            "READY_FOR_EMAIL", "STAGED_TEST", "READY_FOR_PRODUCTION_SEND",
            "SENT", "REPLIED", "ENQUIRY", "HOLD", "REJECTED",
        }
        actual_states = {s.value for s in QualificationState}
        self.assertEqual(expected_states, actual_states)

    def test_apollo_eligible_cannot_transition_to_production_send(self):
        # Invariant 1: APOLLO_ELIGIBLE cannot become READY_FOR_PRODUCTION_SEND directly
        valid, reason = validate_transition(
            QualificationState.APOLLO_ELIGIBLE,
            QualificationState.READY_FOR_PRODUCTION_SEND,
        )
        self.assertFalse(valid)
        self.assertIn("Illegal state transition from APOLLO_ELIGIBLE to READY_FOR_PRODUCTION_SEND", reason)

    def test_inferred_email_cannot_be_ready_for_production_send(self):
        # Invariant 2: Inferred email with mailbox_verified=False
        evidence = {
            "trigger_current": {"verified": True, "recency_status": "CURRENT"},
            "exact_facility": {"verified": True, "address": "Oragadam, Tamil Nadu", "linkage_strength": "DIRECT"},
            "correct_person": {
                "name": "Abhinav Tiwaari",
                "employment_verified": True,
                "duties_verified": True,
                "company_evidence_status": "EXACT_CURRENT_COMPANY",
            },
            "technical_capability": {"status": "CONFIRMED_NABL_SCOPE"},
            "reachable_email": {
                "email": "abhinav.tiwaari@dixoninfo.com",
                "status": "INFERRED",
                "mailbox_verified": False,
                "contact_confidence": "PROBABLE",
            },
        }

        res = determine_qualification_state(evidence, production_mode=True, outbound_test_mode=False)
        self.assertEqual(res.state, QualificationState.CONTACT_FOUND_UNVERIFIED)
        self.assertTrue(res.can_stage_test)
        self.assertFalse(res.can_send_production)
        self.assertTrue(res.requires_apollo)

    def test_verified_mailbox_in_production_mode_becomes_ready_for_production_send(self):
        evidence = {
            "trigger_current": {"verified": True, "recency_status": "CURRENT"},
            "exact_facility": {"verified": True, "address": "Sanand, Gujarat", "linkage_strength": "DIRECT"},
            "correct_person": {
                "name": "Rajesh Verma",
                "employment_verified": True,
                "duties_verified": True,
                "company_evidence_status": "EXACT_CURRENT_COMPANY",
            },
            "technical_capability": {"status": "CONFIRMED_NABL_SCOPE"},
            "reachable_email": {
                "email": "rajesh.verma@tatamotors.com",
                "status": "VERIFIED",
                "mailbox_verified": True,
                "contact_confidence": "HIGH",
            },
        }

        # Under test mode, stages test preview
        res_test = determine_qualification_state(evidence, production_mode=False, outbound_test_mode=True)
        self.assertEqual(res_test.state, QualificationState.STAGED_TEST)
        self.assertTrue(res_test.can_stage_test)
        self.assertFalse(res_test.can_send_production)

        # Under explicit production mode with test mode disabled, becomes READY_FOR_PRODUCTION_SEND
        res_prod = determine_qualification_state(evidence, production_mode=True, outbound_test_mode=False)
        self.assertEqual(res_prod.state, QualificationState.READY_FOR_PRODUCTION_SEND)
        self.assertTrue(res_prod.can_send_production)

    def test_ambiguous_company_maps_to_hold(self):
        evidence = {
            "trigger_current": {"verified": True, "recency_status": "CURRENT"},
            "exact_facility": {"verified": True, "address": "Dahej, Gujarat", "linkage_strength": "DIRECT"},
            "correct_person": {
                "name": "Sunil Mehta",
                "employment_verified": False,
                "company_evidence_status": "AMBIGUOUS_COMPANY",
            },
        }
        res = determine_qualification_state(evidence)
        self.assertEqual(res.state, QualificationState.HOLD)
        self.assertTrue(res.is_hold)
        self.assertFalse(res.can_stage_test)
        self.assertFalse(res.can_send_production)

    def test_other_and_former_company_maps_to_rejected(self):
        for status in ("OTHER_COMPANY", "FORMER_COMPANY"):
            evidence = {
                "trigger_current": {"verified": True, "recency_status": "CURRENT"},
                "exact_facility": {"verified": True, "address": "Noida, UP"},
                "correct_person": {
                    "name": "Rakesh Sharma",
                    "employment_verified": False,
                    "company_evidence_status": status,
                },
            }
            res = determine_qualification_state(evidence)
            self.assertEqual(res.state, QualificationState.REJECTED)
            self.assertTrue(res.is_rejected)
            self.assertFalse(res.can_stage_test)

    def test_non_human_name_maps_to_rejected(self):
        evidence = {
            "trigger_current": {"verified": True},
            "exact_facility": {"verified": True, "address": "Pune, MH"},
            "correct_person": {
                "name": "Head General Manager",
                "employment_verified": True,
            },
        }
        res = determine_qualification_state(evidence)
        self.assertEqual(res.state, QualificationState.REJECTED)
        self.assertTrue(res.is_rejected)


if __name__ == "__main__":
    unittest.main()
