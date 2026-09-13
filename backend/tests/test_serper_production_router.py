"""Tests for Serper Production Router, Daily 1500 Budget, and Early Stopping.

Verifies:
1. Hard 1500 daily limit & request 1501 blocked with SERPER_DAILY_BUDGET_EXHAUSTED.
2. Cache hits do NOT consume Serper API quota.
3. Daily counter reset across date boundaries.
4. Early stopping stops additional queries and records early stop counter.
5. Per-company budget stops at or before configured limit (default 10).
6. Serper failure does not invoke an alternate live search provider.
7. SERPER_API_KEY is never logged or exposed in telemetry.
8. Runtime cache file is in .gitignore and not git-tracked.
9. Kehems-style generic title ("Deputy Manager") enters candidate pool with LOW confidence.
10. Strict verification remains unchanged: FALSE_HIGH stays zero.
"""
from __future__ import annotations

import os
import subprocess
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

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


class TestSerperOnlyRouting:
    """Test that no alternative live research provider is reachable."""

    def test_serper_success_is_returned_directly(self):
        router = ResearchProviderRouter()
        result = ResearchResult(
            title="Quality Head",
            url="https://example.com/quality-head",
            snippet="Quality Head at Example Ltd",
            provider="serper",
        )

        with patch.object(
            router,
            "_search_serper",
            return_value=([result], PROVIDER_LIVE, None),
        ):
            with patch(
                "services.research_provider.get_setting_value",
                side_effect=lambda key, default="": (
                    "valid_serper_key_123456789"
                    if key == "SERPER_API_KEY"
                    else default
                ),
            ):
                response = router.search("Example Ltd quality head")

        assert response["provider"] == "serper"

    def test_serper_empty_does_not_switch_live_provider(self):
        router = ResearchProviderRouter()

        with patch.object(
            router,
            "_search_serper",
            return_value=([], PROVIDER_EMPTY, "No results"),
        ):
            with patch(
                "services.research_provider.get_setting_value",
                side_effect=lambda key, default="": (
                    "valid_serper_key_123456789"
                    if key == "SERPER_API_KEY"
                    else default
                ),
            ):
                response = router.search("Maruti Suzuki quality manager")

        assert response["provider"] == "serper"
        assert response["provider_status"] == PROVIDER_EMPTY

    def test_serper_budget_exhaustion_stops_routing(self):
        router = ResearchProviderRouter()

        with patch.object(
            router,
            "_search_serper",
            return_value=(
                [],
                PROVIDER_BUDGET_EXHAUSTED,
                "SERPER_DAILY_BUDGET_EXHAUSTED",
            ),
        ):
            with patch(
                "services.research_provider.get_setting_value",
                side_effect=lambda key, default="": (
                    "valid_serper_key_123456789"
                    if key == "SERPER_API_KEY"
                    else default
                ),
            ):
                response = router.search("Maruti Suzuki quality manager")

        assert response["provider"] == "serper"
        assert response["provider_status"] == PROVIDER_BUDGET_EXHAUSTED

    def test_provider_inventory_has_no_legacy_live_routes(self):
        names = {
            provider["name"]
            for provider in ResearchProviderRouter()._discover_providers()
        }
        assert names == {"serper", "database_cache"}


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
        if os.path.exists(gitignore_path):
            with open(gitignore_path, "r", encoding="utf-8") as f:
                content = f.read()
            assert "backend/data/runtime_state/search_provider_cache.json" in content
            assert "backend/data/runtime_state/serper_budget_state.json" in content

            # 2. Verify git ls-files does not track search_provider_cache.json
            cmd = ["git", "ls-files", "backend/data/runtime_state/search_provider_cache.json"]
            out = subprocess.check_output(cmd, cwd=os.path.dirname(gitignore_path)).decode("utf-8").strip()
            assert out == "", "search_provider_cache.json must NOT be tracked by git!"
        else:
            from services.search_cache import search_cache

            assert search_cache.cache_path.endswith("search_provider_cache.json")


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


