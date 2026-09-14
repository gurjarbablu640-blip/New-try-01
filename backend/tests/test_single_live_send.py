"""Zero-SMTP safety tests for the bounded single-customer live-send flow."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models  # noqa: F401
from database import Base
from models.campaign import Campaign, CampaignEvent, CampaignRecipient, CampaignStep
from models.company import Company
from models.decision_maker_candidate import DecisionMakerCandidate
from models.intent_signal import CompanyIntentSignal
from services.rediff_transport_bridge import SINGLE_LIVE_AUTHORIZATION, RediffTransportBridge
from services.single_live_send import SingleLiveSendBlocked, SingleLiveSendService


NOW = datetime(2026, 9, 14, 11, 30, tzinfo=timezone.utc)
PROSPECT = "quality.head@qualified-customer.in"


class FakePersonalization:
    def __init__(self, score=96, status="VALIDATED"):
        self.score = score
        self.status = status

    def personalize_record(self, record, force_provider=None):
        return {
            "status": self.status,
            "quality_score": self.score,
            "subject": "Salesoorja internal validation",
            "body": "Validated internal copy",
            "followups": {},
        }

    def enrich_record_for_rediff(self, record, personalized):
        enriched = dict(record)
        enriched["WHY_CALIBRATION_NOW"] = personalized["body"]
        enriched["NOTES"] = "validated"
        return enriched


class FakeBridge:
    def __init__(self, claim_validation="PASS", score=92):
        self.claim_validation = claim_validation
        self.score = score
        self.calls = []

    def available(self):
        return True

    def execute_single_live_transport(self, **kwargs):
        self.calls.append(kwargs)
        dispatch = kwargs["dispatch"]
        return {
            "receipt_id": f"receipt-{len(self.calls)}",
            "run_id": kwargs["run_id"],
            "company_reference": kwargs["company_reference"],
            "person_reference": kwargs["person_reference"],
            "transport_status": "SENT" if dispatch else "READY",
            "transport_called": dispatch,
            "smtp_sent": dispatch,
            "sent_at": NOW.isoformat() if dispatch else None,
            "recipient": PROSPECT,
            "actual_to": PROSPECT,
            "cc": ["Bablu@oorjatechnical.org"],
            "bcc": [],
            "test_mode": False,
            "test_type": "SINGLE_LIVE_CUSTOMER_TEST",
            "touch": "INITIAL",
            "initial_or_followup": "INITIAL",
            "prospect_recipient_count": 1,
            "duplicate_key": "candidate|email|campaign|initial",
            "message_id": None,
            "error": None,
            "preview": {
                "subject": "Calibration support for Plant V",
                "body_html": "<html><body>Full reviewed customer email.</body></html>",
                "personalization_score": self.score,
                "research_score": 90,
                "claim_validation": self.claim_validation,
                "rediff_eligible": self.claim_validation == "PASS",
                "blocker": None if self.claim_validation == "PASS" else "SAFETY_BLOCKED",
                "blocker_reason": None if self.claim_validation == "PASS" else "Claim validation failed",
            },
        }


class FakeOperator:
    def __init__(self):
        self.receipts = []
        self.counters = {"emails_sent": 0, "production_emails_sent": 0, "real_prospect_emails_sent": 0}

    def get_status(self):
        return {"status": "STOPPED"}

    def get_transport_receipts(self):
        return list(self.receipts)

    def record_single_live_transport(self, receipt, *, quality_score):
        self.receipts.append(dict(receipt))
        if receipt["transport_status"] == "SENT":
            self.counters["emails_sent"] += 1
            self.counters["production_emails_sent"] += 1
            self.counters["real_prospect_emails_sent"] += 1


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _settings(tmp_path: Path, *, enabled=True):
    system = tmp_path / "Rediff_Email_System"
    system.mkdir()
    (system / "campaign_runner.py").write_text("# marker\n", encoding="utf-8")
    (system / "send_email.py").write_text("# marker\n", encoding="utf-8")
    return SimpleNamespace(
        SINGLE_LIVE_CUSTOMER_TEST_ENABLED=enabled,
        REAL_OUTREACH_ENABLED=False,
        REDIFF_SYSTEM_PATH=str(system),
        REDIFF_HANDOFF_DIR=str(tmp_path / "handoff"),
        REDIFF_DUPLICATE_WINDOW_DAYS=14,
    )


def _qualified_candidate(db):
    company = Company(
        name="Qualified Customer Limited",
        source="live_search",
        qualification_status="QUALIFIED",
        icp_score=93,
        city="Jamshedpur",
        state="Jharkhand",
    )
    db.add(company)
    db.flush()
    db.add(CompanyIntentSignal(
        company_id=company.id,
        signal_type="PLANT_EXPANSION",
        source_url="https://customer.example/news/plant-v",
        source_snippet="Plant V production expansion is active.",
        urgency_reason="New production assets require calibration readiness.",
        opportunity_note="Commissioning instrumentation requires traceable calibration.",
        is_active=1,
    ))
    candidate = DecisionMakerCandidate(
        company_id=company.id,
        target_persona="Quality / Metrology",
        candidate_name="Qualified Person",
        candidate_title="Plant Quality Head",
        candidate_facility="Plant V",
        verification_status="EMAIL_VERIFIED",
        verification_confidence=0.96,
        score_composite=0.96,
        apollo_email=PROSPECT,
        apollo_email_confidence="HIGH",
        email_status="EMAIL_VERIFIED",
        apollo_response_json={"person": {"email_status": "verified"}},
        evidence_sources=[{
            "source": "BRIGHTDATA_LINKEDIN_PROFILE",
            "evidence_packet": {
                "current_employment": "VERIFIED",
                "facility_relationship": "FACILITY_FUNCTION_OWNER",
                "function_ownership": "STRONG_PLANT_QUALITY_OWNER",
                "authority": "DECISION_MAKER",
                "confidence": "HIGH",
                "score": 96,
                "target_facility": "Plant V",
            },
        }],
    )
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    return candidate


def _service(tmp_path, *, enabled=True, personalization=None, bridge=None, operator=None):
    return SingleLiveSendService(
        settings_obj=_settings(tmp_path, enabled=enabled),
        personalization=personalization or FakePersonalization(),
        transport_bridge=bridge or FakeBridge(),
        operator_obj=operator or FakeOperator(),
        now=lambda: NOW,
    )


def test_single_live_send_requires_confirmation_and_persists_one_recipient(db, tmp_path):
    candidate = _qualified_candidate(db)
    bridge = FakeBridge()
    operator = FakeOperator()
    service = _service(tmp_path, bridge=bridge, operator=operator)

    candidates = service.list_candidates(db)
    preview = service.preview(db, candidate.id)

    assert candidates["total"] == 1
    assert candidates["max_prospect_recipients"] == 1
    assert candidates["mass_production_enabled"] is False
    assert candidates["followups_enabled"] is False
    assert preview["personalization_score"] >= 85
    assert preview["claim_validation"] == "PASS"
    assert preview["cc"] == ["Bablu@oorjatechnical.org"]
    assert preview["bcc"] == []
    with pytest.raises(PermissionError, match="SINGLE_LIVE_CONFIRMATION_REQUIRED"):
        service.send(
            db,
            candidate_id=candidate.id,
            confirmation="send it",
            preview_token=preview["preview_token"],
        )

    result = service.send(
        db,
        candidate_id=candidate.id,
        confirmation=SINGLE_LIVE_AUTHORIZATION,
        preview_token=preview["preview_token"],
    )

    assert result["transport_status"] == "SENT"
    assert result["recipient"] == PROSPECT
    assert result["cc"] == ["Bablu@oorjatechnical.org"]
    assert result["bcc"] == []
    assert result["real_prospect_emails_sent"] == 1
    assert sum(1 for call in bridge.calls if call["dispatch"]) == 1
    assert operator.counters["real_prospect_emails_sent"] == 1
    campaign = db.query(Campaign).one()
    recipient = db.query(CampaignRecipient).one()
    event = db.query(CampaignEvent).one()
    step = db.query(CampaignStep).one()
    assert campaign.daily_limit == 1
    assert campaign.status == "Completed"
    assert recipient.last_sent_at is not None
    assert recipient.next_send_at is None
    assert recipient.metadata_json["followups_enabled"] is False
    assert step.enabled is False
    assert event.payload["simulated"] is False
    assert event.payload["test_mode"] is False
    assert event.payload["test_type"] == "SINGLE_LIVE_CUSTOMER_TEST"

    with pytest.raises(SingleLiveSendBlocked, match="SECOND_SEND_BLOCKED_ALREADY_SENT"):
        service.send(
            db,
            candidate_id=candidate.id,
            confirmation=SINGLE_LIVE_AUTHORIZATION,
            preview_token=preview["preview_token"],
        )
    assert sum(1 for call in bridge.calls if call["dispatch"]) == 1


def test_single_live_send_remains_disabled_without_narrow_override(db, tmp_path):
    candidate = _qualified_candidate(db)
    service = _service(tmp_path, enabled=False)
    preview = service.preview(db, candidate.id)

    assert preview["real_send_available"] is False
    with pytest.raises(PermissionError, match="SINGLE_LIVE_CUSTOMER_TEST_DISABLED"):
        service.send(
            db,
            candidate_id=candidate.id,
            confirmation=SINGLE_LIVE_AUTHORIZATION,
            preview_token=preview["preview_token"],
        )


def test_quality_below_85_is_not_selectable(db, tmp_path):
    candidate = _qualified_candidate(db)
    service = _service(tmp_path, personalization=FakePersonalization(score=84))

    assert service.list_candidates(db)["results"] == []
    with pytest.raises(SingleLiveSendBlocked, match="PERSONALIZATION_QUALITY_BELOW_85"):
        service.preview(db, candidate.id)


def test_rediff_claim_failure_blocks_before_transport(db, tmp_path):
    candidate = _qualified_candidate(db)
    bridge = FakeBridge(claim_validation="FAIL")
    service = _service(tmp_path, bridge=bridge)

    with pytest.raises(SingleLiveSendBlocked, match="Claim validation failed"):
        service.preview(db, candidate.id)
    assert all(call["dispatch"] is False for call in bridge.calls)


def test_rediff_quality_below_85_blocks_before_transport(db, tmp_path):
    candidate = _qualified_candidate(db)
    bridge = FakeBridge(score=84)
    service = _service(tmp_path, bridge=bridge)

    with pytest.raises(SingleLiveSendBlocked, match="PERSONALIZATION_QUALITY_BELOW_85"):
        service.preview(db, candidate.id)
    assert all(call["dispatch"] is False for call in bridge.calls)


@pytest.mark.parametrize("suppression", ["reply", "bounce", "optout"])
def test_suppressed_contacts_are_not_selectable(db, tmp_path, suppression):
    candidate = _qualified_candidate(db)
    company = db.query(Company).filter(Company.id == candidate.company_id).one()
    if suppression == "reply":
        company.reply_received = True
    elif suppression == "bounce":
        company.bounced_email = True
    else:
        campaign = Campaign(name="Prior campaign", status="Completed", approved=True)
        db.add(campaign)
        db.flush()
        db.add(CampaignRecipient(
            campaign_id=campaign.id,
            company_id=company.id,
            status="Unsubscribed",
            email_status="Unsubscribed",
            metadata_json={"recipient": PROSPECT, "opted_out": True},
        ))
    db.commit()
    service = _service(tmp_path)

    assert service.list_candidates(db)["results"] == []


def test_bridge_asserts_one_prospect_bablu_cc_and_zero_bcc(tmp_path):
    calls = []

    def worker(command, **kwargs):
        calls.append(command)
        result_path = Path(command[command.index("--result") + 1])
        result_path.write_text(
            '{"transport_status":"READY","message_id":null,"error":null,"preview":'
            '{"subject":"Subject","body_html":"<p>Body</p>","personalization_score":90,'
            '"research_score":90,"claim_validation":"PASS","rediff_eligible":true}}',
            encoding="utf-8",
        )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    system = tmp_path / "Rediff_Email_System"
    system.mkdir()
    (system / "campaign_runner.py").write_text("# marker\n", encoding="utf-8")
    bridge = RediffTransportBridge(
        system_path=system,
        run_dir=tmp_path / "runs",
        single_live_enabled=True,
        process_runner=worker,
        now=lambda: NOW,
    )
    mapped = {field: "" for field in __import__("services.rediff_sender_adapter", fromlist=["REDIFF_CSV_FIELDS"]).REDIFF_CSV_FIELDS}
    mapped.update({"EMAIL": PROSPECT, "EMAIL_ID": PROSPECT, "CONTACT_NAME": "Qualified Person"})

    with pytest.raises(PermissionError, match="SINGLE_LIVE_CONFIRMATION_REQUIRED"):
        bridge.execute_single_live_transport(
            mapped_record=mapped,
            run_id="run-1",
            company_reference=1,
            person_reference=2,
            authorization="wrong",
        )
    receipt = bridge.execute_single_live_transport(
        mapped_record=mapped,
        run_id="run-1",
        company_reference=1,
        person_reference=2,
        authorization=SINGLE_LIVE_AUTHORIZATION,
        dispatch=False,
    )

    assert receipt["transport_status"] == "READY"
    assert receipt["prospect_recipient_count"] == 1
    assert receipt["actual_to"] == PROSPECT
    assert receipt["cc"] == ["Bablu@oorjatechnical.org"]
    assert receipt["bcc"] == []
    assert calls[0][calls[0].index("--mode") + 1] == "single-live"
    assert calls[0][calls[0].index("--recipient") + 1] == PROSPECT
    assert calls[0][calls[0].index("--cc") + 1] == "Bablu@oorjatechnical.org"
