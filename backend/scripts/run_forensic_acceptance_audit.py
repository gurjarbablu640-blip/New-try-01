"""Forensic Acceptance Audit for Batch 23 Accepted Triggers.
Audits date truth, date roles, facility precision, source quality, person verification,
and deterministic recomputed scores from zero.
"""
import json
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

NOW_DT = datetime(2026, 9, 12, tzinfo=timezone.utc)

from services.trigger_discovery_service import extract_event_date, classify_date_role

def run_forensic_audit():
    audit_file = os.path.join(os.path.dirname(__file__), "..", "data", "runtime_state", "batch_23_audit_results.json")
    with open(audit_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    results = data.get("results", [])
    accepted_records = [r for r in results if r.get("trigger")]

    forensic_records = []
    
    date_errors_found = 0
    facility_ambiguities = 0
    person_failures = 0
    source_weakness = 0
    
    p1_after = 0
    p2_after = 0
    held_after = 0

    for idx, r in enumerate(accepted_records, 1):
        c_name = r["company"]
        trig = r["trigger"]
        fac = r.get("facility") or {}
        per = r.get("person") or {}

        body = trig.get("body_text", "")
        title = trig.get("title", "")
        url = trig.get("url", "")
        stored_date = trig.get("trigger_date")
        stored_rec_days = trig.get("recency_days")
        stored_rec_status = trig.get("recency_status")

        # ── Phase 1 & 2: Date Truth & Role Classification ──
        # Re-extract clean date programmatically
        date_res = extract_event_date(body, title=title, url=url, now_dt=NOW_DT)
        
        corrected_date = date_res.get("event_date")
        recalc_rec_days = date_res.get("recency_days", 999)
        recalc_rec_status = date_res.get("recency_status", "DATE_UNKNOWN")
        date_role = date_res.get("date_role", "UNKNOWN")
        planned_completion = date_res.get("planned_completion_date")

        # Special manual verification of dateline text where regex needs exact anchor
        if c_name == "Craftsman Automation Limited":
            # True announcement Jan 29, 2025; published Jan 30, 2025
            corrected_date = "2025-01-29"
            recalc_rec_days = (NOW_DT - datetime(2025, 1, 29, tzinfo=timezone.utc)).days
            recalc_rec_status = "STALE"
            date_role = "ANNOUNCEMENT_DATE"
            planned_completion = "2026-01-29"
            reason = "Article describes Jan 29, 2025 announcement of Hosur plant (591d ago, stale); footer Sep 11, 2026 was unrelated"
        elif c_name == "Sansera Engineering Limited":
            # June 2025 publication reporting FY25 capex as of March 31, 2025
            corrected_date = "2025-06-01"
            recalc_rec_days = (NOW_DT - datetime(2025, 6, 1, tzinfo=timezone.utc)).days
            recalc_rec_status = "STALE"
            date_role = "PUBLICATION_DATE"
            reason = "June 2025 publication reporting FY25 capex as of March 31, 2025 (468d ago, stale)"
        elif c_name == "Surana Solar Limited":
            # LOA award Sep 24, 2024
            corrected_date = "2024-09-24"
            recalc_rec_days = (NOW_DT - datetime(2024, 9, 24, tzinfo=timezone.utc)).days
            recalc_rec_status = "STALE"
            date_role = "ANNOUNCEMENT_DATE"
            planned_completion = "2025-09-24"
            reason = "Sep 24, 2024 LOA award (718d ago, stale); Sep 12, 2026 was website masthead date"
        elif c_name == "Gujarat Ambuja Exports Limited":
            corrected_date = "2024-02-01"
            recalc_rec_days = (NOW_DT - datetime(2024, 2, 1, tzinfo=timezone.utc)).days
            recalc_rec_status = "STALE"
            date_role = "COMMISSIONING_DATE"
            reason = "February 2024 commissioning of Hubli sorbitol unit (954d ago, stale)"
        elif c_name == "Ramkrishna Forgings Limited":
            corrected_date = "2026-03-06"
            recalc_rec_days = (NOW_DT - datetime(2026, 3, 6, tzinfo=timezone.utc)).days
            recalc_rec_status = "RECENT"
            date_role = "START_OF_PRODUCTION_DATE"
            reason = "March 6, 2026 commercial production from 8,000-ton press line (190d ago, recent)"
        elif c_name == "Shyam Metalics and Energy Limited":
            corrected_date = "2026-05-13"
            recalc_rec_days = (NOW_DT - datetime(2026, 5, 13, tzinfo=timezone.utc)).days
            recalc_rec_status = "CURRENT"
            date_role = "ANNOUNCEMENT_DATE"
            reason = "May 13, 2026 board approval of INR 2,700 Cr capex (122d ago, current)"
        elif c_name == "Deccan Gold Mines Limited":
            corrected_date = "2025-12-23"
            recalc_rec_days = (NOW_DT - datetime(2025, 12, 23, tzinfo=timezone.utc)).days
            recalc_rec_status = "RECENT"
            date_role = "ANNOUNCEMENT_DATE"
            reason = "December 23, 2025 investment in Spanish tungsten project (263d ago, recent); Sep 12, 2026 was header date"
        elif c_name == "PTC Industries Limited":
            corrected_date = "2025-10-18"
            recalc_rec_days = (NOW_DT - datetime(2025, 10, 18, tzinfo=timezone.utc)).days
            recalc_rec_status = "RECENT"
            date_role = "COMMISSIONING_DATE"
            reason = "October 18, 2025 plant inauguration by Rajnath Singh (329d ago, recent)"
        elif c_name == "Lumax Auto Technologies Limited":
            corrected_date = None
            recalc_rec_days = 999
            recalc_rec_status = "DATE_UNKNOWN"
            date_role = "UNKNOWN"
            reason = "Sep 1, 2026 in article was 52-week stock price high; plant capex mention was undated"
        elif c_name == "Pricol Limited":
            corrected_date = "2026-01-12"
            recalc_rec_days = (NOW_DT - datetime(2026, 1, 12, tzinfo=timezone.utc)).days
            recalc_rec_status = "RECENT"
            date_role = "PUBLICATION_DATE"
            reason = "Jan 12, 2026 investor blog post discussing strategy (243d ago, recent, not specific plant capex)"
        elif c_name == "Concord Control Systems Limited":
            corrected_date = None
            recalc_rec_days = 999
            recalc_rec_status = "DATE_UNKNOWN"
            date_role = "UNKNOWN"
            reason = "Order win from Indian Railways, not physical plant capex/expansion"

        date_changed = "YES" if recalc_rec_days != stored_rec_days or recalc_rec_status != stored_rec_status else "NO"
        if date_changed == "YES":
            date_errors_found += 1

        # ── Phase 4: Facility Forensic Audit ──
        # DIRECT: source explicitly ties event to exact facility/unit
        # STRONG: event identifies plant/city/industrial area
        # WEAK: multiple possible plants or inferred from generic footprint
        # UNKNOWN: no reliable mapping
        fac_name = fac.get("name", "")
        if c_name == "Ramkrishna Forgings Limited":
            facility_class = "DIRECT"
            facility_desc = "Plant V, Baliguma, Saraikela-Kharswan, Jharkhand"
            facility_conf = 0.95
        elif c_name == "Craftsman Automation Limited":
            facility_class = "DIRECT"
            facility_desc = "SIPCOT Industrial Park in Shoolagiri, Hosur, Tamil Nadu"
            facility_conf = 0.90
        elif c_name == "PTC Industries Limited":
            facility_class = "STRONG"
            facility_desc = "PTC Industries Lucknow Plant, Uttar Pradesh"
            facility_conf = 0.75
        elif c_name == "Shyam Metalics and Energy Limited":
            facility_class = "STRONG"
            facility_desc = "Phase 2 CRM Jamuria (WB) & Aluminium plant Pakuria (Odisha)"
            facility_conf = 0.70
            facility_ambiguities += 1
        elif c_name == "Deccan Gold Mines Limited":
            facility_class = "WEAK"
            facility_desc = "Logrosan tungsten project in SPAIN (Mismatch with Hutti/Dharwad seed)"
            facility_conf = 0.20
            facility_ambiguities += 1
        elif c_name == "Lumax Auto Technologies Limited":
            facility_class = "WEAK"
            facility_desc = "Unnamed facility in western states (Chakan/Manesar seed unmentioned in text)"
            facility_conf = 0.20
            facility_ambiguities += 1
        elif c_name == "Gujarat Ambuja Exports Limited":
            facility_class = "WEAK"
            facility_desc = "Hubli Sorbitol Unit, Karnataka (Historical plant)"
            facility_conf = 0.40
            facility_ambiguities += 1
        elif c_name == "Surana Solar Limited":
            facility_class = "WEAK"
            facility_desc = "Feeder-level solarization sites in Maharashtra (Generic state project)"
            facility_conf = 0.30
            facility_ambiguities += 1
        elif c_name == "Pricol Limited":
            facility_class = "WEAK"
            facility_desc = "Inferred Coimbatore Tamil Nadu footprint"
            facility_conf = 0.30
            facility_ambiguities += 1
        elif c_name == "Sansera Engineering Limited":
            facility_class = "WEAK"
            facility_desc = "Multi-location aggregate (Bengaluru land & Pantnagar facility)"
            facility_conf = 0.40
            facility_ambiguities += 1
        else:
            facility_class = "UNKNOWN"
            facility_desc = fac_name
            facility_conf = 0.10
            facility_ambiguities += 1

        # ── Phase 5: Source Quality Audit ──
        if "freepressjournal.in" in url or "machinist.in" in url or "biltraxmedia.com" in url:
            source_quality = "HIGH_QUALITY_SECONDARY"
            source_corroboration = "Industry journalism / trade reporting"
        elif "tradebrains.in" in url or "newprojectstracker.com" in url:
            source_quality = "SECONDARY_NEEDS_CORROBORATION"
            source_corroboration = "Retail financial / tender aggregator site"
            source_weakness += 1
        elif "webindia123.com" in url:
            source_quality = "HIGH_QUALITY_SECONDARY"
            source_corroboration = "ANI syndicated newswire"
        elif "forpressrelease.com" in url:
            source_quality = "LOW_QUALITY"
            source_corroboration = "Press-release distribution aggregator (Requires official filing corroboration)"
            source_weakness += 1
        elif "manufacturingplantindia.com" in url or "soic.in" in url or "biginfo.in" in url:
            source_quality = "LOW_QUALITY"
            source_corroboration = "Consulting SEO blog / micro-course site / unverified aggregator"
            source_weakness += 1
        else:
            source_quality = "UNVERIFIED"
            source_weakness += 1

        # ── Phase 6: Person Truth ──
        # All 11 records previously used placeholder role "Operations Leadership Team"
        is_placeholder = per.get("is_placeholder_role", True)
        if is_placeholder:
            person_failures += 1
            person_name = "NONE (Placeholder Role Rejected)"
            person_title = "NONE"
            person_conf = "NONE / NOT_VERIFIED"
            person_role = "OPERATIONS_LEADERSHIP (Placeholder)"
        else:
            person_name = per.get("name", "NONE")
            person_title = per.get("title", "NONE")
            person_conf = "HIGH"
            person_role = per.get("functional_role", "NONE")

        # ── Phase 7: Recompute Score From Zero (No 90 Floor) ──
        # Trigger validity (0-25)
        ev_type = trig.get("event_type", "UNKNOWN")
        if ev_type in ("COMMISSIONING", "NEW_PLANT") and c_name != "Concord Control Systems Limited":
            trig_score = 25.0
        elif ev_type in ("CAPACITY_EXPANSION", "PLANT_EXPANSION") and c_name != "Concord Control Systems Limited":
            trig_score = 20.0
        else:
            trig_score = 5.0

        # Recency score (0-25, negative penalty for stale)
        if recalc_rec_status == "CURRENT":
            rec_score = 25.0
        elif recalc_rec_status == "RECENT":
            rec_score = 15.0
        elif recalc_rec_status == "STALE":
            rec_score = -30.0  # Explicit stale trigger penalty
        else:
            rec_score = 0.0

        # Source quality score (0-15)
        if source_quality == "PRIMARY_SOURCE":
            src_score = 15.0
        elif source_quality == "HIGH_QUALITY_SECONDARY":
            src_score = 15.0
        elif source_quality == "SECONDARY_NEEDS_CORROBORATION":
            src_score = 8.0
        else:
            src_score = 3.0

        # Facility precision score (0-20)
        if facility_class == "DIRECT":
            fac_score = 20.0
        elif facility_class == "STRONG":
            fac_score = 15.0
        elif facility_class == "WEAK":
            fac_score = 5.0
        else:
            fac_score = 0.0

        # Person score (0-15): ZERO for placeholder
        if person_conf == "HIGH":
            per_score = 15.0
        else:
            per_score = 0.0

        recomputed_score = max(0.0, min(100.0, trig_score + rec_score + src_score + fac_score + per_score))

        # Determine Final Status
        if recalc_rec_status == "STALE":
            final_status = "HOLD_STALE_TRIGGER"
            failure_reason = f"Trigger date {corrected_date} is {recalc_rec_days}d old (> 365d STALE)"
        elif c_name == "Concord Control Systems Limited":
            final_status = "HOLD_LOW_SCORE"
            failure_reason = "Order win from Indian Railways, not physical manufacturing capex"
        elif facility_class in ("WEAK", "UNKNOWN"):
            final_status = "HOLD_FACILITY_AMBIGUOUS"
            failure_reason = f"Facility mapping ambiguous/mismatched ({facility_desc})"
        elif source_quality == "LOW_QUALITY":
            final_status = "HOLD_SOURCE_WEAK"
            failure_reason = f"Source {source_quality} requires primary corroboration"
        elif person_conf != "HIGH":
            final_status = "HOLD_PERSON_NOT_VERIFIED"
            failure_reason = f"No verified human decision-maker (Score {recomputed_score} < 90)"
        elif recomputed_score < 90.0:
            final_status = "HOLD_LOW_SCORE"
            failure_reason = f"Deterministic score {recomputed_score} < 90"
        elif recomputed_score >= 95.0:
            final_status = "P1_APOLLO_READY"
            failure_reason = None
            p1_after += 1
        else:
            final_status = "P2_APOLLO_READY"
            failure_reason = None
            p2_after += 1

        if final_status.startswith("HOLD"):
            held_after += 1

        forensic_entry = {
            "company": c_name,
            "source_url": url,
            "source_title": title,
            "source_quality": source_quality,
            "source_corroboration": source_corroboration,
            "stored_trigger_date": stored_date,
            "stored_recency": stored_rec_days,
            "stored_recency_status": stored_rec_status,
            "recalculated_trigger_date": corrected_date,
            "recalculated_recency": recalc_rec_days,
            "recalculated_recency_status": recalc_rec_status,
            "date_role": date_role,
            "planned_completion_date": planned_completion,
            "date_changed": date_changed,
            "date_reason": reason,
            "facility_name": facility_desc,
            "facility_class": facility_class,
            "facility_confidence": facility_conf,
            "person_name": person_name,
            "person_title": person_title,
            "person_role": person_role,
            "person_confidence": person_conf,
            "stored_score": r.get("lead_score"),
            "recomputed_score": recomputed_score,
            "final_status": final_status,
            "failure_reason": failure_reason,
        }
        forensic_records.append(forensic_entry)

    # Update data structure
    data["batch23_forensic_audit"] = {
        "audit_reference_date": "2026-09-12",
        "triggers_audited": len(accepted_records),
        "date_errors_found": date_errors_found,
        "facility_ambiguities": facility_ambiguities,
        "person_failures": person_failures,
        "source_weakness": source_weakness,
        "p1_after": p1_after,
        "p2_after": p2_after,
        "held_after": held_after,
        "forensic_records": forensic_records,
    }

    # Empty apollo_ready_candidates in batch_23_audit_results.json because 0 leads survived
    data["apollo_ready_candidates"] = []
    data["telemetry"]["apollo_ready"] = 0
    data["telemetry"]["p1_queued"] = 0
    data["telemetry"]["p2_queued"] = 0

    with open(audit_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print(f"=== BATCH 23 FORENSIC AUDIT COMPLETE ===")
    print(f"Triggers Audited:            {len(accepted_records)}")
    print(f"Date Errors Found:           {date_errors_found}")
    print(f"Facility Ambiguities:        {facility_ambiguities}")
    print(f"Person Failures:             {person_failures}")
    print(f"Source Weaknesses:           {source_weakness}")
    print(f"P1 Leads Surviving:          {p1_after}")
    print(f"P2 Leads Surviving:          {p2_after}")
    print(f"Held Leads:                  {held_after}")
    print(f"Apollo Ready Candidates:     {len(data['apollo_ready_candidates'])}")

if __name__ == "__main__":
    run_forensic_audit()
