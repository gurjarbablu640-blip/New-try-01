"""
Module 11: Pipeline CRM Layer - FastAPI Routes
"""

import logging

from datetime import (
    datetime,
    date,
    timedelta,
)

from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)

from pydantic import (
    BaseModel,
    Field,
)

from sqlalchemy import (
    func,
    desc,
)

from sqlalchemy.orm import Session

from database import SessionLocal

from models.company import Company

from models.person import Person

from models.pipeline import (
    PipelineStage,
    PipelineActivity,
    ABTestResult,
)

from models.intent_signal import (
    CompanyIntentSignal
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/pipeline",
    tags=["Pipeline"]
)


# ============================================================
# VALID STAGES
# ============================================================

VALID_STAGES = [

    "New",

    "Contacted",

    "Replied",

    "Meeting Booked",

    "Proposal Sent",

    "Negotiation",

    "Won",

    "Lost",

    "Nurture",
]


VALID_ACTIVITY_TYPES = [

    "email_sent",

    "whatsapp_sent",

    "call_made",

    "replied",

    "meeting_booked",

    "no_answer",

    "linkedin_sent",

    "proposal_sent",

    "follow_up",

    "note_added",
]


# ============================================================
# DATABASE
# ============================================================

def get_db():

    db = SessionLocal()

    try:

        yield db

    finally:

        db.close()


# ============================================================
# REQUEST SCHEMAS
# ============================================================

class PipelineMoveRequest(BaseModel):

    company_id: int

    stage: str

    notes: Optional[str] = None

    person_id: Optional[int] = None

    deal_value_est: Optional[float] = None

    loss_reason: Optional[str] = None

    contact_channel: Optional[str] = None


class ActivityRequest(BaseModel):

    company_id: int

    activity_type: str | None = Field(
        None,
        alias="type"
    )

    outcome: Optional[str] = None

    notes: Optional[str] = None

    person_id: Optional[int] = None

    pipeline_id: Optional[int] = None

    class Config:

        populate_by_name = True


class ABResultRequest(BaseModel):

    company_id: int

    subject_variant: int = Field(
        ...,
        ge=1,
        le=5
    )

    opened: bool = False

    replied: bool = False


# ============================================================
# MOVE PIPELINE STAGE
# ============================================================

@router.post("/move")
def move_pipeline_stage(
    body: PipelineMoveRequest,
    db: Session = Depends(get_db)
):

    if body.stage not in VALID_STAGES:

        raise HTTPException(
            400,
            f"Invalid stage"
        )

    company = (
        db.query(Company)
        .filter(
            Company.id == body.company_id
        )
        .first()
    )

    if not company:

        raise HTTPException(
            404,
            "Company not found"
        )

    pipeline = (
        db.query(PipelineStage)
        .filter(
            PipelineStage.company_id
            == body.company_id
        )
        .order_by(
            desc(PipelineStage.created_at)
        )
        .first()
    )

    if pipeline:

        old_stage = pipeline.stage

        pipeline.stage = body.stage

        pipeline.last_touched = (
            datetime.utcnow()
        )

        if body.notes is not None:

            pipeline.notes = body.notes

        if body.person_id:

            pipeline.person_id = (
                body.person_id
            )

        if body.deal_value_est:

            pipeline.deal_value_est = (
                body.deal_value_est
            )

        if body.loss_reason:

            pipeline.loss_reason = (
                body.loss_reason
            )

        if body.contact_channel:

            pipeline.contact_channel = (
                body.contact_channel
            )

    else:

        old_stage = None

        pipeline = PipelineStage(

            company_id=body.company_id,

            person_id=body.person_id,

            stage=body.stage,

            notes=body.notes,

            deal_value_est=body.deal_value_est,

            contact_channel=body.contact_channel,

            last_touched=datetime.utcnow(),
        )

        db.add(pipeline)

    db.commit()

    db.refresh(pipeline)

    return {

        "success": True,

        "pipeline_id": pipeline.id,

        "old_stage": old_stage,

        "new_stage": body.stage,

        "company_name": company.name,
    }


