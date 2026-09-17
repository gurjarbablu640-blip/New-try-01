"""Comprehensive Integration Tests for Phase 2.1 Funnel Recovery.

Validates:
1. ContactWaterfallService is the sole authoritative waterfall engine.
2. Candidate fallback cascade: #1 failure → #2 → #3 → max 3 hold.
3. Stop conditions: verified stops, extrapolated/MX-only continues.
4. Dedup protection: same candidate not enriched twice.
5. PersonEnrichmentEligibilityGate integration:
   - score 84 with strong authority reaches enrichment in grace window
   - score 84 with weak authority rejected
6. SalesPersonalizationV2Engine LLM-first architecture:
   - DeepSeek primary writer
   - Gemini fallback writer
   - Both failing → safe GENERATION_FAILED hold (no fake deterministic email)
   - Deterministic claim guard runs after LLM (unsupported claims trigger CLAIM_VIOLATION)
   - Exact sales signature format
"""
import unittest
from unittest.mock import MagicMock, patch

from services.contact_waterfall_service import (
    ContactWaterfallService,
    EmailVerificationLevel,
    classify_email_verification_level,
    is_send_ready_email,
)
from services.person_enrichment_eligibility_gate import (
    PersonEnrichmentEligibilityGate,
    APOLLO_AUTHORITY_CLASSES,
)
from services.sales_personalization_v2 import (
    SalesPersonalizationV2Engine,
    classify_claim,
    SALES_SIGNATURE,
)


class TestContactWaterfallIntegrationPhase21(unittest.TestCase):

    def setUp(self):
        self.gate = PersonEnrichmentEligibilityGate()
        self.facility_info = {"facility_verified": True, "linkage_confidence": "DIRECT"}
        self.trigger_info = {"valid_trigger": True}

    def _make_candidate(self, name, score=0.90, authority="METROLOGY_OWNER", emp="VERIFIED", fac_rel="DIRECT"):
        return {
            "name": name,
            "candidate_name": name,
            "candidate_title": "Metrology Lead",
            "composite_score": score,
            "authority_class": authority,
            "current_employment": emp,
            "current_employment_verified": emp == "VERIFIED",
            "facility_relationship": fac_rel,
        }

    def test_waterfall_candidate1_verified_stops_cascade(self):
        """Verified email on candidate #1 immediately stops further provider calls."""
        cand1 = self._make_candidate("Cand 1")
        cand2 = self._make_candidate("Cand 2")
        enrich_fn = MagicMock(return_value={"email": "cand1@example.com", "email_status": "verified"})

        service = ContactWaterfallService(eligibility_gate=self.gate, enrich_fn=enrich_fn, max_candidates=3)
        result = service.run([cand1, cand2], self.facility_info, self.trigger_info, opportunity_icp_score=90.0)

        self.assertEqual(result.status, "CONTACT_FOUND")
        self.assertEqual(result.email, "cand1@example.com")
        self.assertEqual(result.email_verification_level, EmailVerificationLevel.VERIFIED_PROVIDER)
        self.assertTrue(result.send_ready)
        self.assertEqual(enrich_fn.call_count, 1)

    def test_waterfall_candidate1_extrapolated_continues_to_candidate2(self):
        """Extrapolated email on candidate #1 continues to candidate #2."""
        cand1 = self._make_candidate("Cand 1")
        cand2 = self._make_candidate("Cand 2")

        def side_effect(c):
            if c["name"] == "Cand 1":
                return {"email": "cand1@domain.com", "email_status": "extrapolated"}
            return {"email": "cand2@domain.com", "email_status": "verified"}

        enrich_fn = MagicMock(side_effect=side_effect)
        service = ContactWaterfallService(eligibility_gate=self.gate, enrich_fn=enrich_fn, max_candidates=3)
        result = service.run([cand1, cand2], self.facility_info, self.trigger_info, opportunity_icp_score=90.0)

        self.assertEqual(result.status, "CONTACT_FOUND")
        self.assertEqual(result.email, "cand2@domain.com")
        self.assertEqual(result.candidate_name, "Cand 2")
        self.assertEqual(enrich_fn.call_count, 2)

    def test_waterfall_mx_only_continues(self):
        """Domain existence / pattern only does not upgrade to send ready; waterfall continues."""
        cand1 = self._make_candidate("Cand 1")
        cand2 = self._make_candidate("Cand 2")

        def side_effect(c):
            if c["name"] == "Cand 1":
                return {"email": "first.last@domain.com", "email_status": None}  # DOMAIN_VALID_PATTERN_ONLY
            return {"email": "verified.user@domain.com", "email_status": "verified"}

        enrich_fn = MagicMock(side_effect=side_effect)
        service = ContactWaterfallService(eligibility_gate=self.gate, enrich_fn=enrich_fn, max_candidates=3)
        result = service.run([cand1, cand2], self.facility_info, self.trigger_info, opportunity_icp_score=90.0)

        self.assertEqual(result.status, "CONTACT_FOUND")
        self.assertEqual(result.candidate_name, "Cand 2")
        self.assertEqual(enrich_fn.call_count, 2)

    def test_candidate3_failure_holds(self):
        """All 3 candidates failing to yield verified email produces HOLD_CONTACT_NOT_FOUND."""
        cands = [self._make_candidate(f"Cand {i}") for i in range(1, 5)]
        enrich_fn = MagicMock(return_value={"email": None})

        service = ContactWaterfallService(eligibility_gate=self.gate, enrich_fn=enrich_fn, max_candidates=3)
        result = service.run(cands, self.facility_info, self.trigger_info, opportunity_icp_score=90.0)

        self.assertEqual(result.status, "HOLD_CONTACT_NOT_FOUND")
        self.assertFalse(result.send_ready)
        self.assertEqual(enrich_fn.call_count, 3)

    def test_max_3_candidates_strictly_enforced(self):
        """Even if 10 candidates provided, max 3 are enriched."""
        cands = [self._make_candidate(f"Cand {i}") for i in range(1, 11)]
        enrich_fn = MagicMock(return_value={"email": None})

        service = ContactWaterfallService(eligibility_gate=self.gate, enrich_fn=enrich_fn, max_candidates=10)
        result = service.run(cands, self.facility_info, self.trigger_info, opportunity_icp_score=90.0)

        self.assertEqual(enrich_fn.call_count, 3)

    def test_provider_dedup_telemetry_tracked(self):
        """Dedup skip or reused existing result is properly tracked in telemetry."""
        cand = self._make_candidate("Cand 1")
        enrich_fn = MagicMock(return_value={"status": "SKIPPED_DEDUPLICATED", "call_type": "DEDUP_SKIPPED", "email": None})

        service = ContactWaterfallService(eligibility_gate=self.gate, enrich_fn=enrich_fn, max_candidates=3)
        result = service.run([cand], self.facility_info, self.trigger_info, opportunity_icp_score=90.0)

        self.assertEqual(result.dedup_skips, 1)
        self.assertEqual(result.new_apollo_calls, 0)

    def test_generic_email_rejected_as_non_send_ready(self):
        """Generic email addresses (info@, sales@, etc.) cannot be verified personal emails."""
        self.assertFalse(is_send_ready_email("info@company.com", EmailVerificationLevel.VERIFIED_PROVIDER))
        self.assertFalse(is_send_ready_email("sales@company.com", EmailVerificationLevel.VERIFIED_PUBLIC_SOURCE))
        self.assertEqual(classify_email_verification_level("info@company.com", "verified"), EmailVerificationLevel.DOMAIN_VALID_PATTERN_ONLY)


