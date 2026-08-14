"""Core Oorja Sales OS CRM and quotation intelligence APIs."""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import SessionLocal
from models.company import Company
from models.sales_os import (
    AIFeedback,
    Opportunity,
    PriceHistory,
    Quotation,
    QuotationItem,
    SalesNote,
    SalesTask,
)
from services.quotation_intelligence import (
    ensure_instrument,
    normalize_instrument_name,
    price_recommendation,
    resolve_instrument,
    similar_quote_items,
)

router = APIRouter(prefix="/api/sales-os", tags=["Sales OS"])


def db_session():
    return SessionLocal()


class OpportunityCreate(BaseModel):
    company_id: int
    person_id: Optional[int] = None
    name: str = Field(min_length=1, max_length=500)
    stage: str = "New"
    probability: Decimal = Decimal("0")
    estimated_value: Decimal = Decimal("0")
    expected_close_date: Optional[date] = None
    source: Optional[str] = None
    notes: Optional[str] = None


class TaskCreate(BaseModel):
    company_id: Optional[int] = None
    opportunity_id: Optional[int] = None
    person_id: Optional[int] = None
    title: str = Field(min_length=1, max_length=500)
    task_type: str = "Follow-up"
    priority: str = "Medium"
    due_at: Optional[datetime] = None
    source: str = "manual"
    ai_reason: Optional[str] = None
    notes: Optional[str] = None


class NoteCreate(BaseModel):
    company_id: int
    person_id: Optional[int] = None
    opportunity_id: Optional[int] = None
    note_type: str = "General"
    body: str = Field(min_length=1)
    source: str = "user"


class FeedbackCreate(BaseModel):
    entity_type: str
    entity_id: Optional[int] = None
    action_type: str
    ai_value: Optional[dict] = None
    human_value: Optional[dict] = None
    reason: Optional[str] = None
    outcome: Optional[str] = None
    confidence: Optional[Decimal] = None


class QuotationCreate(BaseModel):
    company_id: Optional[int] = None
    opportunity_id: Optional[int] = None
    quotation_number: Optional[str] = None
    customer_name: str
    quotation_date: date
    valid_until: Optional[date] = None
    location: Optional[str] = None
    calibration_type: Optional[str] = None
    notes: Optional[str] = None


class QuotationApproval(BaseModel):
    approved: bool


class QuotationItemCreate(BaseModel):
    instrument_name: str = Field(min_length=1, max_length=500)
    make: Optional[str] = None
    model: Optional[str] = None
    range_value: Optional[str] = None
    parameter: Optional[str] = None
    quantity: Decimal = Decimal("1")
    onsite: bool = False
    unit_price: Decimal = Decimal("0")


class InstrumentResolveRequest(BaseModel):
    instrument_name: str = Field(min_length=1)
    parameter: Optional[str] = None


def company_exists(db: Session, company_id: int) -> None:
    if not db.query(Company.id).filter(Company.id == company_id).first():
        raise HTTPException(404, "Company not found")


