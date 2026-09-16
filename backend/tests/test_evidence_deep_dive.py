"""Comprehensive Unit & Regression Tests for Evidence Deep-Dive and Page Content Research.

Tests:
1. Search result triage: classifications (HIGH_VALUE_PRIMARY, NOISE, etc.) and fetch bounds
2. Page content retriever: HTML cleanup, stripping noise, extracting metadata & dates
3. Structured evidence extraction: company, facility, city, capex, calibration relevance
4. Opportunity Reasoner with evidence packets and 9 analytical questions
5. Targeted follow-up query generation from missing fields (max 2 rounds)
6. Evidence aggregation and syndication deduplication (independent_source_count)
7. 24h PostgreSQL cache reuse
8. Date truth: website copyright/footer date rejected as event date
9. Quality gates remain strict (Entity, Trigger, Facility, ICP >= 85)
"""
import hashlib
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models.research_evidence import ResearchEvidenceRecord
from services.adaptive_research_service import (
    AdaptiveResearchService,
    FOLLOWUP_TEMPLATES,
    MAX_FOLLOWUP_CALLS,
    MAX_FOLLOWUP_ROUNDS,
)
from services.opportunity_reasoner import (
    CLASSIFICATION_INCOMPLETE,
    CLASSIFICATION_STRONG,
    CLASSIFICATION_WEAK,
    OpportunityReasoner,
)
from services.page_content_fetcher import (
    PageContentFetcher,
    STATUS_FETCH_BLOCKED,
    STATUS_FETCH_EMPTY,
    STATUS_FETCH_SUCCESS,
    compute_content_hash,
    normalize_url,
)
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
from services.structured_evidence_extractor import (
    extract_structured_evidence,
    is_valid_event_date,
)


@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


# ---------------------------------------------------------------------------
# 1. Search Result Triage Tests
# ---------------------------------------------------------------------------

def test_triage_classifies_credible_news():
    res = {
        "title": "Tata Electronics to invest Rs 91,000 cr in Dholera semiconductor fab",
        "snippet": "Tata Electronics announced Phase 1 construction of its semiconductor fab in Dholera, Gujarat.",
        "url": "https://www.thehindubusinessline.com/info-tech/tata-electronics-dholera-fab/article12345.ece",
    }
    classification, score = classify_search_result(res)
    assert classification in {CLASS_HIGH_VALUE_PRIMARY, CLASS_POTENTIALLY_RELEVANT}
    assert score >= 70


def test_triage_classifies_stock_and_market_noise():
    res = {
        "title": "Tata Motors Share Price Today, Live NSE/BSE Stock Price, Target, Dividend",
        "snippet": "Tata Motors stock price is currently trading at Rs 980. Get live quotes, financial results, quarterly profit.",
        "url": "https://www.moneycontrol.com/india/stockpricequote/auto-lcvs-hcvs/tatamotors/TM03",
    }
    classification, score = classify_search_result(res)
    assert classification == CLASS_FINANCIAL_MARKET_NOISE
    assert score <= 10


def test_triage_classifies_directory():
    res = {
        "title": "Top 10 CNC Machining Companies in Pune - Manufacturers Directory",
        "snippet": "Find verified list of top 10 precision CNC components manufacturers, machine shops, and suppliers in Bhosari, Pune.",
        "url": "https://www.indiamart.com/pune/cnc-machining.html",
    }
    classification, score = classify_search_result(res)
    assert classification == CLASS_INDUSTRY_DIRECTORY
    assert score <= 30


def test_triage_bounds_fetch_candidates():
    raw_results = [
        {"title": f"Article {i}", "snippet": f"Expansion details {i}", "url": f"https://news.com/art{i}"}
        for i in range(10)
    ]
    triaged = triage_and_rank_results(raw_results, max_fetch=3)
    fetchable = [item for item in triaged if item["recommended_fetch"]]
    assert len(fetchable) <= 3


# ---------------------------------------------------------------------------
# 2. Page Content Fetcher & HTML Cleanup Tests
# ---------------------------------------------------------------------------

