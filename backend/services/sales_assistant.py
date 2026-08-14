"""Tool-based orchestration for the Oorja Sales Assistant.

The service intentionally keeps retrieval and business actions separate. It
returns structured tool results rather than allowing an LLM to execute raw
SQL or arbitrary mutations.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from models.company import Company
from models.person import Person
from models.sales_os import AIFeedback, Opportunity, Quotation, SalesTask


def search_companies(db: Session, query: str, limit: int = 20) -> dict[str, Any]:
    pattern = f"%{query.strip()}%"
    rows = (
        db.query(Company)
        .filter(or_(Company.name.ilike(pattern), Company.city.ilike(pattern), Company.industry.ilike(pattern)))
        .order_by(Company.icp_score.desc(), Company.created_at.desc())
        .limit(min(max(limit, 1), 100))
        .all()
    )
    return {
        "tool": "search_companies",
        "results": [
            {
                "id": row.id,
                "name": row.name,
                "industry": row.industry,
                "city": row.city,
                "state": row.state,
                "website": row.website,
                "icp_score": row.icp_score or 0,
                "intent_velocity_score": row.intent_velocity_score or 0,
                "buying_window": row.buying_window,
            }
            for row in rows
        ],
    }


def search_contacts(db: Session, query: str, limit: int = 20) -> dict[str, Any]:
    pattern = f"%{query.strip()}%"
    rows = (
        db.query(Person, Company)
        .join(Company, Company.id == Person.company_id)
        .filter(
            or_(
                Person.full_name.ilike(pattern),
                Person.designation.ilike(pattern),
                Person.department.ilike(pattern),
                Person.email.ilike(pattern),
            )
        )
        .order_by(Person.is_decision_maker.desc(), Person.updated_at.desc())
        .limit(min(max(limit, 1), 100))
        .all()
    )
    return {
        "tool": "search_contacts",
        "results": [
            {
                "id": person.id,
                "name": person.full_name,
                "designation": person.designation,
                "department": person.department,
                "email": person.email,
                "phone": person.phone,
                "company_id": company.id,
                "company": company.name,
                "decision_maker": person.is_decision_maker,
            }
            for person, company in rows
        ],
    }


def search_quotations(db: Session, query: str, limit: int = 20) -> dict[str, Any]:
    pattern = f"%{query.strip()}%"
    rows = (
        db.query(Quotation)
        .filter(or_(Quotation.customer_name.ilike(pattern), Quotation.quotation_number.ilike(pattern)))
        .order_by(Quotation.quotation_date.desc(), Quotation.id.desc())
        .limit(min(max(limit, 1), 100))
        .all()
    )
    return {
        "tool": "search_quotations",
        "results": [
            {
                "id": row.id,
                "quotation_number": row.quotation_number,
                "customer_name": row.customer_name,
                "quotation_date": row.quotation_date,
                "valid_until": row.valid_until,
                "status": row.status,
                "total": float(row.total or 0),
                "human_approved": bool(row.human_approved),
            }
            for row in rows
        ],
    }


def sales_summary(db: Session) -> dict[str, Any]:
    opportunities = db.query(Opportunity).filter(Opportunity.stage.notin_(["Won", "Lost"])).all()
    tasks = db.query(SalesTask).filter(SalesTask.status == "Open").all()
    quotations = db.query(Quotation).filter(Quotation.status.notin_(["Won", "Lost"])).all()
    pipeline_value = sum(float(item.estimated_value or 0) for item in opportunities)
    return {
        "tool": "sales_summary",
        "open_opportunities": len(opportunities),
        "open_pipeline_value": pipeline_value,
        "open_tasks": len(tasks),
        "open_quotations": len(quotations),
        "generated_at": datetime.utcnow().isoformat(),
    }


def record_feedback(
    db: Session,
    entity_type: str,
    entity_id: int | None,
    action_type: str,
    ai_value: dict | None,
    human_value: dict | None,
    reason: str | None,
) -> dict[str, Any]:
    feedback = AIFeedback(
        entity_type=entity_type,
        entity_id=entity_id,
        action_type=action_type,
        ai_value=ai_value,
        human_value=human_value,
        reason=reason,
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return {"tool": "record_feedback", "id": feedback.id, "status": "recorded"}


TOOLS = {
    "search_companies": search_companies,
    "search_contacts": search_contacts,
    "search_quotations": search_quotations,
    "sales_summary": sales_summary,
}
