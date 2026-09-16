"""Adaptive Targeted Research Service for Salesoorja Discovery Intelligence.

Triggered for PROMISING_BUT_INCOMPLETE opportunities to perform
bounded, focused follow-up searches (cap <= 2 searches per company) to
resolve missing facility locations, operational statuses, or commissioning dates.
Fetches top candidate result page, extracts structured facts, aggregates evidence,
and re-reasons with Opportunity Reasoner.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

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

logger = logging.getLogger(__name__)

FOLLOWUP_SEARCH_CAP = 2
MAX_FOLLOWUP_CALLS = 2
MAX_FOLLOWUP_ROUNDS = 2

FOLLOWUP_TEMPLATES = {
    "EXACT_FACILITY": '"{company_name}" plant facility location city new -stock -share -dividend -trading',
    "facility_city": '"{company_name}" plant facility location city new -stock -share -dividend -trading',
    "CURRENT_EVENT_DATE": '"{company_name}" plant commissioning commercial production -stock -share -dividend -trading',
    "event_date": '"{company_name}" plant commissioning commercial production -stock -share -dividend -trading',
    "COMMISSIONING_STATUS": '"{company_name}" plant commissioning commercial production -stock -share -dividend -trading',
    "MACHINERY_CONTEXT": '"{company_name}" machinery installed testing metrology line -stock -share',
}


class AdaptiveResearchService:
    """Executes bounded follow-up research to ground promising but incomplete leads."""

    def __init__(self, router=None, reasoner=None):
        self.router = router or ResearchProviderRouter()
        self.reasoner = reasoner or opportunity_reasoner

    def _generate_targeted_queries(
        self,
        candidate_group: Dict[str, Any],
        missing_fields: List[str],
        geography: str = "",
    ) -> List[str]:
        """Generate deterministic queries based on specific missing factual fields."""
        company_name = candidate_group.get("company_name", "Unknown")
        target_queries: List[str] = []
        for field in missing_fields:
            template = FOLLOWUP_TEMPLATES.get(field)
            if template:
                q = template.format(company_name=company_name)
                if q not in target_queries:
                    target_queries.append(q)
            elif any(k in field.lower() for k in ("facility", "city", "location")):
                q = f'"{company_name}" plant facility location city new -stock -share -dividend -trading'
                if q not in target_queries:
                    target_queries.append(q)
            elif any(k in field.lower() for k in ("date", "status", "commission")):
                q = f'"{company_name}" plant commissioning commercial production -stock -share -dividend -trading'
                if q not in target_queries:
                    target_queries.append(q)
            elif any(k in field.lower() for k in ("machinery", "equipment")):
                q = f'"{company_name}" machinery installed testing metrology line -stock -share'
                if q not in target_queries:
                    target_queries.append(q)

        if not target_queries:
            target_queries.append(
                f'"{company_name}" manufacturing plant facility "commissioning" OR "expansion" -stock -share'
            )
        return target_queries[:MAX_FOLLOWUP_CALLS]

    def _aggregate_evidence(
        self,
        existing_packets: List[Dict[str, Any]],
        new_results: List[Dict[str, Any]],
        company_name: str = "",
    ) -> List[Dict[str, Any]]:
        """Aggregate evidence packets with syndication deduplication."""
        aggregated = list(existing_packets)
        seen_domains = set()
        for p in aggregated:
            u = p.get("url") or ""
            if "/" in u:
                parts = u.split("/")
                if len(parts) > 2:
                    seen_domains.add(parts[2].replace("www.", "").lower())

        for item in new_results:
            url = str(item.get("url") or "")
            domain = url.split("/")[2].replace("www.", "").lower() if "/" in url and len(url.split("/")) > 2 else ""
            is_duplicate = False
            item_title = (item.get("title") or "").casefold().strip()
            for p in aggregated:
                p_title = (p.get("title") or "").casefold().strip()
                if item_title and p_title and (item_title in p_title or p_title in item_title):
                    is_duplicate = True
                    break

            indep_count = 0 if (is_duplicate or (domain and domain in seen_domains)) else 1
            if domain:
                seen_domains.add(domain)

            aggregated.append({
                "url": url,
                "title": item.get("title") or "",
                "snippet": item.get("snippet") or "",
                "extracted_text": item.get("snippet") or "",
                "structured_facts": {"company": company_name},
                "independent_source_count": indep_count,
            })
        return aggregated

    def conduct_targeted_research(
        self,
        candidate_group: Dict[str, Any],
        initial_assessment: Dict[str, Any],
        sector: str = "",
        geography: str = "",
        db: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Conduct targeted searches to resolve missing fields for an incomplete opportunity."""
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

        target_queries = self._generate_targeted_queries(
            candidate_group=candidate_group,
            missing_fields=missing_fields,
            geography=geography,
        )

        merged_candidate = dict(candidate_group)
        merged_titles = list(merged_candidate.get("titles", []))
        merged_snippets = list(merged_candidate.get("snippets", []))
        merged_urls = list(merged_candidate.get("source_urls", []))
        merged_dates = list(merged_candidate.get("dates", []))
        evidence_packets = list(merged_candidate.get("evidence_packets", []))

        executed_queries = []
        pages_fetched_count = 0

        for q in target_queries:
            executed_queries.append(q)
            try:
                search_res = self.router.search(
                    query=q,
                    num_results=3,
                    db=db,
                    use_cache=False,
                )
                raw_followup = search_res.get("results", []) or []
                # Triage top results
                triaged = triage_and_rank_results(raw_followup, max_to_fetch=1)
                for item in triaged:
                    url = str(item.get("url") or "")
                    title = str(item.get("title") or "")
                    snippet = str(item.get("snippet") or "")
                    date_val = str((item.get("metadata") or {}).get("date") or "")

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

            except Exception as exc:
                logger.warning("Targeted research search error for '%s': %s", company_name, exc)

        merged_candidate["titles"] = merged_titles
        merged_candidate["snippets"] = merged_snippets
        merged_candidate["source_urls"] = merged_urls
        merged_candidate["dates"] = merged_dates
        merged_candidate["evidence_packets"] = evidence_packets

        # Track independent source count
        unique_domains = {url.split("/")[2].replace("www.", "") for url in merged_urls if "/" in url}
        merged_candidate["independent_source_count"] = len(unique_domains)

        logger.info(
            "[EVIDENCE_AGGREGATED] Company: %s | Total Sources: %d | Independent Domains: %d | Evidence Packets: %d",
            company_name,
            len(merged_urls),
            len(unique_domains),
            len(evidence_packets),
        )

        # Re-reason with enriched, aggregated evidence
        re_assessment = self.reasoner.reason_opportunity(
            candidate_group=merged_candidate,
            sector=sector,
            geography=geography,
        )

        final_cls = re_assessment.get("opportunity_classification")
        upgraded = (final_cls == CLASSIFICATION_STRONG)

        logger.info(
            "[FOLLOWUP_RESEARCH_COMPLETE] Company: %s | Result: %s -> %s (searches: %d, pages: %d)",
            company_name,
            current_cls,
            final_cls,
            len(executed_queries),
            pages_fetched_count,
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
