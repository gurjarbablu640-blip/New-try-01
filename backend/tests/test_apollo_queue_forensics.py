"""Unit & regression tests for Apollo queue forensic purge, deterministic score/priority,
origin provenance, trigger source validation, recency consistency, and renewal safety.
"""
import json
import os
import unittest
from unittest.mock import patch, MagicMock

from services.fast_contact_waterfall import (
    FastContactWaterfallService,
    STATUS_PENDING_APOLLO_RENEWAL,
    STATUS_HOLD_STALE_TRIGGER,
    STATUS_HOLD_LOW_SCORE,
    STATUS_HOLD_PERSON_REVIEW,
    STATUS_HOLD_WRONG_PERSON,
    STATUS_HOLD_TRIGGER_INVALID,
    STATUS_HOLD_FACILITY_AMBIGUOUS,
    STATUS_HOLD_QUEUE_PROVENANCE_INVALID,
    STATUS_HOLD_RECENCY_INCONSISTENT,
    compute_deterministic_priority_and_status,
    is_stock_quote_url,
    is_generic_homepage_url,
)

class TestApolloQueueForensics(unittest.TestCase):
    """Forensic verification tests enforcing Salesoorja commercial and queue policies."""

    def setUp(self):
        self.test_log = "backend/data/runtime_state/test_apollo_query_log.json"
        self.test_cache = "backend/data/runtime_state/test_contact_cache.json"
        self.test_queue = "backend/data/runtime_state/test_forensic_apollo_pending_queue.json"
        for p in [self.test_log, self.test_cache, self.test_queue]:
            if os.path.exists(p):
                os.remove(p)
        self.service = FastContactWaterfallService(
            apollo_log_file=self.test_log,
            contact_cache_file=self.test_cache,
            pending_queue_file=self.test_queue,
        )

    def tearDown(self):
        for p in [self.test_log, self.test_cache, self.test_queue]:
            if os.path.exists(p):
                os.remove(p)

    # ─────────────────────────────────────────────────────────────────
    # Defect 1: Score & Priority Mapping Tests
    # ─────────────────────────────────────────────────────────────────

    def test_score_95_is_p1(self):
        """score >= 95 MUST be mapped to P1 and PENDING_APOLLO_RENEWAL."""
        priority, status = compute_deterministic_priority_and_status(95.0)
        self.assertEqual(priority, "P1")
        self.assertEqual(status, STATUS_PENDING_APOLLO_RENEWAL)

        priority_100, status_100 = compute_deterministic_priority_and_status(100.0)
        self.assertEqual(priority_100, "P1")
        self.assertEqual(status_100, STATUS_PENDING_APOLLO_RENEWAL)

    def test_score_94_is_p2(self):
        """90 <= score < 95 MUST be mapped to P2 and PENDING_APOLLO_RENEWAL."""
        priority, status = compute_deterministic_priority_and_status(94.0)
        self.assertEqual(priority, "P2")
        self.assertEqual(status, STATUS_PENDING_APOLLO_RENEWAL)

        priority_90, status_90 = compute_deterministic_priority_and_status(90.0)
        self.assertEqual(priority_90, "P2")
        self.assertEqual(status_90, STATUS_PENDING_APOLLO_RENEWAL)

    def test_score_89_is_p3_and_84_99_is_hold(self):
        """85 <= score < 90 maps to P3; only scores below 85 are held."""
        priority, status = compute_deterministic_priority_and_status(89.0)
        self.assertEqual(priority, "P3")
        self.assertEqual(status, STATUS_PENDING_APOLLO_RENEWAL)

        priority_85, status_85 = compute_deterministic_priority_and_status(85.0)
        self.assertEqual(priority_85, "P3")
        self.assertEqual(status_85, STATUS_PENDING_APOLLO_RENEWAL)

        priority_hold, status_hold = compute_deterministic_priority_and_status(84.99)
        self.assertEqual(priority_hold, "HOLD")
        self.assertEqual(status_hold, STATUS_HOLD_LOW_SCORE)

        # Candidate with score 89 cannot enter Apollo enrichment queue
        candidate = {
            "company": "Test Co",
            "lead_score": 84.99,
            "trigger_to_facility": "DIRECT",
            "primary_person": {
                "name": "Arun Sharma",
                "title": "Plant Head",
                "authority_classification": "STRONG_PLANT_QUALITY_OWNER",
            }
        }
        eligible, reason = self.service.is_apollo_eligible(candidate)
        self.assertFalse(eligible)
        self.assertIn("below Apollo qualification threshold", reason)

    # ─────────────────────────────────────────────────────────────────
    # Defect 2: Recency Data Inconsistency Tests
    # ─────────────────────────────────────────────────────────────────

    def test_stored_recency_mismatch_rejected(self):
        """Stored recency mismatching calculated recency by > 2 days must be rejected."""
        candidate = {
            "company": "Marksans Pharma Limited",
            "lead_score": 95.0,
            "trigger_to_facility": "DIRECT",
            "primary_person": {
                "name": "Anil Mohanty",
                "title": "Plant Head",
                "authority_classification": "STRONG_PLANT_QUALITY_OWNER",
            },
            "recency_diff": 80,  # 90d stored vs 10d calculated
            "recency_data_inconsistency": True,
        }
        eligible, reason = self.service.is_apollo_eligible(candidate)
        self.assertFalse(eligible)
        self.assertIn("Recency data inconsistency detected", reason)

    # ─────────────────────────────────────────────────────────────────
    # Defect 3: Trigger Source Quality & Event Semantics Tests
    # ─────────────────────────────────────────────────────────────────

    def test_moneycontrol_stock_page_cannot_prove_plant_expansion(self):
        """A Moneycontrol or Economic Times stock price quote page alone cannot qualify as a trigger."""
        mc_url = "https://www.moneycontrol.com/india/stockpricequote/pharmaceuticals/marksanspharma/MP21"
        self.assertTrue(is_stock_quote_url(mc_url))

        et_url = "https://economictimes.indiatimes.com/kopran-ltd/stocks/companyid-11077.cms"
        self.assertTrue(is_stock_quote_url(et_url))

        candidate = {
            "company": "Marksans Pharma Limited",
            "lead_score": 95.0,
            "trigger_source": mc_url,
            "trigger_to_facility": "DIRECT",
            "primary_person": {
                "name": "Rajesh Kumar",
                "title": "Plant Head",
                "authority_classification": "STRONG_PLANT_QUALITY_OWNER",
            }
        }
        eligible, reason = self.service.is_apollo_eligible(candidate)
        self.assertFalse(eligible)
        self.assertIn("stock quote page", reason)

    def test_generic_homepage_cannot_prove_plant_expansion(self):
        """A generic company homepage without verified event semantics cannot qualify as a trigger."""
        home_url = "https://dixoninfo.com/"
        self.assertTrue(is_generic_homepage_url(home_url))

        candidate = {
            "company": "Dixon Technologies",
            "lead_score": 95.0,
            "trigger_source": home_url,
            "trigger_to_facility": "DIRECT",
            "primary_person": {
                "name": "Rajesh Kumar",
                "title": "Plant Head",
                "authority_classification": "STRONG_PLANT_QUALITY_OWNER",
            }
        }
        eligible, reason = self.service.is_apollo_eligible(candidate)
        self.assertFalse(eligible)
        self.assertIn("generic homepage", reason)

    # ─────────────────────────────────────────────────────────────────
    # Defect 4: Queue Provenance Gate Tests
    # ─────────────────────────────────────────────────────────────────

    def test_manual_payload_cannot_enter_production_queue(self):
        """Manual test payloads cannot enter the active Apollo queue."""
        candidate = {
            "company": "Manual Synthetic Co",
            "lead_score": 98.0,
            "queue_origin": "MANUAL_TEST_PAYLOAD",
            "trigger_to_facility": "DIRECT",
            "primary_person": {
                "name": "Vikram Singh",
                "title": "Plant Head",
                "authority_classification": "STRONG_PLANT_QUALITY_OWNER",
            }
        }
        eligible, reason = self.service.is_apollo_eligible(candidate)
        self.assertFalse(eligible)
        self.assertIn("Queue origin 'MANUAL_TEST_PAYLOAD' is invalid", reason)

    def test_scratch_test_payload_cannot_become_active(self):
        """Scratch scripts or fixture payloads cannot become active production queue records."""
        for invalid_origin in ["SCRATCH_SCRIPT", "FIXTURE", "UNKNOWN"]:
            candidate = {
                "company": "Scratch Co",
                "lead_score": 98.0,
                "queue_origin": invalid_origin,
                "trigger_to_facility": "DIRECT",
                "primary_person": {
                    "name": "Vikram Singh",
                    "title": "Plant Head",
                    "authority_classification": "STRONG_PLANT_QUALITY_OWNER",
                }
            }
            eligible, reason = self.service.is_apollo_eligible(candidate)
            self.assertFalse(eligible, f"Failed to reject origin: {invalid_origin}")
            self.assertIn("Queue origin", reason)

    # ─────────────────────────────────────────────────────────────────
    # Defect 5: Person Authority Commercial Ownership Tests
    # ─────────────────────────────────────────────────────────────────

    def test_functionally_relevant_alone_cannot_automatically_qualify(self):
        """FUNCTIONALLY_RELEVANT without verified commercial ownership (e.g. Officer softgel) must be rejected."""
        candidate = {
            "company": "Marksans Pharma Limited",
            "lead_score": 95.0,
            "trigger_to_facility": "DIRECT",
            "primary_person": {
                "name": "Anil Mohanty",
                "title": "Officer softgel",
                "authority_classification": "FUNCTIONALLY_RELEVANT",
            }
        }
        eligible, reason = self.service.is_apollo_eligible(candidate)
        self.assertFalse(eligible)
        self.assertIn("lacks verified commercial ownership evidence", reason)

    # ─────────────────────────────────────────────────────────────────
    # Phase 10: Queue Processor Safety & HOLD Skip Tests
    # ─────────────────────────────────────────────────────────────────

    def test_queue_processor_skips_every_hold_status(self):
        """process_pending_apollo_queue must skip every record that has a HOLD status."""
        self.service._pending_queue = [
            {
                "company": "Stale Co",
                "person_name": "Person A",
                "person_title": "VP",
                "status": STATUS_HOLD_STALE_TRIGGER,
                "lead_score": 95.0,
                "lookup_priority": "P1",
                "queue_origin": "AUTOMATED_PIPELINE",
                "trigger_event_semantics_verified": True,
                "trigger_to_facility": "DIRECT",
                "apollo_person_confidence": "HIGH",
                "current_employment_verified": True,
                "authority_class": "STRONG_PLANT_QUALITY_OWNER",
                "person_facility_relationship": "FACILITY_OWNER",
            },
            {
                "company": "Low Score Co",
                "person_name": "Person B",
                "person_title": "VP",
                "status": STATUS_HOLD_LOW_SCORE,
                "lead_score": 75.0,
                "lookup_priority": "HOLD",
                "queue_origin": "AUTOMATED_PIPELINE",
                "trigger_event_semantics_verified": True,
                "trigger_to_facility": "DIRECT",
                "apollo_person_confidence": "HIGH",
            },
            {
                "company": "Review Co",
                "person_name": "Person C",
                "person_title": "Quality Engineer",
                "status": STATUS_HOLD_PERSON_REVIEW,
                "lead_score": 92.0,
                "lookup_priority": "P2",
                "queue_origin": "AUTOMATED_PIPELINE",
                "trigger_event_semantics_verified": True,
                "trigger_to_facility": "DIRECT",
                "apollo_person_confidence": "MEDIUM",
            },
            {
                "company": "Wrong Person Co",
                "person_name": "Person D",
                "person_title": "Intern",
                "status": STATUS_HOLD_WRONG_PERSON,
                "lead_score": 92.0,
                "lookup_priority": "P2",
                "queue_origin": "AUTOMATED_PIPELINE",
                "trigger_event_semantics_verified": True,
                "trigger_to_facility": "DIRECT",
                "apollo_person_confidence": "LOW",
            },
            {
                "company": "Invalid Trigger Co",
                "person_name": "Person E",
                "person_title": "VP",
                "status": STATUS_HOLD_TRIGGER_INVALID,
                "lead_score": 0.0,
                "lookup_priority": "HOLD",
                "queue_origin": "AUTOMATED_PIPELINE",
                "trigger_event_semantics_verified": False,
                "trigger_to_facility": "DIRECT",
                "apollo_person_confidence": "HIGH",
            },
            {
                "company": "Ambiguous Facility Co",
                "person_name": "Person F",
                "person_title": "VP",
                "status": STATUS_HOLD_FACILITY_AMBIGUOUS,
                "lead_score": 95.0,
                "lookup_priority": "P1",
                "queue_origin": "AUTOMATED_PIPELINE",
                "trigger_event_semantics_verified": True,
                "trigger_to_facility": "WEAK",
                "apollo_person_confidence": "HIGH",
            },
            {
                "company": "Invalid Provenance Co",
                "person_name": "Person G",
                "person_title": "VP",
                "status": STATUS_HOLD_QUEUE_PROVENANCE_INVALID,
                "lead_score": 95.0,
                "lookup_priority": "P1",
                "queue_origin": "SCRATCH_SCRIPT",
                "trigger_event_semantics_verified": True,
                "trigger_to_facility": "DIRECT",
                "apollo_person_confidence": "HIGH",
            },
            {
                "company": "Recency Inconsistent Co",
                "person_name": "Person H",
                "person_title": "VP",
                "status": STATUS_HOLD_RECENCY_INCONSISTENT,
                "lead_score": 95.0,
                "lookup_priority": "P1",
                "queue_origin": "AUTOMATED_PIPELINE",
                "trigger_event_semantics_verified": True,
                "trigger_to_facility": "DIRECT",
                "apollo_person_confidence": "HIGH",
                "recency_data_inconsistency": True,
            },
        ]

        res = self.service.process_pending_apollo_queue()
        self.assertEqual(res["total_in_queue"], 8)
        self.assertEqual(res["eligible_count"], 0)
        self.assertEqual(res["skipped_count"], 8)
        self.assertEqual(res["apollo_live_calls_made"], 0)

    def test_queue_processor_only_processes_active_compliant(self):
        """process_pending_apollo_queue must execute only genuine, compliant PENDING_APOLLO_RENEWAL leads."""
        self.service._pending_queue = [
            {
                "company": "Maruti Suzuki / Suzuki Motor Gujarat",
                "person_name": "Atul Jain",
                "person_title": "Vice President & Plant Head",
                "status": STATUS_PENDING_APOLLO_RENEWAL,
                "lead_score": 99.0,
                "lookup_priority": "P1",
                "queue_origin": "AUTOMATED_PIPELINE",
                "trigger_event_semantics_verified": True,
                "trigger_to_facility": "DIRECT",
                "apollo_person_confidence": "HIGH",
                "current_employment_verified": True,
                "authority_class": "STRONG_PLANT_QUALITY_OWNER",
                "person_facility_relationship": "FACILITY_OWNER",
                "calculated_recency_days": 44,
                "recency_data_inconsistency": False,
            }
        ]

        # In night mode (APOLLO_ENABLED_FOR_LIVE_LOOKUP = False), zero calls made
        res = self.service.process_pending_apollo_queue()
        self.assertEqual(res["eligible_count"], 1)
        self.assertEqual(res["skipped_count"], 0)
        self.assertEqual(res["apollo_live_calls_made"], 0)

        # In live mode (renewed tomorrow)
        with patch("services.fast_contact_waterfall.get_setting_value", side_effect=lambda k, d=None: True if k == "APOLLO_ENABLED_FOR_LIVE_LOOKUP" else d):
            with patch("services.fast_contact_waterfall.enrich_specific_person", return_value={"status": "SUCCESS", "email": "atul.jain@marutisuzuki.com"}):
                live_res = self.service.process_pending_apollo_queue()
                self.assertEqual(live_res["eligible_count"], 1)
                self.assertEqual(live_res["resumed_count"], 1)
                self.assertEqual(live_res["results"][0]["email"], "atul.jain@marutisuzuki.com")
                self.assertEqual(live_res["credits_consumed"], 1)


if __name__ == "__main__":
    unittest.main()
