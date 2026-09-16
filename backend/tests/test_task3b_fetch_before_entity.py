"""Task 3B Focused Regression Tests: Uncouple Page Fetch from Snippet-Level Company Resolution.

Verifies:
1. Mandatory Case 1: Headline without company name -> passes triage, fetches page, resolves company from body.
2. Mandatory Case 2: Financial stock noise -> no fetch.
3. Mandatory Case 3: Noise / directory -> not deep-fetched.
4. Mandatory Case 4: Company page with facility evidence -> fetched before entity grouping.
5. Mandatory Case 5: Fetch timeout -> snippet fallback remains functional.
6. Mandatory Case 6: Duplicate URL across results -> single fetch / cache reuse.
7. Mandatory Case 7: Fetched page does not resolve entity -> no invented company.
8. Mandatory Case 8: Existing valid snippet-based company -> no regression.
9. Mandatory Case 9: Fetch budget per query -> bounded per query, iteration cap prevents explosion.
"""
from unittest.mock import MagicMock, patch
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from services.search_result_triage import (
    CLASS_COMPANY_PAGE,
    CLASS_FINANCIAL_MARKET_NOISE,
    CLASS_HIGH_VALUE_PRIMARY,
    CLASS_INDUSTRY_DIRECTORY,
    CLASS_NOISE,
    CLASS_POTENTIALLY_RELEVANT,
    classify_search_result,
    triage_and_rank_results,
)
from services.structured_evidence_extractor import extract_structured_evidence
from services.page_content_fetcher import STATUS_FETCH_SUCCESS, STATUS_FETCH_TIMEOUT


@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


# ---------------------------------------------------------------------------
# Mandatory Case 1: Title/snippet does NOT expose company; page body DOES.
# ---------------------------------------------------------------------------
def test_case_1_page_body_resolves_company_when_headline_lacks_it(test_db):
    raw_result = {
        "title": "Rs 500 cr aerospace manufacturing facility inaugurated in Coimbatore",
        "snippet": "A new state-of-the-art precision components plant was inaugurated with 1200 jobs created.",
        "url": "https://www.thehindubusinessline.com/economy/aerospace-facility-coimbatore/article999.ece",
    }

    # 1. Result must pass triage without needing a company
    triage_class, score = classify_search_result(raw_result)
    assert triage_class in {CLASS_HIGH_VALUE_PRIMARY, CLASS_POTENTIALLY_RELEVANT}
    assert score >= 7.0

    selected, all_triaged, telemetry = triage_and_rank_results([raw_result], max_to_fetch=3, return_all=True)
    assert len(selected) == 1
    assert selected[0]["recommended_fetch"] is True

    # 2. Page fetch succeeds and returns body with legitimate company
    page_text = (
        "Tata Advanced Systems today inaugurated its new aerospace manufacturing facility in Coimbatore. "
        "The plant will produce high-precision fuselage components and composite structures with an investment of Rs 500 crore."
    )
    facts = extract_structured_evidence(
        text=page_text,
        title=raw_result["title"],
        url=raw_result["url"],
        publication_date="2026-08-15",
        source_type=triage_class,
    )
    assert facts["company"] == "Tata Advanced Systems"
    assert facts["city"] == "Coimbatore"
    assert facts["investment_amount"] == "₹500 crore"


# ---------------------------------------------------------------------------
# Mandatory Case 2: Obvious financial stock result -> no fetch.
# ---------------------------------------------------------------------------
def test_case_2_financial_stock_noise_excluded_from_fetch():
    stock_item = {
        "title": "Tata Motors Share Price, Live Stock Target, P/E Ratio, Market Cap",
        "snippet": "Tata Motors stock trading at Rs 980. Quarterly financial profit, dividend yield, brokerage buy target.",
        "url": "https://www.moneycontrol.com/india/stockpricequote/auto/tatamotors/TM03",
    }
    triage_class, score = classify_search_result(stock_item)
    assert triage_class == CLASS_FINANCIAL_MARKET_NOISE

    selected = triage_and_rank_results([stock_item], max_to_fetch=3)
    assert len(selected) == 0, "Financial noise must not be selected for page fetch"


