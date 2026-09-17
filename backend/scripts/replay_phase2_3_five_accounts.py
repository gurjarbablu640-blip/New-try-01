"""Offline 5-Account Replay for Phase 2.3A (Truth Audit).

Uses ACTUAL recorded candidate evidence directly from production DB:
1. HARMAN (121) - Rohit Giri (Business Unit Head)
2. Aarti Pharmalabs (349) - Jayendra Chaphekar (Quality Assurance Manager)
3. Tata Advanced Systems (350) - Swathi Ramesh (Quality Assurance & Control Manager – C295)
4. Harman International (354) - Rohit Navdikar (Business Unit Head)
5. GoodEnough Energy (375) - Saurabh Madaan (Plant Head)

Evaluates:
- STORED_AUTHORITY (from historical database)
- RECOMPUTED_AUTHORITY (runtime classifier on actual title + evidence)
- LLM_AUTHORITY (when borderline requires semantic review)
- FINAL_AUTHORITY
- GATE_DECISION
- WOULD_REACH_WATERFALL
- WOULD_CALL_APOLLO
- REUSED_RESULT
- EMAIL_STATE
- EXPECTED_FINAL_OUTCOME
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
    # Exact recorded candidate data from production database
    accounts = [
        {
            "company_id": 121,
            "company_name": "HARMAN",
            "stored_authority": "FACILITY_OWNER",
            "icp_score": 95.0,
            "facility_info": {"facility_verified": True, "linkage_confidence": "DIRECT"},
            "trigger_info": {"valid_trigger": True},
            "candidate": {
                "candidate_name": "Rohit Giri",
                "candidate_title": "Business Unit Head",
                "composite_score": 0.95,
                "current_employment": "VERIFIED",
                "facility_relationship": "DIRECT",
                "candidate_facility": "HARMAN Pune Facility",
                "public_profile_evidence": "Currently working at HARMAN International as Business Unit Head. Rohit Giri. Business Unit Head at HARMAN. HARMAN International Savitribai Phule Pune University. Pune, Maharashtra, India.",
            },
            "contact_state": {
                "email": "rohit.giri@harman.com",
                "email_type": "verified",
                "confidence": "HIGH",
                "mailbox_verified": True,
                "already_sent_in_suppression_window": True,  # Sent 2026-09-16
            },
        },
        {
            "company_id": 349,
            "company_name": "Aarti Pharmalabs",
            "stored_authority": "FUNCTIONALLY_RELEVANT",
            "icp_score": 90.0,
            "facility_info": {"facility_verified": True, "linkage_confidence": "STRONG"},
            "trigger_info": {"valid_trigger": True},
            "candidate": {
                "candidate_name": "Jayendra Chaphekar",
                "candidate_title": "Quality Assurance Manager",
                "composite_score": 0.84,
                "current_employment": "VERIFIED",
                "facility_relationship": "FACILITY_FUNCTION_OWNER",
                "candidate_facility": "Aarti Pharmalabs Manufacturing Unit, Located At Midc",
                "public_profile_evidence": "Currently working at Aarti Pharmalabs Ltd. (APL) as Quality Assurance Manager. Jayendra Chaphekar. Ensuring Quality Product. Aarti Pharmalabs Ltd. (APL) Mumbai University Mumbai. Palghar, Maharashtra",
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
            "stored_authority": "FUNCTIONALLY_RELEVANT",
            "icp_score": 94.0,
            "facility_info": {"facility_verified": True, "linkage_confidence": "DIRECT"},
            "trigger_info": {"valid_trigger": True},
            "candidate": {
                "candidate_name": "Swathi Ramesh",
                "candidate_title": "Quality Assurance & Control Manager – C295 Aircraft Manufacturing | Aerospace Quality",
                "composite_score": 0.84,
                "current_employment": "VERIFIED",
                "facility_relationship": "FACILITY_FUNCTION_OWNER",
                "candidate_facility": "Tata Advanced Systems and Airbus Vadodara Facility",
                "public_profile_evidence": "Currently working at TATA Advanced Systems Limited as Quality Assurance & Control Manager – C295 Aircraft Manufacturing | Aerospace Quality. Swathi Ramesh · Officer (HR) | TATA Advanced Systems Ltd -",
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
            "stored_authority": "FACILITY_OWNER",
            "icp_score": 95.0,
            "facility_info": {"facility_verified": True, "linkage_confidence": "DIRECT"},
            "trigger_info": {"valid_trigger": True},
            "candidate": {
                "candidate_name": "Rohit Navdikar",
                "candidate_title": "Business Unit Head",
                "composite_score": 0.95,
                "current_employment": "VERIFIED",
                "facility_relationship": "DIRECT",
                "candidate_facility": "Pune Manufacturing Plant",
                "public_profile_evidence": "Currently working at HARMAN International as Business Unit Head. Rohit Navdikar. HARMAN International Savitribai Phule Pune University ... Rohit can introduce you to 10+ people at HARMAN International",
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
            "stored_authority": "FACILITY_OWNER",
            "icp_score": 95.0,
            "facility_info": {"facility_verified": True, "linkage_confidence": "DIRECT"},
            "trigger_info": {"valid_trigger": True},
            "candidate": {
                "candidate_name": "Saurabh Madaan",
                "candidate_title": "Plant Head",
                "composite_score": 0.95,
                "current_employment": "VERIFIED",
                "facility_relationship": "FACILITY_OWNER",
                "candidate_facility": "GoodEnough Energy Sector 8 / Phase II Industrial Area, Noida",
                "public_profile_evidence": "Currently working at GoodEnough Energy as Plant Head. Noida, Uttar Pradesh, India. Established in 2015 is 50 CR Company ... View Saurabh's full profile. Saurabh can introduce you to 3 people at GoodEn",
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

    # Mock provider: Gemini failover succeeds when called
    def mock_gemini_failover(prompt: str) -> str:
        return (
            "AUTHORITY_CLASS: STRONG_PLANT_QUALITY_OWNER\n"
            "ENRICH: YES\n"
            "REASON: Confirmed facility-level quality ownership at manufacturing plant."
        )

    gate = PersonEnrichmentEligibilityGate(llm_provider=mock_gemini_failover)

    for acc in accounts:
        cid = acc["company_id"]
        cname = acc["company_name"]
        cand = acc["candidate"]
        fac_info = acc["facility_info"]
        trig_info = acc["trigger_info"]
        contact = acc["contact_state"]
        stored_auth = acc["stored_authority"]

        title = cand["candidate_title"]
        evidence = cand["public_profile_evidence"]

        # 1. Recompute runtime authority class
        recomputed_auth = classify_authority_class(title, evidence)

        cand_eval = dict(cand)
        cand_eval["authority_class"] = recomputed_auth

        contact_info_eval = {"mailbox_verified": True} if contact["mailbox_verified"] else None

        dec = gate.evaluate(
            candidate=cand_eval,
            facility_info=fac_info,
            trigger_info=trig_info,
            opportunity_icp_score=acc["icp_score"],
            contact_info=contact_info_eval,
        )

        final_auth = recomputed_auth
        llm_auth = "N/A"
        if dec.llm_used:
            llm_auth = "STRONG_PLANT_QUALITY_OWNER"
            final_auth = llm_auth

        would_reach_waterfall = dec.enrich_contact or (contact["mailbox_verified"])
        would_call_apollo = dec.enrich_contact and not contact["mailbox_verified"]

        # Final outcome determination
        if contact["already_sent_in_suppression_window"]:
            final_outcome = "DUPLICATE_SUPPRESSED (14-day lock active)"
            reused_result = "REUSED_PRIOR_SEND_RECEIPT"
        elif contact["email_type"] == "extrapolated" and contact["confidence"] == "MEDIUM":
            final_outcome = "HOLD_EXTRAPOLATED_EMAIL (Blocked from send)"
            reused_result = "REUSED_APOLLO_MEDIUM_RESULT"
        elif contact["email_type"] == "NO_RESULT":
            final_outcome = "HOLD_CONTACT_MISSING (No synthetic hallucination)"
            reused_result = "REUSED_APOLLO_NO_RESULT"
        elif would_call_apollo:
            final_outcome = "ELIGIBLE_FOR_APOLLO_ENRICHMENT"
            reused_result = "NEW_ENRICHMENT_AUTHORIZED"
        else:
            final_outcome = "HOLD"
            reused_result = "NONE"

        results.append({
            "company_id": cid,
            "company_name": cname,
            "candidate_name": cand["candidate_name"],
            "candidate_title": title,
            "stored_authority": stored_auth,
            "recomputed_authority": recomputed_auth,
            "llm_authority": llm_auth,
            "final_authority": final_auth,
            "gate_decision": "PASS" if dec.enrich_contact else "HOLD/BYPASS",
            "gate_reason": dec.reason,
            "would_reach_waterfall": would_reach_waterfall,
            "would_call_apollo": would_call_apollo,
            "reused_result": reused_result,
            "email_state": f"{contact['email']} ({contact['confidence'] or 'NONE'})" if contact['email'] else "NONE",
            "expected_final_outcome": final_outcome,
        })

    return {"replay_results": results}


if __name__ == "__main__":
    out = run_5_account_replay()
    print(json.dumps(out, indent=2))
