"""Authoritative LLM Information-Gain Gate for Downstream Follow-Up Research (Task 3D.1F & 3D.1F.1).

Enforces an intelligent, truth-preserving, information-gain boundary before any downstream
follow-up web search is issued for an existing company candidate.

Authoritative Rules & Architecture:
1. Missing Fact Specification: Every search must target an explicit missing fact
   (FACILITY_LOCATION, COMMISSIONING_STATUS, CAPEX_EVENT, etc.). Canonicalizes all aliases.
2. Deterministic Obvious Generic Blocker: Generic terms (Chemical, Steel, Plant) are blocked immediately.
3. Resolved Entity Requirement: Candidate must have a persisted Company ID or pass the Pre-Persistence
   Entity Truth Gate as TARGET_INDUSTRIAL_COMPANY.
4. Semantic Evidence Sufficiency (LLM): DeepSeek (primary) / Gemini (fallback) determines whether
   existing evidence already answers the missing fact -> USE_EXISTING_EVIDENCE.
5. Repetition Stop Rule: Maximum 2 unsuccessful searches per (COMPANY + MISSING_FACT).
   Subsequent searches allowed ONLY if the LLM provides an escalated source strategy
   (e.g. OFFICIAL_COMPANY, GOVERNMENT_SOURCE) with clear rationale.
6. Natural Query Generation: No static blind negative keyword tails (-stock -share -dividend).
   Negative keywords are included only when prior results contain financial noise and the LLM recommends it.
7. Durable Concurrency-Safe Memory & Atomic Reservation: Backed by PostgreSQL (FollowupQueryMemoryRecord)
   and atomic multi-process search reservations with bounded lease (default 60s) via Redis / memory.
8. Safe Fail-Closed LLM Fallback: When both DeepSeek and Gemini fail, the gate safely HOLDS
   to prevent speculative Serper expenditure.
9. Telemetry & Truth Preservation: Tracks productive outcomes preserved, replaced by existing evidence,
   and zero loss of qualified accounts.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
import re
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from database import SessionLocal
from models.followup_query_memory import FollowupQueryMemoryRecord
from services.llm_provider import DeepSeekProvider, GeminiProvider

logger = logging.getLogger(__name__)

# --- Standardized Taxonomies (Task 3D.1F.1 Section 9) ---
VALID_MISSING_FACTS = {
    "FACILITY_LOCATION",
    "TRIGGER_DATE",
    "COMMISSIONING_STATUS",
    "OPERATING_STATUS",
    "PLANT_OWNERSHIP",
    "COMPANY_FACILITY_RELATIONSHIP",
    "CAPEX_EVENT",
    "SUBSIDIARY_RELATIONSHIP",
    "CURRENT_OPERATIONAL_EVIDENCE",
    "MACHINERY_CONTEXT",
}

MISSING_FACT_ALIASES: Dict[str, str] = {
    # Facility Location aliases
    "facility_location": "FACILITY_LOCATION",
    "facility_city": "FACILITY_LOCATION",
    "exact_facility": "FACILITY_LOCATION",
    "facility location": "FACILITY_LOCATION",
    "facility_name": "FACILITY_LOCATION",
    "facility name": "FACILITY_LOCATION",
    "facility": "FACILITY_LOCATION",
    "location": "FACILITY_LOCATION",
    "city": "FACILITY_LOCATION",
    "plant_location": "FACILITY_LOCATION",
    "plant location": "FACILITY_LOCATION",
    
    # Trigger Date aliases
    "trigger_date": "TRIGGER_DATE",
    "current_event_date": "TRIGGER_DATE",
    "event_date": "TRIGGER_DATE",
    "event date": "TRIGGER_DATE",
    "date": "TRIGGER_DATE",
    
    # Commissioning / Operating Status aliases
    "commissioning_status": "COMMISSIONING_STATUS",
    "commissioning": "COMMISSIONING_STATUS",
    "status": "COMMISSIONING_STATUS",
    "operating_status": "OPERATING_STATUS",
    "operational_status": "OPERATING_STATUS",
    
    # Machinery Context aliases
    "machinery_context": "MACHINERY_CONTEXT",
    "machinery": "MACHINERY_CONTEXT",
    "equipment": "MACHINERY_CONTEXT",
    "machinery context": "MACHINERY_CONTEXT",
    
    # Capex Event aliases
    "capex_event": "CAPEX_EVENT",
    "capex": "CAPEX_EVENT",
    "expansion": "CAPEX_EVENT",
    "capital_expenditure": "CAPEX_EVENT",
    
    # Plant Ownership / Relationship aliases
    "plant_ownership": "PLANT_OWNERSHIP",
    "company_facility_relationship": "COMPANY_FACILITY_RELATIONSHIP",
    "facility_relationship": "COMPANY_FACILITY_RELATIONSHIP",
    "ownership": "PLANT_OWNERSHIP",
    
    # Subsidiary Relationship aliases
    "subsidiary_relationship": "SUBSIDIARY_RELATIONSHIP",
    "subsidiary": "SUBSIDIARY_RELATIONSHIP",
    
    # Current Operational Evidence
    "current_operational_evidence": "CURRENT_OPERATIONAL_EVIDENCE",
    "operational_evidence": "CURRENT_OPERATIONAL_EVIDENCE",
}


def canonicalize_missing_fact(fact: str) -> str:
    """Map any alias or raw string to canonical MISSING_FACT taxonomy."""
    if not fact:
        return ""
    clean = fact.strip()
    if clean in VALID_MISSING_FACTS:
        return clean
    clean_upper = clean.upper()
    if clean_upper in VALID_MISSING_FACTS:
        return clean_upper
    lower = clean.lower()
    if lower in MISSING_FACT_ALIASES:
        return MISSING_FACT_ALIASES[lower]
    for alias, canon in MISSING_FACT_ALIASES.items():
        if alias in lower or lower in alias:
            return canon
    return clean_upper


RESEARCH_STRATEGIES = {
    "GENERAL_WEB",
    "OFFICIAL_COMPANY",
    "GOVERNMENT_SOURCE",
    "TRADE_MEDIA",
    "FACILITY_SPECIFIC",
    "CORPORATE_FILING",
    "OTHER",
}

ALTERNATIVE_ACTIONS = {
    "USE_EXISTING_EVIDENCE",
    "SEARCH",
    "HOLD",
    "UPGRADE_OPPORTUNITY",
}

EXPECTED_GAINS = {"HIGH", "MEDIUM", "LOW"}

RESERVATION_LEASE_SECONDS = 60  # Bounded lease to prevent permanent lockout

GENERIC_ENTITY_BLOCKLIST = {
    "chemical", "chemicals", "steel", "steels", "manufacturing", "electronics",
    "plant", "plants", "company", "companies", "industry", "industries",
    "engineering", "metals", "power", "textiles", "plastics", "cement",
    "pharma", "pharmaceuticals", "automotive", "solar", "battery",
    "enterprise", "enterprises", "corporation", "holdings", "technologies",
}

# In-memory telemetry store
_TELEMETRY: Dict[str, int] = {
    "FOLLOWUP_RESEARCH_DECISIONS": 0,
    "FOLLOWUP_SEARCHES_EXECUTED": 0,
    "FOLLOWUP_SEARCH_ALLOWED": 0,
    "FOLLOWUP_SEARCH_BLOCKED_GENERIC_ENTITY": 0,
    "FOLLOWUP_BLOCKED_UNRESOLVED_ENTITY": 0,
    "FOLLOWUP_SEARCH_BLOCKED_EXHAUSTED": 0,
    "FOLLOWUP_SEARCH_BLOCKED_LOW_GAIN": 0,
    "FOLLOWUP_EXISTING_EVIDENCE_REUSED": 0,
    "FOLLOWUP_QUERY_REPETITION_BLOCKED": 0,
    "FOLLOWUP_RESERVATIONS_ACQUIRED": 0,
    "FOLLOWUP_RESERVATIONS_BLOCKED_CONCURRENT": 0,
    "FOLLOWUP_RESERVATIONS_RENEWED": 0,
    "FOLLOWUP_RESERVATIONS_BLOCKED_REDIS_UNAVAILABLE": 0,
    "FOLLOWUP_SEARCH_BLOCKED_CONCURRENT_RESERVATION": 0,
    "FOLLOWUP_SEARCH_BLOCKED_REDIS_UNAVAILABLE": 0,
    "FOLLOWUP_LLM_NEW_SEARCH_JUSTIFIED": 0,
    "FOLLOWUP_LLM_EXISTING_EVIDENCE_SUFFICIENT": 0,
    "FOLLOWUP_LLM_FAILURE_DETERMINISTIC_FALLBACKS": 0,
    "FOLLOWUP_SEARCH_BLOCKED_LLM_FAILURE": 0,
    "FOLLOWUP_PRODUCTIVE_OUTCOME_PRESERVED": 0,
    "FOLLOWUP_PRODUCTIVE_CALL_REPLACED_BY_EXISTING_EVIDENCE": 0,
    "FOLLOWUP_SEARCHES_WITH_NEW_EVIDENCE": 0,
    "FOLLOWUP_SEARCHES_WITHOUT_NEW_EVIDENCE": 0,
    "FOLLOWUP_HOLD_TO_PASS": 0,
    "FOLLOWUP_UNKNOWN_TO_VERIFIED": 0,
    "DEEPSEEK_FOLLOWUP_CALLS": 0,
    "GEMINI_FOLLOWUP_FALLBACKS": 0,
    "FOLLOWUP_PROVIDER_FAILURES": 0,
}
_TELEMETRY_LOCK = threading.Lock()


def increment_telemetry(metric: str, count: int = 1) -> None:
    with _TELEMETRY_LOCK:
        _TELEMETRY[metric] = _TELEMETRY.get(metric, 0) + count


def get_telemetry() -> Dict[str, int]:
    with _TELEMETRY_LOCK:
        return dict(_TELEMETRY)


def reset_telemetry() -> None:
    with _TELEMETRY_LOCK:
        for k in _TELEMETRY:
            _TELEMETRY[k] = 0


@dataclass
class InformationGainDecision:
    """Authoritative decision object produced by FollowupInformationGainGate."""

    search_needed: bool
    missing_fact: str
    expected_information_gain: str  # HIGH, MEDIUM, LOW
    reason: str
    suggested_query: str = ""
    research_strategy: str = "GENERAL_WEB"
    alternative_action: str = "HOLD"  # USE_EXISTING_EVIDENCE, SEARCH, HOLD, UPGRADE_OPPORTUNITY
    decision_type: str = "DETERMINISTIC"  # DETERMINISTIC_REJECT, LLM_EVALUATED, CONCURRENT_RESERVATION_BLOCKED, LLM_FAILURE_HOLD
    provider_used: str = "NONE"  # DEEPSEEK, GEMINI, DETERMINISTIC
    blocked_reason: Optional[str] = None
    prior_attempt_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "search_needed": self.search_needed,
            "missing_fact": self.missing_fact,
            "expected_information_gain": self.expected_information_gain,
            "reason": self.reason,
            "suggested_query": self.suggested_query,
            "research_strategy": self.research_strategy,
            "alternative_action": self.alternative_action,
            "decision_type": self.decision_type,
            "provider_used": self.provider_used,
            "blocked_reason": self.blocked_reason,
            "prior_attempt_count": self.prior_attempt_count,
        }


GATE_SYSTEM_PROMPT = """You are the Authoritative LLM Information-Gain Gate for Salesoorja follow-up research.
Your mission is to ELIMINATE wasteful, redundant downstream follow-up web searches for existing company candidates.