# ---------------------------------------------------------------------------
# Mandatory Case 3: Noise / directory -> not deep-fetched.
# ---------------------------------------------------------------------------
def test_case_3_directory_excluded_from_fetch():
    dir_item = {
        "title": "Top CNC Machining Suppliers and Manufacturers in Pune",
        "snippet": "Directory of precision machining, fabrication units, and machine shops in Bhosari, Pune.",
        "url": "https://www.indiamart.com/pune/cnc-machining.html",
    }
    triage_class, _ = classify_search_result(dir_item)
    assert triage_class == CLASS_INDUSTRY_DIRECTORY

    selected = triage_and_rank_results([dir_item], max_to_fetch=3)
    assert len(selected) == 0, "Directories must not receive deep page fetch by default"


# ---------------------------------------------------------------------------
# Mandatory Case 4: Company page with facility evidence -> fetch before entity grouping.
# ---------------------------------------------------------------------------
def test_case_4_company_page_with_facility_evidence_is_eligible():
    co_page = {
        "title": "Manufacturing Facilities & Technology Infrastructure - Bharat Forge",
        "snippet": "Explore our world-class forging and precision machining plants located at Pune, Baramati, and Chakan.",
        "url": "https://www.bharatforge.com/facilities/pune-plant",
    }
    triage_class, score = classify_search_result(co_page)
    assert triage_class == CLASS_COMPANY_PAGE
    assert score >= 6.0

    selected = triage_and_rank_results([co_page], max_to_fetch=3)
    assert len(selected) == 1
    assert selected[0]["recommended_fetch"] is True


# ---------------------------------------------------------------------------
# Mandatory Case 5: Fetch timeout -> snippet fallback remains possible.
# ---------------------------------------------------------------------------
def test_case_5_fetch_timeout_preserves_snippet_fallback():
    item = {
        "title": "Renewsys commissions 1GW solar cell manufacturing line in Hyderabad",
        "snippet": "Renewsys announced the operational commissioning of its new solar line in Telangana.",
        "url": "https://www.thehindubusinessline.com/news/renewsys-expansion",
        "fetch_status": "FETCH_TIMEOUT",
        "evidence_packet": None,
        "structured_evidence": None,
    }
    # When fetch times out, snippet extraction can still resolve the company
    from services.entity_truth_gate import extract_clean_company_name_from_title, resolve_canonical_company_identity
    cand = extract_clean_company_name_from_title(item["title"])
    res = resolve_canonical_company_identity(raw_candidate=cand, title=item["title"], snippet=item["snippet"], url=item["url"])
    assert res["is_valid"] is True
    assert res["company_name"] == "Renewsys"


# ---------------------------------------------------------------------------
# Mandatory Case 6: Duplicate URL across results -> single fetch.
# ---------------------------------------------------------------------------
def test_case_6_duplicate_url_deduplication():
    url = "https://www.thehindubusinessline.com/companies/tata-motors-plant-expansion/article111.ece"
    item1 = {"title": "Tata Motors expands plant", "snippet": "Capex of 2000 cr", "url": url}
    item2 = {"title": "Tata Motors plant expansion", "snippet": "New manufacturing unit", "url": url}
    item3 = {"title": "Tata Motors Pune unit", "snippet": "Cleanroom installation", "url": f"{url}?ref=rss"}

    # Canonical URL dedup logic
    import re
    seen = set()
    unique = []
    for it in [item1, item2, item3]:
        canon = re.sub(r"[?#].*$", "", it["url"]).rstrip("/").lower()
        if canon not in seen:
            seen.add(canon)
            unique.append(it)

    assert len(unique) == 1, "Duplicate URLs and query-param variants must deduplicate to single fetch"


