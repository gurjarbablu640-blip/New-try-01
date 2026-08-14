"""Web research APIs.

The service stores source-backed research evidence. It does not invent facts
and does not expose AI inference as verified web evidence.
"""
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from database import SessionLocal
from models.company import Company
from models.web_research import WebResearchItem

router = APIRouter(prefix="/api/research", tags=["Web Research"])


class ResearchCreate(BaseModel):
    company_id: Optional[int] = None
    query: str = Field(min_length=1)
    title: Optional[str] = None
    url: str = Field(min_length=1)
    published_date: Optional[datetime] = None
    snippet: Optional[str] = None
    content: Optional[str] = None
    signal_type: Optional[str] = None
    confidence: int = Field(default=50, ge=0, le=100)
    metadata_json: Optional[dict] = None


@router.post("/evidence")
def create_research_evidence(payload: ResearchCreate):
    db = SessionLocal()
    try:
        if payload.company_id and not db.query(Company.id).filter(Company.id == payload.company_id).first():
            raise HTTPException(404, "Company not found")
        domain = urlparse(payload.url).netloc.lower() or None
        item = WebResearchItem(
            **payload.model_dump(),
            source_domain=domain,
            evidence_type="WEB_EVIDENCE",
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        return {
            "id": item.id,
            "company_id": item.company_id,
            "url": item.url,
            "source_domain": item.source_domain,
            "retrieved_at": item.retrieved_at,
            "evidence_type": item.evidence_type,
        }
    finally:
        db.close()


@router.get("/evidence")
def list_research_evidence(
    company_id: Optional[int] = None,
    signal_type: Optional[str] = None,
    domain: Optional[str] = None,
    limit: int = 50,
):
    db = SessionLocal()
    try:
        q = db.query(WebResearchItem)
        if company_id:
            q = q.filter(WebResearchItem.company_id == company_id)
        if signal_type:
            q = q.filter(WebResearchItem.signal_type == signal_type)
        if domain:
            q = q.filter(WebResearchItem.source_domain == domain.lower())
        rows = q.order_by(WebResearchItem.retrieved_at.desc()).limit(min(max(limit, 1), 200)).all()
        return {
            "results": [
                {
                    "id": x.id,
                    "company_id": x.company_id,
                    "query": x.query,
                    "title": x.title,
                    "url": x.url,
                    "source_domain": x.source_domain,
                    "published_date": x.published_date,
                    "retrieved_at": x.retrieved_at,
                    "snippet": x.snippet,
                    "signal_type": x.signal_type,
                    "confidence": x.confidence,
                    "evidence_type": x.evidence_type,
                }
                for x in rows
            ],
            "total": len(rows),
        }
    finally:
        db.close()


@router.get("/company/{company_id}")
def company_research(company_id: int, limit: int = 50):
    return list_research_evidence(company_id=company_id, limit=limit)
