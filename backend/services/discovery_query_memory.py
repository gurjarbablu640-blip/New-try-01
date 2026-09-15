"""Discovery Query Memory for Salesoorja Discovery Intelligence.

Provides hybrid storage:
- Redis for fast operational cooldown caching (24h TTL)
- PostgreSQL (DiscoveryQueryLog) as the durable, authoritative historical memory
- Correct cooldown recovery across Redis / worker restarts
- Transparent productivity and exhaustion scoring
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
from sqlalchemy.orm import Session

from database import SessionLocal, sync_engine
from models.discovery_query_log import DiscoveryQueryLog

logger = logging.getLogger(__name__)

if sync_engine is not None:
    try:
        DiscoveryQueryLog.__table__.create(bind=sync_engine, checkfirst=True)
    except Exception as _init_err:
        logger.debug("discovery_query_logs table creation check: %s", _init_err)

# Execution states per Amendment 4
STATE_SUCCESS_PRODUCTIVE = "SUCCESS_PRODUCTIVE"
STATE_SUCCESS_EXHAUSTED = "SUCCESS_EXHAUSTED"
STATE_PROVIDER_ERROR = "PROVIDER_ERROR"
STATE_RATE_LIMITED = "RATE_LIMITED"
STATE_TIMEOUT = "TIMEOUT"

COOLDOWN_SECONDS_24H = 86400  # 24 hours


def normalize_discovery_query(query: str) -> str:
    """Canonical normalization for discovery queries."""
    if not query:
        return ""
    q = query.strip().lower()
    # Normalize multiple whitespace and quotes
    q = re.sub(r'["\']', '', q)
    q = re.sub(r'\s+', ' ', q)
    return q.strip()


def query_cooldown_key(normalized_query: str, page: int = 1) -> str:
    digest = hashlib.sha256(f"{normalized_query}:page:{page}".encode("utf-8")).hexdigest()[:24]
    return f"salesoorja:discovery:cooldown:{digest}"


class DiscoveryQueryMemory:
    """Manages 24-hour query cooldowns, Redis acceleration, and PostgreSQL historical permanence."""

    def __init__(self, redis_client: Any = None):
        self._redis = redis_client

    def _get_redis(self) -> Any:
        if self._redis is not None:
            return self._redis
        try:
            import redis
            from config import settings
            client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
            client.ping()
            self._redis = client
            return self._redis
        except Exception as exc:
            logger.debug("Discovery Redis not available, using DB authority: %s", exc)
            return None

    def is_query_in_cooldown(
        self,
        query: str,
        page: int = 1,
        db: Optional[Session] = None,
        now: Optional[datetime] = None,
    ) -> bool:
        """Check whether exact normalized query + page was successfully run in the last 24h."""
        normalized = normalize_discovery_query(query)
        if not normalized:
            return False

        key = query_cooldown_key(normalized, page)
        r = self._get_redis()
        if r is not None:
            try:
                if r.exists(key):
                    return True
            except Exception as e:
                logger.warning("Redis cooldown check error: %s", e)

        # Fallback to PostgreSQL as durable authority (Amendment 5)
        now_dt = now or datetime.now(timezone.utc)
        since_dt = now_dt - timedelta(seconds=COOLDOWN_SECONDS_24H)

        should_close = False
        if db is None:
            try:
                db = SessionLocal()
                should_close = True
            except Exception:
                return False

        try:
            prior = (
                db.query(DiscoveryQueryLog)
                .filter(
                    DiscoveryQueryLog.normalized_query == normalized,
                    DiscoveryQueryLog.page == page,
                    DiscoveryQueryLog.execution_state.in_([STATE_SUCCESS_PRODUCTIVE, STATE_SUCCESS_EXHAUSTED]),
                    DiscoveryQueryLog.executed_at >= since_dt,
                )
                .first()
            )
            if prior is not None:
                # Re-seed Redis cache if Redis had lost it (recovery across restart)
                if r is not None:
                    try:
                        elapsed = int((now_dt - prior.executed_at.replace(tzinfo=timezone.utc)).total_seconds())
                        remaining = max(1, COOLDOWN_SECONDS_24H - elapsed)
                        r.setex(key, remaining, "1")
                    except Exception:
                        pass
                return True
            return False
        finally:
            if should_close and db is not None:
                db.close()

    def filter_previously_seen_urls(self, urls: List[str]) -> Tuple[List[str], List[str]]:
        """Separate fresh URLs from previously seen URLs using Redis set and/or DB."""
        if not urls:
            return [], []
        r = self._get_redis()
        seen: Set[str] = set()
        if r is not None:
            try:
                pipe = r.pipeline()
                for u in urls:
                    pipe.sismember("salesoorja:discovery:seen_urls", u)
                results = pipe.execute()
                for u, is_member in zip(urls, results):
                    if is_member:
                        seen.add(u)
            except Exception:
                pass
        new_urls = [u for u in urls if u not in seen]
        seen_urls = [u for u in urls if u in seen]
        return new_urls, seen_urls

    def mark_urls_seen(self, urls: List[str]) -> None:
        """Add URLs to seen set."""
        if not urls:
            return
        r = self._get_redis()
        if r is not None:
            try:
                r.sadd("salesoorja:discovery:seen_urls", *urls[:500])
            except Exception:
                pass

    def compute_productivity_and_exhaustion(
        self,
        results_count: int,
        duplicate_count: int,
        new_companies: int,
        strong_opps: int,
        incomplete_opps: int,
        weak_opps: int,
        invalid_entities: int,
    ) -> Tuple[float, float, str, Dict[str, Any]]:
        """Transparent weighted productivity and exhaustion calculation (Amendment 2)."""
        new_evidence_count = max(0, results_count - duplicate_count)
        raw_score = (
            3.0 * strong_opps
            + 1.5 * incomplete_opps
            + 1.0 * new_companies
            + 0.5 * new_evidence_count
            - 0.5 * duplicate_count
            - 1.0 * invalid_entities
        )
        yield_score = max(0.0, round(float(raw_score), 2))
        exhaustion_score = round(float(duplicate_count) / max(1, results_count), 2)

        # State determination
        if results_count == 0 or (exhaustion_score >= 0.70 and new_companies == 0):
            state = STATE_SUCCESS_EXHAUSTED
        elif yield_score >= 1.5 or (new_companies >= 1 and (strong_opps + incomplete_opps) >= 1):
            state = STATE_SUCCESS_PRODUCTIVE
        else:
            state = STATE_SUCCESS_PRODUCTIVE if new_companies > 0 else STATE_SUCCESS_EXHAUSTED

        components = {
            "results_count": results_count,
            "duplicate_count": duplicate_count,
            "new_evidence_count": new_evidence_count,
            "new_companies": new_companies,
            "strong_opps": strong_opps,
            "incomplete_opps": incomplete_opps,
            "weak_opps": weak_opps,
            "invalid_entities": invalid_entities,
            "raw_yield_score": round(raw_score, 2),
            "yield_score": yield_score,
            "exhaustion_score": exhaustion_score,
        }
        return yield_score, exhaustion_score, state, components

    def record_query_execution(
        self,
        query: str,
        page: int,
        sector: str,
        trigger: str,
        geography: str,
        execution_state: str,
        results_count: int = 0,
        unique_results: int = 0,
        new_companies: int = 0,
        strong_opps: int = 0,
        incomplete_opps: int = 0,
        weak_opps: int = 0,
        yield_score: float = 0.0,
        exhaustion_score: float = 0.0,
        metadata_json: Optional[Dict[str, Any]] = None,
        analyst_decision_id: Optional[int] = None,
        db: Optional[Session] = None,
        now: Optional[datetime] = None,
    ) -> DiscoveryQueryLog:
        """Persist discovery query metrics to PostgreSQL and apply 24h Redis cooldown for successes."""
        normalized = normalize_discovery_query(query)
        now_dt = now or datetime.now(timezone.utc)

        meta = dict(metadata_json or {})
        meta["recorded_at"] = now_dt.isoformat()

        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True

        try:
            log_record = DiscoveryQueryLog(
                analyst_decision_id=analyst_decision_id,
                query=query,
                normalized_query=normalized,
                page=page,
                sector=sector,
                trigger=trigger,
                geography=geography,
                execution_state=execution_state,
                executed_at=now_dt,
                results_count=results_count,
                unique_results=unique_results,
                new_companies=new_companies,
                strong_opportunities=strong_opps,
                incomplete_opportunities=incomplete_opps,
                weak_opportunities=weak_opps,
                yield_score=yield_score,
                exhaustion_score=exhaustion_score,
                metadata_json=meta,
            )

            db.add(log_record)
            db.commit()
            db.refresh(log_record)

            # Apply 24h cooldown ONLY for successful queries (Amendment 4)
            if execution_state in {STATE_SUCCESS_PRODUCTIVE, STATE_SUCCESS_EXHAUSTED}:
                key = query_cooldown_key(normalized, page)
                r = self._get_redis()
                if r is not None:
                    try:
                        r.setex(key, COOLDOWN_SECONDS_24H, "1")
                    except Exception as e:
                        logger.warning("Redis cooldown set error: %s", e)

            return log_record
        finally:
            if should_close and db is not None:
                db.close()


discovery_query_memory = DiscoveryQueryMemory()
