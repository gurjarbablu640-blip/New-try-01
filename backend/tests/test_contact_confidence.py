import unittest
from unittest.mock import patch
from services.contact_confidence import assess_email, infer_emails, discover_email, phone_decision
from services.email_validator import validate_email_address, check_mx_records

MX = lambda domain: (True, ['mail.'+domain], 'MX exists')


class ContactConfidenceTests(unittest.TestCase):
    def test_dns_never_verifies_mailbox(self):
        for origin in ('VERIFIED', 'PROBABLE', 'INFERRED', 'UNVERIFIED'):
            result = assess_email('jane.singh@factory.in', origin, dns_check=MX)
            self.assertNotEqual(result['status'], 'VERIFIED')
            self.assertFalse(result['mailbox_verified'])

    def test_public_evidence_keeps_provenance(self):
        result = discover_email('Jane Singh', 'factory.in', [dict(url='https://factory.in/team', snippet='Jane Singh — jane.singh@factory.in')], dns_check=MX)
        self.assertEqual(result['status'], 'PUBLICLY_FOUND')
        self.assertTrue(result['evidence'])
        self.assertFalse(result['apollo_used'])

    def test_generic_contact_not_assigned(self):
        result = discover_email('Jane Singh', 'factory.in', [dict(url='https://factory.in/team', snippet='Jane Singh — info@factory.in')], dns_check=MX)
        self.assertEqual(result['status'], 'NOT_FOUND')

    def test_long_page_or_multiple_emails_not_associated(self):
        for text in ('Jane Singh '+('text '*101)+' jane.singh@factory.in', 'Jane Singh jane@factory.in bob@factory.in'):
            self.assertEqual(discover_email('Jane Singh', 'factory.in', [dict(url='https://factory.in', snippet=text)], dns_check=MX)['status'], 'NOT_FOUND')

    def test_pattern_requires_sourced_named_same_domain(self):
        known = [dict(name='Ravi Kumar', email='ravi.kumar@factory.in', source='https://factory.in/team', status='PUBLICLY_FOUND')]
        self.assertEqual(infer_emails('Jane Singh', 'factory.in', known)[0]['email'], 'jane.singh@factory.in')
        self.assertEqual(infer_emails('Jane Singh', 'other.in', known), [])
        known[0]['status'] = 'INFERRED'
        self.assertEqual(infer_emails('Jane Singh', 'factory.in', known), [])

    def test_inference_stays_inferred(self):
        known = [dict(name='Ravi Kumar', email='ravi.kumar@factory.in', source='https://factory.in/team', status='PUBLICLY_FOUND')]
        self.assertEqual(discover_email('Jane Singh', 'factory.in', [], known, MX)['status'], 'INFERRED')

    def test_timeout_is_unverified(self):
        self.assertEqual(assess_email('jane@factory.in', 'PUBLICLY_FOUND', [{}], dns_check=lambda _: (False, [], 'timeout'))['status'], 'UNVERIFIED')

    def test_test_addresses_blocked(self):
        self.assertFalse(assess_email('jane@example.com', dns_check=MX)['syntax_valid'])

    def test_selective_phone_gate(self):
        self.assertFalse(phone_decision(94, True, apollo_allowed=True)['apollo_allowed'])
        self.assertFalse(phone_decision(99, False, apollo_allowed=True)['apollo_allowed'])
        self.assertFalse(phone_decision(99, True, '+919999999999', 'DIRECT', apollo_allowed=True)['apollo_allowed'])
        result = phone_decision(99, True, '01112345678', 'SWITCHBOARD', apollo_allowed=True)
        self.assertFalse(result['existing_direct'])
        self.assertTrue(result['apollo_allowed'])

    def test_legacy_validator_no_mailbox_claim(self):
        with patch('services.email_validator.check_mx_records', MX):
            result = validate_email_address('jane@factory.in')
        self.assertEqual(result['status'], 'unverified')
        self.assertFalse(result['mailbox_verified'])

    def test_classify_phone_number(self):
        from services.contact_confidence import classify_phone_number
        mob = classify_phone_number('+91 98250 14820')
        self.assertEqual(mob['phone_type'], 'PERSONAL_MOBILE')
        self.assertTrue(mob['is_direct_mobile'])

        tf = classify_phone_number('1800 120 4567')
        self.assertEqual(tf['phone_type'], 'SWITCHBOARD')
        self.assertFalse(tf['is_direct_mobile'])

        sb = classify_phone_number('022-27788990', context_text='Switchboard / Operator')
        self.assertIn(sb['phone_type'], ('SWITCHBOARD', 'CORPORATE_SWITCHBOARD'))
        self.assertFalse(sb['is_direct_mobile'])

        land = classify_phone_number('0265-2345678')
        self.assertIn(land['phone_type'], ('OFFICE', 'CORPORATE_SWITCHBOARD'))
        self.assertFalse(land['is_direct_mobile'])

    def test_discover_person_phone_public_first(self):
        from services.contact_confidence import discover_person_phone
        evidence = [{'url': 'https://factory.in/team', 'snippet': 'Rajesh Patel — Quality Head: +91 98250 14820'}]
        res = discover_person_phone('Rajesh Patel', evidence)
        self.assertIsNotNone(res)
        self.assertEqual(res['phone_type'], 'PERSONAL_MOBILE')
        self.assertEqual(res['source'], 'public_evidence')

        # Generic line with no person match
        no_match = discover_person_phone('Sanjay Sharma', evidence)
        self.assertIsNone(no_match)

    def test_selective_apollo_phone_enrichment(self):
        from types import SimpleNamespace
        from services.contact_confidence import enrich_candidate_phone

        company = SimpleNamespace(name='High Value Corp', icp_score=96)
        candidate = SimpleNamespace(
            candidate_name='Rajesh Patel',
            candidate_title='QA Head',
            verification_status='VERIFIED_PERSON',
            apollo_phone=None,
            evidence_sources=[],
        )

        mock_apollo = lambda name, co, title: {'status': 'ENRICHED', 'phone': '+91 98250 99999', 'mock_mode': False}

        # 1. Apollo not allowed -> no Apollo call, not found
        res = enrich_candidate_phone(candidate, company, [], apollo_allowed=False, apollo_lookup_fn=mock_apollo)
        self.assertFalse(res['apollo_used'])
        self.assertEqual(res['provider_credits_consumed'], 0)
        self.assertIsNone(candidate.apollo_phone)

        # 2. Apollo allowed on high-value verified person -> Apollo called, credits recorded
        res2 = enrich_candidate_phone(candidate, company, [], apollo_allowed=True, apollo_lookup_fn=mock_apollo)
        self.assertTrue(res2['apollo_used'])
        self.assertEqual(res2['provider_credits_consumed'], 1)
        self.assertEqual(res2['phone_type'], 'PERSONAL_MOBILE')
        self.assertEqual(candidate.apollo_phone, '+91 98250 99999')

        # 3. Switchboard from Apollo does NOT overwrite direct mobile
        candidate_sb = SimpleNamespace(
            candidate_name='Amit Shah',
            candidate_title='VP',
            verification_status='VERIFIED_PERSON',
            apollo_phone=None,
            evidence_sources=[],
        )
        sb_apollo = lambda name, co, title: {'status': 'ENRICHED', 'phone': '1800 200 1111', 'mock_mode': False}
        res3 = enrich_candidate_phone(candidate_sb, company, [], apollo_allowed=True, apollo_lookup_fn=sb_apollo)
        self.assertEqual(res3['phone_type'], 'SWITCHBOARD')
        self.assertIsNone(candidate_sb.apollo_phone)  # Switchboard not stored as personal mobile!

    def test_reject_action_verb_and_non_human_candidate_names(self):
        """Action verbs, ecommerce, media, and SEO tokens must never pass as human names."""
        from services.contact_confidence import is_human_person_candidate, validate_person_name

        bad_names = [
            "Shop Wardrobe Organisers Online",
            "Paras Pokedex",
            "Download CCleaner",
            "Welcome to Gujarat Tourism",
            "NextGen eChallan",
            "Latest Hindi Action Movies",
            "College Football Picks",
            "Buy Solar Panels",
            "Explore Our Products",
        ]
        for name in bad_names:
            is_human, reason = is_human_person_candidate(name)
            self.assertFalse(is_human, f"Failed to reject non-human name: '{name}'")
            val = validate_person_name(name)
            self.assertFalse(val["is_human_name"], f"validate_person_name failed to reject: '{name}'")
            self.assertEqual(val["person_name_validation"], "INVALID_ROLE_TEXT")


if __name__ == '__main__':
    unittest.main()

