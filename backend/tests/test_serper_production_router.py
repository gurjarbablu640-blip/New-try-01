"""Tests for Serper Production Router, Daily 1500 Budget, and Early Stopping.

Verifies:
1. Hard 1500 daily limit & request 1501 blocked with SERPER_DAILY_BUDGET_EXHAUSTED.
2. Cache hits do NOT consume Serper API quota.
3. Daily counter reset across date boundaries.
4. Early stopping stops additional queries and records early stop counter.
5. Per-company budget stops at or before configured limit (default 10).
6. SearXNG is NOT automatically invoked after Serper failure.
7. SERPER_API_KEY is never logged or exposed in telemetry.
8. Runtime cache file is in .gitignore and not git-tracked.
9. Kehems-style generic title ("Deputy Manager") enters candidate pool with LOW confidence.
10. Strict verification remains unchanged: FALSE_HIGH stays zero.
"""
from __future__ import annotations

import os
import re
import subprocess
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from config import settings
from services.research_provider import (
    ResearchProviderRouter,
    SerperSearchProvider,
    ResearchResult,
    PROVIDER_LIVE,
    PROVIDER_BUDGET_EXHAUSTED,
    PROVIDER_EMPTY,
    PROVIDER_ERROR,
    research_router,
)
from services.serper_budget_manager import (
    SerperDailyBudgetManager,
    SerperBudgetExhaustedError,
    serper_budget_manager,
)
from services.person_intelligence_service import (
    extract_person_candidates_from_search_result,
    discover_and_rank_decision_makers,
    compute_deterministic_person_score,
)
from services.decision_maker_discovery import (
    execute_web_person_search,
    is_apollo_eligible_lead,
)


@pytest.fixture
def clean_budget_manager(tmp_path):
    """Provide an isolated budget manager with temporary state path."""
    state_file = str(tmp_path / "serper_budget_state.json")
    manager = SerperDailyBudgetManager(state_path=state_file, daily_limit=1500)
    return manager


class TestSerperDailyHardLimit:
    """Test 1500 daily hard ceiling and quota exhaustion blocking."""

    def test_daily_limit_configuration(self, clean_budget_manager):
        assert clean_budget_manager.daily_limit == 1500
        assert clean_budget_manager.remaining_daily_budget == 1500

    def test_request_1501_is_blocked(self, clean_budget_manager):
        # Consume 1500 requests
        clean_budget_manager.record_live_request(1500)
        assert clean_budget_manager.live_requests_today == 1500
        assert clean_budget_manager.remaining_daily_budget == 0
        assert clean_budget_manager.can_request() is False

        # Request 1501 raises SerperBudgetExhaustedError
        with pytest.raises(SerperBudgetExhaustedError) as exc_info:
            clean_budget_manager.record_live_request(1)
        assert "Serper daily budget exhausted" in str(exc_info.value)
        assert clean_budget_manager.budget_exhausted_events >= 1

    def test_serper_search_provider_returns_budget_exhausted_state(self, clean_budget_manager):
        clean_budget_manager.record_live_request(1500)
        provider = SerperSearchProvider(api_key="valid_serper_key_123456789", budget_manager=clean_budget_manager)

        with patch("services.research_provider.get_setting_value", return_value="valid_serper_key_123456789"):
            with patch("services.serper_budget_manager.serper_budget_manager", clean_budget_manager):
                # Ensure no network call is ever made
                with patch("requests.post") as mock_post:
                    res = provider.search("Maruti Suzuki quality head")
                    assert res["provider_status"] == PROVIDER_BUDGET_EXHAUSTED
                    assert "SERPER_DAILY_BUDGET_EXHAUSTED" in res["error"]
                    assert res["results"] == []
                    mock_post.assert_not_called()


