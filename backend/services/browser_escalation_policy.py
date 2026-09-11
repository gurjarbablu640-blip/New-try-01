"""Browser Escalation Policy — Deterministic criteria for DeerFlow deep-browser invocation.

SearXNG → Crawl4AI → sufficient evidence?
  YES → continue normal pipeline
  NO / JS-heavy / navigation required → DeerFlow browser escalation

This module provides the decision function and tracking for browser escalation.

INVARIANTS:
1. DeerFlow is NEVER invoked for ordinary static pages that Crawl4AI can handle.
2. Escalation must be justified by specific, observable evidence gap criteria.
3. Every escalation attempt is tracked: reason, latency, success/failure.
4. If DeerFlow is disabled/unreachable, escalation records the gap but does NOT block the pipeline.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class EscalationReason(str, Enum):
    """Deterministic criteria for when browser escalation is justified."""
    JS_RENDERED_EMPTY = "JS_RENDERED_EMPTY"           # Crawl4AI returned empty/stub text from JS-rendered page
    CRITICAL_CONTENT_MISSING = "CRITICAL_CONTENT_MISSING"  # Expected content (facility, person, trigger) not found
    MULTI_CLICK_NAVIGATION = "MULTI_CLICK_NAVIGATION"      # Content behind tabs/accordions/pagination
    FACILITY_TAB_HIDDEN = "FACILITY_TAB_HIDDEN"            # Plant/facility info behind interactive UI
    CAREERS_SEARCH_INTERFACE = "CAREERS_SEARCH_INTERFACE"   # Job postings behind search forms
    PROFESSIONAL_PROFILE_NAVIGATION = "PROFESSIONAL_PROFILE_NAVIGATION"  # Public professional pages needing navigation
    DYNAMIC_CONTENT_LOAD = "DYNAMIC_CONTENT_LOAD"          # Content loads via AJAX/lazy-load
    CAPTCHA_OR_LOGIN_WALL = "CAPTCHA_OR_LOGIN_WALL"        # Page requires CAPTCHA/login (handoff to manual)


# Escalation is NOT justified for:
# - Ordinary HTML pages that render fine with HTTP fetch
# - PDF documents (handled by document_extraction)
# - Pages that already yield sufficient evidence from SearXNG snippets
# - Social media profile scraping (ethical boundary)


@dataclass
class EscalationDecision:
    """Result of evaluating whether browser escalation is warranted."""
    should_escalate: bool
    reason: Optional[EscalationReason] = None
    evidence_gap: str = ""
    company: str = ""
    url: str = ""
    crawl4ai_result_length: int = 0
    expected_content_type: str = ""
    requires_manual_action: bool = False  # True for CAPTCHA/login
    manual_action_type: Optional[str] = None


@dataclass
class EscalationRecord:
    """Audit record for a browser escalation attempt."""
    company: str
    url: str
    reason: EscalationReason
    escalation_time: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    crawl4ai_text_length: int = 0
    deerflow_text_length: int = 0
    deerflow_success: bool = False
    deerflow_latency_ms: int = 0
    evidence_gained: str = ""
    crawler_used: str = "crawl4ai"
    deerflow_escalated: bool = True
    browser_success: bool = False
    browser_latency_ms: int = 0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "company": self.company,
            "url": self.url,
            "reason": self.reason.value if isinstance(self.reason, EscalationReason) else str(self.reason),
            "escalation_time": self.escalation_time,
            "crawl4ai_text_length": self.crawl4ai_text_length,
            "deerflow_text_length": self.deerflow_text_length,
            "deerflow_success": self.deerflow_success,
            "deerflow_latency_ms": self.deerflow_latency_ms,
            "evidence_gained": self.evidence_gained,
            "crawler_used": self.crawler_used,
            "deerflow_escalated": self.deerflow_escalated,
            "browser_success": self.browser_success,
            "browser_latency_ms": self.browser_latency_ms,
            "error": self.error,
        }


# ── Minimum content thresholds for escalation decision ──────────────────

MIN_USEFUL_TEXT_LENGTH = 200       # Characters; below this, page is likely JS-rendered stub
MIN_TRIGGER_EVIDENCE_WORDS = 30   # If trigger search yields < this, evidence is weak
FACILITY_KEYWORDS = {"plant", "factory", "facility", "manufacturing", "production", "works", "campus", "site"}
PERSON_KEYWORDS = {"manager", "head", "director", "vp", "gm", "engineer", "officer", "lead", "chief"}


def evaluate_escalation_need(
    *,
    company: str,
    url: str,
    crawl4ai_text: str = "",
    crawl4ai_status: str = "",
    searxng_snippet: str = "",
    expected_content: str = "facility_and_person",
    page_has_js_framework: bool = False,
) -> EscalationDecision:
    """Evaluate whether browser escalation to DeerFlow is warranted.

    Uses deterministic, auditable criteria — not heuristic guessing.
    """
    text = (crawl4ai_text or "").strip()
    text_len = len(text)
    text_lower = text.lower()

    # Case 1: Crawl4AI returned empty or near-empty from a page that should have content
    if crawl4ai_status in ("DISABLED", "UNAVAILABLE", "FAILED") or text_len < MIN_USEFUL_TEXT_LENGTH:
        if page_has_js_framework or text_len < 50:
            return EscalationDecision(
                should_escalate=True,
                reason=EscalationReason.JS_RENDERED_EMPTY,
                evidence_gap=f"Crawl4AI returned {text_len} chars (min {MIN_USEFUL_TEXT_LENGTH}); likely JS-rendered page",
                company=company,
                url=url,
                crawl4ai_result_length=text_len,
                expected_content_type=expected_content,
            )

    # Case 2: CAPTCHA or login wall detected
    captcha_signals = ["captcha", "recaptcha", "verify you are human", "access denied", "please sign in", "log in to continue"]
    if any(sig in text_lower for sig in captcha_signals):
        return EscalationDecision(
            should_escalate=False,  # Don't escalate to DeerFlow for CAPTCHA — needs manual action
            reason=EscalationReason.CAPTCHA_OR_LOGIN_WALL,
            evidence_gap="CAPTCHA or login wall detected; requires manual browser action",
            company=company,
            url=url,
            crawl4ai_result_length=text_len,
            requires_manual_action=True,
            manual_action_type="MANUAL_BROWSER_ACTION_REQUIRED",
        )

    # Case 3: Expected content type not found in extracted text
    if expected_content == "facility_and_person":
        has_facility = any(kw in text_lower for kw in FACILITY_KEYWORDS)
        has_person = any(kw in text_lower for kw in PERSON_KEYWORDS)

        if not has_facility and not has_person and text_len > MIN_USEFUL_TEXT_LENGTH:
            return EscalationDecision(
                should_escalate=True,
                reason=EscalationReason.CRITICAL_CONTENT_MISSING,
                evidence_gap="Page rendered but lacks facility and person keywords; content may be behind tabs/navigation",
                company=company,
                url=url,
                crawl4ai_result_length=text_len,
                expected_content_type=expected_content,
            )

    elif expected_content == "facility_details":
        has_facility = any(kw in text_lower for kw in FACILITY_KEYWORDS)
        if not has_facility and text_len > MIN_USEFUL_TEXT_LENGTH:
            return EscalationDecision(
                should_escalate=True,
                reason=EscalationReason.FACILITY_TAB_HIDDEN,
                evidence_gap="Page rendered but facility details not found; likely behind interactive UI",
                company=company,
                url=url,
                crawl4ai_result_length=text_len,
                expected_content_type=expected_content,
            )

    elif expected_content == "careers":
        if "search" in text_lower and ("apply" in text_lower or "job" in text_lower) and text_len < 500:
            return EscalationDecision(
                should_escalate=True,
                reason=EscalationReason.CAREERS_SEARCH_INTERFACE,
                evidence_gap="Careers page appears to have search interface needing interaction",
                company=company,
                url=url,
                crawl4ai_result_length=text_len,
                expected_content_type=expected_content,
            )

    # Default: no escalation needed — Crawl4AI/SearXNG evidence is sufficient
    return EscalationDecision(
        should_escalate=False,
        reason=None,
        evidence_gap="",
        company=company,
        url=url,
        crawl4ai_result_length=text_len,
        expected_content_type=expected_content,
    )


class BrowserEscalationTracker:
    """Tracks all escalation decisions and outcomes for the session."""

    def __init__(self):
        self._records: List[EscalationRecord] = []
        self._manual_queue: List[Dict[str, Any]] = []

    def record_escalation(self, record: EscalationRecord) -> None:
        self._records.append(record)

    def add_manual_action_required(
        self,
        company: str,
        url: str,
        reason: str,
        task_id: str = "",
        resume_point: str = "",
    ) -> Dict[str, Any]:
        """Queue a manual browser action requirement."""
        entry = {
            "task_id": task_id,
            "company": company,
            "url": url,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "resume_point": resume_point,
            "status": "MANUAL_BROWSER_ACTION_REQUIRED",
        }
        self._manual_queue.append(entry)
        logger.warning(
            "MANUAL_BROWSER_ACTION_REQUIRED: %s at %s — %s",
            company, url, reason,
        )
        return entry

    @property
    def escalation_count(self) -> int:
        return len(self._records)

    @property
    def success_count(self) -> int:
        return sum(1 for r in self._records if r.deerflow_success)

    @property
    def manual_queue(self) -> List[Dict[str, Any]]:
        return list(self._manual_queue)

    def get_summary(self) -> Dict[str, Any]:
        total = len(self._records)
        successes = self.success_count
        reasons = {}
        for r in self._records:
            key = r.reason.value if isinstance(r.reason, EscalationReason) else str(r.reason)
            reasons[key] = reasons.get(key, 0) + 1

        avg_latency = 0
        if total:
            avg_latency = sum(r.deerflow_latency_ms for r in self._records) // max(total, 1)

        return {
            "total_escalations": total,
            "successful": successes,
            "failed": total - successes,
            "escalation_rate": f"{successes}/{total}" if total else "0/0",
            "average_latency_ms": avg_latency,
            "reason_distribution": reasons,
            "manual_queue_length": len(self._manual_queue),
        }

    def to_records_list(self) -> List[Dict[str, Any]]:
        return [r.to_dict() for r in self._records]


# Global tracker instance
escalation_tracker = BrowserEscalationTracker()
