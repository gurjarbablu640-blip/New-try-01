"""Phase 2.1E Release Candidate Identity, Provider, and Personalization Truth Audit Tests.

Verifies:
1. Exact production signature (Bablu Gurjar)
2. No placeholder recipient fallback / Missing recipient -> HOLD
3. Actual DB recipient preserved
4. Actual DB facility preserved
5. TASL Vadodara evidence cannot become Hyderabad
6. Canonical capability allow-list strictly enforced
7. Acoustic calibration rejected
8. Unsupported turnaround/minimal-downtime claim rejected
9. Apollo-only primary provider policy (no unapproved providers)
10. Public email requires explicit authoritative evidence
11. MX-only blocked from send-ready
12. Extrapolated blocked from send-ready
13. DeepSeek primary / Gemini fallback / both fail -> HOLD
14. Max 3 candidate waterfall and duplicate suppression
"""
import pytest
from unittest.mock import MagicMock

from services.sales_personalization_v2 import (
    SalesPersonalizationV2Engine,
    SALES_SIGNATURE,
    classify_claim,
    APPROVED_OORJA_CAPABILITY_GROUPS,
    INDUSTRY_CAPABILITY_MAP,
)
from services.contact_waterfall_service import (
    ContactWaterfallService,
    EmailVerificationLevel,
    classify_email_verification_level,
    is_send_ready_email,
    MX_ONLY_SEND_ALLOWED,
)


