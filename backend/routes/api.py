"""
Main API Routes — FastAPI
===========================
All new API endpoints for Modules 8-17.
"""
import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import SessionLocal
from models.company import Company

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["API"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---- Request schemas ----

class SemanticSearchRequest(BaseModel):
    query: str
    limit: int = 50
    filters: Optional[dict] = None


class OutreachGenerateRequest(BaseModel):
    company_id: int


class OutreachBatchRequest(BaseModel):
    company_ids: List[int]


class RateLeadRequest(BaseModel):
    rating: int
    reason: Optional[str] = None


class ApproveLookalikesRequest(BaseModel):
    company_ids: List[int]


# ---- Endpoints ----

@router.post("/triggers/run-now")
def run_triggers():
    """Manually trigger all buying trigger engines."""
    from workers.triggerEngine import run_all_triggers

    try:
        result = run_all_triggers()
        return {"success": True, "results": result}
    except Exception as e:
        logger.error(f"Trigger run error: {e}")
        raise HTTPException(500, str(e))


@router.get("/buying-window")
def get_buying_window(db: Session = Depends(get_db)):
    """Get companies organized by 30/60/90 day buying window."""
    from services.buyingWindow import get_buying_window_board

    result = get_buying_window_board(db)
    return result


@router.get("/companies")
def get_companies_route(
    q: Optional[str] = None,
    city: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """List companies for CRM and Decision Intelligence workspaces."""
    query = db.query(Company)
    if q:
        query = query.filter(Company.name.ilike(f"%{q}%"))
    if city:
        query = query.filter(Company.city.ilike(f"%{city}%"))

    total = query.count()
    companies = query.order_by(Company.created_at.desc(), Company.id.desc()).offset(offset).limit(limit).all()
    return {
        "success": True,
        "total": total,
        "results": [
            {
                "id": c.id,
                "name": c.name,
                "city": c.city,
                "state": c.state,
                "industry": c.industry,
                "icp_score": c.icp_score,
                "buying_window": c.buying_window,
                "qualification_status": getattr(c, "qualification_status", "QUALIFIED"),
                "lead_status": getattr(c, "lead_status", "New"),
                "phone": getattr(c, "phone", None),
                "email": getattr(c, "email", None),
                "website": getattr(c, "website", None),
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in companies
        ],
    }


@router.get("/companies/{company_id}")
def get_company_detail_route(company_id: int, db: Session = Depends(get_db)):
    """Get single company details."""
    c = db.query(Company).filter(Company.id == company_id).first()
    if not c:
        raise HTTPException(404, "Company not found")
    return {
        "id": c.id,
        "name": c.name,
        "city": c.city,
        "state": c.state,
        "industry": c.industry,
        "icp_score": c.icp_score,
        "buying_window": c.buying_window,
        "qualification_status": getattr(c, "qualification_status", "QUALIFIED"),
        "lead_status": getattr(c, "lead_status", "New"),
        "phone": getattr(c, "phone", None),
        "email": getattr(c, "email", None),
        "website": getattr(c, "website", None),
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


@router.get("/tasks/today")
def get_today_tasks(db: Session = Depends(get_db)):
    """Get today's action queue sorted by urgency + ICP."""
    from routes.pipeline import get_todays_tasks

    return get_todays_tasks(db=db)


@router.post("/companies/{company_id}/rate")
def rate_company(company_id: int, body: RateLeadRequest, db: Session = Depends(get_db)):
    """Rate a lead 1-5 stars for ICP learning."""
    from services.icpLearner import rate_lead

    if body.rating < 1 or body.rating > 5:
        raise HTTPException(400, "Rating must be 1-5")

    result = rate_lead(company_id, body.rating, body.reason, db)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@router.get("/lookalikes")
def get_lookalikes(db: Session = Depends(get_db)):
    """Get all AI-identified lookalike leads not yet contacted."""
    from services.lookalikeEngine import get_lookalike_leads

    leads = get_lookalike_leads(db)
    return {"leads": leads, "total": len(leads)}


@router.post("/lookalikes/approve")
def approve_lookalikes_route(body: ApproveLookalikesRequest, db: Session = Depends(get_db)):
    """Approve batch of lookalike leads for outreach."""
    from services.lookalikeEngine import approve_lookalikes

    if not body.company_ids:
        raise HTTPException(400, "company_ids list required")
    result = approve_lookalikes(body.company_ids, db)
    return result


@router.post("/search/semantic")
def semantic_search_route(body: SemanticSearchRequest, db: Session = Depends(get_db)):
    """Natural language lead search."""
    from services.semanticSearch import semantic_search

    results = semantic_search(body.query, limit=body.limit, db=db, filters=body.filters)
    return {"results": results, "total": len(results), "query": body.query}


@router.get("/ab-insights")
def get_ab_insights_route(db: Session = Depends(get_db)):
    """Get subject line A/B performance data."""
    from services.abOptimizer import get_ab_insights

    return get_ab_insights(db)


@router.get("/icp-insights")
def get_icp_insights_route(db: Session = Depends(get_db)):
    """Get what the AI has learned about ICP."""
    from services.icpLearner import get_icp_insights

    return get_icp_insights(db)


@router.post("/outreach/generate")
def generate_outreach_route(body: OutreachGenerateRequest, db: Session = Depends(get_db)):
    """Generate personalized outreach for a company."""
    from services.ai_synthesis import generate_outreach

    result = generate_outreach(body.company_id, db)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@router.post("/outreach/generate-batch")
def generate_outreach_batch_route(body: OutreachBatchRequest, db: Session = Depends(get_db)):
    """Generate outreach for multiple companies."""
    from services.ai_synthesis import generate_outreach_batch

    if not body.company_ids:
        raise HTTPException(400, "company_ids list required")
    return generate_outreach_batch(body.company_ids, db)


@router.get("/companies/{company_id}/next-action")
def get_next_action(company_id: int, db: Session = Depends(get_db)):
    """Get AI recommended next action for a company."""
    from services.nextBestAction import get_next_best_action

    result = get_next_best_action(company_id, db)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@router.post("/companies/{company_id}/rescore")
def rescore_company(company_id: int, db: Session = Depends(get_db)):
    """Recalculate ICP score for a company."""
    from services.scoringEngine import calculate_icp_score

    result = calculate_icp_score(company_id, db)
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result


@router.post("/scoring/rescore-all")
def rescore_all(db: Session = Depends(get_db)):
    """Rescore all companies (admin action)."""
    from services.scoringEngine import rescore_all_companies

    return rescore_all_companies(db)


@router.post("/search/index-all")
def index_all_companies(db: Session = Depends(get_db)):
    """Index all companies for semantic search (admin action)."""
    from services.semanticSearch import index_all_companies as do_index

    return do_index(db)
