"""Source-traceable web research helpers for the Sales Assistant."""
from typing import Optional

from sqlalchemy.orm import Session

from models.web_research import WebResearchItem


def search_research(
    db: Session,
    query: str,
    company_id: Optional[int] = None,
    limit: int = 20,
):
    q = db.query(WebResearchItem)
    if company_id is not None:
        q = q.filter(WebResearchItem.company_id == company_id)
    if query:
        pattern = f"%{query.strip()}%"
        q = q.filter(
            (WebResearchItem.query.ilike(pattern))
            | (WebResearchItem.title.ilike(pattern))
            | (WebResearchItem.snippet.ilike(pattern))
            | (WebResearchItem.content.ilike(pattern))
        )
    rows = (
        q.order_by(WebResearchItem.retrieved_at.desc(), WebResearchItem.id.desc())
        .limit(min(max(limit, 1), 100))
        .all()
    )
    return {
        "results": [serialize_research(row) for row in rows],
        "total": len(rows),
        "query": query,
    }


def serialize_research(row: WebResearchItem):
    return {
        "id": row.id,
        "company_id": row.company_id,
        "query": row.query,
        "title": row.title,
        "url": row.url,
        "source_domain": row.source_domain,
        "published_date": row.published_date,
        "retrieved_at": row.retrieved_at,
        "signal_type": row.signal_type,
        "snippet": row.snippet,
        "content": row.content,
        "confidence": float(row.confidence or 0),
        "evidence_type": row.evidence_type,
        "metadata_json": row.metadata_json,
    }
