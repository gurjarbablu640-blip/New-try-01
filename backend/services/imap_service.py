"""IMAP Inbound Processing Service with thread matching, bounce/reply detection, and CRM activity logging."""
import email
from email.header import decode_header
import imaplib
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from config import settings
from models.activity import CRMActivity
from models.campaign import Campaign, CampaignEvent, CampaignRecipient
from models.company import Company
from models.person import Person
from services.deduplication import extract_domain, normalize_email
from services.reply_classifier import classify_reply_intent

logger = logging.getLogger(__name__)


def clean_header_str(val: Any) -> str:
    """Safely decode MIME header string."""
    if not val:
        return ""
    decoded_fragments = decode_header(str(val))
    parts = []
    for fragment, encoding in decoded_fragments:
        if isinstance(fragment, bytes):
            try:
                parts.append(fragment.decode(encoding or "utf-8", errors="replace"))
            except Exception:
                parts.append(fragment.decode("latin1", errors="replace"))
        else:
            parts.append(str(fragment))
    return " ".join(parts).strip()


def extract_email_from_header(header_val: str) -> str:
    """Extract clean email address from 'Name <email@domain.com>' format."""
    match = re.search(r"[\w\.-]+@[\w\.-]+", header_val)
    return match.group(0).lower() if match else header_val.strip().lower()


def match_incoming_thread(
    db: Session,
    headers: Dict[str, str],
    from_email: str,
    subject: str,
) -> Tuple[Optional[CampaignRecipient], Optional[Company], Optional[Person], Optional[CampaignEvent]]:
    """
    Multi-tier thread matching:
    1. In-Reply-To / References matching against CampaignEvent.provider_message_id
    2. Custom X-Oorja-Recipient-ID header
    3. From email match against Person.normalized_email in active campaign recipients
    4. Domain match against Company.domain in active campaign recipients
    """
    in_reply_to = headers.get("in-reply-to") or headers.get("In-Reply-To")
    references = headers.get("references") or headers.get("References")
    recipient_id_hdr = headers.get("x-oorja-recipient-id") or headers.get("X-Oorja-Recipient-ID")

    # Priority 1: Match In-Reply-To against prior sent CampaignEvent
    target_ids = []
    if in_reply_to:
        target_ids.append(in_reply_to.strip())
    if references:
        for ref in references.split():
            target_ids.append(ref.strip())

    for tid in target_ids:
        evt = (
            db.query(CampaignEvent)
            .filter(CampaignEvent.provider_message_id == tid)
            .order_by(CampaignEvent.id.desc())
            .first()
        )
        if evt:
            recipient = db.query(CampaignRecipient).filter(CampaignRecipient.id == evt.recipient_id).first()
            if recipient:
                company = db.query(Company).filter(Company.id == recipient.company_id).first()
                person = db.query(Person).filter(Person.id == recipient.person_id).first() if recipient.person_id else None
                return recipient, company, person, evt

    # Priority 2: Match X-Oorja-Recipient-ID header
    if recipient_id_hdr and recipient_id_hdr.isdigit():
        recipient = db.query(CampaignRecipient).filter(CampaignRecipient.id == int(recipient_id_hdr)).first()
        if recipient:
            company = db.query(Company).filter(Company.id == recipient.company_id).first()
            person = db.query(Person).filter(Person.id == recipient.person_id).first() if recipient.person_id else None
            return recipient, company, person, None

    # Priority 3: Match from_email against Person
    norm_from = normalize_email(from_email)
    if norm_from:
        person = db.query(Person).filter(Person.normalized_email == norm_from).first()
        if person:
            # Find most recent campaign recipient for this person
            recipient = (
                db.query(CampaignRecipient)
                .filter(CampaignRecipient.person_id == person.id)
                .order_by(CampaignRecipient.id.desc())
                .first()
            )
            company = db.query(Company).filter(Company.id == person.company_id).first()
            if recipient:
                return recipient, company, person, None

    # Priority 4: Match sender domain against Company domain
    domain = extract_domain(from_email)
    if domain:
        company = db.query(Company).filter(Company.domain == domain).first()
        if company:
            recipient = (
                db.query(CampaignRecipient)
                .filter(CampaignRecipient.company_id == company.id)
                .order_by(CampaignRecipient.id.desc())
                .first()
            )
            return recipient, company, None, None

    return None, None, None, None


