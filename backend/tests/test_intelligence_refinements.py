"""Targeted regression tests for lead generation intelligence refinements.

Tests:
1. Person name validation:
   - "Manufacturing Engineering" rejected as INVALID_ROLE_TEXT
   - "Head General Manager" rejected as INVALID_ROLE_TEXT
   - "Corporate Quality" rejected as INVALID_ROLE_TEXT
   - "Plant Operations" rejected as INVALID_ROLE_TEXT
   - Genuine human names ("Abhishek Kumar", "Srinivasa Rao", "Vikram Sharma") accepted as VALID
2. Email classification:
   - investor@, info@, contact@, careers@ quarantined as non-person-specific
   - firstname.lastname recognized as PERSON_SPECIFIC
   - generic corporate / IR email cannot pass reachable_email gate
3. Phone classification:
   - Tracking / numeric sequences (e.g. 302673483451, 77045376532) rejected as INVALID_NUMERIC_SEQUENCE
   - Valid Indian mobile (+91 98250 14820) classified as PERSONAL_MOBILE
   - Valid Indian landlines classified as SWITCHBOARD / PLANT_SWITCHBOARD / CORPORATE_SWITCHBOARD
4. Apollo credit gate:
   - INVALID_ROLE_TEXT candidate cannot trigger Apollo
   - COMPANY_ONLY candidate cannot trigger Apollo
   - WEAK trigger-facility linkage cannot trigger Apollo
   - Real human FACILITY_OWNER / verified plant lead with missing direct contact triggers Apollo recommendation
"""
import unittest
from services.contact_confidence import (
    classify_email_address,
    classify_phone_number,
    validate_person_name,
)
from services.opportunity_gates import (
    evaluate_apollo_credit_gate,
    evaluate_opportunity_gates,
)


