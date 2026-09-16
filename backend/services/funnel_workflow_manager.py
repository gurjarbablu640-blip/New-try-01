"""Durable PostgreSQL Funnel Workflow Manager.

Manages:
- Transactional stage transitions
- Worker leases and crash recovery
- At-least-once processing with stage idempotency
- Stage-aware backpressure
- Queue depth telemetry
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from models.funnel_work_item import (
    FunnelWorkItem,
    STAGE_DISCOVERY_CANDIDATE,
    STAGE_OPPORTUNITY_RESEARCH,
    STAGE_FACILITY_VERIFICATION,
    STAGE_PERSON_RESEARCH,
    STAGE_PERSON_VERIFICATION,
    STAGE_CONTACT_ENRICHMENT,
    STAGE_PERSONALIZATION,
    STAGE_SEND_READY,
    STAGE_SENT,
    STAGE_HOLD,
    STAGE_FAILED_RETRYABLE,
    STAGE_CLOSED,
    ALL_STAGES,
    STATUS_PENDING,
    STATUS_IN_PROGRESS,
    STATUS_COMPLETED,
    STATUS_HELD,
    STATUS_FAILED,
)

logger = logging.getLogger(__name__)

# Configurable Stage Backpressure Thresholds
DEFAULT_STAGE_LIMITS: Dict[str, int] = {
    STAGE_DISCOVERY_CANDIDATE: 50,
    STAGE_OPPORTUNITY_RESEARCH: 30,
    STAGE_FACILITY_VERIFICATION: 30,
    STAGE_PERSON_RESEARCH: 25,
    STAGE_PERSON_VERIFICATION: 25,
    STAGE_CONTACT_ENRICHMENT: 20,
    STAGE_PERSONALIZATION: 20,
    STAGE_SEND_READY: 30,  # Send-ready buffer
}


class FunnelWorkflowManager:
    """PostgreSQL-backed workflow orchestrator for Salesoorja funnel."""

    def __init__(self, stage_limits: Optional[Dict[str, int]] = None):
        self.stage_limits = stage_limits or dict(DEFAULT_STAGE_LIMITS)

    def enqueue_candidate(
        self,
        db: Session,
        *,
        company_id: Optional[int] = None,
        source_query_id: Optional[int] = None,
        analyst_decision_id: Optional[int] = None,
        payload: Optional[Dict[str, Any]] = None,
        priority: int = 50,
        idempotency_key: Optional[str] = None,
    ) -> Tuple[FunnelWorkItem, bool]:
        """Enqueue a newly discovered candidate into DISCOVERY_CANDIDATE stage.

        Returns (item, created_bool).
        """
        payload = payload or {}
        comp_name = payload.get("company_name") or f"company_{company_id or 'unknown'}"
        evidence_url = payload.get("evidence_url") or ""
        
        if not idempotency_key:
            # Deterministic composite key: company + source_query or url
            idempotency_key = f"candidate:{comp_name.strip().lower()}:{source_query_id or evidence_url[:80]}"

        # Check existing item
        existing = db.query(FunnelWorkItem).filter(FunnelWorkItem.idempotency_key == idempotency_key).first()
        if existing:
            return existing, False

        item = FunnelWorkItem(
            company_id=company_id,
            source_query_id=source_query_id,
            analyst_decision_id=analyst_decision_id,
            current_stage=STAGE_DISCOVERY_CANDIDATE,
            status=STATUS_PENDING,
            priority=priority,
            idempotency_key=idempotency_key,
            payload_json=payload,
            attempt_count=0,
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        logger.info("[FUNNEL_ENQUEUE] Item %s enqueued in %s: %s", item.id, STAGE_DISCOVERY_CANDIDATE, comp_name)
        return item, True

    def acquire_lease(
        self,
        db: Session,
        stage: str,
        worker_id: str,
        limit: int = 1,
        lease_duration_seconds: int = 300,
    ) -> List[FunnelWorkItem]:
        """Acquire lease on available pending items or expired leases in stage."""
        now = datetime.now(timezone.utc)
        lease_expiry = now + timedelta(seconds=lease_duration_seconds)

        # 1. Recover expired leases first
        self.recover_expired_leases(db)

        # 2. Select available items with row locking
        query = (
            db.query(FunnelWorkItem)
            .filter(
                FunnelWorkItem.current_stage == stage,
                FunnelWorkItem.status == STATUS_PENDING,
                FunnelWorkItem.available_at <= now,
            )
            .order_by(FunnelWorkItem.priority.desc(), FunnelWorkItem.created_at.asc())
            .limit(limit)
        )

        try:
            # PostgreSQL supports skip_locked for non-blocking concurrent worker pickup
            items = query.with_for_update(skip_locked=True).all()
        except Exception:
            # Fallback for dialects without skip_locked support in test SQLite
            items = query.all()

        leased_items = []
        for item in items:
            item.status = STATUS_IN_PROGRESS
            item.locked_by = worker_id
            item.lock_expires_at = lease_expiry
            item.attempt_count += 1
            item.last_attempt_at = now
            leased_items.append(item)

        if leased_items:
            db.commit()
            for it in leased_items:
                db.refresh(it)
                logger.info("[FUNNEL_LEASE] Worker %s leased item %s in stage %s", worker_id, it.id, stage)

        return leased_items

    def transition_stage(
        self,
        db: Session,
        item_id: int,
        next_stage: str,
        *,
        status: str = STATUS_PENDING,
        payload_updates: Optional[Dict[str, Any]] = None,
        company_id: Optional[int] = None,
        opportunity_id: Optional[int] = None,
        person_id: Optional[int] = None,
    ) -> Optional[FunnelWorkItem]:
        """Atomically transition item to next stage and release worker lock."""
        item = db.query(FunnelWorkItem).filter(FunnelWorkItem.id == item_id).first()
        if not item:
            logger.warning("[FUNNEL_TRANSITION] Item %s not found", item_id)
            return None

        old_stage = item.current_stage
        item.current_stage = next_stage
        item.status = status
        item.locked_by = None
        item.lock_expires_at = None

        if company_id is not None:
            item.company_id = company_id
        if opportunity_id is not None:
            item.opportunity_id = opportunity_id
        if person_id is not None:
            item.person_id = person_id

        if payload_updates:
            from sqlalchemy.orm.attributes import flag_modified
            current_payload = dict(item.payload_json or {})
            current_payload.update(payload_updates)
            item.payload_json = current_payload
            flag_modified(item, "payload_json")

        db.commit()
        db.refresh(item)
        logger.info("[FUNNEL_STAGE_TRANSITION] Item %s: %s -> %s (status=%s)", item_id, old_stage, next_stage, status)
        return item

    def hold_item(
        self,
        db: Session,
        item_id: int,
        reason: str,
        *,
        payload_updates: Optional[Dict[str, Any]] = None,
    ) -> Optional[FunnelWorkItem]:
        """Transition item to HOLD state with exact reason."""
        updates = payload_updates or {}
        updates["hold_reason"] = reason
        updates["held_at"] = datetime.now(timezone.utc).isoformat()
        return self.transition_stage(
            db,
            item_id,
            next_stage=STAGE_HOLD,
            status=STATUS_HELD,
            payload_updates=updates,
        )

    def release_lease(
        self,
        db: Session,
        item_id: int,
        *,
        error: Optional[str] = None,
        delay_seconds: int = 0,
    ) -> Optional[FunnelWorkItem]:
        """Release lock and return item to PENDING for retry."""
        item = db.query(FunnelWorkItem).filter(FunnelWorkItem.id == item_id).first()
        if not item:
            return None

        item.locked_by = None
        item.lock_expires_at = None
        if error:
            item.last_error = error
            logger.warning("[FUNNEL_LEASE_RELEASE] Item %s error: %s", item_id, error)

        if delay_seconds > 0:
            item.available_at = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)

        item.status = STATUS_PENDING
        db.commit()
        db.refresh(item)
        return item

    def recover_expired_leases(self, db: Session) -> int:
        """Reset items whose lease expired while in progress (worker crash recovery)."""
        now = datetime.now(timezone.utc)
        expired = (
            db.query(FunnelWorkItem)
            .filter(
                FunnelWorkItem.status == STATUS_IN_PROGRESS,
                FunnelWorkItem.lock_expires_at < now,
            )
            .all()
        )

        recovered = 0
        for item in expired:
            logger.warning("[LEASE_RECOVERED] Item %s in %s (leased by %s) expired; resetting to PENDING", item.id, item.current_stage, item.locked_by)
            item.status = STATUS_PENDING
            item.locked_by = None
            item.lock_expires_at = None
            item.last_error = "Worker lease expired; auto-recovered"
            recovered += 1

        if recovered > 0:
            db.commit()
        return recovered

    def get_stage_depths(self, db: Session) -> Dict[str, int]:
        """Return count of active items in each stage."""
        stats = (
            db.query(FunnelWorkItem.current_stage, func.count(FunnelWorkItem.id))
            .filter(FunnelWorkItem.status.in_([STATUS_PENDING, STATUS_IN_PROGRESS]))
            .group_by(FunnelWorkItem.current_stage)
            .all()
        )
        depths = {stage: 0 for stage in ALL_STAGES}
        for stage, count in stats:
            depths[stage] = int(count)
        return depths

    def is_backpressure_active(self, db: Session, stage: str) -> bool:
        """Check if stage backlog exceeds its backpressure threshold."""
        limit = self.stage_limits.get(stage, 50)
        depths = self.get_stage_depths(db)
        return depths.get(stage, 0) >= limit

    def get_send_ready_buffer(self, db: Session, limit: int = 10) -> List[FunnelWorkItem]:
        """Fetch qualified items ready for scheduled send, ordered by priority."""
        return (
            db.query(FunnelWorkItem)
            .filter(
                FunnelWorkItem.current_stage == STAGE_SEND_READY,
                FunnelWorkItem.status == STATUS_PENDING,
            )
            .order_by(FunnelWorkItem.priority.desc(), FunnelWorkItem.created_at.asc())
            .limit(limit)
            .all()
        )


# Global singleton instance
funnel_workflow_manager = FunnelWorkflowManager()
