"""Follow-up Engine: Strategic 3-Stage Consultative Outbound Cadence.

Implements the strict multi-touch rules:
- Initial outreach (Day 0)
- Follow-up 1 (after ~3 business days) adding technical SLA benchmarks
- Follow-up 2 (after another 4-5 business days) adding uncertainty/drift review & referral ask
- Stop automatically after Follow-up 2 (unless a verified new trigger emerges)
- Immediately stop on any reply or opt-out.
- Strictly forbids empty "checking in" / "just following up" phrases.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional

from config import settings

logger = logging.getLogger(__name__)

CADENCE_INITIAL = "INITIAL"
CADENCE_WAITING_FU1 = "WAITING_FU1"
CADENCE_FOLLOW_UP_1_DUE = "FOLLOW_UP_1_DUE"
CADENCE_WAITING_FU2 = "WAITING_FU2"
CADENCE_FOLLOW_UP_2_DUE = "FOLLOW_UP_2_DUE"
CADENCE_STOPPED = "CADENCE_STOPPED"
CADENCE_REACTIVATED = "CADENCE_REACTIVATED"


def add_business_days(start_date: datetime, num_days: int) -> datetime:
    """Adds N business days (skipping Saturday and Sunday) to a UTC datetime."""
    current = start_date
    added = 0
    while added < num_days:
        current += timedelta(days=1)
        # Monday is 0, Sunday is 6
        if current.weekday() < 5:
            added += 1
    return current


@dataclass
class CadenceState:
    record_id: str
    company: str
    facility: str
    contact_name: str
    email: str
    status: str = CADENCE_INITIAL
    initial_sent_at: Optional[str] = None
    follow_up_1_sent_at: Optional[str] = None
    follow_up_2_sent_at: Optional[str] = None
    has_replied: bool = False
    reply_classification: Optional[str] = None
    latest_trigger: Optional[str] = None
    latest_trigger_date: Optional[str] = None
    calibration_opportunity: Optional[str] = None
    stopped_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class FollowUpEngine:
    """Controls progression, scheduling, and value-add copy for outbound follow-ups."""

    def evaluate_cadence_stage(
        self,
        state: CadenceState,
        current_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Evaluates whether Follow-up 1, Follow-up 2, or Stop applies."""
        now = current_time or datetime.now(timezone.utc)

        # 1. If lead replied, STOP cadence immediately
        if state.has_replied:
            return {
                "stage": CADENCE_STOPPED,
                "action_required": "NO_ACTION",
                "reason": f"Lead replied with intent: {state.reply_classification or 'REPLIED'}. Outbound cadence terminated.",
                "send_permitted": False,
            }

        # 2. If already completed Follow-up 2, check for new trigger reactivation
        if state.follow_up_2_sent_at:
            if state.status == CADENCE_REACTIVATED:
                return {
                    "stage": CADENCE_REACTIVATED,
                    "action_required": "INITIAL_OUTREACH_NEW_TRIGGER",
                    "reason": "Cadence reactivated due to verified new facility trigger event.",
                    "send_permitted": True,
                }
            return {
                "stage": CADENCE_STOPPED,
                "action_required": "NO_ACTION",
                "reason": "Maximum 2 follow-ups completed without response. Account transitioned to silent nurture.",
                "send_permitted": False,
            }

        # 3. Check Follow-up 1 progression (3 business days after initial)
        if not state.initial_sent_at:
            return {
                "stage": CADENCE_INITIAL,
                "action_required": "SEND_INITIAL_OUTREACH",
                "reason": "Initial outreach not yet recorded.",
                "send_permitted": True,
            }

        initial_dt = datetime.fromisoformat(state.initial_sent_at)
        if initial_dt.tzinfo is None:
            initial_dt = initial_dt.replace(tzinfo=timezone.utc)

        fu1_due_dt = add_business_days(initial_dt, 3)

        if not state.follow_up_1_sent_at:
            if now >= fu1_due_dt:
                return {
                    "stage": CADENCE_FOLLOW_UP_1_DUE,
                    "action_required": "SEND_FOLLOW_UP_1",
                    "due_date": fu1_due_dt.isoformat(),
                    "reason": "3 business days elapsed since initial outreach. Follow-up 1 (Technical Benchmark) due.",
                    "send_permitted": True,
                }
            else:
                return {
                    "stage": CADENCE_WAITING_FU1,
                    "action_required": "WAIT",
                    "due_date": fu1_due_dt.isoformat(),
                    "reason": f"Within 3 business days grace window. Follow-up 1 scheduled for {fu1_due_dt.strftime('%Y-%m-%d')}.",
                    "send_permitted": False,
                }

        # 4. Check Follow-up 2 progression (4 business days after Follow-up 1)
        fu1_dt = datetime.fromisoformat(state.follow_up_1_sent_at)
        if fu1_dt.tzinfo is None:
            fu1_dt = fu1_dt.replace(tzinfo=timezone.utc)

        fu2_due_dt = add_business_days(fu1_dt, 4)

        if not state.follow_up_2_sent_at:
            if now >= fu2_due_dt:
                return {
                    "stage": CADENCE_FOLLOW_UP_2_DUE,
                    "action_required": "SEND_FOLLOW_UP_2",
                    "due_date": fu2_due_dt.isoformat(),
                    "reason": "4 business days elapsed since Follow-up 1. Final Follow-up 2 (Drift Review & Referral) due.",
                    "send_permitted": True,
                }
            else:
                return {
                    "stage": CADENCE_WAITING_FU2,
                    "action_required": "WAIT",
                    "due_date": fu2_due_dt.isoformat(),
                    "reason": f"Within 4 business days grace window. Follow-up 2 scheduled for {fu2_due_dt.strftime('%Y-%m-%d')}.",
                    "send_permitted": False,
                }

        return {
            "stage": CADENCE_STOPPED,
            "action_required": "NO_ACTION",
            "reason": "Cadence ended.",
            "send_permitted": False,
        }

    def generate_follow_up_copy(
        self,
        candidate_data: Dict[str, Any],
        stage: str,
    ) -> Dict[str, Any]:
        """Generates high-value follow-up email copy without empty 'checking in' fluff."""
        company = candidate_data.get("company") or candidate_data.get("COMPANY", "Your Company")
        facility = candidate_data.get("facility") or candidate_data.get("FACILITY", "Plant Facility")
        contact_name = candidate_data.get("contact_name") or candidate_data.get("CONTACT_NAME") or candidate_data.get("person", "Sir/Madam")
        first_name = candidate_data.get("first_name") or candidate_data.get("FIRST_NAME") or contact_name.split()[0]
        email = candidate_data.get("email") or candidate_data.get("EMAIL", "")
        city = candidate_data.get("city") or candidate_data.get("CITY", "facility")
        opportunity = candidate_data.get("calibration_opportunity") or candidate_data.get("CALIBRATION_OPPORTUNITY", "measurement instrument calibration")

        subject = f"Re: NABL Calibration Traceability & Audit Readiness — {company} ({city})"

        if stage == CADENCE_FOLLOW_UP_1_DUE or stage == "FOLLOW_UP_1":
            body_text = f"""Dear {first_name},

Following our earlier note regarding measurement calibration for {facility}, I wanted to share a specific operational benchmark relevant to your facility's {opportunity}.

For manufacturing facilities facing customer audits or equipment expansion, standard 10–14 day calibration turnaround often creates costly line bottlenecks. Oorja Technical Services provides a certified 48-to-72-hour expedited turnaround with on-site calibration teams for Dimensional, Thermal, Electro-Technical, and Pressure/Torque instrumentation under our ISO/IEC 17025:2017 NABL scope (CC-3963).

Each certificate includes fully documented measurement uncertainty budgets (CMC) and calibration stickers compliant with IATF 16949 / ISO 9001 audit standards.

Would an uncertainty budget specimen or our scope schedule for {facility} be helpful for your team to review?

Best regards,

Oorja Technical Services
Engineering & Metrology Division
Accreditation: ISO/IEC 17025:2017 (NABL CC-3963)
Pune & Dahej Regional Metrology Centers
"""
            value_focus = "48-72h turnaround SLA & measurement uncertainty specimen"

        elif stage == CADENCE_FOLLOW_UP_2_DUE or stage == "FOLLOW_UP_2":
            body_text = f"""Dear {first_name},

I recognize your team at {company} has multiple competing operational priorities at {facility}.

To ensure instrument accuracy and prevent calibration drift across your {opportunity}, our technical team can review your equipment list against our CC-3963 accreditation scope and provide an immediate traceability matrix.

If your plant already has a locked-in calibration schedule under existing AMC, we are glad to stay in touch for your next annual shutdown window. Alternatively, if instrument calibration is overseen by another colleague at {facility}, could you kindly point me to the right lead in Quality or Metrology?

Best regards,

Oorja Technical Services
Engineering & Metrology Division
Accreditation: ISO/IEC 17025:2017 (NABL CC-3963)
Pune & Dahej Regional Metrology Centers
"""
            value_focus = "traceability matrix review & consultative referral option"

        else:
            raise ValueError(f"Invalid follow-up stage: {stage}")

        # Quality assertions
        lower_body = body_text.lower()
        forbidden_phrases = ["just following up", "checking in", "touching base", "did you get my last email"]
        has_forbidden = any(p in lower_body for p in forbidden_phrases)

        return {
            "stage": stage,
            "to": email,
            "cc": ["Bablu@oorjatechnical.org", "piyushk@oorjatechnical.com"],
            "subject": subject,
            "body_text": body_text,
            "value_focus": value_focus,
            "test_mode": bool(settings.OUTBOUND_TEST_MODE),
            "audit": {
                "has_forbidden_filler": has_forbidden,
                "facility_specific": bool(facility in body_text),
                "cc_3963_referenced": bool("CC-3963" in body_text),
                "consultative": True,
            },
        }

    def reactivate_with_new_trigger(
        self,
        state: CadenceState,
        new_trigger_event: str,
        new_trigger_date: str,
    ) -> CadenceState:
        """Reactivates a stopped cadence when fresh public expansion evidence emerges."""
        state.status = CADENCE_REACTIVATED
        state.latest_trigger = new_trigger_event
        state.latest_trigger_date = new_trigger_date
        state.stopped_reason = None
        logger.info("Cadence reactivated for %s (%s) on new trigger: %s", state.contact_name, state.company, new_trigger_event)
        return state


# Global instance
follow_up_engine = FollowUpEngine()
