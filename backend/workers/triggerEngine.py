"""
Module 8: Buying Trigger Engine
================================
The most important module. Cold outreach fails. Trigger-based outreach
converts 3-5x higher because you contact companies EXACTLY when they
have a live need.

Run as Celery beat tasks every 6 hours. Monitors:
  8a. Naukri Job Board Scraper
  8b. Google News Signal Scraper
  8c. NABL Renewal Cycle Tracker
  8d. ISO Audit Window Detector
  8e. Import Spike Detector
  8f. Google Reviews Mining
"""
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional

import httpx
import feedparser
import jellyfish
from bs4 import BeautifulSoup
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from celery_app import celery_app
from database import SessionLocal
from config import settings
from models.company import Company
from models.intent_signal import CompanyIntentSignal
from models.website_intel import CompanyWebsiteIntel

logger = logging.getLogger(__name__)

# ============================================================
# CONSTANTS
# ============================================================

NAUKRI_KEYWORDS = [
    "quality engineer", "calibration engineer", "QA manager",
    "NABL", "metrology", "instrument technician",
    "validation engineer", "QMS manager", "ISO 17025",
]

NEWS_EXPANSION_PHRASES = [
    "new plant", "greenfield", "capacity expansion", "inaugurated",
    "new facility", "commissioning", "production started", "new unit",
    "expansion", "new manufacturing", "new factory",
]

COMPETITOR_PAIN_PHRASES = [
    "delayed", "not on time", "poor service", "changed vendor",
    "looking for alternative", "bad calibration", "unreliable",
    "inaccurate", "missed deadline", "unprofessional",
]

JOB_INTERPRETATION = {
    "quality manager": "expansion or replacement — contact NOW",
    "calibration engineer": "building in-house capability — offer AMC before they hire",
    "validation engineer": "new product line or FDA prep — premium opportunity",
    "qa manager": "expansion or replacement — contact NOW",
    "qms manager": "quality system overhaul — compliance opportunity",
    "metrology": "precision measurement focus — high-value target",
}

SIGNAL_WEIGHTS = {
    "JOB_POSTING_QA": 15,
    "NEWS_EXPANSION": 20,
    "NABL_RENEWAL_DUE": 30,
    "ISO_AUDIT_WINDOW": 25,
    "IMPORT_SPIKE": 15,
    "COMPETITOR_PAIN": 20,
}


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def get_db_session() -> Session:
    """Get a new database session."""
    return SessionLocal()


def fuzzy_match_company(company_name: str, db: Session, threshold: float = 0.75) -> Optional[Company]:
    """
    Fuzzy match a company name from external source to our DB.
    Uses Jaro-Winkler similarity for Indian company names.
    """
    if not company_name:
        return None

    companies = db.query(Company).all()
    best_match = None
    best_score = 0.0

    company_name_lower = company_name.lower().strip()

    for company in companies:
        score = jellyfish.jaro_winkler_similarity(
            company_name_lower,
            company.name.lower().strip()
        )
        if score > best_score and score >= threshold:
            best_score = score
            best_match = company

    return best_match


def insert_signal(
    db: Session,
    company_id: int,
    signal_type: str,
    weight: float,
    urgency_reason: str = None,
    source_url: str = None,
    source_snippet: str = None,
    opportunity_note: str = None,
    expires_days: int = 90
):
    """Insert a new intent signal for a company."""
    # Check for duplicate active signal of same type (within last 7 days)
    existing = db.query(CompanyIntentSignal).filter(
        CompanyIntentSignal.company_id == company_id,
        CompanyIntentSignal.signal_type == signal_type,
        CompanyIntentSignal.is_active == 1,
        CompanyIntentSignal.detected_at >= datetime.utcnow() - timedelta(days=7)
    ).first()

    if existing:
        logger.info(f"Signal {signal_type} already exists for company {company_id}, skipping")
        return existing

    signal = CompanyIntentSignal(
        company_id=company_id,
        signal_type=signal_type,
        weight_applied=weight,
        urgency_reason=urgency_reason,
        source_url=source_url,
        source_snippet=source_snippet,
        opportunity_note=opportunity_note,
        detected_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(days=expires_days),
        is_active=1,
    )
    db.add(signal)
    db.commit()
    db.refresh(signal)

    # Recalculate intent velocity score
    recalculate_intent_velocity(db, company_id)

    logger.info(f"Signal {signal_type} inserted for company {company_id} (weight={weight})")
    return signal


