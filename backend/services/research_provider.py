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
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import os
import requests
from sqlalchemy.orm import Session

from config import settings
from services.settings_manager import get_setting_value
from models.web_research import WebResearchItem
from services.serper_budget_manager import serper_budget_manager, SerperBudgetExhaustedError

logger = logging.getLogger(__name__)

# ── Provider Status Constants ───────────────────────────────────────────
PROVIDER_LIVE = "LIVE"
PROVIDER_NOT_CONFIGURED = "NOT_CONFIGURED"
PROVIDER_ERROR = "ERROR"
PROVIDER_FALLBACK = "FALLBACK"
PROVIDER_EMPTY = "EMPTY"
PROVIDER_BLOCKED = "BLOCKED"
PROVIDER_QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"
PROVIDER_BUDGET_EXHAUSTED = "SERPER_DAILY_BUDGET_EXHAUSTED"



from abc import ABC, abstractmethod


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
        position: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.title = title
        self.url = url
        self.snippet = snippet
        self.source_domain = source_domain or urlparse(url).netloc
        self.retrieved_at = retrieved_at or datetime.now(timezone.utc).isoformat()
        self.confidence = confidence
        self.evidence_type = evidence_type
        self.provider = provider
        self.position = position
        self.metadata = metadata or {}

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
            "position": self.position,
            "metadata": self.metadata,
        }


# ── Common Provider Interface (Phase 5) ──────────────────────────────────
class ResearchProvider(ABC):
    """Abstract base class for all research and web search providers."""

    @abstractmethod
    def search(self, query: str, num_results: int = 5, **kwargs: Any) -> Dict[str, Any]:
        """Execute search and return normalized result payload:
        {
            "provider": str,
            "provider_status": str,
            "results": list[dict],
            "query": str,
            "error": Optional[str],
            "latency_ms": float,
            "cache_hit": bool,
        }
        """
        pass

    @abstractmethod
    def get_status(self) -> str:
        """Return provider status (LIVE, NOT_CONFIGURED, etc.)."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Return whether provider is currently configured and operational."""
        pass


