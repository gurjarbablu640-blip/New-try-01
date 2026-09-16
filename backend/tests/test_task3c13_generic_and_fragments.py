"""Unit test suite for Task 3C.1.3 - Close Generic Category + Incomplete Headline Entity Leaks.

Validates:
CASE A: "Electronics manufacturing services" from /tag/ URL -> GENERIC_INDUSTRY_TERM / non-company.
CASE B: "Electronics Manufacturing Services Private Limited" on official company page -> COMPANY.
CASE C: "India’s Top Fastest" from "India's Top Fastest-Growing EMS Companies" -> ARTICLE_HEADLINE_FRAGMENT.
CASE D: "Toyota to roll out solid-state battery EVs..." -> "Toyota".
CASE E: "India to roll out EV incentives" -> India NOT accepted as company.
CASE F: "Government to roll out manufacturing scheme" -> non-company.
CASE G: "CompanyName to introduce new production line" -> CompanyName retained.
CASE H: "Bosch to manufacture new component" -> Bosch retained.
CASE I: "HARMAN invests..." -> HARMAN retained.
CASE J: "Super Screws commissions..." -> Super Screws retained.
CASE K: all Task 3C.1 + 3C.1.2 known negatives remain rejected.
"""
import unittest

from services.entity_truth_gate import (
    EntityType,
    classify_entity_candidate,
    extract_clean_company_name_from_title,
    trim_headline_subject_boundary,
    validate_company_entity,
    resolve_canonical_company_identity,
    reset_entity_telemetry,
)


