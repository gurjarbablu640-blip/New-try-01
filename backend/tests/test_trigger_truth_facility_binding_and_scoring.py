"""Tests for Trigger Truth, Recency, Facility Binding, Calibration Classification, Decompressed Scoring, and Benchmark Cap.

Covers Phases 5, 6, 7, 8, 9, 10 of Salesoorja Autonomous Quality Recovery Run.
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

from services.trigger_discovery_service import (
    evaluate_event_semantics,
    extract_event_date,
    bind_trigger_to_facility,
    classify_calibration_opportunity,
    compute_lead_qualification_score,
    TRIGGER_FACILITY_DIRECT,
    TRIGGER_FACILITY_STRONG,
    TRIGGER_FACILITY_AMBIGUOUS,
    TRIGGER_FACILITY_NONE,
    CALIBRATION_SOURCE_SUPPORTED,
    CALIBRATION_REASONABLE_INFERENCE,
)
from services.serper_budget_manager import (
    SerperDailyBudgetManager,
    SerperBudgetExhaustedError,
)


# ── Phase 5: Trigger Truth & Static Page Rejection ────────────────────────────
class TestTriggerTruthAndStaticRejection:
    def test_static_company_profile_rejected_as_static_reference(self):
        text = "Welcome to ABC Forgings. We are a leading manufacturer of automotive components established in 1985. Our corporate office is in Mumbai."
        res = evaluate_event_semantics(text, title="ABC Forgings - About Us & Company Profile")
        assert res["is_verified"] is False
        assert res["is_valid"] is False
        assert res["is_valid_event"] is False
        assert res["trigger_type"] == "STATIC_REFERENCE"
        assert res["score"] == 0.0

    def test_directory_listing_rejected_as_static_reference(self):
        text = "Find contact details, address, and product overview for XYZ Precision on IndiaMART directory listing. Registered office Pune."
        res = evaluate_event_semantics(text, title="XYZ Precision - IndiaMART Listing")
        assert res["is_verified"] is False
        assert res["trigger_type"] == "STATIC_REFERENCE"

    def test_real_plant_expansion_verified(self):
        text = "Tata Motors announces capital expenditure of Rs 2,000 crore to expand manufacturing capacity at its Sanand facility."
        res = evaluate_event_semantics(text, title="Tata Motors announces capex for Sanand plant")
        assert res["is_verified"] is True
        assert res["is_valid"] is True
        assert res["trigger_type"] in ("CAPACITY_EXPANSION", "PLANT_EXPANSION")
        assert res["score"] >= 0.9

    def test_commissioning_and_new_line_verified(self):
        text = "Bharat Forge has commissioned its new automated machining line at Chakan works."
        res = evaluate_event_semantics(text, title="Bharat Forge commissions new line")
        assert res["is_verified"] is True
        assert res["trigger_type"] in ("COMMISSIONING", "NEW_LINE")

    def test_quality_hiring_verified(self):
        text = "Urgently hiring Plant Quality Assurance Manager and Metrology Engineer for precision machining plant in Hosur."
        res = evaluate_event_semantics(text, title="Hiring Quality Engineer - Hosur")
        assert res["is_verified"] is True
        assert res["trigger_type"] in ("QUALITY_HIRING", "METROLOGY_HIRING")


# ── Phase 6: Recency Hardening & Date Truth ───────────────────────────────────
class TestRecencyHardening:
    def test_undated_page_returns_unknown_date_no_fallback(self):
        text = "Company announces ongoing manufacturing expansion across western India facilities."
        res = extract_event_date(text, title="Manufacturing Expansion Update")
        assert res["has_date"] is False
        assert res["trigger_date"] == "UNKNOWN_DATE"
        assert res["date_str"] == "UNKNOWN_DATE"
        assert res["recency_tier"] == "DATE_UNKNOWN"
        assert res["recency_days"] == 999

    def test_copyright_date_filtered_and_not_treated_as_event_date(self):
        text = "Leading manufacturer of machined components in Sanand.\n© 2026 Precision Tech Ltd. All rights reserved. Privacy policy and Terms of use."
        res = extract_event_date(text, title="Precision Tech Sanand Plant Overview")
        assert res["has_date"] is False
        assert res["trigger_date"] == "UNKNOWN_DATE"

    def test_current_date_within_180_days(self):
        ref_date = datetime(2026, 9, 12, tzinfo=timezone.utc)
        text = "On 15 July 2026, the company commenced commercial production at its new facility."
        res = extract_event_date(text, now_dt=ref_date)
        assert res["has_date"] is True
        assert res["recency_status"] == "CURRENT"
        assert res["recency_days"] < 180

    def test_stale_date_over_365_days(self):
        ref_date = datetime(2026, 9, 12, tzinfo=timezone.utc)
        text = "The facility was inaugurated on 10 January 2024 by state officials."
        res = extract_event_date(text, now_dt=ref_date)
        assert res["has_date"] is True
        assert res["recency_status"] == "STALE"
        assert res["recency_days"] > 365


# ── Phase 7: Trigger + Facility Binding ───────────────────────────────────────
class TestTriggerFacilityBinding:
    def test_direct_match_exact_plant_and_city(self):
        text = "Tata Motors to invest Rs 1,300 crore in its Sanand manufacturing plant for EV assembly."
        res = bind_trigger_to_facility(text, target_facility="Sanand Plant", target_city="Sanand", target_state="Gujarat")
        assert res["linkage"] == TRIGGER_FACILITY_DIRECT
        assert res["is_bound"] is True
        assert res["confidence"] == "HIGH"

    def test_conflicting_location_mismatch_detected(self):
        # Target facility is Sanand, but trigger is about Dharwad expansion
        text = "Tata Motors begins Rs 500 crore expansion at its Dharwad commercial vehicle facility."
        res = bind_trigger_to_facility(text, target_facility="Sanand Plant", target_city="Sanand", target_state="Gujarat")
        assert res["linkage"] == TRIGGER_FACILITY_AMBIGUOUS
        assert res["is_bound"] is False
        assert "Dharwad" in res["conflicting_locations"]

    def test_rr_kabel_baddi_vs_waghodia_mismatch(self):
        text = "RR Kabel inaugurates new wire and cable manufacturing unit in Baddi industrial area."
        res = bind_trigger_to_facility(text, target_facility="Waghodia Unit", target_city="Waghodia", target_state="Gujarat")
        assert res["linkage"] == TRIGGER_FACILITY_AMBIGUOUS
        assert res["is_bound"] is False
        assert "Baddi" in res["conflicting_locations"]

    def test_neither_facility_nor_city_mentioned(self):
        text = "Company reports quarterly revenue growth across consumer electricals division."
        res = bind_trigger_to_facility(text, target_facility="Chakan Works", target_city="Pune", target_state="Maharashtra")
        assert res["linkage"] == TRIGGER_FACILITY_NONE
        assert res["is_bound"] is False


# ── Phase 8: Calibration Opportunity Truth ───────────────────────────────────
class TestCalibrationOpportunityTruth:
    def test_source_supported_calibration_opportunity(self):
        text = "New quality inspection lab equipped with high-precision CMM, air gauges, and digital torque wrenches."
        res = classify_calibration_opportunity(trigger_snippet=text, sector="Automotive")
        assert res["calibration_evidence_type"] == CALIBRATION_SOURCE_SUPPORTED
        assert res["is_source_supported"] is True
        assert "cmm" in res["supported_instruments"]
        assert "torque wrench" in res["supported_instruments"]

    def test_sector_inferred_opportunity_has_explicit_disclaimer(self):
        text = "Company expands powertrain assembly capacity by 50%."
        res = classify_calibration_opportunity(trigger_snippet=text, sector="Automotive")
        assert res["calibration_evidence_type"] == CALIBRATION_REASONABLE_INFERENCE
        assert res["is_source_supported"] is False
        assert "exact instrument scope requires confirmation" in res["calibration_description"]
        assert "automotive" in res["calibration_description"].lower()


# ── Phase 9: Scoring Decompression & Bands ────────────────────────────────────
class TestScoringDecompression:
    def test_p1_reachable_for_flawless_lead(self):
        trigger = {
            "is_valid": True,
            "trigger_type": "COMMISSIONING",
            "recency_tier": "CURRENT",
            "source_tier": "TIER_A",
            "facility_relationship": "DIRECT",
        }
        person = {
            "name": "Krishna Kumar Jha",
            "current_employment": "VERIFIED",
            "facility_relationship": "FACILITY_OWNER",
            "authority_class": "STRONG_PLANT_QUALITY_OWNER",
            "person_confidence": "HIGH",
            "person_score": 85.0,
        }
        binding = {"linkage": TRIGGER_FACILITY_DIRECT}
        score, band, status, reasons = compute_lead_qualification_score(trigger, person, binding, "Forging")
        assert score >= 95.0
        assert band == "P1"
        assert status == "READY_FOR_CONTACT_ENRICHMENT"

    def test_p2_reachable_for_strong_lead(self):
        trigger = {
            "is_valid": True,
            "trigger_type": "CAPACITY_EXPANSION",
            "recency_tier": "CURRENT",
            "source_tier": "TIER_B",
            "facility_relationship": "STRONG",
        }
        person = {
            "name": "Dharmendra Chouhan",
            "current_employment": "PROBABLE",
            "facility_relationship": "FACILITY_OWNER",
            "authority_class": "STRONG_PLANT_QUALITY_OWNER",
            "person_confidence": "HIGH",
            "person_score": 82.0,
        }
        binding = {"linkage": TRIGGER_FACILITY_STRONG}
        score, band, status, reasons = compute_lead_qualification_score(trigger, person, binding, "Auto Components")
        assert 90.0 <= score <= 94.0
        assert band == "P2"
        assert status == "READY_FOR_CONTACT_ENRICHMENT"

    def test_p3_reachable_for_qualified_group_contact(self):
        trigger = {
            "is_valid": True,
            "trigger_type": "CAPACITY_EXPANSION",
            "recency_tier": "RECENT",
            "has_ongoing": True,
            "source_tier": "TIER_B",
            "facility_relationship": "STRONG",
        }
        person = {
            "name": "Saurabh Gupta",
            "current_employment": "VERIFIED",
            "facility_relationship": "GROUP_FUNCTION_OWNER",
            "authority_class": "GROUP_FUNCTION_OWNER",
            "person_confidence": "MEDIUM",
            "person_score": 78.0,
        }
        binding = {"linkage": TRIGGER_FACILITY_STRONG}
        score, band, status, reasons = compute_lead_qualification_score(trigger, person, binding, "Automotive")
        assert 85.0 <= score <= 89.0
        assert band == "P3"
        assert status == "GROUP_LEVEL_CONTACT"

    def test_p3_reachable_for_plant_contact(self):
        trigger = {
            "is_valid": True,
            "trigger_type": "CAPACITY_EXPANSION",
            "recency_tier": "RECENT",
            "has_ongoing": True,
            "source_tier": "TIER_B",
            "facility_relationship": "STRONG",
        }
        person = {
            "name": "Ravi Singh",
            "current_employment": "PROBABLE",
            "facility_relationship": "FACILITY_FUNCTION_OWNER",
            "authority_class": "STRONG_PLANT_QUALITY_OWNER",
            "person_confidence": "MEDIUM",
            "person_score": 78.0,
        }
        binding = {"linkage": TRIGGER_FACILITY_STRONG}
        score, band, status, reasons = compute_lead_qualification_score(trigger, person, binding, "Automotive")
        assert 85.0 <= score <= 89.0
        assert band == "P3"
        assert status == "READY_FOR_CONTACT_ENRICHMENT"

    def test_hold_when_person_employment_is_contradicted(self):
        # Schneider / Himanshu Sharma case
        trigger = {
            "is_valid": True,
            "trigger_type": "CAPACITY_EXPANSION",
            "recency_tier": "CURRENT",
            "source_tier": "TIER_A",
            "facility_relationship": "DIRECT",
        }
        person = {
            "name": "Himanshu Sharma",
            "current_employment": "CONTRADICTED",
            "facility_relationship": "FACILITY_OWNER",
            "authority_class": "STRONG_PLANT_QUALITY_OWNER",
            "person_confidence": "LOW",
            "person_score": 30.0,
        }
        binding = {"linkage": TRIGGER_FACILITY_DIRECT}
        score, band, status, reasons = compute_lead_qualification_score(trigger, person, binding, "Electrical")
        assert score < 85.0
        assert band == "HOLD"
        assert status == "HOLD_PERSON_CONTRADICTED"

    def test_hold_when_facility_mismatch(self):
        # Tata Motors Sanand vs Avijit Sen Dharwad case
        trigger = {
            "is_valid": True,
            "trigger_type": "CAPACITY_EXPANSION",
            "recency_tier": "CURRENT",
            "source_tier": "TIER_A",
            "facility_relationship": "DIRECT",
        }
        person = {
            "name": "Avijit Sen",
            "current_employment": "VERIFIED",
            "facility_relationship": "OTHER_FACILITY_OWNER",
            "authority_class": "STRONG_PLANT_QUALITY_OWNER",
            "person_confidence": "LOW",
            "person_score": 50.0,
        }
        binding = {"linkage": TRIGGER_FACILITY_DIRECT}
        score, band, status, reasons = compute_lead_qualification_score(trigger, person, binding, "Automotive")
        assert score < 85.0
        assert band == "HOLD"
        assert status == "HOLD_FACILITY_MISMATCH"


# ── Phase 10: Benchmark Request Cap ───────────────────────────────────────────
class TestBenchmarkHardRequestCap:
    def test_benchmark_cap_blocks_excess_requests(self, tmp_path):
        state_file = str(tmp_path / "budget_state.json")
        mgr = SerperDailyBudgetManager(state_path=state_file, daily_limit=1500)
        
        # Configure a strict benchmark budget of 10 requests
        mgr.set_benchmark_run_budget(10)
        status = mgr.get_benchmark_run_status()
        assert status["benchmark_run_limit"] == 10
        assert status["benchmark_requests_used"] == 0
        assert status["is_benchmark_active"] is True

        # First 10 requests must succeed
        for i in range(10):
            assert mgr.can_request() is True
            assert mgr.reserve_request(1) is True

        # 11th request must be blocked
        assert mgr.can_request() is False
        with pytest.raises(SerperBudgetExhaustedError) as exc_info:
            mgr.reserve_request(1)
        assert "benchmark run budget exhausted" in str(exc_info.value).lower()

        # Confirm production daily budget of 1500 was not altered
        assert mgr.daily_limit == 1500
        assert mgr.live_requests_today == 10

        # Clearing benchmark budget restores ability to request against daily limit
        mgr.set_benchmark_run_budget(None)
        assert mgr.can_request() is True
        assert mgr.reserve_request(1) is True
        assert mgr.live_requests_today == 11
