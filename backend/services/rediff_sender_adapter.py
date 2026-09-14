"""Safe file-handoff adapter for the existing Rediff_Email_System.

Salesoorja owns qualification and suppression decisions. This adapter never
imports the Rediff project, opens SMTP, or reads Rediff credentials. Production
handoff is a CSV queue item that the existing sender may consume only after a
separate, explicitly authorized transport run.
"""

from __future__ import annotations

import csv
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

from config import settings
from services.email_validator import EMAIL_REGEX, ROLE_PREFIXES
from services.qualification_state_machine import determine_qualification_state

logger = logging.getLogger(__name__)

QUEUED = "QUEUED"
DRY_RUN_READY = "DRY_RUN_READY"
SENT = "SENT"
FAILED = "FAILED"
TEMPORARY_FAILURE = "TEMPORARY_FAILURE"
SUPPRESSED_NOT_READY = "SUPPRESSED_NOT_READY"
SUPPRESSED_TEST_DATA = "SUPPRESSED_TEST_DATA"
SUPPRESSED_DUPLICATE = "SUPPRESSED_DUPLICATE"
SUPPRESSED_REPLY = "SUPPRESSED_REPLY"
SUPPRESSED_OPTOUT = "SUPPRESSED_OPTOUT"
SUPPRESSED_BOUNCE = "SUPPRESSED_BOUNCE"
INVALID_EMAIL = "INVALID_EMAIL"

REDIFF_ENTRYPOINTS = ("campaign_runner.py", "send_email.py")
BACKEND_ROOT = Path(__file__).resolve().parent.parent
SENSITIVE_KEY_PARTS = ("password", "secret", "token", "credential", "authorization")
TEST_PROVENANCE = {"MOCK", "SYNTHETIC", "TEST", "DEMO"}
STOP_REPLY_CLASSES = {
    "INTERESTED",
    "NOT_INTERESTED",
    "UNSUBSCRIBE",
    "EXISTING_VENDOR",
    "NO_CURRENT_REQUIREMENT",
    "WRONG_PERSON",
    "OTHER",
}

REDIFF_CSV_FIELDS = (
    "LEAD_ID",
    "COMPANY_NAME",
    "COMPANY",
    "FACILITY",
    "LOCATION",
    "CITY",
    "STATE",
    "SCORE",
    "LEAD_SCORE",
    "OPPORTUNITY_CLASS",
    "DEMAND_EVENT",
    "WHY_CALIBRATION_NOW",
    "EXTERNAL_PROVIDER_REASON",
    "VENDOR_INCUMBENCY",
    "CONTACT_PERSON",
    "CONTACT_NAME",
    "FIRST_NAME",
    "DESIGNATION",
    "CONTACT_NUMBER",
    "PHONE",
    "EMAIL_ID",
    "EMAIL",
    "PERSONA",
    "BUYING_WINDOW",
    "PREMIUM_POTENTIAL",
    "EARLY_ENTRY",
    "CONFIDENCE",
    "OUTREACH_STATUS",
    "NEXT_RESEARCH_ACTION",
    "READY_FOR_EMAIL",
    "TRIGGER",
    "TRIGGER_EVENT",
    "TRIGGER_DATE",
    "CALIBRATION_CATEGORY",
    "CALIBRATION_OPPORTUNITY",
    "REASON_FOR_OUTREACH",
    "FACILITY_VERIFIED",
    "CONTACT_VERIFIED",
    "CONTACT_LOCATION",
    "NOTES",
    "CAMPAIGN",
    "FOLLOWUP_STAGE",
    "MESSAGE_ID",
    "IN_REPLY_TO",
    "REFERENCES",
    "CC",
    "SALESOORJA_RECORD_ID",
    "SUBJECT",
    "FINAL_SUBJECT",
    "BODY_HTML",
    "FINAL_BODY_HTML",
    "BODY_TEXT",
    "FINAL_BODY_TEXT",
)


@dataclass(frozen=True)
class RediffAdapterConfig:
    enabled: bool
    test_mode: bool
    system_path: Path
    handoff_dir: Path
    cc_addresses: tuple[str, ...]
    duplicate_window_days: int = 14

    @classmethod
    def from_settings(cls) -> "RediffAdapterConfig":
        handoff_dir = Path(settings.REDIFF_HANDOFF_DIR)
        if not handoff_dir.is_absolute():
            handoff_dir = BACKEND_ROOT / handoff_dir
        return cls(
            enabled=bool(settings.REDIFF_SENDER_ENABLED),
            test_mode=bool(settings.OUTBOUND_TEST_MODE or settings.REDIFF_TEST_MODE),
            system_path=Path(settings.REDIFF_SYSTEM_PATH) if settings.REDIFF_SYSTEM_PATH else Path(),
            handoff_dir=handoff_dir,
            cc_addresses=_parse_addresses(settings.REDIFF_CC_ADDRESSES),
            duplicate_window_days=max(1, int(settings.REDIFF_DUPLICATE_WINDOW_DAYS)),
        )


