"""Lead qualification gate service.

Implements discrete qualification states:
- RAW: Initial ingested state.
- NEEDS_ENRICHMENT: Strong company fit, but missing verified contacts/emails.
- QUALIFIED: Verified target ICP company fit.
- READY_FOR_OUTREACH: Qualified company WITH deliverable decision-maker contacts.
- DISQUALIFIED: Excluded by negative ICP flags (trader, government, non-target).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from models.company import Company
from models.person import Person
from services.scoringEngine import calculate_icp_score
from services.opportunity_gates import evaluate_company_opportunity, READY_FOR_EMAIL, HOT

VALID_QUALIFICATION_STATUSES = {
    "RAW",
    "NEEDS_ENRICHMENT",
    "QUALIFIED",
    "READY_FOR_OUTREACH",
    READY_FOR_EMAIL,
    HOT,
    "DISQUALIFIED",
}


def evaluate_lead_qualification(db: Session, company_id: int) -> dict[str, Any]:
    """Deterministically evaluate the appropriate qualification state for a company.

    Rules:
    1. Critical negative ICP flag (e.g. trading company, dormant) -> DISQUALIFIED
    2. High negative score or score < 25 -> DISQUALIFIED
    3. Strong ICP (score >= 40) + has at least one valid/risky contact email -> READY_FOR_OUTREACH
    4. Strong ICP (score >= 40) + no verified contact email -> NEEDS_ENRICHMENT
    5. Moderate ICP (25 <= score < 40) -> QUALIFIED
    """
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        return {"error": "Company not found"}

    # Recalculate / refresh ICP score
    scoring_res = calculate_icp_score(company_id, db)
    icp_score = scoring_res.get("icp_score", company.icp_score or 0)
    negative_flags = scoring_res.get("negative_flags", company.negative_icp_flags or [])

    # Check for hard disqualifiers
    if any(flag in negative_flags for flag in ["trading_company_only", "dormant_company", "duplicate_listing"]):
        new_status = "DISQUALIFIED"
        reason = f"Disqualified due to negative ICP flag: {', '.join(negative_flags)}"
    elif icp_score < 25:
        new_status = "DISQUALIFIED"
        reason = f"ICP score ({icp_score}) is below minimum viable qualification threshold (25)"
    else:
        gates = evaluate_company_opportunity(db, company_id)
        new_status = gates["status"] if gates["status"] in {READY_FOR_EMAIL, HOT} else "NEEDS_ENRICHMENT" if icp_score >= 40 else "QUALIFIED"
        reason = gates["reason"]

    company.qualification_status = new_status
    company.qualification_reason = reason
    company.qualified_at = datetime.utcnow()
    db.commit()

    return {
        "company_id": company.id,
        "company_name": company.name,
        "qualification_status": new_status,
        "qualification_reason": reason,
        "icp_score": icp_score,
        "tier": company.calculated_tier,
        "qualified_at": company.qualified_at.isoformat() if company.qualified_at else None,
    }


def set_qualification_status(
    db: Session,
    company_id: int,
    status: str,
    reason: Optional[str] = None,
) -> dict[str, Any]:
    """Manually update qualification state with user justification."""
    upper_status = status.strip().upper()
    if upper_status not in VALID_QUALIFICATION_STATUSES:
        return {"error": f"Invalid status: {status}. Must be one of {VALID_QUALIFICATION_STATUSES}"}

    if upper_status in {"READY_FOR_OUTREACH", READY_FOR_EMAIL, HOT}:
        return {"error": "Ready status is evaluator-controlled; run the seven opportunity gates"}

    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        return {"error": "Company not found"}

    company.qualification_status = upper_status
    if reason:
        company.qualification_reason = reason
    company.qualified_at = datetime.utcnow()
    db.commit()

    return {
        "company_id": company.id,
        "company_name": company.name,
        "qualification_status": company.qualification_status,
        "qualification_reason": company.qualification_reason,
        "qualified_at": company.qualified_at.isoformat() if company.qualified_at else None,
    }


def batch_evaluate_leads(db: Session, company_ids: list[int]) -> dict[str, Any]:
    """Evaluate qualification status for a batch of companies."""
    results = []
    for cid in company_ids:
        res = evaluate_lead_qualification(db, cid)
        results.append(res)
    return {"total": len(results), "results": results}