# ============================================================
# LOG ACTIVITY
# ============================================================

@router.post("/activity")
def log_activity(
    body: ActivityRequest,
    db: Session = Depends(get_db)
):

    activity_type = body.activity_type

    if activity_type not in VALID_ACTIVITY_TYPES:

        raise HTTPException(
            400,
            "Invalid activity_type"
        )

    pipeline_id = body.pipeline_id

    if not pipeline_id:

        pipeline = (
            db.query(PipelineStage)
            .filter(
                PipelineStage.company_id
                == body.company_id
            )
            .order_by(
                desc(PipelineStage.created_at)
            )
            .first()
        )

        if pipeline:

            pipeline_id = pipeline.id

            pipeline.last_touched = (
                datetime.utcnow()
            )

    activity = PipelineActivity(

        company_id=body.company_id,

        person_id=body.person_id,

        pipeline_id=pipeline_id,

        activity_type=activity_type,

        outcome=body.outcome,

        notes=body.notes,

        occurred_at=datetime.utcnow(),
    )

    db.add(activity)

    db.commit()

    db.refresh(activity)

    return {

        "success": True,

        "activity_id": activity.id,
    }


# ============================================================
# PIPELINE BOARD
# ============================================================

@router.get("/board")
def get_pipeline_board(
    db: Session = Depends(get_db)
):

    pipelines = (

        db.query(
            PipelineStage,
            Company
        )

        .join(
            Company,
            PipelineStage.company_id
            == Company.id
        )

        .all()
    )

    results = []

    for pipeline, company in pipelines:

        results.append({

            "pipeline_id":
                pipeline.id,

            "company_id":
                company.id,

            "company_name":
                company.name,

            "stage":
                pipeline.stage,

            "icp_score":
                company.icp_score,

            "city":
                company.city,

            "state":
                company.state,

            "last_touched":
                pipeline.last_touched,
        })

    return {

        "success": True,

        "total": len(results),

        "results": results,
    }


# ============================================================
# TODAY TASKS
# ============================================================

@router.get("/tasks")
def get_todays_tasks(
    db: Session = Depends(get_db)
):

    today = date.today()

    tasks = (

        db.query(
            PipelineStage,
            Company
        )

        .join(
            Company,
            PipelineStage.company_id
            == Company.id
        )

        .filter(
            PipelineStage.next_action_date
            <= today
        )

        .all()
    )

    results = []

    for pipeline, company in tasks:

        results.append({

            "company_name":
                company.name,

            "stage":
                pipeline.stage,

            "next_action":
                pipeline.next_action,

            "next_action_date":
                pipeline.next_action_date,
        })

    return {

        "success": True,

        "total": len(results),

        "results": results,
    }


# ============================================================
# STATS
# ============================================================

@router.get("/stats")
def get_pipeline_stats(
    db: Session = Depends(get_db)
):

    total_pipeline = (
        db.query(
            func.count(PipelineStage.id)
        )
        .scalar()
    )

    total_won = (
        db.query(
            func.count(PipelineStage.id)
        )
        .filter(
            PipelineStage.stage == "Won"
        )
        .scalar()
    )

    total_lost = (
        db.query(
            func.count(PipelineStage.id)
        )
        .filter(
            PipelineStage.stage == "Lost"
        )
        .scalar()
    )

    activity_count = (
        db.query(
            func.count(PipelineActivity.id)
        )
        .scalar()
    )

    return {

        "success": True,

        "total_pipeline":
            total_pipeline,

        "total_won":
            total_won,

        "total_lost":
            total_lost,

        "activity_count":
            activity_count,
    }


# ============================================================
# AB TEST RESULT
# ============================================================

@router.post("/ab-result")
def record_ab_result(
    body: ABResultRequest,
    db: Session = Depends(get_db)
):

    result = ABTestResult(

        company_id=body.company_id,

        subject_variant=body.subject_variant,

        opened=body.opened,

        replied=body.replied,
    )

    db.add(result)

    db.commit()

    db.refresh(result)

    return {

        "success": True,

        "ab_test_id": result.id,
    }