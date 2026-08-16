"""
Module 12: Next Best Action Engine
====================================
After every activity logged, AI decides what to do next.
Uses Claude to recommend the single best next action based on
company context, pipeline stage, signals, and activity history.

Shows in dashboard as:
"AI recommends: Call {name} today about NABL renewal"
"""
import json
import logging
from datetime import datetime, timedelta, date
from typing import Dict, Optional, Any

import anthropic
from sqlalchemy import desc
from sqlalchemy.orm import Session

from config import settings
from database import SessionLocal
from models.company import Company
from models.person import Person
from models.pipeline import PipelineStage, PipelineActivity as Activity
from models.intent_signal import CompanyIntentSignal

logger = logging.getLogger(__name__)


# ============================================================
# VALID ACTIONS
# ============================================================

VALID_ACTIONS = [
    "SEND_EMAIL",
    "SEND_WHATSAPP",
    "MAKE_CALL",
    "SEND_VALUE_EMAIL",
    "CONNECT_LINKEDIN",
    "WAIT_7_DAYS",
    "MARK_NURTURE",
    "REQUEST_REFERRAL",
]

# ============================================================
# ACTION RULES (used for fallback when Claude unavailable)
# ============================================================

STAGE_ACTION_MAP = {
    "New": {
        "default": "SEND_EMAIL",
        "has_phone": "SEND_WHATSAPP",
        "high_urgency": "MAKE_CALL",
    },
    "Contacted": {
        "default": "SEND_WHATSAPP",
        "no_reply_7d": "MAKE_CALL",
        "no_reply_14d": "SEND_VALUE_EMAIL",
    },
    "Replied": {
        "default": "MAKE_CALL",
        "positive": "MAKE_CALL",
        "neutral": "SEND_VALUE_EMAIL",
    },
    "Meeting Booked": {
        "default": "WAIT_7_DAYS",
        "after_meeting": "SEND_EMAIL",
    },
    "Proposal Sent": {
        "default": "MAKE_CALL",
        "no_reply_7d": "SEND_WHATSAPP",
        "no_reply_14d": "SEND_VALUE_EMAIL",
    },
    "Negotiation": {
        "default": "MAKE_CALL",
    },
    "Nurture": {
        "default": "SEND_VALUE_EMAIL",
        "trigger_detected": "SEND_WHATSAPP",
    },
}

CHANNEL_ESCALATION = ["SEND_EMAIL", "SEND_WHATSAPP", "MAKE_CALL", "CONNECT_LINKEDIN"]


# ============================================================
# MAIN FUNCTION
# ============================================================

