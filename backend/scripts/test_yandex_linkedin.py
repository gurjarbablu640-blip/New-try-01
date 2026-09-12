import requests

queries = [
    'site:linkedin.com/in "Maruti Suzuki" "Hansalpur"',
    'site:linkedin.com/in "Atul Jain" "Maruti Suzuki"',
    'site:linkedin.com/in "Apollo Tyres" "Plant Head"',
    'site:linkedin.com/in "Endurance Technologies" "Quality Head"',
    'site:linkedin.com/in "Bharat Forge" "Quality Head"',
    'site:linkedin.com/in "Gabriel India" "Plant Head"',
]

print("=== Testing Yandex on SearXNG for LinkedIn People ===")
for q in queries:
    r = requests.get("http://localhost:8080/search", params={
        "q": q,
        "format": "json",
        "engines": "yandex",
    }, timeout=10)
    if r.status_code == 200:
        res = r.json().get("results", [])
        print(f"\nQuery: {q} -> {len(res)} results")
        for item in res[:3]:
            t = item.get("title", "").encode('ascii', 'ignore').decode('ascii')
            u = item.get("url", "")
            s = (item.get("content", "") or "")[:120].encode('ascii', 'ignore').decode('ascii')
            print(f"  * {t} | {u}")
            print(f"    Snippet: {s}")
    else:
        print(f"Query {q} failed: HTTP {r.status_code}")
