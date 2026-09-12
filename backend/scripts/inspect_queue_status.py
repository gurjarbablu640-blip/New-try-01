import json
import os

q_file = os.path.join(os.path.dirname(__file__), "..", "data", "runtime_state", "apollo_pending_queue.json")
with open(q_file, "r", encoding="utf-8") as f:
    records = json.load(f)

active = [r for r in records if r.get("status") == "PENDING_APOLLO_RENEWAL"]
p1 = [r for r in active if r.get("lookup_priority") == "P1"]
p2 = [r for r in active if r.get("lookup_priority") == "P2"]

def count_status(st):
    return sum(1 for r in records if r.get("status") == st)

print("================================================================================")
print("              SALESOORJA APOLLO QUEUE FORENSIC STATUS AUDIT                     ")
print("================================================================================")
print(f"TOTAL RECORDS:                  {len(records)}")
print(f"ACTIVE_APOLLO_READY:            {len(active)}")
print(f"  P1 (>=95):                    {len(p1)}")
print(f"  P2 (90–94):                   {len(p2)}")
print(f"HOLD_LOW_SCORE:                 {count_status('HOLD_LOW_SCORE')}")
print(f"HOLD_STALE_TRIGGER:             {count_status('HOLD_STALE_TRIGGER')}")
print(f"HOLD_PERSON_REVIEW:             {count_status('HOLD_PERSON_REVIEW')}")
print(f"HOLD_WRONG_PERSON:              {count_status('HOLD_WRONG_PERSON')}")
print(f"HOLD_TRIGGER_INVALID:           {count_status('HOLD_TRIGGER_INVALID')}")
print(f"HOLD_FACILITY_AMBIGUOUS:        {count_status('HOLD_FACILITY_AMBIGUOUS')}")
print(f"HOLD_PROVENANCE_INVALID:        {count_status('HOLD_QUEUE_PROVENANCE_INVALID')}")
print(f"HOLD_RECENCY_INCONSISTENT:      {count_status('HOLD_RECENCY_INCONSISTENT')}")
print("================================================================================")