def recalculate_intent_velocity(db: Session, company_id: int):
    """Recalculate the intent_velocity_score for a company based on active signals."""
    active_signals = db.query(CompanyIntentSignal).filter(
        CompanyIntentSignal.company_id == company_id,
        CompanyIntentSignal.is_active == 1
    ).all()

    # Velocity = sum of weights * recency factor
    total_score = 0.0
    for signal in active_signals:
        days_old = (datetime.utcnow() - signal.detected_at).days
        recency_factor = max(0.3, 1.0 - (days_old / 90.0))  # Decay over 90 days
        total_score += signal.weight_applied * recency_factor

    company = db.query(Company).filter(Company.id == company_id).first()
    if company:
        company.intent_velocity_score = round(total_score, 2)
        db.commit()


# ============================================================
# 8a. NAUKRI JOB BOARD SCRAPER
# ============================================================

@celery_app.task(name="workers.triggerEngine.scan_naukri_jobs")
def scan_naukri_jobs():
    """
    Scrape Naukri for QA/calibration job postings.
    Match to companies in DB and insert JOB_POSTING_QA signals.
    """
    db = get_db_session()
    signals_created = 0

    try:
        for keyword in NAUKRI_KEYWORDS:
            try:
                jobs = _scrape_naukri_keyword(keyword)
                for job in jobs:
                    company = fuzzy_match_company(job.get("company_name", ""), db)
                    if company:
                        # Determine interpretation
                        job_title_lower = job.get("title", "").lower()
                        interpretation = "QA expansion detected"
                        for key, interp in JOB_INTERPRETATION.items():
                            if key in job_title_lower:
                                interpretation = interp
                                break

                        urgency = f"Hiring {job.get('title', 'QA role')} — active QA expansion"

                        insert_signal(
                            db=db,
                            company_id=company.id,
                            signal_type="JOB_POSTING_QA",
                            weight=SIGNAL_WEIGHTS["JOB_POSTING_QA"],
                            urgency_reason=urgency,
                            source_url=job.get("url", ""),
                            source_snippet=f"{job.get('title')} at {job.get('company_name')}",
                            opportunity_note=interpretation,
                        )
                        signals_created += 1

            except Exception as e:
                logger.error(f"Error scraping Naukri for '{keyword}': {e}")
                continue

        logger.info(f"Naukri scan complete. {signals_created} signals created.")
        return {"signals_created": signals_created}

    finally:
        db.close()


def _scrape_naukri_keyword(keyword: str) -> List[Dict]:
    """Scrape Naukri job listings for a keyword."""
    jobs = []
    url = f"https://www.naukri.com/jobapi/v3/search?noOfResults=20&urlType=search_by_keyword&searchType=adv&keyword={keyword.replace(' ', '%20')}&location=India"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "appid": "109",
        "systemid": "Starter",
    }

    try:
        with httpx.Client(timeout=30) as client:
            response = client.get(url, headers=headers)
            if response.status_code == 200:
                data = response.json()
                job_details = data.get("jobDetails", [])
                for job in job_details:
                    jobs.append({
                        "title": job.get("title", ""),
                        "company_name": job.get("companyName", ""),
                        "posted_date": job.get("createdDate", ""),
                        "url": f"https://www.naukri.com{job.get('jdURL', '')}",
                        "seniority": _infer_seniority(job.get("title", "")),
                    })
    except Exception as e:
        logger.warning(f"Naukri scrape failed for '{keyword}': {e}")

    # Fallback: scrape HTML if API fails
    if not jobs:
        jobs = _scrape_naukri_html(keyword)

    return jobs


