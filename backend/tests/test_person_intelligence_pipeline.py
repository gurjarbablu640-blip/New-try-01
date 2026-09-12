"""Unit and Regression Tests for Decision-Maker Intelligence Pipeline.

Tests all requirements of Phase 21:
- Company name rejected as human
- LinkedIn company page not treated as person profile
- Old employment evidence cannot become VERIFIED
- Company-only role cannot establish facility ownership
- Multi-site role cannot automatically map to one plant
- Plant Quality Head may qualify without literal 'calibration'
- Generic Quality Executive should not automatically become high authority
- Gemini ranking / external rank cannot override missing evidence
- Benchmark expected person cannot leak into production search
- Production Apollo queue isolation (Maruti intact, zero unqualified leakage)
"""
import inspect
import json
import os
import unittest
from unittest.mock import MagicMock

from services.person_intelligence_service import (
    classify_authority_class,
    classify_current_employment,
    classify_facility_relationship,
    compute_deterministic_person_score,
    extract_person_from_search_result,
    generate_person_search_queries,
    generate_deepseek_person_queries,
    is_human_person_candidate,
    rank_candidates_with_deepseek,
)
from services.llm_provider import LLMResponse


class PersonIntelligencePipelineTests(unittest.TestCase):
    def test_company_name_rejected_as_human(self):
        """Company names, department names, and generic organizations must be rejected."""
        cases = [
            ("Ramkrishna Forgings Limited", "Ramkrishna Forgings"),
            ("Shyam Metalics and Energy", "Shyam Metalics"),
            ("Suzuki Motor Gujarat", "Suzuki Motor Gujarat"),
            ("Operations Leadership Team", "Maruti Suzuki"),
            ("Quality Assurance Department", "Valeo India"),
            ("Sri Ramakrishna Paramahamsa", "Ramkrishna Forgings"),
            ("Swami Vivekananda", "Ramkrishna Forgings"),
            ("Dev Smrt Status", "Ramkrishna Forgings"),
        ]
        for name_str, comp in cases:
            is_human, reason = is_human_person_candidate(name_str, company_name=comp)
            self.assertFalse(is_human, f"Expected '{name_str}' to be rejected as human, but passed. Reason: {reason}")

    def test_legitimate_human_names_accepted(self):
        """Genuine Indian human names with initials/honorifics must pass."""
        valid_names = [
            "Atul Jain",
            "Abhijit Biswal",
            "Ravi Singh",
            "Dr. Dharmendra Chouhan",
            "Vijayaraghavan Manian",
            "M. I. Ahmad",
            "Manohar Pandey",
            "Rishabh Srivastava",
        ]
        for name_str in valid_names:
            is_human, reason = is_human_person_candidate(name_str, company_name="Test Engineering Ltd")
            self.assertTrue(is_human, f"Expected '{name_str}' to pass as human, but rejected. Reason: {reason}")

    def test_linkedin_company_page_not_treated_as_person_profile(self):
        """LinkedIn company pages or search directories must not extract as person candidates."""
        company_item = {
            "title": "Ramkrishna Forgings Limited | LinkedIn",
            "url": "https://in.linkedin.com/company/ramkrishna-forgings",
            "snippet": "Ramkrishna Forgings Limited | 50,000+ followers on LinkedIn. Manufacturing company based in Kolkata.",
        }
        cand = extract_person_from_search_result(company_item, company_name="Ramkrishna Forgings")
        self.assertIsNone(cand, "LinkedIn company page was wrongly extracted as a person candidate")

    def test_old_employment_cannot_become_verified(self):
        """Ex-employees or past roles must be marked CONTRADICTED or UNKNOWN, never VERIFIED."""
        snippet_former = "Former Quality Manager at Valeo India until 2022. Currently VP Quality at Rieter India."
        status = classify_current_employment(snippet_former, "Quality Head", "Valeo India")
        self.assertIn(status, ("CONTRADICTED", "UNKNOWN"))
        self.assertNotEqual(status, "VERIFIED")

        # Stale bio without recent proof
        snippet_stale = "Attended quality conference in 2018 representing Valeo India."
        status_stale = classify_current_employment(snippet_stale, "Engineer", "Valeo India")
        self.assertNotEqual(status_stale, "VERIFIED")

    def test_company_only_role_cannot_establish_facility_ownership(self):
        """A corporate role without facility or city match cannot establish facility ownership."""
        fac_rel = classify_facility_relationship(
            candidate_title="Corporate Head of Quality",
            candidate_text="Based in Mumbai Corporate Headquarters, overseeing group policies.",
            target_facility="Plant V Baliguma",
            target_city="Jamshedpur",
        )
        self.assertNotEqual(fac_rel, "FACILITY_OWNER")
        self.assertNotEqual(fac_rel, "FACILITY_FUNCTION_OWNER")
        self.assertIn(fac_rel, ("GROUP_FUNCTION_OWNER", "COMPANY_ONLY"))

    def test_multi_site_role_cannot_automatically_map_to_one_plant(self):
        """Multi-site company role in Pune cannot be assigned as plant owner in Sanand."""
        fac_rel = classify_facility_relationship(
            candidate_title="Plant Quality Head - Pune Facility",
            candidate_text="Manages testing and quality for Pune operations.",
            target_facility="Sanand Plant",
            target_city="Sanand",
        )
        self.assertNotEqual(fac_rel, "FACILITY_OWNER")
        self.assertNotEqual(fac_rel, "FACILITY_FUNCTION_OWNER")

    def test_plant_quality_head_qualifies_without_literal_calibration(self):
        """A Plant Quality Head must qualify for high authority without requiring literal 'calibration'."""
        auth_class = classify_authority_class("Plant Quality Head")
        self.assertEqual(auth_class, "STRONG_PLANT_QUALITY_OWNER")

        score, conf = compute_deterministic_person_score(
            current_employment="VERIFIED",
            facility_relationship="FACILITY_FUNCTION_OWNER",
            authority_class=auth_class,
            title="Plant Quality Head",
            source_quality="LINKEDIN_SEARCH_SNIPPET",
        )
        # 25 (emp) + 25 (fac) + 23 (fn) + 15 (auth) + 8 (src) = 96.0
        self.assertGreaterEqual(score, 85.0)
        self.assertEqual(conf, "HIGH")

    def test_generic_quality_executive_not_high_authority(self):
        """A generic Quality Executive or Trainee must not receive high authority or score >= 85."""
        auth_class = classify_authority_class("Quality Executive")
        self.assertNotEqual(auth_class, "STRONG_PLANT_QUALITY_OWNER")
        self.assertNotEqual(auth_class, "DIRECT_CALIBRATION_OWNER")

        score, conf = compute_deterministic_person_score(
            current_employment="VERIFIED",
            facility_relationship="FACILITY_FUNCTION_OWNER",
            authority_class=auth_class,
            title="Quality Executive",
            source_quality="LINKEDIN_SEARCH_SNIPPET",
        )
        # Authority score for executive is 5.0, function is lower -> cannot be HIGH
        self.assertLess(score, 85.0)
        self.assertNotEqual(conf, "HIGH")

    def test_gemini_ranking_cannot_override_missing_evidence(self):
        """Deterministic evidence governs confidence; missing employment caps confidence at LOW."""
        score, conf = compute_deterministic_person_score(
            current_employment="UNKNOWN",
            facility_relationship="COMPANY_ONLY",
            authority_class="STRONG_PLANT_QUALITY_OWNER",
            title="Vice President Quality",
            source_quality="LINKEDIN_SEARCH_SNIPPET",
        )
        self.assertEqual(conf, "LOW")
        self.assertLess(score, 70.0)

    def test_deepseek_ranking_cannot_override_missing_evidence(self):
        candidates = [{
            "name": "Arun Sharma",
            "title": "Quality Head",
            "current_employment": "UNKNOWN",
            "facility_relationship": "COMPANY_ONLY",
            "authority_class": "STRONG_PLANT_QUALITY_OWNER",
            "person_score": 45.0,
            "person_confidence": "LOW",
            "source_url": "https://example.com/profile",
            "evidence_snippet": "Quality profile with no current facility evidence",
        }]
        provider = MagicMock()
        provider.complete.return_value = LLMResponse(
            text=json.dumps({"ranked_candidates": [{
                "name": "Arun Sharma",
                "rank": 1,
                "employment_assessment": "VERIFIED",
                "facility_relationship": "DIRECT",
                "functional_alignment": "STRONG",
                "authority_class": "STRONG_PLANT_QUALITY_OWNER",
                "confidence": 0.99,
                "reason": "Model assertion",
            }]}),
            usage={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
            provider="hive",
            model="deepseek-ai/DeepSeek-V4.1-Flash",
        )
        result = rank_candidates_with_deepseek(
            company_name="Example Manufacturing",
            facility_name="Pune Plant",
            city="Pune",
            commercial_trigger="Plant expansion",
            target_functions=["Plant Quality"],
            candidates=candidates,
            provider=provider,
        )
        ranked = result["candidates"][0]
        self.assertEqual(ranked["current_employment"], "UNKNOWN")
        self.assertEqual(ranked["facility_relationship"], "COMPANY_ONLY")
        self.assertEqual(ranked["person_confidence"], "LOW")

    def test_deepseek_query_generation_is_bounded_and_has_no_expected_answer_field(self):
        provider = MagicMock()
        provider.complete.return_value = LLMResponse(
            text=json.dumps({"queries": ["q1", "q2", "q3", "q4"]}),
            provider="hive",
            model="deepseek-ai/DeepSeek-V4.1-Flash",
        )
        result = generate_deepseek_person_queries(
            company_name="Example Manufacturing",
            facility_name="Pune Plant",
            city="Pune",
            commercial_trigger="Plant expansion",
            target_functions=["Plant Quality"],
            provider=provider,
        )
        self.assertEqual(result["queries"], ["q1", "q2", "q3"])
        prompt = provider.complete.call_args.kwargs["messages"][0]["content"]
        self.assertNotIn("expected_person", prompt)
        self.assertNotIn("expected_title", prompt)

    def test_benchmark_zero_answer_leakage(self):
        """generate_person_search_queries must not accept or leak expected person names."""
        sig = inspect.signature(generate_person_search_queries)
        params = list(sig.parameters.keys())
        self.assertNotIn("expected_person", params)
        self.assertNotIn("expected_name", params)
        self.assertNotIn("person_name", params)

        queries = generate_person_search_queries(
            company_name="Ramkrishna Forgings",
            facility_name="Plant V Baliguma",
            city="Jamshedpur",
        )
        for q_dict in queries:
            q_text = q_dict["query"]
            self.assertNotIn("Atul Jain", q_text)
            self.assertNotIn("Abhijit Biswal", q_text)
            self.assertNotIn("Ravi Singh", q_text)

    def test_production_apollo_queue_isolation(self):
        """Verify that Maruti Suzuki remains the sole active record in apollo_pending_queue.json."""
        q_path = os.path.join(
            os.path.dirname(__file__), "..", "data", "runtime_state", "apollo_pending_queue.json"
        )
        self.assertTrue(os.path.exists(q_path))
        with open(q_path, "r", encoding="utf-8") as f:
            queue = json.load(f)

        active = [r for r in queue if r.get("status") == "PENDING_APOLLO_RENEWAL"]
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["person_name"], "Atul Jain")
        self.assertEqual(active[0]["lead_score"], 100.0)
        self.assertEqual(active[0]["lookup_priority"], "P1")


if __name__ == "__main__":
    unittest.main()
