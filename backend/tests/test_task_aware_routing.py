"""Tests for Task-Aware LLM Routing Hardening, 1-RPM Non-Blocking Cooldown,
Source Verification Pipeline, and Zero-Cost Safety.
"""
from datetime import datetime, timezone
import os
import sys
import time
import unittest
from unittest.mock import MagicMock, patch

from services.llm_provider import (
    CloudflareProvider,
    GeminiProvider,
    GroqProvider,
    LLMProviderNotAllowedError,
    LLMResponse,
    OpenAIProvider,
    OpenRouterProvider,
    QuotaExhaustedError,
    TASK_CATEGORY_DETERMINISTIC_ONLY,
    TASK_CATEGORY_PUBLIC_WEB_RESEARCH,
    TASK_CATEGORY_REASONING,
    TASK_CATEGORY_TOOL_EXECUTION,
    UnoRouterProvider,
    ZeroCostRouter,
    get_orchestrator_provider,
    llm_reasoning_cache,
)
from services.source_verification_pipeline import (
    SourceVerificationPipeline,
    normalize_citations,
    strip_internal_model_markers,
)


class TestTaskAwareProviderSelection(unittest.TestCase):
    """Verify provider ordering and exclusion rules per task category."""

    def tearDown(self):
        UnoRouterProvider.reset_rate_limit_state()

    def test_web_research_tasks_prefer_unorouter_first(self):
        """Web research and trigger discovery tasks should place UnoRouter first."""
        research_tasks = [
            "PUBLIC_WEB_RESEARCH",
            "CURRENT_TRIGGER_RESEARCH",
            "SOURCE_DISCOVERY",
            "RECENT_COMPANY_RESEARCH",
        ]
        for task in research_tasks:
            router = ZeroCostRouter(task_type=task)
            self.assertGreater(len(router.providers), 0)
            self.assertIsInstance(
                router.providers[0],
                UnoRouterProvider,
                f"Task '{task}' should place UnoRouterProvider as primary/first provider.",
            )

    def test_general_reasoning_tasks_exclude_unorouter(self):
        """Reasoning tasks should use verified zero-cost reasoning providers; UnoRouter is excluded to protect 1 RPM & latency."""
        reasoning_tasks = [
            "GENERAL_REASONING",
            "PERSON_RANKING",
            "FACILITY_CLASSIFICATION",
            "SUMMARIZATION",
            "COPY_REVIEW",
        ]
        for task in reasoning_tasks:
            router = ZeroCostRouter(task_type=task)
            self.assertGreater(len(router.providers), 0)
            for p in router.providers:
                self.assertNotIsInstance(
                    p,
                    UnoRouterProvider,
                    f"Task '{task}' must exclude UnoRouter due to 35s latency and 1 RPM search-specialized model.",
                )

    def test_tool_call_tasks_strictly_exclude_unorouter(self):
        """Tool-calling and agent loops must NEVER include UnoRouter."""
        tool_tasks = [
            "TOOL_CALL_REQUIRED",
            "AGENT_LOOP",
            "STRUCTURED_TOOL_EXECUTION",
        ]
        for task in tool_tasks:
            router = ZeroCostRouter(task_type=task)
            for p in router.providers:
                self.assertNotIsInstance(
                    p,
                    UnoRouterProvider,
                    f"UnoRouterProvider must be strictly excluded from tool-calling task '{task}'.",
                )

    def test_deterministic_tasks_strictly_prohibit_llm(self):
        """Deterministic gates and classifications must return None and reject LLM calls."""
        deterministic_tasks = [
            "DETERMINISTIC_GATE",
            "CONTACT_CLASSIFICATION",
            "QUALIFICATION_STATE",
            "SCHEDULER",
            "DUPLICATE_CHECK",
        ]
        for task in deterministic_tasks:
            provider = get_orchestrator_provider(task_type=task)
            self.assertIsNone(
                provider,
                f"get_orchestrator_provider must return None for deterministic task '{task}'.",
            )

            router = ZeroCostRouter(task_type=task)
            self.assertEqual(len(router.providers), 0)
            self.assertFalse(router.is_available())

            with self.assertRaises(LLMProviderNotAllowedError):
                router.complete(
                    system_prompt="Analyze this",
                    messages=[{"role": "user", "content": "gate test"}],
                    task_type=task,
                )


