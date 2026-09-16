import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Task 3C.1.2 Focused Regression: Project Tracker & B2B Portal Suppression.

Validates that:
- Case A: Project tracker article suppresses portal (ProjectX India) and extracts manufacturer (Voltamp Transformers).
- Case B: New-project database category page suppresses portal and fails closed (UNKNOWN/empty).
- Case C: Industrial media article suppresses publisher (pv magazine) and extracts manufacturer (Premier Energies).
- Case D: Real manufacturer newsroom page preserves company (Waaree Energies).
- Case E: Legitimate company containing 'Projects' (Tata Projects Limited) is NOT rejected solely because of 'Projects'.
- Case F: Portal about page without manufacturing evidence is rejected.
- Case G: Ambiguous site identity is classified as non-company / fails closed.
- Case H: Task 3C.1 known legitimate companies remain accepted.
"""
import unittest
from services.entity_truth_gate import (
    EntityType,
    classify_entity_candidate,
    extract_clean_company_name_from_title,
    trim_headline_subject_boundary,
    validate_company_entity,
    reset_entity_telemetry,
)
from services.structured_evidence_extractor import extract_structured_evidence


class TestTask3C12PortalSuppression(unittest.TestCase):
    """Test suite for Task 3C.1.2 portal suppression and source vs subject distinction."""

    def setUp(self):
        reset_entity_telemetry()

    def test_case_a_project_tracker_article(self):
        """Case A: Project tracker article about real manufacturer."""
        title = "Voltamp Transformers to supply power transformers to GETCO - ProjectX India"
        url = "https://projectxindia.com/2025/11/01/voltamp-transformers-to-supply-power-transformers-to-getco/"
        
        # 1. Tracker identity must be rejected
        cls_tracker = classify_entity_candidate("ProjectX India", url=url)
        self.assertFalse(cls_tracker["is_company"], "ProjectX India must not be accepted as a COMPANY")
        self.assertIn(cls_tracker["entity_class"], (EntityType.PUBLISHER, EntityType.NEWS_SOURCE, EntityType.DIRECTORY))
        
        # 2. Manufacturer must be extracted from headline
        extracted = extract_clean_company_name_from_title(title, url=url)
        self.assertEqual(extracted, "Voltamp Transformers")
        
        # 3. Structured evidence extraction on body
        body = "Voltamp Transformers has secured a contract to supply power transformers to GETCO in Gujarat."
        ev = extract_structured_evidence(text=body, title=title, url=url)
        self.assertEqual(ev.get("company"), "Voltamp Transformers")

    def test_case_b_project_database_category_page(self):
        """Case B: New-project database category page fails closed."""
        title = "Welcome to New Project Tracker - Projects India"
        url = "https://www.newprojectstracker.net/projects-india/manufacturing?page=4"
        
        cls_p1 = classify_entity_candidate("Welcome to New Project Tracker", url=url)
        self.assertFalse(cls_p1["is_company"])
        
        cls_p2 = classify_entity_candidate("Projects India", url=url)
        self.assertFalse(cls_p2["is_company"])
        
        extracted = extract_clean_company_name_from_title(title, url=url)
        self.assertEqual(extracted, "", "Category page must not extract a company name")

    def test_case_c_industrial_media_article(self):
        """Case C: Industrial media article suppresses publisher and extracts manufacturer."""
        title = "Premier Energies commissions 5.6 GW solar module facility in Telangana - pv magazine India"
        url = "https://www.pv-magazine.com/2026/03/31/premier-energies-commissions-5-6-gw-solar-module-facility-in-india/"
        
        cls_pub = classify_entity_candidate("pv magazine India", url=url)
        self.assertFalse(cls_pub["is_company"])
        self.assertEqual(cls_pub["entity_class"], EntityType.PUBLISHER)
        
        extracted = extract_clean_company_name_from_title(title, url=url)
        self.assertEqual(extracted, "Premier Energies")

    def test_case_d_manufacturer_newsroom_page(self):
        """Case D: Real manufacturer newsroom page is preserved."""
        title = "Waaree Energies Announces New Solar Module Capacity in Gujarat"
        url = "https://www.waaree.com/news/announcement"
        
        cls_mfg = classify_entity_candidate("Waaree Energies", url=url)
        self.assertTrue(cls_mfg["is_company"])
        self.assertEqual(cls_mfg["entity_class"], EntityType.COMPANY)
        
        extracted = extract_clean_company_name_from_title(title, url=url)
        self.assertEqual(extracted, "Waaree Energies")

    def test_case_e_company_containing_projects(self):
        """Case E: Legitimate company containing 'Projects' is not rejected."""
        cand = "Tata Projects Limited"
        cls_proj = classify_entity_candidate(cand)
        self.assertTrue(cls_proj["is_company"], "Tata Projects Limited must be accepted as COMPANY")
        self.assertEqual(cls_proj["entity_class"], EntityType.COMPANY)
        
        title = "Tata Projects Limited to execute major industrial EPC facility in Gujarat"
        extracted = extract_clean_company_name_from_title(title)
        self.assertEqual(extracted, "Tata Projects Limited")

    def test_case_f_portal_about_page(self):
        """Case F: Portal about page with no manufacturing evidence."""
        context = "About ProjectX India - Industrial Project Tracking and Market Intelligence"
        url = "https://projectxindia.com/about-us"
        
        cls_about = classify_entity_candidate("ProjectX India", context_text=context, url=url)
        self.assertFalse(cls_about["is_company"])
        self.assertIn(cls_about["entity_class"], (EntityType.PUBLISHER, EntityType.DIRECTORY))

    def test_case_g_ambiguous_site_identity(self):
        """Case G: Ambiguous site identity fails closed."""
        url = "https://projects-alert.com/"
        cls_amb = classify_entity_candidate("Industrial Projects Alert", url=url)
        self.assertFalse(cls_amb["is_company"])

    def test_case_h_known_companies_remain_accepted(self):
        """Case H: Task 3C.1 known legitimate companies remain accepted."""
        known = [
            "Waaree Energies",
            "Tata Electronics",
            "Neuron Energy",
            "RenewSys",
            "Balaji Speciality Chemicals",
            "Ecosyms Solutions",
            "Voltamp Transformers",
            "Premier Energies",
        ]
        for name in known:
            res = classify_entity_candidate(name)
            self.assertTrue(res["is_company"], f"Company '{name}' must remain accepted")
            self.assertEqual(res["entity_class"], EntityType.COMPANY)


if __name__ == "__main__":
    unittest.main()