def _scrape_naukri_html(keyword: str) -> List[Dict]:
    """Fallback HTML scraper for Naukri."""
    jobs = []
    url = f"https://www.naukri.com/jobs-in-india?q={keyword.replace(' ', '-')}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }

    try:
        with httpx.Client(timeout=30, follow_redirects=True) as client:
            response = client.get(url, headers=headers)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, "html.parser")
                job_cards = soup.select("article.jobTuple, div.srp-jobtuple-wrapper")

                for card in job_cards[:20]:
                    title_el = card.select_one("a.title, a.title")
                    company_el = card.select_one("a.subTitle, span.comp-name")

                    if title_el and company_el:
                        jobs.append({
                            "title": title_el.get_text(strip=True),
                            "company_name": company_el.get_text(strip=True),
                            "url": title_el.get("href", ""),
                            "posted_date": "",
                            "seniority": _infer_seniority(title_el.get_text(strip=True)),
                        })
    except Exception as e:
        logger.warning(f"Naukri HTML scrape failed: {e}")

    return jobs


def _infer_seniority(title: str) -> str:
    """Infer seniority from job title."""
    title_lower = title.lower()
    if any(x in title_lower for x in ["head", "director", "vp", "vice president", "chief"]):
        return "senior"
    elif any(x in title_lower for x in ["manager", "lead", "senior"]):
        return "mid-senior"
    elif any(x in title_lower for x in ["executive", "officer"]):
        return "mid"
    else:
        return "entry"


# ============================================================
# 8b. GOOGLE NEWS SIGNAL SCRAPER
# ============================================================

@celery_app.task(name="workers.triggerEngine.scan_google_news")
def scan_google_news():
    """
    Scan Google News RSS for expansion signals related to companies in DB.
    """
    db = get_db_session()
    signals_created = 0

    try:
        companies = db.query(Company).filter(
            Company.calculated_tier != "Low Potential"
        ).all()

        for company in companies:
            try:
                signals = _check_company_news(company, db)
                signals_created += signals
            except Exception as e:
                logger.error(f"News scan error for {company.name}: {e}")
                continue

        # Also scan for regional expansion news
        states = db.query(Company.state).distinct().filter(Company.state.isnot(None)).all()
        for (state,) in states:
            try:
                _scan_regional_news(state, db)
            except Exception as e:
                logger.error(f"Regional news scan error for {state}: {e}")

        logger.info(f"Google News scan complete. {signals_created} signals created.")
        return {"signals_created": signals_created}

    finally:
        db.close()


def _check_company_news(company: Company, db: Session) -> int:
    """Check Google News for a specific company."""
    signals_count = 0
    query = f"{company.name} India"
    rss_url = f"https://news.google.com/rss/search?q={query.replace(' ', '+')}&hl=en-IN&gl=IN"

    try:
        feed = feedparser.parse(rss_url)
        for entry in feed.entries[:10]:
            title = entry.get("title", "").lower()
            summary = entry.get("summary", "").lower()
            combined = f"{title} {summary}"

            # Check for expansion signals
            for phrase in NEWS_EXPANSION_PHRASES:
                if phrase in combined:
                    urgency = entry.get("title", "")[:80]  # Max 80 chars
                    insert_signal(
                        db=db,
                        company_id=company.id,
                        signal_type="NEWS_EXPANSION",
                        weight=SIGNAL_WEIGHTS["NEWS_EXPANSION"],
                        urgency_reason=urgency,
                        source_url=entry.get("link", ""),
                        source_snippet=entry.get("title", "")[:200],
                        opportunity_note="Expansion detected — new equipment needs baseline calibration",
                    )
                    signals_count += 1
                    break  # One signal per news item

    except Exception as e:
        logger.warning(f"Google News parse failed for {company.name}: {e}")

    return signals_count


def _scan_regional_news(state: str, db: Session):
    """Scan for regional industrial expansion news."""
    queries = [
        f"{state} industrial expansion",
        f"{state} new manufacturing plant",
    ]

    for query in queries:
        rss_url = f"https://news.google.com/rss/search?q={query.replace(' ', '+')}&hl=en-IN&gl=IN"

        try:
            feed = feedparser.parse(rss_url)
            for entry in feed.entries[:5]:
                title = entry.get("title", "").lower()
                # Try to match mentioned company to DB
                companies_in_state = db.query(Company).filter(
                    Company.state == state
                ).all()

                for company in companies_in_state:
                    if company.name.lower() in title:
                        insert_signal(
                            db=db,
                            company_id=company.id,
                            signal_type="NEWS_EXPANSION",
                            weight=SIGNAL_WEIGHTS["NEWS_EXPANSION"],
                            urgency_reason=entry.get("title", "")[:80],
                            source_url=entry.get("link", ""),
                            source_snippet=entry.get("title", "")[:200],
                        )
                        break
        except Exception as e:
            logger.warning(f"Regional news scan failed for {state}: {e}")


