"""Durable PostgreSQL Funnel Work Item model for Salesoorja production pipeline.

PostgreSQL is the single source of truth for workflow state.
Redis is strictly for fast leases, dispatch signals, and short-lived caching.
"""
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import relationship

from database import Base

# Canonical Production Pipeline Stages
STAGE_DISCOVERY_CANDIDATE = "DISCOVERY_CANDIDATE"
STAGE_OPPORTUNITY_RESEARCH = "OPPORTUNITY_RESEARCH"
STAGE_FACILITY_VERIFICATION = "FACILITY_VERIFICATION"
STAGE_PERSON_RESEARCH = "PERSON_RESEARCH"
STAGE_PERSON_VERIFICATION = "PERSON_VERIFICATION"
STAGE_CONTACT_ENRICHMENT = "CONTACT_ENRICHMENT"
STAGE_PERSONALIZATION = "PERSONALIZATION"
STAGE_SEND_READY = "SEND_READY"
STAGE_SENT = "SENT"
STAGE_HOLD = "HOLD"
STAGE_FAILED_RETRYABLE = "FAILED_RETRYABLE"
STAGE_CLOSED = "CLOSED"

ALL_STAGES = [
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
]

STATUS_PENDING = "PENDING"
STATUS_IN_PROGRESS = "IN_PROGRESS"
STATUS_COMPLETED = "COMPLETED"
STATUS_HELD = "HELD"
STATUS_FAILED = "FAILED"


class FunnelWorkItem(Base):
    __tablename__ = "funnel_work_items"

    id = Column(Integer, primary_key=True, index=True)

    # Core Entity Relationships
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True)
    opportunity_id = Column(Integer, ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=True, index=True)
    person_id = Column(Integer, ForeignKey("persons.id", ondelete="CASCADE"), nullable=True, index=True)

    # Provenance Links
    source_query_id = Column(Integer, ForeignKey("discovery_query_logs.id", ondelete="SET NULL"), nullable=True, index=True)
    analyst_decision_id = Column(Integer, ForeignKey("business_analyst_decisions.id", ondelete="SET NULL"), nullable=True, index=True)

    # Workflow State
    current_stage = Column(String(50), nullable=False, default=STAGE_DISCOVERY_CANDIDATE, index=True)
    status = Column(String(30), nullable=False, default=STATUS_PENDING, index=True)
    priority = Column(Integer, nullable=False, default=50, index=True)

    # Idempotency & Concurrency Guards
    idempotency_key = Column(String(255), unique=True, nullable=False, index=True)
    locked_by = Column(String(100), nullable=True)
    lock_expires_at = Column(DateTime(timezone=True), nullable=True, index=True)

    # Execution Tracking
    attempt_count = Column(Integer, nullable=False, default=0)
    last_attempt_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)
    available_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    # Payload & Telemetry (evidence snippets, facility evidence, reasoner assessments, claims, etc.)
    payload_json = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    company = relationship("Company", foreign_keys=[company_id])
    opportunity = relationship("Opportunity", foreign_keys=[opportunity_id])
    person = relationship("Person", foreign_keys=[person_id])
    source_query = relationship("DiscoveryQueryLog", foreign_keys=[source_query_id])
    analyst_decision = relationship("BusinessAnalystDecision", foreign_keys=[analyst_decision_id])

    __table_args__ = (
        Index("ix_funnel_work_stage_status", "current_stage", "status"),
        Index("ix_funnel_work_available_priority", "available_at", "priority"),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "company_id": self.company_id,
            "opportunity_id": self.opportunity_id,
            "person_id": self.person_id,
            "source_query_id": self.source_query_id,
            "analyst_decision_id": self.analyst_decision_id,
            "current_stage": self.current_stage,
            "status": self.status,
            "priority": self.priority,
            "idempotency_key": self.idempotency_key,
            "locked_by": self.locked_by,
            "lock_expires_at": self.lock_expires_at.isoformat() if self.lock_expires_at else None,
            "attempt_count": self.attempt_count,
            "last_attempt_at": self.last_attempt_at.isoformat() if self.last_attempt_at else None,
            "last_error": self.last_error,
            "available_at": self.available_at.isoformat() if self.available_at else None,
            "payload_json": self.payload_json or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
