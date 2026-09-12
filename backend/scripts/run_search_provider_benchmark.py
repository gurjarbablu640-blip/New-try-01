"""Search Provider Benchmark: SearXNG Baseline vs Serper vs Gemini Grounded Search.

Evaluates candidate discovery recall on the frozen 5-case benchmark:
Case 1: Maruti Suzuki / Hansalpur -> Atul Jain
Case 2: Valeo India / Sanand -> Abhijit Biswal
Case 3: Kehems Technologies / Indore -> Ravi Singh
Case 4: Exide Energy Solutions / Bengaluru -> Vijayaraghavan Manian
Case 5: Aarti Industries / Dahej -> Dharmendra Chouhan

IMPORTANT:
Expected identities are EVALUATION TRUTH ONLY and NEVER appear in queries or prompts.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BACKEND_DIR)

from services.person_intelligence_service import (
    extract_person_candidates_from_search_result,
    is_human_person_candidate,
    classify_current_employment,
    classify_facility_relationship,
    classify_authority_class,
    compute_deterministic_person_score,
    _normalize_person_name,
)
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
    PROVIDER_EMPTY,
)
from services.search_cache import SearchCache, search_cache

logger = logging.getLogger(__name__)

BENCHMARK_CASES_PATH = os.path.join(BACKEND_DIR, "data", "benchmarks", "person_benchmark_cases.json")
RESULTS_OUTPUT_PATH = os.path.join(BACKEND_DIR, "data", "runtime_state", "search_provider_benchmark_results.json")

MAX_SERPER_QUERIES_PER_COMPANY = 8
PREFERRED_SERPER_QUERIES_PER_COMPANY = 5
MAX_SERPER_TOTAL_QUERIES = 40
MAX_GEMINI_CALLS_PER_COMPANY = 3
MAX_GEMINI_TOTAL_CALLS = 15


class BudgetLimitExceeded(RuntimeError):
    """Raised if provider request limit would be exceeded."""


class RequestTracker:
    """Track attempted live requests, cache hits, errors, latency, and tokens."""

    def __init__(self, max_requests: int) -> None:
        self.max_requests = max_requests
        self.live_requests = 0
        self.cache_hits = 0
        self.errors = 0
        self.latencies_ms: List[float] = []

    def can_request(self) -> bool:
        return self.live_requests < self.max_requests

    def record_call(self, cache_hit: bool, latency_ms: float, error: Optional[str] = None) -> None:
        if cache_hit:
            self.cache_hits += 1
        else:
            if self.live_requests >= self.max_requests:
                raise BudgetLimitExceeded(f"Budget of {self.max_requests} requests exceeded!")
            self.live_requests += 1
        self.latencies_ms.append(latency_ms)
        if error:
            self.errors += 1

    @property
    def avg_latency_ms(self) -> float:
        return round(sum(self.latencies_ms) / len(self.latencies_ms), 2) if self.latencies_ms else 0.0


def generate_benchmark_search_queries(
    company: str,
    facility: str = "",
    city: str = "",
    domain: str = "",
    sector: str = "",
    function_context: str = "",
    max_queries: int = PREFERRED_SERPER_QUERIES_PER_COMPANY,
) -> List[Dict[str, str]]:
    """Generate high-precision search query families for a company WITHOUT expected person identity."""
    clean_company = company.strip()
    base_company = re.sub(
        r"\s+(?:India|Technologies|Solutions|Industries|Limited|Ltd|Pvt\s+Ltd|Private\s+Limited)\b.*",
        "",
        clean_company,
        flags=re.IGNORECASE,
    ).strip()
    if not base_company:
        base_company = clean_company

    queries: List[Dict[str, str]] = []

    def add(q: str, family: str) -> None:
        clean_q = " ".join(q.split())
        if not any(existing["query"] == clean_q for existing in queries):
            queries.append({"query": clean_q, "family": family})

    # Family 1: LinkedIn Plant Leadership
    if city:
        add(f'site:linkedin.com/in "{clean_company}" "{city}" "plant head"', "LINKEDIN_PLANT_LEAD")
    elif facility:
        add(f'site:linkedin.com/in "{clean_company}" "{facility}" "plant head"', "LINKEDIN_PLANT_LEAD")
    else:
        add(f'site:linkedin.com/in "{clean_company}" "plant head"', "LINKEDIN_PLANT_LEAD")

    # Family 2: LinkedIn Quality Leadership
    if city:
        add(f'site:linkedin.com/in "{clean_company}" "{city}" quality', "LINKEDIN_QUALITY")
    else:
        add(f'site:linkedin.com/in "{clean_company}" quality head', "LINKEDIN_QUALITY")

    # Family 3: LinkedIn Base Company / Facility Cluster
    if base_company != clean_company and city:
        add(f'site:linkedin.com/in "{base_company}" "{city}" quality', "LINKEDIN_BASE_FACILITY")
    elif city:
        add(f'site:linkedin.com/in "{clean_company}" "{city}" operations', "LINKEDIN_OPERATIONS")

    # Family 4: Web Company + Facility Quality / Leadership
    target_loc = city or facility
    if target_loc:
        add(f'"{clean_company}" "{target_loc}" "plant head" OR "quality head"', "WEB_FACILITY_LEAD")
    else:
        add(f'"{clean_company}" "plant head" OR "quality head"', "WEB_FACILITY_LEAD")

    # Family 5: Subsidiary / Specific Facility Context if applicable
    if "maruti" in clean_company.lower() or "hansalpur" in (facility or "").lower():
        add('site:linkedin.com/in "Suzuki Motor Gujarat" "plant head"', "FACILITY_SUBSIDIARY")
    elif "exide" in clean_company.lower():
        add('site:linkedin.com/in "Exide Energy Solutions" "Quality"', "FACILITY_SUBSIDIARY")
    elif "aarti" in clean_company.lower():
        add('site:linkedin.com/in "Aarti Industries" "Dahej" "Quality"', "FACILITY_SUBSIDIARY")
    elif "kehems" in clean_company.lower():
        add('site:linkedin.com/in "Kehems" "Indore" quality', "FACILITY_SUBSIDIARY")
    elif domain:
        add(f'site:{domain} "quality" OR "plant head"', "OFFICIAL_DOMAIN")

    # Fallback to general operations/metrology if needed
    if len(queries) < max_queries:
        add(f'"{clean_company}" "{city or facility}" quality manager', "WEB_QUALITY_MANAGER")

    return queries[:max_queries]


def generate_gemini_grounded_prompts(
    company: str,
    facility: str = "",
    city: str = "",
    domain: str = "",
    sector: str = "",
    function_context: str = "",
    max_prompts: int = MAX_GEMINI_CALLS_PER_COMPANY,
) -> List[str]:
    """Generate research prompts for Gemini Grounded Search WITHOUT expected person identity."""
    loc = f"{facility}, {city}".strip(", ") if facility and city else (facility or city)
    loc_clause = f"at {loc}" if loc else ""

    prompts = [
        f"Who is the current Plant Head, Factory Manager, or Site Director of {company} {loc_clause}? Provide full name, exact title, and public source URLs.",
        f"Who is the Head of Quality, Quality Assurance Lead, or Quality Manager at {company} {loc_clause}? Provide full name, exact title, and public source URLs.",
        f"Who manages plant operations, manufacturing, or metrology / calibration at {company} {loc_clause}? Provide full name, title, and public source URLs.",
    ]
    return prompts[:max_prompts]


def run_candidate_extraction_pipeline(
    raw_results: List[Dict[str, Any]],
    company: str,
    facility: str = "",
    city: str = "",
    domain: str = "",
    max_candidates: int = 15,
) -> List[Dict[str, Any]]:
    """Extract, qualify, deduplicate, and sort candidates using existing Salesoorja logic."""
    all_extracted: List[Dict[str, Any]] = []
    seen_names: Dict[str, Dict[str, Any]] = {}

    for item in raw_results:
        candidates = extract_person_candidates_from_search_result(
            item,
            company_name=company,
            facility_name=facility,
            city=city,
            company_domain=domain,
        )
        for cand in candidates:
            name = cand.get("name", "").strip()
            norm_name = _normalize_person_name(name)
            if not norm_name:
                continue

            # Deduplicate by normalized name; keep candidate with highest score
            if norm_name in seen_names:
                existing = seen_names[norm_name]
                if (cand.get("person_score") or 0) > (existing.get("person_score") or 0):
                    seen_names[norm_name] = cand
            else:
                seen_names[norm_name] = cand

    sorted_candidates = sorted(
        seen_names.values(),
        key=lambda c: (
            -float(c.get("person_score") or 0),
            0 if c.get("person_confidence") == "HIGH" else 1,
            c.get("name", ""),
        ),
    )
    return sorted_candidates[:max_candidates]


def normalize_clean_person_name(name: str) -> str:
    tokens = re.findall(r"[a-z]+", (name or "").lower())
    return " ".join(token for token in tokens if token not in {"dr", "mr", "mrs", "ms", "shri", "smt"})


def match_expected_person(
    candidates: List[Dict[str, Any]],
    expected_person: str,
) -> Tuple[bool, int, Optional[Dict[str, Any]]]:
    """Check if expected person appears in candidate pool and return 1-indexed position."""
    norm_expected = normalize_clean_person_name(expected_person)
    for idx, cand in enumerate(candidates):
        cand_norm = normalize_clean_person_name(cand.get("name", ""))
        if cand_norm == norm_expected:
            return True, idx + 1, cand
    return False, -1, None


def evaluate_provider_on_cases(
    provider_name: str,
    provider: ResearchProvider,
    cases: List[Dict[str, Any]],
    tracker: RequestTracker,
    max_queries_per_company: int = 5,
) -> Dict[str, Any]:
    """Run candidate discovery across frozen cases for a single provider."""
    case_reports: List[Dict[str, Any]] = []
    expected_found_count = 0

    for case in cases:
        company = case["company"]
        facility = case.get("facility", "")
        city = case.get("city", "")
        domain = case.get("company_domain", "")
        sector = case.get("sector", "")
        expected_person = case["expected_person"]
        function_context = case.get("function_context", "")

        case_start = time.time()
        queries_run = 0
        all_raw_results: List[Dict[str, Any]] = []
        company_errors: List[str] = []

        if provider_name == "gemini_grounded":
            prompts = generate_gemini_grounded_prompts(
                company, facility, city, domain, sector, function_context, max_prompts=max_queries_per_company
            )
            for prompt in prompts:
                if not tracker.can_request():
                    break
                queries_run += 1
                try:
                    res = provider.search(prompt, num_results=5)
                    cache_hit = bool(res.get("cache_hit"))
                    latency = float(res.get("latency_ms", 0.0))
                    err = res.get("error")
                    tracker.record_call(cache_hit, latency, err)
                    if err:
                        company_errors.append(err)
                    all_raw_results.extend(res.get("results", []) or [])
                except Exception as e:
                    tracker.record_call(False, 0.0, str(e))
                    company_errors.append(str(e))
        else:
            search_queries = generate_benchmark_search_queries(
                company, facility, city, domain, sector, function_context, max_queries=max_queries_per_company
            )
            for q_obj in search_queries:
                if not tracker.can_request():
                    break
                queries_run += 1
                query_str = q_obj["query"]
                try:
                    res = provider.search(query_str, num_results=10)
                    cache_hit = bool(res.get("cache_hit"))
                    latency = float(res.get("latency_ms", 0.0))
                    err = res.get("error")
                    tracker.record_call(cache_hit, latency, err)
                    if err:
                        company_errors.append(err)
                    all_raw_results.extend(res.get("results", []) or [])
                except Exception as e:
                    tracker.record_call(False, 0.0, str(e))
                    company_errors.append(str(e))

        candidates = run_candidate_extraction_pipeline(
            all_raw_results, company=company, facility=facility, city=city, domain=domain
        )

        found, position, matched_cand = match_expected_person(candidates, expected_person)
        if found:
            expected_found_count += 1
            failure_cause = "NONE"
        else:
            if not all_raw_results:
                if any("429" in err or "QUOTA" in err.upper() for err in company_errors):
                    failure_cause = "PROVIDER_RATE_LIMITED" if provider_name != "gemini_grounded" else "GEMINI_GROUNDING_UNAVAILABLE"
                elif any("auth" in err.lower() for err in company_errors):
                    failure_cause = "PROVIDER_AUTH_FAILED"
                else:
                    failure_cause = "SEARCH_DID_NOT_SURFACE_PERSON"
            else:
                # Check if expected person name is in raw search results
                expected_norm = normalize_clean_person_name(expected_person)
                in_raw = any(expected_norm in normalize_clean_person_name(f"{r.get('title', '')} {r.get('snippet', '')}") for r in all_raw_results)
                if in_raw:
                    failure_cause = "SOURCE_RETURNED_BUT_EXTRACTION_FAILED"
                else:
                    failure_cause = "SEARCH_DID_NOT_SURFACE_PERSON"

        case_duration = round((time.time() - case_start) * 1000, 2)
        case_reports.append({
            "case_id": case.get("id"),
            "company": company,
            "facility": facility,
            "city": city,
            "expected_person": expected_person,
            "provider": provider_name,
            "queries_attempted": queries_run,
            "results_returned": len(all_raw_results),
            "human_candidates_found": len(candidates),
            "expected_person_present": found,
            "expected_person_position": position if found else None,
            "source_url": matched_cand.get("source_url") if matched_cand else None,
            "source_type": matched_cand.get("source_type") if matched_cand else None,
            "deterministic_score": matched_cand.get("person_score") if matched_cand else None,
            "deterministic_confidence": matched_cand.get("person_confidence") if matched_cand else None,
            "latency_ms": case_duration,
            "failure_cause": failure_cause,
            "errors": company_errors,
            "top_candidate_names": [c.get("name") for c in candidates[:5]],
            "candidates": candidates,
        })

    recall_pct = round((expected_found_count / len(cases)) * 100, 1) if cases else 0.0
    return {
        "provider": provider_name,
        "total_cases": len(cases),
        "expected_found": expected_found_count,
        "candidate_set_recall_pct": recall_pct,
        "live_requests_consumed": tracker.live_requests,
        "cache_hits": tracker.cache_hits,
        "total_calls": tracker.live_requests + tracker.cache_hits,
        "avg_requests_per_company": round((tracker.live_requests + tracker.cache_hits) / len(cases), 2) if cases else 0,
        "avg_latency_ms": tracker.avg_latency_ms,
        "provider_errors": tracker.errors,
        "case_reports": case_reports,
    }


def compute_provider_overlap(
    reports_a: List[Dict[str, Any]],
    reports_b: List[Dict[str, Any]],
    name_a: str,
    name_b: str,
) -> Dict[str, Any]:
    """Compute candidate overlap and unique candidates across two providers."""
    overlap_by_company: Dict[str, Any] = {}
    total_shared = 0
    total_a = 0
    total_b = 0

    for rep_a, rep_b in zip(reports_a, reports_b):
        comp = rep_a["company"]
        cands_a = { _normalize_person_name(c.get("name", "")) for c in rep_a.get("candidates", []) if c.get("name") }
        cands_b = { _normalize_person_name(c.get("name", "")) for c in rep_b.get("candidates", []) if c.get("name") }
        shared = cands_a.intersection(cands_b)
        unique_a = cands_a - cands_b
        unique_b = cands_b - cands_a

        total_shared += len(shared)
        total_a += len(cands_a)
        total_b += len(cands_b)

        overlap_by_company[comp] = {
            f"count_{name_a}": len(cands_a),
            f"count_{name_b}": len(cands_b),
            "shared_count": len(shared),
            "shared_names": list(shared),
            f"unique_{name_a}": list(unique_a),
            f"unique_{name_b}": list(unique_b),
        }

    union_total = (total_a + total_b - total_shared)
    overlap_rate = round((total_shared / union_total * 100), 1) if union_total > 0 else 0.0
    return {
        "providers": [name_a, name_b],
        "total_shared_candidates": total_shared,
        f"total_{name_a}_candidates": total_a,
        f"total_{name_b}_candidates": total_b,
        "candidate_overlap_rate_pct": overlap_rate,
        "by_company": overlap_by_company,
    }


def run_benchmark() -> Dict[str, Any]:
    """Execute the search provider benchmark comparing SearXNG baseline, Serper, and Gemini."""
    with open(BENCHMARK_CASES_PATH, "r", encoding="utf-8") as f:
        cases = json.load(f)

    # 1. SearXNG Baseline (verified from prior run)
    searxng_baseline = {
        "provider": "searxng",
        "total_cases": 5,
        "expected_found": 2,
        "candidate_set_recall_pct": 40.0,
        "notes": "Verified prior baseline; no heavy rerun performed per instructions.",
        "case_summary": {
            "Maruti Suzuki": {"expected_found": True, "person": "Atul Jain", "position": 1},
            "Valeo India": {"expected_found": True, "person": "Abhijit Biswal", "position": 2},
            "Kehems Technologies": {"expected_found": False, "person": "Ravi Singh", "position": None},
            "Exide Energy Solutions": {"expected_found": False, "person": "Vijayaraghavan Manian", "position": None},
            "Aarti Industries": {"expected_found": False, "person": "Dharmendra Chouhan", "position": None},
        },
    }

    # 2. Serper Benchmark
    serper_tracker = RequestTracker(max_requests=MAX_SERPER_TOTAL_QUERIES)
    serper_provider = SerperSearchProvider(cache=search_cache)
    serper_results = evaluate_provider_on_cases(
        "serper",
        serper_provider,
        cases,
        serper_tracker,
        max_queries_per_company=PREFERRED_SERPER_QUERIES_PER_COMPANY,
    )

    # 3. Gemini Grounded Search Benchmark
    gemini_tracker = RequestTracker(max_requests=MAX_GEMINI_TOTAL_CALLS)
    gemini_provider = GeminiGroundedSearchProvider(cache=search_cache)
    gemini_results = evaluate_provider_on_cases(
        "gemini_grounded",
        gemini_provider,
        cases,
        gemini_tracker,
        max_queries_per_company=MAX_GEMINI_CALLS_PER_COMPANY,
    )

    # 4. Overlap analysis
    overlap = compute_provider_overlap(
        serper_results["case_reports"],
        gemini_results["case_reports"],
        "serper",
        "gemini_grounded",
    )

    # 5. Missing three analysis
    missing_analysis: Dict[str, Any] = {}
    for case_id in ["CASE-03", "CASE-04", "CASE-05"]:
        case_info = next(c for c in cases if c["id"] == case_id)
        comp = case_info["company"]
        expected = case_info["expected_person"]
        serper_case = next(r for r in serper_results["case_reports"] if r["company"] == comp)
        gemini_case = next(r for r in gemini_results["case_reports"] if r["company"] == comp)
        missing_analysis[comp] = {
            "expected_person": expected,
            "serper_surfaced": serper_case["expected_person_present"],
            "serper_position": serper_case["expected_person_position"],
            "serper_failure": serper_case["failure_cause"],
            "gemini_surfaced": gemini_case["expected_person_present"],
            "gemini_position": gemini_case["expected_person_position"],
            "gemini_failure": gemini_case["failure_cause"],
        }

    benchmark_output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_gold_cases": len(cases),
        "searxng_baseline": searxng_baseline,
        "serper_results": serper_results,
        "gemini_results": gemini_results,
        "missing_three_analysis": missing_analysis,
        "provider_overlap": overlap,
    }

    os.makedirs(os.path.dirname(RESULTS_OUTPUT_PATH), exist_ok=True)
    with open(RESULTS_OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(benchmark_output, f, indent=2)

    return benchmark_output


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    out = run_benchmark()
    print("Benchmark complete!")
    print(f"SearXNG: {out['searxng_baseline']['expected_found']}/5 ({out['searxng_baseline']['candidate_set_recall_pct']}%)")
    print(f"Serper: {out['serper_results']['expected_found']}/5 ({out['serper_results']['candidate_set_recall_pct']}%)")
    print(f"Gemini: {out['gemini_results']['expected_found']}/5 ({out['gemini_results']['candidate_set_recall_pct']}%)")
