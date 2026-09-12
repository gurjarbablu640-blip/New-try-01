import requests

query = 'site:linkedin.com/in "Gabriel India" "Quality"'
print(f"Testing SearXNG with query: {query}")

# Test 1: engines="google,brave,bing"
resp = requests.get("http://localhost:8080/search", params={
    "q": query,
    "format": "json",
    "engines": "google,brave,bing",
}, timeout=15)
if resp.status_code == 200:
    results = resp.json().get("results", [])
    print(f"\n--- engines: google,brave,bing ({len(results)} results) ---")
    for r in results[:5]:
        print("Title:", r.get("title"))
        print("URL:  ", r.get("url"))
        print("Engine:", r.get("engine"))
else:
    print(f"Failed: {resp.status_code}")

# Test 2: general search without site:
q2 = '"Gabriel India" "Head of Quality" OR "Plant Head"'
resp2 = requests.get("http://localhost:8080/search", params={
    "q": q2,
    "format": "json",
    "engines": "google,brave,bing",
}, timeout=15)
if resp2.status_code == 200:
    results2 = resp2.json().get("results", [])
    print(f"\n--- q2 with google,brave,bing ({len(results2)} results) ---")
    for r in results2[:5]:
        print("Title:", r.get("title"))
        print("URL:  ", r.get("url"))
        print("Engine:", r.get("engine"))
