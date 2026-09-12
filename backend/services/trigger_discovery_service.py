"""Salesoorja Plant-Specific Trigger Discovery Service.

Implements:
1. Explicit Trigger Taxonomy (PLANT_EXPANSION, NEW_PLANT, NEW_LINE, COMMISSIONING,
   METROLOGY_LAB_SETUP, QUALITY_LAB_SETUP, CAPACITY_EXPANSION, ORDER_RAMP_UP,
   QUALITY_HIRING, METROLOGY_HIRING, CALIBRATION_HIRING, INSTRUMENTATION_HIRING, etc.)
2. Source Tier Hierarchy (TIER_A: Press/BSE/Investor/Govt, TIER_B: Reputable news/industry,
   TIER_C: Job boards/LinkedIn, TIER_D: Generic marketing/SEO - cannot verify trigger)
3. Event Semantics Verification (rejects generic statements like 'leading manufacturer')
4. Date Extraction & Currentness Policy (0-180d = CURRENT, 181-365d = RECENT, >365d = STALE)
5. Facility Specificity Extraction (EXACT_FACILITY, INDUSTRIAL_AREA, CITY, STATE, COMPANY_ONLY)
6. Plant-Specific and Event-First Query Generators
"""
from __future__ import annotations

from datetime import datetime, timezone
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from services.evidence_provenance import extract_domain

logger = logging.getLogger(__name__)

# ── Trigger Taxonomy ──────────────────────────────────────────────────────────
TRIGGER_TYPES = {
    "PLANT_EXPANSION",
    "NEW_PLANT",
    "NEW_LINE",
    "COMMISSIONING",
    "NEW_EQUIPMENT",
    "NEW_LAB",
    "METROLOGY_LAB_SETUP",
    "QUALITY_LAB_SETUP",
    "CAPACITY_EXPANSION",
    "ORDER_RAMP_UP",
    "NEW_PRODUCT_MANUFACTURING",
    "CUSTOMER_OEM_APPROVAL",
    "EXPORT_RAMP",
    "RELOCATION",
    "PLANT_SHUTDOWN_MAINTENANCE",
    "AUDIT_CERTIFICATION",
    "QUALITY_HIRING",
    "METROLOGY_HIRING",
    "CALIBRATION_HIRING",
    "INSTRUMENTATION_HIRING",
    "MAINTENANCE_HIRING",
    "VALIDATION_QUALIFICATION",
    "FACILITY_MODERNIZATION",
}

HIRING_TRIGGER_TYPES = {
    "QUALITY_HIRING",
    "METROLOGY_HIRING",
    "CALIBRATION_HIRING",
    "INSTRUMENTATION_HIRING",
    "MAINTENANCE_HIRING",
}

# ── Source Tiers ──────────────────────────────────────────────────────────────
SOURCE_TIER_A = "TIER_A"  # Official IR/BSE/Govt/Press
SOURCE_TIER_B = "TIER_B"  # Reputable industry/business media
SOURCE_TIER_C = "TIER_C"  # LinkedIn posts, job boards, industry associations
SOURCE_TIER_D = "TIER_D"  # Generic home/about, directories, SEO articles (DISCOVERY ONLY)

TIER_A_DOMAINS = {
    "bseindia.com", "nseindia.com", "sebi.gov.in", "pib.gov.in", "dpiit.gov.in",
    "investindia.gov.in", "makeinindia.com", "midc.in", "tidco.com", "mca.gov.in"
}

TIER_B_DOMAINS = {
    "economictimes.indiatimes.com", "business-standard.com", "businesstoday.in",
    "livemint.com", "moneycontrol.com", "financialexpress.com", "thehindubusinessline.com",
    "thehindu.com", "reuters.com", "bloomberg.com", "autocarpro.in", "autocarindia.com",
    "evreporter.com", "pv-tech.org", "pharmabiz.com", "expresspharma.in", "electronicsforu.com",
    "cnbctv18.com", "ndtv.com", "freepressjournal.in", "businessworld.in", "fortuneindia.com",
    "timesofindia.indiatimes.com", "sahi.com", "crnasia.com"
}

TIER_C_DOMAINS = {
    "naukri.com", "indeed.com", "glassdoor.com", "shine.com", "monster.com",
    "timesjobs.com", "iimjobs.com", "hirist.com", "linkedin.com", "in.linkedin.com"
}


