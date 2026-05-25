"""
Main API Routes
================
All new API endpoints for Modules 8-17.

Endpoints:
  POST /api/triggers/run-now          - Manually trigger engine
  GET  /api/buying-window             - Companies by 30/60/90 day window
  GET  /api/tasks/today               - Today's action queue
  POST /api/companies/<id>/rate       - Rate a lead 1-5 stars
  GET  /api/lookalikes                - AI-identified lookalike leads
  POST /api/lookalikes/approve        - Move batch to pipeline
  POST /api/search/semantic           - Natural language lead search
  GET  /api/ab-insights               - Subject line performance data
  GET  /api/icp-insights              - What the AI has learned about ICP
  POST /api/outreach/generate         - Generate outreach for a company
  POST /api/outreach/generate-batch   - Generate outreach for multiple companies
  GET  /api/companies/<id>/next-action - Get AI recommended next action
  POST /api/companies/<id>/rescore    - Recalculate ICP score
"""
import logging
from flask import Blueprint, request, jsonify
from sqlalchemy import desc

from backend.database import SessionLocal
from backend.models.company import Company

logger = logging.getLogger(__name__)

api_bp = Blueprint("api", __name__, url_prefix="/api")


def get_db():
    db = SessionLocal()
    return db


# ============================================================
# TRIGGER ENGINE
# ============================================================

@api_bp.route("/triggers/run-now", methods=["POST"])
def run_triggers():
    """Manually trigger all buying trigger engines."""
    from backend.workers.triggerEngine import run_all_triggers
    try:
        # Run synchronously for immediate feedback
        result = run_all_triggers()
        return jsonify({"success": True, "results": result}), 200
    except Exception as e:
        logger.error(f"Trigger run error: {e}")
        return jsonify({"error": str(e)}), 500


# ============================================================
# BUYING WINDOW
# ============================================================

@api_bp.route("/buying-window", methods=["GET"])
def get_buying_window():
    """Get companies organized by 30/60/90 day buying window."""
    from backend.services.buyingWindow import get_buying_window_board
    db = get_db()
    try:
        result = get_buying_window_board(db)
        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Buying window error: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


# ============================================================
# TASKS
# ============================================================

@api_bp.route("/tasks/today", methods=["GET"])
def get_today_tasks():
    """Get today's action queue sorted by urgency + ICP."""
    from backend.routes.pipeline import get_todays_tasks
    return get_todays_tasks()


# ============================================================
# LEAD RATING
# ============================================================

@api_bp.route("/companies/<int:company_id>/rate", methods=["POST"])
def rate_company(company_id):
    """Rate a lead 1-5 stars for ICP learning."""
    from backend.services.icpLearner import rate_lead
    db = get_db()
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Request body required"}), 400

        rating = data.get("rating")
        reason = data.get("reason")

        if not rating or rating not in range(1, 6):
            return jsonify({"error": "Rating must be 1-5"}), 400

        result = rate_lead(company_id, rating, reason, db)
        if "error" in result:
            return jsonify(result), 400
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


# ============================================================
# LOOKALIKES
# ============================================================

@api_bp.route("/lookalikes", methods=["GET"])
def get_lookalikes():
    """Get all AI-identified lookalike leads not yet contacted."""
    from backend.services.lookalikeEngine import get_lookalike_leads
    db = get_db()
    try:
        leads = get_lookalike_leads(db)
        return jsonify({"leads": leads, "total": len(leads)}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


@api_bp.route("/lookalikes/approve", methods=["POST"])
def approve_lookalikes_route():
    """Approve batch of lookalike leads for outreach."""
    from backend.services.lookalikeEngine import approve_lookalikes
    db = get_db()
    try:
        data = request.get_json()
        company_ids = data.get("company_ids", [])
        if not company_ids:
            return jsonify({"error": "company_ids list required"}), 400

        result = approve_lookalikes(company_ids, db)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


# ============================================================
# SEMANTIC SEARCH
# ============================================================

@api_bp.route("/search/semantic", methods=["POST"])
def semantic_search_route():
    """Natural language lead search."""
    from backend.services.semanticSearch import semantic_search
    db = get_db()
    try:
        data = request.get_json()
        if not data or not data.get("query"):
            return jsonify({"error": "query field required"}), 400

        query = data["query"]
        limit = data.get("limit", 50)
        filters = data.get("filters")  # Optional: {state, tier, min_icp}

        results = semantic_search(query, limit=limit, db=db, filters=filters)
        return jsonify({
            "results": results,
            "total": len(results),
            "query": query,
        }), 200
    except Exception as e:
        logger.error(f"Semantic search error: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


# ============================================================
# A/B INSIGHTS
# ============================================================

@api_bp.route("/ab-insights", methods=["GET"])
def get_ab_insights_route():
    """Get subject line A/B performance data."""
    from backend.services.abOptimizer import get_ab_insights
    db = get_db()
    try:
        insights = get_ab_insights(db)
        return jsonify(insights), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


# ============================================================
# ICP INSIGHTS
# ============================================================

@api_bp.route("/icp-insights", methods=["GET"])
def get_icp_insights_route():
    """Get what the AI has learned about ICP."""
    from backend.services.icpLearner import get_icp_insights
    db = get_db()
    try:
        insights = get_icp_insights(db)
        return jsonify(insights), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


# ============================================================
# OUTREACH GENERATION
# ============================================================

@api_bp.route("/outreach/generate", methods=["POST"])
def generate_outreach_route():
    """Generate personalized outreach for a company."""
    from backend.services.ai_synthesis import generate_outreach
    db = get_db()
    try:
        data = request.get_json()
        company_id = data.get("company_id")
        if not company_id:
            return jsonify({"error": "company_id required"}), 400

        result = generate_outreach(company_id, db)
        if "error" in result:
            return jsonify(result), 400
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


@api_bp.route("/outreach/generate-batch", methods=["POST"])
def generate_outreach_batch_route():
    """Generate outreach for multiple companies."""
    from backend.services.ai_synthesis import generate_outreach_batch
    db = get_db()
    try:
        data = request.get_json()
        company_ids = data.get("company_ids", [])
        if not company_ids:
            return jsonify({"error": "company_ids list required"}), 400

        result = generate_outreach_batch(company_ids, db)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


# ============================================================
# NEXT BEST ACTION
# ============================================================

@api_bp.route("/companies/<int:company_id>/next-action", methods=["GET"])
def get_next_action(company_id):
    """Get AI recommended next action for a company."""
    from backend.services.nextBestAction import get_next_best_action
    db = get_db()
    try:
        result = get_next_best_action(company_id, db)
        if "error" in result:
            return jsonify(result), 400
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


# ============================================================
# SCORING
# ============================================================

@api_bp.route("/companies/<int:company_id>/rescore", methods=["POST"])
def rescore_company(company_id):
    """Recalculate ICP score for a company."""
    from backend.services.scoringEngine import calculate_icp_score
    db = get_db()
    try:
        result = calculate_icp_score(company_id, db)
        if "error" in result:
            return jsonify(result), 400
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


@api_bp.route("/scoring/rescore-all", methods=["POST"])
def rescore_all():
    """Rescore all companies (admin action)."""
    from backend.services.scoringEngine import rescore_all_companies
    db = get_db()
    try:
        result = rescore_all_companies(db)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()


# ============================================================
# SEARCH INDEXING
# ============================================================

@api_bp.route("/search/index-all", methods=["POST"])
def index_all_companies():
    """Index all companies for semantic search (admin action)."""
    from backend.services.semanticSearch import index_all_companies as do_index
    db = get_db()
    try:
        result = do_index(db)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db.close()
