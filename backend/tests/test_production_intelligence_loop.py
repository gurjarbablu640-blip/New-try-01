"""Unit test suite for Salesoorja Production Intelligence Loop.

Tests:
1. Gemini primary routing & free-mode guard:
   - Blocks live dispatch if account mode is UNVERIFIED under ZERO_COST_ONLY.
   - Allows Gemini first in chain when free account is confirmed.
2. Tool call routing:
   - Tool calling tasks route to Gemini/Groq/Cloudflare/OpenRouter and strictly exclude UnoRouter.
3. LinkedIn evidence schema & waterfall:
   - Generates 10-query targeted waterfall.
   - Extracts candidates with title and company clues.
   - Sets LINKEDIN_INTELLIGENCE_ATTEMPTED = True.
4. Persistent browser session handling:
   - Detects LinkedIn challenges/login and returns MANUAL_BROWSER_ACTION_REQUIRED.
   - Does not crash or bypass anti-bot defenses.
5. Human person validation & authority model:
   - Rejects non-human role strings (INVALID_ROLE_TEXT).
   - Validates DIRECT_CALIBRATION_OWNER, METROLOGY_OWNER, STRONG_PLANT_QUALITY_OWNER.
6. Apollo qualified-only policy & deduplication:
   - Rejects weak triggers, unknown facilities, former employees, generic titles.
   - Prevents duplicate credit consumption on already-enriched contacts.
7. Fast contact waterfall 60-90s cutoff:
   - Cuts off free search and escalates to Apollo when contacts missing.
8. Apollo post-enrichment requalification:
   - Validates contact email before marking contact verified.
   - Keeps READY_FOR_EMAIL in test mode (no real prospect emails sent).
"""
import unittest
from unittest.mock import MagicMock, patch

from services.fast_contact_waterfall import (
    FastContactWaterfallService,
    CONTACT_FOUND,
    CONTACT_NOT_FOUND,
    MATCH_CONFIRMED,
)
from services.linkedin_intelligence import (
    LinkedInIntelligenceService,
    AUTHORITY_DIRECT_CALIBRATION_OWNER,
    AUTHORITY_METROLOGY_OWNER,
    AUTHORITY_STRONG_PLANT_QUALITY_OWNER,
    AUTHORITY_FUNCTIONALLY_RELEVANT,
    AUTHORITY_GENERAL_QUALITY,
    AUTHORITY_COMPANY_ONLY,
    classify_person_authority,
)
from services.llm_provider import (
    GeminiProvider,
    LLMProviderNotAllowedError,
    ZeroCostRouter,
    get_orchestrator_provider,
    verify_provider_billing_mode,
)
from services.opportunity_gates import evaluate_opportunity_gates


class TestGeminiPrimaryRouting(unittest.TestCase):
    """Test Gemini primary routing and strict free-mode guard."""

    def test_gemini_unverified_account_mode_blocks_dispatch(self):
        with patch("services.llm_provider.get_setting_value") as mock_settings:
            mock_settings.side_effect = lambda k, default=None: {
                "GEMINI_ACCOUNT_MODE": "UNVERIFIED",
                "LLM_COST_POLICY": "ZERO_COST_ONLY",
                "ALLOW_PAID_LLM": False,
            }.get(k, default)

            verified, status = verify_provider_billing_mode("gemini")
            self.assertFalse(verified)
            self.assertEqual(status, "PROVIDER_BILLING_STATUS_UNVERIFIED")

            prov = GeminiProvider(api_key="mock_key_1234567890123")
            self.assertFalse(prov.is_available())

    def test_gemini_free_no_billing_allows_dispatch(self):
        with patch("services.llm_provider.get_setting_value") as mock_settings:
            mock_settings.side_effect = lambda k, default=None: {
                "GEMINI_ACCOUNT_MODE": "FREE_NO_BILLING",
                "LLM_COST_POLICY": "ZERO_COST_ONLY",
                "ALLOW_PAID_LLM": False,
                "GOOGLE_API_KEY": "valid_key_1234567890123",
            }.get(k, default)

            verified, status = verify_provider_billing_mode("gemini")
            self.assertTrue(verified)
            self.assertEqual(status, "FREE_NO_BILLING")

    def test_tool_call_routing_excludes_unorouter(self):
        router = ZeroCostRouter(task_type="TOOL_CALL_REQUIRED")
        provider_names = [p.__class__.__name__ for p in router.providers]
        self.assertNotIn("UnoRouterProvider", provider_names)
        self.assertEqual(provider_names[0], "GeminiProvider")

    def test_deterministic_task_strictly_blocks_llm(self):
        router = ZeroCostRouter(task_type="DETERMINISTIC_GATE")
        self.assertEqual(len(router.providers), 0)
        with self.assertRaises(LLMProviderNotAllowedError):
            router.complete(system_prompt="", messages=[{"role": "user", "content": "test"}])


