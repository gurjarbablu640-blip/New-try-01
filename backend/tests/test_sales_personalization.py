"""Test Suite for Sales Personalization Pipeline.

Validates:
1. Scenario A: Plant Quality Head + new line
2. Scenario B: Plant Head + commissioning
3. Scenario C: Operations Head + expansion
4. Scenario D: Quality Head + audit/compliance context
5. Scenario E: Metrology owner + equipment list
6. Scenario F: Relevant adjacent senior person (referral route)
7. Scenario G: Weak / no trigger conservative handling
8. Scenario H: Wrong facility blocking (never send-ready)
9. DeepSeek primary routing
10. Gemini fallback when DeepSeek unavailable / fails validation
11. Claim safety: Satellite centers, SLAs, and commercial guarantees blocked
12. Unsupported numeric ROI blocked
13. Framework terms (SPIN, Challenger, MEDDPICC, etc.) prohibited in recipient copy
14. Follow-up sequence differentiation (Day 3, Day 5, Day 11, Day 21)
15. Rediff file handoff compatibility and ZERO SMTP invocation
"""
from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

from services.llm_provider import LLMResponse
from services.rediff_bridge import rediff_bridge
from services.rediff_sender_adapter import DRY_RUN_READY, RediffSenderAdapter
from services.sales_personalization import (
    STANDARD_SENDER_EMAIL,
    STANDARD_SENDER_NAME,
    STANDARD_SENDER_PHONE,
    STANDARD_SENDER_TITLE,
    STANDARD_SIGNATURE_TEXT,
    DeterministicPersonalizationGenerator,
    EmailQualityValidator,
    PersonalizationContext,
    SalesPersonalizationPipeline,
    build_personalization_context,
    sales_personalization_pipeline,
)


def _base_record(**kwargs) -> dict:
    rec = {
        "record_id": "synthetic-pers-001",
        "READY_FOR_EMAIL": "YES",
        "company": "Bharat Precision Forgings Ltd",
        "facility": "Plant V, Baliguma, Jamshedpur, Jharkhand",
        "city": "Jamshedpur",
        "state": "Jharkhand",
        "person": "Krishna Kumar Jha",
        "first_name": "Krishna",
        "designation": "Head of Quality & Metrology",
        "persona": "Quality Head",
        "email": "krishna.jha@bharatforgings.test",
        "phone": "+91-9835000000",
        "trigger": "Commercial commissioning of heavy forging press line",
        "trigger_date": "2026-08-20",
        "trigger_source": "Press Information Bureau & Plant Filing",
        "calibration_opportunity": "Dimensional CMM and furnace pyrometry calibration",
        "reasoning": "New line installation requires accredited baseline calibration before OEM audits",
        "icp_score": 95,
        "facility_verified": True,
        "contact_verified": True,
        "provenance": "SYNTHETIC",
        "evidence": {
            "trigger_current": {"verified": True},
            "exact_facility": {
                "verified": True,
                "address": "Plant V, Baliguma, Jamshedpur",
                "status": "VERIFIED_FACILITY",
            },
            "technical_capability": {"status": "IN_SCOPE"},
            "correct_person": {
                "name": "Krishna Kumar Jha",
                "employment_verified": True,
                "duties_verified": True,
                "company_evidence_status": "CURRENT_COMPANY",
            },
            "reachable_email": {
                "email": "krishna.jha@bharatforgings.test",
                "status": "VERIFIED",
                "mailbox_verified": True,
                "contact_confidence": "HIGH",
            },
        },
    }
    rec.update(kwargs)
    return rec


