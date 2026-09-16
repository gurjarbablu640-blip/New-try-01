"""Regression tests proving company-entity truth gates and facility truth gates.

Enforces:
- public figure cannot be company
- headline fragment cannot be company
- location alone cannot be company
- event / scheme cannot be company
- generic noun / adjective cannot be company
- facility=None cannot pass
- real company + no physical facility -> HOLD
- real company + evidence-backed facility -> PASS
"""
import unittest

from services.entity_truth_gate import (
    extract_clean_company_name_from_title,
    validate_company_entity,
    resolve_canonical_company_identity,
)
from services.signal_discovery_engine import (
    _resolve_live_facility,
    ingest_discovered_signal_lead,
)


class TestEntityTruthGate(unittest.TestCase):
    """Guarantees non-companies are blocked from entering the opportunity funnel."""

    def test_generic_page_and_navigation_labels_rejected(self):
        """Webpage navigation, content headings, and generic section titles must be rejected."""
        generic_labels = [
            "Our Businesses",
            "About Us",
            "Who We Are",
            "Our Company",
            "Our Products",
            "Our Services",
            "Business",
            "Businesses",
            "Home",
            "News",
            "Media",
            "Careers",
            "Contact Us",
            "Investor Relations",
            "Locations",
            "Manufacturing",
            "Industries",
            "Solutions",
            "Overview",
        ]
        for label in generic_labels:
            valid, reason = validate_company_entity(label)
            self.assertFalse(valid, f"Expected generic label '{label}' to be rejected, but passed. Reason: {reason}")
            self.assertTrue(
                "generic" in reason.lower() or "invalid" in reason.lower() or "single generic" in reason.lower(),
                f"Rejection reason for '{label}' should identify it as generic: {reason}",
            )

    def test_real_companies_containing_common_words_pass(self):
        """Genuine organizations containing words like 'Industries', 'Solutions', 'Motors' must pass."""
        real_companies = [
            "Reliance Industries",
            "Tata Motors",
            "Bharat Forge",
            "Kaynes Technology",
            "Apex Auto Solutions",
            "Schneider Electric",
            "Adani Enterprises",
            "Mahindra Logistics",
            "Larsen & Toubro",
            "Sterlite Technologies",
            "Jindal Steel & Power",
        ]
        for name in real_companies:
            valid, reason = validate_company_entity(name)
            self.assertTrue(valid, f"Expected real company '{name}' to pass, but rejected: {reason}")

    def test_public_figure_cannot_be_company(self):
        """Public figures, politicians, and official titles must be rejected."""
        figures = [
            "PM Modi",
            "Prime Minister Narendra Modi",
            "Chief Minister of Uttar Pradesh, Yogi Adityanath",
            "Gujarat CM",
            "Honourable Chief Minister Shri Yogi Adityanath",
            "Honourable Minister for Information Technology",
        ]
        for name in figures:
            valid, reason = validate_company_entity(name)
            self.assertFalse(valid, f"Expected '{name}' to be rejected, but passed. Reason: {reason}")
            self.assertIn("public figure", reason.lower())

    def test_headline_fragment_cannot_be_company(self):
        """Action verbs, questions, and predicate phrases must be rejected."""
        headlines = [
            "PM Modi Launches Indias Semiconductor Future",
            "Source India 2026 Inaugurated in Chennai",
            "Decoding Tamil Nadus 2026 Scheme Landscape",
            "11 Verified Upcoming Industrial Projects in Haryana",
            "Did you know the worlds largest single",
            "Rajasthan Operationalizes Indias 13th Semiconductor Unit",
            "UPs Industrial Revolution Begins",
        ]
        for name in headlines:
            valid, reason = validate_company_entity(name)
            self.assertFalse(valid, f"Expected '{name}' to be rejected, but passed. Reason: {reason}")

    def test_location_alone_cannot_be_company(self):
        """Geographic states, cities, and regional hubs must be rejected."""
        locations = [
            "Maharashtra",
            "Gujarat",
            "Tamil Nadu",
            "Bikaner",
            "Kheda",
            "Kalpakkam",
            "Gujarat Semiconductor Hub",
        ]
        for name in locations:
            valid, reason = validate_company_entity(name)
            self.assertFalse(valid, f"Expected '{name}' to be rejected, but passed. Reason: {reason}")

    def test_event_and_generic_nouns_cannot_be_company(self):
        """Expos, generic adjectives, and press notes must be rejected."""
        non_companies = [
            "HUGE",
            "Press Notes",
            "REV Expo 2026",
            "Source India 2026",
        ]
        for name in non_companies:
            valid, reason = validate_company_entity(name)
            self.assertFalse(valid, f"Expected '{name}' to be rejected, but passed. Reason: {reason}")

    def test_real_companies_pass_entity_gate(self):
        """Genuine corporate entities must pass the entity gate."""
        companies = [
            "Jabil",
            "Taural India",
            "BEUMER",
            "Stauff India",
            "Zetwerk",
            "Minda Corporation Ltd",
            "Tata Motors",
            "Premier Energies",
            "Infineum",
        ]
        for name in companies:
            valid, reason = validate_company_entity(name)
            self.assertTrue(valid, f"Expected '{name}' to pass, but rejected: {reason}")

    def test_title_extraction_isolates_real_company(self):
        """News headlines with verbs extract the clean subject organization or reject non-companies."""
        self.assertEqual(
            extract_clean_company_name_from_title("Micron Celebrates Opening of Indias First Semiconductor"),
            "Micron",
        )
        self.assertEqual(
            extract_clean_company_name_from_title("Hitachi Energy secures Indias grid future with major"),
            "Hitachi Energy",
        )
        self.assertEqual(
            extract_clean_company_name_from_title("Premier Energies Launches 5.6 GW Solar Module"),
            "Premier Energies",
        )
        # Headlines with political subjects are rejected
        self.assertEqual(
            extract_clean_company_name_from_title("PM Modi Launches Indias Semiconductor Future"),
            "",
        )
        self.assertEqual(
            extract_clean_company_name_from_title("Decoding Tamil Nadus 2026 Scheme Landscape"),
            "",
        )


