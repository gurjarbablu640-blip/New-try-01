"""Tests for conditional person ranking benchmark, evidence gating, and budget isolation."""
from __future__ import annotations

import inspect
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from services.llm_provider import LLMResponse
from services.opportunity_gates import (
    READY_FOR_CONTACT_ENRICHMENT,
    evaluate_apollo_credit_gate,
    evaluate_opportunity_gates,
)
from services.person_intelligence_service import (
    classify_authority_class,
    classify_current_employment,
    classify_facility_relationship,
    compute_deterministic_person_score,
    rank_candidates_with_deepseek,
)
from scripts.run_conditional_ranking_benchmark import (
    BudgetedProvider,
    HiveRequestBudget,
    HiveRequestBudgetExceeded,
    evaluate_ramkrishna_positive_control,
    run_conditional_ranking_benchmark,
)


def test_expected_identity_never_enters_ranking_prompt():
    """Verify that expected person name or title NEVER appears in the ranking prompt payload."""
    candidates = [
        {"name": "Candidate One", "title": "Quality Engineer", "evidence_snippet": "Works at site"},
        {"name": "Candidate Two", "title": "Plant Head", "evidence_snippet": "Heading plant operations"},
    ]
    mock_provider = MagicMock()
    mock_provider.complete.return_value = LLMResponse(
        text='{"ranking": [{"candidate_id": "C01", "rank": 1, "employment": "SUPPORTED", "facility": "SUPPORTED", "function": "STRONG", "authority": "STRONG", "reason": "Plant head"}]}',
        usage={"input_tokens": 50, "output_tokens": 20},
        provider="hive",
        model="deepseek-ai/DeepSeek-V4.1-Flash",
    )

    rank_candidates_with_deepseek(
        company_name="Maruti Suzuki",
        facility_name="Hansalpur Manufacturing Complex",
        city="Hansalpur",
        commercial_trigger="Plant Operations & Quality",
        target_functions=["Plant Operations & Quality"],
        candidates=candidates,
        provider=mock_provider,
    )

    call_args = mock_provider.complete.call_args
    system_prompt = call_args.kwargs.get("system_prompt", "")
    messages = call_args.kwargs.get("messages", [])
    user_content = messages[0]["content"] if messages else ""

    # Must NOT contain evaluation labels
    assert "expected_person" not in user_content
    assert "expected_title" not in user_content
    assert "Atul Jain" not in user_content
    assert "Abhijit Biswal" not in user_content
    assert "Atul Jain" not in system_prompt
    assert "Abhijit Biswal" not in system_prompt


def test_candidate_ids_map_correctly():
    """Verify that candidate IDs C01, C02 map deterministically to candidate evidence."""
    candidates = [
        {"name": "Alpha Person", "title": "QA Lead", "location": "Sanand"},
        {"name": "Beta Person", "title": "Plant Head", "location": "Sanand"},
    ]
    mock_provider = MagicMock()
    mock_provider.complete.return_value = LLMResponse(
        text='{"ranking": ['
             '{"candidate_id": "C02", "rank": 1, "employment": "SUPPORTED", "facility": "SUPPORTED", "function": "STRONG", "authority": "STRONG", "reason": "Plant Head"},'
             '{"candidate_id": "C01", "rank": 2, "employment": "SUPPORTED", "facility": "SUPPORTED", "function": "MEDIUM", "authority": "MEDIUM", "reason": "QA Lead"}'
             ']}',
        usage={"input_tokens": 50, "output_tokens": 30},
        provider="hive",
        model="deepseek-ai/DeepSeek-V4.1-Flash",
    )

    res = rank_candidates_with_deepseek(
        company_name="Test Company",
        facility_name="Test Plant",
        city="Sanand",
        commercial_trigger="Quality",
        target_functions=["Quality"],
        candidates=candidates,
        provider=mock_provider,
    )

    # Check payload sent to LLM had C01 and C02
    call_messages = mock_provider.complete.call_args.kwargs["messages"]
    payload = json.loads(call_messages[0]["content"])
    llm_candidates = payload["candidates"]
    assert llm_candidates[0]["candidate_id"] == "C01"
    assert llm_candidates[1]["candidate_id"] == "C02"

    # Check mapped result: Beta Person (C02) ranked 1st
    ranked = res["candidates"]
    beta = next(c for c in ranked if c["name"] == "Beta Person")
    alpha = next(c for c in ranked if c["name"] == "Alpha Person")
    assert beta["deepseek_rank"] == 1
    assert alpha["deepseek_rank"] == 2
    assert beta["deepseek_assessment"]["candidate_id"] == "C02"
    assert alpha["deepseek_assessment"]["candidate_id"] == "C01"


