"""Unit tests for Search Provider Benchmark and Strict Anti-Leakage Guard."""
from __future__ import annotations

import json
import os
import re
from unittest.mock import MagicMock, patch
import pytest

from scripts.run_search_provider_benchmark import (
    generate_benchmark_search_queries,
    generate_gemini_grounded_prompts,
    RequestTracker,
    BudgetLimitExceeded,
    run_candidate_extraction_pipeline,
    match_expected_person,
    BENCHMARK_CASES_PATH,
)
from services.person_intelligence_service import generate_person_search_queries
from services.research_provider import (
    ResearchProvider,
    SerperSearchProvider,
    GeminiGroundedSearchProvider,
    SearXNGProvider,
    ResearchResult,
    PROVIDER_LIVE,
    PROVIDER_QUOTA_EXHAUSTED,
    PROVIDER_ERROR,
    PROVIDER_NOT_CONFIGURED,
)
from services.search_cache import SearchCache


GOLD_PERSON_FULL_NAMES = [
    "Atul Jain",
    "Abhijit Biswal",
    "Ravi Singh",
    "Vijayaraghavan Manian",
    "Dharmendra Chouhan",
]

# Sensitive identity parts that must never appear in generated queries
GOLD_PERSON_SENSITIVE_TOKENS = [
    "atul jain",
    "abhijit biswal",
    "ravi singh",
    "vijayaraghavan manian",
    "dharmendra chouhan",
    "vijayaraghavan",
    "chouhan",
    "biswal",
]


def test_anti_leakage_benchmark_queries():
    """MANDATORY: Verify that zero expected person identities enter search queries or prompts."""
    with open(BENCHMARK_CASES_PATH, "r", encoding="utf-8") as f:
        cases = json.load(f)

    all_generated_texts = []

    for case in cases:
        company = case["company"]
        facility = case.get("facility", "")
        city = case.get("city", "")
        domain = case.get("company_domain", "")
        sector = case.get("sector", "")
        context = case.get("function_context", "")

        # 1. Bounded Serper Queries
        serper_queries = generate_benchmark_search_queries(
            company=company,
            facility=facility,
            city=city,
            domain=domain,
            sector=sector,
            function_context=context,
        )
        for q in serper_queries:
            all_generated_texts.append(q["query"].lower())

        # 2. Gemini Grounded Prompts
        gemini_prompts = generate_gemini_grounded_prompts(
            company=company,
            facility=facility,
            city=city,
            domain=domain,
            sector=sector,
            function_context=context,
        )
        for p in gemini_prompts:
            all_generated_texts.append(p.lower())

        # 3. Existing broad person queries
        broad_queries = generate_person_search_queries(
            company_name=company,
            facility_name=facility,
            city=city,
            company_domain=domain,
            sector=sector,
        )
        for bq in broad_queries:
            all_generated_texts.append(bq["query"].lower())

    # Assert that none of the sensitive tokens appear anywhere in generated queries
    for text in all_generated_texts:
        for sensitive in GOLD_PERSON_SENSITIVE_TOKENS:
            assert sensitive not in text, (
                f"LEAK DETECTED! Expected identity '{sensitive}' found inside query: '{text}'"
            )


def test_provider_common_interface():
    """Verify that all search providers inherit from ResearchProvider and implement common methods."""
    serper = SerperSearchProvider()
    gemini = GeminiGroundedSearchProvider()
    searxng = SearXNGProvider()

    for provider in [serper, gemini, searxng]:
        assert isinstance(provider, ResearchProvider)
        assert hasattr(provider, "search")
        assert hasattr(provider, "get_status")
        assert hasattr(provider, "is_available")


