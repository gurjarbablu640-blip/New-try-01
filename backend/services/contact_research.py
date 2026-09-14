"""Durable, bounded contact research. Never sends outreach."""
import csv
import io
import json
import logging
import traceback
import copy
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from database import SessionLocal
from models.company import Company
from models.decision_maker_candidate import DecisionMakerCandidate
from services.decision_maker_discovery import run_full_discovery_pipeline
from services.settings_manager import get_setting_value

ROOT = Path(__file__).resolve().parents[1] / 'data' / 'contact_research_runs'
LOCK = threading.RLock()
ACTIVE = None
INITIALIZED = False

def now():
    return datetime.now(timezone.utc).isoformat()

def save(run):
    ROOT.mkdir(parents=True, exist_ok=True)
    target = ROOT / (run['id'] + '.json')
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps(run, ensure_ascii=False, default=str), encoding='utf-8')
    os.replace(temporary, target)

def initialize():
    global INITIALIZED
    with LOCK:
        if INITIALIZED:
            return
        ROOT.mkdir(parents=True, exist_ok=True)
        for path in ROOT.glob('*.json'):
            try:
                run = json.loads(path.read_text(encoding='utf-8'))
                if run['status'] in ('queued', 'running'):
                    run.update(status='interrupted', finished_at=now())
                    run['errors'].append({'error': 'Server restarted; start a new run to retry unfinished companies.'})
                    save(run)
            except (ValueError, KeyError):
                continue
        INITIALIZED = True

def get_run(run_id):
    initialize()
    if not re.fullmatch(r'[a-f0-9]{32}', run_id):
        raise KeyError(run_id)
    with LOCK:
        try:
            return json.loads((ROOT / (run_id + '.json')).read_text(encoding='utf-8'))
        except FileNotFoundError:
            raise KeyError(run_id)

def list_runs():
    initialize()
    with LOCK:
        runs = []
        for path in ROOT.glob('*.json'):
            try:
                runs.append(json.loads(path.read_text(encoding='utf-8')))
            except ValueError:
                continue
        return sorted(runs, key=lambda r: r['created_at'], reverse=True)[:30]

def provider_status():
    serper_key = str(get_setting_value('SERPER_API_KEY', '') or '').strip()
    apollo_key = str(get_setting_value('APOLLO_API_KEY', '') or '').strip()
    serper_configured = bool(serper_key and not serper_key.lower().startswith(('mock', 'your', 'placeholder')))
    apollo_configured = bool(apollo_key and not apollo_key.lower().startswith(('mock', 'your', 'placeholder')))
    return {'providers': [
        {'id':'serper','name':'Serper production search','configured':serper_configured,'available':serper_configured,'reason':'Only live company, trigger, and facility research provider.'},
        {'id':'apollo','name':'Apollo','configured':apollo_configured,'available':apollo_configured,'reason':'Explicit post-qualification enrichment only; credentials not live-tested.'},
    ]}

