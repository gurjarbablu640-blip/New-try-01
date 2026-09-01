"""Competitor intelligence models for Oorja Sales OS.

Stores observed competitor relationships, evidence, pricing signals, strengths,
weaknesses and source-traceable observations without overwriting CRM facts.
"""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, JSON, func
from sqlalchemy.orm import relationship
from database import Base


class CompetitorProfile(Base):
    __tablename__ = "competitor_profiles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(500), nullable=False, unique=True, index=True)
    website = Column(String(1000))
    country = Column(String(100))
    service_focus = Column(Text)
    positioning = Column(Text)
    pricing_notes = Column(Text)
    strengths = Column(JSON)
    weaknesses = Column(JSON)
    active = Column(Boolean, default=True, nullable=False, index=True)
    metadata_json = Column(JSON)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    observations = relationship("CompetitorObservation", back_populates="competitor", cascade="all, delete-orphan")


class CompetitorObservation(Base):
    __tablename__ = "competitor_observations"

    id = Column(Integer, primary_key=True, index=True)
    competitor_id = Column(Integer, ForeignKey("competitor_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True)
    observation_type = Column(String(100), nullable=False, index=True)
    title = Column(String(500))
    evidence = Column(Text, nullable=False)
    source_url = Column(Text)
    source_name = Column(String(500))
    observed_at = Column(DateTime, server_default=func.now(), index=True)
    confidence = Column(Integer, default=50)
    classification = Column(String(50), default="WEB_EVIDENCE")
    metadata_json = Column(JSON)

    competitor = relationship("CompetitorProfile", back_populates="observations")
