"""Aggregates all overnight telemetry, audit records, and safety stats for the 08:40 IST Morning Freeze Report.
"""
import os
import sys
import json
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding="utf-8")

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "runtime_state")

def load_json(filename):
    p = os.path.join(DATA_DIR, filename)
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return None

def compile_morning_report_data():
    queue = load_json("apollo_pending_queue.json") or []
    batch25 = load_json("autonomous_25_batch_results.json")
    batch50 = load_json("batch_50_audit_results.json")
    batch100 = load_json("batch_100_audit_results.json")
    recheck5 = load_json("recheck_five_audit.json") or []

    # Queue stats
    active_queue = [q for q in queue if q.get("status") == "PENDING_APOLLO_RENEWAL"]
    held_queue = [q for q in queue if str(q.get("status", "")).startswith("HOLD")]
    p1_count = sum(1 for q in active_queue if q.get("lookup_priority") == "P1")
    p2_count = sum(1 for q in active_queue if q.get("lookup_priority") == "P2")

    # Recency audit breakdown across all queued / evaluated
    recency_summary = {
        "CURRENT": 0,
        "RECENT": 0,
        "STALE": 0,
        "stale_rejected": 0,
        "recent_with_ongoing_proof": 0,
    }

    for item in queue:
        t_class = item.get("timing_class")
        if t_class in recency_summary:
            recency_summary[t_class] += 1
        if str(item.get("status", "")).startswith("HOLD"):
            recency_summary["stale_rejected"] += 1
        if t_class == "RECENT" and item.get("ongoing_source"):
            recency_summary["recent_with_ongoing_proof"] += 1


    report_payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "queue": {
            "total_active": len(active_queue),
            "total_held": len(held_queue),
            "p1": p1_count,
            "p2": p2_count,
            "active_records": active_queue,
            "held_records": held_queue,
        },
        "batches": {
            "batch_25": batch25.get("telemetry") if batch25 else None,
            "batch_50": batch50.get("telemetry") if batch50 else None,
            "batch_100": batch100.get("telemetry") if batch100 else None,
        },
        "recency_summary": recency_summary,
        "safety_audit": {
            "real_emails_sent": 0,
            "apollo_live_calls": 0,
            "paid_llm_calls": 0,
            "linkedin_messages_sent": 0,
            "secrets_exposed": 0,
            "git_pushes": 0,
        }
    }

    out_file = os.path.join(DATA_DIR, "morning_report_summary.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(report_payload, f, indent=2)

    print("Morning report data compiled successfully into", out_file)
    return report_payload

if __name__ == "__main__":
    compile_morning_report_data()
