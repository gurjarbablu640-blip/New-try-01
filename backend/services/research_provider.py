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

import requests
from sqlalchemy.orm import Session

from config import settings
from models.web_research import WebResearchItem

logger = logging.getLogger(__name__)

# ── Provider Status Constants ───────────────────────────────────────────
PROVIDER_LIVE = "LIVE"
PROVIDER_NOT_CONFIGURED = "NOT_CONFIGURED"
PROVIDER_ERROR = "ERROR"
PROVIDER_FALLBACK = "FALLBACK"


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

    def __init__(self):
        self._providers = self._discover_providers()

    def _discover_providers(self) -> List[Dict[str, Any]]:
        """Discover which research providers are configured and available."""
        providers = []

        # Google Custom Search
        google_key = getattr(settings, "GOOGLE_API_KEY", "").strip()
        google_cx = getattr(settings, "GOOGLE_SEARCH_CX", "").strip()
        providers.append({
            "name": "google_custom_search",
            "display": "Google Custom Search",
            "configured": bool(google_key and google_cx),
            "priority": 1,
        })

        # Serper
        serper_key = getattr(settings, "SERPER_API_KEY", "").strip()
        providers.append({
            "name": "serper",
            "display": "Serper Search API",
            "configured": bool(serper_key),
            "priority": 2,
        })

        # Direct public page fetch (always available)
        providers.append({
            "name": "public_page_fetch",
            "display": "Public Company Page Fetch",
            "configured": True,
            "priority": 3,
        })

        # Database cache (always available)
        providers.append({
            "name": "database_cache",
            "display": "Web Research Cache",
            "configured": True,
            "priority": 4,
        })

        return sorted(providers, key=lambda p: p["priority"])

    def get_provider_status(self) -> Dict[str, str]:
        """Return status of all providers."""
        return {
            p["name"]: PROVIDER_LIVE if p["configured"] else PROVIDER_NOT_CONFIGURED
            for p in self._providers
        }

    def get_best_search_provider(self) -> Optional[str]:
        """Return the name of the best available search provider."""
        for p in self._providers:
            if p["configured"] and p["name"] in ("google_custom_search", "serper"):
                return p["name"]
        return None

    def search(
        self,
        query: str,
        num_results: int = 5,
        company_id: Optional[int] = None,
        db: Optional[Session] = None,
    ) -> Dict[str, Any]:
        """Execute a search using the best available provider.

        Returns:
            {
                "provider": "google_custom_search" | "serper" | "database_cache",
                "provider_status": "LIVE" | "FALLBACK" | "NOT_CONFIGURED",
                "results": [ResearchResult.to_dict(), ...],
                "query": str,
                "error": str | None,
            }
        """
        best = self.get_best_search_provider()

        if best == "google_custom_search":
            results, status, error = self._search_google(query, num_results)
            if status == PROVIDER_ERROR and self._providers[1]["configured"]:
                # Fallback to Serper
                results, status, error = self._search_serper(query, num_results)
                best = "serper"
                status = PROVIDER_FALLBACK if status == PROVIDER_LIVE else status
        elif best == "serper":
            results, status, error = self._search_serper(query, num_results)
        else:
            # No search API configured — try database cache
            if db:
                results, status, error = self._search_database_cache(query, db)
                best = "database_cache"
            else:
                return {
                    "provider": "none",
                    "provider_status": PROVIDER_NOT_CONFIGURED,
                    "results": [],
                    "query": query,
                    "error": "No search provider configured. Configure GOOGLE_API_KEY + GOOGLE_SEARCH_CX or SERPER_API_KEY in Settings.",
                }

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
            "provider": best or "none",
            "provider_status": status,
            "results": [r.to_dict() for r in results],
            "query": query,
            "error": error,
        }

    def _search_google(
        self, query: str, num_results: int
    ) -> tuple[list[ResearchResult], str, Optional[str]]:
        """Search via Google Custom Search JSON API."""
        api_key = getattr(settings, "GOOGLE_API_KEY", "").strip()
        cx = getattr(settings, "GOOGLE_SEARCH_CX", "").strip()

        if not api_key or not cx:
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
        api_key = getattr(settings, "SERPER_API_KEY", "").strip()

        if not api_key:
            return [], PROVIDER_NOT_CONFIGURED, "Serper API key not configured"

        try:
            resp = requests.post(
                "https://google.serper.dev/search",
                json={"q": query, "num": min(num_results, 10)},
                headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
                timeout=15,
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
            return results, PROVIDER_LIVE, None

        except Exception as e:
            logger.exception("Serper search error: %s", e)
            return [], PROVIDER_ERROR, str(e)

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
