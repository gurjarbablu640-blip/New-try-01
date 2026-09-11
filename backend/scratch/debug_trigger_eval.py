import json
import urllib.request
import urllib.parse
import sys
import os

sys.path.insert(0, "/app")

from services.trigger_discovery_service import (
    classify_source_tier,
    event_semantics_verified,
    extract_event_date,
    extract_trigger_facility_link,
)
from services.entity_resolution import resolve_entity_match
from services.evidence_provenance import extract_domain

query = "Kaynes Technology Sanand plant expansion 2026"
url = f"http://searxng:8080/search?q={urllib.parse.quote(query)}&format=json"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(req) as resp:
    data = json.loads(resp.read().decode("utf-8"))

print(f"Total results: {len(data.get('results', []))}")
for i, r in enumerate(data.get("results", [])[:8], 1):
    u = r.get("url", "")
    t = r.get("title", "")
    c = r.get("content", "")
    tier = classify_source_tier(u, official_domain="kaynestechnology.net")
    ev_ok, ev_type, ev_desc = event_semantics_verified(c, t)
    dt_info = extract_event_date(c, t)
    fac_link = extract_trigger_facility_link(c + " " + t, known_city="Sanand", known_plant_name="Sanand Plant")
    print(f"[{i}] {t}")
    print(f"    URL: {u}")
    print(f"    Tier: {tier} | Event: {ev_ok} ({ev_type}) | Date: {dt_info['recency_status']} ({dt_info.get('event_date')}) | Fac: {fac_link['trigger_facility_specificity']} ({fac_link.get('facility_city_from_trigger')})")
