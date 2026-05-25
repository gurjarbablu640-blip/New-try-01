"""
Module 14: Lookalike Expansion Engine
=======================================
Your best customers reveal what your ideal prospects look like.
Use this to find 100 more companies exactly like your top 10.

Trigger: when a company is moved to stage='Won' in pipeline.
  1. Get that company's full feature vector
  2. Store in won_customers table
  3. Find similar companies using semantic search
  4. Auto-add to pipeline as 'New' with lookalike source
  5. Dashboard badge: "17 new lookalike leads found today"
"""
import json
import logging
from datetime import datetime, date
from typing import List, Dict, Optional

from sqlalchemy import text, desc, func
from sqlalchemy.orm import Session

from backend.celery_app import celery_app
from backend.database import SessionLocal
from backend.models.company import Company
from backend.models.pipeline import PipelineStage
from backend.models.website_intel import CompanyWebsiteIntel
from backend.services.semanticSearch import find_similar_companies

logger = logging.getLogger(__name__)


# ============================================================
# WON CUSTOMER REGISTRATION
# ============================================================

def register_won_customer(company_id: int, db: Session = None):
    """
    Register a company as a won customer and store its feature vector.
    Called when pipeline stage moves to 'Won'.
    """
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        company = db.query(Company).filter(Company.id == company_id).first()
        if not company:
            return

        intel = db.query(CompanyWebsiteIntel).filter(
            CompanyWebsiteIntel.company_id == company_id
        ).first()

        # Build feature vector
        feature_vector = {
            "icp_score": company.icp_score,
            "state": company.state,
            "city": company.city,
            "industry": company.industry,
            "search_keyword": company.search_keyword,
            "headcount_bracket": company.headcount_bracket,
            "has_nabl": company.has_nabl,
            "export_active": company.export_active,
            "calculated_tier": company.calculated_tier,
            "instruments_found": intel.instruments_found if intel else [],
            "iso_standards": intel.iso_standards if intel else [],
            "oem_brands": intel.oem_brands if intel else [],
        }

        # Check if already registered
        existing = db.execute(
            text("SELECT id FROM won_customers WHERE company_id = :cid"),
            {"cid": company_id}
        ).fetchone()

        if existing:
            db.execute(
                text("UPDATE won_customers SET feature_vector = :fv WHERE company_id = :cid"),
                {"fv": json.dumps(feature_vector), "cid": company_id}
            )
        else:
            db.execute(
                text("""INSERT INTO won_customers (company_id, feature_vector, won_at)
                        VALUES (:cid, :fv, NOW())"""),
                {"cid": company_id, "fv": json.dumps(feature_vector)}
            )

        db.commit()
        logger.info(f"Registered won customer: {company.name} (ID: {company_id})")

        # Trigger lookalike search
        find_lookalikes.delay()

    except Exception as e:
        logger.error(f"Error registering won customer {company_id}: {e}")
        db.rollback()
    finally:
        if close_db:
            db.close()


# ============================================================
# LOOKALIKE FINDER (Celery task)
# ============================================================

@celery_app.task(name="backend.services.lookalikeEngine.find_lookalikes")
def find_lookalikes() -> Dict:
    """
    Find companies similar to all won customers.
    Companies not yet in pipeline = lookalike leads.
    Auto-add to pipeline with source reference.
    """
    db = SessionLocal()
    try:
        # Get all won customer IDs
        won_rows = db.execute(
            text("SELECT company_id FROM won_customers")
        ).fetchall()

        if not won_rows:
            logger.info("No won customers yet — skipping lookalike search")
            return {"lookalikes_found": 0}

        won_ids = [row[0] for row in won_rows]

        # Get companies already in pipeline
        pipeline_company_ids = set(
            row[0] for row in db.query(PipelineStage.company_id).all()
        )

        all_lookalikes = []

        for won_id in won_ids:
            # Find similar companies
            similar = find_similar_companies(won_id, limit=30, db=db)

            for company_data in similar:
                cid = company_data["company_id"]

                # Skip if already in pipeline or is a won customer
                if cid in pipeline_company_ids or cid in won_ids:
                    continue

                # Skip if already marked as lookalike
                if cid in [l["company_id"] for l in all_lookalikes]:
                    continue

                company_data["source_won_id"] = won_id
                all_lookalikes.append(company_data)

        # Add top lookalikes to pipeline
        added = 0
        for lookalike in all_lookalikes[:50]:  # Max 50 per run
            try:
                # Get source company name
                source = db.query(Company).filter(
                    Company.id == lookalike["source_won_id"]
                ).first()
                source_name = source.name if source else "won customer"

                # Mark company as lookalike
                company = db.query(Company).filter(
                    Company.id == lookalike["company_id"]
                ).first()
                if company:
                    company.lookalike_source_id = lookalike["source_won_id"]

                # Add to pipeline
                pipeline = PipelineStage(
                    company_id=lookalike["company_id"],
                    stage="New",
                    notes=f"AI-identified lookalike of {source_name}",
                    contact_channel="email",
                )
                db.add(pipeline)
                added += 1

            except Exception as e:
                logger.error(f"Error adding lookalike {lookalike['company_id']}: {e}")
                continue

        db.commit()
        logger.info(f"Lookalike search complete. Found {len(all_lookalikes)}, added {added} to pipeline")

        return {
            "lookalikes_found": len(all_lookalikes),
            "added_to_pipeline": added,
            "won_customers_analyzed": len(won_ids),
        }

    except Exception as e:
        logger.error(f"Lookalike engine error: {e}")
        db.rollback()
        return {"error": str(e)}
    finally:
        db.close()


# ============================================================
# GET LOOKALIKE LEADS (for API)
# ============================================================

def get_lookalike_leads(db: Session = None) -> List[Dict]:
    """Get all lookalike leads not yet contacted."""
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        # Companies with lookalike_source_id set, in 'New' stage
        results = db.query(Company, PipelineStage).join(
            PipelineStage, Company.id == PipelineStage.company_id
        ).filter(
            Company.lookalike_source_id.isnot(None),
            PipelineStage.stage == "New",
        ).order_by(desc(Company.icp_score)).all()

        leads = []
        for company, pipeline in results:
            # Get source company name
            source = db.query(Company).filter(
                Company.id == company.lookalike_source_id
            ).first()

            leads.append({
                "company_id": company.id,
                "name": company.name,
                "city": company.city,
                "state": company.state,
                "industry": company.industry,
                "tier": company.calculated_tier,
                "icp_score": company.icp_score,
                "lookalike_of": source.name if source else "Unknown",
                "lookalike_source_id": company.lookalike_source_id,
                "added_at": pipeline.created_at.isoformat() if pipeline.created_at else None,
                "notes": pipeline.notes,
            })

        return leads

    finally:
        if close_db:
            db.close()


def approve_lookalikes(company_ids: List[int], db: Session = None) -> Dict:
    """Move batch of lookalike leads from New to active pipeline."""
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        approved = 0
        for cid in company_ids:
            pipeline = db.query(PipelineStage).filter(
                PipelineStage.company_id == cid,
                PipelineStage.stage == "New",
            ).first()
            if pipeline:
                pipeline.stage = "New"  # Keep in New but mark as approved
                pipeline.notes = (pipeline.notes or "") + " | Approved for outreach"
                pipeline.last_touched = datetime.utcnow()
                approved += 1

        db.commit()
        return {"approved": approved}

    except Exception as e:
        logger.error(f"Error approving lookalikes: {e}")
        db.rollback()
        return {"error": str(e)}
    finally:
        if close_db:
            db.close()
