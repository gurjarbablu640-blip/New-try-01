"""
Module 15: ICP Learning Engine
================================
The system should get smarter the more you use it.
Rate leads → AI learns your personal ICP → scoring improves.

Weekly Celery task:
1. Collect highly-rated leads (4-5 stars)
2. Collect low-rated leads (1-2 stars)
3. Call Claude to identify distinguishing patterns
4. Apply weight adjustments to scoring engine
5. Recalculate all company scores
"""
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional

import anthropic
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from backend.celery_app import celery_app
from backend.config import settings
from backend.database import SessionLocal
from backend.models.company import Company
from backend.models.pipeline import LeadRating
from backend.models.website_intel import CompanyWebsiteIntel

logger = logging.getLogger(__name__)


# ============================================================
# RATE A LEAD
# ============================================================

def rate_lead(company_id: int, rating: int, reason: str = None, db: Session = None) -> Dict:
    """
    Rate a lead 1-5 stars.
    This data feeds the ICP learning engine.
    """
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        if rating < 1 or rating > 5:
            return {"error": "Rating must be between 1 and 5"}

        company = db.query(Company).filter(Company.id == company_id).first()
        if not company:
            return {"error": "Company not found"}

        # Create rating entry
        lead_rating = LeadRating(
            company_id=company_id,
            user_rating=rating,
            rating_reason=reason,
        )
        db.add(lead_rating)

        # Update company's user_rating (latest rating)
        company.user_rating = rating

        db.commit()

        return {
            "success": True,
            "company_id": company_id,
            "rating": rating,
            "reason": reason,
        }

    except Exception as e:
        logger.error(f"Error rating lead {company_id}: {e}")
        db.rollback()
        return {"error": str(e)}
    finally:
        if close_db:
            db.close()


# ============================================================
# ICP LEARNING (Weekly Celery Task)
# ============================================================

@celery_app.task(name="backend.services.icpLearner.learn_icp_patterns")
def learn_icp_patterns() -> Dict:
    """
    Weekly task: analyze rated leads to learn ICP patterns.
    Identifies what distinguishes good leads from bad ones.
    """
    db = SessionLocal()
    try:
        # Get highly-rated leads (4-5 stars)
        good_ratings = db.query(LeadRating).filter(
            LeadRating.user_rating >= 4
        ).all()
        good_company_ids = list(set([r.company_id for r in good_ratings]))

        # Get low-rated leads (1-2 stars)
        bad_ratings = db.query(LeadRating).filter(
            LeadRating.user_rating <= 2
        ).all()
        bad_company_ids = list(set([r.company_id for r in bad_ratings]))

        if len(good_company_ids) < 5 or len(bad_company_ids) < 3:
            logger.info("Not enough ratings to learn patterns. Need 5+ good and 3+ bad.")
            return {
                "status": "insufficient_data",
                "good_count": len(good_company_ids),
                "bad_count": len(bad_company_ids),
                "message": "Need at least 5 highly-rated and 3 low-rated leads to learn patterns"
            }

        # Build feature summaries
        good_sample = _build_company_summaries(good_company_ids[:15], db)
        bad_sample = _build_company_summaries(bad_company_ids[:15], db)

        # Call Claude to identify patterns
        if settings.ANTHROPIC_API_KEY:
            patterns = _claude_learn_patterns(good_sample, bad_sample)
        else:
            patterns = _rule_based_patterns(good_company_ids, bad_company_ids, db)

        if patterns:
            # Apply learned patterns
            _apply_learned_patterns(patterns, db)

            # Log the learning
            logger.info(
                f"ICP model updated: {len(patterns.get('learned_patterns', []))} patterns learned, "
                f"companies to rescore"
            )

            return {
                "status": "success",
                "learned_patterns": patterns.get("learned_patterns", []),
                "icp_adjustments": patterns.get("icp_adjustments", {}),
                "negative_signals": patterns.get("negative_icp_signals", []),
                "good_leads_analyzed": len(good_company_ids),
                "bad_leads_analyzed": len(bad_company_ids),
            }

        return {"status": "no_patterns_found"}

    except Exception as e:
        logger.error(f"ICP learning error: {e}")
        return {"error": str(e)}
    finally:
        db.close()


def _build_company_summaries(company_ids: List[int], db: Session) -> List[Dict]:
    """Build feature summaries for a list of companies."""
    summaries = []
    for cid in company_ids:
        company = db.query(Company).filter(Company.id == cid).first()
        if not company:
            continue

        intel = db.query(CompanyWebsiteIntel).filter(
            CompanyWebsiteIntel.company_id == cid
        ).first()

        summary = {
            "name": company.name,
            "city": company.city,
            "state": company.state,
            "industry": company.industry,
            "search_keyword": company.search_keyword,
            "tier": company.calculated_tier,
            "icp_score": company.icp_score,
            "headcount": company.headcount_bracket,
            "has_nabl": company.has_nabl,
            "export_active": company.export_active,
            "instruments": intel.instruments_found if intel else [],
            "certifications": intel.iso_standards if intel else [],
            "oem_brands": intel.oem_brands if intel else [],
        }
        summaries.append(summary)

    return summaries


