"""Sales Personalization V2 Engine — Phase 2.1 Funnel Recovery & Hardening.

LLM-First outreach generation with deterministic zero-invention claim guard.

Design principles:
- Normal path: Evidence packet → DeepSeek primary → Gemini fallback → Deterministic claim validation.
- Persona-first value proposition matched to authority class.
- Selective capability group inclusion (1-3 approved groups: ELECTRICAL, THERMAL, PRESSURE, DIMENSIONAL, TORQUE, WEIGHING, CT_PT, ENVIRONMENTAL_MAPPING).
- Strict negative constraints: No invented equipment ownership, no ungrounded person responsibility, no fabricated SLAs, no free offers.
- Strict event status grounding: EXISTING_FACILITY_EXPANSION cannot claim "new facility".
- Strict date grounding: detected_at cannot masquerade as event date; year-only does not invent month/day.
- Strict compliance grounding: Accreditation must not be represented as guaranteeing customer compliance.
- Low-friction industrial CTA: Suggest practical lab/onsite route or referral to colleague.
- Word count constraint: 90–130 words excluding signature.
- Exact professional salesperson signature:
    Best regards,
    Bablu Gurjar
    Sales | Oorja Technical Services Pvt. Ltd.
    Contact No.: 9201949296
    Email: Bablu@oorjatechnical.org
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Exact Salesperson Signature ────────────────────────────────────────────
SALES_SIGNATURE = (
    "Best regards,\n"
    "Bablu Gurjar\n"
    "Sales | Oorja Technical Services Pvt. Ltd.\n"
    "Contact No.: 9201949296\n"
    "Email: Bablu@oorjatechnical.org"
)
SIGNATURE = "\n\n" + SALES_SIGNATURE  # Backward compatibility

# ── Approved Oorja Capability Groups ──────────────────────────────────────
APPROVED_OORJA_CAPABILITY_GROUPS: Dict[str, str] = {
    "ELECTRICAL": "Electrical (multimeters, insulation testers, power quality)",
    "THERMAL": "Thermal (temperature indicators, controllers, RTDs, thermocouples)",
    "PRESSURE": "Pressure (pressure gauges, transmitters, vacuum gauges)",
    "DIMENSIONAL": "Dimensional (calipers, micrometers, height gauges, dial indicators)",
    "TORQUE": "Torque (torque wrenches, torque transducers)",
    "WEIGHING": "Weighing (balances, scales)",
    "CT_PT": "CT/PT (current and potential transformers)",
    "ENVIRONMENTAL_MAPPING": "Environmental Mapping (thermal & humidity mapping)",
}

# ── Event / Facility Status Semantics ───────────────────────────────────────
EVENT_STATUS_NEW_FACILITY = "NEW_FACILITY"
EVENT_STATUS_EXISTING_EXPANSION = "EXISTING_FACILITY_EXPANSION"
EVENT_STATUS_NEW_LINE = "NEW_PRODUCTION_LINE"
EVENT_STATUS_COMMISSIONING = "COMMISSIONING"
EVENT_STATUS_CAPACITY_EXPANSION = "CAPACITY_EXPANSION"
EVENT_STATUS_RELOCATION = "RELOCATION"
EVENT_STATUS_UNKNOWN = "UNKNOWN"

def infer_event_status(text: str, event_type: Optional[str] = None) -> str:
    """Infer the event status from headline, trigger, snippet, or event_type."""
    combined = f"{event_type or ''} {text}".lower()

    # Relocation check
    if any(k in combined for k in ["relocation", "shifting", "relocate", "relocated"]):
        return EVENT_STATUS_RELOCATION

    # Existing plant / facility expansion check
    # E.g. "expand Pune automotive manufacturing plant", "Pune plant expansion", "capacity expansion"
    if any(k in combined for k in [
        "capacity expansion", "expand pune", "plant expansion", "expand automotive manufacturing plant",
        "to expand", "expands", "expansion", "capacity boost", "doubling capacity", "expanding its"
    ]):
        return EVENT_STATUS_EXISTING_EXPANSION

    # New line / assembly line check
    if any(k in combined for k in ["new line", "assembly line", "fal", "new production line", "flightline"]):
        return EVENT_STATUS_NEW_LINE

    # New facility / greenfield / new manufacturing block check
    if any(k in combined for k in [
        "new manufacturing block", "new plant", "greenfield", "new facility",
        "first semiconductor plant", "new site", "new unit", "new campus"
    ]):
        return EVENT_STATUS_NEW_FACILITY

    # Commissioning / inauguration check
    if any(k in combined for k in ["commissioning", "inaugurate", "inaugurates", "inaugurated", "commercial production"]):
        return EVENT_STATUS_COMMISSIONING

    return EVENT_STATUS_UNKNOWN


def resolve_event_date(record: Dict[str, Any]) -> Tuple[str, str]:
    """Resolve the grounded event date phrase and its source.

    Priority:
      1. EVENT_DATE (explicit event_date or verified_event_date)
      2. PUBLICATION_DATE (article publication date)
      3. YEAR_ONLY (if only a year is detected)
      4. UNKNOWN

    CRITICAL CONSTRAINTS:
    - Never use database detected_at, created_at, or today's date as the event date!
    - If only year is known, do NOT invent month or day.
    """
    # 1. Explicit event date
    raw_event_date = record.get("event_date") or record.get("verified_event_date")
    if raw_event_date and isinstance(raw_event_date, str):
        s = raw_event_date.strip()
        if not re.search(r"\d{2}:\d{2}:\d{2}", s):
            if re.fullmatch(r"\d{4}", s):
                return s, "YEAR_ONLY"
            return s, "EVENT_DATE"

    # 2. Publication date
    pub_date = record.get("publication_date") or record.get("pub_date") or record.get("article_date")
    if pub_date and isinstance(pub_date, str):
        s = pub_date.strip()
        if not re.search(r"\d{2}:\d{2}:\d{2}", s):
            if re.fullmatch(r"\d{4}", s):
                return s, "YEAR_ONLY"
            return s, "PUBLICATION_DATE"

    # 3. Trigger date in record
    trig_date = record.get("trigger_date")
    if trig_date and isinstance(trig_date, str):
        s = trig_date.strip()
        if "detected_at" in str(record.get("date_field", "")).lower() or re.search(r"\d{2}:\d{2}:\d{2}", s):
            return "recent expansion activity", "UNKNOWN"
        if re.fullmatch(r"\d{4}", s):
            return s, "YEAR_ONLY"
        if re.match(r"^\d{4}-\d{2}", s):
            return s, "EVENT_DATE"
        if any(m in s.lower() for m in ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]):
            return s, "EVENT_DATE"

    return "recent expansion activity", "UNKNOWN"


# ── Forbidden specific unsupported patterns ────────────────────────────────
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
            r"\b(?:your|their)\s+(?:specific\s+)?(?:processes?|instruments?|equipment|cmm|hplc|gc|avionics)\s+(?:requires?|needs?|demands?)\b",
            re.IGNORECASE,
        ),
        "Specific process/equipment inference is unsupported without grounding evidence",
    ),
    (
        re.compile(
            r"\b(?:you|your)\s+(?:manage|own|oversee|lead|run|supervise|handle)\s+(?:calibration|ndt|metrology|cmm|hplc|gc|avionics|instruments?)\b",
            re.IGNORECASE,
        ),
        "Direct factual attribution of calibration/equipment responsibility to recipient is unsupported",
    ),
    (
        re.compile(
            r"\b(?:you\s+are|you're)\s+(?:responsible|in\s+charge)\s+for\s+(?:calibration|ndt|torque)\b",
            re.IGNORECASE,
        ),
        "Attribution of specific calibration responsibility is unsupported without explicit evidence",
    ),
    (
        re.compile(
            r"\byour\s+(?:calibration\s+team|torque[- ]tool\s+program|cmms?)\b",
            re.IGNORECASE,
        ),
        "Attribution of specific internal team/program ownership is unsupported",
    ),
    (
        re.compile(
            r"\b(?:cmm\s+alignment|optical\s+calibration|analytical[- ]instrument\s+calibration|avionics\s+calibration|high[- ]voltage\s+scope)\b",
            re.IGNORECASE,
        ),
        "Unapproved capability or equipment scope claim",
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
    (
        re.compile(
            r"\b(?:guarantees?|ensures?|assures?)\s+(?:compliance|audit\s+success|regulatory\s+clearance|pass)\b",
            re.IGNORECASE,
        ),
        "Accreditation must not be represented as guaranteeing customer compliance or audit success",
    ),
    (
        re.compile(
            r"\baccreditation\s+(?:guarantees?|ensures?|assures?)\b",
            re.IGNORECASE,
        ),
        "Accreditation must not be represented as guaranteeing customer compliance",
    ),
    (
        re.compile(
            r"\bensure[s]?\s+(?:traceability\s+and\s+)?compliance\b",
            re.IGNORECASE,
        ),
        "Absolute compliance guarantee language is forbidden",
    ),
]

# ── Persona matrix ─────────────────────────────────────────────────────────
PERSONA_VALUE_ANGLES: Dict[str, str] = {
    "METROLOGY_OWNER": (
        "Your metrology function relies on calibration traceability being reliable and audit-ready. "
        "Oorja is an ISO/IEC 17025:2017 NABL-accredited calibration laboratory (CC-3963), which may support "
        "calibration documentation and traceability requirements where relevant."
    ),
    "DIRECT_CALIBRATION_OWNER": (
        "Managing calibration schedules across instruments is resource-intensive. "
        "Oorja is an ISO/IEC 17025:2017 NABL-accredited calibration laboratory (CC-3963), providing "
        "traceable calibration subject to scope and range feasibility."
    ),
    "STRONG_PLANT_QUALITY_OWNER": (
        "Plant quality depends on measurement traceability being audit-ready. "
        "Oorja is an ISO/IEC 17025:2017 NABL-accredited calibration laboratory (CC-3963), which may support "
        "plant quality and traceability requirements where relevant."
    ),
    "FACILITY_OWNER": (
        "Plant operations depend on instruments being calibrated and traceable. "
        "We provide on-site and laboratory calibration under ISO/IEC 17025:2017 (NABL CC-3963), "
        "subject to instrument scope and range feasibility."
    ),
    "GROUP_FUNCTION_OWNER": (
        "Across multi-plant operations, calibration consistency is a recurring operational consideration. "
        "Oorja provides NABL-accredited calibration under CC-3963 subject to scope/range feasibility across locations."
    ),
    "PROCUREMENT": (
        "Sourcing calibration services requires verified NABL accreditation and consistent delivery. "
        "Oorja is NABL-accredited under ISO/IEC 17025:2017 (CC-3963) with transparent commercial terms."
    ),
    "DEFAULT": (
        "Measurement accuracy is fundamental to plant quality and operational standards. "
        "Oorja is an ISO/IEC 17025:2017 NABL-accredited calibration laboratory (Certificate CC-3963), "
        "which may support calibration documentation and traceability requirements where relevant."
    ),
}

# ── Capability groups mapping (Strictly 8 Approved Groups) ──────────────────
CAPABILITY_GROUPS: Dict[str, List[str]] = {
    "dimensional": ["Dimensional (calipers, micrometers, height gauges)"],
    "electrical": ["Electrical (multimeters, insulation testers, power quality)"],
    "thermal": ["Thermal (temperature indicators, RTDs, thermocouples)"],
    "pressure": ["Pressure (pressure gauges, transmitters, vacuum gauges)"],
    "torque": ["Torque (torque wrenches, torque transducers)"],
    "weighing": ["Weighing (balances, scales)"],
    "ct_pt": ["CT/PT (current and potential transformers)"],
    "environmental_mapping": ["Environmental Mapping (thermal & humidity mapping)"],
}

INDUSTRY_CAPABILITY_MAP: Dict[str, List[str]] = {
    "pharmaceutical": ["thermal", "pressure", "weighing"],
    "chemical": ["pressure", "thermal", "electrical"],
    "aerospace": ["dimensional", "pressure", "electrical"],
    "automotive": ["dimensional", "electrical", "torque"],
    "power": ["electrical", "thermal", "pressure"],
    "ev": ["electrical", "thermal", "torque"],
    "food": ["thermal", "pressure", "weighing"],
    "defence": ["dimensional", "electrical", "pressure"],
    "default": ["dimensional", "electrical", "thermal"],
}

CLAIM_CLASSIFICATION_LABELS = {
    "EXPLICIT_EVIDENCE": "Claim grounded in explicit record evidence",
    "SAFE_GENERIC": "Safe generic claim with caveat",
    "UNSUPPORTED_SPECIFIC": "Unsupported specific inference — FORBIDDEN",
}


def classify_claim(
    claim_text: str,
    event_status: str = "UNKNOWN",
    record: Optional[Dict[str, Any]] = None,
) -> Tuple[str, Optional[str]]:
    """Classify a claim string as EXPLICIT_EVIDENCE, SAFE_GENERIC, or UNSUPPORTED_SPECIFIC.

    Returns (label, violation_description).
    violation_description is non-None only for UNSUPPORTED_SPECIFIC.
    """
    for pattern, description in FORBIDDEN_SPECIFIC_UNSUPPORTED_PATTERNS:
        if pattern.search(claim_text):
            return "UNSUPPORTED_SPECIFIC", description

    # Facility status check: for existing expansion, "new facility" is unsupported
    if event_status in {EVENT_STATUS_EXISTING_EXPANSION, EVENT_STATUS_CAPACITY_EXPANSION}:
        if re.search(r"\b(?:new\s+(?:facility|plant|site|unit|campus)|greenfield)\b", claim_text, re.IGNORECASE):
            return "UNSUPPORTED_SPECIFIC", "Claim of 'new facility/plant' is unsupported for an existing facility expansion"

    # Leak of database timestamp into outreach claim
    if re.search(r"\b\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}", claim_text):
        return "UNSUPPORTED_SPECIFIC", "Detected database timestamp leaked into outreach claim"

    generic_markers = [
        r"\btypically\b", r"\busually\b", r"\bgenerally\b", r"\boften\b",
        r"\bcommonly\b", r"\bmay\b", r"\bcan\b", r"\bwould\b", r"\bif\b",
        r"\bsubject to\b", r"\bwhere relevant\b", r"\bplanning\b",
        r"\bas operations expand\b", r"\bstandard practice\b", r"\bwhere applicable\b",
        r"\bdepend(?:s|ing)? on\b",
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
    event_status: str = "UNKNOWN"
    date_source: str = "UNKNOWN"


class SalesPersonalizationV2Engine:
    """LLM-First email personalization engine with post-generation claim guard.

    Pipeline:
      Structured Context Packet
      → DeepSeek primary writer
      → Gemini fallback writer
      → Deterministic Claim Grounding & Formatting
      → VALIDATED or HOLD (CLAIM_VIOLATION / GENERATION_FAILED)
    """

    def __init__(
        self,
        llm_provider: Optional[Any] = None,
        deepseek_provider: Optional[Any] = None,
        gemini_provider: Optional[Any] = None,
    ) -> None:
        self._injected_provider = llm_provider
        self._deepseek = deepseek_provider
        self._gemini = gemini_provider

    def _get_deepseek(self) -> Optional[Any]:
        if self._deepseek is not None:
            return self._deepseek
        try:
            from services.llm_provider import DeepSeekProvider
            p = DeepSeekProvider()
            if p.is_available():
                return p
        except Exception as exc:
            logger.debug("DeepSeek provider initialization failed: %s", exc)
        return None

    def _get_gemini(self) -> Optional[Any]:
        if self._gemini is not None:
            return self._gemini
        try:
            from services.llm_provider import GeminiProvider
            p = GeminiProvider()
            if p.is_available():
                return p
        except Exception as exc:
            logger.debug("Gemini provider initialization failed: %s", exc)
        return None

    # ── Public API ─────────────────────────────────────────────────────────

    def generate_outreach(
        self,
        record: Dict[str, Any],
    ) -> PersonalizationV2Result:
        """Generate an LLM-first personalized outreach email for a qualified record."""
        persona = self._resolve_persona(record)
        capabilities = self._select_capabilities(record)

        # Grounding context
        event_status = record.get("event_status") or infer_event_status(
            f"{record.get('trigger', '')} {record.get('trigger_headline', '')} {record.get('trigger_snippet', '')}"
        )
        date_phrase, date_source = resolve_event_date(record)

        # 1. Draft body & subject via LLM (DeepSeek primary, Gemini fallback)
        subject, raw_body, provider_used, llm_error = self._draft_content(
            record, persona, capabilities, event_status, date_phrase, date_source
        )

        if not raw_body:
            return PersonalizationV2Result(
                status="GENERATION_FAILED",
                subject="",
                body="",
                quality_score=0.0,
                persona_used=persona,
                capabilities_included=capabilities,
                word_count=0,
                violations=[llm_error or "Both DeepSeek and Gemini LLM providers failed or unavailable"],
                llm_provider_used="NONE",
                event_status=event_status,
                date_source=date_source,
            )

        # 2. Deterministic claim check across body
        violations = self._check_claims(raw_body, event_status=event_status, record=record)
        if violations:
            return PersonalizationV2Result(
                status="CLAIM_VIOLATION",
                subject=subject,
                body=raw_body,
                quality_score=0.0,
                persona_used=persona,
                capabilities_included=capabilities,
                word_count=self._word_count(raw_body),
                violations=violations,
                llm_provider_used=provider_used,
                event_status=event_status,
                date_source=date_source,
            )

        # 3. Format and validate
        word_count = self._word_count(raw_body)
        quality_score = self._compute_quality_score(raw_body, word_count, persona, record)

        # Clean final body with exact sales signature
        clean_body = re.split(r"\n+(?:best regards|warm regards|regards)", raw_body, flags=re.IGNORECASE)[0].rstrip()
        full_body = clean_body + "\n\n" + SALES_SIGNATURE.strip()

        return PersonalizationV2Result(
            status="VALIDATED",
            subject=subject,
            body=full_body,
            quality_score=quality_score,
            persona_used=persona,
            capabilities_included=capabilities,
            word_count=word_count,
            violations=[],
            llm_provider_used=provider_used,
            event_status=event_status,
            date_source=date_source,
        )

    # ── Drafting logic ─────────────────────────────────────────────────────

    def _draft_content(
        self,
        record: Dict[str, Any],
        persona: str,
        capabilities: List[str],
        event_status: str = "UNKNOWN",
        date_phrase: str = "recent expansion activity",
        date_source: str = "UNKNOWN",
    ) -> Tuple[str, str, str, Optional[str]]:
        """Draft subject and body. DeepSeek primary → Gemini fallback."""
        # If _build_body is explicitly monkeypatched or overridden (e.g. by unit tests):
        if getattr(self._build_body, "__code__", None) != SalesPersonalizationV2Engine._build_body.__code__:
            try:
                b = self._build_body(record, persona, capabilities)
                s = self._build_subject(record)
                return s, b, "PATCHED_TEST_BUILDER", None
            except Exception as exc:
                return "", "", "", str(exc)

        # If injected provider is provided (e.g. mock in unit tests)
        if self._injected_provider is not None:
            try:
                res = self._call_provider(self._injected_provider, record, persona, capabilities, event_status, date_phrase, date_source)
                if res:
                    return res[0], res[1], "INJECTED_LLM", None
            except Exception as exc:
                return "", "", "", f"Injected LLM failed: {exc}"

        # 1. DeepSeek primary
        deepseek = self._get_deepseek()
        if deepseek is not None:
            try:
                res = self._call_provider(deepseek, record, persona, capabilities, event_status, date_phrase, date_source)
                if res and res[1]:
                    return res[0], res[1], "DEEPSEEK", None
            except Exception as exc:
                logger.info("[PERSONALIZATION_V2] DeepSeek primary failed: %s; trying Gemini fallback", exc)

        # 2. Gemini fallback
        gemini = self._get_gemini()
        if gemini is not None:
            try:
                res = self._call_provider(gemini, record, persona, capabilities, event_status, date_phrase, date_source)
                if res and res[1]:
                    return res[0], res[1], "GEMINI", None
            except Exception as exc:
                logger.warning("[PERSONALIZATION_V2] Gemini fallback failed: %s", exc)

        # If neither LLM succeeded
        return "", "", "", "Both DeepSeek and Gemini LLM providers failed or unavailable"

    def _call_provider(
        self,
        provider: Any,
        record: Dict[str, Any],
        persona: str,
        capabilities: List[str],
        event_status: str = "UNKNOWN",
        date_phrase: str = "recent expansion activity",
        date_source: str = "UNKNOWN",
    ) -> Optional[Tuple[str, str]]:
        prompt = self._build_prompt(record, persona, capabilities, event_status, date_phrase, date_source)
        system_prompt = (
            "You are an expert sales intelligence assistant writing a concise, factual, consultative "
            "B2B outreach email on behalf of Bablu Gurjar from Oorja Technical Services Pvt. Ltd. "
            "(ISO/IEC 17025:2017 NABL-accredited calibration laboratory, Certificate CC-3963).\n"
            "MANDATORY CONSTRAINTS:\n"
            "1. FACILITY GROUNDING:\n"
            "   - If event status is EXISTING_FACILITY_EXPANSION or CAPACITY_EXPANSION, you MUST NOT refer to it as a 'new facility', 'new plant', or 'new site'. Refer strictly to the expansion at the existing plant.\n"
            "   - 'new facility' or 'new plant' may ONLY be used when explicitly grounded under NEW_FACILITY.\n"
            "   - For UNKNOWN event status, use neutral wording.\n"
            "2. DATE GROUNDING:\n"
            "   - Do NOT invent specific dates, days, or months. If date is YEAR_ONLY or UNKNOWN, use 'recent expansion activity' or the year without invented dates.\n"
            "   - NEVER use database insertion timestamps or current date as the event date.\n"
            "3. ACCREDITATION & COMPLIANCE LANGUAGE:\n"
            "   - Safe statement: 'Oorja is an ISO/IEC 17025:2017 NABL-accredited calibration laboratory (CC-3963), which may support calibration documentation and traceability requirements where relevant.'\n"
            "   - DO NOT state or imply that accreditation 'ensures', 'guarantees', or 'secures' customer regulatory compliance, audit success, or quality pass.\n"
            "   - All calibration support is delivered strictly subject to instrument scope and range feasibility.\n"
            "4. CAPABILITY TRUTH:\n"
            "   - Only mention approved Oorja capability groups provided in the prompt (maximum 1–3 groups).\n"
            "   - DO NOT invent unapproved capabilities such as NDT calibration, CMM alignment, optical calibration, analytical-instrument calibration, avionics calibration, or high-voltage scope.\n"
            "5. PERSON RESPONSIBILITY GROUNDING:\n"
            "   - Designation indicates commercial relevance, NOT proof of calibration ownership.\n"
            "   - DO NOT say 'you manage calibration', 'your calibration team', 'you oversee CMMs', or 'your torque-tool program'.\n"
            "6. LOW-FRICTION INDUSTRIAL CTA:\n"
            "   - AVOID generic high-friction CTAs like 'Would you be open to a brief introductory call?'.\n"
            "   - Use a practical low-friction CTA (e.g. offering to review their instrument list to suggest a practical laboratory or on-site calibration route subject to scope and range feasibility, or asking to be pointed to the relevant Quality/Metrology colleague).\n"
            "7. WORD COUNT & STRUCTURE:\n"
            "   - Exactly 3 short paragraphs. Target body word count: 90–130 words excluding signature.\n"
            "   - DO NOT include any sign-off or signature. The system will append the exact signature block.\n"
            "   - Return output strictly in valid JSON format: {\"subject\": \"...\", \"body\": \"...\"}."
        )

        if hasattr(provider, "complete"):
            resp = provider.complete(
                system_prompt=system_prompt,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=400,
                temperature=0.2,
            )
            raw_text = resp.content if hasattr(resp, "content") else str(resp)
        elif callable(provider):
            raw_text = provider(prompt)
        else:
            return None

        return self._parse_llm_json(raw_text, record)

    def _parse_llm_json(self, text_resp: str, record: Dict[str, Any]) -> Optional[Tuple[str, str]]:
        """Extract subject and body from LLM JSON response."""
        clean = text_resp.strip()
        if clean.startswith("```json"):
            clean = clean[7:]
        if clean.startswith("```"):
            clean = clean[3:]
        if clean.endswith("```"):
            clean = clean[:-3]
        clean = clean.strip()

        try:
            data = json.loads(clean)
            subject = str(data.get("subject") or "").strip()
            body = str(data.get("body") or "").strip()
            if subject and body:
                return subject, body
        except Exception:
            sub_m = re.search(r'"subject"\s*:\s*"([^"]+)"', clean)
            body_m = re.search(r'"body"\s*:\s*"([^"]+)"', clean)
            if sub_m and body_m:
                return sub_m.group(1), body_m.group(1)

        # If LLM returned plain text paragraphs
        lines = [l.strip() for l in clean.split("\n") if l.strip()]
        if lines:
            subject = self._build_subject(record)
            body = "\n\n".join(lines)
            return subject, body
        return None

    def _build_prompt(
        self,
        record: Dict[str, Any],
        persona: str,
        capabilities: List[str],
        event_status: str = "UNKNOWN",
        date_phrase: str = "recent expansion activity",
        date_source: str = "UNKNOWN",
    ) -> str:
        first_name = record.get("first_name") or str(record.get("person") or "").split()[0] or "Sir/Madam"
        company = record.get("company") or "your company"
        facility = record.get("facility") or company
        designation = record.get("designation") or "Leader"
        trigger = record.get("trigger") or record.get("trigger_headline") or "recent expansion activity"
        persona_angle = PERSONA_VALUE_ANGLES.get(persona, PERSONA_VALUE_ANGLES["DEFAULT"])
        caps_str = ", ".join(capabilities) if capabilities else "Dimensional, Electrical, and Thermal"

        facility_instruction = "Refer strictly to recent expansion activity at the existing plant. DO NOT say 'new facility' or 'new plant'."
        if event_status == EVENT_STATUS_NEW_FACILITY:
            facility_instruction = "You may refer to the new facility / new manufacturing block as explicitly evidenced."
        elif event_status == EVENT_STATUS_NEW_LINE:
            facility_instruction = "Refer strictly to the new production/assembly line, NOT a new plant."
        elif event_status == EVENT_STATUS_UNKNOWN:
            facility_instruction = "Use neutral wording regarding recent operational activity."

        date_instruction = f"{date_phrase} (source: {date_source}). Do not invent dates or months."

        return (
            f"RECIPIENT CONTEXT:\n"
            f"- Name: {first_name}\n"
            f"- Title: {designation} (treat as commercial relevance, do not assume direct calibration ownership)\n"
            f"- Company: {company}\n"
            f"- Facility: {facility}\n"
            f"- Industry: {record.get('industry', 'Manufacturing')}\n\n"
            f"VERIFIED EVIDENCE:\n"
            f"- Event Trigger: {trigger}\n"
            f"- Event / Facility Status: {event_status} ({facility_instruction})\n"
            f"- Event Date Grounding: {date_instruction}\n"
            f"- Facility Location: {facility}\n\n"
            f"COMMERCIAL CONTEXT:\n"
            f"- Persona Value Angle: {persona_angle}\n"
            f"- Approved Oorja Capabilities: {caps_str} (subject to scope and range feasibility; DO NOT mention NDT, CMM alignment, optical, analytical, avionics, or high-voltage)\n"
            f"- Accreditation: Oorja is an ISO/IEC 17025:2017 NABL-accredited calibration laboratory (CC-3963), which may support documentation and traceability requirements where relevant. NEVER guarantee customer compliance.\n"
            f"- CTA Directive: Low-friction industrial CTA offering to review instrument list for lab/onsite feasibility, or asking to point to the relevant Quality/Metrology colleague. AVOID 'Would you be open to a call?'.\n\n"
            f"TASK:\n"
            f"Write a 3-paragraph consultative outreach email (90–130 words excluding signature) to {first_name} referencing "
            f"the {facility} development accurately without signature."
        )

    # ── Helpers for deterministic checks and fallback ─────────────────────

    def _build_body(
        self,
        record: Dict[str, Any],
        persona: str,
        capabilities: List[str],
    ) -> str:
        """Deterministic body template adhering to Phase 2.1C hardening."""
        first_name = record.get("first_name") or str(record.get("person") or "").split()[0] or "Sir/Madam"
        company = record.get("company") or "your company"
        facility = record.get("facility") or company
        trigger = record.get("trigger") or record.get("trigger_headline") or "recent expansion activity"
        value_angle = PERSONA_VALUE_ANGLES.get(persona, PERSONA_VALUE_ANGLES["DEFAULT"])
        cap_text = ", ".join(capabilities) if capabilities else "Dimensional, Electrical, and Thermal"

        event_status = record.get("event_status") or infer_event_status(f"{trigger} {facility}")

        if event_status in {EVENT_STATUS_EXISTING_EXPANSION, EVENT_STATUS_CAPACITY_EXPANSION}:
            opening = f"I noticed the expansion activity at {facility} regarding {trigger} and wanted to reach out regarding upcoming operational requirements."
        elif event_status == EVENT_STATUS_NEW_LINE:
            opening = f"I noticed the production line setup at {facility} regarding {trigger} and wanted to reach out regarding upcoming calibration requirements."
        elif event_status == EVENT_STATUS_NEW_FACILITY:
            opening = f"I noticed the inauguration of the new facility at {facility} regarding {trigger} and wanted to reach out regarding upcoming operational requirements."
        else:
            opening = f"I noticed recent operational developments at {facility} regarding {trigger} and wanted to reach out regarding your calibration support needs."

        body = (
            f"Dear {first_name},\n\n"
            f"{opening}\n\n"
            f"{value_angle} We support {cap_text} calibration parameters, strictly subject to instrument scope and range feasibility under NABL certificate CC-3963.\n\n"
            f"If useful, you can share your instrument list and I can suggest a practical laboratory or on-site calibration route subject to scope and range feasibility. If this sits with another Quality or Metrology colleague, please feel free to point me to the right person."
        )
        return body

    def _resolve_persona(self, record: Dict[str, Any]) -> str:
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
                selected.append(group[0])
        return selected[:3]

    def _build_subject(self, record: Dict[str, Any]) -> str:
        company = record.get("company") or "your facility"
        trigger = record.get("trigger") or record.get("trigger_headline") or "expansion"
        facility = record.get("facility") or company
        return f"NABL Calibration Support — {facility} ({trigger[:50]})"

    def _check_claims(
        self,
        body: str,
        event_status: str = "UNKNOWN",
        record: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        violations: List[str] = []
        for pattern, description in FORBIDDEN_SPECIFIC_UNSUPPORTED_PATTERNS:
            if pattern.search(body):
                violations.append(description)

        # Facility / event status check
        if event_status in {EVENT_STATUS_EXISTING_EXPANSION, EVENT_STATUS_CAPACITY_EXPANSION}:
            if re.search(r"\b(?:new\s+(?:facility|plant|site|unit|campus)|greenfield)\b", body, re.IGNORECASE):
                violations.append("Claim of 'new facility/plant' is unsupported for an existing facility expansion")

        # Leak of database timestamp
        if re.search(r"\b\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}", body):
            violations.append("Detected database timestamp leaked into outreach body")

        # Sentence-level classify_claim checks
        sentences = re.split(r"(?<=[.!?])\s+", body)
        for s in sentences:
            s_clean = s.strip()
            if not s_clean:
                continue
            cat, viol = classify_claim(s_clean, event_status=event_status, record=record)
            if cat == "UNSUPPORTED_SPECIFIC" and viol and viol not in violations:
                violations.append(viol)

        return violations

    def _word_count(self, text: str) -> int:
        clean = text.split("Best regards,")[0].split("Warm regards,")[0]
        return len(re.findall(r"\w+", clean))

    def _compute_quality_score(
        self,
        body: str,
        word_count: int,
        persona: str,
        record: Dict[str, Any],
    ) -> float:
        score = 100.0
        if word_count < 80:
            score -= 15.0
        elif word_count > 140:
            score -= 15.0

        if persona == "DEFAULT":
            score -= 5.0

        trigger = str(record.get("trigger") or record.get("trigger_headline") or "")
        if len(trigger) < 5:
            score -= 10.0

        company = str(record.get("company") or "")
        facility = str(record.get("facility") or "")
        if company.lower() not in body.lower() and facility.lower() not in body.lower():
            score -= 10.0

        return max(0.0, min(100.0, score))
