import json
import urllib.request
import urllib.parse

SEARXNG_URL = "http://searxng:8080"

queries = [
    ("Varroc Chakan Plant Details", "Varroc Engineering Limited Chakan MIDC plant address Pune"),
    ("Varroc Chakan Facility Operations", "site:varroc.com Chakan Pune plant"),
    ("Varroc Capex Expansion Pune Chakan", "Varroc Engineering capex expansion Chakan Pune 2024 OR 2025 OR 2026"),
    ("Varroc BSE NSE Filing Capex", "Varroc Engineering regulatory filing capex expansion plant"),
    ("Anil Patil Varroc Exact Role", "Anil Patil Varroc Head Quality Plant Chakan Pune LinkedIn"),
    ("Varroc Chakan Quality Manager", "Varroc Engineering Chakan Quality Manager OR Quality Head LinkedIn"),
    ("Varroc Metrology Calibration", "Varroc Engineering Metrology Calibration Quality Engineer LinkedIn"),
    ("Varroc Plant Head Chakan", "Varroc Engineering Chakan Plant Head OR General Manager LinkedIn")
]

for label, q in queries:
    url = f"{SEARXNG_URL}/search?q={urllib.parse.quote(q)}&format=json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            results = data.get("results", [])
            print(f"\n==================== {label} ====================")
            for r in results[:3]:
                print(f"Title: {r.get('title')}")
                print(f"URL: {r.get('url')}")
                print(f"Snippet: {r.get('content')[:250]}...")
    except Exception as e:
        print(f"Error for {label}: {e}")
