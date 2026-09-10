"""Unit tests for DeerFlow isolated service adapter."""

import json
import unittest
from unittest.mock import MagicMock, patch

from services.deerflow_adapter import DeerFlowAdapter


class TestDeerFlowAdapter(unittest.TestCase):
    def test_disabled_adapter_reports_disabled_status(self):
        adapter = DeerFlowAdapter(enabled=False)
        status = adapter.get_status()
        self.assertEqual(status["status"], "disabled")
        self.assertFalse(status["reachable"])
        self.assertIn("disabled", status["message"].lower())

    def test_disabled_adapter_dispatches_safe_local_fallback(self):
        adapter = DeerFlowAdapter(enabled=False)
        result = adapter.dispatch_research_task(
            company_name="Acme Auto",
            domain="acmeauto.in",
            task_type="subagent_research",
            facility="Pune",
        )
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["execution_mode"], "local_fallback")
        self.assertEqual(result["provider"], "salesoorja_fallback")
        self.assertEqual(result["data"]["company_name"], "Acme Auto")

    def test_unreachable_endpoint_falls_back_gracefully(self):
        adapter = DeerFlowAdapter(base_url="http://invalid-deerflow-host:9999", enabled=True, timeout_seconds=1)
        # Status should report unreachable without raising exception
        status = adapter.get_status()
        self.assertEqual(status["status"], "unreachable")
        self.assertFalse(status["reachable"])
        self.assertTrue(status.get("fallback_active"))

        # Dispatch should fall back gracefully
        result = adapter.dispatch_research_task(
            company_name="Apex Cylinders",
            task_type="browser_deep_crawl",
        )
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["execution_mode"], "local_fallback")
        self.assertIsNotNone(result.get("remote_error"))

    @patch("urllib.request.urlopen")
    def test_successful_deerflow_dispatch_and_fetch(self, mock_urlopen):
        # Mock healthy healthcheck
        mock_resp_health = MagicMock()
        mock_resp_health.read.return_value = json.dumps({
            "version": "0.4.0",
            "capabilities": ["browser", "subagent"],
        }).encode("utf-8")
        mock_resp_health.__enter__.return_value = mock_resp_health

        # Mock dispatch response
        mock_resp_dispatch = MagicMock()
        mock_resp_dispatch.read.return_value = json.dumps({
            "status": "queued",
            "job_id": "job-12345",
        }).encode("utf-8")
        mock_resp_dispatch.__enter__.return_value = mock_resp_dispatch

        mock_urlopen.side_effect = [mock_resp_health, mock_resp_dispatch]

        adapter = DeerFlowAdapter(base_url="http://deerflow:8001", enabled=True)
        status = adapter.get_status()
        self.assertEqual(status["status"], "healthy")
        self.assertTrue(status["reachable"])

        res = adapter.dispatch_research_task(company_name="Bharat Forge", domain="bharatforge.com")
        self.assertEqual(res["status"], "queued")
        self.assertEqual(res["provider"], "deerflow")
        self.assertEqual(res["execution_mode"], "remote")


if __name__ == "__main__":
    unittest.main()
