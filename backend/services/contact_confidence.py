"""Free, passive contact assessment. DNS never proves mailbox ownership/delivery.

Results are persisted in the existing candidate evidence JSON by the caller.
No SMTP probes, email sends, or external verifier/provider calls are performed.
"""
import re
import time
from datetime import datetime, timezone
from urllib.parse import urlparse
from services.email_validator import EMAIL_REGEX, ROLE_PREFIXES, ALL_DISPOSABLE_DOMAINS, check_mx_records

STATUSES = {'VERIFIED', 'PUBLICLY_FOUND', 'PROBABLE', 'INFERRED', 'UNVERIFIED', 'NOT_FOUND'}
_DNS_CACHE = {}


def stamp():
    return datetime.now(timezone.utc).isoformat()


def domain_name(value):
    host = urlparse(value if '://' in (value or '') else 'https://' + (value or '')).hostname or ''
    return host.lower().removeprefix('www.')


def passive_dns(domain):
    cached = _DNS_CACHE.get(domain)
    if cached and cached[0] > time.monotonic():
        return cached[1]
    result = check_mx_records(domain)
    if len(_DNS_CACHE) >= 1024:
        _DNS_CACHE.clear()
    _DNS_CACHE[domain] = (time.monotonic() + (3600 if result[0] else 60), result)
    return result


def assess_email(email, origin='UNVERIFIED', evidence=None, apollo_used=False, dns_check=passive_dns):
    clean = (email or '').strip().lower()
    result = dict(email=clean or None, status='NOT_FOUND' if not clean else 'UNVERIFIED',
                  evidence=evidence or [], verification_method='NONE', confidence=0.0,
                  checked_at=stamp(), apollo_used=bool(apollo_used), mailbox_verified=False)
    if not clean:
        return result
    if len(clean) > 254 or not EMAIL_REGEX.fullmatch(clean):
        return dict(result, reason='Invalid syntax', syntax_valid=False)
    local, domain = clean.rsplit('@', 1)
    if domain in ALL_DISPOSABLE_DOMAINS or domain in {'example.com', 'example.org', 'example.net'} or domain.endswith(('.invalid', '.test')):
        return dict(result, reason='Disposable or reserved test domain', syntax_valid=False)
    active, hosts, reason = dns_check(domain)
    result.update(syntax_valid=True, has_mx_records=active, mx_hosts=hosts,
                  is_role_account=local in ROLE_PREFIXES, verification_method='SYNTAX_AND_DNS', reason=reason)
    # A timeout or absent DNS is not proof that a mailbox does not exist.
    if not active:
        return result
    if origin == 'PUBLICLY_FOUND' and evidence:
        result.update(status='PUBLICLY_FOUND', confidence=0.7)
    elif origin == 'INFERRED':
        result.update(status='INFERRED', confidence=0.35)
    elif origin == 'PROBABLE':
        result.update(status='PROBABLE', confidence=0.5)
    else:
        result.update(confidence=0.3)
    return result


def name_patterns(name):
    words = re.findall(r'[a-z]+', (name or '').lower())
    if len(words) < 2:
        return {}
    first, last = words[0], words[-1]
    return {'first.last': first+'.'+last, 'firstlast': first+last,
            'flast': first[0]+last, 'firstl': first+last[0], 'first_last': first+'_'+last}


def infer_emails(name, domain, known_contacts):
    """Only infer patterns observed on named, sourced contacts at this exact domain."""
    domain = domain_name(domain)
    support = {}
    for item in known_contacts:
        email = (item.get('email') or '').lower()
        if not item.get('source') or item.get('status') not in ('VERIFIED', 'PUBLICLY_FOUND'):
            continue
        if not email.endswith('@'+domain):
            continue
        for pattern, local in name_patterns(item.get('name')).items():
            if email == local+'@'+domain:
                support.setdefault(pattern, []).append(item)
    patterns = name_patterns(name)
    return [{'email': patterns[p]+'@'+domain, 'pattern': p, 'evidence': support[p]}
            for p in sorted(support, key=lambda p: -len(support[p])) if p in patterns][:2]