class TestCanonicalCompanyResolution(unittest.TestCase):
    """Tests bounded canonical company resolution and zero-invention guards."""

    def test_generic_title_with_real_company_segment_resolves_grounded_company(self):
        """A title with 'Our Businesses - Apex Electronics' must resolve to 'Apex Electronics', not the generic heading."""
        res = resolve_canonical_company_identity(
            raw_candidate="Our Businesses",
            title="Our Businesses - Apex Electronics - Overview",
            snippet="Apex Electronics operates precision manufacturing facilities in Hosur.",
            url="https://www.apexelectronics.com/what-we-do",
        )
        self.assertTrue(res["is_valid"], f"Resolution should be valid, got: {res}")
        self.assertEqual(res["company_name"], "Apex Electronics")
        self.assertNotEqual(res["company_name"], "Our Businesses")
        self.assertIn(res["canonicalization_method"], ("DOMAIN_CORROBORATED", "EXPLICIT_TITLE_OR_SNIPPET"))
        self.assertGreaterEqual(res["confidence"], 0.88)

    def test_generic_page_title_with_explicit_company_in_snippet(self):
        """When title is merely 'About Us', an explicit corporate name in the snippet is canonicalized."""
        res = resolve_canonical_company_identity(
            raw_candidate="About Us",
            title="About Us",
            snippet="Zenith Instruments Ltd specializes in high-precision metrology sensors across India.",
            url="https://zenithinstruments.com/about",
        )
        self.assertTrue(res["is_valid"], f"Resolution should be valid, got: {res}")
        self.assertEqual(res["company_name"], "Zenith Instruments Ltd")
        self.assertIn(res["canonicalization_method"], ("DOMAIN_CORROBORATED", "EXPLICIT_TITLE_OR_SNIPPET"))

    def test_generic_page_title_without_grounded_text_evidence_holds_zero_invention(self):
        """A generic heading with NO grounded corporate name in text must HOLD (zero-invention: do not guess from domain)."""
        res = resolve_canonical_company_identity(
            raw_candidate="Our Products",
            title="Our Products - Product Catalog",
            snippet="We offer high quality equipment and solutions for all industrial needs.",
            url="https://www.randomdomainxyz.com/products",
        )
        self.assertFalse(res["is_valid"], "Must NOT invent a company name from domain without text grounding")
        self.assertEqual(res["company_name"], "")
        self.assertEqual(res["canonicalization_method"], "UNKNOWN")
        self.assertEqual(res["confidence"], 0.0)

    def test_company_name_domain_contradiction_reduces_confidence_and_holds(self):
        """When extracted company contradicts an unrelated corporate domain, it must be rejected or held."""
        res = resolve_canonical_company_identity(
            raw_candidate="Larsen & Toubro",
            title="Larsen & Toubro Leadership",
            snippet="Overview of engineering divisions.",
            url="https://godrej.com/careers",
        )
        self.assertFalse(res["is_valid"], "Entity contradicting corporate domain must fail validity")
        self.assertIn("contradicts", str(res.get("rejection_reason") or "").lower())

    def test_trade_media_domain_does_not_trigger_domain_contradiction(self):
        """Industry/trade media domains reporting on a company must not trigger domain contradiction."""
        res = resolve_canonical_company_identity(
            raw_candidate="Tata Motors",
            title="Tata Motors Expands Commercial Vehicle Lineup",
            snippet="Tata Motors announced new EV bus production at Dharwad.",
            url="https://www.autocarpro.in/news/tata-motors-expands-commercial-lineup",
        )
        self.assertTrue(res["is_valid"], "Trade media report should not contradict genuine company")
        self.assertEqual(res["company_name"], "Tata Motors")


