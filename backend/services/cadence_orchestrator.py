"""15-Day Non-Response Strategy & Cadence Orchestration Engine.

Manages automated evaluation gates when an outbound campaign recipient
has not replied after a configurable time window (default 15 days).

Evaluates Opportunity Value, Urgency, Stakeholder Role, and Premium Potential
to decide whether to:
- Call Immediately
- Pivot to an alternate stakeholder (e.g. Purchase -> Quality Head)
- Send a second value-add follow-up
- Transition to nurture
- Escalate for executive human review
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
import logging
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from models.company import Company
from models.person import Person
from models.sales_os import Opportunity, SalesTask
from models.company_brain import CompanyTimelineEvent
from services.company_brain import record_timeline_event
from services.lead_intelligence_scorer import evaluate_lead_intelligence
from services.call_intelligence import generate_pre_call_brief

logger = logging.getLogger(__name__)


def evaluate_non_response_cadence(
    company: Company,
    db: Session,
    days_since_outbound: int = 15,
    non_response_threshold_days: int = 15,
    last_contacted_role: str = "Purchase",
    last_contact_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Evaluates the next tactical action for a non-responsive account."""
    scorecard = evaluate_lead_intelligence(company, db)
    composite_score = getattr(scorecard, "composite_score", None) if hasattr(scorecard, "composite_score") else scorecard.get("composite_score", 60)
    opp_value = getattr(scorecard, "opportunity_value_inr", None) if hasattr(scorecard, "opportunity_value_inr") else scorecard.get("opportunity_value_inr", 50000.0)
    buying_window = getattr(scorecard, "buying_window", None) if hasattr(scorecard, "buying_window") else scorecard.get("buying_window", "30_days")
    premium_potential = getattr(scorecard, "premium_potential", None) if hasattr(scorecard, "premium_potential") else scorecard.get("premium_potential", "Medium")

    # Check if threshold is breached
    if days_since_outbound < non_response_threshold_days:
        return {
            "company_id": company.id,
            "company_name": company.name,
            "status": "within_grace_period",
            "days_since_outbound": days_since_outbound,
            "threshold_days": non_response_threshold_days,
            "recommended_action": "Wait for grace period to conclude.",
            "next_evaluation_date": (date.today() + timedelta(days=(non_response_threshold_days - days_since_outbound))).isoformat(),
        }

    # Rule 1: Stalled with Purchase -> Pivot directly to Quality Assurance
    if "purchase" in last_contacted_role.lower() or "procurement" in last_contacted_role.lower():
        action_type = "pivot_stakeholder"
        target_role = "Head of Quality Assurance & Metrology"
        reasoning = (
            f"Purchase department has not responded after {days_since_outbound} days. In calibration procurement, "
            f"Purchase only acts when Quality specifies a technical requirement. Pivot directly to Quality Head."
        )
        call_brief = None
        next_step = f"Send Audit-Readiness & NABL Traceability brief directly to {target_role}."

    # Rule 2: Quality Contact / High Value Account -> Escalate to Direct Phone Call
    elif opp_value >= 150000.0 or composite_score >= 80 or buying_window == "immediate":
        action_type = "escalate_to_call"
        target_role = "Quality / Metrology Head"
        reasoning = (
            f"High-value account (₹{opp_value:,.2f}) with {buying_window} buying window has not replied after "
            f"{days_since_outbound} days. Email engagement insufficient — immediate direct calling required."
        )
        call_brief = generate_pre_call_brief(company, db, person_id=last_contact_id)
        next_step = f"Trigger outbound call to {target_role} using 30-second turnaround pitch."

    # Rule 3: Standard Quality Follow-up -> Send Second Value-Add Followup with SLA Benchmark
    elif "quality" in last_contacted_role.lower() or "metrology" in last_contacted_role.lower():
        action_type = "second_email_followup"
        target_role = "Quality Manager"
        reasoning = (
            f"Quality stakeholder has not engaged after {days_since_outbound} days. "
            f"Provide high-utility technical content: 48-hour emergency calibration turnaround SLA."
        )
        call_brief = None
        next_step = "Send Follow-up #2 with On-site Calibration SLA & Uncertainty Budget specimen."

    # Rule 4: Moderate/Low Fit -> 30-Day Nurture
    else:
        action_type = "nurture_queue"
        target_role = "General Quality Department"
        reasoning = (
            f"No response after {days_since_outbound} days and moderate composite score ({composite_score}). "
            f"Preserve brand equity and avoid spam fatigue — move to 30-day regulatory advisory nurture."
        )
        call_brief = None
        next_step = "Place in 30-day monthly metrology regulatory updates cadence."

    # Log Cadence Decision Timeline Event
    record_timeline_event(
        db=db,
        company_id=company.id,
        event_type="cadence_non_response_evaluated",
        title=f"15-Day Non-Response Action: {action_type.replace('_', ' ').title()}",
        description=reasoning,
        impact_level="medium",
        source="cadence_orchestrator",
    )

    return {
        "company_id": company.id,
        "company_name": company.name,
        "days_since_outbound": days_since_outbound,
        "non_response_threshold_days": non_response_threshold_days,
        "action_type": action_type,
        "target_role": target_role,
        "reasoning": reasoning,
        "next_step": next_step,
        "call_brief": call_brief,
        "composite_score": composite_score,
        "opportunity_value_inr": opp_value,
    }
