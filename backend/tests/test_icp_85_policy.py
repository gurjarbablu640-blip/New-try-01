import os
import tempfile
import unittest

from services.fast_contact_waterfall import (
    FastContactWaterfallService,
    STATUS_HOLD_LOW_SCORE,
    STATUS_PENDING_APOLLO_RENEWAL,
    compute_deterministic_priority_and_status,
)


def qualified_candidate(score=85.0, person_confidence="HIGH"):
    return {
        "company": "Example Manufacturing",
        "lead_score": score,
        "trigger_to_facility": "DIRECT",
        "trigger_event_semantics_verified": True,
        "timing_class": "CURRENT",
        "primary_person": {
            "name": "Arun Sharma",
            "title": "Plant Quality Head",
            "authority_class": "STRONG_PLANT_QUALITY_OWNER",
            "person_confidence": person_confidence,
            "current_employment": "VERIFIED",
            "facility_relationship": "FACILITY_FUNCTION_OWNER",
        },
    }


class Icp85ApolloPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.service = FastContactWaterfallService(
            apollo_log_file=os.path.join(self.temp_dir.name, "apollo.json"),
            contact_cache_file=os.path.join(self.temp_dir.name, "cache.json"),
            pending_queue_file=os.path.join(self.temp_dir.name, "queue.json"),
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_priority_boundaries(self):
        self.assertEqual(compute_deterministic_priority_and_status(95), ("P1", STATUS_PENDING_APOLLO_RENEWAL))
        self.assertEqual(compute_deterministic_priority_and_status(90), ("P2", STATUS_PENDING_APOLLO_RENEWAL))
        self.assertEqual(compute_deterministic_priority_and_status(85), ("P3", STATUS_PENDING_APOLLO_RENEWAL))
        self.assertEqual(compute_deterministic_priority_and_status(84.99), ("HOLD", STATUS_HOLD_LOW_SCORE))

    def test_p3_high_verified_person_is_apollo_eligible(self):
        eligible, reason = self.service.is_apollo_eligible(qualified_candidate())
        self.assertTrue(eligible, reason)

    def test_p3_low_or_medium_person_is_not_apollo_eligible(self):
        for confidence in ("LOW", "MEDIUM"):
            eligible, reason = self.service.is_apollo_eligible(qualified_candidate(person_confidence=confidence))
            self.assertFalse(eligible)
            self.assertIn("HIGH is required", reason)


if __name__ == "__main__":
    unittest.main()