def classify_source_tier(url: str, domain: str = "", official_domain: str = "") -> str:
    """Classify the evidence tier of a discovered source.

    Enforces deterministic hard rejects: stock quote pages, company homepages,
    financial aggregators, directories, and SEO content are forced to SOURCE_TIER_D.
    """
    from services.source_verification_pipeline import (
        classify_source_class,
        TRIGGER_HARD_REJECT_CLASSES,
        SOURCE_CLASS_OFFICIAL_PRESS_RELEASE,
        SOURCE_CLASS_OFFICIAL_INVESTOR_RELEASE,
        SOURCE_CLASS_STOCK_EXCHANGE_FILING,
        SOURCE_CLASS_GOVERNMENT_SOURCE,
        SOURCE_CLASS_REPUTABLE_BUSINESS_NEWS,
        SOURCE_CLASS_REPUTABLE_INDUSTRY_NEWS,
        SOURCE_CLASS_COMPANY_CAREERS,
        SOURCE_CLASS_HIRING_PAGE,
    )

    clean_domain = (domain or extract_domain(url) or "").lower().replace("www.", "")
    clean_official = (official_domain or "").lower().replace("www.", "")
    url_lower = (url or "").lower()

    # 1. Deterministic source class check (hard reject if stock quote, directory, homepage, aggregator, SEO)
    src_class = classify_source_class(url, domain=clean_domain, official_domain=clean_official)
    if src_class in TRIGGER_HARD_REJECT_CLASSES:
        return SOURCE_TIER_D

    # 2. Official company press release / IR / filing
    if src_class in (SOURCE_CLASS_OFFICIAL_PRESS_RELEASE, SOURCE_CLASS_OFFICIAL_INVESTOR_RELEASE, SOURCE_CLASS_STOCK_EXCHANGE_FILING, SOURCE_CLASS_GOVERNMENT_SOURCE):
        return SOURCE_TIER_A

    if clean_official and (clean_domain == clean_official or clean_domain.endswith("." + clean_official)):
        if any(p in url_lower for p in ["press", "investor", "disclosure", "announcement", "news", "filing", "media"]):
            return SOURCE_TIER_A
        if any(p in url_lower for p in ["career", "careers", "jobs", "job", "opening"]):
            return SOURCE_TIER_A
        return SOURCE_TIER_D  # generic official homepage is Tier D (discovery only)

    # Global/corporate official press release paths
    if any(p in url_lower for p in ["/globalnews/", "/press-release", "/press_release", "/pressrelease", "/news-release"]):
        return SOURCE_TIER_A

    for d in TIER_A_DOMAINS:
        if clean_domain == d or clean_domain.endswith("." + d):
            return SOURCE_TIER_A

    if src_class in (SOURCE_CLASS_REPUTABLE_BUSINESS_NEWS, SOURCE_CLASS_REPUTABLE_INDUSTRY_NEWS):
        return SOURCE_TIER_B

    for d in TIER_B_DOMAINS:
        if clean_domain == d or clean_domain.endswith("." + d):
            return SOURCE_TIER_B

    if src_class in (SOURCE_CLASS_COMPANY_CAREERS, SOURCE_CLASS_HIRING_PAGE):
        return SOURCE_TIER_C

    for d in TIER_C_DOMAINS:
        if clean_domain == d or clean_domain.endswith("." + d):
            return SOURCE_TIER_C

    return SOURCE_TIER_D


