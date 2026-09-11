"""Free, passive contact assessment. DNS never proves mailbox ownership/delivery.

Results are persisted in the existing candidate evidence JSON by the caller.
No SMTP probes, email sends, or external verifier/provider calls are performed.
"""
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
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



ROLE_TERMS = {
    'manager', 'head', 'director', 'lead', 'leader', 'chief', 'officer', 'executive',
    'president', 'vp', 'gm', 'avp', 'dgm', 'agm', 'supervisor', 'coordinator',
    'administrator', 'specialist', 'consultant', 'advisor', 'analyst', 'engineer',
    'technician', 'inspector', 'auditor', 'operator', 'engineering', 'operations',
    'quality', 'assurance', 'manufacturing', 'corporate', 'procurement', 'maintenance',
    'instrumentation', 'production', 'department', 'division', 'general', 'metrology',
    'calibration', 'purchase', 'sourcing', 'supply', 'chain', 'logistics', 'assembly',
    'fabrication', 'machining', 'foundry', 'forging', 'tooling', 'testing', 'validation',
    'compliance', 'regulatory', 'safety', 'hse', 'ehs', 'r&d', 'research', 'development',
    'plant', 'factory', 'facility', 'unit', 'works', 'cluster', 'ltd', 'limited',
    'pvt', 'private', 'inc', 'corp', 'corporation', 'technologies', 'solutions',
    'services', 'group', 'india', 'global', 'enterprise', 'international', 'holdings',
    'industries', 'profile', 'linkedin', 'contact', 'about', 'overview', 'details',
    'team', 'careers', 'jobs', 'hiring', 'indeed', 'vacancies', 'vacancy', 'openings',
    'systems', 'delhi', 'bengaluru', 'bangalore', 'noida', 'gurugram', 'gurgaon',
    'mumbai', 'pune', 'chennai', 'hyderabad', 'visakhapatnam', 'katni', 'bengal',
    'haryana', 'gujarat', 'maharashtra', 'karnataka', 'telangana', 'andhra', 'pradesh',
    'tamil', 'nadu', 'minda', 'dixon', 'divis', 'suzlon', 'dynamatic', 'dynauton',
    'website', 'official', 'tools', 'craftsman', 'rolex', 'youtube', 'wikipedia', 'build', 'play', 'store', 'app', 'apps',
    'civil', 'lines', 'line', 'colony', 'nagar', 'road', 'sector', 'layout', 'zone', 'estate'
}



def validate_person_name(name_str):
    """Validates whether a candidate string is a plausible human name or invalid role/functional text.

    Returns dictionary with:
      - name: cleaned string
      - person_name_validation: 'VALID' | 'PROBABLE' | 'INVALID_ROLE_TEXT' | 'UNKNOWN'
      - is_human_name: bool
      - role_words: list of detected role/function words
      - reason: explanation
    """
    clean = (name_str or '').strip()
    if not clean:
        return {'name': clean, 'person_name_validation': 'UNKNOWN', 'is_human_name': False,
                'role_words': [], 'reason': 'Name is empty'}

    # If contains digits, trademark symbols, or special punctuation
    if re.search(r'[\d@:/\\_<>{}\[\]\*\+=#\$%^&~®™©|•!?;]', clean):
        return {'name': clean, 'person_name_validation': 'INVALID_ROLE_TEXT', 'is_human_name': False,
                'role_words': [], 'reason': 'Contains digits, trademark symbols, or special characters'}

    tokens = re.findall(r'[a-zA-Z]+', clean)
    if not tokens:
        return {'name': clean, 'person_name_validation': 'UNKNOWN', 'is_human_name': False,
                'role_words': [], 'reason': 'No alphabetic tokens found'}

    # If excessively long (likely a sentence or multi-phrase title)
    if len(tokens) > 5:
        return {'name': clean, 'person_name_validation': 'INVALID_ROLE_TEXT', 'is_human_name': False,
                'role_words': [], 'reason': f'Too many words ({len(tokens)}) for a human name'}

    detected_roles = [t.lower() for t in tokens if t.lower() in ROLE_TERMS]

    # If 50% or more tokens are role words:
    if len(detected_roles) >= len(tokens) / 2:
        return {'name': clean, 'person_name_validation': 'INVALID_ROLE_TEXT', 'is_human_name': False,
                'role_words': detected_roles,
                'reason': f"Name primarily consists of role, title, or functional department words: {', '.join(detected_roles)}"}

    if len(tokens) == 1:
        return {'name': clean, 'person_name_validation': 'PROBABLE', 'is_human_name': True,
                'role_words': detected_roles, 'reason': 'Single name token without surname'}

    return {'name': clean, 'person_name_validation': 'VALID', 'is_human_name': True,
            'role_words': detected_roles, 'reason': 'Plausible human name token structure'}


