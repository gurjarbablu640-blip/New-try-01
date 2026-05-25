"""
Module 17: A/B Subject Line Optimizer
=======================================
Track which subject line variants get replies.
Learn which patterns work best.
Update Claude's prompt with learned preferences.

5 variants generated per company → track opens/replies → weekly analysis.
"""
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta

from sqlalchemy import func, desc
from sqlalchemy.orm import Session

from backend.celery_app import celery_app
from backend.database import SessionLocal
from backend.models.pipeline import ABTestResult
from backend.models.company import Company

logger = logging.getLogger(__name__)


# ============================================================
# A/B ANALYSIS (Weekly Celery Task)
# ============================================================

@celery_app.task(name="backend.services.abOptimizer.analyze_ab_results")
def analyze_ab_results() -> Dict:
    """
    Weekly analysis: which subject line variants perform best?
    Identifies winning patterns and updates generation preferences.
    """
    db = SessionLocal()
    try:
        # Get all results
        results = db.query(ABTestResult).all()

        if len(results) < 10:
            return {
                "status": "insufficient_data",
                "total_tests": len(results),
                "message": "Need at least 10 A/B test results to analyze"
            }

        # Analyze by variant
        variant_stats = {}
        for variant_num in range(1, 6):
            variant_results = [r for r in results if r.subject_variant == variant_num]
            total = len(variant_results)
            if total == 0:
                continue

            opened = sum(1 for r in variant_results if r.opened)
            replied = sum(1 for r in variant_results if r.replied)

            variant_stats[variant_num] = {
                "total_sent": total,
                "opened": opened,
                "replied": replied,
                "open_rate": round(opened / total * 100, 1) if total > 0 else 0,
                "reply_rate": round(replied / total * 100, 1) if total > 0 else 0,
            }

        # Find best performing variant
        best_variant = None
        best_reply_rate = 0
        for variant_num, stats in variant_stats.items():
            if stats["reply_rate"] > best_reply_rate:
                best_reply_rate = stats["reply_rate"]
                best_variant = variant_num

        # Identify patterns (variant position indicates style)
        # Variant 1: Specific instrument mention
        # Variant 2: Certification-focused
        # Variant 3: Question format
        # Variant 4: Urgency/trigger-based
        # Variant 5: Benefit-led
        variant_patterns = {
            1: "instrument-specific",
            2: "certification-focused",
            3: "question-format",
            4: "urgency-trigger",
            5: "benefit-led",
        }

        winning_pattern = variant_patterns.get(best_variant, "unknown")

        # Calculate overall metrics
        total_sent = sum(s["total_sent"] for s in variant_stats.values())
        total_opened = sum(s["opened"] for s in variant_stats.values())
        total_replied = sum(s["replied"] for s in variant_stats.values())

        insights = {
            "variant_stats": variant_stats,
            "best_variant": best_variant,
            "best_reply_rate": best_reply_rate,
            "winning_pattern": winning_pattern,
            "overall_open_rate": round(total_opened / max(total_sent, 1) * 100, 1),
            "overall_reply_rate": round(total_replied / max(total_sent, 1) * 100, 1),
            "total_emails_tracked": total_sent,
            "recommendation": _generate_recommendation(variant_stats, winning_pattern),
            "analyzed_at": datetime.utcnow().isoformat(),
        }

        # Store insights for use in prompt generation
        _save_ab_insights(insights)

        logger.info(f"A/B analysis complete. Best pattern: {winning_pattern} ({best_reply_rate}% reply rate)")
        return insights

    except Exception as e:
        logger.error(f"A/B analysis error: {e}")
        return {"error": str(e)}
    finally:
        db.close()


