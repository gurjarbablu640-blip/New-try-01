"""Unit tests for LLMDiscoveryStrategist (Task 3D.1A).

Tests all required requirements:
- DeepSeek primary
- Gemini fallback
- Malformed JSON repair
- 3-candidate output validation
- Selection of valid candidate
- Duplicate rejection
- Cooldown rejection
- Keyword-spam and sanity guard rejections
- Adaptive relaxation context
- Success exploitation context
- Both LLMs unavailable -> deterministic planner fallback
"""
import json
import pytest
from unittest.mock import MagicMock, patch

from services.llm_discovery_strategist import (
    LLMDiscoveryStrategist,
    get_telemetry,
    reset_telemetry,
)
from services.llm_provider import LLMResponse


@pytest.fixture(autouse=True)
def clean_telemetry():
    reset_telemetry()
    yield
    reset_telemetry()


class MockLLMProvider:
    """Configurable mock LLM provider for unit tests."""

    def __init__(self, responses=None, available=True, raises=None):
        self.responses = list(responses or [])
        self.available = available
        self.raises = raises
        self.call_count = 0
        self.calls = []

    def is_available(self) -> bool:
        return self.available

    def complete(self, system_prompt: str, messages: list, **kwargs) -> LLMResponse:
        self.call_count += 1
        self.calls.append({"system_prompt": system_prompt, "messages": messages, "kwargs": kwargs})

        if self.raises:
            raise self.raises

        if self.responses:
            resp_content = self.responses.pop(0)
            if isinstance(resp_content, Exception):
                raise resp_content
            return LLMResponse(text=resp_content, provider="mock", model="mock-model")

        return LLMResponse(text="{}", provider="mock", model="mock-model")


# ── 1. DeepSeek Primary Success ───────────────────────────────────────────────

def test_deepseek_primary_success():
    valid_json = json.dumps({
        "strategy_summary": "Natural search targeting Chakan auto component expansions",
        "candidates": [
            {
                "query": "automotive component plant expansion Chakan",
                "search_goal": "Identify tier-1 auto supplier capacity expansions",
                "search_lane": "EVENT_EXPANSION",
                "sector": "Automotive & Auto Components",
                "geography": {"country": "India", "state": "Maharashtra", "cluster": "Chakan"},
                "expected_signal": "new manufacturing unit inauguration",
                "reason": "Chakan is a high-density auto hub with ongoing expansions",
                "confidence": 0.92,
            }
        ]
    })

    mock_deepseek = MockLLMProvider(responses=[valid_json])
    mock_gemini = MockLLMProvider(available=True)
    mock_memory = MagicMock()
    mock_memory.is_query_in_cooldown.return_value = False

    strategist = LLMDiscoveryStrategist(
        primary_provider=mock_deepseek,
        fallback_provider=mock_gemini,
        memory=mock_memory,
    )

    result = strategist.plan_query(
        db=None,
        sector="Automotive & Auto Components",
        geography="Maharashtra",
    )

    assert result["provider"] == "DeepSeek"
    assert result["query"] == "automotive component plant expansion Chakan"
    assert result["confidence"] == 0.92
    assert mock_deepseek.call_count == 1
    assert mock_gemini.call_count == 0  # Fallback was not needed

    telemetry = get_telemetry()
    assert telemetry["DISCOVERY_LLM_PLANNER_CALLS"] == 1
    assert telemetry["DISCOVERY_LLM_PRIMARY_SUCCESS"] == 1
    assert telemetry["DISCOVERY_LLM_FALLBACK_USED"] == 0


# ── 2. Gemini Fallback when DeepSeek Fails ────────────────────────────────────