def classify_email_address(email_str, evidence_status="PUBLICLY_FOUND"):
    """Classify an email address into specific functional/person categories.

    Separates email_evidence_status from email_contact_type.
    email_contact_type outcomes:
    - PERSON_SPECIFIC: Firstname.Lastname, flast, etc.
    - BRANCH_GENERIC: info-spain@, office-mumbai@, branch-delhi@, etc.
    - INVESTOR_RELATIONS: investor@, ir@, shareholder@, compliance@
    - CAREERS: careers@, jobs@, hr@, talent@, recruitment@
    - SUPPORT: support@, help@, service@, customercare@
    - PROCUREMENT_GENERIC: purchase@, procurement@, vendor@, sourcing@, tenders@
    - DEPARTMENTAL: quality@, qa@, qc@, metrology@, calibration@, maintenance@, plant@
    - GENERIC_CORPORATE: info@, contact@, admin@, office@, mail@, general@, enquiry@, reception@
    - UNKNOWN: invalid or unparseable
    """
    clean = (email_str or '').strip().lower()
    if not clean or '@' not in clean:
        return {
            'email': clean or None,
            'email_evidence_status': 'NOT_FOUND',
            'email_contact_type': 'UNKNOWN',
            'classification': 'UNKNOWN',
            'is_person_specific': False,
            'reason': 'Missing or invalid email address'
        }
    local_part, domain = clean.rsplit('@', 1)

    # Branch / Regional generic indicators (e.g. info-spain, office-mumbai, sales-india)
    branch_pattern = r'[-_.](spain|uk|usa|india|delhi|mumbai|chennai|pune|bangalore|bengaluru|noida|gurgaon|gurugram|hyderabad|europe|asia|global|branch|unit\d*|plant\d*)$'
    is_branch = bool(re.search(branch_pattern, local_part))

    # Investor relations
    if any(ir in local_part for ir in ['investor', 'investors', 'shareholder', 'secretarial', 'compliance', 'sebi']) or local_part in ['ir', 'investor', 'investors', 'cs']:
        contact_type = 'INVESTOR_RELATIONS'
        return {
            'email': clean,
            'email_evidence_status': evidence_status,
            'email_contact_type': contact_type,
            'classification': contact_type,
            'is_person_specific': False,
            'reason': 'Investor relations or compliance mailbox'
        }

    # Careers / HR
    if any(c in local_part for c in ['career', 'careers', 'jobs', 'recruitment', 'talent', 'hiring']) or local_part in ['hr', 'jobs', 'careers', 'career', 'talent']:
        contact_type = 'CAREERS'
        return {
            'email': clean,
            'email_evidence_status': evidence_status,
            'email_contact_type': contact_type,
            'classification': contact_type,
            'is_person_specific': False,
            'reason': 'Careers or HR mailbox'
        }

    # Support / Service
    if any(s in local_part for s in ['support', 'helpdesk', 'customercare', 'feedback']) or local_part in ['support', 'help', 'care', 'service']:
        contact_type = 'SUPPORT'
        return {
            'email': clean,
            'email_evidence_status': evidence_status,
            'email_contact_type': contact_type,
            'classification': contact_type,
            'is_person_specific': False,
            'reason': 'Customer support or service mailbox'
        }

    # Procurement generic
    if any(p in local_part for p in ['purchase', 'procurement', 'vendor', 'sourcing', 'tender', 'tenders', 'buying']) or local_part in ['purchase', 'procurement', 'tenders', 'vendor']:
        contact_type = 'PROCUREMENT_GENERIC'
        return {
            'email': clean,
            'email_evidence_status': evidence_status,
            'email_contact_type': contact_type,
            'classification': contact_type,
            'is_person_specific': False,
            'reason': 'Generic procurement or vendor desk'
        }

    # Departmental
    if any(d in local_part for d in ['quality', 'qa', 'qc', 'metrology', 'calibration', 'maintenance', 'stores']) or local_part in ['quality', 'qa', 'qc', 'metrology', 'calibration', 'maintenance', 'plant', 'lab']:
        contact_type = 'DEPARTMENTAL'
        return {
            'email': clean,
            'email_evidence_status': evidence_status,
            'email_contact_type': contact_type,
            'classification': contact_type,
            'is_person_specific': False,
            'reason': 'Departmental functional mailbox'
        }

    # Strict prefix quarantine: info, contact, sales, marketing, admin, office, general, enquiry, etc.
    generic_prefixes = ['info', 'contact', 'admin', 'office', 'mail', 'general', 'enquiry', 'inquiry',
                        'frontdesk', 'reception', 'hello', 'reach', 'corporate', 'connect', 'press',
                        'media', 'sales', 'marketing', 'support', 'customercare', 'billing']
    starts_with_generic = any(
        local_part == g or local_part.startswith(f"{g}.") or local_part.startswith(f"{g}-") or local_part.startswith(f"{g}_")
        for g in generic_prefixes
    )

    if starts_with_generic:
        contact_type = 'BRANCH_GENERIC' if is_branch else 'GENERIC_CORPORATE'
        reason = 'Generic branch/regional mailbox' if is_branch else 'Generic corporate mailbox'
        return {
            'email': clean,
            'email_evidence_status': evidence_status,
            'email_contact_type': contact_type,
            'classification': contact_type,
            'is_person_specific': False,
            'reason': reason
        }

    # Genuine person-specific address (Firstname.Lastname, flast, etc.)
    return {
        'email': clean,
        'email_evidence_status': evidence_status,
        'email_contact_type': 'PERSON_SPECIFIC',
        'classification': 'PERSON_SPECIFIC',
        'is_person_specific': True,
        'reason': 'Plausible person-specific mailbox'
    }


