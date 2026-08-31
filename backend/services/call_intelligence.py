"""Call Intelligence, Pre-Call Brief & Objection Playbook Engine.

Provides:
1. Pre-Call Intelligence Brief for sales reps
2. Structured Post-Call Transcript & Signal Analyzer
3. Sales Call Scoring & "What should I have said?" coaching engine
4. Calibration Objection Playbook (Existing Vendor, Price, Turnaround, Scope)
"""
from dataclasses import dataclass, field
from datetime import date, datetime
import logging
from typing import Any, Optional
from sqlalchemy.orm import Session

from models.company import Company
from models.person import Person
from models.customer_asset import CustomerAsset
from services.calibration_inference_engine import infer_calibration_need
from services.lead_intelligence_scorer import evaluate_lead_intelligence

logger = logging.getLogger(__name__)

# Master Calibration Objection Playbook
OBJECTION_PLAYBOOK = {
    "existing_vendor": {
        "objection": "We already have a calibration vendor.",
        "strategy": "Secondary vendor entry / Turnaround gap discovery",
        "recommended_responses": [
            "Understood. We frequently work with manufacturers where their primary vendor handles routine gauges, while Oorja supports specialized parameters (thermal mapping, HV testing, or CMM) requiring tight NABL uncertainty.",
            "Are there any specific instrument parameters or urgent turnaround requirements where your existing vendor has difficulty meeting your production schedule?",
            "Would it make sense for us to support your team as an accredited secondary vendor for overflow or critical audit requirements?",
        ],
    },
    "price_too_high": {
        "objection": "Your price is higher than our current lab.",
        "strategy": "Cost of Inaction / Downtime & Audit Protection",
        "recommended_responses": [
            "We understand competitive pricing is vital. Choosing Oorja's ISO/IEC 17025 accredited on-site calibration protects against audit non-conformities and eliminates equipment transit downtime. How much does a single day of machine stoppage cost your line?",
            "Instead of discounting individual line items, could we structure a consolidated annual calibration contract covering your full plant to optimize your total spend?",
        ],
    },
    "send_quotation_first": {
        "objection": "Please send your rate list / quotation first.",
        "strategy": "Scope Discovery before pricing commit",
        "recommended_responses": [
            "Gladly. Because accredited calibration rates depend on instrument precision class and parameter range, could we quickly confirm your main instrument categories so we send you an exact, relevant scope?",
            "I'll share our NABL accreditation scope (CC-3498) and standard rate card right away. Who from your Quality team should we include for technical parameter review?",
        ],
    },
}


def generate_pre_call_brief(company: Company, db: Session, person_id: Optional[int] = None) -> dict[str, Any]:
    """
    Generates a 30-second Pre-Call Brief for the salesperson before dialing.
    """
    scorecard = evaluate_lead_intelligence(company, db)
    inference = infer_calibration_need(company, db)
    assets = db.query(CustomerAsset).filter(CustomerAsset.company_id == company.id).all()

    person = None
    if person_id:
        person = db.query(Person).filter(Person.id == person_id).first()
    if not person:
        person = db.query(Person).filter(Person.company_id == company.id).first()

    contact_name = person.full_name if person else "Quality / Metrology Manager"
    contact_role = person.designation if person else "Quality Head"

    top_params = [p["parameter"] for p in inference["parameter_inferences"][:3]]
    params_str = ", ".join(top_params)

    # Determine recommended call opening based on contact role
    if "purchase" in contact_role.lower():
        call_objective = "Commercial Discovery & Vendor Consolidation"
        opening_script = f"Good morning {contact_name}, calling from Oorja Technical Services. We assist manufacturing procurement teams with consolidated multi-parameter calibration SLAs to reduce vendor overhead. Wanted to check if your team currently manages calibration across multiple separate vendors?"
        things_to_avoid = "Do not debate technical measurement uncertainty; focus on consolidated billing and turnaround SLAs."
    else:  # Quality / Metrology / Plant
        call_objective = "Technical Discovery & Audit Traceability"
        opening_script = f"Good morning {contact_name}, calling from Oorja Technical Services. We operate an ISO/IEC 17025 NABL accredited calibration laboratory (CC-3498) in Maharashtra. Reaching out regarding your {params_str} calibration schedule to understand your upcoming audit timeline."
        things_to_avoid = "Do not immediately pitch heavy discounts; explore turnaround pain and audit inspection requirements first."

    return {
        "company_name": company.name,
        "contact_name": contact_name,
        "contact_role": contact_role,
        "contact_phone": person.phone if person else None,
        "opportunity_score": scorecard.composite_score,
        "buying_window": scorecard.buying_window,
        "likely_parameters": top_params,
        "known_assets_count": len(assets),
        "call_objective": call_objective,
        "opening_script": opening_script,
        "suggested_questions": [
            "How is calibration currently managed between in-house testing and external accredited laboratories?",
            "Are there any instruments approaching their calibration due cycle in the next 30 to 60 days?",
            "Does your current calibration arrangement ever experience turnaround delays that impact production?",
        ],
        "things_to_avoid": things_to_avoid,
    }


