"""Audits accepted and rejected candidates from Batch 21 live autonomous research."""
import json
import os
import random

audit_file = os.path.join(os.path.dirname(__file__), "..", "data", "runtime_state", "batch_21_audit_results.json")
if not os.path.exists(audit_file):
    print(f"Error: {audit_file} does not exist yet.")
    exit(1)

with open(audit_file, "r", encoding="utf-8") as f:
    data = json.load(f)

results = data["results"]
telemetry = data["telemetry"]
failure_funnel = data["failure_funnel"]

accepted = [r for r in results if r.get("status") in ("QUALIFIED", "ACCEPTED")]
rejected = [r for r in results if r.get("status") not in ("QUALIFIED", "ACCEPTED")]

print("================================================================")
print("BATCH 21 AUDIT REPORT (50 NEW COMPANIES)")
print("================================================================")
print(f"Total Companies Evaluated: {telemetry['companies_considered']}")
print(f"Total Wall Time: {telemetry['total_wall_clock_sec']}s ({telemetry['avg_sec_per_company']}s/company)")
print(f"Throughput: {telemetry.get('raw_companies_per_hour', 'N/A')} raw cos/hr | {telemetry.get('apollo_ready_per_hour', 'N/A')} qualified/hr")
print(f"Accepted: {len(accepted)} | Rejected/Hold: {len(rejected)}")
print(f"Failure Funnel: {failure_funnel}\n")

print("--- ACCEPTED LEADS AUDIT ---")
for r in accepted:
    trig = r.get("trigger") or {}
    fac = r.get("facility") or {}
    pers = r.get("person") or {}
    print(f"Company: {r['company']}")
    print(f"  Trigger Date: {trig.get('trigger_date')} | Recency: {trig.get('recency_days')} days | Timing Class: {trig.get('recency_tier')}")
    print(f"  Trigger Source: {trig.get('url')}")
    print(f"  Facility: {fac.get('name')} in {fac.get('city')}, {fac.get('state')} (Linkage: {fac.get('linkage')})")
    print(f"  Person: {pers.get('name')} | Title: {pers.get('title')} (Authority: {pers.get('authority_classification', pers.get('authority_class'))}, Ownership: {pers.get('role_score')})")
    print(f"  Lead Score: {r.get('lead_score')} | Apollo Priority: {r.get('apollo_priority')} | Status: {r.get('status')}\n")

print("--- RANDOM REJECTED CANDIDATES AUDIT (3 SAMPLES) ---")
random.seed(42)
sampled_rejected = random.sample(rejected, min(3, len(rejected)))
for r in sampled_rejected:
    print(f"Company: {r['company']}")
    print(f"  Status: {r.get('status')} | Rejection Reason: {r.get('rejection_reason')}")
    print(f"  Sector: {r.get('sector')}\n")
