"""
Module 13: Semantic Search Engine
===================================
Fallback-safe semantic search system.

Gemini embeddings temporarily disabled due to API compatibility issues.
System automatically falls back to SQL keyword search.
"""

import logging
from typing import List, Dict, Optional, Any

from sqlalchemy import text, desc, or_
from sqlalchemy.orm import Session

from config import settings
from database import SessionLocal
from models.company import Company
from models.website_intel import CompanyWebsiteIntel

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = None
EMBEDDING_DIMENSION = 768


# ============================================================
# EMBEDDING GENERATION (DISABLED)
# ============================================================

def generate_embedding(text_input: str) -> Optional[List[float]]:
    """
    Temporary fallback mode.

    Gemini embedding APIs are disabled.
    System will automatically use keyword search instead.
    """
    logger.warning(
        "Embeddings disabled — using keyword search fallback"
    )
    return None


def generate_query_embedding(query: str) -> Optional[List[float]]:
    """
    Temporary fallback mode for query embeddings.
    """
    logger.warning(
        "Query embeddings disabled — using keyword search fallback"
    )
    return None


# ============================================================
# COMPANY TEXT BUILDER
# ============================================================

def build_company_text(
    company: Company,
    intel: Optional[CompanyWebsiteIntel] = None
) -> str:
    """
    Build searchable company text.
    """

    parts = [
        company.name or "",
        company.city or "",
        company.state or "",
        company.industry or "",
        company.search_keyword or "",
        company.calculated_tier or "",
    ]

    if intel:
        if intel.instruments_found:
            parts.append(" ".join(intel.instruments_found))

        if intel.iso_standards:
            parts.append(" ".join(intel.iso_standards))

        if intel.oem_brands:
            parts.append(" ".join(intel.oem_brands))

        if intel.services_offered:
            parts.append(" ".join(intel.services_offered))

        if intel.industries_served:
            parts.append(" ".join(intel.industries_served))

    if company.has_nabl:
        parts.append("NABL accredited laboratory")

    if company.export_active:
        parts.append("export active international trade")

    text_data = " ".join(filter(None, parts))

    return text_data[:2000]


# ============================================================
# INDEX COMPANY
# ============================================================

def index_company(company_id: int, db: Session = None) -> bool:
    """
    Index company.

    Since embeddings are disabled,
    this simply validates company existence.
    """

    close_db = False

    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        company = (
            db.query(Company)
            .filter(Company.id == company_id)
            .first()
        )

        if not company:
            return False

        logger.info(
            f"Indexed company (keyword mode): {company.name}"
        )

        return True

    except Exception as e:
        logger.error(f"Index company error: {e}")
        return False

    finally:
        if close_db:
            db.close()


def index_all_companies(db: Session = None) -> Dict:
    """
    Index all companies.
    """

    close_db = False

    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        companies = db.query(Company).all()

        indexed = 0
        failed = 0

        for company in companies:
            if index_company(company.id, db):
                indexed += 1
            else:
                failed += 1

        return {
            "indexed": indexed,
            "failed": failed,
            "total": len(companies),
        }

    finally:
        if close_db:
            db.close()


# ============================================================
# SEMANTIC SEARCH
# ============================================================

def semantic_search(
    query: str,
    limit: int = 50,
    db: Session = None,
    filters: Optional[Dict] = None
) -> List[Dict[str, Any]]:
    """
    Perform fallback keyword search.
    """

    close_db = False

    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        results = _keyword_search(
            query=query,
            limit=limit,
            db=db,
            filters=filters
        )

        return results

    except Exception as e:
        logger.error(f"Semantic search error: {e}")
        return []

    finally:
        if close_db:
            db.close()


# ============================================================
# KEYWORD SEARCH
# ============================================================

def _keyword_search(
    query: str,
    limit: int,
    db: Session,
    filters: Optional[Dict] = None
) -> List[Dict]:
    """
    SQL keyword-based search.
    """

    keywords = query.lower().split()

    q = db.query(Company)

    search_conditions = []

    for keyword in keywords:
        pattern = f"%{keyword}%"

        search_conditions.extend([
            Company.name.ilike(pattern),
            Company.city.ilike(pattern),
            Company.state.ilike(pattern),
            Company.industry.ilike(pattern),
            Company.search_keyword.ilike(pattern),
        ])

    if search_conditions:
        q = q.filter(or_(*search_conditions))

    # Optional filters
    if filters:
        if filters.get("state"):
            q = q.filter(
                Company.state == filters["state"]
            )

        if filters.get("tier"):
            q = q.filter(
                Company.calculated_tier == filters["tier"]
            )

        if filters.get("min_icp"):
            q = q.filter(
                Company.icp_score >= filters["min_icp"]
            )

    companies = (
        q.order_by(desc(Company.icp_score))
        .limit(limit)
        .all()
    )

    results = []

    for company in companies:
        results.append({
            "company_id": company.id,
            "name": company.name,
            "city": company.city,
            "state": company.state,
            "industry": company.industry,
            "tier": company.calculated_tier,
            "icp_score": company.icp_score,
            "buying_window": company.buying_window,
            "has_nabl": company.has_nabl,
            "similarity_score": None,
        })

    return results


# ============================================================
# SIMILAR COMPANIES
# ============================================================

def find_similar_companies(
    company_id: int,
    limit: int = 20,
    db: Session = None
) -> List[Dict]:
    """
    Find similar companies using attribute matching.
    """

    close_db = False

    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        return _attribute_similar(
            company_id,
            limit,
            db
        )

    except Exception as e:
        logger.error(f"Find similar companies error: {e}")
        return []

    finally:
        if close_db:
            db.close()


def _attribute_similar(
    company_id: int,
    limit: int,
    db: Session
) -> List[Dict]:

    company = (
        db.query(Company)
        .filter(Company.id == company_id)
        .first()
    )

    if not company:
        return []

    q = db.query(Company).filter(
        Company.id != company_id
    )

    if company.industry:
        q = q.filter(
            Company.industry == company.industry
        )

    if company.state:
        q = q.filter(
            Company.state == company.state
        )

    results = (
        q.order_by(desc(Company.icp_score))
        .limit(limit)
        .all()
    )

    return [
        {
            "company_id": c.id,
            "name": c.name,
            "city": c.city,
            "state": c.state,
            "industry": c.industry,
            "tier": c.calculated_tier,
            "icp_score": c.icp_score,
            "buying_window": c.buying_window,
            "similarity_score": None,
        }
        for c in results
    ]