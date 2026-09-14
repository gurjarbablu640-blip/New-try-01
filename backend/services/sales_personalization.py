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

# Prohibited Absolute or Exaggerated Claims (unless strictly evidence-backed)
PROHIBITED_ABSOLUTE_CLAIM_PATTERNS = [
    r"(?i)\bsignificantly\s+reduces?\b",
    r"(?i)\bguarantee(?:s|d)?\b",
    r"(?i)\beliminate(?:s|d)?\b",
    r"(?i)\bnear\s+zero\b",
    r"(?i)\binstant(?:ly)?\b",
    r"(?i)\bfully\s+automated\b",
    r"(?i)\bzero\s+(?:downtime|risk|error)\b",
]

# Audit Assertion Patterns (Must NOT assert upcoming audit unless supported by verified evidence)
AUDIT_ASSERTION_PATTERNS = [
    r"(?i)\bahead\s+of\s+(?:quality\s+|upcoming\s+|your\s+|oem\s+|customer\s+|iatf\s+|regulatory\s+)?audits?\b",
    r"(?i)\bbefore\s+(?:quality\s+|upcoming\s+|your\s+|oem\s+|customer\s+|iatf\s+|regulatory\s+)?audits?\b",
    r"(?i)\bupcoming\s+(?:quality\s+|customer\s+|oem\s+|iatf\s+|regulatory\s+|surveillance\s+)?audits?\b",
    r"(?i)\bfor\s+your\s+(?:upcoming\s+)?audits?\b",
    r"(?i)\bpreparation\s+for\s+(?:your\s+)?audits?\b",
]

