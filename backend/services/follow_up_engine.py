"""Follow-up Engine: Exact 5-Touch Consultative Outbound Cadence (Day 1, 3, 5, 11, 21).

Implements the strict multi-touch rules:
- TOUCH 1 — DAY 1: Initial outreach email sent
- TOUCH 2 — DAY 3: Follow-up 1 sent as reply on the SAME EMAIL THREAD
- TOUCH 3 — DAY 5: Follow-up 2 sent on the SAME EMAIL THREAD
- TOUCH 4 — DAY 11: Follow-up 3 sent on the SAME EMAIL THREAD
- TOUCH 5 — DAY 21: FINAL FOLLOW-UP sent on the SAME EMAIL THREAD
- After Day 21 final follow-up: Cadence terminates (STOPPED). No further automatic follow-ups.

Threading Rule:
- Every follow-up MUST be a reply to the original outbound thread.
- Preserves Message-ID, In-Reply-To, References, recipient, company, lead ID, campaign ID, thread ID.
- Subject prefixed with "Re: <original subject>" or preserves existing thread subject.

Stop Conditions:
- Cancels all pending follow-ups immediately on any meaningful reply:
  ENQUIRY, INTERESTED, REFERRAL, FUTURE_REQUIREMENT, NO_CURRENT_REQUIREMENT,
  EXISTING_VENDOR, EXISTING_VENDOR_OBJECTION, OBJECTION, NOT_INTERESTED, WRONG_PERSON.
- Also stops/suppresses on BOUNCE, OPT_OUT / unsubscribe, invalid mailbox.
- OUT_OF_OFFICE does not permanently terminate cadence: records return date if detectable
  and pauses/reschedules rather than blindly sending into the absence period.

Day Calculation:
- Calendar-day based using Asia/Kolkata timezone:
  Day 1 (initial) -> Day 3 (+2 calendar days) -> Day 5 (+4 calendar days)
  -> Day 11 (+10 calendar days) -> Day 21 (+20 calendar days).

Idempotency:
- Restart must never cause duplicate follow-up sends.
- Verifies touch has not been sent, no reply, contact eligible, thread exists, not opted out, not bounced.
- Deterministic idempotency key: (lead_id, campaign_id, touch_number).
"""
from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from config import settings

logger = logging.getLogger(__name__)

KOLKATA_TZ = ZoneInfo("Asia/Kolkata")

# State Model Constants
STATE_INITIAL_SENT = "INITIAL_SENT"
STATE_FOLLOWUP_1_DUE = "FOLLOWUP_1_DUE"
STATE_FOLLOWUP_1_SENT = "FOLLOWUP_1_SENT"
STATE_FOLLOWUP_2_DUE = "FOLLOWUP_2_DUE"
STATE_FOLLOWUP_2_SENT = "FOLLOWUP_2_SENT"
STATE_FOLLOWUP_3_DUE = "FOLLOWUP_3_DUE"
STATE_FOLLOWUP_3_SENT = "FOLLOWUP_3_SENT"
STATE_FINAL_FOLLOWUP_DUE = "FINAL_FOLLOWUP_DUE"
STATE_FINAL_FOLLOWUP_SENT = "FINAL_FOLLOWUP_SENT"
STATE_REPLIED = "REPLIED"
STATE_STOPPED = "STOPPED"
STATE_BOUNCED = "BOUNCED"
STATE_OPTED_OUT = "OPTED_OUT"
STATE_OOO_PAUSED = "OOO_PAUSED"

# Backwards compatibility aliases
CADENCE_INITIAL = "INITIAL"
CADENCE_FOLLOW_UP_1_DUE = "FOLLOWUP_1_DUE"
CADENCE_FOLLOW_UP_2_DUE = "FOLLOWUP_2_DUE"
CADENCE_FOLLOW_UP_3_DUE = "FOLLOWUP_3_DUE"
CADENCE_FINAL_FOLLOWUP_DUE = "FINAL_FOLLOWUP_DUE"
CADENCE_STOPPED = "STOPPED"
CADENCE_REACTIVATED = "CADENCE_REACTIVATED"

