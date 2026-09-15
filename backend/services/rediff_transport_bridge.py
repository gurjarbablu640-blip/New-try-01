"""Guarded execution bridge to the existing Rediff SMTP transport."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

from config import settings
from services.rediff_sender_adapter import BACKEND_ROOT, REDIFF_CSV_FIELDS

TEST_RECIPIENT = "Bablu@oorjatechnical.org"
TEST_TRANSPORT_AUTHORIZATION = "SEND_ONE_REDIFF_TEST_TO_BABLU"
SINGLE_LIVE_AUTHORIZATION = "SEND LIVE TEST"
SINGLE_LIVE_TEST_TYPE = "SINGLE_LIVE_CUSTOMER_TEST"
PRODUCTION_CAMPAIGN = "salesoorja-autonomous-outbound"
SUPPRESSED_DUPLICATE_TRANSPORT = "SUPPRESSED_DUPLICATE_TRANSPORT"
MAX_TRANSPORT_ATTEMPTS = 2


class RediffTransportBridge:
    """Execute a prepared Salesoorja record through Rediff in isolated TEST mode."""

    def __init__(
        self,
        *,
        system_path: Optional[Path] = None,
        run_dir: Optional[Path] = None,
        timeout_seconds: Optional[int] = None,
        enabled: Optional[bool] = None,
        single_live_enabled: Optional[bool] = None,
        production_enabled: Optional[bool] = None,
        process_runner: Callable[..., Any] = subprocess.run,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self.system_path = Path(system_path or settings.REDIFF_SYSTEM_PATH)
        self.run_dir = run_dir or BACKEND_ROOT / "data" / "rediff_transport_runs"
        self.timeout_seconds = int(timeout_seconds or settings.REDIFF_TRANSPORT_TIMEOUT_SECONDS)
        self.enabled = bool(settings.REDIFF_TEST_TRANSPORT_ENABLED if enabled is None else enabled)
        self.single_live_enabled = bool(
            settings.SINGLE_LIVE_CUSTOMER_TEST_ENABLED
            if single_live_enabled is None
            else single_live_enabled
        )
        self.production_enabled = bool(
            (
                str(settings.SALESOORJA_MODE).upper() == "PRODUCTION"
                and settings.REAL_OUTREACH_ENABLED
                and not settings.OUTBOUND_TEST_MODE
                and settings.REDIFF_SENDER_ENABLED
                and not settings.REDIFF_TEST_MODE
            )
            if production_enabled is None
            else production_enabled
        )
        self._process_runner = process_runner
        self._now = now

    def available(self) -> bool:
        return self.system_path.is_dir() and (self.system_path / "campaign_runner.py").is_file()

    @staticmethod
    def duplicate_key(
        *,
        person_reference: Any,
        original_prospect_email: str,
        campaign_reference: str,
        initial_or_followup: str,
    ) -> str:
        parts = (
            str(person_reference or "").strip().casefold(),
            str(original_prospect_email or "").strip().casefold(),
            str(campaign_reference or "").strip().casefold(),
            str(initial_or_followup or "INITIAL").strip().casefold(),
        )
        return "|".join(parts)

    def execute_test_transport(
        self,
        *,
        mapped_record: Mapping[str, Any],
        run_id: str,
        company_reference: Any = None,
        person_reference: Any = None,
        campaign_reference: str = "salesoorja-operator-transport-test",
        initial_or_followup: str = "INITIAL",
        authorization: str,
        existing_receipts: Sequence[Mapping[str, Any]] = (),
        mode: str = "TEST",
        dispatch: bool = True,
    ) -> dict[str, Any]:
        original_prospect_email = str(mapped_record.get("EMAIL") or mapped_record.get("EMAIL_ID") or "").strip()
        duplicate_key = self.duplicate_key(
            person_reference=person_reference or mapped_record.get("CONTACT_NAME"),
            original_prospect_email=original_prospect_email,
            campaign_reference=campaign_reference,
            initial_or_followup=initial_or_followup,
        )
        attempt_number = 1 + sum(1 for receipt in existing_receipts if receipt.get("duplicate_key") == duplicate_key)
        prior_sent = next(
            (
                receipt
                for receipt in existing_receipts
                if receipt.get("duplicate_key") == duplicate_key and receipt.get("transport_status") == "SENT"
            ),
            None,
        )
        if prior_sent:
            return {
                "transport_status": SUPPRESSED_DUPLICATE_TRANSPORT,
                "duplicate_key": duplicate_key,
                "duplicate_of": prior_sent.get("receipt_id"),
                "transport_called": False,
                "smtp_sent": False,
                "recipient": TEST_RECIPIENT,
                "original_prospect_email": original_prospect_email,
                "test_mode": True,
                "attempt_number": attempt_number,
                "initial_or_followup": initial_or_followup,
            }
        if attempt_number > MAX_TRANSPORT_ATTEMPTS:
            return self._failed_receipt(
                run_id=run_id,
                company_reference=company_reference,
                person_reference=person_reference,
                campaign_reference=campaign_reference,
                original_prospect_email=original_prospect_email,
                initial_or_followup=initial_or_followup,
                attempt_number=attempt_number,
                duplicate_key=duplicate_key,
                error="REDIFF_TRANSPORT_RETRY_LIMIT_REACHED",
                state_history=["READY_FOR_EMAIL", "HANDOFF_CREATED"],
                transport_called=False,
            )

        self._assert_test_authorization(
            authorization=authorization,
            mode=mode,
            actual_to=TEST_RECIPIENT,
            cc=(),
            bcc=(),
            original_prospect_email=original_prospect_email,
        )
        if dispatch and not self.enabled:
            return self._failed_receipt(
                run_id=run_id,
                company_reference=company_reference,
                person_reference=person_reference,
                campaign_reference=campaign_reference,
                original_prospect_email=original_prospect_email,
                initial_or_followup=initial_or_followup,
                attempt_number=attempt_number,
                duplicate_key=duplicate_key,
                error="REDIFF_TEST_TRANSPORT_DISABLED",
                state_history=["READY_FOR_EMAIL", "HANDOFF_CREATED"],
                transport_called=False,
            )
        if not self.available():
            return self._failed_receipt(
                run_id=run_id,
                company_reference=company_reference,
                person_reference=person_reference,
                campaign_reference=campaign_reference,
                original_prospect_email=original_prospect_email,
                initial_or_followup=initial_or_followup,
                attempt_number=attempt_number,
                duplicate_key=duplicate_key,
                error="REDIFF_SYSTEM_UNAVAILABLE",
                state_history=["READY_FOR_EMAIL", "HANDOFF_CREATED"],
                transport_called=False,
            )

        execution_id = f"rediff-test-{uuid.uuid4().hex[:12]}"
        execution_dir = self.run_dir / execution_id
        execution_dir.mkdir(parents=True, exist_ok=False)
        csv_path = execution_dir / "prepared_record.csv"
        html_path = execution_dir / "operator_transport_test.html"
        result_path = execution_dir / "transport_result.json"
        self._write_csv(csv_path, mapped_record)
        body_content = str(mapped_record.get("FINAL_BODY_HTML") or mapped_record.get("BODY_HTML") or "").strip()
        html_path.write_text(body_content or self._test_html(), encoding="utf-8")

        worker = BACKEND_ROOT / "scripts" / "rediff_transport_worker.py"
        command = [
            sys.executable,
            str(worker),
            "--system-path",
            str(self.system_path),
            "--csv",
            str(csv_path),
            "--html",
            str(html_path),
            "--result",
            str(result_path),
            "--recipient",
            TEST_RECIPIENT,
        ]
        if not dispatch:
            command.append("--preview")
        state_history = ["READY_FOR_EMAIL", "HANDOFF_CREATED"]
        if dispatch:
            state_history.append("SEND_ATTEMPTED")
        try:
            completed = self._process_runner(
                command,
                cwd=str(execution_dir),
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
            worker_result = json.loads(result_path.read_text(encoding="utf-8")) if result_path.is_file() else {}
            sent = completed.returncode == 0 and worker_result.get("transport_status") == "SENT"
            ready = completed.returncode == 0 and worker_result.get("transport_status") == "READY"
        except (OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError):
            worker_result = {}
            sent = False
            ready = False

        sent_at = self._now().isoformat() if sent else None
        transport_status = "SENT" if sent else "READY" if ready and not dispatch else "FAILED"
        state_history.append(transport_status)
        return {
            "receipt_id": f"receipt-{uuid.uuid4().hex[:12]}",
            "run_id": run_id,
            "company_reference": company_reference,
            "person_reference": person_reference,
            "campaign_reference": campaign_reference,
            "recipient": TEST_RECIPIENT,
            "original_prospect_email": original_prospect_email,
            "test_mode": True,
            "sent_at": sent_at,
            "transport": "EXISTING_REDIFF_CAMPAIGN_RUNNER",
            "transport_status": transport_status,
            "message_id": worker_result.get("message_id"),
            "attempt_number": attempt_number,
            "initial_or_followup": initial_or_followup,
            "error": None if sent or transport_status == "READY" else str(worker_result.get("error") or "REDIFF_TRANSPORT_FAILED"),
            "duplicate_key": duplicate_key,
            "transport_called": dispatch,
            "smtp_sent": sent,
            "actual_to": TEST_RECIPIENT,
            "cc": [],
            "bcc": [],
            "prospect_recipient_count": 0,
            "state_history": state_history,
        }

    def execute_single_live_transport(
        self,
        *,
        mapped_record: Mapping[str, Any],
        run_id: str,
        company_reference: Any,
        person_reference: Any,
        authorization: str,
        existing_receipts: Sequence[Mapping[str, Any]] = (),
        dispatch: bool = False,
    ) -> dict[str, Any]:
        recipient = str(mapped_record.get("EMAIL") or mapped_record.get("EMAIL_ID") or "").strip()
        campaign_reference = "salesoorja-single-live-customer-test"
        initial_or_followup = "INITIAL"
        self._assert_single_live_authorization(
            authorization=authorization,
            recipient=recipient,
            cc=(TEST_RECIPIENT,),
            bcc=(),
        )
        return self._execute_live_transport(
            mapped_record=mapped_record,
            run_id=run_id,
            company_reference=company_reference,
            person_reference=person_reference,
            campaign_reference=campaign_reference,
            initial_or_followup=initial_or_followup,
            touch="INITIAL",
            existing_receipts=existing_receipts,
            dispatch=dispatch,
            enabled=self.single_live_enabled,
            disabled_error="SINGLE_LIVE_CUSTOMER_TEST_DISABLED",
            worker_mode="single-live",
            test_type=SINGLE_LIVE_TEST_TYPE,
        )

    def execute_production_transport(
        self,
        *,
        mapped_record: Mapping[str, Any],
        run_id: str,
        company_reference: Any,
        person_reference: Any,
        campaign_reference: str = PRODUCTION_CAMPAIGN,
        initial_or_followup: str = "INITIAL",
        existing_receipts: Sequence[Mapping[str, Any]] = (),
        dispatch: bool = True,
    ) -> dict[str, Any]:
        recipient = str(mapped_record.get("EMAIL") or mapped_record.get("EMAIL_ID") or "").strip()
        cc = tuple(
            address.strip()
            for address in str(mapped_record.get("CC") or "").replace(";", ",").split(",")
            if address.strip()
        )
        self._assert_production_authorization(recipient=recipient, cc=cc, bcc=())
        return self._execute_live_transport(
            mapped_record=mapped_record,
            run_id=run_id,
            company_reference=company_reference,
            person_reference=person_reference,
            campaign_reference=campaign_reference,
            initial_or_followup=initial_or_followup,
            touch=initial_or_followup,
            existing_receipts=existing_receipts,
            dispatch=dispatch,
            enabled=self.production_enabled,
            disabled_error="PRODUCTION_OUTREACH_DISABLED",
            worker_mode="production",
            test_type=None,
        )

    def _execute_live_transport(
        self,
        *,
        mapped_record: Mapping[str, Any],
        run_id: str,
        company_reference: Any,
        person_reference: Any,
        campaign_reference: str,
        initial_or_followup: str,
        touch: str,
        existing_receipts: Sequence[Mapping[str, Any]],
        dispatch: bool,
        enabled: bool,
        disabled_error: str,
        worker_mode: str,
        test_type: Optional[str],
    ) -> dict[str, Any]:
        recipient = str(mapped_record.get("EMAIL") or mapped_record.get("EMAIL_ID") or "").strip()
        duplicate_key = self.duplicate_key(
            person_reference=person_reference,
            original_prospect_email=recipient,
            campaign_reference=campaign_reference,
            initial_or_followup=initial_or_followup,
        )
        matching_receipts = [receipt for receipt in existing_receipts if receipt.get("duplicate_key") == duplicate_key]
        attempt_number = len(matching_receipts) + 1
        prior_sent = next(
            (receipt for receipt in matching_receipts if receipt.get("transport_status") == "SENT"),
            None,
        )
        if prior_sent:
            return {
                "transport_status": SUPPRESSED_DUPLICATE_TRANSPORT,
                "duplicate_key": duplicate_key,
                "duplicate_of": prior_sent.get("receipt_id"),
                "transport_called": False,
                "smtp_sent": False,
                "recipient": recipient,
                "actual_to": recipient,
                "cc": [TEST_RECIPIENT],
                "bcc": [],
                "test_mode": False,
                "attempt_number": attempt_number,
                "initial_or_followup": initial_or_followup,
                "touch": touch,
                "prospect_recipient_count": 1,
                **({"test_type": test_type} if test_type else {}),
            }
        if attempt_number > MAX_TRANSPORT_ATTEMPTS:
            return self._live_failed_receipt(
                run_id=run_id,
                company_reference=company_reference,
                person_reference=person_reference,
                recipient=recipient,
                attempt_number=attempt_number,
                duplicate_key=duplicate_key,
                error="REDIFF_TRANSPORT_RETRY_LIMIT_REACHED",
                transport_called=False,
                campaign_reference=campaign_reference,
                initial_or_followup=initial_or_followup,
                touch=touch,
                test_type=test_type,
            )
        if dispatch and not enabled:
            return self._live_failed_receipt(
                run_id=run_id,
                company_reference=company_reference,
                person_reference=person_reference,
                recipient=recipient,
                attempt_number=attempt_number,
                duplicate_key=duplicate_key,
                error=disabled_error,
                transport_called=False,
                campaign_reference=campaign_reference,
                initial_or_followup=initial_or_followup,
                touch=touch,
                test_type=test_type,
            )
        if not self.available():
            return self._live_failed_receipt(
                run_id=run_id,
                company_reference=company_reference,
                person_reference=person_reference,
                recipient=recipient,
                attempt_number=attempt_number,
                duplicate_key=duplicate_key,
                error="REDIFF_SYSTEM_UNAVAILABLE",
                transport_called=False,
                campaign_reference=campaign_reference,
                initial_or_followup=initial_or_followup,
                touch=touch,
                test_type=test_type,
            )

        execution_id = f"rediff-live-{uuid.uuid4().hex[:12]}"
        execution_dir = self.run_dir / execution_id
        execution_dir.mkdir(parents=True, exist_ok=False)
        csv_path = execution_dir / "prepared_record.csv"
        result_path = execution_dir / "transport_result.json"
        self._write_csv(csv_path, mapped_record)
        body_content = str(mapped_record.get("FINAL_BODY_HTML") or mapped_record.get("BODY_HTML") or mapped_record.get("BODY_TEXT") or "").strip()
        (execution_dir / "unused.html").write_text(body_content, encoding="utf-8")
        worker = BACKEND_ROOT / "scripts" / "rediff_transport_worker.py"
        command = [
            sys.executable,
            str(worker),
            "--system-path",
            str(self.system_path),
            "--csv",
            str(csv_path),
            "--html",
            str(execution_dir / "unused.html"),
            "--result",
            str(result_path),
            "--recipient",
            recipient,
            "--cc",
            TEST_RECIPIENT,
            "--mode",
            worker_mode,
        ]
        if not dispatch:
            command.append("--preview")
        state_history = ["READY_FOR_EMAIL", "HANDOFF_CREATED"]
        if dispatch:
            state_history.append("SEND_ATTEMPTED")
        try:
            completed = self._process_runner(
                command,
                cwd=str(execution_dir),
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
            worker_result = json.loads(result_path.read_text(encoding="utf-8")) if result_path.is_file() else {}
            sent = completed.returncode == 0 and worker_result.get("transport_status") == "SENT"
            ready = completed.returncode == 0 and worker_result.get("transport_status") == "READY"
        except (OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError):
            worker_result = {}
            sent = False
            ready = False

        transport_status = "SENT" if sent else "READY" if ready and not dispatch else "FAILED"
        state_history.append(transport_status)
        return {
            "receipt_id": f"receipt-{uuid.uuid4().hex[:12]}",
            "run_id": run_id,
            "company_reference": company_reference,
            "person_reference": person_reference,
            "campaign_reference": campaign_reference,
            "recipient": recipient,
            "original_prospect_email": recipient,
            "actual_to": recipient,
            "cc": [TEST_RECIPIENT],
            "bcc": [],
            "test_mode": False,
            "sent_at": self._now().isoformat() if sent else None,
            "transport": "EXISTING_REDIFF_CAMPAIGN_RUNNER",
            "transport_status": transport_status,
            "message_id": worker_result.get("message_id"),
            "attempt_number": attempt_number,
            "initial_or_followup": initial_or_followup,
            "touch": touch,
            "error": None if sent or transport_status == "READY" else str(worker_result.get("error") or "REDIFF_TRANSPORT_FAILED"),
            "duplicate_key": duplicate_key,
            "transport_called": dispatch,
            "smtp_sent": sent,
            "prospect_recipient_count": 1,
            "state_history": state_history,
            "preview": worker_result.get("preview"),
            **({"test_type": test_type} if test_type else {}),
        }

    def _assert_production_authorization(
        self,
        *,
        recipient: str,
        cc: Sequence[str],
        bcc: Sequence[str],
    ) -> None:
        if not self.production_enabled:
            raise PermissionError("PRODUCTION_OUTREACH_DISABLED")
        if not recipient or recipient.casefold() == TEST_RECIPIENT.casefold():
            raise PermissionError("REAL_PROSPECT_RECIPIENT_REQUIRED")
        if tuple(address.casefold() for address in cc) != (TEST_RECIPIENT.casefold(),):
            raise PermissionError("PRODUCTION_CC_MUST_BE_BABLU_ONLY")
        if bcc:
            raise PermissionError("PRODUCTION_BCC_MUST_BE_EMPTY")

    @staticmethod
    def _assert_single_live_authorization(
        *,
        authorization: str,
        recipient: str,
        cc: Sequence[str],
        bcc: Sequence[str],
    ) -> None:
        if authorization != SINGLE_LIVE_AUTHORIZATION:
            raise PermissionError("SINGLE_LIVE_CONFIRMATION_REQUIRED")
        if not recipient or recipient.casefold() == TEST_RECIPIENT.casefold():
            raise PermissionError("ONE_REAL_PROSPECT_RECIPIENT_REQUIRED")
        if tuple(address.casefold() for address in cc) != (TEST_RECIPIENT.casefold(),):
            raise PermissionError("SINGLE_LIVE_CC_MUST_BE_BABLU_ONLY")
        if bcc:
            raise PermissionError("SINGLE_LIVE_BCC_MUST_BE_EMPTY")

    def _live_failed_receipt(
        self,
        *,
        run_id: str,
        company_reference: Any,
        person_reference: Any,
        recipient: str,
        attempt_number: int,
        duplicate_key: str,
        error: str,
        transport_called: bool,
        campaign_reference: str = "salesoorja-single-live-customer-test",
        initial_or_followup: str = "INITIAL",
        touch: str = "INITIAL",
        test_type: Optional[str] = SINGLE_LIVE_TEST_TYPE,
    ) -> dict[str, Any]:
        receipt = {
            "receipt_id": f"receipt-{uuid.uuid4().hex[:12]}",
            "run_id": run_id,
            "company_reference": company_reference,
            "person_reference": person_reference,
            "campaign_reference": campaign_reference,
            "recipient": recipient,
            "original_prospect_email": recipient,
            "actual_to": recipient,
            "cc": [TEST_RECIPIENT],
            "bcc": [],
            "test_mode": False,
            "sent_at": None,
            "transport": "EXISTING_REDIFF_CAMPAIGN_RUNNER",
            "transport_status": "FAILED",
            "message_id": None,
            "attempt_number": attempt_number,
            "initial_or_followup": initial_or_followup,
            "touch": touch,
            "error": error,
            "duplicate_key": duplicate_key,
            "transport_called": transport_called,
            "smtp_sent": False,
            "prospect_recipient_count": 1,
            "state_history": ["READY_FOR_EMAIL", "HANDOFF_CREATED", "FAILED"],
            "preview": None,
        }
        if test_type:
            receipt["test_type"] = test_type
        return receipt

    @staticmethod
    def _assert_test_authorization(
        *,
        authorization: str,
        mode: str,
        actual_to: str,
        cc: Sequence[str],
        bcc: Sequence[str],
        original_prospect_email: str,
    ) -> None:
        if authorization != TEST_TRANSPORT_AUTHORIZATION:
            raise PermissionError("CONTROLLED_TEST_AUTHORIZATION_REQUIRED")
        if str(mode).upper() != "TEST":
            raise PermissionError("CONTROLLED_TRANSPORT_REQUIRES_TEST_MODE")
        if actual_to.casefold() != TEST_RECIPIENT.casefold():
            raise PermissionError("TEST_RECIPIENT_OVERRIDE_FAILED")
        if cc or bcc:
            raise PermissionError("TEST_TRANSPORT_REQUIRES_ZERO_CC_AND_BCC")
        if original_prospect_email.casefold() == actual_to.casefold():
            return
        if not original_prospect_email:
            raise PermissionError("ORIGINAL_PROSPECT_METADATA_REQUIRED")

    @staticmethod
    def _write_csv(path: Path, mapped_record: Mapping[str, Any]) -> None:
        with path.open("x", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=REDIFF_CSV_FIELDS)
            writer.writeheader()
            writer.writerow({field: mapped_record.get(field, "") for field in REDIFF_CSV_FIELDS})

    @staticmethod
    def _test_html() -> str:
        return """<html><body>SALESOORJA OPERATOR TRANSPORT TEST<br><br>This email proves that the autonomous Salesoorja operator successfully passed qualification, personalization, readiness, Rediff transport and receipt persistence.<br><br>No real prospect received this message.</body></html>"""

    def _failed_receipt(
        self,
        *,
        run_id: str,
        company_reference: Any,
        person_reference: Any,
        campaign_reference: str,
        original_prospect_email: str,
        initial_or_followup: str,
        attempt_number: int,
        duplicate_key: str,
        error: str,
        state_history: list[str],
        transport_called: bool,
    ) -> dict[str, Any]:
        return {
            "receipt_id": f"receipt-{uuid.uuid4().hex[:12]}",
            "run_id": run_id,
            "company_reference": company_reference,
            "person_reference": person_reference,
            "campaign_reference": campaign_reference,
            "recipient": TEST_RECIPIENT,
            "original_prospect_email": original_prospect_email,
            "test_mode": True,
            "sent_at": None,
            "transport": "EXISTING_REDIFF_CAMPAIGN_RUNNER",
            "transport_status": "FAILED",
            "message_id": None,
            "attempt_number": attempt_number,
            "initial_or_followup": initial_or_followup,
            "error": error,
            "duplicate_key": duplicate_key,
            "transport_called": transport_called,
            "smtp_sent": False,
            "actual_to": TEST_RECIPIENT,
            "cc": [],
            "bcc": [],
            "prospect_recipient_count": 0,
            "state_history": state_history + ["FAILED"],
        }
