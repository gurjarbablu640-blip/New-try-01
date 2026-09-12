"""Person Discovery Benchmark & Telemetry Runner.

Measures independent rediscovery of known decision-makers WITHOUT answer leakage.
Evaluates:
- Discovery recall
- Top-1 accuracy
- Top-3 recall
- Current employment verification
- Facility relation verification
- High confidence rate
- Failure funnel classification
- Search engine person yield
"""
import io
import json
import os
import sys
from datetime import datetime, timezone

# Ensure utf-8 output on Windows
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.person_intelligence_service import (
    AUTHORITY_HIERARCHY,
    discover_and_rank_decision_makers,
)


def run_benchmark():
    benchmark_path = os.path.join(os.path.dirname(__file__), "..", "data", "benchmarks", "person_benchmark_cases.json")
    with open(benchmark_path, "r", encoding="utf-8") as f:
        cases = json.load(f)

    metrics = {
        "KNOWN_PERSON_CASES": len(cases),
        "PERSON_FOUND": 0,
        "CORRECT_PRIMARY_PERSON": 0,
        "CORRECT_PERSON_IN_TOP3": 0,
        "CURRENT_EMPLOYMENT_VERIFIED": 0,
        "FACILITY_RELATION_VERIFIED": 0,
        "HIGH_CONFIDENCE_PERSON": 0,
    }

    failure_funnel = {
        "NO_PERSON_SEARCH_RESULT": 0,
        "NON_HUMAN_EXTRACTION": 0,
        "OLD_EMPLOYMENT": 0,
        "EMPLOYMENT_UNKNOWN": 0,
        "FACILITY_UNKNOWN": 0,
        "FUNCTION_UNKNOWN": 0,
        "GROUP_ROLE_AMBIGUOUS": 0,
        "TITLE_TOO_GENERIC": 0,
        "SOURCE_TOO_OLD": 0,
        "LINKEDIN_AUTH_REQUIRED": 0,
        "SEARCH_ENGINE_NO_RESULT": 0,
        "OTHER": 0,
    }

    engine_yield = {
        "searxng_bing": {"queries": 0, "linkedin_hits": 0, "human_candidates": 0, "verified_employment": 0, "facility_linked": 0},
        "searxng_duckduckgo": {"queries": 0, "linkedin_hits": 0, "human_candidates": 0, "verified_employment": 0, "facility_linked": 0},
    }

    case_results = []

    print("=================================================")
    print("SALESOORJA — PERSON DISCOVERY BENCHMARK")
    print(f"Total Cases: {len(cases)}")
    print("Zero Answer Leakage: Production receives only company, facility, city")
    print("=================================================\n")

    for case in cases:
        c_id = case["id"]
        company = case["company"]
        facility = case.get("facility", "")
        city = case.get("city", "")
        expected = case["expected_person"]
        expected_title = case.get("expected_title", "")

        print(f"--- Running {c_id}: {company} ({facility}, {city}) ---")

        # Independent discovery: passes NO answer details
        disc_res = discover_and_rank_decision_makers(
            company_name=company,
            facility_name=facility,
            city=city,
            max_candidates=5,
        )

        candidates = disc_res.get("candidates", [])
        primary = disc_res.get("primary_person")
        telemetry = disc_res.get("telemetry", {})

        # Record engine yield approximations
        engine_yield["searxng_bing"]["queries"] += telemetry.get("queries_run", 0)
        engine_yield["searxng_bing"]["linkedin_hits"] += telemetry.get("results_returned", 0)
        engine_yield["searxng_bing"]["human_candidates"] += telemetry.get("raw_candidates_extracted", 0)
        engine_yield["searxng_bing"]["verified_employment"] += telemetry.get("verified_employment_count", 0)

        # Check expected match
        exp_parts = expected.lower().split()
        cand_names = [c["name"].lower() for c in candidates]

        found = False
        in_top3 = False
        is_primary = False
        matched_cand = None

        for idx, c in enumerate(candidates):
            c_name_lower = c["name"].lower()
            if any(p in c_name_lower for p in exp_parts if len(p) > 3):
                found = True
                matched_cand = c
                if idx < 3:
                    in_top3 = True
                if idx == 0:
                    is_primary = True
                break

        if found:
            metrics["PERSON_FOUND"] += 1
            if in_top3:
                metrics["CORRECT_PERSON_IN_TOP3"] += 1
            if is_primary:
                metrics["CORRECT_PRIMARY_PERSON"] += 1

            if matched_cand["current_employment"] == "VERIFIED":
                metrics["CURRENT_EMPLOYMENT_VERIFIED"] += 1
                engine_yield["searxng_bing"]["facility_linked"] += 1

            if matched_cand["facility_relationship"] in ("FACILITY_OWNER", "FACILITY_FUNCTION_OWNER", "GROUP_FUNCTION_OWNER"):
                metrics["FACILITY_RELATION_VERIFIED"] += 1

            if matched_cand["person_confidence"] == "HIGH":
                metrics["HIGH_CONFIDENCE_PERSON"] += 1

            print(f"  Result: FOUND (Rank #{candidates.index(matched_cand)+1})")
            print(f"  Name: {matched_cand['name']} | Title: {matched_cand['title']}")
            print(f"  Employment: {matched_cand['current_employment']} | Facility Rel: {matched_cand['facility_relationship']}")
            print(f"  Score: {matched_cand['person_score']} | Confidence: {matched_cand['person_confidence']}")
        else:
            print("  Result: MISSED (Expected person not in extracted candidates)")
            if not candidates:
                failure_funnel["NO_PERSON_SEARCH_RESULT"] += 1
            else:
                top_cand = candidates[0]
                if top_cand["current_employment"] == "UNKNOWN":
                    failure_funnel["EMPLOYMENT_UNKNOWN"] += 1
                elif top_cand["facility_relationship"] == "COMPANY_ONLY":
                    failure_funnel["FACILITY_UNKNOWN"] += 1
                elif top_cand["authority_class"] in ("GENERAL_QUALITY", "UNKNOWN"):
                    failure_funnel["FUNCTION_UNKNOWN"] += 1
                else:
                    failure_funnel["OTHER"] += 1

        case_results.append({
            "case_id": c_id,
            "company": company,
            "expected_person": expected,
            "found": found,
            "matched_candidate": matched_cand,
            "top_candidate": primary,
            "total_candidates": len(candidates),
        })

    # Calculate percentages
    total = metrics["KNOWN_PERSON_CASES"]
    p_recall = (metrics["PERSON_FOUND"] / total * 100) if total else 0.0
    top1_acc = (metrics["CORRECT_PRIMARY_PERSON"] / total * 100) if total else 0.0
    top3_rec = (metrics["CORRECT_PERSON_IN_TOP3"] / total * 100) if total else 0.0
    hi_conf_rate = (metrics["HIGH_CONFIDENCE_PERSON"] / total * 100) if total else 0.0

    print("\n=================================================")
    print("BENCHMARK SUMMARY METRICS")
    print("=================================================")
    print(f"KNOWN_PERSON_CASES:           {total}")
    print(f"PERSON_FOUND:                 {metrics['PERSON_FOUND']}")
    print(f"CORRECT_PRIMARY_PERSON:       {metrics['CORRECT_PRIMARY_PERSON']}")
    print(f"CORRECT_PERSON_IN_TOP3:        {metrics['CORRECT_PERSON_IN_TOP3']}")
    print(f"CURRENT_EMPLOYMENT_VERIFIED:  {metrics['CURRENT_EMPLOYMENT_VERIFIED']}")
    print(f"FACILITY_RELATION_VERIFIED:   {metrics['FACILITY_RELATION_VERIFIED']}")
    print(f"HIGH_CONFIDENCE_PERSON:       {metrics['HIGH_CONFIDENCE_PERSON']}")
    print(f"PERSON_DISCOVERY_RECALL:      {p_recall:.1f}%")
    print(f"TOP1_ACCURACY:                {top1_acc:.1f}%")
    print(f"TOP3_RECALL:                  {top3_rec:.1f}%")
    print(f"HIGH_CONFIDENCE_RATE:         {hi_conf_rate:.1f}%")

    print("\n=================================================")
    print("FAILURE FUNNEL")
    print("=================================================")
    for reason, count in failure_funnel.items():
        print(f"  {reason}: {count}")

    print("\n=================================================")
    print("SEARCH ENGINE PERSON YIELD")
    print("=================================================")
    for eng, data in engine_yield.items():
        print(f"  {eng}: {data}")

    # Save benchmark report to runtime state
    out_path = os.path.join(os.path.dirname(__file__), "..", "data", "runtime_state", "person_benchmark_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metrics": {
                **metrics,
                "PERSON_DISCOVERY_RECALL": p_recall,
                "TOP1_ACCURACY": top1_acc,
                "TOP3_RECALL": top3_rec,
                "HIGH_CONFIDENCE_RATE": hi_conf_rate,
            },
            "failure_funnel": failure_funnel,
            "engine_yield": engine_yield,
            "case_results": case_results,
        }, f, indent=2)


if __name__ == "__main__":
    run_benchmark()
