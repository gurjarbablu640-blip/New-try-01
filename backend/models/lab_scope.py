"""NABL Lab Scope Intelligence models for Oorja Sales OS.

Stores accredited laboratory metadata and granular parameter-level scope capabilities
extracted from official NABL accreditation documents across Pan-India.
"""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String, Text, JSON, func
from sqlalchemy.orm import relationship

from database import Base


class NABLLabScope(Base):
    __tablename__ = "nabl_lab_scopes"

    id = Column(Integer, primary_key=True, index=True)
    lab_name = Column(String(500), nullable=False, index=True)
    certificate_no = Column(String(100), unique=True, index=True)
    accreditation_standard = Column(String(100), default="ISO/IEC 17025:2017")
    discipline_summary = Column(String(500))  # Mechanical, Thermal, Electro-technical, etc.
    validity_date = Column(String(50))
    state = Column(String(100), index=True)
    city = Column(String(100), index=True)
    address = Column(Text)
    source_file = Column(String(500))
    source_reference = Column(String(200))
    data_provenance = Column(String(50), default="PILOT_TEST_DATA", nullable=False, index=True)  # PILOT_TEST_DATA, USER_UPLOADED_REAL
    active = Column(Boolean, default=True, nullable=False, index=True)
    metadata_json = Column(JSON)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    parameters = relationship("NABLScopeParameter", back_populates="lab_scope", cascade="all, delete-orphan")


class NABLScopeParameter(Base):
    __tablename__ = "nabl_scope_parameters"

    id = Column(Integer, primary_key=True, index=True)
    lab_scope_id = Column(Integer, ForeignKey("nabl_lab_scopes.id", ondelete="CASCADE"), nullable=False, index=True)
    discipline = Column(String(100), nullable=False, index=True)  # Mechanical, Thermal, Electro-Technical, Fluid Flow, Optical, etc.
    parameter_name = Column(String(300), nullable=False, index=True)
    instrument_or_gage = Column(String(300))
    range_min = Column(String(100))
    range_max = Column(String(100))
    range_description = Column(String(500))
    unit = Column(String(50))
    cmc_uncertainty = Column(String(200))  # Calibration & Measurement Capability (± uncertainty)
    is_onsite = Column(Boolean, default=False)
    service_capability = Column(String(100), default="LAB_AND_ONSITE")  # LAB_ONLY, ONSITE_ONLY, LAB_AND_ONSITE
    source_page = Column(Integer)
    created_at = Column(DateTime, server_default=func.now())

    lab_scope = relationship("NABLLabScope", back_populates="parameters")
