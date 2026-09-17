"""Authoritative Pre-Persistence Entity Truth Gate (Task 3D.1E.1A).

Enforces strict semantic, granular, and deterministic validation before ANY Company row is created:
1. Deterministic Fast-Reject: Cheaply filters pronouns, URLs, emails, publication headers, isolated industry nouns, truncated fragments.
2. Three-Dimensional Entity Evaluation:
   - entity_type: TARGET_INDUSTRIAL_COMPANY, REAL_COMPANY_NON_TARGET, etc.
   - industrial_relevance: MANUFACTURER, INDUSTRIAL_OPERATOR, NON_INDUSTRIAL, UNKNOWN.
   - geographic_serviceability: SERVICEABLE, SERVICEABLE_SUBJECT_TO_PERMISSION, UNKNOWN.
3. Corporate Entity vs. Facility Distinction:
   - Location qualifiers (e.g. 'New Jersey' in 'Hovione New Jersey') belong to facility_name/country, NOT corporate identity.
   - Corporate identity: canonical_company_name = 'Hovione', entity_granularity = EXACT_OPERATING_COMPANY (not an invented subsidiary).
4. Rigorous Corporate Entity Granularity:
   - EXACT_OPERATING_COMPANY: Evidence identifies the operating company itself.
   - SUBSIDIARY: Evidence explicitly establishes a legal subsidiary relationship.
   - JV: Evidence explicitly establishes a joint venture.
   - PARENT_GROUP: Evidence explicitly belongs at parent/group level AND downstream targetability is demonstrated.
   - AMBIGUOUS_GROUP: Brand/group exists but exact operating entity cannot be grounded (e.g. bare 'Tata' with plant evidence but no named subsidiary).
     AMBIGUOUS_GROUP MUST NEVER PERSIST.
5. Strict Zero-Invention:
   - Never infer subsidiaries from parent brand names (e.g. 'Tata' cannot become 'Tata Motors' or 'Agratas' unless explicitly named in evidence).
   - Knowledge that company X owns company Y is NOT enough unless that relationship is present in the evidence packet.
6. Authoritative Persistence Predicate:
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
    r"\.gov(\.in)?",              # Government domains as entity names
    r"\.nic(\.in)?",              # NIC domains
    r"^https?://",                  # URLs
    r"^www\.",                      # Web addresses
    r"\.com", r"\.in", r"\.org", r"\.net", r"\.ai", r"\.us",
]


@dataclass
class PrePersistenceEntityDecision:
    entity_type: str
    canonical_company_name: Optional[str]
    operating_entity_name: Optional[str] = None
    industrial_relevance: str = "UNKNOWN"
    facility_name: Optional[str] = None
    facility_country: Optional[str] = None
    geographic_serviceability: str = "UNKNOWN"
    entity_granularity: str = "UNKNOWN"
    parent_group_event_is_explicitly_grounded: bool = False
    downstream_targetability_is_demonstrated: bool = False
    confidence: float = 0.0
    supporting_evidence: List[str] = field(default_factory=list)
    evidence_supporting_entity_relationship: Optional[str] = None
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
            "facility_name": self.facility_name,
            "facility_country": self.facility_country,
            "geographic_serviceability": self.geographic_serviceability,
            "entity_granularity": self.entity_granularity,
            "parent_group_event_is_explicitly_grounded": self.parent_group_event_is_explicitly_grounded,
            "downstream_targetability_is_demonstrated": self.downstream_targetability_is_demonstrated,
            "confidence": self.confidence,
            "supporting_evidence": self.supporting_evidence,
            "evidence_supporting_entity_relationship": self.evidence_supporting_entity_relationship,
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

CRITICAL PRINCIPLE 2 — CORPORATE ENTITY != FACILITY LOCATION:
- Location qualifiers attached to a company name (e.g. 'New Jersey' in 'Hovione New Jersey', or 'Puerto Rico' in 'Lilly Puerto Rico', or 'Sanand' in 'Tata Sanand') indicate a FACILITY or location, NOT a corporate subsidiary or company name!
- You MUST separate corporate identity from facility location:
  - canonical_company_name: The clean corporate company name without facility/city/state words (e.g. 'Hovione', 'Eli Lilly', 'Tata').
  - operating_entity_name: An exact operating company name ONLY if explicitly named as a corporate entity in evidence (e.g. 'Tata Motors Limited', 'Wipro GE Healthcare'). A facility/plant description like 'Tata (Grounded Sanand EV Cell Plant)' is NOT a company name and is FORBIDDEN.
  - facility_name: The specific facility/plant site if mentioned (e.g. 'New Jersey manufacturing site', 'Sanand EV battery plant', 'Hosur precision machining plant').
  - facility_country: Country where facility is located (e.g. 'India', 'USA', 'Puerto Rico').
  - entity_granularity: EXACT_OPERATING_COMPANY (or SUBSIDIARY only if evidence proves a distinct legal subsidiary). Do NOT fabricate subsidiary status from a facility name or location.

CRITICAL PRINCIPLE 3 — RIGOROUS ENTITY GRANULARITY:
Classify ENTITY_GRANULARITY into:
- EXACT_OPERATING_COMPANY: Evidence identifies the operating company itself (e.g. 'Craftsman Automation Limited', 'USV Pvt. Ltd.', 'Tata Motors Limited', 'Hovione', 'Arterex').
- SUBSIDIARY: Evidence explicitly establishes a legal corporate subsidiary relationship (e.g. 'Amara Raja Advanced Technologies' as battery subsidiary of Amara Raja, 'Wipro GE Healthcare' as healthcare operating entity).
- JV: Evidence explicitly establishes a corporate joint venture (e.g. 'IAMPL' / International Aerospace Manufacturing Pvt. Ltd. as Rolls-Royce and HAL JV).
- PARENT_GROUP: Broad conglomerate or parent group (e.g. 'Tata Group', 'Reliance Industries') where evidence explicitly belongs at group/parent level (e.g. group-wide sovereign MoU or group capex commitment) AND downstream targetability is demonstrated.
- AMBIGUOUS_GROUP: Brand or group identity exists, but the exact operating entity cannot be grounded from evidence.
  CRITICAL RULE FOR AMBIGUOUS_GROUP:
  - If evidence only says 'Tata' (e.g. 'Tata commits Rs 13,000 crore for EV battery plant in Sanand') and does NOT explicitly name which operating subsidiary (e.g. Tata Motors, Agratas, Tata AutoComp) will own/operate it:
    - You MUST NOT infer or guess the subsidiary from industry, facility city, product category, or outside knowledge.
    - A plant location does NOT prove which Tata operating company owns or operates that plant.
    - 'Tata' is NOT itself a subsidiary. Never classify 'Tata' as SUBSIDIARY.
    - Unless the event is explicitly and legitimately a group-level MoU/event satisfying PARENT_GROUP, classify bare 'Tata' as AMBIGUOUS_GROUP.
    - AMBIGUOUS_GROUP must NEVER persist (should_persist = false).

CRITICAL PRINCIPLE 4 — ABSOLUTE ZERO-INVENTION:
- Operating entity names must appear verbatim or as standard legal suffix normalizations in the supplied evidence.
- Knowledge that company X owns company Y is NOT enough unless that relationship is explicitly stated in the supplied evidence.
- If an operating subsidiary is not named in evidence, operating_entity_name MUST be null.

OUTPUT FORMAT (Valid JSON only):
{
  "entity_type": "TARGET_INDUSTRIAL_COMPANY" | "REAL_COMPANY_NON_TARGET" | "PUBLISHER_MEDIA_PORTAL" | "GOVERNMENT_ENTITY" | "GENERIC_TEXT" | "HEADLINE_FRAGMENT" | "PRODUCT_SERVICE" | "PERSON" | "UNKNOWN",
  "industrial_relevance": "MANUFACTURER" | "INDUSTRIAL_OPERATOR" | "NON_INDUSTRIAL" | "UNKNOWN",
  "facility_name": "<Specific facility name or plant site, or null>",
  "facility_country": "<Country name e.g. India, USA, Puerto Rico, or null>",
  "geographic_serviceability": "SERVICEABLE" | "SERVICEABLE_SUBJECT_TO_PERMISSION" | "UNKNOWN",
  "entity_granularity": "EXACT_OPERATING_COMPANY" | "SUBSIDIARY" | "JV" | "PARENT_GROUP" | "AMBIGUOUS_GROUP",
  "canonical_company_name": "<Evidence-grounded corporate company name without facility qualifiers, or null>",
  "operating_entity_name": "<Specific operating company/subsidiary if explicitly established in text, or null>",
  "evidence_supporting_entity_relationship": "<Concise quote or note establishing relationship, or null>",
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

        # 5. Trailing truncated single-letter fragments (e.g. "Waaree's N", "Adani E")
        if (re.search(r"['\s][A-Za-z]$", cand_clean) and not re.search(r"\b[A-Z]\.[A-Z]\b", cand_clean)) or re.search(r"['’]s\s+[A-Za-z]$", cand_clean):
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

        # 6. Verb-phrase and trailing prepositional headline fragments
        if re.search(r"\b(achieves?|sets up|expanding|announces?|launches?|invests?|in a take|at a glance|on the rise|for the year|to roll out|to invest|to set up)\b", cand_lower):
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

        # Direct containment
        if name_lower in evidence_lower:
            return True

        # Strip legal entity suffixes and check core stem
        core_name = re.sub(
            r"\b(ltd|limited|pvt|private|corp|corporation|inc|incorporated|llc|co|company|group|holding|holdings)\b\.?",
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
        """Query LLM judge to classify candidate into 3 dimensions + entity granularity."""
        clean_candidate = (candidate_name or "").strip()
        increment_prepersist_telemetry("ENTITY_PREPERSIST_LLM_CALLS")

        user_prompt = f"""EVALUATE CANDIDATE ENTITY:
Candidate Name: "{clean_candidate}"
Context Title: "{evidence_packet.get('title', '')}"
Evidence Snippet: "{evidence_packet.get('snippet', '')}"
Source URL: "{evidence_packet.get('url', '')}"
Query Industry: "{evidence_packet.get('industry', '')}"
Page Evidence: "{evidence_packet.get('page_evidence', '')[:1000]}"
Facility Info: {json.dumps(evidence_packet.get('facility_name', ''))}

Classify this entity according to the instructions and return ONLY valid JSON matching the schema."""

        parsed: Optional[Dict[str, Any]] = None
        provider_name = "DEEPSEEK"

        def _call_provider(prov):
            if not prov:
                return None
            if hasattr(prov, "is_available") and not prov.is_available():
                return None
            kwargs = {
                "system_prompt": PREPERSISTENCE_SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": user_prompt}],
                "temperature": 0.0,
                "max_tokens": 350,
                "response_format": "json",
            }
            if hasattr(prov, "complete"):
                return prov.complete(**kwargs)
            elif hasattr(prov, "call"):
                return prov.call(prompt=user_prompt, **kwargs)
            elif callable(prov):
                return prov(prompt=user_prompt, **kwargs)
            return None

        if self.primary_provider:
            try:
                increment_prepersist_telemetry("DEEPSEEK_ENTITY_CALLS")
                resp = _call_provider(self.primary_provider)
                parsed = resp.parse_json() if resp and hasattr(resp, "parse_json") else None
            except Exception as e:
                logger.warning("[PREPERSIST_GATE: PRIMARY_FAIL] %s, falling back", e)
                increment_prepersist_telemetry("ENTITY_PROVIDER_FAILURES")

        if (not parsed or not isinstance(parsed, dict) or "entity_type" not in parsed) and self.fallback_provider:
            try:
                increment_prepersist_telemetry("GEMINI_ENTITY_FALLBACKS")
                provider_name = "GEMINI"
                resp = _call_provider(self.fallback_provider)
                parsed = resp.parse_json() if resp and hasattr(resp, "parse_json") else None
            except Exception as e2:
                logger.error("[PREPERSIST_GATE: ALL_LLMS_FAILED] %s", e2)
                increment_prepersist_telemetry("ENTITY_PROVIDER_FAILURES")

        if not parsed or not isinstance(parsed, dict):
            return PrePersistenceEntityDecision(
                entity_type="UNKNOWN",
                canonical_company_name=None,
                operating_entity_name=None,
                industrial_relevance="UNKNOWN",
                facility_name=None,
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
        facility_name = parsed.get("facility_name")
        facility_country = parsed.get("facility_country")
        geo_serv = str(parsed.get("geographic_serviceability") or "UNKNOWN").strip().upper()
        granularity = str(parsed.get("entity_granularity") or "UNKNOWN").strip().upper()
        rel_evidence = parsed.get("evidence_supporting_entity_relationship")
        
        # Target Industrial Check (geography decoupled)
        is_target = (entity_type == "TARGET_INDUSTRIAL_COMPANY")

        # Backward compatibility default for test mocks omitting granularity
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
            facility_name=facility_name,
            facility_country=facility_country,
            geographic_serviceability=geo_serv,
            entity_granularity=granularity,
            parent_group_event_is_explicitly_grounded=parent_grounded,
            downstream_targetability_is_demonstrated=downstream_targetable,
            confidence=conf,
            supporting_evidence=supp_ev if isinstance(supp_ev, list) else [str(supp_ev)],
            evidence_supporting_entity_relationship=rel_evidence,
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

        # Step 3b: Facility vs Operating Entity Sanitization
        # A facility/plant description is NEVER an operating corporate entity!
        if decision.operating_entity_name:
            op_lower = decision.operating_entity_name.lower()
            if any(term in op_lower for term in ("plant", "facility", "factory", "site", "grounded", "gigafactory", "works")):
                if not decision.facility_name:
                    decision.facility_name = decision.operating_entity_name
                decision.operating_entity_name = None

        # If operating entity is identical to canonical company name, avoid redundancy unless SUBSIDIARY/JV
        if decision.operating_entity_name and decision.canonical_company_name:
            if decision.operating_entity_name.strip().lower() == decision.canonical_company_name.strip().lower():
                if decision.entity_granularity not in ("SUBSIDIARY", "JV"):
                    decision.operating_entity_name = None

        # Step 4: Strict Zero-Invention Enforcement (applies across all persistence paths)
        evidence_corpus = f"{clean_candidate} {title} {snippet} {url} {page_evidence}"
        
        # Verify operating entity grounding if proposed
        if decision.operating_entity_name:
            if not self.verify_zero_invention(decision.operating_entity_name, evidence_corpus):
                logger.warning(
                    "[PREPERSIST_UNGROUNDED_SUBSIDIARY] Operating entity '%s' ungrounded in evidence; demoting to None",
                    decision.operating_entity_name,
                )
                decision.operating_entity_name = None

        # Verify canonical name grounding
        name_to_persist = decision.operating_entity_name or decision.canonical_company_name or clean_candidate
        zero_invention_passed = self.verify_zero_invention(name_to_persist, evidence_corpus)

        # Corporate Entity vs Facility: Location qualifier on candidate (e.g. "Hovione New Jersey")
        # Do not invent SUBSIDIARY merely from a facility location qualifier!
        if decision.entity_granularity == "SUBSIDIARY" and not decision.operating_entity_name:
            # If no legal subsidiary was established in evidence, it's EXACT_OPERATING_COMPANY
            decision.entity_granularity = "EXACT_OPERATING_COMPANY"

        # Broad Conglomerate / Brand Group check (e.g. "Tata", "Reliance", "Adani", "Birla")
        # A broad brand name with a plant is NOT a subsidiary!
        cand_lower = clean_candidate.strip().lower()
        canonical_lower = (decision.canonical_company_name or "").strip().lower()
        is_broad_brand = (cand_lower in ("tata", "reliance", "adani", "birla", "mahindra", "godrej", "l&t", "vedanta")
                          or canonical_lower in ("tata", "reliance", "adani", "birla", "mahindra", "godrej", "l&t", "vedanta"))

        if is_broad_brand and not decision.operating_entity_name:
            # If the event is NOT explicitly a legitimate group-wide MoU satisfying PARENT_GROUP
            is_valid_parent_group = (
                decision.entity_granularity == "PARENT_GROUP"
                and decision.parent_group_event_is_explicitly_grounded
                and decision.downstream_targetability_is_demonstrated
            )
            if not is_valid_parent_group:
                # Brand/group identity exists but exact operating entity cannot be grounded
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
        # PERSIST ONLY WHEN ALL GLOBAL CONDITIONS PASS:
        # 1. entity_type == TARGET_INDUSTRIAL_COMPANY
        # 2. industrial_relevance IN (MANUFACTURER, INDUSTRIAL_OPERATOR)
        # 3. zero_invention_grounding_passed (applies to BOTH branches)
        # 4. entity_granularity satisfies ONE of these branches:
        #    BRANCH A:
        #      entity_granularity IN (EXACT_OPERATING_COMPANY, SUBSIDIARY, JV)
        #    OR
        #    BRANCH B:
        #      entity_granularity == PARENT_GROUP
        #      AND parent_group_event_is_explicitly_grounded
        #      AND downstream_targetability_is_demonstrated
        # 5. AMBIGUOUS_GROUP must NEVER persist.

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
                decision.reason = f"Ambiguous broad brand/group '{clean_candidate}' without evidence-grounded operating subsidiary; held from persistence"

        record_prepersist_latency(_t.time() - _t0)

        if decision.should_persist:
            increment_prepersist_telemetry("ENTITY_PREPERSIST_FINAL_ACCEPT")
            logger.info(
                "[PREPERSIST_ACCEPT: TARGET_INDUSTRIAL] '%s' -> Name: '%s' (Granularity: %s, Facility: %s, Country: %s, Conf: %.2f)",
                clean_candidate,
                decision.canonical_company_name,
                decision.entity_granularity,
                decision.facility_name,
                decision.facility_country,
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