def get_next_best_action(company_id: int, db: Session = None) -> Dict[str, Any]:
    """
    Determine the next best action for a company.
    Uses Claude when available, falls back to rule-based logic.

    Returns:
        {
            'action': 'ACTION_TYPE',
            'timing': 'today / tomorrow / in N days',
            'reason': '1 sentence explanation',
            'message_draft': 'ready-to-send message if applicable',
            'ai_recommendation': 'Full AI recommendation text'
        }
    """
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        # Gather context
        company = db.query(Company).filter(Company.id == company_id).first()
        if not company:
            return {"error": "Company not found"}

        pipeline = db.query(PipelineStage).filter(
            PipelineStage.company_id == company_id
        ).order_by(desc(PipelineStage.created_at)).first()

        # Get last activity
        last_activity = db.query(Activity).filter(
            Activity.company_id == company_id
        ).order_by(desc(Activity.occurred_at)).first()

        # Get active signals
        signals = db.query(CompanyIntentSignal).filter(
            CompanyIntentSignal.company_id == company_id,
            CompanyIntentSignal.is_active == 1,
        ).order_by(desc(CompanyIntentSignal.weight_applied)).all()

        # Get decision maker
        person = db.query(Person).filter(
            Person.company_id == company_id
        ).order_by(desc(Person.is_decision_maker), Person.id).first()

        # Calculate days since last touch
        days_since_touch = 0
        if last_activity and last_activity.occurred_at:
            days_since_touch = (datetime.utcnow() - last_activity.occurred_at).days
        elif pipeline and pipeline.last_touched:
            days_since_touch = (datetime.utcnow() - pipeline.last_touched).days

        # Build context for Claude
        context = {
            "company_name": company.name,
            "tier": company.calculated_tier or "Unscored",
            "icp_score": company.icp_score or 0,
            "stage": pipeline.stage if pipeline else "New",
            "last_activity_type": last_activity.activity_type if last_activity else "none",
            "last_activity_outcome": last_activity.outcome if last_activity else "none",
            "days_since_last_touch": days_since_touch,
            "signals": [{"type": s.signal_type, "reason": s.urgency_reason} for s in signals[:5]],
            "person_name": person.full_name if person else None,
            "person_designation": person.designation if person else None,
            "person_phone": person.phone if person else None,
            "buying_window": company.buying_window or "unknown",
        }

        # Try Claude first, fall back to rules
        if settings.ANTHROPIC_API_KEY:
            result = _claude_next_action(context)
            if result:
                # Save recommendation to pipeline
                _save_recommendation(pipeline, result, db)
                return result

        # Fallback to rule-based
        result = _rule_based_next_action(context)
        _save_recommendation(pipeline, result, db)
        return result

    except Exception as e:
        logger.error(f"Next best action error for company {company_id}: {e}")
        return {
            "action": "SEND_EMAIL",
            "timing": "today",
            "reason": f"Error determining action: {str(e)}",
            "message_draft": None,
        }
    finally:
        if close_db:
            db.close()


def _claude_next_action(context: Dict) -> Optional[Dict]:
    """Use Claude to determine next best action."""
    try:
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

        signal_text = "\n".join([
            f"  - {s['type']}: {s['reason']}" for s in context.get("signals", [])
        ]) or "  None active"

        prompt = f"""Company: {context['company_name']}
Tier: {context['tier']} (ICP Score: {context['icp_score']}/100)
Stage: {context['stage']}
Last activity: {context['last_activity_type']}, Outcome: {context['last_activity_outcome']}
Days since last touch: {context['days_since_last_touch']}
Active buying signals:
{signal_text}
Person: {context.get('person_name', 'Unknown')}, {context.get('person_designation', 'Unknown')}
Has phone: {'Yes' if context.get('person_phone') else 'No'}
Buying window: {context['buying_window']}

What is the single best next action? Choose one:
  SEND_EMAIL, SEND_WHATSAPP, MAKE_CALL, SEND_VALUE_EMAIL,
  CONNECT_LINKEDIN, WAIT_7_DAYS, MARK_NURTURE, REQUEST_REFERRAL

Consider:
- If NABL renewal is due within 30 days, urgency is maximum — call today
- If no reply after 2 touches on same channel, switch channels
- If stuck >14 days in Contacted, escalate to call
- If signals are strong but stage is New, be aggressive (WhatsApp or call)
- WhatsApp works better than email for Indian SME decision makers
- After proposal sent, wait 3 days then call

Return JSON only:
{{
  "action": "ACTION_TYPE",
  "timing": "today / tomorrow / in N days",
  "reason": "1 sentence explaining why this action and why now",
  "message_draft": "ready-to-send message if applicable (null for WAIT or MARK actions)"
}}"""

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = response.content[0].text

        # Parse JSON
        try:
            result = json.loads(response_text)
        except json.JSONDecodeError:
            # Try to extract JSON
            start = response_text.index("{")
            end = response_text.rindex("}") + 1
            result = json.loads(response_text[start:end])

        # Validate action
        if result.get("action") not in VALID_ACTIONS:
            result["action"] = "SEND_EMAIL"

        result["ai_recommendation"] = (
            f"AI recommends: {_action_to_human(result['action'])} "
            f"{context.get('person_name', context['company_name'])} "
            f"{result.get('timing', 'today')} — {result.get('reason', '')}"
        )

        return result

    except Exception as e:
        logger.warning(f"Claude next action failed: {e}")
        return None


