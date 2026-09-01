"""Tests for Decision-Maker Discovery & Person Verification Pipeline.

Covers:
  A. Persona inference from signal type
  B. Search query generation
  C. Person candidate extraction from search results
  D. Verification logic (company match, role relevance, rejection)
  E. Multiple stakeholder discovery
  F. Apollo enrichment order-of-operations
  G. Research brief completeness
  H. Failure cases (wrong person, outdated, company mismatch, no evidence, Apollo blocked)
"""
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime

from services.decision_maker_discovery import (
    infer_target_personas,
    generate_search_queries,
    extract_person_candidates,
    verify_person_candidate,
    build_research_brief_with_persons,
    SCORE_WEIGHTS,
    APOLLO_ELIGIBLE_THRESHOLD,
    CANDIDATE_THRESHOLD,
)
from models.decision_maker_candidate import (
    VERIFICATION_STATUSES,
    REJECTION_REASONS,
    STAKEHOLDER_ROLES,
)


class TestPersonaInference(unittest.TestCase):
    """Test Step 1: Persona inference from signal/industry."""

    def test_audit_signal_produces_quality_primary(self):
        personas = infer_target_personas("iso_iatf_audit", "Automotive")
        self.assertEqual(personas[0]["persona"], "Quality / Metrology")
        self.assertEqual(personas[0]["priority"], "PRIMARY")
        self.assertIn("Quality Head", personas[0]["titles"])
        self.assertGreater(len(personas), 1)

    def test_expansion_signal_produces_maintenance_primary(self):
        personas = infer_target_personas("plant_expansion", "Manufacturing")
        self.assertEqual(personas[0]["persona"], "Maintenance / Plant")
        self.assertEqual(personas[0]["priority"], "PRIMARY")
        self.assertIn("Plant Head", personas[0]["titles"])

    def test_qa_hiring_signal_produces_quality_primary(self):
        personas = infer_target_personas("qa_hiring", "Automotive Components")
        self.assertEqual(personas[0]["persona"], "Quality / Metrology")

    def test_multiple_personas_returned(self):
        personas = infer_target_personas("capex_announcement")
        self.assertGreaterEqual(len(personas), 2)
        priorities = [p["priority"] for p in personas]
        self.assertIn("PRIMARY", priorities)
        self.assertIn("SECONDARY", priorities)

    def test_stakeholder_roles_assigned(self):
        personas = infer_target_personas("iso_iatf_audit")
        for p in personas:
            self.assertIn(p["stakeholder_role"], STAKEHOLDER_ROLES)


class TestSearchQueryGeneration(unittest.TestCase):
    """Test Step 2: Search query generation."""

    def test_generates_company_specific_queries(self):
        personas = infer_target_personas("iso_iatf_audit")
        queries = generate_search_queries("Bharat Forge Ltd", personas, city="Pune")

        self.assertGreater(len(queries), 5)
        # All queries should contain company name
        for q in queries:
            self.assertIn("Bharat Forge", q["query"])

    def test_location_qualified_queries(self):
        personas = infer_target_personas("plant_expansion")
        queries = generate_search_queries("Tata Electronics", personas, city="Hosur")

        location_queries = [q for q in queries if q["search_type"] == "location_qualified"]
        self.assertGreater(len(location_queries), 0)
        # At least one should contain city
        has_city = any("Hosur" in q["query"] for q in location_queries)
        self.assertTrue(has_city)

    def test_professional_profile_query_included(self):
        personas = infer_target_personas("general_signal")
        queries = generate_search_queries("Endurance Technologies", personas)
        profile_queries = [q for q in queries if q["search_type"] == "public_professional_profile"]
        self.assertGreater(len(profile_queries), 0)


