"""Unit tests for Salesoorja Entity Resolution Service."""
import unittest

from services.entity_resolution import (
    CANONICAL_TARGET_ENTITIES,
    get_canonical_profile,
    resolve_entity_match,
)


class TestEntityResolution(unittest.TestCase):
    def test_canonical_profiles_loaded(self):
        self.assertGreaterEqual(len(CANONICAL_TARGET_ENTITIES), 13)
        self.assertIsNotNone(get_canonical_profile("Bharat Forge Ltd"))
        self.assertIsNotNone(get_canonical_profile("Kaynes Technology India Ltd"))
        self.assertIsNotNone(get_canonical_profile("Gabriel India Ltd"))

    def test_wrong_entity_rejected_bharatgas_for_bharat_forge(self):
        conf, reason = resolve_entity_match(
            company_name="Bharat Forge Ltd",
            source_url="https://my.ebharatgas.com/bharatgas/Home/Index",
            source_domain="my.ebharatgas.com",
            source_title="Bharatgas LPG cylinder booking",
            snippet="With a legacy spanning 40 years Bharatgas provides clean cooking fuel across India BPCL.",
        )
        self.assertEqual(conf, "WRONG_ENTITY")
        self.assertIn("ebharatgas", reason)

    def test_wrong_entity_rejected_bharatgas_for_bharat_bijlee(self):
        conf, reason = resolve_entity_match(
            company_name="Bharat Bijlee Ltd",
            source_url="https://my.ebharatgas.com/bharatgas/Home/Index",
            source_domain="my.ebharatgas.com",
            source_title="Bharatgas",
            snippet="Bharatgas LPG cylinder delivery",
        )
        self.assertEqual(conf, "WRONG_ENTITY")

    def test_wrong_entity_rejected_voltamp_electricals_for_voltamp_transformers(self):
        conf, reason = resolve_entity_match(
            company_name="Voltamp Transformers Ltd",
            source_url="https://www.voltamp.in/about-us",
            source_domain="www.voltamp.in",
            source_title="Voltamp Electricals Pvt Ltd",
            snippet="Welcome to Voltamp Electricals Pvt Ltd, leading manufacturer of switchgear panel boards.",
        )
        self.assertEqual(conf, "WRONG_ENTITY")

    def test_exact_entity_official_domain(self):
        conf, reason = resolve_entity_match(
            company_name="Gabriel India Ltd",
            source_url="https://www.anandgroupindia.com/gabrielindia/about-us",
            source_domain="www.anandgroupindia.com",
            source_title="Gabriel India Ltd - Anand Group",
            snippet="Gabriel India has become synonymous with ride comfort in India, manufacturing shock absorbers.",
        )
        self.assertEqual(conf, "EXACT_ENTITY")
        self.assertIn("matches official corporate domain", reason)

    def test_exact_entity_kaynes_semicon(self):
        conf, reason = resolve_entity_match(
            company_name="Kaynes Technology India Ltd",
            source_url="https://www.kaynestechnology.co.in/investors.html",
            source_domain="www.kaynestechnology.co.in",
            source_title="Kaynes Technology Investors",
            snippet="Kaynes Technology India Limited investment in Sanand OSAT semiconductor line.",
        )
        self.assertEqual(conf, "EXACT_ENTITY")

    def test_strong_entity_reputable_news_with_full_context(self):
        conf, reason = resolve_entity_match(
            company_name="Bharat Forge Ltd",
            source_url="https://economictimes.indiatimes.com/industry/auto/auto-news/bharat-forge-expands-baramati-plant/articleshow/1000.cms",
            source_domain="economictimes.indiatimes.com",
            source_title="Bharat Forge expands Baramati forging facility with 200 cr capex",
            snippet="Kalyani Group flagship Bharat Forge Limited announces capex expansion at its Baramati precision plant.",
        )
        self.assertEqual(conf, "STRONG_ENTITY")

    def test_ambiguous_entity_insufficient_tokens(self):
        conf, reason = resolve_entity_match(
            company_name="Gabriel India Ltd",
            source_url="https://en.wikipedia.org/wiki/Gabriel_Magalh%C3%A3es",
            source_domain="en.wikipedia.org",
            source_title="Gabriel Magalhães - Wikipedia",
            snippet="Gabriel dos Santos Magalhães is a professional footballer.",
        )
        self.assertIn(conf, ("AMBIGUOUS_ENTITY", "WRONG_ENTITY"))


if __name__ == "__main__":
    unittest.main()
