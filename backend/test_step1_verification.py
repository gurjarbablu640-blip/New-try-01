import os
import sys
import json
import sqlite3
import unittest
from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.types import ARRAY
from sqlalchemy.dialects.postgresql import JSONB

# SQLite adapter for Python lists and PostgreSQL-specific types during tests
sqlite3.register_adapter(list, json.dumps)
sqlite3.register_adapter(dict, json.dumps)

@compiles(ARRAY, "sqlite")
def compile_array_sqlite(type_, compiler, **kw):
    return "TEXT"

@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "TEXT"

# Add backend directory to sys.path
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from database import Base
from models.company import Company
from models.person import Person
from services.deduplication import (
    normalize_company_name,
    extract_domain,
    normalize_phone_number,
    find_company_duplicate,
    ingest_or_merge_lead,
)
from services.email_validator import validate_email_address, validate_email_batch, normalize_email
from services.apollo_adapter import search_apollo_leads
from services.lead_qualification import (
    evaluate_lead_qualification,
    set_qualification_status,
    batch_evaluate_leads,
)


class TestStep1LeadEngine(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Use an in-memory SQLite database for fast, isolated verification
        cls.engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(cls.engine)
        cls.Session = sessionmaker(bind=cls.engine)

    def setUp(self):
        self.db = self.Session()

    def tearDown(self):
        self.db.rollback()
        self.db.close()

    # ------------------------------------------------------------
    # 1. Normalization & Helpers
    # ------------------------------------------------------------
    def test_company_name_normalization(self):
        self.assertEqual(normalize_company_name("Aarti Industries Pvt. Ltd."), "aarti industries")
        self.assertEqual(normalize_company_name("Bharat Forge Limited"), "bharat forge")
        self.assertEqual(normalize_company_name("Reliance Industries Co. Ltd."), "reliance industries")
        self.assertEqual(normalize_company_name("L&T Heavy Engineering"), "l and t heavy engineering")

    def test_domain_extraction(self):
        self.assertEqual(extract_domain("https://www.aarti-industries.com/contact"), "aarti-industries.com")
        self.assertEqual(extract_domain("http://bharatforge.com/about-us"), "bharatforge.com")
        self.assertEqual(extract_domain("sparc.life"), "sparc.life")
        self.assertEqual(extract_domain("rajesh@aarti-industries.com"), "aarti-industries.com")

    def test_phone_normalization(self):
        self.assertEqual(normalize_phone_number("9825014820"), "+919825014820")
        self.assertEqual(normalize_phone_number("+91-98250-14820"), "+919825014820")
        self.assertEqual(normalize_phone_number("09825014820"), "+919825014820")

    # ------------------------------------------------------------
    # 2. Email Validation
    # ------------------------------------------------------------
    def test_email_syntax_and_disposable(self):
        res_valid = validate_email_address("rajesh.patel@aarti-industries.com")
        self.assertEqual(res_valid["status"], "valid")
        self.assertFalse(res_valid["is_disposable"])

        res_disposable = validate_email_address("test@mailinator.com")
        self.assertEqual(res_disposable["status"], "invalid")
        self.assertTrue(res_disposable["is_disposable"])

        res_invalid = validate_email_address("invalid-email-syntax@@domain..com")
        self.assertEqual(res_invalid["status"], "invalid")

        res_role = validate_email_address("admin@aarti-industries.com")
        self.assertTrue(res_role["is_role_account"])
        self.assertEqual(res_role["status"], "risky")

    # ------------------------------------------------------------
    # 3. Apollo Adapter (Mock Mode)
    # ------------------------------------------------------------
    def test_apollo_mock_search(self):
        search_res = search_apollo_leads(query="Chemical", locations=["Gujarat"], force_mock=True)
        self.assertTrue(search_res["mock_mode"])
        self.assertGreater(len(search_res["results"]), 0)
        first_lead = search_res["results"][0]
        self.assertIn("company_name", first_lead)
        self.assertIn("domain", first_lead)
        self.assertIn("contacts", first_lead)
        self.assertGreater(len(first_lead["contacts"]), 0)

    # ------------------------------------------------------------
    # 4. Ingestion & Multi-Vector Deduplication
    # ------------------------------------------------------------
    def test_ingestion_and_deduplication(self):
        # Ingest first lead
        company_data_1 = {
            "name": "Aarti Industries Ltd",
            "website": "https://www.aarti-industries.com",
            "city": "Dahej",
            "state": "Gujarat",
            "industry": "Chemicals",
            "source": "apollo",
            "apollo_id": "org_aarti_01",
        }
        contacts_1 = [
            {
                "name": "Rajesh Patel",
                "title": "Quality Head",
                "email": "rajesh.patel@aarti-industries.com",
                "phone": "9825014820",
                "is_decision_maker": 1,
            }
        ]

        c1, p1, action1 = ingest_or_merge_lead(self.db, company_data_1, contacts_1)
        self.db.commit()

        self.assertEqual(action1, "CREATED")
        self.assertEqual(c1.name, "Aarti Industries Ltd")
        self.assertEqual(c1.domain, "aarti-industries.com")
        self.assertEqual(len(p1), 1)
        self.assertEqual(p1[0].normalized_email, "rajesh.patel@aarti-industries.com")

        # Ingest duplicate with different name variation but same domain
        company_data_2 = {
            "name": "Aarti Industries Pvt. Ltd. (Dahej Plant)",
            "website": "http://aarti-industries.com",
            "city": "Dahej",
            "state": "Gujarat",
            "industry": "Chemical Manufacturing",
            "source": "google_places",
        }
        contacts_2 = [
            {
                "name": "Sanjay Sharma",
                "title": "Plant Head",
                "email": "sanjay.sharma@aarti-industries.com",
                "phone": "9825099112",
                "is_decision_maker": 1,
            }
        ]

        c2, p2, action2 = ingest_or_merge_lead(self.db, company_data_2, contacts_2)
        self.db.commit()

        self.assertEqual(action2, "MERGED")
        self.assertEqual(c2.id, c1.id)  # Same company record merged!
        
        # Verify total contacts on this company
        total_persons = self.db.query(Person).filter(Person.company_id == c1.id).count()
        self.assertEqual(total_persons, 2)

    # ------------------------------------------------------------
    # 5. Lead Qualification Gate
    # ------------------------------------------------------------
    def test_lead_qualification_rules(self):
        # Case A: Strong ICP manufacturing company with verified decision maker -> READY_FOR_OUTREACH
        comp_a = Company(
            name="Precision Auto Parts Ltd",
            normalized_name="precision auto parts",
            domain="precisionauto.com",
            website="https://www.precisionauto.com",
            city="Pune",
            state="Maharashtra",
            industry="Automotive",
            has_nabl=True,
            icp_score=75.0,
            calculated_tier="High-Value Recurring",
            qualification_status="RAW",
        )
        self.db.add(comp_a)
        self.db.flush()

        person_a = Person(
            company_id=comp_a.id,
            full_name="Anand Joshi",
            designation="VP Quality",
            email="anand@precisionauto.com",
            normalized_email="anand@precisionauto.com",
            email_verification_status="valid",
            is_decision_maker=1,
        )
        self.db.add(person_a)
        self.db.commit()

        eval_a = evaluate_lead_qualification(self.db, comp_a.id)
        self.assertEqual(eval_a["qualification_status"], "READY_FOR_OUTREACH")

        # Case B: Strong ICP company WITHOUT contact -> NEEDS_ENRICHMENT
        comp_b = Company(
            name="Gujarat Heavy Engineering Ltd",
            normalized_name="gujarat heavy engineering",
            domain="ghe-ltd.com",
            website="https://www.ghe-ltd.com",
            city="Hazira",
            state="Gujarat",
            industry="Automotive Engineering",
            has_nabl=True,
            icp_score=60.0,
            calculated_tier="Compliance-Driven",
            qualification_status="RAW",
        )
        self.db.add(comp_b)
        self.db.commit()

        eval_b = evaluate_lead_qualification(self.db, comp_b.id)
        self.assertEqual(eval_b["qualification_status"], "NEEDS_ENRICHMENT")

        # Case C: Trading company -> DISQUALIFIED
        comp_c = Company(
            name="Shreeji Trading Corporation",
            normalized_name="shreeji trading",
            domain="shreejitraders.com",
            city="Ahmedabad",
            state="Gujarat",
            industry="Trading",
            icp_score=10.0,
            calculated_tier="Low Potential",
            qualification_status="RAW",
        )
        self.db.add(comp_c)
        self.db.commit()

        eval_c = evaluate_lead_qualification(self.db, comp_c.id)
        self.assertEqual(eval_c["qualification_status"], "DISQUALIFIED")

        # Case D: Manual Override
        set_res = set_qualification_status(self.db, comp_b.id, "QUALIFIED", "Manually approved by sales lead")
        self.assertEqual(set_res["qualification_status"], "QUALIFIED")


if __name__ == "__main__":
    unittest.main()
