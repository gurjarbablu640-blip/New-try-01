import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.research_provider import research_router

companies = [
    ("Gabriel India", "Chakan"),
    ("Endurance Technologies", "Aurangabad"),
    ("Craftsman Automation", "Coimbatore"),
    ("Apollo Tyres", "Chennai"),
    ("CEAT", "Halol"),
]

for co, hub in companies:
    q = f'"{co}" ("Plant Head" OR "Head of Quality" OR "Vice President Operations") {hub}'
    print(f"=== {co} ({hub}) ===")
    res = research_router.search(q, num_results=4)
    for r in res.get("results", []):
        print(f"  - {r.get('title')} | {r.get('url')}")
        content = r.get("content") or r.get("snippet") or ""
        print(f"    Snippet: {content[:150]}")
