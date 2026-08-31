"""Company Brain & Timeline Intelligence Service.

Correlates internal CRM interactions, quotations, assets, customer history,
with external intelligence signals, regulatory notices, and stakeholder graphs into
a unified, source-traceable Company Brain.
"""
from datetime import date, datetime, timedelta
import logging
from typing import Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc

from models.company import Company
from models.company_brain import CompanyIntelligenceFact, CompanyTimelineEvent, StakeholderIntelligence, RegulatoryIntelligence
from models.customer_asset import CustomerAsset
from models.person import Person
from models.sales_os import Opportunity, Quotation

logger = logging.getLogger(__name__)


def record_intelligence_fact(
    db: Session,
    company_id: int,
    category: str,
    fact_key: str,
    fact_value: Optional[dict[str, Any]],
    source: str,
    source_url: Optional[str] = None,
    confidence: float = 0.85,
    evidence_text: Optional[str] = None,
    verified_by_human: bool = False,
) -> CompanyIntelligenceFact:
    """Record or update a verifiable intelligence fact with source provenance and confidence."""
    existing = (
        db.query(CompanyIntelligenceFact)
        .filter(
            CompanyIntelligenceFact.company_id == company_id,
            CompanyIntelligenceFact.category == category,
            CompanyIntelligenceFact.fact_key == fact_key,
        )
        .first()
    )
    if existing:
        existing.fact_value = fact_value
        existing.source = source
        existing.source_url = source_url or existing.source_url
        existing.confidence = confidence
        existing.evidence_text = evidence_text or existing.evidence_text
        existing.verified_by_human = verified_by_human or existing.verified_by_human
        db.commit()
        db.refresh(existing)
        return existing

    fact = CompanyIntelligenceFact(
        company_id=company_id,
        category=category,
        fact_key=fact_key,
        fact_value=fact_value,
        source=source,
        source_url=source_url,
        confidence=confidence,
        evidence_text=evidence_text,
        verified_by_human=verified_by_human,
    )
    db.add(fact)
    db.commit()
    db.refresh(fact)
    return fact


