import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from services.restricted_inbox import collect_replies
from services.imap_service import poll_imap_inbox


class RestrictedInboxTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 10, 12, 0, 0, tzinfo=timezone.utc)

    def test_collect_replies_selects_inbox_readonly(self):
        mail = MagicMock()
        mail.uid.return_value = ('OK', [b''])
        collect_replies(mail, lambda h: False, lambda m: None, lambda mid: False, clock=self.now)
        mail.select.assert_called_once_with('INBOX', readonly=True)

    def test_collect_replies_does_not_fetch_body_if_header_does_not_match(self):
        mail = MagicMock()
        mail.uid.side_effect = [
            ('OK', [b'101']),
            ('OK', [
                (
                    b'101 (INTERNALDATE "10-Sep-2026 11:30:00 +0000" RFC822.SIZE 2048)',
                    b'From: stranger@unknown.com\r\nSubject: Hello\r\nMessage-ID: <msg-1@unknown.com>\r\n\r\n'
                )
            ]),
        ]
        match_fn = MagicMock(return_value=False)
        process_fn = MagicMock()
        already_seen = MagicMock(return_value=False)

        res = collect_replies(mail, match_fn, process_fn, already_seen, clock=self.now)
        self.assertEqual(res['status'], 'ok')
        self.assertEqual(res['messages_checked'], 1)
        self.assertEqual(res['skipped'], 1)
        self.assertEqual(res['processed_results'], [])
        # Only 2 uid calls: 'search' and 1 'fetch' for headers. No body fetch!
        self.assertEqual(mail.uid.call_count, 2)
        match_fn.assert_called_once()
        process_fn.assert_not_called()

    def test_collect_replies_fetches_body_only_after_matching(self):
        mail = MagicMock()
        mail.uid.side_effect = [
            ('OK', [b'102']),
            ('OK', [
                (
                    b'102 (INTERNALDATE "10-Sep-2026 11:45:00 +0000" RFC822.SIZE 1024)',
                    b'From: lead@target.com\r\nSubject: Re: Calibration Quote\r\nMessage-ID: <rep-102@target.com>\r\nIn-Reply-To: <orig-1@oorja.ai>\r\n\r\n'
                )
            ]),
            ('OK', [
                (
                    b'102 (BODY[] {50})',
                    b'From: lead@target.com\r\nSubject: Re: Calibration Quote\r\nMessage-ID: <rep-102@target.com>\r\n\r\nPlease send the revised quote for pressure gauges.'
                )
            ]),
        ]
        match_fn = MagicMock(return_value=True)
        process_fn = MagicMock(side_effect=lambda item: {'handled': item['message_id'], 'body': item['body']})
        already_seen = MagicMock(return_value=False)

        res = collect_replies(mail, match_fn, process_fn, already_seen, clock=self.now)
        self.assertEqual(res['status'], 'ok')
        self.assertEqual(res['messages_checked'], 1)
        self.assertEqual(res['skipped'], 0)
        self.assertEqual(len(res['processed_results']), 1)
        self.assertIn('pressure gauges', res['processed_results'][0]['body'])
        # 3 uid calls: search, fetch header, fetch body
        self.assertEqual(mail.uid.call_count, 3)
        self.assertIn('(BODY.PEEK[]<0.262144>)', mail.uid.call_args_list[2][0][2])

    def test_collect_replies_skips_already_seen_message(self):
        mail = MagicMock()
        mail.uid.side_effect = [
            ('OK', [b'103']),
            ('OK', [
                (
                    b'103 (INTERNALDATE "10-Sep-2026 11:00:00 +0000" RFC822.SIZE 1024)',
                    b'From: lead@target.com\r\nSubject: Re: Hi\r\nMessage-ID: <already-seen@target.com>\r\n\r\n'
                )
            ]),
        ]
        match_fn = MagicMock(return_value=True)
        process_fn = MagicMock()
        already_seen = MagicMock(return_value=True)

        res = collect_replies(mail, match_fn, process_fn, already_seen, clock=self.now)
        self.assertEqual(res['skipped'], 1)
        match_fn.assert_not_called()
        process_fn.assert_not_called()

    def test_collect_replies_skips_large_messages(self):
        mail = MagicMock()
        mail.uid.side_effect = [
            ('OK', [b'104']),
            ('OK', [
                (
                    b'104 (INTERNALDATE "10-Sep-2026 11:00:00 +0000" RFC822.SIZE 500000)',
                    b'From: lead@target.com\r\nSubject: Big\r\nMessage-ID: <big@target.com>\r\n\r\n'
                )
            ]),
        ]
        res = collect_replies(mail, lambda h: True, lambda m: None, lambda mid: False, clock=self.now)
        self.assertEqual(res['skipped'], 1)
        self.assertEqual(mail.uid.call_count, 2)

    def test_poll_imap_inbox_test_mode_safety(self):
        db = MagicMock()
        with patch('services.imap_service.settings') as mock_settings:
            mock_settings.IMAP_HOST = 'imap.rediffmailpro.com'
            mock_settings.OUTBOUND_TEST_MODE = True
            res = poll_imap_inbox(db, folder='INBOX')
            self.assertEqual(res['status'], 'test_mode')
            self.assertTrue(res['mock_mode'])
            self.assertEqual(res['messages_checked'], 0)

    def test_poll_imap_inbox_rejects_non_inbox_folder(self):
        db = MagicMock()
        res = poll_imap_inbox(db, folder='[Gmail]/All Mail')
        self.assertEqual(res['status'], 'error')


if __name__ == '__main__':
    unittest.main()
