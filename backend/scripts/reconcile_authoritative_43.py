import os
import sys
import json
from pathlib import Path

# Add backend to path
sys.path.insert(0, "/app")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, text

# Run in container or host
engine = create_engine("postgresql://salesoorja:salesoorja@db:5432/salesoorja", pool_pre_ping=True)
conn = engine.connect()

# Query candidates
QUALIFIED_IDS = {121, 349, 350, 354, 375}
FACILITY_HOLD_IDS = {113}
ENTITY_REJECT_IDS = {314} # 'of' fragment

# Let's inspect the exact accounts
query = text("""
    SELECT c.id, c.name, c.industry, c.icp_score, c.qualification_status, c.qualification_reason,
           f.name as facility_name, f.city as facility_city, f.state as facility_state,
           s.signal_type, s.source_snippet, s.source_url, s.urgency_reason, s.detected_at
    FROM companies c
    LEFT JOIN (
        SELECT DISTINCT ON (company_id) company_id, name, city, state
        FROM facilities
        ORDER BY company_id, id DESC
    ) f ON c.id = f.company_id
    LEFT JOIN (
        SELECT DISTINCT ON (company_id) company_id, signal_type, source_snippet, source_url, urgency_reason, detected_at
        FROM company_intent_signals
        ORDER BY company_id, id DESC
    ) s ON c.id = s.company_id
    WHERE c.id IN (121, 349, 350, 354, 375, 113, 314, 46, 79, 92, 112, 128, 152, 253, 271, 303, 340, 341, 342, 343, 344, 345, 346, 347, 348, 351, 352, 353, 355, 356, 357, 358, 359, 360, 361, 362, 363, 364, 365, 366, 367, 368, 369)
    ORDER BY c.id ASC;
""")

rows = conn.execute(query).fetchall()
print(f"Total rows retrieved: {len(rows)}")
for r in rows:
    d = dict(r._mapping)
    print(f"ID: {d['id']} | Name: {d['name']} | Facility: {d['facility_name']} | Signal: {d['signal_type']}")
