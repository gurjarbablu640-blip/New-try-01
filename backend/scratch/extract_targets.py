import json

with open('/app/scratch/deep_research_40_results.json') as f:
    data = json.load(f)

targets = [r for r in data['records'] if r.get('trigger_verified')]
print(f"Total trigger_verified targets: {len(targets)}")
for i, t in enumerate(targets, 1):
    c = t.get('company')
    sec = t.get('sector')
    dom = t.get('domain')
    fac = t.get('facility')
    url = t.get('trigger_source_url')
    dt = t.get('trigger_date')
    score = t.get('lead_score')
    snip = t.get('trigger_snippet', '')[:100].replace('\n', ' ')
    print(f"{i:2d}. {c} | {sec} | {dom} | {fac}")
    print(f"    Trigger: {url} | date={dt} | score={score}")
    print(f"    Snippet: {snip}...")