class TestIntelligenceRefinements(unittest.TestCase):

    def test_role_phrases_rejected_as_human_names(self):
        role_phrases = [
            "Manufacturing Engineering",
            "Head General Manager",
            "Corporate Quality",
            "Plant Operations",
            "Quality Assurance Manager",
            "Procurement Division",
        ]
        for phrase in role_phrases:
            res = validate_person_name(phrase)
            self.assertEqual(
                res["person_name_validation"],
                "INVALID_ROLE_TEXT",
                f"Expected '{phrase}' to be rejected as INVALID_ROLE_TEXT, got {res}",
            )
            self.assertFalse(res["is_human_name"])

    def test_genuine_human_names_accepted(self):
        genuine_names = [
            "Abhishek Kumar",
            "Srinivasa Rao",
            "Vikram Sharma",
            "Rajesh Patel",
            "Anand Mahindra",
        ]
        for name in genuine_names:
            res = validate_person_name(name)
            self.assertEqual(
                res["person_name_validation"],
                "VALID",
                f"Expected '{name}' to be accepted as VALID, got {res}",
            )
            self.assertTrue(res["is_human_name"])

    def test_single_token_name_is_probable(self):
        res = validate_person_name("Abhishek")
        self.assertEqual(res["person_name_validation"], "PROBABLE")
        self.assertTrue(res["is_human_name"])

    def test_email_classification_quarantines_generic_corporate_and_ir(self):
        self.assertEqual(
            classify_email_address("investor@unominda.com")["classification"],
            "INVESTOR_RELATIONS",
        )
        self.assertFalse(
            classify_email_address("investor@unominda.com")["is_person_specific"]
        )

        self.assertEqual(
            classify_email_address("info@dixoninfo.com")["classification"],
            "GENERIC_CORPORATE",
        )
        self.assertFalse(
            classify_email_address("info@dixoninfo.com")["is_person_specific"]
        )

        self.assertEqual(
            classify_email_address("contact@divislabs.com")["classification"],
            "GENERIC_CORPORATE",
        )
        self.assertFalse(
            classify_email_address("contact@divislabs.com")["is_person_specific"]
        )

        self.assertEqual(
            classify_email_address("careers@suzlon.com")["classification"],
            "CAREERS",
        )
        self.assertFalse(
            classify_email_address("careers@suzlon.com")["is_person_specific"]
        )

        self.assertEqual(
            classify_email_address("purchase@dynamatics.com")["classification"],
            "PROCUREMENT_GENERIC",
        )
        self.assertFalse(
            classify_email_address("purchase@dynamatics.com")["is_person_specific"]
        )

        # Person specific
        self.assertEqual(
            classify_email_address("abhishek.kumar@unominda.com")["classification"],
            "PERSON_SPECIFIC",
        )
        self.assertTrue(
            classify_email_address("abhishek.kumar@unominda.com")["is_person_specific"]
        )

    def test_generic_email_cannot_pass_reachable_email_gate(self):
        evidence = {
            "trigger_current": {"verified": True},
            "exact_facility": {"verified": True},
            "calibration_demand": {"verified": True},
            "technical_capability": {"verified": True},
            "timing": {"verified": True, "event_type": "expansion"},
            "correct_person": {
                "verified": True,
                "name": "Abhishek Kumar",
                "employment_verified": True,
                "duties_verified": True,
                "facility_classification": "FACILITY_OWNER",
            },
            "reachable_email": {
                "status": "VERIFIED",
                "mailbox_verified": True,
                "contact_confidence": "HIGH",
                "address": "investor@unominda.com",
            },
            "score": 95,
        }
        gate_res = evaluate_opportunity_gates(evidence, production=True)
        # Even if mailbox_verified is True, investor@ is not PERSON_SPECIFIC
        self.assertFalse(gate_res["gates"]["reachable_email"]["passed"])
        self.assertFalse(gate_res["ready_for_email"])

    def test_invalid_numeric_sequences_rejected_as_phones(self):
        # 12 digits starting with 3
        res1 = classify_phone_number("302673483451")
        self.assertIn(res1["phone_type"], ["INVALID", "INVALID_NUMERIC_SEQUENCE"])

        # 11 digits starting with 77045
        res2 = classify_phone_number("77045376532")
        self.assertIn(res2["phone_type"], ["INVALID", "INVALID_NUMERIC_SEQUENCE"])

        # Valid Indian mobile with personal context
        mob = classify_phone_number("+91 98250 14820", context_text="Contact Person: Rajkumar Mobile: +91 98250 14820")
        self.assertEqual(mob["phone_type"], "PERSONAL_MOBILE")
        self.assertTrue(mob["is_direct_mobile"])

    def test_apollo_gate_rejects_invalid_role_text(self):
        evidence = {
            "trigger_current": {
                "verified": True,
                "trigger_date": "2026-05-01",
                "trigger_facility_confidence": "STRONG",
            },
            "exact_facility": {"verified": True, "address": "Noida Sector 68"},
            "calibration_demand": {"verified": True},
            "technical_capability": {"verified": True},
            "timing": {"active_buying_window": True, "timing_evidence": "capex ramp"},
            "correct_person": {
                "name": "Head General Manager",
                "facility_classification": "FACILITY_OWNER",
                "facility_verified": True,
            },
            "reachable_email": {"status": "NOT_FOUND"},
        }
        res = evaluate_apollo_credit_gate(evidence)
        self.assertFalse(res["apollo_recommended"])
        self.assertEqual(res["status"], "NOT_QUALIFIED")
        self.assertIn("not a real human name", res["reason"])

    def test_apollo_gate_rejects_company_only_person(self):
        evidence = {
            "trigger_current": {
                "verified": True,
                "trigger_date": "2026-05-01",
                "trigger_facility_confidence": "STRONG",
            },
            "exact_facility": {"verified": True, "address": "Hyderabad Choutuppal"},
            "calibration_demand": {"verified": True},
            "technical_capability": {"verified": True},
            "timing": {"active_buying_window": True, "timing_evidence": "capex ramp"},
            "correct_person": {
                "name": "Srinivasa Rao",
                "facility_classification": "COMPANY_ONLY",
                "facility_verified": False,
                "employment_verified": True,
                "duties_verified": True,
                "authority_class": "STRONG_PLANT_QUALITY_OWNER",
                "person_confidence": "HIGH",
            },
            "reachable_email": {"status": "NOT_FOUND"},
            "score": 85,
        }
        res = evaluate_apollo_credit_gate(evidence)
        self.assertFalse(res["apollo_recommended"])
        self.assertEqual(res["status"], "NOT_QUALIFIED")
        self.assertIn("COMPANY_ONLY", res["reason"])

    def test_apollo_gate_approves_verified_plant_owner_missing_direct_contact(self):
        evidence = {
            "trigger_current": {
                "verified": True,
                "trigger_date": "2026-05-15",
                "trigger_facility_confidence": "STRONG",
            },
            "exact_facility": {
                "verified": True,
                "address": "Plot 1, Sector 3, IMT Manesar, Gurugram",
                "address_precision": "FULL_ADDRESS",
                "trigger_facility_confidence": "STRONG",
            },
            "calibration_demand": {"verified": True},
            "technical_capability": {"verified": True},
            "timing": {"active_buying_window": True, "timing_evidence": "EV capacity expansion"},
            "correct_person": {
                "name": "Abhishek Kumar",
                "designation": "Plant Quality Head",
                "facility_classification": "FACILITY_OWNER",
                "facility_verified": True,
                "current_employment_verified": True,
                "duties_verified": True,
                "authority_class": "STRONG_PLANT_QUALITY_OWNER",
                "person_confidence": "HIGH",
            },
            "reachable_email": {
                "status": "PUBLICLY_FOUND",
                "address": "investor@unominda.com",
            },
            "phone": {"phone": "0124-2290427", "is_direct_mobile": False},
            "score": 85,
        }
        res = evaluate_apollo_credit_gate(evidence)
        self.assertTrue(res["apollo_recommended"])
        self.assertEqual(res["status"], "READY_FOR_CONTACT_ENRICHMENT")
        self.assertIn("Abhishek Kumar", res["reason"])

    def test_functional_calibration_hierarchy_classification(self):
        from services.decision_maker_discovery import classify_functional_role

        # 1. Metrology owner
        func, hier, score = classify_functional_role("Metrology Manager", "standards room and calibration lab")
        self.assertEqual(hier, "METROLOGY_CALIBRATION_OWNER")
        self.assertEqual(score, 25)

        # 2. Plant Quality Head
        func, hier, score = classify_functional_role("Plant Quality Head", "IATF 16949 QA/QC inspection")
        self.assertEqual(hier, "PLANT_QUALITY_HEAD")
        self.assertEqual(score, 22)

        # 3. Instrumentation Manager
        func, hier, score = classify_functional_role("Instrumentation Manager", "process control & sensor testing")
        self.assertEqual(hier, "INSTRUMENTATION_VALIDATION_OWNER")
        self.assertEqual(score, 20)

        # 4. Maintenance Head
        func, hier, score = classify_functional_role("Maintenance Head", "plant engineering and machinery upkeep")
        self.assertEqual(hier, "MAINTENANCE_HEAD")
        self.assertEqual(score, 16)

        # 5. Plant Operations Head
        func, hier, score = classify_functional_role("AVP Operations", "overall plant production ramp-up")
        self.assertEqual(hier, "PLANT_OPERATIONS_HEAD")
        self.assertEqual(score, 12)

        # 6. Procurement
        func, hier, score = classify_functional_role("Purchase Manager", "vendor onboarding and commercial quotes")
        self.assertEqual(hier, "PROCUREMENT_VENDOR_DEV")
        self.assertEqual(score, 8)

    def test_functional_calibration_ranking_prefers_quality_over_senior_operations(self):
        from services.decision_maker_discovery import rank_calibration_candidates

        facility = {"city": "Noida", "address": "Sector 68, Phase II, Noida, UP"}
        trigger = {"title": "Dixon new smartphone production line commissioning in Noida", "type": "expansion"}

        candidates = [
            {
                "name": "Rakesh Sharma",
                "title": "AVP Operations",
                "location": "Noida",
                "snippet": "Oversees manufacturing operations and production targets at Dixon Noida plant.",
                "candidate_company_match": True,
                "current_company_verified": True,
            },
            {
                "name": "Anil Verma",
                "title": "Plant Quality Head",
                "location": "Noida",
                "snippet": "Responsible for plant quality assurance, IATF compliance, inspection and calibration equipment at Noida facility.",
                "candidate_company_match": True,
                "current_company_verified": True,
            },
            {
                "name": "Pawan Gupta",
                "title": "Senior Metrology Engineer",
                "location": "Noida",
                "snippet": "In-charge of calibration standards room, CMM programming, and dimensional gauge verification at Dixon facility.",
                "candidate_company_match": True,
                "current_company_verified": True,
            },
        ]

        ranked = rank_calibration_candidates(candidates, facility, trigger)
        self.assertEqual(len(ranked), 3)

        # Metrology Specialist or Plant Quality Head must outrank AVP Operations!
        self.assertIn(ranked[0]["candidate_name"], ["Pawan Gupta", "Anil Verma"])
        # AVP Operations must NOT win merely because of seniority
        self.assertNotEqual(ranked[0]["candidate_name"], "Rakesh Sharma")
        # Quality score > Operations score
        quality_score = next(r["functional_ownership_score"] for r in ranked if r["candidate_name"] == "Anil Verma")
        ops_score = next(r["functional_ownership_score"] for r in ranked if r["candidate_name"] == "Rakesh Sharma")
        self.assertGreater(quality_score, ops_score)

    def test_industrial_trigger_query_generation_and_filtering(self):
        from services.signal_discovery_engine import (
            generate_industrial_trigger_query,
            filter_negative_financial_results,
        )

        query = generate_industrial_trigger_query("Uno Minda")
        self.assertIn('"new plant"', query)
        self.assertIn("-stock", query)
        self.assertIn("-share", query)
        self.assertIn("Uno Minda", query)

        mixed_results = [
            {"title": "Uno Minda share price target Rs 1200 buy rating", "snippet": "Brokerage recommends buy on stock price movement NSE"},
            {"title": "Uno Minda commissions new EV manufacturing plant in Manesar", "snippet": "New capacity expansion for 4-wheel EV parts with Rs 500 cr capex"},
        ]
        clean = filter_negative_financial_results(mixed_results)
        self.assertEqual(len(clean), 1)
        self.assertIn("commissions new EV manufacturing plant", clean[0]["title"])

    def test_cross_company_candidate_rejected(self):
        from services.decision_maker_discovery import classify_company_evidence, score_candidate_functional_ownership

        # Query for Divis Laboratories returns a snippet for Dr. Reddy's
        cand_name = "Madhu Sundar"
        snip = "10 Mar 2026 - Dr. Reddys Laboratories has elevated M S Madhu Sundar as Global Head of Quality and PV"
        comp_res = classify_company_evidence(cand_name, snip, "Divis Laboratories")

        self.assertEqual(comp_res["company_evidence_status"], "OTHER_COMPANY")
        self.assertFalse(comp_res["is_current_employee"])
        self.assertFalse(comp_res["passes_current_employment"])

        cand = {
            "name": cand_name,
            "title": "Global Head of Quality",
            "snippet": snip,
            "target_company_name": "Divis Laboratories",
        }
        scored = score_candidate_functional_ownership(
            cand,
            {"city": "Hyderabad"},
            {"title": "Facility Commissioning"},
            target_company_name="Divis Laboratories"
        )
        self.assertEqual(scored["score_breakdown"]["current_company_verified"], 0.0)
        self.assertFalse(scored["current_company_verified"])

    def test_former_employee_rejected(self):
        from services.decision_maker_discovery import classify_company_evidence

        cand_name = "Anil Kumar"
        snip = "Former Plant Head at Dixon Technologies, currently VP Operations at Lava International"
        comp_res = classify_company_evidence(cand_name, snip, "Dixon Technologies")

        self.assertEqual(comp_res["company_evidence_status"], "FORMER_COMPANY")
        self.assertFalse(comp_res["is_current_employee"])
        self.assertFalse(comp_res["passes_current_employment"])

    def test_generic_branch_mailbox_not_person_specific(self):
        from services.contact_confidence import classify_email_address

        res = classify_email_address("info-spain@suzlon.com", evidence_status="PUBLICLY_FOUND")
        self.assertEqual(res["email_contact_type"], "BRANCH_GENERIC")
        self.assertEqual(res["email_evidence_status"], "PUBLICLY_FOUND")
        self.assertFalse(res["is_person_specific"])

        res2 = classify_email_address("office-mumbai@dixoninfo.com")
        self.assertEqual(res2["email_contact_type"], "BRANCH_GENERIC")
        self.assertFalse(res2["is_person_specific"])

    def test_publicly_found_status_separated_from_email_contact_type(self):
        from services.contact_confidence import classify_email_address

        # Check all generic prefixes
        for prefix in ["info", "contact", "investor", "careers", "support", "sales", "marketing", "admin"]:
            email = f"{prefix}@example.com"
            res = classify_email_address(email, evidence_status="PUBLICLY_FOUND")
            self.assertEqual(res["email_evidence_status"], "PUBLICLY_FOUND")
            self.assertNotEqual(res["email_contact_type"], "PERSON_SPECIFIC")
            self.assertFalse(res["is_person_specific"])

        # Genuine person email
        pers = classify_email_address("rajkumar.gupta@dixoninfo.com", evidence_status="INFERRED")
        self.assertEqual(pers["email_evidence_status"], "INFERRED")
        self.assertEqual(pers["email_contact_type"], "PERSON_SPECIFIC")
        self.assertTrue(pers["is_person_specific"])

    def test_malformed_and_unsupported_phone_downgraded(self):
        from services.contact_confidence import classify_phone_number

        # Webpack chunk hash from HTML
        chunk_res = classify_phone_number("993-3991217", context_text="static/chunks/993-39912170d10b0b8c.js")
        self.assertEqual(chunk_res["phone_type"], "INVALID")
        self.assertFalse(chunk_res["is_direct_mobile"])

        # Mobile number without individual owner proof
        anon_mob = classify_phone_number("+91 98250 14820", context_text="Dixon Technologies customer contact helpline")
        self.assertEqual(anon_mob["phone_type"], "UNKNOWN")
        self.assertFalse(anon_mob["is_direct_mobile"])

        # Landline without individual owner proof
        corp_land = classify_phone_number("0120-2567890", context_text="Corporate office reception")
        self.assertEqual(corp_land["phone_type"], "CORPORATE_SWITCHBOARD")
        self.assertFalse(corp_land["is_direct_mobile"])

    def test_plant_head_loses_to_verified_quality_metrology_person(self):
        from services.decision_maker_discovery import rank_calibration_candidates

        facility = {"city": "Noida", "facility_name": "Sector 68 Plant"}
        trigger = {"title": "Electronics capacity expansion commissioning"}

        candidates = [
            {
                "name": "Rajkumar Gupta",
                "title": "Plant Head",
                "location": "Noida",
                "snippet": "Plant Head at Dixon Technologies India Ltd, Noida facility.",
                "candidate_company_match": True,
                "current_company_verified": True,
            },
            {
                "name": "Anil Verma",
                "title": "Plant Quality Head",
                "location": "Noida",
                "snippet": "Head of Quality & QA-QC at Dixon Technologies Noida facility, managing testing labs and calibration standards.",
                "candidate_company_match": True,
                "current_company_verified": True,
            },
        ]

        ranked = rank_calibration_candidates(candidates, facility, trigger, target_company_name="Dixon Technologies")
        self.assertEqual(ranked[0]["candidate_name"], "Anil Verma")
        self.assertIn(ranked[0]["hierarchy_class"], ["PLANT_QUALITY_HEAD", "METROLOGY_CALIBRATION_OWNER"])
        self.assertGreater(ranked[0]["functional_ownership_score"], ranked[1]["functional_ownership_score"])

    def test_plant_head_may_win_only_when_stronger_specialist_unavailable(self):
        from services.decision_maker_discovery import rank_calibration_candidates

        facility = {"city": "Noida", "facility_name": "Sector 68 Plant"}
        trigger = {"title": "Electronics capacity expansion commissioning"}

        # Only Plant Head and a Procurement person available
        candidates = [
            {
                "name": "Rajkumar Gupta",
                "title": "Plant Head",
                "location": "Noida",
                "snippet": "Plant Head at Dixon Technologies India Ltd, Noida facility with overall operational signoff.",
                "candidate_company_match": True,
                "current_company_verified": True,
            },
            {
                "name": "Vikas Malhotra",
                "title": "Procurement Executive",
                "location": "Noida",
                "snippet": "Procurement Executive at Dixon Technologies handling vendor POs.",
                "candidate_company_match": True,
                "current_company_verified": True,
            },
        ]

        ranked = rank_calibration_candidates(candidates, facility, trigger, target_company_name="Dixon Technologies")
        self.assertEqual(ranked[0]["candidate_name"], "Rajkumar Gupta")
        self.assertEqual(ranked[0]["hierarchy_class"], "PLANT_OPERATIONS_HEAD")
        self.assertEqual(ranked[0]["calibration_metrology_ownership_evidence"], "INDIRECT (Overall plant operational sign-off)")

    def test_conditional_trigger_linkage_does_not_pass_apollo_gate(self):
        from services.opportunity_gates import evaluate_apollo_credit_gate

        # Evidence where trigger is corporate but facility linkage is unproven / WEAK
        evidence = {
            "trigger_current": {
                "verified": True,
                "trigger_date": "2026-07-30",
                "trigger_facility_confidence": "WEAK",  # Not proven to link to Noida
            },
            "exact_facility": {"verified": True, "address": "Sector 68, Noida"},
            "calibration_demand": {"verified": True},
            "technical_capability": {"verified": True},
            "timing": {"active_buying_window": True, "timing_evidence": "Capacity expansion"},
            "correct_person": {
                "verified": True,
                "name": "Rajkumar Gupta",
                "employment_verified": True,
                "duties_verified": True,
                "facility_classification": "FACILITY_OWNER",
            },
            "reachable_email": {"verified": False, "status": "INFERRED", "contact_confidence": "LOW"},
            "score": 95,
        }

        eval_res = evaluate_apollo_credit_gate(evidence)
        self.assertFalse(eval_res["apollo_recommended"])
        self.assertEqual(eval_res["status"], "NOT_QUALIFIED")
        self.assertIn("trigger_facility_linkage", eval_res["reason"])


if __name__ == "__main__":
    unittest.main()
