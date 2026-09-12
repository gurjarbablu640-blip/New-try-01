"""Regression tests for Salesoorja Upstream Trigger Quality Recovery.

Verifies:
1. Stock quote result hard reject
2. Homepage cannot prove expansion
3. Snippet-only false positive rejected
4. Event quote must exist in fetched source
5. Future completion date not used as trigger date
6. Publication vs event vs completion date separation
7. Facility seed cannot establish trigger-to-facility linkage without event evidence
8. Path-level source classification (moneycontrol / economictimes)
9. Gemini hallucinated evidence quote rejected
"""
from datetime import datetime, timezone
import unittest
from unittest.mock import MagicMock, patch

from services.source_verification_pipeline import (
    classify_source_class,
    is_source_allowed_for_trigger,
    SOURCE_CLASS_STOCK_QUOTE,
    SOURCE_CLASS_COMPANY_HOMEPAGE,
    SOURCE_CLASS_FINANCIAL_AGGREGATOR,
    SOURCE_CLASS_DIRECTORY,
    SOURCE_CLASS_SEO_CONTENT,
    SOURCE_CLASS_REPUTABLE_BUSINESS_NEWS,
    SOURCE_CLASS_OFFICIAL_PRESS_RELEASE,
    TRIGGER_HARD_REJECT_CLASSES,
)
from services.trigger_discovery_service import (
    classify_source_tier,
    evaluate_event_semantics,
    event_semantics_score,
    event_semantics_verified,
    extract_event_date,
    extract_trigger_facility_link,
    fetch_and_verify_source_content,
    is_quote_grounded,
    SOURCE_TIER_A,
    SOURCE_TIER_B,
    SOURCE_TIER_D,
)
from services.deep_facility_resolver import DeepFacilityResolver
from services.signal_discovery_engine import filter_negative_financial_results


