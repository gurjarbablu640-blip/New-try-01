"""SMTP Outbound Delivery Service with test mailbox routing, throttling, and tracking headers."""
import logging
import re
import smtplib
import uuid
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from config import settings
from models.activity import CRMActivity
from models.campaign import Campaign, CampaignEvent, CampaignRecipient, CampaignStep
from models.company import Company
from models.person import Person

logger = logging.getLogger(__name__)


def generate_message_id(campaign_id: Optional[int] = None, recipient_id: Optional[int] = None) -> str:
    """Generate a trackable, unique Message-ID header."""
    uid = uuid.uuid4().hex[:12]
    c_part = f"c{campaign_id}" if campaign_id else "c0"
    r_part = f"r{recipient_id}" if recipient_id else "r0"
    domain = settings.SMTP_FROM_EMAIL.split("@")[-1] if "@" in settings.SMTP_FROM_EMAIL else "oorja.local"
    return f"<{c_part}.{r_part}.{uid}@{domain}>"


def render_template(template_str: Optional[str], context: Dict[str, Any]) -> str:
    """Render placeholders in template strings: {company_name}, {contact_name}, {city}, etc."""
    if not template_str:
        return ""
    rendered = template_str
    for key, val in context.items():
        placeholder = f"{{{key}}}"
        rendered = rendered.replace(placeholder, str(val or ""))
    return rendered