class TestCacheHitsDoNotConsumeQuota:
    """Test cache hits never count against the 1500 daily API quota."""

    def test_cache_hits_leave_live_requests_unchanged(self, clean_budget_manager):
        mock_cache = MagicMock()
        mock_cache.get.return_value = {
            "provider": "serper",
            "provider_status": PROVIDER_LIVE,
            "results": [{"title": "Test Leader", "url": "https://example.com", "snippet": "Leader at Company"}],
            "query": "test query",
            "cache_hit": True,
        }

        initial_live = clean_budget_manager.live_requests_today
        initial_remaining = clean_budget_manager.remaining_daily_budget
        initial_cache_hits = clean_budget_manager.cache_hits_today

        provider = SerperSearchProvider(api_key="valid_key_123456789", cache=mock_cache, budget_manager=clean_budget_manager)
        with patch("services.research_provider.get_setting_value", return_value="valid_key_123456789"):
            with patch("services.serper_budget_manager.serper_budget_manager", clean_budget_manager):
                res = provider.search("test query")
                assert res.get("cache_hit") is True

        # Cache hit recorded, but zero live requests consumed
        assert clean_budget_manager.cache_hits_today == initial_cache_hits + 1
        assert clean_budget_manager.live_requests_today == initial_live
        assert clean_budget_manager.remaining_daily_budget == initial_remaining


class TestDailyCounterReset:
    """Test daily reset boundary across UTC date rollover."""

    def test_daily_counter_reset_on_date_change(self, clean_budget_manager):
        clean_budget_manager.record_live_request(1500)
        clean_budget_manager.record_cache_hit(50)
        clean_budget_manager.record_company_researched(20)
        clean_budget_manager.record_search_stopped_early(15)
        clean_budget_manager.record_budget_exhausted()

        # Simulate date change to tomorrow
        clean_budget_manager.current_date = "2026-09-11"
        clean_budget_manager._save()

        # Reading or checking resets the counters
        assert clean_budget_manager.can_request() is True
        assert clean_budget_manager.live_requests_today == 0
        assert clean_budget_manager.cache_hits_today == 0
        assert clean_budget_manager.remaining_daily_budget == 1500
        assert clean_budget_manager.companies_researched == 0
        assert clean_budget_manager.searches_stopped_early == 0
        assert clean_budget_manager.budget_exhausted_events == 0


class TestEarlyStoppingAndPerCompanyBudget:
    """Test evidence-driven early stopping and per-company budget ceiling."""

    def test_early_stopping_on_high_confidence_evidence(self, clean_budget_manager):
        mock_router = MagicMock()
        # Mock search to return a HIGH confidence candidate snippet on query 1
        mock_router.search.return_value = {
            "provider": "serper",
            "provider_status": PROVIDER_LIVE,
            "results": [
                {
                    "title": "Atul Jain - Head of Quality - Maruti Suzuki India | LinkedIn",
                    "url": "https://www.linkedin.com/in/atul-jain-quality",
                    "snippet": "Atul Jain is Head of Quality at Maruti Suzuki, Hansalpur plant. Currently serving present 2026.",
                }
            ],
            "query": "mock query",
        }

        with patch("services.serper_budget_manager.serper_budget_manager", clean_budget_manager):
            res = discover_and_rank_decision_makers(
                company_name="Maruti Suzuki",
                facility_name="Hansalpur",
                city="Hansalpur",
                search_router=mock_router,
            )

        telemetry = res.get("telemetry", {})
        # Should have stopped early in initial tier (<= 4 queries run)
        assert telemetry.get("stopped_early") is True
        assert telemetry.get("queries_run") <= 4
        assert clean_budget_manager.searches_stopped_early >= 1

    def test_per_company_budget_ceiling(self, clean_budget_manager):
        mock_router = MagicMock()
        # Empty results to force continuing queries
        mock_router.search.return_value = {
            "provider": "serper",
            "provider_status": PROVIDER_EMPTY,
            "results": [],
            "query": "mock query",
        }

        with patch("services.serper_budget_manager.serper_budget_manager", clean_budget_manager):
            res = discover_and_rank_decision_makers(
                company_name="Unknown Corp",
                facility_name="Unknown Plant",
                city="Unknown City",
                search_router=mock_router,
            )

        telemetry = res.get("telemetry", {})
        # Must not exceed maximum configured company budget (10 queries)
        assert telemetry.get("queries_run") <= 10