class TestUpstreamTriggerRecovery(unittest.TestCase):
    def setUp(self):
        self.ref_dt = datetime(2026, 9, 12, tzinfo=timezone.utc)
        self.facility_resolver = DeepFacilityResolver()

    # ─────────────────────────────────────────────────────────────────
    # Invariant 1: Stock Quote Hard Reject
    # ─────────────────────────────────────────────────────────────────
    def test_stock_quote_result_hard_reject(self):
        """Stock price quote pages must be hard-rejected deterministically."""
        stock_urls = [
            "https://www.moneycontrol.com/india/stockpricequote/pharmaceuticals/marksanspharma/MP",
            "https://economictimes.indiatimes.com/lumax-auto-technologies-ltd/stocks/companyid-18774.cms",
            "https://www.screener.in/company/MARKSANS/consolidated/",
            "https://trendlyne.com/equity/1234/marksans/",
            "https://www.bseindia.com/stock-share-price/marksans-pharma-ltd/marksans/532482/",
        ]
        for url in stock_urls:
            src_class = classify_source_class(url)
            self.assertEqual(src_class, SOURCE_CLASS_STOCK_QUOTE, f"Failed for {url}")
            self.assertIn(src_class, TRIGGER_HARD_REJECT_CLASSES)

            allowed, cls_name, reason = is_source_allowed_for_trigger(url)
            self.assertFalse(allowed, f"Should not allow {url}")
            self.assertIn("Deterministic hard reject", reason)

            tier = classify_source_tier(url)
            self.assertEqual(tier, SOURCE_TIER_D, f"Tier must be D for {url}")

    # ─────────────────────────────────────────────────────────────────
    # Invariant 2: Homepage Cannot Prove Expansion
    # ─────────────────────────────────────────────────────────────────
    def test_homepage_cannot_prove_expansion(self):
        """Generic company homepages and about pages cannot qualify as trigger sources."""
        homepages = [
            ("https://dixoninfo.com/", "dixoninfo.com"),
            ("https://dixoninfo.com/about-us", "dixoninfo.com"),
            ("https://www.anandgroupindia.com", "anandgroupindia.com"),
            ("https://www.anandgroupindia.com/overview", "anandgroupindia.com"),
        ]
        for url, official_dom in homepages:
            src_class = classify_source_class(url, official_domain=official_dom)
            self.assertEqual(src_class, SOURCE_CLASS_COMPANY_HOMEPAGE)

            allowed, _, reason = is_source_allowed_for_trigger(url, official_domain=official_dom)
            self.assertFalse(allowed)
            self.assertIn("COMPANY_HOMEPAGE", reason)

            tier = classify_source_tier(url, official_domain=official_dom)
            self.assertEqual(tier, SOURCE_TIER_D)

    # ─────────────────────────────────────────────────────────────────
    # Invariant 3: Snippet-Only False Positive Rejected
    # ─────────────────────────────────────────────────────────────────
    @patch("requests.get")
    def test_snippet_only_false_positive_rejected(self, mock_get):
        """When search snippet has keywords but fetched page lacks event semantics, reject."""
        # Simulated HTML of a routine financial article with no plant/expansion events
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.iter_content.return_value = [
            b"<html><head><title>Escorts Kubota Monthly Sales</title></head><body>"
            b"<p>Escorts Kubota sold 10,072 tractors in August 2026. Domestic sales were 9,500 units.</p>"
            b"<p>The share price traded flat on NSE and BSE today.</p>"
            b"</body></html>"
        ]
        mock_get.return_value = mock_resp

        search_title = "Escorts Kubota tractor capacity expansion sales"
        search_snippet = "Escorts Kubota announced capacity expansion and sales numbers for August 2026."

        res = fetch_and_verify_source_content(
            url="https://www.business-standard.com/markets/news/escorts-kubota-123.html",
            search_title=search_title,
            search_snippet=search_snippet,
        )

        self.assertFalse(res["verified"])
        self.assertEqual(res["status"], "REJECT_SEARCH_SNIPPET_FALSE_POSITIVE")
        self.assertIn("Search snippet suggested expansion, but fetched source content lacks event semantics", res["reason"])

    # ─────────────────────────────────────────────────────────────────
    # Invariant 4: Event Quote Grounding Verification
    # ─────────────────────────────────────────────────────────────────
    def test_event_quote_must_exist_in_source(self):
        """Quotes extracted by an LLM must be deterministically grounded in fetched text."""
        source_text = (
            "Suzuki Motor Gujarat commissioned its fourth assembly line at Hansalpur plant on 20 August 2026. "
            "The new line adds 250,000 units of annual production capacity with state-of-the-art metrology testing."
        )

        valid_quote = "Suzuki Motor Gujarat commissioned its fourth assembly line at Hansalpur plant"
        self.assertTrue(is_quote_grounded(valid_quote, source_text))

        # Normalized quote with different quotes/casing
        valid_quote_cased = '"suzuki motor gujarat commissioned its fourth assembly line"'
        self.assertTrue(is_quote_grounded(valid_quote_cased, source_text))

        # Hallucinated quote not in source
        hallucinated_quote = "Suzuki Motor Gujarat invested 1500 crore for electric vehicle battery line"
        self.assertFalse(is_quote_grounded(hallucinated_quote, source_text))

    # ─────────────────────────────────────────────────────────────────
    # Invariant 5 & 6: Date Truth & Disambiguation
    # ─────────────────────────────────────────────────────────────────
    def test_future_completion_date_not_used_as_trigger_date(self):
        """Future completion date (e.g. Aug 2028) must NOT become trigger_date or cause negative recency."""
        text = "Article published 10 September 2026. SKF India announced plant expansion with commissioning planned by August 2028."
        title = "SKF India New Manufacturing Plant"

        date_info = extract_event_date(text, title=title, now_dt=self.ref_dt, publication_date="2026-09-10")

        self.assertTrue(date_info["has_date"])
        self.assertTrue(date_info["is_future_planned_milestone"])
        # Commercial trigger date is the announcement date, NOT the 2028 future completion date
        self.assertEqual(date_info["event_date"], "2026-09-10")
        self.assertIn("2028", date_info["planned_completion_date"])
        # Recency days must be calculated against the announcement date (2 days), NEVER negative
        self.assertEqual(date_info["recency_days"], 2)
        self.assertEqual(date_info["ongoing_status"], "CURRENT")

    def test_publication_vs_event_vs_completion_date_separation(self):
        """Verify publication_date, event_date, and planned_completion_date are distinct fields."""
        text = "Tata Motors announced on 25 August 2026 that its new EV assembly plant completion target is December 2027."
        date_info = extract_event_date(text, now_dt=self.ref_dt, publication_date="2026-08-25")

        self.assertEqual(date_info["event_date"], "2026-08-25")
        self.assertEqual(date_info["publication_date"], "2026-08-25")
        self.assertIn("2027", date_info["planned_completion_date"])
        self.assertGreaterEqual(date_info["recency_days"], 0)

    # ─────────────────────────────────────────────────────────────────
    # Invariant 7: Facility Seed Decoupling Safety
    # ─────────────────────────────────────────────────────────────────
    def test_facility_seed_cannot_establish_trigger_to_facility(self):
        """Static seed directory knowledge of a plant cannot create DIRECT/STRONG linkage without event text proof."""
        company = "Marksans Pharma Limited"
        # Corporate-only trigger text that does NOT mention Goa or Verna
        corporate_trigger = "Marksans Pharma announced ₹150 Cr corporate capex program for production expansion across formulation lines."

        # 1. Trigger discovery service extraction
        res = extract_trigger_facility_link(
            text=corporate_trigger,
            known_city="Goa",
            known_industrial_area="Verna Industrial Estate",
            known_plants=["Verna Goa Plant"],
        )
        self.assertEqual(res["trigger_facility_specificity"], "COMPANY_ONLY")
        self.assertFalse(res["is_trigger_facility_corroborated"])
        self.assertEqual(res["facility_city_from_trigger"], "")

        # 2. Deep facility resolver
        deep_res = self.facility_resolver.resolve_facility(
            company_name=company,
            trigger_text=corporate_trigger,
            known_city="Goa",
            evidence_snippets=["Marksans Pharma is headquartered in Mumbai with plant in Verna Goa."],
        )
        # Linkage MUST be WEAK because the corporate trigger itself lacks location proof
        self.assertEqual(deep_res["linkage_confidence"], "WEAK")
        self.assertFalse(deep_res["facility_verified"])
        self.assertIsNone(deep_res["trigger_facility"])

    # ─────────────────────────────────────────────────────────────────
    # Invariant 8: Path-Level Source Classification
    # ─────────────────────────────────────────────────────────────────
    def test_path_level_source_classification(self):
        """Same domain must be classified differently based on URL path."""
        # Moneycontrol
        mc_stock = "https://www.moneycontrol.com/india/stockpricequote/pharmaceuticals/marksanspharma/MP"
        mc_news = "https://www.moneycontrol.com/news/business/companies/maruti-suzuki-to-invest-capex-12345.html"
        self.assertEqual(classify_source_class(mc_stock), SOURCE_CLASS_STOCK_QUOTE)
        self.assertEqual(classify_source_class(mc_news), SOURCE_CLASS_REPUTABLE_BUSINESS_NEWS)
        self.assertFalse(is_source_allowed_for_trigger(mc_stock)[0])
        self.assertTrue(is_source_allowed_for_trigger(mc_news)[0])

        # Economic Times
        et_stock = "https://economictimes.indiatimes.com/lumax-auto-technologies-ltd/stocks/companyid-18774.cms"
        et_news = "https://economictimes.indiatimes.com/industry/auto/auto-news/maruti-inaugurates-new-line/articleshow/98765.cms"
        self.assertEqual(classify_source_class(et_stock), SOURCE_CLASS_STOCK_QUOTE)
        self.assertEqual(classify_source_class(et_news), SOURCE_CLASS_REPUTABLE_BUSINESS_NEWS)
        self.assertFalse(is_source_allowed_for_trigger(et_stock)[0])
        self.assertTrue(is_source_allowed_for_trigger(et_news)[0])

    # ─────────────────────────────────────────────────────────────────
    # Invariant 9: Generic Financial Noise Rejected in Engine
    # ─────────────────────────────────────────────────────────────────
    def test_filter_negative_financial_results_drops_stock_pages(self):
        """filter_negative_financial_results must strip all stock quote URLs and ticker noise."""
        raw_results = [
            {
                "url": "https://www.moneycontrol.com/india/stockpricequote/auto/maruti/MS24",
                "title": "Maruti Suzuki Share Price, Stock Price today",
                "content": "Maruti Suzuki India stock price, live share price, capacity and volume.",
            },
            {
                "url": "https://www.screener.in/company/MARUTI/",
                "title": "Maruti Suzuki India Ltd financial results",
                "content": "Market cap, P/E ratio, quarterly profit and balance sheet.",
            },
            {
                "url": "https://autocarpro.in/news/maruti-suzuki-commissions-fourth-assembly-line-at-gujarat-plant",
                "title": "Maruti Suzuki commissions fourth assembly line at Gujarat plant",
                "content": "Suzuki Motor Gujarat commissioned its fourth assembly line adding 250,000 units capacity.",
            },
        ]
        filtered = filter_negative_financial_results(raw_results)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["url"], "https://autocarpro.in/news/maruti-suzuki-commissions-fourth-assembly-line-at-gujarat-plant")


if __name__ == "__main__":
    unittest.main()