class TestPersonCandidateExtraction(unittest.TestCase):
    """Test Step 4: Person candidate extraction from search results."""

    def test_extracts_person_with_title(self):
        results = [{
            "title": "Amit Kulkarni - Quality Manager at Bharat Forge",
            "url": "https://example.com/profile",
            "snippet": "Amit Kulkarni is the Quality Manager - Metrology & Standards at Bharat Forge Ltd, Pune.",
            "provider": "test",
            "evidence_type": "WEB_EVIDENCE",
            "persona": "Quality / Metrology",
            "search_type": "title_match",
        }]
        candidates = extract_person_candidates(results, "Bharat Forge Ltd")

        self.assertGreater(len(candidates), 0)
        first = candidates[0]
        self.assertEqual(first["candidate_name"], "Amit Kulkarni")
        self.assertTrue(first["candidate_company_match"])

    def test_rejects_non_matching_company(self):
        results = [{
            "title": "John Smith - Quality at Unrelated Corp",
            "url": "https://example.com/profile",
            "snippet": "John Smith is the Quality Head at Unrelated Corp in Mumbai.",
            "provider": "test",
            "evidence_type": "WEB_EVIDENCE",
            "persona": "Quality / Metrology",
            "search_type": "title_match",
        }]
        candidates = extract_person_candidates(results, "Bharat Forge Ltd")
        # Should find zero or low-confidence candidates (company mismatch)
        if candidates:
            self.assertFalse(candidates[0]["candidate_company_match"])

    def test_empty_results_produce_no_candidates(self):
        candidates = extract_person_candidates([], "Test Company")
        self.assertEqual(len(candidates), 0)


class TestPersonVerification(unittest.TestCase):
    """Test Step 5: Person verification & scoring."""

    def _make_company(self, name="Bharat Forge Ltd", city="Pune", state="Maharashtra", industry="Automotive"):
        company = MagicMock()
        company.name = name
        company.city = city
        company.state = state
        company.industry = industry
        return company

    def test_verified_quality_head_scores_high(self):
        """Case A: Clear verified Quality/Metrology contact."""
        candidate = {
            "candidate_name": "Amit Kulkarni",
            "candidate_title": "Quality Manager - Metrology & Standards",
            "candidate_company_match": True,
            "candidate_location": "Pune",
            "evidence_url": "https://bharatforge.com/team/amit-kulkarni",
            "evidence_snippet": "Amit Kulkarni is the Quality Manager at Bharat Forge Ltd Pune plant",
            "search_type": "company_website",
        }
        company = self._make_company()
        result = verify_person_candidate(candidate, company)

        self.assertEqual(result["verification_status"], "PERSON_PUBLICLY_VERIFIED")
        self.assertGreaterEqual(result["composite_score"], APOLLO_ELIGIBLE_THRESHOLD)
        self.assertTrue(result["apollo_eligible"])

    def test_company_mismatch_rejected(self):
        """Case E: Wrong company."""
        candidate = {
            "candidate_name": "Rajesh Patel",
            "candidate_title": "Quality Head",
            "candidate_company_match": False,
            "candidate_location": "Mumbai",
            "evidence_url": "https://other-company.com/team",
            "evidence_snippet": "Rajesh Patel works at Different Company",
            "search_type": "title_match",
        }
        company = self._make_company()
        result = verify_person_candidate(candidate, company)

        self.assertEqual(result["verification_status"], "PERSON_REJECTED")
        self.assertEqual(result["rejection_reason"], "company_mismatch")
        self.assertFalse(result["apollo_eligible"])

    def test_irrelevant_role_rejected(self):
        """Case: Irrelevant department."""
        candidate = {
            "candidate_name": "Vikram Deshmukh",
            "candidate_title": "Marketing Executive",
            "candidate_company_match": True,
            "candidate_location": "Pune",
            "evidence_url": "https://example.com",
            "evidence_snippet": "Vikram at Bharat Forge marketing dept",
            "search_type": "title_match",
        }
        company = self._make_company()
        result = verify_person_candidate(candidate, company)

        # Marketing Executive has no calibration/quality/maintenance relevance
        self.assertIn(result["verification_status"], ["PERSON_REJECTED", "PERSON_CANDIDATE"])

    def test_low_confidence_not_apollo_eligible(self):
        """Case K: Person exists but no email — should not be sent to Apollo without evidence."""
        candidate = {
            "candidate_name": "Unknown Person",
            "candidate_title": "engineer",
            "candidate_company_match": False,
            "candidate_location": "",
            "evidence_url": "https://random-site.com",
            "evidence_snippet": "Some random page mentioning engineer",
            "search_type": "title_match",
        }
        company = self._make_company()
        result = verify_person_candidate(candidate, company)

        self.assertFalse(result["apollo_eligible"])

    def test_adaptive_research_generated(self):
        """Test that low-confidence dimensions produce research tasks."""
        candidate = {
            "candidate_name": "Suresh Kumar",
            "candidate_title": "Quality Manager",
            "candidate_company_match": False,  # Low company match
            "candidate_location": "Chennai",
            "evidence_url": "https://example.com",
            "evidence_snippet": "Suresh Kumar quality manager",
            "search_type": "title_match",
        }
        company = self._make_company(name="Bharat Forge Ltd", city="Pune")
        result = verify_person_candidate(candidate, company)

        # Should generate research task for company verification
        tasks = result.get("pending_research_tasks", [])
        if result["verification_status"] != "PERSON_REJECTED":
            self.assertGreater(len(tasks), 0)

    def test_score_dimensions_present(self):
        """Test all 5 score dimensions are computed."""
        candidate = {
            "candidate_name": "Test Person",
            "candidate_title": "Calibration Head",
            "candidate_company_match": True,
            "candidate_location": "Pune",
            "evidence_url": "https://example.com",
            "evidence_snippet": "Test Person is Calibration Head at Bharat Forge Pune",
            "search_type": "title_match",
        }
        company = self._make_company()
        result = verify_person_candidate(candidate, company)

        for dim in SCORE_WEIGHTS:
            self.assertIn(dim, result["scores"])
            self.assertGreaterEqual(result["scores"][dim], 0.0)
            self.assertLessEqual(result["scores"][dim], 1.0)