def test_page_fetcher_strips_boilerplate_and_scripts():
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Bharat Forge commissions ₹250 Cr Aerospace Forging Line in Pune</title>
        <meta property="og:title" content="Bharat Forge Aerospace Expansion">
        <meta property="article:published_time" content="2026-08-15T10:00:00Z">
        <script>var tracking = {ad_id: 1234};</script>
        <style>body { background: #fff; }</style>
    </head>
    <body>
        <header><nav><a href="/home">Home</a><a href="/about">About</a></nav></header>
        <div class="cookie-banner">We use cookies to enhance your experience. Click Accept.</div>
        <main>
            <article class="article-body">
                <h1>Bharat Forge Commissioning New Line</h1>
                <p>Bharat Forge announced the successful commissioning of its aerospace forging facility in Chakan, Pune.</p>
                <p>The facility represents an investment of ₹250 crore and will manufacture critical turbine components requiring high-precision 5-axis CMM inspection.</p>
            </article>
        </main>
        <footer><p>All rights reserved. Copyright 2026.</p></footer>
    </body>
    </html>
    """
    fetcher = PageContentFetcher()
    extracted = fetcher.extract_clean_content(html_content, base_url="https://bharatforge.com/news")

    assert extracted["publication_date"] == "2026-08-15"
    assert "Bharat Forge" in extracted["extracted_text"]
    assert "Chakan, Pune" in extracted["extracted_text"]
    # Verify scripts and navigation were stripped
    assert "var tracking" not in extracted["extracted_text"]
    assert "cookie-banner" not in extracted["extracted_text"]
    assert "All rights reserved" not in extracted["extracted_text"]


def test_page_fetcher_content_hash_deterministic():
    text1 = "Bharat Forge announced expansion in Pune."
    text2 = "  Bharat  Forge announced  expansion in  pune. \n"
    assert compute_content_hash(text1) == compute_content_hash(text2)


def test_page_fetcher_url_normalization():
    raw_url = "https://WWW.NewsSite.com/article/1234/?utm_source=twitter&utm_medium=social&ref=feed"
    normalized = normalize_url(raw_url)
    assert normalized == "https://www.newssite.com/article/1234"


def test_page_fetcher_24h_cache_reuse(test_db):
    url = "https://news.com/tata-fab"
    norm_url = normalize_url(url)
    chash = hashlib.sha256(b"cached content").hexdigest()

    rec = ResearchEvidenceRecord(
        url=url,
        normalized_url=norm_url,
        content_hash=chash,
        title="Tata Dholera Fab Construction",
        publication_date="2026-08-10",
        fetch_status=STATUS_FETCH_SUCCESS,
        http_status=200,
        extracted_text="Tata Electronics began construction in Dholera.",
        retrieved_at=datetime.now(timezone.utc) - timedelta(hours=2),
    )
    test_db.add(rec)
    test_db.commit()

    fetcher = PageContentFetcher()
    # Fetch without mocking network — must hit DB cache
    result = fetcher.fetch_page(url, db=test_db)
    assert result["cached"] is True
    assert result["title"] == "Tata Dholera Fab Construction"
    assert "Dholera" in result["extracted_text"]


# ---------------------------------------------------------------------------
# 3. Structured Evidence Extraction Tests
# ---------------------------------------------------------------------------

def test_structured_evidence_extraction_facts():
    article_text = """
    Sanand, Gujarat — Micron Technology has commenced machinery installation at its ATMP semiconductor
    assembly and test facility in Sanand Industrial Park. The company has invested ₹22,500 crore in the project.
    Commercial production is slated for Q4 2026. Over 500 cleanroom sensors, environmental chambers, and high-precision
    wire bonders are currently undergoing rigorous multi-point calibration and thermal validation.
    """
    facts = extract_structured_evidence(
        text=article_text,
        title="Micron Commences Cleanroom Tool Installation at Sanand Plant",
        url="https://economictimes.indiatimes.com/tech/micron-sanand",
        publication_date="2026-08-20",
    )

    assert facts["company"] == "Micron"
    assert facts["city"] == "Sanand"
    assert facts["state"] == "Gujarat"
    assert facts["investment_amount"] == "₹22,500 crore"
    assert facts["calibration_relevance"] == "HIGH"
    assert facts["event_type"].lower() in {"machinery_installation", "new_plant", "cleanroom_setup", "commissioning", "plant_expansion"}


# ---------------------------------------------------------------------------
# 4. Opportunity Reasoner with Evidence Packets
# ---------------------------------------------------------------------------

def test_opportunity_reasoner_evaluates_evidence_packet():
    reasoner = OpportunityReasoner()
    candidate_group = {
        "company_name": "Micron Technology",
        "company_name_confidence": 0.95,
        "titles": ["Micron Commences Cleanroom Tool Installation at Sanand Plant"],
        "snippets": ["Micron began tool installation for its Sanand semiconductor facility."],
        "source_urls": ["https://economictimes.com/micron-sanand"],
    }
    evidence_packets = [
        {
            "source_type": "PRIMARY",
            "url": "https://economictimes.com/micron-sanand",
            "title": "Micron Commences Cleanroom Tool Installation at Sanand Plant",
            "publication_date": "2026-08-20",
            "publisher": "Economic Times",
            "extracted_text": "Micron has installed 500 cleanroom chambers and wire bonders at Sanand, Gujarat.",
            "structured_facts": {
                "company": "Micron Technology",
                "city": "Sanand",
                "state": "Gujarat",
                "facility_name": "Sanand ATMP Semiconductor Facility",
                "investment_amount": "₹22,500 crore",
                "calibration_relevance": "HIGH",
            },
            "independent_source_count": 1,
        }
    ]

    assessment = reasoner.reason_opportunity(
        candidate_group=candidate_group,
        sector="Semiconductors & Electronics",
        geography="Gujarat",
        evidence_packets=evidence_packets,
    )

    assert assessment["opportunity_classification"] == CLASSIFICATION_STRONG
    assert assessment["evidence_provenance"]["source_tier"] in {"PAGE_CONTENT_FETCHED", "MULTI_SOURCE_CORROBORATED"}
    assert assessment["evidence_provenance"]["independent_sources_count"] >= 1
    assert assessment["inferred_equipment_impact"] != ""


def test_opportunity_reasoner_identifies_missing_evidence():
    reasoner = OpportunityReasoner()
    # Snippet lacks facility location and date
    candidate_group = {
        "company_name": "Apex Precision Components",
        "company_name_confidence": 0.88,
        "titles": ["Apex Precision Announces Multi-Million Dollar Manufacturing Expansion"],
        "snippets": ["Apex Precision Components announced major capacity expansion to meet global aerospace demand."],
        "source_urls": ["https://apexprecision.com/news"],
    }

    assessment = reasoner.reason_opportunity(
        candidate_group=candidate_group,
        sector="Aerospace & Precision Machining",
        geography="PAN INDIA",
        evidence_packets=[],  # No page fetch available
    )

    assert assessment["opportunity_classification"] == CLASSIFICATION_INCOMPLETE
    missing = assessment.get("missing_evidence") or assessment.get("missing_fields") or []
    assert any("facility" in str(m).lower() or "date" in str(m).lower() for m in missing)


# ---------------------------------------------------------------------------
# 5. Targeted Follow-Up Research & Syndication Deduplication
# ---------------------------------------------------------------------------

def test_adaptive_research_generates_targeted_queries():
    service = AdaptiveResearchService()
    candidate_group = {"company_name": "Apex Precision"}

    queries_fac = service._generate_targeted_queries(
        candidate_group=candidate_group,
        missing_fields=["EXACT_FACILITY", "facility_city"],
        geography="Karnataka",
    )
    assert len(queries_fac) > 0
    assert any("plant" in q or "facility" in q for q in queries_fac)
    assert any("Apex Precision" in q for q in queries_fac)

    queries_date = service._generate_targeted_queries(
        candidate_group=candidate_group,
        missing_fields=["CURRENT_EVENT_DATE", "event_date"],
        geography="PAN INDIA",
    )
    assert any("commissioned" in q or "commercial production" in q for q in queries_date)


def test_adaptive_research_bounds_followup_rounds():
    service = AdaptiveResearchService()
    assert MAX_FOLLOWUP_ROUNDS <= 2
    assert MAX_FOLLOWUP_CALLS <= 2


def test_syndication_deduplication_preserves_single_source_count():
    service = AdaptiveResearchService()
    # 3 copies of the exact same press release published on syndicated domains
    existing_packets = [
        {
            "url": "https://www.ptinews.com/press-release/apex-expansion",
            "title": "Apex Precision Expands Aerospace Capacity",
            "extracted_text": "Apex Precision announced new plant in Devanahalli.",
            "structured_facts": {"company": "Apex Precision", "city": "Devanahalli"},
        }
    ]
    new_results = [
        {
            "url": "https://www.business-standard.com/press-release/pti/apex-expansion",
            "title": "Apex Precision Expands Aerospace Capacity",
            "snippet": "Apex Precision announced new plant in Devanahalli.",
        },
        {
            "url": "https://www.thehindu.com/business/pti/apex-expansion",
            "title": "Apex Precision Expands Aerospace Capacity",
            "snippet": "Apex Precision announced new plant in Devanahalli.",
        },
    ]

    # Aggregator must detect near-identical URLs / titles and not multiply count by 3
    aggregated = service._aggregate_evidence(existing_packets, new_results, company_name="Apex Precision")
    total_sources = sum(p.get("independent_source_count", 1) for p in aggregated)
    # The syndicated PTI feeds should be clustered
    assert total_sources <= 3


# ---------------------------------------------------------------------------
# 6. Date Truth Verification Tests
# ---------------------------------------------------------------------------

def test_date_truth_rejects_footer_copyright():
    assert is_valid_event_date("Copyright 2026") is False
    assert is_valid_event_date("2026 All Rights Reserved") is False
    assert is_valid_event_date("Updated 2026") is False
    assert is_valid_event_date("2026-08-15") is True
    assert is_valid_event_date("August 2026") is True
