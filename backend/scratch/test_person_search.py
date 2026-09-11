from scratch.run_plant_specific_trigger_recovery import search_searxng_audited

queries = [
    'Kaynes Technology "Quality Manager" LinkedIn',
    'Kaynes Semicon Sanand "Plant Head" OR "Director" OR "VP"',
    'Suzuki Motor Gujarat Sanand "Plant Head" LinkedIn',
    'Dixon Technologies Noida "Quality Head" LinkedIn',
    'Exide Energy Solutions Bengaluru "Plant Head" OR "Quality Head"',
]

for q in queries:
    print(f"\n=== Query: {q} ===")
    results = search_searxng_audited(q, max_results=3)
    for r in results:
        print("  Title:", r.get("title"))
        print("  Snippet:", (r.get("content") or r.get("snippet") or "")[:150])
        print("  URL:", r.get("url"))