def public_contacts(evidence):
    contacts = []
    seen = set()
    for item in evidence:
        url = item.get('url', '')
        if not url.startswith(('http://','https://')):
            continue
        text = item.get('snippet', '') or ''
        for kind, pattern in [('email',r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'),('phone',r'(?<!\w)(?:\+91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?!\w)')]:
            for value in re.findall(pattern, text):
                if (kind,value,url) not in seen:
                    seen.add((kind,value,url))
                    contacts.append({'type':kind,'value':value,'source_url':url,'status':'PUBLICLY_LISTED_UNVERIFIED','association':'company_or_page_unconfirmed'})
    return contacts

def official_evidence(company):
    """Read at most three public same-host pages; reject private hosts and redirects."""
    import ipaddress
    import socket
    import requests
    from urllib.parse import urlparse, urljoin
    from bs4 import BeautifulSoup
    url = str(company.website or company.domain or '').strip()
    if not url:
        return []
    if '://' not in url:
        url = 'https://' + url
    host = urlparse(url).hostname
    def allowed(target):
        parsed = urlparse(target)
        if parsed.scheme not in ('http','https') or parsed.hostname != host or parsed.username or parsed.password or parsed.port not in (None,80,443):
            return False
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 443)
        return bool(addresses) and all(ipaddress.ip_address(a[4][0]).is_global for a in addresses)
    queue, evidence = [url], []
    for target in queue:
        try:
            if not allowed(target):
                continue
            with requests.get(target, timeout=8, allow_redirects=False, stream=True) as response:
                if response.status_code != 200 or 'text/html' not in response.headers.get('Content-Type',''):
                    continue
                chunks, count = [], 0
                for chunk in response.iter_content(8192):
                    count += len(chunk)
                    if count > 500000:
                        break
                    chunks.append(chunk)
                soup = BeautifulSoup(b''.join(chunks), 'html.parser')
            if target == url:
                for a in soup.find_all('a', href=True):
                    if any(word in (a.get_text(' ',strip=True)+' '+a['href']).lower() for word in ('contact','team','leadership')):
                        link = urljoin(url,a['href']).split('#')[0]
                        if urlparse(link).hostname == host and link not in queue and len(queue)<3:
                            queue.append(link)
            for tag in soup(['script', 'style']):
                tag.decompose()
            # Only structured heading + adjacent role blocks become named evidence.
            for heading in soup.find_all(['h2', 'h3', 'h4', 'strong']):
                name = heading.get_text(' ', strip=True)
                sibling = heading.find_next_sibling()
                role = sibling.get_text(' ', strip=True) if sibling else ''
                if re.fullmatch(r'[A-Z][a-z]+(?: [A-Z][a-z]+){1,2}', name) and len(role) < 100:
                    if re.search(r'\b(quality|metrology|calibration|maintenance|procurement|plant|engineering)\b', role, re.I):
                        evidence.append({'title': name+' - '+role, 'url': target,
                                         'snippet': company.name+' — '+name+' — '+role,
                                         'provider': 'official_website', 'search_type': 'company_website',
                                         'persona': 'Quality / Metrology', 'retrieved_at': now()})
            snippet = soup.get_text(' ',strip=True)[:50000]
            evidence.append({'url':target,'snippet':snippet,'provider':'official_website','confidence':0.7,'retrieved_at':now()})
        except Exception:
            continue
    return evidence

def candidate_payload(candidate):
    from urllib.parse import urlparse
    evidence = candidate.evidence_sources or []
    import tldextract
    extractor = tldextract.TLDExtract(cache_dir=None, suffix_list_urls=())

    def registrable_domain(url):
        extracted = extractor(urlparse(url).hostname or '')
        modern_value = getattr(extracted, 'top_domain_under_public_suffix', '')
        if modern_value:
            return modern_value
        return '.'.join(part for part in (extracted.domain, extracted.suffix) if part)

    domains = {registrable_domain(item.get('url', ''))
               for item in evidence
               if item.get('url', '').startswith(('https://', 'http://'))
               and 'mock' not in json.dumps(item).lower()}
    domains.discard('')
    status = 'VERIFIED_PERSON' if len(domains) >= 2 and (candidate.verification_confidence or 0) >= 0.75 else 'PROBABLE_PERSON'
    if candidate.verification_status == 'PERSON_REJECTED':
        status = 'PERSON_REJECTED'
    assessment = next((e for e in reversed(evidence) if e.get('type') == 'email_assessment'), {})
    return {
        'name': candidate.candidate_name,
        'title': candidate.candidate_title,
        'confidence': candidate.verification_confidence,
        'verification_status': status,
        'email': candidate.apollo_email,
        'phone': candidate.apollo_phone,
        'email_status': assessment.get('status', 'UNVERIFIED' if candidate.apollo_email else 'NOT_FOUND'),
        'email_assessment': assessment,
        'evidence': evidence,
    }


def reusable_primary(db, company_id):
    """Reuse a recent, sourced named contact; never trust mock or guessed data."""
    rows = db.query(DecisionMakerCandidate).filter(
        DecisionMakerCandidate.company_id == company_id,
        DecisionMakerCandidate.verification_status != 'PERSON_REJECTED',
    ).all()
    rows.sort(key=lambda c: c.verification_confidence or 0, reverse=True)
    for candidate in rows:
        if not candidate.candidate_name or not candidate.apollo_email:
            continue
        if (candidate.verification_confidence or 0) < 0.55:
            continue
        if str(candidate.apollo_email_confidence or '').lower() in ('guessed', 'inferred'):
            continue
        evidence = candidate.evidence_sources or []
        if not evidence or any('mock' in json.dumps(item).lower() for item in evidence):
            continue
        recent = []
        for item in evidence:
            try:
                retrieved = datetime.fromisoformat(item.get('retrieved_at', '').replace('Z', '+00:00'))
                if retrieved.tzinfo is None:
                    retrieved = retrieved.replace(tzinfo=timezone.utc)
                age = (datetime.now(timezone.utc)-retrieved).days
                if 0 <= age <= 180 and item.get('url', '').startswith(('http://','https://')):
                    recent.append(item)
            except (ValueError, TypeError):
                continue
        if recent:
            return candidate_payload(candidate)
    return None


def reusable_run_result(company_id, max_queries, use_apollo):
    """Reuse a successful free result for one day, including a real empty search."""
    if use_apollo:
        return None
    for prior in list_runs():
        if prior.get('status') != 'completed' or prior.get('max_queries', 0) < max_queries:
            continue
        try:
            finished = datetime.fromisoformat(prior.get('finished_at', '').replace('Z', '+00:00'))
            if finished.tzinfo is None:
                finished = finished.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc)-finished).total_seconds()
        except (ValueError, TypeError):
            continue
        if not 0 <= age <= 86400:
            continue
        for result in prior.get('results', []):
            if result.get('company_id') != company_id or result.get('status') not in ('completed', 'no_results'):
                continue
            if 'mock' in json.dumps(result).lower():
                continue
            # Do not repeatedly extend the lifetime of a reused result.
            if result.get('cached_from_run'):
                continue
            cached = copy.deepcopy(result)
            cached['cached_from_run'] = prior['id']
            cached['reuse_reason'] = 'Same or larger free research completed within 24 hours.'
            cached.setdefault('summary', {}).update(cache_hits=1, queries_saved=max_queries)
            cached.setdefault('stages', {})['cache'] = {'status': 'REUSED'}
            return normalize_result_counts(cached)
    return None


