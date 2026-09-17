"""Authoritative Pre-Persistence Entity Truth Gate (Task 3D.1D).

Enforces strict semantic and deterministic validation before ANY Company row is created:
1. Deterministic Fast-Reject: Cheaply filters pronouns, URLs, emails, publication headers, isolated industry nouns, truncated fragments.
2. LLM Semantic Entity Judge: DeepSeek primary, Gemini fallback for deep contextual evaluation.
3. Zero-Invention Enforcement: Verifies canonical name is strictly grounded in supplied evidence text.
4. Non-Target Classification: Distinguishes REAL_COMPANY_NON_TARGET (e.g. software/finance) from TARGET_INDUSTRIAL_COMPANY.
5. Ambiguity Handling: Rejects ambiguous identifiers (e.g. bare "Reliance") as UNKNOWN unless exact target entity is supported.
6. Telemetry Instrumentation.
"""
from __future__ import annotations

import json
import logging
import re
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from services.llm_provider import DeepSeekProvider, GeminiProvider

logger = logging.getLogger(__name__)

# Telemetry tracking
_prepersist_lock = threading.Lock()
PREPERSIST_TELEMETRY: Dict[str, int] = {
    "ENTITY_PREPERSIST_CANDIDATES": 0,
    "ENTITY_PREPERSIST_DETERMINISTIC_REJECT": 0,
    "ENTITY_PREPERSIST_LLM_CALLS": 0,
    "ENTITY_PREPERSIST_LLM_TARGET_ACCEPT": 0,
    "ENTITY_PREPERSIST_LLM_NON_TARGET": 0,
    "ENTITY_PREPERSIST_LLM_UNKNOWN": 0,
    "ENTITY_PREPERSIST_EVIDENCE_REJECT": 0,
    "ENTITY_PREPERSIST_FINAL_ACCEPT": 0,
    "ENTITY_PREPERSIST_FINAL_REJECT": 0,
    "ENTITY_PREPERSIST_FALSE_ACCEPT_AUDIT": 0,
    "DEEPSEEK_ENTITY_CALLS": 0,
    "GEMINI_ENTITY_FALLBACKS": 0,
    "ENTITY_PROVIDER_FAILURES": 0,
}

_PREPERSIST_LATENCIES: List[float] = []
_REJECTED_CANDIDATES_LOG: List[Dict[str, Any]] = []

def record_prepersist_latency(latency_sec: float) -> None:
    with _prepersist_lock:
        _PREPERSIST_LATENCIES.append(latency_sec)

def get_prepersist_latencies() -> Tuple[float, float]:
    with _prepersist_lock:
        if not _PREPERSIST_LATENCIES:
            return 0.0, 0.0
        sorted_lats = sorted(_PREPERSIST_LATENCIES)
        avg_lat = sum(sorted_lats) / len(sorted_lats)
        p95_idx = int(len(sorted_lats) * 0.95)
        p95_lat = sorted_lats[min(p95_idx, len(sorted_lats) - 1)]
        return avg_lat, p95_lat

def record_rejected_candidate(entry: Dict[str, Any]) -> None:
    with _prepersist_lock:
        _REJECTED_CANDIDATES_LOG.append(entry)

def get_rejected_candidates() -> List[Dict[str, Any]]:
    with _prepersist_lock:
        return list(_REJECTED_CANDIDATES_LOG)

def increment_prepersist_telemetry(metric: str, count: int = 1) -> None:
    with _prepersist_lock:
        PREPERSIST_TELEMETRY[metric] = PREPERSIST_TELEMETRY.get(metric, 0) + count

def get_prepersist_telemetry() -> Dict[str, int]:
    with _prepersist_lock:
        return dict(PREPERSIST_TELEMETRY)


# Deterministic Hard Rejection Lexicons
PRONOUNS_AND_GENERIC_SUBJECTS = {
    "we", "they", "our", "it", "this", "us", "you", "he", "she", "i", "me",
    "my", "your", "its", "their", "them", "these", "those", "whose", "which",
    "what", "who", "whom", "anyone", "everyone", "someone", "nobody"
}