class TestOneRpmNonBlockingFallback(unittest.TestCase):
    """Verify UnoRouter 1-RPM rate-limit awareness does NOT block or stall the worker."""

    def setUp(self):
        UnoRouterProvider.reset_rate_limit_state()

    def tearDown(self):
        UnoRouterProvider.reset_rate_limit_state()

    def test_unorouter_sets_cooldown_and_skips_immediately(self):
        """When UnoRouter is in cooldown, is_available() is False immediately without sleeping."""
        provider = UnoRouterProvider(api_key="uno-mock-key")
        
        # Simulate an earlier request setting cooldown
        UnoRouterProvider._last_request_at = time.time()
        UnoRouterProvider._next_allowed_at = time.time() + 60.0

        start_time = time.time()
        available = provider.is_available()
        elapsed = time.time() - start_time

        self.assertFalse(available)
        self.assertLess(elapsed, 2.0, "Cooldown check must be non-blocking (must not sleep 60s).")

        state = UnoRouterProvider.get_rate_limit_state()
        self.assertTrue(state["is_cooling_down"])
        self.assertGreater(state["cooldown_remaining_seconds"], 0)

    def test_unorouter_complete_raises_quota_exhausted_during_cooldown(self):
        """Direct complete() call raises QuotaExhaustedError instantly during cooldown without network call."""
        provider = UnoRouterProvider(api_key="uno-mock-key")
        UnoRouterProvider._last_request_at = time.time()
        UnoRouterProvider._next_allowed_at = time.time() + 45.0

        start_time = time.time()
        with self.assertRaises(QuotaExhaustedError) as ctx:
            provider.complete(
                system_prompt="Test",
                messages=[{"role": "user", "content": "Hello"}],
            )
        elapsed = time.time() - start_time

        self.assertLess(elapsed, 2.0, "Direct call must fail immediately during cooldown.")
        self.assertIn("1 RPM limit", str(ctx.exception))

    def test_router_falls_over_when_unorouter_cooling_down(self):
        """ZeroCostRouter skips UnoRouter and seamlessly calls fallback when UnoRouter is cooling down."""
        # Put UnoRouter in cooldown
        UnoRouterProvider._last_request_at = time.time()
        UnoRouterProvider._next_allowed_at = time.time() + 60.0

        # Create mock fallback provider that succeeds
        mock_fallback = MagicMock()
        mock_fallback.is_available.return_value = True
        mock_fallback.complete.return_value = LLMResponse(
            text="Fallback response",
            provider="mock_free",
            model="mock_model",
            latency_ms=10.0,
        )

        uno_p = UnoRouterProvider(api_key="uno-mock-key")
        router = ZeroCostRouter(task_type="PUBLIC_WEB_RESEARCH")
        router.providers = [uno_p, mock_fallback]

        start_time = time.time()
        resp = router.complete(
            system_prompt="Search",
            messages=[{"role": "user", "content": "Query"}],
        )
        elapsed = time.time() - start_time

        self.assertLess(elapsed, 2.0, "Router must failover immediately without blocking.")
        self.assertEqual(resp.text, "Fallback response")
        mock_fallback.complete.assert_called_once()


