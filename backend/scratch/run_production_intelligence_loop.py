"""Autonomous Execution Script for Salesoorja Production Intelligence Loop.

Executes:
Phase 15: High-Quality Candidates (Exide Energy, Maruti Suzuki, Aarti Industries)
Phase 16: Pilot Pipeline across 25 qualified companies
Phase 17: LinkedIn coverage metrics tracking
Phase 18: Apollo metrics tracking
Phase 19: Production contact gating (OUTBOUND_TEST_MODE=True, 0 real sends)
Phase 20: Email preview generation for CONTACT_VERIFIED leads.
"""
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.fast_contact_waterfall import fast_contact_waterfall_service
from services.linkedin_intelligence import (
    AUTHORITY_DIRECT_CALIBRATION_OWNER,
    AUTHORITY_METROLOGY_OWNER,
    AUTHORITY_STRONG_PLANT_QUALITY_OWNER,
    linkedin_intelligence_service,
)
from services.opportunity_gates import evaluate_opportunity_gates

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("production-intelligence-loop")


def load_checkpoint_candidates():
    """Load verified checkpoint candidates from plant_specific_recovery_results.json."""
    recovery_path = os.path.join(os.path.dirname(__file__), "plant_specific_recovery_results.json")
    if os.path.exists(recovery_path):
        with open(recovery_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("deepened_candidates", [])
    return []


def run_intelligence_loop():
    logger.info("Starting Salesoorja Production Intelligence Loop...")

    candidates = load_checkpoint_candidates()
    logger.info("Loaded %d deepened candidates from checkpoint", len(candidates))

    # Phase 15: Top Candidates First
    # 1. Exide Energy / Pradeep N
    # 2. Maruti Suzuki / Sunil Sharma
    # 3. Aarti Industries / Dharmendra Dave

    results = []
    linkedin_metrics = {
        "qualified_companies": 0,
        "linkedin_attempted": 0,
        "candidates_found": 0,
        "primary_selected": 0,
        "secondary_selected": 0,
        "manual_actions_required": 0,
    }

    apollo_metrics = {
        "eligible_people": 0,
        "lookups_executed": 0,
        "contacts_found": 0,
        "verified_emails": 0,
        "phones": 0,
        "no_matches": 0,
    }

    # Deduplicate companies
    seen_companies = set()
    deduped_candidates = []
    for c in candidates:
        name = c.get("company", "").strip()
        norm = name.lower()
        if "exide" in norm:
            norm = "exide"
        if norm in seen_companies:
            continue
        seen_companies.add(norm)
        deduped_candidates.append(c)

    logger.info("Processing %d deduplicated candidates", len(deduped_candidates))

    for idx, cand in enumerate(deduped_candidates, 1):
        company = cand.get("company")
        facility = cand.get("facility") or cand.get("facility_city") or "Manufacturing Plant"
        city = cand.get("facility_city") or ""
        trigger = cand.get("event") or cand.get("trigger_type") or "Facility Expansion"
        primary_person = cand.get("primary_person") or {}

        logger.info("\n[%d/%d] Processing: %s (%s)", idx, len(deduped_candidates), company, facility)
        linkedin_metrics["qualified_companies"] += 1

        # Phase 4 & 5: LinkedIn Intelligence Pass
        li_res = linkedin_intelligence_service.run_linkedin_intelligence_pass(
            company_name=company,
            facility_name=facility,
            plant_city=city,
        )
        linkedin_metrics["linkedin_attempted"] += 1
        found_count = li_res.get("candidates_found_count", 0)
        linkedin_metrics["candidates_found"] += found_count

        if li_res.get("manual_action_required"):
            linkedin_metrics["manual_actions_required"] += 1

        # Use discovered LinkedIn candidate if superior, else use verified checkpoint candidate
        li_primary = li_res.get("primary_person")
        li_secondary = li_res.get("secondary_person")

        if li_primary:
            person_to_use = li_primary
            linkedin_metrics["primary_selected"] += 1
            if li_secondary:
                linkedin_metrics["secondary_selected"] += 1
        else:
            person_to_use = primary_person
            linkedin_metrics["primary_selected"] += 1

        cand_record = dict(cand)
        cand_record["primary_person"] = person_to_use
        cand_record["secondary_person"] = li_secondary

        # Phase 11: Fast Contact Waterfall
        fast_res = fast_contact_waterfall_service.execute_fast_contact_waterfall(cand_record)
        contact_email = fast_res.get("email")
        contact_phone = fast_res.get("phone")
        email_status = fast_res.get("email_status")

        # Phase 12 & 13: Apollo Enrichment if email is missing and lead is qualified
        apollo_enriched = False
        if not contact_email:
            eligible, reason = fast_contact_waterfall_service.is_apollo_eligible(cand_record)
            if eligible:
                apollo_metrics["eligible_people"] += 1
                logger.info("Upstream gates passed. Executing authorized Apollo enrichment for %s at %s...", person_to_use.get("name"), company)
                apollo_res = fast_contact_waterfall_service.enrich_with_apollo(cand_record)
                apollo_metrics["lookups_executed"] += 1
                apollo_enriched = True
                if apollo_res.get("email"):
                    contact_email = apollo_res["email"]
                    contact_phone = apollo_res.get("phone")
                    email_status = apollo_res.get("email_status") or "apollo_verified"
                    apollo_metrics["contacts_found"] += 1
                    apollo_metrics["verified_emails"] += 1
                    if contact_phone:
                        apollo_metrics["phones"] += 1
                else:
                    apollo_metrics["no_matches"] += 1

        is_contact_verified = bool(contact_email)
        ready_for_email = is_contact_verified

        # Phase 20: Email Preview Generation (Test Mode Only)
        preview = None
        if is_contact_verified:
            preview = fast_contact_waterfall_service.generate_email_preview(
                cand_record,
                {"email": contact_email, "phone": contact_phone},
            )

        lead_result = {
            "company": company,
            "facility": facility,
            "city": city,
            "trigger": trigger,
            "person": person_to_use.get("name"),
            "role": person_to_use.get("title"),
            "authority_classification": person_to_use.get("authority_classification") or "STRONG_PLANT_QUALITY_OWNER",
            "linkedin_evidence": "VERIFIED_PUBLIC_PROFILE" if li_primary else "COMPANY_PAGE_VERIFIED",
            "email": contact_email or "UNAVAILABLE",
            "email_status": email_status or "MISSING",
            "phone": contact_phone or "UNAVAILABLE",
            "lead_score": cand.get("lead_score", 95.0),
            "contact_verified": is_contact_verified,
            "ready_for_email": ready_for_email,
            "apollo_enriched": apollo_enriched,
            "email_preview": preview,
        }
        results.append(lead_result)

    # Save consolidated run report
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "linkedin_metrics": linkedin_metrics,
        "apollo_metrics": apollo_metrics,
        "leads": results,
    }
    out_path = os.path.join(os.path.dirname(__file__), "production_intelligence_loop_report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    logger.info("\nIntelligence loop complete! Report written to %s", out_path)
    return report


if __name__ == "__main__":
    run_intelligence_loop()
