"""
Module 11: Pipeline CRM Layer - FastAPI Routes
================================================
Endpoints:
  POST /api/pipeline/move      - Update pipeline stage
  POST /api/pipeline/activity  - Log a sales activity
  GET  /api/pipeline/board     - Kanban board data by stage
  GET  /api/pipeline/tasks     - Today's action queue (due/overdue)
  GET  /api/pipeline/stats     - Conversion rates, avg days in stage
  POST /api/pipeline/ab-result - Record A/B test result
"""
import logging
from datetime import datetime, date, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, desc
from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.models.company import Company
from backend.models.person import Person
from backend.models.pipeline import PipelineStage, Activity, ABTestResult
from backend.models.intent_signal import CompanyIntentSignal

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/pipeline", tags=["Pipeline"])

VALID_STAGES = [
    "New", "Contacted", "Replied", "Meeting Booked",
    "Proposal Sent", "Negotiation", "Won", "Lost", "Nurture",
]

VALID_ACTIVITY_TYPES = [
    "email_sent", "whatsapp_sent", "call_made", "replied",
    "meeting_booked", "no_answer", "linkedin_sent",
    "proposal_sent", "follow_up", "note_added",
]


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---- Request schemas ----

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
    activity_type: str = Field(..., alias="type", default=None)
    outcome: Optional[str] = None
    notes: Optional[str] = None
    person_id: Optional[int] = None
    pipeline_id: Optional[int] = None

    class Config:
        populate_by_name = True


class ABResultRequest(BaseModel):
    company_id: int
    subject_variant: int = Field(..., ge=1, le=5)
    opened: bool = False
    replied: bool = False


# ---- Endpoints ----

@router.post("/move")
def move_pipeline_stage(body: PipelineMoveRequest, db: Session = Depends(get_db)):
    if body.stage not in VALID_STAGES:
        raise HTTPException(400, f"Invalid stage. Must be one of: {VALID_STAGES}")

    company = db.query(Company).filter(Company.id == body.company_id).first()
    if not company:
        raise HTTPException(404, "Company not found")

    pipeline = (
        db.query(PipelineStage)
        .filter(PipelineStage.company_id == body.company_id)
        .order_by(desc(PipelineStage.created_at))
        .first()
    )

    if pipeline:
        old_stage = pipeline.stage
        pipeline.stage = body.stage
        pipeline.last_touched = datetime.utcnow()
        if body.notes is not None:
            pipeline.notes = body.notes
        if body.person_id:
            pipeline.person_id = body.person_id
        if body.deal_value_est:
            pipeline.deal_value_est = body.deal_value_est
        if body.loss_reason:
            pipeline.loss_reason = body.loss_reason
        if body.contact_channel:
            pipeline.contact_channel = body.contact_channel
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

    if body.stage == "Won":
        logger.info(f"Deal won for company {body.company_id} — triggering lookalike analysis")

    return {
        "success": True,
        "pipeline_id": pipeline.id,
        "old_stage": old_stage,
        "new_stage": body.stage,
        "company_name": company.name,
        "days_in_stage": pipeline.days_in_stage,
    }


@router.post("/activity", status_code=201)
def log_activity(body: ActivityRequest, db: Session = Depends(get_db)):
    activity_type = body.activity_type
    if activity_type not in VALID_ACTIVITY_TYPES:
        raise HTTPException(400, f"Invalid activity_type. Must be one of: {VALID_ACTIVITY_TYPES}")

    pipeline_id = body.pipeline_id
    if not pipeline_id:
        pipeline = (
            db.query(PipelineStage)
            .filter(PipelineStage.company_id == body.company_id)
            .order_by(desc(PipelineStage.created_at))
            .first()
        )
        if pipeline:
            pipeline_id = pipeline.id
            pipeline.last_touched = datetime.utcnow()

    activity = Activity(
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
        "activity_type": activity.activity_type,
        "company_id": body.company_id,
    }


@router.get("/board")
def get_pipeline_board(db: Session = Depends(get_db)):
    pipelines = (
        db.query(PipelineStage, Company)
        .join(Company, PipelineStage.company_id == Company.id)
        .filter(PipelineStage.stage.notin_(["Lost"]))
        .order_by(desc(Company.icp_score))
        .all()
    )

    board = {stage: [] for stage in VALID_STAGES}

    for pipeline, company in pipelines:
        top_signal = (
            db.query(CompanyIntentSignal)
            .filter(CompanyIntentSignal.company_id == company.id, CompanyIntentSignal.is_active == 1)
            .order_by(desc(CompanyIntentSignal.weight_applied))
            .first()
        )

        card = {
            "pipeline_id": pipeline.id,
            "company_id": company.id,
            "company_name": company.name,
            "city": company.city,
            "state": company.state,
            "tier": company.calculated_tier,
            "icp_score": company.icp_score,
            "days_in_stage": pipeline.days_in_stage,
            "stage": pipeline.stage,
            "next_action": pipeline.next_action,
            "next_action_date": pipeline.next_action_date.isoformat() if pipeline.next_action_date else None,
            "deal_value_est": float(pipeline.deal_value_est) if pipeline.deal_value_est else None,
            "contact_channel": pipeline.contact_channel,
            "is_overdue": (
                pipeline.next_action_date is not None and pipeline.next_action_date < date.today()
            ),
            "top_signal": top_signal.signal_type if top_signal else None,
            "top_signal_reason": top_signal.urgency_reason if top_signal else None,
            "last_touched": pipeline.last_touched.isoformat() if pipeline.last_touched else None,
        }
        board[pipeline.stage].append(card)

    stage_counts = {stage: len(cards) for stage, cards in board.items()}
    return {"board": board, "stage_counts": stage_counts, "total_active": sum(stage_counts.values())}