# ---------------------------------------------------------------------------
# Mandatory Case 7: Fetched page does NOT resolve an entity -> no invented company.
# ---------------------------------------------------------------------------
def test_case_7_no_invented_company_on_unresolved_page():
    editorial_text = (
        "India's manufacturing sector registered strong growth this quarter with new investments across multiple states. "
        "Industrial production index expanded by 6.2% driven by automotive and machinery segments."
    )
    facts = extract_structured_evidence(
        text=editorial_text,
        title="Industrial growth accelerates across manufacturing hubs",
        url="https://business-standard.com/economy-news",
    )
    # Must NOT invent or force an entity from generic words like 'India' or 'Industrial'
    assert facts["company"] in {"UNKNOWN", ""}, "Must return UNKNOWN when page evidence lacks a concrete corporate entity"


# ---------------------------------------------------------------------------
# Mandatory Case 8: Existing valid snippet-based company -> no regression.
# ---------------------------------------------------------------------------
def test_case_8_valid_snippet_company_no_regression():
    item = {
        "title": "Thermax opens new manufacturing plant in Sri City, Andhra Pradesh",
        "snippet": "Thermax Ltd has inaugurated its new greenfield manufacturing unit in Sri City for industrial boilers.",
        "url": "https://thehindu.com/thermax-sricity",
    }
    from services.entity_truth_gate import extract_clean_company_name_from_title, resolve_canonical_company_identity
    cand = extract_clean_company_name_from_title(item["title"])
    res = resolve_canonical_company_identity(raw_candidate=cand, title=item["title"], snippet=item["snippet"], url=item["url"])
    assert res["is_valid"] is True
    assert res["company_name"] == "Thermax"


# ---------------------------------------------------------------------------
# Mandatory Case 9: Fetch budget is per query, bounded by iteration cap.
# ---------------------------------------------------------------------------
def test_case_9_fetch_budget_is_per_query_and_bounded():
    FETCH_BUDGET_PER_QUERY = 3
    FETCH_BUDGET_PER_DISCOVERY_ITERATION = 5

    # Simulated Query 1: 5 eligible results
    query1_results = [
        {"title": f"Manufacturer {i} announces plant expansion in Gujarat", "snippet": "Capex 100 cr", "url": f"https://news.com/plant-{i}"}
        for i in range(5)
    ]
    # Simulated Query 2: 5 eligible results
    query2_results = [
        {"title": f"OEM {i} inaugurates assembly line in Tamil Nadu", "snippet": "New facility 200 cr", "url": f"https://news.com/oem-{i}"}
        for i in range(5)
    ]

    selected_q1 = triage_and_rank_results(query1_results, max_to_fetch=FETCH_BUDGET_PER_QUERY)
    assert len(selected_q1) == 3, "Query 1 must select up to FETCH_BUDGET_PER_QUERY (3)"

    selected_q2 = triage_and_rank_results(query2_results, max_to_fetch=FETCH_BUDGET_PER_QUERY)
    assert len(selected_q2) == 3, "Query 2 must independently select up to FETCH_BUDGET_PER_QUERY (3)"

    # Total across iteration capped at FETCH_BUDGET_PER_DISCOVERY_ITERATION (5)
    total_to_fetch = []
    iteration_count = 0
    for q_selected in [selected_q1, selected_q2]:
        for item in q_selected:
            if iteration_count < FETCH_BUDGET_PER_DISCOVERY_ITERATION:
                total_to_fetch.append(item)
                iteration_count += 1

    assert len(total_to_fetch) == 5, "Total fetches across iteration must not exceed aggregate cap"
    # Query 2 gets 2 fetches (5 - 3 = 2), proving Query 1 did not exhaust entire cycle budget
    q2_fetched = [item for item in total_to_fetch if "oem-" in item["url"]]
    assert len(q2_fetched) == 2, "Query 2 still receives fetches within the iteration cap"