class TestSourceVerificationAndCitations(unittest.TestCase):
    """Verify source verification invariants and citation normalization."""

    def test_strip_internal_model_markers(self):
        """Model-internal tokens like 【turn0search0】 must be stripped."""
        text = "According to Dixon Technologies 【turn0search0】, the facility in Noida is expanding [turn1search3]."
        cleaned = strip_internal_model_markers(text)
        self.assertNotIn("turn0search0", cleaned)
        self.assertNotIn("turn1search3", cleaned)
        self.assertIn("According to Dixon Technologies, the facility in Noida is expanding.", cleaned)

    def test_normalize_citations_extracts_actual_urls_and_hashes(self):
        """Normalizer extracts clean URLs, titles, dates, domains, and sha256 hashes."""
        raw_text = (
            "Dixon Technologies announced a new plant in Dehradun.\n"
            "Source: [Dixon Press Release](https://www.dixoninfo.com/press/plant-expansion-2025.html) on April 9, 2025. "
            "See also https://economictimes.indiatimes.com/industry/dixon-expansion.cms 【turn0search1】."
        )
        citations = normalize_citations(raw_text)
        self.assertEqual(len(citations), 2)

        dixon_cite = citations[0]
        self.assertEqual(dixon_cite["source_url"], "https://www.dixoninfo.com/press/plant-expansion-2025.html")
        self.assertIn("dixoninfo.com", dixon_cite["source_domain"])
        self.assertEqual(dixon_cite["source_title"], "Dixon Press Release")
        self.assertIn("2025", dixon_cite["publication_date"])
        self.assertNotIn("turn0search1", dixon_cite["snippet"])
        self.assertTrue(bool(dixon_cite["raw_text_hash"]))

        et_cite = citations[1]
        self.assertEqual(et_cite["source_url"], "https://economictimes.indiatimes.com/industry/dixon-expansion.cms")
        self.assertEqual(et_cite["source_domain"], "economictimes.indiatimes.com")

    def test_reject_internal_markers_without_actual_urls(self):
        """A claim with only marker citations (no URL) yields zero valid citations."""
        marker_only = "UnoRouter reported plant opening 【turn0search0】 and new hiring 【turn0search1】."
        citations = normalize_citations(marker_only)
        self.assertEqual(len(citations), 0, "Marker-only citations must be rejected.")

    def test_unverified_source_cannot_be_promoted_directly(self):
        """LLM search results are DISCOVERY EVIDENCE only and cannot directly verify gates."""
        pipeline = SourceVerificationPipeline()
        
        # Test 1: Fetch failure -> Remains UNVERIFIED
        res_fail = pipeline.verify_discovered_source(
            company="Dixon Technologies",
            claim_type="FACILITY_EXPANSION",
            claim_text="Dixon opened a facility in Tirupati.",
            source_url="https://invalid-nonexistent-domain-404-test.com/news",
            mock_fetch_success=False,
        )
        self.assertFalse(res_fail["verified"])
        self.assertEqual(res_fail["status"], "UNVERIFIED")
        self.assertEqual(res_fail["claim_status"], "UNVERIFIED_FACILITY_EXPANSION")
        self.assertIsNone(res_fail["provenance_record"])

        # Test 2: Successful fetch -> Corroborated source (requires deterministic gate, NOT directly verified)
        res_ok = pipeline.verify_discovered_source(
            company="Dixon Technologies",
            claim_type="TRIGGER",
            claim_text="Dixon acquired new surface mount machines 【turn0search0】.",
            source_url="https://dixoninfo.com/investor-relations/q3-update",
            mock_fetch_success=True,
        )
        self.assertTrue(res_ok["verified"])
        self.assertEqual(res_ok["status"], "CORROBORATED_SOURCE")
        self.assertTrue(res_ok["requires_deterministic_gate"])
        # Crucial check: claim status is NOT TRIGGER_VERIFIED
        self.assertNotEqual(res_ok["claim_status"], "TRIGGER_VERIFIED")
        self.assertEqual(res_ok["claim_status"], "CORROBORATED_TRIGGER")
        self.assertIsNotNone(res_ok["provenance_record"])
        self.assertEqual(res_ok["provenance_record"].source_domain, "dixoninfo.com")

    def test_generic_encyclopedia_and_missing_company_rejected(self):
        """Generic encyclopedias, dictionaries, and snippets without company mention must be rejected."""
        pipeline = SourceVerificationPipeline()

        # Case 1: Wikipedia / dictionary domain rejected
        res_wiki = pipeline.verify_discovered_source(
            company="Kaynes Technology",
            claim_type="TRIGGER",
            claim_text="Kaynes Technology plant expansion in Mysuru.",
            source_url="https://en.wikipedia.org/wiki/Plant",
            mock_fetch_success=True,
        )
        self.assertFalse(res_wiki["verified"])
        self.assertEqual(res_wiki["status"], "UNVERIFIED")
        self.assertEqual(res_wiki["source_role"], "UNTRUSTED")
        self.assertIn("untrusted reference source", res_wiki["reason"])

        # Case 2: Snippet does not mention target company
        res_no_co = pipeline.verify_discovered_source(
            company="Varroc Engineering",
            claim_type="TRIGGER",
            claim_text="Automotive component manufacturer announced 500 crore investment in Chakan.",
            source_url="https://autocarpro.in/news/chakan-plant-update",
            mock_fetch_success=True,
        )
        self.assertFalse(res_no_co["verified"])
        self.assertEqual(res_no_co["status"], "UNVERIFIED")
        self.assertIn("does not mention target company", res_no_co["reason"])

    def test_linkedin_rejected_as_trigger_source(self):
        """LinkedIn company profiles are NOT valid expansion trigger evidence."""
        pipeline = SourceVerificationPipeline()
        res = pipeline.verify_discovered_source(
            company="Varroc Engineering",
            claim_type="MANUFACTURING_TRIGGER",
            claim_text="Varroc Group is a global tier-1 automotive component manufacturer.",
            source_url="https://in.linkedin.com/company/varroc-global",
            mock_fetch_success=True,
        )
        self.assertFalse(res["verified"])
        self.assertEqual(res["status"], "UNVERIFIED")
        self.assertEqual(res["source_role"], "DISCOVERY_ONLY")
        self.assertIn("not acceptable for claim type", res["reason"])

    def test_google_play_rejected_as_trigger_source(self):
        """play.google.com is an app store — never a valid manufacturing trigger source."""
        pipeline = SourceVerificationPipeline()
        res = pipeline.verify_discovered_source(
            company="Craftsman Automation",
            claim_type="MANUFACTURING_TRIGGER",
            claim_text="Craftsman: Building Craft — design houses and castles.",
            source_url="https://play.google.com/store/apps/details?id=com.craftsman.go",
            mock_fetch_success=True,
        )
        self.assertFalse(res["verified"])
        self.assertEqual(res["status"], "UNVERIFIED")
        self.assertEqual(res["source_role"], "IRRELEVANT")
        self.assertIn("irrelevant", res["reason"])

    def test_job_board_rejected_as_trigger_source(self):
        """Job postings (naukri, indeed) are not primary manufacturing trigger evidence."""
        pipeline = SourceVerificationPipeline()
        for job_url in [
            "https://www.naukri.com/job-listings-quality-manager-varroc",
            "https://www.glassdoor.com/Jobs/Craftsman-quality",
            "https://www.indeed.com/q-quality-engineer-varroc",
        ]:
            res = pipeline.verify_discovered_source(
                company="Varroc Engineering",
                claim_type="MANUFACTURING_TRIGGER",
                claim_text="Varroc Engineering is hiring quality engineers at Chakan plant.",
                source_url=job_url,
                mock_fetch_success=True,
            )
            self.assertFalse(res["verified"], f"Job board URL should be rejected: {job_url}")
            self.assertEqual(res["status"], "UNVERIFIED")

    def test_company_directory_rejected_as_trigger_source(self):
        """Screener/Tofler/Crunchbase are corporate directories, not primary trigger sources."""
        pipeline = SourceVerificationPipeline()
        for dir_url in [
            "https://www.screener.in/company/VARROC/",
            "https://www.tofler.in/varroc-engineering",
            "https://www.crunchbase.com/organization/varroc",
        ]:
            res = pipeline.verify_discovered_source(
                company="Varroc Engineering",
                claim_type="MANUFACTURING_TRIGGER",
                claim_text="Varroc Engineering Ltd annual revenue and financials.",
                source_url=dir_url,
                mock_fetch_success=True,
            )
            self.assertFalse(res["verified"], f"Company directory should be rejected: {dir_url}")
            self.assertEqual(res["status"], "UNVERIFIED")