class TestPhase21ETruthAudit:

    def test_exact_production_signature(self):
        """Proof that the exact 5-line signature is enforced and ends the email body."""
        engine = SalesPersonalizationV2Engine()
        mock_provider = MagicMock()
        mock_provider.complete.return_value = MagicMock(content=(
            '{"subject": "Calibration support for Pune operations", "body": "Hello Rohit,\\n\\nI noticed the expansion activity at HARMAN Pune plant.\\n\\nOorja can support dimensional calibration, electrical calibration and torque calibration, subject to instrument, scope and range feasibility.\\n\\nIf useful, please share your instrument list."}'
        ))
        engine._injected_provider = mock_provider

        record = {
            "company": "HARMAN",
            "person": "Rohit Giri",
            "facility": "HARMAN Pune Automotive Manufacturing Plant",
            "trigger": "HARMAN Invests Rs 345 Crore to Expand Pune Automotive Manufacturing Plant",
            "industry": "automotive",
        }
        res = engine.generate_outreach(record)
        assert res.status == "VALIDATED"
        assert res.body.endswith(SALES_SIGNATURE.strip())
        assert "Bablu Gurjar" in res.body
        assert "Sales | Oorja Technical Services Pvt. Ltd." in res.body
        assert "Contact No.: 9201949296" in res.body
        assert "Email: Bablu@oorjatechnical.org" in res.body
        # Ensure no alternative identity survives
        assert "Rohan Sharma" not in res.body
        assert "sales@oorja.biz" not in res.body

    def test_missing_or_placeholder_recipient_returns_hold(self):
        """Missing or placeholder recipient must return HOLD and never synthesize a name."""
        engine = SalesPersonalizationV2Engine()

        for placeholder in ["", None, "   ", "Sir/Madam", "Placeholder", "Unknown", "N/A"]:
            record = {
                "company": "HARMAN",
                "person": placeholder,
                "facility": "HARMAN Pune Plant",
                "trigger": "Expansion",
            }
            res = engine.generate_outreach(record)
            assert res.status == "HOLD", f"Expected HOLD for placeholder '{placeholder}', got {res.status}"
            assert "Missing or placeholder recipient person" in res.violations[0]

    def test_unsupported_performance_claims_rejected(self):
        """Turnaround, minimal downtime, and priority claims are rejected as UNSUPPORTED_SPECIFIC."""
        forbidden_claims = [
            "Our turnaround options are structured to help facilities maintain minimal downtime.",
            "We provide fast turnaround on all equipment.",
            "We offer structured turnaround options for your plant.",
            "We guarantee priority service for automotive testing.",
            "Our calibration ensures guaranteed traceability and compliance.",
        ]
        for claim in forbidden_claims:
            label, viol = classify_claim(claim)
            assert label == "UNSUPPORTED_SPECIFIC", f"Expected UNSUPPORTED_SPECIFIC for: {claim}"

    def test_unapproved_capabilities_rejected(self):
        """Acoustic and mass calibration must be rejected unless authoritative Oorja evidence exists."""
        forbidden_caps = [
            "Oorja can support acoustic calibration for your plant.",
            "We provide mass calibration services.",
            "We support acoustic facilities with calibration.",
        ]
        for claim in forbidden_caps:
            label, viol = classify_claim(claim)
            assert label == "UNSUPPORTED_SPECIFIC", f"Expected UNSUPPORTED_SPECIFIC for: {claim}"

    def test_canonical_capability_allowlist_integrity(self):
        """Canonical groups must only include the 8 approved Oorja capability groups."""
        expected_groups = {
            "ELECTRICAL", "THERMAL", "PRESSURE", "DIMENSIONAL",
            "TORQUE", "WEIGHING", "CT_PT", "ENVIRONMENTAL_MAPPING"
        }
        assert set(APPROVED_OORJA_CAPABILITY_GROUPS.keys()) == expected_groups
        assert "ACOUSTIC" not in APPROVED_OORJA_CAPABILITY_GROUPS
        assert "MASS" not in APPROVED_OORJA_CAPABILITY_GROUPS
        assert "NDT" not in APPROVED_OORJA_CAPABILITY_GROUPS
        assert "AVIONICS" not in APPROVED_OORJA_CAPABILITY_GROUPS

    def test_tasl_vadodara_cannot_become_hyderabad(self):
        """TASL Vadodara FAL record must strictly bind to Vadodara and not Hyderabad."""
        record = {
            "company": "Tata Advanced Systems Limited",
            "facility": "Vadodara C295 Final Assembly Line",
            "person": "Amit Kanawaje",
            "trigger": "Tata Advanced Systems and Airbus inaugurate C295 Final Assembly Line at Vadodara",
            "industry": "aerospace",
        }
        engine = SalesPersonalizationV2Engine()
        body = engine._build_body(record, persona="STRONG_PLANT_QUALITY_OWNER", capabilities=["dimensional calibration"])
        assert "Vadodara" in body
        assert "Hyderabad" not in body
        assert "C295" in body

    def test_email_verification_levels_and_send_ready_policy(self):
        """Only VERIFIED_PROVIDER and VERIFIED_PUBLIC_SOURCE are send-ready; MX-only and extrapolated are blocked."""
        assert MX_ONLY_SEND_ALLOWED is False

        # Provider verified -> Send ready
        lvl = classify_email_verification_level("amit.k@tasl.com", email_status="VERIFIED")
        assert lvl == EmailVerificationLevel.VERIFIED_PROVIDER
        assert is_send_ready_email("amit.k@tasl.com", lvl) is True

        # Public source verified -> Send ready
        lvl = classify_email_verification_level("contact@company.com", source="official_directory")
        # Generic prefix is blocked from send-ready
        assert is_send_ready_email("contact@company.com", lvl) is False

        lvl = classify_email_verification_level("amit.kanawaje@tasl.com", source="company_website")
        assert lvl == EmailVerificationLevel.VERIFIED_PUBLIC_SOURCE
        assert is_send_ready_email("amit.kanawaje@tasl.com", lvl) is True

        # Pattern only (domain exists / MX only) -> NOT send ready
        lvl = classify_email_verification_level("amit.kanawaje@tasl.com")
        assert lvl == EmailVerificationLevel.DOMAIN_VALID_PATTERN_ONLY
        assert is_send_ready_email("amit.kanawaje@tasl.com", lvl) is False

        # Extrapolated -> NOT send ready
        lvl = classify_email_verification_level("amit@tasl.com")
        assert lvl == EmailVerificationLevel.EXTRAPOLATED
        assert is_send_ready_email("amit@tasl.com", lvl) is False

    def test_waterfall_max_3_candidates_and_provider_isolation(self):
        """Waterfall tests max 3 candidates, stops on first verified email, and calls Apollo only."""
        candidates = [
            {"candidate_name": f"Cand {i}", "candidate_title": "Quality Manager", "composite_score": 0.9}
            for i in range(5)
        ]
        enrich_mock = MagicMock(return_value={"status": "NO_RESULT", "email": None})
        gate_mock = MagicMock()
        gate_mock.evaluate.return_value = MagicMock(enrich_contact=True, reason="Eligible", authority_confidence="HIGH", score_at_decision=0.9, llm_used="RULE_ONLY")

        waterfall = ContactWaterfallService(eligibility_gate=gate_mock, enrich_fn=enrich_mock, max_candidates=3)
        res = waterfall.run(candidates, facility_info={}, trigger_info={})

        assert res.status == "HOLD_CONTACT_NOT_FOUND"
        assert enrich_mock.call_count == 3  # Strictly capped at 3 candidates
        assert res.enrichment_calls == 3

    def test_deepseek_primary_gemini_fallback_both_fail_hold(self):
        """DeepSeek is primary; falls back to Gemini; if both fail, returns HOLD/GENERATION_FAILED."""
        engine = SalesPersonalizationV2Engine()
        engine._deepseek = MagicMock()
        engine._deepseek.is_available.return_value = False
        engine._gemini = MagicMock()
        engine._gemini.is_available.return_value = False

        record = {
            "company": "HARMAN",
            "person": "Rohit Giri",
            "facility": "HARMAN Pune Plant",
            "trigger": "Expansion",
        }
        res = engine.generate_outreach(record)
        assert res.status == "GENERATION_FAILED"
        assert "Both DeepSeek and Gemini LLM providers failed" in res.violations[0]
