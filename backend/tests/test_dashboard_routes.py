"""Dashboard read APIs use an isolated database; never connect to the running app DB."""
import unittest
from datetime import date, datetime, timedelta
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import get_db
from models.company import Company
from models.customer_asset import CustomerAsset
from models.campaign import Campaign, CampaignRecipient, CampaignEvent
from routes import campaigns, customer_assets


class DashboardRouteTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        for model in (Company, CustomerAsset, Campaign, CampaignRecipient, CampaignEvent):
            model.__table__.create(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.db.add(Company(id=1, name='Test factory'))
        self.db.commit()
        app = FastAPI()
        app.include_router(customer_assets.router)
        app.include_router(campaigns.router)
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(app)
        self.db_patch = patch.object(campaigns, 'db', self.Session)
        self.db_patch.start()

    def tearDown(self):
        self.db_patch.stop()
        self.client.close()
        self.db.close()
        self.engine.dispose()

    def test_calibration_window_order_limit_and_company(self):
        today = date.today()
        for asset_id, offset, status in [(1, 10, 'Active'), (2, 0, 'Active'), (3, 45, 'Active'), (4, 46, 'Active'), (5, -1, 'Active'), (6, 2, 'Inactive')]:
            self.db.add(CustomerAsset(id=asset_id, company_id=1, instrument_name='Gauge', status=status, calibration_due_date=today + timedelta(days=offset)))
        self.db.add(CustomerAsset(id=7, company_id=1, instrument_name='No date'))
        self.db.commit()
        response = self.client.get('/api/customer-assets/calibration-due?days=45&limit=2')
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result['total'], 3)
        self.assertEqual([r['id'] for r in result['results']], [2, 1])
        self.assertEqual(result['results'][0]['company_name'], 'Test factory')
        self.assertEqual(self.db.query(CustomerAsset).count(), 7)

    def test_replies_filter_order_payload_and_total(self):
        self.db.add(Campaign(id=1, name='Test draft'))
        self.db.add(CampaignRecipient(id=1, campaign_id=1, company_id=1))
        for event_id, event_type, payload in [(1, 'reply', None), (2, 'sent', {}), (3, 'replied', {'from': 'qa@example.test', 'subject': 'Quote request', 'classification': {'category': 'REQUESTING_QUOTE'}}), (4, 'bounced', {})]:
            self.db.add(CampaignEvent(id=event_id, campaign_id=1, recipient_id=1, event_type=event_type, occurred_at=datetime(2026, 1, event_id), payload=payload))
        self.db.commit()
        response = self.client.get('/api/campaigns/inbox/replies?limit=1')
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result['total'], 2)
        self.assertEqual(result['results'][0]['id'], 3)
        self.assertEqual(result['results'][0]['from_email'], 'qa@example.test')
        self.assertEqual(result['results'][0]['classification']['category'], 'REQUESTING_QUOTE')
        full = self.client.get('/api/campaigns/inbox/replies').json()
        self.assertIsNone(full['results'][1]['classification'])
        self.assertEqual(self.db.query(CampaignEvent).count(), 4)

    def test_empty_results_and_validation(self):
        for path in ['/api/customer-assets/calibration-due', '/api/campaigns/inbox/replies']:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['results'], [])
            for limit in [0, 101]:
                self.assertEqual(self.client.get(f'{path}?limit={limit}').status_code, 422)
        for days in [0, 366]:
            self.assertEqual(self.client.get(f'/api/customer-assets/calibration-due?days={days}').status_code, 422)


if __name__ == '__main__':
    unittest.main()
