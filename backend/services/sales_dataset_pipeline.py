"""Master Sales ML Dataset & Feature Pipeline Engine.

Constructs structured training datasets from CRM deals, quotations, assets, timeline events, and call outcomes.
Prepares feature matrices for conversion probability, price elasticity, and customer lifetime value prediction.
"""
from datetime import date, datetime
import logging
from typing import Any, Optional
from sqlalchemy.orm import Session

from models.company import Company
from models.company_brain import CompanyTimelineEvent, CompanyIntelligenceFact
from models.customer_asset import CustomerAsset
from models.person import Person
from models.sales_os import Quotation, Opportunity, PriceHistory

logger = logging.getLogger(__name__)


def extract_sales_ml_dataset(db: Session) -> dict[str, Any]:
    """
    Extracts unified, structured training records across all company sales journeys.
    """
    companies = db.query(Company).all()
    records = []

    for comp in companies:
        quotes = db.query(Quotation).filter(Quotation.company_id == comp.id).all()
        assets = db.query(CustomerAsset).filter(CustomerAsset.company_id == comp.id).all()
        events = db.query(CompanyTimelineEvent).filter(CompanyTimelineEvent.company_id == comp.id).all()
        persons = db.query(Person).filter(Person.company_id == comp.id).all()

        has_expansion = int(any(e.event_type in ["plant_expansion", "capex", "new_production_line"] for e in events))
        has_qa_hiring = int(any(e.event_type in ["qa_hired", "metrology_hired"] for e in events))
        has_iatf = int(any(e.event_type in ["iso_certified", "iatf_certified"] for e in events))
        has_overdue_assets = int(any(a.calibration_due_date and a.calibration_due_date <= date.today() for a in assets))

        engaged_roles = [p.designation for p in persons if p.designation]
        primary_role = "Quality" if any("quality" in r.lower() or "qa" in r.lower() for r in engaged_roles) else ("Purchase" if any("purchase" in r.lower() for r in engaged_roles) else "General")

        if quotes:
            for q in quotes:
                is_won = 1 if q.status == "Won" or q.human_approved else 0
                days_to_convert = (q.quotation_date - comp.created_at.date()).days if q.quotation_date and comp.created_at else 14
                records.append({
                    "company_id": comp.id,
                    "company_name": comp.name,
                    "industry": comp.industry or "Manufacturing",
                    "city": comp.city or "Pune",
                    "icp_score": comp.icp_score or 75,
                    "has_expansion_signal": has_expansion,
                    "has_qa_hiring": has_qa_hiring,
                    "has_iatf_cert": has_iatf,
                    "has_overdue_assets": has_overdue_assets,
                    "known_instrument_count": len(assets),
                    "quotation_number": q.quotation_number,
                    "quoted_amount_inr": float(q.total or 0),
                    "primary_stakeholder_role": primary_role,
                    "buying_window": comp.buying_window or "60_days",
                    "is_converted": is_won,
                    "days_to_conversion": max(days_to_convert, 1),
                })
        else:
            # Unquoted lead row
            records.append({
                "company_id": comp.id,
                "company_name": comp.name,
                "industry": comp.industry or "Manufacturing",
                "city": comp.city or "Pune",
                "icp_score": comp.icp_score or 75,
                "has_expansion_signal": has_expansion,
                "has_qa_hiring": has_qa_hiring,
                "has_iatf_cert": has_iatf,
                "has_overdue_assets": has_overdue_assets,
                "known_instrument_count": len(assets),
                "quotation_number": None,
                "quoted_amount_inr": 0.0,
                "primary_stakeholder_role": primary_role,
                "buying_window": comp.buying_window or "60_days",
                "is_converted": 0,
                "days_to_conversion": 0,
            })

    total_samples = len(records)
    converted_samples = sum(r["is_converted"] for r in records)
    conversion_rate = round(converted_samples / max(total_samples, 1) * 100, 1)

    return {
        "total_dataset_rows": total_samples,
        "converted_outcomes": converted_samples,
        "observed_conversion_rate": f"{conversion_rate}%",
        "dataset_ready_for_ml": total_samples >= 100,
        "status_message": f"Dataset contains {total_samples} historical sales records. Statistical models (XGBoost/LightGBM) recommended when N >= 100. Current mode: Transparent Baseline Heuristics + Rule Learning." if total_samples < 100 else "Dataset is statistically sufficient for XGBoost training.",
        "records": records,
    }
