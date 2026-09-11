import json
from services.browser_research_adapter import browser_research_adapter

test_cases = [
    ("Varroc", "https://varroc.com"),
    ("Craftsman", "https://craftsmanautomation.com"),
    ("Sansera", "https://sansera.in")
]

print("Starting 3 browser regression tests...")
for name, url in test_cases:
    res = browser_research_adapter.dispatch_research_task(company_name=name, target_urls=[url])
    d = res.get("data", {})
    lat = d.get("latency_seconds", 0)
    actions = d.get("actions_performed", [])
    pages = d.get("pages_inspected", [])
    first_title = pages[0].get("title", "N/A") if pages else "N/A"
    second_title = pages[0].get("second_page", {}).get("title", "None") if pages else "None"
    ev = d.get("unique_evidence", [])
    print(f"=== {name} ===")
    print(f"Status: {res.get('status')} | Latency: {lat}s")
    print(f"Page 1 Title: {first_title}")
    print(f"Page 2 (Multi-Step Traversal): {second_title}")
    print(f"Actions Executed ({len(actions)}): {actions}")
    print(f"Evidence Discovered ({len(ev)}): {ev}")