def normalize_result_counts(result):
    """Present conservative counts for the returned primary, not legacy scores."""
    candidates = result.get('candidates', [])
    verified = [c for c in candidates if c.get('verification_status') == 'VERIFIED_PERSON']
    probable = [c for c in candidates if c.get('verification_status') == 'PROBABLE_PERSON']
    result.setdefault('summary', {}).update(
        candidates_verified=len(verified), candidates_probable=len(probable),
        primary_candidates_returned=len(candidates))
    stages = result.setdefault('stages', {})
    if 'public_evidence' in stages:
        stages['public_evidence'].update(verified_count=len(verified), candidate_count=len(probable))
    if 'verification' in stages:
        stages['verification']['verified'] = [{'name':c['name'], 'status':c['verification_status']} for c in verified]
        stages['verification']['probable'] = [{'name':c['name'], 'status':c['verification_status']} for c in probable]
    if 'research_brief' in stages:
        stages['research_brief'].update(has_verified_person=bool(verified), next_best_action='REVIEW_EVIDENCE')
    return result


def start_run(company_ids, max_queries=3, use_apollo=False):
    global ACTIVE
    initialize()
    ids = list(dict.fromkeys(company_ids))
    if not ids or len(ids)>50 or not 1 <= max_queries <= 6:
        raise ValueError('Choose 1–50 companies and 1–6 queries per company.')
    with LOCK:
        if ACTIVE:
            raise RuntimeError('A contact research run is already active.')
        with SessionLocal() as db:
            found = {row.id for row in db.query(Company).filter(Company.id.in_(ids)).all()}
        missing = sorted(set(ids)-found)
        if missing:
            raise ValueError('Unknown company IDs: '+str(missing))
        if use_apollo and not provider_status()['providers'][1]['available']:
            raise ValueError('Apollo is not configured.')
        run = {'id':uuid.uuid4().hex,'status':'queued','completed':0,'total':len(ids),'company_ids':ids,'max_queries':max_queries,'use_apollo':use_apollo,'apollo_attempts':0,'results':[],'errors':[],'created_at':now()}
        save(run)
        ACTIVE = run['id']
        threading.Thread(target=execute, args=(run['id'],), daemon=True).start()
        return run

