"""
Module 16: Predictive Buying Window Dashboard (Backend)
========================================================
The most powerful view in the app.
Shows: "These companies are most likely to buy in the next 30/60/90 days"

Daily Celery job that categorizes companies into buying windows
based on active signals, intent velocity, and pipeline stage.
"""
import logging
from datetime import datetime
from typing import Dict, List

from sqlalchemy import desc, text
from sqlalchemy.orm import Session

from celery_app import celery_app
from database import SessionLocal
from models.company import Company
from models.pipeline import PipelineStage
from models.intent_signal import CompanyIntentSignal

logger = logging.getLogger(__name__)


# ============================================================
# BUYING WINDOW CALCULATION (Daily Celery Task)
# ============================================================

@celery_app.task(name="services.buyingWindow.calculate_buying_windows")
def calculate_buying_windows() -> Dict:
    """
    Daily task: calculate and update buying_window for all companies.
    Categories: next_30_days, next_60_days, next_90_days, unknown
    """
    db = SessionLocal()
    try:
        companies = db.query(Company).filter(
            Company.calculated_tier != "Low Potential"
        ).all()

        counts = {"next_30_days": 0, "next_60_days": 0, "next_90_days": 0, "unknown": 0}

        for company in companies:
            window = _determine_buying_window(company, db)
            if company.buying_window != window:
                company.buying_window = window
            counts[window] = counts.get(window, 0) + 1

        db.commit()
        logger.info(f"Buying windows updated: {counts}")
        return counts

    except Exception as e:
        logger.error(f"Buying window calculation error: {e}")
        db.rollback()
        return {"error": str(e)}
    finally:
        db.close()


def _determine_buying_window(company: Company, db: Session) -> str:
    """Determine the buying window for a single company based on physical assets and intent signals."""
    from services.calibration_intelligence import calculate_company_asset_calibration_summary

    # 1. Primary Priority: Physical Customer Asset Calibration Due Dates
    asset_summary = calculate_company_asset_calibration_summary(company.id, db)
    due_metrics = asset_summary.get("due_metrics", {})
    if due_metrics.get("overdue", 0) > 0 or due_metrics.get("due_next_30_days", 0) > 0:
        company.urgency_reason = asset_summary.get("urgency_summary")
        return "next_30_days"

    if due_metrics.get("due_next_60_days", 0) > 0:
        company.urgency_reason = asset_summary.get("urgency_summary")
        return "next_60_days"

    if due_metrics.get("upcoming_90_to_120_days", 0) > 0:
        company.urgency_reason = asset_summary.get("urgency_summary")
        return "next_90_days"

    # 2. Secondary Priority: Active External Intent Signals
    signals = db.query(CompanyIntentSignal).filter(
        CompanyIntentSignal.company_id == company.id,
        CompanyIntentSignal.is_active == 1,
    ).all()

    signal_types = [s.signal_type for s in signals]

    if "NABL_RENEWAL_DUE" in signal_types:
        return "next_30_days"

    if "ISO_AUDIT_WINDOW" in signal_types:
        return "next_60_days"

    if "JOB_POSTING_QA" in signal_types or "NEWS_EXPANSION" in signal_types:
        return "next_90_days"

    if "IMPORT_SPIKE" in signal_types or "COMPETITOR_PAIN" in signal_types:
        return "next_90_days"

    if company.intent_velocity_score and company.intent_velocity_score > 35:
        return "next_90_days"

    return "unknown"


# ============================================================
# GET BUYING WINDOW DATA (for API)
# ============================================================

def get_buying_window_board(db: Session = None) -> Dict:
    """
    Get companies organized by buying window for the dashboard.
    Returns 3 columns: next_30, next_60, next_90 days.
    """
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        board = {
            "next_30_days": [],
            "next_60_days": [],
            "next_90_days": [],
        }

        for window in board.keys():
            companies = db.query(Company).filter(
                Company.buying_window == window,
                Company.calculated_tier != "Low Potential",
            ).order_by(desc(Company.icp_score)).limit(50).all()

            for company in companies:
                # Get top signal
                top_signal = db.query(CompanyIntentSignal).filter(
                    CompanyIntentSignal.company_id == company.id,
                    CompanyIntentSignal.is_active == 1,
                ).order_by(desc(CompanyIntentSignal.weight_applied)).first()

                # Get pipeline stage
                pipeline = db.query(PipelineStage).filter(
                    PipelineStage.company_id == company.id
                ).order_by(desc(PipelineStage.created_at)).first()

                board[window].append({
                    "company_id": company.id,
                    "name": company.name,
                    "city": company.city,
                    "state": company.state,
                    "tier": company.calculated_tier,
                    "icp_score": company.icp_score,
                    "top_signal": top_signal.signal_type if top_signal else None,
                    "signal_reason": top_signal.urgency_reason if top_signal else None,
                    "pipeline_stage": pipeline.stage if pipeline else "Not in pipeline",
                    "urgency_reason": company.urgency_reason,
                    "intent_velocity": company.intent_velocity_score,
                })

        # Summary stats
        summary = {
            "total_hot_leads": sum(len(v) for v in board.values()),
            "next_30_count": len(board["next_30_days"]),
            "next_60_count": len(board["next_60_days"]),
            "next_90_count": len(board["next_90_days"]),
        }

        return {
            "board": board,
            "summary": summary,
        }

    finally:
        if close_db:
            db.close()