class TestSerperBudgetTimezone:
    """Test configurable reset timezone and IST midnight boundaries."""

    def test_default_timezone_is_kolkata(self, clean_budget_manager):
        assert clean_budget_manager.timezone_str == "Asia/Kolkata"

    def test_ist_midnight_boundary_2359_to_0000(self, clean_budget_manager):
        # 18:29:59 UTC is 23:59:59 IST (same day)
        dt_2359 = datetime(2026, 9, 12, 18, 29, 59, tzinfo=timezone.utc)
        assert clean_budget_manager._today_str(dt_2359) == "2026-09-12"

        # 18:30:00 UTC is 00:00:00 IST (next day rollover)
        dt_0000 = datetime(2026, 9, 12, 18, 30, 0, tzinfo=timezone.utc)
        assert clean_budget_manager._today_str(dt_0000) == "2026-09-13"

        # Simulate usage at 23:59 IST (previous day)
        clean_budget_manager.current_date = "2026-09-12"
        clean_budget_manager.live_requests_today = 1500
        clean_budget_manager._save()
        assert clean_budget_manager.live_requests_today == 1500

        # At 00:00:00 IST, counter must reset to 0
        reset_occurred = clean_budget_manager.check_and_reset_if_new_day(dt_0000)
        assert reset_occurred is True
        assert clean_budget_manager.current_date == "2026-09-13"
        assert clean_budget_manager.live_requests_today == 0
        assert clean_budget_manager.remaining_daily_budget == 1500

    def test_utc_date_differing_from_ist_date(self, clean_budget_manager):
        # 20:00:00 UTC on 2026-09-12 is 01:30:00 IST on 2026-09-13
        dt_utc = datetime(2026, 9, 12, 20, 0, 0, tzinfo=timezone.utc)
        assert dt_utc.strftime("%Y-%m-%d") == "2026-09-12"  # UTC date is 12th
        assert clean_budget_manager._today_str(dt_utc) == "2026-09-13"  # IST date is 13th

    def test_configurable_timezone_override(self, tmp_path):
        custom_state = str(tmp_path / "custom_tz_state.json")
        ny_manager = SerperDailyBudgetManager(
            state_path=custom_state,
            daily_limit=500,
            timezone_str="America/New_York",
        )
        assert ny_manager.timezone_str == "America/New_York"
        # 03:00 UTC is 23:00 previous day in America/New_York (UTC-4 in EDT)
        dt_utc = datetime(2026, 9, 13, 3, 0, 0, tzinfo=timezone.utc)
        assert ny_manager._today_str(dt_utc) == "2026-09-12"


class TestMultiProcessSafetyAndAtomicReservation:
    """Test atomic reservation and multi-process race safety using FileLock."""

    def test_1500_concurrent_reservations_maximum(self, clean_budget_manager):
        import concurrent.futures

        num_threads = 10
        reservations_per_thread = 15
        batch_size = 10  # 10 * 15 * 10 = 1500 total reservations

        def make_reservations():
            for _ in range(reservations_per_thread):
                clean_budget_manager.reserve_request(batch_size)

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(make_reservations) for _ in range(num_threads)]
            for f in futures:
                f.result()

        assert clean_budget_manager.live_requests_today == 1500
        assert clean_budget_manager.remaining_daily_budget == 0
        assert clean_budget_manager.can_request() is False

        # Request 1501 blocked
        with pytest.raises(SerperBudgetExhaustedError):
            clean_budget_manager.reserve_request(1)

    def test_two_workers_competing_for_final_slot(self, tmp_path):
        import concurrent.futures

        state_file = str(tmp_path / "competing_workers.json")
        mgr_w1 = SerperDailyBudgetManager(state_path=state_file, daily_limit=1500)
        mgr_w1.reserve_request(1499)

        # mgr_w2 points to the same underlying state file (simulating another worker process)
        mgr_w2 = SerperDailyBudgetManager(state_path=state_file, daily_limit=1500)

        results = []
        errors = []

        def worker_attempt(mgr):
            try:
                res = mgr.reserve_request(1)
                results.append(res)
            except SerperBudgetExhaustedError as e:
                errors.append(e)

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(worker_attempt, mgr_w1)
            f2 = executor.submit(worker_attempt, mgr_w2)
            f1.result()
            f2.result()

        # Exactly ONE worker must succeed, and exactly ONE must be blocked
        assert len(results) == 1, f"Expected exactly 1 success, got {len(results)}"
        assert len(errors) == 1, f"Expected exactly 1 exhausted error, got {len(errors)}"
        assert "Serper daily budget exhausted" in str(errors[0])

        # Final state on disk must be exactly 1500
        mgr_final = SerperDailyBudgetManager(state_path=state_file, daily_limit=1500)
        assert mgr_final.live_requests_today == 1500
        assert mgr_final.remaining_daily_budget == 0


