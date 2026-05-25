"""
Enhanced Scoring Engine
========================
ICP scoring with positive and negative signals.
Includes all enhanced signals from Modules 8-17.
"""
import json
import logging
import os
from typing import Dict, List, Optional

from sqlalchemy import desc
from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.models.company import Company
from backend.models.website_intel import CompanyWebsiteIntel
from backend.models.intent_signal import CompanyIntentSignal

logger = logging.getLogger(__name__)


# ============================================================
# ICP WEIGHTS (Positive Signals)
# ============================================================

ICP_WEIGHTS = {
    # Core signals
    "has_nabl": 20,
    "has_iso_17025": 15,
    "has_iso_9001": 10,
    "has_iatf_16949": 15,
    "has_multiple_certifications": 15,  # ISO + NABL + IATF together
    "has_website": 5,
    "export_active": 10,

    # Size signals
    "headcount_50_200": 10,
    "headcount_200_plus": 15,

    # Equipment signals
    "has_precision_instruments": 15,
    "has_multiple_oem_brands": 10,

    # Intent signals (from trigger engine)
    "google_reviews_negative_vendor": 15,   # Pain = opportunity
    "naukri_qa_job_posted": 15,
    "news_expansion_detected": 20,
    "nabl_renewal_due_45_days": 35,         # HIGHEST signal
    "iso_audit_window": 25,
    "import_spike_detected": 15,
    "whatsapp_business_verified": 5,        # Signals digital maturity
    "multiple_certifications": 15,          # ISO + NABL + IATF together
    "competitor_pain_detected": 20,

    # Industry signals
    "industry_pharma": 15,
    "industry_automotive": 15,
    "industry_aerospace": 20,
    "industry_medical_devices": 15,
    "industry_food_processing": 10,
    "industry_chemical": 10,
    "industry_electrical": 10,
}

# ============================================================
# NEGATIVE ICP SIGNALS (subtract from score)
# ============================================================

NEGATIVE_ICP_WEIGHTS = {
    "trading_company_only": -20,        # Traders rarely need calibration
    "service_company": -15,             # Offices, IT companies = wrong ICP
    "government_office": -10,           # Long sales cycles
    "headcount_under_10": -15,          # Too small for AMC
    "no_website": -10,                  # Signals low investment in quality
    "no_certifications": -5,            # Lower quality focus
    "dormant_company": -20,             # No recent activity
    "duplicate_listing": -25,           # Data quality issue
}

# ============================================================
# TIER THRESHOLDS
# ============================================================

TIER_THRESHOLDS = {
    "High-Value Recurring": 75,
    "Compliance-Driven": 55,
    "Growth Potential": 35,
    "Low Potential": 0,
}


# ============================================================
# SCORING FUNCTIONS
# ============================================================

