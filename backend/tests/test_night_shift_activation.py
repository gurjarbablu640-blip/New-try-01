"""Regression test suite for Night Shift Gemini activation, LinkedIn evidence hygiene,
Apollo renewal queueing, and CC-3963 claim safety.
"""
import json
import os
import unittest
from unittest.mock import MagicMock, patch

from config import settings
from services.fast_contact_waterfall import (
    FastContactWaterfallService,
    STATUS_DEFERRED_APOLLO_SUBSCRIPTION_INACTIVE,
    STATUS_PENDING_APOLLO_RENEWAL,
)
from services.llm_provider import (
    GeminiProvider,
    GeminiRateLimiter,
    LLMProviderNotAllowedError,
    QuotaExhaustedError,
    _normalize_gemini_model,
)
from services.outreach_claim_guard import OutreachClaimGuard
from services.settings_manager import _mask_secret, get_setting_value


class TestGeminiPrecedenceAndHygiene(unittest.TestCase):
    """Verify .env precedence, secret redaction, and activation guards."""

    def test_secret_masking_never_prints_full_key(self):
        secret = "AIzaSyTestSecretKeyForSalesoorjaTesting12345678"
        masked = _mask_secret(secret)
        self.assertNotIn("TestSecretKey", masked)
        self.assertTrue(masked.startswith("AIza"))
        self.assertTrue(masked.endswith("5678"))
        self.assertIn("••••••••", masked)

    def test_empty_secret_masking_returns_empty(self):
        self.assertEqual(_mask_secret(""), "")
        self.assertEqual(_mask_secret(None), "")

    def test_gemini_model_normalization(self):
        self.assertEqual(_normalize_gemini_model("gemini-3.1-flash-lite"), "gemini-3.1-flash-lite")
        self.assertEqual(_normalize_gemini_model("gemini-3.7-flash"), "gemini-3.7-flash")
        self.assertEqual(_normalize_gemini_model(""), "gemini-3.1-flash-lite")
        self.assertEqual(_normalize_gemini_model("gemini-2.0-flash"), "gemini-2.0-flash")

    def test_gemini_tool_calling_flag(self):
        provider = GeminiProvider(api_key="valid-dummy-key-longer-than-10")
        self.assertTrue(getattr(provider, "supports_tool_calling", False))
        self.assertTrue(getattr(provider, "supports_structured_json", False))

    def test_gemini_rate_limiter_ceilings(self):
        limiter = GeminiRateLimiter
        self.assertEqual(limiter.RPM_CEILING, 60)
        self.assertEqual(limiter.INPUT_TPM_CEILING, 100000)
        self.assertEqual(limiter.SAFETY_RPM, 50)
        self.assertEqual(limiter.SAFETY_INPUT_TPM, 90000)

    def test_gemini_rate_limiter_input_token_estimation(self):
        contents = [{"role": "user", "parts": [{"text": "A" * 400}]}]
        est = GeminiRateLimiter.estimate_input_tokens(contents, system_prompt="System instructions")
        self.assertGreater(est, 90)
        self.assertLess(est, 120)

    def test_gemini_rate_limiter_rejection_at_capacity(self):
        GeminiRateLimiter.reset_for_tests()
        # Acquire 50 requests (safety ceiling)
        for _ in range(50):
            acquired = GeminiRateLimiter.check_and_acquire(10)
            self.assertTrue(acquired)
        # 51st request must be rejected
        acquired_51 = GeminiRateLimiter.check_and_acquire(10)
        self.assertFalse(acquired_51)
        GeminiRateLimiter.reset_for_tests()

    def test_gemini_billing_mode_unverified_guard(self):
        provider = GeminiProvider(api_key="valid-dummy-key-longer-than-10")
        with patch("services.llm_provider.verify_provider_billing_mode", return_value=(False, "BILLING_UNVERIFIED")):
            with self.assertRaises(LLMProviderNotAllowedError):
                provider.complete(system_prompt="", messages=[{"role": "user", "content": "Hi"}])


