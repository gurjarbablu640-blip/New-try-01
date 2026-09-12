"""Freeze ranking candidate pools for the two ranking-eligible gold cases.

Case 1: Maruti Suzuki / Hansalpur (Atul Jain present at position 1)
Case 2: Valeo India / Sanand (Abhijit Biswal present at position 2)

CRITICAL:
The candidate pools are frozen so that ranking benchmark runs:
1. Are 100% deterministic and reproducible.
2. Require ZERO live search calls during ranking evaluation.
3. Test conditional ranking accuracy purely conditional on candidate discovery.
4. Expected person identities remain evaluation-only and never leak into ranking inputs.
"""
import json
import os
import sys

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BACKEND_DIR)

from services.person_intelligence_service import discover_and_rank_decision_makers

FROZEN_PATH = os.path.join(BACKEND_DIR, "data", "benchmarks", "frozen_ranking_candidates.json")
BENCHMARK_CASES_PATH = os.path.join(BACKEND_DIR, "data", "benchmarks", "person_benchmark_cases.json")


def freeze_candidates():
    with open(BENCHMARK_CASES_PATH, "r", encoding="utf-8") as f:
        cases = json.load(f)

    frozen_pools = {}

    for case in cases[:2]:
        case_id = case["id"]
        company = case["company"]
        facility = case.get("facility", "")
        city = case.get("city", "")
        domain = case.get("company_domain", "")
        sector = case.get("sector", "")
        trigger = case.get("function_context", "")

        print(f"Discovering candidate pool for {case_id} ({company} / {facility})...")
        res = discover_and_rank_decision_makers(
            company_name=company,
            facility_name=facility,
            city=city,
            company_domain=domain,
            sector=sector,
            max_candidates=15,
            use_deepseek=False,
            commercial_trigger=trigger,
            target_functions=[trigger or "Plant Quality"],
        )
        candidates = res.get("candidates", [])
        print(f"  -> Extracted {len(candidates)} candidates")
        for i, c in enumerate(candidates):
            print(f"     [{i+1}] {c.get('name')} | {c.get('title')} | score: {c.get('person_score')} | conf: {c.get('person_confidence')}")

        frozen_pools[case_id] = {
            "case_id": case_id,
            "company": company,
            "facility": facility,
            "city": city,
            "commercial_trigger": trigger,
            "target_functions": [trigger or "Plant Quality"],
            "candidates": candidates,
        }

    with open(FROZEN_PATH, "w", encoding="utf-8") as f:
        json.dump(frozen_pools, f, indent=2)
    print(f"\nFrozen candidate pools saved to {FROZEN_PATH}")


if __name__ == "__main__":
    freeze_candidates()