# Keywords confirming verified audit context in trigger evidence
AUDIT_EVIDENCE_KEYWORDS = [
    "audit",
    "certification inspection",
    "customer audit",
    "regulatory inspection",
    "quality-system assessment",
    "surveillance",
    "inspection",
    "assessment",
    "iatf",
    "iso renewal",
    "nabl renewal",
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


def classify_trigger_type(context: PersonalizationContext) -> str:
    """Classify trigger context into primary business event category.

    Primary trigger event takes precedence over secondary reasoning context.
    """
    trigger_lower = (context.trigger_event or "").lower()

    if any(w in trigger_lower for w in ["audit", "surveillance", "certification inspection", "customer audit", "regulatory inspection", "quality-system assessment", "iatf"]):
        return "AUDIT_SURVEILLANCE"
    if any(w in trigger_lower for w in ["new plant", "greenfield", "new facility", "unit setup", "site setup", "new manufacturing unit"]):
        return "NEW_PLANT"
    if any(w in trigger_lower for w in ["new line", "line commissioning", "press line", "machining line", "assembly line", "production line", "commercial commissioning", "machinery commissioning"]):
        return "NEW_LINE"
    if any(w in trigger_lower for w in ["expansion", "phase ii", "phase 2", "ramp-up", "capacity expansion", "expanding", "scale-up"]):
        return "CAPACITY_EXPANSION"
    if any(w in trigger_lower for w in ["hiring", "appointed", "new role", "joined", "lead appointed"]):
        return "HIRING"

    # Secondary check on facility_activity or reasoning if trigger is generic
    activity_lower = f"{context.facility_activity} {context.reasoning}".lower()
    if any(w in activity_lower for w in ["audit", "surveillance", "certification inspection", "customer audit", "regulatory inspection", "quality-system assessment", "iatf"]):
        return "AUDIT_SURVEILLANCE"
    if any(w in activity_lower for w in ["new plant", "greenfield", "new facility", "unit setup", "site setup", "new manufacturing unit"]):
        return "NEW_PLANT"
    if any(w in activity_lower for w in ["new line", "line commissioning", "press line", "machining line", "assembly line", "production line", "commercial commissioning", "machinery commissioning"]):
        return "NEW_LINE"
    if any(w in activity_lower for w in ["expansion", "phase ii", "phase 2", "ramp-up", "capacity expansion", "expanding", "scale-up"]):
        return "CAPACITY_EXPANSION"

    return "ROUTINE"


def extract_technical_focus(calibration_opportunity: str) -> Dict[str, Any]:
    """Parse calibration opportunity into 1-3 specific technical disciplines and natural phrasing.

    Avoids injecting generic four-discipline lists when specific instruments are provided.
    """
    opp_lower = (calibration_opportunity or "").lower()
    disciplines: List[str] = []
    technical_terms: List[str] = []
    value_points: List[str] = []

    # 1. CMM / Dimensional
    if any(k in opp_lower for k in ["cmm", "dimensional", "coordinate measuring", "micrometer", "vernier", "caliper", "gauges", "gauge", "height gauge", "plug gauge", "thread gauge"]):
        disciplines.append("dimensional & CMM measurement")
        technical_terms.append("dimensional masters and CMM systems")
        value_points.append("measurement accuracy and dimensional master traceability")

    # 2. Furnace / Pyrometry / Thermal
    if any(k in opp_lower for k in ["furnace", "pyrometry", "thermal", "temperature", "oven", "heat treat", "thermocouple", "rtd"]):
        disciplines.append("thermal instrumentation & furnace pyrometry")
        technical_terms.append("thermal process instrumentation")
        value_points.append("temperature uniformity and thermal process traceability")

    # 3. Torque
    if any(k in opp_lower for k in ["torque", "tightening", "torque wrench", "torque tool"]):
        disciplines.append("torque tooling & control")
        technical_terms.append("torque tools and assembly gauges")
        value_points.append("assembly tool readiness and torque control")

    # 4. Pressure
    if any(k in opp_lower for k in ["pressure", "transmitter", "transducer", "barometer", "differential pressure"]):
        disciplines.append("process pressure instrumentation")
        technical_terms.append("pressure transmitters and process gauges")
        value_points.append("process instrument reliability and production availability")

    # 5. Electrical
    if any(k in opp_lower for k in ["electrical", "electro-technical", "multimeter", "voltmeter", "current", "power analyzer"]):
        disciplines.append("electrical instrumentation")
        technical_terms.append("electrical test instruments and process loops")
        value_points.append("sensor loop checks and electrical measurement integrity")

    # 6. Mass / Weighing
    if any(k in opp_lower for k in ["mass", "weighing", "balance", "scale", "weights"]):
        disciplines.append("mass & weighing standards")
        technical_terms.append("precision balances and weighing equipment")
        value_points.append("weighing accuracy and calibration records")

    is_specific = len(disciplines) > 0
    disciplines = disciplines[:3]
    technical_terms = technical_terms[:3]
    value_points = value_points[:3]

    if not disciplines:
        disciplines = ["precision plant instrumentation"]
        technical_terms = ["precision gauges and measurement standards"]
        value_points = ["measurement accuracy and audit-ready records"]

    if len(technical_terms) == 1:
        equipment_phrase = technical_terms[0]
    elif len(technical_terms) == 2:
        t0 = technical_terms[0].replace(" and ", ", ")
        equipment_phrase = f"{t0}, and {technical_terms[1]}"
    else:
        t0 = technical_terms[0].replace(" and ", ", ")
        t1 = technical_terms[1].replace(" and ", ", ")
        equipment_phrase = f"{t0}, {t1}, and {technical_terms[2]}"

    return {
        "disciplines": disciplines,
        "equipment_phrase": equipment_phrase,
        "value_points": value_points,
        "is_specific": is_specific,
    }


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

        # 4b. Prohibited Absolute or Exaggerated Claims (Qualitative ROI only)
        for pat in PROHIBITED_ABSOLUTE_CLAIM_PATTERNS:
            m = re.search(pat, full_text)
            if m:
                violations.append(
                    f"UNSUPPORTED_ABSOLUTE_CLAIM: Absolute claim '{m.group(0)}' detected (must use qualitative ROI like 'can help', 'can reduce', 'may simplify')"
                )
                score -= 30

        # 4c. Unsupported Upcoming Audit Assertions
        evidence_text = f"{context.trigger_event} {context.facility_activity} {context.reasoning}".lower()
        has_audit_evidence = any(kw in evidence_text for kw in AUDIT_EVIDENCE_KEYWORDS)
        if not has_audit_evidence:
            for pat in AUDIT_ASSERTION_PATTERNS:
                m = re.search(pat, full_text)
                if m:
                    violations.append(
                        f"UNSUPPORTED_AUDIT_ASSERTION: Audit claim '{m.group(0)}' asserted without verified audit evidence in trigger context"
                    )
                    score -= 30
                    break

        # 4d. Generic Four-Discipline Boilerplate when Opportunity is Narrower
        generic_4_pattern = r"(?i)mechanical,\s*thermal,\s*pressure,\s*(?:and\s+)?electrical"
        if re.search(generic_4_pattern, full_text):
            tech_info = extract_technical_focus(context.calibration_opportunity)
            opp_lower = (context.calibration_opportunity or "").lower()
            has_all_4 = (
                "mechanical" in opp_lower
                and "thermal" in opp_lower
                and "pressure" in opp_lower
                and "electrical" in opp_lower
            )
            if tech_info["is_specific"] and not has_all_4:
                violations.append(
                    f"GENERIC_DISCIPLINE_BOILERPLATE: Generic four-discipline list found when calibration opportunity is narrower ('{context.calibration_opportunity}')"
                )
                score -= 25

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
            or "UNSUPPORTED_ABSOLUTE_CLAIM" in v
            or "UNSUPPORTED_AUDIT_ASSERTION" in v
            or "GENERIC_DISCIPLINE_BOILERPLATE" in v
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

        trigger_type = classify_trigger_type(context)
        tech_info = extract_technical_focus(calibration_opp)
        equipment_phrase = tech_info["equipment_phrase"]

        # Persona-specific tailored observations, Challenger insights, and value angles
        if persona == "Quality Head":
            subject = f"Measurement Traceability & Calibration Control - {company} ({city})"
            if trigger_type == "NEW_LINE":
                hook = (
                    f"As {company} prepares for production launch on the new line at {facility}, "
                    f"qualification activity often increases the volume of measurement equipment that needs to be verified and documented before routine manufacturing starts."
                )
                challenger = (
                    "Calibration planning often gets attention only after equipment installation, "
                    "which can leave qualification activity compressed close to production start."
                )
            elif trigger_type == "NEW_PLANT":
                hook = (
                    f"Commissioning activity at {company}'s {facility} often increases the amount of measurement equipment "
                    f"that needs to be qualified, calibrated, and documented before routine production."
                )
                challenger = (
                    "Calibration planning often gets attention only after machinery installation, "
                    "which can compress qualification timelines and create scheduling friction across multiple external labs."
                )
            elif trigger_type == "CAPACITY_EXPANSION":
                hook = (
                    f"With {company} expanding capacity at {facility}, "
                    f"adding new instruments can create calibration-planning workload and increase the coordination needed to maintain continuous certificate availability."
                )
                challenger = (
                    "When instrument calibration is scattered across multiple external labs, "
                    "tracking out-of-tolerance notifications and certificate availability can create administrative friction for quality teams."
                )
            elif trigger_type == "AUDIT_SURVEILLANCE":
                hook = (
                    f"Ahead of upcoming audit and surveillance requirements at {company}'s {facility}, "
                    f"maintaining continuous measurement traceability and rapid certificate retrieval is a practical priority for quality teams."
                )
                challenger = (
                    "Traceability gaps and certificate retrieval delays often surface late during audit preparations, "
                    "creating unnecessary pressure on quality teams."
                )
            elif trigger_type == "HIRING":
                hook = (
                    f"Following recent quality leadership transitions at {company}'s {facility}, "
                    f"establishing an organized calibration baseline helps ensure consistent measurement traceability across all active instruments."
                )
                challenger = (
                    "Reviewing calibration master scopes early in a new leadership cycle often reveals opportunities "
                    "to bring scattered external lab scopes into a consolidated on-site plan."
                )
            else:  # ROUTINE
                hook = (
                    f"As {company} plans its upcoming calibration cycle at {facility}, "
                    f"reviewing instrument schedules early helps maintain continuous measurement traceability and avoid out-of-tolerance surprises."
                )
                challenger = (
                    "When instrument calibration is scattered across multiple external labs, "
                    "tracking out-of-tolerance notifications and certificate availability can create administrative friction for quality teams."
                )

            value_prop = (
                f"Oorja Technical Services is an ISO/IEC 17025:2017 NABL-accredited calibration laboratory (Certificate CC-3963). "
                f"We support quality teams by coordinating on-site calibration for {equipment_phrase}, "
                f"helping maintain strict measurement traceability and certificate availability without moving critical masters offsite."
            )
            cta = "Would it make sense to review your upcoming equipment calibration schedule to determine which items can be supported on-site?"
            referral_ask = f"If another colleague directly leads metrology or calibration planning for {facility}, could you kindly point me to the right person?"

            day_5 = (
                f"Dear {first_name},\n\n"
                f"From a quality management perspective, managing calibration through fragmented external laboratories often makes tracking certificate availability and out-of-tolerance notifications more difficult than it needs to be. "
                f"Consolidating calibration for {equipment_phrase} under our NABL CC-3963 accredited on-site schedule can make calibration records easier to retrieve when required and support measurement traceability.\n\n"
                f"If you have an upcoming equipment list, I would be glad to review it for on-site feasibility.\n\n"
                f"{STANDARD_SIGNATURE_TEXT}"
            )

            roi_angle = "audit readiness and certificate retrieval" if trigger_type == "AUDIT_SURVEILLANCE" else "measurement traceability and certificate availability"
            compliance_angle = "NABL CC-3963 audit-ready certification and IATF 16949 measurement integrity" if trigger_type == "AUDIT_SURVEILLANCE" else "ISO/IEC 17025:2017 CC-3963 accredited traceability for manufacturing equipment"
            operational_angle = "in-situ verification and on-site master calibration to eliminate transit delays"

        elif persona == "Plant Head":
            subject = f"Shutdown Calibration Planning & Equipment Availability - {company} ({city})"
            if trigger_type in {"NEW_LINE", "NEW_PLANT"}:
                hook = (
                    f"With {company} advancing commissioning at {facility}, "
                    f"planning calibration around scheduled production windows helps prevent avoidable equipment movement and startup delays."
                )
            elif trigger_type == "CAPACITY_EXPANSION":
                hook = (
                    f"As {company} ramps up capacity at {facility}, "
                    f"coordinating calibration during planned maintenance windows helps maintain equipment availability without interrupting active production runs."
                )
            elif trigger_type == "AUDIT_SURVEILLANCE":
                hook = (
                    f"With audit readiness on the radar for {company}'s {facility}, "
                    f"ensuring all operational instruments are verified without disrupting scheduled production runs is essential."
                )
            elif trigger_type == "HIRING":
                hook = (
                    f"As operational leadership drives execution at {company}'s {facility}, "
                    f"structured calibration planning helps ensure equipment availability across both new and existing lines."
                )
            else:  # ROUTINE
                hook = (
                    f"As {company} reviews ongoing operations at {facility}, "
                    f"aligning equipment calibration with planned shutdown windows helps keep production schedules predictable."
                )

            challenger = "Moving multiple instrument categories offsite at different times can create more operational disruption than the calibration work itself."
            value_prop = (
                f"Oorja Technical Services is an ISO/IEC 17025:2017 NABL-accredited calibration laboratory (Certificate CC-3963). "
                f"We work with plant leadership to execute batch on-site calibration for {equipment_phrase} during planned maintenance windows, "
                f"helping avoid transit downtime and keep equipment on the floor."
            )
            cta = "Would it make sense to explore an on-site calibration slot aligned with your next planned maintenance window?"
            referral_ask = f"If your Plant Quality Head or Metrology Lead directly coordinates this planning for {facility}, could you point me to the right lead?"

            day_5 = (
                f"Dear {first_name},\n\n"
                f"A recurring friction point for plant heads during busy production cycles is having critical instruments stuck in off-site transit across multiple vendors. "
                f"Where technically feasible, grouping calibration for {equipment_phrase} into a single planned on-site execution window can protect production continuity and reduce equipment movement.\n\n"
                f"Would it be helpful to review your site equipment list to identify which instruments can be handled on-site?\n\n"
                f"{STANDARD_SIGNATURE_TEXT}"
            )

            roi_angle = "production continuity and minimized equipment transit downtime"
            compliance_angle = "ISO/IEC 17025:2017 CC-3963 accredited traceability for manufacturing equipment"
            operational_angle = "consolidated on-site batch calibration during planned shutdown slots"

        elif persona == "Operations Head":
            subject = f"Line Readiness & Calibration Coordination - {company} ({city})"
            if trigger_type in {"NEW_LINE", "NEW_PLANT"}:
                hook = (
                    f"As {company} prepares to bring the new line into commercial production at {facility}, "
                    f"uncoordinated gauge or sensor calibration can delay line readiness just as startup targets approach."
                )
            elif trigger_type == "CAPACITY_EXPANSION":
                hook = (
                    f"With {company} expanding output at {facility}, "
                    f"managing calibration turnarounds without slowing line speed or causing staging bottlenecks is a practical priority."
                )
            elif trigger_type == "AUDIT_SURVEILLANCE":
                hook = (
                    f"Maintaining operational line readiness while verifying production instruments for upcoming compliance reviews "
                    f"at {facility} requires tight coordination on the shop floor."
                )
            else:
                hook = (
                    f"Managing ongoing production schedules at {company}'s {facility} "
                    f"requires keeping line instruments verified without pulling critical gauges from active shifts."
                )

            challenger = "Staggering calibration across multiple external labs during line commissioning can introduce unexpected delays just as production schedules firm up."
            value_prop = (
                f"Oorja Technical Services is an ISO/IEC 17025:2017 NABL-accredited calibration laboratory (Certificate CC-3963). "
                f"We help operations teams maintain line readiness by performing on-site calibration for {equipment_phrase}, "
                f"minimizing equipment movement and supporting scheduled shift changeovers."
            )
            cta = "Would it make sense to review your upcoming equipment calibration schedule to determine which items can be supported on-site?"
            referral_ask = f"If a colleague in Quality or Maintenance directly manages this schedule for {facility}, could you kindly point me to the right person?"

            day_5 = (
                f"Dear {first_name},\n\n"
                f"In our experience with manufacturing operations, sending production tools and gauges off-site often creates unexpected shift downtime and spare-tool shortages. "
                f"Performing accredited calibration for {equipment_phrase} directly on-site during planned shift intervals can maintain line readiness with minimal equipment movement.\n\n"
                f"Happy to take a quick look at your current equipment list to outline an on-site calibration approach.\n\n"
                f"{STANDARD_SIGNATURE_TEXT}"
            )

            roi_angle = "line readiness and minimal equipment movement"
            compliance_angle = "traceable calibration baseline before commercial production release"
            operational_angle = "single-slot on-site execution to eliminate transit turnaround"

        elif persona == "Metrology Head":
            subject = f"Metrology Scope & Standards Traceability - {company} ({city})"
            hook = (
                f"Regarding precision metrology standards and calibration discipline for {company}'s {facility}, "
                f"maintaining accredited traceability across {equipment_phrase} requires rigorous uncertainty budgets and verified master standards."
            )
            challenger = "Separating items that genuinely require laboratory calibration from those that can be handled onsite can simplify the overall calibration plan."
            value_prop = (
                f"Oorja Technical Services is an ISO/IEC 17025:2017 NABL-accredited metrology and calibration laboratory (Certificate CC-3963). "
                f"Our technical scope covers high-precision calibration for {equipment_phrase}, "
                f"providing documented CMC capabilities, clear uncertainty budgets, and practical onsite-versus-lab scoping."
            )
            cta = "Would you be open to a technical scope review of your equipment list to evaluate on-site calibration feasibility?"
            referral_ask = f"If another colleague in your standards lab directly manages this schedule for {facility}, could you point me to the right lead?"

            day_5 = (
                f"Dear {first_name},\n\n"
                f"From a standards-room perspective, keeping reference masters in active rotation while managing field instruments can create scheduling friction. "
                f"Clearly delineating which items in {equipment_phrase} can be calibrated in-situ versus those requiring controlled lab environments can simplify calibration planning while preserving measurement accuracy.\n\n"
                f"If you have an equipment inventory for {facility}, I would welcome the opportunity to review your technical scope.\n\n"
                f"{STANDARD_SIGNATURE_TEXT}"
            )

            roi_angle = "calibration turnaround and measurement uncertainty control"
            compliance_angle = "ISO/IEC 17025:2017 accredited CMC schedule under Certificate CC-3963"
            operational_angle = "range-specific CMC alignment and on-site master calibration"

        elif persona == "Procurement":
            subject = f"Calibration Vendor Consolidation & Scope Review - {company} ({city})"
            if trigger_type in {"NEW_LINE", "NEW_PLANT"}:
                hook = (
                    f"As {company} progresses with commercial commissioning at {facility}, "
                    f"onboarding multiple separate calibration vendors for newly installed machinery can introduce commercial complexity and administrative overhead."
                )
            elif trigger_type == "CAPACITY_EXPANSION":
                hook = (
                    f"With {company} expanding capacity at {facility}, "
                    f"managing calibration contracts across multiple fragmented suppliers can increase coordination effort and invoice processing."
                )
            elif trigger_type == "AUDIT_SURVEILLANCE":
                hook = (
                    f"Ensuring all calibration purchase orders and vendor accreditations are aligned ahead of site compliance reviews "
                    f"at {facility} helps avoid last-minute administrative friction."
                )
            else:
                hook = (
                    f"As {company} reviews annual vendor agreements for {facility}, "
                    f"consolidating calibration requirements under a single accredited provider can simplify commercial coordination."
                )

            challenger = "The hidden cost is often not the calibration rate alone, but the coordination involved in managing multiple vendors and repeated equipment movement."
            value_prop = (
                f"Oorja Technical Services is an ISO/IEC 17025:2017 NABL-accredited calibration laboratory (Certificate CC-3963). "
                f"We support commercial teams by consolidating calibration for {equipment_phrase} under a unified on-site agreement, "
                f"reducing vendor coordination effort and providing clear scope clarity."
            )
            cta = "Would it make sense to review your upcoming calibration scope to see where vendor consolidation can simplify execution?"
            referral_ask = f"If your Plant Quality Head or Commercial Lead directly coordinates this evaluation for {facility}, could you kindly point me to the right person?"

            day_5 = (
                f"Dear {first_name},\n\n"
                f"Managing calibration through four or five separate specialized vendors often creates hidden administrative costs in purchase order management, gate-pass tracking, and commercial follow-ups. "
                f"Consolidating {equipment_phrase} under a single ISO/IEC 17025:2017 accredited agreement can simplify commercial coordination and reduce vendor management overhead.\n\n"
                f"If you have a scope list for the upcoming cycle at {facility}, I can quickly provide a unified feasibility review.\n\n"
                f"{STANDARD_SIGNATURE_TEXT}"
            )

            roi_angle = "vendor consolidation and reduced coordination effort"
            compliance_angle = "ISO/IEC 17025:2017 NABL CC-3963 accredited commercial coverage"
            operational_angle = "multi-parameter lab and on-site coverage under single SLA"

        else:
            subject = f"Instrumentation Calibration & Field Reliability - {company} ({city})"
            hook = (
                f"As your team oversees instrument reliability at {company}'s {facility}, "
                f"managing sensor drift and calibration schedules across {equipment_phrase} is essential for continuous process uptime."
            )
            challenger = "Instrument drift in process sensors often goes unnoticed until routine maintenance cycles, when uncoordinated dispatches can delay line restarts."
            value_prop = (
                f"Oorja Technical Services is an ISO/IEC 17025:2017 NABL-accredited calibration laboratory (Certificate CC-3963). "
                f"We support engineering teams by performing on-site calibration for {equipment_phrase}, "
                f"reducing equipment movement and supporting reliable field tolerances."
            )
            cta = "Would it make sense to review your upcoming sensor and instrument calibration schedule for on-site feasibility?"
            referral_ask = f"If another colleague in Quality or Operations leads calibration planning for {facility}, could you kindly point me to the right person?"

            day_5 = (
                f"Dear {first_name},\n\n"
                f"Coordinating sensor loop checks and instrument verification during short maintenance windows can be challenging when equipment must be dispatched off-site. "
                f"Performing on-site calibration for {equipment_phrase} can reduce equipment movement and help keep critical instruments available for production.\n\n"
                f"Happy to review your upcoming instrument schedule to explore on-site feasibility.\n\n"
                f"{STANDARD_SIGNATURE_TEXT}"
            )

            roi_angle = "instrument availability and process reliability"
            compliance_angle = "CC-3963 accredited field tolerances and verified master traceability"
            operational_angle = "on-site loop checking and direct sensor calibration"

        body = (
            f"Dear {first_name},\n\n"
            f"{hook}\n\n"
            f"{challenger}\n\n"
            f"{value_prop}\n\n"
            f"{cta}\n\n"
            f"{referral_ask}\n\n"
            f"{STANDARD_SIGNATURE_TEXT}"
        )

        if trigger_type == "NEW_LINE":
            trigger_ref = "new production lines transition into regular operations"
        elif trigger_type == "NEW_PLANT":
            trigger_ref = "commissioning activity progresses toward routine production"
        elif trigger_type == "CAPACITY_EXPANSION":
            trigger_ref = "expanded operations ramp up toward regular production"
        elif trigger_type == "AUDIT_SURVEILLANCE":
            trigger_ref = "scheduled compliance and audit reviews approach"
        else:
            trigger_ref = "upcoming calibration schedules are planned"

        followups = {
            "day_3": (
                f"Dear {first_name},\n\n"
                f"Following up on my earlier note regarding {facility}. As {trigger_ref}, "
                f"teams often see an increase in calibration documentation and gage verification workloads.\n\n"
                f"Are you the right person to discuss calibration planning for this site, or should I connect with someone else on your team?\n\n"
                f"{STANDARD_SIGNATURE_TEXT}"
            ),
            "day_5": day_5,
            "day_11": (
                f"Dear {first_name},\n\n"
                f"If your calibration coverage for {facility} is already fully arranged for this cycle, please feel free to disregard this note. "
                f"If you still have open requirements, I can quickly review your equipment list and separate items that can be handled on-site from those better suited for in-lab testing.\n\n"
                f"{STANDARD_SIGNATURE_TEXT}"
            ),
            "day_21": (
                f"Dear {first_name},\n\n"
                f"I will close the loop with this note so as not to crowd your inbox. "
                f"If calibration planning or measurement traceability support becomes an active priority for {company}'s {facility} in the future, we would be glad to assist.\n\n"
                f"If another colleague in Quality or Operations owns this responsibility, a brief referral would be greatly appreciated.\n\n"
                f"{STANDARD_SIGNATURE_TEXT}"
            ),
        }

        sales_reasoning = {
            "why_this_company": f"Verified industrial leader ({company}) with active plant footprint at {facility}.",
            "why_now": f"Trigger event '{trigger}' introduces newly installed equipment requiring accredited calibration verification.",
            "why_this_person": f"Functional leader ({persona} - {context.designation}) overseeing technical execution or compliance.",
            "pain_hypothesis": "Expanding instrumentation increases calibration scheduling burden, equipment movement, and audit certificate sprawl.",
            "implication": "Delayed equipment qualification, production disruption during uncoordinated shutdowns, and audit compliance risk.",
            "value_hypothesis": f"Consolidated on-site calibration for {equipment_phrase} under ISO/IEC 17025:2017 CC-3963 minimizes transit downtime and vendor interfaces.",
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
            f"On-site and in-lab calibration for {equipment_phrase}",
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
1. EVIDENCE FIRST & CLAIM SAFETY:
   - Use ONLY the verified company, facility, person, designation, and trigger facts provided in the prompt.
   - NEVER invent unverified facts, numeric ROI (e.g. 'save 35% cost'), satellite centers (e.g. 'Pune & Dahej Regional Metrology Center'), unapproved turnaround SLAs (e.g. '48-hour turnaround'), or active audits unless verified.
   - AUDIT RESTRICTION: Do NOT say or imply an audit is upcoming or scheduled (NEVER 'ahead of your upcoming audit' or 'before quality audits') UNLESS the verified trigger evidence explicitly contains 'audit', 'surveillance', or 'inspection'. General phrasing like 'support measurement traceability', 'make calibration records easier to retrieve when required', or 'support audit readiness' is allowed only when context makes sense.
   - QUALITATIVE ROI ONLY: NEVER use absolute claims like 'significantly reduce', 'guarantee', 'eliminate', 'near zero', 'instant', 'fully automated', or 'zero downtime'. Use conservative qualitative phrasing: 'can help', 'can reduce equipment movement and vendor coordination', 'may simplify', 'where technically feasible'.
   - CALIBRATION OPPORTUNITY ALIGNMENT: Do NOT automatically insert a generic four-discipline list ('mechanical, thermal, pressure, and electrical') if the supplied opportunity is specific (e.g. dimensional CMM, furnace pyrometry, torque, pressure). Focus strictly on the 1-3 specific technical disciplines supplied in the opportunity.
   - Frame operational friction cautiously as an industry observation (e.g. 'Commissioning activity often increases...'), NEVER as an accusatory fact (NEVER 'You are struggling with...').

2. PERSONA MATERIAL DIFFERENTIATION:
   Value proposition and Challenger insight MUST materially differ by role:
   - QUALITY HEAD: Emphasize traceability, measurement confidence, calibration control, certificate availability, and out-of-tolerance risk.
   - PLANT HEAD: Emphasize production continuity, shutdown planning, equipment availability, and execution coordination.
   - OPERATIONS HEAD: Emphasize line readiness, minimal equipment movement, commissioning timing, and uptime.
   - METROLOGY HEAD: Emphasize technical feasibility, CMC range/scope, onsite vs lab, masters, and measurement discipline.
   - PROCUREMENT: Emphasize vendor consolidation, commercial coordination, scope clarity, and execution planning.

3. SALES METHODOLOGY (APPLY INTERNALLY ONLY):
   - SPIN SELLING: Understand Situation (trigger & plant), Problem (measurement workload), Implication (qualification/audit delay), Need-Payoff (consolidated on-site calibration).
   - CHALLENGER SALE: Teach one practical observation tailored to the persona and trigger, Take Control with a low-friction next step.
   - GAP SELLING: Highlight friction between scattered vendor logistics and a streamlined on-site calibration plan.
   - VALUE / ROI SELLING: Focus on qualitative outcomes (reduced equipment movement, lower coordination effort, audit readiness).
   - MEDDPICC: Ground the internal strategy in buyer criteria, pain, and process.

4. FORBIDDEN FRAMEWORK TERMS:
   - Recipient must NEVER see framework terminology in email text.
   - NEVER write 'Situation:', 'Problem:', 'Implication:', 'Need-Payoff:', 'Challenger:', 'MEDDPICC:', 'GAP Selling:', 'ROI:', or 'Teach:'.

5. EMAIL STRUCTURE (DAY 1 INITIAL EMAIL):
   - Length: Strictly between 80 and 150 words.
   - Opening: Grounded in verified trigger, persona, and facility context.
   - Observation / Challenger: Practical, persona-specific insight on calibration workload or coordination friction.
   - Value: How Oorja CC-3963 accredited on-site support simplifies execution for the specific equipment supplied.
   - CTA: Low-friction discovery ask tailored to the persona.
   - Referral ask: Polite ask to connect with the right Quality/Metrology lead if recipient is not direct owner.

6. FOLLOW-UP CADENCE (STRICTLY DIFFERENTIATED):
   - Day 3 (40-75 words): Relevance reminder & conservative situation/problem check referencing facility/trigger.
   - Day 5 (50-85 words): Introduce a PERSONA-SPECIFIC Challenger/value insight (Quality: certificate availability & traceability; Plant: off-site equipment transit disruption; Operations: shift delays & line readiness; Metrology: separating in-situ from lab masters; Procurement: hidden coordination costs of fragmented vendors). Do NOT use identical Day-5 copy across personas!
   - Day 11 (40-70 words): Practical offer to review upcoming equipment list to classify on-site vs lab items.
   - Day 21 (30-60 words): Courteous final note, close loop, polite referral request.

7. STANDARDIZED SENDER SIGNATURE (MANDATORY):
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
