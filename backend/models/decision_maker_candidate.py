"""Decision-Maker Candidate model — tracks the full lifecycle of person discovery.

Lifecycle statuses:
  PERSONA_INFERRED → PERSON_CANDIDATE → PERSON_PUBLICLY_VERIFIED
  → CONTACT_ENRICHMENT_READY → APOLLO_ENRICHED → EMAIL_VERIFIED

Rejection: PERSON_REJECTED (with structured reason)
"""
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Text, JSON, ForeignKey, func,
)
from sqlalchemy.orm import relationship
from database import Base


# ── Verification Status Enum Values ──────────────────────────────────────
VERIFICATION_STATUSES = [
    "PERSONA_INFERRED",
    "PERSON_CANDIDATE",
    "PERSON_PUBLICLY_VERIFIED",
    "CONTACT_ENRICHMENT_READY",
    "APOLLO_ENRICHED",
    "EMAIL_VERIFIED",
    "PERSON_REJECTED",
]

# ── Apollo Enrichment Status Enum Values ─────────────────────────────────
APOLLO_ENRICHMENT_STATUSES = [
    "NOT_ATTEMPTED",
    "ENRICHED",
    "APOLLO_BLOCKED",
    "NO_RESULT",
    "ERROR",
]

# ── Email Status Enum Values ────────────────────────────────────────────
EMAIL_STATUSES = [
    "NOT_FOUND",
    "EMAIL_FOUND",
    "EMAIL_VALIDATED",
    "EMAIL_VERIFIED",
    "EMAIL_BOUNCE_RISK",
    "EMAIL_SUPPRESSED",
]

# ── Rejection Reason Enum Values ────────────────────────────────────────
REJECTION_REASONS = [
    "company_mismatch",
    "outdated_employment",
    "irrelevant_role",
    "insufficient_evidence",
    "duplicate",
    "low_confidence",
    "wrong_facility",
    "conflicting_sources",
]

# ── Stakeholder Role Types ──────────────────────────────────────────────
STAKEHOLDER_ROLES = [
    "User",
    "Identifier",
    "Evaluator",
    "Recommender",
    "Approver",
    "Purchaser",
    "Influencer",
    "Blocker",
]


class DecisionMakerCandidate(Base):
    """Tracks a single person-discovery candidate through the full pipeline.

    Each candidate represents one attempt to find a real decision-maker
    for a specific company + persona combination.
    """
    __tablename__ = "decision_maker_candidates"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    person_id = Column(Integer, ForeignKey("persons.id", ondelete="SET NULL"), nullable=True, index=True)

    # ── Persona ─────────────────────────────────────────────────────────
    target_persona = Column(String(200), nullable=False)  # e.g. "Quality / Metrology"
    target_titles = Column(JSON, default=[])  # ["Quality Head", "QA Manager", ...]
    stakeholder_role = Column(String(50))  # User, Evaluator, Approver, Purchaser, etc.
    contact_priority = Column(String(20), default="SECONDARY")  # PRIMARY, SECONDARY
    priority_reason = Column(Text)  # Why this person was selected as primary

    # ── Candidate ───────────────────────────────────────────────────────
    candidate_name = Column(String(300))
    candidate_title = Column(String(300))
    candidate_company_match = Column(Boolean, default=False)
    candidate_facility = Column(String(300))
    candidate_location = Column(String(300))

    # ── Evidence ────────────────────────────────────────────────────────
    evidence_sources = Column(JSON, default=[])
    # Each entry: {source, url, snippet, retrieved_at, confidence, evidence_type}
    public_profile_url = Column(Text)
    public_profile_evidence = Column(Text)
    search_queries_used = Column(JSON, default=[])

    # ── Verification ────────────────────────────────────────────────────
    verification_status = Column(String(50), default="PERSONA_INFERRED", index=True)
    verification_confidence = Column(Float, default=0.0)
    verification_notes = Column(Text)
    rejection_reason = Column(String(100))  # From REJECTION_REASONS
    rejection_details = Column(Text)

    # ── Person Match Score Dimensions ───────────────────────────────────
    score_company_match = Column(Float, default=0.0)  # 0-1
    score_role_relevance = Column(Float, default=0.0)
    score_facility_match = Column(Float, default=0.0)
    score_recency = Column(Float, default=0.0)
    score_evidence_quality = Column(Float, default=0.0)
    score_composite = Column(Float, default=0.0)  # Weighted aggregate

    # ── Apollo Enrichment ───────────────────────────────────────────────
    apollo_enrichment_status = Column(String(30), default="NOT_ATTEMPTED")
    apollo_email = Column(String(300))
    apollo_email_confidence = Column(String(50))
    apollo_phone = Column(String(100))
    apollo_response_json = Column(JSON)

    # ── Email Status ────────────────────────────────────────────────────
    email_status = Column(String(30), default="NOT_FOUND")

    # ── Adaptive Research ───────────────────────────────────────────────
    pending_research_tasks = Column(JSON, default=[])
    # Each: {task, reason, priority, status}

    # ── Timestamps ──────────────────────────────────────────────────────
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    verified_at = Column(DateTime)
    enriched_at = Column(DateTime)

    # ── Relationships ───────────────────────────────────────────────────
    company = relationship("Company", backref="decision_maker_candidates")
    person = relationship("Person", backref="decision_maker_candidates")