class TestTask3C13GenericAndFragments(unittest.TestCase):
    def setUp(self):
        reset_entity_telemetry()

    def test_case_a_generic_industry_category_rejected(self):
        """CASE A: 'Electronics manufacturing services' from tag URL must be rejected as generic."""
        url = "https://manufacturing.economictimes.indiatimes.com/tag/electronics+manufacturing+services"
        res = classify_entity_candidate("Electronics manufacturing services", url=url)
        self.assertFalse(res["is_company"])
        self.assertEqual(res["entity_class"], EntityType.GENERIC_INDUSTRY_TERM)

        # Also test bare candidate without URL
        res_bare = classify_entity_candidate("Electronics manufacturing services")
        self.assertFalse(res_bare["is_company"])
        self.assertEqual(res_bare["entity_class"], EntityType.GENERIC_INDUSTRY_TERM)

        # Test extraction from tag page title
        title = "Electronics manufacturing services - Latest electronics manufacturing news"
        extracted = extract_clean_company_name_from_title(title, url=url)
        self.assertEqual(extracted, "")

    def test_case_b_generic_phrase_with_legal_suffix_accepted(self):
        """CASE B: 'Electronics Manufacturing Services Private Limited' on official company page -> COMPANY."""
        name = "Electronics Manufacturing Services Private Limited"
        url = "https://www.ems-india.com"
        res = classify_entity_candidate(name, url=url)
        self.assertTrue(res["is_company"])
        self.assertEqual(res["entity_class"], EntityType.COMPANY)
        self.assertGreaterEqual(res["confidence"], 0.90)

    def test_case_c_superlative_headline_fragment_rejected(self):
        """CASE C: 'India’s Top Fastest' from listicle title must be rejected as headline fragment."""
        title = "India's Top Fastest-Growing EMS Companies"
        url = "https://www.cxotoday.com/press-release/indias-top-fastest-growing-ems-companies/"

        # With title context
        res_ctx = classify_entity_candidate("India’s Top Fastest", context_text=title, url=url)
        self.assertFalse(res_ctx["is_company"])
        self.assertEqual(res_ctx["entity_class"], EntityType.ARTICLE_HEADLINE_FRAGMENT)

        # Bare candidate
        res_bare = classify_entity_candidate("India’s Top Fastest")
        self.assertFalse(res_bare["is_company"])
        self.assertEqual(res_bare["entity_class"], EntityType.ARTICLE_HEADLINE_FRAGMENT)

        # ASCII apostrophe
        res_ascii = classify_entity_candidate("India's Top Fastest")
        self.assertFalse(res_ascii["is_company"])
        self.assertEqual(res_ascii["entity_class"], EntityType.ARTICLE_HEADLINE_FRAGMENT)

    def test_case_d_toyota_headline_boundary_trimmed(self):
        """CASE D: 'Toyota to roll out solid-state battery EVs...' -> 'Toyota'."""
        title = "Toyota to roll out solid-state battery EVs globally in a couple years, India executive says"
        subj, did_trim = trim_headline_subject_boundary(title)
        self.assertTrue(did_trim)
        self.assertEqual(subj, "Toyota")

        clean = extract_clean_company_name_from_title(title)
        self.assertEqual(clean, "Toyota")

        res = resolve_canonical_company_identity(title=title)
        self.assertTrue(res["is_valid"])
        self.assertEqual(res["company_name"], "Toyota")

    def test_case_e_india_fail_closed(self):
        """CASE E: 'India to roll out EV incentives' -> India NOT accepted as company."""
        title = "India to roll out EV incentives"
        subj, did_trim = trim_headline_subject_boundary(title)
        self.assertFalse(did_trim)
        self.assertNotEqual(subj, "India")

        clean = extract_clean_company_name_from_title(title)
        self.assertEqual(clean, "")

    def test_case_f_government_fail_closed(self):
        """CASE F: 'Government to roll out manufacturing scheme' -> non-company."""
        title = "Government to roll out manufacturing scheme"
        subj, did_trim = trim_headline_subject_boundary(title)
        self.assertFalse(did_trim)
        self.assertNotEqual(subj, "Government")

        clean = extract_clean_company_name_from_title(title)
        self.assertEqual(clean, "")

    def test_case_g_company_name_to_introduce(self):
        """CASE G: 'CompanyName to introduce new production line' -> CompanyName retained."""
        title = "Tata Motors to introduce new production line in Gujarat"
        subj, did_trim = trim_headline_subject_boundary(title)
        self.assertTrue(did_trim)
        self.assertEqual(subj, "Tata Motors")

    def test_case_h_bosch_to_manufacture(self):
        """CASE H: 'Bosch to manufacture new component' -> Bosch retained."""
        title = "Bosch to manufacture new component at Bengaluru plant"
        subj, did_trim = trim_headline_subject_boundary(title)
        self.assertTrue(did_trim)
        self.assertEqual(subj, "Bosch")

    def test_case_i_harman_invests(self):
        """CASE I: 'HARMAN invests...' -> HARMAN still retained."""
        title = "HARMAN invests Rs 345 crore to expand Pune automotive manufacturing plant"
        subj, did_trim = trim_headline_subject_boundary(title)
        self.assertTrue(did_trim)
        self.assertEqual(subj, "HARMAN")

    def test_case_j_super_screws_commissions(self):
        """CASE J: 'Super Screws commissions...' -> Super Screws still retained."""
        title = "Super Screws commissions vertically integrated cold forging fastener manufacturing facility in Haryana"
        subj, did_trim = trim_headline_subject_boundary(title)
        self.assertTrue(did_trim)
        self.assertEqual(subj, "Super Screws")

    def test_case_k_all_prior_regressions_remain_rejected(self):
        """CASE K: All Task 3C.1 + Task 3C.1.2 known negatives remain rejected."""
        prior_negatives = [
            "ProjectX India",
            "pv magazine India",
            "Automobile, Auto Components & EV",
            "Business Data & Market Insights",
            "EV Charging Station Franchise",
            "Daily Morning Newsletter",
            "A 40 Billion",
            "ion cell",
            "Omprakash Singh Bisht",
            "JMK Research",
            "Mega",
            "IBEF",
            "Ems profiles",
            "Our Businesses",
            "Moulding Apqp Jobs",
            "Solar Module",
            "Maruti Suzuki has",
            "ITP Aero has",
        ]
        for neg in prior_negatives:
            res = classify_entity_candidate(neg)
            self.assertFalse(res["is_company"], f"Prior negative '{neg}' must be rejected, got {res}")


if __name__ == "__main__":
    unittest.main()
