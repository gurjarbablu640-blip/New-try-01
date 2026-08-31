"""Customer / Prospect Manual Onboarding & Intelligence Feeder Service.

Enables manual customer/prospect entry from UI and automatically feeds:
1. CRM Company, Person, CustomerAsset tables
2. CompanyBrain facts and timeline events
3. Evidential Belief State with explicit FACT / INFERENCE tagging
4. Calibration Need Inference and initial ICP Scoring
5. Guided Next-Best-Action recommendations
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
import logging
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from models.company import Company
from models.person import Person
from models.customer_asset import CustomerAsset
from models.pipeline import PipelineStage
from services.company_brain import record_intelligence_fact, record_timeline_event
from services.reasoning_engine import (
    get_or_create_belief_state,
    update_belief_with_evidence,
    EpistemicType,
    execute_decision_policy,
)
from services.calibration_inference_engine import infer_calibration_need, calculate_cost_of_inaction
from services.lead_intelligence_scorer import evaluate_lead_intelligence

logger = logging.getLogger(__name__)


def onboard_manual_prospect(
    db: Session,
    company_name: str,
    industry: Optional[str] = None,
    city: Optional[str] = None,
    state: Optional[str] = None,
    country: Optional[str] = "India",
    facility: Optional[str] = None,
    website: Optional[str] = None,
    contact_name: Optional[str] = None,
    contact_role: Optional[str] = None,
    contact_email: Optional[str] = None,
    contact_phone: Optional[str] = None,
    existing_vendor: Optional[str] = None,
    calibration_requirement: Optional[str] = None,
    instrument_categories: Optional[List[str]] = None,
    last_calibration_date: Optional[date] = None,
    next_calibration_due: Optional[date] = None,
    notes: Optional[str] = None,
) -> Dict[str, Any]:
    """Manually onboards a prospect/customer into CRM and seeds the entire decision intelligence loop."""
    company_name = company_name.strip()
    if not company_name:
        raise ValueError("Company name is required.")

    # 1. Find or Create Company
    company = db.query(Company).filter(Company.name.ilike(f"%{company_name}%")).first()
    is_new_company = False
    if not company:
        is_new_company = True
        company = Company(
            name=company_name,
            industry=industry or "Manufacturing",
            city=city or "Unknown",
            state=state or "Unknown",
            country=country or "India",
            domain=website.replace("https://", "").replace("http://", "").split("/")[0] if website else f"{company_name.lower().replace(' ', '')}.com",
            icp_score=75,
            source="Manual User Entry",
            buying_window="30_days",
            lead_status="New",
        )
        db.add(company)
        db.commit()
        db.refresh(company)
    else:
        # Update existing fields if provided
        if industry and (not company.industry or company.industry == "Unknown"):
            company.industry = industry
        if city and (not company.city or company.city == "Unknown"):
            company.city = city
        db.commit()

    # 2. Add Contact Person if provided
    person = None
    if contact_name or contact_email or contact_phone:
        p_name = contact_name or "Key Contact"
        person = db.query(Person).filter(
            Person.company_id == company.id,
            (Person.email == contact_email) if contact_email else (Person.full_name.ilike(f"%{p_name}%"))
        ).first()
        if not person:
            person = Person(
                company_id=company.id,
                full_name=p_name,
                designation=contact_role or "Quality / Technical Lead",
                email=contact_email or f"info@{company.domain}",
                phone=contact_phone,
                linkedin_url="",
            )
            db.add(person)
            db.commit()
            db.refresh(person)

    # 3. Add Customer Asset if calibration details provided
    asset = None
    if instrument_categories or calibration_requirement or next_calibration_due:
        asset_name = f"{company.name} Instrument Inventory ({', '.join(instrument_categories or ['General Metrology'])})"
        asset = CustomerAsset(
            company_id=company.id,
            instrument_name=asset_name,
            parameter=instrument_categories[0] if instrument_categories else "Dimensional",
            model="Standard Tooling",
            status="Active",
            calibration_interval_months=12,
            last_calibrated_date=last_calibration_date or (date.today() - timedelta(days=330)),
            calibration_due_date=next_calibration_due or (date.today() + timedelta(days=35)),
        )
        db.add(asset)
        db.commit()
        db.refresh(asset)

    # 4. Feed Company Brain & Timeline
    fact_text = f"Manual profile onboarded. Plant: {facility or 'Primary Unit'}. Requirement: {calibration_requirement or 'Periodic Metrology'}. Existing Vendor: {existing_vendor or 'Unknown'}."
    record_intelligence_fact(
        company_id=company.id,
        db=db,
        category="onboarding",
        fact_key="manual_onboarding_record",
        fact_value={
            "facility": facility or "Unknown",
            "existing_vendor": existing_vendor or "Unknown",
            "requirement": calibration_requirement or "Unknown",
            "notes": notes or "",
        },
        source="Manual User Input",
        evidence_text=fact_text,
        confidence=0.98,
    )
    record_timeline_event(
        company_id=company.id,
        db=db,
        event_type="prospect_onboarded",
        title=f"Account Created via Manual Entry ({company.name})",
        description=fact_text,
        impact_level="high",
        buying_window_impact="immediate" if next_calibration_due and (next_calibration_due - date.today()).days < 45 else "30_days",
        source="Manual User Entry",
    )

    # 5. Initialize / Update Evidential Belief State
    update_belief_with_evidence(
        company=company,
        db=db,
        epistemic_type=EpistemicType.FACT,
        signal_type="customer_onboarding",
        title=f"Verified Onboarding Profile for {company.name}",
        description=fact_text,
        source="Direct Sales Executive Input",
        source_reliability=0.98,
        causal_template_key="plant_expansion" if "expansion" in (notes or "").lower() else None,
    )

    # 6. Run Calibration Inference & Decision Policy
    inference = infer_calibration_need(company, db)
    decision = execute_decision_policy(company, db)

    # 7. Structured Guided Actions
    guided_workflow = [
        {"step": 1, "action": "RESEARCH_COMPANY", "label": "Execute Web & Regulatory Intel Search", "endpoint": f"/api/intelligence/research-brief/{company.id}"},
        {"step": 2, "action": "CALIBRATION_INFERENCE", "label": "Inspect Parameter Inference & Cost of Inaction", "endpoint": f"/api/intelligence/calibration-inference/{company.id}"},
        {"step": 3, "action": "DECISION_MAKER_RESEARCH", "label": "Identify Decision-Maker Personas", "endpoint": "/api/intelligence/role-pitch"},
        {"step": 4, "action": "APOLLO_PILOT_ENRICHMENT", "label": "Controlled Apollo Enrichment (≤ 6 Contacts)", "endpoint": "/api/intelligence/apollo/pilot-validation"},
        {"step": 5, "action": "NEXT_BEST_ACTION", "label": "Review Next Best Revenue Action", "endpoint": f"/api/intelligence/next-best-action/{company.id}"},
    ]

    return {
        "status": "success",
        "is_new_company": is_new_company,
        "company": {
            "id": company.id,
            "name": company.name,
            "industry": company.industry,
            "city": company.city,
            "domain": company.domain,
            "icp_score": company.icp_score,
            "buying_window": company.buying_window,
        },
        "contact": {
            "id": person.id if person else None,
            "name": person.full_name if person else None,
            "job_title": person.designation if person else None,
            "email": person.email if person else None,
        } if person else None,
        "asset": {
            "id": asset.id if asset else None,
            "asset_name": asset.instrument_name if asset else None,
            "category": asset.parameter if asset else None,
            "next_calibration_due": asset.calibration_due_date.isoformat() if asset and asset.calibration_due_date else None,
        } if asset else None,
        "initial_calibration_need": inference.get("calibration_need_score", 0.75),
        "initial_decision": decision.get("decision", "ROLE_SPECIFIC_EMAIL"),
        "guided_workflow": guided_workflow,
    }