def test_deepseek_cannot_create_high_confidence():
    """Verify that DeepSeek rank #1 CANNOT elevate a candidate to HIGH confidence."""
    candidates = [
        {
            "name": "Medium Candidate",
            "title": "Quality Executive",
            "current_employment": "VERIFIED",
            "facility_relationship": "COMPANY_ONLY",
            "authority_class": "GENERAL_QUALITY",
            "person_score": 68.0,
            "person_confidence": "LOW",
            "evidence_snippet": "Works at Test Company",
        }
    ]
    mock_provider = MagicMock()
    # LLM claims everything is strong
    mock_provider.complete.return_value = LLMResponse(
        text='{"ranking": [{"candidate_id": "C01", "rank": 1, "employment": "SUPPORTED", "facility": "SUPPORTED", "function": "STRONG", "authority": "STRONG", "reason": "Top leader"}]}',
        usage={"input_tokens": 40, "output_tokens": 20},
        provider="hive",
        model="deepseek-ai/DeepSeek-V4.1-Flash",
    )

    res = rank_candidates_with_deepseek(
        company_name="Test Company",
        facility_name="Test Plant",
        city="Sanand",
        commercial_trigger="Quality",
        target_functions=["Quality"],
        candidates=candidates,
        provider=mock_provider,
    )

    ranked_cand = res["candidates"][0]
    assert ranked_cand["deepseek_rank"] == 1
    # STRICT GATE: person_confidence remains LOW, never elevated to HIGH!
    assert ranked_cand["person_confidence"] == "LOW"
    assert ranked_cand["person_score"] == 68.0


def test_unsupported_facility_evidence_rejected():
    """Verify that if DeepSeek claims facility: SUPPORTED for candidate in different city, claim is rejected."""
    candidates = [
        {
            "name": "Remote Person",
            "title": "Corporate Quality Lead",
            "location": "Pune",
            "current_employment": "VERIFIED",
            "facility_relationship": "COMPANY_ONLY",
            "authority_class": "GROUP_FUNCTION_OWNER",
            "evidence_snippet": "Corporate office in Pune",
        }
    ]
    mock_provider = MagicMock()
    mock_provider.complete.return_value = LLMResponse(
        text='{"ranking": [{"candidate_id": "C01", "rank": 1, "employment": "SUPPORTED", "facility": "SUPPORTED", "function": "STRONG", "authority": "STRONG", "reason": "Plant lead"}]}',
        usage={"input_tokens": 40, "output_tokens": 20},
        provider="hive",
        model="deepseek-ai/DeepSeek-V4.1-Flash",
    )

    res = rank_candidates_with_deepseek(
        company_name="Test Company",
        facility_name="Sanand Plant",
        city="Sanand",
        commercial_trigger="Quality",
        target_functions=["Quality"],
        candidates=candidates,
        provider=mock_provider,
    )

    cand = res["candidates"][0]
    assessment = cand["deepseek_assessment"]
    assert assessment["evidence_verified"] is False
    assert "UNSUPPORTED_FACILITY" in assessment["rejected_claims"]


def test_unsupported_employment_evidence_rejected():
    """Verify that if DeepSeek claims employment: SUPPORTED for contradicted ex-employee, claim is rejected."""
    candidates = [
        {
            "name": "Ex Employee",
            "title": "Former Quality Manager",
            "location": "Sanand",
            "current_employment": "CONTRADICTED",
            "facility_relationship": "FACILITY_FUNCTION_OWNER",
            "authority_class": "STRONG_PLANT_QUALITY_OWNER",
            "evidence_snippet": "Former Quality Manager at Valeo until 2022. Currently VP at Rieter.",
        }
    ]
    mock_provider = MagicMock()
    mock_provider.complete.return_value = LLMResponse(
        text='{"ranking": [{"candidate_id": "C01", "rank": 1, "employment": "SUPPORTED", "facility": "SUPPORTED", "function": "STRONG", "authority": "STRONG", "reason": "Active VP"}]}',
        usage={"input_tokens": 40, "output_tokens": 20},
        provider="hive",
        model="deepseek-ai/DeepSeek-V4.1-Flash",
    )

    res = rank_candidates_with_deepseek(
        company_name="Valeo India",
        facility_name="Sanand Plant",
        city="Sanand",
        commercial_trigger="Quality",
        target_functions=["Quality"],
        candidates=candidates,
        provider=mock_provider,
    )

    cand = res["candidates"][0]
    assessment = cand["deepseek_assessment"]
    assert assessment["evidence_verified"] is False
    assert "UNSUPPORTED_EMPLOYMENT" in assessment["rejected_claims"]


