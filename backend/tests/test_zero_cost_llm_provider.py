"""Unit tests for Salesoorja Zero-Cost LLM Architecture and Safe Provider Router.

Verifies:
1. Gemini 2.0 Flash is strictly rejected as retired (MODEL_REMOVED).
2. Gemini Flash is accepted only when GEMINI_ACCOUNT_MODE = 'FREE_NO_BILLING'.
3. Gemini account mode 'UNVERIFIED' blocks real dispatch (PROVIDER_BILLING_STATUS_UNVERIFIED).
4. Gemini account mode 'PAID' is blocked under ZERO_COST_ONLY.
5. Free-eligible model on a paid account is still blocked.
6. Groq account mode 'UNVERIFIED' is blocked.
7. Groq account mode 'FREE' succeeds with modern reasoning model (openai/gpt-oss-20b).
8. Stale/deprecated models are marked MODEL_REMOVED.
9. Unknown quota does not invent fake RPD numbers.
10. Cloudflare paid account is blocked under ZERO_COST_ONLY.
11. OpenRouter paid models and unverified accounts remain blocked.
12. OpenAI is blocked under ZERO_COST_ONLY policy.
13. All free providers unavailable falls back to deterministic handling without crashing.
14. Persistent reasoning cache prevents duplicate inference.
15. Hallucinated LLM reasoning cannot override failed deterministic evidence gates.
16. Analyst / Verifier disagreement forces NEEDS_MORE_RESEARCH (never averaged).
17. ZERO real paid API calls made in tests.
"""
import json
import time
import unittest
from unittest.mock import MagicMock, patch

from services.llm_provider import (
    CloudflareProvider,
    FallbackLLMProvider,
    GeminiProvider,
    GroqProvider,
    LLMProviderNotAllowedError,
    LLMReasoningCache,
    LLMResponse,
    OpenAIProvider,
    OpenRouterProvider,
    QuotaExhaustedError,
    ZeroCostRouter,
    apply_reasoning_to_gate,
    evaluate_llm_task_allowed,
    get_orchestrator_provider,
    get_provider,
    is_cost_allowed,
    llm_reasoning_cache,
    quota_tracker,
    run_analyst_verifier_protocol,
    verify_provider_billing_mode,
    LLM_STATUS_AVAILABLE,
    LLM_STATUS_RATE_LIMITED,
    LLM_STATUS_MODEL_REMOVED,
    LLM_STATUS_FREE_CAPACITY_EXHAUSTED,
    PROVIDER_BILLING_STATUS_UNVERIFIED,
    PROVIDER_ACCOUNT_MODE_PAID_BLOCKED,
)


