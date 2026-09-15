"""API routes for Pre-Serper Business Analyst and Search Strategy."""
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from models.business_analyst_decision import BusinessAnalystDecision
from services.business_analyst_service import business_analyst_service

router = APIRouter(prefix="/api/strategy", tags=["strategy"])


@router.get("/status")
def get_strategy_status(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Expose factual strategic search status without chain-of-thought."""
    return business_analyst_service.get_strategy_status(db=db)


@router.get("/decisions")
def list_strategy_decisions(
    limit: int = Query(20, ge=1, le=100),
    mode: Optional[str] = None,
    sector: Optional[str] = None,
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """List recent Business Analyst strategic search decisions."""
    q = db.query(BusinessAnalystDecision).order_by(BusinessAnalystDecision.id.desc())
    if mode:
        q = q.filter(BusinessAnalystDecision.mode == mode)
    if sector:
        q = q.filter(BusinessAnalystDecision.sector == sector)
    decisions = q.limit(limit).all()
    return [d.to_dict() for d in decisions]


@router.post("/evaluate")
def evaluate_strategy(
    preferred_sector: Optional[str] = None,
    preferred_geo: Optional[str] = None,
    preferred_trigger: Optional[str] = None,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Trigger an explicit strategic search portfolio evaluation."""
    decision = business_analyst_service.evaluate_next_strategy(
        db=db,
        preferred_sector=preferred_sector,
        preferred_geo=preferred_geo,
        preferred_trigger=preferred_trigger,
    )
    return {
        "status": "EVALUATED",
        "decision": decision.to_dict(),
    }