# Stopping reply classifications
TERMINAL_REPLY_INTENTS = {
    "ENQUIRY",
    "INTERESTED",
    "REFERRAL",
    "FUTURE_REQUIREMENT",
    "NO_CURRENT_REQUIREMENT",
    "EXISTING_VENDOR",
    "EXISTING_VENDOR_OBJECTION",
    "OBJECTION",
    "NOT_INTERESTED",
    "WRONG_PERSON",
    "UNSUBSCRIBE",
    "OPT_OUT",
}


def to_kolkata_datetime(dt_or_str: Any) -> datetime:
    """Normalize input datetime or ISO string to Asia/Kolkata timezone."""
    if isinstance(dt_or_str, str):
        dt = datetime.fromisoformat(dt_or_str)
    elif isinstance(dt_or_str, datetime):
        dt = dt_or_str
    else:
        dt = datetime.now(timezone.utc)

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(KOLKATA_TZ)


def calculate_cadence_schedule(initial_sent_at: Any) -> Dict[str, datetime]:
    """Calculate exact calendar-day due dates from Day 1 initial send in Asia/Kolkata.

    Touch 1: Day 1 (initial_sent_at)
    Touch 2: Day 3 (+2 calendar days)
    Touch 3: Day 5 (+4 calendar days)
    Touch 4: Day 11 (+10 calendar days)
    Touch 5: Day 21 (+20 calendar days)
    """
    init_dt = to_kolkata_datetime(initial_sent_at)
    return {
        "initial": init_dt,
        "followup_1_due": init_dt + timedelta(days=2),
        "followup_2_due": init_dt + timedelta(days=4),
        "followup_3_due": init_dt + timedelta(days=10),
        "final_followup_due": init_dt + timedelta(days=20),
    }


def parse_ooo_return_date(text: str, reference_date: Optional[datetime] = None) -> Optional[datetime]:
    """Extract return date from out-of-office message text if present."""
    if not text:
        return None
    ref = reference_date or datetime.now(KOLKATA_TZ)
    content = text.lower()

    # Pattern: back on / return on / returning on <date>
    m = re.search(
        r"(?:back|return(?:ing)?|available)\s+(?:in\s+office\s+)?(?:on|from|by)\s+([A-Za-z]+|\d{1,2})[\s,.-]+(\d{1,2}|[A-Za-z]+)(?:[\s,.-]+(\d{2,4}))?",
        content,
    )
    if m:
        try:
            raw_str = m.group(0)
            # Try to extract day and month
            day_match = re.search(r"\b(\d{1,2})\b", raw_str)
            month_names = {
                "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
                "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
                "aug": 8, "august": 8, "sep": 9, "september": 9, "sept": 9, "oct": 10, "october": 10,
                "nov": 11, "november": 11, "dec": 12, "december": 12,
            }
            found_month = None
            for name, num in month_names.items():
                if name in raw_str:
                    found_month = num
                    break

            if day_match and found_month:
                day = int(day_match.group(1))
                year = ref.year
                year_match = re.search(r"\b(20\d\d)\b", raw_str)
                if year_match:
                    year = int(year_match.group(1))
                return datetime(year, found_month, day, 10, 0, tzinfo=KOLKATA_TZ)
        except Exception:
            pass
    return None


