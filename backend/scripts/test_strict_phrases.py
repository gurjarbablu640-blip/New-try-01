import requests

queries = [
    '"Apollo Tyres" "Quality Head"',
    '"Apollo Tyres" "Plant Head"',
    '"Endurance Technologies" "Quality Head"',
    '"Bharat Forge" "Quality Head"',
    '"Gabriel India" "Quality Head"',
    '"Tata Motors" "Plant Head" Sanand',
    '"Maruti Suzuki" "Plant Head" Hansalpur',
]

for q in queries:
    print(f"\nQUERY: {q}")
    resp = requests.get("http://localhost:8080/search", params={
        "q": q,
        "format": "json",
        "engines": "bing",
        "language": "en-IN"
    }, timeout=10)
    if resp.status_code == 200:
        results = resp.json().get("results", [])
        print(f"  Got {len(results)} results:")
        for r in results[:3]:
            t = r.get("title", "").encode('ascii', 'ignore').decode('ascii')
            u = r.get("url", "")
            s = (r.get("content", "") or "")[:120].encode('ascii', 'ignore').decode('ascii')
            print(f"  * {t}")
            print(f"    URL: {u}")
            print(f"    Snippet: {s}")
