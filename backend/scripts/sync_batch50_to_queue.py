import json
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.fast_contact_waterfall import (
    FastContactWaterfallService,
    STATUS_PENDING_APOLLO_RENEWAL,
)

def sync_batch50():
    b50_path = os.path.join(os.path.dirname(__file__), "..", "data", "runtime_state", "batch_50_audit_results.json")
    if not os.path.exists(b50_path):
        print("batch_50_audit_results.json not found")
        return

    with open(b50_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    waterfall = FastContactWaterfallService()
    synced = 0
    for r in data.get("results", []):
        if r.get("status") == "QUALIFIED":
            c_name = r["company"]
            c_domain = r.get("domain", "")
            t = r.get("trigger", {})
            fac = r.get("facility", {})
            p = r.get("person", {})
            score = r.get("lead_score", 95.0)

            candidate_payload = {
                "company": c_name,
                "legal_company_name": c_name,
                "official_domain": c_domain,
                "facility": fac.get("plant_name", ""),
                "facility_city": fac.get("city", ""),
                "facility_state": fac.get("state", ""),
                "trigger_type": t.get("event_type", "INDUSTRIAL_EXPANSION_CAPEX"),
                "trigger_date": t.get("trigger_date", ""),
                "recency_days": t.get("recency_days", 0),
                "timing_class": t.get("recency_tier", "CURRENT"),
                "trigger_source": t.get("url", ""),
                "ongoing_source": t.get("ongoing_source", ""),
                "ongoing_date": t.get("ongoing_date", ""),
                "timing_reason": f"Trigger {t.get('recency_tier')} ({t.get('recency_days')} days old)",
                "facility_source": t.get("url", ""),
                "person_source": p.get("source_url", ""),
                "trigger_to_facility": "DIRECT",
                "trigger_eval": {
                    "trigger_facility_confidence": "DIRECT",
                    "trigger_facility_link": "DIRECT",
                },
                "lead_score": score,
                "primary_person": {
                    "name": p.get("name", ""),
                    "title": p.get("title", ""),
                    "linkedin_url": p.get("linkedin_url", ""),
                    "authority_classification": p.get("authority_class", "STRONG_PLANT_QUALITY_OWNER"),
                    "source_url": p.get("source_url", ""),
                },
            }
            res = waterfall.enrich_with_apollo(candidate_payload)
            print(f"Synced {c_name} / {p.get('name')}: {res.get('status')}, queue_status={res.get('queue_status')}")
            synced += 1

    print(f"Total synced: {synced}")

if __name__ == "__main__":
    sync_batch50()
