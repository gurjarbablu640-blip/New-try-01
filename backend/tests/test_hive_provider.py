import unittest
from unittest.mock import Mock, patch

from config import AUTHORITATIVE_ENV_FILE, PROJECT_ROOT
from services.llm_provider import HiveProvider, LLMProviderNotAllowedError


class HiveProviderRegressionTests(unittest.TestCase):
    def test_only_actual_control_token_is_removed(self):
        raw = '<customer><html><quality><a href="https://example.com">Keep</a></quality></html></customer><|endoftext|>'
        cleaned = HiveProvider.clean_output(raw)
        self.assertNotIn("<|endoftext|>", cleaned)
        self.assertIn("<customer>", cleaned)
        self.assertIn("<html>", cleaned)
        self.assertIn("<quality>", cleaned)
        self.assertIn('<a href="https://example.com">', cleaned)

    def test_normal_angle_bracket_text_survives(self):
        self.assertEqual(HiveProvider.clean_output("Use <name> and compare x < y"), "Use <name> and compare x < y")

    def test_root_env_is_authoritative(self):
        self.assertEqual(AUTHORITATIVE_ENV_FILE, PROJECT_ROOT / ".env")

    @patch("services.llm_provider.is_cost_allowed", return_value=True)
    @patch("services.llm_provider.verify_provider_billing_mode", return_value=(True, "PROMO_CREDIT"))
    @patch("services.llm_provider.requests.post")
    def test_http_405_blocks_credit_exhausted_account(
        self,
        post: Mock,
        _verify_billing: Mock,
        _is_cost_allowed: Mock,
    ):
        response = Mock(status_code=405, headers={}, text="balance exhausted")
        post.return_value = response
        provider = HiveProvider(api_key="test_hive_key_long_enough")

        with self.assertRaisesRegex(LLMProviderNotAllowedError, "HTTP 405"):
            provider.complete("", [{"role": "user", "content": "test"}])

        self.assertFalse(provider.is_available())


if __name__ == "__main__":
    unittest.main()
