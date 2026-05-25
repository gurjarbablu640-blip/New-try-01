"""
Module 11: Pipeline CRM Layer - API Routes
============================================
Full CRM pipeline with Kanban board, activity logging,
stage management, and task tracking.

Endpoints:
  POST /api/pipeline/move      - Update pipeline stage
  POST /api/pipeline/activity  - Log a sales activity
  GET  /api/pipeline/board     - Kanban board data by stage
  GET  /api/pipeline/tasks     - Today's action queue (due/overdue)
  GET  /api/pipeline/stats     - Conversion rates, avg days in stage
  POST /api/pipeline/ab-result - Record A/B test result
"""
import logging
from datetime import datetime, date
from typing import Optional

from flask import Blueprint, request, jsonify
from sqlalchemy import func, case, desc
from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.models.company import Company
from backend.models.person import Person
from backend.models.pipeline import PipelineStage, Activity, ABTestResult
from backend.models.intent_signal import CompanyIntentSignal

logger = logging.getLogger(__name__)

pipeline_bp = Blueprint("pipeline", __name__, url_prefix="/api/pipeline")

# Valid pipeline stages
VALID_STAGES = [
    "New", "Contacted", "Replied", "Meeting Booked",
    "Proposal Sent", "Negotiation", "Won", "Lost", "Nurture"
]

VALID_ACTIVITY_TYPES = [
    "email_sent", "whatsapp_sent", "call_made", "replied",
    "meeting_booked", "no_answer", "linkedin_sent",
    "proposal_sent", "follow_up", "note_added"
]


def get_db():
    db = SessionLocal()
    try:
        return db
    except Exception:
        db.close()
        raise


# ============================================================
# POST /api/pipeline/move - Update pipeline stage
# ============================================================

@pipeline_bp.route("/move", methods=["POST"])
def move_pipeline_stage():
    """
    Move a company to a new pipeline stage.
    Creates pipeline entry if not exists.

    Body: {
        company_id: int,
        stage: str,
        notes: str (optional),
        person_id: int (optional),
        deal_value_est: float (optional),
        loss_reason: str (optional - required for 'Lost' stage),
        contact_channel: str (optional)
    }
    """
    db = get_db()
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Request body required"}), 400

        company_id = data.get("company_id")
        stage = data.get("stage")

        if not company_id:
            return jsonify({"error": "company_id required"}), 400
        if not stage or stage not in VALID_STAGES:
            return jsonify({"error": f"Invalid stage. Must be one of: {VALID_STAGES}"}), 400

        # Check company exists
        company = db.query(Company).filter(Company.id == company_id).first()
        if not company:
            return jsonify({"error": "Company not found"}), 404

        # Get or create pipeline entry
        pipeline = db.query(PipelineStage).filter(
            PipelineStage.company_id == company_id
        ).order_by(desc(PipelineStage.created_at)).first()

        if pipeline:
            old_stage = pipeline.stage
            pipeline.stage = stage
            pipeline.last_touched = datetime.utcnow()
            pipeline.notes = data.get("notes", pipeline.notes)
            if data.get("person_id"):
                pipeline.person_id = data["person_id"]
            if data.get("deal_value_est"):
                pipeline.deal_value_est = data["deal_value_est"]
            if data.get("loss_reason"):
                pipeline.loss_reason = data["loss_reason"]
            if data.get("contact_channel"):
                pipeline.contact_channel = data["contact_channel"]
        else:
            old_stage = None
            pipeline = PipelineStage(
                company_id=company_id,
                person_id=data.get("person_id"),
                stage=stage,
                notes=data.get("notes"),
                deal_value_est=data.get("deal_value_est"),
                contact_channel=data.get("contact_channel"),
                last_touched=datetime.utcnow(),
            )
            db.add(pipeline)

        db.commit()
        db.refresh(pipeline)

        # If moved to 'Won', trigger lookalike engine
        if stage == "Won":
            _handle_won_deal(company_id, db)

        return jsonify({
            "success": True,
            "pipeline_id": pipeline.id,
            "old_stage": old_stage,
            "new_stage": stage,
            "company_name": company.name,
            "days_in_stage": pipeline.days_in_stage,
        }), 200

    except Exception as e:
        logger.error(f"Pipeline move error: {e}")
        db.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


