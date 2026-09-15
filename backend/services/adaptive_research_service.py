"""Adaptive Targeted Research Service for Salesoorja Discovery Intelligence.

Triggered exclusively for PROMISING_BUT_INCOMPLETE opportunities to perform
bounded, focused follow-up searches (cap <= 2-3 searches per company) to
resolve missing facility locations, operational statuses, or commissioning dates.
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

logger = logging.getLogger(__name__)

FOLLOWUP_SEARCH_CAP = 2


class AdaptiveResearchService:
    """Executes bounded follow-up research to ground promising but incomplete leads."""

    def __init__(self, router=None, reasoner=None):
        self.router = router or ResearchProviderRouter()
        self.reasoner = reasoner or opportunity_reasoner

    def conduct_targeted_research(
        self,
        candidate_group: Dict[str, Any],
        initial_assessment: Dict[str, Any],
        sector: str = "",
        geography: str = "",
        db: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Conduct targeted searches to resolve missing fields for an incomplete opportunity.

        Returns:
            {
                "final_assessment": dict,
                "searches_conducted": int,
                "queries": list[str],
                "upgraded": bool,
            }
        """
        company_name = candidate_group.get("company_name", "Unknown")
        missing_fields = initial_assessment.get("missing_fields") or []

        # If already strong or weak or reasoner unavailable, no targeted research needed
        current_cls = initial_assessment.get("opportunity_classification")
        if current_cls != CLASSIFICATION_INCOMPLETE:
            return {
                "final_assessment": initial_assessment,
                "searches_conducted": 0,
                "queries": [],
                "upgraded": False,
            }

        # Formulate up to FOLLOWUP_SEARCH_CAP targeted queries
        target_queries: List[str] = []
        if any("facility" in f.lower() or "city" in f.lower() or "location" in f.lower() for f in missing_fields):
            target_queries.append(
                f'"{company_name}" plant location facility factory city "commissioning" OR "expansion" -stock'
            )
        if any("date" in f.lower() or "status" in f.lower() or "commission" in f.lower() for f in missing_fields):
            target_queries.append(
                f'"{company_name}" commercial production commissioning "2026" plant -stock'
            )

        # Fallback query if specific missing field pattern didn't match
        if not target_queries:
            target_queries.append(
                f'"{company_name}" manufacturing plant facility "commissioning" "2026" -stock'
            )

        target_queries = target_queries[:FOLLOWUP_SEARCH_CAP]

        merged_candidate = dict(candidate_group)
        merged_titles = list(merged_candidate.get("titles", []))
        merged_snippets = list(merged_candidate.get("snippets", []))
        merged_urls = list(merged_candidate.get("source_urls", []))
        merged_dates = list(merged_candidate.get("dates", []))

        executed_queries = []
        for q in target_queries:
            executed_queries.append(q)
            try:
                search_res = self.router.search(
                    query=q,
                    num_results=3,
                    db=db,
                    use_cache=False,
                )
                for item in search_res.get("results", []):
                    title = str(item.get("title") or "")
                    snippet = str(item.get("snippet") or item.get("content") or "")
                    url = str(item.get("url") or "")
                    date_val = str((item.get("metadata") or {}).get("date") or "")

                    if title and title not in merged_titles:
                        merged_titles.append(title)
                    if snippet and snippet not in merged_snippets:
                        merged_snippets.append(snippet)
                    if url and url not in merged_urls:
                        merged_urls.append(url)
                    if date_val and date_val not in merged_dates:
                        merged_dates.append(date_val)
            except Exception as exc:
                logger.warning("Targeted research search error for '%s': %s", company_name, exc)

        merged_candidate["titles"] = merged_titles
        merged_candidate["snippets"] = merged_snippets
        merged_candidate["source_urls"] = merged_urls
        merged_candidate["dates"] = merged_dates

        # Re-reason with enriched evidence
        re_assessment = self.reasoner.reason_opportunity(
            candidate_group=merged_candidate,
            sector=sector,
            geography=geography,
        )

        final_cls = re_assessment.get("opportunity_classification")
        upgraded = (final_cls == CLASSIFICATION_STRONG)

        logger.info(
            "Adaptive Research: '%s' %s -> %s (searches: %d)",
            company_name,
            current_cls,
            final_cls,
            len(executed_queries),
        )

        return {
            "final_assessment": re_assessment,
            "searches_conducted": len(executed_queries),
            "queries": executed_queries,
            "upgraded": upgraded,
        }


adaptive_research_service = AdaptiveResearchService()