PUBLICATION_AND_REPORT_HEADERS = {
    "cover story", "case study", "special report", "industry analysis",
    "market report", "research report", "press release", "editorial",
    "overview", "whitepaper", "exclusive", "interview", "breaking news",
    "live updates", "latest news", "top stories", "in pictures", "gallery",
    "opinion", "analysis", "viewpoint", "feature story", "spotlight"
}

ISOLATED_GENERIC_INDUSTRY_NOUNS = {
    "chemical", "chemicals", "steel", "manufacturing", "electronics",
    "automotive", "metals", "power", "infrastructure", "defence", "defense",
    "textiles", "plastics", "packaging", "cement", "pharma", "pharmaceuticals",
    "aerospace & defence", "aerospace and defence", "solar module",
    "new solar module", "solar cell", "electric vehicle", "ev battery",
    "battery systems", "food plant", "power plant", "manufacturing plant"
}

DISALLOWED_DOMAIN_PATTERNS = [
    r"@[\w\.-]+\.\w+",               # Email addresses
    r"\.gov(\.in)?\b",              # Government domains as entity names
    r"\.nic(\.in)?\b",              # NIC domains
    r"^https?://",                  # URLs
    r"^www\.",                      # Web addresses
    r"\.com\b", r"\.in\b", r"\.org\b", r"\.net\b", r"\.ai\b", r"\.us\b",
]


@dataclass
class PrePersistenceEntityDecision:
    entity_type: str
    canonical_company_name: Optional[str]
    industrial_relevance: str
    confidence: float
    supporting_evidence: List[str] = field(default_factory=list)
    reason: str = ""
    is_target_industrial: bool = False
    provider_used: str = "DETERMINISTIC"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_type": self.entity_type,
            "canonical_company_name": self.canonical_company_name,
            "industrial_relevance": self.industrial_relevance,
            "confidence": self.confidence,
            "supporting_evidence": self.supporting_evidence,
            "reason": self.reason,
            "is_target_industrial": self.is_target_industrial,
            "provider_used": self.provider_used,
        }


PREPERSISTENCE_SYSTEM_PROMPT = """You are the authoritative Pre-Persistence Entity Truth Gate for Salesoorja, an industrial B2B sales intelligence platform in India.
Your mandate is to evaluate candidate company names extracted from search engine queries/snippets and determine whether they represent an actual Indian industrial target enterprise.

CLASSIFICATION CATEGORIES:
- TARGET_INDUSTRIAL_COMPANY: An authentic, verifiable industrial manufacturing, engineering, heavy processing, or industrial equipment enterprise operating in India (e.g. automotive OEM/component maker, chemical plant, steel mill, solar module manufacturer, precision engineering, aerospace/defense supplier, electronics EMS).
- REAL_COMPANY_NON_TARGET: A genuine commercial company, but NOT an industrial manufacturing or engineering plant target (e.g. pure software/SaaS like Inven, consulting firm, bank/financial institution, consumer retail chain, marketing agency).
- PUBLISHER_MEDIA_PORTAL: A news website, trade magazine, directory, industry association, or media organization (e.g. pv magazine, Manufacturing Today, ET Infra, IBEF).
- GOVERNMENT_ENTITY: A government department, regulatory body, ministry, or public policy initiative (e.g. PIB, MIDC, Ministry of Steel, Defence Industrial Corridor).
- GENERIC_TEXT: Generic descriptive nouns, product categories, or editorial labels (e.g. 'Chemical', 'COVER STORY', 'Case Study', 'new solar module').
- HEADLINE_FRAGMENT: Article headlines, truncated phrases, or milestone snippets (e.g. 'Octillion Achieves Solar', 'OFC industry in a take', 'Waaree\\'s N', 'Steel Plants Operating under SAIL').
- PRODUCT_SERVICE: An individual product, equipment model, or software tool rather than the company itself.
- PERSON: A human person's name extracted mistakenly as a company.
- UNKNOWN: Ambiguous, unverifiable, or insufficient evidence to establish target corporate identity (e.g. single generic word 'Reliance' without subsidiary/division context).

STRICT CRITICAL RULES:
1. ZERO-INVENTION: You may NEVER invent or hallucinate a company name. canonical_company_name must be directly grounded in the provided text evidence.
2. SUBJECT VS SOURCE: If the source is a publisher (e.g. pv-tech.org) reporting on a legitimate industrial company (e.g. Waaree Energies), set canonical_company_name to the industrial subject (e.g. Waaree Energies), NOT the publisher.
3. AMBIGUOUS IDENTIFIERS: If a candidate name is too ambiguous to identify an exact operating company (e.g. bare 'Reliance' without division), classify as UNKNOWN unless the snippet clearly names the exact entity.
4. REAL_COMPANY_NON_TARGET: Genuine non-manufacturing companies (software, finance, media) must be classified as REAL_COMPANY_NON_TARGET.
5. ONLY 'TARGET_INDUSTRIAL_COMPANY' qualifies for Salesoorja persistence.

OUTPUT FORMAT (Valid JSON only):
{
  "entity_type": "TARGET_INDUSTRIAL_COMPANY" | "REAL_COMPANY_NON_TARGET" | "PUBLISHER_MEDIA_PORTAL" | "GOVERNMENT_ENTITY" | "GENERIC_TEXT" | "HEADLINE_FRAGMENT" | "PRODUCT_SERVICE" | "PERSON" | "UNKNOWN",
  "canonical_company_name": "<Canonical name supported by evidence, or null>",
  "industrial_relevance": "MANUFACTURER" | "INDUSTRIAL_OPERATOR" | "NON_INDUSTRIAL" | "UNKNOWN",
  "confidence": <float between 0.0 and 1.0>,
  "supporting_evidence": ["<verbatim quote from evidence supporting this>"],
  "reason": "<1-2 sentence concise explanation>"
}
"""