class TestPersistenceEntityGate(unittest.TestCase):
    """Guarantees invalid or generic entities cannot create Company DB rows."""

    def test_ingest_discovered_signal_lead_rejects_generic_entity(self):
        from unittest.mock import MagicMock
        mock_db = MagicMock()

        result = ingest_discovered_signal_lead(
            db=mock_db,
            company_name="Our Businesses",
            city="Hosur",
            state="Tamil Nadu",
            industry="Electronics",
            signal_type="plant_expansion",
            event_title="Our Businesses",
            event_description="Overview of our business divisions.",
            evidence_url="https://www.someunknownsite.com/what-we-do",
        )

        self.assertEqual(result.get("status"), "rejected_invalid_entity")
        self.assertIsNone(result.get("company_id"))
        mock_db.add.assert_not_called()
        mock_db.commit.assert_not_called()


class TestFacilityTruthGate(unittest.TestCase):
    """Guarantees facility=None and ungrounded facilities cannot pass validation."""

    def test_facility_none_cannot_pass(self):
        """A facility evaluation with facility_name=None must never be marked verified."""
        evidence_text = "General news article without physical plant mention."
        res = _resolve_live_facility("Jabil", evidence_text)
        self.assertFalse(res.get("facility_verified"), "facility_verified must be False when no facility resolved")
        self.assertIn(res.get("linkage_confidence"), ("UNKNOWN", "WEAK"))
        self.assertIsNone(res.get("facility_name"))

    def test_real_company_no_physical_facility_holds(self):
        """A real company mentioned with a city but no physical manufacturing plant evidence must HOLD."""
        evidence_text = "BEUMER signed a commercial partnership agreement in Jaipur, Rajasthan."
        res = _resolve_live_facility("BEUMER", evidence_text)
        self.assertFalse(res.get("facility_verified"))
        self.assertIn(res.get("linkage_confidence"), ("UNKNOWN", "WEAK"))

    def test_real_company_evidence_backed_facility_passes(self):
        """A real company with an explicit industrial cluster/unit must PASS."""
        evidence_text = "Jabil inaugurates new electronics manufacturing plant at MIDC Ranjangaon, Pune."
        res = _resolve_live_facility("Jabil", evidence_text)
        self.assertTrue(res.get("facility_verified"))
        self.assertIn(res.get("linkage_confidence"), ("DIRECT", "STRONG"))
        self.assertIsNotNone(res.get("facility_name"))
        self.assertTrue(len(str(res.get("facility_name"))) > 3)


if __name__ == "__main__":
    unittest.main()
