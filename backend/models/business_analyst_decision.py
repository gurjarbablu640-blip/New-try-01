"""Business Analyst Decision model for Salesoorja Strategic Search Intelligence."""
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
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


class BusinessAnalystDecision(Base):
    """Authoritative durable record of a Pre-Serper strategic search decision."""

    __tablename__ = "business_analyst_decisions"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, server_default=func.now(), index=True, nullable=False)

    # ── Strategic Target ───────────────────────────────────────────────────
    sector = Column(String(100), index=True, nullable=False)
    trigger_family = Column(String(100), index=True, nullable=False)
    geography = Column(String(100), index=True, nullable=False)

    # ── Mode & Priority ────────────────────────────────────────────────────
    mode = Column(String(50), default="EXPLOIT", index=True, nullable=False)  # EXPLOIT, EXPLORE, COLD_START
    priority_score = Column(Float, default=0.0, nullable=False)
    confidence = Column(Float, default=0.0, nullable=False)
    search_budget = Column(Integer, default=3, nullable=False)

    # ── Raw Historical Outcome Counts (Exposure Basis) ─────────────────────
    historical_query_count = Column(Integer, default=0, nullable=False)
    productive_query_count = Column(Integer, default=0, nullable=False)
    strong_opportunities = Column(Integer, default=0, nullable=False)
    incomplete_opportunities = Column(Integer, default=0, nullable=False)
    apollo_reached = Column(Integer, default=0, nullable=False)
    person_passes = Column(Integer, default=0, nullable=False)
    emails_sent = Column(Integer, default=0, nullable=False)
    replies = Column(Integer, default=0, nullable=False)
    enquiries = Column(Integer, default=0, nullable=False)

    # ── Normalized Performance Rates (Exposure Normalized) ─────────────────
    productive_query_rate = Column(Float, default=0.0, nullable=False)
    strong_per_query = Column(Float, default=0.0, nullable=False)
    apollo_per_query = Column(Float, default=0.0, nullable=False)
    person_pass_per_query = Column(Float, default=0.0, nullable=False)
    email_per_query = Column(Float, default=0.0, nullable=False)
    reply_per_email = Column(Float, default=0.0, nullable=False)
    enquiry_per_query = Column(Float, default=0.0, nullable=False)
    enquiry_per_email = Column(Float, default=0.0, nullable=False)

    # ── Strategy Rationale & Metadata ─────────────────────────────────────
    score_components = Column(JSON, nullable=True)
    rationale = Column(Text, nullable=True)

    # ── Substitution Tracking (When Cooled/Exhausted) ──────────────────────
    was_substituted = Column(Boolean, default=False, nullable=False)
    substitution_reason = Column(Text, nullable=True)
    actual_sector = Column(String(100), nullable=True)
    actual_trigger = Column(String(100), nullable=True)
    actual_geography = Column(String(100), nullable=True)

    # ── Downstream Attribution / Future Outcomes ──────────────────────────
    final_outcomes_json = Column(JSON, nullable=True)

    # ── Authoritative 1-to-Many Relationship via discovery_query_logs.analyst_decision_id ──
    query_logs = relationship(
        "DiscoveryQueryLog",
        back_populates="analyst_decision",
        foreign_keys="DiscoveryQueryLog.analyst_decision_id",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_analyst_decision_sector_trigger_geo", "sector", "trigger_family", "geography"),
        Index("ix_analyst_decision_mode_created", "mode", "created_at"),
    )

    @property
    def resulting_query_ids(self) -> list[int]:
        """Derived convenience property computing query IDs from authoritative FK."""
        if self.query_logs:
            return [q.id for q in self.query_logs if q.id is not None]
        return []

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "sector": self.sector,
            "trigger_family": self.trigger_family,
            "geography": self.geography,
            "mode": self.mode,
            "priority_score": self.priority_score,
            "confidence": self.confidence,
            "search_budget": self.search_budget,
            "historical_query_count": self.historical_query_count,
            "productive_query_count": self.productive_query_count,
            "productive_query_rate": self.productive_query_rate,
            "strong_opportunities": self.strong_opportunities,
            "strong_per_query": self.strong_per_query,
            "incomplete_opportunities": self.incomplete_opportunities,
            "apollo_reached": self.apollo_reached,
            "apollo_per_query": self.apollo_per_query,
            "person_passes": self.person_passes,
            "person_pass_per_query": self.person_pass_per_query,
            "emails_sent": self.emails_sent,
            "email_per_query": self.email_per_query,
            "replies": self.replies,
            "reply_per_email": self.reply_per_email,
            "enquiries": self.enquiries,
            "enquiry_per_query": self.enquiry_per_query,
            "enquiry_per_email": self.enquiry_per_email,
            "score_components": self.score_components or {},
            "rationale": self.rationale,
            "was_substituted": self.was_substituted,
            "substitution_reason": self.substitution_reason,
            "actual_sector": self.actual_sector,
            "actual_trigger": self.actual_trigger,
            "actual_geography": self.actual_geography,
            "resulting_query_ids": self.resulting_query_ids,
        }
