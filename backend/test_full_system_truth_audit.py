"""System-Wide Truth Audit & Tool Orchestration Verification Script.

Tests:
1. Real User NABL Upload & Persistence Audit
2. Real User Quotation Upload & Persistence Audit
3. Ask Oorja Tool Orchestration across 4 query classes
4. Ask Oorja Mandatory 8-Section Output Verification
5. Apollo NO_RESULT & Alternate Stakeholder Fallback
6. Data Provenance & Dashboard Integrity
"""
import json
import logging
from database import SessionLocal
from models.lab_scope import NABLLabScope, NABLScopeParameter
from models.sales_os import Quotation, QuotationItem
from models.decision_maker_candidate import DecisionMakerCandidate
from models.company import Company
from services.orchestrator import AskOorjaOrchestrator
from services.apollo_adapter import enrich_specific_person
from services.decision_maker_discovery import verify_person_candidate

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_system_truth_audit():
    db = SessionLocal()
    try:
        print("\n==================================================")
        print("1. REAL USER NABL SCOPE UPLOAD AUDIT")
        print("==================================================")
        nabl_real = db.query(NABLLabScope).filter(
            NABLLabScope.source_file == "Oorja NABL Scope-Calibration.pdf"
        ).first()

        if nabl_real:
            print("NABL Real Upload Status: PERSISTED")
            print(f"  - Database ID: {nabl_real.id}")
            print(f"  - Laboratory: {nabl_real.lab_name}")
            print(f"  - Certificate No: {nabl_real.certificate_no}")
            print(f"  - Standard: {nabl_real.accreditation_standard}")
            print(f"  - Source File: {nabl_real.source_file}")
            print(f"  - Data Provenance: {nabl_real.data_provenance}")
            print(f"  - Persisted Parameters Count: {len(nabl_real.parameters)}")
            print("  - Human-Readable Sample Parameters:")
            for p in nabl_real.parameters[:3]:
                print(f"      • {p.discipline} | {p.parameter_name} | {p.range_description} | CMC: {p.cmc_uncertainty}")
        else:
            print("NABL Real Upload Status: NOT FOUND")

        print("\n==================================================")
        print("2. REAL USER QUOTATION UPLOAD AUDIT")
        print("==================================================")
        quote_real = db.query(Quotation).filter(
            Quotation.source_file == "real_user_quote_bharat_forge_2025.pdf",
            Quotation.quotation_number == "Q-HIST-69679",
        ).first()

        if quote_real:
            print("Quotation Real Upload Status: PERSISTED")
            print(f"  - Database ID: {quote_real.id}")
            print(f"  - Quotation Number: {quote_real.quotation_number}")
            print(f"  - Customer: {quote_real.customer_name}")
            print(f"  - Total: ₹{quote_real.total:,.2f}")
            print(f"  - Source File: {quote_real.source_file}")
            print(f"  - Data Provenance: {quote_real.data_provenance}")
            print(f"  - Persisted Line Items Count: {len(quote_real.items)}")
            print("  - Persisted Line Items:")
            for it in quote_real.items:
                print(f"      • {it.instrument_name} | {it.parameter} | Qty: {it.quantity} | Unit: ₹{it.unit_price:,.2f} | Total: ₹{it.total_price:,.2f}")
        else:
            print("Quotation Real Upload Status: NOT FOUND")

        print("\n==================================================")
        print("3. ASK OORJA TOOL ORCHESTRATION & 8-SECTION VERIFICATION")
        print("==================================================")
        orchestrator = AskOorjaOrchestrator()

        test_queries = [
            ("Query 1 (Discovery & Targeting)", "Find Indian companies likely to need calibration in the next 60 days."),
            ("Query 2 (Person Lookup)", "Find the correct person at the best company."),
            ("Query 3 (NABL Lab Parameter Matching)", "Which NABL labs can perform temperature calibration?"),
            ("Query 4 (Quotation & Pricing Intelligence)", "What should I quote for CMM calibration?"),
        ]

        for q_label, q_text in test_queries:
            print(f"\n--- Testing {q_label} ---")
            print(f"Query: \"{q_text}\"")
            resp = orchestrator.run(query=q_text, db=db)
            print(f"  Intent: {resp.get('intent')}")
            print(f"  Sub-Agents Invoked: {resp.get('sub_agents_used')}")
            print(f"  Tool Calls: {len(resp.get('tool_calls', []))}")
            print(f"  Iterations: {resp.get('iterations')}")
            
            # Check 8 mandatory sections
            ans = resp.get("answer", "")
            mandatory_sections = [
                "### 1. ANSWER",
                "### 2. WHY",
                "### 3. EVIDENCE",
                "### 4. WHAT WE KNOW",
                "### 5. WHAT WE INFER",
                "### 6. WHAT WE DON'T KNOW",
                "### 7. CONFIDENCE",
                "### 8. RECOMMENDED ACTION",
            ]
            sections_present = [s for s in mandatory_sections if s in ans]
            print(f"  8-Section Compliance: {len(sections_present)}/8 Present")
            if len(sections_present) < 8:
                print(f"  Missing Sections: {[s for s in mandatory_sections if s not in ans]}")

        print("\n==================================================")
        print("4. APOLLO NO_RESULT & ALTERNATE PERSON FALLBACK")
        print("==================================================")
        # Verify fallback mechanism for Enerparc Energy
        company = db.query(Company).filter(Company.name.ilike("%Enerparc%")).first()
        if company:
            candidates = db.query(DecisionMakerCandidate).filter(
                DecisionMakerCandidate.company_id == company.id
            ).all()
            print(f"Discovered Candidates for {company.name}: {len(candidates)}")
            for c in candidates:
                print(f"  - Candidate: {c.candidate_name} | Role: {c.candidate_title} | Status: {c.verification_status} | Apollo: {c.apollo_enrichment_status or 'NOT_ATTEMPTED'} | Email: {c.apollo_email or 'NOT_FOUND'}")
        
        print("\n==================================================")
        print("5. DATA PROVENANCE DISTRIBUTION AUDIT")
        print("==================================================")
        from sqlalchemy import text
        nabl_prov = db.execute(text("SELECT data_provenance, count(*) FROM nabl_lab_scopes GROUP BY data_provenance")).fetchall()
        print("NABL Lab Scopes by Provenance:")
        for r in nabl_prov:
            print(f"  • {r[0]}: {r[1]}")

        quote_prov = db.execute(text("SELECT data_provenance, count(*) FROM quotations GROUP BY data_provenance")).fetchall()
        print("Quotations by Provenance:")
        for r in quote_prov:
            print(f"  • {r[0]}: {r[1]}")

        print("\n==================================================")
        print("TRUTH AUDIT VERIFICATION COMPLETE")
        print("==================================================")

    finally:
        db.close()

if __name__ == "__main__":
    run_system_truth_audit()
