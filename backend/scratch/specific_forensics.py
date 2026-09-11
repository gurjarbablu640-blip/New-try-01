import json
import urllib.request
import urllib.parse

SEARXNG_URL = "http://searxng:8080"

queries = [
    ("Rohit Chaubey exact Subros", 'site:linkedin.com/in "Rohit Chaubey" "Subros"'),
    ("A K Banerjee exact Ramkrishna", 'site:linkedin.com/in "Banerjee" "Ramkrishna Forgings" "Quality"'),
    ("M Senthilkumar exact Craftsman", 'site:linkedin.com/in "Senthilkumar" "Craftsman Automation" "Quality"'),
    ("Anil Patil exact Varroc Chakan", 'site:linkedin.com/in "Anil Patil" "Varroc" "Quality"'),
    ("Varroc Chakan capex trigger 2024 2025 2026", '"Varroc Engineering" "Chakan" plant expansion OR capex OR "manufacturing"'),
    ("Craftsman Coimbatore capex trigger", '"Craftsman Automation" "Coimbatore" capex OR expansion OR "plant"'),
    ("Subros Noida capex trigger", '"Subros" "Noida" plant expansion OR capex OR facility')
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
                print(f"Snippet: {r.get('content')[:250]}...")
    except Exception as e:
        print(f"Error for {label}: {e}")