@dataclass
class ThreadIdentifiers:
    original_message_id: str = ""
    thread_id: str = ""
    in_reply_to: str = ""
    references: str = ""
    original_subject: str = ""
    lead_id: str = ""
    campaign_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CadenceState:
    record_id: str
    company: str
    facility: str
    contact_name: str
    email: str
    status: str = STATE_INITIAL_SENT
    initial_sent_at: Optional[str] = None
    followup_1_due_at: Optional[str] = None
    followup_1_sent_at: Optional[str] = None
    followup_2_due_at: Optional[str] = None
    followup_2_sent_at: Optional[str] = None
    followup_3_due_at: Optional[str] = None
    followup_3_sent_at: Optional[str] = None
    final_followup_due_at: Optional[str] = None
    final_followup_sent_at: Optional[str] = None
    has_replied: bool = False
    reply_classification: Optional[str] = None
    reply_received_at: Optional[str] = None
    stop_reason: Optional[str] = None
    is_opted_out: bool = False
    is_bounced: bool = False
    is_superseded: bool = False
    ooo_return_date: Optional[str] = None
    thread_info: ThreadIdentifiers = field(default_factory=ThreadIdentifiers)
    latest_trigger: Optional[str] = None
    latest_trigger_date: Optional[str] = None
    calibration_opportunity: Optional[str] = None

    # Compatibility properties for old code/tests
    @property
    def follow_up_1_sent_at(self) -> Optional[str]:
        return self.followup_1_sent_at

    @follow_up_1_sent_at.setter
    def follow_up_1_sent_at(self, val: Optional[str]) -> None:
        self.followup_1_sent_at = val

    @property
    def follow_up_2_sent_at(self) -> Optional[str]:
        return self.followup_2_sent_at

    @follow_up_2_sent_at.setter
    def follow_up_2_sent_at(self, val: Optional[str]) -> None:
        self.followup_2_sent_at = val

    @property
    def stopped_reason(self) -> Optional[str]:
        return self.stop_reason

    @stopped_reason.setter
    def stopped_reason(self, val: Optional[str]) -> None:
        self.stop_reason = val

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["thread_info"] = self.thread_info.to_dict()
        return d


