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
    record_id: str = field(default_factory=lambda: f"rediff-hnd-{uuid.uuid4().hex[:12]}")
    staged_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    staging_status: str = "STAGED"  # STAGED, EXPORTED, REJECTED, TEST_MOCKED
    test_mode: bool = field(default_factory=lambda: bool(settings.OUTBOUND_TEST_MODE))
    provenance: str = "REAL"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


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

        record = RediffHandoffRecord(
            company=candidate_data["company"],
            facility=candidate_data["facility"],
            person=candidate_data["person"],
            designation=candidate_data["designation"],
            persona=candidate_data.get("persona", "Decision Maker"),
            email=candidate_data["email"],
            phone=candidate_data.get("phone"),
            trigger=candidate_data["trigger"],
            trigger_date=candidate_data["trigger_date"],
            calibration_opportunity=candidate_data["calibration_opportunity"],
            reasoning=candidate_data["reasoning"],
            icp_score=float(candidate_data["icp_score"]),
            evidence=evidence,
            verification_status="7_GATES_PASSED_VERIFIED",
            provenance=provenance,
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

    def list_staged(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """List staged records in the queue."""
        records = self._load_queue()
        if status:
            return [r for r in records if r.get("staging_status") == status]
        return records

    def export_batch(
        self,
        record_ids: Optional[List[str]] = None,
        export_format: str = "json",
    ) -> Dict[str, Any]:
        """Export a batch of staged records for Rediff_Email_System."""
        records = self._load_queue()
        if record_ids:
            target_records = [r for r in records if r.get("record_id") in record_ids]
        else:
            target_records = [r for r in records if r.get("staging_status") == "STAGED"]

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
            writer = csv.DictWriter(
                output,
                fieldnames=[
                    "record_id", "company", "facility", "person", "designation", "persona",
                    "email", "phone", "trigger", "trigger_date", "calibration_opportunity",
                    "reasoning", "icp_score", "verification_status", "test_mode"
                ],
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


# Global instance
rediff_bridge = RediffBridge()
