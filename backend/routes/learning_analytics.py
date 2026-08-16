"""Learning and analytics aggregation for Oorja Sales OS."""
from collections import Counter
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter
from sqlalchemy import func

from database import SessionLocal
from models.company import Company
from models.pipeline import ABTestResult, LeadRating, PipelineStage
from models.sales_os import AIFeedback, LearningRule, Opportunity, PriceHistory, Quotation
from models.campaign import Campaign, CampaignEvent

router = APIRouter(prefix="/api/learning", tags=["Learning & Analytics"])
analytics_router = APIRouter(prefix="/api/analytics", tags=["Sales Analytics"])


def _outcome_counts(values):
    return dict(Counter(v for v in values if v))


@router.get("/summary")
def learning_summary():
    db = SessionLocal()
    try:
        feedback_count = db.query(AIFeedback).count()
        candidate_rules = db.query(LearningRule).filter(LearningRule.status == "Candidate").count()
        approved_rules = db.query(LearningRule).filter(LearningRule.status == "Approved").count()
        ratings = [x.user_rating for x in db.query(LeadRating).all()]
        quote_outcomes = [x.outcome for x in db.query(PriceHistory).all()]
        return {
            "feedback_events": feedback_count,
            "candidate_rules": candidate_rules,
            "approved_rules": approved_rules,
            "lead_ratings": {"count": len(ratings), "average": round(sum(ratings) / len(ratings), 2) if ratings else None},
            "quote_outcomes": _outcome_counts(quote_outcomes),
        }
    finally:
        db.close()


@router.get("/patterns")
def learning_patterns(status: str = "Candidate", limit: int = 50):
    db = SessionLocal()
    try:
        rows = db.query(LearningRule).filter(LearningRule.status == status).order_by(LearningRule.confidence.desc(), LearningRule.evidence_count.desc()).limit(min(max(limit, 1), 200)).all()
        return {"results": [{
            "id": r.id,
            "rule_type": r.rule_type,
            "rule_key": r.rule_key,
            "pattern": r.pattern,
            "evidence_count": r.evidence_count,
            "confidence": float(r.confidence or 0),
            "status": r.status,
        } for r in rows], "total": len(rows)}
    finally:
        db.close()


@router.post("/generate-rules")
def generate_candidate_rules():
    """Analyze recent AI feedback and extract candidate learning rules for human approval."""
    db = SessionLocal()
    try:
        feedback_items = db.query(AIFeedback).all()
        created_rules = 0

        # Group by action_type and reason pattern
        grouped = {}
        for fb in feedback_items:
            key = f"{fb.entity_type}:{fb.action_type}"
            grouped.setdefault(key, []).append(fb)

        for key, items in grouped.items():
            if len(items) >= 1:
                # Check if a rule already exists for this key
                existing = db.query(LearningRule).filter(LearningRule.rule_key == key).first()
                if not existing:
                    rule = LearningRule(
                        rule_type="Heuristic Optimization",
                        rule_key=key,
                        pattern={
                            "entity_type": items[0].entity_type,
                            "action_type": items[0].action_type,
                            "sample_reason": items[0].reason,
                            "sample_human_value": items[0].human_value,
                        },
                        evidence_count=len(items),
                        confidence=min(60.0 + len(items) * 10.0, 95.0),
                        status="Candidate",
                    )
                    db.add(rule)
                    created_rules += 1
                else:
                    existing.evidence_count = len(items)
                    existing.confidence = min(60.0 + len(items) * 10.0, 95.0)

        db.commit()
        return {
            "success": True,
            "feedback_analyzed": len(feedback_items),
            "new_candidate_rules": created_rules,
        }
    finally:
        db.close()


