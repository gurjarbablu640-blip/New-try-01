"""Discovery query audit log and memory model for Salesoorja Discovery Intelligence."""
from sqlalchemy import Column, DateTime, Float, Index, Integer, JSON, String, Text, func
from database import Base


class DiscoveryQueryLog(Base):
    __tablename__ = "discovery_query_logs"

    id = Column(Integer, primary_key=True, index=True)
    query = Column(Text, nullable=False)
    normalized_query = Column(String(500), nullable=False, index=True)
    page = Column(Integer, default=1, nullable=False)
    sector = Column(String(100), index=True, nullable=True)
    trigger = Column(String(100), index=True, nullable=True)
    geography = Column(String(100), index=True, nullable=True)
    execution_state = Column(String(50), default="SUCCESS_PRODUCTIVE", index=True, nullable=False)
    executed_at = Column(DateTime, server_default=func.now(), index=True, nullable=False)
    results_count = Column(Integer, default=0, nullable=False)
    unique_results = Column(Integer, default=0, nullable=False)
    new_companies = Column(Integer, default=0, nullable=False)
    strong_opportunities = Column(Integer, default=0, nullable=False)
    incomplete_opportunities = Column(Integer, default=0, nullable=False)
    weak_opportunities = Column(Integer, default=0, nullable=False)
    yield_score = Column(Float, default=0.0, nullable=False)
    exhaustion_score = Column(Float, default=0.0, nullable=False)
    metadata_json = Column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_discovery_query_page_time", "normalized_query", "page", "executed_at"),
    )
