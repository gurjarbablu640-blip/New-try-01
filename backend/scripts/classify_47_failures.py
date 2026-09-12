"""Forensic classifier for the 47 HOLD_TRIGGER_INVALID queue records."""
import json
import re
from urllib.parse import urlparse

def classify_record(r):
    url = r.get("trigger_source") or ""
    snippet = r.get("trigger_evidence_snippet") or r.get("trigger_event_text") or ""
    title = r.get("trigger_source_title") or r.get("trigger_title") or ""
    u_lower = url.lower()
    t_lower = f"{title} {snippet}".lower()
    parsed = urlparse(u_lower)
    path = parsed.path
    domain = parsed.netloc.replace("www.", "")

    # Check 1: Stock quote / share price ticker
    if any(p in u_lower for p in ["/stockpricequote/", "/stocks/companyid", "screener.in/company", "market-capitalisation", "/share-price-today", "stock-price"]):
        return "STOCK_QUOTE_PAGE"
    if "share price" in t_lower or "stock price" in t_lower or "market cap" in t_lower or "bse:" in t_lower or "nse:" in t_lower:
        if any(f in domain for f in ["moneycontrol.com", "economictimes.indiatimes.com", "screener.in", "livemint.com", "financialexpress.com"]):
            return "STOCK_QUOTE_PAGE"

    # Check 2: Generic company homepage
    if path in ("", "/", "/index.html", "/index.php") or (not path.strip("/") and not parsed.query):
        return "GENERIC_COMPANY_PAGE"
    if any(p in u_lower for p in ["/about-us", "/about", "/contact-us", "/our-company", "/profile"]):
        return "GENERIC_COMPANY_PAGE"

    # Check 3: Generic financial page (quarterly results, dividend, investor presentation without expansion)
    if any(p in u_lower for p in ["/financials", "/dividend", "/quarterly-results", "/balance-sheet", "/profit-loss"]):
        return "GENERIC_FINANCIAL_PAGE"
    if "dividend" in t_lower or "quarterly result" in t_lower or "q1 result" in t_lower or "q2 result" in t_lower or "q3 result" in t_lower or "q4 result" in t_lower:
        return "GENERIC_FINANCIAL_PAGE"

    # Check 4: Unrelated news (sports, politics, obituaries, cricket)
    if any(w in t_lower for w in ["cricket", "scorecard", "match", "ipl", "actor", "actress", "cinema", "movie", "passed away", "tribute", "obituary"]):
        return "UNRELATED_NEWS"

    # Check 5: Search snippet false positive (snippet contains generic word or unrelated mention)
    expansion_words = ["commission", "capacity", "expansion", "new plant", "new line", "capex", "facility", "modernization", "inaugurat"]
    has_event = any(w in t_lower for w in expansion_words)
    if not has_event:
        return "NO_EVENT_SEMANTICS"

    # Check 6: Wrong event type (e.g. CSR, software launch, financial tie-up)
    if any(w in t_lower for w in ["csr", "solar rooftop on office", "tree plantation", "award won", "software launch"]):
        return "WRONG_EVENT_TYPE"

    return "SEARCH_SNIPPET_FALSE_POSITIVE"

def main():
    with open("data/runtime_state/apollo_pending_queue.json", "r", encoding="utf-8") as f:
        queue = json.load(f)

    invalids = [r for r in queue if r.get("status") == "HOLD_TRIGGER_INVALID"]
    print(f"Total HOLD_TRIGGER_INVALID records: {len(invalids)}")

    counts = {}
    details = []

    for idx, r in enumerate(invalids, 1):
        cat = classify_record(r)
        counts[cat] = counts.get(cat, 0) + 1
        details.append({
            "index": idx,
            "company": r.get("company"),
            "url": r.get("trigger_source"),
            "category": cat
        })

    print("\n--- ROOT CAUSE COUNTS ---")
    sorted_counts = sorted(counts.items(), key=lambda x: x[1], reverse=True)
    for cat, cnt in sorted_counts:
        pct = (cnt / len(invalids)) * 100
        print(f"{cat:35}: {cnt:2d} ({pct:5.1f}%)")

    print("\n--- SAMPLE DETAILS ---")
    for d in details[:15]:
        print(f"[{d['index']:02d}] {d['category']:30} | {d['company']:30} | {d['url']}")

if __name__ == "__main__":
    main()