# ============================================================
# 8c. NABL RENEWAL CYCLE TRACKER
# ============================================================

@celery_app.task(name="workers.triggerEngine.check_nabl_renewals")
def check_nabl_renewals():
    """
    NABL accreditations renew every 2 years.
    Check for companies approaching renewal and insert high-priority signals.
    This is the HIGHEST-PRIORITY trigger — almost guaranteed to convert.
    """
    db = get_db_session()
    signals_created = 0

    try:
        today = datetime.utcnow().date()
        threshold_date = today + timedelta(days=45)  # 45 days ahead

        # Find companies with NABL that are approaching renewal
        companies = db.query(Company).filter(
            Company.has_nabl == True,
            Company.predicted_renewal_date.isnot(None),
            Company.predicted_renewal_date <= threshold_date,
            Company.predicted_renewal_date >= today,  # Not already past
        ).all()

        for company in companies:
            days_until = (company.predicted_renewal_date - today).days
            urgency = f"NABL accreditation renewal in {days_until} days — highest priority"

            insert_signal(
                db=db,
                company_id=company.id,
                signal_type="NABL_RENEWAL_DUE",
                weight=SIGNAL_WEIGHTS["NABL_RENEWAL_DUE"],
                urgency_reason=urgency,
                opportunity_note="NABL renewal due — contact is almost guaranteed to convert",
                expires_days=45,
            )

            # Update company urgency
            company.urgency_reason = urgency
            company.buying_window = "within 30 days"
            db.commit()
            signals_created += 1

        # Also calculate predicted_renewal_date for companies missing it
        _calculate_missing_renewal_dates(db)

        logger.info(f"NABL renewal check complete. {signals_created} signals created.")
        return {"signals_created": signals_created}

    finally:
        db.close()


def _calculate_missing_renewal_dates(db: Session):
    """Calculate predicted_renewal_date for companies with NABL but no date set."""
    companies = db.query(Company).filter(
        Company.has_nabl == True,
        Company.nabl_first_seen.isnot(None),
        Company.predicted_renewal_date.is_(None),
    ).all()

    for company in companies:
        # NABL renews every 2 years
        company.predicted_renewal_date = (
            company.nabl_first_seen + timedelta(days=730)
        ).date() if hasattr(company.nabl_first_seen, 'date') else company.nabl_first_seen + timedelta(days=730)
        db.commit()

    if companies:
        logger.info(f"Calculated renewal dates for {len(companies)} companies")


# ============================================================
# 8d. ISO AUDIT WINDOW DETECTOR
# ============================================================

@celery_app.task(name="workers.triggerEngine.check_iso_audit_windows")
def check_iso_audit_windows():
    """
    ISO 9001 / ISO 17025 surveillance audits happen every 12 months.
    Detect audit-related language on company websites.
    """
    db = get_db_session()
    signals_created = 0

    ISO_AUDIT_PHRASES = [
        "audit due", "surveillance", "recertification",
        "renewal", "external audit", "surveillance audit",
        "audit schedule", "upcoming audit", "audit preparation",
    ]

    try:
        # Find companies with ISO certifications
        companies_with_intel = db.query(Company, CompanyWebsiteIntel).join(
            CompanyWebsiteIntel,
            Company.id == CompanyWebsiteIntel.company_id
        ).filter(
            func.array_length(CompanyWebsiteIntel.iso_standards, 1) > 0
        ).all()

        for company, intel in companies_with_intel:
            # Check if expansion_signals or any text hints at audit window
            text_to_check = " ".join([
                intel.expansion_signals or "",
                intel.certifications_expiry_hints or "",
                " ".join(intel.iso_standards or []),
            ]).lower()

            for phrase in ISO_AUDIT_PHRASES:
                if phrase in text_to_check:
                    insert_signal(
                        db=db,
                        company_id=company.id,
                        signal_type="ISO_AUDIT_WINDOW",
                        weight=SIGNAL_WEIGHTS["ISO_AUDIT_WINDOW"],
                        urgency_reason=f"ISO audit window detected — '{phrase}' found",
                        opportunity_note="ISO surveillance audit approaching — calibration compliance required",
                        expires_days=60,
                    )
                    signals_created += 1
                    break  # One signal per company

        logger.info(f"ISO audit check complete. {signals_created} signals created.")
        return {"signals_created": signals_created}

    finally:
        db.close()