def test_serper_search_provider_normalization():
    """Verify Serper results normalize into ResearchResult schema."""
    provider = SerperSearchProvider(api_key="mock-serper-key-12345")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "organic": [
            {
                "title": "Atul Jain - Vice President & Plant Head - Maruti Suzuki",
                "link": "https://in.linkedin.com/in/atul-jain-12345",
                "snippet": "Atul Jain is Vice President and Plant Head at Maruti Suzuki Hansalpur plant.",
                "position": 1,
            },
            {
                "title": "Maruti Suzuki Hansalpur News",
                "link": "https://marutisuzuki.com/press",
                "snippet": "Production expansion at Hansalpur facility.",
                "position": 2,
            },
        ]
    }

    with patch("requests.post", return_value=mock_resp):
        res = provider.search("Maruti Suzuki Hansalpur plant head", num_results=5, use_cache=False)

    assert res["provider"] == "serper"
    assert res["provider_status"] == PROVIDER_LIVE
    assert len(res["results"]) == 2
    first = res["results"][0]
    assert first["title"] == "Atul Jain - Vice President & Plant Head - Maruti Suzuki"
    assert first["url"] == "https://in.linkedin.com/in/atul-jain-12345"
    assert first["position"] == 1
    assert first["provider"] == "serper"
    assert first["evidence_type"] == "WEB_EVIDENCE"


def test_gemini_grounded_provider_normalization():
    """Verify Gemini Grounded search normalizes groundingMetadata into ResearchResult schema."""
    provider = GeminiGroundedSearchProvider(api_key="mock-gemini-key-12345")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": "The plant head at Hansalpur is Atul Jain."}],
                },
                "groundingMetadata": {
                    "webSearchQueries": ["Maruti Suzuki Hansalpur plant head"],
                    "groundingChunks": [
                        {
                            "web": {
                                "uri": "https://in.linkedin.com/in/atul-jain",
                                "title": "Atul Jain - VP & Plant Head",
                            }
                        }
                    ],
                    "groundingSupports": [
                        {
                            "segment": {"text": "The plant head at Hansalpur is Atul Jain."},
                            "groundingChunkIndices": [0],
                        }
                    ],
                },
            }
        ]
    }

    with patch("requests.post", return_value=mock_resp):
        res = provider.search("Who is the plant head?", num_results=5, use_cache=False)

    assert res["provider"] == "gemini_grounded"
    assert res["provider_status"] == PROVIDER_LIVE
    assert len(res["results"]) == 1
    chunk = res["results"][0]
    assert chunk["title"] == "Atul Jain - VP & Plant Head"
    assert chunk["url"] == "https://in.linkedin.com/in/atul-jain"
    assert "Atul Jain" in chunk["snippet"]
    assert chunk["provider"] == "gemini_grounded"
    assert chunk["evidence_type"] == "GROUNDED_WEB_EVIDENCE"


def test_gemini_grounded_handles_quota_429():
    """Verify that HTTP 429 quota exhaustion is safely handled without raising an unhandled exception."""
    provider = GeminiGroundedSearchProvider(api_key="mock-gemini-key-12345")

    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_resp.text = '{"error": {"code": 429, "message": "You exceeded your current quota"}}'
    mock_resp.json.return_value = {"error": {"code": 429, "message": "You exceeded your current quota"}}

    with patch("requests.post", return_value=mock_resp):
        res = provider.search("Who is the plant head?", num_results=5, use_cache=False)

    assert res["provider"] == "gemini_grounded"
    assert res["provider_status"] == PROVIDER_QUOTA_EXHAUSTED
    assert res["results"] == []
    assert "429" in res["error"] or "Quota" in res["error"]


def test_search_cache_hit_and_miss(tmp_path):
    """Verify search cache stores results and returns cache_hit=True on duplicate calls."""
    cache_file = str(tmp_path / "test_cache.json")
    cache = SearchCache(cache_path=cache_file)

    assert cache.get("serper", "test query") is None

    payload = {"provider": "serper", "results": [{"title": "Example"}]}
    cache.set("serper", "test query", payload)

    cached = cache.get("serper", "test query")
    assert cached is not None
    assert cached["cache_hit"] is True
    assert cached["results"] == [{"title": "Example"}]


def test_request_tracker_budget_enforcement():
    """Verify that RequestTracker strictly blocks requests beyond limit."""
    tracker = RequestTracker(max_requests=2)
    assert tracker.can_request() is True

    tracker.record_call(cache_hit=False, latency_ms=100.0)
    assert tracker.live_requests == 1
    assert tracker.can_request() is True

    tracker.record_call(cache_hit=False, latency_ms=120.0)
    assert tracker.live_requests == 2
    assert tracker.can_request() is False

    with pytest.raises(BudgetLimitExceeded):
        tracker.record_call(cache_hit=False, latency_ms=110.0)
