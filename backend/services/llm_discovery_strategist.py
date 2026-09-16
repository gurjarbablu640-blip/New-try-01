"""LLM-First Discovery Search Strategist for Salesoorja (Task 3D.1A).

Adaptive, natural-language search query generation:
- DeepSeek primary (HiveProvider with DeepSeek-V4.1-Flash)
- Gemini fallback (GeminiProvider)
- Deterministic planner fallback (DiscoveryQueryPlanner)
- Summarized context (recent exhausted, recent successful, performance distributions, bottlenecks)
- Multi-candidate proposal (up to 3 candidates with search_goal, expected_signal, confidence)
- Natural search query style (avoids rigid quotes, keyword soup, large negative tails)
- Adaptive relaxation on prior failure
- Success exploitation on prior discovery
- Deterministic sanity guard (length, syntax, token repetition, keyword spam)
- 24-hour query cooldown enforcement
- Telemetry instrumentation
"""
from __future__ import annotations

import json
import logging
import re
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from database import SessionLocal
from models.discovery_query_log import DiscoveryQueryLog
from models.company import Company
from services.discovery_query_memory import (
    discovery_query_memory,
    normalize_discovery_query,
    STATE_SUCCESS_PRODUCTIVE,
    STATE_SUCCESS_EXHAUSTED,
)
from services.llm_provider import DeepSeekProvider, GeminiProvider

logger = logging.getLogger(__name__)

# Telemetry counters
_telemetry_lock = threading.Lock()
_telemetry_counters: Dict[str, int] = {
    "DISCOVERY_LLM_PLANNER_CALLS": 0,
    "DISCOVERY_LLM_PRIMARY_SUCCESS": 0,
    "DISCOVERY_LLM_PRIMARY_FAILURE": 0,
    "DISCOVERY_LLM_FALLBACK_USED": 0,
    "DISCOVERY_LLM_CANDIDATES_PROPOSED": 0,
    "DISCOVERY_LLM_QUERY_SELECTED": 0,
    "DISCOVERY_LLM_QUERY_REJECTED_SANITY": 0,
    "DISCOVERY_LLM_QUERY_REJECTED_COOLDOWN": 0,
}


def increment_telemetry(key: str, amount: int = 1) -> None:
    with _telemetry_lock:
        _telemetry_counters[key] = _telemetry_counters.get(key, 0) + amount


def get_telemetry() -> Dict[str, int]:
    with _telemetry_lock:
        return dict(_telemetry_counters)


def reset_telemetry() -> None:
    with _telemetry_lock:
        for k in _telemetry_counters:
            _telemetry_counters[k] = 0


# System Prompt
STRATEGIST_SYSTEM_PROMPT = """You are the Senior Search Intelligence Strategist for Salesoorja, an industrial B2B intelligence platform operating in India.
Your mission is to generate high-yield, natural-language Google/Serper discovery queries that uncover real industrial manufacturing plant expansions, new facility setups, greenfield/brownfield capex investments, and newly commissioned manufacturing units.

CRITICAL SEARCH QUERY GUIDELINES:
1. PREFER NATURAL SEARCH LANGUAGE:
   - Use search syntax that mirrors how high-quality industrial news and trade publications write about manufacturing developments.
   - CONCEPTUAL EXAMPLES:
     * automotive component plant expansion Chakan
     * new electronics manufacturing facility Tamil Nadu
     * solar manufacturing plant Gujarat expansion
     * pharma manufacturing project Telangana commissioning
     * manufacturers Pithampur new plant
   - These are conceptual examples only; do not copy them verbatim if another sector/geography is requested.

2. AVOID OVERCONSTRAINED QUERY HABITS:
   - NEVER put multiple separate quoted phrases (e.g. DO NOT do: "Gujarat" "automotive" "capex").
   - NEVER append long negative keyword tails (e.g. DO NOT append "-stock -share -brokerage -screener -dividend -trading -equity -sensex -nifty").
   - DO NOT force artificial years unless searching for recent announcements.
   - DO NOT force calibration or instrumentation keywords into the initial discovery query.
   - Avoid keyword soup (unconnected lists of keywords).

3. ADAPTIVE RELAXATION:
   - If recent queries for this sector/corridor resulted in zero results or exhaustion, RELAX the query:
     Progress from specific trigger -> broader event -> sector + geography -> industrial cluster -> company/manufacturer discovery.
   - Do NOT simply delete one quoted word and retry mechanically.

4. SUCCESS EXPLOITATION:
   - If a recent query succeeded in finding a company, industrial estate, or cluster, explore nearby adjacent opportunities (e.g. nearby suppliers, related component manufacturers, or additional facilities in that industrial park or cluster).

5. OUTPUT FORMAT:
   Return ONLY a valid JSON object with up to 3 candidate queries matching this exact schema:
   {
     "strategy_summary": "<1-2 sentence description of the search rationale>",
     "candidates": [
       {
         "query": "<natural search query string, 10-120 chars>",
         "search_goal": "<what this query specifically aims to discover>",
         "search_lane": "<EVENT_EXPANSION | CAPEX_PROJECT | CLUSTER_EXPLOITATION | MANUFACTURER_DISCOVERY>",
         "sector": "<manufacturing sector>",
         "geography": {
           "country": "India",
           "state": "<State or Pan-India>",
           "cluster": "<Industrial corridor/cluster/city if applicable, or null>"
         },
         "expected_signal": "<e.g. facility groundbreaking, plant inauguration, capex announcement>",
         "reason": "<why this angle was chosen>",
         "confidence": <float between 0.1 and 1.0>
       }
     ]
   }
"""


