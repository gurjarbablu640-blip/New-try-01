from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import SessionLocal
from models.company import Company

router = APIRouter(prefix="/api/leads", tags=["Leads"])


class LeadCreateRequest(BaseModel):
    name: str
    city: str
    industry: str
    website: str | None = None
    phone: str | None = None


@router.post("/add")
def add_lead(data: LeadCreateRequest):

    db: Session = SessionLocal()

    try:
        existing = (
            db.query(Company)
            .filter(Company.name == data.name)
            .first()
        )

        if existing:
            return {
                "success": False,
                "message": "Company already exists"
            }

        company = Company(
            name=data.name,
            city=data.city,
            industry=data.industry,
            website=data.website,
            phone=data.phone,
            icp_score=0,
            calculated_tier="Unscored"
        )

        db.add(company)
        db.commit()
        db.refresh(company)

        return {
            "success": True,
            "company_id": company.id,
            "name": company.name
        }

    finally:
        db.close()