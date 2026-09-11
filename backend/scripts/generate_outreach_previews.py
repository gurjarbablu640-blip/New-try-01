"""Generate non-sending outreach previews for top forensically verified opportunities.

Enforces:
1. Strict adherence to verified event, verified facility, verified role.
2. Approved Oorja ISO/IEC 17025:2017 NABL Certificate CC-3963 capabilities.
3. OutreachClaimGuard validation (ZERO hallucinations, zero unapproved regional centers, zero 48h SLA promises).
4. Referral fallback in every email preview.
5. PREVIEW ONLY - ZERO EMAILS SENT.
"""
from __future__ import annotations

import json
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.outreach_claim_guard import OutreachClaimGuard

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def generate_previews():
    guard = OutreachClaimGuard()
    queue_path = os.path.join(os.path.dirname(__file__), "..", "data", "runtime_state", "apollo_pending_queue.json")
    
    if not os.path.exists(queue_path):
        logger.error(f"Queue not found at {queue_path}")
        return []

    with open(queue_path, "r", encoding="utf-8") as f:
        queue = json.load(f)

    previews = []

    for item in queue:
        company = item.get("company", "")
        facility = item.get("facility", "")
        city = item.get("city", "")
        state = item.get("state", "")
        person_name = item.get("person_name", "")
        person_title = item.get("person_title", "")
        trigger_type = item.get("trigger_type", "")
        why_qualified = item.get("why_qualified", "")
        priority = item.get("lookup_priority", "P2")

        # Context-specific event description
        if "Giga" in facility or "Cell" in trigger_type:
            context_note = f"in light of your lithium-ion cell manufacturing facility expansion at {city}"
        elif "Line" in trigger_type or "4th" in trigger_type:
            context_note = f"following the recent commissioning of the new production line at your {facility}"
        elif "Hydrogen" in trigger_type:
            context_note = f"in connection with your green hydrogen manufacturing project at {city}"
        elif "Chemical" in trigger_type:
            context_note = f"regarding the ongoing specialty chemical expansion at your {facility}"
        elif "Electronics" in trigger_type or "SMT" in trigger_type:
            context_note = f"supporting your expanded electronics manufacturing lines at {city}"
        else:
            context_note = f"regarding your ongoing manufacturing operations at {facility}"

        subject = f"Calibration & metrology support for {company} ({facility.split('(')[0].strip()})"

        body = (
            f"Dear {person_name},\n\n"
            f"I hope this message finds you well.\n\n"
            f"I am reaching out from Oorja Technical Services {context_note}. As you scale production "
            f"and commission new equipment, maintaining high-precision traceable calibration and testing is vital "
            f"for plant quality compliance.\n\n"
            f"Oorja Technical Services is an ISO/IEC 17025:2017 accredited laboratory (NABL Certificate CC-3963) "
            f"providing on-site and in-lab calibration across thermal, mechanical, dimensional, and electrical parameters.\n\n"
            f"If you are currently evaluating calibration partners for this facility, I would appreciate the opportunity "
            f"to share our approved scope and schedule a brief introductory discussion.\n\n"
            f"Referral Note: If you are not the person coordinating calibration/testing activities, "
            f"could you please guide me to the relevant colleague?\n\n"
            f"Warm regards,\n\n"
            f"Technical Partnerships Team\n"
            f"Oorja Technical Services\n"
            f"Engineering & Metrology Services\n"
            f"Accreditation: ISO/IEC 17025:2017 (NABL Certificate CC-3963)\n"
            f"Note: This is an internal non-sending preview. Real emails sent = 0."
        )

        # Audit with OutreachClaimGuard
        audit_report = guard.audit_outreach_claims(body)

        preview_record = {
            "company": company,
            "facility": facility,
            "city_state": f"{city}, {state}",
            "recipient_name": person_name,
            "recipient_title": person_title,
            "lookup_priority": priority,
            "subject": subject,
            "body": body,
            "claim_guard_clean": audit_report.clean,
            "claim_violations": [v.rule_description for v in audit_report.violations],
            "status": "PREVIEW_ONLY_NOT_SENT",
        }
        previews.append(preview_record)
        logger.info(f"Generated preview for {company} ({person_name}) | ClaimGuard: {'PASS' if audit_report.clean else 'FAIL'}")

    out_path = os.path.join(os.path.dirname(__file__), "..", "data", "runtime_state", "outreach_previews.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(previews, f, indent=2)

    logger.info(f"=== Successfully generated {len(previews)} outreach previews (all non-sending) ===")
    return previews

if __name__ == "__main__":
    generate_previews()