# ── Event Semantics Verification ──────────────────────────────────────────────
EVENT_ACTION_PATTERNS = [
    # Capex / Plant / Line Events
    (r"\b(will invest|is investing|invests|invested|investment of|investment planned|investment amount|investing in|capex of|capex planned|approved capex)\b", "CAPACITY_EXPANSION", 1.0),
    (r"\b(commissioned|will commission|commissioning|inaugurated|opened|opening of|commencing operations|commence operations|commencement timing|starts production|started production)\b", "COMMISSIONING", 1.0),
    (r"\b(new plant|new manufacturing plant|new factory|new facility|construction of(?: [a-z]+)* plant|setting up plant|sets up plant|greenfield plant|second plant|third plant)\b", "NEW_PLANT", 1.0),
    (r"\b(new line|new manufacturing line|new assembly line|new production line|production line|new smt line|new press line)\b", "NEW_LINE", 1.0),
    (r"\b(expanding|expanding plant|plant expansion|expanding capacity|capacity expansion|capacity increased|facility expansion|expanding manufacturing)\b", "PLANT_EXPANSION", 1.0),
    (r"\b(new equipment|new machinery|production equipment|testing equipment)\b", "NEW_EQUIPMENT", 0.95),
    (r"\b(new lab|new laboratory|metrology lab|calibration lab|testing lab|quality laboratory|qc lab|qa lab)\b", "NEW_LAB", 1.0),
    (r"\b(commercial production|production commenced|commences production|ramp up|ramping up|production ramp)\b", "ORDER_RAMP_UP", 0.95),
    (r"\b(order awarded|bagged order|won contract|oem approval|oem nomination|customer approval)\b", "CUSTOMER_OEM_APPROVAL", 0.9),
    (r"\b(validation activity|validation qualification)\b", "VALIDATION_QUALIFICATION", 0.85),
    (r"\b(modernization|facility upgrade|retooling|equipment upgrade)\b", "FACILITY_MODERNIZATION", 0.9),
    # Hiring Events
    (r"\b(hiring|vacancy|opening|walk-in|recruiting|looking for)\b.*?\b(calibration|gauge|gage)\b", "CALIBRATION_HIRING", 0.85),
    (r"\b(hiring|vacancy|opening|walk-in|recruiting|looking for)\b.*?\b(metrology|measurement)\b", "METROLOGY_HIRING", 0.85),
    (r"\b(hiring|vacancy|opening|walk-in|recruiting|looking for)\b.*?\b(instrumentation|instrument)\b", "INSTRUMENTATION_HIRING", 0.8),
    (r"\b(hiring|vacancy|opening|walk-in|recruiting|looking for)\b.*?\b(plant quality|quality assurance|quality engineer|qa/qc)\b", "QUALITY_HIRING", 0.8),
    (r"\b(hiring|vacancy|opening|walk-in|recruiting|looking for)\b.*?\b(plant maintenance|equipment maintenance)\b", "MAINTENANCE_HIRING", 0.75),
]

GENERIC_FINANCIAL_PATTERNS = [
    r"\bshare price\b",
    r"\bstock price\b",
    r"\bmarket cap\b",
    r"\bmarket capitalisation\b",
    r"\bcompany overview\b",
    r"\bleading manufacturer\b",
    r"\bannual revenue\b",
    r"\bcompany profile\b",
    r"\bfinancial results?\b",
    r"\bquarterly (?:net )?profits?\b",
    r"\bq[1-4] results?\b",
    r"\bdividend\b",
    r"\bbonus issue\b",
    r"\bpromoter holding\b",
    r"\btarget price\b",
    r"\bbuy rating\b",
    r"\bpe ratio\b",
    r"\b52-week high\b",
    r"\btrading volume\b",
    r"\babout us\b",
    r"\bwelcome to\b",
]


def evaluate_event_semantics(text: str, title: str = "") -> Dict[str, Any]:
    """Deterministically evaluates whether text contains genuine industrial event semantics.

    Returns:
        dict with is_verified, trigger_type, description, score, matched_phrase, is_generic_financial
    """
    combined = f"{title} {text}".strip()
    text_lower = combined.lower()

    # Check for generic financial / non-event statements
    matched_generic = [p for p in GENERIC_FINANCIAL_PATTERNS if re.search(p, text_lower)]

    # Check for actionable event action patterns
    matched_event = None
    for pattern, trig_type, score in EVENT_ACTION_PATTERNS:
        match = re.search(pattern, text_lower)
        if match:
            matched_event = (trig_type, match.group(0), score)
            break

    # If generic financial text matched and NO event pattern matched: hard reject with 0.0 score
    if matched_generic and not matched_event:
        return {
            "is_verified": False,
            "trigger_type": "UNKNOWN",
            "description": f"Generic financial/market text without event semantics: '{matched_generic[0]}'",
            "score": 0.0,
            "matched_phrase": "",
            "is_generic_financial": True,
        }

    if matched_event:
        trig_type, phrase, score = matched_event
        # Penalty if generic financial phrasing dominates
        final_score = score if not matched_generic else max(0.5, score - 0.2)
        return {
            "is_verified": True,
            "trigger_type": trig_type,
            "description": f"Actionable event confirmed: '{phrase}'",
            "score": final_score,
            "matched_phrase": phrase,
            "is_generic_financial": bool(matched_generic),
        }

    return {
        "is_verified": False,
        "trigger_type": "UNKNOWN",
        "description": "No actionable event semantics found in source content",
        "score": 0.0,
        "matched_phrase": "",
        "is_generic_financial": bool(matched_generic),
    }


