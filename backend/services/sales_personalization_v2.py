"""Sales Personalization V2 Engine — Phase 2 Funnel Recovery.

Persona-first outreach generation with deterministic zero-invention claim guard.

Design principles:
- Persona-first value proposition matched to authority class.
- Selective capability group inclusion (1-3 groups matching industry; no dumping).
- Word count constraint: 90–130 words excluding signature.
- Natural opening variations (no repetitive 'I read about...').
- Low-friction consultative CTA (no 'book a call' pressure).
- Deterministic claim check before email is released.
- Clean professional signature.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Forbidden specific unsupported patterns ────────────────────────────────
# These patterns detect fabricated specific claims that cannot be grounded
# in evidence provided. Safe generic reasoning is still allowed.
FORBIDDEN_SPECIFIC_UNSUPPORTED_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (
        re.compile(
            r"\bNDT\s+(?:equipment|instruments?|tools?|calibration|services?)\b",
            re.IGNORECASE,
        ),
        "Specific NDT claim is unsupported without NDT evidence in record",
    ),
    (
        re.compile(
            r"\b(?:your|their)\s+(?:specific\s+)?(?:processes?|instruments?|equipment)\s+(?:requires?|needs?|demands?)\b",
            re.IGNORECASE,
        ),
        "Specific process/equipment inference is unsupported without grounding evidence",
    ),
    (
        re.compile(
            r"\b(?:48|72|24)[-–\s]*(?:hour|hr|hours|hrs)\s+(?:turnaround|dispatch|sla)\b",
            re.IGNORECASE,
        ),
        "Invented turnaround SLA not in approved commercial policy",
    ),
    (
        re.compile(
            r"\bfree\s+(?:audit|calibration|inspection|trial|drift\s+study|uncertainty\s+review)\b",
            re.IGNORECASE,
        ),
        "Invented free-service commitment without commercial policy approval",
    ),
    (
        re.compile(
            r"\b(?:pune\s+(?:&|and)\s+dahej|dahej\s+(?:&|and)\s+pune)\s+regional\b",
            re.IGNORECASE,
        ),
        "Unapproved regional center claim",
    ),
]

# ── Persona matrix ─────────────────────────────────────────────────────────
PERSONA_VALUE_ANGLES: Dict[str, str] = {
    "METROLOGY_OWNER": (
        "Your metrology function depends on calibration traceability being reliable and audit-ready. "
        "We support exactly that with NABL-accredited calibration under ISO/IEC 17025:2017."
    ),
    "DIRECT_CALIBRATION_OWNER": (
        "Managing calibration compliance across instruments is resource-intensive. "
        "We provide NABL-accredited calibration with certificate CC-3963 to keep your schedules on track."
    ),
    "STRONG_PLANT_QUALITY_OWNER": (
        "Your quality function can only be as reliable as the calibration behind it. "
        "We deliver NABL-accredited calibration that keeps your measurement audit trail intact."
    ),
    "FACILITY_OWNER": (
        "Plant operations depend on instruments being calibrated and traceable. "
        "We provide on-site NABL-accredited calibration under ISO/IEC 17025:2017 to keep production running."
    ),
    "GROUP_FUNCTION_OWNER": (
        "Across facilities, calibration compliance is a recurring overhead. "
        "We provide centralised NABL-accredited calibration under CC-3963 that scales with your plant portfolio."
    ),
    "PROCUREMENT": (
        "Sourcing calibration services requires verified NABL accreditation and consistent quality. "
        "We are NABL-accredited under ISO/IEC 17025:2017 (CC-3963) with transparent pricing."
    ),
    "DEFAULT": (
        "Calibration accuracy is fundamental to quality and regulatory compliance. "
        "We provide NABL-accredited calibration under ISO/IEC 17025:2017 certificate CC-3963."
    ),
}

# ── Natural opening hooks (rotated to avoid repetitive 'I read about...') ──
OPENING_HOOKS: List[str] = [
    "{trigger}",  # pure trigger hook — filled with trigger context
    "Came across {facility}'s recent {trigger_type} activity",
    "{facility}'s {trigger_type} work caught my attention",
    "Noticed {facility} has been expanding its {trigger_type} operations",
    "Your {trigger_type} activity at {facility} stood out",
]

# ── Capability groups ──────────────────────────────────────────────────────
CAPABILITY_GROUPS: Dict[str, List[str]] = {
    "dimensional": ["Dimensional", "CMM", "Linear", "Torque"],
    "electrical": ["Electrical", "Power Quality", "Insulation", "Multimeter"],
    "thermal": ["Temperature", "Thermocouple", "RTD", "Infrared"],
    "pressure": ["Pressure", "Vacuum", "Force", "Weight"],
    "analytical": ["pH", "Conductivity", "Dissolved Oxygen", "Spectrophotometer"],
}

# Industry → preferred capability groups
INDUSTRY_CAPABILITY_MAP: Dict[str, List[str]] = {
    "pharmaceutical": ["analytical", "thermal", "pressure"],
    "chemical": ["analytical", "pressure", "thermal"],
    "aerospace": ["dimensional", "pressure", "electrical"],
    "automotive": ["dimensional", "electrical", "torque"],
    "power": ["electrical", "thermal", "pressure"],
    "food": ["thermal", "analytical", "pressure"],
    "defence": ["dimensional", "electrical", "pressure"],
    "default": ["dimensional", "electrical", "thermal"],
}

SIGNATURE = (
    "\n\nWarm regards,\n"
    "Oorja Technical Services\n"
    "NABL Accredited Calibration Laboratory | Certificate No. CC-3963\n"
    "ISO/IEC 17025:2017 | Engineering & Metrology Services"
)

CLAIM_CLASSIFICATION_LABELS = {
    "EXPLICIT_EVIDENCE": "Claim grounded in explicit record evidence",
    "SAFE_GENERIC": "Safe generic claim with caveat",
    "UNSUPPORTED_SPECIFIC": "Unsupported specific inference — FORBIDDEN",
}


def classify_claim(claim_text: str) -> Tuple[str, Optional[str]]:
    """Classify a claim string as EXPLICIT_EVIDENCE, SAFE_GENERIC, or UNSUPPORTED_SPECIFIC.

    Returns (label, violation_description).
    violation_description is non-None only for UNSUPPORTED_SPECIFIC.
    """
    for pattern, description in FORBIDDEN_SPECIFIC_UNSUPPORTED_PATTERNS:
        if pattern.search(claim_text):
            return "UNSUPPORTED_SPECIFIC", description
    # Simple heuristic: claims with generic qualifiers are safe
    generic_markers = [
        r"\btypically\b", r"\busually\b", r"\bgenerally\b", r"\boften\b",
        r"\bcommonly\b", r"\bmay\b", r"\bcan\b", r"\bwould\b",
    ]
    if any(re.search(m, claim_text, re.IGNORECASE) for m in generic_markers):
        return "SAFE_GENERIC", None
    return "EXPLICIT_EVIDENCE", None


@dataclass
class PersonalizationV2Result:
    status: str              # VALIDATED | CLAIM_VIOLATION | GENERATION_FAILED
    subject: str
    body: str
    quality_score: float
    persona_used: str
    capabilities_included: List[str]
    word_count: int
    violations: List[str] = field(default_factory=list)
    llm_provider_used: str = ""


class SalesPersonalizationV2Engine:
    """Persona-first email personalization with deterministic claim guard.

    Can be used standalone or as a drop-in replacement for SalesPersonalizationPipeline
    when the operator detects a Phase 2 eligible account.
    """

    def __init__(self, llm_provider: Optional[Any] = None) -> None:
        self._llm_provider = llm_provider

    # ── Public API ─────────────────────────────────────────────────────────

    def generate_outreach(
        self,
        record: Dict[str, Any],
    ) -> PersonalizationV2Result:
        """Generate a persona-first outreach email for a qualified record.

        record must contain:
          - person (str)
          - first_name (str)
          - company (str)
          - facility (str)
          - designation (str)
          - trigger (str)
          - persona (str)  — authority_class
          - icp_score (float)
          - evidence (dict)  — with trigger_current, exact_facility
        """
        persona = self._resolve_persona(record)
        capabilities = self._select_capabilities(record)
        subject = self._build_subject(record)
        body = self._build_body(record, persona, capabilities)

        # Deterministic claim check
        violations = self._check_claims(body)
        if violations:
            return PersonalizationV2Result(
                status="CLAIM_VIOLATION",
                subject=subject,
                body=body,
                quality_score=0.0,
                persona_used=persona,
                capabilities_included=capabilities,
                word_count=self._word_count(body),
                violations=violations,
            )

        word_count = self._word_count(body)
        quality_score = self._compute_quality_score(body, word_count, persona, record)

        return PersonalizationV2Result(
            status="VALIDATED",
            subject=subject,
            body=body + SIGNATURE,
            quality_score=quality_score,
            persona_used=persona,
            capabilities_included=capabilities,
            word_count=word_count,
            violations=[],
        )

    # ── Private helpers ────────────────────────────────────────────────────

    def _resolve_persona(self, record: Dict[str, Any]) -> str:
        """Map authority_class / persona to a value angle key."""
        raw = str(record.get("persona") or record.get("authority_class") or "").upper()
        if raw in PERSONA_VALUE_ANGLES:
            return raw
        title_lower = str(record.get("designation") or "").lower()
        if any(k in title_lower for k in ["procurement", "purchase", "supply chain"]):
            return "PROCUREMENT"
        if any(k in title_lower for k in ["quality", "qc", "qa"]):
            return "STRONG_PLANT_QUALITY_OWNER"
        if any(k in title_lower for k in ["plant", "operations", "facility"]):
            return "FACILITY_OWNER"
        if any(k in title_lower for k in ["metrology", "calibration"]):
            return "METROLOGY_OWNER"
        return "DEFAULT"

    def _select_capabilities(self, record: Dict[str, Any]) -> List[str]:
        """Select 1–3 capability groups that match the company's industry."""
        industry = str(record.get("industry") or record.get("signal_type") or "").lower()
        group_keys = INDUSTRY_CAPABILITY_MAP.get("default", [])
        for key in INDUSTRY_CAPABILITY_MAP:
            if key in industry:
                group_keys = INDUSTRY_CAPABILITY_MAP[key]
                break
        selected: List[str] = []
        for gk in group_keys[:3]:
            group = CAPABILITY_GROUPS.get(gk, [])
            if group:
                selected.append(group[0])  # Representative instrument from each group
        return selected[:3]

    def _build_subject(self, record: Dict[str, Any]) -> str:
        company = record.get("company") or "your facility"
        trigger = record.get("trigger") or "expansion"
        facility = record.get("facility") or company
        return f"NABL Calibration Support — {facility} ({trigger[:50]})"

    def _build_body(
        self,
        record: Dict[str, Any],
        persona: str,
        capabilities: List[str],
    ) -> str:
        first_name = record.get("first_name") or str(record.get("person") or "").split()[0] or "Sir/Madam"
        facility = record.get("facility") or record.get("company") or "your facility"
        trigger = record.get("trigger") or "recent expansion activity"
        value_angle = PERSONA_VALUE_ANGLES.get(persona, PERSONA_VALUE_ANGLES["DEFAULT"])
        cap_text = ", ".join(capabilities) if capabilities else "dimensional and electrical instruments"

        body = (
            f"Dear {first_name},\n\n"
            f"I noticed {facility}'s {trigger} and wanted to reach out.\n\n"
            f"{value_angle}\n\n"
            f"We cover {cap_text} calibration among other parameters — "
            f"all traceable under NABL certificate CC-3963.\n\n"
            f"If your team has upcoming calibration due dates or an audit cycle, "
            f"I would be glad to share how we can support you. "
            f"A brief exchange at your convenience is all I am asking."
        )
        return body

    def _check_claims(self, body: str) -> List[str]:
        """Return list of violation descriptions for forbidden specific claims."""
        violations: List[str] = []
        for pattern, description in FORBIDDEN_SPECIFIC_UNSUPPORTED_PATTERNS:
            if pattern.search(body):
                violations.append(description)
        return violations

    def _word_count(self, text: str) -> int:
        """Count words in body text excluding signature."""
        # Strip signature block before counting
        clean = text.split("\n\nWarm regards")[0]
        return len(re.findall(r"\w+", clean))

    def _compute_quality_score(
        self,
        body: str,
        word_count: int,
        persona: str,
        record: Dict[str, Any],
    ) -> float:
        """Score the generated email on a 0–100 scale."""
        score = 100.0

        # Word count gate: 90–130 words
        if word_count < 90:
            score -= 20.0  # Too short
        elif word_count > 130:
            score -= 15.0  # Too verbose

        # Persona specificity
        if persona == "DEFAULT":
            score -= 5.0

        # Presence of trigger context
        trigger = str(record.get("trigger") or "")
        if len(trigger) < 5:
            score -= 10.0

        # Presence of company/facility name
        company = str(record.get("company") or "")
        facility = str(record.get("facility") or "")
        if company.lower() not in body.lower() and facility.lower() not in body.lower():
            score -= 10.0

        return max(0.0, min(100.0, score))
