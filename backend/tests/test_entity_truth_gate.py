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
)
from services.signal_discovery_engine import _resolve_live_facility


class TestEntityTruthGate(unittest.TestCase):
    """Guarantees non-companies are blocked from entering the opportunity funnel."""

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
        # Generic city mention without a physical manufacturing facility, cluster, or unit
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
