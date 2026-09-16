"""Search Result Triage and Priority Ranking Service.

Classifies and ranks Serper organic search results prior to fetching page content.
Ensures fetch budget is strictly bounded to the 2-4 most promising primary & news sources,
completely avoiding crawling financial noise or directories blindly.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

CLASS_HIGH_VALUE_PRIMARY = "HIGH_VALUE_PRIMARY"
CLASS_POTENTIALLY_RELEVANT = "POTENTIALLY_RELEVANT"
CLASS_COMPANY_PAGE = "COMPANY_PAGE"
CLASS_INDUSTRY_DIRECTORY = "INDUSTRY_DIRECTORY"
CLASS_NOISE = "NOISE"
CLASS_FINANCIAL_MARKET_NOISE = "FINANCIAL_MARKET_NOISE"

# Domains recognized as credible industrial/business publications
CREDIBLE_NEWS_DOMAINS = {
    "economictimes.indiatimes.com",
    "livemint.com",
    "business-standard.com",
    "thehindubusinessline.com",
    "financialexpress.com",
    "autocarpro.in",
    "manufacturingtodayindia.com",
    "cnbctv18.com",
    "moneycontrol.com",
    "reuters.com",
    "bloomberg.com",
    "theprint.in",
    "thehindu.com",
    "timesofindia.indiatimes.com",
    "projectstoday.com",
    "constructionweekonline.in",
    "epcworld.in",
    "pib.gov.in",
}

FINANCIAL_NOISE_DOMAINS = {
    "screener.in",
    "trendlyne.com",
    "tickertape.in",
    "investing.com",
    "groww.in",
    "zerodha.com",
    "angelone.in",
    "marketsmithindia.com",
    "bseindia.com/stock-share-price",
    "nseindia.com/get-quotes",
    "topstockresearch.com",
}

DIRECTORY_DOMAINS = {
    "indiamart.com",
    "tradeindia.com",
    "exportersindia.com",
    "justdial.com",
    "zaubacorp.com",
    "tofler.in",
    "instafinancials.com",
    "glassdoor.co.in",
    "ambitionbox.com",
    "wikipedia.org",
    "linkedin.com",
}

PRIMARY_ANNOUNCEMENT_KEYWORDS = (
    "press release",
    "announces",
    "investor presentation",
    "inauguration",
    "commissioned",
    "groundbreaking",
    "foundation stone",
    "investing crores",
    "new facility",
    "new plant",
    "mou signed",
)

FINANCIAL_NOISE_KEYWORDS = (
    "share price",
    "stock price",
    "target price",
    "quarterly results",
    "q1 results",
    "q2 results",
    "q3 results",
    "q4 results",
    "dividend yield",
    "market cap",
    "pe ratio",
    "brokerage report",
    "buy rating",
    "technical analysis",
)


def classify_search_result(item: Dict[str, Any]) -> Tuple[str, float]:
    """Classify an organic search result into priority tiers and return (tier, score_0_to_100)."""
    url = str(item.get("url") or "").strip().lower()
    title = str(item.get("title") or "").strip().lower()
    snippet = str(item.get("snippet") or item.get("content") or "").strip().lower()

    if not url:
        return CLASS_NOISE, 10.0

    parsed = urlparse(url)
    domain = parsed.netloc.replace("www.", "")

    # 1. Financial Market Noise Check
    if any(fnd in domain or fnd in url for fnd in FINANCIAL_NOISE_DOMAINS):
        return CLASS_FINANCIAL_MARKET_NOISE, 5.0

    combined_text = f"{title} {snippet}"
    if any(fnw in combined_text for fnw in FINANCIAL_NOISE_KEYWORDS):
        return CLASS_FINANCIAL_MARKET_NOISE, 5.0

    # 2. Directory / Aggregator Check
    if any(dd in domain for dd in DIRECTORY_DOMAINS):
        return CLASS_INDUSTRY_DIRECTORY, 20.0

    # 3. High Value Primary Corporate / Regulatory Announcements
    if any(kw in combined_text for kw in PRIMARY_ANNOUNCEMENT_KEYWORDS):
        if domain.endswith(".gov.in") or "press-release" in url or "investor" in url or "news" in url:
            return CLASS_HIGH_VALUE_PRIMARY, 90.0
        return CLASS_POTENTIALLY_RELEVANT, 75.0

    # 4. Credible Business & Industrial News
    if any(cnd in domain for cnd in CREDIBLE_NEWS_DOMAINS):
        return CLASS_POTENTIALLY_RELEVANT, 75.0

    # 5. Direct Company Webpage
    if not any(noise in domain for noise in ("news", "blog", "forum", "wiki")):
        if any(w in url for w in ("about-us", "facilities", "infrastructure", "products", "plants", "operations")):
            return CLASS_COMPANY_PAGE, 60.0

    return CLASS_POTENTIALLY_RELEVANT, 70.0


def triage_and_rank_results(
    raw_results: List[Dict[str, Any]],
    max_to_fetch: int = 3,
    max_fetch: Optional[int] = None,
    return_all: bool = False,
) -> Any:
    """Triage and rank search results, selecting up to max_to_fetch highest-value candidates.

    If return_all is True:
        returns (selected_for_fetch, all_classified_results, triage_telemetry)
    If return_all is False:
        returns selected_for_fetch (for backwards compatibility)
    """
    if max_fetch is not None:
        max_to_fetch = max_fetch
    classified: List[Dict[str, Any]] = []

    telemetry = {
        "RAW_SERPER_RESULTS": len(raw_results),
        "TRIAGE_HIGH_VALUE": 0,
        "TRIAGE_COMPANY_PAGE": 0,
        "TRIAGE_POTENTIAL": 0,
        "TRIAGE_DIRECTORY": 0,
        "TRIAGE_FINANCIAL_NOISE": 0,
        "TRIAGE_NOISE": 0,
        "FETCH_ELIGIBLE": 0,
    }

    for idx, item in enumerate(raw_results):
        triage_class, base_score_100 = classify_search_result(item)
        item_copy = dict(item)
        item_copy["triage_class"] = triage_class
        item_copy["relevance_class"] = triage_class
        item_copy["original_rank"] = idx + 1

        # Track telemetry
        if triage_class == CLASS_HIGH_VALUE_PRIMARY:
            telemetry["TRIAGE_HIGH_VALUE"] += 1
        elif triage_class == CLASS_COMPANY_PAGE:
            telemetry["TRIAGE_COMPANY_PAGE"] += 1
        elif triage_class == CLASS_POTENTIALLY_RELEVANT:
            telemetry["TRIAGE_POTENTIAL"] += 1
        elif triage_class == CLASS_INDUSTRY_DIRECTORY:
            telemetry["TRIAGE_DIRECTORY"] += 1
        elif triage_class == CLASS_FINANCIAL_MARKET_NOISE:
            telemetry["TRIAGE_FINANCIAL_NOISE"] += 1
        else:
            telemetry["TRIAGE_NOISE"] += 1

        # Calculate Priority Score (0.0 to 10.0)
        score = base_score_100 / 10.0 - (idx * 0.2)

        # Bonus for presence of date or industrial expansion keywords
        text = f"{item.get('title', '')} {item.get('snippet', '')}".lower()
        if re.search(r"\b(202[4-6]|inaugurate|commission|capex|plant|crores|facility|chakan|sanand|hosur|sri city)\b", text):
            score += 1.0

        item_copy["relevance_score"] = round(max(0.0, score), 2)
        item_copy["recommended_fetch"] = False
        classified.append(item_copy)

    # Sort descending by relevance score
    classified.sort(key=lambda x: x["relevance_score"], reverse=True)

    # Filter for candidates eligible for page fetching (excluding noise, financial noise, and directories)
    eligible = [
        item for item in classified
        if item["triage_class"] in {CLASS_HIGH_VALUE_PRIMARY, CLASS_POTENTIALLY_RELEVANT, CLASS_COMPANY_PAGE}
        and item["relevance_score"] >= 5.0
    ]
    telemetry["FETCH_ELIGIBLE"] = len(eligible)

    selected = eligible[:max_to_fetch]
    for s in selected:
        s["recommended_fetch"] = True
        logger.info(
            "[SEARCH_RESULT_RELEVANT] Class: %s | Score: %.1f | URL: %s | Title: %s",
            s["triage_class"],
            s["relevance_score"],
            s.get("url"),
            (s.get("title") or "")[:60],
        )

    if return_all:
        return selected, classified, telemetry
    return selected