class SerperSearchProvider(ResearchProvider):
    """Serper.dev Google Search API provider."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout: int = 20,
        cache: Optional[Any] = None,
        budget_manager: Optional[Any] = None,
    ) -> None:
        self._api_key_override = api_key
        self.timeout = timeout
        self.cache = cache
        self.budget_manager = budget_manager

    def _get_api_key(self) -> str:
        if self._api_key_override:
            return self._api_key_override.strip()
        key = str(get_setting_value("SERPER_API_KEY", "") or os.environ.get("SERPER_API_KEY", "")).strip()
        return key

    def is_available(self) -> bool:
        key = self._get_api_key()
        return bool(key and not key.startswith("mock_") and not key.startswith("YOUR_") and len(key) > 8)

    def get_status(self) -> str:
        return PROVIDER_LIVE if self.is_available() else PROVIDER_NOT_CONFIGURED

    def search(self, query: str, num_results: int = 5, **kwargs: Any) -> Dict[str, Any]:
        start_time = time.time()
        key = self._get_api_key()
        if not self.is_available():
            return {
                "provider": "serper",
                "provider_status": PROVIDER_NOT_CONFIGURED,
                "results": [],
                "query": query,
                "error": "Serper API key not configured",
                "latency_ms": 0.0,
                "cache_hit": False,
            }

        mgr = self.budget_manager or kwargs.get("budget_manager") or serper_budget_manager

        # Check cache if provided or available
        cache_instance = self.cache
        if cache_instance is None:
            try:
                from services.search_cache import search_cache
                cache_instance = search_cache
            except Exception:
                cache_instance = None

        use_cache = kwargs.get("use_cache", True)
        if use_cache and cache_instance:
            cached = cache_instance.get("serper", query, num_results=num_results)
            if cached:
                cached["latency_ms"] = round((time.time() - start_time) * 1000, 2)
                # CRITICAL: Cache hits must NOT consume Serper API quota
                try:
                    if mgr:
                        mgr.record_cache_hit(1)
                except Exception as e:
                    logger.debug("Failed to record cache hit: %s", e)
                return cached

        # Check daily/task budget limit BEFORE making live network request
        if mgr and not mgr.can_request():
            mgr.record_budget_exhausted()
            is_task_cap = (
                getattr(mgr, "benchmark_run_limit", None) is not None
                and getattr(mgr, "benchmark_requests_used", 0) >= mgr.benchmark_run_limit
            )
            err_msg = (
                f"SERPER_TASK_BUDGET_EXHAUSTED: Task limit of {mgr.benchmark_run_limit} live requests reached"
                if is_task_cap
                else f"SERPER_DAILY_BUDGET_EXHAUSTED: Daily limit of {getattr(mgr, 'daily_limit', 1500)} live requests reached"
            )
            return {
                "provider": "serper",
                "provider_status": PROVIDER_BUDGET_EXHAUSTED,
                "results": [],
                "query": query,
                "error": err_msg,
                "latency_ms": round((time.time() - start_time) * 1000, 2),
                "cache_hit": False,
            }

        last_err = None
        for attempt in range(2):
            if mgr:
                try:
                    mgr.reserve_request(1)
                except SerperBudgetExhaustedError as be:
                    return {
                        "provider": "serper",
                        "provider_status": PROVIDER_BUDGET_EXHAUSTED,
                        "results": [],
                        "query": query,
                        "error": str(be),
                        "latency_ms": round((time.time() - start_time) * 1000, 2),
                        "cache_hit": False,
                    }

            try:
                req_start = time.time()
                resp = requests.post(
                    "https://google.serper.dev/search",
                    json={"q": query, "num": min(max(int(num_results), 1), 10)},
                    headers={
                        "X-API-KEY": key,
                        "Content-Type": "application/json",
                        "Connection": "close",
                    },
                    timeout=self.timeout,
                )
                latency_ms = round((time.time() - req_start) * 1000, 2)

                if resp.status_code == 200:
                    if mgr:
                        try:
                            mgr.record_successful_request(1)
                        except Exception as me:
                            logger.debug("Failed to record successful request: %s", me)
                    data = resp.json()
                    organic = data.get("organic", []) or []
                    results = []
                    for idx, item in enumerate(organic):
                        item_url = str(item.get("link") or "")
                        pos = item.get("position")
                        if pos is None:
                            pos = idx + 1
                        results.append(
                            ResearchResult(
                                title=str(item.get("title") or ""),
                                url=item_url,
                                snippet=str(item.get("snippet") or ""),
                                provider="serper",
                                confidence=0.85,
                                position=int(pos),
                                metadata={
                                    "serper_position": pos,
                                    "date": item.get("date"),
                                    "sitelinks_count": len(item.get("sitelinks", []) or []),
                                },
                            )
                        )
                    payload = {
                        "provider": "serper",
                        "provider_status": PROVIDER_LIVE if results else PROVIDER_EMPTY,
                        "results": [r.to_dict() for r in results],
                        "query": query,
                        "error": None if results else "Serper returned no organic results",
                        "latency_ms": latency_ms,
                        "cache_hit": False,
                    }
                    if cache_instance:
                        cache_instance.set("serper", query, payload, num_results=num_results)
                    return payload
                elif resp.status_code in (401, 403):
                    if mgr:
                        try:
                            mgr.record_failed_request(1)
                        except Exception as me:
                            logger.debug("Failed to record failed request: %s", me)
                    return {
                        "provider": "serper",
                        "provider_status": PROVIDER_ERROR,
                        "results": [],
                        "query": query,
                        "error": f"Serper auth failed: HTTP {resp.status_code}",
                        "latency_ms": latency_ms,
                        "cache_hit": False,
                    }
                elif resp.status_code == 429:
                    if mgr:
                        try:
                            mgr.record_failed_request(1)
                        except Exception as me:
                            logger.debug("Failed to record failed request: %s", me)
                    return {
                        "provider": "serper",
                        "provider_status": PROVIDER_QUOTA_EXHAUSTED,
                        "results": [],
                        "query": query,
                        "error": "Serper rate limited / quota exhausted: HTTP 429",
                        "latency_ms": latency_ms,
                        "cache_hit": False,
                    }
                else:
                    if mgr:
                        try:
                            mgr.record_failed_request(1)
                        except Exception as me:
                            logger.debug("Failed to record failed request: %s", me)
                    last_err = f"HTTP {resp.status_code}: {resp.text[:200]}"
            except Exception as e:
                if mgr:
                    try:
                        mgr.record_failed_request(1)
                    except Exception as me:
                        logger.debug("Failed to record failed request: %s", me)
                last_err = str(e)
                time.sleep(0.5)

        total_latency = round((time.time() - start_time) * 1000, 2)
        return {
            "provider": "serper",
            "provider_status": PROVIDER_ERROR,
            "results": [],
            "query": query,
            "error": f"Serper search error: {last_err}",
            "latency_ms": total_latency,
            "cache_hit": False,
        }


class GeminiGroundedSearchProvider(ResearchProvider):
    """Google Gemini Grounded Search (Google Search Tool) provider."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gemini-3.5-flash-lite",
        timeout: int = 25,
        cache: Optional[Any] = None,
    ) -> None:
        self._api_key_override = api_key
        self.model = model
        self.timeout = timeout
        self.cache = cache

    def _get_api_key(self) -> str:
        if self._api_key_override:
            return self._api_key_override.strip()
        key = str(
            get_setting_value("GOOGLE_API_KEY", "")
            or get_setting_value("GEMINI_API_KEY", "")
            or os.environ.get("GEMINI_API_KEY", "")
            or os.environ.get("GOOGLE_API_KEY", "")
        ).strip()
        return key

    def is_available(self) -> bool:
        key = self._get_api_key()
        return bool(key and not key.startswith("mock_") and not key.startswith("YOUR_") and len(key) > 10)

    def get_status(self) -> str:
        if not self.is_available():
            return PROVIDER_NOT_CONFIGURED
        return PROVIDER_LIVE

    def search(self, query: str, num_results: int = 5, **kwargs: Any) -> Dict[str, Any]:
        start_time = time.time()
        key = self._get_api_key()
        if not self.is_available():
            return {
                "provider": "gemini_grounded",
                "provider_status": PROVIDER_NOT_CONFIGURED,
                "results": [],
                "query": query,
                "error": "Gemini API key not configured",
                "latency_ms": 0.0,
                "cache_hit": False,
            }

        cache_instance = self.cache
        if cache_instance is None:
            try:
                from services.search_cache import search_cache
                cache_instance = search_cache
            except Exception:
                cache_instance = None

        use_cache = kwargs.get("use_cache", True)
        if use_cache and cache_instance:
            cached = cache_instance.get("gemini_grounded", query, model=self.model)
            if cached:
                cached["latency_ms"] = round((time.time() - start_time) * 1000, 2)
                return cached

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={key}"
        payload = {
            "contents": [{"role": "user", "parts": [{"text": query}]}],
            "tools": [{"google_search": {}}],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 800,
            },
        }

        try:
            req_start = time.time()
            resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=self.timeout)
            latency_ms = round((time.time() - req_start) * 1000, 2)

            if resp.status_code == 200:
                data = resp.json()
                cand = (data.get("candidates") or [{}])[0]
                grounding = cand.get("groundingMetadata") or {}
                chunks = grounding.get("groundingChunks", []) or []
                supports = grounding.get("groundingSupports", []) or []
                queries_executed = grounding.get("webSearchQueries", []) or []

                # Extract chunk text snippet from groundingSupports where available
                chunk_snippets: Dict[int, str] = {}
                for support in supports:
                    seg_text = (support.get("segment") or {}).get("text", "")
                    for c_idx in support.get("groundingChunkIndices", []) or []:
                        if c_idx not in chunk_snippets and seg_text:
                            chunk_snippets[c_idx] = seg_text

                # Synthesized text fallback
                parts = cand.get("content", {}).get("parts", []) or []
                synth_text = parts[0].get("text", "") if parts else ""

                results = []
                for idx, chunk in enumerate(chunks[:num_results]):
                    web_data = chunk.get("web") or {}
                    uri = web_data.get("uri") or ""
                    title = web_data.get("title") or ""
                    snippet = chunk_snippets.get(idx) or synth_text[:300]
                    results.append(
                        ResearchResult(
                            title=title,
                            url=uri,
                            snippet=snippet,
                            provider="gemini_grounded",
                            confidence=0.80,
                            position=idx + 1,
                            evidence_type="GROUNDED_WEB_EVIDENCE",
                            metadata={
                                "model": self.model,
                                "grounding_chunk_index": idx,
                                "web_search_queries": queries_executed,
                            },
                        )
                    )

                status = PROVIDER_LIVE if results else PROVIDER_EMPTY
                out_payload = {
                    "provider": "gemini_grounded",
                    "provider_status": status,
                    "results": [r.to_dict() for r in results],
                    "query": query,
                    "error": None if results else "Gemini returned no grounding chunks",
                    "latency_ms": latency_ms,
                    "model": self.model,
                    "search_queries_run": queries_executed,
                    "cache_hit": False,
                }
                if cache_instance and status == PROVIDER_LIVE:
                    cache_instance.set("gemini_grounded", query, out_payload, model=self.model)
                return out_payload

            elif resp.status_code == 429:
                return {
                    "provider": "gemini_grounded",
                    "provider_status": PROVIDER_QUOTA_EXHAUSTED,
                    "results": [],
                    "query": query,
                    "error": "Gemini Google Search grounding unavailable: HTTP 429 Quota Exceeded (requires paid tier / billing enabled)",
                    "latency_ms": latency_ms,
                    "model": self.model,
                    "cache_hit": False,
                }
            else:
                err_msg = resp.json().get("error", {}).get("message", resp.text[:200]) if resp.text else f"HTTP {resp.status_code}"
                return {
                    "provider": "gemini_grounded",
                    "provider_status": PROVIDER_ERROR,
                    "results": [],
                    "query": query,
                    "error": f"Gemini API error ({resp.status_code}): {err_msg}",
                    "latency_ms": latency_ms,
                    "model": self.model,
                    "cache_hit": False,
                }

        except Exception as e:
            total_latency = round((time.time() - start_time) * 1000, 2)
            return {
                "provider": "gemini_grounded",
                "provider_status": PROVIDER_ERROR,
                "results": [],
                "query": query,
                "error": f"Gemini request exception: {str(e)}",
                "latency_ms": total_latency,
                "model": self.model,
                "cache_hit": False,
            }