def discover_email(name, domain, public_evidence, known_contacts=(), dns_check=passive_dns):
    """Require explicit same-line name/email association; generic page mail stays separate."""
    domain = domain_name(domain)
    for item in public_evidence:
        url = item.get('url', '')
        if not url.startswith(('http://', 'https://')) or item.get('is_mock'):
            continue
        # Only short structured blocks; page-wide occurrence of a name is insufficient.
        for line in (item.get('snippet') or '').splitlines():
            if len(line) > 500 or not re.search(r'(?<!\w)'+re.escape(name or '')+r'(?!\w)', line, re.I) or not name:
                continue
            addresses = set(re.findall(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', line))
            if len(addresses) != 1:
                continue
            email = addresses.pop().lower()
            if email.rsplit('@', 1)[-1] != domain or email.split('@')[0] in ROLE_PREFIXES:
                continue
            return assess_email(email, 'PUBLICLY_FOUND', [{'url': url, 'snippet': line, 'retrieved_at': item.get('retrieved_at')}], dns_check=dns_check)
    inferred = infer_emails(name, domain, known_contacts)
    if inferred:
        result = assess_email(inferred[0]['email'], 'INFERRED', inferred[0]['evidence'], dns_check=dns_check)
        result.update(pattern=inferred[0]['pattern'], alternatives=inferred[1:])
        return result
    return assess_email(None, dns_check=dns_check)


def phone_decision(icp_score, person_verified, existing_phone=None, phone_kind=None,
                   high_intent_evidence=None, apollo_allowed=False):
    high_value = float(icp_score or 0) >= 95 or bool(high_intent_evidence)
    direct = bool(existing_phone and phone_kind in ('PERSONAL_MOBILE', 'DIRECT'))
    allowed = bool(high_value and person_verified and not direct and apollo_allowed)
    return {'required': high_value, 'existing_direct': direct, 'apollo_allowed': allowed,
            'status': 'REUSE' if direct else ('PUBLIC_RESEARCH_FIRST' if high_value else 'NOT_PRIORITIZED'),
            'reason': 'Paid lookup requires a verified person, high value, explicit permission and unresolved direct phone.',
            'checked_at': stamp()}


def classify_phone_number(phone_str, context_text=""):
    """Classify phone numbers as PERSONAL_MOBILE, DIRECT, SWITCHBOARD, RECEPTION, or OFFICE."""
    clean = re.sub(r'[\s\-\(\)\.]', '', phone_str or '')
    if clean.startswith('+91'):
        clean = clean[3:]
    elif clean.startswith('91') and len(clean) == 12:
        clean = clean[2:]
    elif clean.startswith('0') and len(clean) == 11 and clean[1] in '6789':
        clean = clean[1:]

    ctx = (context_text or '').lower()
    is_switchboard = bool(re.search(r'\b(switchboard|board\s*line|board\s*no|reception|front\s*desk|general|operator|ivrs|helpdesk)\b', ctx))
    is_toll_free = clean.startswith(('1800', '1860'))

    if is_toll_free:
        return {'phone': phone_str, 'clean_phone': clean, 'phone_type': 'SWITCHBOARD',
                'is_direct_mobile': False, 'confidence': 0.8, 'reason': 'Toll-free corporate line'}

    if is_switchboard:
        return {'phone': phone_str, 'clean_phone': clean, 'phone_type': 'SWITCHBOARD',
                'is_direct_mobile': False, 'confidence': 0.7, 'reason': 'Context indicates switchboard or general desk'}

    # 10 digit starting with 6, 7, 8, 9 is Indian mobile
    if len(clean) == 10 and clean[0] in '6789':
        return {'phone': phone_str, 'clean_phone': clean, 'phone_type': 'PERSONAL_MOBILE',
                'is_direct_mobile': True, 'confidence': 0.85, 'reason': 'Verified Indian mobile format'}

    # Landlines / fixed line formats
    if clean.startswith('0') or len(clean) in (8, 10, 11):
        ptype = 'DIRECT' if re.search(r'\b(direct|ext|desk)\b', ctx) else 'OFFICE'
        return {'phone': phone_str, 'clean_phone': clean, 'phone_type': ptype,
                'is_direct_mobile': False, 'confidence': 0.6, 'reason': f'Corporate fixed line ({ptype})'}

    return {'phone': phone_str, 'clean_phone': clean, 'phone_type': 'UNKNOWN',
            'is_direct_mobile': False, 'confidence': 0.3, 'reason': 'Unrecognized phone pattern'}


def discover_person_phone(name, public_evidence):
    """Scan public evidence for phone numbers associated on the same line/block with the person."""
    if not name:
        return None
    for item in public_evidence:
        url = item.get('url', '')
        if not url.startswith(('http://', 'https://')) or item.get('is_mock'):
            continue
        for line in (item.get('snippet') or '').splitlines():
            if len(line) > 500 or not re.search(r'(?<!\w)' + re.escape(name) + r'(?!\w)', line, re.I):
                continue
            phones = re.findall(r'(?:\+91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}|\b0\d{2,4}[\s-]?\d{6,8}\b', line)
            if phones:
                classified = classify_phone_number(phones[0], line)
                classified.update(source='public_evidence', evidence_url=url, retrieved_at=item.get('retrieved_at') or stamp())
                return classified
    return None


def enrich_candidate_phone(candidate, company, public_evidence, apollo_allowed=False, apollo_lookup_fn=None):
    """Selectively enrich phone numbers adhering strictly to priority & privacy rules."""
    existing = [e for e in (candidate.evidence_sources or []) if e.get('type') == 'phone_assessment']
    if existing:
        try:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(existing[-1]['timestamp'])).total_seconds()
            if 0 <= age < 86400 and existing[-1].get('phone') == candidate.apollo_phone and (existing[-1].get('phone') or bool(existing[-1].get('apollo_used')) == bool(apollo_allowed)):
                return existing[-1]
        except (ValueError, KeyError, TypeError):
            pass

    # Evaluate phone decision gate
    is_verified_person = candidate.verification_status in ('VERIFIED_PERSON', 'PERSON_PUBLICLY_VERIFIED')
    current_phone = candidate.apollo_phone
    current_kind = classify_phone_number(current_phone)['phone_type'] if current_phone else 'UNKNOWN'

    decision = phone_decision(
        icp_score=company.icp_score,
        person_verified=is_verified_person,
        existing_phone=current_phone,
        phone_kind=current_kind,
        apollo_allowed=apollo_allowed,
    )

    phone_record = {
        'type': 'phone_assessment',
        'phone': current_phone,
        'phone_type': current_kind,
        'source': 'existing' if current_phone else 'none',
        'evidence_url': None,
        'confidence': 0.0,
        'timestamp': stamp(),
        'apollo_used': False,
        'provider_credits_consumed': 0,
        'decision': decision,
        'status': 'EXISTING_DIRECT' if decision.get('existing_direct') else 'NOT_FOUND',
    }

    # If already direct, do not look up
    if decision.get('existing_direct'):
        return phone_record

    # Free / public research first
    public_phone = discover_person_phone(candidate.candidate_name, public_evidence)
    if public_phone:
        phone_record.update({
            'phone': public_phone['phone'],
            'phone_type': public_phone['phone_type'],
            'source': 'public_evidence',
            'evidence_url': public_phone.get('evidence_url'),
            'confidence': public_phone['confidence'],
            'apollo_used': False,
            'provider_credits_consumed': 0,
            'status': 'PUBLICLY_FOUND',
        })
        if public_phone['is_direct_mobile']:
            candidate.apollo_phone = public_phone['phone']
        candidate.evidence_sources = [e for e in (candidate.evidence_sources or []) if e.get('type') != 'phone_assessment'] + [phone_record]
        return phone_record

    # Paid Apollo lookup only when allowed by the phone gate
    if decision.get('apollo_allowed') and apollo_lookup_fn:
        apollo_res = apollo_lookup_fn(candidate.candidate_name, company.name, candidate.candidate_title)
        raw_phone = apollo_res.get('phone') if isinstance(apollo_res, dict) else None
        if raw_phone:
            classified = classify_phone_number(raw_phone, 'Apollo enriched')
            credits = 1 if apollo_res.get('status') == 'ENRICHED' and not apollo_res.get('mock_mode') else 0
            phone_record.update({
                'phone': raw_phone,
                'phone_type': classified['phone_type'],
                'source': 'apollo',
                'evidence_url': 'https://api.apollo.io/v1/people/match',
                'confidence': 0.8 if classified['is_direct_mobile'] else 0.5,
                'apollo_used': True,
                'provider_credits_consumed': credits,
                'status': 'APOLLO_ENRICHED',
            })
            if classified['is_direct_mobile']:
                candidate.apollo_phone = raw_phone
        else:
            phone_record.update({
                'status': 'APOLLO_NO_RESULT',
                'apollo_used': True,
                'provider_credits_consumed': 0,
            })

    candidate.evidence_sources = [e for e in (candidate.evidence_sources or []) if e.get('type') != 'phone_assessment'] + [phone_record]
    return phone_record


def enrich_free_candidate(candidate, company, public_evidence, known_contacts=()):
    """Persist free assessment in existing JSON; inferred guesses never fill the contact field."""
    existing = [e for e in (candidate.evidence_sources or []) if e.get('type') == 'email_assessment']
    if existing:
        try:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(existing[-1]['checked_at'])).total_seconds()
            if 0 <= age < 86400 and (not candidate.apollo_email or existing[-1].get('email') == candidate.apollo_email.lower()) and bool(existing[-1].get('apollo_used')) == (candidate.apollo_enrichment_status == 'ENRICHED'):
                return existing[-1]
        except (ValueError, KeyError, TypeError):
            pass
    if candidate.apollo_email:
        result = assess_email(candidate.apollo_email, evidence=[], apollo_used=candidate.apollo_enrichment_status == 'ENRICHED')
    else:
        result = discover_email(candidate.candidate_name, company.domain or company.website,
                                public_evidence, known_contacts)
    result['type'] = 'email_assessment'
    candidate.evidence_sources = [e for e in (candidate.evidence_sources or []) if e.get('type') != 'email_assessment'] + [result]
    if result['status'] == 'PUBLICLY_FOUND' and not result.get('is_role_account'):
        candidate.apollo_email = result['email']  # Legacy shared contact column; provenance stays explicit.
        candidate.apollo_email_confidence = 'PUBLICLY_FOUND'
        candidate.email_status = 'EMAIL_FOUND'
    return result