def _parse_addresses(raw: str) -> tuple[str, ...]:
    seen: set[str] = set()
    addresses: list[str] = []
    for value in re.split(r"[,;]", raw or ""):
        address = value.strip()
        normalized = address.lower()
        if address and EMAIL_REGEX.fullmatch(address) and normalized not in seen:
            seen.add(normalized)
            addresses.append(address)
    return tuple(addresses)


def _value(record: Mapping[str, Any], *keys: str, default: Any = "") -> Any:
    for key in keys:
        value = record.get(key)
        if value is not None and value != "":
            return value
    return default


def _as_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().upper() in {"TRUE", "YES", "1", "VERIFIED", "PASS", "PASSED"}
    return bool(value)


def _parse_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        parsed = value
    elif value:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _sanitize_payload(payload: Any) -> Any:
    secrets: set[str] = set()

    def collect(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                if any(part in str(key).lower() for part in SENSITIVE_KEY_PARTS) and item:
                    secrets.add(str(item))
                collect(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                collect(item)

    collect(payload)

    def clean(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {
                str(key): "[REDACTED]" if any(part in str(key).lower() for part in SENSITIVE_KEY_PARTS) else clean(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [clean(item) for item in value]
        if isinstance(value, tuple):
            return tuple(clean(item) for item in value)
        if isinstance(value, str):
            sanitized = value
            for secret in secrets:
                sanitized = sanitized.replace(secret, "[REDACTED]")
            return sanitized
        return value

    return clean(payload)


class RediffSenderAdapter:
    """Validate and package a Salesoorja-qualified record for Rediff."""

    def __init__(
        self,
        config: Optional[RediffAdapterConfig] = None,
        now: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self.config = config or RediffAdapterConfig.from_settings()
        self._now = now or (lambda: datetime.now(timezone.utc))

    def _system_available(self) -> bool:
        path = self.config.system_path
        return bool(path and path.is_dir() and all((path / name).is_file() for name in REDIFF_ENTRYPOINTS))

    def system_available(self) -> bool:
        return self._system_available()

    def _result(self, status: str, reason: str, **extra: Any) -> dict[str, Any]:
        result = {
            "status": status,
            "reason": reason,
            "transport_called": False,
            "smtp_sent": False,
            "test_mode": self.config.test_mode,
        }
        result.update(extra)
        logger.info("Rediff handoff result status=%s", status)
        return result

    def _suppression_status(
        self,
        record: Mapping[str, Any],
        outreach_state: Mapping[str, Any],
        *,
        is_followup: bool = False,
    ) -> Optional[tuple[str, str]]:
        ready = str(_value(record, "READY_FOR_EMAIL", "ready_for_email", default="NO")).strip().upper()
        if ready != "YES":
            return SUPPRESSED_NOT_READY, "READY_FOR_EMAIL must be YES"

        pers_status = str(_value(record, "PERSONALIZATION_STATUS", "personalization_status", default="")).strip().upper()
        if pers_status in {"PERSONALIZATION_REVIEW_REQUIRED", "DISQUALIFIED_WRONG_FACILITY", "FAILED"}:
            return SUPPRESSED_NOT_READY, f"Personalization status '{pers_status}' requires human review before outreach"

        raw_score = _value(record, "PERSONALIZATION_SCORE", "quality_score", default=None)
        if raw_score is not None:
            try:
                if float(raw_score) < 85.0 and not self.config.test_mode:
                    return SUPPRESSED_NOT_READY, f"Personalization quality score ({raw_score}) is below production threshold (85.0)"
            except (ValueError, TypeError):
                pass

        provenance = str(_value(record, "provenance", "PROVENANCE", default="REAL")).strip().upper()
        if not self.config.test_mode and provenance in TEST_PROVENANCE:
            return SUPPRESSED_TEST_DATA, "Synthetic, mock, demo, or test records cannot enter production handoff"

        email_status = str(_value(outreach_state, "email_status", "status")).strip().upper()
        if _as_bool(_value(outreach_state, "bounced", default=False)) or outreach_state.get("bounced_at") or email_status == "BOUNCED":
            return SUPPRESSED_BOUNCE, "Recipient is marked bounced"
        if _as_bool(_value(outreach_state, "opted_out", "unsubscribed", default=False)) or email_status in {"OPTOUT", "OPTED_OUT", "UNSUBSCRIBED"}:
            return SUPPRESSED_OPTOUT, "Recipient is opted out or unsubscribed"

        reply_class = str(_value(outreach_state, "reply_classification", "reply_status")).strip().upper()
        meaningful_reply = _as_bool(_value(outreach_state, "meaningful_reply", default=False))
        if meaningful_reply or reply_class in STOP_REPLY_CLASSES or (outreach_state.get("replied_at") and reply_class != "OUT_OF_OFFICE"):
            return SUPPRESSED_REPLY, "Meaningful prior reply requires outreach stop"

        last_sent_at = _parse_datetime(outreach_state.get("last_sent_at"))
        is_followup_check = bool(
            is_followup
            or _as_bool(outreach_state.get("is_followup"))
            or _as_bool(record.get("is_followup"))
            or str(_value(record, "followup_stage", "FOLLOWUP_STAGE", default="INITIAL")).upper() != "INITIAL"
        )
        if not is_followup_check and last_sent_at and self._now().astimezone(timezone.utc) - last_sent_at < timedelta(days=self.config.duplicate_window_days):
            return SUPPRESSED_DUPLICATE, f"Recipient is inside the {self.config.duplicate_window_days}-day duplicate-contact window"
        return None

    def evaluate_suppression(
        self,
        record: Mapping[str, Any],
        outreach_state: Mapping[str, Any],
        *,
        is_followup: bool = False,
    ) -> dict[str, Any]:
        suppression = self._suppression_status(record, outreach_state, is_followup=is_followup)
        if suppression:
            status, reason = suppression
            return {"allowed": False, "status": status, "reason": reason}
        return {"allowed": True, "status": "CLEAR", "reason": "All duplicate, reply, opt-out, and bounce checks passed"}

    def _email_status(self, record: Mapping[str, Any]) -> Optional[tuple[str, str]]:
        email = str(_value(record, "EMAIL", "EMAIL_ID", "email")).strip()
        if not EMAIL_REGEX.fullmatch(email):
            return INVALID_EMAIL, "Recipient email has invalid syntax"
        local_part, domain = email.lower().split("@", 1)
        if local_part in ROLE_PREFIXES:
            return INVALID_EMAIL, "Recipient email must be person-specific, not role-based"
        if not self.config.test_mode and (domain in {"example.com", "example.org", "example.net"} or domain.endswith((".invalid", ".test"))):
            return INVALID_EMAIL, "Reserved test email domains cannot enter production handoff"
        return None

    def _qualification_status(self, record: Mapping[str, Any]) -> Optional[tuple[str, str, str]]:
        evidence = record.get("evidence") or record.get("EVIDENCE") or {}
        if not isinstance(evidence, Mapping):
            return SUPPRESSED_NOT_READY, "Qualification evidence is missing or invalid", "UNKNOWN"
        try:
            qualification = determine_qualification_state(
                dict(evidence),
                outbound_test_mode=self.config.test_mode,
                production_mode=not self.config.test_mode,
            )
        except (AttributeError, TypeError, ValueError):
            return SUPPRESSED_NOT_READY, "Qualification evidence is malformed", "UNKNOWN"
        if self.config.test_mode:
            allowed = qualification.can_stage_test
        else:
            allowed = qualification.can_send_production
        if not allowed:
            return SUPPRESSED_NOT_READY, qualification.reason, qualification.state.value
        return None

    def _map_record(
        self,
        record: Mapping[str, Any],
        *,
        campaign: str,
        followup_stage: str,
        message_id: str,
        in_reply_to: str,
        references: str,
    ) -> dict[str, Any]:
        company = str(_value(record, "COMPANY", "COMPANY_NAME", "company"))
        contact = str(_value(record, "CONTACT_NAME", "CONTACT_PERSON", "person", "contact_name"))
        first_name = str(_value(record, "FIRST_NAME", "first_name", default=(contact.split()[0] if contact else "")))
        email = str(_value(record, "EMAIL", "EMAIL_ID", "email"))
        phone = str(_value(record, "PHONE", "CONTACT_NUMBER", "phone", default="NOT_FOUND"))
        city = str(_value(record, "CITY", "city"))
        state = str(_value(record, "STATE", "state"))
        facility = str(_value(record, "FACILITY", "facility"))
        trigger = str(_value(record, "TRIGGER_EVENT", "TRIGGER", "trigger"))
        opportunity = str(_value(record, "CALIBRATION_OPPORTUNITY", "CALIBRATION_CATEGORY", "calibration_opportunity"))
        reasoning = str(_value(record, "REASON_FOR_OUTREACH", "reasoning", "WHY_CALIBRATION_NOW"))
        score = _value(record, "LEAD_SCORE", "SCORE", "lead_score", "icp_score", default="")
        evidence = record.get("evidence") or record.get("EVIDENCE") or {}
        facility_evidence = evidence.get("exact_facility") if isinstance(evidence, Mapping) else {}
        contact_evidence = evidence.get("reachable_email") if isinstance(evidence, Mapping) else {}
        facility_verified = _as_bool(
            _value(record, "FACILITY_VERIFIED", "facility_verified", default=(facility_evidence or {}).get("verified", False))
        )
        contact_verified = _as_bool(
            _value(record, "CONTACT_VERIFIED", "contact_verified", default=(contact_evidence or {}).get("mailbox_verified", False))
        )
        subject = str(_value(record, "FINAL_SUBJECT", "SUBJECT", "subject", default=""))
        body_html = str(_value(record, "FINAL_BODY_HTML", "BODY_HTML", "body_html", default=""))
        body_text = str(_value(record, "FINAL_BODY_TEXT", "BODY_TEXT", "body_text", default=""))
        mapped = {
            "LEAD_ID": str(_value(record, "LEAD_ID", "record_id", default=f"salesoorja-{uuid.uuid4().hex[:12]}")),
            "COMPANY_NAME": company,
            "COMPANY": company,
            "FACILITY": facility,
            "LOCATION": str(_value(record, "LOCATION", "contact_location", default=", ".join(v for v in (city, state) if v))),
            "CITY": city,
            "STATE": state,
            "SCORE": score,
            "LEAD_SCORE": score,
            "OPPORTUNITY_CLASS": str(_value(record, "OPPORTUNITY_CLASS", "opportunity_class")),
            "DEMAND_EVENT": trigger,
            "WHY_CALIBRATION_NOW": reasoning,
            "EXTERNAL_PROVIDER_REASON": str(_value(record, "EXTERNAL_PROVIDER_REASON", "external_provider_reason")),
            "VENDOR_INCUMBENCY": str(_value(record, "VENDOR_INCUMBENCY", "vendor_incumbency")),
            "CONTACT_PERSON": contact,
            "CONTACT_NAME": contact,
            "FIRST_NAME": first_name,
            "DESIGNATION": str(_value(record, "DESIGNATION", "designation")),
            "CONTACT_NUMBER": phone,
            "PHONE": phone,
            "EMAIL_ID": email,
            "EMAIL": email,
            "PERSONA": str(_value(record, "PERSONA", "persona")),
            "BUYING_WINDOW": str(_value(record, "BUYING_WINDOW", "buying_window")),
            "PREMIUM_POTENTIAL": str(_value(record, "PREMIUM_POTENTIAL", "premium_potential")),
            "EARLY_ENTRY": str(_value(record, "EARLY_ENTRY", "early_entry")),
            "CONFIDENCE": str(_value(record, "CONFIDENCE", "confidence")),
            "OUTREACH_STATUS": "READY_FOR_EMAIL",
            "NEXT_RESEARCH_ACTION": "",
            "READY_FOR_EMAIL": "YES",
            "TRIGGER": trigger,
            "TRIGGER_EVENT": trigger,
            "TRIGGER_DATE": str(_value(record, "TRIGGER_DATE", "trigger_date")),
            "CALIBRATION_CATEGORY": opportunity,
            "CALIBRATION_OPPORTUNITY": opportunity,
            "REASON_FOR_OUTREACH": reasoning,
            "FACILITY_VERIFIED": facility_verified,
            "CONTACT_VERIFIED": contact_verified,
            "CONTACT_LOCATION": str(_value(record, "CONTACT_LOCATION", "contact_location", default=facility)),
            "NOTES": str(_value(record, "NOTES", "notes")),
            "CAMPAIGN": campaign,
            "FOLLOWUP_STAGE": followup_stage,
            "MESSAGE_ID": message_id,
            "IN_REPLY_TO": in_reply_to,
            "REFERENCES": references,
            "CC": ", ".join(self.config.cc_addresses),
            "SALESOORJA_RECORD_ID": str(_value(record, "record_id", "SALESOORJA_RECORD_ID")),
            "SUBJECT": subject,
            "FINAL_SUBJECT": subject,
            "BODY_HTML": body_html,
            "FINAL_BODY_HTML": body_html,
            "BODY_TEXT": body_text,
            "FINAL_BODY_TEXT": body_text,
        }
        return {field: mapped[field] for field in REDIFF_CSV_FIELDS}

    def prepare_handoff(
        self,
        record: Mapping[str, Any],
        *,
        outreach_state: Optional[Mapping[str, Any]] = None,
        campaign: str = "",
        followup_stage: str = "INITIAL",
        message_id: str = "",
        in_reply_to: str = "",
        references: str = "",
        attachments: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Apply Salesoorja gates and return a dry-run or queued file handoff."""
        if not self.config.enabled and not self.config.test_mode:
            return self._result(FAILED, "REDIFF_SENDER_DISABLED")
        if not self.config.test_mode and not self._system_available():
            return self._result(FAILED, "REDIFF_SYSTEM_UNAVAILABLE")
        if attachments:
            return self._result(FAILED, "ATTACHMENTS_UNSUPPORTED_BY_CURRENT_REDIFF_TRANSPORT")

        suppression = self._suppression_status(record, outreach_state or {})
        if suppression:
            return self._result(*suppression)
        email_status = self._email_status(record)
        if email_status:
            return self._result(*email_status)
        qualification_status = self._qualification_status(record)
        if qualification_status:
            status, reason, qualification_state = qualification_status
            return self._result(status, reason, qualification_state=qualification_state)

        mapped = self._map_record(
            record,
            campaign=campaign,
            followup_stage=followup_stage,
            message_id=message_id,
            in_reply_to=in_reply_to,
            references=references,
        )
        qualification_state = determine_qualification_state(
            dict(record.get("evidence") or record.get("EVIDENCE") or {}),
            outbound_test_mode=self.config.test_mode,
            production_mode=not self.config.test_mode,
        ).state.value

        if self.config.test_mode:
            return self._result(
                DRY_RUN_READY,
                "Salesoorja gates passed; no Rediff process or SMTP connection invoked",
                qualification_state=qualification_state,
                mapped_record=mapped,
                cc=list(self.config.cc_addresses),
            )

        handoff_id = f"rediff-handoff-{uuid.uuid4().hex[:12]}"
        handoff_path = self.config.handoff_dir / f"{handoff_id}.csv"
        try:
            self.config.handoff_dir.mkdir(parents=True, exist_ok=True)
            with handoff_path.open("x", newline="", encoding="utf-8-sig") as handle:
                writer = csv.DictWriter(handle, fieldnames=REDIFF_CSV_FIELDS)
                writer.writeheader()
                writer.writerow(mapped)
        except OSError:
            return self._result(FAILED, "REDIFF_HANDOFF_WRITE_FAILED")
        return self._result(
            QUEUED,
            "Qualified record written to controlled Rediff CSV handoff; sending still requires separate authorization",
            qualification_state=qualification_state,
            handoff_id=handoff_id,
            handoff_path=str(handoff_path),
            mapped_record=mapped,
            cc=list(self.config.cc_addresses),
        )

    def normalize_transport_result(self, receipt: Mapping[str, Any]) -> dict[str, Any]:
        """Normalize a Rediff transport receipt without ever assuming delivery."""
        clean = _sanitize_payload(dict(receipt))
        status = str(_value(clean, "status", "smtp_result", default="FAILED")).strip().upper()
        success = _as_bool(clean.get("success"))
        error = str(_value(clean, "failure_reason", "error", default=""))
        if success and status in {"SENT", "SUCCESS", "SENT_SUCCESSFULLY"}:
            normalized = SENT
        elif status in {"421", "TEMPORARY_FAILURE", "DEFERRED"} or "421" in error:
            normalized = TEMPORARY_FAILURE
        else:
            normalized = FAILED
        return {
            "status": normalized,
            "lead_id": _value(clean, "lead_id", "LEAD_ID"),
            "recipient": _value(clean, "recipient", "email", "EMAIL"),
            "timestamp": _value(clean, "timestamp", "sent_at"),
            "message_id": _value(clean, "message_id", "Message-ID"),
            "campaign": _value(clean, "campaign", "CAMPAIGN"),
            "retry_count": int(_value(clean, "retry_count", "attempt", default=0) or 0),
            "failure_reason": error,
            "smtp_accepted": normalized == SENT,
            "delivery_verified": False,
            "raw": clean,
        }


rediff_sender_adapter = RediffSenderAdapter()
