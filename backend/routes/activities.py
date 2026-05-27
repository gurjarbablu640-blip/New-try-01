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


# ============================================================
# REQUEST MODEL
# ============================================================

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


# ============================================================
# ADD ACTIVITY
# ============================================================

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

        # ====================================================
        # UPDATE COMPANY CRM INFO
        # ====================================================

        company.last_contact_date = (
            datetime.utcnow()
        )

        company.lead_status = data.status

        if followup_date:

            company.next_followup_date = (
                followup_date
            )

        db.commit()

        db.refresh(activity)

        return {

            "success": True,

            "activity_id": activity.id,
        }

    except Exception as e:

        return {

            "success": False,

            "error": str(e),
        }

    finally:

        db.close()


# ============================================================
# GET ALL ACTIVITIES
# ============================================================

@router.get("/")
async def get_activities():

    db: Session = SessionLocal()

    try:

        activities = (
            db.query(CRMActivity)
            .order_by(
                CRMActivity.created_at.desc()
            )
            .all()
        )

        results = []

        for activity in activities:

            company = (
                db.query(Company)
                .filter(
                    Company.id
                    == activity.company_id
                )
                .first()
            )

            results.append({

                "id":
                    activity.id,

                "company_id":
                    activity.company_id,

                "company_name":
                    company.name if company else None,

                "activity_type":
                    activity.activity_type,

                "status":
                    activity.status,

                "remarks":
                    activity.remarks,

                "contact_person":
                    activity.contact_person,

                "division":
                    activity.division,

                "phone":
                    activity.phone,

                "email":
                    activity.email,

                "next_followup_date":
                    activity.next_followup_date,

                "created_at":
                    activity.created_at,
            })

        return {

            "success": True,

            "total": len(results),

            "results": results,
        }

    finally:

        db.close()


# ============================================================
# COMPANY ACTIVITIES
# ============================================================

@router.get("/company/{company_id}")
async def get_company_activities(
    company_id: int
):

    db: Session = SessionLocal()

    try:

        activities = (
            db.query(CRMActivity)
            .filter(
                CRMActivity.company_id
                == company_id
            )
            .order_by(
                CRMActivity.created_at.desc()
            )
            .all()
        )

        results = []

        for activity in activities:

            results.append({

                "id":
                    activity.id,

                "activity_type":
                    activity.activity_type,

                "status":
                    activity.status,

                "remarks":
                    activity.remarks,

                "contact_person":
                    activity.contact_person,

                "division":
                    activity.division,

                "phone":
                    activity.phone,

                "email":
                    activity.email,

                "next_followup_date":
                    activity.next_followup_date,

                "created_at":
                    activity.created_at,
            })

        return {

            "success": True,

            "total": len(results),

            "results": results,
        }

    finally:

        db.close()


# ============================================================
# TODAY FOLLOWUPS
# ============================================================

@router.get("/today")
async def today_followups():

    db: Session = SessionLocal()

    try:

        today = datetime.utcnow().date()

        activities = (
            db.query(CRMActivity)
            .all()
        )

        results = []

        for activity in activities:

            if not activity.next_followup_date:
                continue

            if (
                activity.next_followup_date.date()
                <= today
            ):

                company = (
                    db.query(Company)
                    .filter(
                        Company.id
                        == activity.company_id
                    )
                    .first()
                )

                results.append({

                    "id":
                        activity.id,

                    "company_name":
                        company.name
                        if company else None,

                    "contact_person":
                        activity.contact_person,

                    "phone":
                        activity.phone,

                    "status":
                        activity.status,

                    "remarks":
                        activity.remarks,

                    "next_followup_date":
                        activity.next_followup_date,
                })

        return {

            "success": True,

            "total": len(results),

            "results": results,
        }

    finally:

        db.close()


# ============================================================
# MARK FOLLOWUP COMPLETE
# ============================================================

@router.put("/complete/{activity_id}")
async def complete_activity(
    activity_id: int
):

    db: Session = SessionLocal()

    try:

        activity = (
            db.query(CRMActivity)
            .filter(
                CRMActivity.id == activity_id
            )
            .first()
        )

        if not activity:

            return {
                "success": False,
                "error": "Activity not found"
            }

        # ====================================================
        # UPDATE STATUS
        # ====================================================

        activity.status = "Completed"

        activity.next_followup_date = None

        db.commit()

        return {
            "success": True
        }

    finally:

        db.close()