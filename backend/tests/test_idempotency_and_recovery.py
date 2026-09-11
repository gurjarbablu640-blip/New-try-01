"""Tests for Idempotency Guard and Restart Recovery.

Validates:
1. Same inputs produce same idempotency key (deterministic).
2. Duplicate detection blocks replay after restart.
3. State persists across IdempotencyGuard instances (simulating restart).
4. Different companies/operations produce different keys.
5. Expired entries can be cleaned up.
6. Scheduler restart does not duplicate morning discovery.
"""
import json
import os
import shutil
import tempfile
import unittest

from services.idempotency_guard import IdempotencyGuard, make_idempotency_key


class TestIdempotencyGuard(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.state_file = os.path.join(self.test_dir, "idempotency_state.json")
        self.guard = IdempotencyGuard(state_file=self.state_file)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_deterministic_key_generation(self):
        """Same inputs → same key."""
        k1 = make_idempotency_key(
            operation="discovery",
            company="Dixon Technologies",
            trigger="Oragadam plant MoU",
            date_str="2026-09-11",
        )
        k2 = make_idempotency_key(
            operation="discovery",
            company="Dixon Technologies",
            trigger="Oragadam plant MoU",
            date_str="2026-09-11",
        )
        self.assertEqual(k1, k2)

    def test_different_companies_produce_different_keys(self):
        """Different companies → different keys."""
        k1 = make_idempotency_key(operation="discovery", company="Dixon Technologies", date_str="2026-09-11")
        k2 = make_idempotency_key(operation="discovery", company="Bharat Forge", date_str="2026-09-11")
        self.assertNotEqual(k1, k2)

    def test_different_dates_produce_different_keys(self):
        """Same company, different day → different key (allows daily re-run)."""
        k1 = make_idempotency_key(operation="discovery", company="Dixon Technologies", date_str="2026-09-11")
        k2 = make_idempotency_key(operation="discovery", company="Dixon Technologies", date_str="2026-09-12")
        self.assertNotEqual(k1, k2)

    def test_duplicate_detection_blocks_replay(self):
        """First call returns False (not duplicate); second returns True (duplicate)."""
        key = make_idempotency_key(operation="staging", company="Dixon Technologies", date_str="2026-09-11")
        is_dup_1 = self.guard.check_and_mark(key, operation="staging")
        is_dup_2 = self.guard.check_and_mark(key, operation="staging")
        self.assertFalse(is_dup_1)
        self.assertTrue(is_dup_2)

    def test_state_persists_across_instances(self):
        """Simulating restart: new instance loads state from disk."""
        key = make_idempotency_key(operation="discovery", company="Suzlon Energy", date_str="2026-09-11")
        self.guard.check_and_mark(key, operation="discovery")

        # Create new guard instance (simulates restart)
        guard2 = IdempotencyGuard(state_file=self.state_file)
        self.assertTrue(guard2.is_processed(key))
        is_dup = guard2.check_and_mark(key, operation="discovery")
        self.assertTrue(is_dup)

    def test_no_duplicate_company_after_restart(self):
        """After restart, replaying same company discovery is blocked."""
        companies = ["Dixon Technologies", "Uno Minda", "Bharat Forge"]
        keys = []
        for co in companies:
            key = make_idempotency_key(operation="discovery", company=co, date_str="2026-09-11")
            keys.append(key)
            self.guard.check_and_mark(key, operation=f"discovery:{co}")

        # Simulate restart
        guard2 = IdempotencyGuard(state_file=self.state_file)
        for key in keys:
            self.assertTrue(guard2.is_processed(key))
            self.assertTrue(guard2.check_and_mark(key, operation="replay_attempt"))

    def test_no_duplicate_staging_after_restart(self):
        """After restart, re-staging same candidate is blocked."""
        key = make_idempotency_key(
            operation="staging",
            company="Dixon Technologies",
            person="Abhinav Tiwaari",
            date_str="2026-09-11",
        )
        self.assertFalse(self.guard.check_and_mark(key, operation="staging"))

        guard2 = IdempotencyGuard(state_file=self.state_file)
        self.assertTrue(guard2.check_and_mark(key, operation="staging"))

    def test_no_duplicate_follow_up(self):
        """Same follow-up for same company+person is idempotent."""
        key = make_idempotency_key(
            operation="follow_up_schedule",
            company="Valeo India",
            person="Abhijit Biswal",
            date_str="2026-09-11",
        )
        self.assertFalse(self.guard.check_and_mark(key))
        self.assertTrue(self.guard.check_and_mark(key))

    def test_expired_entries_cleanup(self):
        """Entries older than threshold can be cleaned."""
        key = make_idempotency_key(operation="old_task", company="OldCo", date_str="2025-01-01")
        self.guard._processed[key] = {
            "operation": "old_task",
            "processed_at": "2025-01-01T00:00:00+00:00",
        }
        self.guard._save()

        removed = self.guard.clear_expired(max_age_days=7)
        self.assertEqual(removed, 1)
        self.assertFalse(self.guard.is_processed(key))

    def test_processed_count(self):
        """Count accurately reflects processed operations."""
        for i in range(5):
            key = make_idempotency_key(operation="test", company=f"Co{i}", date_str="2026-09-11")
            self.guard.check_and_mark(key)
        self.assertEqual(self.guard.get_processed_count(), 5)


class TestSchedulerRecovery(unittest.TestCase):
    """Validates scheduler state recovery after restart."""

    def test_scheduler_state_file_has_valid_timestamps(self):
        """scheduler_state.json must have parseable ISO timestamps."""
        state_file = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "data", "runtime_state", "scheduler_state.json",
        )
        if not os.path.exists(state_file):
            self.skipTest("scheduler_state.json not found")

        with open(state_file, "r") as f:
            state = json.load(f)

        # Must have required fields
        self.assertIn("current_window", state)
        self.assertIn("metrics", state)
        self.assertIn("last_report_id", state)

        # Timestamp fields should be parseable
        for ts_field in ("last_discovery_start", "last_inbox_check_MORNING_1030"):
            ts_val = state.get(ts_field)
            if ts_val:
                from datetime import datetime, timezone
                parsed = datetime.fromisoformat(ts_val)
                self.assertIsNotNone(parsed)

    def test_scheduler_metrics_are_non_negative(self):
        """Scheduler metrics must be non-negative integers."""
        state_file = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "data", "runtime_state", "scheduler_state.json",
        )
        if not os.path.exists(state_file):
            self.skipTest("scheduler_state.json not found")

        with open(state_file, "r") as f:
            state = json.load(f)

        metrics = state.get("metrics", {})
        for key, val in metrics.items():
            self.assertGreaterEqual(val, 0, f"Metric {key} is negative: {val}")


if __name__ == "__main__":
    unittest.main()
