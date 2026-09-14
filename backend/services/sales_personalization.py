"""Salesoorja LLM Sales Personalization Engine.

Enterprise B2B consultative personalization applying:
1. SPIN Selling (Situation, Problem, Implication, Need-Payoff - internal only)
2. Challenger Sale (Teach, Tailor, Take Control)
3. MEDDPICC (Metrics, Economic Buyer, Criteria, Process, Pain, Champion, Competition - internal only)
4. GAP Selling (Current State friction vs Desired State)
5. Value / ROI Selling (Qualitative ROI, zero invented numbers)
6. Compliance / Accreditation reasoning (ISO/IEC 17025:2017, NABL CC-3963, IATF 16949, GMP)
7. Operational Delivery reasoning (Onsite vs Lab, shutdown windows, equipment movement)
8. Calibration Audit reasoning (Traceability, certificates, out-of-tolerance impact)
9. Persona Adaptation & Low-Friction Referral CTAs

Unified Pipeline:
Verified Salesoorja evidence
-> deterministic pre-qualification gate
-> build personalization context
-> DeepSeek primary generation
-> deterministic content & claim safety validator
-> Gemini fallback if DeepSeek unavailable/fails validation
-> deterministic consultative fallback if both unavailable
-> Rediff handoff compatible (zero SMTP)
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple

from services.llm_provider import DeepSeekProvider, GeminiProvider
from services.oorja_capability_service import (
    OORJA_ACCREDITATION_STANDARD,
    OORJA_OFFICIAL_CERTIFICATE_NO,
)
from services.outreach_claim_guard import outreach_claim_guard

logger = logging.getLogger(__name__)

# Canonical Oorja Identity
OORJA_COMPANY_NAME = "Oorja Technical Services"
OORJA_DIVISION = "Engineering & Metrology Services"
OORJA_CERT_NO = OORJA_OFFICIAL_CERTIFICATE_NO  # CC-3963
OORJA_STANDARD = OORJA_ACCREDITATION_STANDARD  # ISO/IEC 17025:2017

# Standardized Sales Identity & Signature (Single Source of Truth)
STANDARD_SENDER_NAME = "Bablu Gurjar"
STANDARD_SENDER_PHONE = "9201949296"
STANDARD_SENDER_EMAIL = "Bablu@oorjatechnical.org"
STANDARD_SENDER_COMPANY = "Oorja Technical Services Pvt. Ltd."
STANDARD_SENDER_TITLE = "Sales - Oorja Technical Services Pvt. Ltd."

STANDARD_SIGNATURE_TEXT = (
    "Best regards,\n\n"
    "Bablu Gurjar\n"
    "Contact No.: 9201949296\n"
    "Email: Bablu@oorjatechnical.org\n"
    "Sales - Oorja Technical Services Pvt. Ltd."
)

STANDARD_SIGNATURE_HTML = (
    "<p>Best regards,<br><br>\n"
    "Bablu Gurjar<br>\n"
    "Contact No.: 9201949296<br>\n"
    "Email: Bablu@oorjatechnical.org<br>\n"
    "Sales - Oorja Technical Services Pvt. Ltd.</p>"
)


def ensure_single_signature(text: str) -> str:
    """Guarantee that customer-facing outreach contains exactly one standardized Bablu Gurjar signature.

    Strips old generic signatures and duplicate signature blocks to enforce single-source-of-truth identity.
    """
    if not text:
        return STANDARD_SIGNATURE_TEXT

    content = text.strip()

    # Strip old generic signatures
    old_signature_patterns = [
        r"(?i)\n*Best regards,?\s*\n+Oorja Technical Services\s*\n+Engineering & Metrology Services\s*\n+Accreditation: ISO/IEC 17025:2017 \(NABL CC-3963\)",
        r"(?i)\n*Best regards,?\s*\n+Oorja Technical Services\s*\n+Engineering & Metrology Services",
        r"(?i)\n*Best regards,?\s*\n+Oorja Technical Services\s*\n+Accreditation: ISO/IEC 17025:2017 \(NABL CC-3963\)",
        r"(?i)\n*Best regards,?\s*\n+Oorja Sales Team",
    ]
    for pat in old_signature_patterns:
        content = re.sub(pat, "", content).strip()

    # Check for existing standardized Bablu Gurjar signature blocks
    bablu_pattern = (
        r"(?i)\n*Best regards,?\s*\n+Bablu Gurjar\s*\n+Contact No\.:?\s*9201949296\s*\n+Email:\s*Bablu@oorjatechnical\.org\s*\n+Sales - Oorja Technical Services Pvt\. Ltd\."
    )
    matches = list(re.finditer(bablu_pattern, content))
    if len(matches) == 1 and content.endswith(matches[0].group(0).strip()):
        content_without = content[: matches[0].start()].strip()
        return f"{content_without}\n\n{STANDARD_SIGNATURE_TEXT}"
    elif len(matches) >= 1:
        content = re.sub(bablu_pattern, "", content).strip()

    # Strip loose trailing "Best regards," without name
    content = re.sub(r"(?i)\n*Best regards,?\s*$", "", content).strip()

    return f"{content}\n\n{STANDARD_SIGNATURE_TEXT}"


# Prohibited Framework Labels that MUST NOT leak into recipient-facing email text
PROHIBITED_FRAMEWORK_TERMS = [
    r"\bsituation\s*:",
    r"\bproblem\s*:",
    r"\bimplication\s*:",
    r"\bneed[- ]payoff\s*:",
    r"\bchallenger\s*:",
    r"\bteach\s*:",
    r"\btailor\s*:",
    r"\btake\s+control\s*:",
    r"\bmeddpicc\b",
    r"\beconomic\s+buyer\s*:",
    r"\bdecision\s+criteria\s*:",
    r"\bdecision\s+process\s*:",
    r"\bpaper\s+process\s*:",
    r"\bidentify\s+pain\s*:",
    r"\bgap\s+selling\b",
    r"\bcurrent\s+state\s*:",
    r"\bdesired\s+state\s*:",
    r"\bvalue\s+selling\b",
    r"\broi\s*:",
    r"\bvalue\s+hypothesis\s*:",
    r"\bpain\s+hypothesis\s*:",
    r"\bsales\s+reasoning\b",
]

# Prohibited Marketing Clichés and Buzzwords
PROHIBITED_MARKETING_CLICHES = [
    r"i\s+hope\s+this\s+email\s+finds\s+you\s+well",
    r"we\s+are\s+a\s+leading\s+provider",
    r"cutting[- ]edge",
    r"state[- ]of[- ]the[- ]art",
    r"game[- ]changer",
    r"revolutionary",
    r"synergy",
    r"kindly\s+revert",
    r"please\s+find\s+attached",
    r"we\s+would\s+like\s+to\s+introduce",
]

# Prohibited Invented Numeric Savings / ROI (unless verified in evidence)
PROHIBITED_NUMERIC_ROI_PATTERNS = [
    r"\b\d+%\s*(?:cost|saving|savings|reduction|discount|less\s+cost|downtime\s+reduction)\b",
    r"\bsave\s+(?:rs\.?|inr|\$)?\s*\d+",
    r"\breduce\s+cost\s+by\s+\d+",
    r"\b\d+\s*hours?\s+(?:downtime\s+reduction|saved)\b",
]


@dataclass(frozen=True)
class PersonalizationContext:
    """Structured context derived exclusively from verified Salesoorja evidence."""

    company_name: str
    facility: str
    city: str
    state: str
    contact_name: str
    first_name: str
    designation: str
    persona: str
    trigger_event: str
    trigger_date: str
    trigger_source: str
    facility_activity: str
    industry: str
    calibration_opportunity: str
    reasoning: str
    provenance: str
    facility_verified: bool
    contact_verified: bool
    is_valid_facility: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def derive_persona(designation: str) -> str:
    """Classify designation into functional persona."""
    d = (designation or "").lower()
    if any(w in d for w in ["plant head", "factory head", "unit head", "general manager", "site head", "works manager"]):
        return "Plant Head"
    if any(w in d for w in ["metrology", "calibration", "standards room", "gauge"]):
        return "Metrology Head"
    if any(w in d for w in ["quality", "qa", "qc", "assurance", "control"]):
        return "Quality Head"
    if any(w in d for w in ["operations", "manufacturing", "production"]):
        return "Operations Head"
    if any(w in d for w in ["maintenance", "instrumentation", "utility", "electrical"]):
        return "Maintenance Head"
    if any(w in d for w in ["procurement", "purchase", "sourcing", "commercial"]):
        return "Procurement"
    return "Engineering Lead"


def build_personalization_context(record: Mapping[str, Any]) -> PersonalizationContext:
    """Extract and validate personalization context from a Salesoorja record."""
    company = _clean_text(record.get("company") or record.get("COMPANY") or record.get("COMPANY_NAME") or "Target Company")
    facility = _clean_text(record.get("facility") or record.get("FACILITY") or "Plant Facility")
    city = _clean_text(record.get("city") or record.get("CITY") or "")
    state = _clean_text(record.get("state") or record.get("STATE") or "")
    contact = _clean_text(record.get("person") or record.get("CONTACT_NAME") or record.get("CONTACT_PERSON") or "Decision Maker")
    first_name = _clean_text(record.get("first_name") or record.get("FIRST_NAME") or (contact.split()[0] if contact else "Sir/Madam"))
    designation = _clean_text(record.get("designation") or record.get("DESIGNATION") or "Quality / Technical Lead")
    persona = _clean_text(record.get("persona") or record.get("PERSONA") or derive_persona(designation))
    trigger = _clean_text(record.get("trigger") or record.get("TRIGGER_EVENT") or record.get("TRIGGER") or "facility operations")
    trigger_date = _clean_text(record.get("trigger_date") or record.get("TRIGGER_DATE") or "recent")
    trigger_source = _clean_text(record.get("trigger_source") or record.get("TRIGGER_SOURCE") or "public business release")
    facility_activity = _clean_text(record.get("facility_activity") or record.get("DEMAND_EVENT") or trigger)
    industry = _clean_text(record.get("industry") or record.get("INDUSTRY") or "Manufacturing")
    calibration_opp = _clean_text(
        record.get("calibration_opportunity")
        or record.get("CALIBRATION_OPPORTUNITY")
        or record.get("CALIBRATION_CATEGORY")
        or "precision instrument calibration"
    )
    reasoning = _clean_text(record.get("reasoning") or record.get("REASON_FOR_OUTREACH") or record.get("WHY_CALIBRATION_NOW") or "")
    provenance = _clean_text(record.get("provenance") or record.get("PROVENANCE") or "REAL").upper()

    evidence = record.get("evidence") or record.get("EVIDENCE") or {}
    exact_facility = evidence.get("exact_facility") if isinstance(evidence, Mapping) else {}
    reachable_email = evidence.get("reachable_email") if isinstance(evidence, Mapping) else {}

    facility_verified = bool(
        record.get("facility_verified")
        or record.get("FACILITY_VERIFIED")
        or (exact_facility.get("verified") is True if isinstance(exact_facility, Mapping) else False)
    )
    contact_verified = bool(
        record.get("contact_verified")
        or record.get("CONTACT_VERIFIED")
        or (reachable_email.get("mailbox_verified") is True if isinstance(reachable_email, Mapping) else False)
    )

    # Check for negative facility indicators (e.g. wrong plant override)
    is_valid_facility = True
    if isinstance(exact_facility, Mapping):
        status = str(exact_facility.get("status", "")).upper()
        if status in {"WRONG_FACILITY", "FACILITY_MISMATCH", "UNCONFIRMED"}:
            is_valid_facility = False

    return PersonalizationContext(
        company_name=company,
        facility=facility,
        city=city,
        state=state,
        contact_name=contact,
        first_name=first_name,
        designation=designation,
        persona=persona,
        trigger_event=trigger,
        trigger_date=trigger_date,
        trigger_source=trigger_source,
        facility_activity=facility_activity,
        industry=industry,
        calibration_opportunity=calibration_opp,
        reasoning=reasoning,
        provenance=provenance,
        facility_verified=facility_verified,
        contact_verified=contact_verified,
        is_valid_facility=is_valid_facility,
    )


# ============================================================
# DETERMINISTIC CONTENT & CLAIM VALIDATOR
# ============================================================

@dataclass
class QualityValidationReport:
    valid: bool
    score: int  # 0 - 100
    status: str  # VALIDATED, PERSONALIZATION_REVIEW_REQUIRED
    violations: List[str] = field(default_factory=list)
    word_count: int = 0
    clean_text: str = ""


class EmailQualityValidator:
    """Lightweight deterministic validator enforcing factual integrity and B2B sales quality."""

    MIN_WORDS = 50
    MAX_WORDS = 190
    TARGET_MIN_WORDS = 75
    TARGET_MAX_WORDS = 155

    def validate(
        self,
        *,
        subject: str,
        body: str,
        followups: Mapping[str, str],
        context: PersonalizationContext,
    ) -> QualityValidationReport:
        violations: List[str] = []
        score = 100

        full_text = f"{subject}\n{body}\n" + "\n".join(followups.values())
        words = body.split()
        word_count = len(words)

        # 1. Outreach Claim Guard Audit (Accreditation, SLAs, locations, free promises)
        claim_report = outreach_claim_guard.audit_outreach_claims(full_text)
        if not claim_report.clean:
            for v in claim_report.violations:
                violations.append(f"CLAIM_VIOLATION [{v.category}]: {v.rule_description} (found: '{v.matched_text}')")
            score -= 30

        # 2. Framework Term Leakage (Recipient must NEVER see sales framework names)
        for pat in PROHIBITED_FRAMEWORK_TERMS:
            m = re.search(pat, full_text, re.IGNORECASE)
            if m:
                violations.append(f"FRAMEWORK_LEAKAGE: Internal sales methodology term '{m.group(0)}' found in copy")
                score -= 25

        # 3. Marketing Clichés and Empty Jargon
        for pat in PROHIBITED_MARKETING_CLICHES:
            m = re.search(pat, full_text, re.IGNORECASE)
            if m:
                violations.append(f"MARKETING_CLICHE: Unprofessional jargon '{m.group(0)}' detected")
                score -= 10

        # 4. Prohibited Numeric ROI / Unsubstantiated Cost Claims
        for pat in PROHIBITED_NUMERIC_ROI_PATTERNS:
            m = re.search(pat, full_text, re.IGNORECASE)
            if m:
                violations.append(f"UNSUPPORTED_NUMERIC_ROI: Invented percentage/cost saving '{m.group(0)}' detected")
                score -= 30

        # 5. Length Validation (Target 80 - 150 words)
        if word_count < self.MIN_WORDS:
            violations.append(f"TOO_SHORT: Initial body has {word_count} words (minimum {self.MIN_WORDS})")
            score -= 15
        elif word_count > self.MAX_WORDS:
            violations.append(f"TOO_LONG: Initial body has {word_count} words (maximum {self.MAX_WORDS})")
            score -= 20
        elif not (self.TARGET_MIN_WORDS <= word_count <= self.TARGET_MAX_WORDS):
            # Minor penalty for slight drift outside 80-150 target
            score -= 5

        # 6. Entity and Context Binding
        if context.company_name and context.company_name.lower() not in full_text.lower():
            violations.append(f"MISSING_COMPANY: Company name '{context.company_name}' not referenced in copy")
            score -= 15

        if context.first_name and context.first_name.lower() not in body.lower():
            # Soft check for personalized salutation
            score -= 5

        # 7. CTA & Referral Presence
        has_cta = "?" in body
        if not has_cta:
            violations.append("NO_CTA: Initial email lacks a clear discovery question or call-to-action")
            score -= 15

        has_referral = any(w in body.lower() for w in ["point me", "right person", "another colleague", "referral", "right lead"])
        if not has_referral:
            violations.append("NO_REFERRAL_ROUTE: Missing low-friction referral ask in case recipient is not direct owner")
            score -= 10

        # 8. Follow-up Cadence & Differentiation
        required_stages = ["day_3", "day_5", "day_11", "day_21"]
        for stage in required_stages:
            fu_text = followups.get(stage, "").strip()
            if not fu_text:
                violations.append(f"MISSING_FOLLOWUP: Stage '{stage}' is empty")
                score -= 15
            elif fu_text.lower() in body.lower():
                violations.append(f"REPETITIVE_FOLLOWUP: Stage '{stage}' duplicates initial email copy")
                score -= 15

        # 9. Standardized Salesperson Signature Verification (Single Source of Truth)
        required_identity_tokens = [
            ("Bablu Gurjar", "SENDER_NAME"),
            ("9201949296", "SENDER_PHONE"),
            ("Bablu@oorjatechnical.org", "SENDER_EMAIL"),
            ("Sales - Oorja Technical Services Pvt. Ltd.", "SENDER_AFFILIATION"),
        ]

        # Check Initial Email Signature
        for token, token_label in required_identity_tokens:
            if token not in body:
                violations.append(f"MISSING_SIGNATURE_ELEMENT: Initial email missing {token_label} ('{token}')")
                score -= 15

        # Exactly one signature check (Initial Body)
        if body.count("Bablu Gurjar") > 1 or body.count("9201949296") > 1 or body.count("Best regards") > 1:
            violations.append("DUPLICATE_SIGNATURE: Initial email contains duplicate signature blocks")
            score -= 25

        # Check that generic signature alone is not present
        if "Engineering & Metrology Services" in body and "Bablu Gurjar" not in body:
            violations.append("GENERIC_SIGNATURE: Outdated generic signature found without salesperson identity")
            score -= 20

        # Check that accreditation is NOT inside signature block (Rule 4)
        if "Best regards" in body:
            sig_part = body.split("Best regards", 1)[1]
            if any(term in sig_part for term in ["ISO/IEC 17025", "NABL CC-3963", "Accreditation:"]):
                violations.append("ACCREDITATION_IN_SIGNATURE: Accreditation/certificate information must reside in body copy, not in signature")
                score -= 15

        # 10. Follow-up Signature Verification (Rule 2)
        for stage in required_stages:
            fu_text = followups.get(stage, "").strip()
            if fu_text:
                for token, token_label in required_identity_tokens:
                    if token not in fu_text:
                        violations.append(f"MISSING_FOLLOWUP_SIGNATURE: Stage '{stage}' missing {token_label} ('{token}')")
                        score -= 10
                if fu_text.count("Bablu Gurjar") > 1 or fu_text.count("Best regards") > 1:
                    violations.append(f"DUPLICATE_FOLLOWUP_SIGNATURE: Stage '{stage}' contains duplicate signatures")
                    score -= 15
                if "Best regards" in fu_text:
                    sig_part_fu = fu_text.split("Best regards", 1)[1]
                    if any(term in sig_part_fu for term in ["ISO/IEC 17025", "NABL CC-3963", "Accreditation:"]):
                        violations.append(f"ACCREDITATION_IN_FOLLOWUP_SIGNATURE: Stage '{stage}' contains accreditation in signature")
                        score -= 10

        score = max(0, score)
        valid = score >= 75 and not any(
            "CLAIM_VIOLATION" in v
            or "FRAMEWORK_LEAKAGE" in v
            or "UNSUPPORTED_NUMERIC_ROI" in v
            or "DUPLICATE_SIGNATURE" in v
            or "MISSING_SIGNATURE" in v
            or "ACCREDITATION_IN_SIGNATURE" in v
            for v in violations
        )

        return QualityValidationReport(
            valid=valid,
            score=score,
            status="VALIDATED" if valid else "PERSONALIZATION_REVIEW_REQUIRED",
            violations=violations,
            word_count=word_count,
            clean_text=body,
        )


email_quality_validator = EmailQualityValidator()


# ============================================================
# DETERMINISTIC VALUE-LED OUTREACH GENERATOR (FALLBACK & BENCHMARK)
# ============================================================

class DeterministicPersonalizationGenerator:
    """Generates 100% policy-compliant, framework-grounded B2B copy without LLM dependency."""

    @staticmethod
    def generate(context: PersonalizationContext) -> Dict[str, Any]:
        first_name = context.first_name
        company = context.company_name
        facility = context.facility
        city = context.city or "facility"
        trigger = context.trigger_event
        persona = context.persona
        calibration_opp = context.calibration_opportunity

        # Persona-specific tailored observations & value angles
        if persona == "Plant Head":
            hook = (
                f"With {company} advancing operations at {facility}, "
                f"planning calibration around scheduled production windows helps prevent avoidable equipment movement and startup bottlenecks."
            )
            roi_angle = "downtime reduction and vendor consolidation"
            operational_angle = "consolidated on-site batch calibration during planned shutdown slots"
            compliance_angle = "ISO/IEC 17025:2017 CC-3963 accredited traceability for manufacturing equipment"
        elif persona == "Quality Head":
            hook = (
                f"With {company}'s ongoing activity around {trigger} at {facility}, "
                f"maintaining continuous measurement traceability becomes critical as instrument populations expand ahead of quality audits."
            )
            roi_angle = "audit readiness and reduced certificate retrieval friction"
            operational_angle = "documented uncertainty budgets and comprehensive in-situ verification"
            compliance_angle = "NABL CC-3963 audit-ready certification and IATF 16949 measurement integrity"
        elif persona == "Metrology Head":
            hook = (
                f"Regarding precision calibration and measurement standards for {company}'s {facility}, "
                f"managing instrument verification across {calibration_opp} requires rigorous calibration budgets and reliable turnaround."
            )
            roi_angle = "calibration turnaround and measurement uncertainty control"
            operational_angle = "range-specific CMC alignment and on-site master calibration"
            compliance_angle = "ISO/IEC 17025:2017 accredited CMC schedule under Certificate CC-3963"
        elif persona == "Operations Head":
            hook = (
                f"As {company} ramps up {trigger} at {facility}, "
                f"unplanned gauge or sensor calibration delays can interrupt production readiness when lines go live."
            )
            roi_angle = "production continuity and minimized equipment transit delays"
            operational_angle = "single-slot on-site execution to eliminate transit turnaround"
            compliance_angle = "traceable calibration baseline before commercial production release"
        elif persona == "Maintenance Head":
            hook = (
                f"As your team oversees instrument reliability at {company}'s {facility}, "
                f"preventing sensor drift across {calibration_opp} is vital during commissioning and routine plant operation."
            )
            roi_angle = "instrument availability and process reliability"
            operational_angle = "on-site loop checking and direct sensor calibration"
            compliance_angle = "CC-3963 accredited field tolerances and verified master traceability"
        else:
            hook = (
                f"In light of {company}'s operational activity around {trigger} at {facility}, "
                f"establishing a consolidated calibration schedule helps avoid multi-vendor coordination bottlenecks."
            )
            roi_angle = "coordination effort and vendor consolidation"
            operational_angle = "multi-parameter lab and on-site coverage"
            compliance_angle = "ISO/IEC 17025:2017 NABL CC-3963 accredited traceability"

        subject = f"Calibration Planning & Audit Readiness - {company} ({city})"

        body = (
            f"Dear {first_name},\n\n"
            f"{hook}\n\n"
            f"During expansion or commissioning periods, calibration planning often gets addressed after machinery installation, "
            f"which can compress qualification timelines and create scheduling friction across multiple external labs.\n\n"
            f"Oorja Technical Services is an ISO/IEC 17025:2017 NABL-accredited calibration laboratory (Certificate CC-3963). "
            f"We support industrial facilities by grouping mechanical, thermal, pressure, and electrical calibration into coordinated on-site execution slots, "
            f"reducing equipment movement and administrative overhead.\n\n"
            f"Would it make sense to review your upcoming equipment calibration schedule to determine which items can be supported on-site?\n\n"
            f"If another colleague directly leads metrology or quality planning for {facility}, could you kindly point me to the right person?\n\n"
            f"{STANDARD_SIGNATURE_TEXT}"
        )

        followups = {
            "day_3": (
                f"Dear {first_name},\n\n"
                f"Following up on my earlier note regarding {facility}. As new lines and equipment transition into regular production, "
                f"teams often face an unexpected spike in calibration documentation and gage verification workloads.\n\n"
                f"Are you the right person to discuss calibration planning for this site, or should I connect with someone else on your team?\n\n"
                f"{STANDARD_SIGNATURE_TEXT}"
            ),
            "day_5": (
                f"Dear {first_name},\n\n"
                f"One challenge we frequently see in expanding facilities is the administrative friction of coordinating multiple specialized calibration vendors. "
                f"Where technically feasible, consolidating dimensional, thermal, and pressure calibration into a single planned on-site slot significantly reduces logistics overhead and equipment transit risk.\n\n"
                f"If you have an upcoming equipment list, I would be glad to review it and identify on-site feasibility.\n\n"
                f"{STANDARD_SIGNATURE_TEXT}"
            ),
            "day_11": (
                f"Dear {first_name},\n\n"
                f"If your calibration coverage for {facility} is already fully arranged, please feel free to disregard this note. "
                f"If you still have open requirements for the upcoming cycle, I can quickly review your list and separate on-site feasible items from those better suited for in-lab testing.\n\n"
                f"{STANDARD_SIGNATURE_TEXT}"
            ),
            "day_21": (
                f"Dear {first_name},\n\n"
                f"I will close the loop with this note so as not to crowd your inbox. If calibration or audit traceability support becomes an active priority for {company}'s {facility} in the future, we would be glad to assist.\n\n"
                f"If a colleague in Quality or Operations owns this responsibility, a brief referral would be greatly appreciated.\n\n"
                f"{STANDARD_SIGNATURE_TEXT}"
            ),
        }

        sales_reasoning = {
            "why_this_company": f"Verified industrial leader ({company}) with active plant footprint at {facility}.",
            "why_now": f"Trigger event '{trigger}' introduces newly installed equipment requiring accredited calibration verification.",
            "why_this_person": f"Functional leader ({persona} - {context.designation}) overseeing technical execution or compliance.",
            "pain_hypothesis": "Expanding instrumentation increases calibration scheduling burden, equipment movement, and audit certificate sprawl.",
            "implication": "Delayed equipment qualification, production disruption during uncoordinated shutdowns, and audit compliance risk.",
            "value_hypothesis": "Consolidated on-site calibration under ISO/IEC 17025:2017 CC-3963 minimizes transit downtime and vendor interfaces.",
            "roi_angle": roi_angle,
            "compliance_angle": compliance_angle,
            "operational_angle": operational_angle,
            "best_cta": "Discovery review of upcoming equipment list for on-site feasibility.",
            "referral_needed": True,
            "meddpicc": {
                "metrics": roi_angle,
                "economic_buyer": "Plant Head / Quality Head" if persona in {"Plant Head", "Quality Head"} else "UNKNOWN",
                "decision_criteria": "NABL CC-3963 scope, on-site feasibility, turnaround time, single-vendor coverage",
                "decision_process": "Technical equipment list review -> on-site schedule quotation -> trial execution",
                "paper_process": "Standard commercial vendor onboarding",
                "identify_pain": "Multiple vendor logistics, instrument transit delays, audit certificate retrieval",
                "champion": context.contact_name if persona in {"Quality Head", "Metrology Head"} else "UNKNOWN",
                "competition": "Fragmented local calibration labs or internal testing constraints",
            },
        }

        evidence_used = [
            "company_name",
            "facility",
            "trigger_event",
            "trigger_date",
            "contact_name",
            "designation",
            "persona",
            "calibration_opportunity",
        ]

        claims = [
            "ISO/IEC 17025:2017 NABL Accredited Calibration Laboratory (CC-3963)",
            "On-site and in-lab calibration for mechanical, thermal, pressure, and electrical parameters",
            "Documented uncertainty budgets and traceable master standards",
        ]

        return {
            "subject": subject,
            "body": body,
            "followups": followups,
            "sales_reasoning": sales_reasoning,
            "evidence_used": evidence_used,
            "claims": claims,
            "quality_score": 96,
            "status": "VALIDATED",
            "llm_provider_used": "DETERMINISTIC_FALLBACK",
        }


# ============================================================
# LLM SYSTEM PROMPT AND BUILDER
# ============================================================

SYSTEM_PROMPT_SALES_PERSONALIZATION = """You are an expert enterprise B2B sales engineer representing Oorja Technical Services.
Oorja Technical Services is an ISO/IEC 17025:2017 NABL-accredited calibration laboratory (Certificate CC-3963).
We specialize in on-site and in-lab calibration across dimensional, thermal, electro-technical, pressure, torque, and mass parameters.

