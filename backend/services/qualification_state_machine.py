"""Qualification State Machine & Integrity Service for Salesoorja.

Enforces strict semantic separation across the 17 lifecycle states:
- DISCOVERED: Raw company/domain identified
- RESEARCHING: Active background intelligence gathering
- OPPORTUNITY_VERIFIED: Confirmed capex/expansion/compliance trigger + exact facility + CC-3963 scope match
- PERSON_CANDIDATE_FOUND: Potential human decision-maker discovered in web evidence
- PERSON_VERIFIED: Real human, current company confirmed, plant/group functional authority verified
- CONTACT_MISSING: Verified person, but 0 contact channels found
- APOLLO_ELIGIBLE: Qualified opportunity + verified person, free research exhausted, needs Apollo credit lookup
- CONTACT_FOUND_UNVERIFIED: Pattern-inferred email or unverified contact (mailbox_verified=False)
- CONTACT_VERIFIED: Mailbox ping verified, deliverable email or verified direct mobile
- READY_FOR_EMAIL: Passed 7 opportunity gates (evaluates overall readiness)
- STAGED_TEST: Staged for consultative copy preview only (OUTBOUND_TEST_MODE=True, no real send)
- READY_FOR_PRODUCTION_SEND: Strictly verified email (mailbox_verified=True), verified person, production approved
- SENT: Dispatched via outbound sender
- REPLIED: Inbound email received
- ENQUIRY: Primary KPI — Commercial or technical calibration enquiry received
- HOLD: Ambiguous company association / multi-site unconfirmed facility / stale trigger
- REJECTED: Disqualified (out-of-scope, non-human name, competitor, former employee)

CRITICAL INVARIANTS:
1. APOLLO_ELIGIBLE does NOT mean READY_FOR_PRODUCTION_SEND.
2. Inferred email with mailbox_verified=False may generate TEST preview (STAGED_TEST) but CANNOT be READY_FOR_PRODUCTION_SEND.
3. HOLD must be enforced for AMBIGUOUS_COMPANY or unconfirmed facility.
4. REJECTED must be enforced for FORMER_COMPANY, OTHER_COMPANY, or non-human names.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class QualificationState(str, Enum):
    DISCOVERED = "DISCOVERED"
    RESEARCHING = "RESEARCHING"
    OPPORTUNITY_VERIFIED = "OPPORTUNITY_VERIFIED"
    PERSON_CANDIDATE_FOUND = "PERSON_CANDIDATE_FOUND"
    PERSON_VERIFIED = "PERSON_VERIFIED"
    CONTACT_MISSING = "CONTACT_MISSING"
    APOLLO_ELIGIBLE = "APOLLO_ELIGIBLE"
    CONTACT_FOUND_UNVERIFIED = "CONTACT_FOUND_UNVERIFIED"
    CONTACT_VERIFIED = "CONTACT_VERIFIED"
    READY_FOR_EMAIL = "READY_FOR_EMAIL"
    STAGED_TEST = "STAGED_TEST"
    READY_FOR_PRODUCTION_SEND = "READY_FOR_PRODUCTION_SEND"
    SENT = "SENT"
    REPLIED = "REPLIED"
    ENQUIRY = "ENQUIRY"
    HOLD = "HOLD"
    REJECTED = "REJECTED"


# Explicit valid transitions between lifecycle states
VALID_TRANSITIONS: Dict[QualificationState, Set[QualificationState]] = {
    QualificationState.DISCOVERED: {
        QualificationState.RESEARCHING,
        QualificationState.HOLD,
        QualificationState.REJECTED,
    },
    QualificationState.RESEARCHING: {
        QualificationState.OPPORTUNITY_VERIFIED,
        QualificationState.PERSON_CANDIDATE_FOUND,
        QualificationState.HOLD,
        QualificationState.REJECTED,
    },
    QualificationState.OPPORTUNITY_VERIFIED: {
        QualificationState.PERSON_CANDIDATE_FOUND,
        QualificationState.PERSON_VERIFIED,
        QualificationState.HOLD,
        QualificationState.REJECTED,
    },
    QualificationState.PERSON_CANDIDATE_FOUND: {
        QualificationState.PERSON_VERIFIED,
        QualificationState.HOLD,
        QualificationState.REJECTED,
    },
    QualificationState.PERSON_VERIFIED: {
        QualificationState.CONTACT_MISSING,
        QualificationState.APOLLO_ELIGIBLE,
        QualificationState.CONTACT_FOUND_UNVERIFIED,
        QualificationState.CONTACT_VERIFIED,
        QualificationState.HOLD,
        QualificationState.REJECTED,
    },
    QualificationState.CONTACT_MISSING: {
        QualificationState.APOLLO_ELIGIBLE,
        QualificationState.HOLD,
        QualificationState.REJECTED,
    },
    QualificationState.APOLLO_ELIGIBLE: {
        # Apollo eligible can transition to contact states upon enrichment, or hold/reject.
        # It CANNOT transition directly to READY_FOR_PRODUCTION_SEND or SENT!
        QualificationState.CONTACT_VERIFIED,
        QualificationState.CONTACT_FOUND_UNVERIFIED,
        QualificationState.HOLD,
        QualificationState.REJECTED,
    },
    QualificationState.CONTACT_FOUND_UNVERIFIED: {
        # An unverified/inferred contact can be staged for testing/preview, but not sent live
        QualificationState.STAGED_TEST,
        QualificationState.CONTACT_VERIFIED,
        QualificationState.HOLD,
        QualificationState.REJECTED,
    },
    QualificationState.CONTACT_VERIFIED: {
        QualificationState.READY_FOR_EMAIL,
        QualificationState.STAGED_TEST,
        QualificationState.READY_FOR_PRODUCTION_SEND,
        QualificationState.HOLD,
        QualificationState.REJECTED,
    },
    QualificationState.READY_FOR_EMAIL: {
        QualificationState.STAGED_TEST,
        QualificationState.READY_FOR_PRODUCTION_SEND,
        QualificationState.HOLD,
        QualificationState.REJECTED,
    },
    QualificationState.STAGED_TEST: {
        # Test preview generated. Can only become production send if contact is verified
        QualificationState.READY_FOR_PRODUCTION_SEND,
        QualificationState.HOLD,
        QualificationState.REJECTED,
    },
    QualificationState.READY_FOR_PRODUCTION_SEND: {
        QualificationState.SENT,
        QualificationState.HOLD,
        QualificationState.REJECTED,
    },
    QualificationState.SENT: {
        QualificationState.REPLIED,
        QualificationState.HOLD,
    },
    QualificationState.REPLIED: {
        QualificationState.ENQUIRY,
        QualificationState.HOLD,
        QualificationState.REJECTED,
    },
    QualificationState.ENQUIRY: set(),  # Terminal success state (Primary KPI)
    QualificationState.HOLD: {
        QualificationState.RESEARCHING,
        QualificationState.OPPORTUNITY_VERIFIED,
        QualificationState.PERSON_VERIFIED,
        QualificationState.REJECTED,
    },
    QualificationState.REJECTED: set(),  # Disqualified
}


@dataclass(frozen=True)
class StateValidationResult:
    valid: bool
    state: QualificationState
    reason: str
    can_stage_test: bool
    can_send_production: bool
    requires_apollo: bool
    is_hold: bool
    is_rejected: bool


def determine_qualification_state(
    evidence: Dict[str, Any],
    *,
    outbound_test_mode: bool = True,
    production_mode: bool = False,
) -> StateValidationResult:
    """Determine the precise QualificationState from an evidence dictionary.
    
    Evaluates trigger, facility, person, contact verification, and mailbox status.
    """
    evidence = evidence or {}

    # 1. Check for Rejection conditions
    # Non-human name
    person_info = evidence.get("correct_person") or {}
    cand_name = str(person_info.get("name") or person_info.get("candidate_name") or "").strip()
    if cand_name:
        from services.contact_confidence import validate_person_name
        name_check = validate_person_name(cand_name)
        if name_check["person_name_validation"] in {"INVALID_ROLE_TEXT", "INVALID_FORMAT", "CORPORATE_ENTITY"}:
            return StateValidationResult(
                valid=True,
                state=QualificationState.REJECTED,
                reason=f"Candidate '{cand_name}' rejected: {name_check['reason']}",
                can_stage_test=False,
                can_send_production=False,
                requires_apollo=False,
                is_hold=False,
                is_rejected=True,
            )

    # Company evidence status check (quarantine former/other/ambiguous)
    comp_ev_status = str(person_info.get("company_evidence_status") or "").upper()
    if comp_ev_status in {"OTHER_COMPANY", "FORMER_COMPANY"}:
        return StateValidationResult(
            valid=True,
            state=QualificationState.REJECTED,
            reason=f"Candidate '{cand_name}' is associated with {comp_ev_status} (not current employee of target company)",
            can_stage_test=False,
            can_send_production=False,
            requires_apollo=False,
            is_hold=False,
            is_rejected=True,
        )

    # Out of scope technical capability
    cap_info = evidence.get("technical_capability") or {}
    if cap_info.get("status") == "OUT_OF_SCOPE":
        return StateValidationResult(
            valid=True,
            state=QualificationState.REJECTED,
            reason="Requested calibration services are completely out-of-scope under Oorja CC-3963",
            can_stage_test=False,
            can_send_production=False,
            requires_apollo=False,
            is_hold=False,
            is_rejected=True,
        )

    # 2. Check for HOLD conditions
    # Ambiguous company link
    if comp_ev_status == "AMBIGUOUS_COMPANY":
        return StateValidationResult(
            valid=True,
            state=QualificationState.HOLD,
            reason=f"Candidate company association is AMBIGUOUS_COMPANY; requires independent corroboration before outreach",
            can_stage_test=False,
            can_send_production=False,
            requires_apollo=False,
            is_hold=True,
            is_rejected=False,
        )

    # Facility linkage unproven for multi-site corporate entity
    fac_info = evidence.get("exact_facility") or {}
    fac_link = str(fac_info.get("linkage_strength") or "").upper()
    if fac_link == "WEAK":
        return StateValidationResult(
            valid=True,
            state=QualificationState.HOLD,
            reason="Trigger-to-facility linkage is WEAK; corporate announcement not proven to affect specific facility",
            can_stage_test=False,
            can_send_production=False,
            requires_apollo=False,
            is_hold=True,
            is_rejected=False,
        )

    # Stale or Recent trigger recency check
    trig_info = evidence.get("trigger_current") or {}
    recency_status = str(trig_info.get("recency_status") or "").upper()
    ongoing_ev = str(trig_info.get("ongoing_activity_evidence") or trig_info.get("ongoing_source") or "").strip()
    from services.opportunity_gates import is_valid_ongoing_evidence
    has_valid_ongoing, _ = is_valid_ongoing_evidence(ongoing_ev)

    if recency_status == "STALE" and not has_valid_ongoing:
        return StateValidationResult(
            valid=True,
            state=QualificationState.HOLD,
            reason="Trigger is STALE (>365 days old) with no ongoing execution proof",
            can_stage_test=False,
            can_send_production=False,
            requires_apollo=False,
            is_hold=True,
            is_rejected=False,
        )
    elif recency_status == "RECENT" and not has_valid_ongoing:
        return StateValidationResult(
            valid=True,
            state=QualificationState.HOLD,
            reason="Trigger is RECENT (181-365 days old) but lacks required independent ongoing activity evidence",
            can_stage_test=False,
            can_send_production=False,
            requires_apollo=False,
            is_hold=True,
            is_rejected=False,
        )

    # 3. Check Opportunity & Person Verification
    trig_verified = bool(trig_info.get("verified"))
    fac_verified = bool(fac_info.get("verified") or fac_info.get("address"))
    opp_verified = trig_verified and fac_verified

    emp_verified = bool(person_info.get("employment_verified") or person_info.get("current_company_verified"))
    duties_verified = bool(person_info.get("duties_verified") or (person_info.get("functional_ownership_score") or 0) >= 50)
    person_verified = emp_verified and duties_verified and bool(cand_name)

    # 4. Check Contact Verification
    contact_info = evidence.get("reachable_email") or {}
    email_addr = str(contact_info.get("email") or contact_info.get("address") or "").strip()
    email_status = str(contact_info.get("status") or contact_info.get("verification_status") or "").upper()
    mailbox_verified = bool(contact_info.get("mailbox_verified"))
    contact_confidence = str(contact_info.get("contact_confidence") or "").upper()

    has_contact = bool(email_addr)
    is_contact_verified = has_contact and mailbox_verified and email_status in {"VERIFIED", "EMAIL_VERIFIED"} and contact_confidence in {"VERIFIED", "HIGH", "DIRECT"}

    # Evaluate States
    if not opp_verified:
        return StateValidationResult(
            valid=True,
            state=QualificationState.RESEARCHING if trig_verified or fac_verified else QualificationState.DISCOVERED,
            reason="Opportunity verification incomplete (requires verified trigger and exact facility)",
            can_stage_test=False,
            can_send_production=False,
            requires_apollo=False,
            is_hold=False,
            is_rejected=False,
        )

    if not person_verified:
        return StateValidationResult(
            valid=True,
            state=QualificationState.PERSON_CANDIDATE_FOUND if cand_name else QualificationState.OPPORTUNITY_VERIFIED,
            reason="Opportunity verified; decision-maker candidate verification pending",
            can_stage_test=False,
            can_send_production=False,
            requires_apollo=False,
            is_hold=False,
            is_rejected=False,
        )

    # Here, Opportunity IS verified AND Person IS verified
    if not has_contact:
        return StateValidationResult(
            valid=True,
            state=QualificationState.CONTACT_MISSING,
            reason=f"Opportunity and Person '{cand_name}' verified, but 0 contact channels discovered",
            can_stage_test=False,
            can_send_production=False,
            requires_apollo=True,
            is_hold=False,
            is_rejected=False,
        )

    if not is_contact_verified:
        # Inferred / pattern email exists (mailbox_verified=False)
        # CRITICAL RULE: Can stage test preview (STAGED_TEST), but CANNOT be READY_FOR_PRODUCTION_SEND!
        return StateValidationResult(
            valid=True,
            state=QualificationState.CONTACT_FOUND_UNVERIFIED,
            reason=f"Pattern-inferred email ({email_addr}) present with mailbox_verified=False. Eligible for TEST preview staging only.",
            can_stage_test=True,
            can_send_production=False,
            requires_apollo=True,  # Apollo lookup justified to obtain verified mailbox
            is_hold=False,
            is_rejected=False,
        )

    # Verified mailbox exists
    if production_mode and not outbound_test_mode:
        return StateValidationResult(
            valid=True,
            state=QualificationState.READY_FOR_PRODUCTION_SEND,
            reason=f"All gates passed: Opportunity verified, Person '{cand_name}' verified, Mailbox verified ({email_addr}). Ready for production send.",
            can_stage_test=True,
            can_send_production=True,
            requires_apollo=False,
            is_hold=False,
            is_rejected=False,
        )
    else:
        return StateValidationResult(
            valid=True,
            state=QualificationState.STAGED_TEST,
            reason=f"All criteria satisfied under test mode (OUTBOUND_TEST_MODE=True). Staged for consultative copy preview only.",
            can_stage_test=True,
            can_send_production=False,  # Enforced 0 production send under test mode
            requires_apollo=False,
            is_hold=False,
            is_rejected=False,
        )


def validate_transition(
    current_state: QualificationState,
    target_state: QualificationState,
    context: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, str]:
    """Validate whether transitioning from current_state to target_state is permitted."""
    allowed = VALID_TRANSITIONS.get(current_state, set())
    if target_state not in allowed:
        return False, f"Illegal state transition from {current_state.value} to {target_state.value}"

    context = context or {}

    # Strict Invariant 1: APOLLO_ELIGIBLE cannot become READY_FOR_PRODUCTION_SEND
    if current_state == QualificationState.APOLLO_ELIGIBLE and target_state == QualificationState.READY_FOR_PRODUCTION_SEND:
        return False, "APOLLO_ELIGIBLE lead cannot transition directly to READY_FOR_PRODUCTION_SEND without contact verification"

    # Strict Invariant 2: Inferred email cannot become READY_FOR_PRODUCTION_SEND
    if target_state == QualificationState.READY_FOR_PRODUCTION_SEND:
        if not context.get("mailbox_verified"):
            return False, "Cannot transition to READY_FOR_PRODUCTION_SEND: mailbox_verified is False (inferred email must be verified first)"
        if context.get("outbound_test_mode", True):
            return False, "Cannot transition to READY_FOR_PRODUCTION_SEND: OUTBOUND_TEST_MODE is True"

    return True, f"Transition from {current_state.value} to {target_state.value} is valid"


@dataclass(frozen=True)
class PersonChangeInvalidation:
    """Result of evaluating person-change impact on staged/active records."""
    old_person: str
    new_person: str
    company: str
    must_invalidate_contact: bool
    must_invalidate_score: bool
    must_invalidate_staging: bool
    must_invalidate_outreach: bool
    old_state: Optional[QualificationState]
    new_state: QualificationState
    reason: str


def invalidate_for_person_change(
    company: str,
    old_person: str,
    new_person: str,
    old_evidence: Optional[Dict[str, Any]] = None,
    reason: str = "Forensic audit selected different candidate",
) -> PersonChangeInvalidation:
    """Determine what must be invalidated when a candidate is replaced.

    INVARIANTS:
    1. Old person's contact (email, phone) MUST NOT carry over to new person.
    2. Old person's functional ownership score MUST NOT carry over.
    3. Old person's send readiness / staging status MUST be revoked.
    4. Old person's personalized outreach copy MUST be invalidated.
    5. New person MUST independently pass all gates from scratch.

    This function does NOT perform the invalidation — it returns a decision
    object that callers use to coordinate state, staging, and evidence cleanup.
    """
    if not old_person or not new_person:
        return PersonChangeInvalidation(
            old_person=old_person or "",
            new_person=new_person or "",
            company=company,
            must_invalidate_contact=False,
            must_invalidate_score=False,
            must_invalidate_staging=False,
            must_invalidate_outreach=False,
            old_state=None,
            new_state=QualificationState.RESEARCHING,
            reason="Missing person name; no invalidation required",
        )

    # Old person's state from evidence (if available)
    old_state = None
    if old_evidence:
        try:
            result = determine_qualification_state(old_evidence)
            old_state = result.state
        except Exception:
            pass

    # A person change ALWAYS invalidates person-specific fields
    return PersonChangeInvalidation(
        old_person=old_person,
        new_person=new_person,
        company=company,
        must_invalidate_contact=True,    # Different person = different email/phone
        must_invalidate_score=True,      # Different person = different functional ownership
        must_invalidate_staging=True,    # Old staging entry cannot be sent
        must_invalidate_outreach=True,   # Old personalized copy is wrong
        old_state=old_state,
        new_state=QualificationState.REJECTED,  # Old candidate gets REJECTED (superseded)
        reason=reason,
    )
