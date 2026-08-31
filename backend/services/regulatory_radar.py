"""External Regulatory & Market Intelligence Radar (5-Question Engine).

Translates evolving Indian and international standards (Legal Metrology, BIS QCOs, NABL, IATF, CPCB)
into actionable commercial consequences and matches affected companies across the CRM.
"""
from datetime import date, datetime, timedelta
import logging
from typing import Any, Optional
from sqlalchemy.orm import Session

from models.company import Company
from models.company_brain import RegulatoryIntelligence, CompanyIntelligenceFact, CompanyTimelineEvent
from models.customer_asset import CustomerAsset

logger = logging.getLogger(__name__)

# Default Seed Regulatory Intelligence for Indian Metrology & Manufacturing Ecosystem
DEFAULT_REGULATORY_NOTICES = [
    {
        "authority": "Legal Metrology",
        "regulation_code": "LM-GATC-2026",
        "title": "Legal Metrology Government Approved Test Centre (GATC) Verification Reforms",
        "summary": "Mandates mandatory NABL-traceable verification of weighing and measuring instruments used in commercial transaction points and manufacturing dispatch with strict third-party test centre accreditation.",
        "affected_industries": ["Automotive", "Heavy Engineering", "Pharmaceutical", "Chemical", "FMCG"],
        "affected_parameters": ["Mass", "Dimensional", "Pressure", "Flow"],
        "affected_equipment": ["Weighbridges", "Platform Scales", "Pressure Gauges", "Flow Meters"],
        "compliance_deadline": date(2026, 10, 31),
        "commercial_impact_analysis": {
            "what_changed": "Stricter mandatory NABL-traceable verification rules for dispatch measurement equipment under Jan Vishwas reforms.",
            "affected_processes": ["Dispatch Weight Verification", "Incoming Material Inspection", "Custody Transfer"],
            "calibration_requirement": "Mandatory NABL-accredited calibration certificates with documented measurement uncertainty (CMC).",
            "buying_window": "immediate_to_90_days",
            "sales_opportunity": "Consolidated calibration package for weighing & measuring instruments before audit deadline.",
            "premium_justification": "Oorja NABL accreditation (CC-3498) provides guaranteed audit acceptance, eliminating regulatory penalty risk.",
        },
        "source_url": "https://consumeraffairs.nic.in/legal-metrology",
    },
    {
        "authority": "BIS",
        "regulation_code": "BIS-QCO-2026-METROLOGY",
        "title": "BIS Quality Control Order (QCO) for Pressure Measuring Instruments & Gauges",
        "summary": "Imposes mandatory standard mark certification and calibration conformity on industrial pressure transmitters and gauges deployed in hazardous and high-pressure manufacturing.",
        "affected_industries": ["Automotive", "EV & Battery", "Heavy Engineering", "Oil & Gas", "Power"],
        "affected_parameters": ["Pressure", "Torque", "Thermal"],
        "affected_equipment": ["Digital Pressure Transmitters", "Hydrostatic Gauges", "Torque Transducers"],
        "compliance_deadline": date(2026, 12, 15),
        "commercial_impact_analysis": {
            "what_changed": "BIS Quality Control Order enforcing strict tolerance conformity for industrial pressure measurement equipment.",
            "affected_processes": ["Hydrostatic Pressure Testing", "Pneumatic Control", "High-Pressure Hydraulic Systems"],
            "calibration_requirement": "Annual calibration with verified calibration intervals and CMC uncertainty budgets.",
            "buying_window": "30_to_60_days",
            "sales_opportunity": "Target manufacturing plants with hydraulic and pneumatic testing rigs for full-plant pressure scope.",
            "premium_justification": "On-site hydraulic deadweight testing reduces machine downtime by 70% compared to offsite labs.",
        },
        "source_url": "https://bis.gov.in/qco-notifications",
    },
    {
        "authority": "NABL",
        "regulation_code": "NABL-133-TRACEABILITY-2026",
        "title": "NABL Policy on Metrological Traceability & Measurement Uncertainty (ISO/IEC 17025:2017)",
        "summary": "Updated NABL criteria requiring strict uninterrupted traceability chains for master reference standards in dimensional and thermal metrology.",
        "affected_industries": ["Automotive", "Aerospace", "Precision Machining", "Defense"],
        "affected_parameters": ["Dimensional", "Thermal"],
        "affected_equipment": ["CMM", "Slip Gauge Sets", "Optical Comparators", "Calibration Baths"],
        "compliance_deadline": date(2026, 9, 30),
        "commercial_impact_analysis": {
            "what_changed": "Heightened audit scrutiny on master reference standard traceability and calibration interval validation.",
            "affected_processes": ["QA Standards Room", "CMM Inspection", "Precision Tooling"],
            "calibration_requirement": "High-precision calibration of master equipment with accredited expanded uncertainty documentation.",
            "buying_window": "immediate_window",
            "sales_opportunity": "Approach Quality Heads of IATF/ISO certified plants to audit their calibration master traceability.",
            "premium_justification": "Direct NABL-accredited master equipment traceability guarantees seamless IATF/ISO audit clearance.",
        },
        "source_url": "https://nabl-india.org/documents",
    },
]


