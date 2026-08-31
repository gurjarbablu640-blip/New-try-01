"""SQLAlchemy domain models for the Salesoorja Reasoning Foundation.

Provides persistent evidential belief states, temporal signal evidence nodes,
causal graphs, contradictions, and epistemic classification (FACT / INFERENCE / HYPOTHESIS).
"""
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from database import Base


class CompanyBeliefState(Base):
    """Persistent evolving belief state for a company account."""
    __tablename__ = "company_belief_states"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    
    # Core probabilistic beliefs
    # Format: { "calibration_need": { "value": 0.85, "confidence": 0.78, "supporting": [...], "contradicting": [...], "last_updated": "..." } }
    beliefs = Column(JSONB, nullable=False, default=dict)
    
    # Active evidential contradictions requiring resolution
    contradictions = Column(JSONB, nullable=False, default=list)
    
    # Inspectable reasoning traces (EVIDENCE -> INTERPRETATION -> CAUSAL PATH -> BELIEF -> DECISION)
    causal_traces = Column(JSONB, nullable=False, default=list)
    
    # Uncertainty-reducing adaptive research tasks
    active_research_tasks = Column(JSONB, nullable=False, default=list)
    
    # Summary confidence
    overall_confidence = Column(Float, default=0.5)
    last_reasoned_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class SignalEvidenceNode(Base):
    """Granular evidence node with temporal decay and epistemic tagging."""
    __tablename__ = "signal_evidence_nodes"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Epistemic type: FACT, INFERENCE, HYPOTHESIS, UNKNOWN
    epistemic_type = Column(String(50), nullable=False, default="INFERENCE", index=True)
    signal_type = Column(String(100), nullable=False, index=True)
    
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    source = Column(String(200), nullable=False)
    source_url = Column(String(500), nullable=True)
    source_reliability = Column(Float, default=0.8)  # 0.0 (unreliable) to 1.0 (authoritative)
    
    # Temporal context
    event_time = Column(DateTime, nullable=True)
    detection_time = Column(DateTime, default=datetime.utcnow)
    activation_window = Column(String(50), default="30_days")
    staleness_threshold_days = Column(Integer, default=90)
    decay_rate = Column(Float, default=0.01)  # Daily decay factor
    current_effective_confidence = Column(Float, default=0.8)
    
    # Causal template linking
    causal_template_key = Column(String(100), nullable=True)
    is_contradicted = Column(Boolean, default=False)
    evidence_metadata = Column(JSONB, nullable=True, default=dict)
    
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
