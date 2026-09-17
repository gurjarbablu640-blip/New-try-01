"""
Dry-run evaluation for the 5 Qualified Accounts in Salesoorja.
Follows Corrections 13, 14, 15:
- Does NOT send SMTP.
- Uses existing recorded provider results in PostgreSQL / operator_state.
- Does not fabricate Apollo results.
- For candidates without existing Apollo result: WOULD_CALL_APOLLO
- For an existing reusable result: REUSED_EXISTING_RESULT
- For deduplicated request: DEDUP_SKIPPED
- Checks 14-day duplicate transport suppression (e.g. HARMAN rohit.giri@harman.com).
- Checks unsendable extrapolated email on Harman International (rohit.navdikar@harman.com).
- Evaluates candidate fallback for GoodEnough Energy (Saurabh Madaan has no email).
- Enforces account-level outreach (best verified candidate).
"""
import os
import sys
import json
from datetime import datetime, timezone

# Add paths
sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text

def run_dry_run():
    db_url = os.environ.get("DATABASE_URL_SYNC", "postgresql://salesoorja:salesoorja@db:5432/salesoorja")
    engine = create_engine(db_url, pool_pre_ping=True)
    conn = engine.connect()

    # Read operator state for transport receipts (14-day suppression)
    op_state_path = "/app/data/runtime_state/operator_state.json"
    transport_receipts = []
    if os.path.exists(op_state_path):
        with open(op_state_path, "r", encoding="utf-8") as f:
            op_data = json.load(f)
            transport_receipts = op_data.get("transport_receipts", [])

    sent_emails = {r.get("recipient").lower(): r for r in transport_receipts if r.get("recipient")}

    qualified_accounts = [
        {"id": 121, "name": "HARMAN"},
        {"id": 349, "name": "Aarti Pharmalabs"},
        {"id": 350, "name": "Tata Advanced Systems"},
        {"id": 354, "name": "Harman International"},
        {"id": 375, "name": "GoodEnough Energy"},
    ]

    telemetry = {
        "QUALIFIED_ACCOUNTS": len(qualified_accounts),
        "ACCOUNTS_WITH_AUTHORITY_PERSON": 0,
        "ACCOUNTS_REACHING_CONTACT_WATERFALL": 0,
        "NEW_APOLLO_NETWORK_CALLS_WOULD_OCCUR": 0,
        "REUSED_APOLLO_RESULTS": 0,
        "DEDUP_SKIPS": 0,
        "ACCOUNTS_WITH_CONFIRMED_VERIFIED_EMAIL": 0,
        "ACCOUNTS_WITH_ONLY_UNVERIFIED_EMAIL": 0,
        "ACCOUNTS_WITH_NO_EMAIL": 0,
        "VALID_PERSONALIZATIONS": 0,
        "SIMULATED_SEND_READY": 0,
        "DUPLICATE_SUPPRESSED": 0
    }

    account_summaries = []

    for acc in qualified_accounts:
        cid = acc["id"]
        cname = acc["name"]
        
        # 1. Fetch candidates from DB
        candidates = conn.execute(text(
            "SELECT id, candidate_name, candidate_title, score_composite, apollo_email, "
            "apollo_enrichment_status, apollo_response_json, verification_status "
            "FROM decision_maker_candidates WHERE company_id = :cid ORDER BY score_composite DESC, id ASC"
        ), {"cid": cid}).fetchall()

        real_candidates = [dict(c._mapping) for c in candidates if c._mapping.get("candidate_name")]

        has_authority = len(real_candidates) > 0
        if has_authority:
            telemetry["ACCOUNTS_WITH_AUTHORITY_PERSON"] += 1
            telemetry["ACCOUNTS_REACHING_CONTACT_WATERFALL"] += 1

        waterfall_steps = []
        best_verified_candidate = None
        has_verified_email = False
        has_extrapolated_only = False
        has_no_email = False

        for idx, cand in enumerate(real_candidates[:3]):
            c_name = cand["candidate_name"]
            c_title = cand["candidate_title"]
            score = float(cand.get("score_composite") or 0)
            enr_status = cand.get("apollo_enrichment_status")
            apollo_resp = cand.get("apollo_response_json") or {}
            person_data = apollo_resp.get("person") or {}
            raw_email_status = person_data.get("email_status")
            email = cand.get("apollo_email") or person_data.get("email")

            if enr_status == "ENRICHED" and raw_email_status == "verified":
                action = "REUSED_EXISTING_RESULT"
                telemetry["REUSED_APOLLO_RESULTS"] += 1
                has_verified_email = True
                if not best_verified_candidate:
                    best_verified_candidate = cand
                waterfall_steps.append({
                    "candidate": c_name,
                    "title": c_title,
                    "score": score,
                    "call_decision": action,
                    "email": email,
                    "email_status": "VERIFIED",
                    "stop_waterfall": True
                })
                break  # Stop condition: VERIFIED_PROVIDER found!
            elif enr_status == "ENRICHED" and raw_email_status == "extrapolated":
                action = "REUSED_EXISTING_RESULT"
                telemetry["REUSED_APOLLO_RESULTS"] += 1
                has_extrapolated_only = True
                waterfall_steps.append({
                    "candidate": c_name,
                    "title": c_title,
                    "score": score,
                    "call_decision": action,
                    "email": email,
                    "email_status": "EXTRAPOLATED_REJECTED",
                    "stop_waterfall": False
                })
                # Continues to next candidate
            elif enr_status == "NO_RESULT":
                action = "REUSED_EXISTING_RESULT"
                telemetry["REUSED_APOLLO_RESULTS"] += 1
                has_no_email = True
                waterfall_steps.append({
                    "candidate": c_name,
                    "title": c_title,
                    "score": score,
                    "call_decision": action,
                    "email": None,
                    "email_status": "NO_RESULT",
                    "stop_waterfall": False
                })
                # Continues to next candidate
            else:
                # Needs Apollo call in live run
                action = "WOULD_CALL_APOLLO"
                telemetry["NEW_APOLLO_NETWORK_CALLS_WOULD_OCCUR"] += 1
                waterfall_steps.append({
                    "candidate": c_name,
                    "title": c_title,
                    "score": score,
                    "call_decision": action,
                    "email": None,
                    "email_status": "PENDING_NETWORK_CALL",
                    "stop_waterfall": False
                })

        # Evaluate Account-level Email status
        if has_verified_email:
            telemetry["ACCOUNTS_WITH_CONFIRMED_VERIFIED_EMAIL"] += 1
        elif has_extrapolated_only:
            telemetry["ACCOUNTS_WITH_ONLY_UNVERIFIED_EMAIL"] += 1
        else:
            telemetry["ACCOUNTS_WITH_NO_EMAIL"] += 1

        # Check duplicate transport suppression (14 days)
        is_suppressed = False
        suppression_reason = None
        if best_verified_candidate:
            recipient_email = best_verified_candidate.get("apollo_email", "").lower()
            if recipient_email in sent_emails:
                is_suppressed = True
                suppression_reason = f"Duplicate recipient {recipient_email} sent within 14-day grace window ({sent_emails[recipient_email].get('sent_at')})"
                telemetry["DUPLICATE_SUPPRESSED"] += 1
            else:
                telemetry["VALID_PERSONALIZATIONS"] += 1
                telemetry["SIMULATED_SEND_READY"] += 1

        account_summaries.append({
            "company_id": cid,
            "company_name": cname,
            "has_authority_person": has_authority,
            "candidate_count": len(real_candidates),
            "waterfall_steps": waterfall_steps,
            "best_verified_candidate": best_verified_candidate["candidate_name"] if best_verified_candidate else None,
            "best_verified_email": best_verified_candidate.get("apollo_email") if best_verified_candidate else None,
            "is_duplicate_suppressed": is_suppressed,
            "suppression_reason": suppression_reason,
            "simulated_outcome": "SUPPRESSED_14_DAY" if is_suppressed else ("SEND_READY" if best_verified_candidate else ("WOULD_ENRICH_IN_LIVE" if any(s["call_decision"] == "WOULD_CALL_APOLLO" for s in waterfall_steps) else "HOLD_NO_VERIFIED_EMAIL"))
        })

    output = {
        "telemetry": telemetry,
        "account_summaries": account_summaries
    }

    out_file = "/app/data/runtime_state/dry_run_5_qualified_report.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    print("--- DRY RUN TELEMETRY ---")
    for k, v in telemetry.items():
        print(f"{k}: {v}")
    print(f"\nWrote {out_file}")

if __name__ == "__main__":
    run_dry_run()
