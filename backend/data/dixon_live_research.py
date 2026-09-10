"""Live Research Script for High-Confidence Dixon Validation."""
import json
import re
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from datetime import datetime, timezone
from services.research_provider import research_router
from services.decision_maker_discovery import classify_company_evidence, score_candidate_functional_ownership, rank_calibration_candidates
from services.contact_confidence import classify_email_address, classify_phone_number, validate_person_name
from services.opportunity_gates import evaluate_apollo_credit_gate

def main():
    print("==================================================")
    print("1. LIVE SEARCH: DIXON NOIDA TRIGGER VALIDATION")
    print("==================================================")
    q_trig = 'Dixon Technologies Noida ("Sector 68" OR "Sector 90" OR "capacity expansion" OR "new facility" OR "PLI" OR "plant") -stock -share'
    res_trig = research_router.search(q_trig, num_results=6)
    trigger_results = res_trig.get("results", [])
    print(f"Trigger queries returned {len(trigger_results)} results:")
    for idx, r in enumerate(trigger_results):
        print(f"[{idx+1}] Title: {r.get('title')}")
        print(f"    URL: {r.get('url')}")
        print(f"    Snippet: {r.get('snippet')}")
        print()

    print("==================================================")
    print("2. LIVE SEARCH: DIXON QUALITY / METROLOGY / CALIBRATION / NOIDA")
    print("==================================================")
    q_dm = 'Dixon Technologies Noida ("Quality Head" OR "Head of Quality" OR "Plant Quality" OR "Metrology" OR "QA" OR "QC" OR "Instrumentation" OR "Plant Head")'
    res_dm = research_router.search(q_dm, num_results=8)
    dm_results = res_dm.get("results", [])
    print(f"Decision-maker queries returned {len(dm_results)} results:")
    for idx, r in enumerate(dm_results):
        print(f"[{idx+1}] Title: {r.get('title')}")
        print(f"    URL: {r.get('url')}")
        print(f"    Snippet: {r.get('snippet')}")
        print()

    print("==================================================")
    print("3. LIVE SEARCH: VERIFY RAJKUMAR GUPTA AT DIXON NOIDA")
    print("==================================================")
    q_rg = '"Rajkumar Gupta" "Dixon Technologies" (Noida OR "Plant Head")'
    res_rg = research_router.search(q_rg, num_results=5)
    rg_results = res_rg.get("results", [])
    print(f"Rajkumar Gupta verification query returned {len(rg_results)} results:")
    for idx, r in enumerate(rg_results):
        print(f"[{idx+1}] Title: {r.get('title')}")
        print(f"    URL: {r.get('url')}")
        print(f"    Snippet: {r.get('snippet')}")
        print()

    print("==================================================")
    print("4. LIVE SEARCH: MONEYTIMES ARTICLE & EXPANSION LOCATION")
    print("==================================================")
    q_exp = 'Dixon Technologies "new capacity expansion" OR "capacity expansion" Noida'
    res_exp = research_router.search(q_exp, num_results=5)
    exp_results = res_exp.get("results", [])
    for idx, r in enumerate(exp_results):
        print(f"[{idx+1}] Title: {r.get('title')}")
        print(f"    URL: {r.get('url')}")
        print(f"    Snippet: {r.get('snippet')}")
        print()

    # Also check direct Moneytimes article content if accessible
    import urllib.request
    try:
        mt_url = "https://moneytimes.in/dixon-technologies-strengthens-electronics-manufacturing-with-new-capacity-expansion/"
        req = urllib.request.Request(mt_url, headers={'User-Agent': 'Mozilla/5.0'})
        html = urllib.request.urlopen(req, timeout=5).read().decode('utf-8', 'ignore')
        # Extract text snippets mentioning location/facility
        loc_mentions = re.findall(r'([^.\n]*?(?:Noida|facility|plant|manufacturing|crore|expansion|Sector)[^.\n]*?\.)', html, re.I)
        print(f"Moneytimes article fetched ({len(html)} bytes). Location snippets:")
        for m in loc_mentions[:10]:
            print(f"  -> {m.strip()}")
    except Exception as e:
        print(f"Moneytimes fetch failed: {e}")

if __name__ == "__main__":
    main()