class LLMDiscoveryStrategist:
    """Intelligent adaptive search query strategist using DeepSeek primary, Gemini fallback."""

    def __init__(
        self,
        primary_provider: Optional[Any] = None,
        fallback_provider: Optional[Any] = None,
        memory: Optional[Any] = None,
    ):
        self.primary_provider = primary_provider or DeepSeekProvider()
        self.fallback_provider = fallback_provider or GeminiProvider()
        self.memory = memory or discovery_query_memory

    # ── Context Summarization ────────────────────────────────────────────────

    def build_search_context(
        self,
        db: Optional[Session],
        sector: str,
        geography: str,
        trigger: Optional[str] = None,
        search_lane: str = "EVENT_EXPANSION",
    ) -> Dict[str, Any]:
        """Assemble structured, summarized intelligence context for the LLM."""
        now = datetime.now(timezone.utc)
        current_date_str = now.strftime("%Y-%m-%d")

        context: Dict[str, Any] = {
            "current_date": current_date_str,
            "target_sector": sector,
            "target_geography": geography,
            "target_trigger": trigger or "plant_expansion",
            "search_lane": search_lane,
            "funnel_bottleneck": "High zero-result rate from rigid quotes; require natural language discovery",
            "recent_exhausted_queries": [],
            "recent_successful_queries": [],
            "recent_companies_discovered": [],
            "active_cooldown_queries": [],
            "performance_summary": {
                "top_productive_archetypes": ["NEWS_NATURAL (100% productive)", "INVESTMENT_CAPEX (100% productive)"],
                "worst_exhausted_archetypes": ["EVENT_FIRST with rigid quotes (67% zero-results)"],
                "strongest_sectors": ["Solar & Renewable", "Automotive & Components", "EV & Battery Systems", "Semiconductor EMS"],
                "weakest_sectors": ["Metals & Advanced Alloys (100% zero)", "Telecom (100% zero)", "Packaging (89% zero)"],
            },
        }

        should_close = False
        if db is None:
            try:
                db = SessionLocal()
                should_close = True
            except Exception:
                return context

        try:
            # 1. Fetch last 5 exhausted queries
            exhausted = (
                db.query(DiscoveryQueryLog)
                .filter(DiscoveryQueryLog.execution_state == STATE_SUCCESS_EXHAUSTED)
                .order_by(DiscoveryQueryLog.id.desc())
                .limit(5)
                .all()
            )
            context["recent_exhausted_queries"] = [
                {"query": q.query, "sector": q.sector, "geo": q.geography, "results": q.results_count}
                for q in exhausted
            ]

            # 2. Fetch last 5 productive queries
            productive = (
                db.query(DiscoveryQueryLog)
                .filter(DiscoveryQueryLog.execution_state == STATE_SUCCESS_PRODUCTIVE)
                .order_by(DiscoveryQueryLog.id.desc())
                .limit(5)
                .all()
            )
            context["recent_successful_queries"] = [
                {
                    "query": q.query,
                    "sector": q.sector,
                    "geo": q.geography,
                    "companies": q.new_companies,
                    "opps": q.strong_opportunities,
                }
                for q in productive
            ]

            # 3. Fetch 5 recently created companies
            recent_cos = (
                db.query(Company)
                .order_by(Company.id.desc())
                .limit(5)
                .all()
            )
            context["recent_companies_discovered"] = [
                {"name": c.name, "industry": c.industry, "state": c.state}
                for c in recent_cos if c.name
            ]

            # 4. Fetch recent query cooldowns (last 10 queries executed in 24h)
            recent_all = (
                db.query(DiscoveryQueryLog)
                .order_by(DiscoveryQueryLog.id.desc())
                .limit(10)
                .all()
            )
            context["active_cooldown_queries"] = [q.normalized_query for q in recent_all if q.normalized_query]

        except Exception as exc:
            logger.debug("Error assembling search context from DB: %s", exc)
        finally:
            if should_close and db is not None:
                db.close()

        return context

    # ── Deterministic Query Sanity Guard ─────────────────────────────────────

    def validate_candidate_sanity(
        self,
        query: str,
        seen_in_batch: Optional[set] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Validate candidate query against objective sanity rules.

        Rejects only unambiguous problems:
        - empty or whitespace
        - too short (< 10 chars or < 2 words)
        - too long (> 200 chars)
        - exact duplicate in same batch
        - unbalanced quotes
        - unbalanced parentheses
        - obvious token repetition (e.g. word repeated > 2 times consecutively)
        - excessive keyword spam or negative keyword dumps
        """
        if not query or not query.strip():
            return False, "Query is empty"

        q = query.strip()

        if len(q) < 10:
            return False, f"Query too short ({len(q)} chars; minimum 10)"
        if len(q) > 200:
            return False, f"Query too long ({len(q)} chars; maximum 200)"

        words = q.split()
        if len(words) < 2:
            return False, "Query has fewer than 2 words"

        # Check exact duplicate in current proposal batch
        norm = normalize_discovery_query(q)
        if seen_in_batch is not None:
            if norm in seen_in_batch:
                return False, f"Duplicate query in same batch: '{q}'"
            seen_in_batch.add(norm)

        # Check quote balance
        if q.count('"') % 2 != 0 or q.count("'") % 2 != 0:
            return False, "Unbalanced quotation marks in query"

        # Check parentheses balance
        if q.count("(") != q.count(")"):
            return False, "Unbalanced parentheses in query"

        # Check consecutive token repetition (e.g. "solar solar solar")
        for i in range(len(words) - 2):
            w1, w2, w3 = words[i].lower(), words[i + 1].lower(), words[i + 2].lower()
            if w1 == w2 == w3 and len(w1) > 2:
                return False, f"Obvious token repetition detected: '{w1} {w2} {w3}'"

        # Reject massive negative keyword tails (> 3 negative terms)
        neg_count = sum(1 for w in words if w.startswith("-") and len(w) > 1)
        if neg_count > 3:
            return False, f"Excessive negative keyword tail ({neg_count} negative terms)"

        # Check for multiple quoted phrases (discourage overconstrained syntax)
        quoted_phrases = re.findall(r'"[^"]+"', q)
        if len(quoted_phrases) > 2:
            return False, f"Overconstrained syntax: {len(quoted_phrases)} separate quoted phrases"

        return True, None

    # ── Cooldown Check ───────────────────────────────────────────────────────

    def check_cooldown(
        self,
        query: str,
        db: Optional[Session] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Check if query is in 24-hour cooldown memory."""
        norm = normalize_discovery_query(query)
        if self.memory.is_query_in_cooldown(norm, page=1, db=db):
            return False, f"Query is in 24-hour cooldown memory: '{norm}'"
        return True, None

    # ── Candidate Selection ──────────────────────────────────────────────────

    def select_strongest_candidate(
        self,
        candidates: List[Dict[str, Any]],
        db: Optional[Session] = None,
    ) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
        """Filter candidates by sanity guard and cooldown, selecting highest confidence valid candidate.

        Returns: (selected_candidate, evaluation_log)
        """
        seen_in_batch: set = set()
        evaluation_log: List[Dict[str, Any]] = []

        # Sort candidates descending by confidence
        sorted_candidates = sorted(
            candidates,
            key=lambda c: float(c.get("confidence", 0.5)),
            reverse=True,
        )

        selected = None
        for cand in sorted_candidates:
            query = str(cand.get("query", "")).strip()

            # 1. Sanity Guard
            is_sane, sanity_reason = self.validate_candidate_sanity(query, seen_in_batch=seen_in_batch)
            if not is_sane:
                increment_telemetry("DISCOVERY_LLM_QUERY_REJECTED_SANITY")
                evaluation_log.append({
                    "query": query,
                    "status": "REJECTED_SANITY",
                    "reason": sanity_reason,
                    "confidence": cand.get("confidence"),
                })
                continue

            # 2. Cooldown Check
            is_fresh, cooldown_reason = self.check_cooldown(query, db=db)
            if not is_fresh:
                increment_telemetry("DISCOVERY_LLM_QUERY_REJECTED_COOLDOWN")
                evaluation_log.append({
                    "query": query,
                    "status": "REJECTED_COOLDOWN",
                    "reason": cooldown_reason,
                    "confidence": cand.get("confidence"),
                })
                continue

            # Candidate is valid and fresh
            evaluation_log.append({
                "query": query,
                "status": "ACCEPTED",
                "reason": "Passed sanity guard and cooldown check",
                "confidence": cand.get("confidence"),
            })

            if selected is None:
                selected = cand
                increment_telemetry("DISCOVERY_LLM_QUERY_SELECTED")

        return selected, evaluation_log

    # ── LLM Invocation & Structured Parsing ──────────────────────────────────

    def _call_provider_for_candidates(
        self,
        provider: Any,
        user_prompt: str,
        provider_name: str,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Call LLM provider and parse structured JSON with 1 repair attempt."""
        try:
            resp = provider.complete(
                system_prompt=STRATEGIST_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
                temperature=0.25,
                max_tokens=800,
                response_format="json",
            )
            raw_text = resp.text if resp else ""
            parsed = resp.parse_json() if resp else None

            if parsed and isinstance(parsed, dict) and "candidates" in parsed:
                return parsed, None

            # Repair attempt if output was slightly unparseable
            repair_prompt = (
                f"Your previous response could not be parsed as valid JSON or lacked the 'candidates' array.\n"
                f"Raw response was:\n{raw_text[:400]}\n\n"
                f"Please return ONLY a valid JSON object matching the required schema with 'strategy_summary' and 'candidates'."
            )
            repair_resp = provider.complete(
                system_prompt=STRATEGIST_SYSTEM_PROMPT,
                messages=[
                    {"role": "user", "content": user_prompt},
                    {"role": "assistant", "content": raw_text[:400]},
                    {"role": "user", "content": repair_prompt},
                ],
                temperature=0.1,
                max_tokens=800,
                response_format="json",
            )
            repaired_parsed = repair_resp.parse_json() if repair_resp else None
            if repaired_parsed and isinstance(repaired_parsed, dict) and "candidates" in repaired_parsed:
                return repaired_parsed, None

            return None, f"Failed to parse structured output from {provider_name} after repair attempt"

        except Exception as exc:
            return None, f"{provider_name} error: {exc}"

    # ── Main Strategic Planning Entry Point ──────────────────────────────────

    def plan_query(
        self,
        db: Optional[Session] = None,
        sector: str = "Automotive & Auto Components",
        geography: str = "Pan-India",
        trigger: Optional[str] = None,
        search_lane: str = "EVENT_EXPANSION",
        strategy_decision_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Main entry point: generates up to 3 candidate queries, validates, and selects the strongest.

        DeepSeek (Primary) -> Gemini (Fallback) -> Deterministic Planner (Final Fallback).
        """
        increment_telemetry("DISCOVERY_LLM_PLANNER_CALLS")

        # 1. Build rich, summarized context
        search_context = self.build_search_context(
            db=db,
            sector=sector,
            geography=geography,
            trigger=trigger,
            search_lane=search_lane,
        )

        user_prompt = (
            f"Generate high-yield industrial discovery search queries for:\n"
            f"- Sector: {sector}\n"
            f"- Geography/Corridor: {geography}\n"
            f"- Search Lane: {search_lane}\n"
            f"- Target Trigger: {trigger or 'plant_expansion'}\n\n"
            f"Context:\n{json.dumps(search_context, indent=2)}\n\n"
            f"Propose up to 3 candidate natural search queries following the natural language and adaptive relaxation rules."
        )

        selected_candidate = None
        eval_log = []
        strategy_summary = ""
        provider_used = None
        candidates_proposed = []

        # 2. Try DeepSeek (PRIMARY)
        if self.primary_provider and self.primary_provider.is_available():
            parsed_data, err = self._call_provider_for_candidates(
                self.primary_provider, user_prompt, "DeepSeek"
            )
            if parsed_data:
                candidates = parsed_data.get("candidates", [])[:3]
                increment_telemetry("DISCOVERY_LLM_CANDIDATES_PROPOSED", len(candidates))
                selected, log = self.select_strongest_candidate(candidates, db=db)
                if selected:
                    increment_telemetry("DISCOVERY_LLM_PRIMARY_SUCCESS")
                    selected_candidate = selected
                    eval_log = log
                    strategy_summary = parsed_data.get("strategy_summary", "")
                    provider_used = "DeepSeek"
                    candidates_proposed = candidates
                else:
                    increment_telemetry("DISCOVERY_LLM_PRIMARY_FAILURE")
                    logger.warning("DeepSeek proposed %d candidates but none passed sanity/cooldown.", len(candidates))
            else:
                increment_telemetry("DISCOVERY_LLM_PRIMARY_FAILURE")
                logger.warning("DeepSeek call failed: %s; falling back to Gemini.", err)
        else:
            increment_telemetry("DISCOVERY_LLM_PRIMARY_FAILURE")
            logger.info("DeepSeek provider not available; trying Gemini fallback.")

        # 3. Try Gemini (FALLBACK) if DeepSeek did not produce an accepted query
        if not selected_candidate and self.fallback_provider and self.fallback_provider.is_available():
            increment_telemetry("DISCOVERY_LLM_FALLBACK_USED")
            parsed_data, err = self._call_provider_for_candidates(
                self.fallback_provider, user_prompt, "Gemini"
            )
            if parsed_data:
                candidates = parsed_data.get("candidates", [])[:3]
                increment_telemetry("DISCOVERY_LLM_CANDIDATES_PROPOSED", len(candidates))
                selected, log = self.select_strongest_candidate(candidates, db=db)
                if selected:
                    selected_candidate = selected
                    eval_log = log
                    strategy_summary = parsed_data.get("strategy_summary", "")
                    provider_used = "Gemini"
                    candidates_proposed = candidates
                else:
                    logger.warning("Gemini proposed %d candidates but none passed sanity/cooldown.", len(candidates))
            else:
                logger.warning("Gemini fallback call failed: %s", err)

        # 4. Final Fallback to Current Deterministic Planner if both LLMs fail
        if not selected_candidate:
            logger.info("Both LLMs unavailable or exhausted; falling back to deterministic planner.")
            from services.discovery_query_planner import discovery_query_planner
            fallback_plan = discovery_query_planner.get_next_planned_query(
                db=db,
                preferred_sector=sector,
                preferred_geo=geography,
                preferred_trigger=trigger,
                strategy_decision_id=strategy_decision_id,
            )
            return {
                "query": fallback_plan["query"],
                "normalized_query": fallback_plan["normalized_query"],
                "page": 1,
                "sector": fallback_plan["sector"],
                "trigger": fallback_plan["trigger"],
                "geography": fallback_plan["geography"],
                "weight": fallback_plan.get("weight", 1.0),
                "rationale": f"Deterministic fallback: {fallback_plan.get('rationale', '')}",
                "analyst_decision_id": strategy_decision_id,
                "was_substituted": fallback_plan.get("was_substituted", False),
                "substitution_reason": fallback_plan.get("substitution_reason"),
                "provider": "deterministic_fallback",
                "strategy_summary": "Deterministic planner template fallback",
                "candidates_proposed": [],
                "evaluation_log": eval_log,
                "confidence": 0.5,
            }

        # Return chosen LLM candidate query
        final_query = selected_candidate["query"].strip()
        final_norm = normalize_discovery_query(final_query)
        cand_geo = selected_candidate.get("geography", {})
        cand_geo_str = (
            cand_geo.get("state") or geography
            if isinstance(cand_geo, dict)
            else str(cand_geo)
        )

        return {
            "query": final_query,
            "normalized_query": final_norm,
            "page": 1,
            "sector": selected_candidate.get("sector") or sector,
            "trigger": trigger or "plant_expansion",
            "geography": cand_geo_str,
            "weight": 1.5,
            "rationale": f"LLM Strategist ({provider_used}): {selected_candidate.get('reason', '')}",
            "analyst_decision_id": strategy_decision_id,
            "was_substituted": False,
            "substitution_reason": None,
            "provider": provider_used,
            "strategy_summary": strategy_summary,
            "search_goal": selected_candidate.get("search_goal"),
            "search_lane": selected_candidate.get("search_lane"),
            "expected_signal": selected_candidate.get("expected_signal"),
            "confidence": float(selected_candidate.get("confidence", 0.8)),
            "candidates_proposed": candidates_proposed,
            "evaluation_log": eval_log,
        }


llm_discovery_strategist = LLMDiscoveryStrategist()
