"""Fast Bulk Web Crawler & Trigger Pipeline using Crawl4AI.

Pipeline:
SearXNG / Company URLs
→ Domain Restriction & Duplicate URL Suppression
→ Crawl4AI Bulk Fetch (with retry, timeout, and 24h cache)
→ Trigger & Intent Extraction (Expansion, New Plant, Laboratory, Metrology Hiring)
→ Filter useful pages only before any expensive reasoning
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import time
from urllib.parse import urljoin, urlparse
from typing import Any, Dict, List, Optional, Set

from services.document_extraction import (
    extract_url_with_crawl4ai,
    _public_http_url,
    ExtractionResult,
)

logger = logging.getLogger(__name__)

TARGET_SUBPATHS = [
    "/news",
    "/careers",
    "/media",
    "/press-releases",
    "/projects",
    "/locations",
    "/about-us",
    "/manufacturing",
    "/quality",
]

TRIGGER_CATEGORIES = {
    "EXPANSION": [
        "expansion", "capacity expansion", "brownfield", "greenfield",
        "capex", "investment", "scaling production",
    ],
    "NEW_PLANT_COMMISSIONING": [
        "new plant", "new facility", "commissioning", "commercial production",
        "inaugurated", "groundbreaking", "new manufacturing unit",
    ],
    "MACHINERY": [
        "machinery", "machining bay", "cnc", "furnace", "press shop",
        "injection molding", "automated line", "assembly line",
    ],
    "LABORATORY": [
        "testing laboratory", "metrology lab", "calibration lab", "qc lab",
        "rd center", "analytical lab", "nabl accredited lab",
    ],
    "METROLOGY_HIRING": [
        "quality head", "metrology engineer", "calibration technician",
        "qa manager", "qc inspector", "cqa lead", "quality assurance engineer",
    ],
    "VALIDATION_COMPLIANCE": [
        "validation", "qualification", "iq oq pq", "iso/iec 17025",
        "iatf 16949", "as9100", "audit cleared", "nabl renewal",
    ],
    "OEM_EXPORT_APPROVAL": [
        "oem approval", "customer audit", "export ramp-up", "usfda approval",
        "ce mark", "european export", "defense clearance",
    ],
}

_CRAWL_CACHE: Dict[str, Dict[str, Any]] = {}


def normalize_url(url: str) -> str:
    """Strip fragments, tracking queries, and trailing slashes."""
    parsed = urlparse(url.strip())
    # Keep only host and path
    clean_path = parsed.path.rstrip("/")
    return f"{parsed.scheme}://{parsed.netloc.lower()}{clean_path}"


def is_same_registered_domain(url1: str, url2: str) -> bool:
    """Enforce strict domain restrictions."""
    h1 = (urlparse(url1).hostname or "").lower().removeprefix("www.")
    h2 = (urlparse(url2).hostname or "").lower().removeprefix("www.")
    return h1 == h2 or h1.endswith("." + h2) or h2.endswith("." + h1)


def generate_company_target_urls(base_url: str, max_urls: int = 5) -> List[str]:
    """Generate prioritized crawl targets for a company website."""
    if not base_url.startswith(("http://", "https://")):
        base_url = "https://" + base_url.strip()
    root = f"{urlparse(base_url).scheme}://{urlparse(base_url).netloc}"
    targets = [root]
    for sub in TARGET_SUBPATHS:
        if len(targets) >= max_urls:
            break
        targets.append(urljoin(root, sub))
    return targets


def extract_triggers_from_content(markdown_text: str, source_url: str) -> List[Dict[str, Any]]:
    """Scan crawled page markdown for calibration demand triggers."""
    text_lower = (markdown_text or "").lower()
    found_triggers = []

    for category, keywords in TRIGGER_CATEGORIES.items():
        for kw in keywords:
            if kw in text_lower:
                # Find matching sentence or paragraph snippet
                snippet = ""
                for paragraph in (markdown_text or "").split("\n\n"):
                    if kw in paragraph.lower():
                        snippet = paragraph.strip()[:350]
                        break
                found_triggers.append({
                    "category": category,
                    "keyword": kw,
                    "source_url": source_url,
                    "snippet": snippet or kw,
                    "confidence": 0.85 if category in {"NEW_PLANT_COMMISSIONING", "LABORATORY"} else 0.75,
                })
                break  # one keyword match per category per page is sufficient

    return found_triggers


async def crawl_company_pipeline(
    company_domain_or_url: str,
    *,
    seed_urls: Optional[List[str]] = None,
    max_pages: int = 5,
    crawler: Any = None,
    enabled: bool = True,
) -> Dict[str, Any]:
    """Execute Crawl4AI fast bulk crawl with domain bounds, caching, and trigger extraction."""
    base_url = company_domain_or_url if company_domain_or_url.startswith(("http://", "https://")) else f"https://{company_domain_or_url}"
    candidate_urls = seed_urls or generate_company_target_urls(base_url, max_urls=max_pages)

    # Domain restriction & duplicate suppression
    valid_targets: List[str] = []
    seen: Set[str] = set()

    for u in candidate_urls:
        norm = normalize_url(u)
        if norm in seen or len(valid_targets) >= max_pages:
            continue
        if not is_same_registered_domain(norm, base_url):
            logger.debug("Skipping off-domain URL: %s", u)
            continue
        valid, _ = _public_http_url(norm)
        if not valid:
            continue
        seen.add(norm)
        valid_targets.append(norm)

    pages_crawled = []
    all_triggers = []
    now_ts = time.time()

    for url in valid_targets:
        # Check 24-hour cache
        cached = _CRAWL_CACHE.get(url)
        if cached and (now_ts - cached.get("cached_at", 0)) < 86400:
            pages_crawled.append({
                "url": url,
                "status": "CACHED",
                "triggers_count": len(cached.get("triggers", [])),
            })
            all_triggers.extend(cached.get("triggers", []))
            continue

        # Execute fetch
        result: ExtractionResult = await extract_url_with_crawl4ai(
            url,
            enabled=enabled,
            crawler=crawler,
        )

        if result.status == "SUCCESS" and result.text:
            page_triggers = extract_triggers_from_content(result.text, url)
            _CRAWL_CACHE[url] = {
                "url": url,
                "triggers": page_triggers,
                "cached_at": now_ts,
            }
            pages_crawled.append({
                "url": url,
                "status": "SUCCESS",
                "triggers_count": len(page_triggers),
            })
            all_triggers.extend(page_triggers)
        else:
            pages_crawled.append({
                "url": url,
                "status": result.status,
                "warning": result.warning,
                "triggers_count": 0,
            })

    # High value triggers warrant deeper reasoning
    needs_deep_reasoning = any(t["category"] in {"NEW_PLANT_COMMISSIONING", "LABORATORY", "EXPANSION"} for t in all_triggers)

    return {
        "company_target": base_url,
        "pages_evaluated": len(pages_crawled),
        "pages_crawled": pages_crawled,
        "total_triggers_found": len(all_triggers),
        "triggers": all_triggers,
        "needs_deep_browser_reasoning": needs_deep_reasoning,
    }


def crawl_company_pipeline_sync(company_domain_or_url: str, **kwargs: Any) -> Dict[str, Any]:
    """Synchronous entrypoint for pipeline callers."""
    return asyncio.run(crawl_company_pipeline(company_domain_or_url, **kwargs))


_FACILITY_URL_CACHE: Dict[str, List[str]] = {}


def discover_facility_pages(
    domain: str,
    html_text: Optional[str] = None,
    max_pages: int = 4,
    timeout: int = 8,
) -> List[str]:
    """Deep facility discovery: inspect root page navigation and cached paths for plant/manufacturing pages.

    Crawls or scans the root domain for manufacturing, plant, facility, and infrastructure
    sub-pages to locate physical plant operations in India.
    """
    clean_domain = domain.removeprefix("https://").removeprefix("http://").removeprefix("www.").strip().rstrip("/")
    if clean_domain in _FACILITY_URL_CACHE:
        return _FACILITY_URL_CACHE[clean_domain]

    discovered: List[str] = []
    keywords = [
        "manufacturing", "facilities", "plants", "locations", "operations",
        "factories", "infrastructure", "about-us", "production", "contact"
    ]

    if not html_text:
        import urllib.request
        base_url = f"https://www.{clean_domain}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 Salesoorja-Facility-Discovery/2.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        try:
            req = urllib.request.Request(base_url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                html_text = resp.read().decode("utf-8", errors="replace")
        except Exception as exc:
            logger.debug("discover_facility_pages root fetch failed for %s: %s", clean_domain, exc)
            html_text = ""

    if html_text:
        links = re.findall(r'href=[\'"](/?[a-zA-Z0-9_\-\./]+)[\'"]', html_text)
        seen: Set[str] = set()
        for link in links:
            clean = link.split("?")[0].split("#")[0].strip()
            if any(k in clean.lower() for k in keywords):
                if clean.startswith("http") and clean_domain in clean and clean not in seen:
                    discovered.append(clean)
                    seen.add(clean)
                elif clean.startswith("/") and clean not in seen:
                    discovered.append(f"https://www.{clean_domain}{clean}")
                    seen.add(clean)

    _FACILITY_URL_CACHE[clean_domain] = discovered[:max_pages]
    return _FACILITY_URL_CACHE[clean_domain]
