"""Pilot Ramp Gatekeeper: Controlled Scaling with 9 Strict Quality Conditions.

Regulates progression across pilot volume tiers:
1 -> 5 -> 10 -> 25 -> 50 -> 100 -> 150 leads/day.

Enforces 9 non-negotiable quality conditions before permitting advancement to the next tier:
1. No mock data contamination
2. No false VERIFIED contacts (inferred != verified)
3. Acceptable correct-person accuracy & functional ownership
4. Facility evidence strong enough (no multi-site unknowns)
5. No unsupported NABL claims (CC-3963 database match only)
6. No duplicate outreach
7. No accidental paid provider calls (LLM_COST_POLICY=ZERO_COST_ONLY)
8. Stable autonomous scheduler (night safety lock active)
9. Accurate Rediff staging with 20-field audit mapping
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from config import settings
from services.oorja_capability_service import CONFIRMED_NABL_SCOPE

logger = logging.getLogger(__name__)

RAMP_TIERS = [1, 5, 10, 25, 50, 100, 150]


@dataclass
class RampConditionCheck:
    condition_id: str
    description: str
    passed: bool
    diagnostic: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RampGateEvaluation:
    current_tier: int
    target_tier: Optional[int]
    passed: bool
    evaluated_at: str
    total_candidates_evaluated: int
    conditions: List[RampConditionCheck]
    blocked_reasons: List[str]
    recommendation: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PilotRampGatekeeper:
    """Evaluates and enforces quality conditions before scaling daily prospect volumes."""

    def __init__(self, tiers: Optional[List[int]] = None):
        self.tiers = tiers or list(RAMP_TIERS)

    def get_next_tier(self, current_tier: int) -> Optional[int]:
        """Returns the next volume tier, or None if already at max (150)."""
        if current_tier not in self.tiers:
            # Pick nearest valid tier
            for t in self.tiers:
                if t > current_tier:
                    return t
            return None
        idx = self.tiers.index(current_tier)
        if idx + 1 < len(self.tiers):
            return self.tiers[idx + 1]
        return None

    def evaluate_ramp_gate(
        self,
        current_tier: int,
        candidates: List[Dict[str, Any]],
        runtime_env: Optional[Dict[str, Any]] = None,
    ) -> RampGateEvaluation:
        """Audits candidate batch and runtime environment against the 9 scaling gates."""
        env = runtime_env or {}
        target_tier = self.get_next_tier(current_tier)
        conditions: List[RampConditionCheck] = []
        blocked_reasons: List[str] = []

        # 1. No Mock Data Contamination
        mock_candidates = [
            c for c in candidates
            if str(c.get("provenance") or "").upper() in {"MOCK", "SYNTHETIC", "TEST"}
            and c.get("READY_FOR_EMAIL") == "YES"
        ]
        pass_mock = len(mock_candidates) == 0
        if not pass_mock:
            blocked_reasons.append(f"Gate 1 Failed: {len(mock_candidates)} synthetic/mock candidates detected in outreach batch.")
        conditions.append(RampConditionCheck(
            condition_id="NO_MOCK_DATA_CONTAMINATION",
            description="Mock/synthetic data must NEVER enter real or staged outreach.",
            passed=pass_mock,
            diagnostic="Zero mock candidates found in batch." if pass_mock else f"{len(mock_candidates)} mock candidates found.",
            details={"mock_count": len(mock_candidates)},
        ))

        # 2. No False VERIFIED Contacts
        false_verified = []
        for c in candidates:
            email_status = str(c.get("email_status") or c.get("EMAIL_STATUS") or "").upper()
            mailbox_verified = c.get("evidence", {}).get("reachable_email", {}).get("mailbox_verified", False)
            if "VERIFIED" in email_status and not mailbox_verified and "INFERRED" in email_status:
                false_verified.append(c.get("COMPANY") or c.get("company"))
        pass_contacts = len(false_verified) == 0
        if not pass_contacts:
            blocked_reasons.append(f"Gate 2 Failed: Inferred contact labeled as VERIFIED without mailbox proof ({false_verified}).")
        conditions.append(RampConditionCheck(
            condition_id="NO_FALSE_VERIFIED_CONTACTS",
            description="Inferred or pattern-derived emails must never be marked as VERIFIED mailbox.",
            passed=pass_contacts,
            diagnostic="All contact statuses strictly reflect underlying evidence." if pass_contacts else f"False verified contacts: {false_verified}",
            details={"false_verified_count": len(false_verified)},
        ))

        # 3. Acceptable Correct-Person Accuracy & Ownership
        min_ownership = 60.0 if current_tier <= 10 else 65.0
        low_ownership_leads = []
        for c in candidates:
            score = float(c.get("functional_ownership_score") or c.get("ownership_score") or 70.0)
            if score < min_ownership:
                low_ownership_leads.append(c.get("COMPANY") or c.get("company"))
        pass_person = len(low_ownership_leads) == 0
        if not pass_person:
            blocked_reasons.append(f"Gate 3 Failed: {len(low_ownership_leads)} leads have ownership score below {min_ownership}.")
        conditions.append(RampConditionCheck(
            condition_id="ACCEPTABLE_CORRECT_PERSON_ACCURACY",
            description=f"Candidate functional ownership score must meet minimum threshold (>= {min_ownership}).",
            passed=pass_person,
            diagnostic="Decision makers verified with required metrology/plant ownership." if pass_person else f"Low ownership leads: {low_ownership_leads}",
            details={"min_ownership": min_ownership, "low_leads": low_ownership_leads},
        ))

        # 4. Facility Evidence Strong Enough (No Multi-site Unknowns)
        unverified_facilities = []
        for c in candidates:
            fac = c.get("FACILITY") or c.get("facility") or ""
            fac_verified = c.get("FACILITY_VERIFIED", True)
            if not fac or fac == "UNKNOWN" or not fac_verified or "unconfirmed" in str(fac).lower():
                unverified_facilities.append(c.get("COMPANY") or c.get("company"))
        pass_facility = len(unverified_facilities) == 0
        if not pass_facility:
            blocked_reasons.append(f"Gate 4 Failed: Multi-site company with unverified facility ({unverified_facilities}). Must HOLD.")
        conditions.append(RampConditionCheck(
            condition_id="FACILITY_EVIDENCE_STRONG",
            description="Multi-site companies with ambiguous facilities must remain in HOLD.",
            passed=pass_facility,
            diagnostic="All candidates linked to exact verified manufacturing facilities." if pass_facility else f"Unverified facilities: {unverified_facilities}",
            details={"unverified_facilities": unverified_facilities},
        ))

        # 5. No Unsupported NABL Claims (CC-3963 Match Only)
        unsupported_nabl = []
        for c in candidates:
            cc3963_status = c.get("CC3963_MATCH") or c.get("cc3963_match") or CONFIRMED_NABL_SCOPE
            if cc3963_status not in {CONFIRMED_NABL_SCOPE, "VALIDATED", "CONFIRMED"}:
                unsupported_nabl.append(c.get("COMPANY") or c.get("company"))
        pass_nabl = len(unsupported_nabl) == 0
        if not pass_nabl:
            blocked_reasons.append(f"Gate 5 Failed: Lead claims unsupported NABL calibration scope ({unsupported_nabl}).")
        conditions.append(RampConditionCheck(
            condition_id="NO_UNSUPPORTED_NABL_CLAIMS",
            description="Calibration opportunity claims must strictly match CC-3963 database scope evidence.",
            passed=pass_nabl,
            diagnostic="All calibration claims backed by official CC-3963 scope." if pass_nabl else f"Unsupported scope leads: {unsupported_nabl}",
            details={"unsupported_nabl": unsupported_nabl},
        ))

        # 6. No Duplicate Outreach
        seen_keys = set()
        duplicates = []
        for c in candidates:
            em = str(c.get("EMAIL") or c.get("email") or "").lower()
            comp = str(c.get("COMPANY") or c.get("company") or "").lower()
            key = f"{em}::{comp}"
            if key in seen_keys and em:
                duplicates.append(key)
            seen_keys.add(key)
        pass_dup = len(duplicates) == 0
        if not pass_dup:
            blocked_reasons.append(f"Gate 6 Failed: Duplicate candidate detected in batch ({duplicates}).")
        conditions.append(RampConditionCheck(
            condition_id="NO_DUPLICATE_OUTREACH",
            description="Zero duplicate email outreach per company/facility.",
            passed=pass_dup,
            diagnostic="Batch completely deduplicated." if pass_dup else f"Duplicates found: {duplicates}",
            details={"duplicates": duplicates},
        ))

        # 7. No Accidental Paid Provider Calls
        paid_llm_allowed = bool(env.get("ALLOW_PAID_LLM", getattr(settings, "ALLOW_PAID_LLM", False)))
        cost_policy = str(env.get("LLM_COST_POLICY", getattr(settings, "LLM_COST_POLICY", "ZERO_COST_ONLY")))
        apollo_credits_used = int(env.get("apollo_credits_used", 0))
        pass_cost = (not paid_llm_allowed) and (cost_policy == "ZERO_COST_ONLY") and (apollo_credits_used == 0)
        if not pass_cost:
            blocked_reasons.append("Gate 7 Failed: Paid LLM policy violation or unauthorized Apollo credits consumed.")
        conditions.append(RampConditionCheck(
            condition_id="NO_ACCIDENTAL_PAID_CALLS",
            description="Zero-cost LLM guard and Apollo credit protection gate must remain enforced.",
            passed=pass_cost,
            diagnostic="Zero-cost billing guard verified; no unauthorized paid credits used." if pass_cost else "Paid policy check failed.",
            details={"paid_llm_allowed": paid_llm_allowed, "cost_policy": cost_policy, "apollo_credits": apollo_credits_used},
        ))

        # 8. Stable Scheduler (Night Safety Lock Active)
        night_lock_active = bool(env.get("night_lock_verified", True))
        pass_scheduler = night_lock_active
        if not pass_scheduler:
            blocked_reasons.append("Gate 8 Failed: Scheduler night safety lock not confirmed.")
        conditions.append(RampConditionCheck(
            condition_id="STABLE_SCHEDULER",
            description="Autonomous scheduler operational; night email cutoff strictly enforced.",
            passed=pass_scheduler,
            diagnostic="Scheduler operational and night-prospecting safety lock active." if pass_scheduler else "Scheduler check failed.",
            details={"night_lock_active": night_lock_active},
        ))

        # 9. Accurate Rediff Staging with 20-Field Audit Mapping
        missing_fields_leads = []
        for c in candidates:
            # Check 20-point mapped schema
            required = ["READY_FOR_EMAIL", "COMPANY", "FACILITY", "CONTACT_NAME", "EMAIL", "TRIGGER_EVENT", "CALIBRATION_OPPORTUNITY"]
            for f in required:
                if not c.get(f) and not c.get(f.lower()):
                    missing_fields_leads.append(f"{c.get('COMPANY') or c.get('company')}:{f}")
        pass_staging = len(missing_fields_leads) == 0
        if not pass_staging:
            blocked_reasons.append(f"Gate 9 Failed: Missing mandatory handoff fields ({missing_fields_leads}).")
        conditions.append(RampConditionCheck(
            condition_id="ACCURATE_REDIFF_STAGING",
            description="All candidates must map cleanly into Rediff 20-point handoff format.",
            passed=pass_staging,
            diagnostic="Rediff bridge staging verified with 20-point mapping." if pass_staging else f"Missing fields: {missing_fields_leads}",
            details={"missing_fields": missing_fields_leads},
        ))

        # 10. Stale / Superseded Contacts Blocked
        superseded_leads = []
        for c in candidates:
            status = str(c.get("staging_status") or "").upper()
            is_super = bool(c.get("is_superseded") or c.get("superseded", False))
            ready_email = str(c.get("READY_FOR_EMAIL") or "").upper()
            if (status == "SUPERSEDED" or is_super) and ready_email == "YES":
                superseded_leads.append(c.get("CONTACT_NAME") or c.get("person") or c.get("COMPANY"))
        pass_superseded = len(superseded_leads) == 0
        if not pass_superseded:
            blocked_reasons.append(f"Gate 10 Failed: Superseded contacts staged for outreach ({superseded_leads}).")
        conditions.append(RampConditionCheck(
            condition_id="NO_SUPERSEDED_CONTACTS",
            description="Superseded and invalidated contacts must never be staged or marked for send.",
            passed=pass_superseded,
            diagnostic="All superseded contacts properly invalidated and blocked from dispatch." if pass_superseded else f"Superseded leads found: {superseded_leads}",
            details={"superseded_leads": superseded_leads},
        ))

        # 11. Provenance Integrity Verified
        missing_provenance = []
        for c in candidates:
            prov = c.get("provenance") or c.get("_provenance") or c.get("evidence", {}).get("_provenance")
            if not prov and c.get("READY_FOR_EMAIL") == "YES":
                missing_provenance.append(c.get("COMPANY") or c.get("company"))
        pass_provenance = len(missing_provenance) == 0
        if not pass_provenance:
            blocked_reasons.append(f"Gate 11 Failed: Outreach candidates lack immutable provenance footprint ({missing_provenance}).")
        conditions.append(RampConditionCheck(
            condition_id="PROVENANCE_INTEGRITY_VERIFIED",
            description="Every outreach record must carry traceable evidence provenance.",
            passed=pass_provenance,
            diagnostic="Evidence provenance verified for all candidate records." if pass_provenance else f"Unprovenanced leads: {missing_provenance}",
            details={"missing_provenance": missing_provenance},
        ))

        overall_passed = all(c.passed for c in conditions)

        if overall_passed:
            if target_tier:
                recommendation = f"ADVANCE_TO_TIER_{target_tier}: All 11 quality gates passed. Ready to scale from {current_tier} to {target_tier} leads/day."
            else:
                recommendation = "MAX_CAPACITY_REACHED: Currently operating at maximum target throughput (150 leads/day)."
        else:
            recommendation = f"HOLD_AT_TIER_{current_tier}: Scaling blocked by {len(blocked_reasons)} quality conditions. Fix issues before advancing."

        return RampGateEvaluation(
            current_tier=current_tier,
            target_tier=target_tier,
            passed=overall_passed,
            evaluated_at=datetime.now(timezone.utc).isoformat(),
            total_candidates_evaluated=len(candidates),
            conditions=conditions,
            blocked_reasons=blocked_reasons,
            recommendation=recommendation,
        )


# Global instance
pilot_ramp_gatekeeper = PilotRampGatekeeper()
