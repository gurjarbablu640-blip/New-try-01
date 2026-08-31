"""Conversation memory models for Ask Oorja multi-step orchestration."""
import uuid
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from database import Base


class ConversationSession(Base):
    __tablename__ = "conversation_sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    started_at = Column(DateTime, server_default=func.now(), nullable=False)
    last_activity_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    turn_count = Column(Integer, default=0, nullable=False)
    summary = Column(Text, nullable=True)
    context_snapshot = Column(JSONB, nullable=True)
    status = Column(String(20), default="active", nullable=False, index=True)

    turns = relationship("ConversationTurn", back_populates="session", cascade="all, delete-orphan", order_by="ConversationTurn.turn_number")


class ConversationTurn(Base):
    __tablename__ = "conversation_turns"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(36), ForeignKey("conversation_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    turn_number = Column(Integer, nullable=False)
    role = Column(String(20), nullable=False)  # "user", "orchestrator", "sub_agent"
    agent_name = Column(String(50), nullable=True)
    content = Column(Text, nullable=False)
    tool_calls = Column(JSONB, nullable=True)
    reasoning_trace = Column(JSONB, nullable=True)
    iteration_count = Column(Integer, default=1, nullable=False)
    tokens_used = Column(JSONB, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    session = relationship("ConversationSession", back_populates="turns")