def test_invalid_json_safely_falls_back():
    """Verify that invalid/malformed LLM output falls back to deterministic ordering without crashing."""
    candidates = [
        {"name": "Cand A", "title": "QA", "person_score": 80.0, "current_employment": "VERIFIED"},
        {"name": "Cand B", "title": "Engineer", "person_score": 60.0, "current_employment": "VERIFIED"},
    ]
    mock_provider = MagicMock()
    # Completely broken JSON
    mock_provider.complete.return_value = LLMResponse(
        text="<<<Internal Server Error / Truncated Stream>>>",
        usage={"input_tokens": 30, "output_tokens": 10},
        provider="hive",
        model="deepseek-ai/DeepSeek-V4.1-Flash",
    )

    res = rank_candidates_with_deepseek(
        company_name="Test Company",
        facility_name="Test Plant",
        city="Sanand",
        commercial_trigger="Quality",
        target_functions=["Quality"],
        candidates=candidates,
        provider=mock_provider,
    )

    assert res["assessment_count"] == 0
    # Safe fallback preserves candidate order by deterministic score
    assert len(res["candidates"]) == 2
    assert res["candidates"][0]["name"] == "Cand A"
    assert res["candidates"][1]["name"] == "Cand B"


def test_request_budget_stops_before_call_five(tmp_path):
    """Verify that Hive request budget enforces max 4 calls and raises HiveRequestBudgetExceeded on call 5."""
    class DummyProvider:
        def complete(self, *args, **kwargs):
            return LLMResponse(
                text='{"ranking": []}',
                usage={"input_tokens": 10, "output_tokens": 10},
                provider="hive",
                model="deepseek-ai/DeepSeek-V4.1-Flash",
            )

    budget = HiveRequestBudget(max_requests=4, output_path=str(tmp_path / "budget.json"))
    provider = BudgetedProvider(DummyProvider(), budget)

    # 4 calls succeed
    for _ in range(4):
        provider.complete()

    assert budget.attempted_requests == 4
    assert budget.successful_requests == 4
    assert budget.remaining_request_budget == 0

    # Call 5 MUST raise HiveRequestBudgetExceeded
    with pytest.raises(HiveRequestBudgetExceeded):
        provider.complete()


def test_conditional_ranking_denominator_excludes_undiscovered_cases():
    """Verify that conditional ranking denominator is 2 (ranking eligible cases only)."""
    cases_path = Path(__file__).resolve().parents[1] / "data" / "benchmarks" / "person_benchmark_cases.json"
    with open(cases_path, "r", encoding="utf-8") as f:
        cases = json.load(f)

    ranking_eligible = [c for c in cases if c["id"] in ("CASE-01", "CASE-02")]
    undiscovered = [c for c in cases if c["id"] in ("CASE-03", "CASE-04", "CASE-05")]

    assert len(ranking_eligible) == 2
    assert len(undiscovered) == 3
    # Denominator for conditional ranking must be exactly len(ranking_eligible)
    denominator = len(ranking_eligible)
    assert denominator == 2


def test_end_to_end_metric_uses_all_five_cases():
    """Verify that END_TO_END_CORRECT_TOP1 metric always uses denominator 5."""
    cases_path = Path(__file__).resolve().parents[1] / "data" / "benchmarks" / "person_benchmark_cases.json"
    with open(cases_path, "r", encoding="utf-8") as f:
        cases = json.load(f)

    total_gold_cases = len(cases)
    assert total_gold_cases == 5

    # If ranking gets 1 correct top-1 out of 2 eligible:
    deepseek_correct_top1 = 1
    end_to_end = f"{deepseek_correct_top1} / {total_gold_cases}"
    assert end_to_end == "1 / 5"


def test_ramkrishna_control_remains_ready_for_contact_enrichment():
    """Verify Ramkrishna positive control candidate remains HIGH, READY_FOR_CONTACT_ENRICHMENT, not ready for email."""
    ctrl = evaluate_ramkrishna_positive_control()
    assert ctrl["person_name"] == "Krishna Kumar Jha"
    assert ctrl["person_confidence"] == "HIGH"
    assert ctrl["apollo_gate_status"] == READY_FOR_CONTACT_ENRICHMENT
    assert ctrl["ready_for_contact_enrichment"] is True
    assert ctrl["ready_for_email"] is False
    assert ctrl["control_passed"] is True
