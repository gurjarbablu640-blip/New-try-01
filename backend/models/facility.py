"""Facility / Plant model representing a customer physical site."""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship

from database import Base


class Facility(Base):
    __tablename__ = "facilities"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(300), nullable=False, index=True)
    plant_code = Column(String(100), nullable=True, index=True)
    industrial_estate = Column(String(300), nullable=True)
    city = Column(String(200), nullable=True)
    state = Column(String(200), nullable=True)
    address = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    company = relationship("Company", back_populates="facilities")
    assets = relationship("CustomerAsset", back_populates="facility", cascade="all, delete-orphan")
