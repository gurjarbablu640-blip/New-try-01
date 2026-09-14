"""Isolated worker that invokes the existing Rediff campaign transport."""

from __future__ import annotations

import argparse
import contextlib
import csv
import io
import json
import os
import sys
from pathlib import Path


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--system-path", required=True)
    parser.add_argument("--csv", required=True)
    parser.add_argument("--html", required=True)
    parser.add_argument("--result", required=True)
    parser.add_argument("--recipient", required=True)
    parser.add_argument("--mode", choices=("test", "single-live"), default="test")
    parser.add_argument("--cc", default="")
    parser.add_argument("--preview", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    system_path = Path(args.system_path).resolve()
    csv_path = Path(args.csv).resolve()
    html_path = Path(args.html).resolve()
    result_path = Path(args.result).resolve()
    expected_recipient = "Bablu@oorjatechnical.org"
    result = {
        "transport_status": "FAILED",
        "message_id": None,
        "error": "REDIFF_TRANSPORT_FAILED",
    }
    try:
        if not (system_path / "campaign_runner.py").is_file():
            raise FileNotFoundError("REDIFF_CAMPAIGN_RUNNER_NOT_FOUND")
        sys.path.insert(0, str(system_path))
        import campaign_runner
        import config
        import send_email

        with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        if len(rows) != 1:
            raise PermissionError("SINGLE_RECORD_REQUIRED")

        if args.mode == "single-live":
            row_recipient = str(rows[0].get("EMAIL") or rows[0].get("EMAIL_ID") or "").strip()
            if not row_recipient or row_recipient.casefold() != args.recipient.casefold():
                raise PermissionError("LIVE_RECIPIENT_ASSERTION_FAILED")
            if args.cc.casefold() != expected_recipient.casefold():
                raise PermissionError("LIVE_CC_ASSERTION_FAILED")
            configured_template = Path(config.HTML_FILE)
            if not configured_template.is_absolute():
                configured_template = system_path / configured_template
            html_path = configured_template.resolve()
            config.TEST_MODE = False
            config.CC_ADDRESS = expected_recipient
            test_mode = False
        else:
            if args.recipient.casefold() != expected_recipient.casefold():
                raise PermissionError("TEST_RECIPIENT_OVERRIDE_FAILED")
            html_path = Path(args.html).resolve()
            config.TEST_MODE = True
            config.CC_ADDRESS = expected_recipient
            test_mode = True

        os.chdir(result_path.parent)

        config.CSV_FILE = str(csv_path)
        config.HTML_FILE = str(html_path)
        config.REPORT_FILE = str(result_path.parent / "Outreach_Report.xlsx")
        config.LOG_FILE = str(result_path.parent / "personalized_email_log.csv")
        config.SEND_DELAY_SECONDS = 0

        if test_mode:
            actual_to = send_email.parse_email_list(config.CC_ADDRESS)
            if config.TEST_MODE is not True:
                raise PermissionError("REDIFF_TEST_MODE_ASSERTION_FAILED")
            if actual_to != [expected_recipient]:
                raise PermissionError("REDIFF_ACTUAL_TO_ASSERTION_FAILED")
        elif config.TEST_MODE is not False:
            raise PermissionError("REDIFF_LIVE_MODE_ASSERTION_FAILED")

        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            summary = campaign_runner.run_campaign(
                explicit_command=not args.preview,
                test_mode=test_mode,
                csv_path=str(csv_path),
                html_path=str(html_path),
            )
        lead_results = summary.get("lead_results") or []
        lead_result = lead_results[0] if len(lead_results) == 1 else {}
        personalization = lead_result.get("personalization") or {}
        if args.mode == "single-live" and lead_result:
            template = html_path.read_text(encoding="utf-8")
            rendered_html = send_email.personalize(
                template,
                lead_result.get("enriched_lead") or rows[0],
                test_mode=False,
            )
            result["preview"] = {
                "subject": personalization.get("subject") or "",
                "body_html": rendered_html,
                "personalization_score": float(personalization.get("copy_quality_score") or 0),
                "research_score": float(personalization.get("research_score") or 0),
                "claim_validation": "PASS" if lead_result.get("eligible") else "FAIL",
                "rediff_eligible": bool(lead_result.get("eligible")),
                "blocker": lead_result.get("blocker"),
                "blocker_reason": lead_result.get("blocker_reason"),
            }
        if args.preview and int(summary.get("eligible") or 0) == 1:
            result["transport_status"] = "READY"
            result["error"] = None
        elif (
            int(summary.get("total_input") or 0) == 1
            and int(summary.get("eligible") or 0) == 1
            and int(summary.get("sent") or 0) == 1
            and int(summary.get("errors") or 0) == 0
        ):
            result["transport_status"] = "SENT"
            result["error"] = None
    except Exception as exc:
        result["error"] = type(exc).__name__
    result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0 if result["transport_status"] in {"READY", "SENT"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
