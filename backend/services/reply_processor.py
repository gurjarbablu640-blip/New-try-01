"""Reply Processing and Classification Engine for Matched Outreach.

Operates exclusively on replies already verified and collected by the
restricted inbox layer.

Classifies incoming messages into 12 canonical intent categories:
- ENQUIRY
- INTERESTED
- REFERRAL
- FUTURE_REQUIREMENT
- NO_CURRENT_REQUIREMENT
- EXISTING_VENDOR
- OBJECTION
- NOT_INTERESTED
- OUT_OF_OFFICE
- BOUNCE
- WRONG_PERSON
- IRRELEVANT

Stores classification with concrete evidence snippets and feeds outcomes into
the Salesoorja learning and history engine.
"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

CANONICAL_CLASSIFICATIONS = (
    "ENQUIRY",
    "INTERESTED",
    "REFERRAL",
    "FUTURE_REQUIREMENT",
    "NO_CURRENT_REQUIREMENT",
    "EXISTING_VENDOR",
    "OBJECTION",
    "NOT_INTERESTED",
    "OUT_OF_OFFICE",
    "BOUNCE",
    "WRONG_PERSON",
    "IRRELEVANT",
)

CLASSIFICATION_ALIASES = {
    "EXISTING_VENDOR_OBJECTION": "EXISTING_VENDOR",
}

STORAGE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "reply_history")


@dataclass
class ReplyClassificationResult:
    classification: str
    confidence: float
    evidence_snippet: str
    reasons: List[str]
    referral_person: Optional[str] = None
    referral_email: Optional[str] = None
    referral_phone: Optional[str] = None
    timeline_mention: Optional[str] = None
    feed_to_learning: bool = True
    learning_signal: str = "NEUTRAL"  # POSITIVE, NEGATIVE, NEUTRAL
    classified_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    record_id: str = field(default_factory=lambda: f"reply-cls-{uuid.uuid4().hex[:10]}")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ReplyProcessor:
    """Classifies matched outreach email responses and coordinates learning feedback."""

    def __init__(self, storage_dir: str = STORAGE_DIR):
        self.storage_dir = storage_dir
        os.makedirs(self.storage_dir, exist_ok=True)
        self.history_file = os.path.join(self.storage_dir, "classified_replies.json")

    def _load_history(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self.history_file):
            return []
        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            logger.error("Failed to load reply history: %s", exc)
            return []

    def _save_history(self, records: List[Dict[str, Any]]) -> None:
        temp_file = f"{self.history_file}.tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2)
        os.replace(temp_file, self.history_file)

    def classify_reply(
        self,
        reply_packet: Dict[str, Any],
        outreach_context: Optional[Dict[str, Any]] = None,
    ) -> ReplyClassificationResult:
        """Classify a matched reply into one of 12 categories with evidence."""
        subject = str(reply_packet.get("subject") or "").strip()
        body = str(reply_packet.get("body") or "").strip()
        sender = str(reply_packet.get("from") or "").strip()
        content = f"{subject}\n{body}".lower()
        body_lower = body.lower()

        # 1. BOUNCE check (Mail Delivery Subsystem, undeliverable, 550, bounce)
        if (
            "mailer-daemon" in sender.lower()
            or "postmaster@" in sender.lower()
            or "mail delivery failed" in content
            or "undeliverable" in content
            or "recipient address rejected" in content
            or "550 user not found" in content
        ):
            snippet = self._extract_snippet(body or subject, ["undeliverable", "failed", "rejected", "550", "daemon"])
            return ReplyClassificationResult(
                classification="BOUNCE",
                confidence=0.98,
                evidence_snippet=snippet,
                reasons=["Automated bounce message / mail delivery subsystem failure"],
                feed_to_learning=True,
                learning_signal="NEGATIVE",
            )

        # 2. OUT_OF_OFFICE check
        if (
            "out of office" in content
            or "automatic reply" in content
            or "auto-reply" in content
            or "on annual leave" in content
            or "i am away from" in content
            or "back in office on" in content
        ):
            snippet = self._extract_snippet(body or subject, ["out of office", "automatic reply", "away", "leave", "back on"])
            return ReplyClassificationResult(
                classification="OUT_OF_OFFICE",
                confidence=0.95,
                evidence_snippet=snippet,
                reasons=["Automated out-of-office autoreply detected"],
                feed_to_learning=False,
                learning_signal="NEUTRAL",
            )

        # 3. NOT_INTERESTED check ("unsubscribe", "not interested", "remove me", "do not email", "stop emailing")
        # Evaluated early to ensure opt-outs take precedence over thread subject words
        if (
            "not interested" in content
            or "unsubscribe" in content
            or "remove me" in content
            or "do not email" in content
            or "stop emailing" in content
            or "please remove" in content
        ):
            snippet = self._extract_snippet(body, ["not interested", "unsubscribe", "remove", "stop"])
            return ReplyClassificationResult(
                classification="NOT_INTERESTED",
                confidence=0.95,
                evidence_snippet=snippet,
                reasons=["Explicit opt-out or lack of interest requested"],
                feed_to_learning=True,
                learning_signal="NEGATIVE",
            )

        # 4. WRONG_PERSON ("i do not handle", "not my department", "left the company", "wrong person")
        if (
            "not my department" in content
            or "wrong person" in content
            or "do not handle" in content
            or "no longer with" in content
            or "left the company" in content
            or "not involved in calibration" in content
        ):
            snippet = self._extract_snippet(body, ["not my department", "wrong person", "do not handle", "no longer", "left"])
            return ReplyClassificationResult(
                classification="WRONG_PERSON",
                confidence=0.90,
                evidence_snippet=snippet,
                reasons=["Recipient indicates functional role mismatch or departure"],
                feed_to_learning=True,
                learning_signal="NEGATIVE",
            )

        # 5. REFERRAL check ("contact Mr. X", "talk to", "forwarding to", "please reach out to")
        referral_match = re.search(
            r"(?:please\s+contact|talk\s+to|reach\s+out\s+to|connect\s+with|forwarding\s+to)\s+(?:(?:mr|ms|mrs|dr)\.?\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
            body,
            re.IGNORECASE,
        )
        email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", body)
        phone_match = re.search(r"(?:\+91|0)?[6-9]\d{9}", body)

        if referral_match or ("forwarded to" in content and email_match):
            ref_name = referral_match.group(1).strip() if referral_match else None
            ref_email = email_match.group(0).strip() if email_match else None
            ref_phone = phone_match.group(0).strip() if phone_match else None
            snippet = self._extract_snippet(body, ["contact", "reach out", "talk to", "forwarding", "connect with"])
            return ReplyClassificationResult(
                classification="REFERRAL",
                confidence=0.92,
                evidence_snippet=snippet,
                reasons=["Lead referred outreach to an internal colleague or manager"],
                referral_person=ref_name,
                referral_email=ref_email,
                referral_phone=ref_phone,
                feed_to_learning=True,
                learning_signal="POSITIVE",
            )

        # 6. OBJECTION ("too expensive", "your lab is too far", "turnaround time", "only accept on-site")
        # Evaluated before enquiry keywords to prevent "Your quotes are too expensive" becoming ENQUIRY
        if (
            "expensive" in body_lower
            or "too far" in body_lower
            or "turnaround time" in body_lower
            or "on-site only" in body_lower
            or "scope does not cover" in body_lower
        ):
            snippet = self._extract_snippet(body, ["expensive", "far", "turnaround", "on-site", "scope"])
            return ReplyClassificationResult(
                classification="OBJECTION",
                confidence=0.85,
                evidence_snippet=snippet,
                reasons=["Specific commercial, geographical, or accreditation objection raised"],
                feed_to_learning=True,
                learning_signal="NEGATIVE",
            )

        # 7. EXISTING_VENDOR ("already have a vendor", "annual contract", "under amc", "existing agency")
        if (
            "already have a vendor" in content
            or "existing vendor" in content
            or "under amc" in content
            or "annual contract" in content
            or "already tied up" in content
            or "current service provider" in content
        ):
            snippet = self._extract_snippet(body, ["already", "amc", "contract", "vendor", "tied up", "provider"])
            return ReplyClassificationResult(
                classification="EXISTING_VENDOR",
                confidence=0.91,
                evidence_snippet=snippet,
                reasons=["Recipient has an active vendor contract or AMC in place"],
                feed_to_learning=True,
                learning_signal="NEGATIVE",
            )

        # 8. NO_CURRENT_REQUIREMENT ("no requirement right now", "no requirement at present", "currently not required")
        if (
            "no requirement" in content
            or "not required currently" in content
            or "not needed right now" in content
            or "no calibration needs currently" in content
        ):
            snippet = self._extract_snippet(body, ["no requirement", "not required", "not needed"])
            return ReplyClassificationResult(
                classification="NO_CURRENT_REQUIREMENT",
                confidence=0.88,
                evidence_snippet=snippet,
                reasons=["No immediate need, but no hostility or permanent opt-out expressed"],
                feed_to_learning=True,
                learning_signal="NEUTRAL",
            )

        # 9. FUTURE_REQUIREMENT ("next quarter", "next shutdown", "after december", "reach out in", "next year")
        future_terms = ["next quarter", "next month", "next year", "next shutdown", "after march", "after december", "contact us in", "reach out in"]
        if any(term in content for term in future_terms):
            snippet = self._extract_snippet(body, future_terms)
            timeline = next((t for t in future_terms if t in content), "future")
            return ReplyClassificationResult(
                classification="FUTURE_REQUIREMENT",
                confidence=0.88,
                evidence_snippet=snippet,
                reasons=["Recipient indicated future calibration requirement or timing window"],
                timeline_mention=timeline,
                feed_to_learning=True,
                learning_signal="POSITIVE",
            )

        # 10. ENQUIRY ("send quote", "quote for", "quotation", "scope of calibration", "what is your rate", "pricing for")
        if (
            "send" in body_lower and ("quote" in body_lower or "quotation" in body_lower or "rate" in body_lower)
            or "quotation for" in body_lower
            or "quote for" in body_lower
            or "pricing" in body_lower
            or "rate list" in body_lower
            or "scope of accreditation" in body_lower
            or "calibration charges" in body_lower
            or "rfq" in body_lower
            or ("quote" in body_lower and "please" in body_lower)
        ):
            snippet = self._extract_snippet(body, ["quote", "quotation", "pricing", "rate", "scope", "charges", "rfq"])
            return ReplyClassificationResult(
                classification="ENQUIRY",
                confidence=0.94,
                evidence_snippet=snippet,
                reasons=["Direct commercial inquiry or quotation request received"],
                feed_to_learning=True,
                learning_signal="POSITIVE",
            )

        # 11. INTERESTED ("call me", "let's discuss", "send brochure", "schedule a meeting", "available on tuesday")
        if (
            "call me" in content
            or "discuss" in content
            or "send brochure" in content
            or "schedule a meeting" in content
            or "schedule a call" in content
            or "interested" in content
            or "share presentation" in content
            or "visit our plant" in content
        ):
            snippet = self._extract_snippet(body, ["call", "discuss", "brochure", "schedule", "interested", "presentation", "visit"])
            return ReplyClassificationResult(
                classification="INTERESTED",
                confidence=0.92,
                evidence_snippet=snippet,
                reasons=["Prospect expressed affirmative interest in discussion or capabilities"],
                feed_to_learning=True,
                learning_signal="POSITIVE",
            )


        # 12. Default: IRRELEVANT
        snippet = (body[:200] if body else subject[:100]).strip()
        return ReplyClassificationResult(
            classification="IRRELEVANT",
            confidence=0.60,
            evidence_snippet=snippet,
            reasons=["Message content does not match any operational calibration sales categories"],
            feed_to_learning=False,
            learning_signal="NEUTRAL",
        )

    def process_and_store(
        self,
        reply_packet: Dict[str, Any],
        outreach_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Classify reply, persist record with evidence, and return outcome summary."""
        result = self.classify_reply(reply_packet, outreach_context)
        record = {
            "record_id": result.record_id,
            "message_id": reply_packet.get("message_id", ""),
            "from": reply_packet.get("from", ""),
            "subject": reply_packet.get("subject", ""),
            "classification": result.classification,
            "confidence": result.confidence,
            "evidence_snippet": result.evidence_snippet,
            "reasons": result.reasons,
            "referral_person": result.referral_person,
            "referral_email": result.referral_email,
            "referral_phone": result.referral_phone,
            "timeline_mention": result.timeline_mention,
            "learning_signal": result.learning_signal,
            "classified_at": result.classified_at,
            "outreach_context": outreach_context or {},
        }

        history = self._load_history()
        history.append(record)
        self._save_history(history)

        logger.info(
            "Processed reply from %s: Classified as %s (Signal: %s)",
            record["from"],
            record["classification"],
            record["learning_signal"],
        )

        return {
            "status": "classified",
            "record": record,
            "learning_signal": result.learning_signal,
            "feedback_applied": result.feed_to_learning,
        }

    def _extract_snippet(self, text: str, keywords: List[str]) -> str:
        """Extract a 150-char window containing the matching keyword."""
        lower = text.lower()
        for kw in keywords:
            idx = lower.find(kw.lower())
            if idx != -1:
                start = max(0, idx - 40)
                end = min(len(text), idx + len(kw) + 80)
                snippet = text[start:end].replace("\n", " ").strip()
                return f"...{snippet}..." if start > 0 else f"{snippet}..."
        return (text[:150] + "...") if len(text) > 150 else text


# Global instance
reply_processor = ReplyProcessor()
