import json
with open('/app/scratch/deep_research_40_results.json') as f:
    data = json.load(f)
print('Generated:', data['generated_at'])
print('Total:', data['total_companies'])
print('Elapsed:', data['elapsed_seconds'], 's')
print('Trigger verified:', data['trigger_verified_count'])
print('Facility verified:', data['facility_verified_count'])
print('Person employment verified:', data['person_employment_verified_count'])
print('Person duties verified:', data['person_duties_verified_count'])
print('APOLLO_READY:', data['apollo_ready_count'])
print('Gate failure counts:', json.dumps(data['gate_failure_counts'], indent=2))
print()
for r in data['records']:
    print(
        f"{r['company'][:40]:<40} "
        f"trig={r['trigger_verified']} "
        f"prec={r.get('address_precision','?'):<18} "
        f"emp={r['employment_verified']} "
        f"duty={r['duties_verified']} "
        f"score={r['lead_score']:5.1f} "
        f"status={r['status']} "
        f"{'HOLD_WHY: ' + r.get('hold_reason','') if r['status']=='HOLD' else ''}"
    )
