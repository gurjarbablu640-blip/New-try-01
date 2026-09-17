"""Authoritative LLM Information-Gain Gate for Downstream Follow-Up Research (Task 3D.1F).

Enforces an intelligent, truth-preserving, information-gain boundary before any downstream
follow-up web search is issued for an existing company candidate.

Authoritative Rules & Architecture:
1. Missing Fact Specification: Every search must target an explicit missing fact
   (FACILITY_LOCATION, COMMISSIONING_STATUS, CAPEX_EVENT, etc.).
2. Deterministic Obvious Generic Blocker: Generic terms (Chemical, Steel, Plant) are blocked immediately.
3. Resolved Entity Requirement: Candidate must have a persisted Company ID or pass the Pre-Persistence
   Entity Truth Gate as TARGET_INDUSTRIAL_COMPANY.
4. Semantic Evidence Sufficiency (LLM): DeepSeek (primary) / Gemini (fallback) determines whether
   existing evidence already answers the missing fact -> USE_EXISTING_EVIDENCE.
5. Repetition Stop Rule: Maximum 2 unsuccessful searches per (COMPANY + MISSING_FACT).
   Subsequent searches allowed ONLY if the LLM provides an escalated source strategy
   (e.g. OFFICIAL_COMPANY, GOVERNMENT_SOURCE) with clear rationale.
6. Natural Query Generation: No static blind negative keyword tails (-stock -share -dividend).
   Negative keywords are included only when prior results contain financial noise and the LLM recommends it.
7. Durable Concurrency-Safe Memory: Backed by PostgreSQL (FollowupQueryMemoryRecord) with in-memory fallback.
8. Telemetry & Truth Preservation: Tracks productive outcomes preserved, replaced by existing evidence,
   and zero loss of qualified accounts.
"""
from __future__ import annotations

import json
import logging
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from database import SessionLocal
from models.followup_query_memory import FollowupQueryMemoryRecord
from services.llm_provider import DeepSeekProvider, GeminiProvider

logger = logging.getLogger(__name__)

# --- Standardized Taxonomies ---
VALID_MISSING_FACTS = {
    "FACILITY_LOCATION",
    "COMPANY_FACILITY_RELATIONSHIP",
    "TRIGGER_DATE",
    "COMMISSIONING_STATUS",
    "OPERATING_STATUS",
    "PLANT_OWNERSHIP",
    "CAPEX_EVENT",
    "SUBSIDIARY_RELATIONSHIP",
    "CURRENT_OPERATIONAL_EVIDENCE",
    "MACHINERY_CONTEXT",
}

RESEARCH_STRATEGIES = {
    "GENERAL_WEB",
    "OFFICIAL_COMPANY",
    "GOVERNMENT_SOURCE",
    "TRADE_MEDIA",
    "FACILITY_SPECIFIC",
    "EVENT_SPECIFIC",
    "OTHER",
}

EXPECTED_GAINS = {"HIGH", "MEDIUM", "LOW"}
ALTERNATIVE_ACTIONS = {"SEARCH", "USE_EXISTING_EVIDENCE", "HOLD", "OTHER_SOURCE"}

GENERIC_ENTITY_BLOCKLIST = {
    "chemical", "chemicals", "steel", "steels", "manufacturing", "electronics",
    "plant", "plants", "company", "companies", "industry", "industries",
    "engineering", "metals", "power", "textiles", "plastics", "cement",
    "pharma", "pharmaceuticals", "automotive", "solar", "battery",
    "enterprise", "enterprises", "corporation", "holdings", "technologies",
}

