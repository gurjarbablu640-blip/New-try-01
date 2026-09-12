"""Regression tests for authoritative forensic positive and negative controls.

Verifies:
1. Ramkrishna Forgings / Krishna Kumar Jha -> HIGH / READY_FOR_CONTACT_ENRICHMENT (NOT ready for email)
2. Shyam Metalics -> HOLD_FACILITY_AMBIGUOUS (multi-facility / ambiguous capex)
3. Schneider Electric / Himanshu Sharma -> HOLD_PERSON_CONTRADICTED (must NOT qualify)
4. Tata Motors / Avijit Sen for Sanand -> HOLD_FACILITY_MISMATCH (must NOT qualify, at Dharwad)
5. RR Kabel / Praveen Kumar for Waghodia -> HOLD_FACILITY_MISMATCH (must NOT qualify, at Baddi)
"""
import pytest
from services.person_intelligence_service import (
    classify_current_employment,
    classify_facility_relationship,
    classify_authority_class,
)
from services.trigger_discovery_service import (
    bind_trigger_to_facility,
    compute_lead_qualification_score,
    TRIGGER_FACILITY_DIRECT,
    TRIGGER_FACILITY_STRONG,
    TRIGGER_FACILITY_AMBIGUOUS,
    TRIGGER_FACILITY_NONE,
)