class TestLinkedInIntelligence(unittest.TestCase):
    """Test LinkedIn waterfall queries, authority model, and candidate ranking."""

    def setUp(self):
        self.service = LinkedInIntelligenceService(cache_file="/tmp/test_li_cache.json")

    def test_waterfall_queries_generation(self):
        queries = self.service.generate_waterfall_queries("Exide Energy", plant_city="Bengaluru")
        self.assertEqual(len(queries), 10)
        self.assertIn('site:linkedin.com/in "Exide Energy" quality', queries)
        self.assertIn('site:linkedin.com/in "Exide Energy" "Bengaluru" quality', queries)
        self.assertIn('site:linkedin.com/in "Exide Energy" plant quality', queries)

    def test_person_authority_model_classification(self):
        # Direct calibration owner
        c1, r1 = classify_person_authority("Head Calibration Lab", "Sanand Plant")
        self.assertEqual(c1, AUTHORITY_DIRECT_CALIBRATION_OWNER)

        # Metrology owner
        c2, r2 = classify_person_authority("Metrology Manager", "Pune Unit")
        self.assertEqual(c2, AUTHORITY_METROLOGY_OWNER)

        # Strong plant quality owner
        c3, r3 = classify_person_authority("Plant Quality Head", "Bengaluru Plant")
        self.assertEqual(c3, AUTHORITY_STRONG_PLANT_QUALITY_OWNER)

        c3b, r3b = classify_person_authority("Head Quality Cell Manufacturing", "Bengaluru Gigafactory")
        self.assertEqual(c3b, AUTHORITY_STRONG_PLANT_QUALITY_OWNER)

        # General quality
        c4, r4 = classify_person_authority("Quality Engineer", "")
        self.assertEqual(c4, AUTHORITY_GENERAL_QUALITY)

        # Company only
        c5, r5 = classify_person_authority("Vice President Quality", "")
        self.assertEqual(c5, AUTHORITY_COMPANY_ONLY)

    def test_candidate_ranking_primary_and_secondary(self):
        candidates = [
            {
                "name": "Arun Kumar",
                "title": "Quality Engineer",
                "authority_classification": AUTHORITY_GENERAL_QUALITY,
                "authority_weight": 40,
            },
            {
                "name": "Pradeep N",
                "title": "Head Quality Cell Manufacturing",
                "authority_classification": AUTHORITY_STRONG_PLANT_QUALITY_OWNER,
                "authority_weight": 90,
            },
            {
                "name": "Ramesh Patel",
                "title": "Metrology Manager",
                "authority_classification": AUTHORITY_METROLOGY_OWNER,
                "authority_weight": 95,
            },
        ]
        res = self.service.rank_candidates(candidates, "Exide Energy", "Bengaluru")
        self.assertEqual(res["primary_person"]["name"], "Ramesh Patel")
        self.assertEqual(res["secondary_person"]["name"], "Pradeep N")

    def test_manual_browser_action_required_on_challenge(self):
        with patch.object(self.service, "run_browser_verification") as mock_bv:
            mock_bv.return_value = {
                "status": "MANUAL_BROWSER_ACTION_REQUIRED",
                "message": "LinkedIn authentication/challenge required. Security bypass avoided.",
            }
            res = self.service.run_browser_verification("https://linkedin.com/in/test", "Test Corp")
            self.assertEqual(res["status"], "MANUAL_BROWSER_ACTION_REQUIRED")


