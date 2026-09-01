"""Company Website Intelligence model."""
from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Text, JSON, Float, Boolean, func
)
from sqlalchemy.orm import relationship
from database import Base


class CompanyWebsiteIntel(Base):
    __tablename__ = "company_website_intel"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), unique=True, nullable=False)

    # Instruments & Equipment
    instruments_found = Column(JSON, default=[])
    oem_brands = Column(JSON, default=[])

    # Certifications
    iso_standards = Column(JSON, default=[])
    certifications_expiry_hints = Column(Text)

    # Website analysis
    expansion_signals = Column(Text)
    services_offered = Column(JSON, default=[])
    industries_served = Column(JSON, default=[])

    # Reviews & Competitor Intel (Module 8f)
    competitor_mentions = Column(JSON, default=[])
    review_pain_phrases = Column(JSON, default=[])

    # Metadata
    last_crawled_at = Column(DateTime)
    crawl_status = Column(String(50), default="pending")

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    company = relationship("Company", back_populates="website_intel")
