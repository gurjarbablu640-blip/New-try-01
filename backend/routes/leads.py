import pandas as pd

from fastapi import (
    APIRouter,
    UploadFile,
    File,
)

from pydantic import BaseModel

from sqlalchemy.orm import Session

from database import SessionLocal

from models.company import Company


router = APIRouter(
    prefix="/api/leads",
    tags=["Leads"]
)


# ============================================================
# REQUEST MODEL
# ============================================================

class LeadCreateRequest(BaseModel):

    name: str

    city: str

    industry: str

    website: str | None = None

    phone: str | None = None

    email: str | None = None

    linkedin: str | None = None

    contact_person: str | None = None

    division: str | None = None

    remarks: str | None = None


# ============================================================
# ADD LEAD
# ============================================================

@router.post("/add")
def add_lead(data: LeadCreateRequest):

    db: Session = SessionLocal()

    try:

        existing = (
            db.query(Company)
            .filter(
                Company.name == data.name
            )
            .first()
        )

        if existing:

            return {
                "success": False,
                "message":
                    "Company already exists"
            }

        company = Company(

            name=data.name,

            city=data.city,

            industry=data.industry,

            website=data.website,

            phone=data.phone,

            email=data.email,

            linkedin=data.linkedin,

            contact_person=data.contact_person,

            division=data.division,

            remarks=data.remarks,

            lead_status="New",

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


# ============================================================
# CSV / XLSX UPLOAD
# ============================================================

@router.post("/upload")
async def upload_leads(
    file: UploadFile = File(...)
):

    db: Session = SessionLocal()

    inserted = 0

    skipped = 0

    try:

        filename = file.filename.lower()

        # ====================================================
        # READ FILE
        # ====================================================

        if filename.endswith(".csv"):

            df = pd.read_csv(file.file)

        elif filename.endswith(".xlsx"):

            df = pd.read_excel(file.file)

        else:

            return {

                "success": False,

                "error":
                    "Only CSV/XLSX supported"
            }

        # ====================================================
        # PROCESS ROWS
        # ====================================================

        for _, row in df.iterrows():

            company_name = str(
                row.get(
                    "Company Name",
                    ""
                )
            ).strip()

            if not company_name:
                continue

            existing = (
                db.query(Company)
                .filter(
                    Company.name == company_name
                )
                .first()
            )

            if existing:

                skipped += 1

                continue

            company = Company(

                name=company_name,

                city=str(
                    row.get(
                        "Location",
                        ""
                    )
                ),

                contact_person=str(
                    row.get(
                        "Contact Person",
                        ""
                    )
                ),

                division=str(
                    row.get(
                        "Division",
                        ""
                    )
                ),

                phone=str(
                    row.get(
                        "Phone",
                        ""
                    )
                ),

                email=str(
                    row.get(
                        "Email",
                        ""
                    )
                ),

                website=str(
                    row.get(
                        "Website",
                        ""
                    )
                ),

                remarks=str(
                    row.get(
                        "Remarks",
                        ""
                    )
                ),

                industry="Uploaded Lead",

                lead_status="New",

                icp_score=50,

                calculated_tier="Warm",
            )

            db.add(company)

            inserted += 1

        db.commit()

        return {

            "success": True,

            "inserted": inserted,

            "skipped": skipped,
        }

    except Exception as e:

        return {

            "success": False,

            "error": str(e)
        }

    finally:

        db.close()


# ============================================================
# GET ALL LEADS
# ============================================================

@router.get("/")
async def get_leads():

    db: Session = SessionLocal()

    try:

        companies = (
            db.query(Company)
            .order_by(
                Company.created_at.desc()
            )
            .all()
        )

        results = []

        for company in companies:

            results.append({

                "id": company.id,

                "name": company.name,

                "industry": company.industry,

                "city": company.city,

                "state": company.state,

                "website": company.website,

                "email": company.email,

                "phone": company.phone,

                "linkedin": company.linkedin,

                "contact_person":
                    company.contact_person,

                "division":
                    company.division,

                "remarks":
                    company.remarks,

                "lead_status":
                    company.lead_status,

                "last_contact_date":
                    company.last_contact_date,

                "next_followup_date":
                    company.next_followup_date,

                "contact_page":
                    company.contact_page,

                "address":
                    company.address,

                "icp_score":
                    company.icp_score,

                "tier":
                    company.calculated_tier,

                "order_received":
                    company.order_received,

                "order_value":
                    float(company.order_value)
                    if company.order_value
                    else 0,

                "billing_status":
                    company.billing_status,

                "payment_status":
                    company.payment_status,

                "created_at":
                    company.created_at,
            })

        return {

            "success": True,

            "total": len(results),

            "results": results,
        }

    finally:

        db.close()


# ============================================================
# GET SINGLE LEAD
# ============================================================

@router.get("/{company_id}")
async def get_lead(company_id: int):

    db: Session = SessionLocal()

    try:

        company = (
            db.query(Company)
            .filter(
                Company.id == company_id
            )
            .first()
        )

        if not company:

            return {

                "success": False,

                "error":
                    "Lead not found"
            }

        return {

            "success": True,

            "result": {

                "id": company.id,

                "name": company.name,

                "industry": company.industry,

                "city": company.city,

                "state": company.state,

                "website": company.website,

                "email": company.email,

                "phone": company.phone,

                "linkedin": company.linkedin,

                "contact_person":
                    company.contact_person,

                "division":
                    company.division,

                "remarks":
                    company.remarks,

                "lead_status":
                    company.lead_status,

                "last_contact_date":
                    company.last_contact_date,

                "next_followup_date":
                    company.next_followup_date,

                "contact_page":
                    company.contact_page,

                "address":
                    company.address,

                "icp_score":
                    company.icp_score,

                "tier":
                    company.calculated_tier,

                "order_received":
                    company.order_received,

                "po_number":
                    company.po_number,

                "order_value":
                    float(company.order_value)
                    if company.order_value
                    else 0,

                "billing_status":
                    company.billing_status,

                "payment_status":
                    company.payment_status,

                "created_at":
                    company.created_at,
            }
        }

    finally:

        db.close()