"""Gold-Label Regression Tests for Generic Correct-Person Ranking & Verification.

Tests Case 1 (Valeo India / Sanand -> Abhijit Biswal), Case 2 (Kehems Technologies / Indore -> Ravi Singh),
and the negative case (Higher-title irrelevant executive loses to lower-title functional owner).

CRITICAL: Does NOT hardcode person names to companies; verifies that the generic multi-dimensional
scoring algorithm (facility alignment, calibration ownership, current employment, evidence strength)
reaches the expected ranking based on evidence facts.
"""
import unittest
from types import SimpleNamespace

from services.decision_maker_discovery import verify_person_candidate


class GoldLabelCorrectPersonTests(unittest.TestCase):
    def test_case_1_valeo_india_sanand_generic_ranking(self):
        valeo = SimpleNamespace(
            id=101,
            name="Valeo India Pvt Ltd",
            city="Sanand",
            state="Gujarat",
        )

        # Candidate 1: Abhijit Biswal (Quality & Metrology Manager at Sanand plant)
        candidate_abhijit = {
            "candidate_name": "Abhijit Biswal",
            "candidate_title": "Quality Manager - Metrology & Standards",
            "candidate_location": "Sanand",
            "candidate_company_match": True,
            "evidence_url": "https://www.valeo.com/en/sanand-plant/team",
            "search_type": "company_website",
            "evidence_snippet": "Abhijit Biswal manages quality control, measurement room, and calibration standards at Valeo India Sanand facility.",
        }

        # Candidate 2: Corporate VP of Human Resources (Higher title, but zero calibration ownership, wrong location)
        candidate_hr_vp = {
            "candidate_name": "Rajeev Kapoor",
            "candidate_title": "Vice President - Human Resources",
            "candidate_location": "Chennai",
            "candidate_company_match": True,
            "evidence_url": "https://www.linkedin.com/in/rajeev-hr-valeo",
            "search_type": "public_professional_profile",
            "evidence_snippet": "Rajeev Kapoor is Vice President HR at Valeo India corporate office in Chennai.",
        }

        # Candidate 3: Ex-Employee (Former Quality Engineer who left in 2021)
        candidate_former = {
            "candidate_name": "Suresh Nair",
            "candidate_title": "Former Quality Engineer",
            "candidate_location": "Pune",
            "candidate_company_match": False,
            "evidence_url": "https://example.com/profiles/suresh",
            "search_type": "public_web",
            "evidence_snippet": "Suresh Nair previously worked at Valeo India Pune plant until 2021.",
        }

        res_abhijit = verify_person_candidate(candidate_abhijit, valeo)
        res_hr_vp = verify_person_candidate(candidate_hr_vp, valeo)
        res_former = verify_person_candidate(candidate_former, valeo)

        # Verify Abhijit passes with high composite and PUBLICLY_VERIFIED
        self.assertEqual(res_abhijit["verification_status"], "PERSON_PUBLICLY_VERIFIED")
        self.assertGreaterEqual(res_abhijit["composite_score"], 0.75)
        self.assertEqual(res_abhijit["scores"]["facility_match"], 1.0)
        self.assertEqual(res_abhijit["scores"]["role_relevance"], 1.0)

        # Verify Abhijit ranks strictly higher than the corporate HR VP and the former employee
        self.assertGreater(res_abhijit["composite_score"], res_hr_vp["composite_score"])
        self.assertGreater(res_abhijit["composite_score"], res_former["composite_score"])

        # HR VP must be rejected or have low relevance for calibration outreach
        self.assertLess(res_hr_vp["scores"]["role_relevance"], 0.5)

    def test_case_2_kehems_technologies_indore_generic_ranking(self):
        kehems = SimpleNamespace(
            id=102,
            name="Kehems Technologies Pvt Ltd",
            city="Indore",
            state="Madhya Pradesh",
        )

        # Candidate 1: Ravi Singh (Plant & QA Lead in Indore)
        candidate_ravi = {
            "candidate_name": "Ravi Singh",
            "candidate_title": "Plant Quality Assurance Head - Testing & Calibration",
            "candidate_location": "Indore",
            "candidate_company_match": True,
            "evidence_url": "https://www.kehems.com/indore-unit/operations",
            "search_type": "company_website",
            "evidence_snippet": "Ravi Singh oversees plant operations and testing laboratory calibration compliance at Kehems Technologies Indore facility.",
        }

        # Candidate 2: Chief Financial Officer (CFO in Mumbai)
        candidate_cfo = {
            "candidate_name": "Vikas Jain",
            "candidate_title": "Chief Financial Officer",
            "candidate_location": "Mumbai",
            "candidate_company_match": True,
            "evidence_url": "https://www.kehems.com/leadership",
            "search_type": "company_website",
            "evidence_snippet": "Vikas Jain is Chief Financial Officer managing corporate finance.",
        }

        res_ravi = verify_person_candidate(candidate_ravi, kehems)
        res_cfo = verify_person_candidate(candidate_cfo, kehems)

        # Ravi Singh verified with high confidence for Indore plant
        self.assertEqual(res_ravi["verification_status"], "PERSON_PUBLICLY_VERIFIED")
        self.assertGreaterEqual(res_ravi["composite_score"], 0.75)
        self.assertEqual(res_ravi["scores"]["facility_match"], 1.0)
        self.assertEqual(res_ravi["scores"]["role_relevance"], 1.0)

        # Generic algorithm ranks Ravi Singh well above the CFO
        self.assertGreater(res_ravi["composite_score"], res_cfo["composite_score"])
        self.assertLess(res_cfo["scores"]["role_relevance"], 0.5)

    def test_negative_case_higher_title_irrelevant_loses_to_functional_owner(self):
        """A Director / C-Level executive without calibration ownership must lose to a junior/mid-level

        functional lead who has direct calibration/metrology responsibility and facility alignment.
        """
        factory = SimpleNamespace(
            id=103,
            name="Bharat Precision Works",
            city="Chakan",
            state="Maharashtra",
        )

        # Executive 1: High Title ("Executive Director & Board Member") but corporate/finance focused
        exec_director = {
            "candidate_name": "Siddharth Mehta",
            "candidate_title": "Executive Director & Board Member",
            "candidate_location": "Mumbai",  # Head office, not plant
            "candidate_company_match": True,
            "evidence_url": "https://www.linkedin.com/in/siddharth-mehta-director",
            "search_type": "public_professional_profile",
            "evidence_snippet": "Siddharth Mehta is Executive Director leading investor relations and corporate governance.",
        }

        # Functional Lead 2: Modest title ("Assistant Manager - Metrology & Calibration"), but perfect fit
        metrology_lead = {
            "candidate_name": "Deepak Verma",
            "candidate_title": "Assistant Manager - Metrology & Calibration",
            "candidate_location": "Chakan",  # Exact plant facility match
            "candidate_company_match": True,
            "evidence_url": "https://www.bharatprecision.com/chakan/quality-standards",
            "search_type": "company_website",
            "evidence_snippet": "Deepak Verma is responsible for CMM programming, gauge calibration, and NABL audit readiness at Chakan plant.",
        }

        res_exec = verify_person_candidate(exec_director, factory)
        res_lead = verify_person_candidate(metrology_lead, factory)

        # The functional metrology lead MUST beat the executive director
        self.assertGreater(res_lead["composite_score"], res_exec["composite_score"])
        self.assertEqual(res_lead["scores"]["role_relevance"], 1.0)  # has calibration keywords + decision keyword
        self.assertEqual(res_lead["scores"]["facility_match"], 1.0)  # exact facility match
        self.assertEqual(res_lead["verification_status"], "PERSON_PUBLICLY_VERIFIED")


if __name__ == "__main__":
    unittest.main()
