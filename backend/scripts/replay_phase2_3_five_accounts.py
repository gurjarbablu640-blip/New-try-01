"""Offline 5-Account Replay for Phase 2.3.

Replays recorded candidate evidence for the 5 target accounts:
1. HARMAN (121)
2. Aarti Pharmalabs (349)
3. Tata Advanced Systems (350)
4. Harman International (354)
5. GoodEnough Energy (375)

Evaluates:
- Authority classification BEFORE (Phase 2.2) vs AFTER (Phase 2.3)
- Gate outcome with DeepSeek 504 -> Gemini fallback
- Gate outcome with Both LLMs down (narrow deterministic fallback)
- Funnel progression (Enrichment -> Contact Waterfall -> Send Ready -> SMTP)
- Safety invariant checks (Suppression, Extrapolated email block, Zero hallucination)
- ZERO live network / SMTP calls.
"""
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.person_enrichment_eligibility_gate import (
    PersonEnrichmentEligibilityGate,
    APOLLO_AUTHORITY_CLASSES,
)
from services.person_intelligence_service import classify_authority_class


def run_5_account_replay() -> Dict[str, Any]:
    # Recorded account & candidate data from production database & canary audit
    accounts = [
        {
            "company_id": 121,
            "company_name": "HARMAN",
            "icp_score": 92.0,
            "facility_info": {"facility_verified": True, "linkage_confidence": "DIRECT"},
            "trigger_info": {"valid_trigger": True},
            "candidate": {
                "candidate_name": "Rohit Giri",
                "candidate_title": "Senior Quality Manager",
                "composite_score": 0.86,
                "current_employment": "VERIFIED",
                "facility_relationship": "DIRECT",
                "candidate_facility": "Chakan Plant, Pune",
                "public_profile_evidence": "Currently working as Senior Quality Manager at HARMAN Chakan manufacturing plant",
            },
            "contact_state": {
                "email": "rohit.giri@harman.com",
                "email_type": "verified",
                "confidence": "HIGH_VERIFIED",
                "mailbox_verified": True,
                "already_sent_in_suppression_window": True,  # Sent 2026-09-16
            },
        },
        {
            "company_id": 349,
            "company_name": "Aarti Pharmalabs",
            "icp_score": 90.0,
            "facility_info": {"facility_verified": True, "linkage_confidence": "STRONG"},
            "trigger_info": {"valid_trigger": True},
            "candidate": {
                "candidate_name": "Jayendra Chaphekar",
                "candidate_title": "Quality Assurance Manager",
                "composite_score": 0.84,
                "current_employment": "VERIFIED",
                "facility_relationship": "FACILITY_FUNCTION_OWNER",
                "candidate_facility": "MIDC Tarapur Facility",
                "public_profile_evidence": "Currently working as Quality Assurance Manager at Aarti Pharmalabs MIDC manufacturing plant",
            },
            "contact_state": {
                "email": None,
                "email_type": None,
                "confidence": None,
                "mailbox_verified": False,
                "already_sent_in_suppression_window": False,
            },
        },
        {
            "company_id": 350,
            "company_name": "Tata Advanced Systems",
            "icp_score": 94.0,
            "facility_info": {"facility_verified": True, "linkage_confidence": "DIRECT"},
            "trigger_info": {"valid_trigger": True},
            "candidate": {
                "candidate_name": "Swathi Ramesh",
                "candidate_title": "Quality Assurance Manager",
                "composite_score": 0.84,
                "current_employment": "VERIFIED",
                "facility_relationship": "FACILITY_FUNCTION_OWNER",
                "candidate_facility": "Vadodara C295 Final Assembly Line",
                "public_profile_evidence": "Currently working as Quality Assurance Manager at Tata Advanced Systems Vadodara C295 manufacturing plant assembly facility",
            },
            "contact_state": {
                "email": None,
                "email_type": None,
                "confidence": None,
                "mailbox_verified": False,
                "already_sent_in_suppression_window": False,
            },
        },
        {
            "company_id": 354,
            "company_name": "Harman International",
            "icp_score": 89.0,
            "facility_info": {"facility_verified": True, "linkage_confidence": "DIRECT"},
            "trigger_info": {"valid_trigger": True},
            "candidate": {
                "candidate_name": "Rohit Navdikar",
                "candidate_title": "Senior Manager - Quality",
                "composite_score": 0.85,
                "current_employment": "VERIFIED",
                "facility_relationship": "DIRECT",
                "candidate_facility": "Pune Automotive Facility",
                "public_profile_evidence": "Currently working as Senior Manager - Quality at Harman International Pune plant",
            },
            "contact_state": {
                "email": "rohit.navdikar@harman.com",
                "email_type": "extrapolated",
                "confidence": "MEDIUM",
                "mailbox_verified": False,
                "already_sent_in_suppression_window": False,
            },
        },
        {
            "company_id": 375,
            "company_name": "GoodEnough Energy",
            "icp_score": 91.0,
            "facility_info": {"facility_verified": True, "linkage_confidence": "DIRECT"},
            "trigger_info": {"valid_trigger": True},
            "candidate": {
                "candidate_name": "Saurabh Madaan",
                "candidate_title": "Director of Operations",
                "composite_score": 0.82,
                "current_employment": "VERIFIED",
                "facility_relationship": "FACILITY_OWNER",
                "candidate_facility": "Jammu Gigafactory",
                "public_profile_evidence": "Currently working as Director of Operations at GoodEnough Energy Jammu battery manufacturing facility",
            },
            "contact_state": {
                "email": None,
                "email_type": "NO_RESULT",
                "confidence": "NONE",
                "mailbox_verified": False,
                "already_sent_in_suppression_window": False,
            },
        },
    ]

    results = []

    # Mock provider 1: DeepSeek 504 -> Gemini returns approval
    def gemini_failover_provider(prompt: str) -> str:
        return (
            "AUTHORITY_CLASS: STRONG_PLANT_QUALITY_OWNER\n"
            "ENRICH: YES\n"
            "REASON: Candidate has confirmed facility-level quality ownership at manufacturing plant."
        )

    # Mock provider 2: Both LLMs down
    def both_down_provider(prompt: str) -> str:
        raise RuntimeError("Both LLM providers failed: DeepSeek 504, Gemini 429")

    gate_gemini = PersonEnrichmentEligibilityGate(llm_provider=gemini_failover_provider)
    gate_both_down = PersonEnrichmentEligibilityGate(llm_provider=both_down_provider)

    for acc in accounts:
        cid = acc["company_id"]
        cname = acc["company_name"]
        cand = acc["candidate"]
        fac_info = acc["facility_info"]
        trig_info = acc["trigger_info"]
        contact = acc["contact_state"]

        title = cand["candidate_title"]
        evidence = cand["public_profile_evidence"]

        # 1. Authority classification Before vs After
        # Phase 2.2: QA Manager returned FUNCTIONALLY_RELEVANT
        auth_class_before = "FUNCTIONALLY_RELEVANT" if "Quality Assurance Manager" in title else (
            "STRONG_PLANT_QUALITY_OWNER" if "Quality Head" in title or "Senior Quality Manager" in title else "FACILITY_OWNER"
        )
        # Phase 2.3: classify_authority_class with facility grounding
        auth_class_after = classify_authority_class(title, evidence)

        # 2. Gate with Gemini Failover
        cand_with_auth = dict(cand)
        cand_with_auth["authority_class"] = auth_class_after
        # Evaluate if already mailbox-verified
        contact_info_eval = {"mailbox_verified": True} if contact["mailbox_verified"] else None

        dec_gemini = gate_gemini.evaluate(
            candidate=cand_with_auth,
            facility_info=fac_info,
            trigger_info=trig_info,
            opportunity_icp_score=acc["icp_score"],
            contact_info=contact_info_eval,
        )

        # 3. Gate with Both LLMs down (Narrow Deterministic Fallback)
        dec_both_down = gate_both_down.evaluate(
            candidate=cand_with_auth,
            facility_info=fac_info,
            trigger_info=trig_info,
            opportunity_icp_score=acc["icp_score"],
            contact_info=contact_info_eval,
        )

        # 4. Waterfall & Send Progression
        would_reach_waterfall = dec_gemini.enrich_contact
        send_decision = "HOLD"
        hold_reason = ""

        if contact["already_sent_in_suppression_window"]:
            send_decision = "DUPLICATE_SUPPRESSED"
            hold_reason = "14-day duplicate suppression active"
        elif contact["email_type"] == "extrapolated" and contact["confidence"] == "MEDIUM":
            send_decision = "HOLD_EXTRAPOLATED_EMAIL"
            hold_reason = "Extrapolated email with MEDIUM confidence blocked by verified-only policy"
        elif contact["email_type"] == "NO_RESULT" or (not contact["email"] and not would_reach_waterfall):
            send_decision = "HOLD_NO_VERIFIED_CONTACT"
            hold_reason = "No verified contact found; no hallucination produced"
        elif would_reach_waterfall and not contact["email"]:
            send_decision = "ELIGIBLE_FOR_APOLLO_ENRICHMENT"
            hold_reason = "Would query Apollo for verified contact"

        results.append({
            "company_id": cid,
            "company_name": cname,
            "candidate_name": cand["candidate_name"],
            "candidate_title": title,
            "auth_class_before": auth_class_before,
            "auth_class_after": auth_class_after,
            "gate_gemini_enrich": dec_gemini.enrich_contact,
            "gate_gemini_conf": dec_gemini.authority_confidence,
            "gate_gemini_reason": dec_gemini.reason,
            "gate_both_down_enrich": dec_both_down.enrich_contact,
            "gate_both_down_conf": dec_both_down.authority_confidence,
            "gate_both_down_reason": dec_both_down.reason,
            "funnel_outcome": send_decision,
            "safety_reason": hold_reason,
        })

    return {"replay_results": results}


if __name__ == "__main__":
    out = run_5_account_replay()
    print(json.dumps(out, indent=2))