class TestForensicAuthoritativeControls:
    def test_control_1_ramkrishna_forgings_positive_control(self):
        """Ramkrishna Forgings / Krishna Kumar Jha must qualify as P1 / READY_FOR_CONTACT_ENRICHMENT."""
        trigger = {
            "is_valid": True,
            "trigger_type": "COMMISSIONING",
            "recency_tier": "CURRENT",
            "source_tier": "TIER_A",
            "facility_relationship": "DIRECT",
            "discovered_facility": "Jamshedpur Plant V",
            "discovered_city": "Jamshedpur",
            "discovered_state": "jharkhand",
        }
        person = {
            "name": "Krishna Kumar Jha",
            "current_employment": "VERIFIED",
            "facility_relationship": "FACILITY_OWNER",
            "authority_class": "STRONG_PLANT_QUALITY_OWNER",
            "person_confidence": "HIGH",
            "person_score": 88.0,
        }
        binding = {
            "linkage": TRIGGER_FACILITY_DIRECT,
            "target_facility": "Jamshedpur Plant V",
            "target_city": "Jamshedpur",
        }
        score, band, status, reasons = compute_lead_qualification_score(
            trigger, person, binding, "Forging"
        )
        assert score >= 95.0
        assert band == "P1"
        assert status == "READY_FOR_CONTACT_ENRICHMENT"
        assert len(reasons) == 0

    def test_control_2_shyam_metalics_ambiguous_facility_control(self):
        """Shyam Metalics capex announced across multiple sites must yield HOLD_FACILITY_AMBIGUOUS."""
        snippet = "Shyam Metalics announced Rs 2,700 crore capex across Sambalpur and Jamuria facilities."
        binding = bind_trigger_to_facility(
            snippet,
            target_facility="Jamuria Plant",
            target_city="Jamuria",
            target_state="west bengal",
        )
        # Multi-location compound capex is ambiguous
        trigger = {
            "is_valid": True,
            "trigger_type": "CAPACITY_EXPANSION",
            "recency_tier": "CURRENT",
            "source_tier": "TIER_A",
            "facility_relationship": "AMBIGUOUS",
            "discovered_facility": "Jamuria Plant",
            "discovered_city": "Jamuria",
        }
        person = {
            "name": "Subir Mukherjee",
            "current_employment": "VERIFIED",
            "facility_relationship": "FACILITY_FUNCTION_OWNER",
            "authority_class": "STRONG_PLANT_QUALITY_OWNER",
            "person_confidence": "MEDIUM",
            "person_score": 80.0,
        }
        score, band, status, reasons = compute_lead_qualification_score(
            trigger, person, {"linkage": TRIGGER_FACILITY_AMBIGUOUS, "reason": "Compound capex across Sambalpur and Jamuria"}, "Steel"
        )
        assert band == "HOLD"
        assert status == "HOLD_FACILITY_AMBIGUOUS"

    def test_control_3_schneider_himanshu_sharma_past_employment(self):
        """Schneider Electric / Himanshu Sharma left in 2009 -> CONTRADICTED -> HOLD_PERSON_CONTRADICTED."""
        evidence = (
            "Himanshu Sharma - Head of Electrical Quality at ABB India. "
            "Experience: Schneider Electric (Jan 2007 - Nov 2009 · 2 yrs 11 mos) QA Lead."
        )
        emp_status = classify_current_employment("Head of Electrical Quality at ABB India", evidence, "Schneider Electric")
        assert emp_status == "CONTRADICTED"

        trigger = {
            "is_valid": True,
            "trigger_type": "CAPACITY_EXPANSION",
            "recency_tier": "CURRENT",
            "source_tier": "TIER_A",
            "facility_relationship": "DIRECT",
            "discovered_city": "Vadodara",
        }
        person = {
            "name": "Himanshu Sharma",
            "current_employment": emp_status,
            "facility_relationship": "FACILITY_OWNER",
            "authority_class": "STRONG_PLANT_QUALITY_OWNER",
            "person_confidence": "LOW",
            "person_score": 35.0,
        }
        score, band, status, reasons = compute_lead_qualification_score(
            trigger, person, {"linkage": TRIGGER_FACILITY_DIRECT}, "Electrical"
        )
        assert band == "HOLD"
        assert status == "HOLD_PERSON_CONTRADICTED"
        assert score < 85.0

    def test_control_4_tata_motors_avijit_sen_facility_mismatch(self):
        """Tata Motors / Avijit Sen is QA Head at Dharwad, target is Sanand -> HOLD_FACILITY_MISMATCH."""
        candidate_text = "Avijit Sen - Quality Head at Tata Motors Dharwad Plant, Karnataka"
        fac_rel = classify_facility_relationship(
            candidate_title="Quality Head",
            candidate_text=candidate_text,
            target_facility="Sanand Plant",
            target_city="Sanand",
            target_state="gujarat",
        )
        assert fac_rel in ("OTHER_FACILITY_OWNER", "FACILITY_CONTRADICTED")

        trigger = {
            "is_valid": True,
            "trigger_type": "NEW_LINE",
            "recency_tier": "CURRENT",
            "source_tier": "TIER_A",
            "facility_relationship": "DIRECT",
            "discovered_city": "Sanand",
        }
        person = {
            "name": "Avijit Sen",
            "current_employment": "VERIFIED",
            "facility_relationship": fac_rel,
            "authority_class": "STRONG_PLANT_QUALITY_OWNER",
            "person_confidence": "LOW",
            "person_score": 50.0,
        }
        score, band, status, reasons = compute_lead_qualification_score(
            trigger, person, {"linkage": TRIGGER_FACILITY_DIRECT, "target_city": "Sanand"}, "Automotive"
        )
        assert band == "HOLD"
        assert status == "HOLD_FACILITY_MISMATCH"
        assert score < 85.0

    def test_control_5_rr_kabel_praveen_kumar_facility_mismatch(self):
        """RR Kabel / Praveen Kumar is at Baddi, target is Waghodia -> HOLD_FACILITY_MISMATCH."""
        candidate_text = "Praveen Kumar - Plant Quality Head at RR Kabel Baddi Plant, Himachal Pradesh"
        fac_rel = classify_facility_relationship(
            candidate_title="Plant Quality Head",
            candidate_text=candidate_text,
            target_facility="Waghodia Facility",
            target_city="Waghodia",
            target_state="gujarat",
        )
        assert fac_rel in ("OTHER_FACILITY_OWNER", "FACILITY_CONTRADICTED")

        trigger = {
            "is_valid": True,
            "trigger_type": "CAPACITY_EXPANSION",
            "recency_tier": "CURRENT",
            "source_tier": "TIER_A",
            "facility_relationship": "DIRECT",
            "discovered_city": "Waghodia",
        }
        person = {
            "name": "Praveen Kumar",
            "current_employment": "VERIFIED",
            "facility_relationship": fac_rel,
            "authority_class": "STRONG_PLANT_QUALITY_OWNER",
            "person_confidence": "LOW",
            "person_score": 50.0,
        }
        score, band, status, reasons = compute_lead_qualification_score(
            trigger, person, {"linkage": TRIGGER_FACILITY_DIRECT, "target_city": "Waghodia"}, "Cables"
        )
        assert band == "HOLD"
        assert status == "HOLD_FACILITY_MISMATCH"
        assert score < 85.0