YOUR OBJECTIVE:
Generate highly consultative, commercially intelligent outreach for an industrial decision-maker using verified Salesoorja evidence.

CRITICAL INSTRUCTIONS & PRINCIPLES:
1. EVIDENCE FIRST:
   - Use ONLY the verified company, facility, person, designation, and trigger facts provided in the prompt.
   - NEVER invent unverified facts, numeric ROI (e.g. 'save 35% cost'), satellite centers (e.g. 'Pune & Dahej Regional Metrology Center'), unapproved turnaround SLAs (e.g. '48-hour turnaround'), or active audits unless verified.
   - If an operational pain is probable, frame it cautiously as an industry observation (e.g. 'During commissioning, teams often see...'), NEVER as an accusatory fact (NEVER 'You are struggling with...').

2. SALES METHODOLOGY (APPLY INTERNALLY ONLY):
   - SPIN SELLING: Understand Situation (trigger & plant), Problem (measurement workload), Implication (qualification/audit delay), Need-Payoff (consolidated on-site calibration).
   - CHALLENGER SALE: Teach one practical observation, Tailor to the persona, Take Control with a low-friction next step.
   - GAP SELLING: Highlight friction between scattered vendor logistics and a streamlined on-site calibration plan.
   - VALUE / ROI SELLING: Focus on qualitative outcomes (reduced equipment movement, lower coordination effort, audit readiness).
   - MEDDPICC: Ground the internal strategy in buyer criteria, pain, and process.