def serialize_opportunity(item: Opportunity) -> dict:
    return {
        "id": item.id,
        "company_id": item.company_id,
        "person_id": item.person_id,
        "name": item.name,
        "stage": item.stage,
        "probability": float(item.probability or 0),
        "estimated_value": float(item.estimated_value or 0),
        "expected_close_date": item.expected_close_date,
        "source": item.source,
        "loss_reason": item.loss_reason,
        "notes": item.notes,
        "ai_summary": item.ai_summary,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


@router.get("/summary")
def sales_os_summary():
    db = db_session()
    try:
        open_opportunities = db.query(Opportunity).filter(Opportunity.stage.notin_(["Won", "Lost"])).count()
        active_tasks = db.query(SalesTask).filter(SalesTask.status == "Open").count()
        quotations = db.query(Quotation).filter(Quotation.status.notin_(["Won", "Lost"])).count()
        return {
            "open_opportunities": open_opportunities,
            "active_tasks": active_tasks,
            "open_quotations": quotations,
            "system": "Oorja Sales OS",
        }
    finally:
        db.close()


@router.post("/opportunities")
def create_opportunity(payload: OpportunityCreate):
    db = db_session()
    try:
        company_exists(db, payload.company_id)
        item = Opportunity(**payload.model_dump())
        db.add(item)
        db.commit()
        db.refresh(item)
        return serialize_opportunity(item)
    finally:
        db.close()


@router.get("/opportunities")
def list_opportunities(company_id: Optional[int] = None, stage: Optional[str] = None):
    db = db_session()
    try:
        query = db.query(Opportunity)
        if company_id:
            query = query.filter(Opportunity.company_id == company_id)
        if stage:
            query = query.filter(Opportunity.stage == stage)
        items = query.order_by(Opportunity.updated_at.desc()).all()
        return {"results": [serialize_opportunity(x) for x in items], "total": len(items)}
    finally:
        db.close()


@router.post("/tasks")
def create_task(payload: TaskCreate):
    db = db_session()
    try:
        if payload.company_id:
            company_exists(db, payload.company_id)
        item = SalesTask(**payload.model_dump())
        db.add(item)
        db.commit()
        db.refresh(item)
        return {
            "id": item.id,
            "title": item.title,
            "status": item.status,
            "priority": item.priority,
            "due_at": item.due_at,
            "company_id": item.company_id,
            "opportunity_id": item.opportunity_id,
            "ai_reason": item.ai_reason,
        }
    finally:
        db.close()


@router.get("/tasks")
def list_tasks(status: str = "Open", limit: int = 100):
    db = db_session()
    try:
        items = (
            db.query(SalesTask)
            .filter(SalesTask.status == status)
            .order_by(SalesTask.due_at.asc().nullslast(), SalesTask.id.desc())
            .limit(min(max(limit, 1), 500))
            .all()
        )
        return {"results": [{
            "id": x.id,
            "title": x.title,
            "task_type": x.task_type,
            "priority": x.priority,
            "status": x.status,
            "due_at": x.due_at,
            "company_id": x.company_id,
            "opportunity_id": x.opportunity_id,
            "person_id": x.person_id,
            "ai_reason": x.ai_reason,
            "notes": x.notes,
        } for x in items], "total": len(items)}
    finally:
        db.close()


@router.post("/notes")
def create_note(payload: NoteCreate):
    db = db_session()
    try:
        company_exists(db, payload.company_id)
        item = SalesNote(**payload.model_dump())
        db.add(item)
        db.commit()
        db.refresh(item)
        return {"id": item.id, "created_at": item.created_at}
    finally:
        db.close()


@router.post("/ai-feedback")
def record_ai_feedback(payload: FeedbackCreate):
    db = db_session()
    try:
        item = AIFeedback(**payload.model_dump())
        db.add(item)
        db.commit()
        db.refresh(item)
        return {"id": item.id, "status": "recorded"}
    finally:
        db.close()


@router.post("/quotations")
def create_quotation(payload: QuotationCreate):
    db = db_session()
    try:
        if payload.company_id:
            company_exists(db, payload.company_id)
        if payload.quotation_number:
            duplicate = db.query(Quotation.id).filter(Quotation.quotation_number == payload.quotation_number).first()
            if duplicate:
                raise HTTPException(409, "Quotation number already exists")
        item = Quotation(**payload.model_dump())
        db.add(item)
        db.commit()
        db.refresh(item)
        return {
            "id": item.id,
            "quotation_number": item.quotation_number,
            "status": item.status,
            "human_approved": bool(item.human_approved),
            "message": "Draft quotation created. Human approval is required before release.",
        }
    finally:
        db.close()


@router.get("/quotations")
def list_quotations(company_id: Optional[int] = None, status: Optional[str] = None):
    db = db_session()
    try:
        query = db.query(Quotation)
        if company_id:
            query = query.filter(Quotation.company_id == company_id)
        if status:
            query = query.filter(Quotation.status == status)
        items = query.order_by(Quotation.quotation_date.desc(), Quotation.id.desc()).all()
        return {"results": [{
            "id": x.id,
            "quotation_number": x.quotation_number,
            "customer_name": x.customer_name,
            "quotation_date": x.quotation_date,
            "valid_until": x.valid_until,
            "status": x.status,
            "total": float(x.total or 0),
            "human_approved": bool(x.human_approved),
            "company_id": x.company_id,
            "opportunity_id": x.opportunity_id,
        } for x in items], "total": len(items)}
    finally:
        db.close()


@router.post("/quotations/{quotation_id}/items")
def add_quotation_item(quotation_id: int, payload: QuotationItemCreate):
    db = db_session()
    try:
        quotation = db.query(Quotation).filter(Quotation.id == quotation_id).first()
        if not quotation:
            raise HTTPException(404, "Quotation not found")
        if quotation.human_approved:
            raise HTTPException(409, "Approved quotations cannot be edited")

        instrument, normalized, confidence = ensure_instrument(db, payload.instrument_name, payload.parameter)
        total = payload.quantity * payload.unit_price
        item = QuotationItem(
            quotation_id=quotation_id,
            instrument_id=instrument.id,
            instrument_name=payload.instrument_name,
            normalized_name=normalized,
            make=payload.make,
            model=payload.model,
            range_value=payload.range_value,
            parameter=payload.parameter,
            quantity=payload.quantity,
            onsite=int(payload.onsite),
            unit_price=payload.unit_price,
            total_price=total,
            price_source="human_entry",
            ai_confidence=confidence,
        )
        db.add(item)
        db.flush()
        quotation.subtotal = sum((x.total_price or 0) for x in quotation.items)
        quotation.total = quotation.subtotal - (quotation.discount or 0) + (quotation.tax or 0)
        db.commit()
        db.refresh(item)
        return {
            "id": item.id,
            "normalized_name": item.normalized_name,
            "instrument_id": item.instrument_id,
            "unit_price": float(item.unit_price or 0),
            "total_price": float(item.total_price or 0),
            "quotation_total": float(quotation.total or 0),
        }
    finally:
        db.close()


@router.get("/quotations/{quotation_id}/items")
def list_quotation_items(quotation_id: int):
    db = db_session()
    try:
        items = db.query(QuotationItem).filter(QuotationItem.quotation_id == quotation_id).order_by(QuotationItem.id).all()
        return {"results": [{
            "id": x.id,
            "instrument_name": x.instrument_name,
            "normalized_name": x.normalized_name,
            "make": x.make,
            "model": x.model,
            "range_value": x.range_value,
            "parameter": x.parameter,
            "quantity": float(x.quantity or 0),
            "onsite": bool(x.onsite),
            "unit_price": float(x.unit_price or 0),
            "total_price": float(x.total_price or 0),
            "ai_confidence": float(x.ai_confidence or 0),
        } for x in items], "total": len(items)}
    finally:
        db.close()


@router.post("/instrument/resolve")
def resolve_instrument_route(payload: InstrumentResolveRequest):
    db = db_session()
    try:
        instrument, normalized, confidence = ensure_instrument(db, payload.instrument_name, payload.parameter)
        db.commit()
        return {
            "instrument_id": instrument.id,
            "input": payload.instrument_name,
            "normalized_name": normalized,
            "family": instrument.family,
            "parameter": instrument.parameter,
            "confidence": confidence,
        }
    finally:
        db.close()


@router.get("/instrument/normalize")
def normalize_instrument_route(name: str = Query(min_length=1)):
    return {"input": name, "normalized_name": normalize_instrument_name(name)}


@router.get("/quotation-intelligence/similar")
def similar_quotes_route(
    instrument_name: str = Query(min_length=1),
    make: Optional[str] = None,
    parameter: Optional[str] = None,
    calibration_type: Optional[str] = None,
    location: Optional[str] = None,
    limit: int = 20,
):
    db = db_session()
    try:
        matches = similar_quote_items(db, instrument_name, make, parameter, calibration_type, location, limit)
        return {"results": matches, "total": len(matches)}
    finally:
        db.close()


@router.get("/quotation-intelligence/price-recommendation")
def price_recommendation_route(
    instrument_name: str = Query(min_length=1),
    make: Optional[str] = None,
    parameter: Optional[str] = None,
    calibration_type: Optional[str] = None,
    location: Optional[str] = None,
    limit: int = 20,
):
    db = db_session()
    try:
        return price_recommendation(db, instrument_name, make, parameter, calibration_type, location, limit)
    finally:
        db.close()


@router.post("/quotations/{quotation_id}/approval")
def approve_quotation(quotation_id: int, payload: QuotationApproval):
    db = db_session()
    try:
        item = db.query(Quotation).filter(Quotation.id == quotation_id).first()
        if not item:
            raise HTTPException(404, "Quotation not found")
        if payload.approved:
            item.human_approved = 1
            item.approved_at = datetime.utcnow()
            item.status = "Approved"
        else:
            item.human_approved = 0
            item.approved_at = None
            item.status = "Draft"
        db.commit()
        return {
            "id": item.id,
            "status": item.status,
            "human_approved": bool(item.human_approved),
            "approved_at": item.approved_at,
        }
    finally:
        db.close()
