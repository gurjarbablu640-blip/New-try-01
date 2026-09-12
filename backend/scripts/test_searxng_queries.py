import requests
import json

queries = [
    'Gabriel India Quality Head',
    'Gabriel India Plant Head Pune',
    'Endurance Technologies Quality Head',
    'Apollo Tyres Head Quality',
    'Tata Motors Plant Head Pune',
    'Maruti Suzuki Quality Head'
]

print("=== Testing SearXNG without site: constraint ===")
for q in queries:
    resp = requests.get("http://localhost:8080/search", params={
        "q": q,
        "format": "json",
        "language": "en-IN"
    }, timeout=10)
    if resp.status_code == 200:
        data = resp.json()
        results = data.get("results", [])
        print(f"\nQuery: {q} -> {len(results)} results")
        for r in results[:4]:
            t = r.get("title", "")
            u = r.get("url", "")
            s = (r.get("content", "") or "")[:100]
            s = (r.get("content", "") or "")[:100].encode('ascii', 'ignore').decode('ascii')
            t = t.encode('ascii', 'ignore').decode('ascii')
            print(f"  * {t} | {u}")
            print(f"    Snippet: {s}")
