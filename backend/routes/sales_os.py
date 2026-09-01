from datetime import date, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from typing import List, Optional

import pandas as pd
from fastapi import APIRouter, File, HTTPException, Query, UploadFile
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
    similar_quote_items,
    record_price_history,
)

router = APIRouter(prefix="/api/sales-os", tags=["Sales OS"])


def db_session():
    if SessionLocal is not None:
        return SessionLocal()
    from database import sync_engine
    if sync_engine is not None:
        from sqlalchemy.orm import sessionmaker
        return sessionmaker(bind=sync_engine)()
    return None


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


@router.post("/quotations/import")
async def import_historical_quotations(file: UploadFile = File(...)):
    """Import historical quotation line items from CSV/XLSX.

    Supported columns use common aliases: quotation number, date, customer,
    location, calibration type, instrument, make, model, range, parameter,
    quantity, unit price, and outcome.
    """
    db = db_session()
    try:
        filename = (file.filename or "").lower()
        payload = await file.read()
        if filename.endswith(".csv"):
            df = pd.read_csv(BytesIO(payload))
        elif filename.endswith(".xlsx"):
            df = pd.read_excel(BytesIO(payload))
        else:
            raise HTTPException(400, "Only CSV/XLSX historical quotation files are supported")

        aliases = {
            "quotation number": ["quotation number", "quote number", "quotation_no", "quote_no"],
            "quotation date": ["quotation date", "quote date", "date"],
            "customer": ["customer", "customer name", "company", "company name"],
            "location": ["location", "city"],
            "calibration type": ["calibration type", "service type", "type"],
            "instrument": ["instrument", "instrument name", "equipment", "item", "description"],
            "make": ["make", "manufacturer", "brand"],
            "model": ["model"],
            "range": ["range", "range value", "range_value"],
            "parameter": ["parameter", "calibration parameter"],
            "quantity": ["quantity", "qty"],
            "unit price": ["unit price", "price", "unit rate", "rate"],
            "outcome": ["outcome", "status", "quotation status"],
        }

        normalized_columns = {str(col).strip().lower(): col for col in df.columns}

        def pick(key: str, row):
            for alias in aliases[key]:
                if alias in normalized_columns:
                    value = row[normalized_columns[alias]]
                    if pd.isna(value):
                        return None
                    return value
            return None

        imported_rows = 0
        skipped_rows = 0
        created_quotes = 0
        created_items = 0

        for _, row in df.iterrows():
            instrument_name = pick("instrument", row)
            customer_name = pick("customer", row)
            if not instrument_name or not customer_name:
                skipped_rows += 1
                continue

            quote_number = pick("quotation number", row)
            quote_date_raw = pick("quotation date", row)
            if quote_date_raw is None:
                quote_date = date.today()
            else:
                try:
                    quote_date = pd.to_datetime(quote_date_raw).date()
                except Exception:
                    quote_date = date.today()

            existing_quote = None
            if quote_number:
                existing_quote = db.query(Quotation).filter(Quotation.quotation_number == str(quote_number)).first()

            if not existing_quote:
                existing_quote = Quotation(
                    quotation_number=str(quote_number) if quote_number else None,
                    quotation_date=quote_date,
                    customer_name=str(customer_name),
                    location=str(pick("location", row) or "") or None,
                    calibration_type=str(pick("calibration type", row) or "") or None,
                    status="Historical",
                    source_file=file.filename,
                )
                db.add(existing_quote)
                db.flush()
                created_quotes += 1

            raw_price = pick("unit price", row)
            try:
                unit_price = Decimal(str(raw_price).replace(",", "")) if raw_price is not None else Decimal("0")
            except Exception:
                unit_price = Decimal("0")

            raw_qty = pick("quantity", row)
            try:
                quantity = Decimal(str(raw_qty)) if raw_qty is not None else Decimal("1")
            except Exception:
                quantity = Decimal("1")

            parameter = pick("parameter", row)
            instrument, normalized, confidence = ensure_instrument(db, str(instrument_name), str(parameter) if parameter else None)

            item = QuotationItem(
                quotation_id=existing_quote.id,
                instrument_id=instrument.id,
                instrument_name=str(instrument_name),
                normalized_name=normalized,
                make=str(pick("make", row) or "") or None,
                model=str(pick("model", row) or "") or None,
                range_value=str(pick("range", row) or "") or None,
                parameter=str(parameter) if parameter else None,
                quantity=quantity,
                unit_price=unit_price,
                total_price=quantity * unit_price,
                price_source="historical_import",
                ai_confidence=confidence,
            )
            db.add(item)
            db.flush()

            record_price_history(
                db=db,
                quotation_id=existing_quote.id,
                customer_name=str(customer_name),
                instrument_id=instrument.id,
                calibration_type=existing_quote.calibration_type,
                location=existing_quote.location,
                unit_price=unit_price,
                quotation_date=quote_date,
                outcome=str(pick("outcome", row) or "") or None,
                context={"source_file": file.filename, "imported": True},
            )

            existing_quote.subtotal = (existing_quote.subtotal or 0) + (quantity * unit_price)
            existing_quote.total = (existing_quote.subtotal or 0) - (existing_quote.discount or 0) + (existing_quote.tax or 0)

            imported_rows += 1
            created_items += 1

        db.commit()
        return {
            "success": True,
            "source_file": file.filename,
            "rows_received": int(len(df)),
            "rows_imported": imported_rows,
            "rows_skipped": skipped_rows,
            "quotations_created": created_quotes,
            "items_created": created_items,
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(400, f"Historical quotation import failed: {exc}")
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
            "data_provenance": getattr(x, "data_provenance", None) or "PILOT_TEST_DATA",
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


class QuotationReviseRequest(BaseModel):
    revision_notes: Optional[str] = None
    discount: Optional[Decimal] = None
    tax: Optional[Decimal] = None


class QuotationStatusUpdate(BaseModel):
    status: str
    loss_reason: Optional[str] = None


class QuotationGenerateFromAssetsRequest(BaseModel):
    company_id: int
    facility_id: Optional[int] = None
    customer_asset_ids: Optional[List[int]] = None
    calibration_type: Optional[str] = "NABL Calibration"
    location: Optional[str] = None
    notes: Optional[str] = None


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


def revise_quotation_core(quotation_id: int, payload: QuotationReviseRequest, db: Session):
    """Core logic: Create a new immutable revision of an existing quotation."""
    parent = db.query(Quotation).filter(Quotation.id == quotation_id).first()
    if not parent:
        raise HTTPException(404, "Parent quotation not found")

    # Mark parent as previous version (immutable)
    parent.is_latest = False
    if parent.status not in ["Won", "Lost"]:
        parent.status = "Revised"

    # Generate new quotation number (e.g. Q-2026-001-R1)
    root_number = parent.quotation_number.split("-R")[0] if parent.quotation_number else f"Q-{parent.id}"
    next_ver = parent.version_number + 1
    new_quote_num = f"{root_number}-R{next_ver - 1}"

    # Ensure uniqueness
    existing = db.query(Quotation.id).filter(Quotation.quotation_number == new_quote_num).first()
    if existing:
        new_quote_num = f"{root_number}-R{next_ver - 1}-{int(datetime.utcnow().timestamp())}"

    new_quote = Quotation(
        company_id=parent.company_id,
        facility_id=parent.facility_id,
        opportunity_id=parent.opportunity_id,
        parent_quotation_id=parent.id,
        version_number=next_ver,
        is_latest=True,
        revision_notes=payload.revision_notes,
        quotation_number=new_quote_num,
        quotation_date=date.today(),
        valid_until=parent.valid_until or (date.today() + timedelta(days=30)),
        customer_name=parent.customer_name,
        location=parent.location,
        calibration_type=parent.calibration_type,
        subtotal=parent.subtotal,
        discount=payload.discount if payload.discount is not None else parent.discount,
        tax=payload.tax if payload.tax is not None else parent.tax,
        status="Draft",
        human_approved=0,
        notes=parent.notes,
    )
    new_quote.total = (new_quote.subtotal or 0) - (new_quote.discount or 0) + (new_quote.tax or 0)
    db.add(new_quote)
    db.flush()

    # Copy line items
    for item in parent.items:
        new_item = QuotationItem(
            quotation_id=new_quote.id,
            customer_asset_id=item.customer_asset_id,
            instrument_id=item.instrument_id,
            instrument_name=item.instrument_name,
            normalized_name=item.normalized_name,
            make=item.make,
            model=item.model,
            range_value=item.range_value,
            parameter=item.parameter,
            quantity=item.quantity,
            onsite=item.onsite,
            unit_price=item.unit_price,
            total_price=item.total_price,
            nabl_applicable=item.nabl_applicable,
            nabl_validated=item.nabl_validated,
            nabl_fit_status=item.nabl_fit_status,
            price_source=f"copied_from_v{parent.version_number}",
            ai_confidence=item.ai_confidence,
        )
        db.add(new_item)

    db.commit()
    db.refresh(new_quote)

    return {
        "id": new_quote.id,
        "quotation_number": new_quote.quotation_number,
        "version_number": new_quote.version_number,
        "parent_quotation_id": new_quote.parent_quotation_id,
        "status": new_quote.status,
        "total": float(new_quote.total or 0),
        "revision_notes": new_quote.revision_notes,
        "message": f"Quotation revision v{new_quote.version_number} created successfully.",
    }


@router.post("/quotations/{quotation_id}/revise")
def revise_quotation(quotation_id: int, payload: QuotationReviseRequest):
    """Create a new immutable revision of an existing quotation."""
    db = db_session()
    try:
        return revise_quotation_core(quotation_id, payload, db)
    finally:
        db.close()


@router.get("/quotations/{quotation_id}/revisions")
def get_quotation_revisions(quotation_id: int):
    """Get the full revision history for a quotation family."""
    db = db_session()
    try:
        quote = db.query(Quotation).filter(Quotation.id == quotation_id).first()
        if not quote:
            raise HTTPException(404, "Quotation not found")

        # Find the root quote
        root = quote
        while root.parent_quotation_id is not None:
            parent = db.query(Quotation).filter(Quotation.id == root.parent_quotation_id).first()
            if not parent:
                break
            root = parent

        # Collect all revisions in the family
        all_family = (
            db.query(Quotation)
            .filter(
                (Quotation.id == root.id) |
                (Quotation.parent_quotation_id == root.id) |
                (Quotation.quotation_number.like(f"{root.quotation_number.split('-R')[0]}%"))
            )
            .order_by(Quotation.version_number.asc())
            .all()
        )

        return {
            "root_id": root.id,
            "root_number": root.quotation_number,
            "total_versions": len(all_family),
            "results": [
                {
                    "id": q.id,
                    "quotation_number": q.quotation_number,
                    "version_number": q.version_number,
                    "is_latest": bool(q.is_latest),
                    "parent_quotation_id": q.parent_quotation_id,
                    "status": q.status,
                    "total": float(q.total or 0),
                    "human_approved": bool(q.human_approved),
                    "quotation_date": q.quotation_date,
                    "revision_notes": q.revision_notes,
                    "created_at": q.created_at,
                }
                for q in all_family
            ],
        }
    finally:
        db.close()


def compare_quotations_core(quotation_id: int, other_id: int, db: Session):
    """Core logic: Compare two quotation versions side-by-side."""
    q1 = db.query(Quotation).filter(Quotation.id == quotation_id).first()
    q2 = db.query(Quotation).filter(Quotation.id == other_id).first()
    if not q1 or not q2:
        raise HTTPException(404, "One or both quotations not found")

    items_q1 = {i.instrument_name: i for i in q1.items}
    items_q2 = {i.instrument_name: i for i in q2.items}

    all_instruments = set(items_q1.keys()).union(set(items_q2.keys()))
    item_diffs = []

    for inst in all_instruments:
        i1 = items_q1.get(inst)
        i2 = items_q2.get(inst)
        item_diffs.append({
            "instrument_name": inst,
            "in_q1": bool(i1),
            "in_q2": bool(i2),
            "q1_qty": float(i1.quantity) if i1 else None,
            "q2_qty": float(i2.quantity) if i2 else None,
            "q1_unit_price": float(i1.unit_price) if i1 else None,
            "q2_unit_price": float(i2.unit_price) if i2 else None,
            "q1_total": float(i1.total_price) if i1 else None,
            "q2_total": float(i2.total_price) if i2 else None,
            "price_changed": (float(i1.unit_price) != float(i2.unit_price)) if (i1 and i2) else True,
        })

    return {
        "quotation_1": {
            "id": q1.id,
            "number": q1.quotation_number,
            "version": q1.version_number,
            "subtotal": float(q1.subtotal or 0),
            "discount": float(q1.discount or 0),
            "tax": float(q1.tax or 0),
            "total": float(q1.total or 0),
            "status": q1.status,
        },
        "quotation_2": {
            "id": q2.id,
            "number": q2.quotation_number,
            "version": q2.version_number,
            "subtotal": float(q2.subtotal or 0),
            "discount": float(q2.discount or 0),
            "tax": float(q2.tax or 0),
            "total": float(q2.total or 0),
            "status": q2.status,
        },
        "total_diff": float((q2.total or 0) - (q1.total or 0)),
        "line_item_diffs": item_diffs,
    }


@router.get("/quotations/{quotation_id}/compare/{other_id}")
def compare_quotations(quotation_id: int, other_id: int):
    """Compare two quotation versions side-by-side."""
    db = db_session()
    try:
        return compare_quotations_core(quotation_id, other_id, db)
    finally:
        db.close()


def generate_quotation_from_assets_core(payload: QuotationGenerateFromAssetsRequest, db: Session):
    """Core logic: Generate an intelligent quotation draft directly from physical CustomerAsset records."""
    from models.customer_asset import CustomerAsset
    from models.facility import Facility
    from services.calibration_intelligence import match_nabl_service_fit

    company = db.query(Company).filter(Company.id == payload.company_id).first()
    if not company:
        raise HTTPException(404, "Company not found")

    asset_query = db.query(CustomerAsset).filter(
        CustomerAsset.company_id == payload.company_id,
        CustomerAsset.status == "Active",
    )
    if payload.facility_id:
        asset_query = asset_query.filter(CustomerAsset.facility_id == payload.facility_id)
    if payload.customer_asset_ids:
        asset_query = asset_query.filter(CustomerAsset.id.in_(payload.customer_asset_ids))

    assets = asset_query.all()
    if not assets:
        raise HTTPException(400, "No matching active customer assets found for quotation generation")

    facility = db.query(Facility).filter(Facility.id == payload.facility_id).first() if payload.facility_id else None
    location_val = payload.location or (facility.city if facility else company.city)

    quote_num = f"Q-AUTO-{company.id}-{int(datetime.utcnow().timestamp())}"
    quote = Quotation(
        company_id=company.id,
        facility_id=payload.facility_id,
        quotation_number=quote_num,
        quotation_date=date.today(),
        valid_until=date.today() + timedelta(days=30),
        customer_name=company.name,
        location=location_val,
        calibration_type=payload.calibration_type or "NABL Calibration",
        subtotal=Decimal("0"),
        discount=Decimal("0"),
        tax=Decimal("0"),
        total=Decimal("0"),
        status="Draft",
        human_approved=0,
        notes=payload.notes or f"Auto-generated draft quotation for {len(assets)} physical plant instruments.",
    )
    db.add(quote)
    db.flush()

    subtotal = Decimal("0")
    items_created = 0

    for a in assets:
        instrument, normalized, confidence = ensure_instrument(db, a.instrument_name, a.parameter)
        nabl_fit = match_nabl_service_fit(a.instrument_name, a.parameter, a.range_value)

        # Get price recommendation
        price_rec = price_recommendation(
            db=db,
            instrument_name=a.instrument_name,
            make=a.make,
            parameter=a.parameter,
            calibration_type=quote.calibration_type,
            location=location_val,
        )
        unit_price = Decimal(str(price_rec.get("recommended_unit_price") or "1200"))
        qty = Decimal("1")
        line_total = qty * unit_price

        item = QuotationItem(
            quotation_id=quote.id,
            customer_asset_id=a.id,
            instrument_id=instrument.id,
            instrument_name=a.instrument_name,
            normalized_name=normalized,
            make=a.make,
            model=a.model,
            range_value=a.range_value,
            parameter=a.parameter,
            quantity=qty,
            onsite=1 if payload.facility_id else 0,
            unit_price=unit_price,
            total_price=line_total,
            nabl_applicable=1 if nabl_fit["nabl_accredited"] else 0,
            nabl_validated=1,
            nabl_fit_status=nabl_fit["fit_status"],
            price_source=f"ai_recommendation_{price_rec.get('confidence_level', 'medium')}",
            ai_confidence=Decimal(str(confidence)),
        )
        db.add(item)
        subtotal += line_total
        items_created += 1

    quote.subtotal = subtotal
    quote.tax = round(subtotal * Decimal("0.18"), 2)  # 18% standard GST for Calibration in India
    quote.total = quote.subtotal - (quote.discount or Decimal("0")) + quote.tax

    db.commit()
    db.refresh(quote)

    return {
        "id": quote.id,
        "quotation_number": quote.quotation_number,
        "customer_name": quote.customer_name,
        "facility_id": quote.facility_id,
        "subtotal": float(quote.subtotal),
        "tax": float(quote.tax),
        "total": float(quote.total),
        "items_count": items_created,
        "status": quote.status,
        "message": f"Quotation draft generated with {items_created} customer assets.",
    }


@router.post("/quotations/generate-from-assets")
def generate_quotation_from_assets(payload: QuotationGenerateFromAssetsRequest):
    """Generate an intelligent quotation draft directly from physical CustomerAsset records."""
    db = db_session()
    try:
        return generate_quotation_from_assets_core(payload, db)
    finally:
        db.close()


def update_quotation_status_core(quotation_id: int, payload: QuotationStatusUpdate, db: Session):
    """Core logic: Update quotation status and propagate deal outcomes to Opportunities, Companies, and Orders."""
    from models.order import Order
    from models.activity import CRMActivity

    quote = db.query(Quotation).filter(Quotation.id == quotation_id).first()
    if not quote:
        raise HTTPException(404, "Quotation not found")

    quote.status = payload.status
    now = datetime.utcnow()

    if payload.status == "Won":
        # Propagate to Opportunity if linked
        if quote.opportunity_id:
            opp = db.query(Opportunity).filter(Opportunity.id == quote.opportunity_id).first()
            if opp:
                opp.stage = "Won"
                opp.probability = 100.0

        # Update Company
        if quote.company_id:
            comp = db.query(Company).filter(Company.id == quote.company_id).first()
            if comp:
                comp.order_received = True
                comp.order_date = now
                comp.order_value = (comp.order_value or 0) + float(quote.total or 0)
                comp.lead_status = "Customer"

        # Create CRM Activity
        act = CRMActivity(
            company_id=quote.company_id,
            activity_type="Quotation Won",
            status="Completed",
            remarks=f"Quotation {quote.quotation_number} marked as WON for amount INR {quote.total}",
            created_at=now,
        )
        db.add(act)

    elif payload.status == "Lost":
        if quote.opportunity_id:
            opp = db.query(Opportunity).filter(Opportunity.id == quote.opportunity_id).first()
            if opp:
                opp.stage = "Lost"
                opp.loss_reason = payload.loss_reason or "Price / Competitor"

    db.commit()
    return {
        "id": quote.id,
        "status": quote.status,
        "total": float(quote.total or 0),
        "message": f"Quotation status updated to {quote.status}.",
    }


@router.put("/quotations/{quotation_id}/status")
def update_quotation_status(quotation_id: int, payload: QuotationStatusUpdate):
    """Update quotation status and propagate deal outcomes to Opportunities, Companies, and Orders."""
    db = db_session()
    try:
        return update_quotation_status_core(quotation_id, payload, db)
    finally:
        db.close()


class HistoricalQuoteImportRequest(BaseModel):
    quotation_number: Optional[str] = None
    quotation_date: Optional[str] = None
    customer_name: str
    location: Optional[str] = "Pan-India"
    calibration_type: Optional[str] = "NABL Calibration"
    subtotal: float = 0.0
    discount: float = 0.0
    tax: float = 0.0
    total: float = 0.0
    outcome: Optional[str] = "Won"
    source_file: Optional[str] = "manual_import"
    data_provenance: Optional[str] = "USER_PROVIDED_REAL_DATA"
    items: Optional[List[dict]] = None
    raw_quote_text: Optional[str] = None


@router.post("/quotations/import-historical")
def import_historical_quotation_endpoint(payload: HistoricalQuoteImportRequest):
    """Ingests historical quotation data to seed real statistical pricing models and history."""
    from services.historical_quote_importer import parse_historical_quote_text, ingest_historical_quotation

    db = db_session()
    try:
        if payload.raw_quote_text:
            parsed = parse_historical_quote_text(payload.raw_quote_text, source_file=payload.source_file or "raw_text_entry")
            parsed["customer_name"] = payload.customer_name or parsed.get("customer_name")
            parsed["outcome"] = payload.outcome or parsed.get("outcome")
            parsed["location"] = payload.location or parsed.get("location")
            parsed["data_provenance"] = payload.data_provenance or "USER_PROVIDED_REAL_DATA"
        else:
            parsed = payload.model_dump()

        quote = ingest_historical_quotation(db, parsed)
        return {
            "status": "INGESTED SUCCESSFULLY",
            "quotation_id": quote.id,
            "quotation_number": quote.quotation_number,
            "customer_name": quote.customer_name,
            "line_items_indexed": len(quote.items),
            "total_value": float(quote.total or 0),
            "data_provenance": quote.data_provenance,
            "message": "Historical quotation ingested successfully into pricing dataset.",
        }
    finally:
        db.close()


@router.post("/quotations/upload-historical-file")
async def upload_historical_quote_file(file: UploadFile = File(...)):
    """Accepts uploaded PDF/CSV/Text historical quotation, parses line items and prices, and returns review preview."""
    from services.document_extractor import extract_text_from_bytes
    from services.historical_quote_importer import parse_historical_quote_text

    content = await file.read()
    extracted = extract_text_from_bytes(content, filename=file.filename or "historical_quote.pdf")
    text_content = extracted.get("text", "")

    parsed = parse_historical_quote_text(text_content, source_file=file.filename or "uploaded_quote")
    parsed["data_provenance"] = "USER_PROVIDED_REAL_DATA"
    parsed["extraction_status"] = extracted.get("status", "SUCCESS")
    parsed["extraction_confidence"] = extracted.get("confidence", 0.9)
    parsed["total_pages"] = extracted.get("total_pages", 1)
    if extracted.get("warning"):
        parsed["warning"] = extracted.get("warning")

    return {
        "status": "PARSED_FOR_REVIEW",
        "preview": parsed,
        "total_line_items_detected": len(parsed.get("items", [])),
        "extraction_quality": extracted.get("status", "SUCCESS"),
        "message": "Review extracted line items and confirm import to update pricing intelligence database.",
    }


@router.get("/quotations/historical/analytics")
def get_historical_quote_analytics():
    """Returns genuine statistical pricing benchmarks computed from imported historical quotations."""
    from services.historical_quote_importer import get_historical_pricing_analytics

    db = db_session()
    try:
        return get_historical_pricing_analytics(db)
    finally:
        db.close()
