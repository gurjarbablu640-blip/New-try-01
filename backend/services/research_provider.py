"""Serper-only production research with quota-safe local caching."""
from __future__ import annotations

import logging
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

# â”€â”€ Provider Status Constants â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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


# â”€â”€ Common Provider Interface (Phase 5) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

class ResearchProviderRouter:
    """Route every live production search through Serper.

    The in-memory/file cache owned by SerperSearchProvider is checked before
    quota reservation. The database cache remains a local evidence fallback,
    not an external research provider.
    """

    def _discover_providers(self) -> List[Dict[str, Any]]:
        serper_key = str(
            get_setting_value("SERPER_API_KEY", "")
            or getattr(settings, "SERPER_API_KEY", "")
        ).strip()
        is_serper_live = bool(
            serper_key
            and not serper_key.startswith("mock_")
            and not serper_key.startswith("YOUR_")
            and len(serper_key) > 8
        )
        return [
            {
                "name": "serper",
                "display": "Serper Search API",
                "configured": is_serper_live,
                "priority": 1,
            },
            {
                "name": "database_cache",
                "display": "Web Research Cache",
                "configured": True,
                "priority": 2,
            },
        ]

    def get_provider_status(self) -> Dict[str, str]:
        return {
            provider["name"]: (
                PROVIDER_LIVE if provider["configured"] else PROVIDER_NOT_CONFIGURED
            )
            for provider in self._discover_providers()
        }

    def get_best_search_provider(self) -> Optional[str]:
        provider = self._discover_providers()[0]
        return "serper" if provider["configured"] else None

    def search(
        self,
        query: str,
        num_results: int = 5,
        company_id: Optional[int] = None,
        db: Optional[Session] = None,
        free_only: bool = False,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Search with Serper, optionally falling back to stored local evidence."""
        results: List[ResearchResult] = []
        status = PROVIDER_NOT_CONFIGURED
        error: Optional[str] = None
        cache_hit = False
        used_provider = "none"

        serper_key = str(
            get_setting_value("SERPER_API_KEY", "")
            or getattr(settings, "SERPER_API_KEY", "")
        ).strip()
        serper_configured = bool(
            serper_key
            and not serper_key.startswith("mock_")
            and not serper_key.startswith("YOUR_")
        )
        if not free_only and serper_configured:
            used_provider = "serper"
            results, status, error, cache_hit = self._search_serper(
                query, num_results, **kwargs
            )
            if status == PROVIDER_BUDGET_EXHAUSTED:
                return {
                    "provider": "serper",
                    "provider_status": PROVIDER_BUDGET_EXHAUSTED,
                    "results": [],
                    "query": query,
                    "error": error or "SERPER_DAILY_BUDGET_EXHAUSTED",
                    "cache_hit": cache_hit,
                }

        if not results and db and not free_only:
            cached_results, cache_status, cache_error = self._search_database_cache(
                query, db
            )
            if cached_results:
                results = cached_results
                status = PROVIDER_FALLBACK
                error = cache_error
                used_provider = "database_cache"
            elif used_provider == "none":
                status = cache_status
                error = cache_error

        if db and results and used_provider == "serper" and status == PROVIDER_LIVE:
            for result in results:
                try:
                    db.add(
                        WebResearchItem(
                            company_id=company_id,
                            query=query,
                            title=result.title,
                            url=result.url,
                            source_domain=result.source_domain,
                            snippet=result.snippet,
                            confidence=int(result.confidence * 100),
                            evidence_type=result.evidence_type,
                            metadata_json={"provider": result.provider},
                        )
                    )
                except Exception as exc:
                    logger.warning("Failed to cache research result: %s", exc)
            try:
                db.commit()
            except Exception as exc:
                db.rollback()
                logger.warning("Failed to commit research cache: %s", exc)

        return {
            "provider": used_provider,
            "provider_status": status,
            "results": [result.to_dict() for result in results],
            "query": query,
            "error": error,
            "cache_hit": cache_hit,
        }

    def _search_serper(
        self, query: str, num_results: int, **kwargs: Any
    ) -> tuple[list[ResearchResult], str, Optional[str], bool]:
        provider = SerperSearchProvider()
        response = provider.search(query, num_results=num_results, **kwargs)
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
            for item in response.get("results", []) or []
        ]
        return (
            results,
            response.get("provider_status", PROVIDER_ERROR),
            response.get("error"),
            bool(response.get("cache_hit")),
        )

    def _search_database_cache(
        self, query: str, db: Session
    ) -> tuple[list[ResearchResult], str, Optional[str]]:
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
                    title=row.title or "",
                    url=row.url or "",
                    snippet=row.snippet or "",
                    source_domain=row.source_domain or "",
                    confidence=(row.confidence or 50) / 100.0,
                    provider="database_cache",
                )
                for row in rows
            ]
            return (
                results,
                PROVIDER_FALLBACK if results else PROVIDER_NOT_CONFIGURED,
                None,
            )
        except Exception as exc:
            logger.exception("Database cache search error: %s", exc)
            return [], PROVIDER_ERROR, str(exc)


research_router = ResearchProviderRouter()
