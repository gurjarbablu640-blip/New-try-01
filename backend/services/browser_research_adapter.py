"""Salesoorja Browser Research Adapter (Playwright Chromium Engine).

Communicates with the isolated containerized browser_research_service (port 8001).
Provides deterministic browser rendering, JS hydration, multi-step link traversal,
and security challenge detection without marketing misnomers.

Official ByteDance DeerFlow is tracked separately as BLOCKED_BY_LLM_PROVIDER.
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from config import settings

logger = logging.getLogger(__name__)

OFFICIAL_DEERFLOW_STATUS = "WAITING_FOR_VERIFIED_ZERO_COST_MODEL"
OFFICIAL_DEERFLOW_BLOCKER = (
    "Official ByteDance DeerFlow 2.x supports multiple LangChain-compatible model "
    "provider classes. However, under Salesoorja's strict zero-paid-LLM policy "
    "(LLM_COST_POLICY=ZERO_COST_ONLY, ALLOW_PAID_LLM=false), no zero-cost provider "
    "endpoint is currently verified/configured for it on this host. "
    "Deterministic browser extraction is handled by BrowserResearchAdapter."
)


class BrowserResearchAdapter:
    """HTTP Client and boundary adapter for Salesoorja's Playwright browser research worker."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        enabled: Optional[bool] = None,
        timeout_seconds: Optional[int] = None,
    ):
        # Supports BROWSER_RESEARCH_BASE_URL with fallback to DEERFLOW_BASE_URL
        env_url = os.getenv("BROWSER_RESEARCH_BASE_URL") or getattr(settings, "DEERFLOW_BASE_URL", "http://deerflow:8001")
        self.base_url = (base_url or env_url).rstrip("/")
        self.enabled = enabled if enabled is not None else getattr(settings, "DEERFLOW_ENABLED", True)
        self.timeout = timeout_seconds or getattr(settings, "DEERFLOW_TIMEOUT_SECONDS", 60)

    def get_status(self) -> Dict[str, Any]:
        """Check reachability and health of the browser research service."""
        if not self.enabled:
            return {
                "status": "disabled",
                "service": "browser_research_service",
                "base_url": self.base_url,
                "reachable": False,
                "official_deerflow_status": OFFICIAL_DEERFLOW_STATUS,
                "message": "Browser research adapter is disabled in configuration.",
            }

        url = f"{self.base_url}/health"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Salesoorja-BrowserAdapter/1.0", "Accept": "application/json"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=min(self.timeout, 5)) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return {
                    "status": "healthy",
                    "service": data.get("service", "browser_research_service"),
                    "base_url": self.base_url,
                    "reachable": True,
                    "version": data.get("version", "1.0.0-playwright"),
                    "engine": data.get("engine", "playwright-chromium"),
                    "official_bytedance_deerflow_installed": False,
                    "official_deerflow_status": OFFICIAL_DEERFLOW_STATUS,
                    "capabilities": data.get("capabilities", [
                        "deterministic_browser",
                        "js_hydration",
                        "multi_step_navigation",
                        "challenge_detection",
                    ]),
                }
        except Exception as exc:
            return {
                "status": "unreachable",
                "service": "browser_research_service",
                "base_url": self.base_url,
                "reachable": False,
                "official_deerflow_status": OFFICIAL_DEERFLOW_STATUS,
                "error": f"{type(exc).__name__}: {exc}",
                "fallback_active": True,
            }

    def dispatch_research_task(
        self,
        company_name: str,
        domain: Optional[str] = None,
        target_urls: Optional[List[str]] = None,
        task_type: str = "browser_research",
        focus_areas: Optional[List[str]] = None,
        facility: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Dispatch a deterministic browser extraction job to the browser research container."""
        task_id = f"br-task-{uuid.uuid4().hex[:12]}"
        payload = {
            "task_id": task_id,
            "task_type": task_type,
            "company_name": company_name,
            "domain": domain or "",
            "target_urls": target_urls or [],
            "focus_areas": focus_areas or ["plants", "facilities", "quality"],
            "facility": facility or "",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        if not self.enabled:
            logger.info("Browser research service disabled; falling back for %s", company_name)
            return self._local_fallback(payload)

        url = f"{self.base_url}/api/tasks"
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Salesoorja-BrowserAdapter/1.0",
                "Accept": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return {
                    "task_id": task_id,
                    "status": result.get("status", "completed"),
                    "provider": "browser_research_service",
                    "execution_mode": "remote_container",
                    "data": result,
                }
        except Exception as exc:
            logger.warning("Browser research dispatch failed (%s); engaging safe fallback", exc)
            return self._local_fallback(payload, error_detail=str(exc))

    def navigate_url(
        self,
        url: str,
        company_name: str = "",
        follow_links: bool = True,
        keywords: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Direct browser navigation to inspect a single URL with optional link following."""
        endpoint = f"{self.base_url}/api/browser/navigate"
        payload = {
            "url": url,
            "company_name": company_name,
            "follow_links": follow_links,
            "link_keywords": keywords or ["facility", "plant", "location", "quality"],
        }
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            endpoint,
            data=body,
            headers={"Content-Type": "application/json", "User-Agent": "Salesoorja-BrowserAdapter/1.0"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            logger.warning("Direct navigation failed for %s: %s", url, exc)
            return {"status": "error", "url": url, "error": str(exc), "browser_launched": False}

    def _local_fallback(self, payload: Dict[str, Any], error_detail: Optional[str] = None) -> Dict[str, Any]:
        return {
            "task_id": payload["task_id"],
            "status": "fallback_completed",
            "provider": "salesoorja_static_fallback",
            "execution_mode": "local",
            "error_detail": error_detail,
            "data": {
                "extracted_text": "",
                "unique_evidence": [],
                "actions_performed": ["static_fallback_activated"],
            },
        }


# Global instance
browser_research_adapter = BrowserResearchAdapter()
