"""Run the frozen five-case candidate discovery benchmark with five Hive calls."""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BACKEND_DIR)

from config import settings
from scripts.run_person_discovery_benchmark import BudgetedProvider, HiveRequestBudget, write_json_atomic
from services.person_intelligence_service import discover_and_rank_decision_makers


BENCHMARK_PATH = os.path.join(BACKEND_DIR, "data", "benchmarks", "person_benchmark_cases.json")
OUTPUT_PATH = os.path.join(BACKEND_DIR, "data", "runtime_state", "person_candidate_discovery_results.json")
MAX_HIVE_QUERY_REQUESTS = 5
SOURCE_LABELS = {
    "OFFICIAL_COMPANY_PAGE": "official website",
    "ANNUAL_REPORT": "annual report",
    "COMPANY_PUBLIC_POST": "company post",
    "LINKEDIN_SEARCH_SNIPPET": "LinkedIn public",
    "CONFERENCE_TECHNICAL": "conference/technical",
    "TRADE_MEDIA": "trade media",
    "PUBLIC_WEB_BIO": "public web bio",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_person_name(name: str) -> str:
    tokens = re.findall(r"[a-z]+", (name or "").lower())
    return " ".join(token for token in tokens if token not in {"dr", "mr", "mrs", "ms", "shri", "smt"})


def find_expected_candidate(candidates: List[Dict[str, Any]], expected_person: str) -> tuple[int, Optional[Dict[str, Any]]]:
    expected_key = normalize_person_name(expected_person)
    for index, candidate in enumerate(candidates):
        if normalize_person_name(str(candidate.get("name") or "")) == expected_key:
            return index, candidate
    return -1, None


class TracingSearchRouter:
    """Thread-safe public-search trace used only after production query creation."""

    def __init__(self, router: Any) -> None:
        self.router = router
        self.records: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

    def search(self, query: str, num_results: int = 5) -> Dict[str, Any]:
        try:
            result = self.router.search(query, num_results=num_results, free_only=True)
        except TypeError:
            result = self.router.search(query, num_results=num_results)
        except Exception as error:
            with self._lock:
                self.records.append({"query": query, "results": [], "error": type(error).__name__})
            raise
        record = {
            "query": query,
            "provider": result.get("provider"),
            "provider_status": result.get("provider_status"),
            "error": result.get("error"),
            "results": result.get("results", []) or [],
        }
        with self._lock:
            self.records.append(record)
        return result


def diagnose_failure(
    expected_person: str,
    trace: List[Dict[str, Any]],
    candidates: List[Dict[str, Any]],
) -> str:
    if any(record.get("error") for record in trace):
        return "SOURCE_FETCH_FAILURE"
    if not any(record.get("results") for record in trace):
        return "NO_SEARCH_RESULT"
    expected_tokens = normalize_person_name(expected_person)
    raw_text = " ".join(
        f"{item.get('title', '')} {item.get('snippet', '')} {item.get('content', '')}"
        for record in trace
        for item in record.get("results", [])
    )
    if expected_tokens and expected_tokens in normalize_person_name(raw_text):
        return "NAME_EXTRACTION_FAILURE" if candidates else "TITLE_VARIATION_MISSED"
    queries = [str(record.get("query") or "").lower() for record in trace]
    if any("linkedin.com/in" in query for query in queries):
        return "LINKEDIN_SNIPPET_NOT_INDEXED"
    if not any(any(term in query for term in ("annual report", "conference", "speaker", "site:")) for query in queries):
        return "SOURCE_NOT_SEARCHED"
    return "QUERY_TOO_NARROW"


def evaluate_cases(
    cases: List[Dict[str, Any]],
    provider: Any,
    search_router: Any,
    budget: Optional[HiveRequestBudget] = None,
    generated_queries_by_case: Optional[Dict[str, List[str]]] = None,
) -> Dict[str, Any]:
    metrics: Dict[str, Any] = {
        "KNOWN_CASES": len(cases),
        "EXPECTED_PERSON_FOUND": 0,
        "CANDIDATE_SET_RECALL": 0.0,
    }
    source_yield = {label: 0 for label in SOURCE_LABELS.values()}
    case_results: List[Dict[str, Any]] = []

    for case in cases:
        tracing_router = TracingSearchRouter(search_router)
        discovery = discover_and_rank_decision_makers(
            company_name=case["company"],
            facility_name=case.get("facility", ""),
            city=case.get("city", ""),
            company_domain=case.get("company_domain", ""),
            sector=case.get("sector", ""),
            search_router=tracing_router,
            max_candidates=15,
            use_deepseek_queries=generated_queries_by_case is None,
            use_deepseek_ranking=False,
            ranking_provider=provider,
            deepseek_query_limit=5,
            additional_queries=(generated_queries_by_case or {}).get(case["id"], []),
            fetch_public_sources=True,
            commercial_trigger=case.get("function_context", ""),
            target_functions=[case.get("function_context", "Plant Quality")],
        )
        candidates = discovery.get("candidates_before_llm") or discovery.get("candidates", [])
        expected_position, expected_candidate = find_expected_candidate(candidates, case["expected_person"])
        expected_present = expected_candidate is not None
        if expected_present:
            metrics["EXPECTED_PERSON_FOUND"] += 1
        for candidate in candidates:
            label = SOURCE_LABELS.get(str(candidate.get("source_type") or ""), "public web bio")
            source_yield[label] = source_yield.get(label, 0) + 1

        case_results.append({
            "case_id": case["id"],
            "company": case["company"],
            "facility": case.get("facility", ""),
            "queries_run": [record["query"] for record in tracing_router.records],
            "search_results_seen": sum(len(record.get("results", [])) for record in tracing_router.records),
            "human_candidates_found": len(candidates),
            "expected_person_present": expected_present,
            "expected_person_candidate_position": expected_position + 1 if expected_present else None,
            "expected_person_rank_before_llm": expected_position + 1 if expected_present else None,
            "source_that_found_expected_person": ({
                "source_type": expected_candidate.get("source_type"),
                "source_url": expected_candidate.get("source_url"),
            } if expected_candidate else None),
            "failure_cause": "NONE" if expected_present else diagnose_failure(
                case["expected_person"], tracing_router.records, candidates
            ),
            "telemetry": discovery.get("telemetry", {}),
        })
        if budget is not None:
            budget.persist_status("RUNNING", metrics=metrics, case_results=case_results, source_yield=source_yield)

    total = metrics["KNOWN_CASES"]
    metrics["CANDIDATE_SET_RECALL"] = round(
        metrics["EXPECTED_PERSON_FOUND"] / total * 100 if total else 0.0,
        2,
    )
    return {"metrics": metrics, "source_yield": source_yield, "case_results": case_results}


def load_generated_query_replay() -> tuple[Dict[str, List[str]], Dict[str, Any]]:
    with open(OUTPUT_PATH, "r", encoding="utf-8") as prior_file:
        prior = json.load(prior_file)
    prior_usage = prior.get("hive_usage", {})
    if prior_usage.get("attempted_requests") != MAX_HIVE_QUERY_REQUESTS:
        raise RuntimeError("Replay requires a completed five-request query-generation benchmark")
    generated_queries: Dict[str, List[str]] = {}
    for case in prior.get("case_results", []):
        generated_queries[case["case_id"]] = [
            audit["query"]
            for audit in case.get("telemetry", {}).get("query_audit", [])
            if audit.get("family") == "DEEPSEEK_QUERY_GENERATION"
        ]
    return generated_queries, prior_usage


def run_benchmark(reuse_existing_queries: bool = False) -> Dict[str, Any]:
    if settings.HIVE_ALLOW_PAID_OVERAGE:
        raise RuntimeError("HIVE_ALLOW_PAID_OVERAGE must remain false for the controlled benchmark")
    with open(BENCHMARK_PATH, "r", encoding="utf-8") as benchmark_file:
        cases = json.load(benchmark_file)

    from services.research_provider import research_router

    budget: Optional[HiveRequestBudget] = None
    provider = None
    generated_queries_by_case = None
    preserved_hive_usage = None
    if reuse_existing_queries:
        generated_queries_by_case, preserved_hive_usage = load_generated_query_replay()
    else:
        from services.llm_provider import HiveProvider

        budget = HiveRequestBudget(max_requests=MAX_HIVE_QUERY_REQUESTS, output_path=OUTPUT_PATH)
        provider = BudgetedProvider(HiveProvider(), budget)
    try:
        result = evaluate_cases(
            cases,
            provider=provider,
            search_router=research_router,
            budget=budget,
            generated_queries_by_case=generated_queries_by_case,
        )
        result.update({
            "timestamp": utc_now(),
            "mode": "candidate_discovery_query_generation_only",
            "status": "COMPLETED",
            "hive_usage": budget.snapshot() if budget is not None else preserved_hive_usage,
            "controls": {
                "deepseek_query_generation": True,
                "deepseek_ranking": False,
                "generated_query_replay": reuse_existing_queries,
                "max_hive_requests": MAX_HIVE_QUERY_REQUESTS,
                "paid_overage_allowed": False,
                "expected_identity_available_to_discovery": False,
            },
        })
        write_json_atomic(OUTPUT_PATH, result)
    except Exception as error:
        if budget is not None:
            budget.persist_status("FAILED", error_type=type(error).__name__)
        raise

    print(json.dumps({
        "status": result["status"],
        "metrics": result["metrics"],
        "hive_usage": result["hive_usage"],
        "output_path": OUTPUT_PATH,
    }, indent=2))
    return result


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--reuse-existing-queries", action="store_true")
    arguments = parser.parse_args()
    run_benchmark(reuse_existing_queries=arguments.reuse_existing_queries)
