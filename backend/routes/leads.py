"""Lead Management & Outbound Ingestion APIs.

Integrates Apollo discovery, multi-vector deduplication, email validation,
ICP scoring, and lead qualification lifecycle gates.
"""
from __future__ import annotations

from datetime import datetime
from io import BytesIO
from typing import Any, Optional

import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, or_
from sqlalchemy.orm import Session

from database import get_db
from models.company import Company
from models.person import Person
from services.apollo_adapter import search_apollo_leads
from services.deduplication import (
    extract_domain,
    find_company_duplicate,
    ingest_or_merge_lead,
    normalize_company_name,
    normalize_phone_number,
)
from services.email_validator import normalize_email, validate_email_address, validate_email_batch
from services.lead_qualification import (
    batch_evaluate_leads,
    evaluate_lead_qualification,
    set_qualification_status,
)
from services.scoringEngine import calculate_icp_score

router = APIRouter(prefix="/api/leads", tags=["Leads"])


# ============================================================
# PYDANTIC SCHEMAS
# ============================================================


class ContactInput(BaseModel):
    name: str = Field(min_length=1)
    title: Optional[str] = None
    designation: Optional[str] = None
    department: Optional[str] = None
    seniority_level: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    apollo_id: Optional[str] = None
    is_decision_maker: int = 0


class LeadCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    city: Optional[str] = None
    state: Optional[str] = None
    country: str = "India"
    industry: Optional[str] = None
    website: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    linkedin: Optional[str] = None
    contact_person: Optional[str] = None
    division: Optional[str] = None
    remarks: Optional[str] = None
    source: str = "manual"
    contacts: Optional[list[ContactInput]] = None


class ApolloSearchRequest(BaseModel):
    query: Optional[str] = None
    locations: Optional[list[str]] = None
    titles: Optional[list[str]] = None
    industries: Optional[list[str]] = None
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=25, ge=1, le=100)
    force_mock: bool = False


class ApolloLeadPayload(BaseModel):
    apollo_id: Optional[str] = None
    company_name: str
    website: Optional[str] = None
    domain: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = "India"
    industry: Optional[str] = None
    headcount: Optional[str] = None
    contacts: Optional[list[ContactInput]] = None


class ApolloIngestRequest(BaseModel):
    leads: list[ApolloLeadPayload]
    auto_qualify: bool = True


class EmailValidationRequest(BaseModel):
    email: Optional[str] = None
    emails: Optional[list[str]] = None


class DeduplicationCheckRequest(BaseModel):
    name: str
    domain: Optional[str] = None
    city: Optional[str] = None
    email: Optional[str] = None
    apollo_id: Optional[str] = None


class QualificationUpdateRequest(BaseModel):
    status: str
    reason: Optional[str] = None


class BatchQualifyRequest(BaseModel):
    company_ids: list[int]
    status: Optional[str] = None
    reason: Optional[str] = None
    auto_evaluate: bool = False


# ============================================================
# HELPER SERIALIZERS
# ============================================================


def _serialize_person(p: Person) -> dict[str, Any]:
    return {
        "id": p.id,
        "company_id": p.company_id,
        "full_name": p.full_name,
        "designation": p.designation,
        "department": p.department,
        "seniority_level": p.seniority_level,
        "email": p.email,
        "phone": p.phone,
        "linkedin_url": p.linkedin_url,
        "email_verification_status": p.email_verification_status or "unverified",
        "email_verification_reason": p.email_verification_reason,
        "email_verified_at": p.email_verified_at,
        "is_decision_maker": p.is_decision_maker,
    }


