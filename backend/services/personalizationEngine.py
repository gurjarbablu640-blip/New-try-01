"""
Module 9: Hyper-Personalization Engine
=======================================
Generic emails fail. Every outreach must reference something specific
to THAT company that proves you actually looked at them.

This module builds a "personalization context" object per company
before Claude generates the email.
"""
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import desc

from database import SessionLocal
from models.company import Company
from models.person import Person
from models.website_intel import CompanyWebsiteIntel
from models.intent_signal import CompanyIntentSignal

logger = logging.getLogger(__name__)


# ============================================================
# INDUSTRY PAIN TEMPLATES (fallback when no specific signal)
# ============================================================

INDUSTRY_PAIN_TEMPLATES = {
    "pharmaceutical": "FDA/GMP compliance requires calibrated instruments — one failed audit costs lakhs",
    "automotive": "IATF 16949 mandates traceable calibration — production stoppage risk is real",
    "electrical": "Instrument drift in panel testing = field failures and warranty claims",
    "food": "FSSAI and ISO 22000 both require annual calibration proof",
    "chemical": "Process instruments out of spec = batch rejection and raw material waste",
    "manufacturing": "Uncalibrated measuring instruments = scrap, rework, and customer complaints",
    "aerospace": "AS9100 requires documented calibration with NABL traceability",
    "medical": "Medical device manufacturing needs validated calibration per ISO 13485",
    "oil_gas": "Hazardous area instruments need certified calibration for safety compliance",
    "textile": "Quality consistency depends on accurate tension, temperature, and humidity instruments",
    "default": "Instrument accuracy directly impacts product quality and compliance audit readiness",
}


def build_personalization_context(company_id: int, db: Session = None) -> Dict[str, Any]:
    """
    Build a complete personalization context for a company.
    This JSON is passed to Claude when generating outreach.

    Returns:
        personalization_context dict with all company-specific data points
    """
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        company = db.query(Company).filter(Company.id == company_id).first()
        if not company:
            logger.error(f"Company {company_id} not found")
            return {}

        # Get website intelligence
        website_intel = db.query(CompanyWebsiteIntel).filter(
            CompanyWebsiteIntel.company_id == company_id
        ).first()

        # Get active intent signals (ordered by weight)
        signals = db.query(CompanyIntentSignal).filter(
            CompanyIntentSignal.company_id == company_id,
            CompanyIntentSignal.is_active == 1,
        ).order_by(desc(CompanyIntentSignal.weight_applied)).all()

        # Get decision maker (top person)
        decision_maker = db.query(Person).filter(
            Person.company_id == company_id
        ).order_by(
            desc(Person.is_decision_maker),
            Person.id
        ).first()

        # Build context
        context = {
            "company_name": company.name,
            "company_city": company.city or "India",
            "company_state": company.state or "",
            "company_industry": company.industry or "",
            "company_tier": company.calculated_tier or "Unscored",
            "icp_score": company.icp_score or 0,

            # From website intel
            "specific_instruments": _get_instruments(website_intel),
            "oem_brands": _get_oem_brands(website_intel),
            "certifications": _get_certifications(website_intel),
            "expansion_signal": _get_expansion_signal(website_intel),

            # From signals
            "urgency_trigger": _get_urgency_trigger(signals),
            "active_signals": [s.signal_type for s in signals],
            "signal_details": _get_signal_details(signals),

            # Reference customer (social proof)
            "local_reference": nearest_reference_customer(
                company.city, company.state, db
            ),

            # Pain hook
            "pain_hook": derive_pain_from_signals(signals, company),

            # Decision maker
            "decision_maker_name": decision_maker.full_name if decision_maker else None,
            "decision_maker_designation": decision_maker.designation if decision_maker else None,
            "decision_maker_email": decision_maker.email if decision_maker else None,

            # Company characteristics
            "company_size_signal": company.headcount_bracket or "unknown",
            "has_nabl": company.has_nabl or False,
            "export_active": company.export_active or False,

            # Buying window prediction
            "buying_window": predict_buying_window(
                company.icp_score or 0,
                company.intent_velocity_score or 0,
                signals
            ),

            # Negative signals (for internal use, not sent to prospect)
            "negative_flags": company.negative_icp_flags or [],
        }

        return context

    except Exception as e:
        logger.error(f"Error building personalization context for company {company_id}: {e}")
        return {}

    finally:
        if close_db:
            db.close()


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def _get_instruments(intel: Optional[CompanyWebsiteIntel]) -> List[str]:
    """Extract instruments list from website intel."""
    if intel and intel.instruments_found:
        return intel.instruments_found[:10]  # Max 10 for prompt length
    return []


def _get_oem_brands(intel: Optional[CompanyWebsiteIntel]) -> List[str]:
    """Extract OEM brands from website intel."""
    if intel and intel.oem_brands:
        return intel.oem_brands[:8]
    return []


def _get_certifications(intel: Optional[CompanyWebsiteIntel]) -> List[str]:
    """Extract certifications from website intel."""
    if intel and intel.iso_standards:
        return intel.iso_standards
    return []


def _get_expansion_signal(intel: Optional[CompanyWebsiteIntel]) -> Optional[str]:
    """Get expansion signal text."""
    if intel and intel.expansion_signals:
        return intel.expansion_signals[:200]
    return None


def _get_urgency_trigger(signals: List[CompanyIntentSignal]) -> Optional[Dict]:
    """Get the highest-weight active signal as urgency trigger."""
    if signals:
        top_signal = signals[0]
        return {
            "type": top_signal.signal_type,
            "weight": top_signal.weight_applied,
            "reason": top_signal.urgency_reason,
            "note": top_signal.opportunity_note,
            "detected_at": top_signal.detected_at.isoformat() if top_signal.detected_at else None,
        }
    return None


