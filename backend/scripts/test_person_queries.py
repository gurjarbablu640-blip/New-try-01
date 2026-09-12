import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.research_provider import research_router

queries = [
    'site:linkedin.com/in "Gabriel India" Quality',
    'site:linkedin.com/in "Endurance Technologies" Quality Head',
    'site:linkedin.com/in "Apollo Tyres" Plant Head',
    '"Gabriel India" "Plant Head" OR "Quality Head" Chakan',
    '"Endurance Technologies" "Plant Head" OR "Quality" Aurangabad'
]

for q in queries:
    print(f"=== Query: {q} ===")
    res = research_router.search(q, num_results=4)
    results = res.get("results", [])
    if not results:
        print("  NO RESULTS")
    for r in results:
        url = r.get("url", "")
        title = r.get("title", "")
        print(f"  - [{r.get('engine')}] {title}")
        print(f"    URL: {url}")
