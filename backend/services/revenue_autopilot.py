"""Next Best Revenue Action, Deal Rescue & Account Expansion Engine.

Answers: "What is the single highest-probability action we can take right now to create profitable revenue?"
Includes:
1. Next Best Revenue Action Optimizer
2. Deal Rescue AI for stalled quotations and procurement objections
3. Account White-Space Mapping & Cross-Selling for existing accounts
"""
from datetime import date, datetime, timedelta
import logging
from typing import Any, Optional
from sqlalchemy.orm import Session

from models.company import Company
from models.customer_asset import CustomerAsset
from models.person import Person
from models.sales_os import Opportunity, Quotation, QuotationItem
from services.calibration_inference_engine import infer_calibration_need, estimate_instrument_population
from services.lead_intelligence_scorer import evaluate_lead_intelligence

logger = logging.getLogger(__name__)


def compute_next_best_revenue_action(company: Company, db: Session) -> dict[str, Any]:
    """
    Evaluates account state, stalled quotes, calibration urgency, and relationship history
    to recommend the optimal revenue-generating sales action.
    """
    scorecard = evaluate_lead_intelligence(company, db)
    quotes = db.query(Quotation).filter(Quotation.company_id == company.id).all()
    assets = db.query(CustomerAsset).filter(CustomerAsset.company_id == company.id).all()
    persons = db.query(Person).filter(Person.company_id == company.id).all()

    # 1. Deal Rescue Evaluation (Priority 1)
    open_quotes = [q for q in quotes if q.status not in ["Won", "Lost", "Rejected"]]
    if open_quotes:
        rescue_diag = diagnose_deal_rescue(open_quotes[0], db)
        if rescue_diag.get("requires_action"):
            return {
                "company_id": company.id,
                "company_name": company.name,
                "priority": "Critical",
                "recommended_action": rescue_diag["recommended_action"],
                "channel": rescue_diag["recommended_channel"],
                "target_role": rescue_diag["target_role"],
                "reasoning": rescue_diag["diagnosis"],
                "expected_impact": "Prevents deal loss to competitor or premature price discounting.",
                "category": "deal_rescue",
            }

    # 2. Critical Overdue Assets (Priority 2)
    overdue_assets = [a for a in assets if a.calibration_due_date and a.calibration_due_date <= date.today()]
    if overdue_assets and scorecard.buy_probability >= 0.70:
        return {
            "company_id": company.id,
            "company_name": company.name,
            "priority": "High",
            "recommended_action": f"Call Quality Manager immediately regarding {len(overdue_assets)} overdue instruments.",
            "channel": "Phone Call",
            "target_role": "Head - Quality / Metrology",
            "reasoning": f"Critical audit risk detected. {overdue_assets[0].instrument_name} is overdue for calibration.",
            "expected_impact": "High-urgency booking for on-site or laboratory calibration.",
            "category": "urgent_calibration",
        }

    # 3. Account White-Space Expansion (Priority 3)
    if quotes and any(q.status == "Won" or q.human_approved for q in quotes):
        white_space = generate_account_whitespace_map(company, db)
        unserved = [k for k, v in white_space.get("whitespace_map", {}).items() if v["status"] != "Served by Oorja"]
        if unserved:
            return {
                "company_id": company.id,
                "company_name": company.name,
                "priority": "Medium",
                "recommended_action": f"Initiate cross-sell campaign for unserved parameter: {unserved[0]}.",
                "channel": "Email + Technical Brief",
                "target_role": "Head - Quality / Metrology",
                "reasoning": f"Oorja successfully serves active contracts. High lookalike probability to expand into {unserved[0]}.",
                "expected_impact": f"Expands account contract value by an estimated ₹{int(scorecard.opportunity_value_inr * 0.35):,}.",
                "category": "account_expansion",
            }

    # 4. Strategic High-Value Lead Engagement (Priority 4)
    if scorecard.strategic_segment in ["Premium Margin Target", "Strategic High-Value Account"]:
        return {
            "company_id": company.id,
            "company_name": company.name,
            "priority": "High",
            "recommended_action": "Execute targeted multi-touch sequence: Send Audit Readiness Brief to Quality Head, follow up with commercial rate card to Purchase.",
            "channel": "Email + Planned Field Visit",
            "target_role": "Head - Quality / Metrology & Purchase Manager",
            "reasoning": f"Identified as {scorecard.strategic_segment} with ₹{int(scorecard.opportunity_value_inr):,} annual potential.",
            "expected_impact": "Establishes multi-parameter accredited relationship at premium margin.",
            "category": "strategic_acquisition",
        }

    # 5. Default Standard Nurture
    return {
        "company_id": company.id,
        "company_name": company.name,
        "priority": "Low",
        "recommended_action": "Schedule automated educational outreach on NABL traceability and calibration intervals.",
        "channel": "Email",
        "target_role": "Quality / Technical Staff",
        "reasoning": "Standard profile; monitor for expansion or hiring signals.",
        "expected_impact": "Maintains brand awareness until active buying window opens.",
        "category": "nurture",
    }


def diagnose_deal_rescue(quotation: Quotation, db: Session) -> dict[str, Any]:
    """
    Analyzes stalled quotation state and recommends specific deal rescue intervention.
    """
    days_open = (date.today() - quotation.quotation_date).days if quotation.quotation_date else 15
    company = db.query(Company).filter(Company.id == quotation.company_id).first()

    # If deal has been open > 10 days with no decision
    if days_open >= 10:
        return {
            "requires_action": True,
            "diagnosis": f"Quotation {quotation.quotation_number} has been pending for {days_open} days. Risk of procurement-led stalling or competitor price comparison.",
            "recommended_action": "Engage Quality/Metrology Manager to reinforce technical preference (turnaround & NABL CMC) before Purchase finalizes lowest bid.",
            "recommended_channel": "Direct Phone Call + Quality Consultation",
            "target_role": "Head - Quality / Metrology",
        }

    return {"requires_action": False}


def generate_account_whitespace_map(company: Company, db: Session) -> dict[str, Any]:
    """
    Generates a parameter White-Space Map for an existing customer account,
    identifying which calibration parameters are served by Oorja vs Competitors vs Unserved.
    """
    assets = db.query(CustomerAsset).filter(CustomerAsset.company_id == company.id).all()
    served_params = {str(a.parameter).strip().title() for a in assets if a.parameter}

    inference = infer_calibration_need(company, db)
    all_likely_params = [p["parameter"] for p in inference["parameter_inferences"]]

    whitespace_map = {}
    for param in all_likely_params:
        if param in served_params:
            whitespace_map[param] = {"status": "Served by Oorja", "coverage": "Active", "color": "green"}
        else:
            whitespace_map[param] = {"status": "Unserved / Competitor Opportunity", "coverage": "White-Space", "color": "orange"}

    return {
        "company_id": company.id,
        "company_name": company.name,
        "served_parameters": list(served_params),
        "whitespace_map": whitespace_map,
        "expansion_opportunity_count": len([k for k, v in whitespace_map.items() if v["coverage"] == "White-Space"]),
    }