class TestPersonEnrichmentGateGraceWindow(unittest.TestCase):

    def setUp(self):
        self.gate = PersonEnrichmentEligibilityGate()
        self.fac_info = {"facility_verified": True, "linkage_confidence": "DIRECT"}
        self.trig_info = {"valid_trigger": True}

    def test_score_84_strong_authority_reaches_enrichment(self):
        """Score 0.84 with strong authority (e.g. Aarti/TASL) passes in grace window."""
        cand = {
            "composite_score": 0.84,
            "authority_class": "DIRECT_CALIBRATION_OWNER",
            "current_employment": "VERIFIED",
            "facility_relationship": "DIRECT",
        }
        dec = self.gate.evaluate(cand, self.fac_info, self.trig_info, opportunity_icp_score=90.0)
        self.assertTrue(dec.enrich_contact)
        self.assertIn("borderline_score_grace_window", dec.risk_flags)

    def test_score_84_weak_authority_rejected(self):
        """Score 0.84 with weak/unrecognized authority does not pass."""
        cand = {
            "composite_score": 0.84,
            "authority_class": "COMMERCIAL_OPS",
            "current_employment": "VERIFIED",
            "facility_relationship": "DIRECT",
        }
        dec = self.gate.evaluate(cand, self.fac_info, self.trig_info, opportunity_icp_score=90.0)
        self.assertFalse(dec.enrich_contact)