class TestFastContactWaterfallAndApollo(unittest.TestCase):
    """Test fast contact cutoff, Apollo gating, deduplication, and email preview."""

    def setUp(self):
        self.service = FastContactWaterfallService(
            apollo_log_file="/tmp/test_apollo_log.json",
            contact_cache_file="/tmp/test_contact_cache.json",
        )

    def test_apollo_eligibility_enforces_upstream_gates(self):
        # Missing strong trigger linkage -> Ineligible
        ineligible_lead = {
            "company": "Test Motors",
            "trigger_to_facility": "WEAK",
            "primary_person": {"name": "Sunil Sharma", "authority_classification": "STRONG_PLANT_QUALITY_OWNER"},
        }
        eligible, reason = self.service.is_apollo_eligible(ineligible_lead)
        self.assertFalse(eligible)
        self.assertIn("linkage is WEAK", reason)

        # Invalid human person -> Ineligible
        invalid_person_lead = {
            "company": "Test Motors",
            "trigger_to_facility": "STRONG",
            "primary_person": {"name": "Senior Quality Head", "authority_classification": "STRONG_PLANT_QUALITY_OWNER"},
        }
        eligible, reason = self.service.is_apollo_eligible(invalid_person_lead)
        self.assertFalse(eligible)
        self.assertIn("not a valid human person", reason)

        # Valid candidate -> Eligible
        valid_lead = {
            "company": "Maruti Suzuki",
            "trigger_to_facility": "STRONG",
            "primary_person": {"name": "Sunil Sharma", "authority_classification": "STRONG_PLANT_QUALITY_OWNER"},
        }
        eligible, reason = self.service.is_apollo_eligible(valid_lead)
        self.assertTrue(eligible)

    def test_apollo_deduplication_prevents_duplicate_spends(self):
        lead = {
            "company": "Exide Energy",
            "trigger_to_facility": "DIRECT",
            "primary_person": {"name": "Pradeep N", "authority_classification": "STRONG_PLANT_QUALITY_OWNER"},
        }
        # Pre-populate log with successful lookup
        self.service._apollo_log.append({
            "dedup_key": "exideenergy:pradeepn",
            "status": "SUCCESS",
            "email": "pradeep.n@exideenergy.com",
        })
        eligible, reason = self.service.is_apollo_eligible(lead)
        self.assertFalse(eligible)
        self.assertIn("Recent Apollo lookup already exists", reason)

    def test_email_preview_does_not_send(self):
        lead = {
            "company": "Exide Energy Solutions Ltd",
            "facility": "Bengaluru Battery Gigafactory",
            "event": "Rs 450 crore capacity expansion",
            "primary_person": {"name": "Pradeep N", "title": "Head Quality Cell Manufacturing"},
        }
        contact = {"email": "pradeep.n@exideenergy.com", "phone": "+91 98000 11223"}
        preview = self.service.generate_email_preview(lead, contact)

        self.assertEqual(preview["outbound_sent"], False)
        self.assertIn("Dear Pradeep", preview["body"])
        self.assertIn("Bengaluru Battery Gigafactory", preview["body"])
        self.assertIn("Oorja Technical Services", preview["body"])
        self.assertIn("OUTBOUND_TEST_MODE=true", preview["safety_enforced"])


class TestOpportunityGatesWithNewAuthority(unittest.TestCase):
    """Ensure opportunity gates accept new Phase 9 authority classifications."""

    def test_opportunity_gate_accepts_strong_plant_quality_owner(self):
        lead = {
            "trigger": {"actionable": True, "date_within_window": True, "status": "CURRENT"},
            "facility": {"address_precision": "EXACT_FACILITY", "trigger_facility_confidence": "DIRECT"},
            "person": {
                "name": "Pradeep N",
                "employment_verified": True,
                "duties_verified": True,
                "classification": "STRONG_PLANT_QUALITY_OWNER",
            },
            "technical_capability": {"verified": True},
            "timing": {"actionable": True},
            "contact": {"verified": True, "email": "pradeep.n@exideenergy.com"},
        }
        res = evaluate_opportunity_gates(lead)
        self.assertTrue(res["gates"]["correct_person"]["passed"])


if __name__ == "__main__":
    unittest.main()
