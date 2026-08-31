"""Learning and analytics aggregation for Oorja Sales OS."""
from collections import Counter
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter
from sqlalchemy import func
from sqlalchemy.orm import Session

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


import re

def _extract_feedback_group_key(fb: AIFeedback) -> tuple[str, str, dict]:
    """
    Extracts (group_key, rule_type, pattern_metadata) from an AIFeedback row.
    For orchestrator_answer feedback, detects sub-patterns (e.g. instrument_category, intent)
    so specific rules like CMM or Pressure Gauge margin are isolated rather than lumped into a generic bucket.
    If no sub-pattern is detected (e.g. territory questions), safely falls back to entity_type:action_type.
    """
    ai_val = fb.ai_value if isinstance(fb.ai_value, dict) else {}
    human_val = fb.human_value if isinstance(fb.human_value, dict) else {}

    if fb.entity_type == "orchestrator_answer":
        inst = (
            human_val.get("instrument_category")
            or ai_val.get("instrument_category")
            or human_val.get("instrument")
            or ai_val.get("instrument")
        )
        sub_intent = human_val.get("sub_intent") or ai_val.get("intent") or ai_val.get("sub_intent")

        if inst:
            norm_inst = str(inst).strip()
            inst_slug = re.sub(r"[^a-zA-Z0-9]+", "_", norm_inst.lower()).strip("_")
            rule_key = f"{fb.entity_type}:{fb.action_type}:{inst_slug}"
            is_pricing = (
                "pricing" in fb.action_type.lower()
                or "price" in fb.action_type.lower()
                or "margin" in (fb.reason or "").lower()
                or "margin_adjustment" in human_val
                or "corrected_price" in human_val
                or "adjustment_percent" in human_val
            )
            rule_type = "Pricing Pattern" if is_pricing else "Instrument Domain Pattern"
            pattern = {
                "entity_type": fb.entity_type,
                "action_type": fb.action_type,
                "instrument_category": norm_inst,
                "adjustment_percent": (
                    human_val.get("adjustment_percent")
                    or human_val.get("adjustment")
                    or human_val.get("margin_adjustment")
                ),
                "sample_reason": fb.reason or human_val.get("reason"),
                "sample_ai_value": fb.ai_value,
                "sample_human_value": fb.human_value,
            }
            return rule_key, rule_type, pattern

        if sub_intent:
            intent_slug = re.sub(r"[^a-zA-Z0-9]+", "_", str(sub_intent).strip().lower()).strip("_")
            rule_key = f"{fb.entity_type}:{fb.action_type}:{intent_slug}"
            rule_type = "Intent Override"
            pattern = {
                "entity_type": fb.entity_type,
                "action_type": fb.action_type,
                "sub_intent": sub_intent,
                "sample_reason": fb.reason,
                "sample_ai_value": fb.ai_value,
                "sample_human_value": fb.human_value,
            }
            return rule_key, rule_type, pattern

    # Standard fallback grouping for all existing / other entity_types (or orchestrator without sub-fields)
    rule_key = f"{fb.entity_type}:{fb.action_type}"
    rule_type = "Heuristic Optimization"
    pattern = {
        "entity_type": fb.entity_type,
        "action_type": fb.action_type,
        "sample_reason": fb.reason,
        "sample_human_value": fb.human_value,
    }
    return rule_key, rule_type, pattern


def generate_candidate_rules_core(db: Session) -> dict:
    """Core logic to analyze recent AI feedback and extract candidate learning rules."""
    feedback_items = db.query(AIFeedback).all()
    created_rules = 0

    # Group by extracted sub-pattern key
    grouped: dict[str, tuple[str, dict, list[AIFeedback]]] = {}
    for fb in feedback_items:
        key, r_type, pat = _extract_feedback_group_key(fb)
        if key not in grouped:
            grouped[key] = (r_type, pat, [])
        grouped[key][2].append(fb)

    for key, (r_type, pat, items) in grouped.items():
        # Threshold: >=3 for orchestrator_answer, >=1 for all other entity types
        entity_type = items[0].entity_type
        min_threshold = 3 if entity_type == "orchestrator_answer" else 1

        if len(items) >= min_threshold:
            existing = db.query(LearningRule).filter(LearningRule.rule_key == key).first()
            confidence = min(60.0 + len(items) * 10.0, 95.0)
            if not existing:
                rule = LearningRule(
                    rule_type=r_type,
                    rule_key=key,
                    pattern=pat,
                    evidence_count=len(items),
                    confidence=confidence,
                    status="Candidate",
                )
                db.add(rule)
                created_rules += 1
            else:
                existing.evidence_count = len(items)
                existing.confidence = confidence
                existing.pattern = pat

    db.commit()
    return {
        "success": True,
        "feedback_analyzed": len(feedback_items),
        "new_candidate_rules": created_rules,
    }


@router.post("/generate-rules")
def generate_candidate_rules():
    """Analyze recent AI feedback and extract candidate learning rules for human approval."""
    db = SessionLocal()
    try:
        return generate_candidate_rules_core(db)
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
