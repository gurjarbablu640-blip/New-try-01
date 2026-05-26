from fastapi import APIRouter
from sqlalchemy.orm import Session

from database import SessionLocal

from models.company import Company

from services.outreachGenerator import (
    generate_outreach
)

router = APIRouter(
    prefix="/api/outreach",
    tags=["Outreach"]
)


@router.get("/{company_id}")

async def outreach(company_id: int):

    db: Session = SessionLocal()

    try:

        company = (
            db.query(Company)
            .filter(Company.id == company_id)
            .first()
        )

        if not company:

            return {
                "success": False,
                "error": "Company not found"
            }

        outreach_text = generate_outreach(
            company
        )

        return {
            "success": True,
            "company": company.name,
            "outreach": outreach_text,
        }

    finally:

        db.close()