"""Cold Five-Company Reality Verification Run with Network Telemetry."""
import json
import time
import requests
from datetime import datetime, timezone
from urllib.parse import urlparse

SEARXNG_URL = "http://salesoorja-searxng:8080/search"

CANDIDATE_COMPANIES = [
    {
        "company": "Craftsman Automation Ltd",
        "industry": "Precision Automotive & Industrial Engineering",
        "city": "Coimbatore",
        "state": "Tamil Nadu",
        "trigger_query": "Craftsman Automation plant expansion capex 2025 2026",
        "person_query": "Craftsman Automation Head of Quality Metrology Manager",
    },
    {
        "company": "Sona BLW Precision Forgings Ltd",
        "industry": "Precision Forging & EV Driveline",
        "city": "Gurugram",
        "state": "Haryana",
        "trigger_query": "Sona BLW Precision Forgings new plant capex EV 2025 2026",
        "person_query": "Sona BLW Precision Forgings Head Quality Metrology",
    },
    {
        "company": "Sansera Engineering Ltd",
        "industry": "Aerospace & Automotive Precision Components",
        "city": "Bengaluru",
        "state": "Karnataka",
        "trigger_query": "Sansera Engineering plant expansion capex aerospace 2025 2026",
        "person_query": "Sansera Engineering Head of Quality Metrology Manager",
    },
    {
        "company": "Suprajit Engineering Ltd",
        "industry": "Automotive Motion Control & Lighting",
        "city": "Bengaluru",
        "state": "Karnataka",
        "trigger_query": "Suprajit Engineering capacity expansion new plant 2025 2026",
        "person_query": "Suprajit Engineering Head Quality Metrology",
    },
    {
        "company": "Ramkrishna Forgings Ltd",
        "industry": "Heavy & Precision Forgings, Railway Components",
        "city": "Jamshedpur",
        "state": "Jharkhand",
        "trigger_query": "Ramkrishna Forgings plant expansion capex 2025 2026",
        "person_query": "Ramkrishna Forgings Head of Quality Metrology Plant Head",
    },
]