def _rule_based_next_action(context: Dict) -> Dict:
    """Determine next action using rule-based logic (fallback)."""
    stage = context.get("stage", "New")
    days = context.get("days_since_last_touch", 0)
    signals = context.get("signals", [])
    signal_types = [s["type"] for s in signals]
    has_phone = bool(context.get("person_phone"))

    action = "SEND_EMAIL"
    timing = "today"
    reason = ""

    # High urgency signals override everything
    if "NABL_RENEWAL_DUE" in signal_types:
        action = "MAKE_CALL" if has_phone else "SEND_WHATSAPP"
        timing = "today"
        reason = "NABL renewal approaching — highest priority, must contact immediately"

    elif "ISO_AUDIT_WINDOW" in signal_types and stage in ["New", "Nurture"]:
        action = "SEND_WHATSAPP" if has_phone else "SEND_EMAIL"
        timing = "today"
        reason = "ISO audit window detected — time-sensitive opportunity"

    # Stage-based rules
    elif stage == "New":
        if "NEWS_EXPANSION" in signal_types or "JOB_POSTING_QA" in signal_types:
            action = "SEND_WHATSAPP" if has_phone else "SEND_EMAIL"
            timing = "today"
            reason = "Active buying signal detected for new lead — initiate immediately"
        else:
            action = "SEND_EMAIL"
            timing = "today"
            reason = "New lead — start with personalized email"

    elif stage == "Contacted":
        if days >= 14:
            action = "MAKE_CALL" if has_phone else "SEND_VALUE_EMAIL"
            timing = "today"
            reason = f"No reply after {days} days — escalate channel"
        elif days >= 7:
            action = "SEND_WHATSAPP" if has_phone else "SEND_VALUE_EMAIL"
            timing = "today"
            reason = f"No reply after {days} days — try WhatsApp"
        elif days >= 3:
            action = "SEND_WHATSAPP"
            timing = "tomorrow"
            reason = "Follow up on initial outreach via WhatsApp"
        else:
            action = "WAIT_7_DAYS"
            timing = f"in {3 - days} days"
            reason = "Give time for first message to be seen"

    elif stage == "Replied":
        action = "MAKE_CALL" if has_phone else "SEND_EMAIL"
        timing = "today"
        reason = "They replied — strike while interest is warm, book a meeting"

    elif stage == "Meeting Booked":
        if days > 3:
            action = "SEND_WHATSAPP"
            timing = "today"
            reason = "Confirm meeting or send prep material"
        else:
            action = "WAIT_7_DAYS"
            timing = "on meeting day"
            reason = "Meeting scheduled — prepare and wait"

    elif stage == "Proposal Sent":
        if days >= 7:
            action = "MAKE_CALL" if has_phone else "SEND_WHATSAPP"
            timing = "today"
            reason = f"Proposal sent {days} days ago — follow up by call"
        elif days >= 3:
            action = "SEND_WHATSAPP"
            timing = "today"
            reason = "Gentle WhatsApp follow-up on proposal"
        else:
            action = "WAIT_7_DAYS"
            timing = f"in {3 - days} days"
            reason = "Give time to review proposal"

    elif stage == "Negotiation":
        action = "MAKE_CALL" if has_phone else "SEND_EMAIL"
        timing = "today"
        reason = "In negotiation — maintain momentum with direct conversation"

    elif stage == "Nurture":
        if signals:
            action = "SEND_WHATSAPP" if has_phone else "SEND_EMAIL"
            timing = "today"
            reason = f"New signal detected for nurture lead: {signal_types[0]}"
        else:
            action = "SEND_VALUE_EMAIL"
            timing = "in 7 days"
            reason = "Nurture with value content — stay top of mind"

    else:
        action = "SEND_EMAIL"
        timing = "today"
        reason = "Default action — initiate contact"

    # Build message draft
    message_draft = _generate_quick_message(context, action)

    result = {
        "action": action,
        "timing": timing,
        "reason": reason,
        "message_draft": message_draft,
        "ai_recommendation": (
            f"AI recommends: {_action_to_human(action)} "
            f"{context.get('person_name', context['company_name'])} "
            f"{timing} — {reason}"
        ),
    }

    return result