def _generate_recommendation(variant_stats: Dict, winning_pattern: str) -> str:
    """Generate a human-readable recommendation."""
    if not variant_stats:
        return "Not enough data to make recommendations yet."

    best_rate = max(s["reply_rate"] for s in variant_stats.values()) if variant_stats else 0
    worst_rate = min(s["reply_rate"] for s in variant_stats.values()) if variant_stats else 0

    if best_rate == 0:
        return "No replies yet. Consider reviewing email delivery and subject line quality."

    multiplier = round(best_rate / max(worst_rate, 0.1), 1)

    recommendations = {
        "instrument-specific": f"Subject lines mentioning specific instruments get {multiplier}x more replies. Always include the equipment name.",
        "certification-focused": f"Certification-focused subjects get {multiplier}x more replies. Lead with ISO/NABL compliance.",
        "question-format": f"Question-format subjects get {multiplier}x more replies. Ask a specific question in the subject line.",
        "urgency-trigger": f"Urgency/trigger subjects get {multiplier}x more replies. Reference timely events.",
        "benefit-led": f"Benefit-led subjects get {multiplier}x more replies. Lead with what they gain.",
    }

    return recommendations.get(winning_pattern, f"Pattern '{winning_pattern}' is winning with {best_rate}% reply rate.")


def _save_ab_insights(insights: Dict):
    """Save A/B insights for use in outreach generation."""
    import os
    import json

    config_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "data",
        "ab_insights.json"
    )
    os.makedirs(os.path.dirname(config_path), exist_ok=True)

    with open(config_path, "w") as f:
        json.dump(insights, f, indent=2)


# ============================================================
# GET A/B INSIGHTS (for API)
# ============================================================

def get_ab_insights(db: Session = None) -> Dict:
    """Get A/B testing insights for the dashboard."""
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        # Try to load saved insights
        import os
        import json

        config_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "data",
            "ab_insights.json"
        )

        saved_insights = {}
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                saved_insights = json.load(f)

        # Get live stats
        total_tests = db.query(func.count(ABTestResult.id)).scalar() or 0
        total_opened = db.query(func.count(ABTestResult.id)).filter(
            ABTestResult.opened == True
        ).scalar() or 0
        total_replied = db.query(func.count(ABTestResult.id)).filter(
            ABTestResult.replied == True
        ).scalar() or 0

        # Recent results (last 30 days)
        thirty_days = datetime.utcnow() - timedelta(days=30)
        recent_tests = db.query(func.count(ABTestResult.id)).filter(
            ABTestResult.sent_at >= thirty_days
        ).scalar() or 0

        return {
            "total_tests": total_tests,
            "total_opened": total_opened,
            "total_replied": total_replied,
            "overall_open_rate": round(total_opened / max(total_tests, 1) * 100, 1),
            "overall_reply_rate": round(total_replied / max(total_tests, 1) * 100, 1),
            "recent_tests_30d": recent_tests,
            "variant_stats": saved_insights.get("variant_stats", {}),
            "winning_pattern": saved_insights.get("winning_pattern"),
            "best_reply_rate": saved_insights.get("best_reply_rate", 0),
            "recommendation": saved_insights.get("recommendation", "Not enough data yet"),
            "last_analyzed": saved_insights.get("analyzed_at"),
        }

    finally:
        if close_db:
            db.close()


# ============================================================
# GET PROMPT ENHANCEMENT (for ai_synthesis)
# ============================================================

def get_subject_line_guidance() -> str:
    """
    Get learned subject line guidance to enhance Claude's prompt.
    Called by ai_synthesis when generating outreach.
    """
    import os
    import json

    config_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "data",
        "ab_insights.json"
    )

    if not os.path.exists(config_path):
        return ""

    try:
        with open(config_path, "r") as f:
            insights = json.load(f)

        winning = insights.get("winning_pattern")
        rate = insights.get("best_reply_rate", 0)

        if winning and rate > 0:
            return (
                f"\n\nBased on past A/B testing data, '{winning}' subject lines "
                f"get {rate}% reply rate — prioritize this pattern in your 5 variants."
            )
    except Exception:
        pass

    return ""