def execute(run_id):
    global ACTIVE
    try:
        run = get_run(run_id)
        run['status'] = 'running'
        with LOCK:
            save(run)
        for company_id in run['company_ids']:
            try:
                with SessionLocal() as db:
                    company = db.query(Company).filter(Company.id == company_id).first()
                    cached_result = reusable_run_result(company_id, run['max_queries'], run['use_apollo'])
                    if cached_result:
                        rejected = db.query(DecisionMakerCandidate).filter(
                            DecisionMakerCandidate.company_id == company_id,
                            DecisionMakerCandidate.verification_status == 'PERSON_REJECTED').all()
                        names = {(c.candidate_name or '').strip().lower() for c in rejected}
                        if any((c.get('name') or '').strip().lower() in names for c in cached_result.get('candidates', [])):
                            cached_result = None
                        run['results'].append(cached_result)
                        run['completed'] += 1
                        with LOCK:
                            save(run)
                        continue
                    cached = reusable_primary(db, company_id)
                    if cached:
                        run['results'].append({
                            'company_id': company_id, 'company_name': company.name,
                            'status': 'completed', 'summary': {'cache_hits': 1, 'queries_saved': run['max_queries']},
                            'candidates': [cached], 'public_contacts': [],
                            'reuse_reason': 'Recent sourced primary contact already has an email; no external lookup.',
                            'stages': {'cache': {'status': 'REUSED'}},
                        })
                        run['completed'] += 1
                        with LOCK:
                            save(run)
                        continue
                    official = official_evidence(company)

                    def reserve_apollo_attempt():
                        if not run['use_apollo'] or run['apollo_attempts'] >= 6:
                            return False
                        run['apollo_attempts'] += 1
                        with LOCK:
                            save(run)
                        return True

                    result = run_full_discovery_pipeline(
                        company_id, db,
                        max_queries=run['max_queries'],
                        max_apollo_enrichments=min(1, max(0, 6-run['apollo_attempts'])) if run['use_apollo'] else 0,
                        free_only=False,
                        additional_evidence=official,
                        before_apollo=reserve_apollo_attempt,
                    )
                    if result.get('error'):
                        raise ValueError(result['error'])
                    candidates = result.get('candidates', [])
                    rows = db.query(DecisionMakerCandidate).filter(DecisionMakerCandidate.id.in_(result.get('candidate_ids',[]))).all()
                    from services.contact_confidence import enrich_candidate_phone
                    from services.apollo_adapter import enrich_specific_person
                    for c in rows:
                        enrich_candidate_phone(
                            c, company, result.get('public_evidence', []),
                            apollo_allowed=(run['use_apollo'] and c.verification_status == 'CONTACT_ENRICHMENT_READY'),
                            apollo_lookup_fn=(
                                enrich_specific_person
                                if run['use_apollo'] and c.verification_status == 'CONTACT_ENRICHMENT_READY'
                                else None
                            ),
                        )
                    db.commit()
                    candidates = candidates[:1]
                    result.setdefault('stages', {})['official_website'] = {'status':'LIVE' if official else 'NO_PUBLIC_PAGE', 'pages_read':len({item['url'] for item in official})}
                    stage = result.get('stages',{}).get('person_search',{})
                    status = 'completed' if stage.get('total_results',0) or official else 'no_results'
                    if stage.get('status') in ('ERROR','BLOCKED','NOT_CONFIGURED','QUOTA_EXHAUSTED'):
                        status = 'partial' if official else 'failed'
                        run['errors'].append({'company_id':company_id,'error':'Public search unavailable: '+stage['status']})
                    run['results'].append({'company_id':company_id,'company_name':result.get('company_name'),'status':status,'summary':result.get('summary',{}),'candidates':candidates,'public_contacts':public_contacts(result.get('public_evidence',[])),'stages':result.get('stages',{})})
            except Exception as exc:
                frames = [f'{Path(frame.filename).name}:{frame.lineno}:{frame.name}'
                          for frame in traceback.extract_tb(exc.__traceback__)[-5:]]
                error = {'company_id': company_id, 'error': 'Research failed ('+type(exc).__name__+').', 'frames': frames}
                logging.getLogger(__name__).error('Contact research %s: %s at %s', company_id, type(exc).__name__, frames)
                run['errors'].append(error)
                run['results'].append({'company_id': company_id, 'company_name': None,
                                       'status': 'failed', 'summary': {}, 'candidates': [],
                                       'public_contacts': [], 'stages': {'execution': {'status': 'ERROR', 'reason': error['error']}},
                                       'error': error})
            if run['results']:
                normalize_result_counts(run['results'][-1])
            run['completed'] += 1
            with LOCK:
                save(run)
        run.update(status='completed_with_errors' if run['errors'] else 'completed', finished_at=now())
        with LOCK:
            save(run)
    finally:
        with LOCK:
            ACTIVE = None


def export_csv(run):
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    writer.writerow(['company_id','company','name','title','confidence','person_status','email','phone','contact_status','evidence_url'])
    def safe(value):
        text = '' if value is None else str(value)
        return "'"+text if text.startswith(('=','+','-','@','\t','\r')) else text
    for result in run['results']:
        for c in result['candidates']:
            writer.writerow(map(safe,[result['company_id'],result['company_name'],c['name'],c['title'],c['confidence'],c['verification_status'],c['email'],c['phone'],c['email_status'],' | '.join(e.get('url','') for e in c['evidence'])]))
        for c in result['public_contacts']:
            writer.writerow(map(safe,[result['company_id'],result['company_name'],'','','','',c['value'] if c['type']=='email' else '',c['value'] if c['type']=='phone' else '',c['status'],c['source_url']]))
    return output.getvalue()
