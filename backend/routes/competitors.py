"""Competitor intelligence APIs.

Read APIs expose evidence-backed competitor context. Write APIs capture
observations and profiles; they never alter a customer record implicitly.
"""
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import SessionLocal
from models.competitor_intel import CompetitorObservation, CompetitorProfile
from models.company import Company

router = APIRouter(prefix="/api/competitors", tags=["Competitor Intelligence"])


class CompetitorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=500)
    website: Optional[str] = None
    country: Optional[str] = None
    service_focus: Optional[str] = None
    positioning: Optional[str] = None
    pricing_notes: Optional[str] = None
    strengths: Optional[Any] = None
    weaknesses: Optional[Any] = None
    metadata_json: Optional[dict] = None


class ObservationCreate(BaseModel):
    competitor_id: int
    company_id: Optional[int] = None
    observation_type: str = Field(min_length=1, max_length=100)
    title: Optional[str] = None
    evidence: str = Field(min_length=1)
    source_url: Optional[str] = None
    source_name: Optional[str] = None
    observed_at: Optional[datetime] = None
    confidence: int = Field(default=50, ge=0, le=100)
    classification: str = "WEB_EVIDENCE"
    metadata_json: Optional[dict] = None


@router.post("")
def create_competitor(payload: CompetitorCreate):
    db = SessionLocal()
    try:
        exists = db.query(CompetitorProfile).filter(CompetitorProfile.name.ilike(payload.name)).first()
        if exists:
            raise HTTPException(409, "Competitor already exists")
        item = CompetitorProfile(**payload.model_dump())
        db.add(item)
        db.commit()
        db.refresh(item)
        return {"id": item.id, "name": item.name, "status": "created"}
    finally:
        db.close()


@router.post("/seed-default-competitors")
def seed_default_competitors():
    """Seed key regional calibration competitors and battlecards in Gujarat/India."""
    db = SessionLocal()
    try:
        seeds = [
            {
                "name": "TCR Engineering Services Pvt Ltd",
                "website": "https://tcreng.com",
                "country": "India",
                "service_focus": "Materials Testing, Metallurgical & Calibration",
                "positioning": "Large national multi-disciplinary testing laboratory with Pan-India presence.",
                "pricing_notes": "Premium corporate pricing. Standard 7-10 day turnaround.",
                "strengths": ["Strong brand recognition", "Extensive accredited test capabilities", "Large enterprise contracts"],
                "weaknesses": ["Slow turnaround (7-10 days)", "Higher pricing on routine thermal/pressure instruments", "Less flexible on emergency on-site dispatch"],
            },
            {
                "name": "Micro Calibration Systems",
                "website": "https://microcalibration.in",
                "country": "India",
                "service_focus": "Dimensional & Mechanical Metrology",
                "positioning": "Regional laboratory specializing in CNC tooling and precision dimensional gages.",
                "pricing_notes": "Mid-tier pricing, volume discounts on standard micrometers and calipers.",
                "strengths": ["Strong in Ahmedabad/Vadodara engineering corridors", "Good dimensional precision capabilities"],
                "weaknesses": ["Limited high-pressure (>400 bar) and cryo-thermal scope", "Weak on-site chemical plant readiness"],
            },
            {
                "name": "Aditi Metrology & Calibration",
                "website": "https://aditimetrology.com",
                "country": "India",
                "service_focus": "Electro-technical & Thermal Calibration",
                "positioning": "Low-cost local laboratory focusing on Surat and Ankleshwar industrial units.",
                "pricing_notes": "Aggressive discounting (15-20% below standard rates).",
                "strengths": ["Low price point", "Local proximity to South Gujarat chemical plants"],
                "weaknesses": ["Longer certificate turnaround times", "Limited master equipment redundancy", "Subcontracts advanced flow and DP scopes"],
            },
        ]

        created = 0
        for s in seeds:
            exists = db.query(CompetitorProfile).filter(CompetitorProfile.name == s["name"]).first()
            if not exists:
                comp = CompetitorProfile(
                    name=s["name"],
                    website=s["website"],
                    country=s["country"],
                    service_focus=s["service_focus"],
                    positioning=s["positioning"],
                    pricing_notes=s["pricing_notes"],
                    strengths=s["strengths"],
                    weaknesses=s["weaknesses"],
                    active=True,
                )
                db.add(comp)
                created += 1

        db.commit()
        return {
            "success": True,
            "message": f"Seeded {created} default competitors.",
            "total_competitors_added": created,
        }
    finally:
        db.close()


@router.get("")
def list_competitors(active: bool = True, limit: int = 100):
    db = SessionLocal()
    try:
        rows = db.query(CompetitorProfile).filter(CompetitorProfile.active == active).order_by(CompetitorProfile.name.asc()).limit(min(max(limit, 1), 500)).all()
        return {
            "results": [
                {
                    "id": row.id,
                    "name": row.name,
                    "website": row.website,
                    "country": row.country,
                    "service_focus": row.service_focus,
                    "positioning": row.positioning,
                    "pricing_notes": row.pricing_notes,
                    "strengths": row.strengths,
                    "weaknesses": row.weaknesses,
                    "observation_count": len(row.observations),
                }
                for row in rows
            ],
            "total": len(rows),
        }
    finally:
        db.close()


@router.post("/observations")
def create_observation(payload: ObservationCreate):
    if payload.classification not in {"WEB_EVIDENCE", "VERIFIED_FACT", "AI_INFERENCE", "USER_CORRECTED_KNOWLEDGE"}:
        raise HTTPException(400, "Unsupported classification")
    db = SessionLocal()
    try:
        if not db.query(CompetitorProfile.id).filter(CompetitorProfile.id == payload.competitor_id).first():
            raise HTTPException(404, "Competitor not found")
        if payload.company_id and not db.query(Company.id).filter(Company.id == payload.company_id).first():
            raise HTTPException(404, "Company not found")
        item = CompetitorObservation(**payload.model_dump())
        db.add(item)
        db.commit()
        db.refresh(item)
        return {"id": item.id, "status": "recorded"}
    finally:
        db.close()


@router.get("/observations")
def list_observations(competitor_id: Optional[int] = None, company_id: Optional[int] = None, limit: int = 100):
    db = SessionLocal()
    try:
        q = db.query(CompetitorObservation)
        if competitor_id:
            q = q.filter(CompetitorObservation.competitor_id == competitor_id)
        if company_id:
            q = q.filter(CompetitorObservation.company_id == company_id)
        rows = q.order_by(CompetitorObservation.observed_at.desc(), CompetitorObservation.id.desc()).limit(min(max(limit, 1), 500)).all()
        return {
            "results": [
                {
                    "id": row.id,
                    "competitor_id": row.competitor_id,
                    "company_id": row.company_id,
                    "observation_type": row.observation_type,
                    "title": row.title,
                    "evidence": row.evidence,
                    "source_url": row.source_url,
                    "source_name": row.source_name,
                    "observed_at": row.observed_at,
                    "confidence": row.confidence,
                    "classification": row.classification,
                }
                for row in rows
            ],
            "total": len(rows),
        }
    finally:
        db.close()
