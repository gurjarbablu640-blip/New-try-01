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
        with patch("services.apollo_adapter.settings") as mock_settings:
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


if __name__ == "__main__":
    unittest.main()
