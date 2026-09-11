"""Evidence Provenance Tracker — Prevents evidence leakage across candidates, facilities, and companies.

When evidence is gathered (e.g., CAPEX trigger, facility location, person identity, contact details,
calibration needs), it is tagged with an immutable provenance footprint:
- person_name
- company
- facility
- trigger_context
- source metadata & cryptographic raw text hash

If a candidate, facility, trigger, or company changes:
1. The old evidence is marked STALE or INVALID for the new target.
2. Evidence leakage is strictly prevented: a new person or facility cannot inherit superseded evidence.
3. Historical audit records remain intact for forensic compliance.

INVARIANTS:
1. Every evidence record carries an evidence_id and provenance footprint.
2. Cross-candidate, cross-facility, and cross-company evidence contamination is blocked.
3. Provenance checks are applied deterministically at query and staging time.
4. Cryptographic raw_text_hash guarantees snippet immutability.
"""
from __future__ import annotations

import hashlib
import logging
import urllib.parse
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def compute_text_hash(text: str) -> str:
    """Compute deterministic SHA256 hash of raw text or snippet."""
    if not text:
        return ""
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()[:16]


def extract_domain(url: str) -> str:
    """Extract registered domain or hostname from a URL."""
    if not url:
        return ""
    try:
        parsed = urllib.parse.urlparse(url)
        return parsed.netloc.lower()
    except Exception:
        return ""


@dataclass
class EvidenceProvenanceRecord:
    """Canonical Evidence Provenance Record with comprehensive traceability."""
    evidence_id: str
    claim_type: str  # CAPEX_TRIGGER, FACILITY_LOCATION, PERSON_IDENTITY, CALIBRATION_NEED, REACHABLE_CONTACT
    company: str
    facility: str = ""
    person: str = ""
    trigger_context: str = ""
    source_url: str = ""
    source_domain: str = ""
    source_title: str = ""
    publication_date: str = ""
    retrieved_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    snippet: str = ""
    raw_text_hash: str = ""
    recency: str = ""
    company_match: bool = True
    facility_match: bool = True
    person_match: bool = True
    trigger_match: bool = True
    confidence: float = 1.0
    provenance: Dict[str, Any] = field(default_factory=dict)
    is_superseded: bool = False
    superseded_reason: str = ""

    def __post_init__(self):
        if not self.source_domain and self.source_url:
            self.source_domain = extract_domain(self.source_url)
        if not self.raw_text_hash and self.snippet:
            self.raw_text_hash = compute_text_hash(self.snippet)
        if not self.evidence_id:
            raw_id = f"{self.company}|{self.facility}|{self.person}|{self.claim_type}|{self.source_url}|{self.raw_text_hash}"
            self.evidence_id = f"ev_{hashlib.sha256(raw_id.encode('utf-8')).hexdigest()[:12]}"
        if not self.provenance:
            self.provenance = {
                "source": self.source_domain or "unknown",
                "retrieved_at": self.retrieved_at,
                "confidence": self.confidence,
                "claim_type": self.claim_type,
            }

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProvenanceCheckResult:
    """Result of validating evidence provenance against a target context."""
    is_valid: bool
    reason: str
    leakage_detected: bool = False
    leakage_type: str = ""  # CANDIDATE_LEAKAGE, FACILITY_LEAKAGE, COMPANY_LEAKAGE, TRIGGER_LEAKAGE
    stale_person: Optional[str] = None
    stale_facility: Optional[str] = None
    stale_company: Optional[str] = None
    needs_verification: bool = False
    current_person: str = ""
    current_facility: str = ""
    current_company: str = ""


