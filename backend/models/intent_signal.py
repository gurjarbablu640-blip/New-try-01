"""Company Intent Signals model."""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Float, func
from sqlalchemy.orm import relationship
from database import Base


class CompanyIntentSignal(Base):
    __tablename__ = "company_intent_signals"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)

    signal_type = Column(String(100), nullable=False, index=True)
    # Signal types: JOB_POSTING_QA, NEWS_EXPANSION, NABL_RENEWAL_DUE,
    #               ISO_AUDIT_WINDOW, IMPORT_SPIKE, COMPETITOR_PAIN
    weight_applied = Column(Float, default=0.0)
    source_url = Column(Text)
    source_snippet = Column(Text)
    urgency_reason = Column(Text)
    opportunity_note = Column(Text)

    detected_at = Column(DateTime, server_default=func.now())
    expires_at = Column(DateTime)  # Signal relevance expiry
    is_active = Column(Integer, default=1)  # 1=active, 0=expired

    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    company = relationship("Company", back_populates="intent_signals")