def calculate_icp_score(company_id: int, db: Session = None) -> Dict:
    """
    Calculate the full ICP score for a company.
    Combines positive signals, negative flags, and learned adjustments.
    """
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        company = db.query(Company).filter(Company.id == company_id).first()
        if not company:
            return {"error": "Company not found"}

        intel = db.query(CompanyWebsiteIntel).filter(
            CompanyWebsiteIntel.company_id == company_id
        ).first()

        signals = db.query(CompanyIntentSignal).filter(
            CompanyIntentSignal.company_id == company_id,
            CompanyIntentSignal.is_active == 1,
        ).all()

        # Calculate positive score
        positive_score = 0
        triggered_signals = []

        # Certification signals
        if company.has_nabl:
            positive_score += ICP_WEIGHTS["has_nabl"]
            triggered_signals.append("has_nabl")

        if intel:
            certs = intel.iso_standards or []
            if "ISO 17025" in " ".join(certs).upper() or "17025" in " ".join(certs):
                positive_score += ICP_WEIGHTS["has_iso_17025"]
                triggered_signals.append("has_iso_17025")
            if "ISO 9001" in " ".join(certs).upper() or "9001" in " ".join(certs):
                positive_score += ICP_WEIGHTS["has_iso_9001"]
                triggered_signals.append("has_iso_9001")
            if "IATF" in " ".join(certs).upper() or "16949" in " ".join(certs):
                positive_score += ICP_WEIGHTS["has_iatf_16949"]
                triggered_signals.append("has_iatf_16949")
            if len(certs) >= 3:
                positive_score += ICP_WEIGHTS["has_multiple_certifications"]
                triggered_signals.append("has_multiple_certifications")

            # Equipment signals
            if intel.instruments_found and len(intel.instruments_found) > 0:
                positive_score += ICP_WEIGHTS["has_precision_instruments"]
                triggered_signals.append("has_precision_instruments")
            if intel.oem_brands and len(intel.oem_brands) >= 3:
                positive_score += ICP_WEIGHTS["has_multiple_oem_brands"]
                triggered_signals.append("has_multiple_oem_brands")

        # Website
        if company.website:
            positive_score += ICP_WEIGHTS["has_website"]
            triggered_signals.append("has_website")

        # Export
        if company.export_active:
            positive_score += ICP_WEIGHTS["export_active"]
            triggered_signals.append("export_active")

        # Size
        headcount = company.headcount_bracket or ""
        if "50" in headcount or "100" in headcount or "200" in headcount:
            positive_score += ICP_WEIGHTS["headcount_50_200"]
            triggered_signals.append("headcount_50_200")
        elif "500" in headcount or "1000" in headcount:
            positive_score += ICP_WEIGHTS["headcount_200_plus"]
            triggered_signals.append("headcount_200_plus")

        # Intent signals
        signal_types = [s.signal_type for s in signals]
        if "JOB_POSTING_QA" in signal_types:
            positive_score += ICP_WEIGHTS["naukri_qa_job_posted"]
            triggered_signals.append("naukri_qa_job_posted")
        if "NEWS_EXPANSION" in signal_types:
            positive_score += ICP_WEIGHTS["news_expansion_detected"]
            triggered_signals.append("news_expansion_detected")
        if "NABL_RENEWAL_DUE" in signal_types:
            positive_score += ICP_WEIGHTS["nabl_renewal_due_45_days"]
            triggered_signals.append("nabl_renewal_due_45_days")
        if "ISO_AUDIT_WINDOW" in signal_types:
            positive_score += ICP_WEIGHTS["iso_audit_window"]
            triggered_signals.append("iso_audit_window")
        if "IMPORT_SPIKE" in signal_types:
            positive_score += ICP_WEIGHTS["import_spike_detected"]
            triggered_signals.append("import_spike_detected")
        if "COMPETITOR_PAIN" in signal_types:
            positive_score += ICP_WEIGHTS["competitor_pain_detected"]
            triggered_signals.append("competitor_pain_detected")

        # Industry bonus
        industry = (company.industry or "").lower()
        if "pharma" in industry:
            positive_score += ICP_WEIGHTS["industry_pharma"]
            triggered_signals.append("industry_pharma")
        elif "auto" in industry:
            positive_score += ICP_WEIGHTS["industry_automotive"]
            triggered_signals.append("industry_automotive")
        elif "aero" in industry:
            positive_score += ICP_WEIGHTS["industry_aerospace"]
            triggered_signals.append("industry_aerospace")
        elif "medical" in industry or "device" in industry:
            positive_score += ICP_WEIGHTS["industry_medical_devices"]
            triggered_signals.append("industry_medical_devices")

        # Calculate negative score
        negative_score = 0
        negative_flags = []

        if not company.website:
            negative_score += abs(NEGATIVE_ICP_WEIGHTS["no_website"])
            negative_flags.append("no_website")

        if headcount and ("1-10" in headcount or "micro" in headcount.lower()):
            negative_score += abs(NEGATIVE_ICP_WEIGHTS["headcount_under_10"])
            negative_flags.append("headcount_under_10")

        # Check for trading/service company
        name_lower = (company.name or "").lower()
        industry_lower = industry
        if "trading" in name_lower or "traders" in name_lower or "trading" in industry_lower:
            negative_score += abs(NEGATIVE_ICP_WEIGHTS["trading_company_only"])
            negative_flags.append("trading_company_only")
        if "service" in industry_lower and "engineering" not in industry_lower:
            negative_score += abs(NEGATIVE_ICP_WEIGHTS["service_company"])
            negative_flags.append("service_company")
        if "government" in name_lower or "govt" in name_lower:
            negative_score += abs(NEGATIVE_ICP_WEIGHTS["government_office"])
            negative_flags.append("government_office")

        # Apply learned adjustments
        learned_bonus = _get_learned_adjustments(company, intel)
        positive_score += learned_bonus

        # Final score (0-100 scale, capped)
        raw_score = positive_score - negative_score
        final_score = max(0, min(100, raw_score))

        # Determine tier
        tier = "Low Potential"
        for tier_name, threshold in TIER_THRESHOLDS.items():
            if final_score >= threshold:
                tier = tier_name
                break

        # Update company
        company.icp_score = final_score
        company.calculated_tier = tier
        company.negative_icp_flags = negative_flags
        db.commit()

        return {
            "company_id": company_id,
            "icp_score": final_score,
            "tier": tier,
            "positive_score": positive_score,
            "negative_score": negative_score,
            "triggered_signals": triggered_signals,
            "negative_flags": negative_flags,
            "learned_bonus": learned_bonus,
        }

    except Exception as e:
        logger.error(f"Scoring error for company {company_id}: {e}")
        return {"error": str(e)}
    finally:
        if close_db:
            db.close()


def _get_learned_adjustments(company: Company, intel: Optional[CompanyWebsiteIntel]) -> float:
    """Get bonus/penalty from ICP learner adjustments."""
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "data",
        "learned_icp_patterns.json"
    )

    if not os.path.exists(config_path):
        return 0

    try:
        with open(config_path, "r") as f:
            patterns = json.load(f)

        adjustments = patterns.get("adjustments", {})
        bonus = 0

        for signal_name, weight in adjustments.items():
            # Match state-based boosts
            if "state_" in signal_name and company.state:
                state_key = signal_name.replace("state_", "").replace("_boost", "")
                if state_key.lower() in company.state.lower():
                    bonus += weight

            # Match NABL boost
            if "nabl" in signal_name and company.has_nabl:
                bonus += weight

            # Match export boost
            if "export" in signal_name and company.export_active:
                bonus += weight

        return bonus

    except Exception:
        return 0


# ============================================================
# BATCH SCORING
# ============================================================

def rescore_all_companies(db: Session = None) -> Dict:
    """Rescore all companies in the database."""
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        companies = db.query(Company).all()
        scored = 0
        errors = 0

        for company in companies:
            try:
                result = calculate_icp_score(company.id, db)
                if "error" not in result:
                    scored += 1
                else:
                    errors += 1
            except Exception:
                errors += 1

        return {"scored": scored, "errors": errors, "total": len(companies)}

    finally:
        if close_db:
            db.close()
