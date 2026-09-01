"""Test autonomous discovery and data provenance."""
from database import SessionLocal
from services.signal_discovery_engine import discover_new_calibration_opportunities
from services.research_provider import ResearchProviderRouter

def test():
    db = SessionLocal()
    try:
        router = ResearchProviderRouter()
        print("1. Research Provider Status:", router.get_provider_status())
        
        print("\n2. Autonomous Lead Discovery Run:")
        res = discover_new_calibration_opportunities(db=db, limit=4)
        print(f"Total Discovered: {res['total_discovered']}")
        for c in res["candidates"]:
            print(f"  - {c['company_name']} | Provenance: {c['data_provenance']} | Signal: {c['signal_type']}")
    finally:
        db.close()

if __name__ == "__main__":
    test()