def record_timeline_event(
    db: Session,
    company_id: int,
    event_type: str,
    title: str,
    event_date: Optional[date] = None,
    description: Optional[str] = None,
    impact_level: str = "medium",
    buying_window_impact: Optional[str] = None,
    source: str = "system",
    source_ref: Optional[str] = None,
    raw_metadata: Optional[dict[str, Any]] = None,
) -> CompanyTimelineEvent:
    """Record an intelligence or sales interaction event on the company's timeline."""
    event = CompanyTimelineEvent(
        company_id=company_id,
        event_type=event_type,
        event_date=event_date or date.today(),
        title=title,
        description=description,
        impact_level=impact_level,
        buying_window_impact=buying_window_impact,
        source=source,
        source_ref=source_ref,
        raw_metadata=raw_metadata,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def build_company_timeline(db: Session, company_id: int) -> list[dict[str, Any]]:
    """
    Constructs a chronological intelligence timeline combining recorded timeline events,
    quotations, calibration assets, opportunities, and external signals.
    """
    events = []

    # 1. Stored Timeline Events
    stored = (
        db.query(CompanyTimelineEvent)
        .filter(CompanyTimelineEvent.company_id == company_id)
        .order_by(desc(CompanyTimelineEvent.event_date), desc(CompanyTimelineEvent.id))
        .all()
    )
    for s in stored:
        events.append({
            "id": f"event-{s.id}",
            "date": s.event_date.isoformat(),
            "event_type": s.event_type,
            "title": s.title,
            "description": s.description,
            "impact_level": s.impact_level,
            "buying_window_impact": s.buying_window_impact,
            "source": s.source,
            "source_ref": s.source_ref,
            "category": "intelligence",
        })

    # 2. Quotation Events
    quotes = db.query(Quotation).filter(Quotation.company_id == company_id).all()
    for q in quotes:
        events.append({
            "id": f"quote-{q.id}",
            "date": q.quotation_date.isoformat() if q.quotation_date else str(date.today()),
            "event_type": "quotation_submitted",
            "title": f"Quotation {q.quotation_number} (v{q.version_number})",
            "description": f"Quotation status: {q.status}. Total value: INR {float(q.total or 0):,.2f}",
            "impact_level": "high" if q.status == "Approved" else "medium",
            "buying_window_impact": "commercial_negotiation",
            "source": "quotation_engine",
            "source_ref": q.quotation_number,
            "category": "commercial",
        })

    # 3. Active / Due Asset Calibration Events
    assets = db.query(CustomerAsset).filter(CustomerAsset.company_id == company_id).all()
    for a in assets:
        if a.calibration_due_date:
            is_overdue = a.calibration_due_date <= date.today()
            events.append({
                "id": f"asset-{a.id}",
                "date": a.calibration_due_date.isoformat(),
                "event_type": "calibration_overdue" if is_overdue else "calibration_due",
                "title": f"Calibration Due: {a.instrument_name}",
                "description": f"Parameter: {a.parameter or 'Standard'}. Serial: {a.serial_number or 'N/A'}",
                "impact_level": "critical" if is_overdue else "high",
                "buying_window_impact": "immediate_window" if is_overdue else "approaching_cycle",
                "source": "asset_registry",
                "source_ref": a.instrument_name,
                "category": "calibration",
            })

    # Sort descending by date
    events.sort(key=lambda x: x["date"], reverse=True)
    return events


def get_company_brain_dossier(db: Session, company_id: int) -> dict[str, Any]:
    """
    Generates a full Company Brain Dossier containing verified facts, timeline,
    stakeholder decision network, and inferred equipment/processes.
    """
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        return {"error": "Company not found"}

    facts = db.query(CompanyIntelligenceFact).filter(CompanyIntelligenceFact.company_id == company_id).all()
    timeline = build_company_timeline(db, company_id)
    stakeholders = db.query(StakeholderIntelligence).filter(StakeholderIntelligence.company_id == company_id).all()
    persons = db.query(Person).filter(Person.company_id == company_id).all()

    # Group facts by category
    facts_by_category: dict[str, list[dict]] = {}
    for f in facts:
        facts_by_category.setdefault(f.category, []).append({
            "key": f.fact_key,
            "value": f.fact_value,
            "source": f.source,
            "source_url": f.source_url,
            "confidence": f.confidence,
            "evidence": f.evidence_text,
            "verified": f.verified_by_human,
        })

    # Stakeholder network synthesis
    stakeholder_list = []
    for s in stakeholders:
        p_name = s.person.full_name if s.person else "Unassigned / Target Role"
        p_email = s.person.email if s.person else None
        p_phone = s.person.phone if s.person else None
        stakeholder_list.append({
            "id": s.id,
            "role": s.stakeholder_role,
            "name": p_name,
            "email": p_email,
            "phone": p_phone,
            "department": s.department,
            "incentive_focus": s.incentive_focus,
            "influence_weight": s.influence_weight,
            "status": s.engagement_status,
            "notes": s.notes,
        })

    # Add any raw contacts not yet classified
    classified_person_ids = {s.person_id for s in stakeholders if s.person_id}
    for p in persons:
        if p.id not in classified_person_ids:
            stakeholder_list.append({
                "id": f"contact-{p.id}",
                "role": "unclassified",
                "name": p.full_name,
                "email": p.email,
                "phone": p.phone,
                "department": p.department or "General",
                "incentive_focus": "audit_and_technical" if "quality" in (p.designation or "").lower() else "commercial_pricing_sla",
                "influence_weight": 7.0 if p.is_decision_maker else 4.0,
                "status": "contacted" if p.email else "unreached",
                "notes": f"Imported contact: {p.designation or 'Staff'}",
            })

    return {
        "company_id": company.id,
        "company_name": company.name,
        "industry": company.industry,
        "location": f"{company.city}, {company.state}",
        "icp_score": company.icp_score,
        "buying_window": company.buying_window,
        "facts_count": len(facts),
        "facts": facts_by_category,
        "timeline": timeline,
        "stakeholder_network": stakeholder_list,
        "generated_at": datetime.utcnow().isoformat(),
    }