def _handle_won_deal(company_id: int, db: Session):
    """Handle actions when a deal is marked as Won."""
    from backend.models.pipeline import PipelineStage
    # This triggers the lookalike engine to find similar companies
    # Implemented in Module 14
    logger.info(f"Deal won for company {company_id} — triggering lookalike analysis")


# ============================================================
# POST /api/pipeline/activity - Log a sales activity
# ============================================================

@pipeline_bp.route("/activity", methods=["POST"])
def log_activity():
    """
    Log a sales activity (email, call, WhatsApp, etc.)

    Body: {
        company_id: int,
        activity_type: str,
        outcome: str (optional),
        notes: str (optional),
        person_id: int (optional),
        pipeline_id: int (optional)
    }
    """
    db = get_db()
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Request body required"}), 400

        company_id = data.get("company_id")
        activity_type = data.get("activity_type") or data.get("type")

        if not company_id:
            return jsonify({"error": "company_id required"}), 400
        if not activity_type or activity_type not in VALID_ACTIVITY_TYPES:
            return jsonify({"error": f"Invalid activity_type. Must be one of: {VALID_ACTIVITY_TYPES}"}), 400

        # Get pipeline_id if not provided
        pipeline_id = data.get("pipeline_id")
        if not pipeline_id:
            pipeline = db.query(PipelineStage).filter(
                PipelineStage.company_id == company_id
            ).order_by(desc(PipelineStage.created_at)).first()
            if pipeline:
                pipeline_id = pipeline.id
                # Update last_touched
                pipeline.last_touched = datetime.utcnow()

        activity = Activity(
            company_id=company_id,
            person_id=data.get("person_id"),
            pipeline_id=pipeline_id,
            activity_type=activity_type,
            outcome=data.get("outcome"),
            notes=data.get("notes"),
            occurred_at=datetime.utcnow(),
        )
        db.add(activity)
        db.commit()
        db.refresh(activity)

        return jsonify({
            "success": True,
            "activity_id": activity.id,
            "activity_type": activity.activity_type,
            "company_id": company_id,
        }), 201

    except Exception as e:
        logger.error(f"Activity log error: {e}")
        db.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


# ============================================================
# GET /api/pipeline/board - Kanban board data
# ============================================================