def test_gemini_fallback_when_deepseek_fails():
    gemini_json = json.dumps({
        "strategy_summary": "Electronics facility discovery in Sriperumbudur",
        "candidates": [
            {
                "query": "new electronics manufacturing facility Sriperumbudur",
                "search_goal": "Find EMS PCB assembly expansions",
                "search_lane": "EVENT_EXPANSION",
                "sector": "Semiconductor & Electronics (EMS)",
                "geography": {"country": "India", "state": "Tamil Nadu", "cluster": "Sriperumbudur"},
                "expected_signal": "plant commissioning",
                "reason": "Tamil Nadu EMS hub",
                "confidence": 0.88,
            }
        ]
    })

    mock_deepseek = MockLLMProvider(raises=RuntimeError("DeepSeek API 504 Gateway Timeout"))
    mock_gemini = MockLLMProvider(responses=[gemini_json])
    mock_memory = MagicMock()
    mock_memory.is_query_in_cooldown.return_value = False

    strategist = LLMDiscoveryStrategist(
        primary_provider=mock_deepseek,
        fallback_provider=mock_gemini,
        memory=mock_memory,
    )

    result = strategist.plan_query(
        db=None,
        sector="Semiconductor & Electronics (EMS)",
        geography="Tamil Nadu",
    )

    assert result["provider"] == "Gemini"
    assert result["query"] == "new electronics manufacturing facility Sriperumbudur"
    assert mock_deepseek.call_count == 1
    assert mock_gemini.call_count == 1

    telemetry = get_telemetry()
    assert telemetry["DISCOVERY_LLM_PLANNER_CALLS"] == 1
    assert telemetry["DISCOVERY_LLM_PRIMARY_FAILURE"] == 1
    assert telemetry["DISCOVERY_LLM_FALLBACK_USED"] == 1


# ── 3. Malformed JSON Repair ──────────────────────────────────────────────────

def test_malformed_json_repair():
    bad_raw_json = "Sure, here are queries:\n```json\n{ candidates: [ {query: 'broken json'\n```"
    repaired_json = json.dumps({
        "strategy_summary": "Repaired solar expansion discovery",
        "candidates": [
            {
                "query": "solar manufacturing plant Gujarat expansion",
                "search_goal": "Solar PV module expansion",
                "search_lane": "CAPEX_PROJECT",
                "sector": "Solar & Renewable Energy Equipment",
                "geography": {"country": "India", "state": "Gujarat", "cluster": "Dholera"},
                "expected_signal": "capex announcement",
                "reason": "Gujarat solar corridor",
                "confidence": 0.89,
            }
        ]
    })

    mock_deepseek = MockLLMProvider(responses=[bad_raw_json, repaired_json])
    mock_memory = MagicMock()
    mock_memory.is_query_in_cooldown.return_value = False

    strategist = LLMDiscoveryStrategist(
        primary_provider=mock_deepseek,
        fallback_provider=MockLLMProvider(),
        memory=mock_memory,
    )

    result = strategist.plan_query(db=None, sector="Solar & Renewable Energy Equipment")

    assert result["provider"] == "DeepSeek"
    assert result["query"] == "solar manufacturing plant Gujarat expansion"
    assert mock_deepseek.call_count == 2  # 1 initial + 1 repair


# ── 4. Three Candidate Output Structure ───────────────────────────────────────

def test_three_candidate_output_structure():
    three_candidates_json = json.dumps({
        "strategy_summary": "Multi-angle exploration for EV battery sector",
        "candidates": [
            {
                "query": "electric vehicle battery manufacturing plant Hosur",
                "search_goal": "EV battery pack plant setup",
                "search_lane": "EVENT_EXPANSION",
                "sector": "EV & Battery Systems",
                "geography": {"country": "India", "state": "Tamil Nadu", "cluster": "Hosur"},
                "expected_signal": "facility opening",
                "reason": "Hosur EV corridor",
                "confidence": 0.94,
            },
            {
                "query": "battery pack assembly facility Pune expansion",
                "search_goal": "Auto battery pack plant expansion",
                "search_lane": "EVENT_EXPANSION",
                "sector": "EV & Battery Systems",
                "geography": {"country": "India", "state": "Maharashtra", "cluster": "Pune"},
                "expected_signal": "capex addition",
                "reason": "Pune industrial belt",
                "confidence": 0.86,
            },
            {
                "query": "lithium cell gigafactory Gujarat project",
                "search_goal": "Greenfield gigafactory project",
                "search_lane": "CAPEX_PROJECT",
                "sector": "EV & Battery Systems",
                "geography": {"country": "India", "state": "Gujarat", "cluster": "Sanand"},
                "expected_signal": "groundbreaking",
                "reason": "Sanand EV investments",
                "confidence": 0.80,
            },
        ]
    })

    mock_deepseek = MockLLMProvider(responses=[three_candidates_json])
    mock_memory = MagicMock()
    mock_memory.is_query_in_cooldown.return_value = False

    strategist = LLMDiscoveryStrategist(
        primary_provider=mock_deepseek,
        fallback_provider=MockLLMProvider(),
        memory=mock_memory,
    )

    result = strategist.plan_query(db=None, sector="EV & Battery Systems")

    assert result["provider"] == "DeepSeek"
    assert len(result["candidates_proposed"]) == 3
    # Selected strongest (confidence 0.94)
    assert result["query"] == "electric vehicle battery manufacturing plant Hosur"
    assert result["confidence"] == 0.94


