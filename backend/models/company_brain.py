"""SQLAlchemy models for Salesoorja Company Brain, Timeline, Stakeholder Graph, and Regulatory Intelligence."""
from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Text, JSON, func
from sqlalchemy.orm import relationship

from database import Base


class CompanyIntelligenceFact(Base):
    __tablename__ = "company_intelligence_facts"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    category = Column(String(50), nullable=False, index=True)  # equipment, process, certification, expansion, vendor, financial
    fact_key = Column(String(100), nullable=False, index=True)  # e.g. cnc_machines, cmm_mitutoyo, iatf_16949
    fact_value = Column(JSON, nullable=True)  # Structured fact attributes
    source = Column(String(100), nullable=False)  # website_scrape, apollo, crm_activity, quotation, news, regulatory
    source_url = Column(String(500), nullable=True)
    confidence = Column(Float, default=0.8, nullable=False)  # 0.0 to 1.0
    evidence_text = Column(Text, nullable=True)  # Verbatim quote or snippet
    verified_by_human = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    company = relationship("Company", backref="intelligence_facts")


class CompanyTimelineEvent(Base):
    __tablename__ = "company_timeline_events"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(String(50), nullable=False, index=True)  # plant_expansion, qa_hired, capex, quote_submitted, deal_lost, deal_won
    event_date = Column(Date, nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    impact_level = Column(String(20), default="medium", nullable=False)  # low, medium, high, critical
    buying_window_impact = Column(String(50), nullable=True)  # immediate, 30_days, 60_days, renewal_cycle
    source = Column(String(100), nullable=False)
    source_ref = Column(String(255), nullable=True)
    raw_metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    company = relationship("Company", backref="timeline_events")


class StakeholderIntelligence(Base):
    __tablename__ = "stakeholder_intelligence"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    person_id = Column(Integer, ForeignKey("persons.id", ondelete="SET NULL"), nullable=True, index=True)
    stakeholder_role = Column(String(50), nullable=False, index=True)  # technical_buyer, economic_buyer, influencer, blocker, user, plant_head
    department = Column(String(100), nullable=False, index=True)  # Quality / Metrology, Purchase, Maintenance, Management
    incentive_focus = Column(String(100), nullable=True)  # traceability_audit, commercial_pricing_sla, downtime_reduction, cost_of_uncertainty
    influence_weight = Column(Float, default=5.0, nullable=False)  # 1.0 to 10.0
    engagement_status = Column(String(50), default="unreached", nullable=False)  # unreached, contacted, responsive, advocate, resistant
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    company = relationship("Company", backref="stakeholder_profiles")
    person = relationship("Person", backref="stakeholder_profile")


class RegulatoryIntelligence(Base):
    __tablename__ = "regulatory_intelligence"

    id = Column(Integer, primary_key=True, index=True)
    authority = Column(String(100), nullable=False, index=True)  # Legal Metrology, BIS, NABL, ISO, CPCB, IATF
    regulation_code = Column(String(100), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    summary = Column(Text, nullable=False)
    affected_industries = Column(JSON, nullable=True)  # ["Automotive", "Pharmaceutical", "Heavy Engineering"]
    affected_parameters = Column(JSON, nullable=True)  # ["Dimensional", "Thermal", "Pressure", "Electrical"]
    affected_equipment = Column(JSON, nullable=True)  # ["CMM", "Pressure Gauges", "Temperature Transmitters"]
    compliance_deadline = Column(Date, nullable=True, index=True)
    # The Mandatory 5-Question Commercial Impact Breakdown:
    commercial_impact_analysis = Column(JSON, nullable=False)
    # {
    #   "what_changed": str,
    #   "affected_processes": list[str],
    #   "calibration_requirement": str,
    #   "buying_window": str,
    #   "sales_opportunity": str,
    #   "premium_justification": str
    # }
    source_url = Column(String(500), nullable=True)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
