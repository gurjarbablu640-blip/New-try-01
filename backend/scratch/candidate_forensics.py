import json
import urllib.request
import urllib.parse

SEARXNG_URL = "http://searxng:8080"

queries = [
    ("Varroc Capex", "Varroc Engineering Chakan MIDC capex plant expansion 2025 OR 2026"),
    ("Anil Patil", "Anil Patil Varroc Chakan Plant Quality Head LinkedIn"),
    ("M Senthilkumar", "M Senthilkumar Craftsman Automation Quality Metrology"),
    ("Sivasubramaniam S", "Sivasubramaniam S Sansera Engineering Calibration Lead"),
    ("Rohit Chaubey", "Rohit Chaubey Subros Manager Quality Noida"),
    ("A K Banerjee", "A K Banerjee Ramkrishna Forgings Quality Metallurgy")
]

for label, q in queries:
    url = f"{SEARXNG_URL}/search?q={urllib.parse.quote(q)}&format=json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            results = data.get("results", [])
            print(f"\n==================== {label} ====================")
            for r in results[:3]:
                print(f"Title: {r.get('title')}")
                print(f"URL: {r.get('url')}")
                print(f"Snippet: {r.get('content')[:200]}...")
    except Exception as e:
        print(f"Error for {label}: {e}")
