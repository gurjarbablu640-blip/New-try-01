import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from services import contact_research as s
from services.research_provider import ResearchProviderRouter, PROVIDER_ERROR

class ContactResearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = patch.object(s, 'ROOT', Path(self.temp.name))
        self.root.start()
        s.INITIALIZED = False
        s.ACTIVE = None
    def tearDown(self):
        self.root.stop()
        self.temp.cleanup()
    def test_public_contact_requires_evidence_and_is_unverified(self):
        rows = s.public_contacts([{'url':'https://example.com/contact','snippet':'qa@example.com +91 9876543210'}])
        self.assertEqual(len(rows),2)
        self.assertTrue(all(r['status']=='PUBLICLY_LISTED_UNVERIFIED' for r in rows))
        self.assertEqual(s.public_contacts([{'snippet':'qa@example.com'}]),[])
    def test_restart_marks_active_run_interrupted(self):
        s.save({'id':'a'*32,'status':'running','errors':[],'created_at':s.now()})
        self.assertEqual(s.get_run('a'*32)['status'],'interrupted')
    def test_invalid_path_is_not_read(self):
        with self.assertRaises(KeyError): s.get_run('../secret')
    def test_one_active_run_and_bounds(self):
        s.ACTIVE = 'busy'
        with self.assertRaises(RuntimeError): s.start_run([1])
        with self.assertRaises(ValueError): s.start_run(list(range(51)))
    def test_free_search_never_calls_paid_or_cache(self):
        router = ResearchProviderRouter()
        with patch.object(router,'_search_google') as google, patch.object(router,'_search_serper') as serper, patch.object(router,'_search_database_cache') as cache, patch.object(router,'_search_searxng',return_value=([],PROVIDER_ERROR,'unavailable')):
            result = router.search('example',free_only=True)
        google.assert_not_called(); serper.assert_not_called(); cache.assert_not_called()
        self.assertEqual(result['provider_status'],PROVIDER_ERROR)
    def test_csv_neutralizes_formula(self):
        csv = s.export_csv({'results':[{'company_id':1,'company_name':'=CMD()','candidates':[],'public_contacts':[{'type':'email','value':'qa@example.com','status':'PUBLICLY_LISTED_UNVERIFIED','source_url':'https://example.com'}]}]})
        self.assertIn("'=CMD()",csv)

    def make_run(self, use_apollo=False):
        s.initialize()
        run = {'id': 'b'*32, 'status': 'queued', 'errors': [], 'results': [],
               'created_at': s.now(), 'company_ids': [1, 2], 'max_queries': 2,
               'use_apollo': use_apollo, 'apollo_attempts': 0, 'completed': 0, 'total': 2}
        s.save(run)
        return run

    def test_run_reuses_cached_contact_without_external_calls(self):
        run = self.make_run()
        session = MagicMock()
        with patch.object(s, 'SessionLocal', return_value=session), \
             patch.object(s, 'reusable_primary', return_value={'name': 'Known Person'}), \
             patch.object(s, 'official_evidence') as fetch, \
             patch.object(s, 'run_full_discovery_pipeline') as pipeline:
            # Company name must be JSON serializable.
            session.__enter__.return_value.query.return_value.filter.return_value.first.return_value.name = 'Known Company'
            s.execute(run['id'])
        fetch.assert_not_called()
        pipeline.assert_not_called()
        saved = s.get_run(run['id'])
        self.assertEqual(saved['completed'], 2)
        self.assertEqual(saved['status'], 'completed')
        self.assertEqual(saved['results'][0]['summary']['cache_hits'], 1)

    def test_attempts_persist_before_exception_and_never_exceed_six(self):
        run = self.make_run(use_apollo=True)
        run['apollo_attempts'] = 5
        s.save(run)
        observed = []
        def fail_pipeline(*args, **kwargs):
            observed.append(kwargs['max_apollo_enrichments'])
            for unused in range(10):
                kwargs['before_apollo']()
            raise RuntimeError('provider failure with SECRET')
        with patch.object(s, 'SessionLocal', return_value=MagicMock()), \
             patch.object(s, 'reusable_primary', return_value=None), \
             patch.object(s, 'official_evidence', return_value=[]), \
             patch.object(s, 'run_full_discovery_pipeline', side_effect=fail_pipeline):
            s.execute(run['id'])
        saved = s.get_run(run['id'])
        self.assertEqual(saved['apollo_attempts'], 6)
        self.assertEqual(observed, [1, 0])
        self.assertEqual(saved['status'], 'completed_with_errors')
        self.assertNotIn('SECRET', str(saved))

    def test_rejected_candidate_cannot_be_reenabled(self):
        from services.decision_maker_discovery import merge_candidate_evidence
        from types import SimpleNamespace
        old = SimpleNamespace(verification_status='PERSON_REJECTED', evidence_sources=[{'url':'https://old.example'}])
        fresh = SimpleNamespace(verification_status='PERSON_PUBLICLY_VERIFIED', evidence_sources=[{'url':'https://new.example'}])
        merged = merge_candidate_evidence(old, fresh)
        self.assertIs(merged, old)
        self.assertEqual(merged.verification_status, 'PERSON_REJECTED')
        self.assertEqual(len(merged.evidence_sources), 2)

    def test_searx_engine_failure_is_not_empty_success(self):
        response = MagicMock(status_code=200)
        response.json.return_value = {'results': [], 'unresponsive_engines': [['google', 'timeout']]}
        with patch('services.research_provider.requests.get', return_value=response) as request:
            results, status, error = ResearchProviderRouter()._search_searxng('test')
        self.assertEqual(status, PROVIDER_ERROR)
        self.assertEqual(request.call_count, 1)



    def test_actual_domain_library_and_confidence_gate(self):
        from types import SimpleNamespace
        candidate = SimpleNamespace(candidate_name='A Person', candidate_title='Quality Head',
            verification_confidence=0.9, verification_status='PERSON_PUBLICLY_VERIFIED',
            apollo_email=None, apollo_phone=None,
            evidence_sources=[{'url':'https://www.example.com/a'}, {'url':'https://news.example.com/b'}])
        self.assertEqual(s.candidate_payload(candidate)['verification_status'], 'PROBABLE_PERSON')
        candidate.evidence_sources.append({'url':'https://example.org/profile'})
        self.assertEqual(s.candidate_payload(candidate)['verification_status'], 'VERIFIED_PERSON')
        candidate.verification_confidence = 0.4
        self.assertEqual(s.candidate_payload(candidate)['verification_status'], 'PROBABLE_PERSON')
        candidate.verification_status = 'PERSON_REJECTED'
        self.assertEqual(s.candidate_payload(candidate)['verification_status'], 'PERSON_REJECTED')

    def test_completed_empty_result_reused_without_external_work(self):
        s.initialize()
        prior = {'id':'c'*32, 'status':'completed', 'max_queries':3, 'created_at':s.now(),
            'finished_at':s.now(), 'results':[{'company_id':1, 'company_name':'Example',
                'status':'no_results', 'summary':{}, 'candidates':[], 'public_contacts':[], 'stages':{}}]}
        s.save(prior)
        run = self.make_run()
        run.update(company_ids=[1], total=1)
        s.save(run)
        with patch.object(s, 'SessionLocal', return_value=MagicMock()), \
             patch.object(s, 'official_evidence') as fetch, \
             patch.object(s, 'run_full_discovery_pipeline') as pipeline:
            s.execute(run['id'])
        fetch.assert_not_called()
        pipeline.assert_not_called()
        result = s.get_run(run['id'])
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['results'][0]['cached_from_run'], prior['id'])
        self.assertEqual(result['results'][0]['summary']['queries_saved'], 2)
        self.assertIsNone(s.reusable_run_result(1, 4, False))
        self.assertIsNone(s.reusable_run_result(1, 2, True))

    def test_old_or_failed_results_not_reused(self):
        from datetime import datetime, timezone, timedelta
        s.initialize()
        old = (datetime.now(timezone.utc)-timedelta(days=2)).isoformat()
        prior = {'id':'c'*32, 'status':'completed', 'max_queries':3, 'created_at':old,
            'finished_at':old, 'results':[{'company_id':1, 'status':'no_results'}]}
        s.save(prior)
        self.assertIsNone(s.reusable_run_result(1, 1, False))
        prior.update(status='completed_with_errors', finished_at=s.now())
        s.save(prior)
        self.assertIsNone(s.reusable_run_result(1, 1, False))

    def test_existing_crm_email_reused_without_enrichment(self):
        from services.decision_maker_discovery import reuse_crm_email
        from types import SimpleNamespace
        candidate = SimpleNamespace(company_id=1, candidate_name='A Person', apollo_email=None,
            verification_status='PERSON_PUBLICLY_VERIFIED')
        person = SimpleNamespace(full_name='A Person', email='qa@example.com',
            email_verification_status='valid', discovery_source='manual', evidence_json=None)
        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = [person]
        reuse_crm_email(candidate, db)
        self.assertEqual(candidate.apollo_email, 'qa@example.com')
        self.assertEqual(candidate.email_status, 'EMAIL_FOUND')
        candidate.apollo_email = None
        person.discovery_source = 'mock'
        reuse_crm_email(candidate, db)
        self.assertIsNone(candidate.apollo_email)


    def test_probable_result_does_not_inherit_legacy_verified_counts(self):
        result = {'candidates':[{'name':'A Person','verification_status':'PROBABLE_PERSON'}],
            'summary':{'candidates_verified':3},
            'stages':{'research_brief':{'has_verified_person':True}, 'public_evidence':{'verified_count':3}}}
        s.normalize_result_counts(result)
        self.assertEqual(result['summary']['candidates_verified'], 0)
        self.assertEqual(result['summary']['candidates_probable'], 1)
        self.assertFalse(result['stages']['research_brief']['has_verified_person'])

if __name__=='__main__': unittest.main()
