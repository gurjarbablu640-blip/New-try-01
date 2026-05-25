"""Outreach Drafts model."""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, ARRAY, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from database import Base


class OutreachDraft(Base):
    __tablename__ = "outreach_drafts"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)

    # Core outreach content
    email_subject = Column(Text)
    email_body = Column(Text)
    whatsapp_message = Column(Text)

    # Enhanced fields (Module 10)
    email_subject_variants = Column(ARRAY(Text), default=[])
    email_ps = Column(Text)
    call_opener = Column(Text)
    objection_responses = Column(JSONB)
    free_value_offer_outline = Column(Text)
    linkedin_connection_note = Column(Text)
    followup_day3_whatsapp = Column(Text)
    followup_day7_email = Column(Text)
    followup_day14_breakup = Column(Text)

    # Metadata
    generated_by = Column(String(100), default="claude")
    generation_context = Column(JSONB)  # Store personalization_context used

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    company = relationship("Company", back_populates="outreach_drafts")