# ============================================================
# 8e. IMPORT SPIKE DETECTOR
# ============================================================

@celery_app.task(name="workers.triggerEngine.detect_import_spikes")
def detect_import_spikes():
    """
    Compare company's latest import activity vs 3-month average.
    If recent shipment volume is >40% above average, signal detected.
    Uses Zauba-style import data (stored in company metadata).
    """
    db = get_db_session()
    signals_created = 0

    try:
        # Query companies with import activity (export_active flag as proxy)
        companies = db.query(Company).filter(
            Company.export_active == True
        ).all()

        for company in companies:
            spike_detected = _check_import_spike(company, db)
            if spike_detected:
                insert_signal(
                    db=db,
                    company_id=company.id,
                    signal_type="IMPORT_SPIKE",
                    weight=SIGNAL_WEIGHTS["IMPORT_SPIKE"],
                    urgency_reason="Import volume spike >40% above average — new equipment arriving",
                    opportunity_note="New production run or new equipment = new calibration need",
                    expires_days=60,
                )
                signals_created += 1

        logger.info(f"Import spike detection complete. {signals_created} signals created.")
        return {"signals_created": signals_created}

    finally:
        db.close()


def _check_import_spike(company: Company, db: Session) -> bool:
    """
    Check if a company has an import spike.
    In production, this would query Zauba or import DB.
    For now, checks intent signals history as a proxy.
    """
    # Count recent signals (last 30 days) vs average (last 90 days)
    recent_count = db.query(CompanyIntentSignal).filter(
        CompanyIntentSignal.company_id == company.id,
        CompanyIntentSignal.signal_type == "IMPORT_SPIKE",
        CompanyIntentSignal.detected_at >= datetime.utcnow() - timedelta(days=30),
    ).count()

    avg_count = db.query(CompanyIntentSignal).filter(
        CompanyIntentSignal.company_id == company.id,
        CompanyIntentSignal.signal_type == "IMPORT_SPIKE",
        CompanyIntentSignal.detected_at >= datetime.utcnow() - timedelta(days=90),
    ).count()

    avg_monthly = avg_count / 3.0 if avg_count > 0 else 0

    # Spike if recent > 40% above average
    if avg_monthly > 0 and recent_count > avg_monthly * 1.4:
        return True

    return False


# ============================================================
# 8f. GOOGLE REVIEWS MINING
# ============================================================

@celery_app.task(name="workers.triggerEngine.mine_google_reviews")
def mine_google_reviews():
    """
    For companies with Google Maps place_id, analyze their reviews
    for competitor pain signals and sentiment.
    """
    db = get_db_session()
    signals_created = 0

    try:
        companies = db.query(Company).filter(
            Company.google_place_id.isnot(None),
            Company.google_place_id != "",
        ).all()

        for company in companies:
            try:
                result = _analyze_company_reviews(company, db)
                if result.get("pain_detected"):
                    insert_signal(
                        db=db,
                        company_id=company.id,
                        signal_type="COMPETITOR_PAIN",
                        weight=SIGNAL_WEIGHTS["COMPETITOR_PAIN"],
                        urgency_reason="Dissatisfied with current vendor — prime switching opportunity",
                        opportunity_note=result.get("opportunity_note", ""),
                        expires_days=120,
                    )

                    # Update company fields
                    company.competitor_pain_detected = True
                    company.review_sentiment_score = result.get("sentiment_score", 0.0)
                    db.commit()
                    signals_created += 1

            except Exception as e:
                logger.error(f"Review mining error for {company.name}: {e}")
                continue

        logger.info(f"Google Reviews mining complete. {signals_created} signals created.")
        return {"signals_created": signals_created}

    finally:
        db.close()


