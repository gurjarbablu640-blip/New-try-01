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
)

targets = [
    ("Kaynes Technology Sanand", "kaynestechnology.net", "Sanand"),
    ("Suzuki Motor Gujarat Sanand plant", "globalsuzuki.com", "Sanand"),
    ("Amara Raja Divitipally gigafactory", "amararaja.com", "Divitipally"),
    ("Exide Energy battery plant", "exideindustries.com", "Bengaluru"),
    ("Dixon Technologies manufacturing plant", "dixoninfo.com", "Noida"),
    ("Bharat Forge Baramati plant", "bharatforge.com", "Baramati"),
]

for q, dom, city in targets:
    url = f"http://searxng:8080/search?q={urllib.parse.quote(q)}&categories=news&format=json"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req) as resp:
            d = json.loads(resp.read().decode("utf-8"))
            results = d.get("results", [])
            print(f"\n=== {q} (News results: {len(results)}) ===")
            for r in results[:3]:
                u = r.get("url", "")
                t = r.get("title", "")
                c = r.get("content", "")
                tier = classify_source_tier(u, official_domain=dom)
                ev_ok, ev_type, ev_desc = event_semantics_verified(c, t)
                dt = extract_event_date(c, t)
                fac = extract_trigger_facility_link(c + " " + t, known_city=city)
                print(f"  [{tier}] {t[:70]}")
                print(f"    URL: {u}")
                print(f"    Event: {ev_ok} ({ev_type}) | Date: {dt['ongoing_status']} | Fac: {fac['trigger_facility_specificity']} ({fac['facility_city_from_trigger']})")
    except Exception as e:
        print(f"Error {q}: {e}")
