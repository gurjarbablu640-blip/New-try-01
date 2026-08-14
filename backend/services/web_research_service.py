"""Source-traceable web research helpers for the Sales Assistant."""
from typing import Optional

from sqlalchemy.orm import Session

from models.web_research import WebResearch


def search_research(
    db: Session,
    query: str,
    company_id: Optional[int] = None,
    limit: int = 20,
):
    q = db.query(WebResearch)
    if company_id is not None:
        q = q.filter(WebResearch.company_id == company_id)
    if query:
        pattern = f"%{query.strip()}%"
        q = q.filter(
            (WebResearch.query.ilike(pattern))
            | (WebResearch.title.ilike(pattern))
            | (WebResearch.snippet.ilike(pattern))
            | (WebResearch.content.ilike(pattern))
        )
    rows = q.order_by(WebResearch.retrieved_at.desc(), WebResearch.id.desc()).limit(min(max(limit, 1), 100)).all()
    return {
        "results": [serialize_research(row) for row in rows],
        "total": len(rows),
        "query": query,
    }


def serialize_research(row: WebResearch):
    return {
        "id": row.id,
        "company_id": row.company_id,
        "query": row.query,
        "title": row.title,
        "url": row.url,
        "source_domain": row.source_domain,
        "published_at": row.published_at,
        "retrieved_at": row.retrieved_at,
        "signal_type": row.signal_type,
        "evidence": row.evidence,
        "confidence": float(row.confidence or 0),
        "classification": row.classification,
    }
