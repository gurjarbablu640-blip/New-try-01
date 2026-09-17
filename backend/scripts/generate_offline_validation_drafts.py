"""Offline Real-Evidence Validation for Phase 2.1D Personalization Grounding.

Generates offline drafts for:
1. HARMAN / Pune expansion
2. Aarti Pharmalabs / existing recorded evidence
3. Tata Advanced Systems / existing C295 evidence

STRICT CONSTRAINTS:
- NO SMTP.
- NO SEND_READY DB mutation.
- NO Apollo calls.
- Preserves LLM-first architecture (DeepSeek primary -> Gemini fallback).
- NO_APPROVED_CAPABILITY_LANGUAGE
- NO_UNGROUNDED_INSTRUMENT_ENUMERATION
- NO_COMPLIANCE_GUARANTEE
- NO_FALSE_NEW_FACILITY
- NO_UNSUPPORTED_PERSON_RESPONSIBILITY
- MAX_3_CAPABILITY_GROUPS
- DEEPSEEK_PRIMARY
- EXACT_SIGNATURE
- Target: 90–130 words excluding signature.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.sales_personalization_v2 import (
    SalesPersonalizationV2Engine,
    classify_claim,
    infer_event_status,
    resolve_event_date,
    SALES_SIGNATURE,
)


def run_validation():
    engine = SalesPersonalizationV2Engine()

    test_accounts = [
        {
            "id": 121,
            "company": "HARMAN",
            "facility": "HARMAN Pune Automotive Manufacturing Plant",
            "person": "Rohit Giri",
            "first_name": "Rohit",
            "designation": "Business Unit Head",
            "trigger": "HARMAN Invests Rs 345 Crore to Expand Pune Automotive Manufacturing Plant",
            "trigger_headline": "HARMAN Invests Rs 345 Crore to Expand Pune Automotive Manufacturing Plant",
            "trigger_snippet": "Rs 345 crores (USD 42 million) new investment to expand Pune automotive manufacturing plant. Production capacity up by 50%. 300 new jobs to be created.",
            "industry": "automotive",
            "persona": "STRONG_PLANT_QUALITY_OWNER",
        },
        {
            "id": 349,
            "company": "Aarti Pharmalabs Limited",
            "facility": "MIDC Tarapur Manufacturing Block",
            "person": "Jayendra Chaphekar",
            "first_name": "Jayendra",
            "designation": "Quality Assurance Manager",
            "trigger": "Aarti Pharmalabs inaugurates new manufacturing block at MIDC Tarapur",
            "trigger_headline": "Aarti Pharmalabs inaugurates new manufacturing block at MIDC Tarapur",
            "trigger_snippet": "Located at MIDC Tarapur (Plot No. L-28/29/99), the new manufacturing block has an annual production capacity of 3,600 tonnes per annum (TPA) for active pharmaceutical ingredients.",
            "industry": "pharmaceutical",
            "persona": "STRONG_PLANT_QUALITY_OWNER",
        },
        {
            "id": 350,
            "company": "Tata Advanced Systems Limited",
            "facility": "Vadodara C295 Final Assembly Line",
            "person": "Amit Kanawaje",
            "first_name": "Amit",
            "designation": "Assistant Manager - Quality Control (C295 FAL)",
            "trigger": "Tata Advanced Systems and Airbus inaugurate C295 Final Assembly Line at Vadodara",
            "trigger_headline": "Tata Advanced Systems and Airbus inaugurate C295 Final Assembly Line at Vadodara",
            "trigger_snippet": "The first 'Make in India' C295 will roll out of the Vadodara FAL in September 2026, marking a milestone for the Indian aerospace industry.",
            "event_date": "September 2026",
            "industry": "aerospace",
            "persona": "STRONG_PLANT_QUALITY_OWNER",
        },
    ]

    results = []

    for acc in test_accounts:
        res = engine.generate_outreach(acc)

        # Classify sentences
        body_no_sig = res.body.split("Best regards,")[0].strip()
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", body_no_sig) if s.strip()]

        explicit_claims = []
        safe_generic_claims = []
        unsupported_claims = []

        for s in sentences:
            cat, viol = classify_claim(s, event_status=res.event_status, record=acc)
            if cat == "UNSUPPORTED_SPECIFIC":
                unsupported_claims.append(f"{s} [{viol}]")
            elif cat == "SAFE_GENERIC":
                safe_generic_claims.append(s)
            else:
                explicit_claims.append(s)

        # Specific Phase 2.1D assertions
        has_approved_cap_lang = bool(re.search(r"\bapproved\s+capabilities\b", res.body, re.IGNORECASE))
        has_instrument_enumeration = bool(re.search(r"\b(?:calipers|micrometers|multimeters|insulation\s+testers|vacuum\s+gauges|torque\s+wrenches)\b", res.body, re.IGNORECASE))
        has_compliance_guarantee = bool(re.search(r"\b(?:guarantees?|ensures?)\s+(?:compliance|audit\s+success|regulatory\s+clearance)\b", res.body, re.IGNORECASE))
        has_false_new_facility = False
        if acc["company"] == "HARMAN":
            has_false_new_facility = bool(re.search(r"\b(?:new\s+(?:facility|plant|site)|greenfield)\b", res.body, re.IGNORECASE))

        has_person_responsibility = bool(re.search(r"\b(?:you|your)\s+(?:manage|own|oversee|lead|handle)\s+(?:calibration|metrology)\b|\byour\s+(?:calibration\s+team|program)\b", res.body, re.IGNORECASE))
        exact_signature_match = res.body.endswith(SALES_SIGNATURE.strip())
        max_3_caps = len(res.capabilities_included) <= 3

        acc_summary = {
            "COMPANY": acc["company"],
            "FACILITY": acc["facility"],
            "EVENT_TYPE": res.event_status,
            "EVENT_DATE_SOURCE": res.date_source,
            "PERSONA / AUTHORITY_CLASS": res.persona_used,
            "LLM_PROVIDER": res.llm_provider_used,
            "SUBJECT": res.subject,
            "BODY": res.body,
            "WORD_COUNT": res.word_count,
            "CAPABILITIES_SELECTED": res.capabilities_included,
            "EXPLICIT_EVIDENCE_CLAIMS": explicit_claims,
            "SAFE_GENERIC_CLAIMS": safe_generic_claims,
            "UNSUPPORTED_CLAIMS": unsupported_claims,
            "NO_APPROVED_CAPABILITY_LANGUAGE": "YES" if not has_approved_cap_lang else "NO",
            "NO_UNGROUNDED_INSTRUMENT_ENUMERATION": "YES" if not has_instrument_enumeration else "NO",
            "NO_COMPLIANCE_GUARANTEE": "YES" if not has_compliance_guarantee else "NO",
            "NO_FALSE_NEW_FACILITY": "YES" if not has_false_new_facility else "NO",
            "NO_UNSUPPORTED_PERSON_RESPONSIBILITY": "YES" if not has_person_responsibility else "NO",
            "MAX_3_CAPABILITY_GROUPS": "YES" if max_3_caps else "NO",
            "DEEPSEEK_PRIMARY": "YES" if res.llm_provider_used == "DEEPSEEK" else "NO",
            "EXACT_SIGNATURE": "YES" if exact_signature_match else "NO",
            "GROUNDING_RESULT": "PASS - ZERO UNGROUNDED CLAIMS" if (not unsupported_claims and res.status == "VALIDATED") else f"FAIL - {res.violations}",
        }

        results.append(acc_summary)

    out_file = os.path.join(os.path.dirname(__file__), "..", "..", ".system_generated", "offline_drafts_validation_phase2_1d.json")
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print(f"Validation completed. {len(results)} accounts processed.")
    for r in results:
        print("=" * 60)
        print(f"COMPANY: {r['COMPANY']}")
        print(f"FACILITY: {r['FACILITY']}")
        print(f"EVENT_TYPE: {r['EVENT_TYPE']}")
        print(f"EVENT_DATE_SOURCE: {r['EVENT_DATE_SOURCE']}")
        print(f"PERSONA: {r['PERSONA / AUTHORITY_CLASS']}")
        print(f"LLM_PROVIDER: {r['LLM_PROVIDER']}")
        print(f"SUBJECT: {r['SUBJECT']}")
        print(f"WORD_COUNT: {r['WORD_COUNT']}")
        print(f"CAPABILITIES: {r['CAPABILITIES_SELECTED']}")
        print(f"NO_APPROVED_CAPABILITY_LANGUAGE: {r['NO_APPROVED_CAPABILITY_LANGUAGE']}")
        print(f"NO_UNGROUNDED_INSTRUMENT_ENUMERATION: {r['NO_UNGROUNDED_INSTRUMENT_ENUMERATION']}")
        print(f"NO_COMPLIANCE_GUARANTEE: {r['NO_COMPLIANCE_GUARANTEE']}")
        print(f"NO_FALSE_NEW_FACILITY: {r['NO_FALSE_NEW_FACILITY']}")
        print(f"NO_UNSUPPORTED_PERSON_RESPONSIBILITY: {r['NO_UNSUPPORTED_PERSON_RESPONSIBILITY']}")
        print(f"MAX_3_CAPABILITY_GROUPS: {r['MAX_3_CAPABILITY_GROUPS']}")
        print(f"DEEPSEEK_PRIMARY: {r['DEEPSEEK_PRIMARY']}")
        print(f"EXACT_SIGNATURE: {r['EXACT_SIGNATURE']}")
        print(f"GROUNDING_RESULT: {r['GROUNDING_RESULT']}")
        print("\nBODY:\n" + r["BODY"])


if __name__ == "__main__":
    run_validation()
