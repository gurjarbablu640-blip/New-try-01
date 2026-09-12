"""Targeted unit tests for Person Name Extraction, Current Employment, and Facility Cross-Check.

Verifies:
- Phase 1: Upstream rejection of generic roles, subsystems, governance headers, corporate entities.
- Phase 1: Preservation of real Indian names.
- Phase 2: Current employment hardening (Schneider / Himanshu Sharma contradicted).
- Phase 3: Facility-person mismatch detection (Tata Motors / Avijit Sen Sanand vs Dharwad,
           RR Kabel / Praveen Kumar Waghodia vs Baddi, Dixon / Anil Razdan Oragadam vs Noida).
- Phase 4: Junior individual contributor authority classification.
"""
import unittest

from services.person_intelligence_service import (
    is_human_person_candidate,
    classify_current_employment,
    classify_facility_relationship,
    classify_authority_class,
    compute_deterministic_person_score,
)


class TestPersonNameExtractionTruth(unittest.TestCase):
    """Phase 1: Deterministic human candidate validation."""

    def test_reject_forensic_bad_examples(self):
        bad_examples = [
            ("Quality Head", "Amara Raja Energy & Mobility Limited"),
            ("Purchase Head", "Waaree Energies Limited"),
            ("Propulsion Systems", "Ola Electric Mobility Limited"),
            ("Committee Composition. Designation", "Deepak Nitrite Limited"),
            ("CARBOGEN AMCIS Shanghai", "Jyoti CNC Automation Limited"),
            ("Operations Team", "Tata Motors Limited"),
            ("Plant Head", "Havells India Limited"),
            ("Walk-in Interview", "Dixon Technologies"),
            ("Urgent Requirement", "Premier Energies"),
        ]
        for bad_name, comp in bad_examples:
            is_human, reason = is_human_person_candidate(bad_name, company_name=comp)
            self.assertFalse(is_human, f"Failed to reject non-human string '{bad_name}': {reason}")

    def test_preserve_real_indian_names(self):
        real_names = [
            "Atul Jain",
            "Abhijit Biswal",
            "Ravi Singh",
            "Krishna Kumar Jha",
            "Dharmendra Chouhan",
            "Vijayaraghavan Manian",
            "Kuldeep Singh",
            "Ravi Kumar Meka",
            "Saurabh Gupta",
            "Pravin Amate",
            "Nanda UL",
            "Kapil Sharma",
            "Keshava Babu C S",
            "Anil Razdan",
            "Sashikanta Sahoo",
            "Nitin Adya",
            "Lokesh hv",
        ]
        for name in real_names:
            is_human, reason = is_human_person_candidate(name, company_name="Test Company Limited")
            self.assertTrue(is_human, f"Erroneously rejected genuine human name '{name}': {reason}")


class TestCurrentEmploymentHardening(unittest.TestCase):
    """Phase 2: Current employment classification and past-employment rejection."""

    def test_schneider_himanshu_sharma_contradicted(self):
        """Himanshu Sharma left Schneider in 2009 and is currently at Crompton; must be CONTRADICTED."""
        title = "AVP Quality @Crompton I 26 years ..."
        snippet = (
            "Himanshu Sharma - AVP Quality @Crompton. Experience: Schneider Electric (Jan 2007 - Nov 2009), "
            "Crompton Greaves Consumer Electricals (Present)."
        )
        status = classify_current_employment(snippet, title, "Schneider Electric India Private Limited")
        self.assertEqual(status, "CONTRADICTED")

    def test_title_at_other_company_contradicted(self):
        title = "Head of Quality at Crompton Greaves"
        snippet = "Experienced quality professional previously with Schneider Electric in Hyderabad."
        status = classify_current_employment(snippet, title, "Schneider Electric India Private Limited")
        self.assertEqual(status, "CONTRADICTED")

    def test_closed_past_date_range_contradicted(self):
        title = "Quality Manager"
        snippet = "Worked at Tata Motors from 2011 to 2018 in Sanand. Currently pursuing independent consulting."
        status = classify_current_employment(snippet, title, "Tata Motors Limited")
        self.assertEqual(status, "CONTRADICTED")

    def test_active_current_employment_verified(self):
        title = "Head of Quality Assurance"
        snippet = "Divi's Laboratories Limited. Experience: Head of Quality Assurance (2021 - Present). Hyderabad, India."
        status = classify_current_employment(snippet, title, "Divi's Laboratories Limited")
        self.assertEqual(status, "VERIFIED")


