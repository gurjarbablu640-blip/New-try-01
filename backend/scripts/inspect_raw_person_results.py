import os
import sys
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from services.research_provider import research_router

targets = [
    "Samvardhana Motherson International",
    "Craftsman Automation",
    "Endurance Technologies",
    "Apollo Tyres",
    "Bharat Forge",
]

for t in targets:
    q = f'"{t}" ("Quality Head" OR "Head of Quality" OR "Plant Head" OR "VP Quality")'
    print(f"\n==========================================")
    print(f"QUERY: {q}")
    res = research_router.search(q, num_results=3)
    for r in res.get("results", []):
        print(f"  * {r.get('title')}")
        print(f"    URL: {r.get('url')}")
        print(f"    Snippet: {(r.get('content') or r.get('snippet') or '')[:140]}")
