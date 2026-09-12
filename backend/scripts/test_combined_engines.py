import requests

tests = [
    # Trigger query
    ('Maruti Suzuki Hansalpur plant expansion', 'Trigger check'),
    ('Exide Energy Bengaluru lithium giga factory', 'Trigger check'),
    # Person query
    ('site:linkedin.com/in "Apollo Tyres" "Chennai" "Plant Head"', 'Person check'),
    ('site:linkedin.com/in "Endurance Technologies" "Quality Head"', 'Person check'),
    ('site:linkedin.com/in "Craftsman Automation" "Quality"', 'Person check'),
]

print("=== Testing SearXNG with engines: 'bing,yandex' ===")
for q, desc in tests:
    r = requests.get("http://localhost:8080/search", params={
        "q": q,
        "format": "json",
        "engines": "bing,yandex",
    }, timeout=15)
    if r.status_code == 200:
        res = r.json().get("results", [])
        print(f"\n[{desc}] Query: {q} -> {len(res)} results")
        for item in res[:2]:
            print(f"  * {item.get('title')} ({item.get('engine')})")
            print(f"    URL: {item.get('url')}")
    else:
        print(f"[{desc}] Failed HTTP {r.status_code}")