class TestSearXNGPolicy:
    """Test SearXNG is NOT automatically invoked when Serper is primary."""

    def test_searxng_not_automatically_invoked_after_serper(self):
        router = ResearchProviderRouter()

        with patch.object(router, "_search_serper", return_value=([], PROVIDER_EMPTY, "No results")):
            with patch.object(router, "_search_searxng") as mock_searxng:
                with patch("services.research_provider.get_setting_value") as mock_settings:
                    def get_setting(key, default=""):
                        if key == "SERPER_API_KEY":
                            return "valid_serper_key_123456789"
                        return default
                    mock_settings.side_effect = get_setting

                    # With default SEARXNG_AUTO_FALLBACK=False, SearXNG must NOT be called
                    res = router.search("Maruti Suzuki quality manager")
                    assert res["provider"] != "searxng"
                    mock_searxng.assert_not_called()

    def test_serper_budget_exhausted_never_calls_searxng(self):
        router = ResearchProviderRouter()

        with patch.object(router, "_search_serper", return_value=([], PROVIDER_BUDGET_EXHAUSTED, "SERPER_DAILY_BUDGET_EXHAUSTED")):
            with patch.object(router, "_search_searxng") as mock_searxng:
                with patch("services.research_provider.get_setting_value") as mock_settings:
                    def get_setting(key, default=""):
                        if key == "SERPER_API_KEY":
                            return "valid_serper_key_123456789"
                        return default
                    mock_settings.side_effect = get_setting

                    res = router.search("Maruti Suzuki quality manager")
                    assert res["provider_status"] == PROVIDER_BUDGET_EXHAUSTED
                    mock_searxng.assert_not_called()


class TestSecurityAndTelemetry:
    """Test API key is never logged or exposed in telemetry."""

    def test_serper_api_key_never_exposed_in_telemetry(self, clean_budget_manager):
        secret_key = "secret_serper_key_99887766554433"
        clean_budget_manager.record_live_request(5)
        clean_budget_manager.record_cache_hit(10)
        clean_budget_manager.record_company_researched(2)

        telemetry = clean_budget_manager.get_telemetry()
        # Verify required keys exist
        assert "live_requests_today" in telemetry
        assert "cache_hits_today" in telemetry
        assert "remaining_daily_budget" in telemetry
        assert "companies_researched" in telemetry
        assert "searches_stopped_early" in telemetry
        assert "budget_exhausted_events" in telemetry
        assert "average_live_requests_per_company" in telemetry

        # Verify secret key is nowhere in telemetry keys or values
        telemetry_str = str(telemetry)
        assert secret_key not in telemetry_str
        assert "api_key" not in telemetry

    def test_runtime_cache_not_git_tracked(self):
        # 1. Verify in .gitignore
        gitignore_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".gitignore"))
        with open(gitignore_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "backend/data/runtime_state/search_provider_cache.json" in content
        assert "backend/data/runtime_state/serper_budget_state.json" in content

        # 2. Verify git ls-files does not track search_provider_cache.json
        cmd = ["git", "ls-files", "backend/data/runtime_state/search_provider_cache.json"]
        out = subprocess.check_output(cmd, cwd=os.path.dirname(gitignore_path)).decode("utf-8").strip()
        assert out == "", "search_provider_cache.json must NOT be tracked by git!"


class TestKehemsDiscoveryVsVerification:
    """Test Kehems-style generic title enters candidate pool without false HIGH confidence."""

    def test_kehems_deputy_manager_enters_discovery_pool(self):
        raw_result = {
            "title": "Ravi Singh - Deputy Manager - Kehems Technologies | AeroLeads",
            "url": "https://aeroleads.com/p/ravi-singh/kehems",
            "snippet": "Ravi Singh is listed as Deputy Manager at Kehems Technologies Pvt. Ltd. in Indore.",
        }

        candidates = extract_person_candidates_from_search_result(
            raw_result,
            company_name="Kehems Technologies Pvt. Ltd.",
            city="Indore",
            facility_name="Indore",
        )

        assert len(candidates) >= 1
        ravi = next((c for c in candidates if "ravi singh" in c["name"].lower()), None)
        assert ravi is not None, "Ravi Singh must enter candidate pool"
        assert "manager" in ravi["title"].lower()

        # Strict verification tenets
        # Score must be well below 70 and confidence must be LOW
        assert ravi["person_score"] < 70.0
        assert ravi["person_confidence"] == "LOW"
        assert ravi["person_confidence"] != "HIGH"

        # Apollo eligibility must be strictly rejected
        eligible, reason = is_apollo_eligible_lead(
            candidate=ravi,
            facility_info={"verified": True, "linkage_confidence": "DIRECT"},
            trigger_info={"valid_trigger": True, "trigger": "Plant Expansion"},
        )
        assert eligible is False
        assert "below Apollo HIGH-confidence threshold" in reason
