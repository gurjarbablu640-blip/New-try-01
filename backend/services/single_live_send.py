"""Strictly bounded one-customer live-send preparation and execution."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

from sqlalchemy.orm import Session

from config import settings
from models.campaign import Campaign, CampaignEvent, CampaignRecipient, CampaignStep
from models.company import Company
from models.decision_maker_candidate import DecisionMakerCandidate
from models.intent_signal import CompanyIntentSignal
from models.person import Person
from services.deduplication import normalize_email
from services.rediff_sender_adapter import QUEUED, RediffAdapterConfig, RediffSenderAdapter
from services.rediff_transport_bridge import (
    SINGLE_LIVE_AUTHORIZATION,
    SINGLE_LIVE_TEST_TYPE,
    SUPPRESSED_DUPLICATE_TRANSPORT,
    TEST_RECIPIENT,
    RediffTransportBridge,
)
from services.sales_personalization import SalesPersonalizationPipeline


BACKEND_ROOT = Path(__file__).resolve().parent.parent
LIVE_CAMPAIGN_REFERENCE = "salesoorja-single-live-customer-test"
STRONG_FUNCTIONS = {
    "DIRECT_CALIBRATION_OWNER",
    "METROLOGY_OWNER",
    "STRONG_PLANT_QUALITY_OWNER",
    "FACILITY_OWNER",
    "GROUP_FUNCTION_OWNER",
}
TEST_COMPANY_SOURCES = {"mock", "demo", "test", "synthetic"}


class SingleLiveSendBlocked(RuntimeError):
    """Raised when any required safety gate blocks the operation."""


class SingleLiveSendService:
    def __init__(
        self,
        *,
        settings_obj: Any = settings,
        personalization: Optional[SalesPersonalizationPipeline] = None,
        transport_bridge: Optional[RediffTransportBridge] = None,
        operator_obj: Any = None,
        now: Any = None,
    ) -> None:
        self.settings = settings_obj
        self.personalization = personalization or SalesPersonalizationPipeline()
        self.transport_bridge = transport_bridge or RediffTransportBridge()
        self.operator = operator_obj
        self._now = now or (lambda: datetime.now(timezone.utc))

    def list_candidates(self, db: Session) -> dict[str, Any]:
        candidates = (
            db.query(DecisionMakerCandidate)
            .order_by(DecisionMakerCandidate.score_composite.desc(), DecisionMakerCandidate.id.desc())
            .all()
        )
        eligible = []
        for candidate in candidates:
            try:
                context = self._candidate_context(db, candidate)
                self._assert_no_prior_send(db, context)
                personalized = self._salesoorja_personalization(context["record"])
                self._assert_suppression_clear(db, context, personalized)
            except (SingleLiveSendBlocked, KeyError, TypeError, ValueError):
                continue
            eligible.append(self._candidate_summary(context, personalized))
        return {
            "results": eligible,
            "total": len(eligible),
            "max_prospect_recipients": 1,
            "cc": [TEST_RECIPIENT],
            "bcc": [],
            "mass_production_enabled": bool(getattr(self.settings, "REAL_OUTREACH_ENABLED", False)),
            "followups_enabled": False,
            "real_send_available": self._live_send_available(),
        }

    def preview(self, db: Session, candidate_id: int) -> dict[str, Any]:
        context, personalized, receipt = self._prepare_preview(db, candidate_id)
        rediff_preview = receipt.get("preview") or {}
        token = self._preview_token(candidate_id, context["email"], rediff_preview)
        return {
            **self._candidate_summary(context, personalized),
            "subject": rediff_preview.get("subject"),
            "body_html": rediff_preview.get("body_html"),
            "personalization_score": rediff_preview.get("personalization_score"),
            "research_score": rediff_preview.get("research_score"),
            "claim_validation": rediff_preview.get("claim_validation"),
            "preview_token": token,
            "confirmation_required": SINGLE_LIVE_AUTHORIZATION,
            "confirmation_text": (
                f"This will send one real email to:\n{context['email']}\n\n"
                f"CC:\n{TEST_RECIPIENT}\n\nNo other recipients."
            ),
            "max_prospect_recipients": 1,
            "cc": [TEST_RECIPIENT],
            "bcc": [],
            "mass_production_enabled": bool(getattr(self.settings, "REAL_OUTREACH_ENABLED", False)),
            "followups_enabled": False,
            "real_send_available": self._live_send_available(),
        }

    def send(
        self,
        db: Session,
        *,
        candidate_id: int,
        confirmation: str,
        preview_token: str,
    ) -> dict[str, Any]:
        if confirmation != SINGLE_LIVE_AUTHORIZATION:
            raise PermissionError("SINGLE_LIVE_CONFIRMATION_REQUIRED")
        if not bool(getattr(self.settings, "SINGLE_LIVE_CUSTOMER_TEST_ENABLED", False)):
            raise PermissionError("SINGLE_LIVE_CUSTOMER_TEST_DISABLED")
        if bool(getattr(self.settings, "REAL_OUTREACH_ENABLED", False)):
            raise PermissionError("MASS_PRODUCTION_MUST_REMAIN_DISABLED")
        operator = self._operator()
        if operator and operator.get_status().get("status") in {"RUNNING", "WAITING", "STOPPING"}:
            raise SingleLiveSendBlocked("OPERATOR_RUN_ALREADY_ACTIVE")

        context, personalized, preview_receipt = self._prepare_preview(db, candidate_id)
        rediff_preview = preview_receipt.get("preview") or {}
        expected_token = self._preview_token(candidate_id, context["email"], rediff_preview)
        if not preview_token or preview_token != expected_token:
            raise PermissionError("CURRENT_PREVIEW_CONFIRMATION_REQUIRED")
        self._assert_no_prior_send(db, context)

        campaign, recipient = self._create_pending_receipt(db, context, rediff_preview)
        run_id = f"single-live-{uuid.uuid4().hex[:12]}"
        receipts = operator.get_transport_receipts() if operator else []
        receipt = self.transport_bridge.execute_single_live_transport(
            mapped_record=context["mapped_record"],
            run_id=run_id,
            company_reference=context["company"].id,
            person_reference=context["candidate"].id,
            authorization=confirmation,
            existing_receipts=receipts,
            dispatch=True,
        )
        self._finalize_database_receipt(db, campaign, recipient, context, rediff_preview, receipt)
        if operator:
            operator.record_single_live_transport(receipt, quality_score=float(rediff_preview["personalization_score"]))
        if receipt.get("transport_status") == SUPPRESSED_DUPLICATE_TRANSPORT:
            raise SingleLiveSendBlocked("SECOND_SEND_BLOCKED_ALREADY_SENT")
        if receipt.get("transport_status") != "SENT" or receipt.get("smtp_sent") is not True:
            raise SingleLiveSendBlocked(str(receipt.get("error") or "REDIFF_TRANSPORT_FAILED"))
        return {
            "transport_status": "SENT",
            "sent_at": receipt.get("sent_at"),
            "recipient": receipt.get("recipient"),
            "cc": receipt.get("cc"),
            "bcc": receipt.get("bcc"),
            "run_id": run_id,
            "company_id": context["company"].id,
            "candidate_id": context["candidate"].id,
            "touch": "INITIAL",
            "test_type": SINGLE_LIVE_TEST_TYPE,
            "real_prospect_emails_sent": 1,
            "followups_enabled": False,
        }

    def _prepare_preview(
        self,
        db: Session,
        candidate_id: int,
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        candidate = db.query(DecisionMakerCandidate).filter(DecisionMakerCandidate.id == candidate_id).first()
        if not candidate:
            raise SingleLiveSendBlocked("QUALIFIED_CANDIDATE_NOT_FOUND")
        context = self._candidate_context(db, candidate)
        self._assert_no_prior_send(db, context)
        personalized = self._salesoorja_personalization(context["record"])
        self._assert_suppression_clear(db, context, personalized)
        record = self.personalization.enrich_record_for_rediff(context["record"], personalized)
        record["PERSONALIZATION_STATUS"] = personalized["status"]
        record["PERSONALIZATION_SCORE"] = float(personalized["quality_score"])
        adapter = self._production_adapter()
        handoff = adapter.prepare_handoff(
            record,
            outreach_state=self._outreach_state(db, context["company"].id),
            campaign=LIVE_CAMPAIGN_REFERENCE,
            followup_stage="INITIAL",
        )
        if handoff.get("status") != QUEUED:
            raise SingleLiveSendBlocked(str(handoff.get("reason") or handoff.get("status")))
        context["mapped_record"] = handoff["mapped_record"]
        receipt = self.transport_bridge.execute_single_live_transport(
            mapped_record=handoff["mapped_record"],
            run_id="single-live-preview",
            company_reference=context["company"].id,
            person_reference=context["candidate"].id,
            authorization=SINGLE_LIVE_AUTHORIZATION,
            existing_receipts=self._operator().get_transport_receipts() if self._operator() else [],
            dispatch=False,
        )
        preview = receipt.get("preview") or {}
        if receipt.get("transport_status") != "READY":
            raise SingleLiveSendBlocked(str(receipt.get("error") or receipt.get("transport_status")))
        if preview.get("rediff_eligible") is not True:
            raise SingleLiveSendBlocked(str(preview.get("blocker_reason") or "REDIFF_QUALIFICATION_BLOCKED"))
        if float(preview.get("personalization_score") or 0) < 85:
            raise SingleLiveSendBlocked("PERSONALIZATION_QUALITY_BELOW_85")
        if preview.get("claim_validation") != "PASS":
            raise SingleLiveSendBlocked("CLAIM_VALIDATION_FAILED")
        if not preview.get("subject") or not preview.get("body_html"):
            raise SingleLiveSendBlocked("COMPLETE_EMAIL_PREVIEW_REQUIRED")
        return context, personalized, receipt

    def _candidate_context(self, db: Session, candidate: DecisionMakerCandidate) -> dict[str, Any]:
        company = db.query(Company).filter(Company.id == candidate.company_id).first()
        if not company:
            raise SingleLiveSendBlocked("COMPANY_NOT_FOUND")
        packet = self._evidence_packet(candidate)
        signal = (
            db.query(CompanyIntentSignal)
            .filter(CompanyIntentSignal.company_id == company.id, CompanyIntentSignal.is_active == 1)
            .order_by(CompanyIntentSignal.detected_at.desc(), CompanyIntentSignal.id.desc())
            .first()
        )
        email = str(candidate.apollo_email or "").strip()
        apollo_person = (
            (candidate.apollo_response_json or {}).get("person")
            if isinstance(candidate.apollo_response_json, Mapping)
            else {}
        ) or {}
        person_score = float(packet.get("score") or (candidate.score_composite or 0) * 100)
        checks = {
            "real_company": str(company.source or "").casefold() not in TEST_COMPANY_SOURCES,
            "company_qualified": str(company.qualification_status or "").upper() == "QUALIFIED",
            "icp_score": float(company.icp_score or 0) >= 85,
            "trigger_verified": bool(signal and signal.source_url),
            "current_employment": str(packet.get("current_employment") or "").upper() == "VERIFIED",
            "facility": str(packet.get("facility_relationship") or "").upper()
            in {"FACILITY_OWNER", "FACILITY_FUNCTION_OWNER"},
            "function": str(packet.get("function_ownership") or "").upper() in STRONG_FUNCTIONS,
            "authority": str(packet.get("authority") or "").upper() == "DECISION_MAKER",
            "person_confidence": str(packet.get("confidence") or "").upper() == "HIGH",
            "person_score": person_score >= 85,
            "email_present": bool(email),
            "email_confidence": str(candidate.apollo_email_confidence or "").upper() == "HIGH",
            "mailbox_verified": str(apollo_person.get("email_status") or "").casefold() == "verified",
        }
        failed = [name for name, passed in checks.items() if not passed]
        if failed:
            raise SingleLiveSendBlocked("QUALIFICATION_GATES_FAILED:" + ",".join(failed))

        facility = str(packet.get("target_facility") or candidate.candidate_facility or "").strip()
        trigger = str(signal.source_snippet or signal.urgency_reason or signal.signal_type).strip()
        opportunity = str(signal.opportunity_note or signal.urgency_reason or trigger).strip()
        record = {
            "record_id": f"single-live-{company.id}-{candidate.id}",
            "READY_FOR_EMAIL": "YES",
            "company": company.name,
            "facility": facility,
            "city": company.city,
            "state": company.state,
            "person": candidate.candidate_name,
            "first_name": str(candidate.candidate_name or "").split()[0],
            "designation": candidate.candidate_title,
            "persona": candidate.target_persona,
            "email": email,
            "phone": candidate.apollo_phone,
            "trigger": trigger,
            "trigger_date": signal.detected_at.date().isoformat() if signal.detected_at else "",
            "calibration_opportunity": opportunity,
            "reasoning": opportunity,
            "icp_score": float(company.icp_score or 0),
            "facility_verified": True,
            "contact_verified": True,
            "provenance": "REAL",
            "evidence": {
                "trigger_current": {"verified": True},
                "exact_facility": {"verified": True, "address": facility, "linkage_strength": "DIRECT"},
                "technical_capability": {"status": "IN_SCOPE"},
                "correct_person": {
                    "name": candidate.candidate_name,
                    "employment_verified": True,
                    "duties_verified": True,
                    "company_evidence_status": "CURRENT_COMPANY",
                },
                "reachable_email": {
                    "email": email,
                    "status": "VERIFIED",
                    "mailbox_verified": True,
                    "contact_confidence": "HIGH",
                },
            },
        }
        return {
            "candidate": candidate,
            "company": company,
            "signal": signal,
            "packet": packet,
            "email": email,
            "person_score": person_score,
            "record": record,
        }

    def _salesoorja_personalization(self, record: Mapping[str, Any]) -> dict[str, Any]:
        personalized = self.personalization.personalize_record(record, force_provider="DETERMINISTIC")
        if personalized.get("status") != "VALIDATED":
            raise SingleLiveSendBlocked("CLAIM_VALIDATION_FAILED")
        if float(personalized.get("quality_score") or 0) < 85:
            raise SingleLiveSendBlocked("PERSONALIZATION_QUALITY_BELOW_85")
        return personalized

    def _assert_suppression_clear(
        self,
        db: Session,
        context: Mapping[str, Any],
        personalized: Mapping[str, Any],
    ) -> None:
        record = self.personalization.enrich_record_for_rediff(context["record"], personalized)
        record["PERSONALIZATION_STATUS"] = personalized["status"]
        record["PERSONALIZATION_SCORE"] = float(personalized["quality_score"])
        result = self._production_adapter().evaluate_suppression(
            record,
            self._outreach_state(db, context["company"].id),
        )
        if not result["allowed"]:
            raise SingleLiveSendBlocked(str(result["status"]))

    def _production_adapter(self) -> RediffSenderAdapter:
        configured_handoff = Path(str(getattr(self.settings, "REDIFF_HANDOFF_DIR", "data/rediff_handoff") or "data/rediff_handoff"))
        if not configured_handoff.is_absolute():
            configured_handoff = BACKEND_ROOT / configured_handoff
        handoff_dir = configured_handoff / "single-live"
        return RediffSenderAdapter(
            config=RediffAdapterConfig(
                enabled=True,
                test_mode=False,
                system_path=Path(str(getattr(self.settings, "REDIFF_SYSTEM_PATH", "") or "")),
                handoff_dir=handoff_dir,
                cc_addresses=(TEST_RECIPIENT,),
                duplicate_window_days=max(1, int(getattr(self.settings, "REDIFF_DUPLICATE_WINDOW_DAYS", 14))),
            ),
            now=self._now,
        )

    def _outreach_state(self, db: Session, company_id: int) -> dict[str, Any]:
        company = db.query(Company).filter(Company.id == company_id).first()
        recipient = (
            db.query(CampaignRecipient)
            .filter(CampaignRecipient.company_id == company_id)
            .order_by(CampaignRecipient.updated_at.desc(), CampaignRecipient.id.desc())
            .first()
        )
        metadata = dict(recipient.metadata_json or {}) if recipient else {}
        return {
            "last_sent_at": (recipient.last_sent_at if recipient else company.last_contact_date),
            "replied_at": recipient.replied_at if recipient else (self._now() if company.reply_received else None),
            "bounced_at": recipient.bounced_at if recipient else (self._now() if company.bounced_email else None),
            "email_status": recipient.email_status if recipient else None,
            "reply_classification": metadata.get("reply_classification"),
            "meaningful_reply": metadata.get("meaningful_reply", False),
            "opted_out": metadata.get("opted_out", False),
        }

    def _assert_no_prior_send(self, db: Session, context: Mapping[str, Any]) -> None:
        recipients = (
            db.query(CampaignRecipient)
            .filter(CampaignRecipient.company_id == context["company"].id)
            .all()
        )
        email = context["email"].casefold()
        for recipient in recipients:
            metadata = dict(recipient.metadata_json or {})
            if str(metadata.get("recipient") or "").casefold() != email:
                continue
            sent = db.query(CampaignEvent.id).filter(
                CampaignEvent.recipient_id == recipient.id,
                CampaignEvent.event_type == "sent",
            ).first()
            if sent or recipient.last_sent_at:
                raise SingleLiveSendBlocked("SECOND_SEND_BLOCKED_ALREADY_SENT")

    def _create_pending_receipt(
        self,
        db: Session,
        context: Mapping[str, Any],
        preview: Mapping[str, Any],
    ) -> tuple[Campaign, CampaignRecipient]:
        candidate = context["candidate"]
        person = db.query(Person).filter(Person.id == candidate.person_id).first() if candidate.person_id else None
        if not person:
            normalized = normalize_email(context["email"])
            person = db.query(Person).filter(Person.normalized_email == normalized).first()
        if not person:
            person = Person(
                company_id=context["company"].id,
                full_name=candidate.candidate_name,
                designation=candidate.candidate_title,
                email=context["email"],
                normalized_email=normalize_email(context["email"]),
                phone=candidate.apollo_phone,
                linkedin_url=candidate.public_profile_url,
                discovery_status="EMAIL_VERIFIED",
                discovery_source="single_live_customer_test",
                evidence_json={"candidate_id": candidate.id},
                email_verification_status="verified",
                email_verification_reason="Existing verified enrichment evidence",
                email_verified_at=self._now(),
                is_decision_maker=1,
            )
            db.add(person)
            db.flush()
        candidate.person_id = person.id
        campaign = Campaign(
            name=f"Single Live Customer Test - {context['company'].name}",
            description="Explicitly authorized one-recipient initial email; no follow-ups enabled.",
            channel="email",
            status="Sending",
            approved=True,
            approved_at=self._now(),
            daily_limit=1,
            segment_filters={"test_type": SINGLE_LIVE_TEST_TYPE, "max_prospect_recipients": 1},
        )
        db.add(campaign)
        db.flush()
        db.add(CampaignStep(
            campaign_id=campaign.id,
            step_number=1,
            channel="email",
            delay_days=0,
            subject=str(preview.get("subject") or ""),
            body_template=str(preview.get("body_html") or ""),
            enabled=False,
        ))
        recipient = CampaignRecipient(
            campaign_id=campaign.id,
            company_id=context["company"].id,
            person_id=person.id,
            current_step=0,
            status="Sending",
            email_status="Pending",
            next_send_at=None,
            metadata_json={
                "recipient": context["email"],
                "cc": [TEST_RECIPIENT],
                "bcc": [],
                "touch": "INITIAL",
                "test_type": SINGLE_LIVE_TEST_TYPE,
                "followups_enabled": False,
            },
        )
        db.add(recipient)
        db.commit()
        db.refresh(campaign)
        db.refresh(recipient)
        return campaign, recipient

    def _finalize_database_receipt(
        self,
        db: Session,
        campaign: Campaign,
        recipient: CampaignRecipient,
        context: Mapping[str, Any],
        preview: Mapping[str, Any],
        receipt: Mapping[str, Any],
    ) -> None:
        if receipt.get("transport_status") == "SENT" and receipt.get("smtp_sent") is True:
            sent_at = datetime.fromisoformat(str(receipt["sent_at"]).replace("Z", "+00:00"))
            campaign.status = "Completed"
            recipient.status = "Sent"
            recipient.email_status = "Sent"
            recipient.current_step = 1
            recipient.last_sent_at = sent_at
            recipient.next_send_at = None
            context["company"].email_sent = True
            context["company"].last_contact_date = sent_at
            db.add(CampaignEvent(
                campaign_id=campaign.id,
                recipient_id=recipient.id,
                event_type="sent",
                channel="email",
                provider_message_id=receipt.get("message_id"),
                payload={
                    "simulated": False,
                    "test_mode": False,
                    "test_type": SINGLE_LIVE_TEST_TYPE,
                    "transport_status": "SENT",
                    "sent_at": receipt.get("sent_at"),
                    "recipient": context["email"],
                    "cc": [TEST_RECIPIENT],
                    "bcc": [],
                    "run_id": receipt.get("run_id"),
                    "company_id": context["company"].id,
                    "candidate_id": context["candidate"].id,
                    "person_id": recipient.person_id,
                    "touch": "INITIAL",
                    "followups_enabled": False,
                    "subject": preview.get("subject"),
                },
            ))
        else:
            campaign.status = "Failed"
            recipient.status = "Failed"
            recipient.email_status = "Failed"
            recipient.next_send_at = None
            metadata = dict(recipient.metadata_json or {})
            metadata["transport_error"] = receipt.get("error")
            recipient.metadata_json = metadata
        db.commit()

    @staticmethod
    def _evidence_packet(candidate: DecisionMakerCandidate) -> dict[str, Any]:
        for source in reversed(list(candidate.evidence_sources or [])):
            packet = source.get("evidence_packet") if isinstance(source, Mapping) else None
            if isinstance(packet, Mapping):
                return dict(packet)
        return {}

    @staticmethod
    def _candidate_summary(context: Mapping[str, Any], personalized: Mapping[str, Any]) -> dict[str, Any]:
        candidate = context["candidate"]
        company = context["company"]
        packet = context["packet"]
        return {
            "candidate_id": candidate.id,
            "company_id": company.id,
            "company": company.name,
            "facility": context["record"]["facility"],
            "person": candidate.candidate_name,
            "designation": candidate.candidate_title,
            "email": context["email"],
            "trigger": context["record"]["trigger"],
            "person_score": context["person_score"],
            "current_employment": packet.get("current_employment"),
            "facility_relationship": packet.get("facility_relationship"),
            "function": packet.get("function_ownership"),
            "authority": packet.get("authority"),
            "salesoorja_personalization_score": float(personalized.get("quality_score") or 0),
            "salesoorja_claim_validation": "PASS",
        }

    @staticmethod
    def _preview_token(candidate_id: int, email: str, preview: Mapping[str, Any]) -> str:
        payload = json.dumps(
            {
                "candidate_id": candidate_id,
                "email": email.casefold(),
                "subject": preview.get("subject"),
                "body_html": preview.get("body_html"),
                "score": preview.get("personalization_score"),
                "claim_validation": preview.get("claim_validation"),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _live_send_available(self) -> bool:
        return bool(
            getattr(self.settings, "SINGLE_LIVE_CUSTOMER_TEST_ENABLED", False)
            and not getattr(self.settings, "REAL_OUTREACH_ENABLED", False)
            and self.transport_bridge.available()
        )

    def _operator(self):
        if self.operator is None:
            from services.salesoorja_operator import salesoorja_operator

            self.operator = salesoorja_operator
        return self.operator


single_live_send_service = SingleLiveSendService()
