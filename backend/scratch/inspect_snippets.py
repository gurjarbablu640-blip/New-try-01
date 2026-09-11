import json
with open('/app/scratch/deep_research_40_results.json') as f:
    data = json.load(f)

# Show first 8 records with trigger snippets
for r in data['records'][:8]:
    print(f"=== {r['company']} ===")
    print(f"  trigger_verified: {r['trigger_verified']}")
    print(f"  trigger_date: {r.get('trigger_date', 'N/A')}")
    print(f"  trigger_source_role: {r.get('trigger_source_role', 'N/A')}")
    print(f"  trigger_domain: {r.get('trigger_domain', 'N/A')}")
    print(f"  trigger_facility_confidence: {r.get('trigger_facility_confidence', 'N/A')}")
    print(f"  address_precision: {r.get('address_precision', 'N/A')}")
    print(f"  trigger_snippet: {r.get('trigger_snippet', '')[:200]}")
    print()
