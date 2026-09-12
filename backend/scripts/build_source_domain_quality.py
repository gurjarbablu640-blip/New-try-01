"""Builds source_domain_quality.json by aggregating research history across previous batches."""
import glob
import json
import os
import re
from urllib.parse import urlparse

def extract_domain(url: str) -> str:
    if not url:
        return ""
    try:
        netloc = urlparse(url).netloc
        return netloc.lower().replace("www.", "")
    except Exception:
        return ""

def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    state_dir = os.path.join(base_dir, "data", "runtime_state")
    out_path = os.path.join(state_dir, "source_domain_quality.json")

    domain_stats = {}

    def record_domain(url: str, is_valid: bool):
        d = extract_domain(url)
        if not d:
            return
        if d not in domain_stats:
            domain_stats[d] = {
                "results_seen": 0,
                "valid_trigger_count": 0,
                "invalid_trigger_count": 0,
                "acceptance_rate": 0.0,
                "sample_urls": [],
            }
        stats = domain_stats[d]
        stats["results_seen"] += 1
        if is_valid:
            stats["valid_trigger_count"] += 1
        else:
            stats["invalid_trigger_count"] += 1
        if len(stats["sample_urls"]) < 3 and url not in stats["sample_urls"]:
            stats["sample_urls"].append(url)

    # 1. Process apollo_pending_queue.json
    queue_path = os.path.join(state_dir, "apollo_pending_queue.json")
    if os.path.exists(queue_path):
        with open(queue_path, "r", encoding="utf-8") as f:
            queue = json.load(f)
            for r in queue:
                u = r.get("trigger_source") or ""
                st = r.get("status", "")
                is_val = st == "PENDING_APOLLO_RENEWAL"
                record_domain(u, is_val)

    # 2. Process all batch_*_audit_results.json
    audit_files = glob.glob(os.path.join(state_dir, "batch_*_audit_results.json"))
    for af in audit_files:
        try:
            with open(af, "r", encoding="utf-8") as f:
                data = json.load(f)
                recs = data.get("records", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
                for r in recs:
                    trig = r.get("trigger") or {}
                    if isinstance(trig, dict):
                        u = trig.get("url") or trig.get("source_url") or ""
                        lead_score = r.get("lead_score", 0)
                        status = r.get("status", "")
                        # A trigger was valid if candidate scored >= 85 and entered the qualified queue
                        is_val = (status in ("APOLLO_STAGED", "PENDING_APOLLO_RENEWAL")) and lead_score >= 85
                        if u:
                            record_domain(u, is_val)
        except Exception as e:
            print(f"Error reading {af}: {e}")

    # Compute acceptance rates
    for d, stats in domain_stats.items():
        tot = stats["results_seen"]
        stats["acceptance_rate"] = round((stats["valid_trigger_count"] / tot) if tot > 0 else 0.0, 4)

    # Sort by results seen
    sorted_domains = dict(sorted(domain_stats.items(), key=lambda item: item[1]["results_seen"], reverse=True))

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(sorted_domains, f, indent=2)

    print(f"Source domain quality report generated: {len(sorted_domains)} unique domains tracked.")
    print("Top 10 domains by volume:")
    for d, stats in list(sorted_domains.items())[:10]:
        print(f"  {d:35}: seen={stats['results_seen']:3d}, valid={stats['valid_trigger_count']:2d}, invalid={stats['invalid_trigger_count']:3d}, rate={stats['acceptance_rate']*100:.1f}%")

if __name__ == "__main__":
    main()