# --- Telemetry ---
_telemetry_lock = threading.Lock()
FOLLOWUP_TELEMETRY: Dict[str, int] = {
    "FOLLOWUP_RESEARCH_DECISIONS": 0,
    "FOLLOWUP_SEARCH_ALLOWED": 0,
    "FOLLOWUP_SEARCH_BLOCKED_LOW_GAIN": 0,
    "FOLLOWUP_SEARCH_BLOCKED_EXHAUSTED": 0,
    "FOLLOWUP_SEARCH_BLOCKED_GENERIC_ENTITY": 0,
    "FOLLOWUP_BLOCKED_UNRESOLVED_ENTITY": 0,
    "FOLLOWUP_EXISTING_EVIDENCE_REUSED": 0,
    "FOLLOWUP_SEARCHES_EXECUTED": 0,
    "FOLLOWUP_SEARCHES_WITH_NEW_EVIDENCE": 0,
    "FOLLOWUP_SEARCHES_WITHOUT_NEW_EVIDENCE": 0,
    "FOLLOWUP_QUERY_REPETITION_BLOCKED": 0,
    "FOLLOWUP_HOLD_TO_PASS": 0,
    "FOLLOWUP_UNKNOWN_TO_VERIFIED": 0,
    "FOLLOWUP_SERPER_CALLS_PER_ACCOUNT": 0,
    "FOLLOWUP_SERPER_CALLS_PER_FACILITY_PASS": 0,
    "FOLLOWUP_PRODUCTIVE_OUTCOME_PRESERVED": 0,
    "FOLLOWUP_PRODUCTIVE_OUTCOME_LOST": 0,
    "FOLLOWUP_PRODUCTIVE_CALL_REPLACED_BY_EXISTING_EVIDENCE": 0,
    "FOLLOWUP_PERSON_RESEARCH_QUERIES_SEPARATE": 0,
    "FOLLOWUP_LLM_EXISTING_EVIDENCE_SUFFICIENT": 0,
    "FOLLOWUP_LLM_NEW_SEARCH_JUSTIFIED": 0,
    "DEEPSEEK_FOLLOWUP_CALLS": 0,
    "GEMINI_FOLLOWUP_FALLBACKS": 0,
    "FOLLOWUP_PROVIDER_FAILURES": 0,
}


def increment_telemetry(metric: str, count: int = 1) -> None:
    with _telemetry_lock:
        FOLLOWUP_TELEMETRY[metric] = FOLLOWUP_TELEMETRY.get(metric, 0) + count


def get_telemetry() -> Dict[str, int]:
    with _telemetry_lock:
        return dict(FOLLOWUP_TELEMETRY)


def reset_telemetry() -> None:
    with _telemetry_lock:
        for k in FOLLOWUP_TELEMETRY:
            FOLLOWUP_TELEMETRY[k] = 0


@dataclass
class InformationGainDecision:
    """Structured decision returned by the Information-Gain Gate."""
    search_needed: bool
    missing_fact: str
    expected_information_gain: str
    reason: str
    suggested_query: str
    research_strategy: str
    alternative_action: str
    decision_type: str = "LLM_EVALUATED"
    provider_used: str = "DEEPSEEK"
    prior_attempt_count: int = 0
    blocked_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "search_needed": self.search_needed,
            "missing_fact": self.missing_fact,
            "expected_information_gain": self.expected_information_gain,
            "reason": self.reason,
            "suggested_query": self.suggested_query,
            "research_strategy": self.research_strategy,
            "alternative_action": self.alternative_action,
            "decision_type": self.decision_type,
            "provider_used": self.provider_used,
            "prior_attempt_count": self.prior_attempt_count,
            "blocked_reason": self.blocked_reason,
        }


GATE_SYSTEM_PROMPT = """You are the Authoritative Research Strategist and Information-Gain Gate for Salesoorja.
Your mission: evaluate whether another web search is genuinely needed for a company candidate to resolve an explicit missing fact, or if existing evidence is already sufficient, or if further search is wasteful.

EVALUATION RULES:
1. SEMANTIC EVIDENCE SUFFICIENCY: Check if the provided evidence ALREADY contains or sufficiently proves the missing fact.
   - If existing evidence establishes the fact (e.g. mentions plant location, commercial production status, capex amount, or operating entity), DO NOT SEARCH.
   - Set search_needed=false, alternative_action="USE_EXISTING_EVIDENCE", expected_information_gain="LOW".
2. EXPECTED INFORMATION GAIN:
   - "HIGH": Very likely to discover a specific, verifiable missing factual milestone that moves the account from HOLD/INCOMPLETE to PASS/VERIFIED.
   - "MEDIUM": Moderate chance of discovering the fact with an escalated or tailored strategy.
   - "LOW": High probability of returning duplicate facts, promotional noise, or static stock chatter. DO NOT SEARCH.
3. STRATEGY ESCALATION:
   - If prior general web searches produced no new evidence, do not repeat general web search.
   - Escalate strategy: "OFFICIAL_COMPANY" (newsroom, media releases), "GOVERNMENT_SOURCE" (regulatory filings, PCB, GIDC, MIDC, SIPCOT), or "TRADE_MEDIA".
   - If prior 2 searches failed and no genuinely alternate source strategy can be justified, set search_needed=false, alternative_action="HOLD".
4. NATURAL QUERY GENERATION:
   - Generate a targeted, natural query.
   - DO NOT blindly append static negative keywords like "-stock -share -dividend -trading -equity -sensex -nifty".
   - Only include negative keywords if prior search results exhibited financial market noise and excluding it specifically improves precision.

OUTPUT SCHEMA (return valid JSON only):
{
  "search_needed": true | false,
  "missing_fact": "<FACILITY_LOCATION | COMMISSIONING_STATUS | CAPEX_EVENT | ...>",
  "expected_information_gain": "HIGH" | "MEDIUM" | "LOW",
  "reason": "<Detailed rationale explaining evidence sufficiency or information gain>",
  "suggested_query": "<Targeted query or empty string if no search>",
  "research_strategy": "GENERAL_WEB" | "OFFICIAL_COMPANY" | "GOVERNMENT_SOURCE" | "TRADE_MEDIA" | "FACILITY_SPECIFIC" | "EVENT_SPECIFIC" | "OTHER",
  "alternative_action": "SEARCH" | "USE_EXISTING_EVIDENCE" | "HOLD" | "OTHER_SOURCE"
}"""