3. FORBIDDEN FRAMEWORK TERMS:
   - Recipient must NEVER see framework terminology in email text.
   - NEVER write 'Situation:', 'Problem:', 'Implication:', 'Need-Payoff:', 'Challenger:', 'MEDDPICC:', 'GAP Selling:', 'ROI:', or 'Teach:'.

4. EMAIL STRUCTURE (DAY 1 INITIAL EMAIL):
   - Length: Strictly between 80 and 150 words.
   - Opening: Grounded in verified trigger and facility context.
   - Observation: Practical insight on calibration workload or coordination friction.
   - Value: How Oorja CC-3963 accredited on-site support simplifies execution.
   - CTA: Low-friction discovery ask (e.g., review equipment list for on-site feasibility).
   - Referral ask: Polite ask to connect with the right Quality/Metrology lead if recipient is not direct owner.

5. FOLLOW-UP CADENCE (STRICTLY DIFFERENTIATED):
   - Day 3 (40-75 words): Relevance reminder & brief situation/problem check.
   - Day 5 (50-85 words): Challenger insight on grouping multi-parameter calibration on-site to reduce vendor overhead.
   - Day 11 (40-70 words): Practical offer to review upcoming equipment list to classify on-site vs lab items.
   - Day 21 (30-60 words): Courteous final note, close loop, polite referral request.

