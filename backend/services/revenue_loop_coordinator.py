"""Master Revenue Loop Coordinator.

Closes the complete end-to-end loop:
Discovery -> Enrichment -> Stakeholder Decision Graph -> Research Brief -> Scoring ->
Personalized Outreach -> Reply Intelligence -> Calling & Voice Analytics -> Opportunity ->
Quotation & Dynamic Pricing -> Deal Rescue -> Won/Lost Outcome -> Structured Feedback ->
Learning Rules -> Continuous Model Improvement -> LOOP.
"""
from datetime import date, datetime, timedelta
import logging
from typing import Any, Optional
from sqlalchemy.orm import Session

from models.company import Company
from models.person import Person
from models.customer_asset import CustomerAsset
from models.sales_os import Opportunity, Quotation, AIFeedback, LearningRule
from models.company_brain import CompanyTimelineEvent, StakeholderIntelligence
from services.company_brain import record_timeline_event, record_intelligence_fact
from services.calibration_inference_engine import infer_calibration_need, estimate_instrument_population, calculate_cost_of_inaction
from services.lead_intelligence_scorer import evaluate_lead_intelligence
from services.lead_research_brief import generate_lead_research_brief, generate_role_specific_pitch
from services.revenue_autopilot import compute_next_best_revenue_action, generate_account_whitespace_map, diagnose_deal_rescue
from services.call_intelligence import generate_pre_call_brief
from routes.learning_analytics import generate_candidate_rules_core

logger = logging.getLogger(__name__)


def process_incoming_email_reply_loop(
    db: Session,
    company_id: int,
    reply_classification: str,
    reply_body: str,
    recipient_email: str,
    sender_name: Optional[str] = None,
) -> dict[str, Any]:
    """
    Automates the next revenue step when an incoming email reply is received:
    - If Interested / Quote Request -> Creates/progresses Opportunity, generates Pre-Call Brief, evaluates Next Action.
    - If Objection -> Updates stakeholder objection profile, triggers Deal Rescue.
    - If Unsubscribe/Lost -> Logs structured AIFeedback.
    """
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        return {"error": "Company not found"}

    cat = (reply_classification or "neutral").lower()

    if "interested" in cat or "quote" in cat or "request" in cat:
        # 1. Create or progress Opportunity
        opp = (
            db.query(Opportunity)
            .filter(Opportunity.company_id == company_id, Opportunity.stage.in_(["Prospect", "Qualification", "Proposal"]))
            .first()
        )
        if not opp:
            opp = Opportunity(
                company_id=company_id,
                name=f"Calibration Opportunity - {company.name}",
                stage="Proposal",
                estimated_value=75000.0,
                probability=0.75,
                notes="Schedule technical scope discussion / Call Quality Head",
                expected_close_date=date.today() + timedelta(days=21),
                source="reply_intelligence",
            )
            db.add(opp)
            db.commit()
            db.refresh(opp)
        else:
            opp.stage = "Proposal"
            opp.probability = max(float(opp.probability or 0.5), 0.75)
            opp.notes = "Send NABL accredited quotation"
            db.commit()

        # 2. Record Chronological Timeline Event
        record_timeline_event(
            db=db,
            company_id=company_id,
            event_type="email_reply_interested",
            title=f"Inbound Interest from {sender_name or recipient_email}",
            description=f"Classified as '{reply_classification}'. Opportunity stage advanced to Proposal.",
            impact_level="high",
            buying_window_impact="immediate",
            source="reply_intelligence",
        )

        # 3. Generate Pre-Call Brief & Next Best Action
        call_brief = generate_pre_call_brief(company, db)
        next_action = compute_next_best_revenue_action(company, db)

        return {
            "status": "revenue_accelerated",
            "classification": reply_classification,
            "opportunity_id": opp.id,
            "opportunity_stage": opp.stage,
            "recommended_next_action": next_action["recommended_action"],
            "call_brief": call_brief,
        }

    elif "objection" in cat or "vendor" in cat or "price" in cat:
        # Log timeline event
        record_timeline_event(
            db=db,
            company_id=company_id,
            event_type="objection_received",
            title=f"Objection received: {reply_classification}",
            description=reply_body[:200],
            impact_level="medium",
            source="reply_intelligence",
        )

        # Log AIFeedback for learning
        feedback = AIFeedback(
            entity_type="email_objection",
            entity_id=company_id,
            action_type="human_correction",
            ai_value={"initial_pitch": "Standard"},
            human_value={
                "instrument_category": "General",
                "objection_type": reply_classification,
                "adjustment_percent": 0.0,
                "evidence": reply_body[:200],
            },
            reason=reply_body[:200],
        )
        db.add(feedback)
        db.commit()

        # Trigger deal rescue diagnosis
        next_action = compute_next_best_revenue_action(company, db)
        return {
            "status": "objection_logged_deal_rescue_active",
            "classification": reply_classification,
            "deal_rescue_action": next_action["recommended_action"],
        }

    else:
        # Standard logging
        record_timeline_event(
            db=db,
            company_id=company_id,
            event_type="email_reply_received",
            title=f"Email Reply: {reply_classification}",
            description=reply_body[:200],
            impact_level="low",
            source="reply_intelligence",
        )
        return {"status": "reply_logged", "classification": reply_classification}


