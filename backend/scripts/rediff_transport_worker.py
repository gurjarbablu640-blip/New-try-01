"""Isolated worker that invokes the existing Rediff campaign transport.

Salesoorja owns the final subject and body copy.
Rediff serves as transport only: it delivers the content Salesoorja gives it
without rewriting or altering it.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import io
import json
import os
import smtplib
import ssl
import sys
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import make_msgid
from pathlib import Path


def _arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--system-path", required=True)
    parser.add_argument("--csv", required=True)
    parser.add_argument("--html", required=True)
    parser.add_argument("--result", required=True)
    parser.add_argument("--recipient", required=True)
    parser.add_argument("--mode", choices=("test", "single-live", "production"), default="test")
    parser.add_argument("--cc", default="")
    parser.add_argument("--preview", action="store_true")
    return parser.parse_args(argv)


parse_args = _arguments


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
        if "config" in sys.modules and not hasattr(sys.modules["config"], "EMAIL_ADDRESS"):
            del sys.modules["config"]
        import config
        import send_email
        import reporter

        with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        if len(rows) != 1:
            raise PermissionError("SINGLE_RECORD_REQUIRED")

        row = rows[0]
        final_subject = str(row.get("FINAL_SUBJECT") or row.get("SUBJECT") or "").strip()
        final_body = str(row.get("FINAL_BODY_HTML") or row.get("BODY_HTML") or "").strip()
        if not final_body and html_path.is_file():
            final_body = html_path.read_text(encoding="utf-8").strip()

        if args.mode in {"single-live", "production"}:
            row_recipient = str(row.get("EMAIL") or row.get("EMAIL_ID") or "").strip()
            if not row_recipient or row_recipient.casefold() != args.recipient.casefold():
                raise PermissionError("LIVE_RECIPIENT_ASSERTION_FAILED")
            if args.cc.casefold() != expected_recipient.casefold():
                raise PermissionError("LIVE_CC_ASSERTION_FAILED")
            if not final_subject or not final_body:
                result["transport_status"] = "FAILED"
                result["error"] = "TRANSPORT_PAYLOAD_INVALID"
                result["detail"] = (
                    f"Production transport requires non-empty approved copy: "
                    f"subject={'PRESENT' if final_subject else 'MISSING'}, "
                    f"body={'PRESENT' if final_body else 'MISSING'}"
                )
                result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
                return 1
            test_mode = False
            to_addr = args.recipient
            cc_addr = expected_recipient
            envelope = [to_addr, cc_addr]
        else:
            if args.recipient.casefold() != expected_recipient.casefold():
                raise PermissionError("TEST_RECIPIENT_OVERRIDE_FAILED")
            test_mode = True
            to_addr = expected_recipient
            cc_addr = ""
            envelope = [expected_recipient]

        os.chdir(result_path.parent)
        config.CSV_FILE = str(csv_path)
        config.HTML_FILE = str(html_path)
        report_file = str(result_path.parent / "Outreach_Report.xlsx")
        log_file = str(result_path.parent / "personalized_email_log.csv")
        config.REPORT_FILE = report_file
        config.LOG_FILE = log_file
        config.SEND_DELAY_SECONDS = 0

        # When Salesoorja provides the final subject and body, Rediff acts strictly
        # as transport-only without rewriting or re-running copy optimizers.
        if final_subject and final_body:
            subject = f"[TEST] {final_subject}" if test_mode and not final_subject.startswith("[TEST]") else final_subject
            msg_id = str(row.get("MESSAGE_ID") or "").strip() or make_msgid(domain="oorjatechnical.org")
            in_reply_to = str(row.get("IN_REPLY_TO") or "").strip()
            references = str(row.get("REFERENCES") or "").strip()

            if args.preview:
                result["transport_status"] = "READY"
                result["message_id"] = msg_id
                result["error"] = None
                result["preview"] = {
                    "subject": subject,
                    "body_html": final_body,
                    "personalization_score": float(row.get("PERSONALIZATION_SCORE") or row.get("SCORE") or 85.0),
                    "claim_validation": "PASS",
                    "rediff_eligible": True,
                }
            else:
                msg = MIMEMultipart("alternative")
                msg["From"] = config.EMAIL_ADDRESS
                msg["To"] = to_addr
                if cc_addr:
                    msg["CC"] = cc_addr
                msg["Subject"] = subject
                msg["Message-ID"] = msg_id
                if in_reply_to:
                    msg["In-Reply-To"] = in_reply_to
                if references:
                    msg["References"] = references
                msg.attach(MIMEText(final_body, "html"))

                server = smtplib.SMTP_SSL(
                    config.SMTP_SERVER,
                    config.SMTP_PORT,
                    context=ssl.create_default_context(),
                )
                try:
                    server.login(config.EMAIL_ADDRESS, config.EMAIL_PASSWORD)
                    server.sendmail(config.EMAIL_ADDRESS, envelope, msg.as_string())
                finally:
                    with contextlib.suppress(Exception):
                        server.quit()

                result["transport_status"] = "SENT"
                result["message_id"] = msg_id
                result["error"] = None

                # Log transport success
                os.makedirs(os.path.dirname(log_file) or ".", exist_ok=True)
                with open(log_file, "a", newline="", encoding="utf-8") as l_fh:
                    csv.writer(l_fh).writerow([
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        row.get("COMPANY", ""),
                        row.get("CONTACT_NAME", ""),
                        to_addr,
                        subject,
                        cc_addr,
                        "SUCCESS",
                        "",
                        row.get("TRIGGER", ""),
                        row.get("SCORE", ""),
                    ])

                rep = reporter.OutreachReporter(report_file)
                rep.record_outreach({
                    "Mode": "TEST" if test_mode else "PRODUCTION",
                    "Lead_ID": row.get("LEAD_ID", ""),
                    "Company": row.get("COMPANY", ""),
                    "Facility": row.get("FACILITY", ""),
                    "City": row.get("CITY", ""),
                    "State": row.get("STATE", ""),
                    "Contact_Name": row.get("CONTACT_NAME", ""),
                    "Designation": row.get("DESIGNATION", ""),
                    "Email": to_addr,
                    "Phone": row.get("PHONE", ""),
                    "Persona": row.get("PERSONA", ""),
                    "Trigger_Event": row.get("TRIGGER", ""),
                    "Trigger_Date": row.get("TRIGGER_DATE", ""),
                    "Calibration_Opportunity": row.get("CALIBRATION_OPPORTUNITY", ""),
                    "Lead_Score": row.get("SCORE", ""),
                    "Subject": subject,
                    "To": to_addr,
                    "CC": cc_addr,
                    "Status": "SENT",
                    "Attempt_Number": 1,
                    "Notes": "Delivered via Salesoorja transport-only Rediff bridge",
                    "Error": "",
                })
        elif args.mode in {"single-live", "production"}:
            result["transport_status"] = "FAILED"
            result["error"] = "TRANSPORT_PAYLOAD_INVALID"
            result["detail"] = "Production transport must never invoke legacy campaign runner fallback"
            result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
            return 1
        else:
            # Fallback for legacy records without final copy: run campaign runner
            import campaign_runner

            config.TEST_MODE = test_mode
            config.CC_ADDRESS = expected_recipient
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
            if args.mode in {"single-live", "production"} and lead_result:
                template = html_path.read_text(encoding="utf-8")
                rendered_html = send_email.personalize(
                    template,
                    lead_result.get("enriched_lead") or row,
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
        result["transport_status"] = "FAILED"
        result["error"] = type(exc).__name__
        result["detail"] = str(exc)
    result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0 if result["transport_status"] in {"READY", "SENT"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