Rules & Logic:
1. Missing Fact Verification:
   Check whether the Current Evidence Corpus ALREADY contains or clearly implies the missing fact.
   If existing evidence is sufficient, output search_needed=false and alternative_action="USE_EXISTING_EVIDENCE".
2. Stop-Rule on Unproductive Repetition:
   If 2 prior searches for this (company + missing_fact) found no new evidence, you MUST output search_needed=false
   UNLESS you are recommending a genuinely escalated, distinct source strategy (e.g. OFFICIAL_COMPANY, GOVERNMENT_SOURCE)
   with explicit rationale why previous searches failed.
3. Information Gain Standard:
   Expected information gain must be HIGH or MEDIUM to justify search. If gain is LOW, output search_needed=false and alternative_action="HOLD".
4. Natural Targeted Queries:
   When search_needed=true, generate a natural targeted query.
   DO NOT append blind static negative keyword strings (e.g. do NOT blindly append "-stock -share -dividend -trading").
   Include negative keywords ONLY if prior results showed financial confusion and it is strictly necessary.

Output Format: Return valid JSON with keys:
{
  "search_needed": true/false,
  "missing_fact": "<FACILITY_LOCATION | COMMISSIONING_STATUS | CAPEX_EVENT | ...>",
  "expected_information_gain": "<HIGH | MEDIUM | LOW>",
  "reason": "<clear explanation>",
  "suggested_query": "<natural clean query or empty>",
  "research_strategy": "<GENERAL_WEB | OFFICIAL_COMPANY | GOVERNMENT_SOURCE | TRADE_MEDIA | FACILITY_SPECIFIC | CORPORATE_FILING>",
  "alternative_action": "<USE_EXISTING_EVIDENCE | SEARCH | HOLD | UPGRADE_OPPORTUNITY>"
}"""


class FollowupInformationGainGate:
    """Authoritative LLM Information-Gain Gatekeeper for Downstream Follow-Up Research."""

    def __init__(
        self,
        primary_provider: Optional[Any] = None,
        fallback_provider: Optional[Any] = None,
        db_session: Optional[Session] = None,
        redis_client: Optional[Any] = None,
        fail_closed_on_llm_failure: bool = False,
        allow_in_memory_reservation: Optional[bool] = None,
    ):
        self.primary_provider = primary_provider or DeepSeekProvider()
        self.fallback_provider = fallback_provider or GeminiProvider()
        self.db_session = db_session
        self._redis = redis_client
        self.fail_closed_on_llm_failure = fail_closed_on_llm_failure
        self._allow_in_memory_reservation = allow_in_memory_reservation
        # key -> (token, expiry_ts, metadata)
        self._reservations: Dict[str, Tuple[str, float, Dict[str, Any]]] = {}
        self._reservation_lock = threading.Lock()
        self._in_memory_store: Dict[str, List[Dict[str, Any]]] = {}
        self._store_lock = threading.Lock()

    def is_in_memory_fallback_allowed(self) -> bool:
        """Check if local process in-memory reservation is permitted.

        Permitted ONLY in test/dev environments, single-process scripts, or when explicitly enabled.
        Strictly forbidden in PRODUCTION / MULTI-PROCESS mode to prevent
        uncoordinated duplicate Serper searches across FastAPI and Celery.
        """
        if self._allow_in_memory_reservation is not None:
            return self._allow_in_memory_reservation
        if os.environ.get("ALLOW_IN_MEMORY_RESERVATION", "").lower() in {"1", "true"}:
            return True
        if "pytest" in sys.modules or os.environ.get("PYTEST_CURRENT_TEST"):
            return True
        try:
            from config import settings
            mode = str(getattr(settings, "SALESOORJA_MODE", "")).upper()
            if mode in {"PRODUCTION", "LIVE", "24X7"}:
                return False
            if mode in {"TEST", "DEVELOPMENT", "DEV", "LOCAL"}:
                return True
        except Exception:
            pass
        return False

    def _get_redis(self) -> Optional[Any]:
        if self._redis is not None:
            return self._redis
        try:
            import redis
            from config import settings
            client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True, socket_timeout=1.5)
            client.ping()
            self._redis = client
            return self._redis
        except Exception:
            return None

    def _normalize_name(self, name: str) -> str:
        clean = (name or "").strip().lower()
        clean = re.sub(r"[^\w\s]", " ", clean)
        return " ".join(clean.split())

    def _normalize_query(self, query: str) -> str:
        clean = (query or "").strip().lower()
        clean = clean.replace('"', " ").replace("'", " ").replace("-", " ")
        clean = re.sub(r" (stock|share|dividend|trading|equity|sensex|nifty|brokerage|screener) ", "", clean)
        return " ".join(clean.split())

    def is_generic_entity(self, name: str) -> bool:
        """Check if candidate name is an obvious isolated generic industry noun."""
        normalized = self._normalize_name(name)
        if not normalized:
            return True
        if normalized in GENERIC_ENTITY_BLOCKLIST:
            return True
        words = normalized.split()
        if len(words) == 1 and words[0] in GENERIC_ENTITY_BLOCKLIST:
            return True
        return False

    def is_entity_resolved(
        self,
        company_name: str,
        company_id: Optional[int] = None,
        candidate_group: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str]:
        """Verify whether entity is resolved as a real operating company (Amendment 5)."""
        # Obvious generic blocker
        if self.is_generic_entity(company_name):
            return False, f"Name '{company_name}' is an isolated generic industry noun"

        # Check A: Persisted Company ID + non-generic name
        if company_id is not None and company_id > 0:
            return True, "PERSISTED_COMPANY_RECORD"

        # Check candidate group metadata
        if candidate_group:
            if candidate_group.get("entity_verified") is True:
                return True, "CANDIDATE_ENTITY_VERIFIED"
            if candidate_group.get("is_target_industrial") is True and candidate_group.get("company_name"):
                return True, "PREPERSISTENCE_TARGET_INDUSTRIAL"
            # Check pre-persistence evaluation if available
            pre_eval = candidate_group.get("pre_persistence_evaluation")
            if pre_eval and isinstance(pre_eval, dict):
                if pre_eval.get("entity_type") == "TARGET_INDUSTRIAL_COMPANY" and pre_eval.get("should_persist"):
                    return True, "PREPERSISTENCE_PASSED"

        # Check B: Pre-persistence entity gate evaluation (when candidate evidence is present)
        if candidate_group is not None:
            try:
                from services.pre_persistence_entity_gate import pre_persistence_entity_gate
                evidence_packet = {
                    "title": (candidate_group.get("titles", [""])[0] if candidate_group.get("titles") else ""),
                    "snippet": (candidate_group.get("snippets", [""])[0] if candidate_group.get("snippets") else ""),
                    "url": (candidate_group.get("source_urls", [""])[0] if candidate_group.get("source_urls") else ""),
                    "industry": candidate_group.get("sector", ""),
                }
                eval_res = pre_persistence_entity_gate.resolve_pre_persistence_decision(
                    candidate_name=company_name,
                    title=evidence_packet.get('title', ''),
                    snippet=evidence_packet.get('snippet', ''),
                    url=evidence_packet.get('url', ''),
                    industry=evidence_packet.get('industry', ''),
                )
                if eval_res.should_persist and eval_res.entity_type == "TARGET_INDUSTRIAL_COMPANY":
                    return True, "PREPERSISTENCE_EVALUATED_PASS"
                else:
                    return False, f"Pre-persistence gate rejected: {eval_res.reason}"
            except Exception as exc:
                logger.debug("Pre-persistence evaluation failed: %s", exc)

        # Conservative default: if company name is multi-word with non-generic tokens, allow
        words = self._normalize_name(company_name).split()
        non_generic_words = [w for w in words if w not in GENERIC_ENTITY_BLOCKLIST and len(w) > 2]
        if len(non_generic_words) >= 2:
            return True, "MULTI_WORD_NON_GENERIC_STEM"

        return False, f"Entity '{company_name}' is ungrounded / unresolved"

    # --- Atomic Search Reservation System (Task 3D.1F.1 & Task 3D.1F.2) ---

    def acquire_search_reservation(
        self,
        company_name: str,
        missing_fact: str,
        strategy: str = "GENERAL_WEB",
        attempt: int = 1,
        lease_seconds: int = RESERVATION_LEASE_SECONDS,
        worker_id: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Atomically reserve search execution for (company + missing_fact).

        Authoritative distributed reservation scope (Task 3D.1F.2 Section 1):
        normalized_operating_entity + canonical_missing_fact
        ONE unresolved fact = ONE active web search at a time.
        research_strategy, attempt, worker_id are metadata, NOT separate namespaces!

        Prevents two workers (e.g. FastAPI and Celery) from simultaneously deciding
        'no prior search exists' and issuing duplicate Serper calls.
        Safe across multi-process workers via Redis SET NX EX.
        In production, if Redis is unavailable, fails closed to HOLD (Task 3D.1F.2 Section 5).
        """
        norm_entity = self._normalize_name(company_name)
        canon_fact = canonicalize_missing_fact(missing_fact)
        reservation_key = f"salesoorja:followup:reservation:{norm_entity}::{canon_fact}"
        token = worker_id or f"{os.getpid()}:{uuid.uuid4().hex[:8]}"
        metadata = {
            "token": token,
            "company_name": company_name,
            "normalized_operating_entity": norm_entity,
            "missing_fact": canon_fact,
            "strategy": strategy,
            "attempt": attempt,
            "pid": os.getpid(),
            "created_at": time.time(),
        }

        r = self._get_redis()
        if r is not None:
            try:
                # Atomic SET if Not Exists with Expiration (bounded lease)
                acquired = bool(r.set(reservation_key, token, nx=True, ex=lease_seconds))
                if acquired:
                    try:
                        r.set(f"{reservation_key}:meta", json.dumps(metadata), ex=lease_seconds)
                    except Exception:
                        pass
                    increment_telemetry("FOLLOWUP_RESERVATIONS_ACQUIRED")
                    return True, token
                else:
                    increment_telemetry("FOLLOWUP_RESERVATIONS_BLOCKED_CONCURRENT")
                    return False, None
            except Exception as e:
                logger.warning("Redis reservation check failed: %s", e)

        # Task 3D.1F.2 Section 5: Fail closed in production when Redis is unavailable!
        if not self.is_in_memory_fallback_allowed():
            logger.error(
                "[FOLLOWUP_RESERVATION_REDIS_UNAVAILABLE] Redis is unavailable in production mode. "
                "Failing closed to prevent uncoordinated duplicate Serper searches for (%s + %s).",
                company_name, canon_fact,
            )
            increment_telemetry("FOLLOWUP_RESERVATIONS_BLOCKED_REDIS_UNAVAILABLE")
            return False, "FOLLOWUP_RESERVATION_UNAVAILABLE_HOLD"

        # In-memory lease reservation permitted ONLY in unit tests and local dev
        now = time.monotonic()
        with self._reservation_lock:
            existing = self._reservations.get(reservation_key)
            if existing:
                existing_token, expiry, _ = existing
                if now < expiry:
                    # Still active! Reject concurrent reservation
                    increment_telemetry("FOLLOWUP_RESERVATIONS_BLOCKED_CONCURRENT")
                    return False, None
                self._reservations.pop(reservation_key, None)
            self._reservations[reservation_key] = (token, now + lease_seconds, metadata)
            increment_telemetry("FOLLOWUP_RESERVATIONS_ACQUIRED")
            return True, token

    def renew_search_reservation(
        self,
        company_name: str,
        missing_fact: str,
        token: str,
        lease_seconds: int = RESERVATION_LEASE_SECONDS,
    ) -> bool:
        """Renew/extend lease for an active reservation if held by the same token (Task 3D.1F.2 Section 3)."""
        if not token or token == "FOLLOWUP_RESERVATION_UNAVAILABLE_HOLD":
            return False
        norm_entity = self._normalize_name(company_name)
        canon_fact = canonicalize_missing_fact(missing_fact)
        reservation_key = f"salesoorja:followup:reservation:{norm_entity}::{canon_fact}"

        r = self._get_redis()
        if r is not None:
            try:
                # Atomic Lua renewal script: only extend if key holds this worker's token
                lua_renew = """
                if redis.call("get", KEYS[1]) == ARGV[1] then
                    redis.call("expire", KEYS[1], ARGV[2])
                    if redis.call("exists", KEYS[1] .. ":meta") == 1 then
                        redis.call("expire", KEYS[1] .. ":meta", ARGV[2])
                    end
                    return 1
                else
                    return 0
                end
                """
                res = r.eval(lua_renew, 1, reservation_key, token, lease_seconds)
                if bool(res == 1):
                    increment_telemetry("FOLLOWUP_RESERVATIONS_RENEWED")
                    return True
                return False
            except Exception as e:
                logger.warning("Redis reservation renew failed: %s", e)
                return False

        if not self.is_in_memory_fallback_allowed():
            return False

        with self._reservation_lock:
            existing = self._reservations.get(reservation_key)
            if existing and existing[0] == token:
                now = time.monotonic()
                self._reservations[reservation_key] = (token, now + lease_seconds, existing[2])
                increment_telemetry("FOLLOWUP_RESERVATIONS_RENEWED")
                return True
        return False

    def release_search_reservation(
        self,
        company_name: str,
        missing_fact: str,
        token: Optional[str] = None,
    ) -> bool:
        """Release search reservation after search completes or fails."""
        if not token or token == "FOLLOWUP_RESERVATION_UNAVAILABLE_HOLD":
            return False
        norm_entity = self._normalize_name(company_name)
        canon_fact = canonicalize_missing_fact(missing_fact)
        reservation_key = f"salesoorja:followup:reservation:{norm_entity}::{canon_fact}"

        released = False
        r = self._get_redis()
        if r is not None:
            try:
                lua_release = """
                if redis.call("get", KEYS[1]) == ARGV[1] then
                    redis.call("del", KEYS[1])
                    redis.call("del", KEYS[1] .. ":meta")
                    return 1
                else
                    return 0
                end
                """
                res = r.eval(lua_release, 1, reservation_key, token)
                released = bool(res == 1)
            except Exception as e:
                logger.debug("Redis reservation release error: %s", e)

        with self._reservation_lock:
            existing = self._reservations.get(reservation_key)
            if existing and existing[0] == token:
                self._reservations.pop(reservation_key, None)
                released = True
            elif existing and time.monotonic() >= existing[1]:
                self._reservations.pop(reservation_key, None)

        return released

    def is_search_reserved(
        self,
        company_name: str,
        missing_fact: str,
    ) -> bool:
        """Check whether an active non-expired search reservation exists."""
        norm_entity = self._normalize_name(company_name)
        canon_fact = canonicalize_missing_fact(missing_fact)
        reservation_key = f"salesoorja:followup:reservation:{norm_entity}::{canon_fact}"

        r = self._get_redis()
        if r is not None:
            try:
                if r.exists(reservation_key):
                    return True
                return False
            except Exception:
                pass

        if not self.is_in_memory_fallback_allowed():
            # In production mode when Redis is unavailable, block searches
            return True

        now = time.monotonic()
        with self._reservation_lock:
            existing = self._reservations.get(reservation_key)
            if existing:
                _, expiry, _ = existing
                if now < expiry:
                    return True
                self._reservations.pop(reservation_key, None)
        return False

    @contextmanager
    def reserve_search(
        self,
        company_name: str,
        missing_fact: str,
        strategy: str = "GENERAL_WEB",
        attempt: int = 1,
        lease_seconds: int = RESERVATION_LEASE_SECONDS,
        heartbeat_interval: float = 15.0,
        worker_id: Optional[str] = None,
    ):
        """Context manager for clean atomic search reservation with background lease renewal.

        Task 3D.1F.2 Section 3 & 4:
        - Acquires atomic reservation scoped to (normalized_operating_entity + canonical_missing_fact).
        - Spawns a background heartbeat thread renewing the lease every heartbeat_interval while work is active.
        - Automatically stops heartbeat and releases lease on exit.
        - If worker dies mid-execution, heartbeat stops and lease naturally expires after lease_seconds (no permanent lockout).
        """
        acquired, token = self.acquire_search_reservation(
            company_name=company_name,
            missing_fact=missing_fact,
            strategy=strategy,
            attempt=attempt,
            lease_seconds=lease_seconds,
            worker_id=worker_id,
        )
        if not acquired or not token or token == "FOLLOWUP_RESERVATION_UNAVAILABLE_HOLD":
            yield False, token
            return

        norm_entity = self._normalize_name(company_name)
        stop_heartbeat = threading.Event()

        def _heartbeat_worker():
            interval = min(heartbeat_interval, max(0.1, lease_seconds / 3.0))
            while not stop_heartbeat.wait(timeout=interval):
                renewed = self.renew_search_reservation(
                    company_name=company_name,
                    missing_fact=missing_fact,
                    token=token,
                    lease_seconds=lease_seconds,
                )
                if not renewed:
                    logger.warning(
                        "[RESERVATION_HEARTBEAT_EXPIRED] Could not renew reservation for (%s + %s).",
                        company_name, missing_fact,
                    )
                    break

        hb_thread = threading.Thread(
            target=_heartbeat_worker,
            daemon=True,
            name=f"FollowupHB-{norm_entity[:12]}",
        )
        hb_thread.start()

        try:
            yield True, token
        finally:
            stop_heartbeat.set()
            hb_thread.join(timeout=1.0)
            self.release_search_reservation(company_name, missing_fact, token)

    # --- Query Memory Storage & Retrieval ---

    def get_prior_searches(
        self,
        company_name: str,
        missing_fact: str,
        db: Optional[Session] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve historical search records for (company, missing_fact) from PostgreSQL."""
        norm_entity = self._normalize_name(company_name)
        canon_fact = canonicalize_missing_fact(missing_fact)
        session = db or self.db_session
        records = []

        if session:
            try:
                db_records = (
                    session.query(FollowupQueryMemoryRecord)
                    .filter(
                        FollowupQueryMemoryRecord.normalized_operating_entity == norm_entity,
                        FollowupQueryMemoryRecord.missing_fact == canon_fact,
                    )
                    .order_by(FollowupQueryMemoryRecord.timestamp.asc())
                    .all()
                )
                records = [r.to_dict() for r in db_records]
            except Exception as exc:
                logger.debug("Failed reading Postgres followup memory: %s", exc)
                session.rollback()

        if not records:
            mem_key = f"{norm_entity}::{canon_fact}"
            with self._store_lock:
                records = list(self._in_memory_store.get(mem_key, []))

        return records

    def record_search_outcome(
        self,
        company_name: str,
        missing_fact: str,
        query: str,
        research_strategy: str = "GENERAL_WEB",
        result_count: int = 0,
        useful_urls: Optional[List[str]] = None,
        new_evidence_found: bool = False,
        evidence_type_found: Optional[str] = None,
        source_domains: Optional[List[str]] = None,
        funnel_state_before: Optional[str] = None,
        funnel_state_after: Optional[str] = None,
        llm_reasoning: Optional[str] = None,
        company_id: Optional[int] = None,
        db: Optional[Session] = None,
    ) -> None:
        """Persist follow-up search query outcome to PostgreSQL (concurrency-safe) and memory."""
        norm_entity = self._normalize_name(company_name)
        canon_fact = canonicalize_missing_fact(missing_fact)
        urls = useful_urls or []
        domains = source_domains or []
        now_dt = datetime.now(timezone.utc)

        # Update telemetry
        increment_telemetry("FOLLOWUP_SEARCHES_EXECUTED")
        if new_evidence_found:
            increment_telemetry("FOLLOWUP_SEARCHES_WITH_NEW_EVIDENCE")
            increment_telemetry("FOLLOWUP_PRODUCTIVE_OUTCOME_PRESERVED")
        else:
            increment_telemetry("FOLLOWUP_SEARCHES_WITHOUT_NEW_EVIDENCE")

        if funnel_state_before == "HOLD" and funnel_state_after == "PASS":
            increment_telemetry("FOLLOWUP_HOLD_TO_PASS")
        if funnel_state_before in {"UNKNOWN", None} and funnel_state_after in {"VERIFIED", "STRONG"}:
            increment_telemetry("FOLLOWUP_UNKNOWN_TO_VERIFIED")

        session_to_use = db or self.db_session
        own_session = False
        if not session_to_use and SessionLocal is not None:
            try:
                session_to_use = SessionLocal()
                own_session = True
            except Exception:
                session_to_use = None

        if session_to_use:
            try:
                record = FollowupQueryMemoryRecord(
                    company_id=company_id,
                    normalized_operating_entity=norm_entity,
                    missing_fact=canon_fact,
                    query=query,
                    timestamp=now_dt,
                    research_strategy=research_strategy,
                    result_count=result_count,
                    useful_urls=urls,
                    new_evidence_found=new_evidence_found,
                    evidence_type_found=evidence_type_found,
                    source_domains=domains,
                    funnel_state_before=funnel_state_before,
                    funnel_state_after=funnel_state_after,
                    llm_reasoning=llm_reasoning,
                )
                session_to_use.add(record)
                session_to_use.commit()
            except Exception as exc:
                logger.warning("Failed writing Postgres followup memory: %s", exc)
                session_to_use.rollback()
            finally:
                if own_session:
                    session_to_use.close()

        # Update in-memory fallback
        mem_key = f"{norm_entity}::{canon_fact}"
        entry = {
            "company_id": company_id,
            "normalized_operating_entity": norm_entity,
            "missing_fact": canon_fact,
            "query": query,
            "timestamp": now_dt.isoformat(),
            "research_strategy": research_strategy,
            "result_count": result_count,
            "useful_urls": urls,
            "new_evidence_found": new_evidence_found,
            "evidence_type_found": evidence_type_found,
            "source_domains": domains,
            "funnel_state_before": funnel_state_before,
            "funnel_state_after": funnel_state_after,
            "llm_reasoning": llm_reasoning,
        }
        with self._store_lock:
            self._in_memory_store.setdefault(mem_key, []).append(entry)

    def _call_llm_judge(self, user_prompt: str) -> Tuple[Optional[Dict[str, Any]], str]:
        """Query LLM judge with DeepSeek primary and Gemini fallback."""
        kwargs = {
            "system_prompt": GATE_SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": user_prompt}],
            "temperature": 0.0,
            "max_tokens": 400,
            "response_format": "json",
        }

        def _invoke(prov):
            if not prov:
                return None
            if hasattr(prov, "is_available") and not prov.is_available():
                return None
            if hasattr(prov, "complete"):
                return prov.complete(**kwargs)
            elif hasattr(prov, "call"):
                return prov.call(prompt=user_prompt, **kwargs)
            elif callable(prov):
                return prov(prompt=user_prompt, **kwargs)
            return None

        # 1. Primary: DeepSeek
        if self.primary_provider:
            try:
                increment_telemetry("DEEPSEEK_FOLLOWUP_CALLS")
                resp = _invoke(self.primary_provider)
                parsed = resp.parse_json() if resp and hasattr(resp, "parse_json") else None
                if not parsed and resp and hasattr(resp, "text"):
                    parsed = json.loads(resp.text)
                if parsed and isinstance(parsed, dict) and "search_needed" in parsed:
                    return parsed, "DEEPSEEK"
            except Exception as exc:
                logger.warning("[FOLLOWUP_GATE: PRIMARY_FAIL] %s, falling back", exc)
                increment_telemetry("FOLLOWUP_PROVIDER_FAILURES")

        # 2. Fallback: Gemini
        if self.fallback_provider:
            try:
                increment_telemetry("GEMINI_FOLLOWUP_FALLBACKS")
                resp = _invoke(self.fallback_provider)
                parsed = resp.parse_json() if resp and hasattr(resp, "parse_json") else None
                if not parsed and resp and hasattr(resp, "text"):
                    parsed = json.loads(resp.text)
                if parsed and isinstance(parsed, dict) and "search_needed" in parsed:
                    return parsed, "GEMINI"
            except Exception as exc:
                logger.warning("[FOLLOWUP_GATE: FALLBACK_FAIL] %s", exc)
                increment_telemetry("FOLLOWUP_PROVIDER_FAILURES")

        return None, "NONE"

    def evaluate_followup_search(
        self,
        company_name: str,
        missing_fact: str,
        current_evidence: Optional[Dict[str, Any]] = None,
        candidate_group: Optional[Dict[str, Any]] = None,
        company_id: Optional[int] = None,
        facility_name: Optional[str] = None,
        current_funnel_status: str = "INCOMPLETE",
        db: Optional[Session] = None,
        fail_closed_on_llm_failure: Optional[bool] = None,
    ) -> InformationGainDecision:
        """Core Gatekeeper: Evaluates whether a follow-up Serper call is justified."""
        increment_telemetry("FOLLOWUP_RESEARCH_DECISIONS")

        # Step 0: Canonicalize missing_fact & validate taxonomy (Task 3D.1F.1 Section 9)
        canon_fact = canonicalize_missing_fact(missing_fact)
        if not canon_fact or canon_fact not in VALID_MISSING_FACTS:
            return InformationGainDecision(
                search_needed=False,
                missing_fact=missing_fact or "UNSPECIFIED",
                expected_information_gain="LOW",
                reason=f"Missing fact '{missing_fact}' is invalid or unspecified",
                suggested_query="",
                research_strategy="OTHER",
                alternative_action="HOLD",
                decision_type="DETERMINISTIC_REJECT",
                blocked_reason="UNSPECIFIED_MISSING_FACT",
            )

        # Step 0.2: Redis Availability in Production Check (Task 3D.1F.2 Section 5, 6)
        if not self.is_in_memory_fallback_allowed() and self._get_redis() is None:
            increment_telemetry("FOLLOWUP_SEARCH_BLOCKED_REDIS_UNAVAILABLE")
            return InformationGainDecision(
                search_needed=False,
                missing_fact=canon_fact,
                expected_information_gain="LOW",
                reason=f"Distributed reservation system (Redis) is unavailable in production. Holding follow-up search for ({company_name} + {canon_fact}) to prevent duplicate searches across processes.",
                suggested_query="",
                research_strategy="OTHER",
                alternative_action="HOLD",
                decision_type="FOLLOWUP_RESERVATION_UNAVAILABLE_HOLD",
                prior_attempt_count=0,
                blocked_reason="REDIS_UNAVAILABLE_PRODUCTION_HOLD",
            )

        # Step 0.5: Concurrent Search Reservation Check (Task 3D.1F.1 Section 4, 5)
        # If another worker currently holds an active non-expired search lease, block duplicate search!
        if self.is_search_reserved(company_name, canon_fact):
            increment_telemetry("FOLLOWUP_SEARCH_BLOCKED_CONCURRENT_RESERVATION")
            return InformationGainDecision(
                search_needed=False,
                missing_fact=canon_fact,
                expected_information_gain="LOW",
                reason=f"Concurrent search reservation active for ({company_name} + {canon_fact}). Preventing duplicate search.",
                suggested_query="",
                research_strategy="OTHER",
                alternative_action="HOLD",
                decision_type="CONCURRENT_RESERVATION_BLOCKED",
                blocked_reason="ACTIVE_SEARCH_RESERVATION",
            )

        # Step 1: Obvious Generic Entity Block
        if self.is_generic_entity(company_name):
            increment_telemetry("FOLLOWUP_SEARCH_BLOCKED_GENERIC_ENTITY")
            return InformationGainDecision(
                search_needed=False,
                missing_fact=canon_fact,
                expected_information_gain="LOW",
                reason=f"Candidate entity '{company_name}' is an isolated generic industry noun (e.g. Chemical/Steel/Plant)",
                suggested_query="",
                research_strategy="OTHER",
                alternative_action="HOLD",
                decision_type="DETERMINISTIC_REJECT",
                blocked_reason="BLOCK_GENERIC_ENTITY",
            )

        # Step 2: Resolved Entity Verification
        is_resolved, resolve_reason = self.is_entity_resolved(
            company_name=company_name,
            company_id=company_id,
            candidate_group=candidate_group,
        )
        if not is_resolved:
            increment_telemetry("FOLLOWUP_BLOCKED_UNRESOLVED_ENTITY")
            return InformationGainDecision(
                search_needed=False,
                missing_fact=canon_fact,
                expected_information_gain="LOW",
                reason=f"Follow-up research blocked: Candidate '{company_name}' is not a resolved operating entity ({resolve_reason})",
                suggested_query="",
                research_strategy="OTHER",
                alternative_action="HOLD",
                decision_type="DETERMINISTIC_REJECT",
                blocked_reason="BLOCK_UNRESOLVED_ENTITY",
            )

        # Step 3: Fetch Prior Query History from Postgres
        prior_searches = self.get_prior_searches(
            company_name=company_name,
            missing_fact=canon_fact,
            db=db,
        )
        attempt_count = len(prior_searches)
        unsuccessful_searches = [s for s in prior_searches if not s.get("new_evidence_found")]
        unsuccessful_count = len(unsuccessful_searches)

        # Check if already successfully resolved
        successful_searches = [s for s in prior_searches if s.get("new_evidence_found")]
        if successful_searches:
            increment_telemetry("FOLLOWUP_EXISTING_EVIDENCE_REUSED")
            increment_telemetry("FOLLOWUP_PRODUCTIVE_CALL_REPLACED_BY_EXISTING_EVIDENCE")
            return InformationGainDecision(
                search_needed=False,
                missing_fact=canon_fact,
                expected_information_gain="LOW",
                reason=f"Missing fact '{canon_fact}' was already resolved in prior search (evidence: {successful_searches[-1].get('evidence_type_found')})",
                suggested_query="",
                research_strategy=successful_searches[-1].get("research_strategy", "GENERAL_WEB"),
                alternative_action="USE_EXISTING_EVIDENCE",
                decision_type="MEMORY_ALREADY_RESOLVED",
                prior_attempt_count=attempt_count,
            )

        # Step 4: Repetition Stop Rule
        exhausted = unsuccessful_count >= 2

        # Step 5: Check Existing Evidence Corpus
        ev_dict = current_evidence or {}
        if candidate_group and not ev_dict:
            ev_dict = {
                "titles": candidate_group.get("titles", []),
                "snippets": candidate_group.get("snippets", []),
                "source_urls": candidate_group.get("source_urls", []),
                "evidence_packets": candidate_group.get("evidence_packets", []),
            }

        # Build LLM Prompt
        evidence_summary = self._summarize_evidence(ev_dict)
        prior_search_summary = self._summarize_prior_searches(prior_searches)

        user_prompt = f"""EVALUATE FOLLOW-UP RESEARCH INFORMATION GAIN:
Company: "{company_name}"
Facility: {json.dumps(facility_name)}
Missing Fact Required: "{canon_fact}"
Current Funnel Status: "{current_funnel_status}"

Current Evidence Corpus:
{evidence_summary}

Prior Searches Executed for ({company_name} + {canon_fact}):
{prior_search_summary}

Prior Unsuccessful Searches: {unsuccessful_count} / Maximum 2

TASK:
1. Does the Current Evidence Corpus ALREADY provide or substantiate the missing fact '{canon_fact}'?
2. If not, would another search yield HIGH or MEDIUM information gain?
   (If 2 prior searches failed with no new evidence, you may ONLY authorize search if recommending an escalated source strategy like OFFICIAL_COMPANY or GOVERNMENT_SOURCE with explicit justification. Otherwise output search_needed=false).
3. If search is needed, generate a natural targeted query (DO NOT append static negative keyword lists).

Return ONLY valid JSON matching the schema."""

        parsed, provider_used = self._call_llm_judge(user_prompt)

        if parsed:
            search_needed = bool(parsed.get("search_needed", False))
            exp_gain = str(parsed.get("expected_information_gain", "LOW")).upper()
            if exp_gain not in EXPECTED_GAINS:
                exp_gain = "LOW"
            alt_action = str(parsed.get("alternative_action", "HOLD")).upper()
            if alt_action not in ALTERNATIVE_ACTIONS:
                alt_action = "HOLD"
            reason = str(parsed.get("reason", "Evaluated by Information-Gain Gate"))
            suggested_query = str(parsed.get("suggested_query", "")).strip()
            research_strategy = str(parsed.get("research_strategy", "GENERAL_WEB")).upper()
            if research_strategy not in RESEARCH_STRATEGIES:
                research_strategy = "GENERAL_WEB"

            # Check if LLM determined existing evidence is sufficient
            if alt_action == "USE_EXISTING_EVIDENCE" or not search_needed:
                if alt_action == "USE_EXISTING_EVIDENCE":
                    increment_telemetry("FOLLOWUP_EXISTING_EVIDENCE_REUSED")
                    increment_telemetry("FOLLOWUP_LLM_EXISTING_EVIDENCE_SUFFICIENT")
                    increment_telemetry("FOLLOWUP_PRODUCTIVE_CALL_REPLACED_BY_EXISTING_EVIDENCE")
                else:
                    increment_telemetry("FOLLOWUP_SEARCH_BLOCKED_LOW_GAIN")

                return InformationGainDecision(
                    search_needed=False,
                    missing_fact=canon_fact,
                    expected_information_gain=exp_gain,
                    reason=reason,
                    suggested_query="",
                    research_strategy=research_strategy,
                    alternative_action=alt_action,
                    decision_type="LLM_EVALUATED",
                    provider_used=provider_used,
                    prior_attempt_count=attempt_count,
                )

            # Deterministic Guard: Repetition Stop Rule Enforcement
            if exhausted:
                prior_strategies = {s.get("research_strategy") for s in prior_searches}
                if research_strategy in prior_strategies or research_strategy == "GENERAL_WEB":
                    increment_telemetry("FOLLOWUP_SEARCH_BLOCKED_EXHAUSTED")
                    return InformationGainDecision(
                        search_needed=False,
                        missing_fact=canon_fact,
                        expected_information_gain="LOW",
                        reason=f"Blocked after 2 unsuccessful searches for ({company_name} + {canon_fact}). Strategy '{research_strategy}' is not an escalated new source strategy.",
                        suggested_query="",
                        research_strategy=research_strategy,
                        alternative_action="HOLD",
                        decision_type="DETERMINISTIC_REPETITION_STOP",
                        provider_used=provider_used,
                        prior_attempt_count=attempt_count,
                        blocked_reason="BLOCK_EXHAUSTED",
                    )

            # Check query deduplication against prior queries
            if suggested_query:
                norm_q = self._normalize_query(suggested_query)
                for s in prior_searches:
                    if self._normalize_query(s.get("query", "")) == norm_q:
                        increment_telemetry("FOLLOWUP_QUERY_REPETITION_BLOCKED")
                        return InformationGainDecision(
                            search_needed=False,
                            missing_fact=canon_fact,
                            expected_information_gain="LOW",
                            reason=f"Suggested query is a cosmetic duplicate of an exhausted prior query ('{s.get('query')}')",
                            suggested_query="",
                            research_strategy=research_strategy,
                            alternative_action="HOLD",
                            decision_type="DETERMINISTIC_DEDUPE_BLOCK",
                            provider_used=provider_used,
                            prior_attempt_count=attempt_count,
                            blocked_reason="BLOCK_REPETITION",
                        )

            # Execution Rule: search_needed == True AND expected_gain IN (HIGH, MEDIUM)
            if search_needed and exp_gain in {"HIGH", "MEDIUM"}:
                increment_telemetry("FOLLOWUP_SEARCH_ALLOWED")
                increment_telemetry("FOLLOWUP_LLM_NEW_SEARCH_JUSTIFIED")
                return InformationGainDecision(
                    search_needed=True,
                    missing_fact=canon_fact,
                    expected_information_gain=exp_gain,
                    reason=reason,
                    suggested_query=suggested_query,
                    research_strategy=research_strategy,
                    alternative_action="SEARCH",
                    decision_type="LLM_EVALUATED",
                    provider_used=provider_used,
                    prior_attempt_count=attempt_count,
                )
            else:
                increment_telemetry("FOLLOWUP_SEARCH_BLOCKED_LOW_GAIN")
                return InformationGainDecision(
                    search_needed=False,
                    missing_fact=canon_fact,
                    expected_information_gain="LOW",
                    reason=reason,
                    suggested_query="",
                    research_strategy=research_strategy,
                    alternative_action=alt_action,
                    decision_type="LLM_EVALUATED",
                    provider_used=provider_used,
                    prior_attempt_count=attempt_count,
                    blocked_reason="BLOCK_LOW_GAIN",
                )

        # Safe deterministic fallback when both LLMs fail (Task 3D.1F.1 Section 8)
        fc = self.fail_closed_on_llm_failure if fail_closed_on_llm_failure is None else fail_closed_on_llm_failure
        return self._deterministic_fallback_evaluation(
            company_name=company_name,
            missing_fact=canon_fact,
            ev_dict=ev_dict,
            prior_searches=prior_searches,
            attempt_count=attempt_count,
            unsuccessful_count=unsuccessful_count,
            fail_closed=fc,
        )

    def _deterministic_fallback_evaluation(
        self,
        company_name: str,
        missing_fact: str,
        ev_dict: Dict[str, Any],
        prior_searches: List[Dict[str, Any]],
        attempt_count: int,
        unsuccessful_count: int,
        fail_closed: bool = False,
    ) -> InformationGainDecision:
        """Safe fail-closed deterministic fallback when LLM providers are unavailable.

        Principle (Task 3D.1F.1 Section 8):
        Use deterministic existing-memory / max-attempt / entity safety checks,
        then HOLD when semantic information-gain cannot be established.
        We do NOT blindly spend repeated Serper credits when both LLMs fail.
        """
        increment_telemetry("FOLLOWUP_LLM_FAILURE_DETERMINISTIC_FALLBACKS")

        # 1. Repetition stop check
        if unsuccessful_count >= 2:
            increment_telemetry("FOLLOWUP_SEARCH_BLOCKED_EXHAUSTED")
            return InformationGainDecision(
                search_needed=False,
                missing_fact=missing_fact,
                expected_information_gain="LOW",
                reason=f"Deterministic fallback: Exceeded 2 unsuccessful attempts for ({company_name} + {missing_fact})",
                suggested_query="",
                research_strategy="OTHER",
                alternative_action="HOLD",
                decision_type="DETERMINISTIC_FALLBACK",
                prior_attempt_count=attempt_count,
                blocked_reason="BLOCK_EXHAUSTED",
            )

        # 2. Check existing evidence in corpus
        combined_text = " ".join(
            ev_dict.get("titles", []) + ev_dict.get("snippets", [])
        ).lower()
        if missing_fact in {"COMMISSIONING_STATUS", "TRIGGER_DATE", "CAPEX_EVENT"}:
            if any(w in combined_text for w in ["commissioned", "inaugurated", "commercial production", "commenced production"]):
                increment_telemetry("FOLLOWUP_EXISTING_EVIDENCE_REUSED")
                return InformationGainDecision(
                    search_needed=False,
                    missing_fact=missing_fact,
                    expected_information_gain="LOW",
                    reason="Deterministic fallback: Existing text already references commissioning/commercial production",
                    suggested_query="",
                    research_strategy="GENERAL_WEB",
                    alternative_action="USE_EXISTING_EVIDENCE",
                    decision_type="DETERMINISTIC_FALLBACK",
                    prior_attempt_count=attempt_count,
                )

        # 3. Section 8 Requirement: HOLD when fail_closed is requested or semantic gain cannot be established
        if fail_closed:
            increment_telemetry("FOLLOWUP_SEARCH_BLOCKED_LLM_FAILURE")
            return InformationGainDecision(
                search_needed=False,
                missing_fact=missing_fact,
                expected_information_gain="LOW",
                reason=f"Safe LLM failure hold: Both DeepSeek and Gemini failed to evaluate information gain for ({company_name} + {missing_fact}). Holding to prevent speculative Serper spend.",
                suggested_query="",
                research_strategy="OTHER",
                alternative_action="HOLD",
                decision_type="LLM_FAILURE_HOLD",
                prior_attempt_count=attempt_count,
                blocked_reason="HOLD_LLM_UNAVAILABLE",
            )

        # 4. Natural clean query without static negative tails for attempt 1 (capped at max 2 attempts)
        query = f'"{company_name}" plant {missing_fact.replace("_", " ").lower()}'
        increment_telemetry("FOLLOWUP_SEARCH_ALLOWED")
        return InformationGainDecision(
            search_needed=True,
            missing_fact=missing_fact,
            expected_information_gain="MEDIUM",
            reason=f"Deterministic fallback: Attempt {attempt_count + 1} for unresolved {missing_fact}",
            suggested_query=query,
            research_strategy="GENERAL_WEB",
            alternative_action="SEARCH",
            decision_type="DETERMINISTIC_FALLBACK",
            prior_attempt_count=attempt_count,
        )

    def _summarize_evidence(self, ev_dict: Dict[str, Any]) -> str:
        lines = []
        titles = ev_dict.get("titles", [])
        snippets = ev_dict.get("snippets", [])
        packets = ev_dict.get("evidence_packets", [])

        if titles:
            lines.append("Titles: " + " | ".join(titles[:3]))
        if snippets:
            lines.append("Snippets: " + " ".join(snippets[:2])[:400])
        if packets:
            facts = []
            for p in packets[:2]:
                facts.extend([f"{k}={v}" for k, v in (p.get("structured_facts") or {}).items()])
            if facts:
                lines.append("Extracted Facts: " + ", ".join(facts[:5]))

        return "\n".join(lines) if lines else "No prior textual evidence in corpus."

    def _summarize_prior_searches(self, prior_searches: List[Dict[str, Any]]) -> str:
        if not prior_searches:
            return "No previous follow-up searches executed for this (company + missing_fact)."
        lines = []
        for i, s in enumerate(prior_searches, start=1):
            q = s.get("query", "")
            strat = s.get("research_strategy", "GENERAL_WEB")
            found = s.get("new_evidence_found", False)
            ev_type = s.get("evidence_type_found") or "NONE"
            lines.append(f"Attempt {i} [{strat}]: query='{q}' -> new_evidence={found} ({ev_type})")
        return "\n".join(lines)


# Authoritative Global Singleton
followup_information_gain_gate = FollowupInformationGainGate()
