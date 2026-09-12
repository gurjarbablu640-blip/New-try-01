import requests

engines = [
    "bing", "duckduckgo", "google", "brave", "yahoo", "startpage", 
    "qwant", "mojeek", "seznam", "yandex", "baidu"
]

query = '"Maruti Suzuki" "Hansalpur" "Plant Head"'
print(f"Testing engines with query: {query}\n")

for eng in engines:
    try:
        r = requests.get("http://localhost:8080/search", params={
            "q": query,
            "format": "json",
            "engines": eng,
            "timeout": 5
        }, timeout=8)
        if r.status_code == 200:
            res = r.json().get("results", [])
            print(f"[{eng}] {len(res)} results")
            for item in res[:2]:
                print(f"   -> {item.get('title')} ({item.get('url')})")
        else:
            print(f"[{eng}] HTTP {r.status_code}")
    except Exception as e:
        print(f"[{eng}] Error: {type(e).__name__}")
