import os
import sys
import json
import glob
import re
from datetime import datetime, timezone, date
from dateutil import parser as date_parser

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

RUNTIME_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "runtime_state")

QUEUE_FILE = os.path.join(RUNTIME_DIR, "apollo_pending_queue.json")
REF_DATE = date(2026, 9, 12)

def load_json(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None

def parse_date(date_str: str):
    if not date_str or not str(date_str).strip():
        return None, "EMPTY_DATE"
    s = str(date_str).strip()
    # clean up dots or bullets
    s = s.replace("·", "").replace("•", "").strip()
    try:
        # Try standard formats
        for fmt in ("%Y-%m-%d", "%d %b, %Y", "%d %B, %Y", "%d-%m-%Y", "%d/%m/%Y"):
            try:
                dt = datetime.strptime(s, fmt).date()
                return dt, "EXACT_PARSED"
            except ValueError:
                pass
        # Month Year like "August 2026", "June 2026"
        for fmt in ("%B %Y", "%b %Y"):
            try:
                dt = datetime.strptime(s, fmt).date()
                # default to 1st of that month
                return dt, "MONTH_YEAR_APPROX"
            except ValueError:
                pass
        dt = date_parser.parse(s, fuzzy=True).date()
        return dt, "FUZZY_PARSED"
    except Exception as e:
        return None, f"PARSE_ERROR: {e}"

def is_stock_quote_url(url: str) -> bool:
    if not url:
        return False
    u = url.lower()
    stock_patterns = [
        "/stockpricequote/",
        "/stocks/companyid-",
        "stock-share-price",
        "screener.in/company/",
        "marketscreener.com",
        "livemint.com/market/",
        "bloomberg.com/quote/",
        "bseindia.com/stock-share-price",
        "/market-activity/stocks/",
    ]
    return any(p in u for p in stock_patterns)

def is_generic_company_page(url: str) -> bool:
    if not url:
        return True
    u = url.lower().rstrip("/")
    # Homepage or generic page
    parts = u.split("://")[-1].split("/")
    if len(parts) <= 1 or (len(parts) == 2 and parts[1] in ("", "about-us", "about", "contact", "home", "en")):
        return True
    return False

def analyze():
    queue = load_json(QUEUE_FILE) or []
    print(f"Loaded {len(queue)} queue records.")

    # Load all batch audit files
    batch_files = glob.glob(os.path.join(RUNTIME_DIR, "*audit*.json"))
    batch_items_by_company = {}
    for bf in batch_files:
        bn = os.path.basename(bf)
        data = load_json(bf)
        results = data.get("results", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
        for r in results:
            if isinstance(r, dict):
                c = (r.get("company") or r.get("company_name") or "").strip().lower()
                if c and c not in batch_items_by_company:
                    batch_items_by_company[c] = (bn, r)

    findings = []
    for idx, r in enumerate(queue):
        comp = r.get("company", "")
        c_low = comp.strip().lower()
        person_name = r.get("person_name", "")
        person_title = r.get("person_title", "")
        auth_class = r.get("authority_class", "")
        t_src = r.get("trigger_source", "")
        f_src = r.get("facility_source", "")
        p_src = r.get("person_source", "")
        t_date_str = r.get("trigger_date", "")
        stored_recency = r.get("recency_days")
        stored_score = r.get("lead_score")
        stored_prio = r.get("lookup_priority")
        stored_status = r.get("status")

        # Provenance match
        batch_match = None
        for k, v in batch_items_by_company.items():
            if k in c_low or c_low in k:
                batch_match = v
                break
        batch_file, batch_record = batch_match if batch_match else ("UNKNOWN", {})

        # Date analysis
        parsed_dt, parse_status = parse_date(t_date_str)
        if parsed_dt:
            calc_recency = (REF_DATE - parsed_dt).days
            recency_diff = abs(stored_recency - calc_recency)
            recency_inconsistent = (recency_diff > 2)
        else:
            calc_recency = None
            recency_diff = None
            recency_inconsistent = True

        # Trigger source analysis
        is_stock = is_stock_quote_url(t_src)
        is_gen = is_generic_company_page(t_src)
        trigger_snippet = ""
        trigger_title = ""
        if batch_record and isinstance(batch_record.get("trigger"), dict):
            trigger_snippet = batch_record["trigger"].get("snippet", "")
            trigger_title = batch_record["trigger"].get("title", "")

        findings.append({
            "idx": idx,
            "company": comp,
            "person_name": person_name,
            "person_title": person_title,
            "auth_class": auth_class,
            "batch_file": batch_file,
            "stored_status": stored_status,
            "stored_score": stored_score,
            "stored_prio": stored_prio,
            "stored_recency": stored_recency,
            "t_date_str": t_date_str,
            "parsed_dt": str(parsed_dt),
            "parse_status": parse_status,
            "calc_recency": calc_recency,
            "recency_diff": recency_diff,
            "recency_inconsistent": recency_inconsistent,
            "t_src": t_src,
            "is_stock": is_stock,
            "is_gen": is_gen,
            "trigger_snippet": trigger_snippet,
            "trigger_title": trigger_title,
            "facility": r.get("facility", ""),
            "city": r.get("city", ""),
            "facility_src": f_src,
        })

    with open("forensic_analysis_report.json", "w", encoding="utf-8") as f:
        json.dump(findings, f, indent=2)
    print("Saved forensic_analysis_report.json with 55 records.")

    print_summary(findings)

def print_summary(findings):
    print("\n" + "=" * 80)
    print("FORENSIC SUMMARY FINDINGS")
    print("=" * 80)
    recency_mismatches = [d for d in findings if d["recency_inconsistent"]]
    stock_sources = [d for d in findings if d["is_stock"]]
    gen_sources = [d for d in findings if d["is_gen"]]

    print(f"Total evaluated records: {len(findings)}")
    print(f"Recency data inconsistencies (>2d diff): {len(recency_mismatches)}")
    for rm in recency_mismatches:
        print(f"  [{rm['idx']:02d}] {rm['company'][:30]:30} | Stored: {rm['stored_recency']}d | Calc: {rm['calc_recency']}d | Date: {rm['t_date_str']}")

    print(f"\nStock price / quote pages as trigger: {len(stock_sources)}")
    for ss in stock_sources:
        print(f"  [{ss['idx']:02d}] {ss['company'][:30]:30} | URL: {ss['t_src']}")

    print(f"\nGeneric / Homepages as trigger: {len(gen_sources)}")
    for gs in gen_sources:
        print(f"  [{gs['idx']:02d}] {gs['company'][:30]:30} | URL: {gs['t_src']}")

    print("\nPerson Authority Distribution:")
    auth_counts = {}
    for d in findings:
        a = d["auth_class"]
        auth_counts[a] = auth_counts.get(a, 0) + 1
    for a, c in auth_counts.items():
        print(f"  {a:30}: {c}")

    non_stock = [d for d in findings if not d["is_stock"] and not d["is_gen"]]
    print(f"\nNon-stock, non-generic trigger sources: {len(non_stock)}")
    for ns in non_stock:
        print(f"[{ns['idx']:02d}] {ns['company']}")
        print(f"     Trigger: {ns['t_src']}")
        print(f"     Snippet: {ns['trigger_snippet'][:120]}")
        print(f"     Facility: {ns['facility']} | City: {ns['city']}")
        print(f"     Person: {ns['person_name']} ({ns['person_title']}) | Auth: {ns['auth_class']}")
        print(f"     Date: {ns['t_date_str']} | Stored recency: {ns['stored_recency']} | Calc recency: {ns['calc_recency']}")
        print(f"     Status: {ns['stored_status']}")
        print("-" * 70)


if __name__ == "__main__":
    analyze()


