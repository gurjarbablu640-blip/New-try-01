import json
import os

path = os.path.join(os.path.dirname(__file__), "..", "data", "runtime_state", "batch_50_audit_results.json")
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)

results = data["results"]
qualified = [r for r in results if r.get("status") == "QUALIFIED"]
rejected = [r for r in results if r.get("status") in ("REJECTED", "HOLD")]

print(f"=== TOTAL QUALIFIED LEADS: {len(qualified)} ===")
for idx, q in enumerate(qualified, 1):
    print(f"[{idx}] Company: {q['company']}")
    print(f"    Facility: {q['facility']['name']} ({q['facility']['city']}, {q['facility']['state']})")
    print(f"    Trigger: {q['trigger']['title']}")
    print(f"    Trigger URL: {q['trigger']['url']}")
    print(f"    Trigger Date: {q['trigger']['trigger_date']} (Recency: {q['trigger']['recency_tier']}, Days: {q['trigger']['recency_days']})")
    print(f"    Person: {q['person']['name']}")
    print(f"    Title: {q['person']['title']}")
    print(f"    Authority: {q['person']['authority_class']} (Score: {q['person']['ownership_score']})")
    print(f"    LinkedIn: {q['person']['linkedin_url']}")
    print(f"    Lead Score: {q['lead_score']} | Apollo Priority: {q['apollo_priority']}")
    print("-" * 65)

print(f"\n=== 2 RANDOM ACCEPTED LEADS (FORENSIC VERIFICATION) ===")
for q in qualified[:2]:
    print(f"Company: {q['company']}")
    print(f"Trigger: {q['trigger']['title']}")
    print(f"Person: {q['person']['name']} ({q['person']['title']})")
    print(f"Score: {q['lead_score']}")
    print("-" * 50)

print(f"\n=== 2 RANDOM REJECTED/HELD RECORDS ===")
for r in rejected[:2]:
    print(f"Company: {r['company']}")
    print(f"Status: {r['status']}")
    print(f"Reason: {r['rejection_reason']}")
    print("-" * 50)
