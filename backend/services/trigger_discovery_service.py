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
    "CAPACITY_EXPANSION",
    "PRODUCTION_RAMP",
    "MACHINERY_INSTALLATION",
    "ORDER_DRIVEN_RAMP",
    "QUALITY_VALIDATION",
    "LAB_SETUP",
    "CERTIFICATION_RAMP",
    "HIRING_RAMP",
    "NEW_EQUIPMENT",
    "NEW_LAB",
    "METROLOGY_LAB_SETUP",
    "QUALITY_LAB_SETUP",
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
    "STATIC_REFERENCE",
    "OTHER",
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
    # 1. New Plant
    (r"\b(new plant|new manufacturing plant|new factory|new facility|construction of(?: [a-z]+)* plant|greenfield plant|second plant|third plant|fourth plant|sets? up(?:\s+[a-zA-Z0-9\-\.]+){0,6}\s+(?:plant|facility|factory|unit|works)|to set up(?:\s+[a-zA-Z0-9\-\.]+){0,6}\s+(?:plant|facility|factory|unit|works)|to build(?:\s+[a-zA-Z0-9\-\.]+){0,6}\s+(?:plant|facility|factory|works))\b", "NEW_PLANT", 1.0),
    # 2. New Line
    (r"\b(new line|new manufacturing line|new assembly line|new production line|production line|new smt line|new press line|fourth unit|fourth line|new unit|additional unit|additional line|second production line|third production line)\b", "NEW_LINE", 1.0),
    # 3. Commissioning
    (r"\b(commissions?|commissioned|will commission|to commission|commissioning of (?:a |the |its |their )?(?:new )?(?:plant|facility|factory|unit|line|project|capacity|expansion|furnace|kiln|smelter|reactor)|inaugurate[ds]?|inauguration|inaugurating|opened|opening of|commencing operations|commence operations|commencement timing|starts? production|started production|commercial production)\b", "COMMISSIONING", 1.0),
    # 4. Capacity Expansion
    (r"\b(will invest|is investing|invests|invested|investment of|investment planned|investment amount|investing in|capex of|capex planned|approved capex|capex investment|capital expenditure of|announces? capex|announced capex|expanding (?:manufacturing )?capacity|capacity expansion|capacity increased|expands? capacity|capacity ramp-?up|doubl(?:ing|es?) capacity|expansion of manufacturing capacity)\b", "CAPACITY_EXPANSION", 1.0),
    (r"\b(expanding|expanding plant|plant expansion|facility expansion|expanding manufacturing)\b", "PLANT_EXPANSION", 1.0),
    # 5. Production Ramp
    (r"\b(production ramp|ramping up production|commercial operations commenced|ramp-?up of production|scaling up manufacturing|scaled up production|mass production started|commercial run started)\b", "PRODUCTION_RAMP", 0.95),
    # 6. Machinery Installation
    (r"\b(installed (?:new )?(?:machinery|equipment|press|furnace|cnc|cmm|robotics)|installing (?:new )?(?:machinery|equipment|press|furnace|cnc|cmm)|machinery installation|new equipment commissioned|new press line installed|tooling installation|new equipment|new machinery|production equipment|testing equipment|machining center)\b", "MACHINERY_INSTALLATION", 0.95),
    # 7. Order-Driven Ramp
    (r"\b(order awarded|bagged order|won contract|oem approval|oem nomination|customer approval|major contract win|supply agreement with oem|export order)\b", "ORDER_DRIVEN_RAMP", 0.9),
    # 8. Quality Validation
    (r"\b(validation activity|validation qualification|ppap approval|pilot run|pre-series production|prototype validation|sop approval)\b", "QUALITY_VALIDATION", 0.85),
    # 9. Lab Setup
    (r"\b(new lab|new laboratory|metrology lab|calibration lab|testing lab|quality laboratory|qc lab|qa lab|sets? up (?:a |the )?(?:metrology|calibration|testing|quality) lab)\b", "LAB_SETUP", 1.0),
    # 10. Certification Ramp
    (r"\b(iatf 16949|iso 17025|nabl accreditation|as9100|iso 9001 certification|audit preparation|cleanroom certification|nabl certified)\b", "CERTIFICATION_RAMP", 0.9),
    # 11. Hiring Events
    (r"\b(hiring|vacancy|opening|walk-in|recruiting|looking for)\b.*?\b(calibration|gauge|gage)\b", "CALIBRATION_HIRING", 0.85),
    (r"\b(hiring|vacancy|opening|walk-in|recruiting|looking for)\b.*?\b(metrology|measurement)\b", "METROLOGY_HIRING", 0.85),
    (r"\b(hiring|vacancy|opening|walk-in|recruiting|looking for)\b.*?\b(instrumentation|instrument)\b", "INSTRUMENTATION_HIRING", 0.8),
    (r"\b(hiring|vacancy|opening|walk-in|recruiting|looking for)\b.*?\b(plant quality|quality assurance|quality engineer|qa/qc)\b", "QUALITY_HIRING", 0.8),
    (r"\b(hiring|vacancy|opening|walk-in|recruiting|looking for)\b.*?\b(plant maintenance|equipment maintenance)\b", "MAINTENANCE_HIRING", 0.75),
    (r"\b(hiring|recruiting|vacancy|walk-in|opening)\b.*?\b(production engineer|plant operator|technician|machine operator)\b", "HIRING_RAMP", 0.75),
    # Modernization
    (r"\b(modernization|facility upgrade|retooling|equipment upgrade)\b", "FACILITY_MODERNIZATION", 0.9),
]

STATIC_REFERENCE_PATTERNS = [
    r"\babout us\b",
    r"\bwelcome to\b",
    r"\bcompany profile\b",
    r"\bcompany overview\b",
    r"\bcorporate profile\b",
    r"\bwho we are\b",
    r"\bour presence\b",
    r"\bour plants\b",
    r"\bour facilities\b",
    r"\bour locations\b",
    r"\bregistered office\b",
    r"\bcorporate office\b",
    r"\bhead office\b",
    r"\bcontact us\b",
    r"\breach us\b",
    r"\bcorporate governance\b",
    r"\bboard of directors\b",
    r"\bmanagement team\b",
    r"\bcsr initiatives?\b",
    r"\bcorporate social responsibility\b",
    r"\bdirectory listing\b",
    r"\bindiamart\b",
    r"\btradeindia\b",
    r"\bjustdial\b",
    r"\byellow pages\b",
    r"\bleading manufacturer of\b",
    r"\bestablished in 19\d\d\b",
    r"\bfounded in 19\d\d\b",
    r"\bsince 19\d\d\b",
    r"\bdecade-long experience\b",
    r"\bannual report 20(?:1\d|2[0-3])\b",
    r"\bcase study 20(?:1\d|2[0-3])\b",
    r"\baward(?:ed)? in 20(?:1\d|2[0-3])\b",
]

GENERIC_FINANCIAL_PATTERNS = [
    r"\bshare price\b",
    r"\bstock price\b",
    r"\bmarket cap\b",
    r"\bmarket capitalisation\b",
    r"\bannual revenue\b",
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
]