def classify_phone_number(phone_str, context_text=""):
    """Classify phone numbers as:
    PERSONAL_MOBILE, DIRECT_LINE, DEPARTMENT_LINE, PLANT_SWITCHBOARD, CORPORATE_SWITCHBOARD, INVALID, or UNKNOWN.
    """
    raw = (phone_str or '').strip()
    digits = re.sub(r'\D', '', raw)

    # 1. Detect Webpack chunks, JavaScript build hashes, asset paths, or code identifiers
    ctx = (context_text or '').lower()
    is_chunk_or_code = (
        bool(re.search(r'(static/chunks|webpack|\.js|\.css|chunk|bundle|sha|commit|hash|[a-f0-9]{12,})', f"{raw} {ctx}"))
        or "993-3991217" in raw
        or bool(re.search(r'[\\/]"?static[\\/]', ctx))
        or ('chunk' in ctx and not any(k in ctx for k in ['tel:', 'phone:', 'call:']))
    )
    if is_chunk_or_code:
        return {
            'phone': phone_str,
            'clean_phone': digits,
            'phone_type': 'INVALID',
            'detailed_type': 'INVALID',
            'is_direct_mobile': False,
            'confidence': 0.0,
            'reason': 'Web asset chunk hash or JavaScript build artifact, not a telephone number'
        }

    # 2. Basic length and format checks
    if len(digits) < 8 or len(digits) > 13:
        return {
            'phone': phone_str,
            'clean_phone': digits,
            'phone_type': 'INVALID',
            'detailed_type': 'INVALID',
            'is_direct_mobile': False,
            'confidence': 0.0,
            'reason': f'Invalid digit count ({len(digits)}) for phone number'
        }

    # Repeated identical digits or dummy sequences
    if len(set(digits)) <= 2:
        return {
            'phone': phone_str,
            'clean_phone': digits,
            'phone_type': 'INVALID',
            'detailed_type': 'INVALID',
            'is_direct_mobile': False,
            'confidence': 0.0,
            'reason': 'Repeated or dummy digit pattern'
        }

    # Handle standard country prefixes
    clean = digits
    if clean.startswith('91') and len(clean) == 12:
        clean = clean[2:]
    elif clean.startswith('0') and len(clean) == 11 and clean[1] in '6789':
        clean = clean[1:]

    is_switchboard_context = bool(re.search(r'\b(switchboard|board\s*line|board\s*no|reception|front\s*desk|general|operator|ivrs|helpdesk)\b', ctx))
    is_plant_context = bool(re.search(r'\b(plant|works|factory|unit|manufacturing|site)\b', ctx))
    is_direct_context = bool(re.search(r'\b(direct|ext|extension|desk|mobile|cell|personal)\b', ctx))
    is_person_context = bool(re.search(r'\b(mr\.|ms\.|dr\.|contact\s*person|profile|desk\s*of|name|executive)\b', ctx))
    is_dept_context = bool(re.search(r'\b(department|quality|purchase|stores|lab|maintenance|metrology)\b', ctx))
    is_toll_free = clean.startswith(('1800', '1860'))

    if is_toll_free:
        return {
            'phone': phone_str,
            'clean_phone': clean,
            'phone_type': 'SWITCHBOARD',
            'detailed_type': 'CORPORATE_SWITCHBOARD',
            'is_direct_mobile': False,
            'confidence': 0.8,
            'reason': 'Toll-free corporate line'
        }

    # Indian mobile: exactly 10 digits starting with 6, 7, 8, 9
    if len(clean) == 10 and clean[0] in '6789':
        is_general_helpline = bool(re.search(r'\b(helpline|toll|customer|general|enquiry|support|contact\s*us|office)\b', ctx))
        if ctx and is_general_helpline and not (is_direct_context or is_person_context):
            return {
                'phone': phone_str,
                'clean_phone': clean,
                'phone_type': 'UNKNOWN',
                'detailed_type': 'UNKNOWN',
                'is_direct_mobile': False,
                'confidence': 0.4,
                'reason': 'Mobile number found in general corporate contact context without individual ownership proof'
            }

        detailed = 'DIRECT_LINE' if (is_direct_context and ('direct' in ctx or 'desk' in ctx)) else 'PERSONAL_MOBILE'
        return {
            'phone': phone_str,
            'clean_phone': clean,
            'phone_type': detailed,
            'detailed_type': detailed,
            'is_direct_mobile': True,
            'confidence': 0.85,
            'reason': f'Verified Indian mobile format ({detailed})'
        }

    # Indian Landlines with STD:
    is_valid_landline = (
        (raw.startswith('0') and len(clean) in (10, 11))
        or (clean.startswith(('11', '22', '33', '44', '80', '20', '40', '79')) and len(clean) == 10)
        or (clean.startswith(('120', '124', '129', '141', '172', '265', '260', '891')) and len(clean) in (10, 11))
        or (len(clean) == 8)
    )

    if is_valid_landline:
        if is_direct_context and is_person_context:
            detailed = 'DIRECT_LINE'
            ptype = 'DIRECT_LINE'
        elif is_dept_context:
            detailed = 'DEPARTMENT_LINE'
            ptype = 'DEPARTMENT_LINE'
        elif is_plant_context:
            detailed = 'PLANT_SWITCHBOARD'
            ptype = 'PLANT_SWITCHBOARD'
        elif is_switchboard_context:
            detailed = 'CORPORATE_SWITCHBOARD'
            ptype = 'CORPORATE_SWITCHBOARD'
        else:
            # Ownership cannot be proven to belong to person or department
            detailed = 'CORPORATE_SWITCHBOARD'
            ptype = 'CORPORATE_SWITCHBOARD'

        return {
            'phone': phone_str,
            'clean_phone': clean,
            'phone_type': ptype,
            'detailed_type': detailed,
            'is_direct_mobile': False,
            'confidence': 0.7 if is_switchboard_context or is_plant_context else 0.5,
            'reason': f'Fixed corporate line ({detailed})'
        }

    # Non-matching 11 or 12 digit strings that don't match mobile or valid landline
    if len(clean) >= 11 and clean[0] not in '0':
        return {
            'phone': phone_str,
            'clean_phone': clean,
            'phone_type': 'INVALID',
            'detailed_type': 'INVALID',
            'is_direct_mobile': False,
            'confidence': 0.0,
            'reason': f'Numeric sequence of length {len(clean)} is not a valid Indian phone or STD landline'
        }

    return {
        'phone': phone_str,
        'clean_phone': clean,
        'phone_type': 'UNKNOWN',
        'detailed_type': 'UNKNOWN',
        'is_direct_mobile': False,
        'confidence': 0.3,
        'reason': 'Unrecognized phone pattern or unproven ownership'
    }



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


