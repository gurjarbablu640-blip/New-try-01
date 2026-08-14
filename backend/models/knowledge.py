from sqlalchemy import Column, Date, DateTime, Integer, String, Text, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from database import Base

class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), nullable=False, index=True)
    document_type = Column(String(100), default="internal", index=True)
    company = Column(String(500), index=True)
    source_uri = Column(String(1000))
    source_name = Column(String(500))
    document_date = Column(Date)
    version = Column(String(100))
    content_hash = Column(String(128), unique=True, index=True)
    status = Column(String(50), default="active", index=True)
    metadata_json = Column(JSONB)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    chunks = relationship("KnowledgeChunk", back_populates="document", cascade="all, delete-orphan")

class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    page_number = Column(Integer)
    section = Column(String(500))
    content = Column(Text, nullable=False)
    fact_classification = Column(String(50), default="VERIFIED_FACT", index=True)
    source_reference = Column(String(1000))
    source_date = Column(Date)
    confidence = Column(Integer, default=100)
    embedding_model = Column(String(200))
    metadata_json = Column(JSONB)
    created_at = Column(DateTime, server_default=func.now())
    document = relationship("KnowledgeDocument", back_populates="chunks")