@pipeline_bp.route("/board", methods=["GET"])
def get_pipeline_board():
    """
    Get pipeline data organized by stage for Kanban board display.
    Returns companies grouped by stage with key metrics.
    """
    db = get_db()
    try:
        # Get all active pipeline entries with company data
        pipelines = db.query(PipelineStage, Company).join(
            Company, PipelineStage.company_id == Company.id
        ).filter(
            PipelineStage.stage.notin_(["Lost"])  # Exclude lost by default
        ).order_by(desc(Company.icp_score)).all()

        # Group by stage
        board = {stage: [] for stage in VALID_STAGES}

        for pipeline, company in pipelines:
            # Get top signal for this company
            top_signal = db.query(CompanyIntentSignal).filter(
                CompanyIntentSignal.company_id == company.id,
                CompanyIntentSignal.is_active == 1,
            ).order_by(desc(CompanyIntentSignal.weight_applied)).first()

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
                    pipeline.next_action_date is not None and
                    pipeline.next_action_date < date.today()
                ),
                "top_signal": top_signal.signal_type if top_signal else None,
                "top_signal_reason": top_signal.urgency_reason if top_signal else None,
                "last_touched": pipeline.last_touched.isoformat() if pipeline.last_touched else None,
            }
            board[pipeline.stage].append(card)

        # Include counts
        stage_counts = {stage: len(cards) for stage, cards in board.items()}

        return jsonify({
            "board": board,
            "stage_counts": stage_counts,
            "total_active": sum(stage_counts.values()),
        }), 200

    except Exception as e:
        logger.error(f"Pipeline board error: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


# ============================================================
# GET /api/pipeline/tasks - Today's action queue
# ============================================================

@pipeline_bp.route("/tasks", methods=["GET"])
def get_todays_tasks():
    """
    Get all tasks due today or overdue, sorted by priority.
    Priority: NABL_RENEWAL_DUE first, then by ICP score.
    """
    db = get_db()
    try:
        today = date.today()

        # Get pipelines with actions due today or overdue
        tasks = db.query(PipelineStage, Company).join(
            Company, PipelineStage.company_id == Company.id
        ).filter(
            PipelineStage.next_action_date <= today,
            PipelineStage.stage.notin_(["Won", "Lost"]),
        ).all()

        task_list = []
        for pipeline, company in tasks:
            # Get person
            person = None
            if pipeline.person_id:
                person = db.query(Person).filter(Person.id == pipeline.person_id).first()

            # Get top signal
            top_signal = db.query(CompanyIntentSignal).filter(
                CompanyIntentSignal.company_id == company.id,
                CompanyIntentSignal.is_active == 1,
            ).order_by(desc(CompanyIntentSignal.weight_applied)).first()

            # Priority score (higher = more urgent)
            priority = company.icp_score or 0
            if top_signal:
                if top_signal.signal_type == "NABL_RENEWAL_DUE":
                    priority += 100  # Highest priority
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

        # Sort: overdue first, then by priority score
        task_list.sort(key=lambda x: (-int(x["is_overdue"]), -x["priority_score"]))

        return jsonify({
            "tasks": task_list,
            "total_tasks": len(task_list),
            "overdue_count": sum(1 for t in task_list if t["is_overdue"]),
            "today_count": sum(1 for t in task_list if not t["is_overdue"]),
        }), 200

    except Exception as e:
        logger.error(f"Tasks fetch error: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


# ============================================================
# GET /api/pipeline/stats - Pipeline statistics
# ============================================================

@pipeline_bp.route("/stats", methods=["GET"])
def get_pipeline_stats():
    """
    Get pipeline statistics: conversion rates, avg days in stage,
    activity counts, and velocity metrics.
    """
    db = get_db()
    try:
        # Stage counts
        stage_counts = db.query(
            PipelineStage.stage,
            func.count(PipelineStage.id)
        ).group_by(PipelineStage.stage).all()

        # Total won vs total entered
        total_entries = db.query(func.count(PipelineStage.id)).scalar() or 0
        total_won = db.query(func.count(PipelineStage.id)).filter(
            PipelineStage.stage == "Won"
        ).scalar() or 0
        total_lost = db.query(func.count(PipelineStage.id)).filter(
            PipelineStage.stage == "Lost"
        ).scalar() or 0

        # Win rate
        closed_deals = total_won + total_lost
        win_rate = (total_won / closed_deals * 100) if closed_deals > 0 else 0

        # Average deal value (won deals)
        avg_deal_value = db.query(func.avg(PipelineStage.deal_value_est)).filter(
            PipelineStage.stage == "Won",
            PipelineStage.deal_value_est.isnot(None)
        ).scalar() or 0

        # Activity counts (last 30 days)
        thirty_days_ago = datetime.utcnow() - __import__("datetime").timedelta(days=30)
        activity_counts = db.query(
            Activity.activity_type,
            func.count(Activity.id)
        ).filter(
            Activity.occurred_at >= thirty_days_ago
        ).group_by(Activity.activity_type).all()

        # Average days in each stage
        # (simplified - uses last_touched vs created_at)

        return jsonify({
            "stage_counts": {stage: count for stage, count in stage_counts},
            "total_in_pipeline": total_entries,
            "total_won": total_won,
            "total_lost": total_lost,
            "win_rate_percent": round(win_rate, 1),
            "avg_deal_value": float(avg_deal_value),
            "activity_counts_30d": {atype: count for atype, count in activity_counts},
            "total_activities_30d": sum(count for _, count in activity_counts),
        }), 200

    except Exception as e:
        logger.error(f"Pipeline stats error: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


# ============================================================
# POST /api/pipeline/ab-result - Record A/B test result
# ============================================================

@pipeline_bp.route("/ab-result", methods=["POST"])
def record_ab_result():
    """
    Record an A/B test result for subject line testing.

    Body: {
        company_id: int,
        subject_variant: int (1-5),
        opened: bool,
        replied: bool
    }
    """
    db = get_db()
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Request body required"}), 400

        company_id = data.get("company_id")
        variant = data.get("subject_variant") or data.get("variant")

        if not company_id:
            return jsonify({"error": "company_id required"}), 400
        if not variant or variant not in range(1, 6):
            return jsonify({"error": "subject_variant must be 1-5"}), 400

        result = ABTestResult(
            company_id=company_id,
            subject_variant=variant,
            opened=data.get("opened", False),
            replied=data.get("replied", False),
        )
        db.add(result)
        db.commit()
        db.refresh(result)

        return jsonify({
            "success": True,
            "ab_test_id": result.id,
        }), 201

    except Exception as e:
        logger.error(f"A/B result error: {e}")
        db.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()
