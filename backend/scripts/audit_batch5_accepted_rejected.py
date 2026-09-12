import os
import sys
import json
import random

sys.stdout.reconfigure(encoding="utf-8")

results_file = os.path.join(os.path.dirname(__file__), "..", "data", "runtime_state", "batch_5_audit_results.json")
if not os.path.exists(results_file):
    print(f"Error: {results_file} does not exist yet.")
    sys.exit(1)

with open(results_file, "r", encoding="utf-8") as f:
    data = json.load(f)

telemetry = data["telemetry"]
failure_funnel = data["failure_funnel"]
results = data["results"]

accepted = [r for r in results if r.get("status") == "QUALIFIED"]
rejected = [r for r in results if r.get("status") in ("HOLD", "REJECTED")]

print("================================================================================")
print("                    BATCH 5 AUTONOMOUS AUDIT REPORT                             ")
print("================================================================================")
print(f"Total Companies Evaluated:   {telemetry['companies_considered']}")
print(f"Wall Clock Time:             {telemetry['total_wall_clock_sec']}s ({telemetry['avg_sec_per_company']}s/company)")
print(f"Verified Triggers Discovered:{telemetry['valid_events']}")
print(f"Facility Qualified:          {telemetry['facility_qualified']}")
print(f"Person Qualified:            {telemetry['person_qualified']}")
print(f"Apollo Queued:               {telemetry['apollo_queued']} (P1: {telemetry['p1_queued']}, P2: {telemetry['p2_queued']})")
print("\nThroughput:")
print(f"  Raw Companies/hr:          {telemetry.get('raw_companies_per_hour', 0.0)}")
print(f"  Verified Triggers/hr:      {telemetry.get('verified_triggers_per_hour', 0.0)}")
print(f"  Facility-Qualified/hr:     {telemetry.get('facility_qualified_per_hour', 0.0)}")
print(f"  Person-Qualified/hr:       {telemetry.get('person_qualified_per_hour', 0.0)}")
print(f"  Apollo-Ready/hr:           {telemetry.get('apollo_ready_per_hour', 0.0)}")

print("\nFailure Funnel Breakdown:")
for k, v in sorted(failure_funnel.items(), key=lambda item: item[1], reverse=True):
    print(f"  {k:28s}: {v}")

print("\n" + "="*80)
print(f"AUDIT 1: TOP ACCEPTED CANDIDATES (Total Qualified: {len(accepted)})")
print("="*80)

accepted_sorted = sorted(accepted, key=lambda x: x.get("lead_score", 0.0), reverse=True)
top_5 = accepted_sorted[:5]

if not top_5:
    print("  No accepted records found in this batch.")
else:
    for idx, r in enumerate(top_5, 1):
        trig = r.get("trigger", {})
        fac = r.get("facility", {})
        p = r.get("person", {})
        print(f"\n[ACCEPTED #{idx}] {r['company']} (Score: {r.get('lead_score', 0.0)} | {r.get('apollo_priority', 'P2')})")
        print(f"  Trigger Event:     {trig.get('title')}")
        print(f"  Trigger Date:      {trig.get('trigger_date')} ({trig.get('recency_days')} days old | {trig.get('recency_tier')})")
        print(f"  Trigger Source:    {trig.get('url')}")
        print(f"  Ongoing Evidence:  {trig.get('ongoing_source') or 'N/A (CURRENT)'}")
        print(f"  Facility Linkage:  {fac.get('name')} | City: {fac.get('city')} | State: {fac.get('state')} ({fac.get('linkage')})")
        print(f"  Decision Maker:    {p.get('name')} | Title: {p.get('title')}")
        print(f"  Authority Class:   {p.get('authority_class')} | Score: {p.get('ownership_score')}")
        print(f"  LinkedIn URL:      {p.get('linkedin_url')}")
        print(f"  Provenance:        {p.get('provenance')}")
        print(f"  Status:            {r.get('status')} -> PENDING_APOLLO_RENEWAL")

print("\n" + "="*80)
print(f"AUDIT 2: RANDOM ACCEPTED SAMPLES (2 Records)")
print("="*80)
random.seed(66)
if len(accepted_sorted) > 5:
    random_accepted = random.sample(accepted_sorted[5:], min(2, len(accepted_sorted) - 5))
else:
    random_accepted = random.sample(accepted_sorted, min(2, len(accepted_sorted)))

for idx, r in enumerate(random_accepted, 1):
    trig = r.get("trigger", {})
    fac = r.get("facility", {})
    p = r.get("person", {})
    print(f"\n[RANDOM ACCEPTED #{idx}] {r['company']} (Score: {r.get('lead_score', 0.0)} | {r.get('apollo_priority', 'P2')})")
    print(f"  Trigger Date:      {trig.get('trigger_date')} ({trig.get('recency_days')} days old | {trig.get('recency_tier')})")
    print(f"  Trigger Source:    {trig.get('url')}")
    print(f"  Facility Linkage:  {fac.get('name')} ({fac.get('city')})")
    print(f"  Decision Maker:    {p.get('name')} | {p.get('title')}")
    print(f"  LinkedIn URL:      {p.get('linkedin_url')}")

print("\n" + "="*80)
print(f"AUDIT 3: RANDOM REJECTED SAMPLES (2 Records from {len(rejected)} rejected)")
print("="*80)
random_rejected = random.sample(rejected, min(2, len(rejected))) if rejected else []
for idx, r in enumerate(random_rejected, 1):
    trig = r.get("trigger", {})
    print(f"\n[REJECTED #{idx}] {r['company']}")
    print(f"  Rejection Reason:  {r.get('rejection_reason')}")
    print(f"  Status:            {r.get('status')}")
    if trig:
        print(f"  Trigger Found:     {trig.get('title')} ({trig.get('trigger_date')}, {trig.get('recency_tier')})")
    else:
        print(f"  Trigger Found:     None / Recency semantics failed")
