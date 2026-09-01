"""Campaign engine models for controlled outbound sequences."""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, JSON, func
from sqlalchemy.orm import relationship
from database import Base


class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(300), nullable=False, index=True)
    description = Column(Text)
    channel = Column(String(50), default="email", nullable=False)
    status = Column(String(50), default="Draft", nullable=False, index=True)
    approved = Column(Boolean, default=False, nullable=False)
    approved_at = Column(DateTime)
    segment_filters = Column(JSON)
    daily_limit = Column(Integer, default=50)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    steps = relationship("CampaignStep", back_populates="campaign", cascade="all, delete-orphan")
    recipients = relationship("CampaignRecipient", back_populates="campaign", cascade="all, delete-orphan")


class CampaignStep(Base):
    __tablename__ = "campaign_steps"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True)
    step_number = Column(Integer, nullable=False)
    channel = Column(String(50), default="email", nullable=False)
    delay_days = Column(Integer, default=0)
    subject = Column(String(1000))
    body_template = Column(Text)
    enabled = Column(Boolean, default=True, nullable=False)

    campaign = relationship("Campaign", back_populates="steps")


class CampaignRecipient(Base):
    __tablename__ = "campaign_recipients"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True)
    company_id = Column(Integer, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    person_id = Column(Integer, ForeignKey("persons.id", ondelete="SET NULL"), nullable=True, index=True)
    current_step = Column(Integer, default=0)
    status = Column(String(50), default="Queued", nullable=False, index=True)
    email_status = Column(String(50), default="Pending")
    last_sent_at = Column(DateTime)
    next_send_at = Column(DateTime)
    replied_at = Column(DateTime)
    bounced_at = Column(DateTime)
    metadata_json = Column(JSON)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    campaign = relationship("Campaign", back_populates="recipients")


class CampaignEvent(Base):
    __tablename__ = "campaign_events"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True)
    recipient_id = Column(Integer, ForeignKey("campaign_recipients.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(String(50), nullable=False, index=True)
    channel = Column(String(50))
    provider_message_id = Column(String(500))
    payload = Column(JSON)
    occurred_at = Column(DateTime, server_default=func.now(), index=True)
