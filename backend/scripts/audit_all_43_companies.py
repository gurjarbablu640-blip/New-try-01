import json
import sys
sys.path.insert(0, "/app")
from sqlalchemy import text
from database import SessionLocal

db = SessionLocal()

companies = db.execute(text("""
    SELECT id, name, domain, industry, lead_status, qualification_status, qualification_reason,
           icp_score, qualified_at, created_at, updated_at
    FROM companies
    WHERE date(created_at) = CURRENT_DATE OR date(updated_at) = CURRENT_DATE
    ORDER BY id ASC
""")).fetchall()

print(f"Total companies active today: {len(companies)}")
comp_ids = []
for c in companies:
    d = dict(c._mapping)
    comp_ids.append(d['id'])
    print(f"ID: {d['id']} | Name: {d['name']} | Ind: {d.get('industry')} | LeadStat: {d.get('lead_status')} | QualStat: {d.get('qualification_status')} | Reason: {d.get('qualification_reason')}")

ev_cols = db.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'research_evidence_records'")).fetchall()
print("Evidence columns:", [c[0] for c in ev_cols])

evidence = db.execute(text(f"""
    SELECT company_id, evidence_type, snippet, url, confidence, retrieved_at
    FROM research_evidence_records
    WHERE company_id IN ({','.join(str(i) for i in comp_ids) if comp_ids else '0'})
""")).fetchall()
print(f"Total evidence records found: {len(evidence)}")
for e in evidence[:10]:
    print(" ", dict(e._mapping))

# Also check facilities
fac_cols = db.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'facilities'")).fetchall()
print("Facility columns:", [c[0] for c in fac_cols])

facilities = db.execute(text(f"""
    SELECT id, company_id, name, location, state, status, created_at
    FROM facilities
    WHERE company_id IN ({','.join(str(i) for i in comp_ids) if comp_ids else '0'})
""")).fetchall()
print(f"Total facilities found: {len(facilities)}")
for fac in facilities:
    print(" ", dict(fac._mapping))



db.close()
