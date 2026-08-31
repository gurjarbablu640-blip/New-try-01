"""Multi-Dimensional Lead Intelligence Scorer & Explainability Engine.

Evaluates leads across separate commercial dimensions:
1. Buy Probability (0.0 - 1.0)
2. Price Sensitivity (Low, Medium, High)
3. Premium Acceptance Potential (Low, Medium, High, Very High)
4. Calibration Need Score (0 - 100)
5. Buying Window (immediate, 30_days, 60_days, 90_days, future_nurture)
6. Opportunity Value Estimation (INR)

Generates transparent score explanations (+7 Plant expansion, +5 Regulation change, etc.)
and classifies accounts into Strategic Segments (Volume vs Premium Margin).
"""
from dataclasses import dataclass, field
from datetime import date, datetime
import logging
from typing import Any, Optional
from sqlalchemy.orm import Session

from models.company import Company
from models.company_brain import CompanyIntelligenceFact, CompanyTimelineEvent
from models.customer_asset import CustomerAsset
from models.sales_os import Quotation
from services.calibration_inference_engine import estimate_instrument_population

logger = logging.getLogger(__name__)


@dataclass
class LeadScoreCard:
    company_id: int
    company_name: str
    composite_score: int
    buy_probability: float
    price_sensitivity: str
    premium_potential: str
    calibration_need_score: int
    buying_window: str
    opportunity_value_inr: float
    confidence: float
    strategic_segment: str
    score_reasons: list[dict[str, Any]] = field(default_factory=list)


def evaluate_lead_intelligence(company: Company, db: Session) -> LeadScoreCard:
    """
    Computes full multi-dimensional intelligence scorecard with granular factor explanations.
    """
    reasons = []
    base_score = 50.0

    # 1. Timeline & Events Signals
    events = (
        db.query(CompanyTimelineEvent)
        .filter(CompanyTimelineEvent.company_id == company.id)
        .all()
    )
    has_expansion = any(e.event_type in ["plant_expansion", "capex", "new_production_line"] for e in events)
    has_qa_hiring = any(e.event_type in ["qa_hired", "metrology_hired"] for e in events)
    has_certification = any(e.event_type in ["iso_certified", "iatf_certified", "nabl_accreditation"] for e in events)

    if has_expansion:
        base_score += 15.0
        reasons.append({"factor": "Plant expansion / CAPEX detected", "delta": "+15", "type": "positive"})
    if has_qa_hiring:
        base_score += 10.0
        reasons.append({"factor": "Quality / Metrology hiring signal", "delta": "+10", "type": "positive"})
    if has_certification:
        base_score += 8.0
        reasons.append({"factor": "IATF / ISO compliance environment", "delta": "+8", "type": "positive"})

    # 2. Asset & Calibration Urgency Signals
    assets = db.query(CustomerAsset).filter(CustomerAsset.company_id == company.id).all()
    overdue_assets = [a for a in assets if a.calibration_due_date and a.calibration_due_date <= date.today()]
    due_soon_assets = [a for a in assets if a.calibration_due_date and date.today() < a.calibration_due_date <= (date.today() + datetime.resolution * 30)]

    if overdue_assets:
        base_score += 12.0
        reasons.append({"factor": f"{len(overdue_assets)} instruments currently overdue for calibration", "delta": "+12", "type": "positive"})
        buying_window = "immediate"
    elif due_soon_assets:
        base_score += 8.0
        reasons.append({"factor": f"{len(due_soon_assets)} instruments due within 30 days", "delta": "+8", "type": "positive"})
        buying_window = "30_days"
    else:
        buying_window = company.buying_window or "60_days"

    # 3. Industry Archetype & Premium Signals
    comp_ind = (company.industry or "").lower()
    is_premium_ind = any(k in comp_ind for k in ["automotive", "ev", "battery", "pharma", "aerospace", "defense", "medical"])
    if is_premium_ind:
        base_score += 10.0
        reasons.append({"factor": f"High-consequence industry ({company.industry})", "delta": "+10", "type": "positive"})
        premium_potential = "Very High" if has_expansion or has_certification else "High"
        price_sensitivity = "Low"
    else:
        premium_potential = "Medium"
        price_sensitivity = "Medium"

    # 4. Quotation History Signals
    quotes = db.query(Quotation).filter(Quotation.company_id == company.id).all()
    if quotes:
        won_quotes = [q for q in quotes if q.status == "Won" or q.human_approved]
        if won_quotes:
            base_score += 10.0
            reasons.append({"factor": "Existing approved quotation history with Oorja", "delta": "+10", "type": "positive"})
            price_sensitivity = "Low"
        else:
            reasons.append({"factor": "Past quotation submitted; evaluating conversion", "delta": "+4", "type": "neutral"})

    composite_score = int(min(max(base_score, 20.0), 99.0))
    buy_probability = round(composite_score / 100.0, 2)
    calibration_need_score = int(min(composite_score + 5, 100))

    # Instrument population & opportunity value estimation
    pop_data = estimate_instrument_population(company, db)
    opportunity_val = pop_data["estimated_annual_calibration_market_inr"]

    # Strategic Segment Assignment
    if premium_potential in ["High", "Very High"] and price_sensitivity == "Low":
        strategic_segment = "Premium Margin Target"
    elif buy_probability >= 0.75 and price_sensitivity in ["Medium", "High"]:
        strategic_segment = "Volume Target"
    elif opportunity_val >= 500000.0:
        strategic_segment = "Strategic High-Value Account"
    else:
        strategic_segment = "Nurture / Standard Outreach"

    # Confidence calculation
    confidence = 0.90 if len(events) + len(assets) + len(quotes) >= 3 else 0.75

    return LeadScoreCard(
        company_id=company.id,
        company_name=company.name,
        composite_score=composite_score,
        buy_probability=buy_probability,
        price_sensitivity=price_sensitivity,
        premium_potential=premium_potential,
        calibration_need_score=calibration_need_score,
        buying_window=buying_window,
        opportunity_value_inr=opportunity_val,
        confidence=confidence,
        strategic_segment=strategic_segment,
        score_reasons=reasons,
    )