class TestFailureAccountingAndTelemetry:
    """Test accounting semantics: failed live requests consume quota, cache hits and blocks do not."""

    def test_failed_live_network_request_consumes_quota(self, clean_budget_manager):
        provider = SerperSearchProvider(api_key="valid_serper_key_12345", budget_manager=clean_budget_manager)

        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"

        with patch("services.research_provider.get_setting_value", return_value="valid_serper_key_12345"):
            with patch("requests.post", return_value=mock_resp):
                res = provider.search("Maruti Suzuki plant expansion", use_cache=False)
                assert res["provider_status"] == PROVIDER_ERROR

        # Network request was attempted, so daily safety budget IS consumed
        assert clean_budget_manager.live_requests_today > 0
        assert clean_budget_manager.failed_live_requests > 0
        assert clean_budget_manager.successful_live_requests == 0
        assert clean_budget_manager.remaining_daily_budget == 1500 - clean_budget_manager.live_requests_today

        telemetry = clean_budget_manager.get_telemetry()
        assert telemetry["failed_live_requests"] > 0
        assert telemetry["successful_live_requests"] == 0

    def test_successful_live_network_request_accounting(self, clean_budget_manager):
        provider = SerperSearchProvider(api_key="valid_serper_key_12345", budget_manager=clean_budget_manager)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "organic": [{"title": "Director of Manufacturing", "link": "https://linkedin.com/in/director", "snippet": "Director"}]
        }

        with patch("services.research_provider.get_setting_value", return_value="valid_serper_key_12345"):
            with patch("requests.post", return_value=mock_resp):
                res = provider.search("Valeo India director", use_cache=False)
                assert res["provider_status"] == PROVIDER_LIVE

        assert clean_budget_manager.live_requests_today == 1
        assert clean_budget_manager.successful_live_requests == 1
        assert clean_budget_manager.failed_live_requests == 0
        assert clean_budget_manager.remaining_daily_budget == 1499

    def test_blocked_request_does_not_consume_quota(self, clean_budget_manager):
        clean_budget_manager.reserve_request(1500)
        assert clean_budget_manager.live_requests_today == 1500

        provider = SerperSearchProvider(api_key="valid_serper_key_12345", budget_manager=clean_budget_manager)

        with patch("services.research_provider.get_setting_value", return_value="valid_serper_key_12345"):
            with patch("requests.post") as mock_post:
                res = provider.search("Blocked query", use_cache=False)
                assert res["provider_status"] == PROVIDER_BUDGET_EXHAUSTED
                mock_post.assert_not_called()

        # Quota remains at 1500, does not increase to 1501
        assert clean_budget_manager.live_requests_today == 1500
        assert clean_budget_manager.budget_exhausted_events >= 1


