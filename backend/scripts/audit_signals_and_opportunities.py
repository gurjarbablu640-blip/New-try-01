import json
import sys
sys.path.insert(0, "/app")
from sqlalchemy import text
from database import SessionLocal

db = SessionLocal()

print("=== OPPORTUNITIES ===")
opps = db.execute(text("SELECT * FROM opportunities ORDER BY id DESC")).fetchall()
print(f"Total opportunities: {len(opps)}")
for op in opps[:15]:
    print(" ", dict(op._mapping))

print("\n=== INTENT SIGNALS ===")
signals = db.execute(text("SELECT * FROM company_intent_signals ORDER BY id DESC LIMIT 20")).fetchall()
print(f"Total intent signals: {len(signals)}")
for s in signals:
    print(" ", dict(s._mapping))

print("\n=== BUSINESS ANALYST DECISIONS ===")
bads = db.execute(text("SELECT * FROM business_analyst_decisions ORDER BY id DESC LIMIT 20")).fetchall()
print(f"Total BA decisions: {len(bads)}")
for b in bads:
    print(" ", dict(b._mapping))

print("\n=== FACILITIES ===")
facs = db.execute(text("SELECT * FROM facilities ORDER BY id DESC LIMIT 20")).fetchall()
print(f"Total facilities: {len(facs)}")
for f in facs:
    print(" ", dict(f._mapping))

db.close()