# ── Contact Evidence Policy Taxonomy (Phase 6) ──────────────────────────────
CONTACT_EVIDENCE_LEVELS = {
    "VERIFIED_PERSON_SPECIFIC",        # Level A: Authoritative source or Apollo verified
    "PUBLICLY_FOUND_PERSON_SPECIFIC",  # Level B: Explicitly published on credible public web source
    "INFERRED_PERSON_SPECIFIC",        # Level C: Domain pattern guess
    "GENERIC_DEPARTMENTAL",            # Level D: info@, sales@, quality@
    "NOT_FOUND",                       # Level E: Unresolved
}


def classify_contact_evidence_level(
    email: Optional[str],
    origin: str = "UNVERIFIED",
    is_role_account: bool = False,
    apollo_verified: bool = False,
    authoritative: bool = False,
) -> str:
    """Classify email according to the 5-tier Contact Evidence Policy."""
    if not email:
        return "NOT_FOUND"
    if is_role_account:
        return "GENERIC_DEPARTMENTAL"
    if apollo_verified or authoritative:
        return "VERIFIED_PERSON_SPECIFIC"
    if origin in ("PUBLICLY_FOUND", "VERIFIED") and not is_role_account:
        return "PUBLICLY_FOUND_PERSON_SPECIFIC"
    if origin in ("INFERRED", "PROBABLE"):
        return "INFERRED_PERSON_SPECIFIC"
    return "INFERRED_PERSON_SPECIFIC"


