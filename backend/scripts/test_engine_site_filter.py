import urllib.request
import urllib.parse
import json

for q_format in [
    'linkedin.com/in "Gabriel India" Quality',
    '"linkedin.com/in" "Gabriel India" Quality',
    'Gabriel India Quality Head linkedin',
    'site:in.linkedin.com/in Gabriel India Quality',
    'Gabriel India "Head Quality" OR "Plant Head"',
]:
    params = {
        "q": q_format,
        "format": "json",
        "engines": "bing",
    }
    url = f"http://localhost:8080/search?{urllib.parse.urlencode(params)}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            results = data.get("results", [])
            print(f"Format [{q_format}]: {len(results)} results")
            for r in results[:3]:
                print(f"   -> {r.get('url')} | {r.get('title')}")
    except Exception as e:
        print(f"Format [{q_format}] error: {e}")

