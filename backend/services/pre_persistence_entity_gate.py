"""Authoritative Pre-Persistence Entity Truth Gate (Task 3D.1E.1).

Enforces strict semantic, granular, and deterministic validation before ANY Company row is created:
1. Deterministic Fast-Reject: Cheaply filters pronouns, URLs, emails, publication headers, isolated industry nouns, truncated fragments.
2. Three-Dimensional Entity Evaluation:
   - entity_type: TARGET_INDUSTRIAL_COMPANY, REAL_COMPANY_NON_TARGET, etc.
   - industrial_relevance: MANUFACTURER, INDUSTRIAL_OPERATOR, NON_INDUSTRIAL, UNKNOWN.
   - geographic_serviceability: SERVICEABLE, SERVICEABLE_SUBJECT_TO_PERMISSION, UNKNOWN.
3. Decoupled Geography: Oorja calibration is global (subject to permissions). Foreign HQ or facilities != non-target.
4. Corporate Entity Granularity: EXACT_OPERATING_COMPANY, SUBSIDIARY, JV, PARENT_GROUP, AMBIGUOUS_GROUP.
5. Strict Zero-Invention: Canonical and operating entities must be strictly grounded in evidence text.
6. Authoritative Persistence Predicate:
   PERSIST = (
       entity_type == TARGET_INDUSTRIAL_COMPANY
       AND industrial_relevance IN (MANUFACTURER, INDUSTRIAL_OPERATOR)
       AND zero_invention_grounding_passed
       AND (
           entity_granularity IN (EXACT_OPERATING_COMPANY, SUBSIDIARY, JV)
           OR (
               entity_granularity == PARENT_GROUP
               AND parent_group_event_is_explicitly_grounded
               AND downstream_targetability_is_demonstrated
           )
       )
   )
   AMBIGUOUS_GROUP MUST NEVER PERSIST.
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
    operating_entity_name: Optional[str] = None
    industrial_relevance: str = "UNKNOWN"
    facility_country: Optional[str] = None
    geographic_serviceability: str = "UNKNOWN"
    entity_granularity: str = "UNKNOWN"
    parent_group_event_is_explicitly_grounded: bool = False
    downstream_targetability_is_demonstrated: bool = False
    confidence: float = 0.0
    supporting_evidence: List[str] = field(default_factory=list)
    reason: str = ""
    is_target_industrial: bool = False
    should_persist: bool = False
    provider_used: str = "DETERMINISTIC"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_type": self.entity_type,
            "canonical_company_name": self.canonical_company_name,
            "operating_entity_name": self.operating_entity_name,
            "industrial_relevance": self.industrial_relevance,
            "facility_country": self.facility_country,
            "geographic_serviceability": self.geographic_serviceability,
            "entity_granularity": self.entity_granularity,
            "parent_group_event_is_explicitly_grounded": self.parent_group_event_is_explicitly_grounded,
            "downstream_targetability_is_demonstrated": self.downstream_targetability_is_demonstrated,
            "confidence": self.confidence,
            "supporting_evidence": self.supporting_evidence,
            "reason": self.reason,
            "is_target_industrial": self.is_target_industrial,
            "should_persist": self.should_persist,
            "provider_used": self.provider_used,
        }


PREPERSISTENCE_SYSTEM_PROMPT = """You are the authoritative Pre-Persistence Entity Truth Gate for Salesoorja, an industrial B2B sales intelligence and calibration/testing equipment platform.
Your mandate is to evaluate candidate company entities extracted from search queries and web snippets.

CRITICAL PRINCIPLE 1 — GEOGRAPHY IS DECOUPLED FROM TARGET INDUSTRIAL STATUS:
- Oorja's calibration and equipment testing serviceability is GLOBAL (subject to applicable permissions/authorizations).
- TARGET_INDUSTRIAL_COMPANY means a real operating industrial/manufacturing organization with plausible need for calibration, testing, measurement, or quality services.
- It does NOT require Indian headquarters, Indian ownership, or Indian facilities.
- Examples of targets if evidence supports manufacturing: Royal Philips, Copeland, GE Healthcare, Hovione, Arterex, Eli Lilly.
- A company is REAL_COMPANY_NON_TARGET ONLY if its BUSINESS MODEL is non-industrial (e.g. pure software SaaS like Inven, media publisher, financial services, consumer retail, consulting).
- NEVER classify a manufacturer as REAL_COMPANY_NON_TARGET merely because its headquarters or facilities are outside India.