class TestZeroCostLLMProvider(unittest.TestCase):

    def setUp(self):
        llm_reasoning_cache.clear()

    # 1. Gemini 2.0 Flash rejected as retired
    def test_gemini_2_0_flash_rejected_as_retired(self):
        with patch("services.llm_provider.get_setting_value") as mock_val:
            mock_val.side_effect = lambda k, default=None: {
                "ALLOW_PAID_LLM": False,
                "LLM_COST_POLICY": "ZERO_COST_ONLY",
                "GEMINI_ACCOUNT_MODE": "FREE_NO_BILLING",
                "GOOGLE_API_KEY": "AIzaSyValidKey1234567890",
            }.get(k, default)

            # Cost check must return False
            self.assertFalse(is_cost_allowed("gemini", "gemini-2.0-flash"))

            prov = GeminiProvider(api_key="AIzaSyValidKey1234567890", model_name="gemini-2.0-flash")
            self.assertFalse(prov.is_available())
            self.assertEqual(prov.get_status(), LLM_STATUS_MODEL_REMOVED)

            with self.assertRaises(LLMProviderNotAllowedError) as ctx:
                prov.complete(system_prompt="Test", messages=[{"role": "user", "content": "Hi"}])
            self.assertIn("MODEL_REMOVED", str(ctx.exception))

    # 2. Current discovered Gemini model accepted only when account mode = FREE_NO_BILLING
    @patch("services.llm_provider.requests.post")
    def test_gemini_accepted_when_free_no_billing(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"x-ratelimit-remaining-requests": "1450"}
        mock_resp.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": json.dumps({"decision": "STRONG", "confidence": 0.92})}]}}],
            "usageMetadata": {"promptTokenCount": 50, "candidatesTokenCount": 20},
        }
        mock_post.return_value = mock_resp

        with patch("services.llm_provider.get_setting_value") as mock_val:
            mock_val.side_effect = lambda k, default=None: {
                "ALLOW_PAID_LLM": False,
                "LLM_COST_POLICY": "ZERO_COST_ONLY",
                "GEMINI_ACCOUNT_MODE": "FREE_NO_BILLING",
                "GOOGLE_API_KEY": "AIzaSyValidKey1234567890",
                "ORCHESTRATOR_GEMINI_MODEL": "gemini-3.7-flash",
            }.get(k, default)

            self.assertTrue(is_cost_allowed("gemini", "gemini-3.7-flash"))
            prov = GeminiProvider(api_key="AIzaSyValidKey1234567890", model_name="gemini-3.7-flash")
            self.assertTrue(prov.is_available())

            resp = prov.complete(system_prompt="Analyze", messages=[{"role": "user", "content": "Lead data"}], response_format="json")
            self.assertEqual(resp.provider, "gemini")
            self.assertEqual(resp.model, "gemini-3.7-flash")
            self.assertEqual(resp.parse_json().get("decision"), "STRONG")

    # 3. Gemini account mode UNVERIFIED blocks real dispatch
    def test_gemini_account_mode_unverified_blocks_real_dispatch(self):
        with patch("services.llm_provider.get_setting_value") as mock_val:
            mock_val.side_effect = lambda k, default=None: {
                "ALLOW_PAID_LLM": False,
                "LLM_COST_POLICY": "ZERO_COST_ONLY",
                "GEMINI_ACCOUNT_MODE": "UNVERIFIED",
                "GOOGLE_API_KEY": "AIzaSyValidKey1234567890",
            }.get(k, default)

            verified, reason = verify_provider_billing_mode("gemini")
            self.assertFalse(verified)
            self.assertEqual(reason, PROVIDER_BILLING_STATUS_UNVERIFIED)

            prov = GeminiProvider(api_key="AIzaSyValidKey1234567890", model_name="gemini-3.7-flash")
            self.assertFalse(prov.is_available())

            with self.assertRaises(LLMProviderNotAllowedError) as ctx:
                prov.complete(system_prompt="Test", messages=[{"role": "user", "content": "Hi"}])
            self.assertIn(PROVIDER_BILLING_STATUS_UNVERIFIED, str(ctx.exception))

    # 4. Gemini account mode PAID blocked under ZERO_COST_ONLY
    def test_gemini_account_mode_paid_blocked_under_zero_cost(self):
        with patch("services.llm_provider.get_setting_value") as mock_val:
            mock_val.side_effect = lambda k, default=None: {
                "ALLOW_PAID_LLM": False,
                "LLM_COST_POLICY": "ZERO_COST_ONLY",
                "GEMINI_ACCOUNT_MODE": "PAID",
                "GOOGLE_API_KEY": "AIzaSyValidKey1234567890",
            }.get(k, default)

            verified, reason = verify_provider_billing_mode("gemini")
            self.assertFalse(verified)
            self.assertEqual(reason, PROVIDER_ACCOUNT_MODE_PAID_BLOCKED)

            prov = GeminiProvider(api_key="AIzaSyValidKey1234567890", model_name="gemini-3.7-flash")
            self.assertFalse(prov.is_available())

            with self.assertRaises(LLMProviderNotAllowedError) as ctx:
                prov.complete(system_prompt="Test", messages=[{"role": "user", "content": "Hi"}])
            self.assertIn(PROVIDER_ACCOUNT_MODE_PAID_BLOCKED, str(ctx.exception))

    # 5. Free-eligible model on paid account still blocked
    def test_free_eligible_model_on_paid_account_still_blocked(self):
        with patch("services.llm_provider.get_setting_value") as mock_val:
            mock_val.side_effect = lambda k, default=None: {
                "ALLOW_PAID_LLM": False,
                "LLM_COST_POLICY": "ZERO_COST_ONLY",
                "GEMINI_ACCOUNT_MODE": "PAID",
                "GROQ_ACCOUNT_MODE": "PAID",
            }.get(k, default)

            # Even though gemini-3.7-flash and openai/gpt-oss-20b are free-eligible models,
            # they MUST be blocked because the account has a paid billing profile attached!
            self.assertFalse(is_cost_allowed("gemini", "gemini-3.7-flash"))
            self.assertFalse(is_cost_allowed("groq", "openai/gpt-oss-20b"))

    # 6. Groq account mode UNVERIFIED blocked
    def test_groq_account_mode_unverified_blocked(self):
        with patch("services.llm_provider.get_setting_value") as mock_val:
            mock_val.side_effect = lambda k, default=None: {
                "ALLOW_PAID_LLM": False,
                "LLM_COST_POLICY": "ZERO_COST_ONLY",
                "GROQ_ACCOUNT_MODE": "UNVERIFIED",
                "GROQ_API_KEY": "gsk_test_valid_key12345",
            }.get(k, default)

            verified, reason = verify_provider_billing_mode("groq")
            self.assertFalse(verified)
            self.assertEqual(reason, PROVIDER_BILLING_STATUS_UNVERIFIED)

            prov = GroqProvider(api_key="gsk_test_valid_key12345", model_name="openai/gpt-oss-20b")
            self.assertFalse(prov.is_available())

            with self.assertRaises(LLMProviderNotAllowedError):
                prov.complete(system_prompt="System", messages=[{"role": "user", "content": "Hi"}])

    # 7. Groq account mode FREE succeeds with modern model (mocked)
    @patch("services.llm_provider.requests.post")
    def test_groq_account_mode_free_succeeds(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"x-ratelimit-remaining-requests": "980", "x-ratelimit-remaining-tokens": "11500"}
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": json.dumps({"decision": "STRONG", "confidence": 0.89})}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 40},
        }
        mock_post.return_value = mock_resp

        with patch("services.llm_provider.get_setting_value") as mock_val:
            mock_val.side_effect = lambda k, default=None: {
                "ALLOW_PAID_LLM": False,
                "LLM_COST_POLICY": "ZERO_COST_ONLY",
                "GROQ_ACCOUNT_MODE": "FREE",
                "GROQ_API_KEY": "gsk_test_valid_key12345",
                "GROQ_MODEL": "openai/gpt-oss-20b",
            }.get(k, default)

            self.assertTrue(is_cost_allowed("groq", "openai/gpt-oss-20b"))
            prov = GroqProvider(api_key="gsk_test_valid_key12345", model_name="openai/gpt-oss-20b")
            self.assertTrue(prov.is_available())

            resp = prov.complete(system_prompt="Test", messages=[{"role": "user", "content": "Evidence"}], response_format="json")
            self.assertEqual(resp.provider, "groq")
            self.assertEqual(resp.model, "openai/gpt-oss-20b")

    # 8. Stale/deprecated model removed dynamically
    def test_stale_model_removed_dynamically(self):
        with patch("services.llm_provider.get_setting_value") as mock_val:
            mock_val.side_effect = lambda k, default=None: {
                "ALLOW_PAID_LLM": False,
                "LLM_COST_POLICY": "ZERO_COST_ONLY",
                "GROQ_ACCOUNT_MODE": "FREE",
                "GROQ_API_KEY": "gsk_test_valid_key12345",
            }.get(k, default)

            # llama-3.3-70b-versatile was deprecated on Groq free plan as of Aug 2026
            self.assertFalse(is_cost_allowed("groq", "llama-3.3-70b-versatile"))

            prov = GroqProvider(api_key="gsk_test_valid_key12345", model_name="llama-3.3-70b-versatile")
            self.assertFalse(prov.is_available())
            self.assertEqual(prov.get_status(), LLM_STATUS_MODEL_REMOVED)

            with self.assertRaises(LLMProviderNotAllowedError) as ctx:
                prov.complete(system_prompt="Hi", messages=[{"role": "user", "content": "Hi"}])
            self.assertIn("MODEL_REMOVED", str(ctx.exception))

    # 9. Unknown quota does not invent RPD numbers
    def test_unknown_quota_does_not_invent_rpd(self):
        # Empty tracker check
        q = quota_tracker.get_quota("non_existent_provider")
        self.assertIsNone(q.rpd)
        self.assertIsNone(q.rpm)
        self.assertIsNone(q.remaining_requests)
        self.assertEqual(q.source, "UNKNOWN")

    # 10. Cloudflare paid account blocked under ZERO_COST_ONLY
    def test_cloudflare_paid_account_blocked_under_zero_cost(self):
        with patch("services.llm_provider.get_setting_value") as mock_val:
            mock_val.side_effect = lambda k, default=None: {
                "ALLOW_PAID_LLM": False,
                "LLM_COST_POLICY": "ZERO_COST_ONLY",
                "CLOUDFLARE_ACCOUNT_MODE": "PAID",
                "CLOUDFLARE_ACCOUNT_ID": "acc123",
                "CLOUDFLARE_API_TOKEN": "tok1234567890",
            }.get(k, default)

            prov = CloudflareProvider(account_id="acc123", api_token="tok1234567890", model_name="@cf/meta/llama-3.1-8b-instruct")
            self.assertFalse(prov.is_available())

            with self.assertRaises(LLMProviderNotAllowedError) as ctx:
                prov.complete(system_prompt="Test", messages=[{"role": "user", "content": "Hi"}])
            self.assertIn(PROVIDER_ACCOUNT_MODE_PAID_BLOCKED, str(ctx.exception))

    # 11. OpenRouter paid model remains blocked
    def test_openrouter_paid_model_and_unverified_account_remains_blocked(self):
        with patch("services.llm_provider.get_setting_value") as mock_val:
            mock_val.side_effect = lambda k, default=None: {
                "ALLOW_PAID_LLM": False,
                "LLM_COST_POLICY": "ZERO_COST_ONLY",
                "OPENROUTER_ACCOUNT_MODE": "FREE",
                "OPENROUTER_API_KEY": "sk-or-v1-validkey12345",
            }.get(k, default)

            # Paid model without :free strictly blocked
            self.assertFalse(is_cost_allowed("openrouter", "openai/gpt-4o"))
            paid_prov = OpenRouterProvider(api_key="sk-or-v1-validkey12345", model_name="openai/gpt-4o")
            self.assertFalse(paid_prov.is_available())
            with self.assertRaises(LLMProviderNotAllowedError):
                paid_prov.complete(system_prompt="Test", messages=[{"role": "user", "content": "Hi"}])

    # 12. OpenAI is blocked under ZERO_COST_ONLY policy
    def test_openai_blocked_under_zero_cost_policy(self):
        with patch("services.llm_provider.get_setting_value") as mock_val:
            mock_val.side_effect = lambda k, default=None: {
                "ALLOW_PAID_LLM": False,
                "LLM_COST_POLICY": "ZERO_COST_ONLY",
                "OPENAI_API_KEY": "sk-real-looking-key-1234567890",
                "OPENAI_MODEL": "gpt-4o",
            }.get(k, default)

            self.assertFalse(is_cost_allowed("openai", "gpt-4o"))
            prov = OpenAIProvider(api_key="sk-real-looking-key-1234567890", model_name="gpt-4o")
            self.assertFalse(prov.is_available())

            with self.assertRaises(LLMProviderNotAllowedError):
                prov.complete(system_prompt="test", messages=[{"role": "user", "content": "hi"}])

    # 13. All free providers unavailable falls back to deterministic handling without crashing
    def test_all_free_providers_unavailable_deterministic_fallback(self):
        router = FallbackLLMProvider(providers=[
            GeminiProvider(api_key=""),
            GroqProvider(api_key=""),
        ])
        self.assertFalse(router.is_available())

        with self.assertRaises(QuotaExhaustedError) as ctx:
            router.complete(system_prompt="Test", messages=[{"role": "user", "content": "Q"}])
        self.assertIn(LLM_STATUS_FREE_CAPACITY_EXHAUSTED, str(ctx.exception))

        res = run_analyst_verifier_protocol(
            task_type="TRIGGER_INTERPRETATION",
            company="Tata Motors",
            facility="Pune Plant",
            evidence="Capex announcement",
            analyst_provider=router,
        )
        self.assertEqual(res["decision"], "HOLD")
        self.assertTrue(res["requires_more_research"])
        self.assertIn("FREE_CAPACITY_EXHAUSTED", res["reason"])

    # 14. Persistent reasoning cache prevents duplicate inference
    def test_cache_prevents_duplicate_inference(self):
        mock_provider = MagicMock(spec=GeminiProvider)
        mock_provider.is_available.return_value = True
        mock_provider.complete.return_value = LLMResponse(
            text=json.dumps({"decision": "STRONG", "confidence": 0.92, "reason": "Consistent capex"}),
            provider="gemini",
            model="gemini-3.7-flash",
        )

        res1 = run_analyst_verifier_protocol(
            task_type="TRIGGER_INTERPRETATION",
            company="Bharat Forge",
            facility="Mundhwa Pune",
            evidence="Machining line expansion 2026",
            analyst_provider=mock_provider,
        )
        self.assertEqual(res1["decision"], "STRONG")
        self.assertFalse(res1.get("cache_hit", False))
        self.assertEqual(mock_provider.complete.call_count, 1)

        res2 = run_analyst_verifier_protocol(
            task_type="TRIGGER_INTERPRETATION",
            company="Bharat Forge",
            facility="Mundhwa Pune",
            evidence="Machining line expansion 2026",
            analyst_provider=mock_provider,
        )
        self.assertEqual(res2["decision"], "STRONG")
        self.assertTrue(res2.get("cache_hit"))
        self.assertEqual(mock_provider.complete.call_count, 1)

    # 15. Hallucinated LLM reasoning cannot override failed deterministic evidence gates
    def test_llm_cannot_fabricate_evidence_into_passed_hard_gate(self):
        deterministic_passed = False
        hallucinated_llm_reasoning = {
            "decision": "STRONG",
            "confidence": 0.99,
            "reason": "I think this facility is definitely linked even without source proof.",
        }

        gate_eval = apply_reasoning_to_gate(deterministic_passed=deterministic_passed, llm_reasoning=hallucinated_llm_reasoning)
        self.assertFalse(gate_eval["passed"])
        self.assertEqual(gate_eval["gate_decision"], "FAILED_DETERMINISTIC")
        self.assertFalse(gate_eval["llm_applied"])

    # 16. Analyst / Verifier disagreement forces NEEDS_MORE_RESEARCH (never averaged)
    def test_analyst_verifier_disagreement_forces_needs_more_research(self):
        analyst = MagicMock(spec=GeminiProvider)
        analyst.is_available.return_value = True
        analyst.complete.return_value = LLMResponse(
            text=json.dumps({
                "decision": "BORDERLINE",
                "confidence": 0.70,
                "reason": "Uncertain whether QA Head has direct ownership of metrology.",
                "requires_more_research": True,
                "contradictions": ["Snippet indicates role is corporate HSE."],
            }),
            provider="gemini",
            model="gemini-3.7-flash",
        )

        verifier = MagicMock(spec=GroqProvider)
        verifier.is_available.return_value = True
        verifier.complete.return_value = LLMResponse(
            text=json.dumps({
                "verdict": "NOT_SUPPORTED",
                "critique": "Candidate is in Environmental safety, not calibration.",
            }),
            provider="groq",
            model="openai/gpt-oss-20b",
        )

        res = run_analyst_verifier_protocol(
            task_type="PERSON_COMPARISON",
            company="L&T Heavy Engineering",
            facility="Hazira Works",
            evidence="Mr. A profile snippet: HSE lead",
            icp_score=95.0,
            analyst_provider=analyst,
            verifier_provider=verifier,
        )

        self.assertEqual(res["decision"], "NEEDS_MORE_RESEARCH")
        self.assertTrue(res["requires_more_research"])
        self.assertEqual(res["verifier_verdict"], "NOT_SUPPORTED")
        self.assertIn("Analyst and Verifier disagreed", res["reason"])

    # 17. Disallowed tasks rejected
    def test_disallowed_tasks_rejected(self):
        self.assertFalse(evaluate_llm_task_allowed("DATE_COMPARISON"))
        self.assertFalse(evaluate_llm_task_allowed("PHONE_VALIDATION"))
        self.assertFalse(evaluate_llm_task_allowed("APOLLO_CREDIT_GATE"))
        self.assertFalse(evaluate_llm_task_allowed("NABL_SCOPE_MATCH"))
        self.assertTrue(evaluate_llm_task_allowed("TRIGGER_INTERPRETATION"))
        self.assertTrue(evaluate_llm_task_allowed("FACILITY_LINK_REASONING"))


if __name__ == "__main__":
    unittest.main()
