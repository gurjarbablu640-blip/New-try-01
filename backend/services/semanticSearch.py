"""
Module 13: Semantic Search Engine
===================================
Allow salespeople to search leads using natural language, not just filters.

Examples of what should work:
  "pharma companies with CMM machines in Maharashtra"
  "electrical panel manufacturers hiring QA engineers"
  "companies with ISO 17025 that import from Germany"
  "high-value leads in Gujarat not contacted yet"
  "companies similar to ABC Industries Pune"

Implementation:
  1. Generate embeddings via Gemini text-embedding-004 (free tier)
  2. Store as vector(768) in companies table
  3. At search time, embed query and find nearest neighbors
  4. Re-rank by icp_score
"""
import logging
from typing import List, Dict, Optional, Any

import google.generativeai as genai
from sqlalchemy import text, desc
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import SessionLocal
from backend.models.company import Company
from backend.models.website_intel import CompanyWebsiteIntel
from backend.models.intent_signal import CompanyIntentSignal
from backend.models.pipeline import PipelineStage

logger = logging.getLogger(__name__)

# Configure Gemini
if settings.GOOGLE_API_KEY:
    genai.configure(api_key=settings.GOOGLE_API_KEY)

EMBEDDING_MODEL = "models/text-embedding-004"
EMBEDDING_DIMENSION = 768


# ============================================================
# EMBEDDING GENERATION
# ============================================================

def generate_embedding(text_input: str) -> Optional[List[float]]:
    """
    Generate a 768-dimensional embedding using Gemini text-embedding-004.
    Returns None if API is unavailable.
    """
    if not settings.GOOGLE_API_KEY:
        logger.warning("GOOGLE_API_KEY not set — embeddings unavailable")
        return None

    try:
        result = genai.embed_content(
            model=EMBEDDING_MODEL,
            content=text_input,
            task_type="retrieval_document",
        )
        return result["embedding"]

    except Exception as e:
        logger.error(f"Embedding generation error: {e}")
        return None


def generate_query_embedding(query: str) -> Optional[List[float]]:
    """Generate embedding for a search query (uses retrieval_query task type)."""
    if not settings.GOOGLE_API_KEY:
        return None

    try:
        result = genai.embed_content(
            model=EMBEDDING_MODEL,
            content=query,
            task_type="retrieval_query",
        )
        return result["embedding"]

    except Exception as e:
        logger.error(f"Query embedding error: {e}")
        return None


# ============================================================
# COMPANY TEXT BUILDER (for embedding)
# ============================================================

def build_company_text(company: Company, intel: Optional[CompanyWebsiteIntel] = None) -> str:
    """
    Build a rich text representation of a company for embedding.
    Combines all available data into a single string.
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

    # Clean and join
    text = " ".join(filter(None, parts))
    # Limit to ~500 tokens worth of text
    return text[:2000]


# ============================================================
# INDEX COMPANY (call on insert/update)
# ============================================================

def index_company(company_id: int, db: Session = None) -> bool:
    """
    Generate and store embedding for a company.
    Call this on company insert/update.
    """
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        company = db.query(Company).filter(Company.id == company_id).first()
        if not company:
            return False

        intel = db.query(CompanyWebsiteIntel).filter(
            CompanyWebsiteIntel.company_id == company_id
        ).first()

        # Build text and generate embedding
        company_text = build_company_text(company, intel)
        embedding = generate_embedding(company_text)

        if embedding:
            # Store embedding using raw SQL (pgvector)
            embedding_str = "[" + ",".join(map(str, embedding)) + "]"
            db.execute(
                text("UPDATE companies SET name_embedding = :emb WHERE id = :id"),
                {"emb": embedding_str, "id": company_id}
            )
            db.commit()
            logger.info(f"Indexed company {company_id}: {company.name}")
            return True
        else:
            logger.warning(f"Could not generate embedding for company {company_id}")
            return False

    except Exception as e:
        logger.error(f"Error indexing company {company_id}: {e}")
        db.rollback()
        return False

    finally:
        if close_db:
            db.close()


def index_all_companies(db: Session = None) -> Dict:
    """Index all companies in the database."""
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

        return {"indexed": indexed, "failed": failed, "total": len(companies)}

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
    Perform semantic search using natural language query.

    Args:
        query: Natural language search query
        limit: Max results to return (default 50)
        db: Database session
        filters: Optional additional filters (state, tier, etc.)

    Returns:
        List of matching companies with similarity scores
    """
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        # Generate query embedding
        query_embedding = generate_query_embedding(query)

        if query_embedding:
            # Vector similarity search using pgvector
            results = _vector_search(query_embedding, limit, db, filters)
        else:
            # Fallback to keyword search if embeddings unavailable
            results = _keyword_search(query, limit, db, filters)

        return results

    except Exception as e:
        logger.error(f"Semantic search error: {e}")
        # Fallback to keyword search
        return _keyword_search(query, limit, db, filters)

    finally:
        if close_db:
            db.close()