def process_incoming_email(db: Session, email_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process an incoming parsed email dict:
    - Matches thread / recipient / company
    - Classifies intent (reply vs bounce vs interested)
    - Updates campaign recipient status
    - Records CampaignEvent & CRMActivity
    """
    from_raw = email_data.get("from", "")
    from_email = extract_email_from_header(from_raw)
    subject = email_data.get("subject", "")
    body = email_data.get("body", "")
    headers = email_data.get("headers", {})
    message_id = email_data.get("message_id") or headers.get("message-id", "")

    # Classify intent
    classification = classify_reply_intent(subject=subject, body=body, from_email=from_email)
    category = classification["category"]

    # Match thread
    recipient, company, person, matched_event = match_incoming_thread(
        db=db,
        headers=headers,
        from_email=from_email,
        subject=subject,
    )

    now = datetime.now(timezone.utc)
    res_status = "unmatched"

    if recipient:
        res_status = "matched"
        campaign_id = recipient.campaign_id

        if category == "BOUNCE":
            recipient.bounced_at = now
            recipient.status = "Bounced"
            recipient.email_status = "Bounced"
            if company:
                company.bounced_email = True
            if person:
                person.email_verification_status = "bounced"
                person.email_verification_reason = f"Bounce detected: {subject}"

            event = CampaignEvent(
                campaign_id=campaign_id,
                recipient_id=recipient.id,
                event_type="bounced",
                channel="email",
                provider_message_id=message_id,
                payload={
                    "from": from_email,
                    "subject": subject,
                    "classification": classification,
                },
            )
            db.add(event)

            crm_act = CRMActivity(
                company_id=recipient.company_id,
                activity_type="Email Bounced",
                status="Completed",
                contact_person=person.full_name if person else (company.contact_person if company else None),
                email=from_email,
                remarks=f"Email bounced for {from_email}: {subject}",
            )
            db.add(crm_act)

        else:
            # Valid reply (INTERESTED, REQUESTING_QUOTE, OBJECTION, NOT_INTERESTED, etc.)
            recipient.replied_at = now
            recipient.status = "Replied"
            recipient.email_status = "Replied"
            if company:
                company.reply_received = True
                company.lead_status = "Replied"

            event = CampaignEvent(
                campaign_id=campaign_id,
                recipient_id=recipient.id,
                event_type="replied",
                channel="email",
                provider_message_id=message_id,
                payload={
                    "from": from_email,
                    "subject": subject,
                    "classification": classification,
                },
            )
            db.add(event)

            crm_act = CRMActivity(
                company_id=recipient.company_id,
                activity_type="Email Reply Received",
                status="Completed",
                contact_person=person.full_name if person else (company.contact_person if company else None),
                email=from_email,
                phone=person.phone if person else (company.phone if company else None),
                division=company.division if company else None,
                remarks=f"[{category}] {subject} - {classification.get('summary', '')}",
            )
            db.add(crm_act)

            # Auto-create or link Opportunity for interested replies
            if category in ["INTERESTED", "REQUESTING_QUOTE", "MEETING_REQUESTED"] and recipient.company_id:
                from models.sales_os import Opportunity
                existing_opp = db.query(Opportunity).filter(
                    Opportunity.company_id == recipient.company_id,
                    Opportunity.stage.notin_(["Won", "Lost"]),
                ).first()

                if not existing_opp:
                    new_opp = Opportunity(
                        company_id=recipient.company_id,
                        person_id=recipient.person_id,
                        name=f"Inbound Calibration Interest — {company.name if company else from_email}",
                        stage="Qualified" if category == "INTERESTED" else "Proposal",
                        probability=50.0 if category == "INTERESTED" else 75.0,
                        estimated_value=25000.0,
                        source="Outbound Campaign",
                        ai_summary=classification.get("summary") or f"Auto-created from {category} reply to campaign #{campaign_id}",
                    )
                    db.add(new_opp)

        db.commit()

    return {
        "status": res_status,
        "from_email": from_email,
        "subject": subject,
        "classification": classification,
        "recipient_id": recipient.id if recipient else None,
        "company_id": company.id if company else None,
        "company_name": company.name if company else None,
    }


def poll_imap_inbox(db: Session, folder: str = "INBOX", limit: int = 50) -> Dict[str, Any]:
    """
    Connect to IMAP server, fetch unseen messages, parse and process them.
    In mock / unconfigured mode, returns clean empty report.
    """
    if not settings.IMAP_HOST or settings.IMAP_HOST.strip() == "":
        logger.info("[MOCK IMAP] IMAP host not configured. Running in mock polling mode.")
        return {
            "status": "ok",
            "mock_mode": True,
            "messages_checked": 0,
            "processed_results": [],
        }

    try:
        if settings.IMAP_USE_SSL:
            mail = imaplib.IMAP4_SSL(settings.IMAP_HOST, settings.IMAP_PORT)
        else:
            mail = imaplib.IMAP4(settings.IMAP_HOST, settings.IMAP_PORT)

        if settings.IMAP_USER and settings.IMAP_PASSWORD:
            mail.login(settings.IMAP_USER, settings.IMAP_PASSWORD)

        mail.select(folder)
        _, data = mail.search(None, "UNSEEN")
        mail_ids = data[0].split()

        processed_results = []
        for mid in mail_ids[-limit:]:
            _, msg_data = mail.fetch(mid, "(RFC822)")
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    subject = clean_header_str(msg.get("Subject"))
                    from_hdr = clean_header_str(msg.get("From"))
                    msg_id = clean_header_str(msg.get("Message-ID"))
                    in_reply_to = clean_header_str(msg.get("In-Reply-To"))
                    references = clean_header_str(msg.get("References"))

                    # Body extraction
                    body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            ctype = part.get_content_type()
                            if ctype == "text/plain":
                                body = part.get_payload(decode=True).decode("utf-8", errors="replace")
                                break
                    else:
                        body = msg.get_payload(decode=True).decode("utf-8", errors="replace")

                    headers_dict = {
                        "in-reply-to": in_reply_to,
                        "references": references,
                        "message-id": msg_id,
                        "x-oorja-recipient-id": clean_header_str(msg.get("X-Oorja-Recipient-ID")),
                    }

                    parsed_email = {
                        "from": from_hdr,
                        "subject": subject,
                        "body": body,
                        "message_id": msg_id,
                        "headers": headers_dict,
                    }

                    res = process_incoming_email(db, parsed_email)
                    processed_results.append(res)

        mail.close()
        mail.logout()
        return {
            "status": "ok",
            "mock_mode": False,
            "messages_checked": len(mail_ids),
            "processed_results": processed_results,
        }
    except Exception as exc:
        logger.error(f"IMAP polling error: {exc}")
        return {
            "status": "error",
            "error": str(exc),
            "mock_mode": False,
            "messages_checked": 0,
            "processed_results": [],
        }
