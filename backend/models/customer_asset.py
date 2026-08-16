"""CustomerAsset model representing physical customer-owned instruments at a plant/facility."""
from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship

from database import Base


class CustomerAsset(Base):
    __tablename__ = "customer_assets"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_id = Column(Integer, ForeignKey("facilities.id", ondelete="CASCADE"), nullable=True, index=True)
    instrument_id = Column(Integer, ForeignKey("instruments.id", ondelete="SET NULL"), nullable=True, index=True)

    asset_tag = Column(String(200), nullable=True, index=True)
    serial_number = Column(String(200), nullable=True, index=True)
    instrument_name = Column(String(500), nullable=False, index=True)
    make = Column(String(300), nullable=True)
    model = Column(String(300), nullable=True)
    parameter = Column(String(300), nullable=True, index=True)
    range_value = Column(String(300), nullable=True)
    location_in_plant = Column(String(300), nullable=True)

    last_calibrated_date = Column(Date, nullable=True)
    calibration_due_date = Column(Date, nullable=True, index=True)
    calibration_interval_months = Column(Integer, default=12, nullable=False)
    certificate_number = Column(String(200), nullable=True)
    status = Column(String(50), default="Active", nullable=False, index=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    company = relationship("Company", back_populates="customer_assets")
    facility = relationship("Facility", back_populates="assets")
    instrument = relationship("Instrument")
