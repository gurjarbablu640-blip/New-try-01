"""Unit tests for PilotRampGatekeeper controlled batch scaling."""

import unittest

from services.pilot_ramp_gatekeeper import (
    PilotRampGatekeeper,
    RAMP_TIERS,
)


class TestPilotRampGatekeeper(unittest.TestCase):
    def setUp(self):
        self.gatekeeper = PilotRampGatekeeper()

    def _valid_candidate(self, email="anil.gupta@tatamotors.com", company="Tata Motors"):
        return {
            "READY_FOR_EMAIL": "YES",
            "COMPANY": company,
            "FACILITY": "Sanand Plant, Ahmedabad, Gujarat",
            "CITY": "Sanand",
            "STATE": "Gujarat",
            "CONTACT_NAME": "Anil Gupta",
            "FIRST_NAME": "Anil",
            "DESIGNATION": "Head of Quality & Metrology",
            "PERSONA": "Quality Head",
            "EMAIL": email,
            "PHONE": "+91-9876543210",
            "TRIGGER_EVENT": "EV Line Commissioning",
            "TRIGGER_DATE": "2026-08-20",
            "CALIBRATION_OPPORTUNITY": "Automated CMM & Pressure Sensor Calibration",
            "REASON_FOR_OUTREACH": "Facility expansion requires NABL traceable calibration",
            "LEAD_SCORE": 92.0,
            "functional_ownership_score": 85.0,
            "FACILITY_VERIFIED": True,
            "CONTACT_VERIFIED": True,
            "CONTACT_LOCATION": "Sanand Plant",
            "NOTES": "Real lead",
            "provenance": "REAL",
            "CC3963_MATCH": "CONFIRMED_NABL_SCOPE",
            "email_status": "PUBLICLY_FOUND",
            "evidence": {
                "exact_facility": True,
                "reachable_email": {"mailbox_verified": True},
            },
        }

    def test_advancement_when_all_conditions_pass(self):
        candidates = [self._valid_candidate()]
        eval_res = self.gatekeeper.evaluate_ramp_gate(current_tier=1, candidates=candidates)

        self.assertTrue(eval_res.passed)
        self.assertEqual(eval_res.current_tier, 1)
        self.assertEqual(eval_res.target_tier, 5)
        self.assertIn("ADVANCE_TO_TIER_5", eval_res.recommendation)
        self.assertEqual(len(eval_res.blocked_reasons), 0)

    def test_block_when_mock_data_detected(self):
        bad_lead = self._valid_candidate()
        bad_lead["provenance"] = "MOCK"
        eval_res = self.gatekeeper.evaluate_ramp_gate(current_tier=5, candidates=[bad_lead])

        self.assertFalse(eval_res.passed)
        self.assertIn("HOLD_AT_TIER_5", eval_res.recommendation)
        mock_check = next(c for c in eval_res.conditions if c.condition_id == "NO_MOCK_DATA_CONTAMINATION")
        self.assertFalse(mock_check.passed)

    def test_block_when_false_verified_contact_detected(self):
        bad_lead = self._valid_candidate()
        bad_lead["email_status"] = "INFERRED (VERIFIED)"
        bad_lead["evidence"]["reachable_email"]["mailbox_verified"] = False
        eval_res = self.gatekeeper.evaluate_ramp_gate(current_tier=10, candidates=[bad_lead])

        self.assertFalse(eval_res.passed)
        contact_check = next(c for c in eval_res.conditions if c.condition_id == "NO_FALSE_VERIFIED_CONTACTS")
        self.assertFalse(contact_check.passed)

    def test_block_when_facility_unconfirmed(self):
        bad_lead = self._valid_candidate()
        bad_lead["FACILITY"] = "Manesar (City unconfirmed)"
        eval_res = self.gatekeeper.evaluate_ramp_gate(current_tier=25, candidates=[bad_lead])

        self.assertFalse(eval_res.passed)
        fac_check = next(c for c in eval_res.conditions if c.condition_id == "FACILITY_EVIDENCE_STRONG")
        self.assertFalse(fac_check.passed)

    def test_block_when_unsupported_nabl_claims(self):
        bad_lead = self._valid_candidate()
        bad_lead["CC3963_MATCH"] = "NOT_IN_SCOPE_RADIATION_CALIBRATION"
        eval_res = self.gatekeeper.evaluate_ramp_gate(current_tier=50, candidates=[bad_lead])

        self.assertFalse(eval_res.passed)
        nabl_check = next(c for c in eval_res.conditions if c.condition_id == "NO_UNSUPPORTED_NABL_CLAIMS")
        self.assertFalse(nabl_check.passed)

    def test_block_when_duplicate_outreach_detected(self):
        lead1 = self._valid_candidate(email="dup@company.com", company="Bharat Forge")
        lead2 = self._valid_candidate(email="dup@company.com", company="Bharat Forge")
        eval_res = self.gatekeeper.evaluate_ramp_gate(current_tier=5, candidates=[lead1, lead2])

        self.assertFalse(eval_res.passed)
        dup_check = next(c for c in eval_res.conditions if c.condition_id == "NO_DUPLICATE_OUTREACH")
        self.assertFalse(dup_check.passed)

    def test_block_when_paid_llm_or_apollo_credit_violated(self):
        candidates = [self._valid_candidate()]
        # Unauthorized Apollo credit
        bad_env = {"apollo_credits_used": 5, "ALLOW_PAID_LLM": False, "LLM_COST_POLICY": "ZERO_COST_ONLY"}
        eval_res = self.gatekeeper.evaluate_ramp_gate(current_tier=10, candidates=candidates, runtime_env=bad_env)

        self.assertFalse(eval_res.passed)
        cost_check = next(c for c in eval_res.conditions if c.condition_id == "NO_ACCIDENTAL_PAID_CALLS")
        self.assertFalse(cost_check.passed)

    def test_max_tier_capacity_handling(self):
        candidates = [self._valid_candidate()]
        eval_res = self.gatekeeper.evaluate_ramp_gate(current_tier=150, candidates=candidates)

        self.assertTrue(eval_res.passed)
        self.assertIsNone(eval_res.target_tier)
        self.assertIn("MAX_CAPACITY_REACHED", eval_res.recommendation)


if __name__ == "__main__":
    unittest.main()
