import asyncio
import unittest
from unittest.mock import patch

from services.crawl4ai_pipeline import (
    crawl_company_pipeline,
    extract_triggers_from_content,
    generate_company_target_urls,
    is_same_registered_domain,
    normalize_url,
    _CRAWL_CACHE,
)


class Crawl4AIPipelineTests(unittest.TestCase):
    def setUp(self):
        _CRAWL_CACHE.clear()

    def test_url_normalization_and_domain_restriction(self):
        self.assertEqual(
            normalize_url("https://www.valeo.com/en/news/?utm_source=feed#headline"),
            "https://www.valeo.com/en/news",
        )
        self.assertTrue(is_same_registered_domain("https://valeo.com", "https://news.valeo.com/press"))
        self.assertFalse(is_same_registered_domain("https://valeo.com", "https://unrelated-competitor.com"))

    def test_target_url_generation(self):
        targets = generate_company_target_urls("https://kehems.com", max_urls=4)
        self.assertEqual(len(targets), 4)
        self.assertIn("https://kehems.com", targets)
        self.assertIn("https://kehems.com/news", targets)

    def test_trigger_extraction_from_markdown(self):
        content = """
        # Press Release: Sanand Facility Expansion
        Valeo has commenced commercial production at our new plant in Sanand, Gujarat.
        The brownfield capacity expansion includes a state-of-the-art CNC machining bay.
        We have commissioned a dedicated testing laboratory with a high-precision CMM.
        We are actively hiring a Lead Metrology Engineer and QA Manager.
        """
        triggers = extract_triggers_from_content(content, "https://valeo.com/news/expansion")
        categories = {t["category"] for t in triggers}
        self.assertIn("NEW_PLANT_COMMISSIONING", categories)
        self.assertIn("EXPANSION", categories)
        self.assertIn("MACHINERY", categories)
        self.assertIn("LABORATORY", categories)
        self.assertIn("METROLOGY_HIRING", categories)

    def test_crawl_pipeline_with_mock_crawler_and_caching(self):
        class MockOutcome:
            markdown = "Company inaugurated a new plant and upgraded its testing laboratory in Indore."

        class MockCrawler:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                return False
            async def arun(self, *, url):
                return MockOutcome()

        with patch("services.document_extraction._public_http_url", return_value=(True, "")):
            res1 = asyncio.run(
                crawl_company_pipeline(
                    "https://kehems.com",
                    seed_urls=["https://kehems.com/news"],
                    crawler=MockCrawler(),
                )
            )
            self.assertEqual(res1["total_triggers_found"], 2)
            self.assertTrue(res1["needs_deep_browser_reasoning"])
            self.assertEqual(res1["pages_crawled"][0]["status"], "SUCCESS")

            # Second run with same URL must hit the 24h cache without calling arun again
            res2 = asyncio.run(
                crawl_company_pipeline(
                    "https://kehems.com",
                    seed_urls=["https://kehems.com/news"],
                    crawler=MockCrawler(),
                )
            )
            self.assertEqual(res2["pages_crawled"][0]["status"], "CACHED")


if __name__ == "__main__":
    unittest.main()