class TestSalesPersonalizationPipeline(unittest.TestCase):

    def setUp(self):
        self.validator = EmailQualityValidator()
        self.pipeline = sales_personalization_pipeline

    def test_scenario_a_plant_quality_head_new_line(self):
        """Scenario A: Plant Quality Head + new line."""
        record = _base_record(
            persona="Quality Head",
            designation="Plant Quality Head",
            trigger="New precision machining and press line commissioning",
        )
        result = self.pipeline.personalize_record(record, force_provider="DETERMINISTIC")

        self.assertEqual(result["status"], "VALIDATED")
        self.assertGreaterEqual(result["quality_score"], 80)
        body = result["body"]
        self.assertIn("Krishna", body)
        self.assertIn("Bharat Precision Forgings Ltd", body)
        self.assertIn("Plant V", body)
        self.assertIn("traceability", body.lower())
        self.assertIn("?", body)  # CTA present

        # Internal sales reasoning
        reasoning = result["sales_reasoning"]
        self.assertIn("pain_hypothesis", reasoning)
        self.assertIn("implication", reasoning)
        self.assertIn("value_hypothesis", reasoning)
        self.assertIn("roi_angle", reasoning)
        self.assertIn("meddpicc", reasoning)

    def test_scenario_b_plant_head_commissioning(self):
        """Scenario B: Plant Head + commissioning."""
        record = _base_record(
            person="Rameshwar Prasad",
            first_name="Rameshwar",
            designation="Executive Director & Plant Head",
            persona="Plant Head",
            trigger="Full facility ramp-up and machinery commissioning",
        )
        result = self.pipeline.personalize_record(record, force_provider="DETERMINISTIC")

        self.assertEqual(result["status"], "VALIDATED")
        body = result["body"]
        self.assertIn("Rameshwar", body)
        self.assertIn("production", body.lower())
        self.assertIn("on-site", body.lower())
        # Check referral ask is present for senior Plant Head
        self.assertTrue(
            any(w in body.lower() for w in ["point me", "right person", "another colleague", "colleague directly leads"])
        )

    def test_scenario_c_operations_head_expansion(self):
        """Scenario C: Operations Head + expansion."""
        record = _base_record(
            person="Vikas Sundaram",
            first_name="Vikas",
            designation="Vice President - Manufacturing Operations",
            persona="Operations Head",
            trigger="Phase II plant capacity expansion",
        )
        result = self.pipeline.personalize_record(record, force_provider="DETERMINISTIC")

        self.assertEqual(result["status"], "VALIDATED")
        body = result["body"]
        self.assertIn("Vikas", body)
        self.assertIn("production", body.lower())

    def test_scenario_d_quality_head_audit_compliance(self):
        """Scenario D: Quality Head + audit/compliance context."""
        record = _base_record(
            person="Dr. Sunita Rao",
            first_name="Sunita",
            designation="Chief Quality Officer & NABL In-charge",
            persona="Quality Head",
            trigger="Upcoming annual IATF and customer surveillance audit",
        )
        result = self.pipeline.personalize_record(record, force_provider="DETERMINISTIC")

        self.assertEqual(result["status"], "VALIDATED")
        reasoning = result["sales_reasoning"]
        self.assertIn("audit", reasoning["roi_angle"].lower())
        self.assertIn("IATF", reasoning["compliance_angle"])

    def test_scenario_e_metrology_owner_equipment_list(self):
        """Scenario E: Metrology owner + equipment list."""
        record = _base_record(
            person="Anil Deshmukh",
            first_name="Anil",
            designation="Senior Manager - Metrology & Standards Lab",
            persona="Metrology Head",
            calibration_opportunity="Coordinate Measuring Machines and Vernier/Micrometer masters",
        )
        result = self.pipeline.personalize_record(record, force_provider="DETERMINISTIC")

        self.assertEqual(result["status"], "VALIDATED")
        body = result["body"]
        self.assertIn("Anil", body)
        self.assertIn("metrology", body.lower())

    def test_scenario_f_adjacent_senior_referral(self):
        """Scenario F: Relevant adjacent senior person where referral is required."""
        record = _base_record(
            person="Pooja Kulkarni",
            first_name="Pooja",
            designation="Head of Strategic Procurement & Vendor Sourcing",
            persona="Procurement",
        )
        result = self.pipeline.personalize_record(record, force_provider="DETERMINISTIC")

        self.assertEqual(result["status"], "VALIDATED")
        body = result["body"]
        self.assertTrue(
            any(w in body.lower() for w in ["point me", "right person", "another colleague", "colleague directly leads"])
        )
        self.assertTrue(result["sales_reasoning"]["referral_needed"])

    def test_scenario_g_weak_trigger_conservative_language(self):
        """Scenario G: Weak/no trigger uses cautious, consultative language."""
        record = _base_record(
            trigger="routine plant maintenance",
            reasoning="Regular scheduled calibration cycle",
        )
        result = self.pipeline.personalize_record(record, force_provider="DETERMINISTIC")

        self.assertEqual(result["status"], "VALIDATED")
        body = result["body"]
        # Must not accuse prospect of failure
        self.assertNotIn("suffering from", body.lower())
        self.assertNotIn("struggling with", body.lower())

    def test_scenario_h_wrong_facility_blocked(self):
        """Scenario H: Wrong facility must NEVER become send-ready."""
        record = _base_record()
        record["evidence"]["exact_facility"]["status"] = "WRONG_FACILITY"

        result = self.pipeline.personalize_record(record)
        self.assertEqual(result["status"], "DISQUALIFIED_WRONG_FACILITY")
        self.assertEqual(result["quality_score"], 0)
        self.assertEqual(result["llm_provider_used"], "NONE")

    def test_claim_safety_unapproved_satellite_center_rejected(self):
        """Claim Safety: Unapproved satellite facilities are rejected by validator."""
        context = build_personalization_context(_base_record())
        bad_body = (
            "Dear Krishna,\n\n"
            "Our Pune & Dahej Regional Metrology Centers provide fast calibration for your facility. "
            "We ensure complete coverage for your team. Would it make sense to review your list?\n\n"
            "If not the right person, please point me to the right lead."
        )
        report = self.validator.validate(
            subject="Calibration Support",
            body=bad_body,
            followups={"day_3": "f3", "day_5": "f5", "day_11": "f11", "day_21": "f21"},
            context=context,
        )
        self.assertFalse(report.valid)
        self.assertTrue(any("UNAPPROVED_FACILITY_LOCATION" in v for v in report.violations))

    def test_claim_safety_unapproved_sla_rejected(self):
        """Claim Safety: Fabricated turnaround SLAs are rejected."""
        context = build_personalization_context(_base_record())
        bad_body = (
            "Dear Krishna,\n\n"
            "Oorja Technical Services guarantees a certified 48-to-72-hour expedited turnaround for your plant. "
            "We have full capabilities across Bharat Precision Forgings Ltd. Would you like to review?\n\n"
            "If another colleague owns this, please point me to the right person."
        )
        report = self.validator.validate(
            subject="Turnaround Support",
            body=bad_body,
            followups={"day_3": "f3", "day_5": "f5", "day_11": "f11", "day_21": "f21"},
            context=context,
        )
        self.assertFalse(report.valid)
        self.assertTrue(any("UNAPPROVED_TURNAROUND_SLA" in v for v in report.violations))

    def test_unsupported_numeric_roi_rejected(self):
        """Value Safety: Invented numeric ROI (e.g. 'save 35% cost') is strictly rejected."""
        context = build_personalization_context(_base_record())
        bad_body = (
            "Dear Krishna,\n\n"
            "Our calibration program will save 35% cost and reduce downtime by 4 hours for Bharat Precision Forgings Ltd. "
            "We provide complete NABL CC-3963 accredited support. Would you be open to a discussion?\n\n"
            "If another lead owns this, please point me to them."
        )
        report = self.validator.validate(
            subject="Cost Reduction",
            body=bad_body,
            followups={"day_3": "f3", "day_5": "f5", "day_11": "f11", "day_21": "f21"},
            context=context,
        )
        self.assertFalse(report.valid)
        self.assertTrue(any("UNSUPPORTED_NUMERIC_ROI" in v for v in report.violations))

    def test_framework_names_not_in_email_text(self):
        """Framework terms (SPIN, Challenger, MEDDPICC, etc.) must NEVER leak into recipient text."""
        context = build_personalization_context(_base_record())
        bad_body = (
            "Dear Krishna,\n\n"
            "Situation: You are opening a new line at Bharat Precision Forgings Ltd. "
            "Problem: Instruments are uncalibrated. "
            "Implication: Audit risk. "
            "Need-Payoff: Oorja can help. Would you like to review?\n\n"
            "If another colleague owns this, point me to the right lead."
        )
        report = self.validator.validate(
            subject="SPIN Calibration Review",
            body=bad_body,
            followups={"day_3": "f3", "day_5": "f5", "day_11": "f11", "day_21": "f21"},
            context=context,
        )
        self.assertFalse(report.valid)
        self.assertTrue(any("FRAMEWORK_LEAKAGE" in v for v in report.violations))

    def test_followup_differentiation(self):
        """Follow-ups across Day 3, 5, 11, and 21 must be distinct and non-repetitive."""
        record = _base_record()
        result = self.pipeline.personalize_record(record, force_provider="DETERMINISTIC")

        followups = result["followups"]
        self.assertEqual(len(followups), 4)

        d3 = followups["day_3"]
        d5 = followups["day_5"]
        d11 = followups["day_11"]
        d21 = followups["day_21"]

        # Ensure none are identical
        texts = [d3, d5, d11, d21]
        self.assertEqual(len(set(texts)), 4)

        # Day 21 must be a polite closing note
        self.assertTrue("close the loop" in d21.lower() or "final note" in d21.lower())

    def test_deepseek_routing_primary(self):
        """DeepSeek is primary LLM when available and generates valid structured JSON."""
        mock_deepseek = MagicMock()
        mock_deepseek.is_available.return_value = True

        mock_payload = {
            "subject": "Calibration Planning - Bharat Precision Forgings Ltd (Jamshedpur)",
            "body": (
                "Dear Krishna,\n\n"
                "With Bharat Precision Forgings Ltd advancing commissioning at Plant V, "
                "managing instrument verification across newly installed press lines becomes essential ahead of initial production runs.\n\n"
                "During ramp-up phases, calibration planning often gets addressed after mechanical installation, "
                "which can compress qualification timelines and create scheduling bottlenecks across multiple external labs.\n\n"
                "Oorja Technical Services is an ISO/IEC 17025:2017 NABL-accredited calibration laboratory (Certificate CC-3963). "
                "We provide consolidated on-site calibration for dimensional masters, CMM systems, and thermal process instrumentation, "
                "reducing equipment movement and administrative overhead.\n\n"
                "Would it make sense to review your upcoming equipment calibration schedule to determine which items can be supported on-site?\n\n"
                "If another colleague directly leads metrology or quality planning for Plant V, could you kindly point me to the right lead?\n\n"
                f"{STANDARD_SIGNATURE_TEXT}"
            ),
            "followups": {
                "day_3": f"Dear Krishna, following up regarding Plant V calibration. Are you the right lead to connect with?\n\n{STANDARD_SIGNATURE_TEXT}",
                "day_5": f"Dear Krishna, one common challenge is vendor sprawl across multiple labs. Grouping on-site helps.\n\n{STANDARD_SIGNATURE_TEXT}",
                "day_11": f"Dear Krishna, if upcoming calibration is sorted, all good. Otherwise I can review the list.\n\n{STANDARD_SIGNATURE_TEXT}",
                "day_21": f"Dear Krishna, closing the loop on this thread. A referral to the right lead would be appreciated.\n\n{STANDARD_SIGNATURE_TEXT}",
            },
            "sales_reasoning": {
                "why_this_company": "Industrial forging leader",
                "why_now": "New line commissioning",
                "why_this_person": "Quality Head",
                "pain_hypothesis": "Instrument qualification bottleneck",
                "implication": "Startup delay",
                "value_hypothesis": "On-site consolidated calibration",
                "roi_angle": "downtime reduction",
                "compliance_angle": "NABL CC-3963",
                "operational_angle": "On-site batch slot",
                "best_cta": "Review equipment list",
                "referral_needed": True,
                "meddpicc": {"metrics": "downtime", "economic_buyer": "Plant Head"},
            },
            "evidence_used": ["company", "facility", "trigger"],
            "claims": ["NABL CC-3963 accredited calibration"],
        }

        mock_deepseek.complete.return_value = LLMResponse(
            text=json.dumps(mock_payload),
            provider="hive",
            model="deepseek-ai/DeepSeek-V4.1-Flash",
        )

        pipeline = SalesPersonalizationPipeline(deepseek_provider=mock_deepseek)
        result = pipeline.personalize_record(_base_record())

        self.assertEqual(result["llm_provider_used"], "DEEPSEEK")
        self.assertEqual(result["status"], "VALIDATED")
        mock_deepseek.complete.assert_called_once()

    def test_gemini_fallback_when_deepseek_fails(self):
        """Gemini fallback activates when DeepSeek throws an exception or is unavailable."""
        mock_deepseek = MagicMock()
        mock_gemini = MagicMock()

        mock_deepseek.is_available.return_value = True
        mock_gemini.is_available.return_value = True

        mock_deepseek.complete.side_effect = RuntimeError("DeepSeek Hive timeout")

        mock_gemini_payload = {
            "subject": "Calibration Planning - Bharat Precision Forgings Ltd (Jamshedpur)",
            "body": (
                "Dear Krishna,\n\n"
                "With Bharat Precision Forgings Ltd advancing commissioning at Plant V, "
                "managing instrument verification across newly installed press lines becomes essential ahead of initial production runs.\n\n"
                "During ramp-up phases, calibration planning often gets addressed after mechanical installation, "
                "which can compress qualification timelines and create scheduling bottlenecks across multiple external labs.\n\n"
                "Oorja Technical Services is an ISO/IEC 17025:2017 NABL-accredited calibration laboratory (Certificate CC-3963). "
                "We provide consolidated on-site calibration for dimensional masters, CMM systems, and thermal process instrumentation, "
                "reducing equipment movement and administrative overhead.\n\n"
                "Would it make sense to review your upcoming equipment calibration schedule to determine which items can be supported on-site?\n\n"
                "If another colleague directly leads metrology or quality planning for Plant V, could you kindly point me to the right lead?\n\n"
                f"{STANDARD_SIGNATURE_TEXT}"
            ),
            "followups": {
                "day_3": f"Dear Krishna, following up on Plant V calibration planning. Are you the right lead?\n\n{STANDARD_SIGNATURE_TEXT}",
                "day_5": f"Dear Krishna, grouping calibrations into an on-site slot reduces transit overhead.\n\n{STANDARD_SIGNATURE_TEXT}",
                "day_11": f"Dear Krishna, happy to review open items on your equipment list if scheduling is underway.\n\n{STANDARD_SIGNATURE_TEXT}",
                "day_21": f"Dear Krishna, closing the loop. Please let me know if another colleague leads this activity.\n\n{STANDARD_SIGNATURE_TEXT}",
            },
            "sales_reasoning": {
                "why_this_company": "Forging plant",
                "why_now": "Line commissioning",
                "why_this_person": "Quality Head",
                "pain_hypothesis": "Calibration logistics",
                "implication": "Startup friction",
                "value_hypothesis": "Onsite grouping",
                "roi_angle": "vendor consolidation",
                "compliance_angle": "ISO/IEC 17025:2017 CC-3963",
                "operational_angle": "Onsite execution",
                "best_cta": "List review",
                "referral_needed": True,
                "meddpicc": {"metrics": "turnaround", "economic_buyer": "Plant Head"},
            },
            "evidence_used": ["company", "facility"],
            "claims": ["CC-3963 accredited"],
        }

        mock_gemini.complete.return_value = LLMResponse(
            text=json.dumps(mock_gemini_payload),
            provider="gemini",
            model="gemini-3.1-flash-lite",
        )

        pipeline = SalesPersonalizationPipeline(
            deepseek_provider=mock_deepseek,
            gemini_provider=mock_gemini,
        )
        result = pipeline.personalize_record(_base_record())

        self.assertEqual(result["llm_provider_used"], "GEMINI")
        self.assertEqual(result["status"], "VALIDATED")
        mock_deepseek.complete.assert_called_once()
        mock_gemini.complete.assert_called_once()

    def test_rediff_mapping_and_zero_smtp(self):
        """Personalized record integrates with Rediff file handoff adapter with ZERO SMTP."""
        record = _base_record()
        result = self.pipeline.personalize_record(record, force_provider="DETERMINISTIC")

        # Enrich record for Rediff adapter
        enriched_record = self.pipeline.enrich_record_for_rediff(record, result)
        self.assertEqual(enriched_record["WHY_CALIBRATION_NOW"], result["body"])
        self.assertEqual(enriched_record["REASON_FOR_OUTREACH"], result["body"])
        self.assertIn("subject", enriched_record["NOTES"])

        # Pass through RediffSenderAdapter in test mode
        adapter = RediffSenderAdapter()
        with patch("smtplib.SMTP") as mock_smtp, patch("smtplib.SMTP_SSL") as mock_smtp_ssl:
            handoff_result = adapter.prepare_handoff(enriched_record, campaign="personalized-production-test")

            self.assertEqual(handoff_result["status"], DRY_RUN_READY)
            self.assertFalse(handoff_result["transport_called"])
            self.assertFalse(handoff_result["smtp_sent"])
            mock_smtp.assert_not_called()
            mock_smtp_ssl.assert_not_called()

            # Ensure mapped CSV contains personalized copy
            mapped = handoff_result["mapped_record"]
            self.assertEqual(mapped["WHY_CALIBRATION_NOW"], result["body"])
            self.assertEqual(mapped["READY_FOR_EMAIL"], "YES")

    def test_initial_email_standard_signature(self):
        """Initial outreach email must end with full standardized Bablu Gurjar signature."""
        result = self.pipeline.personalize_record(_base_record(), force_provider="DETERMINISTIC")
        body = result["body"]

        # Required fields present
        self.assertIn("Bablu Gurjar", body)
        self.assertIn("9201949296", body)
        self.assertIn("Bablu@oorjatechnical.org", body)
        self.assertIn("Sales - Oorja Technical Services Pvt. Ltd.", body)
        self.assertIn("Best regards,", body)

        # Exactly one signature
        self.assertEqual(body.count("Bablu Gurjar"), 1)
        self.assertEqual(body.count("9201949296"), 1)
        self.assertEqual(body.count("Bablu@oorjatechnical.org"), 1)
        self.assertEqual(body.count("Sales - Oorja Technical Services Pvt. Ltd."), 1)
        self.assertEqual(body.count("Best regards"), 1)

        # Accreditation not in signature block
        sig_part = body.split("Best regards", 1)[1]
        self.assertNotIn("ISO/IEC 17025", sig_part)
        self.assertNotIn("CC-3963", sig_part)
        self.assertNotIn("Accreditation:", sig_part)

        # Body text itself still has accredited lab details naturally
        self.assertIn("CC-3963", body)

    def test_all_followups_contain_standard_signature(self):
        """All four follow-up stages (Day 3, Day 5, Day 11, Day 21) must contain full signature."""
        result = self.pipeline.personalize_record(_base_record(), force_provider="DETERMINISTIC")
        followups = result["followups"]

        for stage in ["day_3", "day_5", "day_11", "day_21"]:
            fu = followups[stage]
            self.assertIn("Bablu Gurjar", fu, f"Stage {stage} missing sender name")
            self.assertIn("9201949296", fu, f"Stage {stage} missing contact number")
            self.assertIn("Bablu@oorjatechnical.org", fu, f"Stage {stage} missing email")
            self.assertIn("Sales - Oorja Technical Services Pvt. Ltd.", fu, f"Stage {stage} missing title")
            self.assertEqual(fu.count("Bablu Gurjar"), 1, f"Stage {stage} has duplicate signature")
            self.assertEqual(fu.count("Best regards"), 1, f"Stage {stage} has duplicate sign-off")

            sig_part = fu.split("Best regards", 1)[1]
            self.assertNotIn("ISO/IEC 17025", sig_part)
            self.assertNotIn("CC-3963", sig_part)
            self.assertNotIn("Accreditation:", sig_part)

    def test_validator_rejects_missing_signature_elements(self):
        """Quality validator fails copy missing any required signature identity element."""
        context = build_personalization_context(_base_record())
        valid_result = DeterministicPersonalizationGenerator.generate(context)

        # Missing phone
        bad_body = valid_result["body"].replace("9201949296", "")
        report = self.validator.validate(
            subject=valid_result["subject"],
            body=bad_body,
            followups=valid_result["followups"],
            context=context,
        )
        self.assertFalse(report.valid)
        self.assertTrue(any("MISSING_SIGNATURE_ELEMENT" in v for v in report.violations))

        # Missing sender email
        bad_body_email = valid_result["body"].replace("Bablu@oorjatechnical.org", "")
        report_email = self.validator.validate(
            subject=valid_result["subject"],
            body=bad_body_email,
            followups=valid_result["followups"],
            context=context,
        )
        self.assertFalse(report_email.valid)
        self.assertTrue(any("MISSING_SIGNATURE_ELEMENT" in v for v in report_email.violations))

    def test_validator_rejects_duplicate_signatures(self):
        """Quality validator strictly rejects duplicated signatures."""
        context = build_personalization_context(_base_record())
        valid_result = DeterministicPersonalizationGenerator.generate(context)

        double_signed_body = valid_result["body"] + f"\n\n{STANDARD_SIGNATURE_TEXT}"
        report = self.validator.validate(
            subject=valid_result["subject"],
            body=double_signed_body,
            followups=valid_result["followups"],
            context=context,
        )
        self.assertFalse(report.valid)
        self.assertTrue(any("DUPLICATE_SIGNATURE" in v for v in report.violations))

    def test_validator_rejects_accreditation_in_signature(self):
        """Accreditation in the signature block is prohibited (must remain in body only)."""
        context = build_personalization_context(_base_record())
        valid_result = DeterministicPersonalizationGenerator.generate(context)

        bad_sig_body = valid_result["body"] + "\nAccreditation: ISO/IEC 17025:2017 (NABL CC-3963)"
        report = self.validator.validate(
            subject=valid_result["subject"],
            body=bad_sig_body,
            followups=valid_result["followups"],
            context=context,
        )
        self.assertFalse(report.valid)
        self.assertTrue(any("ACCREDITATION_IN_SIGNATURE" in v for v in report.violations))

    def test_rediff_mapping_preserves_single_signature_and_zero_smtp(self):
        """Rediff mapping preserves personalized signature without duplication and sends zero SMTP."""
        record = _base_record()
        result = self.pipeline.personalize_record(record, force_provider="DETERMINISTIC")
        enriched = self.pipeline.enrich_record_for_rediff(record, result)

        preview = rediff_bridge.generate_outreach_preview(enriched)

        # Body text has exactly ONE signature
        self.assertEqual(preview["body_text"].count("Bablu Gurjar"), 1)
        self.assertEqual(preview["body_text"].count("9201949296"), 1)
        self.assertEqual(preview["body_text"].count("Bablu@oorjatechnical.org"), 1)
        self.assertEqual(preview["body_text"].count("Sales - Oorja Technical Services Pvt. Ltd."), 1)

        # HTML has exactly ONE signature
        self.assertEqual(preview["body_html"].count("Bablu Gurjar"), 1)
        self.assertEqual(preview["body_html"].count("9201949296"), 1)
        self.assertEqual(preview["body_html"].count("Bablu@oorjatechnical.org"), 1)
        self.assertEqual(preview["body_html"].count("Sales - Oorja Technical Services Pvt. Ltd."), 1)

        # No images or banner elements
        self.assertNotIn("<img", preview["body_html"].lower())

        # Zero SMTP verified
        self.assertTrue(preview["test_mode"])
        self.assertTrue(preview["no_send_enforced"])

    def test_validator_rejects_unsupported_audit_assertion(self):
        """Quality validator fails copy asserting an upcoming audit without verified evidence."""
        record = _base_record(
            trigger="New precision machining and press line commissioning",
            reasoning="Commissioning of new manufacturing machinery",
        )
        context = build_personalization_context(record)
        bad_body = (
            "Dear Krishna,\n\n"
            "With Bharat Precision Forgings Ltd advancing commissioning at Plant V, "
            "maintaining continuous measurement traceability becomes essential ahead of your upcoming audit.\n\n"
            "Oorja Technical Services is an ISO/IEC 17025:2017 NABL-accredited calibration laboratory (Certificate CC-3963). "
            "We provide consolidated on-site calibration for dimensional masters and CMM systems, "
            "reducing equipment movement and administrative overhead.\n\n"
            "Would it make sense to review your upcoming equipment calibration schedule to determine which items can be supported on-site?\n\n"
            "If another colleague directly leads metrology or quality planning for Plant V, could you kindly point me to the right person?\n\n"
            f"{STANDARD_SIGNATURE_TEXT}"
        )
        report = self.validator.validate(
            subject="Audit Preparation Support",
            body=bad_body,
            followups={
                "day_3": f"f3\n\n{STANDARD_SIGNATURE_TEXT}",
                "day_5": f"f5\n\n{STANDARD_SIGNATURE_TEXT}",
                "day_11": f"f11\n\n{STANDARD_SIGNATURE_TEXT}",
                "day_21": f"f21\n\n{STANDARD_SIGNATURE_TEXT}",
            },
            context=context,
        )
        self.assertFalse(report.valid)
        self.assertEqual(report.status, "PERSONALIZATION_REVIEW_REQUIRED")
        self.assertTrue(any("UNSUPPORTED_AUDIT_ASSERTION" in v for v in report.violations))

    def test_validator_allows_audit_mention_when_audit_evidence_present(self):
        """Quality validator permits audit context when verified audit evidence is present."""
        record = _base_record(
            trigger="Upcoming annual IATF and customer surveillance audit",
            reasoning="Audit compliance requires calibration certificate retrieval",
        )
        context = build_personalization_context(record)
        valid_result = DeterministicPersonalizationGenerator.generate(context)
        report = self.validator.validate(
            subject=valid_result["subject"],
            body=valid_result["body"],
            followups=valid_result["followups"],
            context=context,
        )
        self.assertTrue(report.valid)
        self.assertFalse(any("UNSUPPORTED_AUDIT_ASSERTION" in v for v in report.violations))

    def test_validator_rejects_unsupported_absolute_claims(self):
        """Quality validator fails copy containing unverified absolute claims like 'significantly reduces'."""
        context = build_personalization_context(_base_record())
        bad_body = (
            "Dear Krishna,\n\n"
            "With Bharat Precision Forgings Ltd advancing commissioning at Plant V, "
            "managing instrument verification across newly installed press lines is a practical priority.\n\n"
            "Oorja Technical Services is an ISO/IEC 17025:2017 NABL-accredited calibration laboratory (Certificate CC-3963). "
            "Our on-site execution significantly reduces logistics overhead and eliminates downtime risk.\n\n"
            "Would it make sense to review your upcoming equipment calibration schedule to determine which items can be supported on-site?\n\n"
            "If another colleague directly leads metrology or quality planning for Plant V, could you kindly point me to the right person?\n\n"
            f"{STANDARD_SIGNATURE_TEXT}"
        )
        report = self.validator.validate(
            subject="Calibration Support",
            body=bad_body,
            followups={
                "day_3": f"f3\n\n{STANDARD_SIGNATURE_TEXT}",
                "day_5": f"f5\n\n{STANDARD_SIGNATURE_TEXT}",
                "day_11": f"f11\n\n{STANDARD_SIGNATURE_TEXT}",
                "day_21": f"f21\n\n{STANDARD_SIGNATURE_TEXT}",
            },
            context=context,
        )
        self.assertFalse(report.valid)
        self.assertEqual(report.status, "PERSONALIZATION_REVIEW_REQUIRED")
        self.assertTrue(any("UNSUPPORTED_ABSOLUTE_CLAIM" in v for v in report.violations))

    def test_validator_rejects_generic_four_discipline_boilerplate_when_narrower(self):
        """Quality validator rejects generic four-discipline list when opportunity is narrower."""
        context = build_personalization_context(_base_record(
            calibration_opportunity="Dimensional CMM and furnace pyrometry calibration"
        ))
        bad_body = (
            "Dear Krishna,\n\n"
            "With Bharat Precision Forgings Ltd advancing commissioning at Plant V, "
            "managing instrument verification across newly installed press lines is a practical priority.\n\n"
            "Oorja Technical Services is an ISO/IEC 17025:2017 NABL-accredited calibration laboratory (Certificate CC-3963). "
            "We group mechanical, thermal, pressure, and electrical calibration into a single planned on-site slot.\n\n"
            "Would it make sense to review your upcoming equipment calibration schedule to determine which items can be supported on-site?\n\n"
            "If another colleague directly leads metrology or quality planning for Plant V, could you kindly point me to the right person?\n\n"
            f"{STANDARD_SIGNATURE_TEXT}"
        )
        report = self.validator.validate(
            subject="Calibration Support",
            body=bad_body,
            followups={
                "day_3": f"f3\n\n{STANDARD_SIGNATURE_TEXT}",
                "day_5": f"f5\n\n{STANDARD_SIGNATURE_TEXT}",
                "day_11": f"f11\n\n{STANDARD_SIGNATURE_TEXT}",
                "day_21": f"f21\n\n{STANDARD_SIGNATURE_TEXT}",
            },
            context=context,
        )
        self.assertFalse(report.valid)
        self.assertEqual(report.status, "PERSONALIZATION_REVIEW_REQUIRED")
        self.assertTrue(any("GENERIC_DISCIPLINE_BOILERPLATE" in v for v in report.violations))

    def test_synthetic_comparison_three_personas_materially_differ(self):
        """Synthetic Comparison: 1 company, 1 facility, 1 trigger, 3 personas materially differ."""
        base_kwargs = dict(
            company="Tata Motors Commercial Vehicles Ltd",
            facility="Commercial Vehicle Plant, Pimpri, Pune, Maharashtra",
            city="Pune",
            state="Maharashtra",
            trigger="new production line commissioning",
            calibration_opportunity="dimensional + temperature calibration",
            reasoning="Commissioning of new transmission assembly line",
        )

        rec_quality = _base_record(
            person="Arun Deshmukh",
            first_name="Arun",
            designation="Head of Quality Assurance",
            persona="Quality Head",
            **base_kwargs,
        )
        rec_plant = _base_record(
            person="Rajesh Sharma",
            first_name="Rajesh",
            designation="Executive Director & Plant Head",
            persona="Plant Head",
            **base_kwargs,
        )
        rec_proc = _base_record(
            person="Siddharth Mehta",
            first_name="Siddharth",
            designation="Head of Sourcing & Vendor Procurement",
            persona="Procurement",
            **base_kwargs,
        )

        res_quality = self.pipeline.personalize_record(rec_quality, force_provider="DETERMINISTIC")
        res_plant = self.pipeline.personalize_record(rec_plant, force_provider="DETERMINISTIC")
        res_proc = self.pipeline.personalize_record(rec_proc, force_provider="DETERMINISTIC")

        # 1. All must be VALIDATED
        self.assertEqual(res_quality["status"], "VALIDATED")
        self.assertEqual(res_plant["status"], "VALIDATED")
        self.assertEqual(res_proc["status"], "VALIDATED")

        body_q = res_quality["body"]
        body_p = res_plant["body"]
        body_pr = res_proc["body"]

        # 2. None may be identical
        self.assertNotEqual(body_q, body_p)
        self.assertNotEqual(body_q, body_pr)
        self.assertNotEqual(body_p, body_pr)

        # 3. Persona-specific content checks
        self.assertTrue("traceability" in body_q.lower() or "qualification" in body_q.lower())
        self.assertTrue("production" in body_p.lower() or "shutdown" in body_p.lower())
        self.assertTrue("vendor" in body_pr.lower() or "commercial" in body_pr.lower())

        # 4. Day 5 follow-up differentiation
        d5_q = res_quality["followups"]["day_5"]
        d5_p = res_plant["followups"]["day_5"]
        d5_pr = res_proc["followups"]["day_5"]
        self.assertNotEqual(d5_q, d5_p)
        self.assertNotEqual(d5_q, d5_pr)
        self.assertNotEqual(d5_p, d5_pr)

        # 5. Opportunity alignment (no generic 4-discipline boilerplate)
        for b in [body_q, body_p, body_pr]:
            self.assertNotIn("mechanical, thermal, pressure, and electrical", b.lower())
            self.assertNotIn("significantly reduces", b.lower())

        # 6. No invented upcoming audit assertion
        for b in [body_q, body_p, body_pr]:
            self.assertNotIn("ahead of quality audits", b.lower())
            self.assertNotIn("upcoming audit", b.lower())

    def test_synthetic_comparison_three_triggers_materially_differ(self):
        """Synthetic Comparison: 1 Quality Head across 3 triggers materially differs."""
        base_kwargs = dict(
            company="Bharat Precision Forgings Ltd",
            facility="Plant V, Baliguma, Jamshedpur",
            city="Jamshedpur",
            person="Krishna Kumar Jha",
            first_name="Krishna",
            designation="Head of Quality & Metrology",
            persona="Quality Head",
            calibration_opportunity="dimensional CMM and furnace pyrometry calibration",
        )

        rec_new_line = _base_record(
            trigger="new production line commissioning",
            reasoning="Installation of high-precision forging press line",
            **base_kwargs,
        )
        rec_audit = _base_record(
            trigger="upcoming annual IATF and customer surveillance audit",
            reasoning="Annual surveillance audit approaching",
            **base_kwargs,
        )
        rec_routine = _base_record(
            trigger="routine plant maintenance cycle",
            reasoning="Regular scheduled annual calibration",
            **base_kwargs,
        )

        res_nl = self.pipeline.personalize_record(rec_new_line, force_provider="DETERMINISTIC")
        res_aud = self.pipeline.personalize_record(rec_audit, force_provider="DETERMINISTIC")
        res_rtn = self.pipeline.personalize_record(rec_routine, force_provider="DETERMINISTIC")

        self.assertEqual(res_nl["status"], "VALIDATED")
        self.assertEqual(res_aud["status"], "VALIDATED")
        self.assertEqual(res_rtn["status"], "VALIDATED")

        body_nl = res_nl["body"]
        body_aud = res_aud["body"]
        body_rtn = res_rtn["body"]

        # None may be identical
        self.assertNotEqual(body_nl, body_aud)
        self.assertNotEqual(body_nl, body_rtn)
        self.assertNotEqual(body_aud, body_rtn)

        # Trigger-specific language
        self.assertTrue("new line" in body_nl.lower() or "launch" in body_nl.lower())
        self.assertTrue("audit" in body_aud.lower() or "surveillance" in body_aud.lower())
        self.assertTrue("upcoming calibration cycle" in body_rtn.lower() or "routine" in body_rtn.lower())
        # Routine must NOT fake urgency with audit
        self.assertNotIn("ahead of quality audits", body_rtn.lower())
        self.assertNotIn("upcoming audit", body_rtn.lower())

    def test_validator_rejects_invented_vendor_count(self):
        """Part 1: Quality validator strictly rejects invented vendor counts (e.g. 'four or five separate vendors')."""
        context = build_personalization_context(_base_record())
        bad_body = (
            "Dear Krishna,\n\n"
            "Managing calibration through four or five separate vendors creates unnecessary administrative friction. "
            "Where technically feasible, Oorja Technical Services can help consolidate your calibration requirements.\n\n"
            "Would it make sense to review your upcoming equipment calibration schedule to determine which items can be supported on-site?\n\n"
            "If another colleague directly leads metrology or calibration planning for Plant V, could you kindly point me to the right person?\n\n"
            f"{STANDARD_SIGNATURE_TEXT}"
        )
        report = self.validator.validate(
            subject="Vendor Coordination",
            body=bad_body,
            followups={
                "day_3": f"f3\n\n{STANDARD_SIGNATURE_TEXT}",
                "day_5": f"f5\n\n{STANDARD_SIGNATURE_TEXT}",
                "day_11": f"f11\n\n{STANDARD_SIGNATURE_TEXT}",
                "day_21": f"f21\n\n{STANDARD_SIGNATURE_TEXT}",
            },
            context=context,
        )
        self.assertFalse(report.valid)
        self.assertEqual(report.status, "PERSONALIZATION_REVIEW_REQUIRED")
        self.assertTrue(any("INVENTED_VENDOR_COUNT" in v for v in report.violations))

    def test_validator_rejects_unsupported_operational_promises(self):
        """Part 1: Quality validator strictly rejects unsupported operational claims like 'keep equipment on the floor'."""
        context = build_personalization_context(_base_record())
        for bad_phrase in [
            "keep equipment on the floor",
            "avoid transit downtime",
            "without moving critical masters offsite",
            "under a unified agreement",
        ]:
            bad_body = (
                f"Dear Krishna,\n\n"
                f"With Bharat Precision Forgings Ltd commissioning Plant V, we help you {bad_phrase}. "
                f"Where technically feasible, our NABL CC-3963 accredited laboratory supports equipment calibration.\n\n"
                f"Would it make sense to review your upcoming equipment calibration schedule to determine which items can be supported on-site?\n\n"
                f"If another colleague leads this planning for Plant V, could you kindly point me to the right person?\n\n"
                f"{STANDARD_SIGNATURE_TEXT}"
            )
            report = self.validator.validate(
                subject="Calibration Support",
                body=bad_body,
                followups={
                    "day_3": f"f3\n\n{STANDARD_SIGNATURE_TEXT}",
                    "day_5": f"f5\n\n{STANDARD_SIGNATURE_TEXT}",
                    "day_11": f"f11\n\n{STANDARD_SIGNATURE_TEXT}",
                    "day_21": f"f21\n\n{STANDARD_SIGNATURE_TEXT}",
                },
                context=context,
            )
            self.assertFalse(report.valid, f"Failed to reject bad phrase: {bad_phrase}")
            self.assertEqual(report.status, "PERSONALIZATION_REVIEW_REQUIRED")
            self.assertTrue(any("UNSUPPORTED_OPERATIONAL_CLAIM" in v for v in report.violations))

    def test_validator_rejects_unsupported_maintenance_window(self):
        """Part 1: Quality validator rejects 'planned maintenance window' unless evidence supports it."""
        record = _base_record(
            trigger="New precision machining and press line commissioning",
            reasoning="Commissioning of new manufacturing machinery",
        )
        context = build_personalization_context(record)
        bad_body = (
            "Dear Krishna,\n\n"
            "With Bharat Precision Forgings Ltd commissioning Plant V, "
            "we coordinate on-site calibration during your planned maintenance window. "
            "Where technically feasible, our NABL CC-3963 accredited laboratory supports measurement traceability.\n\n"
            "Would it make sense to review your upcoming equipment calibration schedule to determine which items can be supported on-site?\n\n"
            "If another colleague directly leads metrology or quality planning for Plant V, could you point me to the right lead?\n\n"
            f"{STANDARD_SIGNATURE_TEXT}"
        )
        report = self.validator.validate(
            subject="Maintenance Planning",
            body=bad_body,
            followups={
                "day_3": f"f3\n\n{STANDARD_SIGNATURE_TEXT}",
                "day_5": f"f5\n\n{STANDARD_SIGNATURE_TEXT}",
                "day_11": f"f11\n\n{STANDARD_SIGNATURE_TEXT}",
                "day_21": f"f21\n\n{STANDARD_SIGNATURE_TEXT}",
            },
            context=context,
        )
        self.assertFalse(report.valid)
        self.assertEqual(report.status, "PERSONALIZATION_REVIEW_REQUIRED")
        self.assertTrue(any("UNSUPPORTED_MAINTENANCE_WINDOW" in v for v in report.violations))

    def test_capability_vs_opportunity_separation_and_onsite_qualification(self):
        """Part 2: Opportunity does not prove capability; unhedged on-site promises are blocked."""
        context = build_personalization_context(_base_record())
        # Unhedged on-site promise without feasibility qualifier
        bad_body = (
            "Dear Krishna,\n\n"
            "With Bharat Precision Forgings Ltd commissioning Plant V, "
            "we execute on-site calibration for dimensional CMM and furnace pyrometry calibration. "
            "Oorja Technical Services is an ISO/IEC 17025:2017 NABL-accredited calibration laboratory (CC-3963).\n\n"
            "Would it make sense to review your schedule?\n\n"
            "If another colleague leads this planning for Plant V, could you point me to the right person?\n\n"
            f"{STANDARD_SIGNATURE_TEXT}"
        )
        report = self.validator.validate(
            subject="CMM Support",
            body=bad_body,
            followups={
                "day_3": f"f3\n\n{STANDARD_SIGNATURE_TEXT}",
                "day_5": f"f5\n\n{STANDARD_SIGNATURE_TEXT}",
                "day_11": f"f11\n\n{STANDARD_SIGNATURE_TEXT}",
                "day_21": f"f21\n\n{STANDARD_SIGNATURE_TEXT}",
            },
            context=context,
        )
        self.assertFalse(report.valid)
        self.assertTrue(
            any("UNSUPPORTED_ONSITE_PROMISES" in v or "UNQUALIFIED_ONSITE_CLAIM" in v for v in report.violations)
        )

    def test_deterministic_output_fully_compliant_with_copy_rules(self):
        """Deterministic generator produces 100% compliant copy with zero unsafe claims and exact signature."""
        record = _base_record()
        result = self.pipeline.personalize_record(record, force_provider="DETERMINISTIC")

        self.assertEqual(result["status"], "VALIDATED")
        self.assertGreaterEqual(result["quality_score"], 85)

        full_copy = result["body"] + " " + " ".join(result["followups"].values())

        # No invented quantities
        self.assertNotIn("four or five", full_copy.lower())
        self.assertNotIn("4 or 5", full_copy.lower())

        # No unsupported operational promises
        self.assertNotIn("keep equipment on the floor", full_copy.lower())
        self.assertNotIn("avoid transit downtime", full_copy.lower())
        self.assertNotIn("without moving critical masters offsite", full_copy.lower())
        self.assertNotIn("under a unified agreement", full_copy.lower())
        self.assertNotIn("planned maintenance window", full_copy.lower())

        # Softened feasibility phrasing present
        self.assertTrue(
            "where technically feasible" in full_copy.lower()
            or "feasibility" in full_copy.lower()
        )

        # Standard signature exact on initial and all followups
        self.assertEqual(result["body"].count("Bablu Gurjar"), 1)
        for stage in ["day_3", "day_5", "day_11", "day_21"]:
            self.assertEqual(result["followups"][stage].count("Bablu Gurjar"), 1)

    def test_score_75_requires_review_and_cannot_enter_production(self):
        """A personalization quality score of 75 MUST produce PERSONALIZATION_REVIEW_REQUIRED and be suppressed from production."""
        record = _base_record()
        context = build_personalization_context(record)

        # Build copy that misses company name (-15) and referral CTA (-10) -> score 75
        body_75 = (
            f"Dear Krishna,\n\n"
            f"We understand your Plant V operations in Baliguma are ramping up precision manufacturing activities. "
            f"Where technically feasible, our NABL CC-3963 accredited laboratory supports high-precision equipment calibration under ISO/IEC 17025:2017 standards. "
            f"Our team provides on-site measurement verification and calibration services tailored for industrial production lines.\n\n"
            f"Would it make sense to review your upcoming equipment calibration schedule to determine which items can be supported on-site?\n\n"
            f"{STANDARD_SIGNATURE_TEXT}"
        )
        report = self.validator.validate(
            subject="Equipment Calibration Support",
            body=body_75,
            followups={
                "day_3": f"Regarding your calibration schedule at Plant V.\n\n{STANDARD_SIGNATURE_TEXT}",
                "day_5": f"Following up on metrology planning.\n\n{STANDARD_SIGNATURE_TEXT}",
                "day_11": f"Touching base on ISO/IEC 17025 compliance support.\n\n{STANDARD_SIGNATURE_TEXT}",
                "day_21": f"Final check on equipment calibration requirements.\n\n{STANDARD_SIGNATURE_TEXT}",
            },
            context=context,
        )
        self.assertEqual(report.score, 75)
        self.assertFalse(report.valid)
        self.assertEqual(report.status, "PERSONALIZATION_REVIEW_REQUIRED")

        # Test Rediff production handoff gate suppresses score 75 / review required
        from services.rediff_sender_adapter import RediffSenderAdapter, SUPPRESSED_NOT_READY
        from services.opportunity_gates import evaluate_opportunity_gates
        adapter = RediffSenderAdapter()
        suppressed_record = {
            "COMPANY": "CG Power and Industrial Solutions Limited",
            "EMAIL": "pradeep.deo@cgpower.com",
            "READY_FOR_EMAIL": "YES",
            "PERSONALIZATION_STATUS": report.status,
            "PERSONALIZATION_SCORE": report.score,
            "evidence": record["evidence"],
        }
        res = adapter.prepare_handoff(suppressed_record, campaign="test-campaign")
        self.assertEqual(res["status"], SUPPRESSED_NOT_READY)
        self.assertIn("requires human review", res["reason"])


if __name__ == "__main__":
    unittest.main()