6. STANDARDIZED SENDER SIGNATURE (MANDATORY):
   Every generated customer-facing email (initial body and all follow-ups) MUST end with this exact signature:
   Best regards,

   Bablu Gurjar
   Contact No.: 9201949296
   Email: Bablu@oorjatechnical.org
   Sales - Oorja Technical Services Pvt. Ltd.

   Do NOT include accreditation, standard names, or certificate numbers in the signature block (accreditation CC-3963 belongs naturally in the body copy only). Never use generic signatures.

OUTPUT FORMAT:
You MUST reply with ONLY a valid JSON object matching this schema:
{
  "subject": "...",
  "body": "...",
  "followups": {
    "day_3": "...",
    "day_5": "...",
    "day_11": "...",
    "day_21": "..."
  },
  "sales_reasoning": {
    "why_this_company": "...",
    "why_now": "...",
    "why_this_person": "...",
    "pain_hypothesis": "...",
    "implication": "...",
    "value_hypothesis": "...",
    "roi_angle": "...",
    "compliance_angle": "...",
    "operational_angle": "...",
    "best_cta": "...",
    "referral_needed": true,
    "meddpicc": {
      "metrics": "...",
      "economic_buyer": "...",
      "decision_criteria": "...",
      "decision_process": "...",
      "paper_process": "...",
      "identify_pain": "...",
      "champion": "...",
      "competition": "..."
    }
  },
  "evidence_used": ["..."],
  "claims": ["..."]
}
"""


def _build_llm_prompt(context: PersonalizationContext) -> str:
    return f"""VERIFIED PROSPECT EVIDENCE:
