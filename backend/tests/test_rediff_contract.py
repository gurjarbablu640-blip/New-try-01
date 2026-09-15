import csv
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from services.sales_personalization import sales_personalization_pipeline
from services.rediff_sender_adapter import RediffSenderAdapter, REDIFF_CSV_FIELDS
from services.rediff_transport_bridge import RediffTransportBridge


def test_salesoorja_personalization_maps_to_canonical_final_fields():
    """Approved Salesoorja subject and body must map directly to canonical transport fields."""
    record = {
        "company": "RenewSys India",
        "facility": "Module Manufacturing Facility",
        "person": "Sadhasivam Durairaj",
        "email": "sadhasivam.durairaj@renewsysindia.com",
    }
    outreach = {
        "status": "VALIDATED",
        "quality_score": 95.0,
        "subject": "Precision Calibration for Module Manufacturing Facility",
        "body": "<p>Approved personalized outreach content</p>",
        "followups": {},
        "llm_provider_used": "DEEPSEEK",
    }
    enriched = sales_personalization_pipeline.enrich_record_for_rediff(record, outreach)

    assert enriched["FINAL_SUBJECT"] == outreach["subject"]
    assert enriched["SUBJECT"] == outreach["subject"]
    assert enriched["FINAL_BODY_HTML"] == outreach["body"]
    assert enriched["BODY_HTML"] == outreach["body"]
    assert enriched["FINAL_BODY_TEXT"] == outreach["body"]
    assert enriched["BODY_TEXT"] == outreach["body"]


def test_rediff_sender_adapter_writes_canonical_fields_to_prepared_csv(tmp_path):
    """Rediff adapter must write non-empty approved copy into prepared CSV."""
    adapter = RediffSenderAdapter()
    record = {
        "company": "RenewSys India",
        "facility": "Module Manufacturing Facility",
        "person": "Sadhasivam Durairaj",
        "email": "sadhasivam.durairaj@renewsysindia.com",
        "FINAL_SUBJECT": "Approved Subject Line",
        "SUBJECT": "Approved Subject Line",
        "FINAL_BODY_HTML": "<p>Approved Body</p>",
        "BODY_HTML": "<p>Approved Body</p>",
        "FINAL_BODY_TEXT": "Approved Body",
        "BODY_TEXT": "Approved Body",
        "READY_FOR_EMAIL": "YES",
        "PERSONALIZATION_STATUS": "VALIDATED",
        "PERSONALIZATION_SCORE": 95.0,
        "evidence": {
            "exact_facility": {"verified": True},
            "reachable_email": {"mailbox_verified": True},
        },
    }
    mapped = adapter._map_record(
        record,
        campaign="salesoorja-autonomous-outbound",
        followup_stage="INITIAL",
        message_id="<test-msg-id@oorjatechnical.org>",
        in_reply_to="",
        references="",
    )

    assert mapped["FINAL_SUBJECT"] == "Approved Subject Line"
    assert mapped["SUBJECT"] == "Approved Subject Line"
    assert mapped["FINAL_BODY_HTML"] == "<p>Approved Body</p>"
    assert mapped["BODY_HTML"] == "<p>Approved Body</p>"
    assert mapped["EMAIL"] == "sadhasivam.durairaj@renewsysindia.com"
    assert mapped["CC"] == "Bablu@oorjatechnical.org"