@router.get("/tasks")
def get_todays_tasks(db: Session = Depends(get_db)):
    today = date.today()
    tasks = (
        db.query(PipelineStage, Company)
        .join(Company, PipelineStage.company_id == Company.id)
        .filter(PipelineStage.next_action_date <= today, PipelineStage.stage.notin_(["Won", "Lost"]))
        .all()
    )

    task_list = []
    for pipeline, company in tasks:
        person = db.query(Person).filter(Person.id == pipeline.person_id).first() if pipeline.person_id else None
        top_signal = (
            db.query(CompanyIntentSignal)
            .filter(CompanyIntentSignal.company_id == company.id, CompanyIntentSignal.is_active == 1)
            .order_by(desc(CompanyIntentSignal.weight_applied))
            .first()
        )

        priority = company.icp_score or 0
        if top_signal:
            if top_signal.signal_type == "NABL_RENEWAL_DUE":
                priority += 100
            elif top_signal.signal_type == "ISO_AUDIT_WINDOW":
                priority += 75
            else:
                priority += 50

        task_list.append({
            "pipeline_id": pipeline.id,
            "company_id": company.id,
            "company_name": company.name,
            "city": company.city,
            "tier": company.calculated_tier,
            "icp_score": company.icp_score,
            "stage": pipeline.stage,
            "next_action": pipeline.next_action,
            "next_action_date": pipeline.next_action_date.isoformat(),
            "is_overdue": pipeline.next_action_date < today,
            "days_overdue": (today - pipeline.next_action_date).days,
            "contact_channel": pipeline.contact_channel,
            "person_name": person.full_name if person else None,
            "person_designation": person.designation if person else None,
            "top_signal": top_signal.signal_type if top_signal else None,
            "urgency_reason": top_signal.urgency_reason if top_signal else None,
            "priority_score": priority,
        })

    task_list.sort(key=lambda x: (-int(x["is_overdue"]), -x["priority_score"]))

    return {
        "tasks": task_list,
        "total_tasks": len(task_list),
        "overdue_count": sum(1 for t in task_list if t["is_overdue"]),
        "today_count": sum(1 for t in task_list if not t["is_overdue"]),
    }


@router.get("/stats")
def get_pipeline_stats(db: Session = Depends(get_db)):
    stage_counts = db.query(PipelineStage.stage, func.count(PipelineStage.id)).group_by(PipelineStage.stage).all()
    total_entries = db.query(func.count(PipelineStage.id)).scalar() or 0
    total_won = db.query(func.count(PipelineStage.id)).filter(PipelineStage.stage == "Won").scalar() or 0
    total_lost = db.query(func.count(PipelineStage.id)).filter(PipelineStage.stage == "Lost").scalar() or 0

    closed_deals = total_won + total_lost
    win_rate = (total_won / closed_deals * 100) if closed_deals > 0 else 0
    avg_deal_value = (
        db.query(func.avg(PipelineStage.deal_value_est))
        .filter(PipelineStage.stage == "Won", PipelineStage.deal_value_est.isnot(None))
        .scalar()
        or 0
    )

    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    activity_counts = (
        db.query(Activity.activity_type, func.count(Activity.id))
        .filter(Activity.occurred_at >= thirty_days_ago)
        .group_by(Activity.activity_type)
        .all()
    )

    return {
        "stage_counts": {stage: count for stage, count in stage_counts},
        "total_in_pipeline": total_entries,
        "total_won": total_won,
        "total_lost": total_lost,
        "win_rate_percent": round(win_rate, 1),
        "avg_deal_value": float(avg_deal_value),
        "activity_counts_30d": {atype: count for atype, count in activity_counts},
        "total_activities_30d": sum(count for _, count in activity_counts),
    }


@router.post("/ab-result", status_code=201)
def record_ab_result(body: ABResultRequest, db: Session = Depends(get_db)):
    result = ABTestResult(
        company_id=body.company_id,
        subject_variant=body.subject_variant,
        opened=body.opened,
        replied=body.replied,
    )
    db.add(result)
    db.commit()
    db.refresh(result)
    return {"success": True, "ab_test_id": result.id}