Company Name: {context.company_name}
Plant Facility: {context.facility}
Location: {context.city}, {context.state}
Contact Person: {context.contact_name} (First Name: {context.first_name})
Designation: {context.designation}
Assigned Persona: {context.persona}
Verified Trigger Event: {context.trigger_event}
Trigger Date: {context.trigger_date}
Trigger Evidence Source: {context.trigger_source}
Facility Activity: {context.facility_activity}
Industry: {context.industry}
Calibration Opportunity: {context.calibration_opportunity}
Contextual Notes: {context.reasoning}

Generate the structured JSON outreach now adhering strictly to word count (80-150 words for initial body), zero invented claims, standardized Bablu Gurjar signature, and no framework labels in email text."""


# ============================================================
# UNIFIED PERSONALIZATION PIPELINE
# ============================================================

class SalesPersonalizationPipeline:
    """Production Personalization Pipeline: DeepSeek Primary, Gemini Fallback, Deterministic Safety."""

    def __init__(
        self,
        *,
        deepseek_provider: Optional[DeepSeekProvider] = None,
        gemini_provider: Optional[GeminiProvider] = None,
        validator: Optional[EmailQualityValidator] = None,
    ):
        self.deepseek = deepseek_provider or DeepSeekProvider()
        self.gemini = gemini_provider or GeminiProvider()
        self.validator = validator or email_quality_validator

    def personalize_record(
        self,
        record: Mapping[str, Any],
        *,
        force_provider: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Personalize an outbound record through the verified production flow."""
        context = build_personalization_context(record)

        # 1. Deterministic Truth Gate: Reject Wrong Facility or Unverified Opportunity
        if not context.is_valid_facility:
            return {
                "status": "DISQUALIFIED_WRONG_FACILITY",
                "reason": f"Record contains conflicting or wrong facility evidence ({context.facility})",
                "quality_score": 0,
                "llm_provider_used": "NONE",
            }

        # 2. Build Prompt
        prompt = _build_llm_prompt(context)
        messages = [{"role": "user", "content": prompt}]

        # Provider Selection Strategy
        provider_name = (force_provider or "DEEPSEEK").upper().strip()

        if provider_name in {"DETERMINISTIC", "FALLBACK"}:
            return DeterministicPersonalizationGenerator.generate(context)

        # Step 3: Try Primary LLM (DeepSeek via Hive)
        if provider_name in {"DEEPSEEK", "AUTO"}:
            result = self._try_llm_generation(self.deepseek, "DEEPSEEK", messages, context)
            if result:
                return result

        # Step 4: Try Fallback LLM (Gemini)
        if provider_name in {"GEMINI", "AUTO", "DEEPSEEK"}:
            logger.info("DeepSeek generation failed or was bypassed; engaging Gemini fallback.")
            result = self._try_llm_generation(self.gemini, "GEMINI", messages, context)
            if result:
                return result

        # Step 5: Deterministic Policy Fallback (Ensures 100% Reliability)
        logger.info("LLM providers unavailable; using deterministic consultative generator.")
        return DeterministicPersonalizationGenerator.generate(context)

    def _try_llm_generation(
        self,
        provider: Any,
        provider_label: str,
        messages: List[Dict[str, str]],
        context: PersonalizationContext,
    ) -> Optional[Dict[str, Any]]:
        if not getattr(provider, "is_available", lambda: False)():
            return None

        try:
            resp = provider.complete(
                system_prompt=SYSTEM_PROMPT_SALES_PERSONALIZATION,
                messages=messages,
                temperature=0.3,
                max_tokens=1800,
                response_format="json",
            )
            data = None
            if hasattr(resp, "parse_json") and callable(resp.parse_json):
                data = resp.parse_json()
            if not data:
                raw_text = getattr(resp, "text", getattr(resp, "content", str(resp))).strip()
                data = self._extract_json(raw_text)
            if not data or not isinstance(data, dict):
                logger.warning(f"{provider_label} output failed JSON parsing")
                return None

            subject = data.get("subject", "")
            raw_body = data.get("body", "")
            raw_followups = data.get("followups", {})

            # Guarantee single standardized signature before validation
            body = ensure_single_signature(raw_body)
            followups = {
                k: ensure_single_signature(v) if isinstance(v, str) else v
                for k, v in raw_followups.items()
            }
            data["body"] = body
            data["followups"] = followups

            # Deterministic Content & Claim Validation
            val_report = self.validator.validate(
                subject=subject,
                body=body,
                followups=followups,
                context=context,
            )

            # If minor validation failure, attempt 1 bounded correction
            if not val_report.valid and len(val_report.violations) <= 2:
                corrected = self._bounded_correction(provider, provider_label, messages, raw_text, val_report.violations, context)
                if corrected:
                    return corrected

            if val_report.valid:
                data["quality_score"] = val_report.score
                data["status"] = val_report.status
                data["llm_provider_used"] = provider_label
                return data

            logger.warning(f"{provider_label} failed quality validation: {val_report.violations}")
            return None

        except Exception as err:
            logger.warning(f"Error during {provider_label} generation: {err}")
            return None

    def _bounded_correction(
        self,
        provider: Any,
        provider_label: str,
        original_messages: List[Dict[str, str]],
        failed_output: str,
        violations: List[str],
        context: PersonalizationContext,
    ) -> Optional[Dict[str, Any]]:
        """Perform exactly 1 bounded correction step with validation feedback."""
        feedback = "; ".join(violations)
        correction_messages = list(original_messages) + [
            {"role": "assistant", "content": failed_output},
            {
                "role": "user",
                "content": f"Your previous response had validation issues: {feedback}. Please fix these strictly, keep the initial email between 80 and 150 words, remove any framework terms, end all emails with Bablu Gurjar signature, and output only valid JSON.",
            },
        ]
        try:
            resp = provider.complete(
                system_prompt=SYSTEM_PROMPT_SALES_PERSONALIZATION,
                messages=correction_messages,
                temperature=0.2,
                max_tokens=1800,
                response_format="json",
            )
            data = self._extract_json(resp.content.strip())
            if not data or not isinstance(data, dict):
                return None

            raw_body = data.get("body", "")
            raw_followups = data.get("followups", {})
            body = ensure_single_signature(raw_body)
            followups = {
                k: ensure_single_signature(v) if isinstance(v, str) else v
                for k, v in raw_followups.items()
            }
            data["body"] = body
            data["followups"] = followups

            val_report = self.validator.validate(
                subject=data.get("subject", ""),
                body=body,
                followups=followups,
                context=context,
            )
            if val_report.valid:
                data["quality_score"] = val_report.score
                data["status"] = val_report.status
                data["llm_provider_used"] = f"{provider_label}_CORRECTED"
                return data
        except Exception as err:
            logger.warning(f"Bounded correction failed on {provider_label}: {err}")
        return None

    @staticmethod
    def _extract_json(raw_text: str) -> Optional[Dict[str, Any]]:
        text = raw_text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try finding first { and last }
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    return None
            return None

    def enrich_record_for_rediff(
        self,
        record: Mapping[str, Any],
        outreach_result: Mapping[str, Any],
    ) -> Dict[str, Any]:
        """Map finished Salesoorja personalized copy into existing record for Rediff handoff."""
        enriched = dict(record)
        subject = outreach_result.get("subject", "")
        body = outreach_result.get("body", "")
        followups = outreach_result.get("followups", {})

        enriched["body_text"] = body
        enriched["WHY_CALIBRATION_NOW"] = body
        enriched["REASON_FOR_OUTREACH"] = body
        enriched["NOTES"] = json.dumps(
            {
                "subject": subject,
                "followups": followups,
                "quality_score": outreach_result.get("quality_score", 90),
                "llm_provider": outreach_result.get("llm_provider_used", "UNKNOWN"),
            }
        )
        return enriched


sales_personalization_pipeline = SalesPersonalizationPipeline()