# ── 5. Selection of Highest Confidence Valid Candidate ────────────────────────

def test_selection_of_valid_candidate_skipping_invalid():
    candidates_json = json.dumps({
        "strategy_summary": "Test prioritization and validation",
        "candidates": [
            {
                "query": "too short",  # Invalid (too short)
                "confidence": 0.99,
            },
            {
                "query": "pharma manufacturing project Telangana commissioning",
                "search_goal": "Pharma sterile injectables commissioning",
                "search_lane": "EVENT_EXPANSION",
                "sector": "Pharmaceuticals & Bulk Drugs",
                "geography": {"country": "India", "state": "Telangana", "cluster": "Genome Valley"},
                "confidence": 0.91,
            },
            {
                "query": "bulk drug active pharmaceutical ingredient unit Hyderabad",
                "confidence": 0.75,
            },
        ]
    })

    mock_deepseek = MockLLMProvider(responses=[candidates_json])
    mock_memory = MagicMock()
    mock_memory.is_query_in_cooldown.return_value = False

    strategist = LLMDiscoveryStrategist(
        primary_provider=mock_deepseek,
        fallback_provider=MockLLMProvider(),
        memory=mock_memory,
    )

    result = strategist.plan_query(db=None, sector="Pharmaceuticals & Bulk Drugs")

    # Should skip "too short" and pick confidence 0.91
    assert result["query"] == "pharma manufacturing project Telangana commissioning"
    assert result["confidence"] == 0.91

    telemetry = get_telemetry()
    assert telemetry["DISCOVERY_LLM_QUERY_REJECTED_SANITY"] == 1
    assert telemetry["DISCOVERY_LLM_QUERY_SELECTED"] == 1


# ── 6. Duplicate Rejection ────────────────────────────────────────────────────

def test_duplicate_rejection():
    candidates_json = json.dumps({
        "strategy_summary": "Testing batch duplicate rejection",
        "candidates": [
            {
                "query": "manufacturers Pithampur new plant",
                "confidence": 0.95,
            },
            {
                "query": "manufacturers Pithampur new plant",  # Exact duplicate in same batch
                "confidence": 0.90,
            },
        ]
    })

    mock_deepseek = MockLLMProvider(responses=[candidates_json])
    mock_memory = MagicMock()
    mock_memory.is_query_in_cooldown.return_value = False

    strategist = LLMDiscoveryStrategist(
        primary_provider=mock_deepseek,
        fallback_provider=MockLLMProvider(),
        memory=mock_memory,
    )

    result = strategist.plan_query(db=None)

    assert result["query"] == "manufacturers Pithampur new plant"
    telemetry = get_telemetry()
    assert telemetry["DISCOVERY_LLM_QUERY_REJECTED_SANITY"] == 1


# ── 7. Cooldown Rejection ─────────────────────────────────────────────────────

def test_cooldown_rejection():
    candidates_json = json.dumps({
        "strategy_summary": "Testing 24h cooldown collision handling",
        "candidates": [
            {
                "query": "solar manufacturing plant Gujarat expansion",  # In cooldown
                "confidence": 0.95,
            },
            {
                "query": "solar cell module manufacturing unit Dholera",  # Fresh
                "confidence": 0.88,
            },
        ]
    })

    mock_deepseek = MockLLMProvider(responses=[candidates_json])
    mock_memory = MagicMock()
    # First query in cooldown, second is not
    mock_memory.is_query_in_cooldown.side_effect = lambda q, page=1, db=None: "gujarat" in q

    strategist = LLMDiscoveryStrategist(
        primary_provider=mock_deepseek,
        fallback_provider=MockLLMProvider(),
        memory=mock_memory,
    )

    result = strategist.plan_query(db=None)

    # Picked second candidate because first was in cooldown
    assert result["query"] == "solar cell module manufacturing unit Dholera"
    assert result["confidence"] == 0.88

    telemetry = get_telemetry()
    assert telemetry["DISCOVERY_LLM_QUERY_REJECTED_COOLDOWN"] == 1
    assert telemetry["DISCOVERY_LLM_QUERY_SELECTED"] == 1


# ── 8. Keyword-Spam and Sanity Guard Rejections ───────────────────────────────

