"""Adaptive Targeted Research Service for Salesoorja Discovery Intelligence (Task 3D.1F).

Triggered for PROMISING_BUT_INCOMPLETE opportunities to perform
bounded, focused follow-up searches guarded by the Authoritative
LLM Information-Gain Gate.

Key Behaviors:
- Resolves missing facility locations, operational statuses, or commissioning dates.
- Gates every search via FollowupInformationGainGate (DeepSeek primary / Gemini fallback).
- Reuses existing evidence if already sufficient (USE_EXISTING_EVIDENCE).
- Enforces repetition stop rule (max 2 unsuccessful searches).
- Generates natural targeted queries without blind static negative keywords.
- Persists outcome to concurrency-safe PostgreSQL memory.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

from services.opportunity_reasoner import (
    opportunity_reasoner,
    CLASSIFICATION_STRONG,
    CLASSIFICATION_INCOMPLETE,
    CLASSIFICATION_WEAK,
)
from services.research_provider import ResearchProviderRouter
from services.page_content_fetcher import page_content_fetcher, STATUS_FETCH_SUCCESS
from services.search_result_triage import triage_and_rank_results
from services.structured_evidence_extractor import extract_structured_evidence
from services.followup_information_gain_gate import (
    followup_information_gain_gate,
    FollowupInformationGainGate,
)

logger = logging.getLogger(__name__)

FOLLOWUP_SEARCH_CAP = 2
MAX_FOLLOWUP_CALLS = 2
MAX_FOLLOWUP_ROUNDS = 2

# Natural targeted query templates without blind static negative tails (Amendment 6)
FOLLOWUP_TEMPLATES = {
    "EXACT_FACILITY": '"{company_name}" plant facility location city',
    "facility_city": '"{company_name}" plant facility location city',
    "CURRENT_EVENT_DATE": '"{company_name}" plant commissioning commercial production',
    "event_date": '"{company_name}" plant commissioning commercial production',
    "COMMISSIONING_STATUS": '"{company_name}" plant commissioning commercial production',
    "MACHINERY_CONTEXT": '"{company_name}" machinery installed testing metrology line',
}

FIELD_TO_FACT_MAP = {
    "EXACT_FACILITY": "FACILITY_LOCATION",
    "facility_city": "FACILITY_LOCATION",
    "facility_name": "FACILITY_LOCATION",
    "location": "FACILITY_LOCATION",
    "city": "FACILITY_LOCATION",
    "CURRENT_EVENT_DATE": "TRIGGER_DATE",
    "event_date": "TRIGGER_DATE",
    "date": "TRIGGER_DATE",
    "COMMISSIONING_STATUS": "COMMISSIONING_STATUS",
    "status": "COMMISSIONING_STATUS",
    "commissioning": "COMMISSIONING_STATUS",
    "MACHINERY_CONTEXT": "MACHINERY_CONTEXT",
    "machinery": "MACHINERY_CONTEXT",
    "capex": "CAPEX_EVENT",
}


class AdaptiveResearchService:
    """Executes bounded follow-up research guarded by LLM Information-Gain Gate."""

    def __init__(
        self,
        router: Optional[Any] = None,
        reasoner: Optional[Any] = None,
        gate: Optional[FollowupInformationGainGate] = None,
    ):
        self.router = router or ResearchProviderRouter()
        self.reasoner = reasoner or opportunity_reasoner
        self.gate = gate or followup_information_gain_gate

    def _map_field_to_missing_fact(self, field: str) -> str:
        """Map raw missing field names to standardized MISSING_FACT taxonomy."""
        clean = (field or "").strip()
        if clean in FIELD_TO_FACT_MAP:
            return FIELD_TO_FACT_MAP[clean]
        lower = clean.lower()
        for k, v in FIELD_TO_FACT_MAP.items():
            if k.lower() in lower:
                return v
        return "COMMISSIONING_STATUS"

    def _generate_fallback_query(
        self,
        company_name: str,
        missing_fact: str,
    ) -> str:
        """Generate clean, natural fallback query without static negative keyword tails."""
        template = FOLLOWUP_TEMPLATES.get(missing_fact)
        if template:
            return template.format(company_name=company_name)
        if missing_fact == "FACILITY_LOCATION":
            return f'"{company_name}" plant facility location city'
        elif missing_fact in {"TRIGGER_DATE", "COMMISSIONING_STATUS"}:
            return f'"{company_name}" plant commissioning commercial production'
        elif missing_fact == "CAPEX_EVENT":
            return f'"{company_name}" manufacturing plant capex expansion'
        return f'"{company_name}" manufacturing plant facility commissioning'

    def conduct_targeted_research(
        self,
        candidate_group: Dict[str, Any],
        initial_assessment: Dict[str, Any],
        sector: str = "",
        geography: str = "",
        db: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Conduct targeted searches to resolve missing fields, gated by Information-Gain Gate."""
        company_name = candidate_group.get("company_name", "Unknown")
        missing_fields = initial_assessment.get("missing_fields") or []

        current_cls = initial_assessment.get("opportunity_classification")
        if current_cls != CLASSIFICATION_INCOMPLETE:
            return {
                "final_assessment": initial_assessment,
                "searches_conducted": 0,
                "queries": [],
                "upgraded": False,
            }

        logger.info(
            "[FOLLOWUP_RESEARCH_STARTED] Company: %s | Missing: %s",
            company_name,
            missing_fields,
        )

        merged_candidate = dict(candidate_group)
        merged_titles = list(merged_candidate.get("titles", []))
        merged_snippets = list(merged_candidate.get("snippets", []))
        merged_urls = list(merged_candidate.get("source_urls", []))
        merged_dates = list(merged_candidate.get("dates", []))
        evidence_packets = list(merged_candidate.get("evidence_packets", []))

        executed_queries: List[str] = []
        pages_fetched_count = 0
        existing_facts_count = sum(len(p.get("structured_facts") or {}) for p in evidence_packets)

        # Iterate over missing fields, evaluating each through Information-Gain Gate
        for raw_field in missing_fields[:MAX_FOLLOWUP_CALLS]:
            missing_fact = self._map_field_to_missing_fact(raw_field)

            # Gate Decision: Ask DeepSeek / Gemini whether search is justified
            gate_decision = self.gate.evaluate_followup_search(
                company_name=company_name,
                missing_fact=missing_fact,
                current_evidence={
                    "titles": merged_titles,
                    "snippets": merged_snippets,
                    "source_urls": merged_urls,
                    "evidence_packets": evidence_packets,
                },
                candidate_group=merged_candidate,
                company_id=merged_candidate.get("company_id"),
                facility_name=merged_candidate.get("facility"),
                current_funnel_status=current_cls,
                db=db,
            )

            if not gate_decision.search_needed or gate_decision.expected_information_gain not in {"HIGH", "MEDIUM"}:
                logger.info(
                    "[FOLLOWUP_RESEARCH_BLOCKED] Company: %s | Fact: %s | Gain: %s | Action: %s | Reason: %s",
                    company_name,
                    missing_fact,
                    gate_decision.expected_information_gain,
                    gate_decision.alternative_action,
                    gate_decision.reason,
                )
                continue

            # Query is approved by Gate
            query_to_run = gate_decision.suggested_query or self._generate_fallback_query(company_name, missing_fact)
            executed_queries.append(query_to_run)

            logger.info(
                "[FOLLOWUP_SEARCH_EXECUTING] Company: %s | Fact: %s | Strategy: %s | Query: %s",
                company_name,
                missing_fact,
                gate_decision.research_strategy,
                query_to_run,
            )

            new_results_for_query: List[Dict[str, Any]] = []
            useful_urls: List[str] = []
            source_domains: Set[str] = set()

            try:
                search_res = self.router.search(
                    query=query_to_run,
                    num_results=3,
                    db=db,
                    use_cache=False,
                )
                raw_followup = search_res.get("results", []) or []
                triaged = triage_and_rank_results(raw_followup, max_to_fetch=1)

                for item in triaged:
                    url = str(item.get("url") or "")
                    title = str(item.get("title") or "")
                    snippet = str(item.get("snippet") or "")
                    date_val = str((item.get("metadata") or {}).get("date") or "")

                    if url:
                        useful_urls.append(url)
                        if "/" in url and len(url.split("/")) > 2:
                            source_domains.add(url.split("/")[2].replace("www.", ""))

                    if url and url not in merged_urls:
                        merged_urls.append(url)
                    if title and title not in merged_titles:
                        merged_titles.append(title)
                    if snippet and snippet not in merged_snippets:
                        merged_snippets.append(snippet)
                    if date_val and date_val not in merged_dates:
                        merged_dates.append(date_val)

                    # Bounded Page Fetch & Structured Fact Extraction
                    fetch_res = page_content_fetcher.fetch_page(
                        url=url,
                        db=db,
                        source_type="STRONG_SECONDARY" if item.get("triage_class") == "HIGH_VALUE_PRIMARY" else "SECONDARY",
                    )
                    pages_fetched_count += 1
                    if fetch_res.get("fetch_status") == STATUS_FETCH_SUCCESS:
                        packet = extract_structured_evidence(
                            url=url,
                            title=fetch_res.get("title") or title,
                            article_text=fetch_res.get("extracted_text", ""),
                            publication_date=fetch_res.get("publication_date") or date_val,
                            candidate_company=company_name,
                            source_type=fetch_res.get("source_type", "SECONDARY"),
                        )
                        evidence_packets.append(packet)
                        new_results_for_query.append(packet)

                # Determine if material new evidence was found
                current_facts_count = sum(len(p.get("structured_facts") or {}) for p in evidence_packets)
                has_new_facts = current_facts_count > existing_facts_count
                has_new_urls = bool(useful_urls and any(u not in candidate_group.get("source_urls", []) for u in useful_urls))
                has_material_evidence = has_new_facts or (len(raw_followup) > 0 and has_new_urls)
                evidence_type = "STRUCTURED_FACTS" if has_new_facts else ("CORROBORATING_URL" if has_material_evidence else "NONE")

                # Persist outcome to PostgreSQL memory
                self.gate.record_search_outcome(
                    company_name=company_name,
                    missing_fact=missing_fact,
                    query=query_to_run,
                    research_strategy=gate_decision.research_strategy,
                    result_count=len(raw_followup),
                    useful_urls=useful_urls,
                    new_evidence_found=has_material_evidence,
                    evidence_type_found=evidence_type,
                    source_domains=list(source_domains),
                    funnel_state_before=current_cls,
                    funnel_state_after=None,  # Updated after re-reasoning
                    llm_reasoning=gate_decision.reason,
                    company_id=merged_candidate.get("company_id"),
                    db=db,
                )

                existing_facts_count = current_facts_count

            except Exception as exc:
                logger.warning("Targeted research search error for '%s': %s", company_name, exc)

            if len(executed_queries) >= MAX_FOLLOWUP_CALLS:
                break

        merged_candidate["titles"] = merged_titles
        merged_candidate["snippets"] = merged_snippets
        merged_candidate["source_urls"] = merged_urls
        merged_candidate["dates"] = merged_dates
        merged_candidate["evidence_packets"] = evidence_packets

        # Track independent source count
        unique_domains = {url.split("/")[2].replace("www.", "") for url in merged_urls if "/" in url}
        merged_candidate["independent_source_count"] = len(unique_domains)

        # Re-reason with enriched, aggregated evidence
        re_assessment = self.reasoner.reason_opportunity(
            candidate_group=merged_candidate,
            sector=sector,
            geography=geography,
        )

        final_cls = re_assessment.get("opportunity_classification")
        upgraded = (final_cls == CLASSIFICATION_STRONG)

        logger.info(
            "[FOLLOWUP_RESEARCH_COMPLETE] Company: %s | Result: %s -> %s (searches: %d, pages: %d, upgraded: %s)",
            company_name,
            current_cls,
            final_cls,
            len(executed_queries),
            pages_fetched_count,
            upgraded,
        )

        return {
            "final_assessment": re_assessment,
            "searches_conducted": len(executed_queries),
            "pages_fetched": pages_fetched_count,
            "queries": executed_queries,
            "upgraded": upgraded,
            "merged_candidate": merged_candidate,
        }


adaptive_research_service = AdaptiveResearchService()
