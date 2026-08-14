"""Unified Company 360 view across CRM and Sales OS intelligence."""
from fastapi import APIRouter, HTTPException

from database import SessionLocal
from models.company import Company
from models.person import Person
from models.intent_signal import CompanyIntentSignal
from models.sales_os import Opportunity, SalesTask, Quotation
from models.web_research import WebResearchItem
from models.competitor_intel import CompetitorObservation
from models.campaign import CampaignRecipient, CampaignEvent

router = APIRouter(prefix="/api/company-360", tags=["Company 360"])


def _company_summary(company: Company):
    return {
        "id": company.id,
        "name": company.name,
        "city": company.city,
        "state": company.state,
        "country": company.country,
        "industry": company.industry,
        "website": company.website,
        "lead_status": company.lead_status,
        "icp_score": company.icp_score,
        "intent_velocity_score": company.intent_velocity_score,
        "tier": company.calculated_tier,
        "has_nabl": company.has_nabl,
        "buying_window": company.buying_window,
        "urgency_reason": company.urgency_reason,
        "competitor_pain_detected": company.competitor_pain_detected,
        "reply_received": company.reply_received,
        "bounced_email": company.bounced_email,
        "order_received": company.order_received,
        "order_value": float(company.order_value or 0),
    }


@router.get("/{company_id}")
def get_company_360(company_id: int):
    db = SessionLocal()
    try:
        company = db.query(Company).filter(Company.id == company_id).first()
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        people = db.query(Person).filter(Person.company_id == company_id).order_by(Person.id.desc()).limit(50).all()
        signals = db.query(CompanyIntentSignal).filter(CompanyIntentSignal.company_id == company_id).order_by(CompanyIntentSignal.id.desc()).limit(50).all()
        opportunities = db.query(Opportunity).filter(Opportunity.company_id == company_id).order_by(Opportunity.updated_at.desc()).limit(50).all()
        tasks = db.query(SalesTask).filter(SalesTask.company_id == company_id).order_by(SalesTask.due_at.asc().nullslast(), SalesTask.id.desc()).limit(50).all()
        quotations = db.query(Quotation).filter(Quotation.company_id == company_id).order_by(Quotation.quotation_date.desc()).limit(50).all()
        research = db.query(WebResearchItem).filter(WebResearchItem.company_id == company_id).order_by(WebResearchItem.retrieved_at.desc()).limit(50).all()
        competitor_observations = db.query(CompetitorObservation).filter(CompetitorObservation.company_id == company_id).order_by(CompetitorObservation.observed_at.desc()).limit(50).all()
        recipients = db.query(CampaignRecipient).filter(CampaignRecipient.company_id == company_id).order_by(CampaignRecipient.updated_at.desc()).limit(50).all()
        recipient_ids = [r.id for r in recipients]
        campaign_events = []
        if recipient_ids:
            campaign_events = db.query(CampaignEvent).filter(CampaignEvent.recipient_id.in_(recipient_ids)).order_by(CampaignEvent.occurred_at.desc()).limit(100).all()

        return {
            "company": _company_summary(company),
            "contacts": [
                {"id": p.id, "name": p.name, "designation": p.designation, "department": p.department, "email": p.email, "phone": p.phone, "linkedin": p.linkedin}
                for p in people
            ],
            "intent_signals": [
                {"id": s.id, "signal_type": s.signal_type, "signal_strength": s.signal_strength, "source": s.source, "detected_at": s.detected_at, "details": s.details}
                for s in signals
            ],
            "opportunities": [
                {"id": o.id, "name": o.name, "stage": o.stage, "probability": float(o.probability or 0), "estimated_value": float(o.estimated_value or 0), "expected_close_date": o.expected_close_date, "source": o.source, "loss_reason": o.loss_reason}
                for o in opportunities
            ],
            "tasks": [
                {"id": t.id, "title": t.title, "task_type": t.task_type, "priority": t.priority, "status": t.status, "due_at": t.due_at, "source": t.source, "ai_reason": t.ai_reason}
                for t in tasks
            ],
            "quotations": [
                {"id": q.id, "quotation_number": q.quotation_number, "quotation_date": q.quotation_date, "total": float(q.total or 0), "status": q.status, "human_approved": bool(q.human_approved)}
                for q in quotations
            ],
            "web_research": [
                {"id": r.id, "title": r.title, "url": r.url, "source_domain": r.source_domain, "published_date": r.published_date, "retrieved_at": r.retrieved_at, "signal_type": r.signal_type, "snippet": r.snippet, "confidence": r.confidence}
                for r in research
            ],
            "competitor_observations": [
                {"id": o.id, "competitor_id": o.competitor_id, "observation_type": o.observation_type, "title": o.title, "evidence": o.evidence, "source_url": o.source_url, "observed_at": o.observed_at, "confidence": o.confidence, "classification": o.classification}
                for o in competitor_observations
            ],
            "campaign": {
                "recipients": [
                    {"id": r.id, "campaign_id": r.campaign_id, "person_id": r.person_id, "current_step": r.current_step, "status": r.status, "email_status": r.email_status, "last_sent_at": r.last_sent_at, "next_send_at": r.next_send_at, "replied_at": r.replied_at, "bounced_at": r.bounced_at}
                    for r in recipients
                ],
                "events": [
                    {"id": e.id, "campaign_id": e.campaign_id, "recipient_id": e.recipient_id, "event_type": e.event_type, "channel": e.channel, "occurred_at": e.occurred_at}
                    for e in campaign_events
                ],
            },
        }
    finally:
        db.close()
