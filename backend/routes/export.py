import io

import pandas as pd

from fastapi import APIRouter

from fastapi.responses import StreamingResponse

from sqlalchemy.orm import Session

from database import SessionLocal

from models.activity import CRMActivity

from models.company import Company


router = APIRouter(
    prefix="/api/export",
    tags=["Export"]
)


# ============================================================
# EXPORT ACTIVITIES
# ============================================================

@router.get("/activities")
async def export_activities():

    db: Session = SessionLocal()

    try:

        activities = (
            db.query(CRMActivity)
            .order_by(
                CRMActivity.created_at.desc()
            )
            .all()
        )

        rows = []

        for activity in activities:

            company = (
                db.query(Company)
                .filter(
                    Company.id
                    == activity.company_id
                )
                .first()
            )

            rows.append({

                "Company":
                    company.name
                    if company else "",

                "Activity":
                    activity.activity_type,

                "Status":
                    activity.status,

                "Contact Person":
                    activity.contact_person,

                "Division":
                    activity.division,

                "Phone":
                    activity.phone,

                "Email":
                    activity.email,

                "Remarks":
                    activity.remarks,

                "Followup Date":
                    activity.next_followup_date,

                "Created":
                    activity.created_at,
            })

        df = pd.DataFrame(rows)

        output = io.BytesIO()

        with pd.ExcelWriter(
            output,
            engine="openpyxl"
        ) as writer:

            df.to_excel(
                writer,
                index=False,
                sheet_name="Activities"
            )

        output.seek(0)

        return StreamingResponse(

            output,

            media_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),

            headers={

                "Content-Disposition":
                    "attachment; filename=crm_activities.xlsx"
            }
        )

    finally:

        db.close()