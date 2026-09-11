import json

with open('/app/scratch/targeted_deepening_results.json') as f:
    data = json.load(f)

print("=== FUNNEL ===")
print(json.dumps(data['funnel'], indent=2))
print("\n=== TELEMETRY ===")
print(json.dumps(data['telemetry'], indent=2))

print("\n=== RECORDS SUMMARY ===")
for i, r in enumerate(data['records'], 1):
    p = r.get('primary_person') or {}
    co = r['company'][:28]
    prec = r.get('address_precision', 'N/A')
    link = r.get('trigger_facility_confidence', 'N/A')
    pname = (p.get('name') or 'None')[:16]
    ptitle = (p.get('title') or 'None')[:28]
    score = r.get('lead_score', 0)
    status = r.get('status', 'N/A')
    hold = r.get('hold_reason', '')[:50]
    print(f"{i:2d}. {co:<28} | {prec:<15} | {link:<6} | {pname:<16} | {ptitle:<28} | {score:<4} | {status:<6} | {hold}")
