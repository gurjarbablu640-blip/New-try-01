"""Forensic re-check of top 5 candidates.
Queries SearXNG and checks public sources for company, trigger, facility, and person.
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

candidates = [
    {
        "company": "Exide Energy Solutions Ltd",
        "person": "Pradeep N",
        "facility": "Bengaluru Battery Cell Gigafactory",
        "title": "Head Quality Cell Manufacturing"
    },
    {
        "company": "Maruti Suzuki / Suzuki Motor Gujarat",
        "person": "Sunil Sharma",
        "facility": "Suzuki Motor Gujarat Manufacturing Complex",
        "title": "Plant Quality Head"
    },
    {
        "company": "Aarti Industries Ltd",
        "person": "Dharmendra Dave",
        "facility": "Dahej Specialty Chemical Manufacturing Complex",
        "title": "Vice President Quality"
    },
    {
        "company": "JSW Energy Ltd",
        "person": "Alok Mishra",
        "facility": "Vijayanagar Green Hydrogen & Renewable Plant",
        "title": "Head Testing & Metrology"
    },
    {
        "company": "Dixon Technologies (India) Ltd",
        "person": "Ashish Kumar",
        "facility": "Noida Precision Electronics Manufacturing Plant",
        "title": "Quality Head SMT Line"
    }
]

print("=== STARTING FORENSIC AUDIT OF 5 EXISTING CANDIDATES ===\n")

for c in candidates:
    print(f"--- CANDIDATE: {c['company']} | {c['person']} ({c['title']}) ---")
    # 1. Search for person + company + quality
    p_query = f'"{c["person"]}" "{c["company"].split("/")[0].strip()}"'
    print(f"Query 1: {p_query}")
    results = search(p_query, limit=3)
    found_person = False
    for r in results:
        title = r.get("title", "")
        url = r.get("url", "")
        content = r.get("content", "")
        print(f"  Result: {title} | {url}\n    Snippet: {content[:150]}")
        if c["person"].lower() in (title + content).lower():
            found_person = True
            
    # 2. Search for site:linkedin.com/in
    li_query = f'site:linkedin.com/in "{c["person"]}" "{c["company"].split("/")[0].strip()}"'
    print(f"Query 2 (LinkedIn): {li_query}")
    li_results = search(li_query, limit=3)
    for r in li_results:
        print(f"  LinkedIn Result: {r.get('title')} | {r.get('url')}\n    Snippet: {r.get('content', '')[:150]}")

    # 3. Search for trigger & facility
    trig_query = f'"{c["company"].split("/")[0].strip()}" {c["facility"]} expansion OR commissioning OR plant'
    print(f"Query 3 (Trigger & Facility): {trig_query}")
    trig_results = search(trig_query, limit=2)
    for r in trig_results:
        print(f"  Facility Result: {r.get('title')} | {r.get('url')}\n    Snippet: {r.get('content', '')[:150]}")
    print("\n" + "="*70 + "\n")
