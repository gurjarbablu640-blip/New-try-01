import requests

targets = [
    ("Apollo Tyres", "Chennai"),
    ("Endurance Technologies", "Aurangabad"),
    ("Bharat Forge", "Pune"),
]

for company, city in targets:
    q = f'"{company}" "Quality" "Head" OR "Manager"'
    print(f"\nTarget: {company}")
    print(f"Query: {q}")
    resp = requests.get("http://localhost:8080/search", params={
        "q": q,
        "format": "json",
        "engines": "bing",
        "categories": "general",
        "language": "en-IN"
    }, timeout=10)
    if resp.status_code == 200:
        results = resp.json().get("results", [])
        print(f"  Got {len(results)} results:")
        for r in results[:4]:
            t = r.get("title", "")
            u = r.get("url", "")
            s = (r.get("content", "") or "")[:120].encode('ascii', 'ignore').decode('ascii')
            print(f"  * {t} | {u}")
            print(f"    Snippet: {s}")
