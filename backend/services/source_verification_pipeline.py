"""Source Verification and Citation Normalization Pipeline.

Enforces Salesoorja Evidence Invariants:
1. LLM-discovered sources are DISCOVERY EVIDENCE only.
2. An LLM-generated claim can NEVER be promoted directly to:
   - TRIGGER_VERIFIED
   - FACILITY_VERIFIED
   - PERSON_VERIFIED
   - CONTACT_VERIFIED
3. Internal model markers (e.g. 'turn0search0') are normalized and NEVER persisted as source IDs.
4. Genuine citations must provide a valid source_url, source_domain, snippet, and raw_text_hash.
5. If a cited URL cannot be fetched or corroborated independently, the claim remains UNVERIFIED.

Source Role Classification (replaces global domain blacklist):
The SAME domain may be used for different evidence purposes depending on URL path and context.
Each verify_discovered_source() call checks whether the source's role is acceptable for
the specific claim_type, rather than rejecting domains globally.

Source Roles:
- PRIMARY_TRIGGER_SOURCE      : Official IR, press release, gov't project announcement
- CORROBORATING_TRIGGER_SOURCE: Reputable business/industry news
- HIRING_SIGNAL_SOURCE        : Job boards with calibration/quality/metrology role keywords
- PERSON_EMPLOYMENT_SOURCE    : Individual LinkedIn profiles, professional biographies
- FACILITY_SOURCE             : Company address pages, Maps
- COMPANY_EXISTENCE_SOURCE    : Screener, Tofler, MCA, Crunchbase, company directories
- DISCOVERY_ONLY              : Company LinkedIn pages, Twitter, Facebook (not trigger evidence)
- IRRELEVANT                  : Games, entertainment, app stores (hard-rejected all types)
- UNTRUSTED                   : Wikipedia, generic dictionaries (hard-rejected all types)
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import logging
import re
from typing import Any, Dict, List, Optional
import urllib.parse

import requests

from services.evidence_provenance import (
    EvidenceProvenanceRecord,
    compute_text_hash,
    extract_domain,
)

logger = logging.getLogger(__name__)

# Pattern to identify and strip internal search model tokens like 【turn0search0】
INTERNAL_MARKER_PATTERN = re.compile(r"【turn\d+search\d+】|\[turn\d+search\d+\]|turn\d+search\d+", re.IGNORECASE)

# Pattern for markdown links: [Title](URL)
MARKDOWN_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\((https?://[^\s\)]+)\)")

# Pattern for standalone URLs
RAW_URL_PATTERN = re.compile(r"https?://[^\s\)\]>\"']+")

# Pattern to extract dates
DATE_PATTERN = re.compile(
    r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+202[4-7]\b"
    r"|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},?\s+202[4-7]\b"
    r"|\b202[4-7]-\d{2}-\d{2}\b"
    r"|\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+202[4-7]\b"
    r"|\b202[4-7]\b",
    re.IGNORECASE,
)


def strip_internal_model_markers(text: str) -> str:
    """Removes model-internal markers (e.g., 【turn0search0】) from text."""
    if not text:
        return ""
    cleaned = INTERNAL_MARKER_PATTERN.sub("", text)
    cleaned = re.sub(r"\s+([.,;:!?])", r"\1", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def normalize_citations(raw_text: str) -> List[Dict[str, Any]]:
    """Extracts and normalizes citations from search model text output."""
    if not raw_text:
        return []
    citations: List[Dict[str, Any]] = []
    seen_urls: set[str] = set()
    for match in MARKDOWN_LINK_PATTERN.finditer(raw_text):
        title = strip_internal_model_markers(match.group(1)).strip()
        url = match.group(2).rstrip(".,;)>]").strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        start_idx = max(0, match.start() - 150)
        end_idx = min(len(raw_text), match.end() + 150)
        snippet = strip_internal_model_markers(raw_text[start_idx:end_idx])
        date_match = DATE_PATTERN.search(snippet)
        pub_date = date_match.group(0) if date_match else ""
        domain = extract_domain(url)
        text_hash = compute_text_hash(snippet)
        citations.append({
            "source_url": url, "source_domain": domain,
            "source_title": title or domain, "publication_date": pub_date,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "snippet": snippet, "raw_text_hash": text_hash, "source_type": "WEB_CITATION",
        })
    for match in RAW_URL_PATTERN.finditer(raw_text):
        url = match.group(0).rstrip(".,;)>]").strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        start_idx = max(0, match.start() - 150)
        end_idx = min(len(raw_text), match.end() + 150)
        snippet = strip_internal_model_markers(raw_text[start_idx:end_idx])
        date_match = DATE_PATTERN.search(snippet)
        pub_date = date_match.group(0) if date_match else ""
        domain = extract_domain(url)
        text_hash = compute_text_hash(snippet)
        citations.append({
            "source_url": url, "source_domain": domain, "source_title": domain,
            "publication_date": pub_date,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "snippet": snippet, "raw_text_hash": text_hash, "source_type": "RAW_URL",
        })
    return citations


# ── Source Role Constants ─────────────────────────────────────────────────────
SOURCE_ROLE_PRIMARY_TRIGGER = "PRIMARY_TRIGGER_SOURCE"
SOURCE_ROLE_CORROBORATING_TRIGGER = "CORROBORATING_TRIGGER_SOURCE"
SOURCE_ROLE_HIRING_SIGNAL = "HIRING_SIGNAL_SOURCE"
SOURCE_ROLE_PERSON_EMPLOYMENT = "PERSON_EMPLOYMENT_SOURCE"
SOURCE_ROLE_FACILITY = "FACILITY_SOURCE"
SOURCE_ROLE_COMPANY_EXISTENCE = "COMPANY_EXISTENCE_SOURCE"
SOURCE_ROLE_DISCOVERY_ONLY = "DISCOVERY_ONLY"
SOURCE_ROLE_IRRELEVANT = "IRRELEVANT"
SOURCE_ROLE_UNTRUSTED = "UNTRUSTED"

# ── 16 Deterministic Source Classes (Phase 2) ─────────────────────────────────
SOURCE_CLASS_OFFICIAL_PRESS_RELEASE = "OFFICIAL_PRESS_RELEASE"
SOURCE_CLASS_OFFICIAL_INVESTOR_RELEASE = "OFFICIAL_INVESTOR_RELEASE"
SOURCE_CLASS_STOCK_EXCHANGE_FILING = "STOCK_EXCHANGE_FILING"
SOURCE_CLASS_GOVERNMENT_SOURCE = "GOVERNMENT_SOURCE"
SOURCE_CLASS_REPUTABLE_BUSINESS_NEWS = "REPUTABLE_BUSINESS_NEWS"
SOURCE_CLASS_REPUTABLE_INDUSTRY_NEWS = "REPUTABLE_INDUSTRY_NEWS"
SOURCE_CLASS_COMPANY_CAREERS = "COMPANY_CAREERS"
SOURCE_CLASS_HIRING_PAGE = "HIRING_PAGE"
SOURCE_CLASS_PROFESSIONAL_PROFILE = "PROFESSIONAL_PROFILE"
SOURCE_CLASS_STOCK_QUOTE = "STOCK_QUOTE"
SOURCE_CLASS_FINANCIAL_AGGREGATOR = "FINANCIAL_AGGREGATOR"
SOURCE_CLASS_COMPANY_HOMEPAGE = "COMPANY_HOMEPAGE"
SOURCE_CLASS_DIRECTORY = "DIRECTORY"
SOURCE_CLASS_SEO_CONTENT = "SEO_CONTENT"
SOURCE_CLASS_SOCIAL_POST = "SOCIAL_POST"
SOURCE_CLASS_UNKNOWN = "UNKNOWN"

# Hard reject classes for trigger evidence (cannot prove plant capex/expansion)
TRIGGER_HARD_REJECT_CLASSES: set[str] = {
    SOURCE_CLASS_STOCK_QUOTE,
    SOURCE_CLASS_FINANCIAL_AGGREGATOR,
    SOURCE_CLASS_COMPANY_HOMEPAGE,
    SOURCE_CLASS_DIRECTORY,
    SOURCE_CLASS_SEO_CONTENT,
}

# Source quality weights for ranking (Phase 8)
SOURCE_QUALITY_WEIGHTS: dict[str, float] = {
    SOURCE_CLASS_OFFICIAL_PRESS_RELEASE: 1.0,
    SOURCE_CLASS_OFFICIAL_INVESTOR_RELEASE: 1.0,
    SOURCE_CLASS_STOCK_EXCHANGE_FILING: 1.0,
    SOURCE_CLASS_GOVERNMENT_SOURCE: 1.0,
    SOURCE_CLASS_REPUTABLE_BUSINESS_NEWS: 0.85,
    SOURCE_CLASS_REPUTABLE_INDUSTRY_NEWS: 0.85,
    SOURCE_CLASS_COMPANY_CAREERS: 0.6,
    SOURCE_CLASS_HIRING_PAGE: 0.6,
    SOURCE_CLASS_PROFESSIONAL_PROFILE: 0.5,
    SOURCE_CLASS_SOCIAL_POST: 0.2,
    SOURCE_CLASS_UNKNOWN: 0.3,
    SOURCE_CLASS_STOCK_QUOTE: 0.0,
    SOURCE_CLASS_FINANCIAL_AGGREGATOR: 0.0,
    SOURCE_CLASS_COMPANY_HOMEPAGE: 0.0,
    SOURCE_CLASS_DIRECTORY: 0.0,
    SOURCE_CLASS_SEO_CONTENT: 0.0,
}

# Which source roles are accepted for each claim type
CLAIM_TYPE_ALLOWED_ROLES: dict[str, set[str]] = {
    "MANUFACTURING_TRIGGER": {SOURCE_ROLE_PRIMARY_TRIGGER, SOURCE_ROLE_CORROBORATING_TRIGGER},
    "TRIGGER": {SOURCE_ROLE_PRIMARY_TRIGGER, SOURCE_ROLE_CORROBORATING_TRIGGER},
    "HIRING_SIGNAL": {SOURCE_ROLE_HIRING_SIGNAL, SOURCE_ROLE_PRIMARY_TRIGGER, SOURCE_ROLE_CORROBORATING_TRIGGER},
    "PERSON_EMPLOYMENT": {SOURCE_ROLE_PERSON_EMPLOYMENT, SOURCE_ROLE_PRIMARY_TRIGGER, SOURCE_ROLE_CORROBORATING_TRIGGER},
    "FACILITY": {SOURCE_ROLE_FACILITY, SOURCE_ROLE_PRIMARY_TRIGGER, SOURCE_ROLE_CORROBORATING_TRIGGER, SOURCE_ROLE_COMPANY_EXISTENCE},
    "COMPANY_EXISTENCE": {SOURCE_ROLE_COMPANY_EXISTENCE, SOURCE_ROLE_PRIMARY_TRIGGER, SOURCE_ROLE_CORROBORATING_TRIGGER, SOURCE_ROLE_DISCOVERY_ONLY},
}

# Hard-rejected domains: IRRELEVANT for all claim types (no matter what snippet says)
IRRELEVANT_DOMAINS: set[str] = {
    "play.google.com", "apps.apple.com", "itunes.apple.com",
    "brainplay.com", "steam.com", "steampowered.com", "epicgames.com",
    "youtube.com", "netflix.com", "primevideo.com", "hotstar.com",
}

# Untrusted domains: encyclopedias/dictionaries
UNTRUSTED_DOMAINS: set[str] = {
    "wikipedia.org", "en.wikipedia.org", "en.m.wikipedia.org", "simple.wikipedia.org",
    "dictionary.cambridge.org", "merriam-webster.com", "dictionary.com",
    "vocabulary.com", "thefreedictionary.com", "britannica.com", "investopedia.com",
}

# Kept for backward-compatibility with tests importing this name
DISALLOWED_TRIGGER_DOMAINS = IRRELEVANT_DOMAINS | UNTRUSTED_DOMAINS

# Domains categorized as financial aggregators
FINANCIAL_AGGREGATOR_DOMAINS: set[str] = {
    "tofler.in", "zaubacorp.com", "zauba.com", "instafinancials.com",
    "company360.in", "quickcompany.in", "crunchbase.com", "groww.in/stocks",
}

# Domains categorized as directories
DIRECTORY_DOMAINS: set[str] = {
    "indiamart.com", "tradeindia.com", "justdial.com", "yellowpages.in",
    "exportersindia.com", "infobanc.com", "tradekey.com",
}

# Domains categorized as SEO content / syndicated report aggregators
SEO_CONTENT_DOMAINS: set[str] = {
    "marketresearchfuture.com", "transparencymarketresearch.com",
    "reportsanddata.com", "openpr.com", "prlog.org", "issuewire.com",
    "einpresswire.com", "marketsandmarkets.com", "grandviewresearch.com",
}

# Reputable Indian / Global business news domains
REPUTABLE_BUSINESS_NEWS_DOMAINS: set[str] = {
    "business-standard.com", "livemint.com", "economictimes.indiatimes.com",
    "thehindubusinessline.com", "financialexpress.com", "moneycontrol.com",
    "businesstoday.in", "fortuneindia.com", "cnbctv18.com", "reuters.com",
    "bloomberg.com", "ndtv.com", "thehindu.com", "timesofindia.indiatimes.com",
}

# Reputable Indian / Global industry-specific news domains
REPUTABLE_INDUSTRY_NEWS_DOMAINS: set[str] = {
    "autocarpro.in", "autocarindia.com", "evreporter.com", "pv-tech.org",
    "pharmabiz.com", "expresspharma.in", "electronicsforu.com", "automotiveworld.com",
    "chemweek.com", "steelguru.com", "manufacturingtodayindia.com", "epcworld.in",
    "projectstoday.com", "crnasia.com", "sahi.com",
}

# Government / statutory project & investment domains
GOVERNMENT_DOMAINS: set[str] = {
    "pib.gov.in", "dpiit.gov.in", "sebi.gov.in", "mca.gov.in", "midc.in",
    "tidco.com", "investindia.gov.in", "makeinindia.com", "gidc.gujarat.gov.in",
    "riico.co.in", "kiadb.in", "siidcul.com",
}

# Domain → default source role
_DOMAIN_ROLE_MAP: dict[str, str] = {
    "bseindia.com": SOURCE_ROLE_PRIMARY_TRIGGER,
    "nseindia.com": SOURCE_ROLE_PRIMARY_TRIGGER,
    "sebi.gov.in": SOURCE_ROLE_PRIMARY_TRIGGER,
    "mca.gov.in": SOURCE_ROLE_COMPANY_EXISTENCE,
    "pib.gov.in": SOURCE_ROLE_PRIMARY_TRIGGER,
    "dpiit.gov.in": SOURCE_ROLE_PRIMARY_TRIGGER,
    "makeinindia.com": SOURCE_ROLE_PRIMARY_TRIGGER,
    "investindia.gov.in": SOURCE_ROLE_PRIMARY_TRIGGER,
    "midc.in": SOURCE_ROLE_PRIMARY_TRIGGER,
    "tidco.com": SOURCE_ROLE_PRIMARY_TRIGGER,
    "economictimes.indiatimes.com": SOURCE_ROLE_CORROBORATING_TRIGGER,
    "business-standard.com": SOURCE_ROLE_CORROBORATING_TRIGGER,
    "businesstoday.in": SOURCE_ROLE_CORROBORATING_TRIGGER,
    "livemint.com": SOURCE_ROLE_CORROBORATING_TRIGGER,
    "moneycontrol.com": SOURCE_ROLE_CORROBORATING_TRIGGER,
    "financialexpress.com": SOURCE_ROLE_CORROBORATING_TRIGGER,
    "thehindubusinessline.com": SOURCE_ROLE_CORROBORATING_TRIGGER,
    "thehindu.com": SOURCE_ROLE_CORROBORATING_TRIGGER,
    "ndtv.com": SOURCE_ROLE_CORROBORATING_TRIGGER,
    "cnbctv18.com": SOURCE_ROLE_CORROBORATING_TRIGGER,
    "reuters.com": SOURCE_ROLE_CORROBORATING_TRIGGER,
    "bloomberg.com": SOURCE_ROLE_CORROBORATING_TRIGGER,
    "autocarpro.in": SOURCE_ROLE_CORROBORATING_TRIGGER,
    "autocarindia.com": SOURCE_ROLE_CORROBORATING_TRIGGER,
    "evreporter.com": SOURCE_ROLE_CORROBORATING_TRIGGER,
    "pv-tech.org": SOURCE_ROLE_CORROBORATING_TRIGGER,
    "pharmabiz.com": SOURCE_ROLE_CORROBORATING_TRIGGER,
    "expresspharma.in": SOURCE_ROLE_CORROBORATING_TRIGGER,
    "electronicsforu.com": SOURCE_ROLE_CORROBORATING_TRIGGER,
    "screener.in": SOURCE_ROLE_COMPANY_EXISTENCE,
    "tofler.in": SOURCE_ROLE_COMPANY_EXISTENCE,
    "crunchbase.com": SOURCE_ROLE_COMPANY_EXISTENCE,
    "zaubacorp.com": SOURCE_ROLE_COMPANY_EXISTENCE,
    "zauba.com": SOURCE_ROLE_COMPANY_EXISTENCE,
    "indiamart.com": SOURCE_ROLE_COMPANY_EXISTENCE,
    "justdial.com": SOURCE_ROLE_COMPANY_EXISTENCE,
    "naukri.com": SOURCE_ROLE_COMPANY_EXISTENCE,   # overridden to HIRING_SIGNAL by snippet
    "indeed.com": SOURCE_ROLE_COMPANY_EXISTENCE,
    "glassdoor.com": SOURCE_ROLE_COMPANY_EXISTENCE,
    "shine.com": SOURCE_ROLE_COMPANY_EXISTENCE,
    "monster.com": SOURCE_ROLE_COMPANY_EXISTENCE,
    "timesjobs.com": SOURCE_ROLE_COMPANY_EXISTENCE,
    "iimjobs.com": SOURCE_ROLE_COMPANY_EXISTENCE,
    "linkedin.com": SOURCE_ROLE_DISCOVERY_ONLY,    # overridden by URL path analysis
    "in.linkedin.com": SOURCE_ROLE_DISCOVERY_ONLY,
    "twitter.com": SOURCE_ROLE_DISCOVERY_ONLY,
    "x.com": SOURCE_ROLE_DISCOVERY_ONLY,
    "facebook.com": SOURCE_ROLE_DISCOVERY_ONLY,
    "instagram.com": SOURCE_ROLE_DISCOVERY_ONLY,
    "pinterest.com": SOURCE_ROLE_DISCOVERY_ONLY,
    "threads.net": SOURCE_ROLE_DISCOVERY_ONLY,
    "quora.com": SOURCE_ROLE_DISCOVERY_ONLY,
    "reddit.com": SOURCE_ROLE_DISCOVERY_ONLY,
    "maps.google.com": SOURCE_ROLE_FACILITY,
}

# Keywords that indicate a calibration/quality/metrology role in a job posting
_CALIBRATION_ROLE_KEYWORDS = {
    "calibration", "metrology", "gauges", "measurement", "msa", "gage",
    "inspection", "testing lab", "quality laboratory", "nabl", "iso 17025",
    "instrument", "qc lab", "qa lab", "iatf", "quality assurance", "quality control",
    "quality manager", "quality engineer", "quality head", "plant quality",
    "quality systems", "validation", "verification",
}

_JOB_BOARD_DOMAINS = {
    "naukri.com", "indeed.com", "glassdoor.com", "shine.com",
    "monster.com", "timesjobs.com", "iimjobs.com", "hirist.com",
}


def classify_source_class(
    url: str,
    domain: str = "",
    official_domain: str = "",
    title: str = "",
    snippet: str = "",
) -> str:
    """Classify a source into one of the 16 deterministic classes BEFORE LLM analysis."""
    if not (url or "").strip() and not (domain or "").strip():
        return SOURCE_CLASS_UNKNOWN

    clean_domain = (domain or extract_domain(url) or "").lower().replace("www.", "")
    clean_official = (official_domain or "").lower().replace("www.", "")
    url_lower = (url or "").lower()
    parsed = urllib.parse.urlparse(url_lower)
    path = parsed.path


    # 1. Stock Quote / Share price tickers (HARD REJECT for triggers)
    if "screener.in" in clean_domain:
        return SOURCE_CLASS_STOCK_QUOTE
    if any(p in url_lower for p in [
        "/stockpricequote/", "/stocks/companyid", "/market-capitalisation/",
        "/share-price-today", "stock-price", "/stocks/", "/stock-share-price/",
        "/get-quotes/", "trendlyne.com/equity", "marketsmithindia.com",
        "market-stats",
    ]):
        if any(d in clean_domain for d in [
            "moneycontrol.com", "economictimes.indiatimes.com", "bseindia.com",
            "nseindia.com", "livemint.com", "financialexpress.com", "trendlyne.com"
        ]):
            return SOURCE_CLASS_STOCK_QUOTE
        # Generic stock ticker pattern
        if "/stocks/" in url_lower or "/stockpricequote/" in url_lower:
            return SOURCE_CLASS_STOCK_QUOTE

    # 2. Financial Aggregators (HARD REJECT for triggers)
    if any(clean_domain == fa or clean_domain.endswith("." + fa) for fa in FINANCIAL_AGGREGATOR_DOMAINS):
        return SOURCE_CLASS_FINANCIAL_AGGREGATOR

    # 3. Directories (HARD REJECT for triggers)
    if any(clean_domain == dd or clean_domain.endswith("." + dd) for dd in DIRECTORY_DOMAINS):
        return SOURCE_CLASS_DIRECTORY

    # 4. SEO / Syndicated Market Reports (HARD REJECT for triggers)
    if any(clean_domain == sd or clean_domain.endswith("." + sd) for sd in SEO_CONTENT_DOMAINS):
        return SOURCE_CLASS_SEO_CONTENT
    if "marketwatch.com/press-release" in url_lower:
        return SOURCE_CLASS_SEO_CONTENT

    # 5. Stock Exchange Filings
    if "bseindia.com" in clean_domain:
        if any(p in path for p in ["/xml-data/corpfiling/", "/corporates/", "/corporate-actions/"]):
            return SOURCE_CLASS_STOCK_EXCHANGE_FILING
    if "nseindia.com" in clean_domain:
        if any(p in path for p in ["/companies-listing/corporate-filings/", "/corporates/"]):
            return SOURCE_CLASS_STOCK_EXCHANGE_FILING

    # 6. Government Sources
    if clean_domain.endswith(".gov.in") or clean_domain.endswith(".nic.in"):
        return SOURCE_CLASS_GOVERNMENT_SOURCE
    if any(clean_domain == gd or clean_domain.endswith("." + gd) for gd in GOVERNMENT_DOMAINS):
        return SOURCE_CLASS_GOVERNMENT_SOURCE

    # 7. Official Company Domain Classifications
    if clean_official and (clean_domain == clean_official or clean_domain.endswith("." + clean_official)):
        # Press release
        if any(p in path for p in ["/press-release", "/press_release", "/pressrelease", "/news", "/media", "/announcement"]):
            return SOURCE_CLASS_OFFICIAL_PRESS_RELEASE
        # Investor release
        if any(p in path for p in ["/investor", "/investors", "/annual-report", "/financials", "/disclosure"]):
            return SOURCE_CLASS_OFFICIAL_INVESTOR_RELEASE
        # Careers
        if any(p in path for p in ["/career", "/careers", "/jobs", "/job", "/work-with-us"]):
            return SOURCE_CLASS_COMPANY_CAREERS
        # Homepage / generic profile (HARD REJECT for triggers)
        if path in ("", "/", "/index.html", "/index.php") or any(p in path for p in ["/about", "/contact", "/overview", "/profile"]):
            return SOURCE_CLASS_COMPANY_HOMEPAGE

    # Generic bare domain or about-us for non-news websites (HARD REJECT for triggers)
    if path in ("", "/", "/index.html", "/index.php") and clean_domain and clean_domain not in REPUTABLE_BUSINESS_NEWS_DOMAINS and clean_domain not in REPUTABLE_INDUSTRY_NEWS_DOMAINS:
        return SOURCE_CLASS_COMPANY_HOMEPAGE
    if any(p in path for p in ["/about-us", "/about", "/contact-us", "/contact", "/company-profile"]) and clean_domain and clean_domain not in REPUTABLE_BUSINESS_NEWS_DOMAINS:
        return SOURCE_CLASS_COMPANY_HOMEPAGE


    # 8. Professional Profiles & Social Posts
    if "linkedin.com" in clean_domain:
        if "/in/" in path:
            return SOURCE_CLASS_PROFESSIONAL_PROFILE
        if "/jobs/" in path or "/job/" in path:
            return SOURCE_CLASS_HIRING_PAGE
        return SOURCE_CLASS_SOCIAL_POST

    if any(clean_domain == jb or clean_domain.endswith("." + jb) for jb in _JOB_BOARD_DOMAINS):
        return SOURCE_CLASS_HIRING_PAGE

    if any(d in clean_domain for d in ["twitter.com", "x.com", "facebook.com", "instagram.com", "threads.net", "youtube.com", "reddit.com", "quora.com"]):
        return SOURCE_CLASS_SOCIAL_POST

    # 9. Reputable Industry News
    if any(clean_domain == ind or clean_domain.endswith("." + ind) for ind in REPUTABLE_INDUSTRY_NEWS_DOMAINS):
        return SOURCE_CLASS_REPUTABLE_INDUSTRY_NEWS

    # 10. Reputable Business News
    if any(clean_domain == bn or clean_domain.endswith("." + bn) for bn in REPUTABLE_BUSINESS_NEWS_DOMAINS):
        return SOURCE_CLASS_REPUTABLE_BUSINESS_NEWS

    # Global press release paths on arbitrary domains
    if any(p in path for p in ["/press-release", "/press_release", "/pressrelease", "/news-release"]):
        return SOURCE_CLASS_OFFICIAL_PRESS_RELEASE

    return SOURCE_CLASS_UNKNOWN


def is_source_allowed_for_trigger(
    url: str,
    domain: str = "",
    official_domain: str = "",
    title: str = "",
    snippet: str = "",
) -> Tuple[bool, str, str]:
    """Check whether a discovered source URL is deterministically permitted as a trigger source.

    Returns:
        (is_allowed, source_class, reason)
    """
    src_class = classify_source_class(
        url=url, domain=domain, official_domain=official_domain, title=title, snippet=snippet
    )
    if src_class in TRIGGER_HARD_REJECT_CLASSES:
        return False, src_class, f"Deterministic hard reject: {src_class} cannot prove plant capex or expansion"
    return True, src_class, f"Source class {src_class} is allowed for trigger evaluation"


def classify_source_role(
    url: str,
    domain: str,
    claim_type: str = "",
    snippet: str = "",
) -> str:
    """Classify the role of a source based on domain, URL path, and snippet context.

    Enforces path-level classification so that stock quotes or homepages on reputable
    domains are NEVER promoted to trigger evidence.
    """
    clean_domain = (domain or "").lower().replace("www.", "")
    url_lower = (url or "").lower()
    snippet_lower = (snippet or "").lower()

    # Hard reject: IRRELEVANT
    for d in IRRELEVANT_DOMAINS:
        clean_d = d.replace("www.", "")
        if clean_domain == clean_d or clean_domain.endswith("." + clean_d):
            return SOURCE_ROLE_IRRELEVANT

    # Hard reject: UNTRUSTED
    for d in UNTRUSTED_DOMAINS:
        clean_d = d.replace("www.", "")
        if clean_domain == clean_d or clean_domain.endswith("." + clean_d):
            return SOURCE_ROLE_UNTRUSTED

    # Deterministic source class check: reject stock quotes and homepages from trigger roles
    src_class = classify_source_class(url, domain=clean_domain, snippet=snippet)
    if src_class == SOURCE_CLASS_STOCK_QUOTE:
        return SOURCE_ROLE_COMPANY_EXISTENCE
    if src_class in (SOURCE_CLASS_FINANCIAL_AGGREGATOR, SOURCE_CLASS_DIRECTORY):
        return SOURCE_ROLE_COMPANY_EXISTENCE
    if src_class == SOURCE_CLASS_COMPANY_HOMEPAGE:
        return SOURCE_ROLE_COMPANY_EXISTENCE
    if src_class == SOURCE_CLASS_SEO_CONTENT:
        return SOURCE_ROLE_DISCOVERY_ONLY

    # LinkedIn: path-based classification
    if "linkedin.com" in clean_domain:
        if "/in/" in url_lower:
            return SOURCE_ROLE_PERSON_EMPLOYMENT
        if "/jobs/" in url_lower or "/job/" in url_lower:
            has_cal = any(kw in snippet_lower for kw in _CALIBRATION_ROLE_KEYWORDS)
            return SOURCE_ROLE_HIRING_SIGNAL if has_cal else SOURCE_ROLE_DISCOVERY_ONLY
        return SOURCE_ROLE_DISCOVERY_ONLY

    # Job boards: upgrade to HIRING_SIGNAL if calibration/quality role in snippet
    if any(clean_domain == jb or clean_domain.endswith("." + jb) for jb in _JOB_BOARD_DOMAINS):
        has_cal = any(kw in snippet_lower for kw in _CALIBRATION_ROLE_KEYWORDS)
        return SOURCE_ROLE_HIRING_SIGNAL if has_cal else SOURCE_ROLE_COMPANY_EXISTENCE

    # Google Maps
    if "maps.google" in url_lower or ("google.com" in clean_domain and "/maps" in url_lower):
        return SOURCE_ROLE_FACILITY

    # Domain map lookup
    for map_domain, role in _DOMAIN_ROLE_MAP.items():
        clean_map = map_domain.replace("www.", "")
        if clean_domain == clean_map or clean_domain.endswith("." + clean_map):
            return role

    # Default: CORROBORATING_TRIGGER_SOURCE (unknown press/news sites)
    return SOURCE_ROLE_CORROBORATING_TRIGGER


def is_source_role_allowed_for_claim(source_role: str, claim_type: str) -> bool:
    """Return True if source_role is acceptable evidence for claim_type."""
    if source_role in (SOURCE_ROLE_IRRELEVANT, SOURCE_ROLE_UNTRUSTED):
        return False
    allowed = CLAIM_TYPE_ALLOWED_ROLES.get(claim_type.upper(), None)
    if allowed is None:
        return True
    return source_role in allowed


class SourceVerificationPipeline:
    """Verifies discovered sources; prevents direct promotion to verified states."""

    @staticmethod
    def verify_discovered_source(
        company: str,
        claim_type: str,
        claim_text: str,
        source_url: str,
        facility: str = "",
        person: str = "",
        timeout_seconds: int = 10,
        mock_fetch_success: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """Validate a discovered source against evidence integrity rules.

        Returns dict containing verified, status, source_role, reason,
        provenance_record, claim_status, requires_deterministic_gate.
        """
        clean_company = company.strip()
        clean_url = source_url.strip()

        if not clean_url or not (clean_url.startswith("http://") or clean_url.startswith("https://")):
            return {
                "status": "UNVERIFIED", "verified": False, "source_role": SOURCE_ROLE_IRRELEVANT,
                "reason": "Cited source does not provide a valid HTTP/HTTPS URL.",
                "provenance_record": None, "claim_status": f"UNVERIFIED_{claim_type}",
            }

        domain = extract_domain(clean_url)
        if not domain:
            return {
                "status": "UNVERIFIED", "verified": False, "source_role": SOURCE_ROLE_IRRELEVANT,
                "reason": f"Cannot extract valid domain from URL: {clean_url}",
                "provenance_record": None, "claim_status": f"UNVERIFIED_{claim_type}",
            }

        source_role = classify_source_role(
            url=clean_url, domain=domain, claim_type=claim_type, snippet=claim_text
        )

        if source_role == SOURCE_ROLE_IRRELEVANT:
            return {
                "status": "UNVERIFIED", "verified": False, "source_role": source_role,
                "reason": f"Domain '{domain}' is irrelevant (games/entertainment/app store) and cannot serve as evidence.",
                "provenance_record": None, "claim_status": f"UNVERIFIED_{claim_type}",
            }

        if source_role == SOURCE_ROLE_UNTRUSTED:
            return {
                "status": "UNVERIFIED", "verified": False, "source_role": source_role,
                "reason": f"Domain '{domain}' is an untrusted reference source (encyclopedia/dictionary) and cannot corroborate corporate claims.",
                "provenance_record": None, "claim_status": f"UNVERIFIED_{claim_type}",
            }

        if not is_source_role_allowed_for_claim(source_role, claim_type):
            return {
                "status": "UNVERIFIED", "verified": False, "source_role": source_role,
                "reason": (
                    f"Source role '{source_role}' from '{domain}' is not acceptable for claim type '{claim_type}'. "
                    f"Allowed roles: {sorted(CLAIM_TYPE_ALLOWED_ROLES.get(claim_type.upper(), set()))}."
                ),
                "provenance_record": None, "claim_status": f"UNVERIFIED_{claim_type}",
            }

        # Company co-occurrence check
        company_tokens = [
            tok for tok in re.split(r"[^\w]+", clean_company.lower())
            if len(tok) > 2 and tok not in {
                "ltd", "limited", "pvt", "private", "india", "the", "and", "inc",
                "corp", "corporation", "group", "systems", "industries", "technologies",
            }
        ]
        snippet_lower = (claim_text or "").lower()
        if company_tokens and not any(tok in snippet_lower for tok in company_tokens):
            return {
                "status": "UNVERIFIED", "verified": False, "source_role": source_role,
                "reason": f"Evidence snippet does not mention target company '{clean_company}'.",
                "provenance_record": None, "claim_status": f"UNVERIFIED_{claim_type}",
            }

        # Independent URL fetch check
        fetch_ok = False
        fetch_error = ""
        if mock_fetch_success is not None:
            fetch_ok = mock_fetch_success
            if not fetch_ok:
                fetch_error = "Mock fetch failed"
        else:
            try:
                headers = {"User-Agent": "SalesoorjaVerificationBot/1.0"}
                resp = requests.head(clean_url, headers=headers, timeout=timeout_seconds, allow_redirects=True)
                if resp.status_code in (200, 301, 302, 307, 308, 403):
                    fetch_ok = True
                else:
                    resp_get = requests.get(clean_url, headers=headers, timeout=timeout_seconds, stream=True)
                    fetch_ok = resp_get.status_code < 400
            except Exception as e:
                fetch_ok = False
                fetch_error = str(e)

        if not fetch_ok:
            return {
                "status": "UNVERIFIED", "verified": False, "source_role": source_role,
                "reason": f"Cited URL '{clean_url}' could not be independently fetched: {fetch_error or 'HTTP error'}",
                "provenance_record": None, "claim_status": f"UNVERIFIED_{claim_type}",
            }

        snippet = strip_internal_model_markers(claim_text)
        record = EvidenceProvenanceRecord(
            evidence_id="",
            claim_type=claim_type,
            company=clean_company,
            facility=facility,
            person=person,
            source_url=clean_url,
            source_domain=domain,
            snippet=snippet,
            raw_text_hash=compute_text_hash(snippet),
            confidence=0.85 if source_role == SOURCE_ROLE_PRIMARY_TRIGGER else 0.75,
            provenance={
                "source_type": "INDEPENDENTLY_FETCHED_URL",
                "source_role": source_role,
                "verified_at": datetime.now(timezone.utc).isoformat(),
                "original_llm_discovered": True,
            },
        )

        return {
            "status": "CORROBORATED_SOURCE",
            "verified": True,
            "source_role": source_role,
            "reason": f"Source URL {clean_url} is active and verified (role: {source_role}).",
            "provenance_record": record,
            "claim_status": f"CORROBORATED_{claim_type}",
            "requires_deterministic_gate": True,
        }


source_verification_pipeline = SourceVerificationPipeline()