class TestFacilityPersonCrossCheck(unittest.TestCase):
    """Phase 3 & 4: Facility/person matching, contradiction, and authority hierarchy."""

    def test_tata_motors_sanand_vs_dharwad_mismatch(self):
        """Avijit Sen is Head of Plant QA at Dharwad (Karnataka), target is Sanand (Gujarat)."""
        rel = classify_facility_relationship(
            candidate_title="Head of Plant QA",
            candidate_text="Avijit Sen - Head of Plant QA at Dharwad, Karnataka. Tata Motors manufacturing.",
            target_facility="Sanand",
            target_city="Sanand",
            target_state="Gujarat",
        )
        self.assertIn(rel, ("OTHER_FACILITY_OWNER", "FACILITY_CONTRADICTED"))

        score, conf = compute_deterministic_person_score(
            current_employment="VERIFIED",
            facility_relationship=rel,
            authority_class="STRONG_PLANT_QUALITY_OWNER",
            title="Head of Plant QA",
            source_quality="LINKEDIN_SEARCH_SNIPPET",
        )
        self.assertNotEqual(conf, "HIGH")

    def test_rr_kabel_waghodia_vs_baddi_mismatch(self):
        """Praveen Kumar is Plant Quality Head at Baddi (Himachal Pradesh), target is Waghodia (Gujarat)."""
        rel = classify_facility_relationship(
            candidate_title="Plant Quality Head",
            candidate_text="Praveen Kumar - Plant Quality Head at Baddi, Himachal Pradesh. RR Kabel Limited.",
            target_facility="Waghodia Plant",
            target_city="Waghodia",
            target_state="Gujarat",
        )
        self.assertIn(rel, ("OTHER_FACILITY_OWNER", "FACILITY_CONTRADICTED"))

        score, conf = compute_deterministic_person_score(
            current_employment="VERIFIED",
            facility_relationship=rel,
            authority_class="STRONG_PLANT_QUALITY_OWNER",
            title="Plant Quality Head",
            source_quality="LINKEDIN_SEARCH_SNIPPET",
        )
        self.assertNotEqual(conf, "HIGH")

    def test_dixon_oragadam_vs_noida_group_or_other(self):
        """Anil Razdan at Noida HQ is not local plant owner for Oragadam (Tamil Nadu)."""
        rel = classify_facility_relationship(
            candidate_title="VP & Group Quality Head",
            candidate_text="Anil Razdan - VP & Group Quality Head at Noida. Dixon Technologies.",
            target_facility="Oragadam Plant",
            target_city="Oragadam",
            target_state="Tamil Nadu",
        )
        self.assertEqual(rel, "GROUP_FUNCTION_OWNER")

    def test_direct_plant_qa_owner_qualifies_high(self):
        """Kuldeep Singh at Halol (Gujarat) for Polycab Halol plant."""
        rel = classify_facility_relationship(
            candidate_title="Chief Manager Quality Assurance (Plant)",
            candidate_text="Kuldeep Singh - Chief Manager Quality Assurance (Plant) at Halol, Gujarat. Polycab India.",
            target_facility="Halol Plant",
            target_city="Halol",
            target_state="Gujarat",
        )
        self.assertEqual(rel, "FACILITY_FUNCTION_OWNER")

        score, conf = compute_deterministic_person_score(
            current_employment="VERIFIED",
            facility_relationship=rel,
            authority_class="STRONG_PLANT_QUALITY_OWNER",
            title="Chief Manager Quality Assurance (Plant)",
            source_quality="LINKEDIN_SEARCH_SNIPPET",
        )
        self.assertEqual(conf, "HIGH")
        self.assertGreaterEqual(score, 85.0)

    def test_junior_engineer_no_decision_authority(self):
        """Junior QA Engineer lacks decision authority; must not qualify as HIGH."""
        auth_class = classify_authority_class("Junior QA Engineer", "Kaynes Technology India")
        self.assertEqual(auth_class, "JUNIOR_IC")

        score, conf = compute_deterministic_person_score(
            current_employment="VERIFIED",
            facility_relationship="FACILITY_FUNCTION_OWNER",
            authority_class=auth_class,
            title="Junior QA Engineer",
            source_quality="LINKEDIN_SEARCH_SNIPPET",
        )
        self.assertNotEqual(conf, "HIGH")


if __name__ == "__main__":
    unittest.main()
