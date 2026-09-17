"""Reconcile and audit today's complete revenue funnel data from PostgreSQL and runtime state."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, "/app")

from datetime import datetime, date
from sqlalchemy import text
from database import SessionLocal

db = SessionLocal()

print("==================================================")
print("1. RECONCILING CONTACT_ENRICHMENT_INVOKED COUNT")
print("==================================================")

# Check all decision_maker_candidates
res = db.execute(text("SELECT * FROM decision_maker_candidates ORDER BY id DESC")).fetchall()
print(f"\nTotal DecisionMakerCandidates: {len(res)}")
for r in res:
    d = dict(r._mapping)
    print(f"ID: {d.get('id')} | CoID: {d.get('company_id')} | Name: {d.get('candidate_name')} | Title: {d.get('candidate_title')} | Status: {d.get('verification_status')} | ApolloEnrich: {d.get('apollo_enrichment_status')} | Email: {d.get('apollo_email')} | Composite: {d.get('score_composite')}")


# Check persons table
persons = db.execute(text("""
    SELECT id, company_id, full_name, designation, email, email_verification_status, apollo_id, discovery_status, created_at, updated_at
    FROM persons
    ORDER BY id DESC
""")).fetchall()
print(f"\nTotal Persons: {len(persons)}")
for p in persons:
    print(" ", dict(p._mapping))

# Check runtime state files
print("\n--- Operator State Provider Usage & Counters ---")
try:
    with open("data/runtime_state/operator_state.json", "r") as f:
        op = json.load(f)
    print("Provider usage:", json.dumps(op.get("provider_usage", {}), indent=2))
    print("Counters:", json.dumps(op.get("counters", {}), indent=2))
    print("Historical Provider usage:", json.dumps(op.get("historical_provider_usage", {}), indent=2))
    print("Processed accounts:", op.get("processed_accounts", []))
    print("QUALIFIED_NOT_SENT:", json.dumps(op.get("records", {}).get("QUALIFIED_NOT_SENT", []), indent=2))
    print("Transport receipts count:", len(op.get("transport_receipts", [])))
    for tr in op.get("transport_receipts", []):
        print("  Receipt:", tr.get("receipt_id"), tr.get("recipient"), tr.get("sent_at"), tr.get("transport_status"))
except Exception as e:
    print("Error reading operator_state.json:", e)

print("\n--- Apollo Pending Queue & Log ---")
try:
    with open("data/runtime_state/apollo_pending_queue.json", "r") as f:
        ap_queue = json.load(f)
    print(f"Apollo pending queue items: {len(ap_queue)}")
    for item in ap_queue[:5]:
        print("  Queue item:", item.get("company_name"), item.get("person_name"), item.get("status"), item.get("score"))
except Exception as e:
    print("Error reading apollo_pending_queue.json:", e)

# Inspect companies researched today
print("\n==================================================")
print("2. TODAY'S RESEARCHED COMPANIES (43 ACCOUNTS)")
print("==================================================")
companies_today = db.execute(text("""
    SELECT id, name, domain, industry, is_target_industry, status, created_at, updated_at
    FROM companies
    ORDER BY id ASC
""")).fetchall()
print(f"Total companies in database: {len(companies_today)}")
for comp in companies_today:
    c_dict = dict(comp._mapping)
    print(f"ID: {c_dict['id']} | Name: {c_dict['name']} | Status: {c_dict['status']} | Ind: {c_dict['industry']}")

print("\n==================================================")
print("3. RESEARCH EVIDENCE & TRIGGERS")
print("==================================================")
try:
    evidences = db.execute(text("""
        SELECT id, company_id, evidence_type, verified, facility_name, trigger_date, trigger_type, created_at
        FROM research_evidence
        ORDER BY id ASC
    """)).fetchall()
    print(f"Research evidence rows: {len(evidences)}")
    for ev in evidences:
        print("  ", dict(ev._mapping))
except Exception as e:
    print("Error querying research_evidence:", e)

# Outreach records
print("\n==================================================")
print("4. OUTREACH DRAFTS & RECORDS")
print("==================================================")
try:
    drafts = db.execute(text("""
        SELECT id, company_id, person_id, subject, status, created_at
        FROM outreach_drafts
        ORDER BY id DESC
    """)).fetchall()
    print(f"Outreach drafts count: {len(drafts)}")
    for dr in drafts:
        print("  ", dict(dr._mapping))
except Exception as e:
    print("Error querying outreach_drafts:", e)

db.close()