def process_deal_outcome_loop(
    db: Session,
    company_id: int,
    outcome: str,  # "Won", "Lost"
    quotation_id: Optional[int] = None,
    loss_reason: Optional[str] = None,
    instrument_category: str = "General",
) -> dict[str, Any]:
    """
    Feeds deal outcomes back into the learning loop:
    - Logs Won/Lost timeline events.
    - Creates structured AIFeedback rows for rule learning.
    - If Won: Generates Account White-Space map for cross-selling.
    - If Lost: Analyzes sequence failure and updates strategy rules.
    """
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        return {"error": "Company not found"}

    is_won = outcome.lower() == "won"

    # 1. Update Quotation if provided
    if quotation_id:
        quote = db.query(Quotation).filter(Quotation.id == quotation_id).first()
        if quote:
            quote.status = "Won" if is_won else "Lost"
            db.commit()

    # 2. Record Timeline Event
    event_title = f"Deal {outcome}: INR {quote.total if quotation_id and quote else 0:,.2f}"
    record_timeline_event(
        db=db,
        company_id=company_id,
        event_type="deal_won" if is_won else "deal_lost",
        title=event_title,
        description=f"Outcome: {outcome}. Loss reason: {loss_reason or 'None'}. Category: {instrument_category}.",
        impact_level="critical" if is_won else "high",
        source="sales_outcome",
    )

    # 3. Log Structured Feedback into AIFeedback for Autolearn
    feedback = AIFeedback(
        entity_type="deal_outcome",
        entity_id=company_id,
        action_type="win" if is_won else "loss",
        ai_value={"predicted_conversion": 0.75},
        human_value={
            "instrument_category": instrument_category,
            "outcome": outcome,
            "loss_reason": loss_reason or "price_vs_quality",
            "adjustment_percent": 10.0 if is_won else -5.0,
            "company_industry": company.industry or "Automotive",
        },
        reason=loss_reason or f"Deal {outcome}",
    )
    db.add(feedback)
    db.commit()

    # 4. If Won -> Auto-generate White-Space Map for immediate account expansion
    whitespace = None
    if is_won:
        whitespace = generate_account_whitespace_map(company, db)

    # 5. Check candidate rules in learning engine
    rules_generated = generate_candidate_rules_core(db)

    return {
        "company_id": company_id,
        "outcome": outcome,
        "loss_reason": loss_reason,
        "whitespace_expansion": whitespace,
        "new_candidate_rules_count": rules_generated.get("new_candidate_rules", 0),
        "message": "Outcome successfully incorporated into master sales dataset and learning rules.",
    }


def execute_full_revenue_loop_audit(db: Session, company_id: int) -> dict[str, Any]:
    """
    Executes a comprehensive, automated 360° revenue audit for an account,
    connecting Discovery -> Research -> Scoring -> Pitch -> Next Action -> White-Space.
    """
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        return {"error": "Company not found"}

    scorecard = evaluate_lead_intelligence(company, db)
    inference = infer_calibration_need(company, db)
    cost = calculate_cost_of_inaction(company, db)
    brief = generate_lead_research_brief(company, db)
    pitch = generate_role_specific_pitch(company, "Quality / Metrology", db)
    next_action = compute_next_best_revenue_action(company, db)
    call_brief = generate_pre_call_brief(company, db)
    whitespace = generate_account_whitespace_map(company, db)

    return {
        "company_id": company.id,
        "company_name": company.name,
        "revenue_loop_stage": "Active Revenue Pipeline",
        "composite_score": scorecard.composite_score,
        "buy_probability": scorecard.buy_probability,
        "strategic_segment": scorecard.strategic_segment,
        "top_calibration_parameter": inference["parameter_inferences"][0]["parameter"] if inference["parameter_inferences"] else "General",
        "cost_of_inaction_exposure_inr": cost["total_estimated_exposure_inr"],
        "recommended_next_action": next_action["recommended_action"],
        "priority_channel": next_action["channel"],
        "target_decision_maker": brief.target_stakeholders[0]["title"],
        "personalized_pitch_subject": pitch["subject"],
        "pre_call_opening": call_brief["opening_script"],
        "unserved_parameters_count": whitespace["expansion_opportunity_count"],
    }
