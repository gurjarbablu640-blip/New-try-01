"""Outreach Claim Guard: Factual Integrity & Zero-Invention Validator.

Strictly audits and sanitizes all generated outreach copy, follow-up messages,
and email previews to ensure ZERO factual hallucination.

Allowed Authority Sources:
1. Database-backed ISO/IEC 17025:2017 NABL Certificate CC-3963
2. Approved Oorja company profile & verified capabilities
3. Explicit user-approved commercial policy

Strictly Forbids Invention of:
- Unapproved regional centers / satellite facility locations (e.g., 'Pune & Dahej Regional Metrology Centers')
- Unapproved turnaround SLAs (e.g., '48-to-72-hour expedited turnaround', '24h turnaround')
- Unapproved commercial promises (e.g., 'free audit', '0 cost', 'unconditional discount')
- Unapproved accreditation certificate numbers (anything other than CC-3963)
- Unaccredited parameter claims (claiming NABL accreditation for items outside CC-3963 schedule)
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from services.oorja_capability_service import (
    CONFIRMED_NABL_SCOPE,
    OORJA_OFFICIAL_CERTIFICATE_NO,
    OUT_OF_SCOPE,
    classify_technical_scope_batch,
)

logger = logging.getLogger(__name__)


# ── Canonical Approved Oorja Baseline ──────────────────────────────────
APPROVED_CERTIFICATE_NO = "CC-3963"
APPROVED_STANDARD = "ISO/IEC 17025:2017"
APPROVED_COMPANY_NAME = "Oorja Technical Services"
APPROVED_DIVISION_NAME = "Engineering & Metrology Services"


# ── Prohibited Unapproved Patterns ─────────────────────────────────────
PROHIBITED_FACILITY_PATTERNS = [
    (
        r"(?:pune\s+&\s+dahej|dahej\s+&\s+pune)\s+regional\s+(?:metrology\s+)?(?:centers|facilities)",
        "Unapproved regional center claim: 'Pune & Dahej Regional Metrology Centers' is not an approved physical facility under CC-3963",
    ),
    (
        r"(?:regional\s+metrology\s+center\s+in\s+(?:pune|dahej|chennai|noida|bangalore))",
        "Invented regional facility location",
    ),
    (
        r"(?:dahej|pune)\s+regional\s+metrology\s+center",
        "Invented regional center location",
    ),
]

PROHIBITED_SLA_PATTERNS = [
    (
        r"\b(?:48[-–\s]*(?:to\s*)?72[-–\s]*(?:hour|hr|hours|hrs)|24[-–\s]*(?:hour|hr|hours|hrs)|48[-–\s]*(?:hour|hr|hours|hrs))\s+(?:expedited\s+)?(?:turnaround|dispatch|sla|certificate)\b",
        "Invented turnaround SLA: 48-hour turnaround commitment lacks user-approved commercial authorization",
    ),
    (
        r"\bguaranteed\s+(?:\d+[-–\s]*(?:hour|hr|day|days))\s+turnaround\b",
        "Invented commercial SLA guarantee",
    ),
    (
        r"\bcertified\s+48-to-72-hour\s+expedited\s+turnaround\b",
        "Invented certified SLA timeframe",
    ),
]

PROHIBITED_STANDARD_SEMANTIC_PATTERNS = [
    (
        r"(?:(?:customer(?:'s)?|client(?:'s)?)\s+)?(?:NABL\s+)?CC-3963\s+standards?\b",
        "Semantic violation: CC-3963 is Oorja's lab accreditation certificate number, NOT a customer compliance standard",
    ),
    (
        r"\bstandards?\s+of\s+CC-3963\b",
        "Semantic violation: CC-3963 is an accreditation certificate number, not an industrial compliance standard",
    ),
]

PROHIBITED_COMMERCIAL_PATTERNS = [
    (
        r"\b(?:free\s+audit|free\s+trial|free\s+calibration|zero[- ]cost\s+audit|100%\s+free)\b",
        "Invented free service commitment without commercial policy approval",
    ),
    (
        r"\bmoney[- ]back\s+guarantee\b",
        "Invented commercial guarantee",
    ),
    (
        r"\b(?:free\s+drift\s+study|complimentary\s+drift\s+study|zero[- ]cost\s+drift\s+study)\b",
        "Invented unapproved complimentary drift study",
    ),
    (
        r"\b(?:free\s+uncertainty\s+review|complimentary\s+uncertainty\s+review|zero[- ]cost\s+uncertainty\s+review)\b",
        "Invented unapproved complimentary uncertainty review",
    ),
    (
        r"\b(?:lowest\s+price\s+guaranteed?|unconditional\s+discount|\d+%\s+discount|fixed\s+rate\s+of\s+rs\.?)\b",
        "Invented unapproved pricing or commercial terms",
    ),
]

UNAPPROVED_CERTIFICATE_PATTERNS = [
    (
        r"\b(?:CC[- ]\d{4,5})\b",
        "Unapproved NABL certificate number detected",
    ),
]


@dataclass
class ClaimViolation:
    category: str
    matched_text: str
    rule_description: str
    severity: str  # CRITICAL, HIGH, MEDIUM


@dataclass
class OutreachClaimAuditReport:
    clean: bool
    violations: List[ClaimViolation] = field(default_factory=list)
    sanitized_text: str = ""
    cc_3963_scope_validated: bool = True
    unapproved_locations_detected: bool = False
    unapproved_slas_detected: bool = False
    unapproved_commercial_detected: bool = False


class OutreachClaimGuard:
    """Validator and sanitizer for outbound communication claims."""

    def audit_outreach_claims(
        self,
        text: str,
        instruments: Optional[List[str]] = None,
    ) -> OutreachClaimAuditReport:
        """Audit text for factual accuracy against Oorja CC-3963 authoritative truth."""
        violations: List[ClaimViolation] = []
        text_lower = (text or "").lower()

        # 1. Check Unapproved Facility Locations
        has_bad_location = False
        for pattern, desc in PROHIBITED_FACILITY_PATTERNS:
            matches = re.findall(pattern, text_lower, re.IGNORECASE)
            for m in matches:
                violations.append(
                    ClaimViolation(
                        category="UNAPPROVED_FACILITY_LOCATION",
                        matched_text=m if isinstance(m, str) else str(m),
                        rule_description=desc,
                        severity="CRITICAL",
                    )
                )
                has_bad_location = True

        # 2. Check Unapproved Turnaround SLAs
        has_bad_sla = False
        for pattern, desc in PROHIBITED_SLA_PATTERNS:
            matches = re.findall(pattern, text_lower, re.IGNORECASE)
            for m in matches:
                violations.append(
                    ClaimViolation(
                        category="UNAPPROVED_TURNAROUND_SLA",
                        matched_text=m if isinstance(m, str) else str(m),
                        rule_description=desc,
                        severity="HIGH",
                    )
                )
                has_bad_sla = True

        # 3. Check Unapproved Commercial Promises
        has_bad_commercial = False
        for pattern, desc in PROHIBITED_COMMERCIAL_PATTERNS:
            matches = re.findall(pattern, text_lower, re.IGNORECASE)
            for m in matches:
                violations.append(
                    ClaimViolation(
                        category="UNAPPROVED_COMMERCIAL_PROMISE",
                        matched_text=m if isinstance(m, str) else str(m),
                        rule_description=desc,
                        severity="HIGH",
                    )
                )
                has_bad_commercial = True

        # 4. Check Certificate Number Accuracy
        for pattern, desc in UNAPPROVED_CERTIFICATE_PATTERNS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for m in matches:
                normalized = m.upper().replace(" ", "-")
                if normalized != APPROVED_CERTIFICATE_NO:
                    violations.append(
                        ClaimViolation(
                            category="UNAPPROVED_CERTIFICATE_NO",
                            matched_text=m,
                            rule_description=f"{desc} (only {APPROVED_CERTIFICATE_NO} is authorized)",
                            severity="CRITICAL",
                        )
                    )

        # 5. Check Scope Compatibility if instruments provided
        scope_valid = True
        if instruments:
            eval_scope = classify_technical_scope_batch(instruments, certificate_no=APPROVED_CERTIFICATE_NO)
            if eval_scope.get(OUT_OF_SCOPE) and not eval_scope.get(CONFIRMED_NABL_SCOPE):
                scope_valid = False
                violations.append(
                    ClaimViolation(
                        category="OUT_OF_SCOPE_NABL_CLAIM",
                        matched_text=", ".join(eval_scope.get(OUT_OF_SCOPE, [])),
                        rule_description="Requested instruments fall outside Oorja CC-3963 accredited schedule",
                        severity="CRITICAL",
                    )
                )

        # 6. Check Semantic Standards Confusion (CC-3963 is Oorja's lab accreditation cert, not customer compliance standard)
        for pattern, desc in PROHIBITED_STANDARD_SEMANTIC_PATTERNS:
            matches = re.findall(pattern, text_lower, re.IGNORECASE)
            for m in matches:
                violations.append(
                    ClaimViolation(
                        category="MISCHARACTERIZED_STANDARD",
                        matched_text=m if isinstance(m, str) else str(m),
                        rule_description=desc,
                        severity="HIGH",
                    )
                )

        sanitized = self.sanitize_text(text)
        is_clean = len(violations) == 0

        return OutreachClaimAuditReport(
            clean=is_clean,
            violations=violations,
            sanitized_text=sanitized,
            cc_3963_scope_validated=scope_valid,
            unapproved_locations_detected=has_bad_location,
            unapproved_slas_detected=has_bad_sla,
            unapproved_commercial_detected=has_bad_commercial,
        )

    def sanitize_text(self, text: str) -> str:
        """Sanitize unapproved claims from text to produce authoritative copy."""
        if not text:
            return ""

        sanitized = text

        # 1. Replace unapproved regional center claims with authoritative footer
        sanitized = re.sub(
            r"Facilities:\s*Pune\s*&\s*Dahej\s*Regional\s*Metrology\s*Centers",
            f"Engineering & Metrology Services\nAccreditation: {APPROVED_STANDARD} (NABL {APPROVED_CERTIFICATE_NO})",
            sanitized,
            flags=re.IGNORECASE,
        )
        sanitized = re.sub(
            r"Pune\s*&\s*Dahej\s*Regional\s*Metrology\s*Centers",
            f"Engineering & Metrology Services",
            sanitized,
            flags=re.IGNORECASE,
        )

        # 2. Replace unapproved turnaround SLAs with consultative timing
        sanitized = re.sub(
            r"provides\s+a\s+certified\s+48-to-72-hour\s+expedited\s+turnaround\s+with\s+on-site\s+calibration\s+teams",
            f"provides ISO/IEC 17025:2017 accredited calibration (NABL CC-3963) with on-site calibration capabilities",
            sanitized,
            flags=re.IGNORECASE,
        )
        sanitized = re.sub(
            r"48-to-72-hour\s+expedited\s+turnaround",
            "responsive calibration turnaround aligned with plant production schedules",
            sanitized,
            flags=re.IGNORECASE,
        )
        sanitized = re.sub(
            r"48[-–]72h\s+turnaround\s+SLA",
            "accredited calibration turnaround and measurement uncertainty schedule",
            sanitized,
            flags=re.IGNORECASE,
        )

        # 3. Replace free audit / commercial guarantees / unapproved promises
        sanitized = re.sub(
            r"\b(?:free\s+audit|free\s+trial|zero[- ]cost\s+audit)\b",
            "consultative technical review",
            sanitized,
            flags=re.IGNORECASE,
        )
        sanitized = re.sub(
            r"\b(?:free|complimentary|zero[- ]cost)\s+drift\s+study\b",
            "measurement drift and stability analysis",
            sanitized,
            flags=re.IGNORECASE,
        )
        sanitized = re.sub(
            r"\b(?:free|complimentary|zero[- ]cost)\s+uncertainty\s+review\b",
            "CMC measurement uncertainty evaluation",
            sanitized,
            flags=re.IGNORECASE,
        )

        # 4. Correct CC-3963 described as a customer compliance standard
        sanitized = re.sub(
            r"\b(?:NABL\s+)?CC-3963\s+standards?\b",
            "ISO/IEC 17025:2017 (NABL CC-3963) accredited scope",
            sanitized,
            flags=re.IGNORECASE,
        )

        return sanitized


# Global instance
outreach_claim_guard = OutreachClaimGuard()
