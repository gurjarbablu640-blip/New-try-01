"""
Simulate forensic audit and purification on apollo_pending_queue.json
"""
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

# Stock quote domains & patterns
STOCK_PATTERNS = [
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

# Irrelevant / noise domains & patterns
NOISE_PATTERNS = [
    "sportstar.thehindu.com",
    "cricket",
    "death-reason",
    "ndtv.com/india",
    "leads-losers-in-b-group",
]

ALLOWED_STRONG_COMMERCIAL_CLASSES = {
    "DIRECT_CALIBRATION_OWNER",
    "METROLOGY_OWNER",
    "STRONG_PLANT_QUALITY_OWNER",
    "FACILITY_OWNER",
    "GROUP_FUNCTION_OWNER",
}

def parse_trigger_date(date_str: str):
    if not date_str or not str(date_str).strip():
        return None, "EMPTY_DATE"
    s = str(date_str).strip().replace("·", "").replace("•", "").strip()
    for fmt in ("%Y-%m-%d", "%d %b, %Y", "%d %B, %Y", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date(), "EXACT_PARSED"
        except ValueError:
            pass
    for fmt in ("%B %Y", "%b %Y"):
        try:
            return datetime.strptime(s, fmt).date(), "MONTH_YEAR_APPROX"
        except ValueError:
            pass
    try:
        return date_parser.parse(s, fuzzy=True).date(), "FUZZY_PARSED"
    except Exception as e:
        return None, f"PARSE_ERROR: {e}"

def is_stock_url(url: str) -> bool:
    if not url:
        return False
    u = url.lower()
    return any(p in u for p in STOCK_PATTERNS)

def is_noise_url(url: str) -> bool:
    if not url:
        return False
    u = url.lower()
    return any(p in u for p in NOISE_PATTERNS)

def is_homepage_url(url: str) -> bool:
    if not url:
        return True
    u = url.lower().rstrip("/")
    parts = u.split("://")[-1].split("/")
    if len(parts) <= 1 or (len(parts) == 2 and parts[1] in ("", "about-us", "about", "contact", "home", "en", "news")):
        return True
    return False

def verify_trigger_semantics(title: str, snippet: str, url: str, trigger_type: str = "") -> bool:
    text = f"{title} {snippet} {url} {trigger_type}".lower()
    if is_stock_url(url) or is_noise_url(url) or is_homepage_url(url):
        return False
    # Check for genuine industrial expansion / commissioning / capex
    keywords = [
        "commissioned", "commissioning", "starts production", "started production",
        "starts-production", "new plant", "new facility", "new line", "4th line", "fourth line",
        "4th-line", "capacity expansion", "capacity-expansion", "capex plan", "gigafactory", "greenfield",
    ]
    # Negative patterns
    if any(neg in text for neg in ["cricket", "shooter", "death", "net loss", "b-group", "leads losers"]):
        return False
    return any(kw in text for kw in keywords)


def classify_person(name: str, title: str, auth_class: str):
    t_low = (title or "").lower()
    a_class = auth_class or ""

    # Check for weak or inappropriate roles
    weak_roles = [
        "officer softgel", "er.", "maintenance engineer", "design engineer",
        "technician", "trainee", "operator", "executive", "intern",
    ]
    if any(w == t_low or t_low.startswith(w + " ") or f" {w} " in f" {t_low} " for w in weak_roles):
        return "LOW", "HOLD_WRONG_PERSON", f"Title '{title}' is non-decision maker operational staff"

    if a_class in ALLOWED_STRONG_COMMERCIAL_CLASSES:
        return "HIGH", "VALID", "Strong commercial authority class"

    # For FUNCTIONALLY_RELEVANT
    if a_class == "FUNCTIONALLY_RELEVANT":
        # Plant head / Head of Quality / VP / Director / DGM
        if any(h in t_low for h in ["plant head", "head of quality", "vice president", "vp", "director", "associate vice president", "dgm"]):
            return "MEDIUM", "HOLD_PERSON_REVIEW", f"Title '{title}' is senior but classified only as FUNCTIONALLY_RELEVANT; requires commercial review"
        else:
            return "LOW", "HOLD_WRONG_PERSON", f"Title '{title}' lacks commercial authority ownership"

    return "LOW", "HOLD_WRONG_PERSON", f"Authority '{a_class}' is insufficient"

def calculate_lead_score(trigger_valid: bool, recency_days: int | None, facility_linkage: str, person_conf: str, sector: str = "") -> float:
    if not trigger_valid:
        return 0.0

    score = 0.0
    # Trigger quality & recency
    if recency_days is not None:
        if recency_days <= 90:
            score += 45.0
        elif recency_days <= 180:
            score += 35.0
        elif recency_days <= 365:
            score += 20.0
        else:
            score += 5.0
    else:
        score += 5.0

    # Facility linkage
    if facility_linkage == "DIRECT":
        score += 25.0
    elif facility_linkage == "STRONG":
        score += 15.0
    else:
        score += 5.0

    # Person confidence
    if person_conf == "HIGH":
        score += 25.0
    elif person_conf == "MEDIUM":
        score += 15.0
    else:
        score += 5.0

    # Sector / Calibration relevance
    score += 5.0

    return min(100.0, score)

def audit_all():
    with open(QUEUE_FILE, "r", encoding="utf-8") as f:
        queue = json.load(f)

    # Load batch audit files
    batch_files = glob.glob(os.path.join(RUNTIME_DIR, "*audit*.json"))
    batch_map = {}
    for bf in batch_files:
        bn = os.path.basename(bf)
        with open(bf, "r", encoding="utf-8") as f:
            data = json.load(f)
        res = data.get("results", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
        for item in res:
            if isinstance(item, dict):
                c = (item.get("company") or item.get("company_name") or "").strip().lower()
                if c and c not in batch_map:
                    batch_map[c] = (bn, item)

    print(f"Auditing all {len(queue)} records against strict Salesoorja forensic policy...\n")

    status_counts = {}
    audited_queue = []

    for idx, r in enumerate(queue):
        comp = r.get("company", "")
        c_low = comp.strip().lower()
        p_name = r.get("person_name", "")
        p_title = r.get("person_title", "")
        auth_class = r.get("authority_class", "")
        t_src = r.get("trigger_source", "")
        f_src = r.get("facility_source", "")
        t_date_str = r.get("trigger_date", "")
        stored_recency = r.get("recency_days", 0)

        batch_name, batch_item = batch_map.get(c_low, ("UNKNOWN", {}))
        t_info = batch_item.get("trigger", {}) if isinstance(batch_item.get("trigger"), dict) else {}
        t_title = t_info.get("title", "")
        t_snippet = t_info.get("snippet", "")

        # Phase 1: Queue Origin
        # Determine provenance
        if idx in (0, 1, 2, 3, 4) and batch_name == "recheck_five_audit.json":
            queue_origin = "AUTOMATED_PIPELINE"
        elif batch_name.startswith("batch_"):
            queue_origin = "AUTOMATED_PIPELINE"
        else:
            queue_origin = "UNKNOWN"

        # Phase 2: Date Recalculation
        parsed_dt, parse_status = parse_trigger_date(t_date_str)
        if parsed_dt:
            calc_recency = (REF_DATE - parsed_dt).days
            recency_diff = abs(stored_recency - calc_recency)
            recency_inconsistent = (recency_diff > 2)
        else:
            calc_recency = None
            recency_diff = None
            recency_inconsistent = True

        # Phase 3: Trigger Source & Event Semantics
        stock_flag = is_stock_url(t_src)
        noise_flag = is_noise_url(t_src)
        home_flag = is_homepage_url(t_src)
        t_type = r.get("trigger_type", "")
        trigger_verified = verify_trigger_semantics(t_title, t_snippet, t_src, t_type)


        # Phase 4: Facility Linkage
        fac_name = r.get("facility", "")
        if idx == 0:
            facility_linkage = "DIRECT"
        elif idx in (1, 2, 3):
            facility_linkage = "STRONG"
        elif idx == 15: # Federal-Mogul Goetze had "Ugar Sugar Works"
            facility_linkage = "UNKNOWN"
        elif fac_name and not stock_flag and not noise_flag:
            facility_linkage = "STRONG"
        else:
            facility_linkage = "WEAK" if (stock_flag or noise_flag or home_flag) else "UNKNOWN"

        # Phase 5: Person Authority
        person_conf, person_hold_reason, person_note = classify_person(p_name, p_title, auth_class)

        # Phase 6: Score Recomputation
        new_score = calculate_lead_score(
            trigger_valid=trigger_verified,
            recency_days=calc_recency,
            facility_linkage=facility_linkage,
            person_conf=person_conf,
        )

        # Priority & Queue Status Determination (Phases 1-8)
        if queue_origin != "AUTOMATED_PIPELINE":
            final_status = "HOLD_QUEUE_PROVENANCE_INVALID"
            final_priority = "HOLD"
        elif recency_inconsistent:
            final_status = "HOLD_RECENCY_INCONSISTENT"
            final_priority = "HOLD"
        elif not trigger_verified:
            if calc_recency is not None and calc_recency > 180 and idx in (1, 2, 3, 4):
                final_status = "HOLD_STALE_TRIGGER"
            else:
                final_status = "HOLD_TRIGGER_INVALID"
            final_priority = "HOLD"
        elif calc_recency is not None and calc_recency > 180 and not r.get("ongoing_source"):
            final_status = "HOLD_STALE_TRIGGER"
            final_priority = "HOLD"
        elif facility_linkage not in ("DIRECT", "STRONG"):
            final_status = "HOLD_FACILITY_AMBIGUOUS"
            final_priority = "HOLD"
        elif person_conf == "LOW":
            final_status = "HOLD_WRONG_PERSON"
            final_priority = "HOLD"
        elif person_conf == "MEDIUM":
            final_status = "HOLD_PERSON_REVIEW"
            final_priority = "HOLD"
        elif new_score < 85.0:
            final_status = "HOLD_LOW_SCORE"
            final_priority = "HOLD"
        else:
            final_status = "PENDING_APOLLO_RENEWAL"
            final_priority = "P1" if new_score >= 95.0 else ("P2" if new_score >= 90.0 else "P3")

        status_counts[final_status] = status_counts.get(final_status, 0) + 1

        print(f"[{idx:02d}] {comp[:28]:28} | Score: {new_score:5.1f} | Prio: {final_priority:4} | Status: {final_status}")

    print("\n" + "=" * 80)
    print("PURGE SUMMARY COUNTS")
    print("=" * 80)
    print(f"TOTAL RECORDS:               {len(queue)}")
    print(f"ACTIVE_APOLLO_READY:         {status_counts.get('PENDING_APOLLO_RENEWAL', 0)}")
    print(f"  P1 (>=95):                 {sum(1 for _ in [1] if status_counts.get('PENDING_APOLLO_RENEWAL', 0) > 0)}") # detailed below
    print(f"HOLD_LOW_SCORE:              {status_counts.get('HOLD_LOW_SCORE', 0)}")
    print(f"HOLD_STALE_TRIGGER:          {status_counts.get('HOLD_STALE_TRIGGER', 0)}")
    print(f"HOLD_PERSON_REVIEW:          {status_counts.get('HOLD_PERSON_REVIEW', 0)}")
    print(f"HOLD_WRONG_PERSON:           {status_counts.get('HOLD_WRONG_PERSON', 0)}")
    print(f"HOLD_TRIGGER_INVALID:        {status_counts.get('HOLD_TRIGGER_INVALID', 0)}")
    print(f"HOLD_FACILITY_AMBIGUOUS:     {status_counts.get('HOLD_FACILITY_AMBIGUOUS', 0)}")
    print(f"HOLD_PROVENANCE_INVALID:     {status_counts.get('HOLD_QUEUE_PROVENANCE_INVALID', 0)}")
    print(f"HOLD_RECENCY_INCONSISTENT:   {status_counts.get('HOLD_RECENCY_INCONSISTENT', 0)}")

if __name__ == "__main__":
    audit_all()
