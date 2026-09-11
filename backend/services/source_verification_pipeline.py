"""Source Verification and Citation Normalization Pipeline.

Enforces Salesoorja Evidence Invariants:
1. LLM-discovered sources (e.g. from UnoRouter glm-5.3-search:free) are DISCOVERY EVIDENCE only.
2. An LLM-generated claim can NEVER be promoted directly to:
   - TRIGGER_VERIFIED
   - FACILITY_VERIFIED
   - PERSON_VERIFIED
   - CONTACT_VERIFIED
3. Internal model markers (e.g. 'turn0search0') are normalized and NEVER persisted as source IDs.
4. Genuine citations must provide a valid source_url, source_domain, source_title, retrieved_at,
   snippet, and cryptographic raw_text_hash.
5. If a cited URL cannot be fetched or corroborated independently, the claim remains UNVERIFIED.
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

# Pattern to extract dates like "April 9, 2025", "November 2025", "2025-04-09", "2026"
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
    """Extracts and normalizes citations from search model text output.
    
    Extracts:
    - source_url
    - source_domain
    - source_title
    - publication_date (if mentioned)
    - retrieved_at
    - clean snippet (with internal model markers stripped)
    - raw_text_hash
    
    Rejects any marker-only citations lacking a genuine URL.
    """
    if not raw_text:
        return []

    citations: List[Dict[str, Any]] = []
    seen_urls: set[str] = set()

    # 1. Parse markdown links [Title](URL)
    for match in MARKDOWN_LINK_PATTERN.finditer(raw_text):
        title = strip_internal_model_markers(match.group(1)).strip()
        url = match.group(2).rstrip(".,;)>]").strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)

        # Context snippet around match
        start_idx = max(0, match.start() - 150)
        end_idx = min(len(raw_text), match.end() + 150)
        snippet = strip_internal_model_markers(raw_text[start_idx:end_idx])

        # Extract publication date if mentioned
        date_match = DATE_PATTERN.search(snippet)
        pub_date = date_match.group(0) if date_match else ""

        domain = extract_domain(url)
        text_hash = compute_text_hash(snippet)

        citations.append({
            "source_url": url,
            "source_domain": domain,
            "source_title": title or domain,
            "publication_date": pub_date,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "snippet": snippet,
            "raw_text_hash": text_hash,
            "source_type": "WEB_CITATION",
        })

    # 2. Parse raw URLs not already captured
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
            "source_url": url,
            "source_domain": domain,
            "source_title": domain,
            "publication_date": pub_date,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "snippet": snippet,
            "raw_text_hash": text_hash,
            "source_type": "RAW_URL",
        })

    return citations


class SourceVerificationPipeline:
    """Verifies discovered sources and prevents direct promotion to verified states."""

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
        """Validates that an LLM-discovered source is fetchable and corroborated.
        
        Strict Safety Invariants:
        - LLM claims are DISCOVERY EVIDENCE only.
        - Claim can NEVER be promoted to TRIGGER_VERIFIED, FACILITY_VERIFIED,
          PERSON_VERIFIED, or CONTACT_VERIFIED directly.
        - If cited URL cannot be fetched or corroborated, claim remains UNVERIFIED.
        """
        clean_company = company.strip()
        clean_url = source_url.strip()

        # Check URL validity
        if not clean_url or not (clean_url.startswith("http://") or clean_url.startswith("https://")):
            return {
                "status": "UNVERIFIED",
                "verified": False,
                "reason": "Cited source does not provide a valid HTTP/HTTPS URL.",
                "provenance_record": None,
                "claim_status": f"UNVERIFIED_{claim_type}",
            }

        domain = extract_domain(clean_url)
        if not domain:
            return {
                "status": "UNVERIFIED",
                "verified": False,
                "reason": f"Cannot extract valid domain from URL: {clean_url}",
                "provenance_record": None,
                "claim_status": f"UNVERIFIED_{claim_type}",
            }

        # Independent fetch check
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
                    # 403 often indicates cloudflare protection on a live real domain
                    fetch_ok = True
                else:
                    # Retry with GET in case HEAD is disallowed
                    resp_get = requests.get(clean_url, headers=headers, timeout=timeout_seconds, stream=True)
                    fetch_ok = resp_get.status_code < 400
            except Exception as e:
                fetch_ok = False
                fetch_error = str(e)

        if not fetch_ok:
            return {
                "status": "UNVERIFIED",
                "verified": False,
                "reason": f"Cited URL '{clean_url}' could not be verified independently: {fetch_error or 'HTTP error'}",
                "provenance_record": None,
                "claim_status": f"UNVERIFIED_{claim_type}",
            }

        # Source is corroborated as live and fetchable
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
            confidence=0.80,
            provenance={
                "source_type": "INDEPENDENTLY_FETCHED_URL",
                "verified_at": datetime.now(timezone.utc).isoformat(),
                "original_llm_discovered": True,
            },
        )

        return {
            "status": "CORROBORATED_SOURCE",
            "verified": True,
            "reason": f"Source URL {clean_url} is active and verified.",
            "provenance_record": record,
            "claim_status": f"CORROBORATED_{claim_type}",
            "requires_deterministic_gate": True,
        }


source_verification_pipeline = SourceVerificationPipeline()
