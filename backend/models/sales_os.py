"""Core Oorja Sales OS domain models.

These models extend the existing Salesoorja CRM without replacing the
legacy company/contact/pipeline models. They provide the foundation for
opportunity management, quotation intelligence, instrument normalization,
and auditable AI learning.
"""
from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from database import Base


class Opportunity(Base):
    __tablename__ = "opportunities"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    person_id = Column(Integer, ForeignKey("persons.id", ondelete="SET NULL"), nullable=True, index=True)
    name = Column(String(500), nullable=False)
    stage = Column(String(100), default="New", nullable=False, index=True)
    probability = Column(Numeric(5, 2), default=0)
    estimated_value = Column(Numeric(14, 2), default=0)
    expected_close_date = Column(Date)
    source = Column(String(100))
    loss_reason = Column(Text)
    notes = Column(Text)
    ai_summary = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class SalesTask(Base):
    __tablename__ = "sales_tasks"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True)
    opportunity_id = Column(Integer, ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=True, index=True)
    person_id = Column(Integer, ForeignKey("persons.id", ondelete="SET NULL"), nullable=True, index=True)
    title = Column(String(500), nullable=False)
    task_type = Column(String(100), default="Follow-up")
    priority = Column(String(30), default="Medium", index=True)
    status = Column(String(30), default="Open", index=True)
    due_at = Column(DateTime, index=True)
    completed_at = Column(DateTime)
    source = Column(String(100), default="manual")
    ai_reason = Column(Text)
    notes = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class SalesNote(Base):
    __tablename__ = "sales_notes"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    person_id = Column(Integer, ForeignKey("persons.id", ondelete="SET NULL"), nullable=True)
    opportunity_id = Column(Integer, ForeignKey("opportunities.id", ondelete="SET NULL"), nullable=True)
    note_type = Column(String(100), default="General")
    body = Column(Text, nullable=False)
    source = Column(String(100), default="user")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class Quotation(Base):
    __tablename__ = "quotations"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True)
    facility_id = Column(Integer, ForeignKey("facilities.id", ondelete="SET NULL"), nullable=True, index=True)
    opportunity_id = Column(Integer, ForeignKey("opportunities.id", ondelete="SET NULL"), nullable=True, index=True)
    parent_quotation_id = Column(Integer, ForeignKey("quotations.id", ondelete="SET NULL"), nullable=True, index=True)
    version_number = Column(Integer, default=1, nullable=False, index=True)
    is_latest = Column(Boolean, default=True, nullable=False, index=True)
    revision_notes = Column(Text, nullable=True)

    quotation_number = Column(String(100), unique=True, index=True)
    quotation_date = Column(Date, nullable=False)
    valid_until = Column(Date)
    customer_name = Column(String(500), nullable=False)
    location = Column(String(300))
    calibration_type = Column(String(100))
    subtotal = Column(Numeric(14, 2), default=0)
    discount = Column(Numeric(14, 2), default=0)
    tax = Column(Numeric(14, 2), default=0)
    total = Column(Numeric(14, 2), default=0)
    status = Column(String(50), default="Draft", index=True)
    source_file = Column(String(1000))
    ai_recommendation = Column(JSONB)
    human_approved = Column(Integer, default=0)
    approved_at = Column(DateTime)
    notes = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    items = relationship("QuotationItem", back_populates="quotation", cascade="all, delete-orphan")
    facility = relationship("Facility")
    parent = relationship("Quotation", remote_side=[id], backref="revisions")


class QuotationItem(Base):
    __tablename__ = "quotation_items"

    id = Column(Integer, primary_key=True, index=True)
    quotation_id = Column(Integer, ForeignKey("quotations.id", ondelete="CASCADE"), nullable=False, index=True)
    customer_asset_id = Column(Integer, ForeignKey("customer_assets.id", ondelete="SET NULL"), nullable=True, index=True)
    instrument_id = Column(Integer, ForeignKey("instruments.id", ondelete="SET NULL"), nullable=True, index=True)
    instrument_name = Column(String(500), nullable=False)
    normalized_name = Column(String(500), index=True)
    make = Column(String(300))
    model = Column(String(300))
    range_value = Column(String(300))
    parameter = Column(String(300))
    quantity = Column(Numeric(12, 3), default=1)
    onsite = Column(Integer, default=0)
    unit_price = Column(Numeric(14, 2), default=0)
    total_price = Column(Numeric(14, 2), default=0)
    nabl_applicable = Column(Integer)
    nabl_validated = Column(Integer, default=0)
    nabl_fit_status = Column(String(50), nullable=True)
    price_source = Column(String(100))
    ai_confidence = Column(Numeric(5, 2))
    created_at = Column(DateTime, server_default=func.now())

    quotation = relationship("Quotation", back_populates="items")
    customer_asset = relationship("CustomerAsset")


class Instrument(Base):
    __tablename__ = "instruments"

    id = Column(Integer, primary_key=True, index=True)
    family = Column(String(300), nullable=False, index=True)
    parameter = Column(String(300), index=True)
    make = Column(String(300))
    model = Column(String(300))
    range_value = Column(String(300))
    unit = Column(String(100))
    calibration_requirement = Column(Text)
    nabl_applicable = Column(Integer)
    metadata_json = Column(JSONB)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class InstrumentAlias(Base):
    __tablename__ = "instrument_aliases"

    id = Column(Integer, primary_key=True, index=True)
    instrument_id = Column(Integer, ForeignKey("instruments.id", ondelete="CASCADE"), nullable=False, index=True)
    alias = Column(String(500), nullable=False, index=True)
    source = Column(String(100), default="user")
    confidence = Column(Numeric(5, 2), default=100)
    created_at = Column(DateTime, server_default=func.now())


class PriceHistory(Base):
    __tablename__ = "price_history"

    id = Column(Integer, primary_key=True, index=True)
    instrument_id = Column(Integer, ForeignKey("instruments.id", ondelete="SET NULL"), nullable=True, index=True)
    customer_name = Column(String(500), index=True)
    quotation_id = Column(Integer, ForeignKey("quotations.id", ondelete="SET NULL"), nullable=True, index=True)
    calibration_type = Column(String(100))
    location = Column(String(300))
    unit_price = Column(Numeric(14, 2), nullable=False)
    quotation_date = Column(Date)
    outcome = Column(String(50))
    context = Column(JSONB)
    created_at = Column(DateTime, server_default=func.now())


class AIFeedback(Base):
    __tablename__ = "ai_feedback"

    id = Column(Integer, primary_key=True, index=True)
    entity_type = Column(String(100), nullable=False, index=True)
    entity_id = Column(Integer, nullable=True, index=True)
    action_type = Column(String(100), nullable=False)
    ai_value = Column(JSONB)
    human_value = Column(JSONB)
    reason = Column(Text)
    outcome = Column(String(100))
    confidence = Column(Numeric(5, 2))
    created_at = Column(DateTime, server_default=func.now())


class LearningRule(Base):
    __tablename__ = "learning_rules"

    id = Column(Integer, primary_key=True, index=True)
    rule_type = Column(String(100), nullable=False, index=True)
    rule_key = Column(String(300), nullable=False, index=True)
    pattern = Column(JSONB, nullable=False)
    evidence_count = Column(Integer, default=0)
    confidence = Column(Numeric(5, 2), default=0)
    status = Column(String(50), default="Candidate", index=True)
    approved_by = Column(String(200))
    approved_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