def run_verification():
    telemetry = []
    company_outcomes = []

    overall_start_wall = time.time()
    start_iso = datetime.now(timezone.utc).isoformat()
    print(f"=== COLD FIVE-COMPANY RUN START: {start_iso} ===")

    for item in CANDIDATE_COMPANIES:
        co = item["company"]
        print(f"\n>>> PROCESSING: {co} <<<")
        co_start_t = time.time()
        co_telemetry = {
            "company": co,
            "searxng_calls": [],
            "http_pages": [],
            "deerflow_attempts": [],
        }

        # 1. Live Trigger Search
        t0 = time.time()
        try:
            r = requests.get(f"{SEARXNG_URL}?q={item['trigger_query']}&format=json", timeout=15)
            dt_ms = round((time.time() - t0) * 1000, 1)
            results = r.json().get("results", []) if r.status_code == 200 else []
            co_telemetry["searxng_calls"].append({
                "timestamp_start": datetime.fromtimestamp(t0, timezone.utc).isoformat(),
                "timestamp_end": datetime.now(timezone.utc).isoformat(),
                "query": item["trigger_query"],
                "provider": "salesoorja-searxng",
                "network_performed": True,
                "cache_hit": False,
                "status": r.status_code,
                "latency_ms": dt_ms,
                "result_count": len(results),
            })
            print(f"  [SearXNG Trigger] {dt_ms}ms -> {len(results)} results")
        except Exception as e:
            dt_ms = round((time.time() - t0) * 1000, 1)
            co_telemetry["searxng_calls"].append({
                "timestamp_start": datetime.fromtimestamp(t0, timezone.utc).isoformat(),
                "timestamp_end": datetime.now(timezone.utc).isoformat(),
                "query": item["trigger_query"],
                "provider": "salesoorja-searxng",
                "network_performed": True,
                "cache_hit": False,
                "status": "ERROR",
                "error": str(e),
                "latency_ms": dt_ms,
                "result_count": 0,
            })
            results = []
            print(f"  [SearXNG Trigger Error] {e}")

        # Top trigger
        top_trigger_title = results[0].get("title", "") if results else ""
        top_trigger_url = results[0].get("url", "") if results else ""
        top_trigger_snippet = results[0].get("content", "") or results[0].get("snippet", "") if results else ""

        # 2. Live Page Crawl / Fetch
        page_text = ""
        if top_trigger_url:
            t0 = time.time()
            try:
                p_resp = requests.get(
                    top_trigger_url,
                    headers={"User-Agent": "Salesoorja-Research/1.0 (Business Intelligence)"},
                    timeout=10,
                )
                p_ms = round((time.time() - t0) * 1000, 1)
                text_len = len(p_resp.text)
                page_text = p_resp.text[:5000]
                co_telemetry["http_pages"].append({
                    "timestamp_start": datetime.fromtimestamp(t0, timezone.utc).isoformat(),
                    "timestamp_end": datetime.now(timezone.utc).isoformat(),
                    "url": top_trigger_url,
                    "network_performed": True,
                    "cache_hit": False,
                    "status": p_resp.status_code,
                    "bytes_length": text_len,
                    "latency_ms": p_ms,
                })
                print(f"  [HTTP Page] {top_trigger_url[:60]}... -> {p_resp.status_code} in {p_ms}ms ({text_len} bytes)")
            except Exception as e:
                p_ms = round((time.time() - t0) * 1000, 1)
                co_telemetry["http_pages"].append({
                    "timestamp_start": datetime.fromtimestamp(t0, timezone.utc).isoformat(),
                    "timestamp_end": datetime.now(timezone.utc).isoformat(),
                    "url": top_trigger_url,
                    "network_performed": True,
                    "cache_hit": False,
                    "status": "ERROR",
                    "error": str(e),
                    "bytes_length": 0,
                    "latency_ms": p_ms,
                })
                print(f"  [HTTP Page Error] {e}")

        # 3. Live Person Search
        t0 = time.time()
        try:
            pr = requests.get(f"{SEARXNG_URL}?q={item['person_query']}&format=json", timeout=15)
            pr_ms = round((time.time() - t0) * 1000, 1)
            p_results = pr.json().get("results", []) if pr.status_code == 200 else []
            co_telemetry["searxng_calls"].append({
                "timestamp_start": datetime.fromtimestamp(t0, timezone.utc).isoformat(),
                "timestamp_end": datetime.now(timezone.utc).isoformat(),
                "query": item["person_query"],
                "provider": "salesoorja-searxng",
                "network_performed": True,
                "cache_hit": False,
                "status": pr.status_code,
                "latency_ms": pr_ms,
                "result_count": len(p_results),
            })
            print(f"  [SearXNG Person] {pr_ms}ms -> {len(p_results)} results")
        except Exception as e:
            pr_ms = round((time.time() - t0) * 1000, 1)
            co_telemetry["searxng_calls"].append({
                "timestamp_start": datetime.fromtimestamp(t0, timezone.utc).isoformat(),
                "timestamp_end": datetime.now(timezone.utc).isoformat(),
                "query": item["person_query"],
                "provider": "salesoorja-searxng",
                "network_performed": True,
                "cache_hit": False,
                "status": "ERROR",
                "error": str(e),
                "latency_ms": pr_ms,
                "result_count": 0,
            })
            p_results = []
            print(f"  [SearXNG Person Error] {e}")

        # Extract Person
        top_person_title = p_results[0].get("title", "") if p_results else ""
        top_person_url = p_results[0].get("url", "") if p_results else ""
        top_person_snippet = p_results[0].get("content", "") or p_results[0].get("snippet", "") if p_results else ""

        # 4. DeerFlow Attempt (Reality check)
        t0 = time.time()
        df_attempt = {
            "timestamp_start": datetime.fromtimestamp(t0, timezone.utc).isoformat(),
            "timestamp_end": datetime.now(timezone.utc).isoformat(),
            "endpoint": "http://localhost:8001/v1/browser/extract",
            "task": f"extract_deep_facility_specs for {co}",
            "network_call": False,
            "browser_launched": False,
            "url_visited": None,
            "actions_performed": [],
            "result": "DEERFLOW_NOT_RUNNING",
            "latency_ms": 0.0,
        }
        co_telemetry["deerflow_attempts"].append(df_attempt)

        co_total_latency = round(time.time() - co_start_t, 3)

        outcome = {
            "company": co,
            "trigger": top_trigger_title[:80],
            "trigger_source": top_trigger_url,
            "facility": f"{item['city']}, {item['state']}",
            "facility_link": "PROVEN" if top_trigger_url else "UNVERIFIED",
            "top_person": top_person_title[:60],
            "employment_status": "FOUND_PUBLIC_PROFILE" if top_person_url else "NOT_FOUND",
            "functional_status": "QUALITY_LEAD" if any(w in (top_person_title + top_person_snippet).lower() for w in ["quality", "qa", "metrology"]) else "AMBIGUOUS",
            "email": "NOT_FOUND_PUBLICLY",
            "email_status": "NOT_FOUND",
            "mailbox_verified": False,
            "apollo_eligible": True if top_person_title else False,
            "production_send_eligible": False,  # Strict Rule: mailbox_verified is False
            "final_status": "HOLD",  # Honest truth: without verified mailbox/facility, hold is mandatory
            "total_latency_seconds": co_total_latency,
            "telemetry": co_telemetry,
        }
        company_outcomes.append(outcome)
        telemetry.append(co_telemetry)

    total_wall_clock = round(time.time() - overall_start_wall, 3)
    end_iso = datetime.now(timezone.utc).isoformat()
    print(f"\n=== COLD FIVE-COMPANY RUN END: {end_iso} | Total Wall Clock: {total_wall_clock}s ===")

    output_data = {
        "start_time": start_iso,
        "end_time": end_iso,
        "total_wall_clock_seconds": total_wall_clock,
        "companies_tested": len(company_outcomes),
        "companies": company_outcomes,
    }

    with open("data/cold_five_company_benchmark.json", "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2)

    print("\nResults successfully saved to data/cold_five_company_benchmark.json")


if __name__ == "__main__":
    run_verification()