class TestPersonalizationV2LLMFirst(unittest.TestCase):

    def setUp(self):
        self.base_record = {
            "person": "Anil Sharma",
            "first_name": "Anil",
            "company": "Tata Advanced Systems",
            "facility": "Vadodara Aerospace Facility",
            "designation": "Quality Control Manager",
            "trigger": "assembly line setup for C295 transport aircraft",
            "trigger_date": "2026-03",
            "persona": "STRONG_PLANT_QUALITY_OWNER",
            "icp_score": 92.0,
            "industry": "aerospace",
        }

    def test_deepseek_primary_writer_used(self):
        """DeepSeek writes the normal V2 outreach body when available."""
        mock_deepseek = MagicMock()
        mock_deepseek.is_available.return_value = True
        mock_deepseek.complete.return_value = MagicMock(
            content='{"subject": "NABL Calibration Support — Vadodara Facility", "body": "Dear Anil,\\n\\nI noticed the assembly line setup for C295 transport aircraft at your Vadodara Aerospace Facility.\\n\\nPlant quality depends on measurement traceability being audit-ready. We deliver NABL-accredited calibration under ISO/IEC 17025:2017 to keep your quality audit trail intact.\\n\\nWe support dimensional, electrical, and pressure calibration subject to instrument scope and range feasibility under NABL certificate CC-3963.\\n\\nIf calibration is currently being planned for the new facility, I would welcome a brief exchange at your convenience."}'
        )

        engine = SalesPersonalizationV2Engine(deepseek_provider=mock_deepseek)
        result = engine.generate_outreach(self.base_record)

        self.assertEqual(result.status, "VALIDATED")
        self.assertEqual(result.llm_provider_used, "DEEPSEEK")
        self.assertIn("Best regards,\nBablu Gurjar", result.body)
        mock_deepseek.complete.assert_called_once()

    def test_gemini_fallback_writer_used_when_deepseek_fails(self):
        """Gemini is invoked when DeepSeek fails."""
        mock_deepseek = MagicMock()
        mock_deepseek.is_available.return_value = True
        mock_deepseek.complete.side_effect = RuntimeError("DeepSeek connection timed out")

        mock_gemini = MagicMock()
        mock_gemini.is_available.return_value = True
        mock_gemini.complete.return_value = MagicMock(
            content='{"subject": "NABL Calibration Support — Vadodara Aerospace Facility", "body": "Dear Anil,\\n\\nI noted the assembly line setup for C295 transport aircraft at your Vadodara Aerospace Facility.\\n\\nPlant quality depends on measurement traceability being audit-ready. We deliver NABL-accredited calibration under ISO/IEC 17025:2017 to keep your quality audit trail intact.\\n\\nWe provide dimensional and pressure calibration under Certificate CC-3963, strictly subject to instrument scope and range feasibility.\\n\\nIf your team is currently scheduling calibration or audit preparation at Vadodara, I would welcome a brief exchange."}'
        )

        engine = SalesPersonalizationV2Engine(deepseek_provider=mock_deepseek, gemini_provider=mock_gemini)
        result = engine.generate_outreach(self.base_record)

        self.assertEqual(result.status, "VALIDATED")
        self.assertEqual(result.llm_provider_used, "GEMINI")
        mock_gemini.complete.assert_called_once()

    def test_both_llms_failing_produces_safe_generation_failed_hold(self):
        """If both DeepSeek and Gemini fail, engine returns GENERATION_FAILED (never silent fake email)."""
        mock_deepseek = MagicMock()
        mock_deepseek.is_available.return_value = True
        mock_deepseek.complete.side_effect = RuntimeError("DeepSeek down")

        mock_gemini = MagicMock()
        mock_gemini.is_available.return_value = True
        mock_gemini.complete.side_effect = RuntimeError("Gemini down")

        engine = SalesPersonalizationV2Engine(deepseek_provider=mock_deepseek, gemini_provider=mock_gemini)
        result = engine.generate_outreach(self.base_record)

        self.assertEqual(result.status, "GENERATION_FAILED")
        self.assertFalse(result.body)
        self.assertTrue(len(result.violations) > 0)

    def test_claim_guard_detects_unsupported_person_responsibility(self):
        """Attributing direct calibration management responsibility triggers CLAIM_VIOLATION."""
        mock_deepseek = MagicMock()
        mock_deepseek.is_available.return_value = True
        mock_deepseek.complete.return_value = MagicMock(
            content='{"subject": "Calibration", "body": "Dear Anil,\\n\\nSince you manage calibration at the Vadodara facility, we can calibrate your equipment."}'
        )

        engine = SalesPersonalizationV2Engine(deepseek_provider=mock_deepseek)
        result = engine.generate_outreach(self.base_record)

        self.assertEqual(result.status, "CLAIM_VIOLATION")
        self.assertTrue(any("responsibility" in v.lower() for v in result.violations))

    def test_claim_guard_detects_unsupported_equipment_claim(self):
        """Asserting specific equipment needs calibration triggers CLAIM_VIOLATION."""
        mock_deepseek = MagicMock()
        mock_deepseek.is_available.return_value = True
        mock_deepseek.complete.return_value = MagicMock(
            content='{"subject": "Calibration", "body": "Dear Anil,\\n\\nYour NDT equipment requires immediate calibration for the new C295 line."}'
        )

        engine = SalesPersonalizationV2Engine(deepseek_provider=mock_deepseek)
        result = engine.generate_outreach(self.base_record)

        self.assertEqual(result.status, "CLAIM_VIOLATION")
        self.assertTrue(any("ndt" in v.lower() for v in result.violations))