def _serialize_company(c: Company, include_contacts: bool = False) -> dict[str, Any]:
    res = {
        "id": c.id,
        "name": c.name,
        "normalized_name": c.normalized_name,
        "domain": c.domain,
        "industry": c.industry,
        "city": c.city,
        "state": c.state,
        "country": c.country,
        "website": c.website,
        "email": c.email,
        "phone": c.phone,
        "linkedin": c.linkedin,
        "contact_person": c.contact_person,
        "division": c.division,
        "remarks": c.remarks,
        "source": c.source or "manual",
        "apollo_id": c.apollo_id,
        "lead_status": c.lead_status,
        "qualification_status": c.qualification_status or "RAW",
        "qualification_reason": c.qualification_reason,
        "qualified_at": c.qualified_at,
        "last_contact_date": c.last_contact_date,
        "next_followup_date": c.next_followup_date,
        "contact_page": c.contact_page,
        "address": c.address,
        "icp_score": c.icp_score or 0,
        "tier": c.calculated_tier or "Unscored",
        "has_nabl": c.has_nabl or False,
        "buying_window": c.buying_window or "unknown",
        "order_received": c.order_received or False,
        "order_value": float(c.order_value) if c.order_value else 0,
        "billing_status": c.billing_status or "Pending",
        "payment_status": c.payment_status or "Pending",
        "created_at": c.created_at,
        "updated_at": c.updated_at,
    }
    if include_contacts and c.persons:
        res["contacts"] = [_serialize_person(p) for p in c.persons]
    return res


# ============================================================
# APOLLO SEARCH & INGESTION ENDPOINTS
# ============================================================


@router.post("/apollo/search")
def apollo_search(data: ApolloSearchRequest):
    """Search industrial leads via Apollo API or mock fallback."""
    return search_apollo_leads(
        query=data.query,
        locations=data.locations,
        titles=data.titles,
        industries=data.industries,
        page=data.page,
        per_page=data.per_page,
        force_mock=data.force_mock,
    )


@router.post("/apollo/ingest")
def apollo_ingest(data: ApolloIngestRequest, db: Session = Depends(get_db)):
    """Ingest, deduplicate, validate emails, and qualify selected Apollo leads."""
    created_count = 0
    merged_count = 0
    ingested_results = []

    for item in data.leads:
        company_data = {
            "name": item.company_name,
            "website": item.website,
            "domain": item.domain or extract_domain(item.website),
            "city": item.city,
            "state": item.state,
            "country": item.country or "India",
            "industry": item.industry,
            "source": "apollo",
            "apollo_id": item.apollo_id,
            "qualification_status": "RAW",
        }

        contacts_payload = []
        if item.contacts:
            for c in item.contacts:
                contacts_payload.append(c.model_dump())

        company, persons, action = ingest_or_merge_lead(
            db=db,
            company_data=company_data,
            contacts_data=contacts_payload,
            auto_validate_emails=True,
        )

        if action == "CREATED":
            created_count += 1
        else:
            merged_count += 1

        # Run ICP Scoring
        calculate_icp_score(company.id, db)

        # Run Qualification Gate
        if data.auto_qualify:
            evaluate_lead_qualification(db, company.id)

        ingested_results.append(
            {
                "company_id": company.id,
                "company_name": company.name,
                "domain": company.domain,
                "action": action,
                "qualification_status": company.qualification_status,
                "icp_score": company.icp_score,
                "tier": company.calculated_tier,
                "contacts_count": len(persons),
            }
        )

    db.commit()
    return {
        "success": True,
        "total_processed": len(data.leads),
        "created": created_count,
        "merged": merged_count,
        "results": ingested_results,
    }


# ============================================================
# EMAIL VALIDATION & DEDUPLICATION TOOLS
# ============================================================


@router.post("/validate-email")
def validate_email_endpoint(payload: EmailValidationRequest):
    """Validate a single email address or a list of emails."""
    if payload.email:
        return validate_email_address(payload.email)
    if payload.emails:
        return {"total": len(payload.emails), "results": validate_email_batch(payload.emails)}
    raise HTTPException(400, "Provide either 'email' or 'emails' in payload")


