"""Person Enrichment Eligibility Gate — Phase 2 Funnel Recovery.

Replaces the hardcoded 0.85 composite-score threshold with a structured
deterministic pre-check + LLM review so that high-authority candidates
with verified current employment and direct facility ownership are not
incorrectly blocked solely due to a borderline composite score (e.g. 84.0).

Design contract:
- Deterministic safety checks come FIRST — mandatory hard blocks.
- LLM (DeepSeek primary / Gemini fallback) is a secondary authority check.
- The numeric score remains an input feature; it is NOT the sole gate.
- Returns EnrichmentEligibilityDecision with enrich_contact + full audit trail.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Authority classes that may receive Apollo credits ──────────────────────
APOLLO_AUTHORITY_CLASSES = {
    "DIRECT_CALIBRATION_OWNER",
    "METROLOGY_OWNER",
    "STRONG_PLANT_QUALITY_OWNER",
    "FACILITY_OWNER",
    "GROUP_FUNCTION_OWNER",
}

# Facility relationships that establish a person is at the right location
VALID_FACILITY_RELATIONSHIPS = {
    "DIRECT",
    "STRONG",
    "FACILITY_OWNER",
    "FACILITY_FUNCTION_OWNER",
    "GROUP_FUNCTION_OWNER",
}

# Absolute minimum score below which no LLM can override (prevents wasteful API calls)
HARD_FLOOR_SCORE = 0.60  # 60 / 100 normalised

# Threshold above which purely deterministic pass is acceptable
DETERMINISTIC_PASS_THRESHOLD = 0.85  # 85 / 100 normalised

# LLM borderline zone: [HARD_FLOOR, DETERMINISTIC_PASS_THRESHOLD)
LLM_BORDERLINE_LOW = HARD_FLOOR_SCORE
LLM_BORDERLINE_HIGH = DETERMINISTIC_PASS_THRESHOLD


@dataclass
class EnrichmentEligibilityDecision:
    enrich_contact: bool
    authority_confidence: str           # HIGH | MEDIUM | LOW | BLOCKED
    reason: str
    commercial_relevance: str           # DIRECT | STRONG | WEAK | NONE
    risk_flags: List[str] = field(default_factory=list)
    evidence_used: List[str] = field(default_factory=list)
    llm_used: bool = False
    llm_provider: str = ""
    score_at_decision: float = 0.0


class PersonEnrichmentEligibilityGate:
    """Structured eligibility gate for Apollo contact enrichment.

    Steps:
    1. Deterministic hard blocks (unverified employment, wrong facility, etc.)
    2. If score >= DETERMINISTIC_PASS_THRESHOLD AND authority is strong → pass.
    3. If score in borderline zone [60, 85) → call LLM for authority review.
    4. Score below 60 → hard block, no LLM call.
    """

    def __init__(
        self,
        llm_provider: Any = None,  # injected for testability; lazy-loaded if None
    ) -> None:
        self._llm_provider = llm_provider

    # ── Public API ─────────────────────────────────────────────────────────

    def evaluate(
        self,
        candidate: Dict[str, Any],
        facility_info: Dict[str, Any],
        trigger_info: Dict[str, Any],
        opportunity_icp_score: float = 0.0,
        contact_info: Optional[Dict[str, Any]] = None,
    ) -> EnrichmentEligibilityDecision:
        """Evaluate whether a candidate warrants Apollo contact enrichment.

        Parameters
        ----------
        candidate:
            Raw candidate dict with keys: composite_score, authority_class,
            current_employment, facility_relationship, candidate_name,
            candidate_title.
        facility_info:
            Dict with facility_verified (bool) and linkage_confidence (str).
        trigger_info:
            Dict with valid_trigger (bool).
        opportunity_icp_score:
            Numeric ICP score (0–100).
        contact_info:
            Optional dict; if email already verified, skip enrichment.
        """
        risk_flags: List[str] = []
        evidence_used: List[str] = []

        # ── Step 0: Contact already verified ──────────────────────────────
        if contact_info:
            if contact_info.get("mailbox_verified") is True:
                return EnrichmentEligibilityDecision(
                    enrich_contact=False,
                    authority_confidence="HIGH",
                    reason="Contact already mailbox-verified; Apollo enrichment unnecessary",
                    commercial_relevance="DIRECT",
                    risk_flags=[],
                    evidence_used=["contact_info.mailbox_verified"],
                )
            if contact_info.get("evidence_level") == "VERIFIED_PERSON_SPECIFIC":
                return EnrichmentEligibilityDecision(
                    enrich_contact=False,
                    authority_confidence="HIGH",
                    reason="Authoritative person-specific email already exists",
                    commercial_relevance="DIRECT",
                    risk_flags=[],
                    evidence_used=["contact_info.evidence_level"],
                )

        # ── Step 1: Trigger validity ────────────────────────────────────
        trigger_valid = trigger_info.get("valid_trigger") if "valid_trigger" in trigger_info else bool(
            trigger_info.get("trigger") or trigger_info.get("title")
        )
        if not trigger_valid:
            return EnrichmentEligibilityDecision(
                enrich_contact=False,
                authority_confidence="BLOCKED",
                reason="Trigger is invalid or unverified",
                commercial_relevance="NONE",
                risk_flags=["invalid_trigger"],
            )
        evidence_used.append("trigger_info.valid_trigger")

        # ── Step 2: Facility linkage ────────────────────────────────────
        fac_linkage = str(
            facility_info.get("linkage_confidence")
            or facility_info.get("trigger_facility_confidence")
            or ""
        ).upper()
        fac_verified = bool(facility_info.get("facility_verified") or facility_info.get("verified"))
        if not fac_verified or fac_linkage not in {"DIRECT", "STRONG"}:
            return EnrichmentEligibilityDecision(
                enrich_contact=False,
                authority_confidence="BLOCKED",
                reason=f"Facility linkage is {fac_linkage or 'UNVERIFIED'}; DIRECT or STRONG required",
                commercial_relevance="NONE",
                risk_flags=["facility_linkage_insufficient"],
            )
        evidence_used.append(f"facility.linkage={fac_linkage}")

        # ── Step 3: ICP score ──────────────────────────────────────────
        if float(opportunity_icp_score or 0) < 85.0:
            return EnrichmentEligibilityDecision(
                enrich_contact=False,
                authority_confidence="BLOCKED",
                reason=f"ICP score {float(opportunity_icp_score or 0):.1f} below minimum 85.0",
                commercial_relevance="NONE",
                risk_flags=["low_icp_score"],
            )
        evidence_used.append(f"icp_score={float(opportunity_icp_score or 0):.1f}")

        # ── Step 4: Normalise numeric score ───────────────────────────────
        raw_score = float(
            candidate.get("composite_score")
            or candidate.get("score")
            or candidate.get("functional_ownership_score")
            or 0.0
        )
        norm_score = raw_score / 100.0 if raw_score > 1.0 else raw_score
        evidence_used.append(f"composite_score={norm_score:.3f}")

        if norm_score < HARD_FLOOR_SCORE:
            return EnrichmentEligibilityDecision(
                enrich_contact=False,
                authority_confidence="BLOCKED",
                reason=(
                    f"Candidate score {norm_score:.2f} is below absolute floor {HARD_FLOOR_SCORE:.2f}; "
                    "no LLM review warranted"
                ),
                commercial_relevance="NONE",
                risk_flags=["score_below_hard_floor"],
                score_at_decision=norm_score,
            )

        # ── Step 5: Current employment ─────────────────────────────────
        employment_verified = bool(
            candidate.get("current_company_verified")
            or candidate.get("employment_verified")
            or candidate.get("current_employment_verified")
            or str(candidate.get("current_employment") or "").upper() == "VERIFIED"
        )
        if not employment_verified:
            return EnrichmentEligibilityDecision(
                enrich_contact=False,
                authority_confidence="BLOCKED",
                reason="Current employment is not verified",
                commercial_relevance="NONE",
                risk_flags=["employment_unverified"],
                score_at_decision=norm_score,
            )
        evidence_used.append("current_employment=VERIFIED")

        # ── Step 6: Facility relationship ─────────────────────────────
        person_facility = str(
            candidate.get("facility_relationship")
            or candidate.get("person_facility_relationship")
            or ""
        ).upper()
        if person_facility not in VALID_FACILITY_RELATIONSHIPS:
            return EnrichmentEligibilityDecision(
                enrich_contact=False,
                authority_confidence="BLOCKED",
                reason=f"Person-to-facility relationship is {person_facility or 'UNKNOWN'}; direct ownership required",
                commercial_relevance="NONE",
                risk_flags=["facility_relationship_insufficient"],
                score_at_decision=norm_score,
            )
        evidence_used.append(f"facility_relationship={person_facility}")

        # ── Step 7: Authority class ────────────────────────────────────
        authority = str(
            candidate.get("authority_class")
            or candidate.get("authority_classification")
            or ""
        ).upper()
        authority_strong = authority in APOLLO_AUTHORITY_CLASSES
        evidence_used.append(f"authority_class={authority or 'UNKNOWN'}")

        commercial_relevance = "DIRECT" if authority_strong else "STRONG" if person_facility in {"FACILITY_OWNER", "FACILITY_FUNCTION_OWNER"} else "WEAK"

        # ── Step 8: Deterministic pass (score >= 0.85 AND strong authority) ──
        if norm_score >= DETERMINISTIC_PASS_THRESHOLD and authority_strong:
            return EnrichmentEligibilityDecision(
                enrich_contact=True,
                authority_confidence="HIGH",
                reason=(
                    f"Deterministic pass: score {norm_score:.2f} >= {DETERMINISTIC_PASS_THRESHOLD:.2f} "
                    f"with authority {authority}"
                ),
                commercial_relevance=commercial_relevance,
                risk_flags=risk_flags,
                evidence_used=evidence_used,
                score_at_decision=norm_score,
            )

        # ── Step 9: Borderline zone — attempt LLM review ──────────────────
        if LLM_BORDERLINE_LOW <= norm_score < LLM_BORDERLINE_HIGH:
            llm_decision = self._llm_authority_review(
                candidate=candidate,
                norm_score=norm_score,
                authority=authority,
                person_facility=person_facility,
                evidence_used=evidence_used,
            )
            if llm_decision is not None:
                return llm_decision

        # Fallback: deterministic block for borderline without valid LLM
        if authority_strong:
            # Strong authority class even without score crossing threshold is passable
            # if within [0.80, 0.85) — near-miss grace window
            if norm_score >= 0.80:
                risk_flags.append("borderline_score_grace_window")
                return EnrichmentEligibilityDecision(
                    enrich_contact=True,
                    authority_confidence="MEDIUM",
                    reason=(
                        f"Near-miss grace: score {norm_score:.2f} in [0.80, 0.85) "
                        f"with strong authority {authority} and verified employment+facility"
                    ),
                    commercial_relevance=commercial_relevance,
                    risk_flags=risk_flags,
                    evidence_used=evidence_used,
                    score_at_decision=norm_score,
                )

        return EnrichmentEligibilityDecision(
            enrich_contact=False,
            authority_confidence="LOW",
            reason=(
                f"Score {norm_score:.2f} in borderline zone; authority {authority or 'UNKNOWN'} "
                "not sufficient for Apollo spend without LLM confirmation"
            ),
            commercial_relevance=commercial_relevance,
            risk_flags=risk_flags + ["borderline_no_llm_confirmation"],
            evidence_used=evidence_used,
            score_at_decision=norm_score,
        )

    # ── Private: LLM authority review ─────────────────────────────────────

    def _llm_authority_review(
        self,
        candidate: Dict[str, Any],
        norm_score: float,
        authority: str,
        person_facility: str,
        evidence_used: List[str],
    ) -> Optional[EnrichmentEligibilityDecision]:
        """Call LLM to determine if borderline candidate merits Apollo enrichment."""
        provider, provider_name = self._get_llm_provider()
        if provider is None:
            logger.warning("[ENRICHMENT_GATE] LLM unavailable; falling back to deterministic decision")
            return None

        name = candidate.get("candidate_name") or candidate.get("name") or "Unknown"
        title = candidate.get("candidate_title") or candidate.get("title") or "Unknown"

        prompt = (
            f"You are evaluating whether to spend Apollo contact enrichment credits on this person:\n\n"
            f"Name: {name}\n"
            f"Title: {title}\n"
            f"Authority Class: {authority}\n"
            f"Facility Relationship: {person_facility}\n"
            f"Composite Score: {norm_score:.2f} (scale 0–1)\n"
            f"Current Employment: VERIFIED\n\n"
            f"Context: This is a calibration services sales system targeting industrial facility managers.\n"
            f"Apollo enrichment costs money. Criteria for YES:\n"
            f"  - Title/authority class indicates direct ownership of metrology, quality, or calibration function\n"
            f"  - Person has direct facility linkage (not group-only)\n"
            f"  - Score above 0.60 with strong domain signals\n\n"
            f"Respond with exactly one word: YES or NO, then one sentence reason."
        )

        try:
            response_text = provider(prompt)
            first_line = str(response_text or "").strip().split("\n")[0].strip().upper()
            approved = first_line.startswith("YES")
            reason_text = str(response_text or "").strip()

            return EnrichmentEligibilityDecision(
                enrich_contact=approved,
                authority_confidence="HIGH" if approved else "LOW",
                reason=f"LLM ({provider_name}) review: {reason_text[:200]}",
                commercial_relevance="DIRECT" if approved else "WEAK",
                risk_flags=[] if approved else ["llm_borderline_rejected"],
                evidence_used=evidence_used + [f"llm_review={provider_name}"],
                llm_used=True,
                llm_provider=provider_name,
                score_at_decision=norm_score,
            )
        except Exception as exc:
            logger.warning("[ENRICHMENT_GATE] LLM review failed (%s): %s", provider_name, exc)
            return None

    def _get_llm_provider(self) -> Tuple[Optional[Any], str]:
        """Return (callable, name) for text completion. DeepSeek primary, Gemini fallback."""
        if self._llm_provider is not None:
            return self._llm_provider, "INJECTED"

        # Try DeepSeek
        try:
            from services.llm_provider import call_deepseek_completion
            def _deepseek(prompt: str) -> str:
                return call_deepseek_completion(prompt, max_tokens=120)
            return _deepseek, "DEEPSEEK"
        except Exception:
            pass

        # Try Gemini
        try:
            from services.llm_provider import call_gemini_completion
            def _gemini(prompt: str) -> str:
                return call_gemini_completion(prompt, max_tokens=120)
            return _gemini, "GEMINI"
        except Exception:
            pass

        return None, ""


# ── Module-level singleton ─────────────────────────────────────────────────
_gate_instance: Optional[PersonEnrichmentEligibilityGate] = None


def get_enrichment_eligibility_gate() -> PersonEnrichmentEligibilityGate:
    global _gate_instance
    if _gate_instance is None:
        _gate_instance = PersonEnrichmentEligibilityGate()
    return _gate_instance