class FollowupInformationGainGate:
    """Authoritative gate controlling follow-up research for existing company candidates."""

    def __init__(
        self,
        primary_provider: Optional[Any] = None,
        fallback_provider: Optional[Any] = None,
        db_session: Optional[Session] = None,
    ):
        self.primary_provider = primary_provider or DeepSeekProvider()
        self.fallback_provider = fallback_provider or GeminiProvider()
        self.db_session = db_session
        self._in_memory_store: Dict[str, List[Dict[str, Any]]] = {}
        self._store_lock = threading.Lock()

    def _normalize_name(self, name: str) -> str:
        clean = (name or "").strip().lower()
        clean = re.sub(r"[^\w\s]", " ", clean)
        return " ".join(clean.split())

    def _normalize_query(self, query: str) -> str:
        clean = (query or "").strip().lower()
        clean = re.sub(r'["\'-]', " ", clean)
        clean = re.sub(r"(stock|share|dividend|trading|equity|sensex|nifty|brokerage|screener)", "", clean)
        return " ".join(clean.split())

    def is_generic_entity(self, name: str) -> bool:
        """Check if candidate name is an obvious isolated generic industry noun."""
        normalized = self._normalize_name(name)
        if not normalized:
            return True
        if normalized in GENERIC_ENTITY_BLOCKLIST:
            return True
        words = normalized.split()
        if len(words) == 1 and words[0] in GENERIC_ENTITY_BLOCKLIST:
            return True
        return False

    def is_entity_resolved(
        self,
        company_name: str,
        company_id: Optional[int] = None,
        candidate_group: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str]:
        """Verify whether entity is resolved as a real operating company (Amendment 5)."""
        # Obvious generic blocker
        if self.is_generic_entity(company_name):
            return False, f"Name '{company_name}' is an isolated generic industry noun"

        # Check A: Persisted Company ID + non-generic name
        if company_id is not None and company_id > 0:
            return True, "PERSISTED_COMPANY_RECORD"

        # Check candidate group metadata
        if candidate_group:
            if candidate_group.get("entity_verified") is True:
                return True, "CANDIDATE_ENTITY_VERIFIED"
            if candidate_group.get("is_target_industrial") is True and candidate_group.get("company_name"):
                return True, "PREPERSISTENCE_TARGET_INDUSTRIAL"
            # Check pre-persistence evaluation if available
            pre_eval = candidate_group.get("pre_persistence_evaluation")
            if pre_eval and isinstance(pre_eval, dict):
                if pre_eval.get("entity_type") == "TARGET_INDUSTRIAL_COMPANY" and pre_eval.get("should_persist"):
                    return True, "PREPERSISTENCE_PASSED"

        # Check B: Pre-persistence entity gate evaluation
        try:
            from services.pre_persistence_entity_gate import pre_persistence_entity_gate
            evidence_packet = {
                "title": (candidate_group.get("titles", [""])[0] if candidate_group and candidate_group.get("titles") else ""),
                "snippet": (candidate_group.get("snippets", [""])[0] if candidate_group and candidate_group.get("snippets") else ""),
                "url": (candidate_group.get("source_urls", [""])[0] if candidate_group and candidate_group.get("source_urls") else ""),
                "industry": candidate_group.get("sector", "") if candidate_group else "",
            }
            eval_res = pre_persistence_entity_gate.resolve_pre_persistence_decision(
                candidate_name=company_name,
                title=evidence_packet.get('title', ''),
                snippet=evidence_packet.get('snippet', ''),
                url=evidence_packet.get('url', ''),
                industry=evidence_packet.get('industry', ''),
            )
            if eval_res.should_persist and eval_res.entity_type == "TARGET_INDUSTRIAL_COMPANY":
                return True, "PREPERSISTENCE_EVALUATED_PASS"
            else:
                return False, f"Pre-persistence gate rejected: {eval_res.reason}"
        except Exception as exc:
            logger.debug("Pre-persistence evaluation failed: %s", exc)

        # Conservative default: if company name is multi-word with non-generic tokens, allow
        words = self._normalize_name(company_name).split()
        non_generic_words = [w for w in words if w not in GENERIC_ENTITY_BLOCKLIST and len(w) > 2]
        if len(non_generic_words) >= 2:
            return True, "MULTI_WORD_NON_GENERIC_STEM"

        return False, f"Entity '{company_name}' is ungrounded / unresolved"

    def get_prior_searches(
        self,
        company_name: str,
        missing_fact: str,
        db: Optional[Session] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve historical search records for (company, missing_fact) from PostgreSQL."""
        norm_entity = self._normalize_name(company_name)
        session = db or self.db_session
        records = []

        if session:
            try:
                db_records = (
                    session.query(FollowupQueryMemoryRecord)
                    .filter(
                        FollowupQueryMemoryRecord.normalized_operating_entity == norm_entity,
                        FollowupQueryMemoryRecord.missing_fact == missing_fact,
                    )
                    .order_by(FollowupQueryMemoryRecord.timestamp.asc())
                    .all()
                )
                records = [r.to_dict() for r in db_records]
            except Exception as exc:
                logger.debug("Failed reading Postgres followup memory: %s", exc)
                session.rollback()

        if not records:
            mem_key = f"{norm_entity}::{missing_fact}"
            with self._store_lock:
                records = list(self._in_memory_store.get(mem_key, []))

        return records

    def record_search_outcome(
        self,
        company_name: str,
        missing_fact: str,
        query: str,
        research_strategy: str = "GENERAL_WEB",
        result_count: int = 0,
        useful_urls: Optional[List[str]] = None,
        new_evidence_found: bool = False,
        evidence_type_found: Optional[str] = None,
        source_domains: Optional[List[str]] = None,
        funnel_state_before: Optional[str] = None,
        funnel_state_after: Optional[str] = None,
        llm_reasoning: Optional[str] = None,
        company_id: Optional[int] = None,
        db: Optional[Session] = None,
    ) -> None:
        """Persist follow-up search query outcome to PostgreSQL (concurrency-safe) and memory."""
        norm_entity = self._normalize_name(company_name)
        urls = useful_urls or []
        domains = source_domains or []
        now_dt = datetime.now(timezone.utc)

        # Update telemetry
        increment_telemetry("FOLLOWUP_SEARCHES_EXECUTED")
        if new_evidence_found:
            increment_telemetry("FOLLOWUP_SEARCHES_WITH_NEW_EVIDENCE")
            increment_telemetry("FOLLOWUP_PRODUCTIVE_OUTCOME_PRESERVED")
        else:
            increment_telemetry("FOLLOWUP_SEARCHES_WITHOUT_NEW_EVIDENCE")

        if funnel_state_before == "HOLD" and funnel_state_after == "PASS":
            increment_telemetry("FOLLOWUP_HOLD_TO_PASS")
        if funnel_state_before in {"UNKNOWN", None} and funnel_state_after in {"VERIFIED", "STRONG"}:
            increment_telemetry("FOLLOWUP_UNKNOWN_TO_VERIFIED")

        session_to_use = db or self.db_session
        own_session = False
        if not session_to_use and SessionLocal is not None:
            try:
                session_to_use = SessionLocal()
                own_session = True
            except Exception:
                session_to_use = None

        if session_to_use:
            try:
                record = FollowupQueryMemoryRecord(
                    company_id=company_id,
                    normalized_operating_entity=norm_entity,
                    missing_fact=missing_fact,
                    query=query,
                    timestamp=now_dt,
                    research_strategy=research_strategy,
                    result_count=result_count,
                    useful_urls=urls,
                    new_evidence_found=new_evidence_found,
                    evidence_type_found=evidence_type_found,
                    source_domains=domains,
                    funnel_state_before=funnel_state_before,
                    funnel_state_after=funnel_state_after,
                    llm_reasoning=llm_reasoning,
                )
                session_to_use.add(record)
                session_to_use.commit()
            except Exception as exc:
                logger.warning("Failed writing Postgres followup memory: %s", exc)
                session_to_use.rollback()
            finally:
                if own_session:
                    session_to_use.close()

        # Update in-memory fallback
        mem_key = f"{norm_entity}::{missing_fact}"
        entry = {
            "company_id": company_id,
            "normalized_operating_entity": norm_entity,
            "missing_fact": missing_fact,
            "query": query,
            "timestamp": now_dt.isoformat(),
            "research_strategy": research_strategy,
            "result_count": result_count,
            "useful_urls": urls,
            "new_evidence_found": new_evidence_found,
            "evidence_type_found": evidence_type_found,
            "source_domains": domains,
            "funnel_state_before": funnel_state_before,
            "funnel_state_after": funnel_state_after,
            "llm_reasoning": llm_reasoning,
        }
        with self._store_lock:
            self._in_memory_store.setdefault(mem_key, []).append(entry)

    def _call_llm_judge(self, user_prompt: str) -> Tuple[Optional[Dict[str, Any]], str]:
        """Query LLM judge with DeepSeek primary and Gemini fallback."""
        kwargs = {
            "system_prompt": GATE_SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": user_prompt}],
            "temperature": 0.0,
            "max_tokens": 400,
            "response_format": "json",
        }

        def _invoke(prov):
            if not prov:
                return None
            if hasattr(prov, "is_available") and not prov.is_available():
                return None
            if hasattr(prov, "complete"):
                return prov.complete(**kwargs)
            elif hasattr(prov, "call"):
                return prov.call(prompt=user_prompt, **kwargs)
            elif callable(prov):
                return prov(prompt=user_prompt, **kwargs)
            return None

        # 1. Primary: DeepSeek
        if self.primary_provider:
            try:
                increment_telemetry("DEEPSEEK_FOLLOWUP_CALLS")
                resp = _invoke(self.primary_provider)
                parsed = resp.parse_json() if resp and hasattr(resp, "parse_json") else None
                if not parsed and resp and hasattr(resp, "text"):
                    parsed = json.loads(resp.text)
                if parsed and isinstance(parsed, dict) and "search_needed" in parsed:
                    return parsed, "DEEPSEEK"
            except Exception as exc:
                logger.warning("[FOLLOWUP_GATE: PRIMARY_FAIL] %s, falling back", exc)
                increment_telemetry("FOLLOWUP_PROVIDER_FAILURES")

        # 2. Fallback: Gemini
        if self.fallback_provider:
            try:
                increment_telemetry("GEMINI_FOLLOWUP_FALLBACKS")
                resp = _invoke(self.fallback_provider)
                parsed = resp.parse_json() if resp and hasattr(resp, "parse_json") else None
                if not parsed and resp and hasattr(resp, "text"):
                    parsed = json.loads(resp.text)
                if parsed and isinstance(parsed, dict) and "search_needed" in parsed:
                    return parsed, "GEMINI"
            except Exception as exc:
                logger.warning("[FOLLOWUP_GATE: FALLBACK_FAIL] %s", exc)
                increment_telemetry("FOLLOWUP_PROVIDER_FAILURES")

        return None, "NONE"

    def evaluate_followup_search(
        self,
        company_name: str,
        missing_fact: str,
        current_evidence: Optional[Dict[str, Any]] = None,
        candidate_group: Optional[Dict[str, Any]] = None,
        company_id: Optional[int] = None,
        facility_name: Optional[str] = None,
        current_funnel_status: str = "INCOMPLETE",
        db: Optional[Session] = None,
    ) -> InformationGainDecision:
        """Core Gatekeeper: Evaluates whether a follow-up Serper call is justified."""
        increment_telemetry("FOLLOWUP_RESEARCH_DECISIONS")

        # Step 0: Validate missing_fact
        if not missing_fact or missing_fact not in VALID_MISSING_FACTS:
            return InformationGainDecision(
                search_needed=False,
                missing_fact=missing_fact or "UNSPECIFIED",
                expected_information_gain="LOW",
                reason=f"Missing fact '{missing_fact}' is invalid or unspecified",
                suggested_query="",
                research_strategy="OTHER",
                alternative_action="HOLD",
                decision_type="DETERMINISTIC_REJECT",
                blocked_reason="UNSPECIFIED_MISSING_FACT",
            )

        # Step 1: Obvious Generic Entity Block
        if self.is_generic_entity(company_name):
            increment_telemetry("FOLLOWUP_SEARCH_BLOCKED_GENERIC_ENTITY")
            return InformationGainDecision(
                search_needed=False,
                missing_fact=missing_fact,
                expected_information_gain="LOW",
                reason=f"Candidate entity '{company_name}' is an isolated generic industry noun (e.g. Chemical/Steel/Plant)",
                suggested_query="",
                research_strategy="OTHER",
                alternative_action="HOLD",
                decision_type="DETERMINISTIC_REJECT",
                blocked_reason="BLOCK_GENERIC_ENTITY",
            )

        # Step 2: Resolved Entity Verification (Amendment 5)
        is_resolved, resolve_reason = self.is_entity_resolved(
            company_name=company_name,
            company_id=company_id,
            candidate_group=candidate_group,
        )
        if not is_resolved:
            increment_telemetry("FOLLOWUP_BLOCKED_UNRESOLVED_ENTITY")
            return InformationGainDecision(
                search_needed=False,
                missing_fact=missing_fact,
                expected_information_gain="LOW",
                reason=f"Follow-up research blocked: Candidate '{company_name}' is not a resolved operating entity ({resolve_reason})",
                suggested_query="",
                research_strategy="OTHER",
                alternative_action="HOLD",
                decision_type="DETERMINISTIC_REJECT",
                blocked_reason="BLOCK_UNRESOLVED_ENTITY",
            )

        # Step 3: Fetch Prior Query History from Postgres
        prior_searches = self.get_prior_searches(
            company_name=company_name,
            missing_fact=missing_fact,
            db=db,
        )
        attempt_count = len(prior_searches)
        unsuccessful_searches = [s for s in prior_searches if not s.get("new_evidence_found")]
        unsuccessful_count = len(unsuccessful_searches)

        # Check if already successfully resolved
        successful_searches = [s for s in prior_searches if s.get("new_evidence_found")]
        if successful_searches:
            increment_telemetry("FOLLOWUP_EXISTING_EVIDENCE_REUSED")
            increment_telemetry("FOLLOWUP_PRODUCTIVE_CALL_REPLACED_BY_EXISTING_EVIDENCE")
            return InformationGainDecision(
                search_needed=False,
                missing_fact=missing_fact,
                expected_information_gain="LOW",
                reason=f"Missing fact '{missing_fact}' was already resolved in prior search (evidence: {successful_searches[-1].get('evidence_type_found')})",
                suggested_query="",
                research_strategy=successful_searches[-1].get("research_strategy", "GENERAL_WEB"),
                alternative_action="USE_EXISTING_EVIDENCE",
                decision_type="MEMORY_ALREADY_RESOLVED",
                prior_attempt_count=attempt_count,
            )

        # Step 4: Repetition Stop Rule (Section 8)
        # Default max: 2 unsuccessful searches.
        exhausted = unsuccessful_count >= 2

        # Step 5: Check Existing Evidence Corpus
        ev_dict = current_evidence or {}
        if candidate_group and not ev_dict:
            ev_dict = {
                "titles": candidate_group.get("titles", []),
                "snippets": candidate_group.get("snippets", []),
                "source_urls": candidate_group.get("source_urls", []),
                "evidence_packets": candidate_group.get("evidence_packets", []),
            }

        # Build LLM Prompt
        evidence_summary = self._summarize_evidence(ev_dict)
        prior_search_summary = self._summarize_prior_searches(prior_searches)

        user_prompt = f"""EVALUATE FOLLOW-UP RESEARCH INFORMATION GAIN:
Company: "{company_name}"
Facility: {json.dumps(facility_name)}
Missing Fact Required: "{missing_fact}"
Current Funnel Status: "{current_funnel_status}"

Current Evidence Corpus:
{evidence_summary}

Prior Searches Executed for ({company_name} + {missing_fact}):
{prior_search_summary}

Prior Unsuccessful Searches: {unsuccessful_count} / Maximum 2

TASK:
1. Does the Current Evidence Corpus ALREADY provide or substantiate the missing fact '{missing_fact}'?
2. If not, would another search yield HIGH or MEDIUM information gain?
   (If 2 prior searches failed with no new evidence, you may ONLY authorize search if recommending an escalated source strategy like OFFICIAL_COMPANY or GOVERNMENT_SOURCE with explicit justification. Otherwise output search_needed=false).
3. If search is needed, generate a natural targeted query (DO NOT append static negative keyword lists).

Return ONLY valid JSON matching the schema."""

        parsed, provider_used = self._call_llm_judge(user_prompt)

        if parsed:
            search_needed = bool(parsed.get("search_needed", False))
            exp_gain = str(parsed.get("expected_information_gain", "LOW")).upper()
            if exp_gain not in EXPECTED_GAINS:
                exp_gain = "LOW"
            alt_action = str(parsed.get("alternative_action", "HOLD")).upper()
            if alt_action not in ALTERNATIVE_ACTIONS:
                alt_action = "HOLD"
            reason = str(parsed.get("reason", "Evaluated by Information-Gain Gate"))
            suggested_query = str(parsed.get("suggested_query", "")).strip()
            research_strategy = str(parsed.get("research_strategy", "GENERAL_WEB")).upper()
            if research_strategy not in RESEARCH_STRATEGIES:
                research_strategy = "GENERAL_WEB"

            # Check if LLM determined existing evidence is sufficient
            if alt_action == "USE_EXISTING_EVIDENCE" or not search_needed:
                if alt_action == "USE_EXISTING_EVIDENCE":
                    increment_telemetry("FOLLOWUP_EXISTING_EVIDENCE_REUSED")
                    increment_telemetry("FOLLOWUP_LLM_EXISTING_EVIDENCE_SUFFICIENT")
                    increment_telemetry("FOLLOWUP_PRODUCTIVE_CALL_REPLACED_BY_EXISTING_EVIDENCE")
                else:
                    increment_telemetry("FOLLOWUP_SEARCH_BLOCKED_LOW_GAIN")

                return InformationGainDecision(
                    search_needed=False,
                    missing_fact=missing_fact,
                    expected_information_gain=exp_gain,
                    reason=reason,
                    suggested_query="",
                    research_strategy=research_strategy,
                    alternative_action=alt_action,
                    decision_type="LLM_EVALUATED",
                    provider_used=provider_used,
                    prior_attempt_count=attempt_count,
                )

            # Deterministic Guard: Repetition Stop Rule Enforcement (Section 8)
            if exhausted:
                # Only allowed if strategy is genuinely escalated and different from prior strategies
                prior_strategies = {s.get("research_strategy") for s in prior_searches}
                if research_strategy in prior_strategies or research_strategy == "GENERAL_WEB":
                    increment_telemetry("FOLLOWUP_SEARCH_BLOCKED_EXHAUSTED")
                    return InformationGainDecision(
                        search_needed=False,
                        missing_fact=missing_fact,
                        expected_information_gain="LOW",
                        reason=f"Blocked after 2 unsuccessful searches for ({company_name} + {missing_fact}). Strategy '{research_strategy}' is not an escalated new source strategy.",
                        suggested_query="",
                        research_strategy=research_strategy,
                        alternative_action="HOLD",
                        decision_type="DETERMINISTIC_REPETITION_STOP",
                        provider_used=provider_used,
                        prior_attempt_count=attempt_count,
                        blocked_reason="BLOCK_EXHAUSTED",
                    )

            # Check query deduplication against prior queries
            if suggested_query:
                norm_q = self._normalize_query(suggested_query)
                for s in prior_searches:
                    if self._normalize_query(s.get("query", "")) == norm_q:
                        increment_telemetry("FOLLOWUP_QUERY_REPETITION_BLOCKED")
                        return InformationGainDecision(
                            search_needed=False,
                            missing_fact=missing_fact,
                            expected_information_gain="LOW",
                            reason=f"Suggested query is a cosmetic duplicate of an exhausted prior query ('{s.get('query')}')",
                            suggested_query="",
                            research_strategy=research_strategy,
                            alternative_action="HOLD",
                            decision_type="DETERMINISTIC_DEDUPE_BLOCK",
                            provider_used=provider_used,
                            prior_attempt_count=attempt_count,
                            blocked_reason="BLOCK_REPETITION",
                        )

            # Execution Rule: search_needed == True AND expected_gain IN (HIGH, MEDIUM)
            if search_needed and exp_gain in {"HIGH", "MEDIUM"}:
                increment_telemetry("FOLLOWUP_SEARCH_ALLOWED")
                increment_telemetry("FOLLOWUP_LLM_NEW_SEARCH_JUSTIFIED")
                return InformationGainDecision(
                    search_needed=True,
                    missing_fact=missing_fact,
                    expected_information_gain=exp_gain,
                    reason=reason,
                    suggested_query=suggested_query,
                    research_strategy=research_strategy,
                    alternative_action="SEARCH",
                    decision_type="LLM_EVALUATED",
                    provider_used=provider_used,
                    prior_attempt_count=attempt_count,
                )
            else:
                increment_telemetry("FOLLOWUP_SEARCH_BLOCKED_LOW_GAIN")
                return InformationGainDecision(
                    search_needed=False,
                    missing_fact=missing_fact,
                    expected_information_gain="LOW",
                    reason=reason,
                    suggested_query="",
                    research_strategy=research_strategy,
                    alternative_action=alt_action,
                    decision_type="LLM_EVALUATED",
                    provider_used=provider_used,
                    prior_attempt_count=attempt_count,
                    blocked_reason="BLOCK_LOW_GAIN",
                )

        # Fallback if both LLMs fail: Safe Deterministic Fallback
        return self._deterministic_fallback_evaluation(
            company_name=company_name,
            missing_fact=missing_fact,
            ev_dict=ev_dict,
            prior_searches=prior_searches,
            attempt_count=attempt_count,
            unsuccessful_count=unsuccessful_count,
        )

    def _deterministic_fallback_evaluation(
        self,
        company_name: str,
        missing_fact: str,
        ev_dict: Dict[str, Any],
        prior_searches: List[Dict[str, Any]],
        attempt_count: int,
        unsuccessful_count: int,
    ) -> InformationGainDecision:
        """Safe deterministic fallback when LLM providers are unavailable."""
        if unsuccessful_count >= 2:
            increment_telemetry("FOLLOWUP_SEARCH_BLOCKED_EXHAUSTED")
            return InformationGainDecision(
                search_needed=False,
                missing_fact=missing_fact,
                expected_information_gain="LOW",
                reason=f"Deterministic fallback: Exceeded 2 unsuccessful attempts for ({company_name} + {missing_fact})",
                suggested_query="",
                research_strategy="OTHER",
                alternative_action="HOLD",
                decision_type="DETERMINISTIC_FALLBACK",
                prior_attempt_count=attempt_count,
                blocked_reason="BLOCK_EXHAUSTED",
            )

        # Check basic evidence presence
        combined_text = " ".join(
            ev_dict.get("titles", []) + ev_dict.get("snippets", [])
        ).lower()
        if missing_fact in {"COMMISSIONING_STATUS", "TRIGGER_DATE", "CAPEX_EVENT"}:
            if any(w in combined_text for w in ["commissioned", "inaugurated", "commercial production", "commenced production"]):
                increment_telemetry("FOLLOWUP_EXISTING_EVIDENCE_REUSED")
                return InformationGainDecision(
                    search_needed=False,
                    missing_fact=missing_fact,
                    expected_information_gain="LOW",
                    reason=f"Deterministic fallback: Existing text already references commissioning/commercial production",
                    suggested_query="",
                    research_strategy="GENERAL_WEB",
                    alternative_action="USE_EXISTING_EVIDENCE",
                    decision_type="DETERMINISTIC_FALLBACK",
                    prior_attempt_count=attempt_count,
                )

        # Natural clean query without static negative tails
        query = f'"{company_name}" plant {missing_fact.replace("_", " ").lower()}'
        increment_telemetry("FOLLOWUP_SEARCH_ALLOWED")
        return InformationGainDecision(
            search_needed=True,
            missing_fact=missing_fact,
            expected_information_gain="MEDIUM",
            reason=f"Deterministic fallback: Attempt {attempt_count + 1} for unresolved {missing_fact}",
            suggested_query=query,
            research_strategy="GENERAL_WEB",
            alternative_action="SEARCH",
            decision_type="DETERMINISTIC_FALLBACK",
            prior_attempt_count=attempt_count,
        )

    def _summarize_evidence(self, ev_dict: Dict[str, Any]) -> str:
        lines = []
        titles = ev_dict.get("titles", [])
        snippets = ev_dict.get("snippets", [])
        packets = ev_dict.get("evidence_packets", [])

        for idx, t in enumerate(titles[:3]):
            snip = snippets[idx] if idx < len(snippets) else ""
            lines.append(f"- Title: {t} | Snippet: {snip[:250]}")

        for p in packets[:2]:
            facts = p.get("structured_facts") or {}
            ext = p.get("extracted_text", "")[:400]
            lines.append(f"- Structured Facts: {json.dumps(facts)} | Page Text: {ext}")

        return "\n".join(lines) if lines else "No prior evidence recorded."

    def _summarize_prior_searches(self, prior_searches: List[Dict[str, Any]]) -> str:
        if not prior_searches:
            return "No prior searches executed for this missing fact."
        lines = []
        for idx, s in enumerate(prior_searches):
            q = s.get("query", "")
            strat = s.get("research_strategy", "")
            cnt = s.get("result_count", 0)
            new_ev = s.get("new_evidence_found", False)
            ev_type = s.get("evidence_type_found", "None")
            lines.append(
                f"Attempt {idx+1}: Query='{q}' | Strategy={strat} | Results={cnt} | "
                f"NewEvidence={new_ev} | TypeFound={ev_type}"
            )
        return "\n".join(lines)


# Global singleton instance
followup_information_gain_gate = FollowupInformationGainGate()