def test_keyword_spam_and_sanity_rules():
    strategist = LLMDiscoveryStrategist(memory=MagicMock())

    # Empty
    valid, reason = strategist.validate_candidate_sanity("")
    assert not valid
    assert "empty" in reason.lower()

    # Too short
    valid, reason = strategist.validate_candidate_sanity("auto")
    assert not valid
    assert "too short" in reason.lower()

    # Too long (> 200 chars)
    long_q = "automotive plant " * 15
    valid, reason = strategist.validate_candidate_sanity(long_q)
    assert not valid
    assert "too long" in reason.lower()

    # Unbalanced quotes
    valid, reason = strategist.validate_candidate_sanity('plant "expansion Maharashtra')
    assert not valid
    assert "unbalanced quotation" in reason.lower()

    # Unbalanced parentheses
    valid, reason = strategist.validate_candidate_sanity("plant expansion (Maharashtra")
    assert not valid
    assert "unbalanced parentheses" in reason.lower()

    # Obvious token repetition
    valid, reason = strategist.validate_candidate_sanity("solar solar solar plant expansion")
    assert not valid
    assert "token repetition" in reason.lower()

    # Excessive negative keyword tail (> 3 negative terms)
    spam_neg = "plant expansion -stock -share -brokerage -screener -dividend"
    valid, reason = strategist.validate_candidate_sanity(spam_neg)
    assert not valid
    assert "negative keyword tail" in reason.lower()

    # Overconstrained syntax (> 2 separate quoted phrases)
    overconstrained = '"Maharashtra" "automotive components" "capex" plant'
    valid, reason = strategist.validate_candidate_sanity(overconstrained)
    assert not valid
    assert "overconstrained syntax" in reason.lower()

    # Natural valid search query
    valid, reason = strategist.validate_candidate_sanity("automotive component plant expansion Chakan")
    assert valid
    assert reason is None


# ── 9. Adaptive Relaxation Context ────────────────────────────────────────────

def test_adaptive_relaxation_context():
    strategist = LLMDiscoveryStrategist(memory=MagicMock())
    context = strategist.build_search_context(
        db=None,
        sector="Metals & Advanced Alloys Processing",
        geography="Gujarat",
        trigger="capex_announcement",
    )

    assert context["target_sector"] == "Metals & Advanced Alloys Processing"
    assert context["target_geography"] == "Gujarat"
    assert "funnel_bottleneck" in context
    assert "performance_summary" in context
    assert "Metals & Advanced Alloys (100% zero)" in context["performance_summary"]["weakest_sectors"]


# ── 10. Success Exploitation Context ──────────────────────────────────────────

def test_success_exploitation_context():
    strategist = LLMDiscoveryStrategist(memory=MagicMock())
    context = strategist.build_search_context(
        db=None,
        sector="Solar & Renewable Energy Equipment",
        geography="Gujarat",
        search_lane="CLUSTER_EXPLOITATION",
    )

    assert context["search_lane"] == "CLUSTER_EXPLOITATION"
    assert "NEWS_NATURAL (100% productive)" in context["performance_summary"]["top_productive_archetypes"]


# ── 11. Both LLMs Unavailable Fallback to Deterministic Planner ───────────────

def test_both_llms_unavailable_fallback_to_deterministic():
    mock_deepseek = MockLLMProvider(raises=RuntimeError("DeepSeek down"))
    mock_gemini = MockLLMProvider(raises=RuntimeError("Gemini down"))
    mock_memory = MagicMock()
    mock_memory.is_query_in_cooldown.return_value = False

    strategist = LLMDiscoveryStrategist(
        primary_provider=mock_deepseek,
        fallback_provider=mock_gemini,
        memory=mock_memory,
    )

    result = strategist.plan_query(
        db=None,
        sector="Automotive & Auto Components",
        geography="Maharashtra",
    )

    assert result["provider"] == "deterministic_fallback"
    assert result["query"] != ""
    assert "Automotive" in result["sector"]
    assert mock_deepseek.call_count == 1
    assert mock_gemini.call_count == 1


# ── 12. Query Planner Delegation Method ───────────────────────────────────────

def test_planner_delegation_method():
    from services.discovery_query_planner import discovery_query_planner

    with patch("services.llm_discovery_strategist.llm_discovery_strategist.plan_query") as mock_plan:
        mock_plan.return_value = {
            "query": "mocked query",
            "provider": "DeepSeek",
            "confidence": 0.9,
        }
        res = discovery_query_planner.plan_with_llm_strategist(
            db=None,
            preferred_sector="Automotive & Auto Components",
            preferred_geo="Maharashtra",
        )
        assert res["query"] == "mocked query"
        assert res["provider"] == "DeepSeek"
        mock_plan.assert_called_once()
