"""Unit tests for FollowUpEngine 5-Touch consultative outbound cadence.

Validates:
- Touch 1: Day 1 (initial outreach)
- Touch 2: Day 3 (Follow-up 1) on same thread
- Touch 3: Day 5 (Follow-up 2) on same thread
- Touch 4: Day 11 (Follow-up 3) on same thread
- Touch 5: Day 21 (Final Follow-up) on same thread
- Termination after Day 21 final follow-up (no further automatic follow-ups)
- Reply after Day 1 cancels all subsequent follow-ups
- Reply after Day 3 cancels Days 5, 11, 21
- Reply after Day 5 cancels Days 11, 21
- Reply after Day 11 cancels Day 21
- Stop on Opt-Out / Unsubscribe
- Stop on Bounce / Invalid Mailbox
- Stop if lead is Superseded
- OOO pauses cadence and reschedules rather than blind-sending
- Restart idempotency protection prevents duplicate sends
- Threading headers (In-Reply-To, References, Re: subject) preserved
- Copy rules enforced (no filler, CC-3963 approved parameters, closure note)
"""
import unittest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from services.follow_up_engine import (
    FollowUpEngine,
    CadenceState,
    ThreadIdentifiers,
    KOLKATA_TZ,
    STATE_INITIAL_SENT,
    STATE_FOLLOWUP_1_DUE,
    STATE_FOLLOWUP_2_DUE,
    STATE_FOLLOWUP_3_DUE,
    STATE_FINAL_FOLLOWUP_DUE,
    STATE_REPLIED,
    STATE_STOPPED,
    STATE_BOUNCED,
    STATE_OPTED_OUT,
    STATE_OOO_PAUSED,
    CADENCE_REACTIVATED,
    calculate_cadence_schedule,
    parse_ooo_return_date,
)


