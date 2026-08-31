"""Lead Research Brief & Role-Specific Campaign Generator.

Transforms qualified leads into actionable AI Research Briefs and generates
differentiated, role-specific outreach tailored to:
1. Quality / Metrology (Audit readiness, NABL traceability, CMC uncertainty)
2. Purchase / Procurement (Vendor consolidation, commercial SLA, pricing)
3. Maintenance / Plant Head (On-site calibration, downtime reduction, production continuity)
4. Management / CFO (Risk of measurement error, operational efficiency)
"""
from dataclasses import dataclass, field
from datetime import date, datetime
import logging
from typing import Any, Optional
from sqlalchemy.orm import Session

from models.company import Company
from models.person import Person
from models.customer_asset import CustomerAsset
from services.calibration_inference_engine import infer_calibration_need, estimate_instrument_population, calculate_cost_of_inaction
from services.lead_intelligence_scorer import evaluate_lead_intelligence
from services.regulatory_radar import scan_regulatory_radar_for_company

logger = logging.getLogger(__name__)


@dataclass
class LeadResearchBrief:
    company_id: int
    company_name: str
    industry: str
    location: str
    opportunity_score: int
    premium_score: str
    strategic_segment: str
    why_selected: list[str]
    likely_calibration_requirements: list[dict[str, Any]]
    priority_departments: list[str]
    target_stakeholders: list[dict[str, str]]
    search_instructions: dict[str, Any]
    cost_of_inaction_summary: str
    regulatory_drivers: list[str]


def generate_lead_research_brief(company: Company, db: Session) -> LeadResearchBrief:
    """
    Generates a structured Research Brief with precise instructions for contact extraction
    and company intelligence gathering.
    """
    scorecard = evaluate_lead_intelligence(company, db)
    inference = infer_calibration_need(company, db)
    cost_data = calculate_cost_of_inaction(company, db)
    reg_notices = scan_regulatory_radar_for_company(company, db)

    # Why selected reasons
    why_selected = [r["factor"] for r in scorecard.score_reasons]
    if not why_selected:
        why_selected = [f"Operates in {company.industry or 'Manufacturing'} with high calibration demand density."]

    # Target stakeholder hierarchy
    target_stakeholders = [
        {"role": "Primary Technical Decision Maker", "title": "Head / Manager – Quality / Metrology / QA", "department": "Quality"},
        {"role": "Commercial Decision Maker", "title": "Purchase Manager / Procurement Head", "department": "Purchase"},
        {"role": "Operational Stakeholder", "title": "Maintenance Head / Plant Engineer", "department": "Maintenance"},
        {"role": "Executive Escalation", "title": "Plant Head / VP Operations", "department": "Plant Management"},
    ]

    # Search instructions for extraction agents
    c_name = company.name
    search_instructions = {
        "google_queries": [
            f'"{c_name}" "Quality Head" OR "QA Manager"',
            f'"{c_name}" "Metrology" OR "Calibration"',
            f'"{c_name}" "Purchase Manager" OR "Procurement"',
            f'"{c_name}" "Plant Head" OR "Operations"',
        ],
        "linkedin_filters": {
            "company": c_name,
            "target_functions": ["Quality Assurance", "Metrology", "Purchasing", "Operations"],
            "seniority": ["Manager", "Director", "Head", "VP"],
        },
        "apollo_criteria": {
            "organization_name": c_name,
            "titles": ["Quality", "QA", "Metrology", "Purchase", "Procurement", "Plant Head"],
        },
    }

    cost_summary = cost_data["premium_justification"]["value_statement"]
    reg_drivers = [r["title"] for r in reg_notices]

    return LeadResearchBrief(
        company_id=company.id,
        company_name=company.name,
        industry=company.industry or "Manufacturing",
        location=f"{company.city}, {company.state}",
        opportunity_score=scorecard.composite_score,
        premium_score=scorecard.premium_potential,
        strategic_segment=scorecard.strategic_segment,
        why_selected=why_selected,
        likely_calibration_requirements=inference["parameter_inferences"],
        priority_departments=["Quality / Metrology", "Maintenance", "Purchase", "Plant Head"],
        target_stakeholders=target_stakeholders,
        search_instructions=search_instructions,
        cost_of_inaction_summary=cost_summary,
        regulatory_drivers=reg_drivers,
    )


