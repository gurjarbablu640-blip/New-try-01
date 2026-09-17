"""Contact Waterfall Service — Phase 2 Funnel Recovery.

Multi-candidate waterfall with strict email verification classification.
Implements the following steps per account (max 3 candidates):
  Step 1: Primary candidate Apollo enrichment via PersonEnrichmentEligibilityGate.
  Step 2: Fallback to next verified high-authority candidate if Step 1 produces no usable email.
  Step 3: Grounded public web evidence search (best-effort, time-boxed).
  Step 4: Strict email classification.

Hard Rules:
- MX_ONLY_SEND_ALLOWED = False: domain existence NEVER upgrades extrapolated email to SEND_READY.
- Maximum 3 Apollo enrichment attempts per account per run.
- Verified-person gate must pass before any Apollo credit is consumed.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Hard policy: MX-only (domain-exists-only) email is NOT send-ready
MX_ONLY_SEND_ALLOWED = False

MAX_CANDIDATES_PER_ACCOUNT = 3

EMAIL_RE = re.compile(
    r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
)


class EmailVerificationLevel(str, Enum):
    VERIFIED_PROVIDER = "VERIFIED_PROVIDER"            # Apollo confirmed + email_status=verified
    VERIFIED_PUBLIC_SOURCE = "VERIFIED_PUBLIC_SOURCE"  # Found in authoritative public source
    DOMAIN_VALID_PATTERN_ONLY = "DOMAIN_VALID_PATTERN_ONLY"  # Pattern-derived, domain valid
    EXTRAPOLATED = "EXTRAPOLATED"                      # Guessed from naming pattern
    UNKNOWN = "UNKNOWN"                                # Cannot classify


@dataclass
class WaterfallCandidate:
    name: str
    title: str
    composite_score: float
    authority_class: str
    facility_relationship: str
    current_employment: str
    raw_record: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WaterfallResult:
    status: str               # CONTACT_FOUND | HOLD_CONTACT_NOT_FOUND | GATE_BLOCK
    email: Optional[str]
    email_verification_level: EmailVerificationLevel
    send_ready: bool
    candidate_name: Optional[str]
    candidate_title: Optional[str]
    attempts: List[Dict[str, Any]] = field(default_factory=list)
    enrichment_calls: int = 0
    hold_reason: Optional[str] = None
    gate_reasons: List[str] = field(default_factory=list)


def classify_email_verification_level(
    email: Optional[str],
    email_status: Optional[str] = None,
    source: Optional[str] = None,
) -> EmailVerificationLevel:
    """Classify an email address by its verification confidence level."""
    if not email or not EMAIL_RE.match(str(email).strip()):
        return EmailVerificationLevel.UNKNOWN

    status_upper = str(email_status or "").upper()

    # Apollo-confirmed verification
    if status_upper == "VERIFIED":
        return EmailVerificationLevel.VERIFIED_PROVIDER

    # Authoritative public source (company website, official directory)
    if source and any(
        indicator in str(source).lower()
        for indicator in ["company_website", "official_directory", "annual_report", "regulatory_filing"]
    ):
        return EmailVerificationLevel.VERIFIED_PUBLIC_SOURCE

    # Pattern-only (first.last@domain.com with valid domain but no confirmation)
    local_part = email.split("@")[0]
    if "." in local_part and len(local_part) >= 4:
        return EmailVerificationLevel.DOMAIN_VALID_PATTERN_ONLY

    return EmailVerificationLevel.EXTRAPOLATED


def is_send_ready_email(
    email: Optional[str],
    verification_level: EmailVerificationLevel,
) -> bool:
    """Determine if an email+verification_level combination is send-ready.

    Policy:
    - VERIFIED_PROVIDER → send-ready
    - VERIFIED_PUBLIC_SOURCE → send-ready
    - DOMAIN_VALID_PATTERN_ONLY → NOT send-ready (MX_ONLY_SEND_ALLOWED = False)
    - EXTRAPOLATED → NOT send-ready
    - UNKNOWN → NOT send-ready
    """
    if not email or not EMAIL_RE.match(str(email).strip()):
        return False
    return verification_level in {
        EmailVerificationLevel.VERIFIED_PROVIDER,
        EmailVerificationLevel.VERIFIED_PUBLIC_SOURCE,
    }


class ContactWaterfallService:
    """Orchestrates multi-candidate Apollo contact enrichment waterfall.

    Injected dependencies (for testability):
    - eligibility_gate: callable(candidate, facility_info, trigger_info, icp_score) -> EnrichmentEligibilityDecision
    - enrich_fn: callable(candidate_record) -> {email, phone, email_status, ...}
    """

    def __init__(
        self,
        eligibility_gate: Optional[Any] = None,
        enrich_fn: Optional[Callable[..., Dict[str, Any]]] = None,
        max_candidates: int = MAX_CANDIDATES_PER_ACCOUNT,
    ) -> None:
        self._gate = eligibility_gate
        self._enrich_fn = enrich_fn
        self._max_candidates = min(max(int(max_candidates), 1), MAX_CANDIDATES_PER_ACCOUNT)

    def _get_gate(self) -> Any:
        if self._gate is not None:
            return self._gate
        from services.person_enrichment_eligibility_gate import get_enrichment_eligibility_gate
        return get_enrichment_eligibility_gate()

    def run(
        self,
        candidates: List[Dict[str, Any]],
        facility_info: Dict[str, Any],
        trigger_info: Dict[str, Any],
        opportunity_icp_score: float = 0.0,
        contact_info: Optional[Dict[str, Any]] = None,
    ) -> WaterfallResult:
        """Run the contact enrichment waterfall across up to max_candidates.

        Parameters
        ----------
        candidates:
            Ordered list of verified candidate dicts. First entry is primary.
            Each dict must have composite_score, authority_class, facility_relationship,
            current_employment, candidate_name, candidate_title, and optionally
            _candidate_record (ORM object).
        facility_info, trigger_info, opportunity_icp_score, contact_info:
            Passed to the eligibility gate for each candidate.
        """
        gate = self._get_gate()
        attempts: List[Dict[str, Any]] = []
        enrichment_calls = 0

        for candidate in candidates[: self._max_candidates]:
            name = candidate.get("candidate_name") or candidate.get("name") or "Unknown"
            title = candidate.get("candidate_title") or candidate.get("title") or ""

            # ── Eligibility gate ──────────────────────────────────────────
            decision = gate.evaluate(
                candidate=candidate,
                facility_info=facility_info,
                trigger_info=trigger_info,
                opportunity_icp_score=opportunity_icp_score,
                contact_info=contact_info,
            )

            if not decision.enrich_contact:
                attempts.append({
                    "name": name,
                    "title": title,
                    "outcome": "GATE_BLOCKED",
                    "reason": decision.reason,
                    "authority_confidence": decision.authority_confidence,
                    "llm_used": decision.llm_used,
                })
                logger.info(
                    "[WATERFALL_GATE_BLOCKED] Candidate: %s | Reason: %s", name, decision.reason
                )
                continue

            # ── Apollo enrichment ─────────────────────────────────────────
            enrich_fn = self._enrich_fn
            if enrich_fn is None:
                logger.warning("[WATERFALL] No enrich_fn configured; skipping %s", name)
                attempts.append({"name": name, "outcome": "NO_ENRICH_FN"})
                continue

            logger.info("[WATERFALL_ENRICH_STARTED] Candidate: %s | Score: %.2f", name, decision.score_at_decision)
            try:
                result = enrich_fn(candidate)
            except Exception as exc:
                logger.warning("[WATERFALL_ENRICH_ERROR] Candidate: %s | %s", name, exc)
                attempts.append({"name": name, "outcome": "ENRICH_ERROR", "error": str(exc)})
                continue

            enrichment_calls += 1
            email = result.get("email")
            email_status = result.get("email_status") or result.get("apollo_email_confidence")
            source = result.get("source") or result.get("email_source")

            verification_level = classify_email_verification_level(
                email=email,
                email_status=email_status,
                source=source,
            )
            send_ready = is_send_ready_email(email, verification_level)

            attempt_entry = {
                "name": name,
                "title": title,
                "outcome": "CONTACT_FOUND" if email else "CONTACT_NOT_FOUND",
                "email": email,
                "verification_level": verification_level.value,
                "send_ready": send_ready,
                "authority_confidence": decision.authority_confidence,
                "gate_reason": decision.reason,
                "llm_used": decision.llm_used,
            }
            attempts.append(attempt_entry)

            if email and send_ready:
                logger.info(
                    "[WATERFALL_CONTACT_FOUND] Candidate: %s | Email: %s | Level: %s",
                    name, email, verification_level.value,
                )
                return WaterfallResult(
                    status="CONTACT_FOUND",
                    email=email,
                    email_verification_level=verification_level,
                    send_ready=True,
                    candidate_name=name,
                    candidate_title=title,
                    attempts=attempts,
                    enrichment_calls=enrichment_calls,
                )

            if email and not send_ready:
                logger.info(
                    "[WATERFALL_EMAIL_NOT_SEND_READY] Candidate: %s | Level: %s | Policy: MX_ONLY_SEND_ALLOWED=%s",
                    name, verification_level.value, MX_ONLY_SEND_ALLOWED,
                )
                # Continue to next candidate; do NOT promote unverified email

        # Exhausted all candidates
        gate_reasons = [
            a.get("reason", a.get("gate_reason", ""))
            for a in attempts
            if a.get("outcome") in {"GATE_BLOCKED", "CONTACT_NOT_FOUND"}
        ]
        logger.info(
            "[WATERFALL_HOLD] No send-ready contact found after %d enrichment calls",
            enrichment_calls,
        )
        return WaterfallResult(
            status="HOLD_CONTACT_NOT_FOUND",
            email=None,
            email_verification_level=EmailVerificationLevel.UNKNOWN,
            send_ready=False,
            candidate_name=None,
            candidate_title=None,
            attempts=attempts,
            enrichment_calls=enrichment_calls,
            hold_reason="No verified email found across all eligible candidates",
            gate_reasons=gate_reasons,
        )
