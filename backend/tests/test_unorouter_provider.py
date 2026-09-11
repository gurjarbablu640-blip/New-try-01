"""Unit tests for UnoRouter zero-cost LLM provider integration.

Verifies:
1. Free-model allowlist: 'glm-5.3-search:free' is permitted under ZERO_COST_ONLY.
2. Paid-route rejection: 'glm-5.3-search' (without :free) or paid models are blocked.
3. UNOROUTER_ACCOUNT_MODE = 'PAID' blocks provider dispatch.
4. Missing or placeholder API key renders provider unavailable.
5. HTTP 401 raises authentication RuntimeError without exposing secrets.
6. HTTP 402 immediately blocks the provider from further dispatch.
7. HTTP 429 raises QuotaExhaustedError and tracks retry-after / rate limits.
8. Request timeout raises RuntimeError with clean error message.
9. Malformed JSON response raises RuntimeError.
10. Reasoning cache hashes provider, model, system, and user prompt.
11. ZeroCostRouter prioritizes UnoRouter as #1 and fails over cleanly.
12. Secret redaction: API key is never exposed in errors or representations.
"""
import json
import unittest
from unittest.mock import MagicMock, patch
import requests

from services.llm_provider import (
    UnoRouterProvider,
    ZeroCostRouter,
    FallbackLLMProvider,
    LLMProviderNotAllowedError,
    QuotaExhaustedError,
    is_cost_allowed,
    verify_provider_billing_mode,
    llm_reasoning_cache,
    quota_tracker,
    LLM_STATUS_AVAILABLE,
    LLM_STATUS_RATE_LIMITED,
    LLM_STATUS_UNAVAILABLE,
    LLM_PROVIDER_NOT_ALLOWED,
)