def seed_default_regulatory_intelligence(db: Session) -> int:
    """Seeds baseline Indian regulatory notices into the database if not present."""
    count = 0
    for notice in DEFAULT_REGULATORY_NOTICES:
        existing = (
            db.query(RegulatoryIntelligence)
            .filter(RegulatoryIntelligence.regulation_code == notice["regulation_code"])
            .first()
        )
        if not existing:
            reg = RegulatoryIntelligence(
                authority=notice["authority"],
                regulation_code=notice["regulation_code"],
                title=notice["title"],
                summary=notice["summary"],
                affected_industries=notice["affected_industries"],
                affected_parameters=notice["affected_parameters"],
                affected_equipment=notice["affected_equipment"],
                compliance_deadline=notice["compliance_deadline"],
                commercial_impact_analysis=notice["commercial_impact_analysis"],
                source_url=notice["source_url"],
                active=True,
            )
            db.add(reg)
            count += 1
    if count > 0:
        db.commit()
    return count


def match_companies_for_regulation(regulation_id: int, db: Session) -> list[dict[str, Any]]:
    """
    Finds all CRM companies affected by a specific regulatory notice
    and generates specific sales recommendations for each.
    """
    reg = db.query(RegulatoryIntelligence).filter(RegulatoryIntelligence.id == regulation_id).first()
    if not reg:
        return []

    affected_industries = [str(i).lower() for i in (reg.affected_industries or [])]
    affected_params = [str(p).lower() for p in (reg.affected_parameters or [])]

    companies = db.query(Company).all()
    matched_results = []

    for comp in companies:
        comp_ind = (comp.industry or "").lower()
        industry_match = any(ind in comp_ind or comp_ind in ind for ind in affected_industries)

        # Check if company has matching assets in customer_assets
        assets = db.query(CustomerAsset).filter(CustomerAsset.company_id == comp.id).all()
        param_match = any(str(a.parameter or "").lower() in affected_params for a in assets)

        if industry_match or param_match:
            analysis = reg.commercial_impact_analysis
            matched_results.append({
                "company_id": comp.id,
                "company_name": comp.name,
                "city": comp.city,
                "industry": comp.industry,
                "regulation_code": reg.regulation_code,
                "compliance_deadline": reg.compliance_deadline.isoformat() if reg.compliance_deadline else None,
                "urgency": "Critical" if reg.compliance_deadline and reg.compliance_deadline <= (date.today() + timedelta(days=60)) else "High",
                "recommended_action": f"Contact Quality / Metrology: {analysis.get('sales_opportunity')}",
                "premium_argument": analysis.get("premium_justification"),
                "buying_window": analysis.get("buying_window"),
            })

    return matched_results


def scan_regulatory_radar_for_company(company: Company, db: Session) -> list[dict[str, Any]]:
    """
    Scans the Regulatory Radar for all active notices affecting a specific company.
    """
    seed_default_regulatory_intelligence(db)
    active_regs = db.query(RegulatoryIntelligence).filter(RegulatoryIntelligence.active == True).all()

    comp_ind = (company.industry or "").lower()
    matches = []

    for reg in active_regs:
        affected_industries = [str(i).lower() for i in (reg.affected_industries or [])]
        if any(ind in comp_ind or comp_ind in ind for ind in affected_industries):
            matches.append({
                "regulation_id": reg.id,
                "authority": reg.authority,
                "regulation_code": reg.regulation_code,
                "title": reg.title,
                "summary": reg.summary,
                "compliance_deadline": reg.compliance_deadline.isoformat() if reg.compliance_deadline else None,
                "commercial_impact": reg.commercial_impact_analysis,
            })

    return matches
