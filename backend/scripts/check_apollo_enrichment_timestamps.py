import json
import sys
sys.path.insert(0, "/app")
from datetime import datetime
from sqlalchemy import text
from database import SessionLocal


db = SessionLocal()
res = db.execute(text("""
    SELECT id, company_id, candidate_name, candidate_title, 
           apollo_enrichment_status, apollo_email, email_status,
           score_composite, created_at, updated_at
    FROM decision_maker_candidates
    WHERE apollo_enrichment_status != 'NOT_ATTEMPTED'
    ORDER BY id DESC LIMIT 10
""")).fetchall()

print("Candidates with Apollo enrichment attempted:")
for r in res:
    print(dict(r._mapping))

# Also check company 121, 354, 375 in companies table
companies = db.execute(text("SELECT id, name, created_at, updated_at FROM companies WHERE id IN (121, 349, 350, 354, 375)")).fetchall()
print("\nTarget Companies:")
for c in companies:
    print(dict(c._mapping))

db.close()
