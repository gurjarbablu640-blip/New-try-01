import json
from unittest.mock import MagicMock

from services.llm_provider import LLMResponse
from services.opportunity_gates import evaluate_opportunity_gates
from services.person_intelligence_service import (
    discover_and_rank_decision_makers,
    extract_people_from_document_pages,
    extract_person_candidates_from_search_result,
    generate_person_search_queries,
)
from scripts.run_candidate_discovery_benchmark import (
    MAX_HIVE_QUERY_REQUESTS,
    BudgetedProvider,
    HiveRequestBudget,
    evaluate_cases,
)


class StaticSearchRouter:
    def __init__(self, results):
        self.results = results

    def search(self, query, num_results=5, **kwargs):
        return {
            "provider": "fixture",
            "provider_status": "LIVE",
            "results": self.results,
            "query": query,
            "error": None,
        }


class QueryProvider:
    def __init__(self, queries=None):
        self.queries = queries or []

    def complete(self, *args, **kwargs):
        return LLMResponse(
            text=json.dumps({"queries": self.queries}),
            usage={"input_tokens": 10, "output_tokens": 5},
            provider="hive",
            model="deepseek-ai/DeepSeek-V4.1-Flash",
        )


def test_discovery_retains_candidate_before_facility_verification():
    router = StaticSearchRouter([{
        "title": "Ravi Singh - Quality Assurance Head - LinkedIn",
        "url": "https://linkedin.com/in/ravi-singh",
        "snippet": "Experience: Example Manufacturing (Present). Corporate quality leadership.",
    }])

    result = discover_and_rank_decision_makers(
        company_name="Example Manufacturing",
        facility_name="Pune Plant",
        city="Pune",
        search_router=router,
        max_candidates=15,
    )

    assert result["candidates"][0]["name"] == "Ravi Singh"
    assert result["candidates"][0]["facility_relationship"] in {"FUNCTIONALLY_RELEVANT", "COMPANY_ONLY"}
    assert result["candidates"][0]["person_confidence"] != "HIGH"


def test_weak_facility_candidate_still_fails_outbound_gate():
    person = {
        "name": "Ravi Singh",
        "current_employment": "VERIFIED",
        "employment_verified": True,
        "facility_relationship": "COMPANY_ONLY",
        "facility_verified": False,
        "duties_verified": True,
        "authority_class": "STRONG_PLANT_QUALITY_OWNER",
        "person_confidence": "LOW",
    }
    result = evaluate_opportunity_gates({
        "trigger_current": True,
        "exact_facility": True,
        "calibration_demand": True,
        "technical_capability": True,
        "timing": True,
        "correct_person": person,
        "reachable_email": {"address": "ravi@example.test", "status": "verified", "mailbox_verified": True},
        "score": 90,
    })

    assert not result["ready_for_email"]
    assert not result["gates"]["correct_person"]["passed"]


def test_query_families_include_title_variants_and_source_surfaces():
    queries = generate_person_search_queries(
        "Example Manufacturing",
        facility_name="Pune Plant",
        city="Pune",
        company_domain="example.com",
        sector="Automotive",
        max_queries=50,
    )
    query_text = "\n".join(query["query"] for query in queries)

    assert '"Head QA"' in query_text
    assert '"DGM Quality"' in query_text
    assert "annual report" in query_text
    assert "conference quality" in query_text
    assert "site:example.com" in query_text


def test_annual_report_extraction_has_page_provenance():
    candidates = extract_people_from_document_pages(
        ["Atul Jain - Vice President, currently with Example Manufacturing at the Pune Plant in 2026."],
        source_url="https://example.com/investors/annual-report-2026.pdf",
        company_name="Example Manufacturing",
        facility_name="Pune Plant",
        city="Pune",
        company_domain="example.com",
    )

    assert candidates[0]["name"] == "Atul Jain"
    assert candidates[0]["source_type"] == "ANNUAL_REPORT"
    assert candidates[0]["source_page"] == 1


