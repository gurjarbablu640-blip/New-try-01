"""Unit and regression tests for Salesoorja Trigger Discovery Service."""
import unittest

from services.contact_confidence import is_human_person_candidate, validate_person_name
from services.trigger_discovery_service import (
    HIRING_TRIGGER_TYPES,
    SOURCE_TIER_A,
    SOURCE_TIER_B,
    SOURCE_TIER_C,
    SOURCE_TIER_D,
    TRIGGER_TYPES,
    classify_source_tier,
    event_semantics_verified,
    extract_event_date,
    extract_trigger_facility_link,
    generate_event_first_discovery_queries,
    generate_plant_specific_queries,
)


class TestTriggerDiscoveryService(unittest.TestCase):
    def test_non_human_person_goldi_style_extraction_rejected(self):
        """Goldi Solar as candidate name matching company name must be rejected."""
        is_human, reason = is_human_person_candidate("Goldi Solar", company_name="Goldi Solar Pvt Ltd")
        self.assertFalse(is_human)
        self.assertIn("matches company name", reason)

        val = validate_person_name("Goldi Solar", company_name="Goldi Solar Pvt Ltd")
        self.assertEqual(val["person_name_validation"], "INVALID_ROLE_TEXT")
        self.assertFalse(val["is_human_name"])

    def test_seo_article_title_as_person_rejected(self):
        """'Top Solar Panel Companies' must be rejected as non-human person candidate."""
        is_human, reason = is_human_person_candidate("Top Solar Panel Companies")
        self.assertFalse(is_human)

        val = validate_person_name("Top Solar Panel Companies")
        self.assertFalse(val["is_human_name"])

    def test_slogan_marketing_terms_rejected(self):
        """Marketing/slogan phrases like 'Trusted Partner', 'Solution Provider' must be rejected."""
        for phrase in ["Trusted Partner", "Solution Provider", "Turnkey Specialist", "Global Expert"]:
            is_human, reason = is_human_person_candidate(phrase)
            self.assertFalse(is_human, f"Should reject non-human phrase: {phrase}")
            val = validate_person_name(phrase)
            self.assertFalse(val["is_human_name"], f"validate_person_name should reject: {phrase}")

    def test_brand_division_names_rejected(self):
        """Company brand combinations like 'Mahindra Auto', 'Hyundai Cars', 'Ola Cabs' must be rejected."""
        test_cases = [
            ("Mahindra Auto", "Mahindra & Mahindra Limited"),
            ("Hyundai Cars", "Hyundai Motor India Limited"),
            ("Ola Cabs", "Ola Electric Mobility Limited"),
            ("Tata Motors", "Tata Motors Limited"),
            ("SONA Digital Ecosystem", "Sona BLW Precision Forgings Ltd"),
            ("I GOLDI", "Goldi Solar Private Limited"),
            ("Microsoft Community", "Dynamatic Technologies Limited"),
        ]
        for name, comp in test_cases:
            is_human, reason = is_human_person_candidate(name, company_name=comp)
            self.assertFalse(is_human, f"Should reject brand division: {name}")
            val = validate_person_name(name, company_name=comp)
            self.assertFalse(val["is_human_name"], f"validate_person_name should reject: {name}")

    def test_crore_plant_mother_plant_rejected_as_facility_names(self):
        """Quantifier or generic phrases like '320 crore plant' or 'its mother plant' must not become facility names."""
        res1 = extract_trigger_facility_link("Approved Rs 320 crore plant to enter passenger vehicle seating systems business.")
        self.assertNotEqual(res1.get("facility_name_from_trigger"), "Crore Plant")

        res2 = extract_trigger_facility_link("Expanded its mother plant in Mysore with new SMT line.")
        self.assertNotEqual(res2.get("facility_name_from_trigger"), "Its Mother Plant")

    def test_indian_names_with_initials_accepted(self):
        """Indian naming structures with single initials must be accepted."""
        for name in ["K S Mohan", "A K Banerjee", "M Senthilkumar", "Anil Patil", "Rohit Chaubey"]:
            is_human, reason = is_human_person_candidate(name)
            self.assertTrue(is_human, f"Failed for valid name: {name} ({reason})")
            val = validate_person_name(name)
            self.assertTrue(val["is_human_name"])

    def test_generic_company_page_not_a_trigger(self):
        """Generic statements like 'leading manufacturer' are NOT event triggers."""
        snippet = "We are a leading manufacturer of precision shock absorbers with manufacturing plants across India. Quality is our priority."
        is_event, trig_type, desc = event_semantics_verified(snippet, title="About Us - Gabriel India")
        self.assertFalse(is_event)
        self.assertEqual(trig_type, "UNKNOWN")

    def test_real_event_semantics_verified_expansion(self):
        """Actionable events like 'commissioned new line' are verified triggers."""
        snippet = "Kaynes Technology commissioned new assembly line at Sanand facility with capex of 200 crore."
        is_event, trig_type, desc = event_semantics_verified(snippet, title="Expansion Update")
        self.assertTrue(is_event)
        self.assertIn(trig_type, ("COMMISSIONING", "NEW_LINE", "CAPACITY_EXPANSION"))

    def test_hiring_signal_preserved_as_hiring_trigger_not_capex(self):
        """Current hiring for calibration/metrology is preserved as hiring trigger, NOT CAPEX."""
        snippet = "Varroc Engineering is hiring calibration engineer for Chakan plant standards room."
        is_event, trig_type, desc = event_semantics_verified(snippet, title="Job Vacancy")
        self.assertTrue(is_event)
        self.assertEqual(trig_type, "CALIBRATION_HIRING")
        self.assertIn(trig_type, HIRING_TRIGGER_TYPES)
        self.assertNotEqual(trig_type, "CAPACITY_EXPANSION")
        self.assertNotEqual(trig_type, "PLANT_EXPANSION")

    def test_stale_trigger_date_rejected(self):
        """Trigger from 2022 is STALE (>365 days)."""
        dt_res = extract_event_date("Published on 2022-04-15. Company announced expansion.")
        self.assertTrue(dt_res["has_date"])
        self.assertEqual(dt_res["ongoing_status"], "STALE")
        self.assertGreater(dt_res["recency_days"], 365)

    def test_current_trigger_date_accepted(self):
        """Trigger from 2026 is CURRENT (<=180 days)."""
        dt_res = extract_event_date("Published on 2026-08-10. Company inaugurated new facility.")
        self.assertTrue(dt_res["has_date"])
        self.assertEqual(dt_res["ongoing_status"], "CURRENT")
        self.assertLessEqual(dt_res["recency_days"], 180)

    def test_recency_364_days_is_recent(self):
        """364 days boundary test is RECENT."""
        from datetime import datetime, timezone, timedelta
        ref_dt = datetime(2026, 9, 12, tzinfo=timezone.utc)
        target_dt = ref_dt - timedelta(days=364)
        date_str = target_dt.strftime("%Y-%m-%d")
        dt_res = extract_event_date(f"Published on {date_str}. Event update.", now_dt=ref_dt)
        self.assertEqual(dt_res["recency_days"], 364)
        self.assertEqual(dt_res["recency_status"], "RECENT")

    def test_recency_366_days_is_stale(self):
        """366 days boundary test is STALE."""
        from datetime import datetime, timezone, timedelta
        ref_dt = datetime(2026, 9, 12, tzinfo=timezone.utc)
        target_dt = ref_dt - timedelta(days=366)
        date_str = target_dt.strftime("%Y-%m-%d")
        dt_res = extract_event_date(f"Published on {date_str}. Event update.", now_dt=ref_dt)
        self.assertEqual(dt_res["recency_days"], 366)
        self.assertEqual(dt_res["recency_status"], "STALE")

    def test_source_tier_classification(self):
        """Classify tiers: BSE/Official = A, Economic Times = B, Naukri = C, Generic = D."""
        self.assertEqual(classify_source_tier("https://www.bseindia.com/xml-data/corpfiling/1.pdf", "bseindia.com"), SOURCE_TIER_A)
        self.assertEqual(classify_source_tier("https://www.anandgroupindia.com/press-release", "anandgroupindia.com", "anandgroupindia.com"), SOURCE_TIER_A)
        self.assertEqual(classify_source_tier("https://economictimes.indiatimes.com/auto/1.cms", "economictimes.indiatimes.com"), SOURCE_TIER_B)
        self.assertEqual(classify_source_tier("https://www.naukri.com/job-listings-quality-chakan", "naukri.com"), SOURCE_TIER_C)
        self.assertEqual(classify_source_tier("https://www.anandgroupindia.com", "anandgroupindia.com", "anandgroupindia.com"), SOURCE_TIER_D)
        self.assertEqual(classify_source_tier("https://www.tofler.in/company/gabriel", "tofler.in"), SOURCE_TIER_D)

    def test_facility_specificity_extraction(self):
        """Extract exact facility, industrial area, and city specificity levels."""
        # 1. Exact facility
        res1 = extract_trigger_facility_link("Company inaugurated Chakan Plant in Pune.", known_plants=["Chakan Plant"])
        self.assertEqual(res1["trigger_facility_specificity"], "EXACT_FACILITY")

        # 2. Industrial area
        res2 = extract_trigger_facility_link("Investment at Sanand GIDC Phase II near Ahmedabad.", known_industrial_area="Sanand GIDC Phase II")
        self.assertEqual(res2["trigger_facility_specificity"], "INDUSTRIAL_AREA")

        # 3. City only
        res3 = extract_trigger_facility_link("Company announced expansion in Coimbatore.")
        self.assertEqual(res3["trigger_facility_specificity"], "CITY")

        # 4. Company only
        res4 = extract_trigger_facility_link("Company announced overall capex across its businesses.")
        self.assertEqual(res4["trigger_facility_specificity"], "COMPANY_ONLY")

    def test_event_first_discovery_queries_schema(self):
        """Event first discovery queries must return a non-empty list of targeted phrases."""
        queries = generate_event_first_discovery_queries()
        self.assertGreaterEqual(len(queries), 8)
        for q in queries:
            self.assertIn("India", q)
            self.assertTrue(any(yr in q for yr in ["2026", "September"]))


if __name__ == "__main__":
    unittest.main()