CRITICAL PRINCIPLE 2 — THREE SEPARATE DIMENSIONS:
You must evaluate and return three distinct dimensions:
1. ENTITY_TYPE:
   - TARGET_INDUSTRIAL_COMPANY: Real operating industrial manufacturer, factory operator, engineering, or processing company.
   - REAL_COMPANY_NON_TARGET: Genuine commercial company, but non-industrial business model (software, banking, media, consulting, retail).
   - PUBLISHER_MEDIA_PORTAL: News site, publisher, industry magazine, directory, aggregator.
   - GOVERNMENT_ENTITY: Government department, ministry, regulatory authority.
   - GENERIC_TEXT: Generic descriptive noun, product category, or label (e.g. 'Chemical', 'COVER STORY').
   - HEADLINE_FRAGMENT: Truncated headline, article title snippet, or sentence fragment.
   - PRODUCT_SERVICE: Specific product model or service offering rather than corporate entity.
   - PERSON: Individual human name.
   - UNKNOWN: Ambiguous, unverifiable, or insufficient evidence.

2. INDUSTRIAL_RELEVANCE:
   - MANUFACTURER: Produces physical goods, hardware, formulation, components, machinery.
   - INDUSTRIAL_OPERATOR: Operates plants, mills, energy facilities, industrial utilities.
   - NON_INDUSTRIAL: Commercial services, software, finance, media, consulting.
   - UNKNOWN: Indeterminate.

3. GEOGRAPHIC_SERVICEABILITY:
   - SERVICEABLE: Domestic Indian facility or direct domestic operating footprint.
   - SERVICEABLE_SUBJECT_TO_PERMISSION: Foreign/international facility or global operations.
   - UNKNOWN: Cannot be determined from evidence.

CRITICAL PRINCIPLE 3 — CORPORATE ENTITY GRANULARITY:
Classify ENTITY_GRANULARITY into:
- EXACT_OPERATING_COMPANY: Specific operating company (e.g. 'Craftsman Automation Limited', 'USV Pvt. Ltd.').
- SUBSIDIARY: Specific operating subsidiary (e.g. 'Amara Raja Advanced Technologies', 'Agratas', 'Wipro GE Healthcare').
- JV: Joint Venture entity (e.g. 'IAMPL' / International Aerospace Manufacturing Pvt. Ltd.).
- PARENT_GROUP: Broad conglomerate or parent group (e.g. 'Tata Group', 'Tata', 'Reliance Industries').
- AMBIGUOUS_GROUP: Broad group/brand without any grounded operating company context in evidence.

OPERATING ENTITY RESOLUTION & ZERO-INVENTION RULES:
1. If evidence for a broad group explicitly mentions an operating subsidiary (e.g. text mentions 'Tata Motors' or 'Agratas' investing in EV battery plant), set operating_entity_name to that exact operating subsidiary.
2. STRICT ZERO-INVENTION: You may NEVER guess or invent a subsidiary from general knowledge. If candidate is 'Tata' and snippet ONLY says 'Tata plans new plant' without naming the division, operating_entity_name MUST be null, and entity_granularity is 'AMBIGUOUS_GROUP'.
3. For PARENT_GROUP: Only set entity_granularity = 'PARENT_GROUP' if evidence explicitly shows the event genuinely belongs to the parent group (e.g. group-wide capex agreement, sovereign MoU) AND downstream facility/person research can act on that parent group. Set parent_group_event_is_explicitly_grounded = true and downstream_targetability_is_demonstrated = true. Otherwise set entity_granularity = 'AMBIGUOUS_GROUP'.
4. canonical_company_name and operating_entity_name MUST be strictly grounded in the provided text.

