"""Company-First Discovery Lane with Directory/List Safety and Bounded Trigger Verification.

Workflow:
1. Industrial corridor manufacturer discovery (e.g. "Sanand automotive component manufacturers")
2. Directory/list page safety: Extract real company names from listings, rejecting directory titles
3. Canonical company entity validation via entity_truth_gate
4. Bounded trigger research (max 1 follow-up Serper call per verified company)
5. Standard qualification: Static companies without verified current triggers are strictly HELD
   and NEVER become outreach-ready.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session

from services.entity_truth_gate import validate_company_entity
from services.research_provider import ResearchProviderRouter, research_router

logger = logging.getLogger(__name__)

# Patterns indicating directory, list, or generic aggregator pages
DIRECTORY_LIST_PATTERNS = [
    r"\btop\s+\d+\b",
    r"\blist\s+of\b",
    r"\bdirectory\b",
    r"\byellow\s*pages\b",
    r"\bindustrial\s+park\b",
    r"\bindustrial\s+estate\b",
    r"\bmanufacturers\s+in\b",
    r"\bcompanies\s+in\b",
    r"\bassociation\b",
    r"\bexporters\s+in\b",
    r"\bsuppliers\s+in\b",
    r"\btradeindia\b",
    r"\bindiamart\b",
    r"\bjustdial\b",
]

# Max follow-up trigger searches per company in company-first lane
MAX_TRIGGER_SEARCHES_PER_COMPANY = 1


def is_directory_or_list_title(title: str, snippet: str = "") -> bool:
    """Check if title or snippet matches directory, list, or aggregator pattern."""
    text = f"{title} {snippet}".lower()
    return any(re.search(pattern, text) for pattern in DIRECTORY_LIST_PATTERNS)


def extract_candidate_entities_from_text(text: str) -> List[str]:
    """Extract candidate company names from directory text or list snippets."""
    candidates = []
    # Pattern: Capitalized phrases followed by Ltd/Pvt/Limited/Industries/Corp
    pattern = r"\b([A-Z][A-Za-z0-9\.\s&-]{2,35}\s+(?:Ltd|Pvt\s+Ltd|Private\s+Limited|Limited|Industries|Enterprises|Corporation|Corp|Engineering))\b"
    for match in re.finditer(pattern, text):
        clean_name = match.group(1).strip()
        if len(clean_name) > 3 and clean_name not in candidates:
            candidates.append(clean_name)
    return candidates


class CompanyFirstDiscoveryService:
    """Complementary lane discovering manufacturers and verifying current triggers."""

    def __init__(self, router: Optional[ResearchProviderRouter] = None):
        self.router = router or research_router

    def discover_corridor_manufacturers(
        self,
        sector: str,
        geography: str,
        limit: int = 10,
        db: Optional[Session] = None,
    ) -> List[Dict[str, Any]]:
        """Search industrial corridor for active manufacturers and safely extract entities."""
        query = f'"{geography}" "{sector}" manufacturing companies {geography} -stock -share -dividend'
        search_res = self.router.search(query, num_results=limit, db=db)
        raw_items = search_res.get("results", []) or []

        extracted_companies: List[Dict[str, Any]] = []
        seen_names = set()

        for item in raw_items:
            title = str(item.get("title") or "")
            snippet = str(item.get("snippet") or "")
            url = str(item.get("url") or "")

            is_dir = is_directory_or_list_title(title, snippet)

            if is_dir:
                # Directory/List page safety: Extract real companies mentioned in the snippet
                nested_entities = extract_candidate_entities_from_text(f"{title}. {snippet}")
                for entity_name in nested_entities:
                    clean_key = entity_name.lower().strip()
                    if clean_key in seen_names:
                        continue
                    is_valid, reason = validate_company_entity(entity_name, title)
                    if is_valid:
                        seen_names.add(clean_key)
                        extracted_companies.append({
                            "company_name": entity_name,
                            "source_type": "DIRECTORY_EXTRACTION",
                            "source_url": url,
                            "source_title": title,
                            "sector": sector,
                            "geography": geography,
                            "evidence_snippet": snippet[:300],
                        })
            else:
                # Direct company website or article
                # Derive company name from title before separators (| - : )
                raw_name = title.split(" - ")[0].split(" | ")[0].split(" : ")[0].strip()
                clean_key = raw_name.lower()
                if clean_key not in seen_names and len(raw_name) > 3:
                    is_valid, reason = validate_company_entity(raw_name, title)
                    if is_valid:
                        seen_names.add(clean_key)
                        extracted_companies.append({
                            "company_name": raw_name,
                            "source_type": "ORGANIC_COMPANY_PAGE",
                            "source_url": url,
                            "source_title": title,
                            "sector": sector,
                            "geography": geography,
                            "evidence_snippet": snippet[:300],
                        })

        logger.info("[COMPANY_FIRST_DISCOVERY] Discovered %s candidate companies in %s (%s)", len(extracted_companies), geography, sector)
        return extracted_companies

    def research_company_triggers(
        self,
        company_name: str,
        geography: str,
        sector: str,
        db: Optional[Session] = None,
    ) -> Dict[str, Any]:
        """Perform bounded follow-up Serper search to check if company has an active current trigger.

        Guarded by Authoritative LLM Information-Gain Gate (Task 3D.1F).
        Strict Safety: Static company without verified current trigger is HELD and NEVER outreach-ready.
        """
        from services.followup_information_gain_gate import followup_information_gain_gate

        # Gate Evaluation: Block generic/unresolved entities or queries with low gain
        gate_decision = followup_information_gain_gate.evaluate_followup_search(
            company_name=company_name,
            missing_fact="CAPEX_EVENT",
            current_evidence={"sector": sector, "geography": geography},
            current_funnel_status="INCOMPLETE",
            db=db,
        )

        if not gate_decision.search_needed or gate_decision.expected_information_gain not in {"HIGH", "MEDIUM"}:
            logger.info(
                "[COMPANY_FIRST_GATE_BLOCKED] Company: %s | Gain: %s | Action: %s | Reason: %s",
                company_name,
                gate_decision.expected_information_gain,
                gate_decision.alternative_action,
                gate_decision.reason,
            )
            return {
                "has_trigger": False,
                "trigger_type": "NONE",
                "evidence_url": None,
                "evidence_snippet": None,
                "hold_reason": gate_decision.blocked_reason or "STATIC_MANUFACTURER_NO_CURRENT_TRIGGER",
            }

        # Natural targeted query generated without static negative tails (-stock)
        query = gate_decision.suggested_query or f'"{company_name}" (expansion OR capex OR "new plant" OR commissioned OR inaugurated) "{geography}"'
        search_res = self.router.search(query, num_results=5, db=db)
        results = search_res.get("results", []) or []

        if not results:
            followup_information_gain_gate.record_search_outcome(
                company_name=company_name,
                missing_fact="CAPEX_EVENT",
                query=query,
                research_strategy=gate_decision.research_strategy,
                result_count=0,
                new_evidence_found=False,
                evidence_type_found=None,
                funnel_state_before="INCOMPLETE",
                funnel_state_after="HOLD",
                llm_reasoning=gate_decision.reason,
                db=db,
            )
            return {
                "has_trigger": False,
                "trigger_type": "NONE",
                "evidence_url": None,
                "evidence_snippet": None,
                "hold_reason": "STATIC_MANUFACTURER_NO_CURRENT_TRIGGER",
            }

        # Analyze matching events with bounded page content research
        from services.search_result_triage import triage_and_rank_results
        from services.page_content_fetcher import page_content_fetcher
        from services.structured_evidence_extractor import extract_structured_evidence
        from services.trigger_discovery_service import evaluate_event_semantics, extract_event_date
        from datetime import datetime, timezone

        triaged = triage_and_rank_results(results, max_fetch=2)
        top = triaged[0] if triaged else results[0]
        title = str(top.get("title") or "")
        snippet = str(top.get("snippet") or "")
        url = str(top.get("url") or "")

        content_res = page_content_fetcher.fetch_page(url, db=db)
        article_text = content_res.get("extracted_text", "") if content_res.get("fetch_status") == "FETCH_SUCCESS" else ""
        pub_date = content_res.get("publication_date", "")

        date_eval_text = f"{snippet} {pub_date} {article_text[:2000]}".strip()
        semantics = evaluate_event_semantics(f"{snippet} {article_text[:1000]}", title=title)
        recency = extract_event_date(date_eval_text, title=title, now_dt=datetime.now(timezone.utc), url=url)

        is_valid = bool(
            semantics.get("is_valid")
            and recency.get("recency_tier") in {"CURRENT", "RECENT"}
            and not recency.get("is_future_planned_milestone")
        )

        if is_valid:
            structured_facts = (
                extract_structured_evidence(article_text, title=title, url=url, publication_date=pub_date)
                if article_text
                else {}
            )
            return {
                "has_trigger": True,
                "trigger_type": semantics.get("trigger_type", "plant_expansion"),
                "evidence_url": url,
                "evidence_title": title,
                "evidence_snippet": snippet,
                "recency": recency,
                "semantics": semantics,
                "structured_evidence": structured_facts,
                "hold_reason": None,
            }

        return {
            "has_trigger": False,
            "trigger_type": "UNVERIFIED",
            "evidence_url": url,
            "evidence_snippet": snippet,
            "hold_reason": f"Trigger recency or semantics unverified ({recency.get('recency_tier', 'UNKNOWN')})",
        }


company_first_discovery = CompanyFirstDiscoveryService()
