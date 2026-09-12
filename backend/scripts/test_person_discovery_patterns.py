import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.research_provider import research_router

test_queries = [
    # 1. Direct role + company
    '"Gabriel India" "Head of Quality"',
    '"Gabriel India" "Plant Head" Chakan',
    '"Endurance Technologies" "Head of Quality"',
    '"Apollo Tyres" "Plant Head" Chennai',
    '"Bharat Forge" "Head of Quality" Pune',
    # 2. LinkedIn in title or query without site:
    '"Gabriel India" "Quality Head" linkedin',
    '"Endurance Technologies" "Plant Head" linkedin',
    '"Apollo Tyres" "Head - Quality" linkedin',
    # 3. Annual report / leadership
    '"Gabriel India" annual report "Plant Head" OR "Quality"',
    '"Tata Motors" "Plant Head" Sanand',
]

for q in test_queries:
    print(f"\n==========================================")
    print(f"QUERY: {q}")
    res = research_router.search(q, num_results=3)
    results = res.get("results", [])
    if not results:
        print("  NO RESULTS")
    for r in results:
        print(f"  - Title: {r.get('title')}")
        print(f"    URL:   {r.get('url')}")
        print(f"    Snippet: {(r.get('content') or r.get('snippet') or '')[:120]}")
