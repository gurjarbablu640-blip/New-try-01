import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from services.research_provider import research_router
import json

queries = [
    '"Shyam Metalics" Jamuria capex press release',
    '"Shyam Metalics" Pakuria capex press release',
    '"Shyam Metalics" Jamuria expansion BSE NSE filing',
    'site:bseindia.com "Shyam Metalics" Jamuria',
]

for q in queries:
    print(f"=== QUERY: {q} ===")
    res = research_router.search(q, num_results=3)
    for item in res.get("results", []):
        print("URL:", item.get("url"))
        print("TITLE:", item.get("title"))
        print("SNIPPET:", item.get("snippet", "")[:250])
        print("---")
