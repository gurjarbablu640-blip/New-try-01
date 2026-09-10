"""Unit tests for reply processing, 12-category intent classification, and learning feedback."""

import os
import shutil
import tempfile
import unittest

from services.reply_processor import CANONICAL_CLASSIFICATIONS, ReplyProcessor


class TestReplyProcessor(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.processor = ReplyProcessor(storage_dir=self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_canonical_classifications_count(self):
        self.assertEqual(len(CANONICAL_CLASSIFICATIONS), 12)

    def test_classify_enquiry(self):
        packet = {
            "from": "rajesh.patel@maruti.co.in",
            "subject": "Re: Calibration support for Sanand facility",
            "body": "Hi, please send across your rate list and quotation for calibrating 15 micrometers and 4 pressure gauges under NABL scope.",
        }
        res = self.processor.classify_reply(packet)
        self.assertEqual(res.classification, "ENQUIRY")
        self.assertEqual(res.learning_signal, "POSITIVE")
        self.assertTrue(res.confidence >= 0.9)
        self.assertIn("quotation", res.evidence_snippet.lower())

    def test_classify_interested(self):
        packet = {
            "from": "vikram.mehta@tatamotors.com",
            "subject": "Re: Instrument Calibration Support",
            "body": "Thanks for writing. We are definitely interested in exploring on-site calibration. Can you schedule a meeting next Tuesday at 3 PM?",
        }
        res = self.processor.classify_reply(packet)
        self.assertEqual(res.classification, "INTERESTED")
        self.assertEqual(res.learning_signal, "POSITIVE")
        self.assertIn("meeting", res.evidence_snippet.lower())

    def test_classify_referral(self):
        packet = {
            "from": "s.sharma@bosch.com",
            "subject": "Re: Calibration partner for Jaipur unit",
            "body": "Hello, I am handling procurement now. Please contact Mr. Amit Verma (amit.verma@bosch.com) who leads our Quality Assurance department.",
        }
        res = self.processor.classify_reply(packet)
        self.assertEqual(res.classification, "REFERRAL")
        self.assertEqual(res.learning_signal, "POSITIVE")
        self.assertEqual(res.referral_person, "Amit Verma")
        self.assertEqual(res.referral_email, "amit.verma@bosch.com")

    def test_classify_future_requirement(self):
        packet = {
            "from": "plant.head@thermax.com",
            "subject": "Re: Annual calibration audit",
            "body": "All our gauges are currently calibrated. Please reach out in next quarter when our annual shutdown is scheduled.",
        }
        res = self.processor.classify_reply(packet)
        self.assertEqual(res.classification, "FUTURE_REQUIREMENT")
        self.assertEqual(res.learning_signal, "POSITIVE")
        self.assertEqual(res.timeline_mention, "next quarter")

    def test_classify_existing_vendor(self):
        packet = {
            "from": "qa@havells.com",
            "subject": "Re: Calibration Services",
            "body": "We already have an annual contract under AMC with an existing vendor for all electrical calibration.",
        }
        res = self.processor.classify_reply(packet)
        self.assertEqual(res.classification, "EXISTING_VENDOR")
        self.assertEqual(res.learning_signal, "NEGATIVE")

    def test_classify_wrong_person(self):
        packet = {
            "from": "k.nair@lnt.com",
            "subject": "Re: Metrology support",
            "body": "This is not my department. I handle civil logistics, so I am not involved in calibration of testing equipment.",
        }
        res = self.processor.classify_reply(packet)
        self.assertEqual(res.classification, "WRONG_PERSON")
        self.assertEqual(res.learning_signal, "NEGATIVE")

    def test_classify_bounce(self):
        packet = {
            "from": "mailer-daemon@googlemail.com",
            "subject": "Delivery Status Notification (Failure)",
            "body": "The response was: 550 user not found. Mail delivery failed.",
        }
        res = self.processor.classify_reply(packet)
        self.assertEqual(res.classification, "BOUNCE")
        self.assertEqual(res.learning_signal, "NEGATIVE")

    def test_classify_out_of_office(self):
        packet = {
            "from": "arun.kumar@mahindra.com",
            "subject": "Automatic reply: Out of office until Sept 20",
            "body": "I am away from office on annual leave and will have limited email access.",
        }
        res = self.processor.classify_reply(packet)
        self.assertEqual(res.classification, "OUT_OF_OFFICE")
        self.assertEqual(res.learning_signal, "NEUTRAL")
        self.assertFalse(res.feed_to_learning)

    def test_process_and_store_persists_record(self):
        packet = {
            "message_id": "<reply-test-999@domain.com>",
            "from": "deepak@tvs.in",
            "subject": "Re: Calibration request",
            "body": "Please send quotation for pressure calibration.",
        }
        res = self.processor.process_and_store(packet)
        self.assertEqual(res["status"], "classified")
        self.assertEqual(res["record"]["classification"], "ENQUIRY")
        self.assertTrue(os.path.exists(self.processor.history_file))


if __name__ == "__main__":
    unittest.main()
