from datetime import datetime

from fastapi import APIRouter

from pydantic import BaseModel

from sqlalchemy.orm import Session

from database import SessionLocal

from models.activity import CRMActivity

from models.company import Company


router = APIRouter(
    prefix="/api/activities",
    tags=["Activities"]
)


class ActivityCreateRequest(BaseModel):

    company_id: int

    activity_type: str

    status: str

    remarks: str | None = None

    contact_person: str | None = None

    division: str | None = None

    phone: str | None = None

    email: str | None = None

    next_followup_date: str | None = None


@router.post("/add")
async def add_activity(
    data: ActivityCreateRequest
):

    db: Session = SessionLocal()

    try:

        company = (
            db.query(Company)
            .filter(
                Company.id == data.company_id
            )
            .first()
        )

        if not company:

            return {
                "success": False,
                "error": "Company not found"
            }

        followup_date = None

        if data.next_followup_date:

            followup_date = datetime.fromisoformat(
                data.next_followup_date
            )

        activity = CRMActivity(

            company_id=data.company_id,

            activity_type=data.activity_type,

            status=data.status,

            remarks=data.remarks,

            contact_person=data.contact_person,

            division=data.division,

            phone=data.phone,

            email=data.email,

            next_followup_date=followup_date,
        )

        db.add(activity)

        company.last_contact_date = datetime.utcnow()

        if followup_date:

            company.next_followup_date = (
                followup_date
            )

        company.lead_status = data.status

        db.commit()

        db.refresh(activity)

        return {

            "success": True,

            "activity_id": activity.id,
        }

    except Exception as e:

        return {
            "success": False,
            "error": str(e)
        }

    finally:

        db.close()