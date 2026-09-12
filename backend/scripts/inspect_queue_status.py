import json
import os

q_file = os.path.join(os.path.dirname(__file__), "..", "data", "runtime_state", "apollo_pending_queue.json")
with open(q_file, "r", encoding="utf-8") as f:
    records = json.load(f)

active = [r for r in records if r.get("status") == "PENDING_APOLLO_RENEWAL"]
held = [r for r in records if r.get("status") == "HOLD_STALE_TRIGGER"]
p1 = [r for r in active if r.get("lookup_priority") == "P1"]
p2 = [r for r in active if r.get("lookup_priority") == "P2"]

print(f"Total Records in Queue File: {len(records)}")
print(f"Active Leads (PENDING_APOLLO_RENEWAL): {len(active)} (P1: {len(p1)}, P2: {len(p2)})")
print(f"Held Leads (HOLD_STALE_TRIGGER): {len(held)}")

stale_in_active = [r for r in active if (r.get("recency_days") or 0) > 365]
recent_no_ongoing = [r for r in active if 180 < (r.get("recency_days") or 0) <= 365 and not r.get("ongoing_source")]
print(f"Violations in Active Queue (recency > 365d): {len(stale_in_active)}")
print(f"Violations in Active Queue (181-365d without ongoing evidence): {len(recent_no_ongoing)}")
