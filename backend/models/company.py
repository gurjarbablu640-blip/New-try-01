"""Company model."""
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Text, ARRAY,
    Numeric, func
)
from sqlalchemy.orm import relationship
from backend.database import Base


class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(500), nullable=False, index=True)
    city = Column(String(200))
    state = Column(String(200))
    country = Column(String(100), default="India")
    industry = Column(String(300))
    search_keyword = Column(String(300))
    website = Column(String(500))
    phone = Column(String(100))
    email = Column(String(300))

    # Scoring fields
    icp_score = Column(Float, default=0.0)
    intent_velocity_score = Column(Float, default=0.0)
    calculated_tier = Column(String(100), default="Unscored")
    headcount_bracket = Column(String(50))

    # NABL / Certification
    has_nabl = Column(Boolean, default=False)
    nabl_first_seen = Column(DateTime)
    predicted_renewal_date = Column(DateTime)

    # Enhanced fields (Modules 8-17)
    buying_window = Column(Text, default="unknown")
    urgency_reason = Column(Text)
    competitor_pain_detected = Column(Boolean, default=False)
    review_sentiment_score = Column(Float)
    lookalike_source_id = Column(Integer)
    user_rating = Column(Integer)
    negative_icp_flags = Column(ARRAY(Text), default=[])
    export_active = Column(Boolean, default=False)

    # Google Maps
    google_place_id = Column(String(300))

    # Timestamps
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    persons = relationship("Person", back_populates="company", cascade="all, delete-orphan")
    website_intel = relationship("CompanyWebsiteIntel", back_populates="company", uselist=False, cascade="all, delete-orphan")
    intent_signals = relationship("CompanyIntentSignal", back_populates="company", cascade="all, delete-orphan")
    outreach_drafts = relationship("OutreachDraft", back_populates="company", cascade="all, delete-orphan")
    pipeline_stages = relationship("PipelineStage", back_populates="company", cascade="all, delete-orphan")
    activities = relationship("Activity", back_populates="company", cascade="all, delete-orphan")
    lead_ratings = relationship("LeadRating", back_populates="company", cascade="all, delete-orphan")
