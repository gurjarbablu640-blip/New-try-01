"""Header-first inbox collector. No body fetch until matched to real outreach."""
import email
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime


def collect_replies(mail, match_header, process, already_seen, limit=50, clock=None):
    now = clock or datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=24)
    mail.select('INBOX', readonly=True)
    status, data = mail.uid('search', None, 'SINCE', cutoff.strftime('%d-%b-%Y'))
    if status != 'OK':
        raise RuntimeError('IMAP header search failed')
    results, skipped = [], 0
    ids = (data[0] or b'').split()[-min(max(limit, 1), 100):]
    for uid in ids:
        status, parts = mail.uid('fetch', uid, '(INTERNALDATE RFC822.SIZE BODY.PEEK[HEADER.FIELDS (FROM SUBJECT MESSAGE-ID IN-REPLY-TO REFERENCES DATE)])')
        if status != 'OK':
            skipped += 1
            continue
        packets = [p for p in parts if isinstance(p, tuple)]
        if not packets:
            skipped += 1
            continue
        envelope, raw = packets[0]
        meta = envelope.decode('ascii', 'replace')
        date = re.search(r'INTERNALDATE "([^"]+)"', meta)
        size = re.search(r'RFC822.SIZE (\d+)', meta)
        if not date or not size or int(size[1]) > 262144:
            skipped += 1
            continue
        try:
            clean_date = re.sub(r'\s+', ' ', date[1].strip())
            received = datetime.strptime(clean_date, '%d-%b-%Y %H:%M:%S %z')
        except (ValueError, TypeError):
            skipped += 1
            continue
        if not cutoff <= received <= now:
            skipped += 1
            continue
        header = email.message_from_bytes(raw)
        message_id = header.get('Message-ID', '')
        if not message_id or already_seen(message_id) or not match_header(header):
            skipped += 1
            continue
        status, bodies = mail.uid('fetch', uid, '(BODY.PEEK[]<0.262144>)')
        if status != 'OK':
            skipped += 1
            continue
        for packet in bodies:
            if not isinstance(packet, tuple):
                continue
            msg = email.message_from_bytes(packet[1])
            body = ''
            for part in msg.walk():
                if part.get_content_type() == 'text/plain' and part.get_content_disposition() != 'attachment':
                    body = (part.get_payload(decode=True) or b'').decode(part.get_content_charset() or 'utf-8', errors='replace')
                    break
            results.append(process({'from': msg.get('From', ''), 'subject': msg.get('Subject', ''),
                'message_id': message_id, 'body': body,
                'headers': {k.lower(): v for k, v in header.items()}}))
            break
    return {'status': 'ok', 'messages_checked': len(ids), 'skipped': skipped, 'processed_results': results, 'mock_mode': False}