def analyze_call_transcript(transcript_text: str, company: Optional[Company] = None) -> dict[str, Any]:
    """
    Parses a call transcript to extract customer facts, buying signals,
    objections, sales scoring, and 'What should I have said?' coaching advice.
    """
    text_lower = (transcript_text or "").lower()

    # 1. Signal & Objection Detection
    buying_signals = []
    if any(k in text_lower for k in ["due next month", "due soon", "upcoming calibration", "audit next"]):
        buying_signals.append("Upcoming calibration cycle / audit deadline mentioned")
    if any(k in text_lower for k in ["send scope", "nabl certificate", "send details", "share profile"]):
        buying_signals.append("Requested NABL accreditation scope / technical credentials")
    if any(k in text_lower for k in ["instruments", "gauges", "cmm", "micrometer", "quantity"]):
        buying_signals.append("Discussed specific instrument inventory and parameter requirements")

    objections = []
    detected_playbook_advice = []
    if any(k in text_lower for k in ["existing vendor", "regular vendor", "current vendor"]) or ("already have" in text_lower and ("vendor" in text_lower or "lab" in text_lower)):
        objections.append("Existing Vendor Relationship")
        detected_playbook_advice.append(OBJECTION_PLAYBOOK["existing_vendor"])
    if any(k in text_lower for k in ["expensive", "price too high", "cheaper", "rates are high", "discount", "high price"]):
        objections.append("Price Objection")
        detected_playbook_advice.append(OBJECTION_PLAYBOOK["price_too_high"])
    if any(k in text_lower for k in ["send rates", "share price", "quotation first", "send rate card", "send quotation"]):
        objections.append("Premature Quotation Request")
        detected_playbook_advice.append(OBJECTION_PLAYBOOK["send_quotation_first"])

    # 2. Sales Score Breakdown (0 - 100)
    has_discovery = "?" in transcript_text or any(k in text_lower for k in ["how", "what", "which", "when"])
    has_next_step = any(k in text_lower for k in ["follow up", "email", "meeting", "visit", "share", "call you", "send", "schedule", "rate card", "scope"])

    opening_score = 8
    discovery_score = 9 if has_discovery else 5
    objection_handling_score = 8 if objections else 9
    next_step_score = 9 if has_next_step else 4
    total_score = int((opening_score + discovery_score + objection_handling_score + next_step_score) * 2.5)

    return {
        "call_score": total_score,
        "score_breakdown": {
            "opening": f"{opening_score}/10",
            "discovery": f"{discovery_score}/10",
            "objection_handling": f"{objection_handling_score}/10",
            "next_step_clarity": f"{next_step_score}/10",
        },
        "buying_signals_detected": buying_signals,
        "objections_detected": objections,
        "playbook_coaching_advice": detected_playbook_advice,
        "recommended_next_action": "Follow up with NABL scope (CC-3498) and schedule plant visit" if buying_signals else "Log call notes in CRM and schedule nurture follow-up",
    }
