"""Synthetic, zero-send tests for the Rediff file-handoff adapter."""

from __future__ import annotations

import csv
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from services.rediff_sender_adapter import (
    DRY_RUN_READY,
    FAILED,
    INVALID_EMAIL,
    QUEUED,
    SUPPRESSED_BOUNCE,
    SUPPRESSED_DUPLICATE,
    SUPPRESSED_NOT_READY,
    SUPPRESSED_OPTOUT,
    SUPPRESSED_REPLY,
    SUPPRESSED_TEST_DATA,
    TEMPORARY_FAILURE,
    RediffAdapterConfig,
    RediffSenderAdapter,
)


NOW = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)


def _rediff_system(tmp_path: Path) -> Path:
    system = tmp_path / "Rediff_Email_System"
    system.mkdir()
    for name in ("campaign_runner.py", "send_email.py"):
        (system / name).write_text("# compatibility marker\n", encoding="utf-8")
    return system


def _adapter(tmp_path: Path, *, test_mode: bool = True, system_path: Path | None = None) -> RediffSenderAdapter:
    config = RediffAdapterConfig(
        enabled=True,
        test_mode=test_mode,
        system_path=system_path or _rediff_system(tmp_path),
        handoff_dir=tmp_path / "handoff",
        cc_addresses=("Bablu@oorjatechnical.org", "piyushk@oorjatechnical.com"),
        duplicate_window_days=14,
    )
    return RediffSenderAdapter(config=config, now=lambda: NOW)


def _qualified_record(*, provenance: str = "SYNTHETIC") -> dict:
    return {
        "record_id": "synthetic-rediff-001",
        "READY_FOR_EMAIL": "YES",
        "company": "Synthetic Precision Components",
        "facility": "Test Plant V, Pune, Maharashtra",
        "city": "Pune",
        "state": "Maharashtra",
        "person": "Asha Verma",
        "designation": "Plant Quality Head",
        "persona": "Quality Head",
        "email": "asha.verma@synthetic.test",
        "phone": "+91-9000000000",
        "trigger": "Synthetic line commissioning",
        "trigger_date": "2026-09-01",
        "calibration_opportunity": "Synthetic dimensional calibration requirement",
        "reasoning": "Synthetic source-backed test opportunity",
        "icp_score": 96,
        "facility_verified": True,
        "contact_verified": True,
        "provenance": provenance,
        "evidence": {
            "trigger_current": {"verified": True},
            "exact_facility": {"verified": True, "address": "Test Plant V, Pune"},
            "technical_capability": {"status": "IN_SCOPE"},
            "correct_person": {
                "name": "Asha Verma",
                "employment_verified": True,
                "duties_verified": True,
                "company_evidence_status": "CURRENT_COMPANY",
            },
            "reachable_email": {
                "email": "asha.verma@synthetic.test",
                "status": "VERIFIED",
                "mailbox_verified": True,
                "contact_confidence": "HIGH",
            },
        },
    }


def test_synthetic_case_1_qualified_maps_to_dry_run_without_transport(tmp_path, monkeypatch):
    smtp_calls = []
    monkeypatch.setattr("smtplib.SMTP", lambda *args, **kwargs: smtp_calls.append((args, kwargs)))
    monkeypatch.setattr("smtplib.SMTP_SSL", lambda *args, **kwargs: smtp_calls.append((args, kwargs)))

    result = _adapter(tmp_path).prepare_handoff(_qualified_record(), campaign="synthetic-control")

    assert result["status"] == DRY_RUN_READY
    assert result["transport_called"] is False
    assert result["smtp_sent"] is False
    assert smtp_calls == []
    assert not (tmp_path / "handoff").exists()
    mapped = result["mapped_record"]
    assert mapped["COMPANY_NAME"] == "Synthetic Precision Components"
    assert mapped["CONTACT_PERSON"] == "Asha Verma"
    assert mapped["EMAIL_ID"] == "asha.verma@synthetic.test"
    assert mapped["READY_FOR_EMAIL"] == "YES"