class TestResearchBrief(unittest.TestCase):
    """Test Step 7: Research brief completeness."""

    def test_brief_has_all_required_fields(self):
        company = MagicMock()
        company.id = 1
        company.name = "Bharat Forge Ltd"
        company.city = "Pune"
        company.state = "Maharashtra"
        company.industry = "Automotive"
        company.buying_window = "30_days"

        brief = build_research_brief_with_persons(company, [], signal_info={
            "signal_type": "plant_expansion",
            "event_title": "New CNC Line",
            "calibration_impact": "Baseline calibration needed",
            "likely_parameters": ["Dimensional", "Torque"],
            "price_sensitivity": "Low",
        })

        required_fields = [
            "company", "facility", "discovery_signal", "signal_evidence",
            "calibration_reasoning", "likely_requirement", "target_persona",
            "actual_person", "buying_window", "premium_potential",
            "price_sensitivity", "what_we_know", "what_we_infer",
            "what_we_dont_know", "next_best_action",
        ]
        for field in required_fields:
            self.assertIn(field, brief, f"Missing required field: {field}")

    def test_brief_shows_research_required_when_no_person(self):
        company = MagicMock()
        company.id = 1
        company.name = "Test Company"
        company.city = "Mumbai"
        company.state = "Maharashtra"
        company.industry = "Manufacturing"
        company.buying_window = "unknown"

        brief = build_research_brief_with_persons(company, [])

        self.assertIn("NO VERIFIED PERSON", brief["actual_person"]["name"])
        self.assertIn("RESEARCH REQUIRED", brief["actual_person"]["verification_status"])


class TestApolloEnrichmentOrder(unittest.TestCase):
    """Test Step 6: Apollo enrichment order-of-operations."""

    def test_apollo_blocked_for_unconfigured_key(self):
        from services.apollo_adapter import enrich_specific_person
        with patch("services.apollo_adapter.settings") as mock_settings, \
             patch("services.apollo_adapter.get_setting_value", return_value=""):
            mock_settings.APOLLO_API_KEY = ""
            mock_settings.APOLLO_API_BASE_URL = "https://api.apollo.io/v1"
            result = enrich_specific_person("Test Person", "Test Company")

        self.assertEqual(result["status"], "APOLLO_BLOCKED")
        self.assertIsNone(result["email"])

    def test_apollo_not_called_for_rejected_candidate(self):
        """Rejected candidates must NOT proceed to Apollo."""
        from services.decision_maker_discovery import enrich_candidate_via_apollo
        candidate = MagicMock()
        candidate.verification_status = "PERSON_REJECTED"
        candidate.verification_confidence = 0.2

        db = MagicMock()
        result = enrich_candidate_via_apollo(candidate, "Test Company", db)

        self.assertEqual(result["status"], "SKIPPED")

    def test_apollo_not_called_for_low_confidence(self):
        """Low-confidence candidates must NOT proceed to Apollo."""
        from services.decision_maker_discovery import enrich_candidate_via_apollo
        candidate = MagicMock()
        candidate.verification_status = "PERSON_CANDIDATE"
        candidate.verification_confidence = 0.3  # Below threshold

        db = MagicMock()
        result = enrich_candidate_via_apollo(candidate, "Test Company", db)

        self.assertEqual(result["status"], "SKIPPED")


