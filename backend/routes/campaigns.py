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
        now = datetime.now(timezone.utc)
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


# ============================================================
# STEP 2 OUTBOUND & IMAP ENDPOINTS
# ============================================================

class DispatchBatchRequest(BaseModel):
    max_count: int = Field(default=50, ge=1, le=500)


class TestSendRequest(BaseModel):
    recipient_email: Optional[str] = None
    step_number: int = Field(default=1, ge=1)
    subject_override: Optional[str] = None
    body_override: Optional[str] = None


class SimulateReplyRequest(BaseModel):
    from_email: str
    subject: str
    body: str
    in_reply_to: Optional[str] = None
    recipient_id: Optional[int] = None


@router.post("/{campaign_id}/dispatch-batch")
def dispatch_batch_endpoint(campaign_id: int, payload: DispatchBatchRequest):
    """Dispatch approved recipients for a campaign via SMTP delivery engine."""
    from services.smtp_service import dispatch_campaign_batch
    session = db()
    try:
        res = dispatch_campaign_batch(session, campaign_id, max_count=payload.max_count)
        if "error" in res:
            raise HTTPException(400, res["error"])
        return res
    finally:
        session.close()


@router.post("/{campaign_id}/test-send")
def test_send_endpoint(campaign_id: int, payload: TestSendRequest):
    """Send a single test email for a campaign step to test mailbox or target."""
    from services.smtp_service import send_email_message, render_template
    session = db()
    try:
        campaign = session.query(Campaign).filter(Campaign.id == campaign_id).first()
        if not campaign:
            raise HTTPException(404, "Campaign not found")
        step = session.query(CampaignStep).filter(
            CampaignStep.campaign_id == campaign_id,
            CampaignStep.step_number == payload.step_number,
        ).first()

        subject = payload.subject_override or (step.subject if step else f"Test Send: {campaign.name}")
        body = payload.body_override or (step.body_template if step else "This is a test outbound email from Oorja Sales OS.")

        context = {
            "company_name": "Acme Industrial Test Plant",
            "contact_name": "Test Contact",
            "first_name": "Test",
            "city": "Dahej",
            "state": "Gujarat",
            "industry": "Manufacturing",
            "division": "Testing Division",
        }
        subject = render_template(subject, context)
        body = render_template(body, context)

        target_email = payload.recipient_email or "test@oorja.local"
        res = send_email_message(
            to_email=target_email,
            subject=subject,
            body=body,
            campaign_id=campaign_id,
        )
        return res
    finally:
        session.close()


@router.post("/imap/poll")
def poll_imap_endpoint():
    """Poll IMAP inbox for incoming prospect replies and delivery bounces."""
    from services.imap_service import poll_imap_inbox
    session = db()
    try:
        return poll_imap_inbox(session)
    finally:
        session.close()


@router.post("/imap/simulate-reply")
def simulate_reply_endpoint(payload: SimulateReplyRequest):
    """Simulate an incoming email reply or bounce to trigger CRM activities and classifications."""
    from services.imap_service import process_incoming_email
    session = db()
    try:
        headers_dict = {}
        if payload.in_reply_to:
            headers_dict["in-reply-to"] = payload.in_reply_to
        if payload.recipient_id:
            headers_dict["x-oorja-recipient-id"] = str(payload.recipient_id)

        parsed_email = {
            "from": payload.from_email,
            "subject": payload.subject,
            "body": payload.body,
            "headers": headers_dict,
        }
        return process_incoming_email(session, parsed_email)
    finally:
        session.close()


@router.get("/{campaign_id}/analytics")
def get_campaign_analytics(campaign_id: int):
    """Get delivery, reply, and bounce analytics for a campaign."""
    session = db()
    try:
        campaign = session.query(Campaign).filter(Campaign.id == campaign_id).first()
        if not campaign:
            raise HTTPException(404, "Campaign not found")

        total_recipients = session.query(CampaignRecipient).filter(CampaignRecipient.campaign_id == campaign_id).count()
        sent_count = session.query(CampaignRecipient).filter(
            CampaignRecipient.campaign_id == campaign_id,
            CampaignRecipient.email_status == "Sent",
        ).count()
        replied_count = session.query(CampaignRecipient).filter(
            CampaignRecipient.campaign_id == campaign_id,
            CampaignRecipient.status == "Replied",
        ).count()
        bounced_count = session.query(CampaignRecipient).filter(
            CampaignRecipient.campaign_id == campaign_id,
            CampaignRecipient.status == "Bounced",
        ).count()

        events_count = session.query(CampaignEvent).filter(CampaignEvent.campaign_id == campaign_id).count()

        return {
            "campaign_id": campaign.id,
            "name": campaign.name,
            "status": campaign.status,
            "approved": campaign.approved,
            "daily_limit": campaign.daily_limit,
            "metrics": {
                "total_recipients": total_recipients,
                "sent": sent_count,
                "replied": replied_count,
                "bounced": bounced_count,
                "total_events": events_count,
                "reply_rate": round((replied_count / sent_count * 100), 1) if sent_count > 0 else 0.0,
                "bounce_rate": round((bounced_count / sent_count * 100), 1) if sent_count > 0 else 0.0,
            },
        }
    finally:
        session.close()