def _get_signal_details(signals: List[CompanyIntentSignal]) -> List[Dict]:
    """Get detailed signal list."""
    return [
        {
            "type": s.signal_type,
            "weight": s.weight_applied,
            "reason": s.urgency_reason,
            "detected_at": s.detected_at.isoformat() if s.detected_at else None,
        }
        for s in signals[:5]  # Top 5 signals
    ]


# ============================================================
# CORE FUNCTIONS
# ============================================================

def derive_pain_from_signals(
    signals: List[CompanyIntentSignal],
    company: Company
) -> str:
    """
    Derive the most relevant pain hook based on active signals.
    This is the opening line that grabs attention.
    """
    signal_types = [s.signal_type for s in signals]

    if "NABL_RENEWAL_DUE" in signal_types:
        return "Your NABL accreditation renewal is approaching — labs that prepare early avoid last-minute audit stress"

    if "JOB_POSTING_QA" in signal_types:
        # Find the specific job posting signal for context
        job_signal = next((s for s in signals if s.signal_type == "JOB_POSTING_QA"), None)
        if job_signal and job_signal.urgency_reason:
            return f"You're building your QA team — right time to set up AMC so the new hire walks into a compliant lab"
        return "You're expanding your quality team — right time to set up calibration AMC"

    if "NEWS_EXPANSION" in signal_types:
        news_signal = next((s for s in signals if s.signal_type == "NEWS_EXPANSION"), None)
        if news_signal and news_signal.urgency_reason:
            return f"Congratulations on your new facility — new equipment needs baseline calibration before production starts"
        return "Your expansion means new instruments that need commissioning calibration"

    if "IMPORT_SPIKE" in signal_types:
        return "Your recent equipment imports will need commissioning calibration before they're production-ready"

    if "ISO_AUDIT_WINDOW" in signal_types:
        return "With your ISO surveillance audit approaching, now is the time to get calibration certificates updated"

    if "COMPETITOR_PAIN" in signal_types:
        city = company.city or "your area"
        return f"We've heard the calibration market in {city} has reliability issues — we do things differently"

    # Fallback: use industry-specific pain
    industry = (company.industry or "").lower()
    for key, pain in INDUSTRY_PAIN_TEMPLATES.items():
        if key in industry:
            return pain

    # Final fallback using ICP score
    if company.icp_score and company.icp_score > 60:
        return "Your quality infrastructure suggests you take compliance seriously — we help companies like yours stay ahead of audits"

    return INDUSTRY_PAIN_TEMPLATES["default"]


def predict_buying_window(
    icp_score: float,
    velocity: float,
    signals: List[CompanyIntentSignal]
) -> str:
    """
    Predict when this company is most likely to buy.
    Used for pipeline prioritization and outreach timing.
    """
    signal_types = [s.signal_type for s in signals]

    if "NABL_RENEWAL_DUE" in signal_types:
        return "within 30 days"

    if "ISO_AUDIT_WINDOW" in signal_types:
        return "within 60 days"

    if "NEWS_EXPANSION" in signal_types:
        return "within 45 days"

    if "JOB_POSTING_QA" in signal_types:
        return "within 90 days"

    if "IMPORT_SPIKE" in signal_types:
        return "within 60 days"

    if "COMPETITOR_PAIN" in signal_types:
        return "within 90 days"

    if velocity > 40:
        return "within 60 days"

    if icp_score > 70:
        return "within 90 days"

    return "within 6 months"


def nearest_reference_customer(
    city: Optional[str],
    state: Optional[str],
    db: Session
) -> Optional[str]:
    """
    Find the nearest reference customer for social proof.
    Query companies with tier='High-Value Recurring' in same city/state.
    Returns: "{company_name} in {city}" for use in outreach.
    """
    if not city and not state:
        return None

    # Try city match first
    if city:
        ref = db.query(Company).filter(
            Company.calculated_tier == "High-Value Recurring",
            Company.city == city,
        ).order_by(desc(Company.icp_score)).first()

        if ref:
            return f"{ref.name} in {ref.city}"

    # Fall back to state match
    if state:
        ref = db.query(Company).filter(
            Company.calculated_tier == "High-Value Recurring",
            Company.state == state,
        ).order_by(desc(Company.icp_score)).first()

        if ref:
            return f"{ref.name} in {ref.city or ref.state}"

    # Fall back to any high-value reference
    ref = db.query(Company).filter(
        Company.calculated_tier == "High-Value Recurring",
    ).order_by(desc(Company.icp_score)).first()

    if ref:
        return f"{ref.name} in {ref.city or 'India'}"

    return None


def get_personalization_summary(context: Dict) -> str:
    """
    Generate a human-readable summary of personalization data.
    Useful for salespeople to quickly understand what data is available.
    """
    parts = []

    if context.get("specific_instruments"):
        parts.append(f"Instruments: {', '.join(context['specific_instruments'][:3])}")

    if context.get("oem_brands"):
        parts.append(f"Brands: {', '.join(context['oem_brands'][:3])}")

    if context.get("certifications"):
        parts.append(f"Certs: {', '.join(context['certifications'])}")

    if context.get("urgency_trigger"):
        parts.append(f"Trigger: {context['urgency_trigger']['type']}")

    if context.get("pain_hook"):
        parts.append(f"Hook: {context['pain_hook'][:60]}...")

    if context.get("buying_window"):
        parts.append(f"Window: {context['buying_window']}")

    if context.get("local_reference"):
        parts.append(f"Reference: {context['local_reference']}")

    return " | ".join(parts) if parts else "Limited personalization data available"