class FollowUpEngine:
    """Controls progression, scheduling, threading, and consultative copy for 5-touch cadence."""

    def initialize_cadence(
        self,
        record_id: str,
        company: str,
        facility: str,
        contact_name: str,
        email: str,
        initial_sent_at: datetime,
        message_id: str,
        original_subject: str,
        lead_id: str = "",
        campaign_id: str = "",
        calibration_opportunity: str = "",
    ) -> CadenceState:
        """Initialize a new 5-touch cadence on Day 1 initial send."""
        sched = calculate_cadence_schedule(initial_sent_at)
        thread = ThreadIdentifiers(
            original_message_id=message_id,
            thread_id=message_id,
            in_reply_to=message_id,
            references=message_id,
            original_subject=original_subject,
            lead_id=lead_id,
            campaign_id=campaign_id,
        )
        state = CadenceState(
            record_id=record_id,
            company=company,
            facility=facility,
            contact_name=contact_name,
            email=email,
            status=STATE_INITIAL_SENT,
            initial_sent_at=sched["initial"].isoformat(),
            followup_1_due_at=sched["followup_1_due"].isoformat(),
            followup_2_due_at=sched["followup_2_due"].isoformat(),
            followup_3_due_at=sched["followup_3_due"].isoformat(),
            final_followup_due_at=sched["final_followup_due"].isoformat(),
            thread_info=thread,
            calibration_opportunity=calibration_opportunity,
        )
        return state

    def handle_reply_or_event(
        self,
        state: CadenceState,
        classification: str,
        event_time: Optional[datetime] = None,
        reply_body: str = "",
    ) -> CadenceState:
        """Process an inbound response or delivery event and apply stop conditions."""
        now_iso = (event_time or datetime.now(KOLKATA_TZ)).isoformat()
        cls_upper = (classification or "").upper().strip()

        if cls_upper in ("BOUNCE", "INVALID_MAILBOX"):
            state.is_bounced = True
            state.status = STATE_BOUNCED
            state.stop_reason = f"Outbound cadence stopped: Mailbox bounced / delivery failure ({cls_upper})"
            logger.info("[%s] Cadence stopped on BOUNCE for %s", state.record_id, state.email)
            return state

        if cls_upper in ("UNSUBSCRIBE", "OPT_OUT", "NOT_INTERESTED"):
            state.is_opted_out = True
            state.status = STATE_OPTED_OUT
            state.stop_reason = f"Outbound cadence stopped: Recipient opted out / not interested ({cls_upper})"
            logger.info("[%s] Cadence stopped on OPT_OUT for %s", state.record_id, state.email)
            return state

        if cls_upper == "OUT_OF_OFFICE":
            ref_dt = to_kolkata_datetime(event_time)
            ret_dt = parse_ooo_return_date(reply_body, reference_date=ref_dt)
            if ret_dt:
                state.ooo_return_date = ret_dt.isoformat()
                state.status = STATE_OOO_PAUSED
                state.stop_reason = f"Cadence paused for out-of-office until detected return: {ret_dt.strftime('%Y-%m-%d')}"
                logger.info("[%s] Cadence paused for OOO returning %s", state.record_id, ret_dt.strftime('%Y-%m-%d'))
            else:
                # Default safety: pause for 7 days
                fallback_ret = ref_dt + timedelta(days=7)
                state.ooo_return_date = fallback_ret.isoformat()
                state.status = STATE_OOO_PAUSED
                state.stop_reason = f"Cadence paused for out-of-office (default 7 days until {fallback_ret.strftime('%Y-%m-%d')})"
            return state

        # Any meaningful business response stops all future follow-ups immediately
        if cls_upper in TERMINAL_REPLY_INTENTS or cls_upper:
            state.has_replied = True
            state.reply_classification = cls_upper
            state.reply_received_at = now_iso
            state.status = STATE_REPLIED
            state.stop_reason = f"Outbound cadence stopped: Meaningful reply received ({cls_upper})"
            logger.info("[%s] Cadence stopped on reply %s from %s", state.record_id, cls_upper, state.email)
            return state

        return state

    def evaluate_cadence_stage(
        self,
        state: CadenceState,
        current_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Evaluate cadence state at current_time and determine exact next action."""
        now = to_kolkata_datetime(current_time)

        # 1. Terminal Suppression Checks
        if state.is_superseded:
            return {
                "stage": STATE_STOPPED,
                "action_required": "NO_ACTION",
                "reason": "Lead has been superseded by a more recent/relevant contact. Cadence cancelled.",
                "send_permitted": False,
            }

        if state.is_bounced:
            return {
                "stage": STATE_BOUNCED,
                "action_required": "NO_ACTION",
                "reason": f"Cadence permanently halted: {state.stop_reason or 'Mailbox bounced'}",
                "send_permitted": False,
            }

        if state.is_opted_out:
            return {
                "stage": STATE_OPTED_OUT,
                "action_required": "NO_ACTION",
                "reason": f"Cadence permanently halted: {state.stop_reason or 'Recipient opted out'}",
                "send_permitted": False,
            }

        if state.has_replied:
            return {
                "stage": STATE_REPLIED,
                "action_required": "NO_ACTION",
                "reason": f"Cadence terminated: {state.stop_reason or 'Reply received'}",
                "send_permitted": False,
            }

        # 2. OOO Reschedule Handling
        if state.status == STATE_OOO_PAUSED and state.ooo_return_date:
            ret_dt = to_kolkata_datetime(state.ooo_return_date)
            if now < ret_dt:
                return {
                    "stage": STATE_OOO_PAUSED,
                    "action_required": "WAIT_FOR_OOO_RETURN",
                    "due_date": ret_dt.isoformat(),
                    "reason": f"Prospect is out-of-office until {ret_dt.strftime('%Y-%m-%d')}. Follow-ups paused.",
                    "send_permitted": False,
                }
            else:
                # Returned from OOO; resume normal evaluation
                state.status = STATE_INITIAL_SENT
                state.ooo_return_date = None

        # 3. Final Follow-up (Touch 5) Already Sent Check
        if state.final_followup_sent_at:
            if state.status == CADENCE_REACTIVATED:
                return {
                    "stage": CADENCE_REACTIVATED,
                    "action_required": "INITIAL_OUTREACH_NEW_TRIGGER",
                    "reason": "Cadence reactivated due to verified new facility trigger event.",
                    "send_permitted": True,
                }
            return {
                "stage": STATE_STOPPED,
                "action_required": "NO_ACTION",
                "reason": "Touch 5 (Day 21 Final Follow-up) completed. 5-touch cadence finished. Sequence stopped.",
                "send_permitted": False,
            }

        # Ensure due dates are calculated if missing
        if not state.initial_sent_at:
            return {
                "stage": CADENCE_INITIAL,
                "action_required": "SEND_INITIAL_OUTREACH",
                "reason": "Initial outreach not yet recorded.",
                "send_permitted": True,
            }

        if not state.followup_1_due_at:
            sched = calculate_cadence_schedule(state.initial_sent_at)
            state.followup_1_due_at = sched["followup_1_due"].isoformat()
            state.followup_2_due_at = sched["followup_2_due"].isoformat()
            state.followup_3_due_at = sched["followup_3_due"].isoformat()
            state.final_followup_due_at = sched["final_followup_due"].isoformat()

        f1_due = to_kolkata_datetime(state.followup_1_due_at)
        f2_due = to_kolkata_datetime(state.followup_2_due_at)
        f3_due = to_kolkata_datetime(state.followup_3_due_at)
        final_due = to_kolkata_datetime(state.final_followup_due_at)

        # 4. Touch 2 — Day 3 (Follow-up 1)
        if not state.followup_1_sent_at:
            if now >= f1_due:
                return {
                    "stage": STATE_FOLLOWUP_1_DUE,
                    "touch_number": 2,
                    "action_required": "SEND_FOLLOW_UP_1",
                    "due_date": f1_due.isoformat(),
                    "reason": "Day 3 reached. Follow-up 1 due as same-thread reply.",
                    "send_permitted": True,
                }
            return {
                "stage": "WAITING_FOLLOWUP_1",
                "action_required": "WAIT",
                "due_date": f1_due.isoformat(),
                "reason": f"Waiting for Day 3 (scheduled for {f1_due.strftime('%Y-%m-%d')}).",
                "send_permitted": False,
            }

        # 5. Touch 3 — Day 5 (Follow-up 2)
        if not state.followup_2_sent_at:
            if now >= f2_due:
                return {
                    "stage": STATE_FOLLOWUP_2_DUE,
                    "touch_number": 3,
                    "action_required": "SEND_FOLLOW_UP_2",
                    "due_date": f2_due.isoformat(),
                    "reason": "Day 5 reached. Follow-up 2 due as same-thread reply.",
                    "send_permitted": True,
                }
            return {
                "stage": "WAITING_FOLLOWUP_2",
                "action_required": "WAIT",
                "due_date": f2_due.isoformat(),
                "reason": f"Waiting for Day 5 (scheduled for {f2_due.strftime('%Y-%m-%d')}).",
                "send_permitted": False,
            }

        # 6. Touch 4 — Day 11 (Follow-up 3)
        if not state.followup_3_sent_at:
            if now >= f3_due:
                return {
                    "stage": STATE_FOLLOWUP_3_DUE,
                    "touch_number": 4,
                    "action_required": "SEND_FOLLOW_UP_3",
                    "due_date": f3_due.isoformat(),
                    "reason": "Day 11 reached. Follow-up 3 due as same-thread reply.",
                    "send_permitted": True,
                }
            return {
                "stage": "WAITING_FOLLOWUP_3",
                "action_required": "WAIT",
                "due_date": f3_due.isoformat(),
                "reason": f"Waiting for Day 11 (scheduled for {f3_due.strftime('%Y-%m-%d')}).",
                "send_permitted": False,
            }

        # 7. Touch 5 — Day 21 (Final Follow-up)
        if not state.final_followup_sent_at:
            if now >= final_due:
                return {
                    "stage": STATE_FINAL_FOLLOWUP_DUE,
                    "touch_number": 5,
                    "action_required": "SEND_FINAL_FOLLOWUP",
                    "due_date": final_due.isoformat(),
                    "reason": "Day 21 reached. Final Follow-up due. Sequence will stop after send.",
                    "send_permitted": True,
                }
            return {
                "stage": "WAITING_FINAL_FOLLOWUP",
                "action_required": "WAIT",
                "due_date": final_due.isoformat(),
                "reason": f"Waiting for Day 21 (scheduled for {final_due.strftime('%Y-%m-%d')}).",
                "send_permitted": False,
            }

        return {
            "stage": STATE_STOPPED,
            "action_required": "NO_ACTION",
            "reason": "All 5 outreach touches completed. Cadence stopped.",
            "send_permitted": False,
        }

    def generate_follow_up_copy(
        self,
        candidate_data: Dict[str, Any],
        stage: str,
        thread_info: Optional[ThreadIdentifiers] = None,
    ) -> Dict[str, Any]:
        """Generate high-value consultative follow-up copy tailored for each of the 4 follow-up touches."""
        company = candidate_data.get("company") or candidate_data.get("COMPANY", "Your Company")
        facility = candidate_data.get("facility") or candidate_data.get("FACILITY", "Plant Facility")
        contact_name = candidate_data.get("contact_name") or candidate_data.get("CONTACT_NAME") or candidate_data.get("person", "Sir/Madam")
        first_name = candidate_data.get("first_name") or candidate_data.get("FIRST_NAME") or contact_name.split()[0]
        email = candidate_data.get("email") or candidate_data.get("EMAIL", "")
        city = candidate_data.get("city") or candidate_data.get("CITY", "facility")
        opportunity = candidate_data.get("calibration_opportunity") or candidate_data.get("CALIBRATION_OPPORTUNITY", "measurement instrument calibration")

        # Threading header preservation
        t_info = thread_info or ThreadIdentifiers()
        orig_subj = t_info.original_subject or candidate_data.get("original_subject") or f"NABL Calibration Traceability & Audit Readiness — {company} ({city})"
        subject = orig_subj if orig_subj.lower().startswith("re:") else f"Re: {orig_subj}"

        in_reply_to = t_info.original_message_id or t_info.in_reply_to or ""
        references = t_info.references or in_reply_to

        normalized_stage = stage.upper().strip()

        # ── Touch 2 / Follow-up 1 (Day 3): Brief reminder + original trigger/relevance
        if normalized_stage in (STATE_FOLLOWUP_1_DUE, "FOLLOW_UP_1", "FOLLOWUP_1"):
            touch_num = 2
            body_text = f"""Dear {first_name},

Following our earlier note regarding measurement calibration for {facility}, I wanted to share a brief reminder regarding your plant's {opportunity}.

As production activities scale, maintaining uninterrupted calibration cycles is essential to prevent line delays and uphold IATF 16949 / ISO audit readiness. Oorja Technical Services operates an active ISO/IEC 17025:2017 accredited laboratory (NABL Certificate CC-3963) with dedicated lab and on-site calibration capabilities across Maharashtra and industrial corridors.

Would our accreditation scope schedule for {facility} be helpful for your quality team to review?

Best regards,

Oorja Technical Services
Engineering & Metrology Services
Accreditation: ISO/IEC 17025:2017 (NABL CC-3963)
"""
            value_focus = "Brief reminder + facility calibration relevance"

        # ── Touch 3 / Follow-up 2 (Day 5): Useful Oorja capability/relevance point (CC-3963 approved)
        elif normalized_stage in (STATE_FOLLOWUP_2_DUE, "FOLLOW_UP_2", "FOLLOWUP_2"):
            touch_num = 3
            body_text = f"""Dear {first_name},

I wanted to highlight a specific technical capability relevant to quality management at {facility}.

Under our active NABL accreditation (CC-3963), Oorja provides comprehensive calibration with documented measurement uncertainty budgets for:
- Coordinate Measuring Machines (CMMs, 0–1200 mm) both on-site and in-lab
- Digital Calipers & Depth Gauges (0–600 mm)
- External & Internal Micrometers (0–300 mm)
- Dial Indicators & Lever Gauges (0–50 mm)
- Torque Wrenches & Transducers (5 Nm to 1000 Nm)

All certificates provide direct SI traceability, uncertainty budgets (CMC), and calibration stickers aligned with Tier-1 OEM audit standards.

If you have an upcoming recalibration window at {facility}, our technical team can review your equipment list against our scope.

Best regards,

Oorja Technical Services
Engineering & Metrology Services
Accreditation: ISO/IEC 17025:2017 (NABL CC-3963)
"""
            value_focus = "Approved CC-3963 scope parameters (CMM, micrometers, torque)"

        # ── Touch 4 / Follow-up 3 (Day 11): Strong reminder + ask if requirement is current or who handles
        elif normalized_stage in (STATE_FOLLOWUP_3_DUE, "FOLLOW_UP_3", "FOLLOWUP_3"):
            touch_num = 4
            body_text = f"""Dear {first_name},

I recognize your team at {company} manages tight production and quality deadlines at {facility}.

I wanted to quickly check whether instrument recalibration is an active priority for your plant this quarter, or if your requirements are currently fully locked in under an existing AMC.

Alternatively, if calibration and metrology governance at {facility} is handled by another colleague in Quality, Standards, or Plant Operations, could you kindly guide me to the appropriate person?

Best regards,

Oorja Technical Services
Engineering & Metrology Services
Accreditation: ISO/IEC 17025:2017 (NABL CC-3963)
"""
            value_focus = "Active requirement verification + referral query"

        # ── Touch 5 / Final Follow-up (Day 21): Short closure message
        elif normalized_stage in (STATE_FINAL_FOLLOWUP_DUE, "FINAL_FOLLOWUP", "FINAL_FOLLOW_UP"):
            touch_num = 5
            body_text = f"""Dear {first_name},

I don't want to keep filling your inbox, so I'll close the loop after this note.

If calibration support or audit-readiness assistance for {facility} is relevant now or in a future shutdown cycle, our team would be glad to assist under our ISO/IEC 17025:2017 (NABL CC-3963) scope.

If another colleague at {company} oversees outside calibration contracts, a brief referral would be greatly appreciated. Otherwise, thank you for your time, and I wish you and your plant continued operational success.

Best regards,

Oorja Technical Services
Engineering & Metrology Services
Accreditation: ISO/IEC 17025:2017 (NABL CC-3963)
"""
            value_focus = "Courteous closure loop + referral opportunity"

        else:
            raise ValueError(f"Invalid follow-up stage: {stage}")

        # Quality assertions: OutreachClaimGuard compliance
        lower_body = body_text.lower()
        forbidden_phrases = ["just following up", "touching base", "did you get my last email"]
        has_forbidden = any(p in lower_body for p in forbidden_phrases)

        return {
            "stage": stage,
            "touch_number": touch_num,
            "to": email,
            "cc": ["Bablu@oorjatechnical.org", "piyushk@oorjatechnical.com"],
            "subject": subject,
            "body_text": body_text,
            "value_focus": value_focus,
            "threading_headers": {
                "In-Reply-To": in_reply_to,
                "References": references,
                "Message-ID": f"<followup-{touch_num}-{t_info.lead_id or 'lead'}@oorja.local>",
            },
            "thread_identifiers": t_info.to_dict(),
            "test_mode": bool(settings.OUTBOUND_TEST_MODE),
            "audit": {
                "has_forbidden_filler": has_forbidden,
                "facility_specific": bool(facility in body_text),
                "cc_3963_referenced": bool("CC-3963" in body_text),
                "is_same_thread_reply": bool(subject.lower().startswith("re:")),
                "consultative": True,
            },
        }

    def verify_send_idempotency(
        self,
        state: CadenceState,
        touch_number: int,
        executed_touches_store: Optional[Dict[str, bool]] = None,
    ) -> Tuple[bool, str]:
        """Strict pre-send idempotency check to prevent duplicate follow-up sends on restart."""
        # Touch numbers: 1=Initial, 2=F1, 3=F2, 4=F3, 5=Final
        idempotency_key = f"{state.record_id}:{state.thread_info.campaign_id}:{touch_number}"

        if executed_touches_store and executed_touches_store.get(idempotency_key):
            return False, f"Touch {touch_number} already executed for {idempotency_key} (idempotency store match)"

        if touch_number == 2 and state.followup_1_sent_at:
            return False, f"Follow-up 1 already sent at {state.followup_1_sent_at}"
        if touch_number == 3 and state.followup_2_sent_at:
            return False, f"Follow-up 2 already sent at {state.followup_2_sent_at}"
        if touch_number == 4 and state.followup_3_sent_at:
            return False, f"Follow-up 3 already sent at {state.followup_3_sent_at}"
        if touch_number == 5 and state.final_followup_sent_at:
            return False, f"Final follow-up already sent at {state.final_followup_sent_at}"

        if state.has_replied:
            return False, f"Cannot send touch {touch_number}: lead has replied ({state.reply_classification})"
        if state.is_opted_out:
            return False, f"Cannot send touch {touch_number}: lead has opted out"
        if state.is_bounced:
            return False, f"Cannot send touch {touch_number}: lead mailbox has bounced"
        if state.is_superseded:
            return False, f"Cannot send touch {touch_number}: lead is superseded"

        return True, "Send permitted: idempotency and suppression gates pass"

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
        state.stop_reason = None
        state.has_replied = False
        logger.info("Cadence reactivated for %s (%s) on new trigger: %s", state.contact_name, state.company, new_trigger_event)
        return state


# Global instance
follow_up_engine = FollowUpEngine()
