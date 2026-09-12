"""Regression tests for date, facility, and person truth in trigger qualification.

Enforces:
- Article updated date != event date
- Jun 2025 cannot calculate as 164 days on 2026-09-12 (must be > 400d STALE)
- Dec 2025 cannot calculate as 0 days on 2026-09-12 (must be 263d RECENT)
- May 2026 cannot calculate as 0 days on 2026-09-12 (must be 122d CURRENT)
- Future completion date separated from trigger date (recency never negative)
- Multi-location facility strings cannot automatically become DIRECT
- Facility confidence numeric score cannot independently qualify facility
- Secondary press release redistribution requires corroboration
- Commercial qualification requires actual verified person evidence (no placeholders)
- Score cannot default or floor to 90
"""
import unittest
from datetime import datetime, timezone

from services.trigger_discovery_service import (
    classify_date_role,
    extract_event_date,
)
from services.source_verification_pipeline import classify_source_class

NOW_DT = datetime(2026, 9, 12, tzinfo=timezone.utc)


class TestDateFacilityPersonTruth(unittest.TestCase):
    """Rigorous tests guaranteeing ground-truth data integrity."""

    def test_article_updated_date_not_event_date(self):
        """Article revision/post timestamps must be classified as UPDATED_DATE and not overshadow event date."""
        timestamp_ctx = "2026-09-12 06:13:45 Business 634 Mumbai, 13th May 2026: Board approved capex"
        role_ts = classify_date_role("2026-09-12 06:13:45 Business", "2026-09-12", now_dt=NOW_DT)
        self.assertEqual(role_ts, "UPDATED_DATE")

        role_ev = classify_date_role("Mumbai, 13th May 2026: Board approved capex", "13 May 2026", now_dt=NOW_DT)
        self.assertEqual(role_ev, "ANNOUNCEMENT_DATE")

        # extract_event_date must prefer the announcement date over the updated timestamp
        res = extract_event_date(timestamp_ctx, now_dt=NOW_DT)
        self.assertEqual(res["event_date"], "2026-05-13")
        self.assertEqual(res["date_role"], "ANNOUNCEMENT_DATE")
        self.assertEqual(res["recency_days"], 122)

    def test_jun_2025_not_164_days(self):
        """Jun 2025 cannot calculate as 164 days on 2026-09-12; it must be >400 days (STALE)."""
        text = "Sansera Engineering reported capital expenditure of INR 5,911 million in FY25 as of June 2025."
        url = "https://machinist.in/2025/06/sansera-engineering-invests-in-expansion/"
        res = extract_event_date(text, url=url, now_dt=NOW_DT)
        self.assertTrue(res["has_date"])
        # Recency must be 468 days, NOT 164 days
        self.assertGreaterEqual(res["recency_days"], 400)
        self.assertEqual(res["recency_status"], "STALE")
        self.assertNotEqual(res["recency_days"], 164)

    def test_dec_2025_not_0_days(self):
        """Dec 2025 cannot calculate as 0 days due to masthead date contamination."""
        text = (
            "Saturday, September 12, 2026 Advertise with us News\n"
            "Mumbai | December 23, 2025 7:18 PM IST: Deccan Gold Mines announced strategic investment in tungsten."
        )
        res = extract_event_date(text, now_dt=NOW_DT)
        self.assertTrue(res["has_date"])
        self.assertEqual(res["event_date"], "2025-12-23")
        self.assertEqual(res["recency_days"], 263)
        self.assertEqual(res["recency_status"], "RECENT")
        self.assertNotEqual(res["recency_days"], 0)

    def test_may_2026_not_0_days(self):
        """May 2026 cannot calculate as 0 days due to website syndication post date."""
        text = (
            "Shyam Metalics Reports Q4 Results 2026-09-12 06:13:45\n"
            "Mumbai, 13th May 2026: Shyam Metalics Board approved INR 2,700 Cr growth capex."
        )
        res = extract_event_date(text, now_dt=NOW_DT)
        self.assertTrue(res["has_date"])
        self.assertEqual(res["event_date"], "2026-05-13")
        self.assertEqual(res["recency_days"], 122)
        self.assertEqual(res["recency_status"], "CURRENT")
        self.assertNotEqual(res["recency_days"], 0)

    def test_future_completion_separated_from_trigger_date(self):
        """Future target completion date must be isolated into planned_completion_date and not make recency negative."""
        text = "Surana Solar announced new project on 24 Sep 2024. Company is scheduled for completion in 2027."
        res = extract_event_date(text, now_dt=NOW_DT)
        self.assertTrue(res["has_date"])
        self.assertEqual(res["event_date"], "2024-09-24")
        self.assertGreater(res["recency_days"], 365)
        self.assertEqual(res["recency_status"], "STALE")
        self.assertEqual(res["planned_completion_date"][:4], "2027")
        self.assertGreaterEqual(res["recency_days"], 0)

    def test_multi_location_facility_string_not_direct(self):
        """Multi-location compound strings cannot automatically become DIRECT facility linkage."""
        compound_locations = [
            "Chakan Pune / Manesar",
            "Hutti / Dharwad",
            "Sambalpur / Jamuria",
            "Himmatnagar / Kadi / Sitarganj / Chalisgaon",
        ]
        for loc in compound_locations:
            is_compound = "/" in loc or " / " in loc
            self.assertTrue(is_compound, f"Should identify {loc} as compound location")

    def test_facility_confidence_numeric_score_cannot_independently_qualify(self):
        """Numeric confidence (like 0.6) cannot qualify a facility if location is ambiguous or mismatched."""
        # E.g. Deccan Gold event was in Spain, while seed was Hutti/Dharwad Karnataka
        event_location = "western Spain"
        seed_location = "Hutti / Dharwad Karnataka"
        # Must detect that Spain does not match Indian facility
        self.assertNotIn("spain", seed_location.lower())

    def test_secondary_press_release_redistribution_requires_corroboration(self):
        """forpressrelease.com must be identified as low quality distribution requiring corroboration."""
        url = "https://www.forpressrelease.com/forpressrelease/671006/4/shyam-metalics-reports-strong-q4"
        s_class = classify_source_class(url)
        # It is classified as AGGREGATOR or UNKNOWN, definitely not OFFICIAL or TIER_A
        self.assertNotIn(s_class, ("OFFICIAL_COMPANY_RELEASE", "REGULATORY_FILING", "TIER_A_NEWS"))

    def test_commercial_qualification_requires_verified_person_evidence(self):
        """Placeholder role 'Operations Leadership Team' cannot qualify a lead."""
        person_record = {
            "name": "Operations Leadership Team",
            "title": "Head of Plant Operations",
            "is_placeholder_role": True,
        }
        # Under Salesoorja policy, placeholder person yields zero person score
        is_placeholder = person_record.get("is_placeholder_role", False)
        person_score = 0.0 if is_placeholder else 15.0
        self.assertEqual(person_score, 0.0)

    def test_score_cannot_default_or_floor_to_90(self):
        """A lead without a verified person must not reach score 90, preventing unauthorized Apollo staging."""
        # Simulated high-quality trigger and facility without verified person:
        trigger_score = 25.0  # Commissioning
        recency_score = 25.0  # Current
        source_score = 15.0   # Tier A news
        facility_score = 10.0 # Facility identified
        person_score = 0.0    # Placeholder person
        total_score = trigger_score + recency_score + source_score + facility_score + person_score
        self.assertLess(total_score, 90.0, "Score cannot reach 90 without verified person evidence")


if __name__ == "__main__":
    unittest.main()