def _analyze_company_reviews(company: Company, db: Session) -> Dict:
    """Fetch and analyze Google reviews for a company."""
    result = {"pain_detected": False, "sentiment_score": 0.0, "opportunity_note": ""}

    if not settings.GOOGLE_MAPS_API_KEY or not company.google_place_id:
        return result

    url = (
        f"https://maps.googleapis.com/maps/api/place/details/json"
        f"?place_id={company.google_place_id}"
        f"&fields=reviews,rating"
        f"&key={settings.GOOGLE_MAPS_API_KEY}"
    )

    try:
        with httpx.Client(timeout=15) as client:
            response = client.get(url)
            if response.status_code != 200:
                return result

            data = response.json()
            place_result = data.get("result", {})
            reviews = place_result.get("reviews", [])
            overall_rating = place_result.get("rating", 3.0)

            if not reviews:
                return result

            # Analyze reviews for pain signals
            pain_phrases_found = []
            negative_count = 0
            total_reviews = len(reviews)

            for review in reviews:
                text = review.get("text", "").lower()
                rating = review.get("rating", 3)

                if rating <= 2:
                    negative_count += 1

                for phrase in COMPETITOR_PAIN_PHRASES:
                    if phrase in text:
                        pain_phrases_found.append(phrase)

            # Calculate sentiment score (-1.0 to +1.0)
            sentiment_score = (overall_rating - 3.0) / 2.0  # Normalize to -1 to +1

            # Detect competitor pain
            if pain_phrases_found or (negative_count / max(total_reviews, 1)) > 0.3:
                result["pain_detected"] = True
                result["sentiment_score"] = sentiment_score
                result["opportunity_note"] = (
                    f"Pain signals: {', '.join(set(pain_phrases_found[:3]))}. "
                    f"Rating: {overall_rating}/5"
                )

                # Update website intel
                intel = db.query(CompanyWebsiteIntel).filter(
                    CompanyWebsiteIntel.company_id == company.id
                ).first()
                if intel:
                    intel.review_pain_phrases = list(set(pain_phrases_found))
                    db.commit()

            else:
                result["sentiment_score"] = sentiment_score

    except Exception as e:
        logger.warning(f"Google Reviews API error for {company.name}: {e}")

    return result


# ============================================================
# UTILITY: Manual trigger run
# ============================================================

@celery_app.task(name="workers.triggerEngine.run_all_triggers")
def run_all_triggers():
    """Run all trigger engines manually (for /api/triggers/run-now endpoint)."""
    results = {}

    try:
        results["naukri"] = scan_naukri_jobs()
    except Exception as e:
        results["naukri"] = {"error": str(e)}

    try:
        results["news"] = scan_google_news()
    except Exception as e:
        results["news"] = {"error": str(e)}

    try:
        results["nabl"] = check_nabl_renewals()
    except Exception as e:
        results["nabl"] = {"error": str(e)}

    try:
        results["iso"] = check_iso_audit_windows()
    except Exception as e:
        results["iso"] = {"error": str(e)}

    try:
        results["import_spike"] = detect_import_spikes()
    except Exception as e:
        results["import_spike"] = {"error": str(e)}

    try:
        results["reviews"] = mine_google_reviews()
    except Exception as e:
        results["reviews"] = {"error": str(e)}

    logger.info(f"All triggers complete: {results}")
    return results


# ============================================================
# UTILITY: Expire old signals
# ============================================================

@celery_app.task(name="workers.triggerEngine.expire_old_signals")
def expire_old_signals():
    """Mark expired signals as inactive."""
    db = get_db_session()
    try:
        expired = db.query(CompanyIntentSignal).filter(
            CompanyIntentSignal.is_active == 1,
            CompanyIntentSignal.expires_at <= datetime.utcnow()
        ).all()

        for signal in expired:
            signal.is_active = 0

        db.commit()
        logger.info(f"Expired {len(expired)} old signals")
        return {"expired_count": len(expired)}

    finally:
        db.close()
