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

test_targets = [
    ("Kaynes Technology", "kaynestechnology.net", "Sanand", "Kaynes Technology Sanand expansion 2026"),
    ("Suzuki Motor Gujarat", "marutisuzuki.com", "Sanand", "Suzuki Motor Gujarat Sanand plant commissioning 2026"),
    ("Tata Electronics", "tataelectronics.com", "Hosur", "Tata Electronics Hosur plant expansion 2026"),
    ("Amara Raja Energy", "amararaja.com", "Divitipally", "Amara Raja Divitipally gigafactory commissioning 2026"),
    ("Exide Energy", "exideindustries.com", "Bengaluru", "Exide Energy battery plant Bengaluru commissioning 2026"),
    ("Dixon Technologies", "dixoninfo.com", "Noida", "Dixon Technologies manufacturing facility commissioning 2026"),
    ("Bharat Forge", "bharatforge.com", "Baramati", "Bharat Forge Baramati plant expansion 2026"),
    ("Micron Technology", "micron.com", "Sanand", "Micron Sanand plant commissioning 2026"),
]

for comp, dom, city, q in test_targets:
    url = f"http://searxng:8080/search?q={urllib.parse.quote(q)}&format=json"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            results = data.get("results", [])
            print(f"\nTarget: {comp} ({city}) | Results: {len(results)}")
            for r in results[:4]:
                u = r.get("url", "")
                t = r.get("title", "")
                c = r.get("content", "")
                tier = classify_source_tier(u, official_domain=dom)
                ev_ok, ev_type, ev_desc = event_semantics_verified(c, t)
                dt = extract_event_date(c, t)
                fac = extract_trigger_facility_link(c + " " + t, known_city=city)
                print(f"  [{tier}] {t[:65]}")
                print(f"    URL: {u[:75]}")
                print(f"    Event: {ev_ok} ({ev_type}) | Date: {dt['ongoing_status']} | Fac: {fac['trigger_facility_specificity']} ({fac['facility_city_from_trigger']})")
    except Exception as e:
        print(f"Error {comp}: {e}")