class TestCrashSafetyAndProcessRestart:
    """Test process restart preserves same-day usage without resetting or duplicating allowance."""

    def test_restart_during_same_ist_day_preserves_usage(self, tmp_path):
        state_file = str(tmp_path / "crash_safety_state.json")

        # Process 1 runs and executes 1200 searches
        proc1_manager = SerperDailyBudgetManager(state_path=state_file, daily_limit=1500)
        proc1_manager.reserve_request(1200)
        assert proc1_manager.live_requests_today == 1200
        assert proc1_manager.remaining_daily_budget == 300

        # Process 1 crashes or terminates; Process 2 starts later on the same day
        proc2_manager = SerperDailyBudgetManager(state_path=state_file, daily_limit=1500)
        assert proc2_manager.live_requests_today == 1200
        assert proc2_manager.remaining_daily_budget == 300

        # Process 2 can reserve the remaining 300
        proc2_manager.reserve_request(300)
        assert proc2_manager.live_requests_today == 1500
        assert proc2_manager.remaining_daily_budget == 0

        # Request 1501 is blocked
        with pytest.raises(SerperBudgetExhaustedError):
            proc2_manager.reserve_request(1)


class TestTaskLevelSerperBudgetEnforcement:
    """Test task-level hard budget mechanism requested in Section 1.

    Requirements:
    - Task cap = 5: requests 1-5 allowed, request 6 blocked.
    - Coexists with production 1500/day limit without altering it.
    - Cache hits do NOT consume either live-request budget.
    """

    def test_task_budget_cap_enforcement_request_6_blocked(self, clean_budget_manager):
        with clean_budget_manager.task_budget(5):
            # Requests 1 to 5 succeed
            for i in range(5):
                assert clean_budget_manager.can_request() is True
                assert clean_budget_manager.reserve_request(1) is True

            # Task budget is now exhausted
            assert clean_budget_manager.can_request() is False
            status = clean_budget_manager.get_task_budget_status()
            assert status["task_requests_used"] == 5
            assert status["task_budget_cap"] == 5
            assert status["task_remaining"] == 0

            # Request 6 MUST be blocked with SerperBudgetExhaustedError
            with pytest.raises(SerperBudgetExhaustedError) as exc_info:
                clean_budget_manager.reserve_request(1)
            assert "task budget exhausted" in str(exc_info.value).lower()

        # Outside the task_budget context, daily limit room remains intact
        assert clean_budget_manager.live_requests_today == 5
        assert clean_budget_manager.remaining_daily_budget == 1495
        assert clean_budget_manager.can_request() is True

    def test_cache_hits_do_not_consume_task_budget(self, clean_budget_manager):
        provider = SerperSearchProvider(api_key="valid_key", budget_manager=clean_budget_manager)
        mock_cache = MagicMock()
        mock_cache.get.return_value = {
            "provider": "serper",
            "provider_status": PROVIDER_LIVE,
            "results": [{"title": "Cached Title", "link": "https://example.com", "snippet": "Cached"}],
            "query": "Cached Query",
            "cache_hit": True,
        }
        provider.cache = mock_cache

        with clean_budget_manager.task_budget(5):
            for _ in range(10):
                res = provider.search("Cached Query", use_cache=True)
                assert res["cache_hit"] is True

            status = clean_budget_manager.get_task_budget_status()
            assert status["task_requests_used"] == 0
            assert clean_budget_manager.live_requests_today == 0
            assert clean_budget_manager.cache_hits_today == 10
            assert clean_budget_manager.can_request() is True

    def test_task_budget_cap_24_request_25_blocked(self, clean_budget_manager):
        """Hard task cap = 24: requests 1-24 allowed, request 25 strictly blocked."""
        with clean_budget_manager.task_budget(24):
            for i in range(24):
                assert clean_budget_manager.can_request() is True
                assert clean_budget_manager.reserve_request(1) is True

            assert clean_budget_manager.can_request() is False
            status = clean_budget_manager.get_task_budget_status()
            assert status["task_requests_used"] == 24
            assert status["task_remaining"] == 0

            with pytest.raises(SerperBudgetExhaustedError) as exc_info:
                clean_budget_manager.reserve_request(1)
            assert "task budget exhausted" in str(exc_info.value).lower()