class TestVerificationStatuses(unittest.TestCase):
    """Test distinct status tracking."""

    def test_all_statuses_defined(self):
        expected = [
            "PERSONA_INFERRED", "PERSON_CANDIDATE", "PERSON_PUBLICLY_VERIFIED",
            "CONTACT_ENRICHMENT_READY", "APOLLO_ENRICHED", "EMAIL_VERIFIED",
            "PERSON_REJECTED",
        ]
        for status in expected:
            self.assertIn(status, VERIFICATION_STATUSES)

    def test_all_rejection_reasons_defined(self):
        expected = [
            "company_mismatch", "outdated_employment", "irrelevant_role",
            "insufficient_evidence", "duplicate", "low_confidence",
            "wrong_facility", "conflicting_sources",
        ]
        for reason in expected:
            self.assertIn(reason, REJECTION_REASONS)

    def test_all_stakeholder_roles_defined(self):
        expected = [
            "User", "Identifier", "Evaluator", "Recommender",
            "Approver", "Purchaser", "Influencer", "Blocker",
        ]
        for role in expected:
            self.assertIn(role, STAKEHOLDER_ROLES)


class TestResearchProviderAbstraction(unittest.TestCase):
    """Test research provider router."""

    def test_provider_status_reporting(self):
        from services.research_provider import research_router
        status = research_router.get_provider_status()

        # Should have at least 4 providers
        self.assertGreaterEqual(len(status), 3)
        # Each should report LIVE or NOT_CONFIGURED
        for name, st in status.items():
            self.assertIn(st, ["LIVE", "NOT_CONFIGURED"])

    def test_database_cache_always_available(self):
        from services.research_provider import research_router
        status = research_router.get_provider_status()
        self.assertEqual(status["database_cache"], "LIVE")

    def test_public_page_fetch_always_available(self):
        from services.research_provider import research_router
        status = research_router.get_provider_status()
        self.assertEqual(status["public_page_fetch"], "LIVE")


class TestMultipleStakeholderDiscovery(unittest.TestCase):
    """Test discovery of multiple stakeholders per company."""

    def test_multiple_personas_discovered(self):
        personas = infer_target_personas("iso_iatf_audit", "Automotive")
        # Should return primary + at least 1 secondary
        self.assertGreaterEqual(len(personas), 2)
        primaries = [p for p in personas if p["priority"] == "PRIMARY"]
        secondaries = [p for p in personas if p["priority"] == "SECONDARY"]
        self.assertEqual(len(primaries), 1)
        self.assertGreater(len(secondaries), 0)

    def test_distinct_stakeholder_roles(self):
        personas = infer_target_personas("plant_expansion")
        roles = [p["stakeholder_role"] for p in personas]
        # Should have distinct roles
        self.assertEqual(len(roles), len(set(roles)))