@router.post("/patterns/{rule_id}/approve")
def approve_learning_rule(rule_id: int, approved: bool = True, approved_by: str = "user"):
    """Approve or reject a candidate learning rule to activate it in scoring."""
    db = SessionLocal()
    try:
        row = db.query(LearningRule).filter(LearningRule.id == rule_id).first()
        if not row:
            from fastapi import HTTPException
            raise HTTPException(404, "Learning rule not found")
        row.status = "Approved" if approved else "Rejected"
        row.approved_by = approved_by if approved else None
        row.approved_at = datetime.utcnow() if approved else None
        db.commit()
        return {"id": row.id, "status": row.status, "approved_by": row.approved_by}
    finally:
        db.close()


@router.get("/next-actions")
def next_learning_actions(limit: int = 20):
    db = SessionLocal()
    try:
        rows = db.query(Opportunity).filter(Opportunity.stage.notin_(["Won", "Lost"])).order_by(Opportunity.updated_at.asc()).limit(min(max(limit, 1), 100)).all()
        return {"results": [{
            "opportunity_id": r.id,
            "company_id": r.company_id,
            "name": r.name,
            "stage": r.stage,
            "estimated_value": float(r.estimated_value or 0),
            "recommended_action": "Review opportunity and schedule next human follow-up",
            "reason": r.ai_summary or "Opportunity has not been recently updated",
        } for r in rows], "total": len(rows)}
    finally:
        db.close()


@analytics_router.get("/overview")
def analytics_overview(days: int = 90):
    db = SessionLocal()
    try:
        since = datetime.utcnow() - timedelta(days=max(days, 1))
        open_opps = db.query(Opportunity).filter(Opportunity.stage.notin_(["Won", "Lost"])).all()
        won_opps = db.query(Opportunity).filter(Opportunity.stage == "Won", Opportunity.updated_at >= since).all()
        lost_opps = db.query(Opportunity).filter(Opportunity.stage == "Lost", Opportunity.updated_at >= since).all()
        draft_quotes = db.query(Quotation).filter(Quotation.status == "Draft").count()
        approved_quotes = db.query(Quotation).filter(Quotation.status == "Approved", Quotation.updated_at >= since).count()
        campaigns = db.query(Campaign).count()
        events = db.query(CampaignEvent).filter(CampaignEvent.occurred_at >= since).all()
        event_counts = _outcome_counts([e.event_type for e in events])
        pipeline_value = sum(float(x.estimated_value or 0) for x in open_opps)
        won_value = sum(float(x.estimated_value or 0) for x in won_opps)
        return {
            "period_days": days,
            "pipeline": {"open_opportunities": len(open_opps), "open_value": round(pipeline_value, 2), "won_opportunities": len(won_opps), "won_value": round(won_value, 2), "lost_opportunities": len(lost_opps)},
            "quotations": {"draft": draft_quotes, "approved_in_period": approved_quotes},
            "campaigns": {"campaign_count": campaigns, "events": event_counts},
            "conversion": {"win_rate": round(len(won_opps) / (len(won_opps) + len(lost_opps)) * 100, 2) if (won_opps or lost_opps) else None},
        }
    finally:
        db.close()


@analytics_router.get("/ab")
def analytics_ab():
    db = SessionLocal()
    try:
        rows = db.query(ABTestResult).all()
        grouped = {}
        for r in rows:
            bucket = grouped.setdefault(r.subject_variant, {"sent": 0, "opened": 0, "replied": 0})
            bucket["sent"] += 1
            bucket["opened"] += int(bool(r.opened))
            bucket["replied"] += int(bool(r.replied))
        results = []
        for variant, data in grouped.items():
            results.append({"variant": variant, **data, "open_rate": round(data["opened"] / data["sent"] * 100, 2) if data["sent"] else 0, "reply_rate": round(data["replied"] / data["sent"] * 100, 2) if data["sent"] else 0})
        return {"results": results}
    finally:
        db.close()


@analytics_router.get("/lead-quality")
def analytics_lead_quality():
    db = SessionLocal()
    try:
        rows = db.query(Company.calculated_tier, func.avg(Company.icp_score), func.count(Company.id)).group_by(Company.calculated_tier).all()
        return {"results": [{"tier": tier or "Unscored", "average_icp": round(float(avg or 0), 2), "lead_count": count} for tier, avg, count in rows]}
    finally:
        db.close()
