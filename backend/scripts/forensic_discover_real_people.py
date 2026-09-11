"""Forensic search for REAL quality/plant leaders at the 5 target plants.
"""
import sys
import json
import requests

sys.stdout.reconfigure(encoding="utf-8")

def search(query, limit=5):
    try:
        r = requests.get("http://localhost:8080/search", params={"q": query, "format": "json"}, timeout=15)
        if r.status_code == 200:
            return r.json().get("results", [])[:limit]
    except Exception as e:
        print(f"Error searching for '{query}': {e}")
    return []

targets = [
    {
        "company": "Exide Energy Solutions",
        "queries": [
            'site:linkedin.com/in "Exide Energy Solutions" "Quality" OR "Metrology" OR "Plant"',
            '"Exide Energy Solutions" "Bengaluru" ("Quality Head" OR "Head of Quality" OR "Plant Head")',
        ]
    },
    {
        "company": "Suzuki Motor Gujarat / Maruti Suzuki Hansalpur",
        "queries": [
            'site:linkedin.com/in "Suzuki Motor Gujarat" ("Quality Head" OR "Head of Quality" OR "QA" OR "QC" OR "Plant Head")',
            'site:linkedin.com/in "Maruti Suzuki" "Hansalpur" "Quality"',
        ]
    },
    {
        "company": "Aarti Industries",
        "queries": [
            'site:linkedin.com/in "Aarti Industries" "Quality Head" OR "Head of Quality" OR "Vice President Quality"',
            'site:linkedin.com/in "Aarti Industries" "Dahej" "Quality"',
        ]
    },
    {
        "company": "JSW Energy Vijayanagar",
        "queries": [
            'site:linkedin.com/in "JSW Energy" "Vijayanagar" ("Quality" OR "Testing" OR "Plant Head")',
            'site:linkedin.com/in "JSW Energy" ("Head Quality" OR "Plant Quality")',
        ]
    },
    {
        "company": "Dixon Technologies",
        "queries": [
            'site:linkedin.com/in "Dixon Technologies" ("Quality Head" OR "Head Quality" OR "Quality Manager" OR "SMT")',
            'site:linkedin.com/in "Dixon Technologies" "Noida" "Quality"',
        ]
    }
]

for t in targets:
    print(f"==================================================")
    print(f"TARGET: {t['company']}")
    print(f"==================================================")
    for q in t["queries"]:
        print(f"\nQUERY: {q}")
        results = search(q, limit=4)
        for r in results:
            print(f"  * {r.get('title')}")
            print(f"    URL: {r.get('url')}")
            print(f"    Snippet: {r.get('content', '')[:160]}\n")
