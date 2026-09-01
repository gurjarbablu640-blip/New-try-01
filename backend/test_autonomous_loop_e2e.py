"""End-to-End Autonomous Lead Discovery, Causality, Person Verification & Apollo Pilot.

Validates the full chain:
1. Search Provider Router (SearXNG / Web fallback)
2. Autonomous Lead Discovery (without user-supplied company names)
3. 5-Question Second-Order Calibration Causality Reasoning
4. Decision-Maker Persona Discovery with Public Web Evidence
5. Multi-Dimensional Verification Scoring (Company, Role, Location, Recency, Evidence)
6. Controlled Single-Person Apollo Enrichment (POST /api/v1/people/match)
7. Company Brain & Timeline Synchronization
8. Ask Oorja Tool Orchestration
"""
import io
import time
from database import SessionLocal
from services.research_provider import ResearchProviderRouter
from services.signal_discovery_engine import discover_new_calibration_opportunities
from services.decision_maker_discovery import (
    run_full_discovery_pipeline,
    build_research_brief_with_persons,
)
from services.orchestrator import AskOorjaOrchestrator
from models.company import Company
from models.decision_maker_candidate import DecisionMakerCandidate

def run_autonomous_loop_test():
    db = SessionLocal()
    try:
        print("==================================================")
        print("STAGE 1: SEARCH PROVIDER ROUTER VALIDATION")
        print("==================================================")
        router = ResearchProviderRouter()
        provider_status = router.get_provider_status()
        print(f"Discovered Provider Statuses: {provider_status}")

        t0 = time.time()
        search_res = router.search("India manufacturing plant expansion CAPEX 2026", num_results=3, db=db)
        latency = round((time.time() - t0) * 1000, 2)

        print(f"Active Search Provider: {search_res.get('provider')}")
        print(f"Provider Status: {search_res.get('provider_status')}")
        print(f"Search Latency: {latency} ms")
        print(f"Results Count: {len(search_res.get('results', []))}")
        for r in search_res.get("results", [])[:2]:
            print(f"  - Title: {r.get('title')[:60]}... | URL: {r.get('url')}")

        print("\n==================================================")
        print("STAGE 2: AUTONOMOUS LEAD DISCOVERY (NO COMPANY NAME PROVIDED)")
        print("==================================================")
        disco_res = discover_new_calibration_opportunities(db=db, geography="PAN INDIA", limit=3)
        print(f"Geography Scope: {disco_res.get('geography_scope')}")
        print(f"Total Companies Discovered: {disco_res.get('total_discovered')}")
        
        candidates = disco_res.get("candidates", [])
        assert len(candidates) > 0, "Autonomous discovery must return candidate companies"

        top_candidate = candidates[0]
        print(f"\nTop Opportunity Discovered:")
        print(f"  Company: {top_candidate['company_name']}")
        print(f"  Location: {top_candidate['city']}, {top_candidate['state']}")
        print(f"  Industry: {top_candidate['industry']}")
        print(f"  Signal Type: {top_candidate['signal_type']}")
        print(f"  Event: {top_candidate['event_title']}")
        print(f"  Evidence URL: {top_candidate['evidence_url']}")
        print(f"  Data Provenance: {top_candidate['data_provenance']}")
        print(f"  Opportunity ICP Score: {top_candidate['icp_score']} / 100")
        print(f"  Buying Window: {top_candidate['buying_window']}")

        causality = top_candidate.get("causality_chain", {})
        print(f"\n5-Question Calibration Causality Reasoning:")
        print(f"  Q1 (What Changed?): {causality.get('business_change')}")
        print(f"  Q3 (Calibration Impact): {causality.get('calibration_impact')}")
        print(f"  Q4 (Likely Parameters): {causality.get('likely_parameters')}")
        print(f"  Q5 (Recommended Role): {causality.get('recommended_role')}")
        print(f"  Action Strategy: {causality.get('action_strategy')}")

        print("\n==================================================")
        print("STAGE 3: DECISION-MAKER DISCOVERY & EVIDENCE VERIFICATION")
        print("==================================================")
        company_id = top_candidate["company_id"]
        # Clear legacy candidates for this company to test fresh discovery
        db.query(DecisionMakerCandidate).filter(DecisionMakerCandidate.company_id == company_id).delete()
        db.commit()

        pipeline_res = run_full_discovery_pipeline(
            company_id=company_id,
            signal_type=top_candidate["signal_type"],
            max_apollo_enrichments=1,
            db=db,
        )
        
        print(f"Person Discovery Status: {pipeline_res.get('status')}")
        summary = pipeline_res.get("summary", {})
        print(f"Person Candidates Discovered: {summary.get('candidates_found', 0)}")
        print(f"Candidates Verified: {summary.get('candidates_verified', 0)}")
        print(f"Apollo Enriched Count: {summary.get('apollo_enriched', 0)}")

        top_candidates = db.query(DecisionMakerCandidate).filter(
            DecisionMakerCandidate.company_id == company_id,
            DecisionMakerCandidate.candidate_name.isnot(None),
        ).all()

        genuine_verified_people = [
            c for c in top_candidates 
            if c.verification_status == "PERSON_PUBLICLY_VERIFIED"
        ]
        rejected_candidates = [
            c for c in top_candidates 
            if c.verification_status == "PERSON_REJECTED"
        ]
        candidate_hypotheses = [
            c for c in top_candidates 
            if c.verification_status == "PERSON_CANDIDATE"
        ]

        print(f"\nCandidates Audit Breakdown:")
        print(f"  - Total Candidates Extracted: {len(top_candidates)}")
        print(f"  - Truly Verified Individuals (PERSON_PUBLICLY_VERIFIED): {len(genuine_verified_people)}")
        print(f"  - Unverified Hypotheses (PERSON_CANDIDATE): {len(candidate_hypotheses)}")
        print(f"  - Rejected (False Positives / Job Listings): {len(rejected_candidates)}")

        if genuine_verified_people:
            top_person = sorted(genuine_verified_people, key=lambda x: x.score_composite or 0, reverse=True)[0]
            print(f"\nDiscovered Top Verified Stakeholder:")
            print(f"  Name: {top_person.candidate_name}")
            print(f"  Title / Role: {top_person.candidate_title}")
            print(f"  Stakeholder Role: {top_person.stakeholder_role}")
            print(f"  Verification Status: {top_person.verification_status}")
            print(f"  Composite Match Score: {round(top_person.score_composite or 0, 3)}")
            print(f"  Evidence Sources: {top_person.evidence_sources}")
            print(f"  Public Profile URL: {top_person.public_profile_url}")

            # Step 3B: Enrich ONE verified person via Apollo
            from services.decision_maker_discovery import enrich_candidate_via_apollo
            print("\n--- Running Specific-Person Apollo Request (POST /api/v1/people/match) ---")
            print(f"  Target Person: {top_person.candidate_name}")
            print(f"  Target Company: {top_candidate['company_name']}")
            print(f"  Target Title: {top_person.candidate_title}")
            print(f"  Endpoint: POST https://api.apollo.io/api/v1/people/match")

            apollo_res = enrich_candidate_via_apollo(candidate_record=top_person, company_name=top_candidate["company_name"], db=db)
            print(f"  Apollo Response Classification: {apollo_res.get('status')}")
            print(f"  Email Found: {top_person.apollo_email or 'NOT_FOUND'}")
            print(f"  Apollo Terminal State: {top_person.apollo_enrichment_status}")
            print(f"  Action Strategy: {'ENGAGE_VERIFIED_EMAIL' if top_person.apollo_email else 'RESEARCH_REQUIRED'}")
        else:
            print("\n  PRIMARY STAKEHOLDER: NONE (No candidate met strict individual person-verification threshold)")
            print("  RECOMMENDED ACTION: RESEARCH_REQUIRED")

        print("\n==================================================")
        print("STAGE 4: COMPANY BRAIN & RESEARCH BRIEF ASSEMBLY")
        print("==================================================")
        comp = db.query(Company).filter(Company.id == company_id).first()
        brief = build_research_brief_with_persons(company=comp, candidates=top_candidates, signal_info={
            "signal_type": top_candidate["signal_type"],
            "event_title": top_candidate["event_title"],
            "calibration_impact": causality.get("calibration_impact"),
            "likely_parameters": ["Dimensional", "Thermal", "Pressure"],
            "price_sensitivity": "Medium",
        })
        print(f"Research Brief Company: {brief.get('company')}")
        print(f"Strategic Target Persona: {brief.get('target_persona')}")
        print(f"Actual Person Status: {brief.get('actual_person', {}).get('verification_status')}")
        print(f"Actionable Next Steps: {brief.get('next_best_action')}")

        print("\n==================================================")
        print("STAGE 5: ASK OORJA MANDATORY 8-SECTION ORCHESTRATION")
        print("==================================================")
        orchestrator = AskOorjaOrchestrator()
        ai_resp = orchestrator.run(
            query="Find Indian companies likely to need calibration in the next 60 days.",
            db=db,
        )
        print(f"Ask Oorja Intent: {ai_resp.get('intent')}")
        print(f"Sub-Agents / Tools Used: {ai_resp.get('sub_agents_used')}")
        print(f"Iterations: {ai_resp.get('iterations')}")
        print("\nFull 8-Section Output:")
        print(ai_resp.get('answer', ''))

        print("\n==================================================")
        print("ALL AUTONOMOUS DISCOVERY & ENRICHMENT AUDIT STAGES COMPLETE!")
        print("==================================================")

    finally:
        db.close()

if __name__ == "__main__":
    run_autonomous_loop_test()