def _generate_quick_message(context: Dict, action: str) -> Optional[str]:
    """Generate a quick message draft based on action type."""
    company = context.get("company_name", "")
    person = context.get("person_name", "")
    first_name = person.split()[0] if person else ""
    signals = context.get("signals", [])
    top_signal = signals[0] if signals else {}

    if action == "SEND_WHATSAPP":
        if top_signal.get("type") == "NABL_RENEWAL_DUE":
            return f"{company} — noticed your NABL renewal is coming up. Do you have your calibration partner sorted for the renewal audit? — Ravi"
        elif top_signal.get("type") == "JOB_POSTING_QA":
            return f"Hi{' ' + first_name if first_name else ''}, saw {company} is hiring for QA. Building the team is step 1 — need calibration AMC support too? Quick question."
        else:
            return f"{company} — quick question: do you handle calibration in-house or outsource currently?"

    elif action == "MAKE_CALL":
        if top_signal.get("type") == "NABL_RENEWAL_DUE":
            return f"Hi {first_name or 'sir'}, calling about {company}'s upcoming NABL renewal. We help labs get calibration sorted before the audit window. Do you have 2 minutes?"
        return f"Hi {first_name or 'sir'}, this is regarding {company}'s calibration requirements. We work with similar companies in your area. Can I share how we help?"

    elif action == "SEND_VALUE_EMAIL":
        return f"Subject: Calibration interval reference for {company}\n\nI put together a quick reference showing recommended calibration intervals for instruments commonly used in your industry. Thought it might be useful regardless of whether we work together. Shall I share?"

    elif action in ["WAIT_7_DAYS", "MARK_NURTURE"]:
        return None

    return None


def _action_to_human(action: str) -> str:
    """Convert action code to human-readable text."""
    mapping = {
        "SEND_EMAIL": "Email",
        "SEND_WHATSAPP": "WhatsApp",
        "MAKE_CALL": "Call",
        "SEND_VALUE_EMAIL": "Send value email to",
        "CONNECT_LINKEDIN": "Connect on LinkedIn with",
        "WAIT_7_DAYS": "Wait 7 days for",
        "MARK_NURTURE": "Move to nurture:",
        "REQUEST_REFERRAL": "Ask for referral from",
    }
    return mapping.get(action, action)


def _save_recommendation(pipeline: Optional[PipelineStage], result: Dict, db: Session):
    """Save the recommendation to the pipeline stage."""
    if not pipeline:
        return

    try:
        pipeline.next_action = f"{result.get('action', '')} — {result.get('reason', '')}"

        # Set next action date
        timing = result.get("timing", "today")
        if timing == "today":
            pipeline.next_action_date = date.today()
        elif timing == "tomorrow":
            pipeline.next_action_date = date.today() + timedelta(days=1)
        elif "in" in timing and "days" in timing:
            try:
                days = int("".join(filter(str.isdigit, timing)))
                pipeline.next_action_date = date.today() + timedelta(days=days)
            except ValueError:
                pipeline.next_action_date = date.today() + timedelta(days=3)
        else:
            pipeline.next_action_date = date.today() + timedelta(days=1)

        db.commit()
    except Exception as e:
        logger.error(f"Error saving recommendation: {e}")
        db.rollback()


# ============================================================
# BATCH PROCESSING
# ============================================================

def refresh_all_recommendations(db: Session = None) -> Dict:
    """Refresh next best action for all active pipeline entries."""
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        active_pipelines = db.query(PipelineStage).filter(
            PipelineStage.stage.notin_(["Won", "Lost"])
        ).all()

        updated = 0
        errors = 0

        for pipeline in active_pipelines:
            try:
                result = get_next_best_action(pipeline.company_id, db)
                if "error" not in result:
                    updated += 1
                else:
                    errors += 1
            except Exception:
                errors += 1

        return {"updated": updated, "errors": errors}

    finally:
        if close_db:
            db.close()