def event_semantics_score(text: str, title: str = "") -> float:
    """Returns the event semantics score (0.0 to 1.0)."""
    return evaluate_event_semantics(text, title=title)["score"]


def event_semantics_verified(snippet: str, title: str = "") -> Tuple[bool, str, str]:
    """Checks whether text contains real commercial/industrial EVENT semantics."""
    res = evaluate_event_semantics(snippet, title=title)
    return res["is_verified"], res["trigger_type"], res["description"]


# ── Content Fetch & Snippet False Positive Detection (Phase 4) ───────────────
def fetch_and_verify_source_content(
    url: str,
    search_title: str = "",
    search_snippet: str = "",
    timeout: int = 6,
) -> Dict[str, Any]:
    """Fetch public page content and verify whether event semantics actually exist in source text.

    If snippet appeared to suggest an expansion but fetched page does not contain event semantics:
    flags REJECT_SEARCH_SNIPPET_FALSE_POSITIVE.
    """
    import requests
    retrieved_at = datetime.now(timezone.utc).isoformat()
    clean_url = (url or "").strip()
    if not clean_url.startswith("http://") and not clean_url.startswith("https://"):
        return {
            "verified": False,
            "status": "INVALID_URL",
            "reason": "URL lacks http/https scheme",
            "search_title": search_title,
            "search_snippet": search_snippet,
            "source_title": "",
            "source_body_event_snippet": "",
            "source_url": clean_url,
            "retrieved_at": retrieved_at,
            "event_semantics_verified": False,
            "event_semantics_score": 0.0,
            "source_body_text": "",
        }

    try:
        resp = requests.get(
            clean_url,
            headers={
                "User-Agent": "Salesoorja-Research/1.0 (Commercial Trigger Verification)",
                "Accept": "text/html,application/xhtml+xml",
            },
            timeout=timeout,
            allow_redirects=True,
            stream=True,
        )
        if resp.status_code != 200:
            return {
                "verified": False,
                "status": f"HTTP_{resp.status_code}",
                "reason": f"HTTP fetch failed with status {resp.status_code}",
                "search_title": search_title,
                "search_snippet": search_snippet,
                "source_title": "",
                "source_body_event_snippet": "",
                "source_url": clean_url,
                "retrieved_at": retrieved_at,
                "event_semantics_verified": False,
                "event_semantics_score": 0.0,
                "source_body_text": "",
            }

        content_bytes = b""
        for chunk in resp.iter_content(chunk_size=10240):
            content_bytes += chunk
            if len(content_bytes) >= 51200:
                break

        html_text = content_bytes.decode("utf-8", errors="replace")
        title_m = re.search(r"<title[^>]*>([^<]+)</title>", html_text, re.IGNORECASE)
        source_title = title_m.group(1).strip() if title_m else search_title

        clean_html = re.sub(r"<(script|style|nav|footer|header)[^>]*>.*?</\1>", " ", html_text, flags=re.DOTALL | re.IGNORECASE)
        clean_text = re.sub(r"<[^>]+>", " ", clean_html)
        clean_text = re.sub(r"\s+", " ", clean_text).strip()

        sem_eval = evaluate_event_semantics(clean_text[:10000], title=source_title)
        snippet_eval = evaluate_event_semantics(search_snippet, title=search_title)

        if not sem_eval["is_verified"]:
            if snippet_eval["is_verified"]:
                status = "REJECT_SEARCH_SNIPPET_FALSE_POSITIVE"
                reason = "Search snippet suggested expansion, but fetched source content lacks event semantics"
            else:
                status = "REJECT_NO_EVENT_SEMANTICS"
                reason = sem_eval["description"]
            return {
                "verified": False,
                "status": status,
                "reason": reason,
                "search_title": search_title,
                "search_snippet": search_snippet,
                "source_title": source_title,
                "source_body_event_snippet": "",
                "source_url": clean_url,
                "retrieved_at": retrieved_at,
                "event_semantics_verified": False,
                "event_semantics_score": sem_eval["score"],
                "source_body_text": clean_text[:5000],
            }

        matched_phrase = sem_eval.get("matched_phrase", "")
        body_snippet = ""
        if matched_phrase:
            idx = clean_text.lower().find(matched_phrase.lower())
            if idx != -1:
                start = max(0, idx - 100)
                end = min(len(clean_text), idx + len(matched_phrase) + 150)
                body_snippet = clean_text[start:end].strip()

        return {
            "verified": True,
            "status": "SOURCE_CONTENT_VERIFIED",
            "reason": sem_eval["description"],
            "search_title": search_title,
            "search_snippet": search_snippet,
            "source_title": source_title,
            "source_body_event_snippet": body_snippet or clean_text[:250],
            "source_url": clean_url,
            "retrieved_at": retrieved_at,
            "event_semantics_verified": True,
            "event_semantics_score": sem_eval["score"],
            "trigger_type": sem_eval["trigger_type"],
            "source_body_text": clean_text[:5000],
        }

    except Exception as e:
        logger.warning(f"Error fetching source content from {clean_url}: {e}")
        return {
            "verified": False,
            "status": "FETCH_EXCEPTION",
            "reason": str(e),
            "search_title": search_title,
            "search_snippet": search_snippet,
            "source_title": "",
            "source_body_event_snippet": "",
            "source_url": clean_url,
            "retrieved_at": retrieved_at,
            "event_semantics_verified": False,
            "event_semantics_score": 0.0,
            "source_body_text": "",
        }