class TestPersonalizationGroundingHardeningPhase21C(unittest.TestCase):
    """Rigorous Phase 2.1C grounding hardening verification test suite."""

    def setUp(self):
        self.harman_record = {
            "company": "HARMAN",
            "facility": "HARMAN Pune Automotive Manufacturing Plant",
            "person": "Rohit Giri",
            "first_name": "Rohit",
            "designation": "Business Unit Head",
            "trigger": "HARMAN Invests Rs 345 Crore to Expand Pune Automotive Manufacturing Plant",
            "trigger_headline": "HARMAN Invests Rs 345 Crore to Expand Pune Automotive Manufacturing Plant",
            "trigger_snippet": "Rs 345 crores new investment to expand Pune automotive manufacturing plant, boosting capacity by 50%",
            "persona": "STRONG_PLANT_QUALITY_OWNER",
            "industry": "automotive",
        }
        self.aarti_record = {
            "company": "Aarti Pharmalabs",
            "facility": "MIDC Tarapur Manufacturing Block",
            "person": "Jayendra Chaphekar",
            "first_name": "Jayendra",
            "designation": "Quality Assurance Manager",
            "trigger": "Aarti Pharmalabs inaugurates new manufacturing block at MIDC Tarapur",
            "trigger_headline": "Aarti Pharmalabs inaugurates new manufacturing block at MIDC Tarapur",
            "persona": "STRONG_PLANT_QUALITY_OWNER",
            "industry": "pharmaceutical",
        }

    def test_existing_plant_expansion_cannot_claim_new_facility(self):
        """HARMAN Pune expansion cannot be called 'new facility' or 'new plant'."""
        mock_deepseek = MagicMock()
        mock_deepseek.is_available.return_value = True
        # LLM erroneously claims 'new facility' for an existing expansion
        mock_deepseek.complete.return_value = MagicMock(
            content='{"subject": "NABL Calibration Support — Pune Plant", "body": "Dear Rohit,\\n\\nI noticed the recent expansion at the Pune plant.\\n\\nAs you set up production lines for your new facility, ensuring measurement traceability is critical.\\n\\nOorja is an ISO/IEC 17025:2017 NABL-accredited laboratory (CC-3963).\\n\\nIf useful, please share your instrument list."}'
        )

        engine = SalesPersonalizationV2Engine(deepseek_provider=mock_deepseek)
        result = engine.generate_outreach(self.harman_record)

        self.assertEqual(result.status, "CLAIM_VIOLATION")
        self.assertTrue(any("new facility" in v.lower() for v in result.violations))

    def test_new_facility_allowed_with_explicit_evidence(self):
        """When evidence explicitly proves a new facility, the phrasing is permitted."""
        mock_deepseek = MagicMock()
        mock_deepseek.is_available.return_value = True
        mock_deepseek.complete.return_value = MagicMock(
            content='{"subject": "NABL Calibration Support — Tarapur Facility", "body": "Dear Jayendra,\\n\\nI noticed the inauguration of your new manufacturing block at MIDC Tarapur.\\n\\nPlant quality depends on measurement traceability being audit-ready. Oorja is an ISO/IEC 17025:2017 NABL-accredited calibration laboratory (CC-3963), which may support documentation and traceability requirements where relevant.\\n\\nWe support thermal, pressure, and weighing calibration subject to scope and range feasibility.\\n\\nIf useful, you can share your instrument list to explore a practical calibration route."}'
        )

        engine = SalesPersonalizationV2Engine(deepseek_provider=mock_deepseek)
        result = engine.generate_outreach(self.aarti_record)

        self.assertEqual(result.status, "VALIDATED")
        self.assertEqual(result.event_status, "NEW_FACILITY")

    def test_detected_at_cannot_masquerade_as_event_date(self):
        """Database timestamps such as detected_at cannot be used as event dates."""
        from services.sales_personalization_v2 import resolve_event_date
        rec = {
            "trigger_date": "2026-09-17 08:09:26.151509",
            "date_field": "detected_at",
        }
        phrase, source = resolve_event_date(rec)
        self.assertEqual(source, "UNKNOWN")
        self.assertNotIn("08:09:26", phrase)

    def test_year_only_evidence_does_not_invent_month_day(self):
        """Year-only evidence does not invent month or day."""
        from services.sales_personalization_v2 import resolve_event_date
        rec = {"event_date": "2026"}
        phrase, source = resolve_event_date(rec)
        self.assertEqual(source, "YEAR_ONLY")
        self.assertEqual(phrase, "2026")
        self.assertNotIn("january", phrase.lower())

    def test_accreditation_compliance_guarantee_blocked(self):
        """Accreditation cannot be represented as guaranteeing customer compliance."""
        mock_deepseek = MagicMock()
        mock_deepseek.is_available.return_value = True
        mock_deepseek.complete.return_value = MagicMock(
            content='{"subject": "Calibration", "body": "Dear Rohit,\\n\\nOur NABL accreditation ensures compliance for all your audit requirements at the Pune plant."}'
        )

        engine = SalesPersonalizationV2Engine(deepseek_provider=mock_deepseek)
        result = engine.generate_outreach(self.harman_record)

        self.assertEqual(result.status, "CLAIM_VIOLATION")
        self.assertTrue(any("compliance" in v.lower() or "guarantee" in v.lower() for v in result.violations))

    def test_unsupported_person_ownership_and_team_claims_blocked(self):
        """Claims like 'your calibration team' or 'your torque-tool program' are blocked."""
        mock_deepseek = MagicMock()
        mock_deepseek.is_available.return_value = True
        mock_deepseek.complete.return_value = MagicMock(
            content='{"subject": "Calibration", "body": "Dear Rohit,\\n\\nWe can assist your calibration team with your torque-tool program at the Pune plant."}'
        )

        engine = SalesPersonalizationV2Engine(deepseek_provider=mock_deepseek)
        result = engine.generate_outreach(self.harman_record)

        self.assertEqual(result.status, "CLAIM_VIOLATION")
        self.assertTrue(any("team" in v.lower() or "program" in v.lower() for v in result.violations))

    def test_known_oorja_capability_allowlist_enforced(self):
        """Unapproved capabilities (NDT, CMM alignment, optical, avionics) trigger CLAIM_VIOLATION."""
        mock_deepseek = MagicMock()
        mock_deepseek.is_available.return_value = True
        mock_deepseek.complete.return_value = MagicMock(
            content='{"subject": "Calibration", "body": "Dear Rohit,\\n\\nWe provide CMM alignment and optical calibration for your plant expansion."}'
        )

        engine = SalesPersonalizationV2Engine(deepseek_provider=mock_deepseek)
        result = engine.generate_outreach(self.harman_record)

        self.assertEqual(result.status, "CLAIM_VIOLATION")
        self.assertTrue(any("unapproved" in v.lower() or "cmm" in v.lower() for v in result.violations))

    def test_exact_signature_preserved(self):
        """Exact sales signature must be cleanly appended to the body."""
        from services.sales_personalization_v2 import SALES_SIGNATURE
        mock_deepseek = MagicMock()
        mock_deepseek.is_available.return_value = True
        mock_deepseek.complete.return_value = MagicMock(
            content='{"subject": "NABL Calibration Support — Pune Plant", "body": "Dear Rohit,\\n\\nI noticed the expansion activity at the HARMAN Pune plant.\\n\\nPlant quality depends on measurement traceability being audit-ready. Oorja is an ISO/IEC 17025:2017 NABL-accredited calibration laboratory (CC-3963), which may support documentation and traceability requirements where relevant.\\n\\nWe support electrical, dimensional, and torque calibration subject to instrument scope and range feasibility.\\n\\nIf useful, you can share your instrument list and I can suggest a practical calibration route."}'
        )

        engine = SalesPersonalizationV2Engine(deepseek_provider=mock_deepseek)
        result = engine.generate_outreach(self.harman_record)

        self.assertEqual(result.status, "VALIDATED")
        self.assertTrue(result.body.endswith(SALES_SIGNATURE.strip()))
        self.assertIn("Bablu Gurjar\nSales | Oorja Technical Services Pvt. Ltd.", result.body)
        self.assertIn("Contact No.: 9201949296", result.body)
        self.assertIn("Email: Bablu@oorjatechnical.org", result.body)


if __name__ == "__main__":
    unittest.main()

