"""Execute 3 real browser research jobs via DeerFlow service."""
import json
import time
from services.deerflow_adapter import DeerFlowAdapter

def run_tests():
    adapter = DeerFlowAdapter(enabled=True, timeout_seconds=60)
    status = adapter.get_status()
    print("DeerFlow Status:", json.dumps(status, indent=2))
    assert status["reachable"] is True, "DeerFlow service must be reachable"

    jobs = [
        {
            "company": "Dixon Technologies (India) Ltd",
            "url": "https://dixoninfo.com",
            "why_escalated": "Extract dynamic manufacturing facility locations and SMT infrastructure across plants",
            "focus_areas": ["facilities", "plants", "manufacturing", "oragadam", "noida"],
        },
        {
            "company": "Craftsman Automation Ltd",
            "url": "https://www.craftsmanautomation.com",
            "why_escalated": "Multi-step navigation to discover exact precision machining and metrology plants",
            "focus_areas": ["facilities", "plants", "locations", "coimbatore", "pune"],
        },
        {
            "company": "Sona BLW Precision Forgings Ltd",
            "url": "https://www.sonacomstar.com",
            "why_escalated": "Discover EV driveline and bevel gear plant locations and inspection facilities",
            "focus_areas": ["plants", "manufacturing", "locations", "chennai", "gurgaon"],
        },
    ]

    results = []
    for j in jobs:
        print(f"\n==========================================")
        print(f"Starting DeerFlow Browser Job for {j['company']} ({j['url']})...")
        t0 = time.perf_counter()
        res = adapter.dispatch_research_task(
            company_name=j["company"],
            target_urls=[j["url"]],
            focus_areas=j["focus_areas"],
            task_type="deep_browser_research",
        )
        elapsed = time.perf_counter() - t0
        print(f"Completed in {elapsed:.2f}s, status: {res.get('status')}")
        data = res.get("data", {})
        print("Actions performed:", data.get("actions_performed"))
        print("Pages inspected count:", len(data.get("pages_inspected", [])))
        if data.get("pages_inspected"):
            p0 = data["pages_inspected"][0]
            print(f"Page 1 Title: {p0.get('title')}, Text Len: {p0.get('text_length')}")
            if "second_page" in p0:
                p1 = p0["second_page"]
                print(f"Step 2 Page Title: {p1.get('title')}, URL: {p1.get('url')}, Text Len: {p1.get('text_length')}")
        
        j_result = {
            "company": j["company"],
            "url": j["url"],
            "why_escalated": j["why_escalated"],
            "elapsed_seconds": round(elapsed, 2),
            "response": res,
        }
        results.append(j_result)

    with open("/app/data/deerflow_browser_jobs_evidence.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print("\nSaved all results to /app/data/deerflow_browser_jobs_evidence.json")

if __name__ == "__main__":
    run_tests()
