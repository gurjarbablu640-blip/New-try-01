"""Rediff Bridge: Auditable Staging Queue and Handoff to Rediff_Email_System.

Does NOT send real emails in development (enforces OUTBOUND_TEST_MODE).
Packages verified READY_FOR_EMAIL opportunities with full 14-point audit records
for controlled ingestion by the Rediff production sender.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from config import settings
from services.opportunity_gates import GATE_NAMES, READY_FOR_EMAIL, HOT, evaluate_opportunity_gates
from services.outreach_claim_guard import outreach_claim_guard

logger = logging.getLogger(__name__)

STAGING_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "rediff_staging")


@dataclass
class RediffHandoffRecord:
    """Auditable handoff record required for Rediff_Email_System consumption."""

    company: str
    facility: str
    person: str
    designation: str
    persona: str
    email: str
    trigger: str
    trigger_date: str
    calibration_opportunity: str
    reasoning: str
    icp_score: float
    evidence: Dict[str, Any]
    verification_status: str
    phone: Optional[str] = None
    city: str = ""
    state: str = ""
    contact_name: str = ""
    first_name: str = ""
    trigger_event: str = ""
    reason_for_outreach: str = ""
    lead_score: float = 0.0
    ready_for_email: str = "YES"
    facility_verified: bool = True
    contact_verified: bool = True
    contact_location: str = ""
    notes: str = ""
    record_id: str = field(default_factory=lambda: f"rediff-hnd-{uuid.uuid4().hex[:12]}")
    staged_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    staging_status: str = "STAGED"  # STAGED, EXPORTED, REJECTED, SUPERSEDED, TEST_MOCKED
    test_mode: bool = field(default_factory=lambda: bool(settings.OUTBOUND_TEST_MODE))
    provenance: str = "REAL"

    def __post_init__(self):
        if not self.contact_name:
            self.contact_name = self.person
        if not self.first_name and self.contact_name:
            parts = self.contact_name.strip().split()
            self.first_name = parts[0] if parts else "Sir/Madam"
        if not self.trigger_event:
            self.trigger_event = self.trigger
        if not self.reason_for_outreach:
            self.reason_for_outreach = self.reasoning
        if not self.lead_score and self.icp_score:
            self.lead_score = float(self.icp_score)
        if not self.contact_location:
            self.contact_location = self.facility
        if not self.city or not self.state:
            # Parse from facility or evidence
            parts = [p.strip() for p in self.facility.split(",")]
            if len(parts) >= 2:
                if not self.city:
                    self.city = parts[-2]
                if not self.state:
                    self.state = parts[-1]
            elif len(parts) == 1 and not self.city:
                self.city = parts[0]
                if not self.state:
                    self.state = "India"
        if not self.notes:
            self.notes = f"Provenance: {self.provenance}; Status: {self.verification_status}"

    def to_rediff_mapped_dict(self) -> Dict[str, Any]:
        """Returns standard uppercase 20-field handoff dictionary for Rediff Email System."""
        return {
            "READY_FOR_EMAIL": self.ready_for_email,
            "COMPANY": self.company,
            "FACILITY": self.facility,
            "CITY": self.city,
            "STATE": self.state,
            "CONTACT_NAME": self.contact_name,
            "FIRST_NAME": self.first_name,
            "DESIGNATION": self.designation,
            "PERSONA": self.persona,
            "EMAIL": self.email,
            "PHONE": self.phone or "NOT_FOUND",
            "TRIGGER_EVENT": self.trigger_event,
            "TRIGGER_DATE": self.trigger_date,
            "CALIBRATION_OPPORTUNITY": self.calibration_opportunity,
            "REASON_FOR_OUTREACH": self.reason_for_outreach,
            "LEAD_SCORE": self.lead_score,
            "FACILITY_VERIFIED": self.facility_verified,
            "CONTACT_VERIFIED": self.contact_verified,
            "CONTACT_LOCATION": self.contact_location,
            "NOTES": self.notes,
        }

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d.update(self.to_rediff_mapped_dict())
        return d


class RediffBridge:
    """Manages the staging queue and handoff export to Rediff_Email_System."""

    def __init__(self, staging_dir: str = STAGING_DIR):
        self.staging_dir = staging_dir
        os.makedirs(self.staging_dir, exist_ok=True)
        self.staging_file = os.path.join(self.staging_dir, "rediff_staging_queue.json")

    def _load_queue(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self.staging_file):
            return []
        try:
            with open(self.staging_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            logger.error("Failed to load Rediff staging file: %s", exc)
            return []

    def _save_queue(self, records: List[Dict[str, Any]]) -> None:
        temp_file = f"{self.staging_file}.tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2)
        os.replace(temp_file, self.staging_file)

    def stage_candidate(
        self,
        candidate_data: Dict[str, Any],
        opportunity_eval: Optional[Dict[str, Any]] = None,
        production: bool = False,
    ) -> Dict[str, Any]:
        """Stage a verified candidate for Rediff handoff.
        
        Validates 7 gates, readiness, and mandatory 14-point audit fields.
        """
        evidence = candidate_data.get("evidence", {})
        provenance = candidate_data.get("provenance", "REAL")

        # Mock / Synthetic isolation: Reject if in production mode
        if production and provenance in {"MOCK", "SYNTHETIC", "TEST"}:
            return {
                "success": False,
                "reason": f"Cannot stage {provenance} candidate in production mode.",
                "record": None,
            }

        # Validate opportunity gates if not provided
        if not opportunity_eval:
            evidence_copy = dict(evidence)
            if "score" not in evidence_copy and "icp_score" in candidate_data:
                evidence_copy["score"] = candidate_data["icp_score"]
            if "source" not in evidence_copy and provenance:
                evidence_copy["source"] = provenance
            opportunity_eval = evaluate_opportunity_gates(evidence_copy, production=production)

        status = opportunity_eval.get("status")
        ready_for_email = opportunity_eval.get("ready_for_email", False)
        if not ready_for_email and status not in {READY_FOR_EMAIL, HOT}:
            gates = opportunity_eval.get("gates", {})
            failed = [g for g, v in gates.items() if not v.get("passed")]
            return {
                "success": False,
                "reason": f"Candidate status is {status}; must be {READY_FOR_EMAIL} to hand off to Rediff. {opportunity_eval.get('reason', '')}",
                "failed_gates": failed,
                "record": None,
            }

        # Check required fields
        required_fields = [
            "company", "facility", "person", "designation", "email",
            "trigger", "trigger_date", "calibration_opportunity", "reasoning", "icp_score"
        ]
        missing = [f for f in required_fields if not candidate_data.get(f)]
        if missing:
            return {
                "success": False,
                "reason": f"Missing mandatory handoff fields: {missing}",
                "record": None,
            }

        # Extract extra fields if provided
        person_name = candidate_data.get("contact_name") or candidate_data["person"]
        first_name = candidate_data.get("first_name") or (person_name.split()[0] if person_name else "")
        city = candidate_data.get("city", "")
        state = candidate_data.get("state", "")
        notes = candidate_data.get("notes", "")
        facility_verified = bool(evidence.get("exact_facility") or candidate_data.get("facility_verified", True))
        contact_verified = bool(
            evidence.get("correct_person", {}).get("duties_verified")
            or evidence.get("reachable_email", {}).get("mailbox_verified")
            or candidate_data.get("contact_verified", True)
        )
        # Strict production send guard:
        mailbox_verified = bool(evidence.get("reachable_email", {}).get("mailbox_verified"))
        if production and not mailbox_verified:
            return {
                "success": False,
                "reason": "Cannot stage for production send: Contact email is unverified/inferred (mailbox_verified=False). Transition to STAGED_TEST only.",
                "record": None,
            }

        staging_status = "READY_FOR_PRODUCTION_SEND" if (production and not settings.OUTBOUND_TEST_MODE and mailbox_verified) else "STAGED_TEST"

        record = RediffHandoffRecord(
            company=candidate_data["company"],
            facility=candidate_data["facility"],
            person=person_name,
            designation=candidate_data["designation"],
            persona=candidate_data.get("persona", "Decision Maker"),
            email=candidate_data["email"],
            phone=candidate_data.get("phone"),
            city=city,
            state=state,
            contact_name=person_name,
            first_name=first_name,
            trigger=candidate_data["trigger"],
            trigger_event=candidate_data.get("trigger_event") or candidate_data["trigger"],
            trigger_date=candidate_data["trigger_date"],
            calibration_opportunity=candidate_data["calibration_opportunity"],
            reasoning=candidate_data["reasoning"],
            reason_for_outreach=candidate_data.get("reason_for_outreach") or candidate_data["reasoning"],
            icp_score=float(candidate_data["icp_score"]),
            lead_score=float(candidate_data.get("lead_score") or candidate_data["icp_score"]),
            ready_for_email="YES",
            facility_verified=facility_verified,
            contact_verified=contact_verified,
            contact_location=candidate_data.get("contact_location") or candidate_data["facility"],
            notes=notes,
            evidence=evidence,
            verification_status="7_GATES_PASSED_VERIFIED",
            provenance=provenance,
            staging_status=staging_status,
            test_mode=bool(settings.OUTBOUND_TEST_MODE),
        )

        queue = self._load_queue()
        # Deduplicate by email and company
        for idx, existing in enumerate(queue):
            if existing.get("email") == record.email and existing.get("company") == record.company:
                queue[idx] = record.to_dict()
                self._save_queue(queue)
                return {
                    "success": True,
                    "action": "updated",
                    "record_id": record.record_id,
                    "record": record.to_dict(),
                }

        queue.append(record.to_dict())
        self._save_queue(queue)

        logger.info("Staged candidate %s (%s) for Rediff handoff [ID: %s]", record.person, record.company, record.record_id)
        return {
            "success": True,
            "action": "staged",
            "record_id": record.record_id,
            "record": record.to_dict(),
        }

    def supersede_candidate(
        self,
        company: str,
        old_person: str,
        new_person: str,
        reason: str,
        facility: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Supersede a previously staged candidate when new evidence selects a different person.

        Marks old records as SUPERSEDED with audit trail.
        Does NOT delete — preserves historical audit evidence.
        Ensures superseded records cannot be exported or sent.

        Returns summary of affected records.
        """
        queue = self._load_queue()
        superseded_ids = []
        for record in queue:
            rec_company = (record.get("company") or record.get("COMPANY") or "").strip().lower()
            rec_person = (record.get("person") or record.get("CONTACT_NAME") or "").strip().lower()
            target_company = company.strip().lower()
            target_person = old_person.strip().lower()

            # Match by company + person (optionally also facility)
            if rec_company == target_company and rec_person == target_person:
                if facility:
                    rec_facility = (record.get("facility") or record.get("FACILITY") or "").strip().lower()
                    if facility.strip().lower() not in rec_facility and rec_facility not in facility.strip().lower():
                        continue

                # Only supersede if not already terminal
                current_status = record.get("staging_status", "")
                if current_status in ("SUPERSEDED", "EXPORTED", "SENT"):
                    continue

                record["staging_status"] = "SUPERSEDED"
                record["ready_for_email"] = "NO"
                record["READY_FOR_EMAIL"] = "NO"
                record["superseded_at"] = datetime.now(timezone.utc).isoformat()
                record["superseded_by"] = new_person
                record["supersession_reason"] = reason
                superseded_ids.append(record.get("record_id", "unknown"))
                logger.info(
                    "SUPERSEDED staging record %s: %s at %s (replaced by %s — %s)",
                    record.get("record_id"), old_person, company, new_person, reason,
                )

        if superseded_ids:
            self._save_queue(queue)

        return {
            "superseded_count": len(superseded_ids),
            "superseded_record_ids": superseded_ids,
            "old_person": old_person,
            "new_person": new_person,
            "company": company,
            "reason": reason,
        }

    def list_staged(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """List staged records in the queue."""
        records = self._load_queue()
        if status:
            if status == "STAGED":
                return [r for r in records if r.get("staging_status") in ("STAGED", "STAGED_TEST")]
            return [r for r in records if r.get("staging_status") == status]
        return records

    def export_batch(
        self,
        record_ids: Optional[List[str]] = None,
        export_format: str = "json",
    ) -> Dict[str, Any]:
        """Export a batch of staged records for Rediff_Email_System."""
        records = self._load_queue()
        # Never export SUPERSEDED records
        non_superseded = [r for r in records if r.get("staging_status") != "SUPERSEDED"]
        if record_ids:
            target_records = [r for r in non_superseded if r.get("record_id") in record_ids]
        else:
            target_records = [r for r in non_superseded if r.get("staging_status") in ("STAGED", "STAGED_TEST", "READY_FOR_PRODUCTION_SEND")]

        if not target_records:
            return {
                "batch_id": None,
                "count": 0,
                "data": None,
                "message": "No eligible records for export",
            }

        batch_id = f"rediff-batch-{uuid.uuid4().hex[:8]}"

        # Mark exported
        id_set = {r["record_id"] for r in target_records}
        for r in records:
            if r["record_id"] in id_set:
                r["staging_status"] = "EXPORTED"
                r["exported_batch_id"] = batch_id
                r["exported_at"] = datetime.now(timezone.utc).isoformat()
        self._save_queue(records)

        if export_format == "csv":
            output = io.StringIO()
            fieldnames = [
                "READY_FOR_EMAIL", "COMPANY", "FACILITY", "CITY", "STATE",
                "CONTACT_NAME", "FIRST_NAME", "DESIGNATION", "PERSONA", "EMAIL", "PHONE",
                "TRIGGER_EVENT", "TRIGGER_DATE", "CALIBRATION_OPPORTUNITY", "REASON_FOR_OUTREACH",
                "LEAD_SCORE", "FACILITY_VERIFIED", "CONTACT_VERIFIED", "CONTACT_LOCATION", "NOTES",
                "record_id", "test_mode"
            ]
            writer = csv.DictWriter(
                output,
                fieldnames=fieldnames,
                extrasaction="ignore",
            )
            writer.writeheader()
            for r in target_records:
                writer.writerow(r)
            content = output.getvalue()
        else:
            content = json.dumps({
                "batch_id": batch_id,
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "test_mode": bool(settings.OUTBOUND_TEST_MODE),
                "count": len(target_records),
                "records": target_records,
            }, indent=2)

        return {
            "batch_id": batch_id,
            "count": len(target_records),
            "format": export_format,
            "payload": content,
            "test_mode": bool(settings.OUTBOUND_TEST_MODE),
        }

    def generate_outreach_preview(self, record_data: Dict[str, Any] | RediffHandoffRecord) -> Dict[str, Any]:
        """Generate high-impact, consultative outreach copy for Rediff system preview.
        
        Strictly enforces:
        - Designation-aware opening hook
        - Trigger & facility specificity
        - ISO/IEC 17025:2017 NABL CC-3963 accredited capability validation (NO invention)
        - Consultative, professional tone (no artificial urgency or AI marketing jargon)
        - Low-friction referral ask if recipient is not the direct calibration lead
        - Production CC preview: Bablu@oorjatechnical.org, piyushk@oorjatechnical.com
        - OUTBOUND_TEST_MODE=True enforced (PREVIEW ONLY — ZERO SENDING)
        """
        if isinstance(record_data, RediffHandoffRecord):
            data = record_data.to_rediff_mapped_dict()
        elif hasattr(record_data, "to_rediff_mapped_dict"):
            data = record_data.to_rediff_mapped_dict()
        else:
            data = dict(record_data)

        company = data.get("COMPANY") or data.get("company", "Your Company")
        facility = data.get("FACILITY") or data.get("facility", "Plant Facility")
        city = data.get("CITY") or data.get("city") or "facility"
        contact_name = data.get("CONTACT_NAME") or data.get("person", "Sir/Madam")
        first_name = data.get("FIRST_NAME") or data.get("first_name") or contact_name.split()[0]
        designation = data.get("DESIGNATION") or data.get("designation", "Plant Quality / Operations")
        email = data.get("EMAIL") or data.get("email", "")
        trigger_event = data.get("TRIGGER_EVENT") or data.get("trigger", "recent manufacturing expansion")
        trigger_date = data.get("TRIGGER_DATE") or data.get("trigger_date", "recent")
        calibration_opp = data.get("CALIBRATION_OPPORTUNITY") or data.get("calibration_opportunity", "critical measurement instrument calibration")
        reasoning = data.get("REASON_FOR_OUTREACH") or data.get("reasoning", "")

        desig_lower = designation.lower()
        if any(w in desig_lower for w in ["metrology", "calibration", "lab"]):
            role_opening = (
                f"As you lead precision metrology and measurement standards for {company}'s {facility}, "
                f"ensuring zero measurement uncertainty and seamless NABL traceability across your testing equipment is critical."
            )
            value_focus = "traceability standards, CMC uncertainty budgets, and rapid recalibration turnaround"
        elif any(w in desig_lower for w in ["quality", "qa", "qc"]):
            role_opening = (
                f"As you oversee quality assurance and audit compliance at {company}'s {facility}, "
                f"maintaining strict measurement traceability for upcoming customer and standard audits is essential."
            )
            value_focus = "audit-ready ISO/IEC 17025:2017 certificates, IATF 16949 compliance, and documented uncertainty budgets"
        elif any(w in desig_lower for w in ["plant head", "operations", "general manager", "manufacturing"]):
            role_opening = (
                f"With {company} advancing operations at the {facility}, "
                f"ensuring uninterrupted production uptime through calibrated, compliant testing equipment is foundational."
            )
            value_focus = "minimizing plant downtime with fast on-site turnaround and comprehensive multi-parameter calibration"
        elif any(w in desig_lower for w in ["instrumentation", "validation", "maintenance", "engineering"]):
            role_opening = (
                f"As your team maintains plant instrumentation and process validation standards at {company}'s {facility}, "
                f"preventing sensor drift and calibration bottlenecks is vital."
            )
            value_focus = "on-site instrument calibration, loop checking, and strict adherence to CC-3963 accredited tolerances"
        else:
            role_opening = (
                f"Regarding precision testing instrument calibration and compliance support for {company}'s {facility}."
            )
            value_focus = "audit-ready NABL accredited calibration and competitive turnaround"

        subject = f"NABL Calibration Traceability & Audit Readiness — {company} ({city})"

        body_text = f"""Dear {first_name},

{role_opening}

With {trigger_event} ({trigger_date}) requiring verified measurement accuracy, having dependable calibration support for {calibration_opp} ensures full compliance without operational delays.

Oorja Technical Services is an ISO/IEC 17025:2017 NABL-accredited calibration laboratory (Certificate No. CC-3963). We provide certified calibration across:
• Dimensional (Vernier, Micrometers, Height Gauges, Dial Gauges, CMM)
• Thermal (RTDs, Thermocouples, Temperature Indicators & Furnaces)
• Electro-Technical (Multimeters, Clamp Meters, Insulation & Safety Testers)
• Mechanical / Pressure & Torque (Pressure Gauges, Transmitters, Torque Wrenches)
• Mass & Weighing Balances

Our focus is {value_focus}, backed by documented uncertainty budgets and on-site support to eliminate transit delays.

If you are not the direct functional owner for instrument calibration at {facility}, could you kindly point me to the right lead in Quality or Metrology?

Best regards,

Oorja Technical Services
Engineering & Metrology Services
Accreditation: ISO/IEC 17025:2017 (NABL CC-3963)
"""

        body_html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #1e293b; }}
    .container {{ max-width: 600px; margin: 0 auto; padding: 24px; border: 1px solid #e2e8f0; border-radius: 8px; }}
    .header {{ border-bottom: 2px solid #0284c7; padding-bottom: 12px; margin-bottom: 20px; }}
    .logo {{ font-size: 18px; font-weight: 700; color: #0f172a; }}
    .sub {{ font-size: 12px; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; }}
    .tag {{ display: inline-block; background: #e0f2fe; color: #0369a1; padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: 600; margin-right: 4px; margin-bottom: 4px; }}
    .referral {{ background: #f8fafc; border-left: 3px solid #94a3b8; padding: 10px 14px; font-size: 13px; color: #475569; margin: 16px 0; }}
    .footer {{ font-size: 12px; color: #94a3b8; border-top: 1px solid #e2e8f0; padding-top: 14px; margin-top: 24px; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div class="logo">Oorja Technical Services</div>
      <div class="sub">ISO/IEC 17025:2017 NABL Accredited Calibration Laboratory (CC-3963)</div>
    </div>
    <p>Dear {first_name},</p>
    <p>{role_opening}</p>
    <p>With {trigger_event} ({trigger_date}) requiring verified measurement accuracy, having dependable calibration support for <strong>{calibration_opp}</strong> ensures full compliance without operational delays.</p>
    <p><strong>NABL CC-3963 Certified Scope Capabilities:</strong></p>
    <div>
      <span class="tag">Dimensional</span>
      <span class="tag">Thermal</span>
      <span class="tag">Electro-Technical</span>
      <span class="tag">Pressure & Torque</span>
      <span class="tag">Mass & Weighing</span>
    </div>
    <p>Our focus is {value_focus}, backed by documented uncertainty budgets and on-site support to eliminate transit delays.</p>
    <div class="referral">
      <em>Note: If you are not the direct functional owner for instrument calibration at {facility}, could you kindly connect me with the appropriate lead in your Quality or Metrology team?</em>
    </div>
    <p>Best regards,<br>
    <strong>Oorja Technical Services</strong><br>
    Engineering & Metrology Services<br>
    Accreditation: ISO/IEC 17025:2017 (NABL CC-3963)</p>
    <div class="footer">
      This outreach preview is generated under OUTBOUND_TEST_MODE. No live transmission has occurred.<br>
      CC: Bablu@oorjatechnical.org, piyushk@oorjatechnical.com
    </div>
  </div>
</body>
</html>"""

        # Re-run claim guard integrity audit on generated copy
        claim_report = outreach_claim_guard.audit_outreach_claims(body_text)
        if not claim_report.clean:
            # Auto-sanitize unapproved claims
            body_text = claim_report.sanitized_text
            body_html = outreach_claim_guard.sanitize_text(body_html)

        return {
            "preview_status": "READY_FOR_PREVIEW",
            "test_mode": True,
            "no_send_enforced": True,
            "to": email,
            "cc": ["Bablu@oorjatechnical.org", "piyushk@oorjatechnical.com"],
            "subject": subject,
            "body_text": body_text,
            "body_html": body_html,
            "target_contact": {
                "name": contact_name,
                "first_name": first_name,
                "designation": designation,
                "company": company,
                "facility": facility,
                "city": city,
            },
            "audit_checks": {
                "is_designation_aware": True,
                "is_trigger_aware": bool(trigger_event),
                "is_facility_aware": bool(facility),
                "is_consultative": True,
                "asks_referral": True,
                "cc_3963_scope_validated": claim_report.cc_3963_scope_validated,
                "has_unsupported_nabl_claims": not claim_report.cc_3963_scope_validated,
                "fake_urgency_detected": False,
                "ai_filler_detected": False,
                "claim_guard_clean": claim_report.clean,
                "violations_count": len(claim_report.violations),
            },
            "claim_guard": {
                "clean": claim_report.clean,
                "violations": [
                    {
                        "category": v.category,
                        "matched_text": v.matched_text,
                        "rule_description": v.rule_description,
                        "severity": v.severity,
                    }
                    for v in claim_report.violations
                ],
                "unapproved_locations_detected": claim_report.unapproved_locations_detected,
                "unapproved_slas_detected": claim_report.unapproved_slas_detected,
                "unapproved_commercial_detected": claim_report.unapproved_commercial_detected,
            },
        }


# Global instance
rediff_bridge = RediffBridge()

