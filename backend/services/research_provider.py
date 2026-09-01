"""Research Provider Abstraction — unified web/person research router.

Supports multiple legitimate configured research sources:
- Google Custom Search API (GOOGLE_API_KEY + GOOGLE_SEARCH_CX)
- Serper API (SERPER_API_KEY)
- Existing web_research_service (database cache)
- Direct HTTP fetch of public company pages

Each provider clearly reports its status:
  LIVE, NOT_CONFIGURED, ERROR, FALLBACK

Does NOT bypass login controls, anti-bot protections, or access restrictions.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import os
import requests
from sqlalchemy.orm import Session

from config import settings
from services.settings_manager import get_setting_value
from models.web_research import WebResearchItem

logger = logging.getLogger(__name__)

# ── Provider Status Constants ───────────────────────────────────────────
PROVIDER_LIVE = "LIVE"
PROVIDER_NOT_CONFIGURED = "NOT_CONFIGURED"
PROVIDER_ERROR = "ERROR"
PROVIDER_FALLBACK = "FALLBACK"
PROVIDER_EMPTY = "EMPTY"
PROVIDER_BLOCKED = "BLOCKED"
PROVIDER_QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"


class ResearchResult:
    """Single research result from any provider."""

    def __init__(
        self,
        title: str,
        url: str,
        snippet: str,
        source_domain: str = "",
        retrieved_at: Optional[str] = None,
        confidence: float = 0.5,
        evidence_type: str = "WEB_EVIDENCE",
        provider: str = "unknown",
    ):
        self.title = title
        self.url = url
        self.snippet = snippet
        self.source_domain = source_domain or urlparse(url).netloc
        self.retrieved_at = retrieved_at or datetime.utcnow().isoformat()
        self.confidence = confidence
        self.evidence_type = evidence_type
        self.provider = provider

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "source_domain": self.source_domain,
            "retrieved_at": self.retrieved_at,
            "confidence": self.confidence,
            "evidence_type": self.evidence_type,
            "provider": self.provider,
        }


class ResearchProviderRouter:
    """Routes research queries to the best available provider.

    Priority order:
    1. Google Custom Search API (if GOOGLE_API_KEY + GOOGLE_SEARCH_CX configured)
    2. Serper API (if SERPER_API_KEY configured)
    3. Direct public page fetch (for company websites)
    4. Existing web_research cache (database)
    """

    def _discover_providers(self) -> List[Dict[str, Any]]:
        """Discover which research providers are configured and available."""
        providers = []

        # Google Custom Search
        google_key = str(get_setting_value("GOOGLE_API_KEY", "")).strip()
        google_cx = str(get_setting_value("GOOGLE_SEARCH_CX", "")).strip()
        # Ensure mock keys are not treated as live search keys
        is_google_live = bool(google_key and google_cx and not google_key.startswith("mock_") and not google_key.startswith("YOUR_"))
        providers.append({
            "name": "google_custom_search",
            "display": "Google Custom Search",
            "configured": is_google_live,
            "priority": 1,
        })

        # Serper
        serper_key = str(get_setting_value("SERPER_API_KEY", "")).strip()
        is_serper_live = bool(serper_key and not serper_key.startswith("mock_") and not serper_key.startswith("YOUR_"))
        providers.append({
            "name": "serper",
            "display": "Serper Search API",
            "configured": is_serper_live,
            "priority": 2,
        })

        # SearXNG Private Self-Hosted Search
        searxng_url = str(getattr(settings, "SEARXNG_BASE_URL", "") or get_setting_value("SEARXNG_BASE_URL", "http://localhost:8080")).strip()
        providers.append({
            "name": "searxng",
            "display": "SearXNG Private Search",
            "configured": bool(searxng_url),
            "priority": 3,
        })

        # Direct public page fetch (always available)
        providers.append({
            "name": "public_page_fetch",
            "display": "Public Company Page Fetch",
            "configured": True,
            "priority": 4,
        })

        # Database cache (always available)
        providers.append({
            "name": "database_cache",
            "display": "Web Research Cache",
            "configured": True,
            "priority": 5,
        })

        return sorted(providers, key=lambda p: p["priority"])

    def get_provider_status(self) -> Dict[str, str]:
        """Return status of all providers."""
        providers = self._discover_providers()
        return {
            p["name"]: PROVIDER_LIVE if p["configured"] else PROVIDER_NOT_CONFIGURED
            for p in providers
        }

    def get_best_search_provider(self) -> Optional[str]:
        """Return the name of the best available search provider."""
        providers = self._discover_providers()
        for p in providers:
            if p["configured"] and p["name"] in ("google_custom_search", "serper", "searxng"):
                return p["name"]
        return None

    def search(
        self,
        query: str,
        num_results: int = 5,
        company_id: Optional[int] = None,
        db: Optional[Session] = None,
    ) -> Dict[str, Any]:
        """Execute a search using the best available provider with automatic fallback.

        Priority order:
        1. Google Custom Search
        2. Serper API
        3. SearXNG Private Instance
        4. Database Cache
        """
        results = []
        status = PROVIDER_NOT_CONFIGURED
        error = None
        used_provider = "none"

        # 1. Google Custom Search
        google_key = str(get_setting_value("GOOGLE_API_KEY", "")).strip()
        google_cx = str(get_setting_value("GOOGLE_SEARCH_CX", "")).strip()
        if google_key and google_cx and not google_key.startswith("mock_") and not google_key.startswith("YOUR_"):
            results, status, error = self._search_google(query, num_results)
            if status == PROVIDER_LIVE:
                used_provider = "google_custom_search"

        # 2. Serper fallback
        if not results:
            serper_key = str(get_setting_value("SERPER_API_KEY", "")).strip()
            if serper_key and not serper_key.startswith("mock_") and not serper_key.startswith("YOUR_"):
                results, status, error = self._search_serper(query, num_results)
                if status == PROVIDER_LIVE:
                    used_provider = "serper"

        # 3. SearXNG fallback
        if not results:
            results, status, error = self._search_searxng(query, num_results)
            if status == PROVIDER_LIVE:
                used_provider = "searxng"

        # 4. Database Cache fallback
        if not results and db:
            results, status, error = self._search_database_cache(query, db)
            if status == PROVIDER_LIVE:
                used_provider = "database_cache"
                status = PROVIDER_FALLBACK

        # Store results in database for future cache
        if db and results and status in (PROVIDER_LIVE, PROVIDER_FALLBACK):
            for r in results:
                try:
                    item = WebResearchItem(
                        company_id=company_id,
                        query=query,
                        title=r.title,
                        url=r.url,
                        source_domain=r.source_domain,
                        snippet=r.snippet,
                        confidence=int(r.confidence * 100),
                        evidence_type=r.evidence_type,
                        metadata_json={"provider": r.provider},
                    )
                    db.add(item)
                except Exception as e:
                    logger.warning("Failed to cache research result: %s", e)
            try:
                db.commit()
            except Exception as e:
                db.rollback()
                logger.warning("Failed to commit research cache: %s", e)

        return {
            "provider": used_provider,
            "provider_status": status,
            "results": [r.to_dict() for r in results],
            "query": query,
            "error": error,
        }

    def _search_searxng(
        self, query: str, num_results: int = 5
    ) -> tuple[list[ResearchResult], str, Optional[str]]:
        """Search via self-hosted SearXNG instance."""
        candidate_urls = [
            os.environ.get("SEARXNG_BASE_URL", "").rstrip("/"),
            str(getattr(settings, "SEARXNG_BASE_URL", "")).rstrip("/"),
            "http://searxng:8080",
            "http://localhost:8080",
        ]
        candidate_urls = [u for u in candidate_urls if u]
        for base in candidate_urls:
            url = f"{base}/search"
            params = {
                "q": query,
                "format": "json",
                "categories": "general",
                "language": "en-IN",
            }
            try:
                resp = requests.get(url, params=params, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    raw_results = data.get("results", [])
                    results = []
                    for item in raw_results[:num_results]:
                        results.append(ResearchResult(
                            title=item.get("title", ""),
                            url=item.get("url", ""),
                            snippet=item.get("content", ""),
                            provider="searxng",
                            confidence=0.85,
                        ))
                    if results:
                        return results, PROVIDER_LIVE, None
            except Exception as e:
                logger.debug("SearXNG candidate %s connection note: %s", base, e)
                continue
        return [], PROVIDER_EMPTY, "SearXNG returned no results"

    def _search_google(
        self, query: str, num_results: int
    ) -> tuple[list[ResearchResult], str, Optional[str]]:
        """Search via Google Custom Search JSON API."""
        api_key = str(get_setting_value("GOOGLE_API_KEY", "")).strip()
        cx = str(get_setting_value("GOOGLE_SEARCH_CX", "")).strip()

        if not api_key or not cx or api_key.startswith("mock_") or api_key.startswith("YOUR_"):
            return [], PROVIDER_NOT_CONFIGURED, "Google API key or Search Engine ID not configured"

        try:
            resp = requests.get(
                "https://www.googleapis.com/customsearch/v1",
                params={"key": api_key, "cx": cx, "q": query, "num": min(num_results, 10)},
                timeout=15,
            )
            if resp.status_code != 200:
                logger.error("Google Custom Search HTTP %s: %s", resp.status_code, resp.text[:200])
                return [], PROVIDER_ERROR, f"Google API HTTP {resp.status_code}"

            data = resp.json()
            results = []
            for item in data.get("items", []):
                results.append(ResearchResult(
                    title=item.get("title", ""),
                    url=item.get("link", ""),
                    snippet=item.get("snippet", ""),
                    provider="google_custom_search",
                    confidence=0.75,
                ))
            return results, PROVIDER_LIVE, None

        except Exception as e:
            logger.exception("Google Custom Search error: %s", e)
            return [], PROVIDER_ERROR, str(e)

    def _search_serper(
        self, query: str, num_results: int
    ) -> tuple[list[ResearchResult], str, Optional[str]]:
        """Search via Serper.dev API."""
        api_key = str(get_setting_value("SERPER_API_KEY", "")).strip()

        if not api_key or api_key.startswith("mock_") or api_key.startswith("YOUR_"):
            return [], PROVIDER_NOT_CONFIGURED, "Serper API key not configured"

        last_err = None
        for attempt in range(3):
            try:
                resp = requests.post(
                    "https://google.serper.dev/search",
                    json={"q": query, "num": min(num_results, 10)},
                    headers={
                        "X-API-KEY": api_key,
                        "Content-Type": "application/json",
                        "Connection": "close",
                    },
                    timeout=20,
                )
                if resp.status_code != 200:
                    logger.error("Serper API HTTP %s: %s", resp.status_code, resp.text[:200])
                    return [], PROVIDER_ERROR, f"Serper API HTTP {resp.status_code}"

                data = resp.json()
                results = []
                for item in data.get("organic", []):
                    results.append(ResearchResult(
                        title=item.get("title", ""),
                        url=item.get("link", ""),
                        snippet=item.get("snippet", ""),
                        provider="serper",
                        confidence=0.72,
                    ))

                if results:
                    return results, PROVIDER_LIVE, None
                return [], PROVIDER_EMPTY, "Serper returned no organic results"

            except Exception as e:
                last_err = e
                logger.warning(f"Serper attempt {attempt + 1} failed: {e}. Retrying...")
                time.sleep(1)

        logger.error("Serper search error after retries: %s", last_err, exc_info=True)
        return [], PROVIDER_ERROR, f"Serper search error: {str(last_err)[:100]}"

    def _search_database_cache(
        self, query: str, db: Session
    ) -> tuple[list[ResearchResult], str, Optional[str]]:
        """Search existing web_research database cache."""
        try:
            pattern = f"%{query.strip()}%"
            rows = (
                db.query(WebResearchItem)
                .filter(
                    (WebResearchItem.query.ilike(pattern))
                    | (WebResearchItem.title.ilike(pattern))
                    | (WebResearchItem.snippet.ilike(pattern))
                )
                .order_by(WebResearchItem.retrieved_at.desc())
                .limit(10)
                .all()
            )
            results = [
                ResearchResult(
                    title=r.title or "",
                    url=r.url or "",
                    snippet=r.snippet or "",
                    source_domain=r.source_domain or "",
                    confidence=(r.confidence or 50) / 100.0,
                    provider="database_cache",
                )
                for r in rows
            ]
            return results, PROVIDER_FALLBACK if results else PROVIDER_NOT_CONFIGURED, None
        except Exception as e:
            logger.exception("Database cache search error: %s", e)
            return [], PROVIDER_ERROR, str(e)

    def fetch_public_page(
        self, url: str, timeout: int = 10
    ) -> Optional[Dict[str, Any]]:
        """Fetch a public company page for evidence extraction.

        Only fetches from public, non-authenticated pages.
        Does NOT bypass login walls, anti-bot, or access restrictions.
        """
        try:
            resp = requests.get(
                url,
                headers={
                    "User-Agent": "Salesoorja-Research/1.0 (Business Intelligence)",
                    "Accept": "text/html",
                },
                timeout=timeout,
                allow_redirects=True,
            )
            if resp.status_code == 200:
                # Basic text extraction (no JS rendering)
                text = resp.text[:50000]
                title_match = re.search(r"<title[^>]*>([^<]+)</title>", text, re.IGNORECASE)
                title = title_match.group(1).strip() if title_match else url

                # Strip HTML tags for plain text
                clean = re.sub(r"<[^>]+>", " ", text)
                clean = re.sub(r"\s+", " ", clean).strip()[:5000]

                return {
                    "url": url,
                    "title": title,
                    "text": clean,
                    "status": "fetched",
                    "status_code": 200,
                }
            elif resp.status_code in (401, 403, 429):
                return {
                    "url": url,
                    "title": "",
                    "text": "",
                    "status": "access_restricted",
                    "status_code": resp.status_code,
                }
            else:
                return {
                    "url": url,
                    "title": "",
                    "text": "",
                    "status": "http_error",
                    "status_code": resp.status_code,
                }
        except Exception as e:
            logger.warning("Public page fetch failed for %s: %s", url, e)
            return None


# Singleton
research_router = ResearchProviderRouter()