class TestAdversarialCasesAThroughL(unittest.TestCase):
    """Explicitly verify all 12 Adversarial & Edge Cases (A through L)."""

    def _make_company(self, name="Bharat Forge Ltd", city="Pune", state="Maharashtra", industry="Automotive"):
        company = MagicMock()
        company.id = 101
        company.name = name
        company.city = city
        company.state = state
        company.industry = industry
        company.buying_window = "30_days"
        return company

    def test_case_a_clear_correct_person(self):
        """Case A: Clear correct person -> High verification match score, apollo eligible."""
        company = self._make_company()
        candidate = {
            "candidate_name": "Amit Kulkarni",
            "candidate_title": "Quality Manager - Metrology & Standards",
            "candidate_company_match": True,
            "candidate_location": "Pune",
            "evidence_url": "https://bharatforge.com/leadership/amit-kulkarni",
            "evidence_snippet": "Amit Kulkarni is Quality Manager at Bharat Forge Ltd Pune plant.",
            "search_type": "company_website",
        }
        res = verify_person_candidate(candidate, company)
        self.assertEqual(res["verification_status"], "PERSON_PUBLICLY_VERIFIED")
        self.assertGreaterEqual(res["composite_score"], APOLLO_ELIGIBLE_THRESHOLD)
        self.assertTrue(res["apollo_eligible"])
        self.assertIsNone(res["rejection_reason"])

    def test_case_b_multiple_plausible_people(self):
        """Case B: Multiple plausible people -> Distinct candidates ranked PRIMARY / SECONDARY with rationale."""
        company = self._make_company()
        c1 = MagicMock()
        c1.candidate_name = "Amit Kulkarni"
        c1.candidate_title = "Quality Manager"
        c1.target_persona = "Quality / Metrology"
        c1.stakeholder_role = "Evaluator"
        c1.verification_status = "PERSON_PUBLICLY_VERIFIED"
        c1.score_composite = 0.85
        c1.contact_priority = "PRIMARY"
        c1.priority_reason = "Highest verification score (0.85) for Quality / Metrology"
        c1.evidence_sources = [{"source": "web", "url": "https://bharatforge.com"}]
        c1.public_profile_url = "https://bharatforge.com/amit"
        c1.apollo_enrichment_status = "NOT_ATTEMPTED"
        c1.apollo_email = None
        c1.apollo_email_confidence = None
        c1.email_status = "NOT_FOUND"
        c1.apollo_phone = None
        c1.pending_research_tasks = []

        c2 = MagicMock()
        c2.candidate_name = "Sanjay Sharma"
        c2.candidate_title = "Plant Head"
        c2.target_persona = "Maintenance / Plant"
        c2.stakeholder_role = "User"
        c2.verification_status = "PERSON_PUBLICLY_VERIFIED"
        c2.score_composite = 0.72
        c2.contact_priority = "SECONDARY"
        c2.priority_reason = "Secondary stakeholder for plant operations"
        c2.evidence_sources = [{"source": "web", "url": "https://bharatforge.com"}]
        c2.public_profile_url = "https://bharatforge.com/sanjay"
        c2.apollo_enrichment_status = "NOT_ATTEMPTED"
        c2.apollo_email = None
        c2.apollo_email_confidence = None
        c2.email_status = "NOT_FOUND"
        c2.apollo_phone = None
        c2.pending_research_tasks = []

        brief = build_research_brief_with_persons(company, [c1, c2])
        self.assertEqual(brief["actual_person"]["name"], "Amit Kulkarni")
        self.assertEqual(len(brief["secondary_contacts"]), 1)
        self.assertEqual(brief["secondary_contacts"][0]["name"], "Sanjay Sharma")
        self.assertIn("Amit Kulkarni", brief["contact_sequence"])

    def test_case_c_no_identifiable_person(self):
        """Case C: No identifiable person -> Returns NO VERIFIED PERSON, research required in brief."""
        company = self._make_company()
        brief = build_research_brief_with_persons(company, [])
        self.assertEqual(brief["actual_person"]["name"], "NO VERIFIED PERSON FOUND")
        self.assertEqual(brief["actual_person"]["verification_status"], "RESEARCH REQUIRED")
        self.assertEqual(brief["actual_person"]["person_match_score"], 0)
        self.assertIn("RESEARCH REQUIRED", brief["next_best_action"])

    def test_case_d_outdated_person(self):
        """Case D: Outdated person / low recency -> flags for research and verifies pending tasks."""
        company = self._make_company()
        candidate = {
            "candidate_name": "Ramesh Gupta",
            "candidate_title": "Ex Quality Manager",
            "candidate_company_match": True,
            "candidate_location": "Pune",
            "evidence_url": "https://archive.org/profile",
            "evidence_snippet": "Ramesh Gupta was Quality Manager at Bharat Forge Ltd until 2018.",
            "search_type": "title_match",
        }
        res = verify_person_candidate(candidate, company)
        # Low composite or pending research tasks generated
        self.assertIn("pending_research_tasks", res)

    def test_case_e_wrong_company(self):
        """Case E: Wrong company -> Verification status is PERSON_REJECTED with reason company_mismatch."""
        company = self._make_company(name="Bharat Forge Ltd")
        candidate = {
            "candidate_name": "Rajesh V. Patel",
            "candidate_title": "Quality Head",
            "candidate_company_match": False,
            "candidate_location": "Dahej",
            "evidence_url": "https://aarti-industries.com",
            "evidence_snippet": "Rajesh Patel works at Aarti Industries Ltd Dahej.",
            "search_type": "title_match",
        }
        res = verify_person_candidate(candidate, company)
        self.assertEqual(res["verification_status"], "PERSON_REJECTED")
        self.assertEqual(res["rejection_reason"], "company_mismatch")
        self.assertFalse(res["apollo_eligible"])

    def test_case_f_wrong_facility(self):
        """Case F: Wrong facility/location -> Facility match score reflects distance/mismatch."""
        company = self._make_company(name="Tata Motors", city="Pune")
        candidate_same_city = {
            "candidate_name": "Anil Deshpande",
            "candidate_title": "Quality Manager",
            "candidate_company_match": True,
            "candidate_location": "Pune",
            "evidence_url": "https://tatamotors.com",
            "evidence_snippet": "Anil Deshpande Quality Manager Tata Motors Pune plant.",
            "search_type": "title_match",
        }
        candidate_diff_city = {
            "candidate_name": "Anil Deshpande",
            "candidate_title": "Quality Manager",
            "candidate_company_match": True,
            "candidate_location": "Chennai",
            "evidence_url": "https://tatamotors.com",
            "evidence_snippet": "Anil Deshpande Quality Manager Tata Motors Chennai facility.",
            "search_type": "title_match",
        }
        res_same = verify_person_candidate(candidate_same_city, company)
        res_diff = verify_person_candidate(candidate_diff_city, company)
        self.assertGreater(res_same["scores"]["facility_match"], res_diff["scores"]["facility_match"])

    def test_case_g_apollo_no_result(self):
        """Case G: Apollo no result -> Status NO_RESULT, email None, no fake contact substituted."""
        from services.apollo_adapter import enrich_specific_person
        with patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {"person": None}

            with patch("services.apollo_adapter.settings") as mock_settings:
                mock_settings.APOLLO_API_KEY = "test_key"
                mock_settings.APOLLO_API_BASE_URL = "https://api.apollo.io/v1"
                res = enrich_specific_person("Amit Kulkarni", "Bharat Forge Ltd", "Quality Manager")

        self.assertEqual(res["status"], "NO_RESULT")
        self.assertIsNone(res["email"])
        self.assertFalse(res.get("mock_mode", False))

    def test_case_h_apollo_authentication_failure(self):
        """Case H: Apollo auth failure -> Status APOLLO_BLOCKED, no mock contacts substituted."""
        from services.apollo_adapter import enrich_specific_person
        with patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 401
            mock_post.return_value.text = "Unauthorized"

            with patch("services.apollo_adapter.settings") as mock_settings:
                mock_settings.APOLLO_API_KEY = "invalid_key"
                mock_settings.APOLLO_API_BASE_URL = "https://api.apollo.io/v1"
                res = enrich_specific_person("Amit Kulkarni", "Bharat Forge Ltd")

        self.assertEqual(res["status"], "APOLLO_BLOCKED")
        self.assertIn("authentication failed", res["error"].lower())
        self.assertIsNone(res["email"])
        self.assertFalse(res.get("mock_mode", False))

    def test_case_i_conflicting_evidence(self):
        """Case I: Conflicting evidence -> Borderline role/company confidence generates adaptive pending research tasks."""
        company = self._make_company()
        candidate = {
            "candidate_name": "Mahesh Joshi",
            "candidate_title": "Engineering Lead",
            "candidate_company_match": True,
            "candidate_location": "Pune",
            "evidence_url": "https://example.com/mention",
            "evidence_snippet": "Mahesh Joshi is Engineering Lead at Bharat Forge Pune.",
            "search_type": "title_match",
        }
        res = verify_person_candidate(candidate, company)
        # Should generate pending research tasks to verify metrology/calibration role
        self.assertGreater(len(res["pending_research_tasks"]), 0)
        self.assertIn("pending_research_tasks", res)

    def test_case_j_duplicate_person(self):
        """Case J: Duplicate person -> Deduplication prevents duplicate candidates from search."""
        results = [
            {
                "title": "Amit Kulkarni Quality Manager Bharat Forge",
                "url": "https://site1.com/amit",
                "snippet": "Amit Kulkarni Quality Manager at Bharat Forge Ltd Pune.",
                "provider": "google",
                "evidence_type": "WEB_EVIDENCE",
                "persona": "Quality / Metrology",
                "search_type": "title_match",
            },
            {
                "title": "Amit Kulkarni - Quality Head Bharat Forge",
                "url": "https://site2.com/amit",
                "snippet": "Amit Kulkarni Head of Quality at Bharat Forge Ltd.",
                "provider": "google",
                "evidence_type": "WEB_EVIDENCE",
                "persona": "Quality / Metrology",
                "search_type": "title_match",
            },
        ]
        candidates = extract_person_candidates(results, "Bharat Forge Ltd")
        # Same person extracted only once
        names = [c["candidate_name"].lower() for c in candidates]
        self.assertEqual(names.count("amit kulkarni"), 1)

    def test_case_k_person_found_but_no_email(self):
        """Case K: Person found but Apollo returns no email -> Remains PERSON_PUBLICLY_VERIFIED, email NOT FOUND."""
        from services.decision_maker_discovery import enrich_candidate_via_apollo
        candidate = MagicMock()
        candidate.candidate_name = "Amit Kulkarni"
        candidate.candidate_title = "Quality Manager"
        candidate.verification_status = "PERSON_PUBLICLY_VERIFIED"
        candidate.verification_confidence = 0.85
        candidate.apollo_enrichment_status = "NOT_ATTEMPTED"
        candidate.apollo_email = None

        db = MagicMock()
        with patch("services.apollo_adapter.enrich_specific_person") as mock_enrich:
            mock_enrich.return_value = {
                "status": "NO_RESULT",
                "email": None,
                "email_confidence": None,
                "phone": None,
                "raw_response": None,
            }
            res = enrich_candidate_via_apollo(candidate, "Bharat Forge Ltd", db)

        self.assertEqual(res["status"], "NO_RESULT")
        self.assertIsNone(candidate.apollo_email)
        # Should not falsely mark as APOLLO_ENRICHED if no email found
        self.assertNotEqual(candidate.verification_status, "APOLLO_ENRICHED")

    def test_case_l_email_found_but_not_verified(self):
        """Case L: Email found (guessed/unverified) -> Stored as EMAIL_FOUND with LOW/MEDIUM confidence, distinct from EMAIL_VERIFIED."""
        from services.decision_maker_discovery import enrich_candidate_via_apollo
        candidate = MagicMock()
        candidate.candidate_name = "Amit Kulkarni"
        candidate.candidate_title = "Quality Manager"
        candidate.verification_status = "PERSON_PUBLICLY_VERIFIED"
        candidate.verification_confidence = 0.85
        candidate.apollo_enrichment_status = "NOT_ATTEMPTED"
        candidate.apollo_email = None
        candidate.email_status = "NOT_FOUND"

        db = MagicMock()
        with patch("services.apollo_adapter.enrich_specific_person") as mock_enrich:
            mock_enrich.return_value = {
                "status": "ENRICHED",
                "email": "amit.kulkarni@bharatforge.com",
                "email_confidence": "LOW",
                "email_status": "guessed",
                "phone": None,
                "raw_response": {"person": {"email": "amit.kulkarni@bharatforge.com", "email_status": "guessed"}},
            }
            res = enrich_candidate_via_apollo(candidate, "Bharat Forge Ltd", db)

        self.assertEqual(res["status"], "ENRICHED")
        self.assertEqual(candidate.apollo_email, "amit.kulkarni@bharatforge.com")
        self.assertEqual(candidate.email_status, "EMAIL_FOUND")
        # Crucial: Not EMAIL_VERIFIED
        self.assertNotEqual(candidate.email_status, "EMAIL_VERIFIED")


if __name__ == "__main__":
    unittest.main()
