"""Pipeline CRM models - Module 11."""
from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Text, Boolean, Numeric, Date, func
)
from sqlalchemy.orm import relationship
from backend.database import Base


class PipelineStage(Base):
    """CRM Pipeline stage tracking for each company."""
    __tablename__ = "pipeline_stages"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    person_id = Column(Integer, ForeignKey("persons.id"), nullable=True)

    stage = Column(Text, default="New", index=True)
    # Stages: New → Contacted → Replied → Meeting Booked →
    #         Proposal Sent → Negotiation → Won → Lost → Nurture

    contact_channel = Column(Text)  # 'email', 'whatsapp', 'phone', 'linkedin'
    next_action = Column(Text)
    next_action_date = Column(Date)
    deal_value_est = Column(Numeric)
    loss_reason = Column(Text)
    notes = Column(Text)
    last_touched = Column(DateTime, server_default=func.now())

    created_at = Column(DateTime, server_default=func.now())

    # Relationships
    company = relationship("Company", back_populates="pipeline_stages")
    person = relationship("Person", back_populates="pipeline_stages")
    activities = relationship("Activity", back_populates="pipeline")

    @property
    def days_in_stage(self):
        """Calculate days since last touched."""
        from datetime import datetime
        if self.last_touched:
            return (datetime.utcnow() - self.last_touched).days
        return 0


class Activity(Base):
    """Sales activity log."""
    __tablename__ = "activities"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    person_id = Column(Integer, ForeignKey("persons.id"), nullable=True)
    pipeline_id = Column(Integer, ForeignKey("pipeline_stages.id"), nullable=True)

    activity_type = Column(Text, nullable=False)
    # Types: email_sent, whatsapp_sent, call_made, replied,
    #        meeting_booked, no_answer, linkedin_sent
    outcome = Column(Text)
    notes = Column(Text)

    occurred_at = Column(DateTime, server_default=func.now())

    # Relationships
    company = relationship("Company", back_populates="activities")
    person = relationship("Person", back_populates="activities")
    pipeline = relationship("PipelineStage", back_populates="activities")


class ABTestResult(Base):
    """A/B test tracking for subject line variants - Module 17."""
    __tablename__ = "ab_test_results"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    subject_variant = Column(Integer)  # 1-5 which variant was used
    opened = Column(Boolean, default=False)
    replied = Column(Boolean, default=False)

    sent_at = Column(DateTime, server_default=func.now())


class LeadRating(Base):
    """User lead ratings for ICP learning - Module 15."""
    __tablename__ = "lead_ratings"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    user_rating = Column(Integer, nullable=False)  # 1-5
    rating_reason = Column(Text)  # 'wrong industry', 'too small', 'perfect fit'

    rated_at = Column(DateTime, server_default=func.now())

    # Relationships
    company = relationship("Company", back_populates="lead_ratings")
