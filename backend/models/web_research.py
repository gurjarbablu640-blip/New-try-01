"""Web research evidence captured for Sales OS company intelligence."""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, JSON, func
from database import Base


class WebResearchItem(Base):
    __tablename__ = "web_research"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True)
    query = Column(Text, nullable=False)
    title = Column(String(1000))
    url = Column(Text, nullable=False)
    source_domain = Column(String(300), index=True)
    published_date = Column(DateTime)
    retrieved_at = Column(DateTime, server_default=func.now(), index=True)
    snippet = Column(Text)
    content = Column(Text)
    signal_type = Column(String(100), index=True)
    confidence = Column(Integer, default=50)
    evidence_type = Column(String(50), default="WEB_EVIDENCE")
    metadata_json = Column(JSON)
