"""Person Enrichment Eligibility Gate — Phase 2.3 Authority Semantics + LLM Failover.

Design contract:
- Deterministic safety checks come FIRST — mandatory hard blocks.
- LLM (DeepSeek primary / Gemini fallback via FallbackLLMProvider) is the
  secondary authority-classification layer. DeepSeek 504/timeout/exception
  ALWAYS triggers Gemini; both-fail → narrow deterministic fallback.
- The numeric score is a supporting feature; it cannot replace authority semantics.
- Returns EnrichmentEligibilityDecision with enrich_contact + full audit trail.

LLM failover semantics:
  DeepSeek success          → use DeepSeek classification
  DeepSeek 5xx/timeout/exc  → FallbackLLMProvider automatically invokes Gemini
  Gemini success            → use Gemini classification
  Both fail                 → narrow deterministic fallback (NOT semantic rejection)

NB: FUNCTIONALLY_RELEVANT is NOT added to APOLLO_AUTHORITY_CLASSES.
Facility-linked QA/QC Managers may receive STRONG_PLANT_QUALITY_OWNER via
semantic LLM review or narrow deterministic fallback; they do not auto-pass.
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
            or candidate.get("function_ownership")
            or candidate.get("authority")
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

        # ── Step 8b: Deterministic grace window (score in [0.80, 0.85) AND strong authority) ──
        if norm_score >= 0.80 and authority_strong:
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

        # ── Narrow deterministic fallback (both LLMs down) ────────────────────
        # This is SYSTEM/PROVIDER_FAILURE fallback, not a semantic rejection path.
        # Only passes when ALL conditions are simultaneously true:
        #   a. score >= 0.80
        #   b. existing authority class is already in APOLLO_AUTHORITY_CLASSES (strong)
        #      OR the title contains explicit facility-level quality ownership keywords
        #      (QA Manager, QC Manager, Quality Head, Quality Assurance Manager, etc.)
        #      when person_facility indicates FACILITY_FUNCTION_OWNER or stronger.
        #   c. employment and facility already verified (checked above in steps 5–6)
        # Score alone (>= 0.80) is NOT sufficient without the authority/title check.
        if norm_score >= 0.80:
            # Gate A: existing authority_class already in APOLLO set
            if authority_strong:
                risk_flags.append("borderline_score_grace_window_llm_down")
                return EnrichmentEligibilityDecision(
                    enrich_contact=True,
                    authority_confidence="MEDIUM",
                    reason=(
                        f"Narrow deterministic fallback (LLM down): score {norm_score:.2f} >= 0.80, "
                        f"authority {authority} already in APOLLO_AUTHORITY_CLASSES, "
                        "verified employment+facility"
                    ),
                    commercial_relevance=commercial_relevance,
                    risk_flags=risk_flags,
                    evidence_used=evidence_used,
                    score_at_decision=norm_score,
                )

            # Gate B: facility-linked quality ownership title check
            # Only applies when facility_relationship is FACILITY_FUNCTION_OWNER or stronger.
            _strong_facility_rels = {
                "FACILITY_FUNCTION_OWNER", "FACILITY_OWNER",
                "GROUP_FUNCTION_OWNER", "DIRECT", "STRONG",
            }
            _quality_ownership_keywords = [
                "quality assurance manager", "quality control manager",
                "qa manager", "qc manager", "manager quality",
                "quality head", "head quality", "qa head", "qc head",
                "plant quality", "head of quality",
                "quality assurance & control manager",
                "quality assurance and control manager",
            ]
            title_lower = (
                candidate.get("candidate_title") or candidate.get("title") or ""
            ).lower()
            has_quality_ownership = any(
                kw in title_lower for kw in _quality_ownership_keywords
            )
            if has_quality_ownership and person_facility in _strong_facility_rels:
                risk_flags.append(
                    "narrow_deterministic_facility_quality_owner_llm_down"
                )
                return EnrichmentEligibilityDecision(
                    enrich_contact=True,
                    authority_confidence="MEDIUM",
                    reason=(
                        f"Narrow deterministic fallback (LLM down): score {norm_score:.2f} >= 0.80, "
                        f"title '{title_lower[:80]}' indicates facility-level quality ownership, "
                        f"facility_relationship={person_facility}, verified employment"
                    ),
                    commercial_relevance="STRONG",
                    risk_flags=risk_flags,
                    evidence_used=evidence_used + ["narrow_deterministic_quality_ownership"],
                    score_at_decision=norm_score,
                )

        return EnrichmentEligibilityDecision(
            enrich_contact=False,
            authority_confidence="LOW",
            reason=(
                f"Score {norm_score:.2f} in borderline zone; authority {authority or 'UNKNOWN'} "
                "not sufficient for Apollo spend; LLM unavailable and narrow deterministic "
                "fallback conditions not met"
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
        """Call LLM to semantically classify candidate authority and decide enrichment.

        Uses FallbackLLMProvider so DeepSeek 504/timeout/exception automatically
        escalates to Gemini. Both failing returns None → narrow deterministic fallback.
        Provider failure is SYSTEM/PROVIDER_FAILURE, NOT a semantic person rejection.
        """
        provider, provider_name = self._get_llm_provider()
        if provider is None:
            logger.warning(
                "[ENRICHMENT_GATE] Both LLM providers unavailable; "
                "falling back to narrow deterministic decision"
            )
            return None

        name = candidate.get("candidate_name") or candidate.get("name") or "Unknown"
        title = candidate.get("candidate_title") or candidate.get("title") or "Unknown"
        company = (
            candidate.get("candidate_company") or candidate.get("company")
            or candidate.get("company_name") or "Unknown"
        )
        facility = (
            candidate.get("candidate_facility") or candidate.get("facility_name")
            or candidate.get("facility") or "Unknown"
        )
        persona = candidate.get("persona") or candidate.get("persona_type") or "Unknown"
        profile_evidence = (
            candidate.get("public_profile_evidence")
            or candidate.get("evidence")
            or ""
        )[:600]

        prompt = (
            "You are an authority classifier for a calibration services sales system.\n"
            "Your task: classify this person's authority class based on structured evidence,\n"
            "then decide if Apollo contact enrichment is warranted.\n\n"
            "== STRUCTURED EVIDENCE ==\n"
            f"Name: {name}\n"
            f"Title: {title}\n"
            f"Company: {company}\n"
            f"Relevant Facility: {facility}\n"
            f"Facility Relationship: {person_facility}\n"
            f"Current Employment: VERIFIED (confirmed current role at this company)\n"
            f"Persona Type: {persona}\n"
            f"Composite Score: {norm_score:.2f} (scale 0.0–1.0; supporting feature only)\n"
            f"Profile Evidence: {profile_evidence}\n\n"
            "== AUTHORITY TAXONOMY ==\n"
            "Classify into exactly one of these canonical classes:\n"
            "  DIRECT_CALIBRATION_OWNER  — owns/manages calibration lab or metrology function\n"
            "  METROLOGY_OWNER          — CMM, MSA, measurement systems ownership\n"
            "  STRONG_PLANT_QUALITY_OWNER — QA/QC Manager or Head with facility-level quality ownership\n"
            "                              (e.g. Quality Assurance Manager, QC Manager at a named facility)\n"
            "  FACILITY_OWNER           — plant head, factory manager, site head with P&L/operations authority\n"
            "  GROUP_FUNCTION_OWNER     — corporate/group quality function (multi-site scope)\n"
            "  FUNCTIONALLY_RELEVANT    — relevant quality/ops role but without confirmed facility ownership\n"
            "  INSUFFICIENT_AUTHORITY   — junior IC, trainee, inspector, analyst, associate\n\n"
            "== APOLLO ENRICHMENT CRITERIA ==\n"
            "Spend Apollo credits (YES) only when ALL are true:\n"
            "  1. Authority class is one of: DIRECT_CALIBRATION_OWNER, METROLOGY_OWNER,\n"
            "     STRONG_PLANT_QUALITY_OWNER, FACILITY_OWNER, GROUP_FUNCTION_OWNER\n"
            "  2. Facility relationship is verified (DIRECT, STRONG, FACILITY_FUNCTION_OWNER, etc.)\n"
            "  3. Current employment is VERIFIED\n"
            "  4. The person plausibly controls or influences calibration/quality instrument decisions\n"
            "  5. Score >= 0.60 (use as supporting signal only, not the sole determinant)\n\n"
            "IMPORTANT: FUNCTIONALLY_RELEVANT or INSUFFICIENT_AUTHORITY → NO enrichment.\n"
            "  Quality Engineer, Inspector, Analyst, Associate → INSUFFICIENT_AUTHORITY → NO.\n"
            "  QA/QC Manager at a named facility → evaluate for STRONG_PLANT_QUALITY_OWNER.\n\n"
            "== RESPONSE FORMAT ==\n"
            "Line 1: AUTHORITY_CLASS: <one class from taxonomy above>\n"
            "Line 2: ENRICH: YES or NO\n"
            "Line 3: REASON: <one concise sentence>"
        )

        try:
            response_text = provider(prompt)
            lines = [ln.strip() for ln in str(response_text or "").strip().split("\n") if ln.strip()]

            # Parse structured response
            classified_authority = authority  # default to existing
            approved = False
            reason_text = str(response_text or "").strip()[:300]

            for line in lines:
                upper = line.upper()
                if upper.startswith("AUTHORITY_CLASS:"):
                    raw_cls = line.split(":", 1)[1].strip().upper()
                    # Validate against known taxonomy
                    _valid = {
                        "DIRECT_CALIBRATION_OWNER", "METROLOGY_OWNER",
                        "STRONG_PLANT_QUALITY_OWNER", "FACILITY_OWNER",
                        "GROUP_FUNCTION_OWNER", "FUNCTIONALLY_RELEVANT",
                        "INSUFFICIENT_AUTHORITY",
                    }
                    if raw_cls in _valid:
                        classified_authority = raw_cls
                elif upper.startswith("ENRICH:"):
                    approved = "YES" in upper
                elif upper.startswith("REASON:"):
                    reason_text = line.split(":", 1)[1].strip()[:300]

            # Cross-check: LLM approval must only be for authority classes in APOLLO set
            if approved and classified_authority not in APOLLO_AUTHORITY_CLASSES:
                approved = False
                reason_text = (
                    f"LLM classified as {classified_authority} which is not in APOLLO_AUTHORITY_CLASSES; "
                    "enrichment blocked by gate policy."
                )

            logger.info(
                "[ENRICHMENT_GATE] LLM (%s) classified %r → %s | enrich=%s | reason=%s",
                provider_name, title, classified_authority, approved, reason_text[:120],
            )

            return EnrichmentEligibilityDecision(
                enrich_contact=approved,
                authority_confidence="HIGH" if approved else "LOW",
                reason=f"LLM ({provider_name}) authority={classified_authority}: {reason_text}",
                commercial_relevance="DIRECT" if approved else "WEAK",
                risk_flags=[] if approved else ["llm_authority_not_sufficient"],
                evidence_used=evidence_used + [
                    f"llm_review={provider_name}",
                    f"llm_authority_class={classified_authority}",
                ],
                llm_used=True,
                llm_provider=provider_name,
                score_at_decision=norm_score,
            )
        except Exception as exc:
            # Provider runtime failure is SYSTEM/PROVIDER_FAILURE, not a person rejection.
            logger.warning(
                "[ENRICHMENT_GATE] LLM runtime error (%s): %s — "
                "treating as PROVIDER_FAILURE, not semantic rejection",
                provider_name, exc,
            )
            return None

    def _get_llm_provider(self) -> Tuple[Optional[Any], str]:
        """Return (callable, provider_name) via FallbackLLMProvider.

        Uses the production-grade FallbackLLMProvider which internally routes:
          DeepSeek (HiveProvider) → Gemini (GeminiProvider)

        DeepSeek 5xx / timeout / any runtime exception causes FallbackLLMProvider
        to retry with Gemini automatically — the gate never needs to manage
        individual provider retry logic.

        Returns (None, "") only when BOTH providers are unavailable or both raise.
        """
        if self._llm_provider is not None:
            # Injected provider (used in tests or explicit override).
            # Wrap as a simple callable if it's a plain LLMProvider instance.
            from services.llm_provider import LLMProvider as _LLMProvider
            if isinstance(self._llm_provider, _LLMProvider):
                def _call(prompt: str) -> str:
                    resp = self._llm_provider.complete(
                        system_prompt="",
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=300,
                    )
                    return resp.text
                return _call, "INJECTED"
            # Already a callable
            return self._llm_provider, "INJECTED"

        try:
            from services.llm_provider import FallbackLLMProvider, DeepSeekProvider, GeminiProvider
            fallback = FallbackLLMProvider(
                primary=DeepSeekProvider(),
                fallback=GeminiProvider(),
            )
            if not fallback.is_available():
                logger.warning("[ENRICHMENT_GATE] No LLM provider is currently available")
                return None, ""

            # Determine which provider name to report (first available)
            provider_name = "DEEPSEEK"
            try:
                from services.llm_provider import DeepSeekProvider as _DS
                if not _DS().is_available():
                    provider_name = "GEMINI"
            except Exception:
                provider_name = "FALLBACK"

            def _call_via_fallback(prompt: str) -> str:
                resp = fallback.complete(
                    system_prompt="",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=300,
                    temperature=0.1,
                )
                return resp.text

            return _call_via_fallback, provider_name
        except Exception as exc:
            logger.warning("[ENRICHMENT_GATE] Could not initialise LLM providers: %s", exc)
            return None, ""


# ── Module-level singleton ─────────────────────────────────────────────────
_gate_instance: Optional[PersonEnrichmentEligibilityGate] = None


def get_enrichment_eligibility_gate() -> PersonEnrichmentEligibilityGate:
    global _gate_instance
    if _gate_instance is None:
        _gate_instance = PersonEnrichmentEligibilityGate()
    return _gate_instance