def test_transport_worker_direct_smtp_path(tmp_path):
    """Transport worker must use direct SMTP path without altering copy when final fields are present."""
    worker_script = Path(__file__).resolve().parent.parent / "scripts" / "rediff_transport_worker.py"
    system_dir = tmp_path / "system"
    system_dir.mkdir()
    (system_dir / "campaign_runner.py").write_text("# marker", encoding="utf-8")
    (system_dir / "config.py").write_text(
        "EMAIL_ADDRESS = 'Bablu@oorjatechnical.org'\n"
        "EMAIL_PASSWORD = 'secret'\n"
        "SMTP_SERVER = 'smtp.example.com'\n"
        "SMTP_PORT = 465\n",
        encoding="utf-8",
    )
    (system_dir / "send_email.py").write_text("# marker", encoding="utf-8")
    (system_dir / "reporter.py").write_text(
        "class OutreachReporter:\n"
        "    def __init__(self, path):\n"
        "        pass\n"
        "    def record_outreach(self, data):\n"
        "        pass\n",
        encoding="utf-8",
    )

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    csv_path = run_dir / "prepared_record.csv"
    result_path = run_dir / "transport_result.json"
    html_path = run_dir / "unused.html"
    html_path.write_text("<p>Unused HTML</p>", encoding="utf-8")

    record = {
        "LEAD_ID": "lead-001",
        "COMPANY": "RenewSys India",
        "FACILITY": "Module Manufacturing Facility",
        "CONTACT_NAME": "Sadhasivam Durairaj",
        "EMAIL": "sadhasivam.durairaj@renewsysindia.com",
        "FINAL_SUBJECT": "Approved Precision Calibration",
        "SUBJECT": "Approved Precision Calibration",
        "FINAL_BODY_HTML": "<p>Approved Body HTML Content</p>",
        "BODY_HTML": "<p>Approved Body HTML Content</p>",
        "SCORE": "95.0",
        "TRIGGER": "plant_expansion",
        "MESSAGE_ID": "<custom-msg-id@oorjatechnical.org>",
    }
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(record.keys()))
        writer.writeheader()
        writer.writerow(record)

    with patch("smtplib.SMTP_SSL") as mock_smtp_ssl:
        mock_server = MagicMock()
        mock_smtp_ssl.return_value = mock_server

        # Import and run worker main() with mocked arguments
        sys_path_save = list(sys.path)
        saved_config = sys.modules.get("config")
        try:
            from scripts import rediff_transport_worker

            test_args = [
                "rediff_transport_worker.py",
                "--system-path", str(system_dir),
                "--csv", str(csv_path),
                "--html", str(html_path),
                "--result", str(result_path),
                "--recipient", "sadhasivam.durairaj@renewsysindia.com",
                "--cc", "Bablu@oorjatechnical.org",
                "--mode", "production",
            ]
            with patch.object(sys, "argv", test_args):
                exit_code = rediff_transport_worker.main()

            assert exit_code == 0
            assert result_path.is_file()
            result = json.loads(result_path.read_text(encoding="utf-8"))
            assert result["transport_status"] == "SENT"
            assert result["message_id"] == "<custom-msg-id@oorjatechnical.org>"
            assert result["error"] is None

            # Verify SMTP was called with unchanged approved copy
            mock_server.login.assert_called_once_with("Bablu@oorjatechnical.org", "secret")
            mock_server.sendmail.assert_called_once()
            args, _ = mock_server.sendmail.call_args
            sender, envelope, raw_msg = args
            assert sender == "Bablu@oorjatechnical.org"
            assert envelope == ["sadhasivam.durairaj@renewsysindia.com", "Bablu@oorjatechnical.org"]
            assert "Approved Precision Calibration" in raw_msg
            assert "<p>Approved Body HTML Content</p>" in raw_msg
        finally:
            sys.path[:] = sys_path_save
            if saved_config is not None:
                sys.modules["config"] = saved_config
            else:
                sys.modules.pop("config", None)


def test_transport_worker_blocks_legacy_fallback_when_fields_missing(tmp_path):
    """Production transport worker must fail with TRANSPORT_PAYLOAD_INVALID if final copy is missing."""
    system_dir = tmp_path / "system"
    system_dir.mkdir()
    (system_dir / "campaign_runner.py").write_text("# marker", encoding="utf-8")
    (system_dir / "config.py").write_text("EMAIL_ADDRESS = 'Bablu@oorjatechnical.org'\n", encoding="utf-8")

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    csv_path = run_dir / "prepared_record.csv"
    result_path = run_dir / "transport_result.json"
    html_path = run_dir / "unused.html"

    # Missing FINAL_SUBJECT and FINAL_BODY_HTML
    record = {
        "LEAD_ID": "lead-001",
        "COMPANY": "RenewSys India",
        "CONTACT_NAME": "Sadhasivam Durairaj",
        "EMAIL": "sadhasivam.durairaj@renewsysindia.com",
        "FINAL_SUBJECT": "",
        "SUBJECT": "",
        "FINAL_BODY_HTML": "",
        "BODY_HTML": "",
    }
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(record.keys()))
        writer.writeheader()
        writer.writerow(record)

    sys_path_save = list(sys.path)
    saved_config = sys.modules.get("config")
    try:
        from scripts import rediff_transport_worker

        test_args = [
            "rediff_transport_worker.py",
            "--system-path", str(system_dir),
            "--csv", str(csv_path),
            "--html", str(html_path),
            "--result", str(result_path),
            "--recipient", "sadhasivam.durairaj@renewsysindia.com",
            "--cc", "Bablu@oorjatechnical.org",
            "--mode", "production",
        ]
        with patch.object(sys, "argv", test_args):
            exit_code = rediff_transport_worker.main()

        assert exit_code == 1
        assert result_path.is_file()
        result = json.loads(result_path.read_text(encoding="utf-8"))
        assert result["transport_status"] == "FAILED"
        assert result["error"] == "TRANSPORT_PAYLOAD_INVALID"
        assert "Production transport requires non-empty approved copy" in result.get("detail", "")
    finally:
        sys.path[:] = sys_path_save
        if saved_config is not None:
            sys.modules["config"] = saved_config
        else:
            sys.modules.pop("config", None)
