import json
import urllib.request
import urllib.parse
import sys
sys.path.insert(0, "/app")

from services.trigger_discovery_service import (
    classify_source_tier,
    event_semantics_verified,
    extract_event_date,
    extract_trigger_facility_link,
    generate_event_first_discovery_queries,
)

queries = [
    "India new manufacturing plant 2026",
    "manufacturing plant commissioning India 2026",
    "new automotive plant commissioning India 2026",
    "new solar module line commissioning India 2026",
    "new electronics factory India SMT 2026",
    "site:economictimes.indiatimes.com plant commissioning 2026",
    "site:business-standard.com new plant 2026",
]

for q in queries:
    url = f"http://searxng:8080/search?q={urllib.parse.quote(q)}&format=json"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            results = data.get("results", [])
            print(f"\nQuery: {q} (Results: {len(results)})")
            for r in results[:4]:
                u = r.get("url", "")
                t = r.get("title", "")
                c = r.get("content", "")
                tier = classify_source_tier(u)
                ev_ok, ev_type, ev_desc = event_semantics_verified(c, t)
                dt = extract_event_date(c, t)
                fac = extract_trigger_facility_link(c + " " + t)
                print(f"  - [{tier}] {t[:60]}")
                print(f"    URL: {u}")
                print(f"    Event: {ev_ok} ({ev_type}) | Date: {dt['ongoing_status']} | Fac: {fac['trigger_facility_specificity']} ({fac['facility_city_from_trigger']})")
    except Exception as e:
        print(f"Error for {q}: {e}")