class TestUnoRouterProvider(unittest.TestCase):

    def setUp(self):
        llm_reasoning_cache.clear()

    # 1. Free-model allowlist
    def test_free_model_allowlist(self):
        with patch("services.llm_provider.get_setting_value") as mock_val:
            mock_val.side_effect = lambda k, default=None: {
                "ALLOW_PAID_LLM": False,
                "LLM_COST_POLICY": "ZERO_COST_ONLY",
                "UNOROUTER_ACCOUNT_MODE": "FREE",
                "UNOROUTER_API_KEY": "sk-unorouter-test-key-1234567890",
            }.get(k, default)

            self.assertTrue(is_cost_allowed("unorouter", "glm-5.3-search:free"))
            prov = UnoRouterProvider(api_key="sk-unorouter-test-key-1234567890", model_name="glm-5.3-search:free")
            self.assertTrue(prov.is_available())

    # 2. Paid-route rejection
    def test_paid_route_rejection(self):
        with patch("services.llm_provider.get_setting_value") as mock_val:
            mock_val.side_effect = lambda k, default=None: {
                "ALLOW_PAID_LLM": False,
                "LLM_COST_POLICY": "ZERO_COST_ONLY",
                "UNOROUTER_ACCOUNT_MODE": "FREE",
                "UNOROUTER_API_KEY": "sk-unorouter-test-key-1234567890",
            }.get(k, default)

            # Route missing :free suffix must be rejected
            self.assertFalse(is_cost_allowed("unorouter", "glm-5.3-search"))
            self.assertFalse(is_cost_allowed("unorouter", "gpt-4o"))
            self.assertFalse(is_cost_allowed("unorouter", "claude-3-5-sonnet"))

            prov = UnoRouterProvider(api_key="sk-unorouter-test-key-1234567890", model_name="glm-5.3-search")
            self.assertFalse(prov.is_available())
            with self.assertRaises(LLMProviderNotAllowedError) as ctx:
                prov.complete(system_prompt="Test", messages=[{"role": "user", "content": "Hi"}])
            self.assertIn("not an approved free route", str(ctx.exception))

    # 3. Paid account mode blocked
    def test_account_mode_paid_blocked(self):
        with patch("services.llm_provider.get_setting_value") as mock_val:
            mock_val.side_effect = lambda k, default=None: {
                "ALLOW_PAID_LLM": False,
                "LLM_COST_POLICY": "ZERO_COST_ONLY",
                "UNOROUTER_ACCOUNT_MODE": "PAID",
                "UNOROUTER_API_KEY": "sk-unorouter-test-key-1234567890",
            }.get(k, default)

            allowed, reason = verify_provider_billing_mode("unorouter")
            self.assertFalse(allowed)
            self.assertEqual(reason, "PROVIDER_ACCOUNT_MODE_PAID_BLOCKED")

            prov = UnoRouterProvider(api_key="sk-unorouter-test-key-1234567890")
            self.assertFalse(prov.is_available())
            with self.assertRaises(LLMProviderNotAllowedError):
                prov.complete(system_prompt="Test", messages=[{"role": "user", "content": "Hi"}])

    # 4. Missing or invalid key
    def test_missing_or_placeholder_key(self):
        prov_none = UnoRouterProvider(api_key="")
        self.assertFalse(prov_none.is_available())

        prov_mock = UnoRouterProvider(api_key="mock_key_123456")
        self.assertFalse(prov_mock.is_available())

        prov_short = UnoRouterProvider(api_key="12345")
        self.assertFalse(prov_short.is_available())

    # 5. HTTP 401 invalid key handling
    @patch("services.llm_provider.requests.post")
    def test_http_401_invalid_key(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = '{"error":{"message":"Invalid API key"}}'
        mock_resp.headers = {}
        mock_post.return_value = mock_resp

        with patch("services.llm_provider.get_setting_value") as mock_val:
            mock_val.side_effect = lambda k, default=None: {
                "ALLOW_PAID_LLM": False,
                "LLM_COST_POLICY": "ZERO_COST_ONLY",
                "UNOROUTER_ACCOUNT_MODE": "FREE",
                "UNOROUTER_API_KEY": "sk-unorouter-test-key-1234567890",
            }.get(k, default)

            prov = UnoRouterProvider(api_key="sk-unorouter-test-key-1234567890")
            with self.assertRaises(RuntimeError) as ctx:
                prov.complete(system_prompt="Test", messages=[{"role": "user", "content": "Hi"}])
            self.assertIn("HTTP 401", str(ctx.exception))
            # Verify raw secret is NOT in exception
            self.assertNotIn("sk-unorouter-test-key-1234567890", str(ctx.exception))

    # 6. HTTP 402 payment required immediately blocks provider
    @patch("services.llm_provider.requests.post")
    def test_http_402_immediate_block(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 402
        mock_resp.text = '{"error":{"message":"Payment required for this route"}}'
        mock_resp.headers = {}
        mock_post.return_value = mock_resp

        with patch("services.llm_provider.get_setting_value") as mock_val:
            mock_val.side_effect = lambda k, default=None: {
                "ALLOW_PAID_LLM": False,
                "LLM_COST_POLICY": "ZERO_COST_ONLY",
                "UNOROUTER_ACCOUNT_MODE": "FREE",
                "UNOROUTER_API_KEY": "sk-unorouter-test-key-1234567890",
            }.get(k, default)

            prov = UnoRouterProvider(api_key="sk-unorouter-test-key-1234567890")
            self.assertTrue(prov.is_available())

            with self.assertRaises(LLMProviderNotAllowedError) as ctx:
                prov.complete(system_prompt="Test", messages=[{"role": "user", "content": "Hi"}])
            self.assertIn("BLOCKED immediately", str(ctx.exception))

            # Provider must now be permanently blocked
            self.assertTrue(prov._blocked)
            self.assertFalse(prov.is_available())

            # Subsequent call must be blocked before network dispatch
            with self.assertRaises(LLMProviderNotAllowedError):
                prov.complete(system_prompt="Test", messages=[{"role": "user", "content": "Hi"}])

    # 7. HTTP 429 rate limit handling
    @patch("services.llm_provider.requests.post")
    def test_http_429_rate_limit(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.text = '{"error":{"message":"Too many requests. retry in 30s."}}'
        mock_resp.headers = {"Retry-After": "45", "x-ratelimit-remaining": "0"}
        mock_post.return_value = mock_resp

        with patch("services.llm_provider.get_setting_value") as mock_val:
            mock_val.side_effect = lambda k, default=None: {
                "ALLOW_PAID_LLM": False,
                "LLM_COST_POLICY": "ZERO_COST_ONLY",
                "UNOROUTER_ACCOUNT_MODE": "FREE",
                "UNOROUTER_API_KEY": "sk-unorouter-test-key-1234567890",
            }.get(k, default)

            prov = UnoRouterProvider(api_key="sk-unorouter-test-key-1234567890")
            with self.assertRaises(QuotaExhaustedError) as ctx:
                prov.complete(system_prompt="Test", messages=[{"role": "user", "content": "Hi"}])
            self.assertEqual(ctx.exception.retry_after, 45)
            self.assertFalse(prov.is_available())

    # 8. Timeout handling
    @patch("services.llm_provider.requests.post")
    def test_timeout_handling(self, mock_post):
        mock_post.side_effect = requests.exceptions.Timeout("Read timed out")

        with patch("services.llm_provider.get_setting_value") as mock_val:
            mock_val.side_effect = lambda k, default=None: {
                "ALLOW_PAID_LLM": False,
                "LLM_COST_POLICY": "ZERO_COST_ONLY",
                "UNOROUTER_ACCOUNT_MODE": "FREE",
                "UNOROUTER_API_KEY": "sk-unorouter-test-key-1234567890",
            }.get(k, default)

            prov = UnoRouterProvider(api_key="sk-unorouter-test-key-1234567890")
            with self.assertRaises(RuntimeError) as ctx:
                prov.complete(system_prompt="Test", messages=[{"role": "user", "content": "Hi"}])
            self.assertIn("timed out", str(ctx.exception))

    # 9. Malformed JSON handling
    @patch("services.llm_provider.requests.post")
    def test_malformed_json_response(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.side_effect = ValueError("Invalid JSON")
        mock_resp.headers = {}
        mock_post.return_value = mock_resp

        with patch("services.llm_provider.get_setting_value") as mock_val:
            mock_val.side_effect = lambda k, default=None: {
                "ALLOW_PAID_LLM": False,
                "LLM_COST_POLICY": "ZERO_COST_ONLY",
                "UNOROUTER_ACCOUNT_MODE": "FREE",
                "UNOROUTER_API_KEY": "sk-unorouter-test-key-1234567890",
            }.get(k, default)

            prov = UnoRouterProvider(api_key="sk-unorouter-test-key-1234567890")
            with self.assertRaises(RuntimeError) as ctx:
                prov.complete(system_prompt="Test", messages=[{"role": "user", "content": "Hi"}])
            self.assertIn("malformed JSON", str(ctx.exception))

    # 10. Cache verification
    def test_cache_hashing_and_retrieval(self):
        llm_reasoning_cache.set_prompt_response(
            provider="unorouter",
            model="glm-5.3-search:free",
            system_prompt="Test system",
            user_prompt="Test prompt",
            output={"answer": "cached_ok"},
        )
        cached = llm_reasoning_cache.get_prompt_response(
            provider="unorouter",
            model="glm-5.3-search:free",
            system_prompt="Test system",
            user_prompt="Test prompt",
        )
        self.assertIsNotNone(cached)
        self.assertEqual(cached["output"]["answer"], "cached_ok")

        # Different prompt should miss
        miss = llm_reasoning_cache.get_prompt_response(
            provider="unorouter",
            model="glm-5.3-search:free",
            system_prompt="Test system",
            user_prompt="Different prompt",
        )
        self.assertIsNone(miss)

    # 11. ZeroCostRouter priority and fallback
    @patch("services.llm_provider.UnoRouterProvider.complete")
    @patch("services.llm_provider.UnoRouterProvider.is_available")
    @patch("services.llm_provider.GeminiProvider.complete")
    @patch("services.llm_provider.GeminiProvider.is_available")
    def test_zero_cost_router_priority_and_fallback(
        self,
        mock_gemini_avail,
        mock_gemini_complete,
        mock_uno_avail,
        mock_uno_complete,
    ):
        mock_uno_avail.return_value = True
        mock_gemini_avail.return_value = True

        # Case A: UnoRouter succeeds as Priority #1
        from services.llm_provider import LLMResponse
        mock_uno_complete.return_value = LLMResponse(
            text="UnoRouter response",
            provider="unorouter",
            model="glm-5.3-search:free",
        )

        router = ZeroCostRouter()
        resp = router.complete(system_prompt="S", messages=[{"role": "user", "content": "U"}])
        self.assertEqual(resp.provider, "unorouter")
        mock_uno_complete.assert_called_once()
        mock_gemini_complete.assert_not_called()

        # Case B: UnoRouter fails over to Gemini on QuotaExhaustedError
        mock_uno_complete.reset_mock()
        mock_gemini_complete.reset_mock()
        mock_uno_complete.side_effect = QuotaExhaustedError("Rate limit hit")
        mock_gemini_complete.return_value = LLMResponse(
            text="Gemini fallback response",
            provider="gemini",
            model="gemini-3.7-flash",
        )

        resp2 = router.complete(system_prompt="S", messages=[{"role": "user", "content": "U"}])
        self.assertEqual(resp2.provider, "gemini")
        mock_uno_complete.assert_called_once()
        mock_gemini_complete.assert_called_once()

    # 12. Secret redaction
    def test_secret_redaction(self):
        secret = "unorouter-secret-token-abcdef1234567890"
        prov = UnoRouterProvider(api_key=secret)
        self.assertNotIn(secret, repr(prov))
        self.assertNotIn(secret, str(prov))


if __name__ == "__main__":
    unittest.main()