def check_evidence_leakage(
    evidence: Dict[str, Any] | EvidenceProvenanceRecord,
    target_company: str,
    target_facility: str = "",
    target_person: str = "",
    target_trigger: str = "",
) -> ProvenanceCheckResult:
    """Check whether using this evidence for target context would cause evidence leakage.

    Strictly prevents:
    1. Cross-company leakage: Evidence from Company A used for Company B.
    2. Cross-candidate leakage: Evidence from Person A (e.g. Rakesh Sharma) used for Person B (e.g. Sunil Kumar).
    3. Cross-facility leakage: Evidence from Facility A (e.g. Noida Plant) used for Facility B (e.g. Dahej Plant).
    4. Cross-trigger leakage: Obsolete trigger claims associated with incompatible scope.
    """
    ev_dict = evidence.to_dict() if isinstance(evidence, EvidenceProvenanceRecord) else evidence

    provenance_meta = ev_dict.get("provenance", {}) or ev_dict.get("_provenance", {})
    orig_company = (ev_dict.get("company") or provenance_meta.get("company") or "").strip()
    orig_facility = (ev_dict.get("facility") or provenance_meta.get("facility") or "").strip()
    orig_person = (ev_dict.get("person") or provenance_meta.get("person_tag") or provenance_meta.get("person") or "").strip()
    orig_trigger = (ev_dict.get("trigger_context") or provenance_meta.get("trigger_context") or "").strip()

    ev_company = orig_company.lower()
    ev_facility = orig_facility.lower()
    ev_person = orig_person.lower()
    ev_trigger = orig_trigger.lower()

    tgt_company = target_company.strip().lower()
    tgt_facility = target_facility.strip().lower()
    tgt_person = target_person.strip().lower()
    tgt_trigger = target_trigger.strip().lower()

    # 1. Company check
    if ev_company and tgt_company and ev_company != tgt_company:
        return ProvenanceCheckResult(
            is_valid=False,
            reason=f"Evidence belongs to company '{orig_company}', not target '{target_company}'",
            leakage_detected=True,
            leakage_type="COMPANY_LEAKAGE",
            stale_company=orig_company,
            current_company=target_company,
            current_person=target_person,
            current_facility=target_facility,
        )

    # 2. Person / Candidate check (prevent candidate A data leaking to candidate B)
    if ev_person and tgt_person and ev_person != tgt_person:
        return ProvenanceCheckResult(
            is_valid=False,
            reason=f"Evidence gathered for '{orig_person}' cannot be used for target candidate '{target_person}' (superseded candidate leakage)",
            leakage_detected=True,
            leakage_type="CANDIDATE_LEAKAGE",
            stale_person=orig_person,
            current_person=target_person,
            current_company=target_company,
            current_facility=target_facility,
        )

    # 3. Facility check (prevent Plant X data leaking to Plant Y)
    if ev_facility and tgt_facility and ev_facility != tgt_facility:
        return ProvenanceCheckResult(
            is_valid=False,
            reason=f"Evidence gathered for facility '{orig_facility}' cannot be applied to target facility '{target_facility}'",
            leakage_detected=True,
            leakage_type="FACILITY_LEAKAGE",
            stale_facility=orig_facility,
            current_facility=target_facility,
            current_company=target_company,
            current_person=target_person,
        )

    # 4. Trigger check
    if ev_trigger and tgt_trigger and ev_trigger != tgt_trigger:
        return ProvenanceCheckResult(
            is_valid=False,
            reason=f"Evidence gathered under trigger context '{orig_trigger}' does not match current trigger '{target_trigger}'",
            leakage_detected=True,
            leakage_type="TRIGGER_LEAKAGE",
            current_company=target_company,
            current_person=target_person,
            current_facility=target_facility,
        )

    return ProvenanceCheckResult(
        is_valid=True,
        reason="Provenance verified: no evidence leakage detected across company, facility, candidate, or trigger.",
        leakage_detected=False,
        current_person=target_person,
        current_facility=target_facility,
        current_company=target_company,
    )


def tag_evidence(
    evidence: Dict[str, Any],
    person_name: str,
    company: str,
    facility: str = "",
    evidence_type: str = "general",
    source: str = "unknown",
    source_url: str = "",
    snippet: str = "",
    confidence: float = 1.0,
    claim_type: str = "GENERAL_EVIDENCE",
    trigger_context: str = "",
) -> Dict[str, Any]:
    """Tag an evidence record with immutable provenance metadata.
    Returns a new dict without mutating input.
    """
    tagged = dict(evidence)
    text_hash = compute_text_hash(snippet or str(evidence))
    raw_id = f"{company}|{facility}|{person_name}|{claim_type}|{source_url}|{text_hash}"
    ev_id = f"ev_{hashlib.sha256(raw_id.encode('utf-8')).hexdigest()[:12]}"

    now_iso = datetime.now(timezone.utc).isoformat()
    tagged["evidence_id"] = ev_id
    tagged["claim_type"] = claim_type
    tagged["company"] = company
    tagged["facility"] = facility
    tagged["person"] = person_name
    tagged["trigger_context"] = trigger_context
    tagged["source_url"] = source_url
    tagged["source_domain"] = extract_domain(source_url) if source_url else ""
    tagged["snippet"] = snippet
    tagged["raw_text_hash"] = text_hash
    tagged["confidence"] = confidence
    tagged["retrieved_at"] = now_iso

    tagged["_provenance"] = {
        "evidence_id": ev_id,
        "person_tag": person_name,
        "company": company,
        "facility": facility,
        "trigger_context": trigger_context,
        "evidence_type": evidence_type,
        "source": source,
        "source_url": source_url,
        "tagged_at": now_iso,
        "confidence": confidence,
    }
    return tagged


def filter_valid_evidence(
    evidence_list: List[Dict[str, Any]],
    current_person: str,
    current_company: str,
    current_facility: str = "",
    current_trigger: str = "",
) -> List[Dict[str, Any]]:
    """Filter evidence records to only those valid for target context.

    Excludes records originating from superseded candidates, mismatched facilities,
    or different companies. Logs leakage events.
    """
    valid = []
    leakage_count = 0
    for ev in evidence_list:
        res = check_evidence_leakage(
            ev,
            target_company=current_company,
            target_facility=current_facility,
            target_person=current_person,
            target_trigger=current_trigger,
        )
        if res.is_valid:
            valid.append(ev)
        else:
            leakage_count += 1
            logger.info(
                "Filtered out leaked/stale evidence [%s]: %s (stale_person=%s, stale_facility=%s)",
                res.leakage_type, res.reason, res.stale_person, res.stale_facility,
            )

    if leakage_count:
        logger.info(
            "Provenance filter: %d valid, %d filtered out for %s at %s (%s)",
            len(valid), leakage_count, current_person, current_company, current_facility or "all-facilities",
        )
    return valid