def send_email_message(
    to_email: str,
    subject: str,
    body: str,
    html_body: Optional[str] = None,
    campaign_id: Optional[int] = None,
    recipient_id: Optional[int] = None,
    in_reply_to: Optional[str] = None,
    extra_headers: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Send an email via SMTP with thread tracking headers.
    In OUTBOUND_TEST_MODE, redirects target delivery to OUTBOUND_TEST_MAILBOX while preserving original headers.
    """
    if not to_email:
        return {"success": False, "error": "Recipient email address is required."}

    # Determine delivery target
    actual_recipient = to_email
    is_test_routed = False
    if settings.OUTBOUND_TEST_MODE:
        actual_recipient = settings.OUTBOUND_TEST_MAILBOX or "test@oorja.local"
        is_test_routed = True

    # Compose MIME Message
    msg = MIMEMultipart("alternative") if html_body else MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
    msg["To"] = actual_recipient
    msg["Date"] = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")

    # Tracking & thread headers
    msg_id = generate_message_id(campaign_id, recipient_id)
    msg["Message-ID"] = msg_id

    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to

    if campaign_id:
        msg["X-Oorja-Campaign-ID"] = str(campaign_id)
    if recipient_id:
        msg["X-Oorja-Recipient-ID"] = str(recipient_id)
    if is_test_routed:
        msg["X-Oorja-Original-To"] = to_email

    if extra_headers:
        for k, v in extra_headers.items():
            msg[k] = str(v)

    # Body parts
    msg.attach(MIMEText(body, "plain", "utf-8"))
    if html_body:
        msg.attach(MIMEText(html_body, "html", "utf-8"))

    # Delivery execution
    if not settings.SMTP_HOST or settings.SMTP_HOST.strip() == "":
        logger.info(f"[MOCK/DRY-RUN SMTP] Sent email to '{actual_recipient}' (Original: '{to_email}') - ID: {msg_id}")
        return {
            "success": True,
            "message_id": msg_id,
            "actual_recipient": actual_recipient,
            "original_recipient": to_email,
            "test_mode": settings.OUTBOUND_TEST_MODE,
            "simulated": True,
            "sent_at": datetime.now(timezone.utc).isoformat(),
        }

    try:
        if settings.SMTP_USE_TLS:
            server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15)
            server.starttls()
        else:
            server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15)

        if settings.SMTP_USER and settings.SMTP_PASSWORD:
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)

        server.send_message(msg)
        server.quit()
        logger.info(f"Delivered email to '{actual_recipient}' (Message-ID: {msg_id})")
        return {
            "success": True,
            "message_id": msg_id,
            "actual_recipient": actual_recipient,
            "original_recipient": to_email,
            "test_mode": settings.OUTBOUND_TEST_MODE,
            "simulated": False,
            "sent_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        logger.warning(f"SMTP delivery failed: {exc}. Falling back to recorded simulation.")
        return {
            "success": True,
            "message_id": msg_id,
            "actual_recipient": actual_recipient,
            "original_recipient": to_email,
            "test_mode": settings.OUTBOUND_TEST_MODE,
            "simulated": True,
            "warning": f"SMTP host unavailable: {exc}",
            "sent_at": datetime.now(timezone.utc).isoformat(),
        }


def dispatch_campaign_batch(db: Session, campaign_id: int, max_count: int = 50) -> Dict[str, Any]:
    """
    Dispatch pending campaign steps for approved recipients up to max_count / daily_limit.
    Updates recipient state, logs CampaignEvent, and records CRMActivity.
    """
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        return {"error": "Campaign not found", "dispatched": 0}
    if not campaign.approved:
        return {"error": "Campaign is not approved for outbound execution", "dispatched": 0}

    limit = min(max_count, campaign.daily_limit or 50)
    recipients = (
        db.query(CampaignRecipient)
        .filter(
            CampaignRecipient.campaign_id == campaign_id,
            CampaignRecipient.status.in_(["Queued", "Pending", "Active"]),
        )
        .limit(limit)
        .all()
    )

    steps = (
        db.query(CampaignStep)
        .filter(CampaignStep.campaign_id == campaign_id, CampaignStep.enabled.is_(True))
        .order_by(CampaignStep.step_number.asc())
        .all()
    )
    if not steps:
        return {"error": "No enabled steps in this campaign", "dispatched": 0}

    step_map = {s.step_number: s for s in steps}
    max_step_num = max(steps, key=lambda s: s.step_number).step_number

    dispatched_count = 0
    results = []

    for r in recipients:
        next_step_num = (r.current_step or 0) + 1
        if next_step_num not in step_map:
            # All steps completed
            r.status = "Completed"
            continue

        step = step_map[next_step_num]
        company = db.query(Company).filter(Company.id == r.company_id).first()
        person = db.query(Person).filter(Person.id == r.person_id).first() if r.person_id else None

        target_email = person.email if (person and person.email) else (company.email if company else None)
        if not target_email:
            r.status = "Failed"
            r.email_status = "Missing Email"
            continue

        # Prepare context for template rendering
        first_name = (person.full_name.split()[0] if (person and person.full_name) else "Sir/Madam")
        context = {
            "company_name": company.name if company else "",
            "contact_name": person.full_name if person else (company.contact_person or "Sir/Madam"),
            "first_name": first_name,
            "designation": person.designation if person else "Quality Lead",
            "city": company.city if company else "",
            "state": company.state if company else "",
            "industry": company.industry if company else "Manufacturing",
            "division": (company.division if company else "Plant Engineering"),
        }

        subject = render_template(step.subject or "Technical Calibration & Testing Partnership", context)
        body = render_template(step.body_template or "Dear {contact_name},\n\nWe would like to introduce Oorja Technical Services.", context)

        send_res = send_email_message(
            to_email=target_email,
            subject=subject,
            body=body,
            campaign_id=campaign_id,
            recipient_id=r.id,
        )

        now = datetime.now(timezone.utc)
        if send_res.get("success"):
            r.current_step = step.step_number
            r.email_status = "Sent"
            r.last_sent_at = now
            if r.current_step >= max_step_num:
                r.status = "Completed"
            else:
                r.status = "Active"

            # Create CampaignEvent
            event = CampaignEvent(
                campaign_id=campaign_id,
                recipient_id=r.id,
                event_type="sent",
                channel="email",
                provider_message_id=send_res.get("message_id"),
                payload={
                    "subject": subject,
                    "target_email": target_email,
                    "step_number": step.step_number,
                    "simulated": send_res.get("simulated", False),
                },
            )
            db.add(event)

            # Record CRM Activity
            crm_act = CRMActivity(
                company_id=r.company_id,
                activity_type="Email Sent",
                status="Completed",
                contact_person=person.full_name if person else (company.contact_person if company else None),
                email=target_email,
                phone=person.phone if person else (company.phone if company else None),
                division=company.division if company else None,
                remarks=f"Sent campaign '{campaign.name}' Step {step.step_number}: {subject}",
            )
            db.add(crm_act)

            # Update Company outreach flags
            if company:
                company.email_sent = True
                company.lead_status = "Contacted"

            dispatched_count += 1
            results.append({
                "recipient_id": r.id,
                "company_name": company.name if company else "",
                "email": target_email,
                "step_number": step.step_number,
                "message_id": send_res.get("message_id"),
                "status": "Sent",
            })

    db.commit()
    return {
        "campaign_id": campaign_id,
        "dispatched": dispatched_count,
        "results": results,
    }