def evaluate_event_semantics(text: str, title: str = "") -> Dict[str, Any]:
    """Deterministically evaluates whether text contains genuine industrial event semantics.

    Returns:
        dict with is_verified, is_valid, is_valid_event, trigger_type, description, score, matched_phrase
    """
    combined = f"{title} {text}".strip()
    text_lower = combined.lower()

    # Check for actionable event action patterns first
    matched_event = None
    for pattern, trig_type, score in EVENT_ACTION_PATTERNS:
        match = re.search(pattern, text_lower)
        if match:
            matched_event = (trig_type, match.group(0), score)
            break

    # Check for static profile / directory references
    matched_static = [p for p in STATIC_REFERENCE_PATTERNS if re.search(p, text_lower)]
    matched_generic = [p for p in GENERIC_FINANCIAL_PATTERNS if re.search(p, text_lower)]

    # If static reference and NO active event pattern matched: hard reject with STATIC_REFERENCE
    if matched_static and not matched_event:
        return {
            "is_verified": False,
            "is_valid": False,
            "is_valid_event": False,
            "trigger_type": "STATIC_REFERENCE",
            "description": f"Static profile or directory reference without actionable event semantics: '{matched_static[0]}'",
            "score": 0.0,
            "matched_phrase": "",
            "is_generic_financial": bool(matched_generic),
            "is_static_reference": True,
        }

    # If generic financial text matched and NO event pattern matched: hard reject with 0.0 score
    if matched_generic and not matched_event:
        return {
            "is_verified": False,
            "is_valid": False,
            "is_valid_event": False,
            "trigger_type": "UNKNOWN",
            "description": f"Generic financial/market text without event semantics: '{matched_generic[0]}'",
            "score": 0.0,
            "matched_phrase": "",
            "is_generic_financial": True,
            "is_static_reference": False,
        }

    if matched_event:
        trig_type, phrase, score = matched_event
        # Penalty if generic financial or static phrasing is present
        penalty = 0.0
        if matched_generic:
            penalty += 0.2
        if matched_static:
            penalty += 0.1
        final_score = max(0.5, score - penalty) if penalty > 0 else score
        return {
            "is_verified": True,
            "is_valid": True,
            "is_valid_event": True,
            "trigger_type": trig_type,
            "description": f"Actionable event confirmed: '{phrase}'",
            "score": final_score,
            "matched_phrase": phrase,
            "is_generic_financial": bool(matched_generic),
            "is_static_reference": bool(matched_static),
        }

    return {
        "is_verified": False,
        "is_valid": False,
        "is_valid_event": False,
        "trigger_type": "UNKNOWN",
        "description": "No actionable event semantics found in source content",
        "score": 0.0,
        "matched_phrase": "",
        "is_generic_financial": bool(matched_generic),
        "is_static_reference": bool(matched_static),
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
    timeout: int = 10,
) -> Dict[str, Any]:
    """Fetch public page content and verify whether event semantics actually exist in source text.

    Supports:
    - Standard HTML pages with realistic browser headers
    - Targeted PDF extraction (BSE/NSE announcements, investor decks) via pypdf
    - Browser escalation hook for anti-bot blocked promising sources (Tier A/B)
    """
    import io
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

    browser_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf,*/*;q=0.8",
        "Accept-Language": "en-IN,en-US;q=0.9,en;q=0.8",
    }

    try:
        resp = requests.get(
            clean_url,
            headers=browser_headers,
            timeout=timeout,
            allow_redirects=True,
            stream=True,
        )

        # ── Browser Escalation Hook for Anti-Bot Blocks on Promising Sources ──
        if resp.status_code in (403, 429, 503):
            from services.source_verification_pipeline import (
                classify_source_class,
                TRIGGER_HARD_REJECT_CLASSES,
            )
            src_class = classify_source_class(clean_url, title=search_title, snippet=search_snippet)
            if src_class not in TRIGGER_HARD_REJECT_CLASSES:
                # Promising legitimate source (Tier A/B news, exchange filing, official domain)
                # Escalate with session & retry headers
                try:
                    s = requests.Session()
                    s.headers.update(browser_headers)
                    s.headers.update({"Sec-Ch-Ua": '"Chromium";v="128", "Not;A=Brand";v="24"', "Sec-Ch-Ua-Mobile": "?0", "Sec-Ch-Ua-Platform": '"Windows"'})
                    resp_retry = s.get(clean_url, timeout=timeout + 2, allow_redirects=True, stream=True)
                    if resp_retry.status_code == 200:
                        resp = resp_retry
                except Exception:
                    pass

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

        content_type = resp.headers.get("Content-Type", "").lower()
        is_pdf = "application/pdf" in content_type or clean_url.lower().split("?")[0].endswith(".pdf")

        if is_pdf:
            # ── PDF Handling via pypdf ──
            try:
                import pypdf
                pdf_bytes = b""
                for chunk in resp.iter_content(chunk_size=32768):
                    pdf_bytes += chunk
                    if len(pdf_bytes) >= 5 * 1024 * 1024:  # 5MB cap
                        break
                
                reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
                total_pages = len(reader.pages)
                extracted_pages_text = []
                trigger_keywords = ["capex", "expansion", "commissioning", "plant", "facility", "manufacturing", "crore", "line", "production"]
                
                for p_idx, page in enumerate(reader.pages):
                    try:
                        p_txt = page.extract_text() or ""
                        p_txt_lower = p_txt.lower()
                        if any(kw in p_txt_lower for kw in trigger_keywords):
                            extracted_pages_text.append(p_txt)
                        elif p_idx < 3:
                            extracted_pages_text.append(p_txt)
                        if len(" ".join(extracted_pages_text)) >= 20000:
                            break
                    except Exception:
                        continue
                
                clean_text = " ".join(extracted_pages_text)
                clean_text = re.sub(r"\s+", " ", clean_text).strip()
                source_title = search_title or (f"PDF Document ({total_pages} pages)")
            except Exception as pdf_err:
                logger.warning(f"PDF extraction error on {clean_url}: {pdf_err}")
                clean_text = ""
                source_title = search_title
        else:
            # ── HTML Handling ──
            content_bytes = b""
            for chunk in resp.iter_content(chunk_size=16384):
                content_bytes += chunk
                if len(content_bytes) >= 262144:  # 256KB buffer
                    break

            html_text = content_bytes.decode("utf-8", errors="replace")
            title_m = re.search(r"<title[^>]*>([^<]+)</title>", html_text, re.IGNORECASE)
            source_title = title_m.group(1).strip() if title_m else search_title

            clean_html = re.sub(r"<(script|style|nav|footer|header)[^>]*>.*?</\1>", " ", html_text, flags=re.DOTALL | re.IGNORECASE)
            clean_text = re.sub(r"<[^>]+>", " ", clean_html)
            clean_text = re.sub(r"\s+", " ", clean_text).strip()

        sem_eval = evaluate_event_semantics(clean_text[:12000], title=source_title)
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


def is_company_grounded_in_text(company_name: str, text: str, url: str = "") -> bool:
    """Verifies that the target company is actually mentioned in the source title, snippet, URL, or body."""
    if not company_name:
        return True

    clean = re.sub(r"\b(Limited|Ltd\.?|Pvt\.?|Private|LLP|Inc\.?|Corporation|Corp\.?)\b", "", company_name, flags=re.IGNORECASE).strip()
    clean_lower = clean.lower()

    tokens = [t for t in re.findall(r"\b[a-zA-Z]{4,}\b", clean_lower) if t not in ("india", "company", "group", "industries", "enterprises", "solutions")]

    combined = f"{text} {url}".lower()

    if clean_lower in combined:
        return True

    if tokens and any(t in combined for t in tokens):
        return True

    return False


# ── Date & Currentness (Phase 6) ──────────────────────────────────────────────
DATE_PATTERNS = [
    # YYYY-MM-DD or YYYY/MM/DD
    r"\b(20[12]\d[-/]\d{2}[-/]\d{2})\b",
    # DD Month YYYY or Month DD, YYYY (supporting ordinals and compact commas like 13th May 2026, Sep 24,2024)
    r"\b(\d{1,2}(?:st|nd|rd|th)?\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*,?\s*20[12]\d)\b",
    r"\b((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s*\d{1,2},?\s*20[12]\d)\b",
    # Month YYYY
    r"\b((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+20[12]\d)\b",
    # Relative: X days/weeks/months ago
    r"\b(\d+\s+(?:days?|weeks?|months?|hours?)\s+ago)\b",
]

FUTURE_PLAN_PATTERNS = [
    r"\b(?:planned|target|expected|scheduled|aims|slated|by fiscal|by)\s+(?:to be|for|by|in)?\s*(?:commissioned|completed|completion|ready|operational|operationalize|202[7-9])\b",
    r"\b(?:commissioning|completion)\s+(?:planned|scheduled|by|in)?\s*(?:in|by)?\s*202[7-9]\b",
    r"\bcompletion\s+(?:by|in)\s+202[7-9]\b",
]


DATE_ROLE_PRIORITY = {
    "START_OF_PRODUCTION_DATE": 100,
    "COMMISSIONING_DATE": 90,
    "EVENT_DATE": 80,
    "ANNOUNCEMENT_DATE": 70,
    "PUBLICATION_DATE": 60,
    "UPDATED_DATE": 40,
    "PLANNED_COMPLETION_DATE": 30,
    "FUTURE_TARGET_DATE": 20,
    "UNKNOWN": 10,
}


def classify_date_role(context: str, date_str: str = "", now_dt: datetime | None = None) -> str:
    """Classify the commercial and semantic role of an extracted date.

    Possible return values:
    - START_OF_PRODUCTION_DATE: Date commercial production or operations began.
    - COMMISSIONING_DATE: Date plant/press/line was commissioned or inaugurated.
    - EVENT_DATE: Exact date the event occurred.
    - ANNOUNCEMENT_DATE: Date company or board announced capex, expansion, or MoU.
    - PUBLICATION_DATE: Original publication/byline date of the source article.
    - UPDATED_DATE: Article revision/updated timestamp.
    - PLANNED_COMPLETION_DATE: Target future completion date for capex/project.
    - FUTURE_TARGET_DATE: Any date occurring after reference date without explicit plan context.
    - UNKNOWN: Role cannot be reliably determined.
    """
    now_dt = now_dt or datetime(2026, 9, 12, tzinfo=timezone.utc)
    clean_ctx = context.lower() if context else ""

    # Check if date itself is parsed and in the future
    is_future = False
    if date_str:
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d %b %Y", "%d %B %Y", "%B %d %Y", "%b %d %Y", "%B %Y", "%b %Y", "%Y"):
            try:
                p_dt = datetime.strptime(date_str.replace(",", "").strip(), fmt).replace(tzinfo=timezone.utc)
                if p_dt > now_dt:
                    is_future = True
                break
            except Exception:
                pass

    if is_future:
        if any(w in clean_ctx for w in ["planned", "expected", "scheduled", "target", "by", "aims to", "completion", "operational by"]):
            return "PLANNED_COMPLETION_DATE"
        return "FUTURE_TARGET_DATE"

    # Stock price / market capitalization dates are NOT commercial events
    if any(re.search(pat, clean_ctx) for pat in [
        r"(?:stock|trading|touched|52\s+week\s+high|shares?|pe\s+ratio|market\s+cap)",
    ]):
        if "high of" in clean_ctx or "touched" in clean_ctx or "trading at" in clean_ctx:
            return "UNKNOWN"

    # Start of production
    if any(re.search(pat, clean_ctx) for pat in [
        r"(?:commenced|commence|began|started|starts|commencing)\s+(?:commercial\s+)?production",
        r"became\s+(?:fully\s+)?operational",
        r"commenced\s+(?:commercial\s+)?operations",
        r"operational\s+on\b",
        r"commercial\s+production\s+from\b",
        r"trial\s+(?:runs?|production)\s+(?:started|commenced)",
    ]):
        return "START_OF_PRODUCTION_DATE"

    # Commissioning / Inauguration
    if any(re.search(pat, clean_ctx) for pat in [
        r"(?:commissioned|commissions|inaugurated|inaugurates|inauguration|dedicates?)\s+(?:on|in|the|its|a)\b",
        r"commissioning\s+(?:date|ceremony|of\s+(?:the\s+)?(?:new\s+)?(?:plant|facility|line|unit|press))",
        r"inauguration\s+(?:on|of|date)",
        r"inaugurates\s+(?:world-class|new|titanium|plant|facility)",
    ]):
        return "COMMISSIONING_DATE"

    # Check if date_str itself is part of a timestamp pattern like 2026-09-12 06:13:45 or updated/revision
    if (date_str and re.search(re.escape(date_str) + r"\s+\d{2}:\d{2}", clean_ctx)) or any(re.search(pat, clean_ctx) for pat in [
        r"(?:updated|last\s+updated|revised|modified)\s*[:\s]",
        r"\bupdate\s*:\s*",
    ]):
        return "UPDATED_DATE"

    # Announcement / Capex approval
    if any(re.search(pat, clean_ctx) for pat in [
        r"(?:announced|announces|board\s+approved?|approves?|unveiled?|signed\s+mou)\b",
        r"announced\s+plans\b",
        r"reports?\s+(?:strong\s+)?q\d\b",
        r"(?:awarded|bags?\s+order|received\s+(?:letter\s+of\s+award|contract|order))\b",
        r"board\s+approves\s+.*capex\b",
        r"announced\s+a\s+strategic\s+investment\b",
        r"mumbai,\s*\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)",
    ]):
        return "ANNOUNCEMENT_DATE"

    # Planned completion
    if any(re.search(pat, clean_ctx) for pat in [
        r"(?:planned|expected|scheduled|aims?\s+to\s+complete|target(?:ed)?)\s+(?:to\s+be\s+completed|commissioning|by|in|within)",
        r"within\s+\d+\s+months\b",
        r"target\s+(?:date|year|quarter)\b",
    ]):
        return "PLANNED_COMPLETION_DATE"

    # Publication / Byline
    if any(re.search(pat, clean_ctx) for pat in [
        r"(?:published|posted|dateline)\s*[:\s]",
        r"\b(?:ist|pdt|est|utc|gmt)\b",
        r"\bby\s+[A-Z][a-z]+",
        r"\bdesk\b",
        r"-->",
        r"\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:am|pm)?\b",
        r"mumbai\s*\(?.*?\)?\s*\|",
        r"new\s+delhi\s*\|",
    ]):
        return "PUBLICATION_DATE"

    # Event date
    if any(re.search(pat, clean_ctx) for pat in [
        r"\bon\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)?\s*,?\s*(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|\d{1,2})",
        r"\bvisited\b",
        r"\bheld\s+on\b",
        r"\bconducted\s+on\b",
        r"\bmeeting\s+held\s+on\b",
    ]):
        return "EVENT_DATE"

    return "UNKNOWN"


def extract_event_date(
    text: str,
    title: str = "",
    now_dt: datetime | None = None,
    publication_date: str = "",
    url: str = "",
) -> Dict[str, Any]:
    """Extract event publication/action date and compute recency status deterministically.

    Disambiguates publication_date, event_date, and planned_completion_date.
    Future planned completion dates (e.g. 2028 commissioning) are NOT used as trigger_date,
    ensuring recency_days is NEVER negative.
    Trunctates unrelated sidebar/footer/related sections to prevent leakage of today's date.
    Uses classify_date_role to prioritize START_OF_PRODUCTION_DATE, COMMISSIONING_DATE,
    EVENT_DATE, and ANNOUNCEMENT_DATE over generic UPDATED_DATE or website timestamps.
    """
    from datetime import timedelta

    now_dt = now_dt or datetime(2026, 9, 12, tzinfo=timezone.utc)
    now_dt_iso = now_dt.strftime("%Y-%m-%d")

    # 1. Truncate sidebar/footer sections that cause date contamination
    clean_text = text or ""
    m_split = re.search(
        r'\b(?:Related\s+Articles?|Related:|Discover\s+more\s+from|MOST\s+VISITED|Latest\s+Projects|Recent\s+News)\b',
        clean_text,
        re.IGNORECASE,
    )
    if m_split:
        clean_text = clean_text[:m_split.start()]

    combined_text = f"{clean_text} {title}".strip()
    has_future_plan = any(re.search(pat, combined_text, re.IGNORECASE) for pat in FUTURE_PLAN_PATTERNS)

    candidates = []

    # 2. Check URL for explicit publication date (/YYYY/MM/DD/ or /YYYY/MM/ or /YYYYMMDD/)
    if url:
        m_url = re.search(r'/(\d{4})/(\d{2})(?:/(\d{2}))?/', url)
        if m_url:
            y, m = int(m_url.group(1)), int(m_url.group(2))
            d = int(m_url.group(3)) if m_url.group(3) else 1
            u_dt = datetime(y, m, d, tzinfo=timezone.utc)
            if u_dt <= now_dt:
                candidates.append({
                    "dt": u_dt,
                    "dt_str": u_dt.strftime("%Y-%m-%d"),
                    "role": "PUBLICATION_DATE",
                    "role_priority": DATE_ROLE_PRIORITY["PUBLICATION_DATE"],
                    "source": "URL_PATH",
                    "pos": 0,
                })
        else:
            m_url2 = re.search(r'/(\d{4})(\d{2})(\d{2})/', url)
            if m_url2:
                u_dt2 = datetime(int(m_url2.group(1)), int(m_url2.group(2)), int(m_url2.group(3)), tzinfo=timezone.utc)
                if u_dt2 <= now_dt:
                    candidates.append({
                        "dt": u_dt2,
                        "dt_str": u_dt2.strftime("%Y-%m-%d"),
                        "role": "PUBLICATION_DATE",
                        "role_priority": DATE_ROLE_PRIORITY["PUBLICATION_DATE"],
                        "source": "URL_PATH",
                        "pos": 0,
                    })
            else:
                m_url3 = re.search(r'/(\d{4})-(\d{2})-(\d{2})(?:[-/.]|$)', url)
                if m_url3:
                    u_dt3 = datetime(int(m_url3.group(1)), int(m_url3.group(2)), int(m_url3.group(3)), tzinfo=timezone.utc)
                    if u_dt3 <= now_dt:
                        candidates.append({
                            "dt": u_dt3,
                            "dt_str": u_dt3.strftime("%Y-%m-%d"),
                            "role": "PUBLICATION_DATE",
                            "role_priority": DATE_ROLE_PRIORITY["PUBLICATION_DATE"],
                            "source": "URL_PATH",
                            "pos": 0,
                        })

    # 3. Check relative date
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
        candidates.append({
            "dt": dt,
            "dt_str": dt.strftime("%Y-%m-%d"),
            "role": "PUBLICATION_DATE",
            "role_priority": DATE_ROLE_PRIORITY["PUBLICATION_DATE"],
            "source": "RELATIVE_DATE",
            "pos": m_rel.start(),
        })

    # 4. Search for regex date patterns in clean text
    for pat in DATE_PATTERNS:
        for m in re.finditer(pat, clean_text, re.IGNORECASE):
            raw_str = m.group(1).strip()
            clean_str = re.sub(r'(\d+)(?:st|nd|rd|th)', r'\1', raw_str).replace(',', ' ')
            clean_str = re.sub(r'\s+', ' ', clean_str).strip()

            # Filter out masthead current-date artifacts if present on the same line
            line_start = clean_text.rfind('\n', 0, m.start())
            line_start = 0 if line_start == -1 else line_start + 1
            line_end = clean_text.find('\n', m.end())
            line_end = len(clean_text) if line_end == -1 else line_end
            line_text = clean_text[line_start:line_end].lower()

            if any(h in line_text for h in [
                "latest news", "advertise with us", "hot press news", "sparsh week",
                "copyright", "©", "(c)", "all rights reserved", "terms of use", "privacy policy", "disclaimer"
            ]):
                continue

            start_ctx = max(0, m.start() - 60)
            end_ctx = min(len(clean_text), m.end() + 60)
            ctx = clean_text[start_ctx:end_ctx]

            if any(h in ctx.lower() for h in ["copyright 20", "© 20", "all rights reserved 20", "terms of use 20"]):
                continue

            for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d %b %Y", "%d %B %Y", "%B %d %Y", "%b %d %Y", "%B %Y", "%b %Y", "%Y"):
                try:
                    p_dt = datetime.strptime(clean_str, fmt).replace(tzinfo=timezone.utc)
                    role = classify_date_role(ctx, clean_str, now_dt=now_dt)
                    candidates.append({
                        "dt": p_dt,
                        "dt_str": p_dt.strftime("%Y-%m-%d"),
                        "role": role,
                        "role_priority": DATE_ROLE_PRIORITY.get(role, 10),
                        "source": "BODY_TEXT",
                        "pos": m.start(),
                    })
                    break
                except (ValueError, Exception):
                    pass

    # 5. Add publication_date parameter if provided and no candidates yet
    if not candidates and publication_date:
        try:
            p_dt = datetime.strptime(publication_date.split("T")[0], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            candidates.append({
                "dt": p_dt,
                "dt_str": publication_date.split("T")[0],
                "role": "PUBLICATION_DATE",
                "role_priority": DATE_ROLE_PRIORITY["PUBLICATION_DATE"],
                "source": "METADATA",
                "pos": 0,
            })
        except Exception:
            pass

    if not candidates:
        return {
            "event_date": "UNKNOWN_DATE",
            "trigger_date": "UNKNOWN_DATE",
            "publication_date": publication_date,
            "planned_completion_date": "",
            "recency_days": 999,
            "calculated_recency_days": 999,
            "calculation_reference_date": now_dt_iso,
            "ongoing_status": "DATE_UNKNOWN",
            "recency_status": "DATE_UNKNOWN",
            "recency_tier": "DATE_UNKNOWN",
            "has_date": False,
            "date_role": "UNKNOWN",
            "date_source": "NONE",
            "is_future_planned_milestone": False,
            "date_parse_status": "DATE_NOT_FOUND",
            "days_ago": 999,
            "date_str": "UNKNOWN_DATE",
        }

    # Separate future / planned completion dates
    valid_past = [c for c in candidates if c["dt"] <= now_dt and c["role"] not in ("PLANNED_COMPLETION_DATE", "FUTURE_TARGET_DATE")]
    future_or_planned = [c for c in candidates if c["dt"] > now_dt or c["role"] in ("PLANNED_COMPLETION_DATE", "FUTURE_TARGET_DATE")]

    planned_completion_date = ""
    is_future_milestone = False
    if future_or_planned:
        latest_future = max(future_or_planned, key=lambda x: x["dt"])
        planned_completion_date = latest_future["dt_str"]
        is_future_milestone = True
    elif has_future_plan:
        m_fut = re.search(r"\b(?:completion|commissioning|ready|operational|completed|scheduled\s+for(?:\s+completion)?)\s+(?:in|by|for)?\s*(202[7-9])\b", combined_text, re.IGNORECASE)
        if m_fut:
            planned_completion_date = f"{m_fut.group(1)}-12-31"
            is_future_milestone = True

    if not valid_past:
        if is_future_milestone:
            return {
                "event_date": planned_completion_date,
                "trigger_date": planned_completion_date,
                "publication_date": publication_date,
                "planned_completion_date": planned_completion_date,
                "recency_days": 999,
                "calculated_recency_days": 999,
                "calculation_reference_date": now_dt_iso,
                "ongoing_status": "STALE",
                "recency_status": "STALE",
                "recency_tier": "STALE",
                "has_date": True,
                "date_role": "PLANNED_COMPLETION_DATE",
                "date_source": "BODY_TEXT",
                "is_future_planned_milestone": True,
                "date_parse_status": "FUTURE_PLANNED_MILESTONE",
                "days_ago": 999,
                "date_str": planned_completion_date,
            }
        return {
            "event_date": "UNKNOWN_DATE",
            "trigger_date": "UNKNOWN_DATE",
            "publication_date": publication_date,
            "planned_completion_date": "",
            "recency_days": 999,
            "calculated_recency_days": 999,
            "calculation_reference_date": now_dt_iso,
            "ongoing_status": "DATE_UNKNOWN",
            "recency_status": "DATE_UNKNOWN",
            "recency_tier": "DATE_UNKNOWN",
            "has_date": False,
            "date_role": "UNKNOWN",
            "date_source": "NONE",
            "is_future_planned_milestone": False,
            "date_parse_status": "DATE_NOT_FOUND",
            "days_ago": 999,
            "date_str": "UNKNOWN_DATE",
        }

    # Sort valid_past by:
    # 1. role priority (descending)
    # 2. position in text (earlier in text usually byline/dateline/lead paragraph)
    valid_past.sort(key=lambda x: (-x["role_priority"], x["pos"]))
    best = valid_past[0]

    effective_event_date = best["dt_str"]
    recency_days = max(0, (now_dt - best["dt"]).days)

    if recency_days <= 180:
        rec_status = "CURRENT"
    elif recency_days <= 365:
        rec_status = "RECENT"
    else:
        rec_status = "STALE"

    return {
        "event_date": effective_event_date,
        "trigger_date": effective_event_date,
        "publication_date": publication_date or effective_event_date,
        "planned_completion_date": planned_completion_date,
        "recency_days": recency_days,
        "calculated_recency_days": recency_days,
        "calculation_reference_date": now_dt_iso,
        "ongoing_status": rec_status,
        "recency_status": rec_status,
        "recency_tier": rec_status,
        "has_date": True,
        "date_role": best["role"],
        "date_source": best["source"],
        "is_future_planned_milestone": is_future_milestone,
        "date_parse_status": "VALID",
        "days_ago": recency_days,
        "date_str": effective_event_date,
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
                "integrated", "dedicated", "advanced", "modern", "latest",
                "without", "with", "for", "from", "at", "in", "on", "by", "of",
                "physical", "no", "not", "any", "all", "entire", "general",
                "news", "article", "mention", "mentioned", "commercial",
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


def should_escalate_to_browser(url: str, status_code: int) -> bool:
    """Evaluates whether an HTTP request failure warrants browser escalation.

    Only Tier A or B domains with anti-bot/rate-limiting response codes (403, 429, 503)
    are escalated. Hard-rejected domains (social media, SEO, directories) are NEVER escalated.
    """
    if status_code not in (403, 429, 503):
        return False
    tier = classify_source_tier(url)
    return tier in (SOURCE_TIER_A, SOURCE_TIER_B)


def extract_pdf_capex_text(pdf_bytes: bytes, max_pages: int = 25) -> str:
    """Extracts targeted text from a PDF stream focusing on capex, plant, expansion, or commissioning sections."""
    try:
        import io
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        total_pages = len(reader.pages)
        pages_to_check = min(total_pages, max_pages)

        extracted_sections = []
        keywords = ("capex", "capital expenditure", "plant", "commissioning", "expansion", "facility", "capacity", "project", "inaugurat")

        for i in range(pages_to_check):
            page_text = reader.pages[i].extract_text() or ""
            text_lower = page_text.lower()
            if any(kw in text_lower for kw in keywords):
                extracted_sections.append(page_text)
                if len(extracted_sections) >= 5:
                    break
        return "\n\n".join(extracted_sections)
    except Exception as exc:
        logger.warning(f"Failed to parse PDF bytes: {exc}")
        return ""


# ── Phase 7: Trigger + Facility Binding ───────────────────────────────────────
TRIGGER_FACILITY_DIRECT = "TRIGGER_FACILITY_DIRECT"
TRIGGER_FACILITY_STRONG = "TRIGGER_FACILITY_STRONG"
TRIGGER_FACILITY_AMBIGUOUS = "TRIGGER_FACILITY_AMBIGUOUS"
TRIGGER_FACILITY_NONE = "TRIGGER_FACILITY_NONE"


def bind_trigger_to_facility(
    trigger_text: str,
    target_facility: str = "",
    target_city: str = "",
    target_state: str = "",
) -> Dict[str, Any]:
    """Deterministically evaluates whether commercial trigger applies to target facility.

    Rules:
    - TRIGGER_FACILITY_DIRECT: Trigger explicitly names the target facility / unit
      or target city + specific plant phrase (e.g. 'Sanand plant', 'Sanand facility').
    - TRIGGER_FACILITY_STRONG: Trigger names target city/industrial hub where company
      is expanding, without conflicting locations.
    - TRIGGER_FACILITY_AMBIGUOUS: Trigger names a conflicting manufacturing hub
      (e.g., Pune/Dharwad when target is Sanand/Waghodia), or only corporate India.
    - TRIGGER_FACILITY_NONE: Neither target facility nor target city is mentioned.
    """
    from services.person_intelligence_service import INDIAN_CITIES_TO_STATE

    text_lower = (trigger_text or "").lower()
    city_lower = (target_city or "").strip().lower()
    fac_lower = (target_facility or "").strip().lower()
    state_lower = (target_state or "").strip().lower()

    if not text_lower:
        return {
            "linkage": TRIGGER_FACILITY_NONE,
            "is_bound": False,
            "confidence": "NONE",
            "reason": "Empty trigger text provided",
            "matched_location": "",
            "conflicting_locations": [],
        }

    # Detect any industrial cities mentioned in the trigger text
    cities_in_text = []
    for c_name in sorted(INDIAN_CITIES_TO_STATE.keys(), key=len, reverse=True):
        if re.search(r"\b" + re.escape(c_name) + r"\b", text_lower):
            cities_in_text.append(c_name.title())

    conflicting_cities = [c for c in cities_in_text if city_lower and c.lower() != city_lower]

    # 1. Direct match: Exact facility name mentioned
    if fac_lower and (fac_lower in text_lower or any(
        part in text_lower for part in fac_lower.split() if len(part) > 4 and part not in ("plant", "facility", "works", "unit", "limited")
    )):
        if city_lower and city_lower in text_lower:
            return {
                "linkage": TRIGGER_FACILITY_DIRECT,
                "is_bound": True,
                "confidence": "HIGH",
                "reason": f"Target facility '{target_facility}' and city '{target_city}' directly confirmed in trigger text",
                "matched_location": f"{target_facility} ({target_city})",
                "conflicting_locations": conflicting_cities,
            }
        elif not conflicting_cities:
            return {
                "linkage": TRIGGER_FACILITY_DIRECT,
                "is_bound": True,
                "confidence": "HIGH",
                "reason": f"Target facility '{target_facility}' directly confirmed in trigger text",
                "matched_location": target_facility,
                "conflicting_locations": [],
            }

    # 2. Check target city presence
    if city_lower and re.search(r"\b" + re.escape(city_lower) + r"\b", text_lower):
        has_plant_word = any(pw in text_lower for pw in ["plant", "facility", "unit", "works", "factory", "site", "line"])
        if has_plant_word and not conflicting_cities:
            return {
                "linkage": TRIGGER_FACILITY_DIRECT,
                "is_bound": True,
                "confidence": "HIGH",
                "reason": f"Target city '{target_city}' directly associated with manufacturing facility in trigger",
                "matched_location": target_city,
                "conflicting_locations": [],
            }
        elif not conflicting_cities:
            return {
                "linkage": TRIGGER_FACILITY_WEAK,
                "is_bound": False,
                "confidence": "LOW",
                "reason": f"Target city '{target_city}' present in text, but contains zero manufacturing facility evidence",
                "matched_location": target_city,
                "conflicting_locations": [],
            }
        else:
            return {
                "linkage": TRIGGER_FACILITY_WEAK,
                "is_bound": False,
                "confidence": "LOW",
                "reason": f"Target city '{target_city}' mentioned without facility evidence alongside other locations ({', '.join(conflicting_cities)})",
                "matched_location": target_city,
                "conflicting_locations": conflicting_cities,
            }

    # 3. If target city is NOT present, but conflicting manufacturing hubs are present:
    if conflicting_cities:
        return {
            "linkage": TRIGGER_FACILITY_AMBIGUOUS,
            "is_bound": False,
            "confidence": "LOW",
            "reason": f"Trigger event is located at conflicting manufacturing hub ({', '.join(conflicting_cities)}), not target city '{target_city}'",
            "matched_location": conflicting_cities[0],
            "conflicting_locations": conflicting_cities,
        }

    # 4. State only match
    if state_lower and re.search(r"\b" + re.escape(state_lower) + r"\b", text_lower):
        return {
            "linkage": TRIGGER_FACILITY_AMBIGUOUS,
            "is_bound": False,
            "confidence": "LOW",
            "reason": f"Trigger mentions state '{target_state}' only, without proving target city '{target_city}'",
            "matched_location": target_state,
            "conflicting_locations": [],
        }

    return {
        "linkage": TRIGGER_FACILITY_NONE,
        "is_bound": False,
        "confidence": "NONE",
        "reason": f"Neither target facility '{target_facility}' nor target city '{target_city}' mentioned in trigger",
        "matched_location": "",
        "conflicting_locations": [],
    }


# ── Phase 8: Calibration Opportunity Truth ───────────────────────────────────
CALIBRATION_SOURCE_SUPPORTED = "SOURCE_SUPPORTED"
CALIBRATION_REASONABLE_INFERENCE = "REASONABLE_INFERENCE"
CALIBRATION_UNKNOWN = "UNKNOWN"

SOURCE_CALIBRATION_TERMS = [
    (r"\bcalibration\b", "calibration"),
    (r"\bcalibrat\w*\b", "calibration"),
    (r"\bmetrology\b", "metrology"),
    (r"\bcmm\b", "cmm"),
    (r"\bcoordinate measuring\b", "coordinate measuring machine"),
    (r"\bgaug(?:e|es|ing)\b", "gauges"),
    (r"\bmicrometer(?:s)?\b", "micrometers"),
    (r"\bvernier(?:s)?\b", "verniers"),
    (r"\bprofile projector(?:s)?\b", "profile projectors"),
    (r"\bpressure gaug(?:e|es)\b", "pressure gauges"),
    (r"\bpressure transmitter(?:s)?\b", "pressure transmitters"),
    (r"\btemperature sensor(?:s)?\b", "temperature sensors"),
    (r"\bthermocouple(?:s)?\b", "thermocouples"),
    (r"\brtd(?:s)?\b", "rtd sensors"),
    (r"\bmultimeter(?:s)?\b", "multimeters"),
    (r"\boscilloscope(?:s)?\b", "oscilloscopes"),
    (r"\btorque wrench(?:es)?\b", "torque wrench"),
    (r"\btesting laborator(?:y|ies)\b", "testing laboratory"),
    (r"\bquality lab(?:s)?\b", "quality lab"),
    (r"\bnabl\b", "nabl accredited calibration"),
    (r"\bstandard room\b", "standard room"),
    (r"\bcleanroom\b", "cleanroom"),
    (r"\btensile tester(?:s)?\b", "tensile testers"),
    (r"\bhardness tester(?:s)?\b", "hardness testers"),
]

CALIBRATION_SECTOR_TEMPLATES = {
    "Automotive": "Likely calibration opportunities for an automotive manufacturing ramp include dimensional metrology (CMM, bore gauges, micrometers), torque wrenches, pressure/vacuum sensors, and temperature controllers; exact instrument scope requires confirmation.",
    "Auto Components": "Likely calibration opportunities for an automotive component manufacturing ramp include dimensional metrology (CMM, profile projectors, gauges), torque tools, force gauges, and hardness testers; exact instrument scope requires confirmation.",
    "Aerospace": "Likely calibration opportunities for an aerospace manufacturing ramp include high-precision dimensional metrology, torque, pressure/vacuum, and electrical test equipment; exact instrument scope requires confirmation.",
    "Defence": "Likely calibration opportunities for a defence manufacturing facility include dimensional inspection, pressure transducers, temperature sensors, and electrical test instruments; exact instrument scope requires confirmation.",
    "Electronics": "Likely calibration opportunities for an electronics/SMT manufacturing ramp include electrical test equipment (oscilloscopes, digital multimeters, LCR meters), ESD monitoring, thermal profiling, and dimensional inspection; exact instrument scope requires confirmation.",
    "Electrical": "Likely calibration opportunities for an electrical equipment manufacturing ramp include high-voltage test sets, power meters, insulation testers, multimeters, and temperature calibration; exact instrument scope requires confirmation.",
    "Pharma": "Likely calibration opportunities for a pharmaceutical manufacturing ramp include temperature sensors (RTD, thermocouples), pressure gauges, analytical balances, humidity transmitters, and autoclave validation; exact instrument scope requires confirmation.",
    "Life Sciences": "Likely calibration opportunities for a life sciences manufacturing facility include temperature/humidity monitoring, analytical balances, pipettes, pressure sensors, and bio-reactor instrumentation; exact instrument scope requires confirmation.",
    "Steel": "Likely calibration opportunities for a steel/metals manufacturing ramp include pyrometry/thermal sensors, pressure gauges, dimensional metrology, and mechanical testing machines; exact instrument scope requires confirmation.",
    "Metals": "Likely calibration opportunities for a metals fabrication ramp include dimensional metrology, hardness testers, temperature controllers, and pressure instrumentation; exact instrument scope requires confirmation.",
    "Heavy Engineering": "Likely calibration opportunities for a heavy engineering manufacturing ramp include large-scale dimensional metrology, laser tracking, torque multipliers, pressure gauges, and welding gauge calibration; exact instrument scope requires confirmation.",
    "Chemicals": "Likely calibration opportunities for a specialty chemicals plant include flow meters, pressure transmitters, RTDs, pH meters, and gas monitors; exact instrument scope requires confirmation.",
    "Power & Energy": "Likely calibration opportunities for an energy equipment manufacturing facility include pressure transmitters, temperature sensors, power analyzers, and electrical calibrators; exact instrument scope requires confirmation.",
}


def classify_calibration_opportunity(
    trigger_snippet: str = "",
    sector: str = "",
    page_text: str = "",
) -> Dict[str, Any]:
    """Deterministically separates source-supported equipment mentions from sector-inferred opportunities.

    Never invents exact equipment models, ranges, or quantities.
    """
    combined = f"{trigger_snippet} {page_text}".lower()

    # 1. Check for explicit source-supported metrology / calibration equipment mentions
    found_terms = []
    for pat, label in SOURCE_CALIBRATION_TERMS:
        if re.search(pat, combined):
            found_terms.append(label)

    if found_terms:
        unique_terms = sorted(list(set(found_terms)))
        return {
            "calibration_evidence_type": CALIBRATION_SOURCE_SUPPORTED,
            "calibration_description": f"Source explicitly mentions instrumentation/metrology requirements: {', '.join(unique_terms)}.",
            "supported_instruments": unique_terms,
            "sector": sector,
            "is_source_supported": True,
        }

    # 2. Sector-inferred opportunity with explicit confirmation disclaimer
    sec_clean = (sector or "").strip()
    template = CALIBRATION_SECTOR_TEMPLATES.get(
        sec_clean,
        f"Likely calibration opportunities for a {sec_clean or 'manufacturing'} ramp include dimensional metrology, torque, pressure/vacuum, and electrical test instruments; exact instrument scope requires confirmation."
    )

    return {
        "calibration_evidence_type": CALIBRATION_REASONABLE_INFERENCE if sec_clean else CALIBRATION_UNKNOWN,
        "calibration_description": template,
        "supported_instruments": [],
        "sector": sec_clean,
        "is_source_supported": False,
    }


# ── Phase 9: Composite Lead Qualification & Decompressed Scoring ──────────────
def compute_lead_qualification_score(
    trigger_info: Dict[str, Any],
    person_info: Optional[Dict[str, Any]],
    facility_binding_info: Optional[Dict[str, Any]] = None,
    sector: str = "",
) -> Tuple[float, str, str, List[str]]:
    """Computes canonical production outbound qualification score and priority band.

    Canonical bands:
    - 95–100: P1 / HOT
    - 90–94:  P2 / STRONG
    - 85–89:  P3 / QUALIFIED
    - < 85:   HOLD / RESEARCH

    Returns:
        (lead_score, priority_band, status, hold_reasons)
    """
    hold_reasons: List[str] = []

    # 1. Validate Trigger
    is_trig_valid = bool(trigger_info.get("is_valid") or trigger_info.get("is_verified"))
    trig_type = str(trigger_info.get("trigger_type") or "").upper()
    rec_tier = str(trigger_info.get("recency_tier") or trigger_info.get("recency_status") or "").upper()
    has_ongoing = bool(trigger_info.get("has_ongoing") or trigger_info.get("ongoing_activity_evidence"))

    if not is_trig_valid or trig_type in ("STATIC_REFERENCE", "UNKNOWN"):
        return 40.0, "HOLD", "HOLD_TRIGGER_WEAK", ["Trigger lacks valid commercial event semantics (STATIC_REFERENCE or UNKNOWN)."]

    if rec_tier in ("DATE_UNKNOWN", "UNKNOWN_DATE"):
        return 45.0, "HOLD", "HOLD_TRIGGER_STALE", ["Trigger lacks verified publication/event date (DATE_UNKNOWN)."]

    if rec_tier == "STALE" and not has_ongoing:
        return 48.0, "HOLD", "HOLD_TRIGGER_STALE", ["Trigger is >365 days old without verified ongoing activity evidence."]

    # 2. Validate Facility Linkage
    fb_link = (
        (facility_binding_info or {}).get("linkage")
        or trigger_info.get("facility_relationship")
        or "TRIGGER_FACILITY_NONE"
    )
    if fb_link in ("TRIGGER_FACILITY_AMBIGUOUS", "TRIGGER_FACILITY_NONE", "AMBIGUOUS"):
        reason = (facility_binding_info or {}).get("reason") or "Trigger not bound to target facility."
        return 55.0, "HOLD", "HOLD_FACILITY_AMBIGUOUS", [f"Trigger-facility link ambiguous: {reason}"]

    # 3. Validate Person
    if not person_info:
        return 50.0, "HOLD", "HOLD_PERSON_UNCERTAIN", ["No human decision-maker candidate discovered."]

    p_name = str(person_info.get("name") or "")
    emp_status = str(person_info.get("current_employment") or "UNKNOWN").upper()
    fac_rel = str(person_info.get("facility_relationship") or "UNKNOWN").upper()
    p_score = float(person_info.get("person_score", 0.0) or 0.0)
    p_conf = str(person_info.get("person_confidence") or "LOW").upper()
    auth_class = str(person_info.get("authority_class") or "").upper()

    # Contradicted employment hard block
    if emp_status == "CONTRADICTED":
        return 45.0, "HOLD", "HOLD_PERSON_CONTRADICTED", [f"Candidate '{p_name}' current employment contradicted (past tenure only)."]

    # Facility mismatch hard block
    if fac_rel in ("OTHER_FACILITY_OWNER", "FACILITY_CONTRADICTED"):
        return 55.0, "HOLD", "HOLD_FACILITY_MISMATCH", [f"Candidate '{p_name}' is located at a different facility ({fac_rel})."]

    # Current employment must be strictly VERIFIED for contact enrichment (PROBABLE / UNKNOWN must HOLD)
    if emp_status != "VERIFIED":
        return 65.0, "HOLD", "HOLD_PERSON_CURRENT_EMPLOYMENT", [
            f"Candidate '{p_name}' current employment status is {emp_status}. Verified current employment is strictly mandatory for contact enrichment."
        ]

    # Junior IC hard block
    if auth_class == "JUNIOR_IC" or p_conf == "LOW" or p_score < 65.0:
        return 65.0, "HOLD", "HOLD_AUTHORITY_INSUFFICIENT", [f"Candidate '{p_name}' lacks plant decision authority or score < 65."]


    # Person-Facility Relationship Gate:
    # Plant-specific requires verified plant ownership (FACILITY_OWNER or FACILITY_FUNCTION_OWNER).
    # Group-level requires verified group ownership (GROUP_FUNCTION_OWNER) and is assigned GROUP_LEVEL_CONTACT.
    # FUNCTIONALLY_RELEVANT or COMPANY_ONLY lacks verified facility link -> must be held as HOLD_PERSON_UNCERTAIN.
    is_plant_owner = fac_rel in ("FACILITY_OWNER", "FACILITY_FUNCTION_OWNER")
    is_group_owner = fac_rel == "GROUP_FUNCTION_OWNER" or auth_class == "GROUP_FUNCTION_OWNER"

    if not is_plant_owner and not is_group_owner:
        return 70.0, "HOLD", "HOLD_PERSON_UNCERTAIN", [
            f"Candidate '{p_name}' lacks verified facility relationship ({fac_rel}). Plant-specific qualification requires direct plant quality/operations leadership."
        ]

    # Target facility must have a known location or name for on-site plant qualification
    target_city = (
        (facility_binding_info or {}).get("target_city")
        or trigger_info.get("discovered_city")
        or trigger_info.get("city")
        or ""
    )
    target_fac = (
        (facility_binding_info or {}).get("target_facility")
        or trigger_info.get("discovered_facility")
        or trigger_info.get("facility")
        or trigger_info.get("facility_relationship")
        or ""
    )
    if not target_city and not target_fac and is_plant_owner:
        return 60.0, "HOLD", "HOLD_FACILITY_AMBIGUOUS", [
            "Target manufacturing facility geographical location (city/state) is unverified."
        ]

    # 4. Canonical Decompressed Scoring
    # Trigger Component (0 to 50, base 40.0):
    trig_comp = 40.0
    if fb_link in ("TRIGGER_FACILITY_DIRECT", "DIRECT"):
        trig_comp += 5.0
    elif fb_link in ("TRIGGER_FACILITY_STRONG", "STRONG"):
        trig_comp += 2.0

    if rec_tier == "CURRENT":
        trig_comp += 3.0
    elif rec_tier == "RECENT" and has_ongoing:
        trig_comp += 1.0

    src_tier = str(trigger_info.get("source_tier") or "").upper()
    if src_tier == "TIER_A":
        trig_comp += 2.0
    elif src_tier == "TIER_B":
        trig_comp += 1.0

    trig_comp = min(trig_comp, 50.0)

    # Person Component (0 to 50, base 40.0):
    person_comp = 40.0
    if auth_class in ("DIRECT_CALIBRATION_OWNER", "METROLOGY_OWNER"):
        person_comp += 4.0
    elif auth_class == "STRONG_PLANT_QUALITY_OWNER":
        person_comp += 3.0
    elif auth_class == "FACILITY_OWNER":
        person_comp += 2.0
    elif auth_class == "GROUP_FUNCTION_OWNER":
        person_comp += 1.0

    if emp_status == "VERIFIED":
        person_comp += 3.0
    elif emp_status == "PROBABLE":
        person_comp += 1.0

    if fac_rel == "FACILITY_OWNER":
        person_comp += 2.0
    elif fac_rel == "GROUP_FUNCTION_OWNER":
        person_comp += 1.0

    if p_conf == "HIGH":
        person_comp += 1.0

    person_comp = min(person_comp, 50.0)

    total_score = round(trig_comp + person_comp, 1)

    # Priority Band Assignment
    if is_group_owner:
        # Group-level qualification
        if total_score >= 85.0:
            priority_band = "P2" if total_score >= 90.0 else "P3"
            status = "GROUP_LEVEL_CONTACT"
        else:
            priority_band = "HOLD"
            status = "HOLD_RESEARCH"
            hold_reasons.append(f"Group lead composite score ({total_score}) is below production qualification threshold (85.0).")
    else:
        # Plant-specific qualification
        if total_score >= 95.0:
            priority_band = "P1"
            status = "READY_FOR_CONTACT_ENRICHMENT"
        elif total_score >= 90.0:
            priority_band = "P2"
            status = "READY_FOR_CONTACT_ENRICHMENT"
        elif total_score >= 85.0:
            priority_band = "P3"
            status = "READY_FOR_CONTACT_ENRICHMENT"
        else:
            priority_band = "HOLD"
            status = "HOLD_RESEARCH"
            hold_reasons.append(f"Composite score ({total_score}) is below production qualification threshold (85.0).")

    return total_score, priority_band, status, hold_reasons

