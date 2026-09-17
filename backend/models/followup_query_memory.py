"""PostgreSQL Durable Model for Follow-Up Query Memory (Task 3D.1F).

Persists follow-up search queries and evidence outcomes keyed by:
COMPANY / OPERATING_ENTITY + MISSING_FACT

Used by the LLM Information-Gain Gate to:
1. Prevent repetitive queries with no material evidence gain.
2. Enforce maximum 2 unsuccessful attempts per missing fact.
3. Escalate research strategy (GENERAL_WEB -> OFFICIAL_COMPANY -> GOVERNMENT_SOURCE).
4. Provide complete prior search history to DeepSeek/Gemini.
5. Provide multi-process, concurrency-safe persistence for backend + Celery.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON

from database import Base

# Dialect-safe JSON type (JSONB on PostgreSQL, JSON on SQLite)
JSONType = JSON().with_variant(JSONB, "postgresql")


class FollowupQueryMemoryRecord(Base):
    """PostgreSQL durable model for follow-up research query memory."""

    __tablename__ = "followup_query_memory_records"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(
        Integer,
        ForeignKey("companies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    normalized_operating_entity = Column(String(255), nullable=False, index=True)
    missing_fact = Column(String(100), nullable=False, index=True)
    query = Column(Text, nullable=False)
    timestamp = Column(
        DateTime(timezone=True),
        default=func.now(),
        index=True,
        nullable=False,
    )
    research_strategy = Column(String(50), nullable=False, default="GENERAL_WEB")
    result_count = Column(Integer, nullable=False, default=0)
    useful_urls = Column(JSONType, nullable=False, default=list)
    new_evidence_found = Column(Boolean, nullable=False, default=False)
    evidence_type_found = Column(String(100), nullable=True)
    source_domains = Column(JSONType, nullable=False, default=list)
    funnel_state_before = Column(String(50), nullable=True)
    funnel_state_after = Column(String(50), nullable=True)
    llm_reasoning = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index(
            "ix_followup_entity_fact",
            "normalized_operating_entity",
            "missing_fact",
            "timestamp",
        ),
        Index("ix_followup_company_fact", "company_id", "missing_fact"),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "company_id": self.company_id,
            "normalized_operating_entity": self.normalized_operating_entity,
            "missing_fact": self.missing_fact,
            "query": self.query,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "research_strategy": self.research_strategy,
            "result_count": self.result_count,
            "useful_urls": self.useful_urls or [],
            "new_evidence_found": self.new_evidence_found,
            "evidence_type_found": self.evidence_type_found,
            "source_domains": self.source_domains or [],
            "funnel_state_before": self.funnel_state_before,
            "funnel_state_after": self.funnel_state_after,
            "llm_reasoning": self.llm_reasoning,
        }