def _claude_learn_patterns(good_sample: List[Dict], bad_sample: List[Dict]) -> Optional[Dict]:
    """Use Claude to identify ICP patterns."""
    try:
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

        prompt = f"""Analyze these lead ratings to identify ICP (Ideal Customer Profile) patterns.

TOP-RATED LEADS (4-5 stars — these are ideal customers):
{json.dumps(good_sample, indent=2)}

LOW-RATED LEADS (1-2 stars — these are poor fits):
{json.dumps(bad_sample, indent=2)}

Identify 3-5 patterns that distinguish good leads from bad ones.
Consider: industry, geography, certifications, company size, instruments, export status.

Return JSON:
{{
  "learned_patterns": [
    "Pattern 1 description",
    "Pattern 2 description",
    "Pattern 3 description"
  ],
  "icp_adjustments": {{
    "signal_name": weight_delta_integer,
    "example: has_nabl_in_pharma": 10,
    "example: maharashtra_manufacturing": 5
  }},
  "negative_icp_signals": [
    "signal that predicts bad fit 1",
    "signal that predicts bad fit 2"
  ],
  "insights_summary": "2-3 sentence summary of what makes a good lead"
}}"""

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = response.content[0].text

        # Parse JSON
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            start = response_text.index("{")
            end = response_text.rindex("}") + 1
            return json.loads(response_text[start:end])

    except Exception as e:
        logger.error(f"Claude ICP learning error: {e}")
        return None


def _rule_based_patterns(
    good_ids: List[int],
    bad_ids: List[int],
    db: Session
) -> Dict:
    """Fallback: identify patterns using simple statistics."""
    good_companies = db.query(Company).filter(Company.id.in_(good_ids)).all()
    bad_companies = db.query(Company).filter(Company.id.in_(bad_ids)).all()

    patterns = []
    adjustments = {}
    negative_signals = []

    # Compare NABL rates
    good_nabl = sum(1 for c in good_companies if c.has_nabl) / max(len(good_companies), 1)
    bad_nabl = sum(1 for c in bad_companies if c.has_nabl) / max(len(bad_companies), 1)
    if good_nabl > bad_nabl + 0.2:
        patterns.append("NABL accredited companies are significantly better leads")
        adjustments["has_nabl_boost"] = 10

    # Compare export activity
    good_export = sum(1 for c in good_companies if c.export_active) / max(len(good_companies), 1)
    bad_export = sum(1 for c in bad_companies if c.export_active) / max(len(bad_companies), 1)
    if good_export > bad_export + 0.2:
        patterns.append("Export-active companies are better leads")
        adjustments["export_active_boost"] = 8

    # Check state concentration
    good_states = {}
    for c in good_companies:
        if c.state:
            good_states[c.state] = good_states.get(c.state, 0) + 1

    if good_states:
        top_state = max(good_states, key=good_states.get)
        if good_states[top_state] / max(len(good_companies), 1) > 0.4:
            patterns.append(f"Companies in {top_state} are disproportionately good leads")
            adjustments[f"state_{top_state.lower()}_boost"] = 5

    # Check bad patterns
    bad_industries = {}
    for c in bad_companies:
        if c.industry:
            bad_industries[c.industry] = bad_industries.get(c.industry, 0) + 1

    if bad_industries:
        top_bad_industry = max(bad_industries, key=bad_industries.get)
        if bad_industries[top_bad_industry] / max(len(bad_companies), 1) > 0.3:
            negative_signals.append(f"Industry '{top_bad_industry}' often indicates poor fit")

    return {
        "learned_patterns": patterns,
        "icp_adjustments": adjustments,
        "negative_icp_signals": negative_signals,
        "insights_summary": f"Identified {len(patterns)} positive patterns and {len(negative_signals)} negative indicators.",
    }


def _apply_learned_patterns(patterns: Dict, db: Session):
    """Apply learned patterns to the scoring system."""
    # Store patterns for reference (could be a config table in future)
    # For now, log them and they'll be picked up by scoringEngine
    adjustments = patterns.get("icp_adjustments", {})
    negative = patterns.get("negative_icp_signals", [])

    logger.info(f"Applying ICP adjustments: {adjustments}")
    logger.info(f"New negative signals: {negative}")

    # In a full implementation, this would update a config table
    # that scoringEngine reads from. For now, store as a JSON file.
    try:
        import os
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "data",
            "learned_icp_patterns.json"
        )
        os.makedirs(os.path.dirname(config_path), exist_ok=True)

        existing = {}
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                existing = json.load(f)

        existing["last_updated"] = datetime.utcnow().isoformat()
        existing["adjustments"] = adjustments
        existing["negative_signals"] = negative
        existing["patterns"] = patterns.get("learned_patterns", [])

        with open(config_path, "w") as f:
            json.dump(existing, f, indent=2)

    except Exception as e:
        logger.error(f"Error saving learned patterns: {e}")


# ============================================================
# GET ICP INSIGHTS (for API)
# ============================================================

def get_icp_insights(db: Session = None) -> Dict:
    """Get current ICP insights for display in dashboard."""
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        # Get rating statistics
        total_ratings = db.query(func.count(LeadRating.id)).scalar() or 0
        avg_rating = db.query(func.avg(LeadRating.user_rating)).scalar() or 0

        good_count = db.query(func.count(LeadRating.id)).filter(
            LeadRating.user_rating >= 4
        ).scalar() or 0
        bad_count = db.query(func.count(LeadRating.id)).filter(
            LeadRating.user_rating <= 2
        ).scalar() or 0

        # Load learned patterns if available
        import os
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "data",
            "learned_icp_patterns.json"
        )

        learned_patterns = {}
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                learned_patterns = json.load(f)

        return {
            "total_ratings": total_ratings,
            "average_rating": round(float(avg_rating), 1),
            "good_leads_rated": good_count,
            "bad_leads_rated": bad_count,
            "patterns_learned": learned_patterns.get("patterns", []),
            "adjustments_active": learned_patterns.get("adjustments", {}),
            "negative_signals": learned_patterns.get("negative_signals", []),
            "last_updated": learned_patterns.get("last_updated"),
            "ready_to_learn": good_count >= 5 and bad_count >= 3,
        }

    finally:
        if close_db:
            db.close()