@router.post("/deduplicate/check")
def check_duplicate(payload: DeduplicationCheckRequest, db: Session = Depends(get_db)):
    """Check potential duplicate candidates for a company payload."""
    match, reason, confidence = find_company_duplicate(
        db=db,
        name=payload.name,
        domain=payload.domain,
        city=payload.city,
        email=payload.email,
        apollo_id=payload.apollo_id,
    )
    if match:
        return {
            "is_duplicate": True,
            "match_reason": reason,
            "confidence": confidence,
            "existing_company": _serialize_company(match),
        }
    return {
        "is_duplicate": False,
        "match_reason": "no_match",
        "confidence": 0,
        "existing_company": None,
    }


# ============================================================
# QUALIFICATION GATE ENDPOINTS
# ============================================================


@router.post("/{company_id}/qualify")
def qualify_lead_endpoint(
    company_id: int,
    payload: Optional[QualificationUpdateRequest] = None,
    db: Session = Depends(get_db),
):
    """Set qualification status manually or run automated evaluation."""
    if payload and payload.status:
        res = set_qualification_status(
            db=db,
            company_id=company_id,
            status=payload.status,
            reason=payload.reason,
        )
    else:
        res = evaluate_lead_qualification(db=db, company_id=company_id)

    if "error" in res:
        raise HTTPException(400, res["error"])
    return res


@router.get("/qualification-queue")
def get_qualification_queue(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """Get leads in the qualification queue (RAW, NEEDS_ENRICHMENT, QUALIFIED, etc.)."""
    query = db.query(Company)
    if status:
        query = query.filter(Company.qualification_status == status.strip().upper())
    else:
        query = query.filter(Company.qualification_status.in_(["RAW", "NEEDS_ENRICHMENT", "QUALIFIED"]))

    total = query.count()
    companies = query.order_by(Company.icp_score.desc().nullslast(), Company.id.desc()).offset(offset).limit(limit).all()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "results": [_serialize_company(c, include_contacts=True) for c in companies],
    }


@router.post("/qualification-queue/batch")
def batch_qualify_endpoint(payload: BatchQualifyRequest, db: Session = Depends(get_db)):
    """Batch qualify or evaluate multiple company IDs."""
    if payload.auto_evaluate:
        return batch_evaluate_leads(db, payload.company_ids)

    if not payload.status:
        raise HTTPException(400, "Provide 'status' or set 'auto_evaluate=true'")

    results = []
    for cid in payload.company_ids:
        res = set_qualification_status(
            db=db,
            company_id=cid,
            status=payload.status,
            reason=payload.reason or "Batch updated",
        )
        results.append(res)
    return {"total": len(results), "results": results}


# ============================================================
# STANDARD LEAD CRUD ENDPOINTS (PRESERVED & ENHANCED)
# ============================================================


@router.post("/add")
def add_lead(data: LeadCreateRequest, db: Session = Depends(get_db)):
    """Create or merge a lead with deduplication and email validation."""
    company_data = {
        "name": data.name,
        "city": data.city,
        "state": data.state,
        "country": data.country,
        "industry": data.industry,
        "website": data.website,
        "phone": data.phone,
        "email": data.email,
        "linkedin": data.linkedin,
        "contact_person": data.contact_person,
        "division": data.division,
        "remarks": data.remarks,
        "source": data.source or "manual",
    }

    contacts_payload = []
    if data.contacts:
        contacts_payload = [c.model_dump() for c in data.contacts]
    elif data.contact_person or data.email or data.phone:
        contacts_payload.append(
            {
                "name": data.contact_person or "Primary Contact",
                "email": data.email,
                "phone": data.phone,
                "designation": data.division,
                "is_decision_maker": 1,
            }
        )

    company, persons, action = ingest_or_merge_lead(
        db=db,
        company_data=company_data,
        contacts_data=contacts_payload,
        auto_validate_emails=True,
    )

    calculate_icp_score(company.id, db)
    evaluate_lead_qualification(db, company.id)
    db.commit()

    return {
        "success": True,
        "action": action,
        "company_id": company.id,
        "name": company.name,
        "qualification_status": company.qualification_status,
        "icp_score": company.icp_score,
        "tier": company.calculated_tier,
    }


