"""Targeted regression and unit tests for Deep Qualification Rules.

Covers:
- Deep Facility Resolution classification (DIRECT, STRONG, WEAK, UNKNOWN)
- Apollo Eligibility Gatekeeper (strictly rejects ambiguous facilities)
- Contact Evidence Policy (inferred emails are NEVER production send eligible)
- Candidate name hygiene validation (rejects web page titles / brands)
"""
import unittest

from services.contact_confidence import (
    classify_contact_evidence_level,
    is_production_send_eligible_contact,
    validate_person_name,
)
from services.decision_maker_discovery import is_apollo_eligible_lead
from services.deep_facility_resolver import deep_facility_resolver


class TestDeepQualificationRules(unittest.TestCase):
    """Test suite verifying deep facility, person hygiene, contact policy, and Apollo gating."""

    def test_facility_resolution_linkage_levels(self):
        # 1. DIRECT: Trigger explicitly names the corridor/plant
        direct_res = deep_facility_resolver.resolve_facility(
            company_name="Dixon Technologies",
            trigger_text="Dixon signs ₹1,000 Cr MoU for new manufacturing plant in Oragadam SIPCOT",
            known_city="Chennai",
            known_state="Tamil Nadu",
        )
        self.assertEqual(direct_res["linkage_confidence"], "DIRECT")
        self.assertTrue(direct_res["facility_verified"])
        self.assertEqual(direct_res["industrial_cluster"], "Oragadam")

        # 2. STRONG: Corroborated by independent snippets/cluster
        strong_res = deep_facility_resolver.resolve_facility(
            company_name="Sona BLW Precision Forgings Ltd",
            trigger_text="Expansion of EV drive unit production",
            known_city="Gurugram",
            known_state="Haryana",
            evidence_snippets=["Operating active manufacturing at Plot No 13 Sector 2 IMT Manesar"],
        )
        self.assertEqual(strong_res["linkage_confidence"], "STRONG")
        self.assertTrue(strong_res["facility_verified"])

        # 3. WEAK: City known, but no plant address or cluster match
        weak_res = deep_facility_resolver.resolve_facility(
            company_name="Generic Parts Ltd",
            trigger_text="Corporate profit increased by 15% in Q3",
            known_city="Pune",
            known_state="Maharashtra",
            evidence_snippets=["Corporate head office located in Pune city"],
        )
        self.assertEqual(weak_res["linkage_confidence"], "WEAK")
        self.assertFalse(weak_res["facility_verified"])

        # 4. UNKNOWN: No location info
        unknown_res = deep_facility_resolver.resolve_facility(
            company_name="Unknown Entity",
            trigger_text="General press announcement",
            known_city="",
            known_state="",
        )
        self.assertEqual(unknown_res["linkage_confidence"], "UNKNOWN")
        self.assertFalse(unknown_res["facility_verified"])

    def test_apollo_eligibility_strictly_rejects_ambiguous_facility(self):
        candidate = {
            "functional_ownership_score": 0.85,
            "current_company_verified": True,
        }
        trigger_info = {"valid_trigger": True, "title": "Plant expansion announced"}
        contact_info = {"evidence_level": "INFERRED_PERSON_SPECIFIC", "mailbox_verified": False}

        # Case A: Facility is WEAK -> Apollo MUST reject
        facility_weak = {"linkage_confidence": "WEAK", "facility_verified": False}
        eligible, reason = is_apollo_eligible_lead(candidate, facility_weak, trigger_info, contact_info)
        self.assertFalse(eligible)
        self.assertIn("WEAK", reason)

        # Case B: Facility is UNKNOWN -> Apollo MUST reject
        facility_unknown = {"linkage_confidence": "UNKNOWN", "facility_verified": False}
        eligible, reason = is_apollo_eligible_lead(candidate, facility_unknown, trigger_info, contact_info)
        self.assertFalse(eligible)

        # Case C: Facility is STRONG -> Apollo is permitted for paid queue
        facility_strong = {"linkage_confidence": "STRONG", "facility_verified": True}
        eligible, reason = is_apollo_eligible_lead(candidate, facility_strong, trigger_info, contact_info)
        self.assertTrue(eligible)

    def test_contact_evidence_policy_inferred_never_production_send(self):
        inferred_level = classify_contact_evidence_level(
            email="john.doe@company.com",
            origin="INFERRED",
            is_role_account=False,
            apollo_verified=False,
        )
        self.assertEqual(inferred_level, "INFERRED_PERSON_SPECIFIC")

        # Inferred email with unverified mailbox CANNOT be production send eligible
        eligible, reason = is_production_send_eligible_contact(inferred_level, mailbox_verified=False)
        self.assertFalse(eligible)
        self.assertIn("inferred", reason.lower())

        # Authoritative public source yields Tier A (VERIFIED_PERSON_SPECIFIC)
        auth_level = classify_contact_evidence_level(
            email="john.doe@company.com",
            origin="PUBLICLY_FOUND",
            is_role_account=False,
            apollo_verified=False,
            authoritative=True,
        )
        self.assertEqual(auth_level, "VERIFIED_PERSON_SPECIFIC")
        eligible_auth, _ = is_production_send_eligible_contact(auth_level, mailbox_verified=False)
        self.assertTrue(eligible_auth)

        # Non-authoritative public source yields Tier B (PUBLICLY_FOUND_PERSON_SPECIFIC)
        public_level = classify_contact_evidence_level(
            email="john.doe@company.com",
            origin="PUBLICLY_FOUND",
            is_role_account=False,
            apollo_verified=False,
            authoritative=False,
        )
        self.assertEqual(public_level, "PUBLICLY_FOUND_PERSON_SPECIFIC")
        eligible_pub, _ = is_production_send_eligible_contact(public_level, mailbox_verified=False)
        self.assertTrue(eligible_pub)

    def test_human_name_validation(self):
        # Non-human brand / page titles should be rejected
        self.assertFalse(validate_person_name("CRAFTSMAN® BUILD ON™")["is_human_name"])
        self.assertFalse(validate_person_name("Official Rolex Website")["is_human_name"])
        self.assertFalse(validate_person_name("YouTube 動画をアップロードする")["is_human_name"])
        self.assertFalse(validate_person_name("Wikipedia")["is_human_name"])

        # Real human names should pass
        self.assertTrue(validate_person_name("Anil Patil")["is_human_name"])
        self.assertTrue(validate_person_name("M. Senthilkumar")["is_human_name"])
        self.assertTrue(validate_person_name("Rohit Chaubey")["is_human_name"])

    def test_generic_plant_mailbox_cannot_masquerade_as_person_specific(self):
        """Phase 3 & 14: Plant mailbox (e.g. pressplant5@) must classify as GENERIC_PLANT and reject production send."""
        plant_email = "pressplant5@ramkrishnaforgings.com"
        level = classify_contact_evidence_level(
            email=plant_email,
            origin="PUBLICLY_FOUND",
            is_role_account=False,
            apollo_verified=False,
            authoritative=False,
        )
        self.assertEqual(level, "GENERIC_PLANT")
        eligible, reason = is_production_send_eligible_contact(level, mailbox_verified=False)
        self.assertFalse(eligible)
        self.assertIn("plant mailbox cannot impersonate", reason.lower())

        # Other plant & departmental variants
        self.assertEqual(classify_contact_evidence_level("plant2@company.com"), "GENERIC_PLANT")
        self.assertEqual(classify_contact_evidence_level("unit3@company.com"), "GENERIC_PLANT")
        self.assertEqual(classify_contact_evidence_level("quality@company.com"), "GENERIC_DEPARTMENTAL")
        self.assertEqual(classify_contact_evidence_level("info@company.com"), "CORPORATE_SWITCHBOARD_CONTACT")

    def test_official_deerflow_status_and_custom_playwright_service(self):
        """Phase 1 & 2: Custom Playwright service is distinct from official ByteDance DeerFlow."""
        from services.browser_research_adapter import (
            OFFICIAL_DEERFLOW_STATUS,
            browser_research_adapter,
        )
        self.assertEqual(OFFICIAL_DEERFLOW_STATUS, "BLOCKED_BY_LLM_PROVIDER")
        status = browser_research_adapter.get_status()
        self.assertIn(status.get("service"), ("browser_research_service", "disabled", "unreachable"))
        self.assertEqual(status.get("official_deerflow_status"), "BLOCKED_BY_LLM_PROVIDER")

    def test_production_ready_vs_apollo_ready_semantics(self):
        """Phase 4: Apollo-ready and research-qualified leads are NOT production-ready."""
        candidate = {
            "functional_ownership_score": 0.85,
            "current_company_verified": True,
        }
        facility_info = {"linkage_confidence": "STRONG", "facility_verified": True}
        trigger_info = {"valid_trigger": True, "title": "Facility Capex Expansion"}
        contact_inferred = {"evidence_level": "INFERRED_PERSON_SPECIFIC", "mailbox_verified": False}

        # Candidate is Apollo eligible
        is_apollo, _ = is_apollo_eligible_lead(candidate, facility_info, trigger_info, contact_inferred)
        self.assertTrue(is_apollo)

        # But candidate is NOT production send eligible!
        is_prod, _ = is_production_send_eligible_contact(contact_inferred["evidence_level"], mailbox_verified=False)
        self.assertFalse(is_prod)
        self.assertNotEqual(is_apollo, is_prod)


if __name__ == "__main__":
    unittest.main()