OUTPUT FORMAT (Valid JSON only):
{
  "entity_type": "TARGET_INDUSTRIAL_COMPANY" | "REAL_COMPANY_NON_TARGET" | "PUBLISHER_MEDIA_PORTAL" | "GOVERNMENT_ENTITY" | "GENERIC_TEXT" | "HEADLINE_FRAGMENT" | "PRODUCT_SERVICE" | "PERSON" | "UNKNOWN",
  "industrial_relevance": "MANUFACTURER" | "INDUSTRIAL_OPERATOR" | "NON_INDUSTRIAL" | "UNKNOWN",
  "facility_country": "<Country name e.g. India, USA, Puerto Rico, or null>",
  "geographic_serviceability": "SERVICEABLE" | "SERVICEABLE_SUBJECT_TO_PERMISSION" | "UNKNOWN",
  "entity_granularity": "EXACT_OPERATING_COMPANY" | "SUBSIDIARY" | "JV" | "PARENT_GROUP" | "AMBIGUOUS_GROUP",
  "canonical_company_name": "<Evidence-grounded canonical company name, or null>",
  "operating_entity_name": "<Specific operating company/subsidiary grounded in evidence, or null>",
  "parent_group_event_is_explicitly_grounded": true | false,
  "downstream_targetability_is_demonstrated": true | false,
  "confidence": <float between 0.0 and 1.0>,
  "supporting_evidence": ["<verbatim quote from text supporting this>"],
  "reason": "<Concise 1-2 sentence explanation>"
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
                entity_granularity="UNKNOWN",
                confidence=1.0,
                reason=f"Candidate too short ({len(cand_clean)} chars)",
                is_target_industrial=False,
                should_persist=False,
                provider_used="DETERMINISTIC_FAST_REJECT",
            )

        # 1. Pronoun check
        if cand_lower in PRONOUNS_AND_GENERIC_SUBJECTS:
            return PrePersistenceEntityDecision(
                entity_type="INVALID_ENTITY",
                canonical_company_name=None,
                industrial_relevance="NON_INDUSTRIAL",
                entity_granularity="UNKNOWN",
                confidence=1.0,
                reason=f"Candidate is an English pronoun/generic subject ('{cand_clean}')",
                is_target_industrial=False,
                should_persist=False,
                provider_used="DETERMINISTIC_FAST_REJECT",
            )

        # 2. Email or raw domain check
        if "@" in cand_clean or any(re.search(pat, cand_lower) for pat in DISALLOWED_DOMAIN_PATTERNS):
            return PrePersistenceEntityDecision(
                entity_type="INVALID_ENTITY",
                canonical_company_name=None,
                industrial_relevance="NON_INDUSTRIAL",
                entity_granularity="UNKNOWN",
                confidence=1.0,
                reason=f"Candidate contains email or web domain syntax ('{cand_clean}')",
                is_target_industrial=False,
                should_persist=False,
                provider_used="DETERMINISTIC_FAST_REJECT",
            )

        # 3. Publication / report headers
        if cand_lower in PUBLICATION_AND_REPORT_HEADERS:
            return PrePersistenceEntityDecision(
                entity_type="GENERIC_TEXT",
                canonical_company_name=None,
                industrial_relevance="NON_INDUSTRIAL",
                entity_granularity="UNKNOWN",
                confidence=1.0,
                reason=f"Candidate is an editorial/publication header ('{cand_clean}')",
                is_target_industrial=False,
                should_persist=False,
                provider_used="DETERMINISTIC_FAST_REJECT",
            )

        # 4. Isolated generic industry nouns
        if cand_lower in ISOLATED_GENERIC_INDUSTRY_NOUNS:
            return PrePersistenceEntityDecision(
                entity_type="GENERIC_TEXT",
                canonical_company_name=None,
                industrial_relevance="NON_INDUSTRIAL",
                entity_granularity="UNKNOWN",
                confidence=1.0,
                reason=f"Candidate is an isolated generic industry/product noun ('{cand_clean}')",
                is_target_industrial=False,
                should_persist=False,
                provider_used="DETERMINISTIC_FAST_REJECT",
            )

        # 5. Malformed single-letter trailing words (e.g. "Waaree's N")
        if re.search(r"['’]s\s+[A-Za-z]$", cand_clean) or re.search(r"\s+[A-Za-z]$", cand_clean):
            return PrePersistenceEntityDecision(
                entity_type="HEADLINE_FRAGMENT",
                canonical_company_name=None,
                industrial_relevance="UNKNOWN",
                entity_granularity="UNKNOWN",
                confidence=0.95,
                reason=f"Candidate has truncated single-letter trailing character ('{cand_clean}')",
                is_target_industrial=False,
                should_persist=False,
                provider_used="DETERMINISTIC_FAST_REJECT",
            )

        # 6. Trailing prepositional fragments (e.g. "OFC industry in a take")
        if re.search(r"\b(in a take|at a glance|on the rise|for the year|to roll out|to invest|to set up)\b", cand_lower):
            return PrePersistenceEntityDecision(
                entity_type="HEADLINE_FRAGMENT",
                canonical_company_name=None,
                industrial_relevance="UNKNOWN",
                entity_granularity="UNKNOWN",
                confidence=0.95,
                reason=f"Candidate contains incomplete headline phrase fragment ('{cand_clean}')",
                is_target_industrial=False,
                should_persist=False,
                provider_used="DETERMINISTIC_FAST_REJECT",
            )

        return None

    def verify_zero_invention(
        self,
        name_to_check: Optional[str],
        evidence_corpus: str,
    ) -> bool:
        """Ensure canonical/operating name is grounded in supplied evidence text."""
        if not name_to_check or not name_to_check.strip():
            return False

        name_clean = name_to_check.strip()
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

        # Check if individual significant words appear in evidence
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
                    max_tokens=350,
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
                    max_tokens=350,
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
                operating_entity_name=None,
                industrial_relevance="UNKNOWN",
                facility_country=None,
                geographic_serviceability="UNKNOWN",
                entity_granularity="UNKNOWN",
                confidence=0.0,
                reason="LLM judge failed to produce structured decision; held for safety",
                is_target_industrial=False,
                should_persist=False,
                provider_used="LLM_FALLBACK_FAILED",
            )

        entity_type = str(parsed.get("entity_type") or "UNKNOWN").strip().upper()
        canonical_name = parsed.get("canonical_company_name")
        operating_name = parsed.get("operating_entity_name")
        ind_rel = str(parsed.get("industrial_relevance") or "UNKNOWN").strip().upper()
        facility_country = parsed.get("facility_country")
        geo_serv = str(parsed.get("geographic_serviceability") or "UNKNOWN").strip().upper()
        granularity = str(parsed.get("entity_granularity") or "UNKNOWN").strip().upper()
        
        # Target Industrial Check (geography decoupled)
        is_target = (entity_type == "TARGET_INDUSTRIAL_COMPANY")

        if granularity in ("", "UNKNOWN", "NONE") and is_target:
            granularity = "EXACT_OPERATING_COMPANY"

        parent_grounded = bool(
            parsed.get("parent_group_event_is_explicitly_grounded")
            or parsed.get("parent_targetability_demonstrated", False)
        )
        downstream_targetable = bool(
            parsed.get("downstream_targetability_is_demonstrated")
            or parsed.get("downstream_targetability_demonstrated", False)
        )
        conf = float(parsed.get("confidence") or 0.80)
        supp_ev = parsed.get("supporting_evidence") or []
        reason = str(parsed.get("reason") or "")

        if is_target:
            increment_prepersist_telemetry("ENTITY_PREPERSIST_LLM_TARGET_ACCEPT")
        elif entity_type == "REAL_COMPANY_NON_TARGET":
            increment_prepersist_telemetry("ENTITY_PREPERSIST_LLM_NON_TARGET")
        else:
            increment_prepersist_telemetry("ENTITY_PREPERSIST_LLM_UNKNOWN")

        return PrePersistenceEntityDecision(
            entity_type=entity_type,
            canonical_company_name=canonical_name if is_target else None,
            operating_entity_name=operating_name if is_target else None,
            industrial_relevance=ind_rel,
            facility_country=facility_country,
            geographic_serviceability=geo_serv,
            entity_granularity=granularity,
            parent_group_event_is_explicitly_grounded=parent_grounded,
            downstream_targetability_is_demonstrated=downstream_targetable,
            confidence=conf,
            supporting_evidence=supp_ev if isinstance(supp_ev, list) else [str(supp_ev)],
            reason=reason,
            is_target_industrial=is_target,
            should_persist=False,  # Evaluated authoritatively in resolve_pre_persistence_decision
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

        PERSIST ONLY WHEN ALL GLOBAL CONDITIONS PASS:
        1. entity_type == TARGET_INDUSTRIAL_COMPANY
        2. industrial_relevance IN (MANUFACTURER, INDUSTRIAL_OPERATOR)
        3. zero_invention_grounding_passed (applies to BOTH branches)
        4. entity_granularity satisfies ONE of these branches:
           BRANCH A:
             entity_granularity IN (EXACT_OPERATING_COMPANY, SUBSIDIARY, JV)
           OR
           BRANCH B:
             entity_granularity == PARENT_GROUP
             AND parent_group_event_is_explicitly_grounded
             AND downstream_targetability_is_demonstrated
        5. AMBIGUOUS_GROUP must NEVER persist.
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
        decision = self.judge_entity_with_llm(clean_candidate, evidence_packet)

        # Step 4: Strict Zero-Invention Enforcement (applies across all persistence paths)
        evidence_corpus = f"{clean_candidate} {title} {snippet} {url} {page_evidence}"
        
        # Determine candidate name to check
        name_to_persist = decision.operating_entity_name or decision.canonical_company_name or clean_candidate
        zero_invention_passed = self.verify_zero_invention(name_to_persist, evidence_corpus)

        # If operating_entity_name was proposed by LLM but not grounded in evidence,
        # fallback to canonical_company_name only if canonical is grounded
        if not zero_invention_passed and decision.canonical_company_name and decision.canonical_company_name != name_to_persist:
            if self.verify_zero_invention(decision.canonical_company_name, evidence_corpus):
                logger.warning(
                    "[PREPERSIST_UNGROUNDED_SUBSIDIARY] Operating entity '%s' ungrounded in evidence; demoting to canonical '%s'",
                    decision.operating_entity_name,
                    decision.canonical_company_name,
                )
                decision.operating_entity_name = None
                name_to_persist = decision.canonical_company_name
                zero_invention_passed = True
                # If operating entity was demoted, broad group cannot assume SUBSIDIARY
                if decision.entity_granularity == "SUBSIDIARY":
                    decision.entity_granularity = "AMBIGUOUS_GROUP"

        if decision.is_target_industrial and not zero_invention_passed:
            increment_prepersist_telemetry("ENTITY_PREPERSIST_EVIDENCE_REJECT")
            increment_prepersist_telemetry("ENTITY_PREPERSIST_FINAL_REJECT")
            logger.warning(
                "[PREPERSIST_REJECT: ZERO_INVENTION] Candidate '%s' proposed ungrounded name '%s'",
                clean_candidate,
                name_to_persist,
            )
            decision.entity_type = "UNKNOWN"
            decision.canonical_company_name = None
            decision.operating_entity_name = None
            decision.is_target_industrial = False
            decision.should_persist = False
            decision.reason = f"Zero-invention guard failed: name '{name_to_persist}' not grounded in evidence"
            record_prepersist_latency(_t.time() - _t0)
            return decision

        # Step 5: Authoritative Persistence Predicate
        # PERSIST = (
        #     entity_type == TARGET_INDUSTRIAL_COMPANY
        #     AND industrial_relevance IN (MANUFACTURER, INDUSTRIAL_OPERATOR)
        #     AND zero_invention_grounding_passed
        #     AND (
        #         entity_granularity IN (EXACT_OPERATING_COMPANY, SUBSIDIARY, JV)
        #         OR (
        #             entity_granularity == PARENT_GROUP
        #             AND parent_group_event_is_explicitly_grounded
        #             AND downstream_targetability_is_demonstrated
        #         )
        #     )
        # )
        # AMBIGUOUS_GROUP must NEVER persist.

        is_target_type = (decision.entity_type == "TARGET_INDUSTRIAL_COMPANY")
        is_industrial_rel = (decision.industrial_relevance in ("MANUFACTURER", "INDUSTRIAL_OPERATOR"))

        branch_a = decision.entity_granularity in ("EXACT_OPERATING_COMPANY", "SUBSIDIARY", "JV")
        branch_b = (
            decision.entity_granularity == "PARENT_GROUP"
            and decision.parent_group_event_is_explicitly_grounded
            and decision.downstream_targetability_is_demonstrated
        )

        decision.should_persist = bool(
            is_target_type
            and is_industrial_rel
            and zero_invention_passed
            and (branch_a or branch_b)
            and decision.entity_granularity != "AMBIGUOUS_GROUP"
        )

        if decision.should_persist:
            decision.is_target_industrial = True
            if not decision.canonical_company_name:
                decision.canonical_company_name = decision.operating_entity_name or clean_candidate
        else:
            decision.is_target_industrial = False
            decision.canonical_company_name = None
            decision.operating_entity_name = None
            if decision.entity_granularity == "AMBIGUOUS_GROUP":
                decision.reason = f"Ambiguous broad group '{clean_candidate}' without evidence-grounded operating subsidiary; held from persistence"

        record_prepersist_latency(_t.time() - _t0)

        if decision.should_persist:
            increment_prepersist_telemetry("ENTITY_PREPERSIST_FINAL_ACCEPT")
            logger.info(
                "[PREPERSIST_ACCEPT: TARGET_INDUSTRIAL] '%s' -> Name: '%s' (Granularity: %s, Geo: %s, Provider: %s, Conf: %.2f)",
                clean_candidate,
                decision.canonical_company_name,
                decision.entity_granularity,
                decision.geographic_serviceability,
                decision.provider_used,
                decision.confidence,
            )
        else:
            record_rejected_candidate({
                "candidate": clean_candidate,
                "evidence": f"{title} {snippet} {url}",
                "gate_result": decision.entity_type,
                "granularity": decision.entity_granularity,
                "provider": decision.provider_used,
                "reason": decision.reason,
            })
            increment_prepersist_telemetry("ENTITY_PREPERSIST_FINAL_REJECT")
            logger.info(
                "[PREPERSIST_REJECT: NON_TARGET] '%s' -> Class: %s, Granularity: %s (%s)",
                clean_candidate,
                decision.entity_type,
                decision.entity_granularity,
                decision.reason,
            )

        return decision


pre_persistence_entity_gate = PrePersistenceEntityGate()
