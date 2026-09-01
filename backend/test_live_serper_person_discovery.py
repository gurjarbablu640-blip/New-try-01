"""Live Decision-Maker Discovery Runner using Configured Serper Search Provider.

Runs full 8-step pipeline against real companies with live public web search.
"""
import sys
import os
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base
import models
from models.company import Company
from services.research_provider import research_router
from services.decision_maker_discovery import run_full_discovery_pipeline, get_company_decision_makers


def test_live_serper_discovery():
    print("=" * 90)
    print("SALESOORJA LIVE PERSON-FIRST DECISION-MAKER DISCOVERY RUNNER (SERPER SEARCH)")
    print("=" * 90)

    # Check search provider
    status = research_router.get_provider_status()
    best = research_router.get_best_search_provider()
    print(f"Provider Status: {status}")
    print(f"Active Search Provider: {best}")

    test_engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(test_engine)
    TestSessionLocal = sessionmaker(bind=test_engine)
    db = TestSessionLocal()

    # Create Real Company
    company = Company(
        name="Bharat Forge Ltd",
        domain="bharatforge.com",
        industry="Automotive & Heavy Forging",
        city="Pune",
        state="Maharashtra",
        lead_status="New",
        icp_score=95.0,
        buying_window="immediate",
        urgency_reason="Upcoming IATF 16949 re-certification audit requiring precision calibration",
    )
    db.add(company)
    db.commit()
    db.refresh(company)

    print(f"\nTarget Company:")
    print(f"  • Name:     {company.name}")
    print(f"  • Industry: {company.industry}")
    print(f"  • Facility: {company.city}, {company.state}")
    print(f"  • Signal:   {company.urgency_reason}")

    # Run full discovery pipeline with live Serper
    print("\nExecuting Full Autonomous 8-Step Discovery Pipeline...")
    discovery_res = run_full_discovery_pipeline(
        company_id=company.id,
        signal_type="iso_iatf_audit",
        db=db,
    )

    summary = discovery_res.get("summary", {})
    print(f"\nPipeline Execution Result Summary:")
    print(f"  • Status:               {discovery_res.get('status')}")
    print(f"  • Time:                 {discovery_res.get('processing_time_seconds')}s")
    print(f"  • Search Provider:      {discovery_res.get('stages', {}).get('person_search', {}).get('provider')}")
    print(f"  • Research Status:      {discovery_res.get('stages', {}).get('person_search', {}).get('status')}")
    print(f"  • Search Results:       {summary.get('search_results')}")
    print(f"  • Candidates Found:     {summary.get('candidates_found')}")
    print(f"  • Candidates Verified:  {summary.get('candidates_verified')}")
    print(f"  • Candidates Rejected:  {summary.get('candidates_rejected')}")

    # Inspect decision-makers
    dm_data = get_company_decision_makers(company.id, db)
    primary = dm_data.get("primary_decision_maker")
    secondary = dm_data.get("secondary_stakeholders", [])
    other = dm_data.get("other_candidates", [])

    print("\n" + "=" * 90)
    print("DISCOVERED & VERIFIED STAKEHOLDERS (LIVE PUBLIC SEARCH):")
    print("=" * 90)

    if primary:
        print(f"\n[PRIMARY DECISION-MAKER]")
        print(f"  • Name:             {primary.get('candidate_name')}")
        print(f"  • Title:            {primary.get('candidate_title')}")
        print(f"  • Persona:          {primary.get('persona')} ({primary.get('stakeholder_role')})")
        print(f"  • Selection Reason: {primary.get('priority_selection_reason')}")
        print(f"  • Status:           {primary.get('verification_status')}")
        print(f"  • Composite Score:  {primary.get('composite_score'):.2f} / 1.00 ({primary.get('composite_score')*100:.0f}%)")
        print(f"  • Score Breakdown:  {primary.get('score_breakdown')}")
        print(f"  • Evidence URL:     {primary.get('evidence_url')}")
        snip = str(primary.get('evidence_snippet', '')).encode('ascii', 'replace').decode('ascii')
        print(f"  • Evidence Snippet: {snip}")
        print(f"  • Apollo Status:    {primary.get('apollo_enrichment_status')}")
        print(f"  • Email:            {primary.get('email') or 'NOT FOUND (Honest Status)'}")
    else:
        print("\n[NO PRIMARY DECISION-MAKER FOUND]")

    print(f"\n[SECONDARY STAKEHOLDERS] ({len(secondary)} found):")
    for idx, sec in enumerate(secondary, 1):
        snip = str(sec.get('evidence_snippet', ''))[:100].encode('ascii', 'replace').decode('ascii')
        print(f"  {idx}. {sec.get('candidate_name')} - {sec.get('candidate_title')}")
        print(f"     Persona: {sec.get('persona')} ({sec.get('stakeholder_role')}) | Score: {sec.get('composite_score'):.2f} | Status: {sec.get('verification_status')}")
        print(f"     Source URL: {sec.get('evidence_url')}")
        print(f"     Evidence: {snip}...")

    if other:
        print(f"\n[OTHER / CANDIDATES] ({len(other)} found):")
        for idx, ot in enumerate(other, 1):
            print(f"  {idx}. {ot.get('candidate_name')} - {ot.get('candidate_title')} | Score: {ot.get('composite_score'):.2f}")

    print("\n" + "=" * 90)
    print("LIVE SERPER DECISION-MAKER DISCOVERY TEST COMPLETE")
    print("=" * 90)


if __name__ == "__main__":
    test_live_serper_discovery()
