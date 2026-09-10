"""Unit tests for FollowUpEngine 3-stage consultative outbound cadence."""

import unittest
from datetime import datetime, timezone, timedelta

from services.follow_up_engine import (
    CADENCE_FOLLOW_UP_1_DUE,
    CADENCE_FOLLOW_UP_2_DUE,
    CADENCE_INITIAL,
    CADENCE_REACTIVATED,
    CADENCE_STOPPED,
    CADENCE_WAITING_FU1,
    CADENCE_WAITING_FU2,
    CadenceState,
    FollowUpEngine,
    add_business_days,
)


class TestFollowUpEngine(unittest.TestCase):
    def setUp(self):
        self.engine = FollowUpEngine()
        self.base_time = datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)  # Tuesday

    def test_add_business_days_skips_weekends(self):
        # Tuesday + 3 business days -> Friday (Sept 4)
        tue = datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)
        fri = add_business_days(tue, 3)
        self.assertEqual(fri.day, 4)
        self.assertEqual(fri.weekday(), 4)  # Friday

        # Friday + 1 business day -> Monday (Sept 7)
        mon = add_business_days(fri, 1)
        self.assertEqual(mon.day, 7)
        self.assertEqual(mon.weekday(), 0)  # Monday

    def test_cadence_progression_from_initial_to_fu1(self):
        state = CadenceState(
            record_id="rec-001",
            company="Tata Motors",
            facility="Sanand Plant",
            contact_name="Rajesh Verma",
            email="rajesh.verma@tatamotors.com",
            initial_sent_at=self.base_time.isoformat(),
        )

        # 1 day later (Wednesday): should be WAITING_FU1
        day1 = self.base_time + timedelta(days=1)
        res1 = self.engine.evaluate_cadence_stage(state, current_time=day1)
        self.assertEqual(res1["stage"], CADENCE_WAITING_FU1)
        self.assertFalse(res1["send_permitted"])

        # 3 business days later (Friday): should be FOLLOW_UP_1_DUE
        day3 = add_business_days(self.base_time, 3)
        res3 = self.engine.evaluate_cadence_stage(state, current_time=day3)
        self.assertEqual(res3["stage"], CADENCE_FOLLOW_UP_1_DUE)
        self.assertTrue(res3["send_permitted"])
        self.assertEqual(res3["action_required"], "SEND_FOLLOW_UP_1")

    def test_cadence_progression_from_fu1_to_fu2(self):
        fu1_time = add_business_days(self.base_time, 3)  # Friday Sept 4
        state = CadenceState(
            record_id="rec-002",
            company="Bharat Forge",
            facility="Mundhwa Plant",
            contact_name="Sunil Kulkarni",
            email="sunil.k@bharatforge.com",
            initial_sent_at=self.base_time.isoformat(),
            follow_up_1_sent_at=fu1_time.isoformat(),
        )

        # 2 business days after FU1 (Tuesday Sept 8): should be WAITING_FU2
        tue_next = add_business_days(fu1_time, 2)
        res_wait = self.engine.evaluate_cadence_stage(state, current_time=tue_next)
        self.assertEqual(res_wait["stage"], CADENCE_WAITING_FU2)
        self.assertFalse(res_wait["send_permitted"])

        # 4 business days after FU1 (Thursday Sept 10): should be FOLLOW_UP_2_DUE
        thu_next = add_business_days(fu1_time, 4)
        res_due = self.engine.evaluate_cadence_stage(state, current_time=thu_next)
        self.assertEqual(res_due["stage"], CADENCE_FOLLOW_UP_2_DUE)
        self.assertTrue(res_due["send_permitted"])
        self.assertEqual(res_due["action_required"], "SEND_FOLLOW_UP_2")

    def test_cadence_stops_after_fu2(self):
        fu1_time = add_business_days(self.base_time, 3)
        fu2_time = add_business_days(fu1_time, 4)
        state = CadenceState(
            record_id="rec-003",
            company="Dixon Technologies",
            facility="Sriperumbudur Plant",
            contact_name="Rakesh Sharma",
            email="rakesh.sharma@dixoninfo.com",
            initial_sent_at=self.base_time.isoformat(),
            follow_up_1_sent_at=fu1_time.isoformat(),
            follow_up_2_sent_at=fu2_time.isoformat(),
        )

        # After FU2 has been sent, cadence must stop
        later = fu2_time + timedelta(days=2)
        res = self.engine.evaluate_cadence_stage(state, current_time=later)
        self.assertEqual(res["stage"], CADENCE_STOPPED)
        self.assertFalse(res["send_permitted"])
        self.assertEqual(res["action_required"], "NO_ACTION")

    def test_cadence_stops_immediately_on_reply(self):
        state = CadenceState(
            record_id="rec-004",
            company="Uno Minda",
            facility="Manesar Plant",
            contact_name="Surender Singh",
            email="surender.singh@unominda.com",
            initial_sent_at=self.base_time.isoformat(),
            has_replied=True,
            reply_classification="INTERESTED",
        )

        # Even if 10 days passed, if replied, must STOP
        later = self.base_time + timedelta(days=10)
        res = self.engine.evaluate_cadence_stage(state, current_time=later)
        self.assertEqual(res["stage"], CADENCE_STOPPED)
        self.assertFalse(res["send_permitted"])
        self.assertIn("INTERESTED", res["reason"])

    def test_reactivation_on_new_verified_trigger(self):
        fu1_time = add_business_days(self.base_time, 3)
        fu2_time = add_business_days(fu1_time, 4)
        state = CadenceState(
            record_id="rec-005",
            company="Tata Motors",
            facility="Sanand Plant",
            contact_name="Rajesh Verma",
            email="rajesh.verma@tatamotors.com",
            initial_sent_at=self.base_time.isoformat(),
            follow_up_1_sent_at=fu1_time.isoformat(),
            follow_up_2_sent_at=fu2_time.isoformat(),
            status=CADENCE_STOPPED,
        )

        # New trigger emerges
        state = self.engine.reactivate_with_new_trigger(
            state=state,
            new_trigger_event="Phase 2 Battery Assembly Line Expansion",
            new_trigger_date="2026-09-08",
        )
        self.assertEqual(state.status, CADENCE_REACTIVATED)
        self.assertEqual(state.latest_trigger, "Phase 2 Battery Assembly Line Expansion")

        eval_res = self.engine.evaluate_cadence_stage(state)
        self.assertEqual(eval_res["stage"], CADENCE_REACTIVATED)
        self.assertTrue(eval_res["send_permitted"])

    def test_generate_follow_up_copy_quality(self):
        candidate = {
            "company": "Tata Motors",
            "facility": "Sanand Plant",
            "city": "Sanand",
            "contact_name": "Rajesh Verma",
            "first_name": "Rajesh",
            "email": "rajesh.verma@tatamotors.com",
            "calibration_opportunity": "CMM & Dimensional Testing Rig Calibration",
        }

        # Follow-up 1 Copy
        fu1 = self.engine.generate_follow_up_copy(candidate, "FOLLOW_UP_1")
        self.assertIn("Sanand Plant", fu1["body_text"])
        self.assertIn("CC-3963", fu1["body_text"])
        self.assertIn("ISO/IEC 17025:2017", fu1["body_text"])
        self.assertIn("Rajesh", fu1["body_text"])
        self.assertFalse(fu1["audit"]["has_forbidden_filler"])
        self.assertTrue(fu1["audit"]["facility_specific"])

        # Follow-up 2 Copy
        fu2 = self.engine.generate_follow_up_copy(candidate, "FOLLOW_UP_2")
        self.assertIn("Sanand Plant", fu2["body_text"])
        self.assertIn("CC-3963", fu2["body_text"])
        self.assertIn("point me to the right lead", fu2["body_text"].lower())
        self.assertFalse(fu2["audit"]["has_forbidden_filler"])
        self.assertTrue(fu2["audit"]["facility_specific"])


if __name__ == "__main__":
    unittest.main()