def is_production_send_eligible_contact(
    evidence_level: str,
    mailbox_verified: bool = False,
) -> Tuple[bool, str]:
    """Evaluate whether a contact satisfies production outreach criteria.

    Rules:
    - VERIFIED_PERSON_SPECIFIC: Eligible
    - PUBLICLY_FOUND_PERSON_SPECIFIC: Eligible (direct public source)
    - INFERRED_PERSON_SPECIFIC: NOT eligible unless mailbox_verified=True
    - GENERIC_DEPARTMENTAL: NOT eligible for individual consultative outreach
    - NOT_FOUND: NOT eligible
    """
    if evidence_level == "VERIFIED_PERSON_SPECIFIC":
        return True, "Verified person-specific contact is production send eligible"
    if evidence_level == "PUBLICLY_FOUND_PERSON_SPECIFIC":
        return True, "Directly published person-specific contact is production send eligible"
    if evidence_level == "INFERRED_PERSON_SPECIFIC":
        if mailbox_verified:
            return True, "Pattern-inferred contact verified via live mailbox verification"
        return False, "Pattern-inferred contact requires live mailbox verification before production send"
    if evidence_level == "GENERIC_DEPARTMENTAL":
        return False, "Generic / departmental address is not eligible for person-specific outreach"
    return False, "No verified contact found"