def _vector_search(
    query_embedding: List[float],
    limit: int,
    db: Session,
    filters: Optional[Dict] = None
) -> List[Dict]:
    """Perform vector similarity search using pgvector."""
    embedding_str = "[" + ",".join(map(str, query_embedding)) + "]"

    # Build WHERE clause for filters
    where_clauses = ["c.name_embedding IS NOT NULL"]
    params = {"query_emb": embedding_str, "limit": limit}

    if filters:
        if filters.get("state"):
            where_clauses.append("c.state = :state")
            params["state"] = filters["state"]
        if filters.get("tier"):
            where_clauses.append("c.calculated_tier = :tier")
            params["tier"] = filters["tier"]
        if filters.get("min_icp"):
            where_clauses.append("c.icp_score >= :min_icp")
            params["min_icp"] = filters["min_icp"]

    where_sql = " AND ".join(where_clauses)

    sql = text(f"""
        SELECT
            c.id,
            c.name,
            c.city,
            c.state,
            c.industry,
            c.calculated_tier,
            c.icp_score,
            c.buying_window,
            c.has_nabl,
            1 - (c.name_embedding <=> :query_emb::vector) as similarity
        FROM companies c
        WHERE {where_sql}
        ORDER BY c.name_embedding <=> :query_emb::vector
        LIMIT :limit
    """)

    rows = db.execute(sql, params).fetchall()

    results = []
    for row in rows:
        results.append({
            "company_id": row[0],
            "name": row[1],
            "city": row[2],
            "state": row[3],
            "industry": row[4],
            "tier": row[5],
            "icp_score": row[6],
            "buying_window": row[7],
            "has_nabl": row[8],
            "similarity_score": round(float(row[9]) * 100, 1),  # As percentage
        })

    # Re-rank by combination of similarity and ICP score
    results.sort(key=lambda x: (
        x["similarity_score"] * 0.6 + (x["icp_score"] or 0) * 0.4
    ), reverse=True)

    return results


def _keyword_search(
    query: str,
    limit: int,
    db: Session,
    filters: Optional[Dict] = None
) -> List[Dict]:
    """Fallback keyword-based search when embeddings unavailable."""
    # Parse query for keywords
    keywords = query.lower().split()

    # Build base query
    q = db.query(Company)

    # Apply text search across multiple fields
    for keyword in keywords:
        pattern = f"%{keyword}%"
        q = q.filter(
            (Company.name.ilike(pattern)) |
            (Company.city.ilike(pattern)) |
            (Company.state.ilike(pattern)) |
            (Company.industry.ilike(pattern)) |
            (Company.search_keyword.ilike(pattern))
        )

    # Apply filters
    if filters:
        if filters.get("state"):
            q = q.filter(Company.state == filters["state"])
        if filters.get("tier"):
            q = q.filter(Company.calculated_tier == filters["tier"])
        if filters.get("min_icp"):
            q = q.filter(Company.icp_score >= filters["min_icp"])

    companies = q.order_by(desc(Company.icp_score)).limit(limit).all()

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
            "similarity_score": None,  # No similarity score for keyword search
        })

    return results


# ============================================================
# SIMILAR COMPANIES (for lookalike)
# ============================================================

def find_similar_companies(
    company_id: int,
    limit: int = 20,
    db: Session = None
) -> List[Dict]:
    """Find companies similar to a given company using embedding similarity."""
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        # Get the target company's embedding
        result = db.execute(
            text("SELECT name_embedding FROM companies WHERE id = :id"),
            {"id": company_id}
        ).fetchone()

        if not result or not result[0]:
            # No embedding, fall back to attribute-based similarity
            return _attribute_similar(company_id, limit, db)

        # Use the company's embedding as query
        sql = text("""
            SELECT
                c.id, c.name, c.city, c.state, c.industry,
                c.calculated_tier, c.icp_score, c.buying_window,
                1 - (c.name_embedding <=> (SELECT name_embedding FROM companies WHERE id = :source_id)) as similarity
            FROM companies c
            WHERE c.id != :source_id
              AND c.name_embedding IS NOT NULL
            ORDER BY c.name_embedding <=> (SELECT name_embedding FROM companies WHERE id = :source_id)
            LIMIT :limit
        """)

        rows = db.execute(sql, {"source_id": company_id, "limit": limit}).fetchall()

        return [
            {
                "company_id": row[0],
                "name": row[1],
                "city": row[2],
                "state": row[3],
                "industry": row[4],
                "tier": row[5],
                "icp_score": row[6],
                "buying_window": row[7],
                "similarity_score": round(float(row[8]) * 100, 1),
            }
            for row in rows
        ]

    except Exception as e:
        logger.error(f"Find similar companies error: {e}")
        return _attribute_similar(company_id, limit, db)

    finally:
        if close_db:
            db.close()


def _attribute_similar(company_id: int, limit: int, db: Session) -> List[Dict]:
    """Fallback: find similar companies by attributes."""
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        return []

    q = db.query(Company).filter(Company.id != company_id)

    # Match on industry or state
    if company.industry:
        q = q.filter(Company.industry == company.industry)
    if company.state:
        q = q.filter(Company.state == company.state)

    results = q.order_by(desc(Company.icp_score)).limit(limit).all()

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