def test_company_post_extracts_multiple_people():
    candidates = extract_person_candidates_from_search_result(
        {
            "title": "Leadership appointments",
            "url": "https://example.com/media/news/leadership",
            "snippet": (
                "Example Manufacturing appointed Ravi Singh as Quality Assurance Head for Pune Plant in 2026. "
                "Atul Jain - Plant Head, currently with Example Manufacturing at Pune Plant."
            ),
        },
        company_name="Example Manufacturing",
        facility_name="Pune Plant",
        city="Pune",
        company_domain="example.com",
    )

    assert {candidate["name"] for candidate in candidates} == {"Ravi Singh", "Atul Jain"}
    assert {candidate["source_type"] for candidate in candidates} == {"COMPANY_PUBLIC_POST"}


def test_full_name_company_dedup_and_hard_pool_limit():
    names = [
        "Aarav Sharma", "Vivaan Verma", "Aditya Gupta", "Arjun Mehta", "Sai Reddy",
        "Reyansh Nair", "Ayaan Joshi", "Krishna Iyer", "Ishaan Rao", "Kabir Singh",
        "Rohan Das", "Rahul Bose", "Karan Shah", "Nitin Jain", "Manish Kumar",
        "Deepak Yadav", "Sanjay Mishra", "Vikas Patel", "Ajay Kapoor", "Mohan Pillai",
    ]
    results = [
        {
            "title": f"{name} - Quality Manager - LinkedIn",
            "url": f"https://linkedin.com/in/person-{index}",
            "snippet": "Experience: Example Manufacturing (Present). Pune Plant.",
        }
        for index, name in enumerate(names)
    ]
    results.append(dict(results[0]))

    result = discover_and_rank_decision_makers(
        company_name="Example Manufacturing",
        facility_name="Pune Plant",
        city="Pune",
        search_router=StaticSearchRouter(results),
        max_candidates=99,
    )

    assert len(result["candidates"]) == 15
    assert len({(candidate["name"], candidate["company"]) for candidate in result["candidates"]}) == 15


def test_candidate_benchmark_recall_and_five_request_budget():
    cases = [
        {
            "id": f"CASE-{index}",
            "company": "Example Manufacturing",
            "facility": "Pune Plant",
            "city": "Pune",
            "company_domain": "example.com",
            "sector": "Automotive",
            "function_context": "Plant Quality",
            "expected_person": "Ravi Singh",
        }
        for index in range(5)
    ]
    router = StaticSearchRouter([{
        "title": "Ravi Singh - Quality Assurance Head - LinkedIn",
        "url": "https://linkedin.com/in/ravi-singh",
        "snippet": "Experience: Example Manufacturing (Present). Pune Plant.",
    }])
    budget = HiveRequestBudget(max_requests=MAX_HIVE_QUERY_REQUESTS)
    provider = BudgetedProvider(QueryProvider(), budget)

    result = evaluate_cases(cases, provider=provider, search_router=router, budget=budget)

    assert result["metrics"]["EXPECTED_PERSON_FOUND"] == 5
    assert result["metrics"]["CANDIDATE_SET_RECALL"] == 100.0
    assert budget.snapshot()["attempted_requests"] == 5
    assert all(case["expected_person_rank_before_llm"] == 1 for case in result["case_results"])


def test_query_generation_prompt_never_receives_expected_identity():
    provider = MagicMock()
    provider.complete.return_value = LLMResponse(
        text='{"queries": []}', provider="hive", model="deepseek-ai/DeepSeek-V4.1-Flash"
    )
    discover_and_rank_decision_makers(
        company_name="Example Manufacturing",
        facility_name="Pune Plant",
        city="Pune",
        search_router=StaticSearchRouter([]),
        ranking_provider=provider,
        use_deepseek_queries=True,
        use_deepseek_ranking=False,
    )

    prompt = provider.complete.call_args.kwargs["messages"][0]["content"]
    assert "expected_person" not in prompt
    assert "expected_title" not in prompt
    assert "Secret Gold Person" not in prompt
