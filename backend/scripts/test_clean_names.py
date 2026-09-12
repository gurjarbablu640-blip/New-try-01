import os
import sys
import re
import json

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.research_provider import research_router

test_companies = [
    "Samvardhana Motherson International Limited",
    "Ramkrishna Forgings Limited",
    "Minda Corporation Limited",
    "Lumax Auto Technologies Limited",
    "Apollo Tyres Limited",
]

for c in test_companies:
    clean = re.sub(r"\b(Limited|Ltd\.?|Pvt\.?|Private|LLP|Inc\.?)\b", "", c, flags=re.IGNORECASE).strip()
    q = f'site:linkedin.com/in "{clean}" "Quality"'
    print(f"\nTarget: {c} -> Clean: {clean}")
    print(f"Query: {q}")
    res = research_router.search(q, num_results=3)
    results = res.get("results", [])
    print(f"  Got {len(results)} results:")
    for r in results:
        print(f"   * {r.get('title')} ({r.get('url')})")