class TestProviderModeAuditAndSafety(unittest.TestCase):
    """Audit provider modes and zero-cost billing invariants."""

    def test_unverified_gemini_cannot_be_selected(self):
        """When GEMINI_ACCOUNT_MODE is UNVERIFIED, Gemini cannot be dispatched live."""
        with patch.dict(os.environ, {"GEMINI_ACCOUNT_MODE": "UNVERIFIED"}):
            p = GeminiProvider(api_key="AIzaSyMockKeyForSafetyAudit")
            self.assertFalse(
                p.is_available(),
                "GeminiProvider must not be available when GEMINI_ACCOUNT_MODE is UNVERIFIED.",
            )

    def test_paid_providers_strictly_blocked(self):
        """Paid LLM providers (e.g. OpenAI) remain blocked under ZERO_COST_ONLY policy."""
        with patch.dict(os.environ, {"ALLOW_PAID_LLM": "false", "LLM_COST_POLICY": "ZERO_COST_ONLY"}):
            p = OpenAIProvider(api_key="sk-mock-openai-key")
            self.assertFalse(p.is_available())
            with self.assertRaises(LLMProviderNotAllowedError):
                p.complete(
                    system_prompt="System",
                    messages=[{"role": "user", "content": "Test"}],
                )

    def test_search_cache_reuse_for_identical_queries(self):
        """Search responses are normalized, cached, and reused to preserve 1-RPM quota."""
        query_a = "  Dixon Technologies Noida Plant Expansion 2025   "
        query_b = "dixon technologies   noida plant expansion 2025"

        norm_a = llm_reasoning_cache.normalize_search_query(query_a)
        norm_b = llm_reasoning_cache.normalize_search_query(query_b)
        self.assertEqual(norm_a, norm_b)

        # Store in search cache
        llm_reasoning_cache.set_search_cache(
            provider="unorouter",
            model="glm-5.3-search:free",
            query=query_a,
            output={"results": "Expansion confirmed at Sector 68 Noida."},
            freshness_context="2026-09",
            citations=[{"source_url": "https://dixoninfo.com/press", "source_domain": "dixoninfo.com"}],
        )

        # Retrieve with variation
        cached = llm_reasoning_cache.get_search_cache(
            provider="unorouter",
            model="glm-5.3-search:free",
            query=query_b,
            freshness_context="2026-09",
        )
        self.assertIsNotNone(cached)
        self.assertEqual(cached["status"], "CACHED")
        self.assertEqual(cached["output"]["results"], "Expansion confirmed at Sector 68 Noida.")
        self.assertEqual(len(cached["citations"]), 1)


if __name__ == "__main__":
    unittest.main()