class SearXNGProvider(ResearchProvider):
    """SearXNG self-hosted private search provider."""

    def __init__(self, base_url: Optional[str] = None, timeout: int = 16) -> None:
        self.base_url = base_url
        self.timeout = timeout

    def is_available(self) -> bool:
        candidates = research_router._get_candidate_searxng_urls() if "research_router" in globals() else []
        return bool(candidates or self.base_url)

    def get_status(self) -> str:
        return PROVIDER_LIVE if self.is_available() else PROVIDER_NOT_CONFIGURED

    def search(self, query: str, num_results: int = 5, **kwargs: Any) -> Dict[str, Any]:
        start_time = time.time()
        results, status, error = research_router._search_searxng(query, num_results)
        latency_ms = round((time.time() - start_time) * 1000, 2)
        return {
            "provider": "searxng",
            "provider_status": status,
            "results": [r.to_dict() for r in results],
            "query": query,
            "error": error,
            "latency_ms": latency_ms,
            "cache_hit": False,
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

        # 1. Serper Search API (Primary production search provider)
        serper_key = str(get_setting_value("SERPER_API_KEY", "") or getattr(settings, "SERPER_API_KEY", "")).strip()
        is_serper_live = bool(serper_key and not serper_key.startswith("mock_") and not serper_key.startswith("YOUR_") and len(serper_key) > 8)
        providers.append({
            "name": "serper",
            "display": "Serper Search API",
            "configured": is_serper_live,
            "priority": 1,
        })

        # 2. Google Custom Search (secondary if Serper not configured)
        google_key = str(get_setting_value("GOOGLE_API_KEY", "") or getattr(settings, "GOOGLE_API_KEY", "")).strip()
        google_cx = str(get_setting_value("GOOGLE_SEARCH_CX", "") or getattr(settings, "GOOGLE_SEARCH_CX", "")).strip()
        is_google_live = bool(google_key and google_cx and not google_key.startswith("mock_") and not google_key.startswith("YOUR_"))
        providers.append({
            "name": "google_custom_search",
            "display": "Google Custom Search",
            "configured": is_google_live,
            "priority": 2,
        })

        # 3. SearXNG Private Self-Hosted Search (OPTIONAL fallback, disabled by default)
        auto_fallback = bool(getattr(settings, "SEARXNG_AUTO_FALLBACK", False))
        searxng_url = str(getattr(settings, "SEARXNG_BASE_URL", "") or get_setting_value("SEARXNG_BASE_URL", "http://localhost:8080")).strip()
        providers.append({
            "name": "searxng",
            "display": "SearXNG Private Search",
            "configured": bool(searxng_url) and auto_fallback,
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
            if p["configured"] and p["name"] in ("serper", "google_custom_search", "searxng"):
                return p["name"]
        return None

    def search(
        self,
        query: str,
        num_results: int = 5,
        company_id: Optional[int] = None,
        db: Optional[Session] = None,
        free_only: bool = False,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Execute a search using the best available provider with automatic fallback.

        Priority order:
        1. Serper API (Primary production search)
        2. Google Custom Search (Secondary if configured and Serper missing)
        3. SearXNG Private Instance (OPTIONAL fallback, disabled by default)
        4. Database Cache
        """
        results = []
        status = PROVIDER_NOT_CONFIGURED
        error = None
        used_provider = "none"

        # 1. Serper API (Primary)
        serper_key = str(get_setting_value("SERPER_API_KEY", "") or getattr(settings, "SERPER_API_KEY", "")).strip()
        if not free_only and serper_key and not serper_key.startswith("mock_") and not serper_key.startswith("YOUR_"):
            results, status, error = self._search_serper(query, num_results, **kwargs)
            if status == PROVIDER_LIVE:
                used_provider = "serper"
            elif status == PROVIDER_BUDGET_EXHAUSTED:
                # When Serper daily budget is exhausted, do NOT fall back to SearXNG
                return {
                    "provider": "serper",
                    "provider_status": PROVIDER_BUDGET_EXHAUSTED,
                    "results": [],
                    "query": query,
                    "error": error or "SERPER_DAILY_BUDGET_EXHAUSTED",
                }

        # 2. Google Custom Search (secondary if Serper not configured)
        if not results and used_provider != "serper":
            google_key = str(get_setting_value("GOOGLE_API_KEY", "")).strip()
            google_cx = str(get_setting_value("GOOGLE_SEARCH_CX", "")).strip()
            if not free_only and google_key and google_cx and not google_key.startswith("mock_") and not google_key.startswith("YOUR_"):
                results, status, error = self._search_google(query, num_results)
                if status == PROVIDER_LIVE:
                    used_provider = "google_custom_search"

        # 3. SearXNG fallback (OPTIONAL only; disabled by default in production; allowed when free_only=True or explicitly requested)
        searxng_allowed = bool(
            free_only
            or kwargs.get("allow_searxng_fallback", False)
            or getattr(settings, "SEARXNG_AUTO_FALLBACK", False)
        )
        if not results and searxng_allowed and used_provider == "none":
            results, status, error = self._search_searxng(query, num_results)
            if status == PROVIDER_LIVE:
                used_provider = "searxng"

        # 4. Database Cache fallback
        if not results and db and not free_only:
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

    _cached_searxng_base: Optional[str] = None

    def _get_candidate_searxng_urls(self) -> list[str]:
        """Return candidate SearXNG base URLs in priority order."""
        if getattr(self, "_cached_searxng_base", None):
            return [self._cached_searxng_base]
        if getattr(ResearchProviderRouter, "_cached_searxng_base", None):
            return [ResearchProviderRouter._cached_searxng_base]

        candidate_urls = []
        if os.name == "nt":
            try:
                import subprocess
                wsl_out = subprocess.check_output(
                    ["wsl", "-d", "docker-desktop", "-e", "/bin/sh", "-c", "ip addr show eth0"],
                    timeout=2,
                    stderr=subprocess.DEVNULL,
                ).decode("utf-8", errors="ignore")
                m = re.search(r"inet\s+([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)", wsl_out)
                if m:
                    candidate_urls.append(f"http://{m.group(1)}:8080")
            except Exception:
                pass

        candidate_urls.extend([
            os.environ.get("SEARXNG_BASE_URL", "").rstrip("/"),
            str(getattr(settings, "SEARXNG_BASE_URL", "")).rstrip("/"),
            "http://searxng:8080",
            "http://localhost:8080",
        ])
        return list(dict.fromkeys(u for u in candidate_urls if u))

    def get_searxng_base_url(self) -> Optional[str]:
        """Detect and return the working SearXNG base URL."""
        candidates = self._get_candidate_searxng_urls()
        return candidates[0] if candidates else None

    def _search_searxng(
        self, query: str, num_results: int = 5
    ) -> tuple[list[ResearchResult], str, Optional[str]]:
        """Search via self-hosted SearXNG instance."""
        candidate_urls = self._get_candidate_searxng_urls()

        for base in candidate_urls:
            url = f"{base}/search"
            params = {
                "q": query,
                "format": "json",
                "categories": "general,news",
                "engines": "bing,yandex,bing news",
                "language": "en-IN",
            }
            try:
                resp = requests.get(url, params=params, timeout=16)
                if resp.status_code == 200:
                    ResearchProviderRouter._cached_searxng_base = base
                    self._cached_searxng_base = base
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
                    if data.get("unresponsive_engines"):
                        return [], PROVIDER_ERROR, "SearXNG search engines unavailable"
                    return [], PROVIDER_EMPTY, "SearXNG returned no matching results"
            except Exception as e:
                logger.debug("SearXNG connection failed: %s", type(e).__name__)
                continue
        return [], PROVIDER_ERROR, "SearXNG unavailable"


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
        self, query: str, num_results: int, **kwargs: Any
    ) -> tuple[list[ResearchResult], str, Optional[str]]:
        """Search via Serper.dev API using SerperSearchProvider with budget management."""
        provider = SerperSearchProvider()
        res = provider.search(query, num_results=num_results, **kwargs)
        raw_results = res.get("results", []) or []
        results = [
            ResearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("snippet", ""),
                provider="serper",
                confidence=float(item.get("confidence", 0.85)),
                position=item.get("position"),
                metadata=item.get("metadata"),
            )
            for item in raw_results
        ]
        return results, res.get("provider_status", PROVIDER_ERROR), res.get("error")

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
