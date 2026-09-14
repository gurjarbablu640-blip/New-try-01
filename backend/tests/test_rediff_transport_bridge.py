"""No-SMTP tests for the guarded existing-Rediff transport bridge."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from services.rediff_transport_bridge import (
    SUPPRESSED_DUPLICATE_TRANSPORT,
    TEST_RECIPIENT,
    TEST_TRANSPORT_AUTHORIZATION,
    RediffTransportBridge,
)


NOW = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)


def _system(tmp_path: Path) -> Path:
    system = tmp_path / "Rediff_Email_System"
    system.mkdir()
    (system / "campaign_runner.py").write_text("# existing sender marker\n", encoding="utf-8")
    return system


def _mapped_record() -> dict:
    return {
        "LEAD_ID": "operator-control-001",
        "COMPANY_NAME": "Synthetic Precision Components",
        "COMPANY": "Synthetic Precision Components",
        "FACILITY": "Test Plant V, Pune",
        "CONTACT_PERSON": "Asha Verma",
        "CONTACT_NAME": "Asha Verma",
        "EMAIL_ID": "asha.verma@synthetic.test",
        "EMAIL": "asha.verma@synthetic.test",
        "READY_FOR_EMAIL": "YES",
    }


class WorkerStub:
    def __init__(self, status: str):
        self.status = status
        self.calls = 0
        self.commands = []

    def __call__(self, command, **kwargs):
        self.calls += 1
        self.commands.append((command, kwargs))
        result_path = Path(command[command.index("--result") + 1])
        result_path.write_text(
            json.dumps(
                {
                    "transport_status": self.status,
                    "message_id": None,
                    "error": None if self.status == "SENT" else "SMTPException",
                }
            ),
            encoding="utf-8",
        )
        return SimpleNamespace(returncode=0 if self.status in {"READY", "SENT"} else 1, stdout="", stderr="")


def _bridge(tmp_path: Path, worker: WorkerStub, *, enabled: bool = True) -> RediffTransportBridge:
    return RediffTransportBridge(
        system_path=_system(tmp_path),
        run_dir=tmp_path / "runs",
        timeout_seconds=5,
        enabled=enabled,
        process_runner=worker,
        now=lambda: NOW,
    )


def _execute(bridge: RediffTransportBridge, receipts=()):
    return bridge.execute_test_transport(
        mapped_record=_mapped_record(),
        run_id="operator-run-001",
        company_reference="Synthetic Precision Components",
        person_reference="Asha Verma",
        campaign_reference="salesoorja-operator-transport-test",
        initial_or_followup="INITIAL",
        authorization=TEST_TRANSPORT_AUTHORIZATION,
        existing_receipts=receipts,
        mode="TEST",
    )


def test_successful_existing_rediff_transport_creates_sent_receipt(tmp_path):
    worker = WorkerStub("SENT")
    receipt = _execute(_bridge(tmp_path, worker))

    assert receipt["transport_status"] == "SENT"
    assert receipt["state_history"] == ["READY_FOR_EMAIL", "HANDOFF_CREATED", "SEND_ATTEMPTED", "SENT"]
    assert receipt["sent_at"] == NOW.isoformat()
    assert receipt["transport"] == "EXISTING_REDIFF_CAMPAIGN_RUNNER"
    assert receipt["recipient"] == TEST_RECIPIENT
    assert receipt["actual_to"] == TEST_RECIPIENT
    assert receipt["original_prospect_email"] == "asha.verma@synthetic.test"
    assert receipt["cc"] == []
    assert receipt["bcc"] == []
    assert receipt["prospect_recipient_count"] == 0
    assert receipt["smtp_sent"] is True
    assert worker.calls == 1
    html_path = next((tmp_path / "runs").glob("*/operator_transport_test.html"))
    assert "<body>SALESOORJA OPERATOR TRANSPORT TEST" in html_path.read_text(encoding="utf-8")


def test_failed_transport_never_marks_sent(tmp_path):
    receipt = _execute(_bridge(tmp_path, WorkerStub("FAILED")))

    assert receipt["transport_status"] == "FAILED"
    assert receipt["sent_at"] is None
    assert receipt["smtp_sent"] is False
    assert receipt["state_history"][-1] == "FAILED"


def test_handoff_created_is_not_sent_when_transport_disabled(tmp_path):
    worker = WorkerStub("SENT")
    receipt = _execute(_bridge(tmp_path, worker, enabled=False))

    assert receipt["transport_status"] == "FAILED"
    assert receipt["state_history"] == ["READY_FOR_EMAIL", "HANDOFF_CREATED", "FAILED"]
    assert receipt["transport_called"] is False
    assert worker.calls == 0


def test_sent_receipt_blocks_duplicate_without_worker_call(tmp_path):
    worker = WorkerStub("SENT")
    bridge = _bridge(tmp_path, worker)
    first = _execute(bridge)
    duplicate = _execute(bridge, receipts=[first])

    assert first["transport_status"] == "SENT"
    assert duplicate["transport_status"] == SUPPRESSED_DUPLICATE_TRANSPORT
    assert duplicate["transport_called"] is False
    assert duplicate["duplicate_of"] == first["receipt_id"]
    assert worker.calls == 1


def test_wrong_authorization_aborts_before_transport(tmp_path):
    worker = WorkerStub("SENT")
    bridge = _bridge(tmp_path, worker)

    with pytest.raises(PermissionError, match="CONTROLLED_TEST_AUTHORIZATION_REQUIRED"):
        bridge.execute_test_transport(
            mapped_record=_mapped_record(),
            run_id="operator-run-001",
            authorization="SEND_TO_PROSPECT",
            mode="TEST",
        )

    assert worker.calls == 0


def test_preview_runs_same_worker_without_send_attempt(tmp_path):
    worker = WorkerStub("READY")
    bridge = _bridge(tmp_path, worker, enabled=False)

    receipt = bridge.execute_test_transport(
        mapped_record=_mapped_record(),
        run_id="operator-run-001",
        authorization=TEST_TRANSPORT_AUTHORIZATION,
        mode="TEST",
        dispatch=False,
    )

    assert receipt["transport_status"] == "READY"
    assert receipt["state_history"] == ["READY_FOR_EMAIL", "HANDOFF_CREATED", "READY"]
    assert receipt["transport_called"] is False
    assert receipt["smtp_sent"] is False
    assert "--preview" in worker.commands[0][0]


def test_failed_transport_retry_is_bounded_across_receipts(tmp_path):
    worker = WorkerStub("FAILED")
    bridge = _bridge(tmp_path, worker)
    first = _execute(bridge)
    second = _execute(bridge, receipts=[first])
    third = _execute(bridge, receipts=[first, second])

    assert first["transport_called"] is True
    assert second["transport_called"] is True
    assert third["transport_called"] is False
    assert third["error"] == "REDIFF_TRANSPORT_RETRY_LIMIT_REACHED"
    assert worker.calls == 2