class TestFollowUpEngine5Touch(unittest.TestCase):
    def setUp(self):
        self.engine = FollowUpEngine()
        # Tuesday, Sept 1, 2026 at 10:00 AM IST
        self.base_time = datetime(2026, 9, 1, 10, 0, tzinfo=KOLKATA_TZ)
        self.state = self.engine.initialize_cadence(
            record_id="rec-varroc-001",
            company="Varroc Engineering Ltd",
            facility="Chakan MIDC Vendor Park Campus",
            contact_name="Anil Patil",
            email="anil.patil@varroc.com",
            initial_sent_at=self.base_time,
            message_id="<msg-initial-varroc-001@oorja.local>",
            original_subject="NABL Calibration Traceability & Audit Readiness — Varroc Engineering (Chakan)",
            lead_id="lead-101",
            campaign_id="camp-auto-01",
            calibration_opportunity="CMM & Dimensional Testing Rig Calibration",
        )

    def test_cadence_schedule_exact_calendar_days(self):
        """Touch 1 (Day 1) -> Touch 2 (Day 3) -> Touch 3 (Day 5) -> Touch 4 (Day 11) -> Touch 5 (Day 21)."""
        sched = calculate_cadence_schedule(self.base_time)
        self.assertEqual(sched["initial"].day, 1)  # Sept 1 (Day 1)
        self.assertEqual(sched["followup_1_due"].day, 3)  # Sept 3 (Day 3)
        self.assertEqual(sched["followup_2_due"].day, 5)  # Sept 5 (Day 5)
        self.assertEqual(sched["followup_3_due"].day, 11)  # Sept 11 (Day 11)
        self.assertEqual(sched["final_followup_due"].day, 21)  # Sept 21 (Day 21)

    def test_cadence_progression_all_5_touches(self):
        """Walk through progression of all 5 outreach touches without reply."""
        # 1. Day 1: Just sent initial -> WAITING_FOLLOWUP_1
        res_day1 = self.engine.evaluate_cadence_stage(self.state, current_time=self.base_time)
        self.assertEqual(res_day1["stage"], "WAITING_FOLLOWUP_1")
        self.assertFalse(res_day1["send_permitted"])

        # 2. Day 3 (Sept 3 10:00 IST): Follow-up 1 Due
        day3 = self.base_time + timedelta(days=2)
        res_day3 = self.engine.evaluate_cadence_stage(self.state, current_time=day3)
        self.assertEqual(res_day3["stage"], STATE_FOLLOWUP_1_DUE)
        self.assertEqual(res_day3["touch_number"], 2)
        self.assertTrue(res_day3["send_permitted"])

        # Record Follow-up 1 sent
        self.state.followup_1_sent_at = day3.isoformat()

        # Day 4 (Sept 4): WAITING_FOLLOWUP_2
        day4 = self.base_time + timedelta(days=3)
        res_day4 = self.engine.evaluate_cadence_stage(self.state, current_time=day4)
        self.assertEqual(res_day4["stage"], "WAITING_FOLLOWUP_2")
        self.assertFalse(res_day4["send_permitted"])

        # 3. Day 5 (Sept 5 10:00 IST): Follow-up 2 Due
        day5 = self.base_time + timedelta(days=4)
        res_day5 = self.engine.evaluate_cadence_stage(self.state, current_time=day5)
        self.assertEqual(res_day5["stage"], STATE_FOLLOWUP_2_DUE)
        self.assertEqual(res_day5["touch_number"], 3)
        self.assertTrue(res_day5["send_permitted"])

        # Record Follow-up 2 sent
        self.state.followup_2_sent_at = day5.isoformat()

        # Day 8 (Sept 8): WAITING_FOLLOWUP_3
        day8 = self.base_time + timedelta(days=7)
        res_day8 = self.engine.evaluate_cadence_stage(self.state, current_time=day8)
        self.assertEqual(res_day8["stage"], "WAITING_FOLLOWUP_3")
        self.assertFalse(res_day8["send_permitted"])

        # 4. Day 11 (Sept 11 10:00 IST): Follow-up 3 Due
        day11 = self.base_time + timedelta(days=10)
        res_day11 = self.engine.evaluate_cadence_stage(self.state, current_time=day11)
        self.assertEqual(res_day11["stage"], STATE_FOLLOWUP_3_DUE)
        self.assertEqual(res_day11["touch_number"], 4)
        self.assertTrue(res_day11["send_permitted"])

        # Record Follow-up 3 sent
        self.state.followup_3_sent_at = day11.isoformat()

        # Day 15: WAITING_FINAL_FOLLOWUP
        day15 = self.base_time + timedelta(days=14)
        res_day15 = self.engine.evaluate_cadence_stage(self.state, current_time=day15)
        self.assertEqual(res_day15["stage"], "WAITING_FINAL_FOLLOWUP")
        self.assertFalse(res_day15["send_permitted"])

        # 5. Day 21 (Sept 21 10:00 IST): Final Follow-up Due
        day21 = self.base_time + timedelta(days=20)
        res_day21 = self.engine.evaluate_cadence_stage(self.state, current_time=day21)
        self.assertEqual(res_day21["stage"], STATE_FINAL_FOLLOWUP_DUE)
        self.assertEqual(res_day21["touch_number"], 5)
        self.assertTrue(res_day21["send_permitted"])

        # Record Final Follow-up sent
        self.state.final_followup_sent_at = day21.isoformat()

        # Day 22+: Sequence MUST terminate permanently
        day22 = self.base_time + timedelta(days=21)
        res_day22 = self.engine.evaluate_cadence_stage(self.state, current_time=day22)
        self.assertEqual(res_day22["stage"], STATE_STOPPED)
        self.assertFalse(res_day22["send_permitted"])
        self.assertIn("5-touch cadence finished", res_day22["reason"])

    def test_reply_after_day1_cancels_all_subsequent_touches(self):
        """Inbound reply on Day 2 immediately cancels Touch 2, 3, 4, 5."""
        reply_time = self.base_time + timedelta(days=1)
        self.engine.handle_reply_or_event(self.state, classification="INTERESTED", event_time=reply_time)
        self.assertTrue(self.state.has_replied)
        self.assertEqual(self.state.status, STATE_REPLIED)

        # Checking at Day 3, 5, 11, 21: All must be stopped
        for days in (2, 4, 10, 20):
            t = self.base_time + timedelta(days=days)
            res = self.engine.evaluate_cadence_stage(self.state, current_time=t)
            self.assertEqual(res["stage"], STATE_REPLIED)
            self.assertFalse(res["send_permitted"])

    def test_reply_after_day3_cancels_touch3_4_5(self):
        """Follow-up 1 sent on Day 3; reply on Day 4 cancels Days 5, 11, 21."""
        self.state.followup_1_sent_at = (self.base_time + timedelta(days=2)).isoformat()
        reply_time = self.base_time + timedelta(days=3)
        self.engine.handle_reply_or_event(self.state, classification="EXISTING_VENDOR", event_time=reply_time)

        res_day5 = self.engine.evaluate_cadence_stage(self.state, current_time=self.base_time + timedelta(days=4))
        self.assertEqual(res_day5["stage"], STATE_REPLIED)
        self.assertFalse(res_day5["send_permitted"])

    def test_reply_after_day5_cancels_touch4_5(self):
        """Follow-up 2 sent on Day 5; reply on Day 7 cancels Days 11, 21."""
        self.state.followup_1_sent_at = (self.base_time + timedelta(days=2)).isoformat()
        self.state.followup_2_sent_at = (self.base_time + timedelta(days=4)).isoformat()
        self.engine.handle_reply_or_event(self.state, classification="NO_CURRENT_REQUIREMENT", event_time=self.base_time + timedelta(days=6))

        res_day11 = self.engine.evaluate_cadence_stage(self.state, current_time=self.base_time + timedelta(days=10))
        self.assertEqual(res_day11["stage"], STATE_REPLIED)
        self.assertFalse(res_day11["send_permitted"])

    def test_reply_after_day11_cancels_day21(self):
        """Follow-up 3 sent on Day 11; reply on Day 14 cancels Day 21."""
        self.state.followup_1_sent_at = (self.base_time + timedelta(days=2)).isoformat()
        self.state.followup_2_sent_at = (self.base_time + timedelta(days=4)).isoformat()
        self.state.followup_3_sent_at = (self.base_time + timedelta(days=10)).isoformat()
        self.engine.handle_reply_or_event(self.state, classification="WRONG_PERSON", event_time=self.base_time + timedelta(days=13))

        res_day21 = self.engine.evaluate_cadence_stage(self.state, current_time=self.base_time + timedelta(days=20))
        self.assertEqual(res_day21["stage"], STATE_REPLIED)
        self.assertFalse(res_day21["send_permitted"])

    def test_stop_on_bounce_and_opt_out(self):
        """Bounce and Unsubscribe permanently halt cadence."""
        # Bounce test
        state_bounce = self.engine.initialize_cadence(
            "b-1", "Aarti", "Dahej", "Rajesh", "bad@aarti.com", self.base_time, "<msg-b@oorja.local>", "Test"
        )
        self.engine.handle_reply_or_event(state_bounce, classification="BOUNCE")
        self.assertEqual(state_bounce.status, STATE_BOUNCED)
        res_b = self.engine.evaluate_cadence_stage(state_bounce, current_time=self.base_time + timedelta(days=5))
        self.assertEqual(res_b["stage"], STATE_BOUNCED)
        self.assertFalse(res_b["send_permitted"])

        # Opt-out test
        state_opt = self.engine.initialize_cadence(
            "o-1", "Bharat", "Chakan", "Amit", "amit@bf.com", self.base_time, "<msg-o@oorja.local>", "Test"
        )
        self.engine.handle_reply_or_event(state_opt, classification="UNSUBSCRIBE")
        self.assertEqual(state_opt.status, STATE_OPTED_OUT)
        res_o = self.engine.evaluate_cadence_stage(state_opt, current_time=self.base_time + timedelta(days=5))
        self.assertEqual(res_o["stage"], STATE_OPTED_OUT)
        self.assertFalse(res_o["send_permitted"])

    def test_stop_on_superseded_lead(self):
        """Superseded lead cannot receive follow-up."""
        self.state.is_superseded = True
        res = self.engine.evaluate_cadence_stage(self.state, current_time=self.base_time + timedelta(days=3))
        self.assertEqual(res["stage"], STATE_STOPPED)
        self.assertFalse(res["send_permitted"])
        self.assertIn("superseded", res["reason"])

    def test_ooo_rescheduling_behavior(self):
        """Out-of-office autoreply pauses cadence until detected return date rather than terminating."""
        ooo_text = "Thank you for your email. I am away from office on annual leave and will return on September 15, 2026."
        self.engine.handle_reply_or_event(self.state, classification="OUT_OF_OFFICE", event_time=self.base_time + timedelta(days=2), reply_body=ooo_text)

        self.assertEqual(self.state.status, STATE_OOO_PAUSED)
        self.assertIsNotNone(self.state.ooo_return_date)

        # Before return date (e.g. Sept 10): paused
        eval_before = self.engine.evaluate_cadence_stage(self.state, current_time=datetime(2026, 9, 10, 10, 0, tzinfo=KOLKATA_TZ))
        self.assertEqual(eval_before["stage"], STATE_OOO_PAUSED)
        self.assertFalse(eval_before["send_permitted"])

        # After return date (Sept 16): resumes evaluation
        eval_after = self.engine.evaluate_cadence_stage(self.state, current_time=datetime(2026, 9, 16, 10, 0, tzinfo=KOLKATA_TZ))
        self.assertTrue(eval_after["send_permitted"])
        self.assertEqual(eval_after["stage"], STATE_FOLLOWUP_1_DUE)

    def test_idempotency_restart_protection(self):
        """Verify duplicate touch cannot be sent after restart."""
        # Touch 2 already sent
        self.state.followup_1_sent_at = (self.base_time + timedelta(days=2)).isoformat()
        can_send_f1, reason_f1 = self.engine.verify_send_idempotency(self.state, touch_number=2)
        self.assertFalse(can_send_f1)
        self.assertIn("already sent", reason_f1)

        # Touch 3 not yet sent -> allowed
        can_send_f2, _ = self.engine.verify_send_idempotency(self.state, touch_number=3)
        self.assertTrue(can_send_f2)

        # Idempotency store match
        store = {f"{self.state.record_id}:{self.state.thread_info.campaign_id}:3": True}
        can_send_f2_dup, reason_store = self.engine.verify_send_idempotency(self.state, touch_number=3, executed_touches_store=store)
        self.assertFalse(can_send_f2_dup)
        self.assertIn("already executed", reason_store)

    def test_same_thread_copy_and_headers_preservation(self):
        """All follow-ups maintain Re: subject, In-Reply-To, References, and consultative copy."""
        candidate = {
            "company": "Varroc Engineering Ltd",
            "facility": "Chakan MIDC Vendor Park Campus",
            "city": "Pune",
            "contact_name": "Anil Patil",
            "first_name": "Anil",
            "email": "anil.patil@varroc.com",
            "calibration_opportunity": "CMM & Dimensional Testing Rig Calibration",
        }

        # Touch 2 (Follow-up 1)
        fu1 = self.engine.generate_follow_up_copy(candidate, "FOLLOW_UP_1", self.state.thread_info)
        self.assertTrue(fu1["subject"].startswith("Re:"))
        self.assertEqual(fu1["threading_headers"]["In-Reply-To"], self.state.thread_info.original_message_id)
        self.assertIn("CC-3963", fu1["body_text"])
        self.assertIn("Chakan", fu1["body_text"])

        # Touch 3 (Follow-up 2)
        fu2 = self.engine.generate_follow_up_copy(candidate, "FOLLOW_UP_2", self.state.thread_info)
        self.assertTrue(fu2["subject"].startswith("Re:"))
        self.assertIn("Coordinate Measuring Machines", fu2["body_text"])
        self.assertIn("0–1200 mm", fu2["body_text"])
        self.assertIn("Torque Wrenches", fu2["body_text"])

        # Touch 4 (Follow-up 3)
        fu3 = self.engine.generate_follow_up_copy(candidate, "FOLLOW_UP_3", self.state.thread_info)
        self.assertTrue(fu3["subject"].startswith("Re:"))
        self.assertIn("existing AMC", fu3["body_text"])
        self.assertIn("guide me to the appropriate person", fu3["body_text"])

        # Touch 5 (Final Follow-up)
        fu5 = self.engine.generate_follow_up_copy(candidate, "FINAL_FOLLOWUP", self.state.thread_info)
        self.assertTrue(fu5["subject"].startswith("Re:"))
        self.assertIn("close the loop after this note", fu5["body_text"])
        self.assertIn("referral would be greatly appreciated", fu5["body_text"])

    def test_reactivation_after_final_followup_on_new_trigger(self):
        """New trigger reactivates a stopped cadence."""
        self.state.final_followup_sent_at = (self.base_time + timedelta(days=20)).isoformat()
        self.state.status = STATE_STOPPED

        # New capex trigger announced
        self.engine.reactivate_with_new_trigger(
            self.state,
            new_trigger_event="Varroc Chakan Phase-4 EV Inverter Production Capex",
            new_trigger_date="2026-10-01",
        )
        self.assertEqual(self.state.status, CADENCE_REACTIVATED)
        eval_res = self.engine.evaluate_cadence_stage(self.state)
        self.assertEqual(eval_res["stage"], CADENCE_REACTIVATED)
        self.assertTrue(eval_res["send_permitted"])


if __name__ == "__main__":
    unittest.main()
