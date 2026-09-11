"""Source Verification and Citation Normalization Pipeline.

Enforces Salesoorja Evidence Invariants:
1. LLM-discovered sources (e.g. from UnoRouter glm-5.3-search:free) are DISCOVERY EVIDENCE only.
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


def classify_source_role(
    url: str,
    domain: str,
    claim_type: str = "",
    snippet: str = "",
) -> str:
    """Classify the role of a source based on domain, URL path, and snippet context.

    The same domain can serve different roles:
    - linkedin.com/in/john-doe  -> PERSON_EMPLOYMENT_SOURCE
    - linkedin.com/company/foo  -> DISCOVERY_ONLY
    - naukri.com job with "calibration" in snippet -> HIRING_SIGNAL_SOURCE
    - play.google.com           -> IRRELEVANT (always)
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