@router.post("/upload")
async def upload_leads(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Upload leads from CSV/XLSX with automatic deduplication and normalization."""
    filename = (file.filename or "").lower()
    payload = await file.read()

    try:
        if filename.endswith(".csv"):
            df = pd.read_csv(BytesIO(payload))
        elif filename.endswith((".xlsx", ".xls")):
            df = pd.read_excel(BytesIO(payload))
        else:
            return {"success": False, "error": "Only CSV/XLSX supported"}

        created = 0
        merged = 0
        skipped = 0

        for _, row in df.iterrows():
            company_name = str(row.get("Company Name") or row.get("Company") or row.get("name") or "").strip()
            if not company_name or company_name.lower() in {"nan", "none"}:
                skipped += 1
                continue

            city = str(row.get("Location") or row.get("City") or row.get("city") or "")
            state = str(row.get("State") or row.get("state") or "")
            contact_person = str(row.get("Contact Person") or row.get("Contact") or "")
            phone = str(row.get("Phone") or row.get("Mobile") or "")
            email = str(row.get("Email") or row.get("email") or "")
            website = str(row.get("Website") or row.get("website") or "")
            industry = str(row.get("Industry") or row.get("industry") or "Uploaded Lead")
            remarks = str(row.get("Remarks") or row.get("remarks") or "")

            company_data = {
                "name": company_name,
                "city": city if city and city.lower() != "nan" else None,
                "state": state if state and state.lower() != "nan" else None,
                "website": website if website and website.lower() != "nan" else None,
                "phone": phone if phone and phone.lower() != "nan" else None,
                "email": email if email and email.lower() != "nan" else None,
                "industry": industry if industry and industry.lower() != "nan" else "Uploaded Lead",
                "remarks": remarks if remarks and remarks.lower() != "nan" else None,
                "source": "csv_upload",
            }

            contacts_data = []
            if (contact_person and contact_person.lower() != "nan") or (email and email.lower() != "nan"):
                contacts_data.append(
                    {
                        "name": contact_person if contact_person and contact_person.lower() != "nan" else "Primary Contact",
                        "email": email if email and email.lower() != "nan" else None,
                        "phone": phone if phone and phone.lower() != "nan" else None,
                        "is_decision_maker": 1,
                    }
                )

            company, persons, action = ingest_or_merge_lead(
                db=db,
                company_data=company_data,
                contacts_data=contacts_data,
                auto_validate_emails=True,
            )

            calculate_icp_score(company.id, db)
            evaluate_lead_qualification(db, company.id)

            if action == "CREATED":
                created += 1
            else:
                merged += 1

        db.commit()
        return {
            "success": True,
            "created": created,
            "merged": merged,
            "skipped": skipped,
            "total_rows": len(df),
        }
    except Exception as exc:
        db.rollback()
        return {"success": False, "error": str(exc)}


@router.get("/")
def get_leads(
    status: Optional[str] = None,
    qualification_status: Optional[str] = None,
    tier: Optional[str] = None,
    city: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """List all leads with optional filtering and pagination."""
    query = db.query(Company)
    if status:
        query = query.filter(Company.lead_status == status)
    if qualification_status:
        query = query.filter(Company.qualification_status == qualification_status.strip().upper())
    if tier:
        query = query.filter(Company.calculated_tier == tier)
    if city:
        query = query.filter(Company.city.ilike(f"%{city}%"))

    total = query.count()
    companies = query.order_by(Company.created_at.desc(), Company.id.desc()).offset(offset).limit(limit).all()

    return {
        "success": True,
        "total": total,
        "results": [_serialize_company(c) for c in companies],
    }


@router.get("/{company_id}")
def get_lead(company_id: int, db: Session = Depends(get_db)):
    """Get single lead with attached contacts and qualification details."""
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(404, "Lead not found")
    return {"success": True, "result": _serialize_company(company, include_contacts=True)}