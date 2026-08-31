"""SQLAlchemy model for Call Intelligence, Voice Coaching, and Recorded Conversations."""
from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from database import Base


class CallRecord(Base):
    __tablename__ = "call_records"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    person_id = Column(Integer, ForeignKey("persons.id", ondelete="SET NULL"), nullable=True, index=True)
    salesperson_name = Column(String(100), default="Sales Rep", nullable=False)
    call_date = Column(DateTime, server_default=func.now(), nullable=False, index=True)
    duration_seconds = Column(Integer, default=0, nullable=False)
    call_channel = Column(String(50), default="Phone", nullable=False)  # Phone, WhatsApp, Zoom, Teams
    recording_file_url = Column(String(500), nullable=True)
    transcript_text = Column(Text, nullable=True)
    call_objective = Column(String(100), nullable=True)  # discovery, qualification, proposal_review, objection_handling
    call_score = Column(Integer, default=70, nullable=False)  # 0 to 100
    score_breakdown = Column(JSONB, nullable=True)
    # { "opening": "8/10", "discovery": "9/10", "objection_handling": "8/10", "next_step_clarity": "9/10" }
    buying_signals_detected = Column(JSONB, nullable=True)  # list of signals
    objections_detected = Column(JSONB, nullable=True)  # list of objections
    extracted_facts = Column(JSONB, nullable=True)
    # { "instrument_count": 1200, "current_vendor": "XYZ Lab", "calibration_frequency": "Annual", "next_cycle": "October" }
    coaching_advice = Column(JSONB, nullable=True)  # "What should I have said?" advice & golden moments
    outcome_status = Column(String(50), default="completed", nullable=False)  # qualified, proposal_requested, callback_scheduled, rejected
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    company = relationship("Company", backref="call_records")
    person = relationship("Person", backref="call_records")