def generate_role_specific_pitch(
    company: Company,
    target_role: str,
    db: Session,
    contact_name: Optional[str] = None,
) -> dict[str, str]:
    """
    Drafts tailored, highly personalized outreach for a specific stakeholder role
    addressing their specific incentive drivers and pain points.
    """
    c_name = company.name
    name = contact_name or "Sir/Madam"
    inference = infer_calibration_need(company, db)
    top_params = [p["parameter"] for p in inference["parameter_inferences"][:3]]
    params_str = ", ".join(top_params)

    role_key = (target_role or "quality").lower()

    if "quality" in role_key or "metrology" in role_key or "qa" in role_key:
        subject = f"NABL Calibration Traceability & Audit Readiness for {c_name}"
        body = (
            f"Dear {name},\n\n"
            f"As your quality and metrology team maintains precision standards at {c_name}, ensuring seamless audit compliance "
            f"and strict measurement traceability across {params_str} equipment is vital.\n\n"
            f"Oorja Technical Services operates as an ISO/IEC 17025:2017 NABL accredited laboratory (CC-3498). We support high-precision "
            f"dimensional, thermal, electrical, and pressure calibration with documented measurement uncertainty budgets and fast turnaround, "
            f"giving your team complete audit confidence.\n\n"
            f"Would it be helpful to review our accredited scope and discuss your upcoming calibration schedule?"
        )
    elif "purchase" in role_key or "procurement" in role_key:
        subject = f"Consolidated Calibration Vendor Efficiency for {c_name}"
        body = (
            f"Dear {name},\n\n"
            f"Managing multiple calibration vendors across separate parameters often introduces procurement overhead and scheduling delays.\n\n"
            f"Oorja Technical Services helps procurement teams consolidate calibration requirements under a single accredited SLA. "
            f"Covering {params_str} with both on-site plant coverage and laboratory support, we offer transparent annual contracts "
            f"and predictable turnaround times to simplify billing and lower total operational spend.\n\n"
            f"Could we share a comparative rate card and schedule a brief commercial evaluation?"
        )
    elif "maintenance" in role_key or "plant" in role_key or "operations" in role_key:
        subject = f"On-Site Calibration Support & Downtime Reduction for {c_name}"
        body = (
            f"Dear {name},\n\n"
            f"Production continuity depends on keeping your plant's instrumentation accurately calibrated without causing avoidable equipment downtime.\n\n"
            f"Oorja Technical Services specializes in comprehensive on-site calibration for plant machinery, thermal ovens, pressure systems, "
            f"and electrical test rigs. Our mobile calibration engineering teams execute calibrations during planned shutdowns or shift windows, "
            f"ensuring zero production disruption.\n\n"
            f"May we coordinate a brief discussion to explore on-site calibration support for your upcoming maintenance cycle?"
        )
    else:  # Management / CFO / Executive
        subject = f"Mitigating Measurement Uncertainty & Audit Risk at {c_name}"
        body = (
            f"Dear {name},\n\n"
            f"In precision manufacturing, measurement uncertainty, instrument drift, and delayed calibration intervals directly impact production yield, audit compliance, "
            f"and customer quality acceptance.\n\n"
            f"Oorja Technical Services partners with manufacturing leadership to manage plant-wide calibration ecosystems. Through comprehensive "
            f"NABL accreditation and guaranteed turnaround SLAs, we protect operational continuity while consolidating service costs across facilities.\n\n"
            f"We would welcome an opportunity to connect with your leadership team regarding strategic calibration management."
        )

    return {
        "target_role": target_role,
        "subject": subject,
        "body": body,
        "key_value_proposition": "Quality Traceability" if "quality" in role_key else "Vendor Consolidation & Uptime",
    }
