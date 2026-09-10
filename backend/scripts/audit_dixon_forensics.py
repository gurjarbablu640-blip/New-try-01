"""Phase A Forensic Investigation Script for Dixon Technologies.
Audits:
1. Rakesh Sharma: Exact company, title, location, facility relation, recency, same-name/former status.
2. Calibration-relevant candidates at Dixon (QA, QC, Metrology, Instrumentation, Plant Operations).
3. 2026 Tamil Nadu / Oragadam laptop & PC manufacturing plant MoU / expansion.
"""
import json
import logging
from typing import Any, Dict, List

from services.research_provider import research_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("dixon_forensic_audit")


def search_and_log(query: str, num_results: int = 6) -> List[Dict[str, Any]]:
    print(f"\n========================================================")
    print(f"QUERY: {query}")
    print(f"========================================================")
    res = research_router.search(query, num_results=num_results)
    results = res.get("results", [])
    print(f"Provider: {res.get('provider')} | Returned: {len(results)} items")
    for i, r in enumerate(results, 1):
        print(f"[{i}] Title: {r.get('title')}")
        print(f"    URL:   {r.get('url')}")
        print(f"    Snip:  {r.get('snippet')}\n")
    return results


def main():
    investigation = {}

    # 1. Rakesh Sharma Identity Investigation
    print("\n--- SECTION A1: RAKESH SHARMA IDENTITY & CAREER FORENSICS ---")
    investigation["q1_rakesh_dixon"] = search_and_log('"Rakesh Sharma" "Dixon Technologies"', num_results=8)
    investigation["q2_rakesh_title"] = search_and_log('"Rakesh Sharma" "Dixon" ("AVP" OR "Plant Head" OR "Operations" OR "General Manager" OR "Quality")', num_results=8)
    investigation["q3_rakesh_linkedin"] = search_and_log('site:linkedin.com/in "Rakesh Sharma" "Dixon Technologies"', num_results=8)
    investigation["q4_rakesh_other_companies"] = search_and_log('"Rakesh Sharma" ("Bajaj Auto" OR "Hero" OR "Samsung" OR "Voltas" OR "Dixon")', num_results=8)

    # 2. Calibration / Metrology / QA / QC Decision Makers at Dixon
    print("\n--- SECTION A2: DIXON QUALITY & METROLOGY DECISION MAKERS ---")
    investigation["q5_dixon_quality_head"] = search_and_log('"Dixon Technologies" ("Quality Head" OR "Head of Quality" OR "QA Head" OR "VP Quality")', num_results=8)
    investigation["q6_dixon_metrology"] = search_and_log('"Dixon Technologies" ("Metrology" OR "Calibration" OR "Instrumentation" OR "Testing Manager")', num_results=8)
    investigation["q7_dixon_plant_qa"] = search_and_log('"Dixon Technologies" ("Plant Quality" OR "Quality Manager" OR "DGM Quality" OR "AGM Quality")', num_results=8)
    investigation["q8_dixon_oragadam_head"] = search_and_log('"Dixon Technologies" ("Oragadam" OR "Chennai" OR "Tamil Nadu") ("Plant Head" OR "General Manager" OR "Operations Head")', num_results=8)

    # 3. Tamil Nadu / Oragadam Trigger & Exact Facility Linkage
    print("\n--- SECTION A3 & A4: TAMIL NADU / ORAGADAM TRIGGER & FACILITY EVIDENCE ---")
    investigation["q9_dixon_tn_trigger"] = search_and_log('"Dixon Technologies" ("Tamil Nadu" OR "Oragadam" OR "Chennai") ("MoU" OR "laptop" OR "plant" OR "expansion")', num_results=8)
    investigation["q10_dixon_tn_filing"] = search_and_log('"Dixon Technologies" "Tamil Nadu" ("BSE" OR "NSE" OR "press release" OR "exchange filing")', num_results=8)

    with open("/app/data/dixon_forensic_raw_results.json", "w", encoding="utf-8") as f:
        json.dump(investigation, f, indent=2)
    print("\n[SUCCESS] Raw results written to /app/data/dixon_forensic_raw_results.json")


if __name__ == "__main__":
    main()
