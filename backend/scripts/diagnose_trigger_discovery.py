import os
import sys
import json

sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.research_provider import research_router
from services.signal_discovery_engine import generate_industrial_trigger_query
from services.trigger_discovery_service import extract_event_date
from datetime import datetime, timezone

NOW_DT = datetime(2026, 9, 12, tzinfo=timezone.utc)

companies = ["Hindustan Aeronautics Limited", "Bharat Electronics Limited", "Tata Steel Limited"]

for c_name in companies:
    print(f"\n--- Testing: {c_name} ---")
    clean = c_name.replace("Limited", "").replace("Ltd", "").strip()
    queries = [
        f'"{clean}" ("new plant" OR "commissioning" OR "expansion" OR "manufacturing unit" OR "facility")',
        f'"{clean}" capex "2026"',
    ]
    for q in queries:
        print("Query:", q)
        res = research_router.search(q, num_results=4)
        results = res.get("results", [])
        print(f"Results count: {len(results)}")
        for r in results:
            title = r.get("title", "")
            snippet = r.get("content", "") or r.get("snippet", "")
            url = r.get("url", "")
            d_info = extract_event_date(snippet, title=title, now_dt=NOW_DT)
            print(f"  * Title: {title[:60]}... | DateInfo: {d_info.get('has_date')}, {d_info.get('event_date')}, {d_info.get('recency_days')}d, {d_info.get('recency_status')} | URL: {url[:50]}")