# ── Quote Grounding Verification (Phase 5) ───────────────────────────────────
def is_quote_grounded(quote: str, source_text: str) -> bool:
    """Verifies deterministically that Gemini's evidence quote exists in the source text."""
    if not quote or not source_text:
        return False
    q_norm = re.sub(r"\s+", " ", quote.strip().lower())
    s_norm = re.sub(r"\s+", " ", source_text.strip().lower())
    if q_norm in s_norm:
        return True
    q_clean = re.sub(r"^[“\"\'`]+|[”\"\'`]+$", "", q_norm).strip()
    if q_clean and q_clean in s_norm:
        return True
    q_alpha = re.sub(r"[^\w\s]", "", q_norm)
    s_alpha = re.sub(r"[^\w\s]", "", s_norm)
    if q_alpha and len(q_alpha) > 12 and q_alpha in s_alpha:
        return True
    return False


# ── Date & Currentness (Phase 6) ──────────────────────────────────────────────
DATE_PATTERNS = [
    # YYYY-MM-DD or YYYY/MM/DD
    r"\b(20[12]\d[-/]\d{2}[-/]\d{2})\b",
    # DD Month YYYY or Month DD, YYYY
    r"\b(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*,?\s+20[12]\d)\b",
    r"\b((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+20[12]\d)\b",
    # Month YYYY
    r"\b((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+20[12]\d)\b",
    # Relative: X days/weeks/months ago
    r"\b(\d+\s+(?:days?|weeks?|months?|hours?)\s+ago)\b",
    # Bare Year: 2018-2027
    r"\b(20[12]\d)\b",
]

FUTURE_PLAN_PATTERNS = [
    r"\b(?:planned|target|expected|scheduled|aims|slated|by fiscal|by)\s+(?:to be|for|by|in)?\s*(?:commissioned|completed|ready|operational|operationalize|202[7-9])\b",
    r"\bcommissioning\s+(?:planned|scheduled|by)\s+(?:in|by)?\s*202[7-9]\b",
    r"\bcompletion\s+by\s+202[7-9]\b",
]


