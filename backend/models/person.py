"""Person / Contact model."""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON, func
from sqlalchemy.orm import relationship
from database import Base


class Person(Base):
    __tablename__ = "persons"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    full_name = Column(String(300))
    designation = Column(String(300))
    email = Column(String(300))
    normalized_email = Column(String(300), index=True)
    phone = Column(String(100))
    normalized_phone = Column(String(50), index=True)
    linkedin_url = Column(String(500))
    seniority_level = Column(String(100))
    department = Column(String(200))
    apollo_id = Column(String(100), index=True)
    email_verification_status = Column(String(50), default="unverified", index=True)
    email_verification_reason = Column(String(200))
    email_verified_at = Column(DateTime)
    is_decision_maker = Column(Integer, default=0)  # 0=unknown, 1=yes, 2=no

    # ── Decision-Maker Discovery Fields ─────────────────────────────────
    discovery_status = Column(String(50), default="UNKNOWN", index=True)
    # UNKNOWN, PERSONA_INFERRED, PERSON_CANDIDATE, PERSON_PUBLICLY_VERIFIED,
    # APOLLO_ENRICHED, EMAIL_VERIFIED
    discovery_source = Column(String(100))
    # e.g. "web_research", "apollo", "company_website", "manual"
    evidence_json = Column(JSON)
    # Structured evidence trail: [{source, url, snippet, retrieved_at, confidence}]

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    company = relationship("Company", back_populates="persons")
    pipeline_stages = relationship("PipelineStage", back_populates="person")
    activities = relationship(
    "PipelineActivity",
    back_populates="person"
)
