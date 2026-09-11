from scratch.run_targeted_deepening import search_searxng_cached

queries = [
    'Kaynes Technology Sanand semiconductor plant capex',
    'Kaynes Semicon Sanand GIDC facility',
    'site:kaynestechnology.net Sanand',
    'site:economictimes.indiatimes.com Kaynes Sanand semiconductor',
]
for q in queries:
    print(f"=== Query: {q} ===")
    res = search_searxng_cached(q, max_results=2)
    for r in res:
        print("  URL:", r.get("url"))
        print("  Title:", r.get("title"))
        print("  Snippet:", r.get("content", "")[:180].replace("\n", " "))