def test_synthetic_case_2_hold_is_blocked_before_rediff(tmp_path):
    record = _qualified_record()
    record["READY_FOR_EMAIL"] = "NO"

    result = _adapter(tmp_path).prepare_handoff(record)

    assert result["status"] == SUPPRESSED_NOT_READY
    assert result["transport_called"] is False
    assert "mapped_record" not in result


def test_synthetic_case_3_recent_duplicate_is_suppressed(tmp_path):
    result = _adapter(tmp_path).prepare_handoff(
        _qualified_record(),
        outreach_state={"last_sent_at": (NOW - timedelta(days=3)).isoformat()},
    )

    assert result["status"] == SUPPRESSED_DUPLICATE
    assert result["transport_called"] is False


def test_mock_or_synthetic_record_cannot_enter_production_handoff(tmp_path):
    result = _adapter(tmp_path, test_mode=False).prepare_handoff(_qualified_record())

    assert result["status"] == SUPPRESSED_TEST_DATA
    assert not (tmp_path / "handoff").exists()


def test_opt_out_is_suppressed(tmp_path):
    result = _adapter(tmp_path).prepare_handoff(_qualified_record(), outreach_state={"opted_out": True})
    assert result["status"] == SUPPRESSED_OPTOUT


def test_bounce_is_suppressed(tmp_path):
    result = _adapter(tmp_path).prepare_handoff(_qualified_record(), outreach_state={"email_status": "Bounced"})
    assert result["status"] == SUPPRESSED_BOUNCE


def test_meaningful_reply_is_suppressed(tmp_path):
    result = _adapter(tmp_path).prepare_handoff(
        _qualified_record(),
        outreach_state={"replied_at": NOW.isoformat(), "reply_classification": "INTERESTED"},
    )
    assert result["status"] == SUPPRESSED_REPLY


def test_invalid_or_role_email_is_blocked(tmp_path):
    record = _qualified_record()
    record["email"] = "info@synthetic.test"
    record["evidence"]["reachable_email"]["email"] = record["email"]

    result = _adapter(tmp_path).prepare_handoff(record)

    assert result["status"] == INVALID_EMAIL


def test_existing_deterministic_person_gate_cannot_be_bypassed(tmp_path):
    record = _qualified_record()
    record["evidence"]["correct_person"]["employment_verified"] = False

    result = _adapter(tmp_path).prepare_handoff(record)

    assert result["status"] == SUPPRESSED_NOT_READY
    assert result["qualification_state"] == "PERSON_CANDIDATE_FOUND"


def test_malformed_qualification_evidence_is_safely_blocked(tmp_path):
    record = _qualified_record()
    record["evidence"]["technical_capability"] = True

    result = _adapter(tmp_path).prepare_handoff(record)

    assert result["status"] == SUPPRESSED_NOT_READY
    assert result["qualification_state"] == "UNKNOWN"


def test_cc_configuration_maps_without_becoming_smtp_credentials(tmp_path):
    result = _adapter(tmp_path).prepare_handoff(_qualified_record())

    assert result["cc"] == ["Bablu@oorjatechnical.org", "piyushk@oorjatechnical.com"]
    assert result["mapped_record"]["CC"] == "Bablu@oorjatechnical.org, piyushk@oorjatechnical.com"
    assert not any("password" in key.lower() for key in result["mapped_record"])


def test_followup_thread_metadata_survives_handoff_mapping(tmp_path):
    result = _adapter(tmp_path).prepare_handoff(
        _qualified_record(),
        followup_stage="FOLLOW_UP_1",
        message_id="<salesoorja-001@oorja.local>",
        in_reply_to="<rediff-parent-001@oorja.local>",
        references="<rediff-parent-001@oorja.local>",
    )

    mapped = result["mapped_record"]
    assert mapped["FOLLOWUP_STAGE"] == "FOLLOW_UP_1"
    assert mapped["MESSAGE_ID"] == "<salesoorja-001@oorja.local>"
    assert mapped["IN_REPLY_TO"] == "<rediff-parent-001@oorja.local>"
    assert mapped["REFERENCES"] == "<rediff-parent-001@oorja.local>"


