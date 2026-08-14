"""Controlled campaign management APIs.

Campaigns can be prepared and reviewed in the UI. No outbound message is
sent by these endpoints; approval is required before a future sender worker
may execute a campaign.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import SessionLocal
from models.campaign import Campaign, CampaignStep, CampaignRecipient, CampaignEvent
from models.company import Company
from models.person import Person

router = APIRouter(prefix="/api/campaigns", tags=["Campaigns"])


class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    description: Optional[str] = None
    channel: str = "email"
    daily_limit: int = Field(default=50, ge=1, le=1000)
    segment_filters: Optional[dict] = None


class StepCreate(BaseModel):
    step_number: int = Field(ge=1)
    channel: str = "email"
    delay_days: int = Field(default=0, ge=0, le=365)
    subject: Optional[str] = None
    body_template: Optional[str] = None
    enabled: bool = True


class RecipientCreate(BaseModel):
    company_id: int
    person_id: Optional[int] = None


class ApprovalRequest(BaseModel):
    approved: bool


class EventCreate(BaseModel):
    recipient_id: int
    event_type: str
    channel: Optional[str] = None
    provider_message_id: Optional[str] = None
    payload: Optional[dict] = None


def db():
    return SessionLocal()


def serialize_campaign(campaign: Campaign) -> dict:
    return {
        "id": campaign.id,
        "name": campaign.name,
        "description": campaign.description,
        "channel": campaign.channel,
        "status": campaign.status,
        "approved": campaign.approved,
        "approved_at": campaign.approved_at,
        "daily_limit": campaign.daily_limit,
        "segment_filters": campaign.segment_filters,
        "step_count": len(campaign.steps),
        "recipient_count": len(campaign.recipients),
        "created_at": campaign.created_at,
        "updated_at": campaign.updated_at,
    }


@router.get("")
def list_campaigns(status: Optional[str] = None):
    session = db()
    try:
        query = session.query(Campaign)
        if status:
            query = query.filter(Campaign.status == status)
        items = query.order_by(Campaign.updated_at.desc(), Campaign.id.desc()).all()
        return {"results": [serialize_campaign(x) for x in items], "total": len(items)}
    finally:
        session.close()


@router.post("")
def create_campaign(payload: CampaignCreate):
    session = db()
    try:
        campaign = Campaign(**payload.model_dump())
        session.add(campaign)
        session.commit()
        session.refresh(campaign)
        return serialize_campaign(campaign)
    finally:
        session.close()


@router.post("/{campaign_id}/steps")
def add_step(campaign_id: int, payload: StepCreate):
    session = db()
    try:
        campaign = session.query(Campaign).filter(Campaign.id == campaign_id).first()
        if not campaign:
            raise HTTPException(404, "Campaign not found")
        step = CampaignStep(campaign_id=campaign_id, **payload.model_dump())
        session.add(step)
        session.commit()
        session.refresh(step)
        return {"id": step.id, "campaign_id": campaign_id, "step_number": step.step_number}
    finally:
        session.close()


@router.get("/{campaign_id}/steps")
def list_steps(campaign_id: int):
    session = db()
    try:
        items = session.query(CampaignStep).filter(CampaignStep.campaign_id == campaign_id).order_by(CampaignStep.step_number).all()
        return {"results": [{
            "id": x.id, "step_number": x.step_number, "channel": x.channel,
            "delay_days": x.delay_days, "subject": x.subject,
            "body_template": x.body_template, "enabled": x.enabled,
        } for x in items], "total": len(items)}
    finally:
        session.close()


@router.post("/{campaign_id}/recipients")
def add_recipient(campaign_id: int, payload: RecipientCreate):
    session = db()
    try:
        if not session.query(Campaign.id).filter(Campaign.id == campaign_id).first():
            raise HTTPException(404, "Campaign not found")
        if not session.query(Company.id).filter(Company.id == payload.company_id).first():
            raise HTTPException(404, "Company not found")
        if payload.person_id and not session.query(Person.id).filter(Person.id == payload.person_id).first():
            raise HTTPException(404, "Person not found")
        existing = session.query(CampaignRecipient).filter(
            CampaignRecipient.campaign_id == campaign_id,
            CampaignRecipient.company_id == payload.company_id,
            CampaignRecipient.person_id == payload.person_id,
        ).first()
        if existing:
            return {"id": existing.id, "status": "already_queued"}
        item = CampaignRecipient(campaign_id=campaign_id, **payload.model_dump())
        session.add(item)
        session.commit()
        session.refresh(item)
        return {"id": item.id, "status": item.status}
    finally:
        session.close()


@router.get("/{campaign_id}/recipients")
def list_recipients(campaign_id: int, status: Optional[str] = None):
    session = db()
    try:
        query = session.query(CampaignRecipient).filter(CampaignRecipient.campaign_id == campaign_id)
        if status:
            query = query.filter(CampaignRecipient.status == status)
        items = query.order_by(CampaignRecipient.id.desc()).all()
        return {"results": [{
            "id": x.id, "company_id": x.company_id, "person_id": x.person_id,
            "current_step": x.current_step, "status": x.status,
            "email_status": x.email_status, "last_sent_at": x.last_sent_at,
            "next_send_at": x.next_send_at, "replied_at": x.replied_at,
            "bounced_at": x.bounced_at,
        } for x in items], "total": len(items)}
    finally:
        session.close()


@router.post("/{campaign_id}/approval")
def approve_campaign(campaign_id: int, payload: ApprovalRequest):
    session = db()
    try:
        campaign = session.query(Campaign).filter(Campaign.id == campaign_id).first()
        if not campaign:
            raise HTTPException(404, "Campaign not found")
        if payload.approved:
            if not campaign.steps:
                raise HTTPException(400, "Add at least one campaign step before approval")
            if not campaign.recipients:
                raise HTTPException(400, "Add at least one recipient before approval")
            campaign.approved = True
            campaign.approved_at = datetime.utcnow()
            campaign.status = "Approved"
        else:
            campaign.approved = False
            campaign.approved_at = None
            campaign.status = "Draft"
        session.commit()
        return {"id": campaign.id, "status": campaign.status, "approved": campaign.approved, "approved_at": campaign.approved_at}
    finally:
        session.close()


@router.post("/{campaign_id}/events")
def record_event(campaign_id: int, payload: EventCreate):
    session = db()
    try:
        recipient = session.query(CampaignRecipient).filter(
            CampaignRecipient.id == payload.recipient_id,
            CampaignRecipient.campaign_id == campaign_id,
        ).first()
        if not recipient:
            raise HTTPException(404, "Campaign recipient not found")
        event = CampaignEvent(campaign_id=campaign_id, **payload.model_dump())
        session.add(event)
        now = datetime.utcnow()
        event_type = payload.event_type.lower()
        if event_type == "sent":
            recipient.last_sent_at = now
            recipient.email_status = "Sent"
        elif event_type in {"reply", "replied"}:
            recipient.replied_at = now
            recipient.status = "Replied"
            recipient.email_status = "Replied"
        elif event_type in {"bounce", "bounced"}:
            recipient.bounced_at = now
            recipient.status = "Bounced"
            recipient.email_status = "Bounced"
        elif event_type == "unsubscribe":
            recipient.status = "Unsubscribed"
        session.commit()
        return {"event_id": event.id, "recipient_status": recipient.status}
    finally:
        session.close()