class PrePersistenceEntityGate:
    """Authoritative decision maker before persisting any Company row to PostgreSQL."""

    def __init__(
        self,
        primary_provider: Optional[Any] = None,
        fallback_provider: Optional[Any] = None,
    ):
        self.primary_provider = primary_provider or DeepSeekProvider()
        self.fallback_provider = fallback_provider or GeminiProvider()

    def deterministic_hard_reject(
        self,
        candidate_name: str,
        context_text: str = "",
        url: str = "",
    ) -> Optional[PrePersistenceEntityDecision]:
        """Cheap, deterministic rejection for objectively invalid entity candidates."""
        cand_clean = (candidate_name or "").strip()
        cand_lower = cand_clean.lower()

        if not cand_clean or len(cand_clean) < 2:
            return PrePersistenceEntityDecision(
                entity_type="INVALID_ENTITY",
                canonical_company_name=None,
                industrial_relevance="NON_INDUSTRIAL",
                confidence=1.0,
                reason=f"Candidate too short ({len(cand_clean)} chars)",
                is_target_industrial=False,
                provider_used="DETERMINISTIC_FAST_REJECT",
            )

        # 1. Pronoun check
        if cand_lower in PRONOUNS_AND_GENERIC_SUBJECTS:
            return PrePersistenceEntityDecision(
                entity_type="INVALID_ENTITY",
                canonical_company_name=None,
                industrial_relevance="NON_INDUSTRIAL",
                confidence=1.0,
                reason=f"Candidate is an English pronoun/generic subject ('{cand_clean}')",
                is_target_industrial=False,
                provider_used="DETERMINISTIC_FAST_REJECT",
            )

        # 2. Email or raw domain check
        if "@" in cand_clean or any(re.search(pat, cand_lower) for pat in DISALLOWED_DOMAIN_PATTERNS):
            return PrePersistenceEntityDecision(
                entity_type="INVALID_ENTITY",
                canonical_company_name=None,
                industrial_relevance="NON_INDUSTRIAL",
                confidence=1.0,
                reason=f"Candidate contains email or web domain syntax ('{cand_clean}')",
                is_target_industrial=False,
                provider_used="DETERMINISTIC_FAST_REJECT",
            )

        # 3. Publication / report headers
        if cand_lower in PUBLICATION_AND_REPORT_HEADERS:
            return PrePersistenceEntityDecision(
                entity_type="GENERIC_TEXT",
                canonical_company_name=None,
                industrial_relevance="NON_INDUSTRIAL",
                confidence=1.0,
                reason=f"Candidate is an editorial/publication header ('{cand_clean}')",
                is_target_industrial=False,
                provider_used="DETERMINISTIC_FAST_REJECT",
            )

        # 4. Isolated generic industry nouns
        if cand_lower in ISOLATED_GENERIC_INDUSTRY_NOUNS:
            return PrePersistenceEntityDecision(
                entity_type="GENERIC_TEXT",
                canonical_company_name=None,
                industrial_relevance="NON_INDUSTRIAL",
                confidence=1.0,
                reason=f"Candidate is an isolated generic industry/product noun ('{cand_clean}')",
                is_target_industrial=False,
                provider_used="DETERMINISTIC_FAST_REJECT",
            )

        # 5. Malformed single-letter trailing words (e.g. "Waaree's N")
        if re.search(r"['’]s\s+[A-Za-z]$", cand_clean) or re.search(r"\s+[A-Za-z]$", cand_clean):
            return PrePersistenceEntityDecision(
                entity_type="HEADLINE_FRAGMENT",
                canonical_company_name=None,
                industrial_relevance="UNKNOWN",
                confidence=0.95,
                reason=f"Candidate has truncated single-letter trailing character ('{cand_clean}')",
                is_target_industrial=False,
                provider_used="DETERMINISTIC_FAST_REJECT",
            )

        # 6. Trailing prepositional fragments (e.g. "OFC industry in a take")
        if re.search(r"\b(in a take|at a glance|on the rise|for the year|to roll out|to invest|to set up)\b", cand_lower):
            return PrePersistenceEntityDecision(
                entity_type="HEADLINE_FRAGMENT",
                canonical_company_name=None,
                industrial_relevance="UNKNOWN",
                confidence=0.95,
                reason=f"Candidate contains incomplete headline phrase fragment ('{cand_clean}')",
                is_target_industrial=False,
                provider_used="DETERMINISTIC_FAST_REJECT",
            )

        return None

    def verify_zero_invention(
        self,
        canonical_name: Optional[str],
        evidence_corpus: str,
    ) -> bool:
        """Ensure canonical_company_name is grounded in supplied evidence text."""
        if not canonical_name or not canonical_name.strip():
            return False

        name_clean = canonical_name.strip()
        name_lower = name_clean.lower()
        evidence_lower = (evidence_corpus or "").lower()

        # Check exact or core tokens in evidence
        if name_lower in evidence_lower:
            return True

        # Strip standard corporate legal suffix and check core name
        core_name = re.sub(
            r"\b(pvt|ltd|limited|private|inc|corp|corporation|llp|holdings|group|industries)\b",
            "",
            name_lower,
            flags=re.IGNORECASE,
        ).strip()

        if core_name and len(core_name) >= 3 and core_name in evidence_lower:
            return True

        # Check if individual significant words appear closely together
        words = [w for w in re.split(r"\W+", core_name) if len(w) >= 3]
        if words and all(w in evidence_lower for w in words):
            return True

        return False

    def judge_entity_with_llm(
        self,
        candidate_name: str,
        evidence_packet: Dict[str, Any],
    ) -> PrePersistenceEntityDecision:
        """Call DeepSeek (primary) or Gemini (fallback) for semantic arbitration."""
        increment_prepersist_telemetry("ENTITY_PREPERSIST_LLM_CALLS")

        user_prompt = f"""Audit the following candidate company entity:
Candidate Entity Name: '{candidate_name}'
Extracted Domain: '{evidence_packet.get('domain', '')}'
Search Title: '{evidence_packet.get('title', '')}'
Search Snippet: '{evidence_packet.get('snippet', '')}'
Source URL: '{evidence_packet.get('url', '')}'
Target Industry: '{evidence_packet.get('industry', '')}'
Discovery Query: '{evidence_packet.get('query', '')}'
Page Evidence Excerpt: '{evidence_packet.get('page_evidence', '')}'
Facility Mentioned: '{evidence_packet.get('facility_name', '')}' in '{evidence_packet.get('facility_city', '')}, {evidence_packet.get('facility_state', '')}'

Classify this entity according to the instructions and return ONLY valid JSON matching the schema."""

        parsed = None
        provider_name = "DeepSeek"

        # 1. Primary: DeepSeek
        if self.primary_provider and getattr(self.primary_provider, "is_available", lambda: True)():
            increment_prepersist_telemetry("DEEPSEEK_ENTITY_CALLS")
            try:
                resp = self.primary_provider.complete(
                    system_prompt=PREPERSISTENCE_SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": user_prompt}],
                    temperature=0.0,
                    max_tokens=250,
                    response_format="json",
                )
                parsed = resp.parse_json() if resp else None
            except Exception as d_err:
                logger.warning("DeepSeek pre-persistence entity judge failed: %s; trying Gemini.", d_err)

        # 2. Fallback: Gemini
        if not parsed and self.fallback_provider and getattr(self.fallback_provider, "is_available", lambda: True)():
            provider_name = "Gemini"
            increment_prepersist_telemetry("GEMINI_ENTITY_FALLBACKS")
            try:
                resp = self.fallback_provider.complete(
                    system_prompt=PREPERSISTENCE_SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": user_prompt}],
                    temperature=0.0,
                    max_tokens=250,
                    response_format="json",
                )
                parsed = resp.parse_json() if resp else None
            except Exception as g_err:
                logger.warning("Gemini pre-persistence entity judge failed: %s", g_err)

        if not parsed:
            increment_prepersist_telemetry("ENTITY_PROVIDER_FAILURES")
            increment_prepersist_telemetry("ENTITY_PREPERSIST_LLM_UNKNOWN")
            return PrePersistenceEntityDecision(
                entity_type="UNKNOWN",
                canonical_company_name=None,
                industrial_relevance="UNKNOWN",
                confidence=0.0,
                reason="LLM judge failed to produce structured decision; held for safety",
                is_target_industrial=False,
                provider_used="LLM_FALLBACK_FAILED",
            )

        entity_type = str(parsed.get("entity_type") or "UNKNOWN").strip().upper()
        canonical_name = parsed.get("canonical_company_name")
        ind_rel = str(parsed.get("industrial_relevance") or "UNKNOWN").strip().upper()
        conf = float(parsed.get("confidence") or 0.80)
        supp_ev = parsed.get("supporting_evidence") or []
        reason = str(parsed.get("reason") or "")

        # Strict Target Industrial check
        is_target = (entity_type == "TARGET_INDUSTRIAL_COMPANY")

        if is_target:
            increment_prepersist_telemetry("ENTITY_PREPERSIST_LLM_TARGET_ACCEPT")
        elif entity_type == "REAL_COMPANY_NON_TARGET":
            increment_prepersist_telemetry("ENTITY_PREPERSIST_LLM_NON_TARGET")
        else:
            increment_prepersist_telemetry("ENTITY_PREPERSIST_LLM_UNKNOWN")

        return PrePersistenceEntityDecision(
            entity_type=entity_type,
            canonical_company_name=canonical_name if is_target else None,
            industrial_relevance=ind_rel,
            confidence=conf,
            supporting_evidence=supp_ev if isinstance(supp_ev, list) else [str(supp_ev)],
            reason=reason,
            is_target_industrial=is_target,
            provider_used=provider_name,
        )

    def resolve_pre_persistence_decision(
        self,
        candidate_name: str,
        title: str = "",
        snippet: str = "",
        url: str = "",
        query: str = "",
        industry: str = "",
        page_evidence: str = "",
        facility_info: Optional[Dict[str, Any]] = None,
        deterministic_is_valid: bool = True,
        deterministic_reason: str = "",
    ) -> PrePersistenceEntityDecision:
        """Authoritative single gate called before any Company row persistence.

        Returns PrePersistenceEntityDecision with is_target_industrial = True ONLY if:
        1. Not blocked by deterministic fast-reject
        2. Classified as TARGET_INDUSTRIAL_COMPANY by LLM Semantic Judge
        3. Zero-invention verification passes (name grounded in evidence)
        """
        import time as _t
        _t0 = _t.time()
        increment_prepersist_telemetry("ENTITY_PREPERSIST_CANDIDATES")

        clean_candidate = (candidate_name or "").strip()

        # Step 1: Deterministic Hard Reject
        hard_reject = self.deterministic_hard_reject(clean_candidate, context_text=title, url=url)
        if hard_reject:
            record_prepersist_latency(_t.time() - _t0)
            record_rejected_candidate({
                "candidate": clean_candidate,
                "evidence": f"{title} {snippet} {url}",
                "gate_result": hard_reject.entity_type,
                "provider": hard_reject.provider_used,
                "reason": hard_reject.reason,
            })
            increment_prepersist_telemetry("ENTITY_PREPERSIST_DETERMINISTIC_REJECT")
            increment_prepersist_telemetry("ENTITY_PREPERSIST_FINAL_REJECT")
            logger.info("[PREPERSIST_REJECT: DETERMINISTIC] Candidate '%s' -> %s (%s)", clean_candidate, hard_reject.entity_type, hard_reject.reason)
            return hard_reject

        # Step 2: Assemble rich evidence packet
        fac = facility_info or {}
        evidence_packet = {
            "candidate": clean_candidate,
            "title": title or "",
            "snippet": snippet or "",
            "url": url or "",
            "domain": re.sub(r"^https?://(www\.)?", "", url or "").split("/")[0] if url else "",
            "query": query or "",
            "industry": industry or "",
            "page_evidence": page_evidence or "",
            "facility_name": fac.get("facility_name") or fac.get("name") or "",
            "facility_city": fac.get("city") or "",
            "facility_state": fac.get("state") or "",
            "deterministic_valid": deterministic_is_valid,
            "deterministic_reason": deterministic_reason,
        }

        # Step 3: LLM Semantic Entity Judge
        llm_decision = self.judge_entity_with_llm(clean_candidate, evidence_packet)

        # Step 4: Zero-Invention Enforcement on Target Industrial Companies
        if llm_decision.is_target_industrial:
            evidence_corpus = f"{clean_candidate} {title} {snippet} {url} {page_evidence}"
            is_grounded = self.verify_zero_invention(llm_decision.canonical_company_name, evidence_corpus)
            if not is_grounded:
                increment_prepersist_telemetry("ENTITY_PREPERSIST_EVIDENCE_REJECT")
                increment_prepersist_telemetry("ENTITY_PREPERSIST_FINAL_REJECT")
                logger.warning(
                    "[PREPERSIST_REJECT: ZERO_INVENTION] Candidate '%s' proposed ungrounded canonical name '%s'",
                    clean_candidate,
                    llm_decision.canonical_company_name,
                )
                return PrePersistenceEntityDecision(
                    entity_type="UNKNOWN",
                    canonical_company_name=None,
                    industrial_relevance="UNKNOWN",
                    confidence=0.0,
                    supporting_evidence=[],
                    reason=f"Zero-invention guard failed: canonical name '{llm_decision.canonical_company_name}' not grounded in evidence",
                    is_target_industrial=False,
                    provider_used=llm_decision.provider_used,
                )

        record_prepersist_latency(_t.time() - _t0)
        if llm_decision.is_target_industrial:
            increment_prepersist_telemetry("ENTITY_PREPERSIST_FINAL_ACCEPT")
            logger.info(
                "[PREPERSIST_ACCEPT: TARGET_INDUSTRIAL] '%s' -> Canonical: '%s' (%s, conf=%.2f)",
                clean_candidate,
                llm_decision.canonical_company_name,
                llm_decision.provider_used,
                llm_decision.confidence,
            )
        else:
            record_rejected_candidate({
                "candidate": clean_candidate,
                "evidence": f"{title} {snippet} {url}",
                "gate_result": llm_decision.entity_type,
                "provider": llm_decision.provider_used,
                "reason": llm_decision.reason,
            })
            increment_prepersist_telemetry("ENTITY_PREPERSIST_FINAL_REJECT")
            logger.info(
                "[PREPERSIST_REJECT: NON_TARGET] '%s' -> Class: %s (%s)",
                clean_candidate,
                llm_decision.entity_type,
                llm_decision.reason,
            )

        return llm_decision


pre_persistence_entity_gate = PrePersistenceEntityGate()