def test_rediff_system_unavailable_returns_safe_structured_error(tmp_path):
    result = _adapter(tmp_path, system_path=tmp_path / "missing-rediff").prepare_handoff(_qualified_record())

    assert result == {
        "status": FAILED,
        "reason": "REDIFF_SYSTEM_UNAVAILABLE",
        "transport_called": False,
        "smtp_sent": False,
        "test_mode": True,
    }


def test_transport_failure_never_normalizes_to_sent_and_redacts_credentials(tmp_path, caplog):
    adapter = _adapter(tmp_path)
    with caplog.at_level(logging.INFO):
        result = adapter.normalize_transport_result(
            {
                "success": False,
                "status": "FAILED",
                "password": "do-not-log-this",
                "error": "Authentication failed for do-not-log-this",
            }
        )

    assert result["status"] == FAILED
    assert result["smtp_accepted"] is False
    assert result["delivery_verified"] is False
    assert result["raw"]["password"] == "[REDACTED]"
    assert "do-not-log-this" not in result["failure_reason"]
    assert "do-not-log-this" not in caplog.text


def test_421_receipt_is_temporary_failure(tmp_path):
    result = _adapter(tmp_path).normalize_transport_result(
        {"success": False, "status": "FAILED", "error": "421 temporarily deferred", "retry_count": 2}
    )
    assert result["status"] == TEMPORARY_FAILURE
    assert result["retry_count"] == 2


def test_production_handoff_writes_one_rediff_compatible_csv_without_sending(tmp_path):
    record = _qualified_record(provenance="REAL")
    record["email"] = "asha.verma@precision-components.in"
    record["evidence"]["reachable_email"]["email"] = record["email"]

    result = _adapter(tmp_path, test_mode=False).prepare_handoff(record, campaign="controlled-production")

    assert result["status"] == QUEUED
    assert result["transport_called"] is False
    handoff_path = Path(result["handoff_path"])
    assert handoff_path.is_file()
    with handoff_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1
    assert rows[0]["EMAIL_ID"] == "asha.verma@precision-components.in"
    assert rows[0]["READY_FOR_EMAIL"] == "YES"


def test_sender_disabled_in_test_mode_still_allows_dry_run(tmp_path):
    config = RediffAdapterConfig(
        enabled=False,
        test_mode=True,
        system_path=_rediff_system(tmp_path),
        handoff_dir=tmp_path / "handoff",
        cc_addresses=("Bablu@oorjatechnical.org", "piyushk@oorjatechnical.com"),
        duplicate_window_days=14,
    )
    adapter = RediffSenderAdapter(config=config, now=lambda: NOW)
    result = adapter.prepare_handoff(_qualified_record())

    assert result["status"] == DRY_RUN_READY
    assert result["transport_called"] is False
    assert result["smtp_sent"] is False


def test_sender_disabled_in_production_mode_is_safely_blocked(tmp_path):
    config = RediffAdapterConfig(
        enabled=False,
        test_mode=False,
        system_path=_rediff_system(tmp_path),
        handoff_dir=tmp_path / "handoff",
        cc_addresses=("Bablu@oorjatechnical.org", "piyushk@oorjatechnical.com"),
        duplicate_window_days=14,
    )
    adapter = RediffSenderAdapter(config=config, now=lambda: NOW)
    result = adapter.prepare_handoff(_qualified_record(provenance="REAL"))

    assert result["status"] == FAILED
    assert result["reason"] == "REDIFF_SENDER_DISABLED"
    assert result["transport_called"] is False
    assert result["smtp_sent"] is False

