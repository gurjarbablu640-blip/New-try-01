"""PostgreSQL Durable Research Evidence Record Model.

Persists fetched web page content and extracted structured facts for:
- Discovery opportunity grounding
- Cross-source corroboration and syndication deduplication
- Preventing redundant page fetches within 24h freshness windows
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON

from database import Base

# Dialect-safe JSON type
JSONType = JSON().with_variant(JSONB, "postgresql")


class ResearchEvidenceRecord(Base):
    """PostgreSQL durable model for web page evidence and structured factual extraction."""

    __tablename__ = "research_evidence_records"

    id = Column(Integer, primary_key=True, index=True)
    url = Column(String(2048), nullable=False, index=True)
    normalized_url = Column(String(2048), nullable=False, index=True)
    content_hash = Column(String(64), nullable=False, index=True)
    title = Column(String(1000), nullable=True)
    publication_date = Column(String(100), nullable=True)
    author = Column(String(255), nullable=True)
    publisher = Column(String(255), nullable=True)
    retrieved_at = Column(DateTime(timezone=True), default=func.now(), index=True, nullable=False)
    fetch_status = Column(String(50), nullable=False, default="FETCH_SUCCESS", index=True)
    http_status = Column(Integer, nullable=True)
    source_type = Column(String(50), nullable=False, default="SECONDARY")
    relevance_score = Column(Float, nullable=False, default=0.0)
    extracted_text = Column(Text, nullable=True)
    evidence_json = Column(JSONType, nullable=False, default=dict)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True)
    query_log_id = Column(Integer, ForeignKey("discovery_query_logs.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now(), nullable=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "url": self.url,
            "normalized_url": self.normalized_url,
            "content_hash": self.content_hash,
            "title": self.title,
            "publication_date": self.publication_date,
            "author": self.author,
            "publisher": self.publisher,
            "retrieved_at": self.retrieved_at.isoformat() if self.retrieved_at else None,
            "fetch_status": self.fetch_status,
            "http_status": self.http_status,
            "source_type": self.source_type,
            "relevance_score": self.relevance_score,
            "extracted_text_preview": (self.extracted_text[:300] + "...") if self.extracted_text and len(self.extracted_text) > 300 else self.extracted_text,
            "evidence_json": self.evidence_json or {},
            "company_id": self.company_id,
            "query_log_id": self.query_log_id,
        }
