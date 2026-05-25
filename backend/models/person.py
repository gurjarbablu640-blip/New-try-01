"""Person / Contact model."""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from backend.database import Base


class Person(Base):
    __tablename__ = "persons"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    full_name = Column(String(300))
    designation = Column(String(300))
    email = Column(String(300))
    phone = Column(String(100))
    linkedin_url = Column(String(500))
    seniority_level = Column(String(100))
    department = Column(String(200))
    is_decision_maker = Column(Integer, default=0)  # 0=unknown, 1=yes, 2=no

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    company = relationship("Company", back_populates="persons")
    pipeline_stages = relationship("PipelineStage", back_populates="person")
    activities = relationship("Activity", back_populates="person")
