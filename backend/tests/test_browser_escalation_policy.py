"""Tests for Browser Escalation Policy — DeerFlow deep-browser decision criteria.

Validates:
1. JS-rendered empty pages trigger escalation.
2. CAPTCHA/login walls trigger MANUAL_BROWSER_ACTION_REQUIRED (not DeerFlow).
3. Pages with sufficient content do NOT trigger escalation.
4. Missing facility/person evidence triggers escalation for appropriate content types.
5. Escalation tracker records and summarizes correctly.
6. Manual action queue works correctly.
"""
import unittest

from services.browser_escalation_policy import (
    BrowserEscalationTracker,
    EscalationReason,
    EscalationRecord,
    evaluate_escalation_need,
)


class TestBrowserEscalationPolicy(unittest.TestCase):

    def test_js_empty_page_triggers_escalation(self):
        """JS-rendered page with < MIN_USEFUL_TEXT_LENGTH triggers escalation."""
        decision = evaluate_escalation_need(
            company="Bharat Forge",
            url="https://www.bharatforge.com/facilities",
            crawl4ai_text="Loading...",
            crawl4ai_status="SUCCESS",
            page_has_js_framework=True,
        )
        self.assertTrue(decision.should_escalate)
        self.assertEqual(decision.reason, EscalationReason.JS_RENDERED_EMPTY)

    def test_crawl4ai_failed_triggers_escalation(self):
        """Crawl4AI failure with JS framework triggers escalation."""
        decision = evaluate_escalation_need(
            company="Suzlon Energy",
            url="https://www.suzlon.com/plants",
            crawl4ai_text="",
            crawl4ai_status="FAILED",
            page_has_js_framework=True,
        )
        self.assertTrue(decision.should_escalate)
        self.assertEqual(decision.reason, EscalationReason.JS_RENDERED_EMPTY)

    def test_captcha_wall_requires_manual_action(self):
        """CAPTCHA detection must NOT escalate to DeerFlow — needs manual action."""
        decision = evaluate_escalation_need(
            company="Tata Motors",
            url="https://careers.tatamotors.com",
            crawl4ai_text="Please verify you are human before proceeding. Complete the CAPTCHA below.",
            crawl4ai_status="SUCCESS",
        )
        self.assertFalse(decision.should_escalate)
        self.assertEqual(decision.reason, EscalationReason.CAPTCHA_OR_LOGIN_WALL)
        self.assertTrue(decision.requires_manual_action)
        self.assertEqual(decision.manual_action_type, "MANUAL_BROWSER_ACTION_REQUIRED")

    def test_sufficient_content_no_escalation(self):
        """Page with sufficient text and relevant keywords should NOT trigger escalation."""
        good_text = (
            "Bharat Forge Limited operates multiple manufacturing plants across India. "
            "The Pune plant facility houses advanced CNC machining centers and quality laboratories. "
            "Plant Head: Rajesh Kumar, General Manager Operations, oversees all production lines. "
            "The facility is ISO 9001:2015 certified with annual calibration schedules maintained by the quality manager."
        )
        decision = evaluate_escalation_need(
            company="Bharat Forge",
            url="https://www.bharatforge.com/about-us",
            crawl4ai_text=good_text,
            crawl4ai_status="SUCCESS",
            expected_content="facility_and_person",
        )
        self.assertFalse(decision.should_escalate)
        self.assertIsNone(decision.reason)

    def test_missing_facility_person_triggers_escalation(self):
        """Page with text but no facility/person keywords triggers escalation."""
        investor_text = (
            "Annual Report 2025-26. Revenue grew 15% year-over-year. "
            "EBITDA margin expanded to 23.4%. Dividend of Rs 5 per share declared. "
            "Quarterly results available online. Investor presentation uploaded to BSE portal. "
            "Stock price gained 12%. Net profit increased 22%. Order book at all-time high."
        )
        decision = evaluate_escalation_need(
            company="Dynamatic Technologies",
            url="https://www.dynamatic.com/investors",
            crawl4ai_text=investor_text,
            crawl4ai_status="SUCCESS",
            expected_content="facility_and_person",
        )
        self.assertTrue(decision.should_escalate)
        self.assertEqual(decision.reason, EscalationReason.CRITICAL_CONTENT_MISSING)

    def test_escalation_tracker_records_and_summarizes(self):
        """Tracker accurately records escalations and produces summary."""
        tracker = BrowserEscalationTracker()
        tracker.record_escalation(EscalationRecord(
            company="TestCo",
            url="https://testco.com",
            reason=EscalationReason.JS_RENDERED_EMPTY,
            deerflow_success=True,
            deerflow_latency_ms=1200,
            deerflow_text_length=500,
        ))
        tracker.record_escalation(EscalationRecord(
            company="TestCo2",
            url="https://testco2.com",
            reason=EscalationReason.CRITICAL_CONTENT_MISSING,
            deerflow_success=False,
            deerflow_latency_ms=3000,
            error="Timeout",
        ))

        summary = tracker.get_summary()
        self.assertEqual(summary["total_escalations"], 2)
        self.assertEqual(summary["successful"], 1)
        self.assertEqual(summary["failed"], 1)
        self.assertEqual(summary["reason_distribution"]["JS_RENDERED_EMPTY"], 1)
        self.assertEqual(summary["reason_distribution"]["CRITICAL_CONTENT_MISSING"], 1)

    def test_manual_action_queue(self):
        """Manual action items are tracked correctly."""
        tracker = BrowserEscalationTracker()
        entry = tracker.add_manual_action_required(
            company="Maruti Suzuki",
            url="https://careers.marutisuzuki.com",
            reason="CAPTCHA wall detected",
            task_id="task-123",
            resume_point="person_search",
        )
        self.assertEqual(entry["status"], "MANUAL_BROWSER_ACTION_REQUIRED")
        self.assertEqual(len(tracker.manual_queue), 1)
        self.assertEqual(tracker.manual_queue[0]["company"], "Maruti Suzuki")

    def test_careers_search_interface_triggers_escalation(self):
        """Careers search page with minimal content triggers escalation."""
        careers_text = "Search jobs at our company. Apply now. Filter by job category."
        decision = evaluate_escalation_need(
            company="Uno Minda",
            url="https://www.unominda.com/careers",
            crawl4ai_text=careers_text,
            crawl4ai_status="SUCCESS",
            expected_content="careers",
        )
        self.assertTrue(decision.should_escalate)
        self.assertEqual(decision.reason, EscalationReason.CAREERS_SEARCH_INTERFACE)


if __name__ == "__main__":
    unittest.main()