class TestApolloNightModeAndQueue(unittest.TestCase):
    """Verify Apollo night mode deferred status, queue persistence, and dedup."""

    def setUp(self):
        self.test_log = "backend/data/runtime_state/test_apollo_query_log.json"
        self.test_cache = "backend/data/runtime_state/test_contact_cache.json"
        self.test_queue = "backend/data/runtime_state/test_apollo_pending_queue.json"
        for p in [self.test_log, self.test_cache, self.test_queue]:
            if os.path.exists(p):
                os.remove(p)
        self.service = FastContactWaterfallService(
            apollo_log_file=self.test_log,
            contact_cache_file=self.test_cache,
            pending_queue_file=self.test_queue,
        )

    def tearDown(self):
        for p in [self.test_log, self.test_cache, self.test_queue]:
            if os.path.exists(p):
                os.remove(p)

    def test_apollo_night_mode_defers_and_enqueues(self):
        candidate = {
            "company": "Tata Motors Ltd",
            "legal_company_name": "Tata Motors Limited",
            "official_domain": "tatamotors.com",
            "facility": "Sanand Plant",
            "facility_city": "Sanand",
            "trigger_to_facility": "DIRECT",
            "trigger_event_semantics_verified": True,
            "timing_class": "CURRENT",
            "lead_score": 98.0,
            "primary_person": {
                "name": "Rakesh Patel",
                "title": "Plant Quality Head",
                "authority_classification": "STRONG_PLANT_QUALITY_OWNER",
                "person_confidence": "HIGH",
                "current_employment": "VERIFIED",
                "facility_relationship": "FACILITY_FUNCTION_OWNER",
            }
        }

        # Under night mode (APOLLO_ENABLED_FOR_LIVE_LOOKUP = False)
        with patch("services.fast_contact_waterfall.get_setting_value", side_effect=lambda k, d=None: False if k == "APOLLO_ENABLED_FOR_LIVE_LOOKUP" else d):
            res = self.service.enrich_with_apollo(candidate)

        self.assertEqual(res["status"], STATUS_DEFERRED_APOLLO_SUBSCRIPTION_INACTIVE)
        self.assertEqual(res["lookup_priority"], "P1")
        self.assertEqual(res["apollo_live_calls_made"], 0)
        self.assertEqual(res["credits_consumed"], 0)
        self.assertEqual(res["queue_status"], STATUS_PENDING_APOLLO_RENEWAL)

        # Verify queue was written to disk
        self.assertTrue(os.path.exists(self.test_queue))
        with open(self.test_queue, "r") as f:
            queue_items = json.load(f)
        self.assertEqual(len(queue_items), 1)
        self.assertEqual(queue_items[0]["person_name"], "Rakesh Patel")
        self.assertEqual(queue_items[0]["lookup_priority"], "P1")

    def test_apollo_queue_deduplication(self):
        candidate = {
            "company": "Tata Motors Ltd",
            "legal_company_name": "Tata Motors Limited",
            "official_domain": "tatamotors.com",
            "facility": "Sanand Plant",
            "facility_city": "Sanand",
            "trigger_to_facility": "DIRECT",
            "trigger_event_semantics_verified": True,
            "timing_class": "CURRENT",
            "lead_score": 98.0,
            "primary_person": {
                "name": "Rakesh Patel",
                "title": "Plant Quality Head",
                "authority_classification": "STRONG_PLANT_QUALITY_OWNER",
                "person_confidence": "HIGH",
                "current_employment": "VERIFIED",
                "facility_relationship": "FACILITY_FUNCTION_OWNER",
            }
        }
        with patch("services.fast_contact_waterfall.get_setting_value", return_value=False):
            self.service.enrich_with_apollo(candidate)
            self.service.enrich_with_apollo(candidate)

        with open(self.test_queue, "r") as f:
            queue_items = json.load(f)
        # Should be deduplicated to 1 item
        self.assertEqual(len(queue_items), 1)


class TestOutreachClaimGuardAndSemanticSafety(unittest.TestCase):
    """Verify rejection of 48-hour turnarounds and CC-3963 standard mischaracterization."""

    def setUp(self):
        self.guard = OutreachClaimGuard()

    def test_rejects_unsupported_48_hour_turnaround(self):
        copy = "We provide rapid 48-hour turnaround on all torque and pressure calibration."
        report = self.guard.audit_outreach_claims(copy)
        self.assertFalse(report.clean)
        self.assertTrue(report.unapproved_slas_detected)
        self.assertTrue(any("48-hour turnaround" in v.rule_description for v in report.violations))

    def test_rejects_mischaracterizing_cc3963_as_customer_standard(self):
        copy = "Your manufacturing lines must comply with NABL CC-3963 standards."
        report = self.guard.audit_outreach_claims(copy)
        self.assertFalse(report.clean)
        self.assertTrue(any(v.category == "MISCHARACTERIZED_STANDARD" for v in report.violations))

    def test_accepts_authoritative_cc3963_laboratory_accreditation(self):
        copy = (
            "Oorja Technical Services operates an ISO/IEC 17025:2017 accredited calibration laboratory "
            "(NABL Certificate No. CC-3963) with certified testing scope."
        )
        report = self.guard.audit_outreach_claims(copy)
        self.assertTrue(report.clean)
        self.assertEqual(len(report.violations), 0)


if __name__ == "__main__":
    unittest.main()