def extract_event_date(
    text: str,
    title: str = "",
    now_dt: datetime | None = None,
    publication_date: str = "",
) -> Dict[str, Any]:
    """Extract event publication/action date and compute recency status deterministically.

    Disambiguates publication_date, event_date, and planned_completion_date.
    Future planned completion dates (e.g. 2028 commissioning) are NOT used as trigger_date,
    ensuring recency_days is NEVER negative.
    """
    from datetime import timedelta
    combined_text = f"{text} {title}".strip()
    now_dt = now_dt or datetime(2026, 9, 12, tzinfo=timezone.utc)
    now_dt_iso = now_dt.strftime("%Y-%m-%d")

    has_future_plan = any(re.search(pat, combined_text, re.IGNORECASE) for pat in FUTURE_PLAN_PATTERNS)

    # Collect all candidate dates found in combined text
    found_dates = []

    # Check relative date
    m_rel = re.search(r"(\d+)\s+(day|week|month|hour)s?\s+ago", combined_text, re.IGNORECASE)
    if m_rel:
        val = int(m_rel.group(1))
        unit = m_rel.group(2).lower()
        if unit == "hour":
            dt = now_dt - timedelta(hours=val)
        elif unit == "day":
            dt = now_dt - timedelta(days=val)
        elif unit == "week":
            dt = now_dt - timedelta(weeks=val)
        elif unit == "month":
            dt = now_dt - timedelta(days=val * 30)
        found_dates.append((dt, dt.strftime("%Y-%m-%d"), False))

    for pat in DATE_PATTERNS:
        for m in re.finditer(pat, combined_text, re.IGNORECASE):
            raw_str = m.group(1).strip()
            clean_str = raw_str.replace(",", "")
            for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d %b %Y", "%d %B %Y", "%B %d %Y", "%b %d %Y", "%B %Y", "%b %Y", "%Y"):
                try:
                    p_dt = datetime.strptime(clean_str, fmt).replace(tzinfo=timezone.utc)
                    found_dates.append((p_dt, clean_str, p_dt > now_dt))
                    break
                except (ValueError, Exception):
                    pass

    if not found_dates and publication_date:
        try:
            p_dt = datetime.strptime(publication_date.split("T")[0], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            found_dates.append((p_dt, publication_date, p_dt > now_dt))
        except Exception:
            pass

    if not found_dates:
        return {
            "event_date": "",
            "publication_date": publication_date,
            "planned_completion_date": "",
            "recency_days": 999,
            "calculated_recency_days": 999,
            "calculation_reference_date": now_dt_iso,
            "ongoing_status": "DATE_UNKNOWN",
            "recency_status": "DATE_UNKNOWN",
            "has_date": False,
            "is_future_planned_milestone": False,
            "date_parse_status": "DATE_NOT_FOUND",
        }

    # Separate future dates from current/past dates
    past_or_current = [d for d in found_dates if not d[2]]
    future_dates = [d for d in found_dates if d[2]]

    planned_completion_date = ""
    is_future_milestone = False
    if future_dates and (has_future_plan or past_or_current or publication_date):
        latest_future = max(future_dates, key=lambda x: x[0])
        planned_completion_date = latest_future[0].strftime("%Y-%m-%d")
        is_future_milestone = True

    # Determine event_date and recency
    if past_or_current:
        primary_dt, _, _ = max(past_or_current, key=lambda x: x[0])
        effective_event_date = primary_dt.strftime("%Y-%m-%d")
        recency_days = max(0, (now_dt - primary_dt).days)
    elif publication_date:
        try:
            pub_dt = datetime.strptime(publication_date.split("T")[0], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            effective_event_date = pub_dt.strftime("%Y-%m-%d")
            recency_days = max(0, (now_dt - pub_dt).days)
        except Exception:
            effective_event_date = now_dt_iso
            recency_days = 0
    elif is_future_milestone:
        effective_event_date = now_dt_iso
        recency_days = 0
    else:
        primary_dt, _, _ = future_dates[0]
        return {
            "event_date": primary_dt.strftime("%Y-%m-%d"),
            "publication_date": publication_date,
            "planned_completion_date": "",
            "recency_days": 999,
            "calculated_recency_days": 999,
            "calculation_reference_date": now_dt_iso,
            "ongoing_status": "STALE",
            "recency_status": "STALE",
            "has_date": True,
            "is_future_planned_milestone": False,
            "date_parse_status": "FUTURE_DATE_INCONSISTENT",
        }

    if recency_days <= 180:
        rec_status = "CURRENT"
    elif recency_days <= 365:
        rec_status = "RECENT"
    else:
        rec_status = "STALE"

    return {
        "event_date": effective_event_date,
        "publication_date": publication_date or effective_event_date,
        "planned_completion_date": planned_completion_date,
        "recency_days": recency_days,
        "calculated_recency_days": recency_days,
        "calculation_reference_date": now_dt_iso,
        "ongoing_status": rec_status,
        "recency_status": rec_status,
        "has_date": True,
        "is_future_planned_milestone": is_future_milestone,
        "date_parse_status": "FUTURE_PLANNED_MILESTONE" if is_future_milestone else "VALID",
    }


# ── Facility Link & Specificity in Trigger Discovery ─────────────────────────
INDUSTRIAL_AREA_KEYWORDS = [
    "midc", "gidc", "riico", "sipcot", "tidco", "kiadb", "hsiidc", "dic",
    "industrial area", "industrial estate", "industrial park", "industrial corridor",
    "sez", "export promotion park", "electronic city", "aerospace park",
    "phase i", "phase ii", "phase 1", "phase 2", "plot no", "gate no",
]


def extract_trigger_facility_link(
    text: str,
    known_city: str = "",
    known_industrial_area: str = "",
    known_plants: Optional[List[str]] = None,
    known_plant_name: str = "",
) -> Dict[str, Any]:
    """Extracts facility location details from trigger text and assigns specificity level:

    Specificity Levels:
    - EXACT_FACILITY: names a specific named unit / plant / plot
    - INDUSTRIAL_AREA: names a specific industrial estate/park/MIDC
    - CITY: names a specific city
    - STATE: names only a state
    - COMPANY_ONLY: no location mentioned
    """
    text_lower = text.lower()
    city_from_trigger = ""
    area_from_trigger = ""
    fac_name_from_trigger = ""
    specificity = "COMPANY_ONLY"

    plants_to_check = list(known_plants or [])
    if known_plant_name and known_plant_name not in plants_to_check:
        plants_to_check.append(known_plant_name)

    # 1. Exact facility / plant name matching
    if plants_to_check:
        for plant in plants_to_check:
            if plant.lower() in text_lower:
                fac_name_from_trigger = plant
                specificity = "EXACT_FACILITY"
                break

    # Plant naming regex e.g. "Chakan plant", "Sanand facility", "Unit 2", "Plant II"
    if not fac_name_from_trigger:
        plant_match = re.search(r"\b([A-Za-z]+(?:\s+[A-Za-z]+)?\s+(?:plant|facility|works|unit\s+\d+|unit\s+[IVX]+))\b", text_lower)
        if plant_match:
            candidate_plant = plant_match.group(1).strip()
            invalid_plant_terms = {
                "power", "solar", "steel", "chemical", "manufacturing", "crore",
                "mother", "new", "existing", "proposed", "mega", "upcoming",
                "second", "third", "first", "the", "a", "an", "its", "our",
                "this", "each", "every", "that", "their", "current", "assembly",
                "integrated", "dedicated", "advanced", "modern", "latest"
            }
            valid_words = [
                w for w in candidate_plant.split()
                if w.lower() not in invalid_plant_terms and w.lower() not in {"plant", "facility", "works"}
            ]
            if valid_words:
                fac_name_from_trigger = candidate_plant.title()
                if specificity != "EXACT_FACILITY":
                    specificity = "EXACT_FACILITY"

    # 2. Industrial area matching
    if known_industrial_area and known_industrial_area.lower() in text_lower:
        area_from_trigger = known_industrial_area
        if specificity != "EXACT_FACILITY":
            specificity = "INDUSTRIAL_AREA"
    else:
        for kw in INDUSTRIAL_AREA_KEYWORDS:
            if kw in text_lower:
                area_match = re.search(r"\b([A-Za-z]+(?:\s+[A-Za-z]+)?\s+" + re.escape(kw) + r")\b", text_lower)
                area_from_trigger = area_match.group(1).title() if area_match else kw.upper()
                if specificity != "EXACT_FACILITY":
                    specificity = "INDUSTRIAL_AREA"
                break

    # 3. City matching
    if known_city and known_city.lower() in text_lower:
        city_from_trigger = known_city
        if specificity not in ("EXACT_FACILITY", "INDUSTRIAL_AREA"):
            specificity = "CITY"
    else:
        # Common industrial cities
        common_cities = [
            "chakan", "pune", "sanand", "bawal", "coimbatore", "hosur", "noida",
            "gurugram", "gurgaon", "manesar", "aurangabad", "waluj", "chennai",
            "oragadam", "sriperumbudur", "bengaluru", "bangalore", "mysuru", "mysore",
            "jamshedpur", "vadodara", "savli", "makarpura", "nagpur", "butibori",
            "jabalpur", "kolhapur", "kagal", "dewas", "parwanoo", "navsari", "surat"
        ]
        for c in common_cities:
            if re.search(r"\b" + re.escape(c) + r"\b", text_lower):
                city_from_trigger = c.title()
                if specificity not in ("EXACT_FACILITY", "INDUSTRIAL_AREA"):
                    specificity = "CITY"
                break

    is_corroborated = specificity in ("EXACT_FACILITY", "INDUSTRIAL_AREA", "CITY")
    return {
        "facility_name_from_trigger": fac_name_from_trigger,
        "facility_city_from_trigger": city_from_trigger,
        "facility_area_from_trigger": area_from_trigger,
        "known_company_facility": known_plant_name or (known_plants[0] if known_plants else ""),
        "known_company_city": known_city,
        "is_trigger_facility_corroborated": is_corroborated,
        "trigger_facility_specificity": specificity,
    }


NEGATIVE_SEARCH_TERMS = "-stock -share-price -market-cap -screener -dividend"


def generate_plant_specific_queries(
    company_name: str,
    domain: str = "",
    known_city: str = "",
    known_area: str = "",
    official_domain: str = "",
    city: str = "",
    sector: str = "",
) -> List[str]:
    """Generate high-signal, plant-specific queries with recency, known plants, and negative terms to avoid stock quote pages."""
    clean_domain = (domain or official_domain).lower().replace("www.", "")
    target_city = known_city or city
    queries = []

    # 1. Capex / Commissioning / Expansion queries (with negative terms to filter stock quotes)
    if target_city:
        queries.append(f'"{company_name}" "{target_city}" expansion plant 2026 India {NEGATIVE_SEARCH_TERMS}')
        queries.append(f'"{company_name}" "{target_city}" commissioning 2026 {NEGATIVE_SEARCH_TERMS}')
        queries.append(f'"{company_name}" new line "{target_city}" 2026 {NEGATIVE_SEARCH_TERMS}')
        queries.append(f'"{company_name}" capex "{target_city}" 2025 OR 2026 {NEGATIVE_SEARCH_TERMS}')
    else:
        queries.append(f'"{company_name}" expansion plant 2026 India {NEGATIVE_SEARCH_TERMS}')
        queries.append(f'"{company_name}" commissioning plant 2026 {NEGATIVE_SEARCH_TERMS}')

    # 2. Quality / Metrology / Lab setup queries
    if target_city:
        queries.append(f'"{company_name}" "{target_city}" metrology lab')
        queries.append(f'"{company_name}" "{target_city}" quality hiring')
    else:
        queries.append(f'"{company_name}" quality lab setup 2025 OR 2026')
        queries.append(f'"{company_name}" metrology engineer hiring India')

    # 3. Official domain searches
    if clean_domain:
        queries.append(f'site:{clean_domain} expansion 2026')
        queries.append(f'site:{clean_domain} commissioning')
        queries.append(f'site:{clean_domain} capex')
        queries.append(f'site:{clean_domain} filetype:pdf expansion')

    return queries


# ── Event-First Discovery Queries (Phase 11) ──────────────────────────────────
EVENT_FIRST_SEARCH_QUERIES = [
    f"India new manufacturing plant September 2026 {NEGATIVE_SEARCH_TERMS}",
    f"India manufacturing expansion September 2026 capex {NEGATIVE_SEARCH_TERMS}",
    f"new automotive plant commissioning India 2026 {NEGATIVE_SEARCH_TERMS}",
    f"new electronics factory India SMT 2026 {NEGATIVE_SEARCH_TERMS}",
    f"new EV component plant India 2026 capex {NEGATIVE_SEARCH_TERMS}",
    f"new solar module line India 2026 commissioning {NEGATIVE_SEARCH_TERMS}",
    f"new battery gigafactory plant India 2026 {NEGATIVE_SEARCH_TERMS}",
    f"new aerospace manufacturing facility India 2026 {NEGATIVE_SEARCH_TERMS}",
    f"manufacturing plant commissioning India 2026 {NEGATIVE_SEARCH_TERMS}",
    "quality metrology hiring plant India 2026",
]


def generate_event_first_discovery_queries() -> List[str]:
    """Generates the Phase 11 event-first discovery query list."""
    return list(EVENT_FIRST_SEARCH_QUERIES)
