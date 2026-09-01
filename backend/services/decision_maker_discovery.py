"""Decision-Maker Discovery & Verification Engine.

Implements the complete 8-step pipeline:
1. Persona inference from signal/industry
2. Search query generation
3. Web/public research execution
4. Person candidate extraction
5. Person verification & scoring
6. Apollo enrichment (specific person)
7. Research brief assembly
8. Full pipeline orchestration

Core principle: PERSONA ≠ PERSON.
A persona inference such as "Quality / Metrology Manager" is NOT a person.
The system must find an actual human with evidence before Apollo enrichment.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from config import settings
from models.company import Company
from models.person import Person
from models.decision_maker_candidate import (
    DecisionMakerCandidate,
    VERIFICATION_STATUSES,
    REJECTION_REASONS,
    STAKEHOLDER_ROLES,
)
from services.research_provider import research_router, PROVIDER_LIVE, PROVIDER_NOT_CONFIGURED

logger = logging.getLogger(__name__)

# ── Person Match Score Weights ──────────────────────────────────────────
# Configurable — can later be learned from outcomes
SCORE_WEIGHTS = {
    "company_match": 0.30,
    "role_relevance": 0.30,
    "facility_match": 0.10,
    "recency": 0.15,
    "evidence_quality": 0.15,
}

# Minimum score threshold for Apollo enrichment
APOLLO_ELIGIBLE_THRESHOLD = 0.55
CANDIDATE_THRESHOLD = 0.30

# ── Persona → Titles Mapping ───────────────────────────────────────────
PERSONA_TITLE_MAP = {
    "Quality / Metrology": {
        "titles": [
            "Quality Head", "Quality Manager", "QA Manager", "QA Head",
            "Metrology Manager", "Metrology Head", "Metrology Engineer",
            "Calibration Manager", "Calibration Head", "Calibration Engineer",
            "Head of Quality Assurance", "Director Quality",
        ],
        "stakeholder_role": "Evaluator",
        "department_keywords": ["quality", "metrology", "calibration", "qa", "qc", "qms"],
    },
    "Maintenance / Plant": {
        "titles": [
            "Plant Head", "Plant Manager", "Maintenance Head", "Maintenance Manager",
            "Maintenance Engineer", "Engineering Manager", "Operations Head",
            "VP Operations", "Plant Engineer", "Chief Engineer",
        ],
        "stakeholder_role": "User",
        "department_keywords": ["maintenance", "plant", "operations", "engineering", "production"],
    },
    "Purchase / Procurement": {
        "titles": [
            "Purchase Manager", "Procurement Head", "Procurement Manager",
            "Purchase Head", "Senior Procurement Manager", "Buyer",
            "Vendor Development Manager",
        ],
        "stakeholder_role": "Purchaser",
        "department_keywords": ["purchase", "procurement", "buying", "sourcing", "vendor"],
    },
    "Management / Executive": {
        "titles": [
            "Managing Director", "CEO", "COO", "VP Operations",
            "General Manager", "Factory Manager", "Works Manager",
        ],
        "stakeholder_role": "Approver",
        "department_keywords": ["management", "executive", "leadership", "general"],
    },
    "Corporate Quality": {
        "titles": [
            "Corporate Quality Head", "Group Quality Head",
            "Director Corporate Quality", "VP Quality",
        ],
        "stakeholder_role": "Recommender",
        "department_keywords": ["corporate quality", "group quality"],
    },
}


# ═════════════════════════════════════════════════════════════════════════
# STEP 1: Persona Inference
# ═════════════════════════════════════════════════════════════════════════

def infer_target_personas(
    signal_type: str,
    industry: str = "Manufacturing",
) -> List[Dict[str, Any]]:
    """Infer target decision-maker personas from signal type and industry.

    Returns ranked list of personas with their titles, stakeholder roles,
    and search priority.

    This is PERSONA INFERENCE only — not person identification.
    """
    # Primary persona selection based on signal
    if signal_type in ("iso_iatf_audit", "regulatory_qco"):
        primary = "Quality / Metrology"
        secondary = ["Purchase / Procurement", "Management / Executive"]
    elif signal_type in ("plant_expansion", "capex_announcement"):
        primary = "Maintenance / Plant"
        secondary = ["Quality / Metrology", "Purchase / Procurement"]
    elif signal_type in ("qa_hiring",):
        primary = "Quality / Metrology"
        secondary = ["Maintenance / Plant"]
    elif signal_type in ("oem_supplier_mandate",):
        primary = "Quality / Metrology"
        secondary = ["Purchase / Procurement", "Maintenance / Plant"]
    elif signal_type in ("ev_battery_manufacturing",):
        primary = "Maintenance / Plant"
        secondary = ["Quality / Metrology", "Purchase / Procurement"]
    else:
        primary = "Quality / Metrology"
        secondary = ["Maintenance / Plant", "Purchase / Procurement"]

    personas = []
    primary_info = PERSONA_TITLE_MAP.get(primary, {})
    personas.append({
        "persona": primary,
        "titles": primary_info.get("titles", []),
        "stakeholder_role": primary_info.get("stakeholder_role", "Evaluator"),
        "priority": "PRIMARY",
        "reason": f"Signal '{signal_type}' in {industry} most directly affects {primary} function.",
    })

    for sec in secondary:
        sec_info = PERSONA_TITLE_MAP.get(sec, {})
        personas.append({
            "persona": sec,
            "titles": sec_info.get("titles", []),
            "stakeholder_role": sec_info.get("stakeholder_role", "Influencer"),
            "priority": "SECONDARY",
            "reason": f"Secondary stakeholder for {signal_type} signal.",
        })

    return personas


# ═════════════════════════════════════════════════════════════════════════
# STEP 2: Search Query Generation
# ═════════════════════════════════════════════════════════════════════════

def generate_search_queries(
    company_name: str,
    personas: List[Dict[str, Any]],
    city: Optional[str] = None,
    facility: Optional[str] = None,
) -> List[Dict[str, str]]:
    """Generate targeted search queries for person discovery.

    Dynamically constructs queries based on company, persona, and location.
    """
    queries = []
    clean_name = company_name.strip()

    for persona_info in personas:
        persona = persona_info["persona"]
        titles = persona_info.get("titles", [])[:5]  # Top 5 titles

        for title in titles:
            # Direct title search
            queries.append({
                "query": f'"{clean_name}" "{title}"',
                "persona": persona,
                "search_type": "title_match",
            })

        # Location-qualified search
        if city:
            queries.append({
                "query": f'"{clean_name}" quality metrology {city}',
                "persona": persona,
                "search_type": "location_qualified",
            })

        # Department search
        dept_keywords = PERSONA_TITLE_MAP.get(persona, {}).get("department_keywords", [])
        if dept_keywords:
            queries.append({
                "query": f'"{clean_name}" {dept_keywords[0]} head manager',
                "persona": persona,
                "search_type": "department_search",
            })

    # Company leadership page
    queries.append({
        "query": f'"{clean_name}" team leadership management site:{clean_name.lower().replace(" ", "")}.com',
        "persona": "General",
        "search_type": "company_website",
    })

    # Professional profile search (public indexed)
    queries.append({
        "query": f'{clean_name} quality calibration metrology manager site:linkedin.com/in',
        "persona": "Quality / Metrology",
        "search_type": "public_professional_profile",
    })

    return queries


# ═════════════════════════════════════════════════════════════════════════
# STEP 3: Web/Public Research Execution
# ═════════════════════════════════════════════════════════════════════════

def execute_web_person_search(
    company_id: int,
    company_name: str,
    queries: List[Dict[str, str]],
    db: Session,
    max_queries: int = 8,
) -> Dict[str, Any]:
    """Execute real web searches using configured research provider.

    Returns structured results with provider status transparency.
    Does NOT generate fictional search results.
    """
    all_results = []
    provider_status = research_router.get_provider_status()
    best_provider = research_router.get_best_search_provider()
    search_provider_used = best_provider or "none"
    overall_status = PROVIDER_LIVE if best_provider else PROVIDER_NOT_CONFIGURED

    executed_queries = []

    for q_info in queries[:max_queries]:
        search_result = research_router.search(
            query=q_info["query"],
            num_results=5,
            company_id=company_id,
            db=db,
        )

        executed_queries.append({
            "query": q_info["query"],
            "persona": q_info["persona"],
            "search_type": q_info["search_type"],
            "provider": search_result["provider"],
            "provider_status": search_result["provider_status"],
            "result_count": len(search_result["results"]),
            "error": search_result.get("error"),
        })

        for r in search_result["results"]:
            r["persona"] = q_info["persona"]
            r["search_type"] = q_info["search_type"]
            all_results.append(r)

        if search_result["provider_status"] != PROVIDER_LIVE:
            overall_status = search_result["provider_status"]

    return {
        "company_id": company_id,
        "company_name": company_name,
        "search_provider": search_provider_used,
        "provider_statuses": provider_status,
        "overall_status": overall_status,
        "queries_executed": executed_queries,
        "total_results": len(all_results),
        "results": all_results,
    }


# ═════════════════════════════════════════════════════════════════════════
# STEP 4: Person Candidate Extraction
# ═════════════════════════════════════════════════════════════════════════

def extract_person_candidates(
    search_results: List[Dict[str, Any]],
    company_name: str,
) -> List[Dict[str, Any]]:
    """Extract person candidates from raw search results.

    Uses pattern matching for name + title + company co-occurrence.
    Each candidate is a hypothesis, NOT a verified person.
    """
    candidates = []
    seen_names = set()
    company_lower = company_name.lower()

    # Common Indian name patterns
    name_pattern = re.compile(
        r"\b([A-Z][a-z]{1,15}(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]{2,20}(?:\s+[A-Z][a-z]{2,20})?)\b"
    )

    # Title keywords that indicate calibration/quality decision-makers
    title_keywords = [
        "quality", "metrology", "calibration", "qa", "qc", "maintenance",
        "plant head", "plant manager", "purchase", "procurement", "operations",
        "engineering", "instrumentation", "testing", "inspection",
        "head", "manager", "director", "lead", "vp", "chief",
    ]

    # Direct profile pattern in result titles: "Name - Title [- Company]"
    profile_title_pattern = re.compile(
        r"^([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\s*[-–|:]\s*([A-Za-z\s/&,.-]{4,60}?)(?:\s*[-–|:]|\s+at\s+|\s+@\s+|$)",
        re.IGNORECASE
    )

    for result in search_results:
        snippet = result.get("snippet", "")
        title = result.get("title", "")
        url = result.get("url", "")
        combined_text = f"{title} {snippet}"

        # Check if this result is relevant to our company
        company_relevance = _fuzzy_company_match(combined_text, company_name)
        if company_relevance < 0.3:
            continue

        # Strategy A: Check for structured profile title: "Name - Title [- Company]"
        profile_match = profile_title_pattern.match(title.strip())
        if profile_match:
            cand_name = profile_match.group(1).strip()
            cand_raw_title = profile_match.group(2).strip()
            if not _is_non_name(cand_name) and cand_name.lower() not in seen_names:
                if any(kw in cand_raw_title.lower() for kw in title_keywords):
                    seen_names.add(cand_name.lower())
                    location = _extract_location_hint(combined_text)
                    candidates.append({
                        "candidate_name": cand_name,
                        "candidate_title": cand_raw_title.title(),
                        "candidate_company_match": company_relevance > 0.5,
                        "candidate_facility": location.get("facility", ""),
                        "candidate_location": location.get("city", ""),
                        "evidence_source": result.get("provider", "web_search"),
                        "evidence_url": url,
                        "evidence_snippet": snippet[:300],
                        "evidence_type": result.get("evidence_type", "WEB_EVIDENCE"),
                        "persona": result.get("persona", ""),
                        "search_type": result.get("search_type", ""),
                        "raw_confidence": 0.85,
                    })
                    continue

        # Strategy B: LinkedIn profile URL with name in title (e.g., "First Last - Company | LinkedIn")
        if "linkedin.com/in/" in url and (" - " in title or " | " in title):
            raw_name_part = title.split(" - ")[0].split(" | ")[0].strip()
            if not _is_non_name(raw_name_part) and len(raw_name_part.split()) in (2, 3):
                title_found = _extract_title_near_name(combined_text, raw_name_part, title_keywords) or "Quality / Technical Lead"
                seen_names.add(raw_name_part.lower())
                location = _extract_location_hint(combined_text)
                candidates.append({
                    "candidate_name": raw_name_part,
                    "candidate_title": title_found,
                    "candidate_company_match": company_relevance > 0.5,
                    "candidate_facility": location.get("facility", ""),
                    "candidate_location": location.get("city", ""),
                    "evidence_source": result.get("provider", "web_search"),
                    "evidence_url": url,
                    "evidence_snippet": snippet[:300],
                    "evidence_type": "public_professional_profile",
                    "persona": result.get("persona", ""),
                    "search_type": "public_professional_profile",
                    "raw_confidence": 0.90,
                })
                continue

        # Strategy C: Extract name ONLY from title, never from arbitrary snippet sentences
        title_names = name_pattern.findall(title)
        for name in title_names:
            name = name.strip()
            if len(name) < 5 or name.lower() in seen_names or _is_non_name(name):
                continue
            title_found = _extract_title_near_name(title, name, title_keywords)
            if title_found:
                seen_names.add(name.lower())
                location = _extract_location_hint(combined_text)
                candidates.append({
                    "candidate_name": name,
                    "candidate_title": title_found,
                    "candidate_company_match": company_relevance > 0.5,
                    "candidate_facility": location.get("facility", ""),
                    "candidate_location": location.get("city", ""),
                    "evidence_source": result.get("provider", "web_search"),
                    "evidence_url": url,
                    "evidence_snippet": snippet[:300],
                    "evidence_type": result.get("evidence_type", "WEB_EVIDENCE"),
                    "persona": result.get("persona", ""),
                    "search_type": result.get("search_type", ""),
                    "raw_confidence": company_relevance * 0.6 + 0.4,
                })

    return candidates


def _fuzzy_company_match(text: str, company_name: str) -> float:
    """Calculate fuzzy match score between text and company name."""
    text_lower = text.lower()
    company_lower = company_name.lower()

    # Exact match
    if company_lower in text_lower:
        return 1.0

    # Key word overlap
    company_words = set(company_lower.split())
    # Remove common stop words
    stop_words = {"ltd", "pvt", "limited", "private", "inc", "co", "the", "of", "and", "&"}
    company_words -= stop_words
    if not company_words:
        return 0.0

    matches = sum(1 for w in company_words if w in text_lower)
    return matches / len(company_words)


def _is_non_name(name: str) -> bool:
    """Filter out common false-positive name patterns."""
    name_lower = name.lower().strip()
    non_names = {
        "quality head", "plant head", "quality manager", "purchase manager",
        "corporate quality head", "plant quality head", "senior manager",
        "general manager", "managing director", "operations head",
        "read more", "learn more", "click here", "see more", "view all",
        "terms conditions", "privacy policy", "cookie policy",
        "phone number", "email address", "contact details",
        "bharat forge", "bharat forge ltd", "bharat forge limited",
        "kalyani forge", "talbros automotive", "talbros automotive ltd",
        "manufacturing quality assurance", "india view", "colleague at",
        "pharma jobs", "walk in interview", "executive maintenance jobs",
        "quality engineer", "maintenance head", "plant engineer",
    }
    if name_lower in non_names:
        return True
    action_words = ("responsible", "experienced", "certified", "skilled", "accomplished", "leading", "handling", "seeking", "dedicated")
    if any(name_lower.startswith(w + " ") or name_lower.startswith(w + "-") for w in action_words):
        return True
    if any(term in name_lower for term in (
        "head", "manager", "director", "phone", "email", "limited", "ltd", "pvt",
        "assurance", "colleague", "view", "profile", "jobs", "job", "hiring",
        "interview", "opening", "vacancy", "careers", "executive", "engineer",
        "operations", "walk-in", "recruitment", "news", "updates", "team",
        "quality", "maintenance", "procurement", "purchase", "engineering",
        "production", "metrology", "calibration", "safety", "inspection",
        "testing", "instrumentation", "services", "solutions",
    )):
        return True
    return len(name.split()) > 4 or len(name.split()) < 2


def _extract_title_near_name(text: str, name: str, title_keywords: list) -> Optional[str]:
    """Extract a professional title near a person's name in text."""
    text_lower = text.lower()
    name_lower = name.lower()
    name_pos = text_lower.find(name_lower)

    if name_pos == -1:
        return None

    # Look at text within 150 chars of the name
    context = text_lower[max(0, name_pos - 80):name_pos + len(name) + 150]

    # Common title patterns
    title_patterns = [
        r"(?:head|manager|director|lead|chief|vp|sr\.|senior)\s+(?:of\s+)?(?:quality|metrology|calibration|maintenance|operations|procurement|purchase|engineering|plant|production|instrumentation)",
        r"(?:quality|metrology|calibration|maintenance|operations|procurement|purchase|engineering|plant|production|instrumentation)\s+(?:head|manager|director|lead|chief|engineer|officer)",
        r"(?:managing director|general manager|factory manager|works manager|ceo|coo|cto)",
    ]

    for pattern in title_patterns:
        match = re.search(pattern, context, re.IGNORECASE)
        if match:
            return match.group(0).strip().title()

    # Fallback: any title keyword near the name
    for kw in title_keywords:
        if kw in context:
            # Try to extract a meaningful title phrase
            kw_pos = context.find(kw)
            phrase = context[max(0, kw_pos - 20):kw_pos + len(kw) + 20].strip()
            # Clean up
            phrase = re.sub(r"[^a-zA-Z\s/&-]", "", phrase).strip()
            if len(phrase) > 5:
                return phrase.title()

    return None


def _extract_location_hint(text: str) -> Dict[str, str]:
    """Extract location hints from text."""
    indian_cities = [
        "Mumbai", "Pune", "Chennai", "Bengaluru", "Bangalore", "Hyderabad",
        "Delhi", "Noida", "Gurgaon", "Gurugram", "Ahmedabad", "Vadodara",
        "Nashik", "Aurangabad", "Hosur", "Coimbatore", "Kolkata", "Jaipur",
        "Indore", "Dahej", "Hazira", "Chakan", "Rajkot", "Surat",
    ]
    result = {"city": "", "facility": ""}
    text_lower = text.lower()

    for city in indian_cities:
        if city.lower() in text_lower:
            result["city"] = city
            break

    # Facility hints
    facility_match = re.search(
        r"(?:plant|unit|facility|factory|works|division)\s*[-:]?\s*(\d+|[A-Z])",
        text, re.IGNORECASE
    )
    if facility_match:
        result["facility"] = facility_match.group(0)

    return result


# ═════════════════════════════════════════════════════════════════════════
# STEP 5: Person Verification & Scoring
# ═════════════════════════════════════════════════════════════════════════

def verify_person_candidate(
    candidate: Dict[str, Any],
    company: Company,
) -> Dict[str, Any]:
    """Verify a person candidate against company and calibration relevance.

    Multi-dimensional scoring:
    - Company Match: 0.30 weight
    - Role Relevance: 0.30 weight
    - Facility Match: 0.10 weight
    - Recency: 0.15 weight
    - Evidence Quality: 0.15 weight

    Thresholds:
    - Composite >= 0.55: PERSON_PUBLICLY_VERIFIED
    - Composite >= 0.30: PERSON_CANDIDATE
    - Composite < 0.30: PERSON_REJECTED
    """
    scores = {}

    # ── Company Match (0.30 weight) ─────────────────────────────────────
    if candidate.get("candidate_company_match"):
        scores["company_match"] = 1.0
    else:
        # Fuzzy check
        company_words = set(company.name.lower().split()) - {"ltd", "pvt", "limited", "private"}
        name_in_evidence = candidate.get("evidence_snippet", "").lower()
        overlap = sum(1 for w in company_words if w in name_in_evidence) / max(len(company_words), 1)
        scores["company_match"] = min(overlap, 1.0)

    # ── Role Relevance (0.30 weight) ────────────────────────────────────
    title = (candidate.get("candidate_title") or "").lower()
    calibration_keywords = [
        "quality", "metrology", "calibration", "qa", "qc", "testing",
        "inspection", "measurement", "instrumentation",
    ]
    decision_keywords = ["head", "manager", "director", "lead", "chief", "vp", "sr"]

    has_calibration = any(kw in title for kw in calibration_keywords)
    has_decision = any(kw in title for kw in decision_keywords)
    has_operations = any(kw in title for kw in ["maintenance", "plant", "operations", "purchase", "procurement"])

    if has_calibration and has_decision:
        scores["role_relevance"] = 1.0
    elif has_calibration:
        scores["role_relevance"] = 0.7
    elif has_operations and has_decision:
        scores["role_relevance"] = 0.6
    elif has_decision:
        scores["role_relevance"] = 0.4
    else:
        scores["role_relevance"] = 0.1

    # ── Facility/Location Match (0.10 weight) ──────────────────────────
    candidate_city = (candidate.get("candidate_location") or "").lower()
    company_city = (company.city or "").lower()

    if candidate_city and company_city and candidate_city in company_city:
        scores["facility_match"] = 1.0
    elif candidate_city and company_city:
        scores["facility_match"] = 0.3
    else:
        scores["facility_match"] = 0.5  # Unknown = neutral

    # ── Recency (0.15 weight) ──────────────────────────────────────────
    # We can't always determine recency from web results
    # Default to moderate unless evidence suggests otherwise
    scores["recency"] = 0.6

    # ── Evidence Quality (0.15 weight) ──────────────────────────────────
    evidence_url = candidate.get("evidence_url", "")
    evidence_type = candidate.get("search_type", "")

    if "linkedin.com" in evidence_url:
        scores["evidence_quality"] = 0.85
    elif any(d in evidence_url for d in [".com/team", ".com/about", ".com/leadership"]):
        scores["evidence_quality"] = 0.90
    elif evidence_type == "public_professional_profile":
        scores["evidence_quality"] = 0.75
    elif evidence_type == "company_website":
        scores["evidence_quality"] = 0.80
    else:
        scores["evidence_quality"] = 0.50

    # ── Composite Score ────────────────────────────────────────────────
    composite = sum(scores[dim] * SCORE_WEIGHTS[dim] for dim in SCORE_WEIGHTS)

    # ── Verification Decision ──────────────────────────────────────────
    rejection_reason = None
    rejection_details = None

    if scores["company_match"] < 0.3:
        verification_status = "PERSON_REJECTED"
        rejection_reason = "company_mismatch"
        rejection_details = f"Company match score {scores['company_match']:.2f} below threshold"
    elif scores["role_relevance"] < 0.2:
        verification_status = "PERSON_REJECTED"
        rejection_reason = "irrelevant_role"
        rejection_details = f"Role '{candidate.get('candidate_title')}' not relevant to calibration decisions"
    elif composite < CANDIDATE_THRESHOLD:
        verification_status = "PERSON_REJECTED"
        rejection_reason = "low_confidence"
        rejection_details = f"Composite score {composite:.2f} below threshold {CANDIDATE_THRESHOLD}"
    elif composite >= APOLLO_ELIGIBLE_THRESHOLD:
        verification_status = "PERSON_PUBLICLY_VERIFIED"
    else:
        verification_status = "PERSON_CANDIDATE"

    # ── Adaptive Research Tasks ────────────────────────────────────────
    pending_research = []
    if scores["company_match"] < 0.7 and verification_status != "PERSON_REJECTED":
        pending_research.append({
            "task": f"Verify whether {candidate.get('candidate_name')} is currently employed by {company.name}.",
            "reason": f"Company match score is {scores['company_match']:.2f}",
            "priority": "HIGH",
            "status": "PENDING",
        })
    if scores["role_relevance"] < 0.5 and verification_status != "PERSON_REJECTED":
        pending_research.append({
            "task": f"Find evidence that {candidate.get('candidate_name')} manages metrology or calibration.",
            "reason": f"Role relevance score is {scores['role_relevance']:.2f}",
            "priority": "MEDIUM",
            "status": "PENDING",
        })

    return {
        "verification_status": verification_status,
        "scores": scores,
        "composite_score": round(composite, 3),
        "rejection_reason": rejection_reason,
        "rejection_details": rejection_details,
        "pending_research_tasks": pending_research,
        "apollo_eligible": composite >= APOLLO_ELIGIBLE_THRESHOLD and verification_status != "PERSON_REJECTED",
    }


# ═════════════════════════════════════════════════════════════════════════
# STEP 6: Apollo Enrichment (Specific Person)
# ═════════════════════════════════════════════════════════════════════════

def enrich_candidate_via_apollo(
    candidate_record: DecisionMakerCandidate,
    company_name: str,
    db: Session,
) -> Dict[str, Any]:
    """Enrich a specific verified person via Apollo.

    Apollo is used as ENRICHMENT, not person discovery.
    Only verified candidates with sufficient confidence proceed.
    """
    from services.apollo_adapter import enrich_specific_person

    if candidate_record.verification_status in ("PERSON_REJECTED", "PERSONA_INFERRED"):
        return {
            "status": "SKIPPED",
            "reason": f"Candidate status is {candidate_record.verification_status}, not eligible for Apollo",
        }

    if candidate_record.verification_confidence < APOLLO_ELIGIBLE_THRESHOLD:
        return {
            "status": "SKIPPED",
            "reason": f"Confidence {candidate_record.verification_confidence:.2f} below Apollo threshold {APOLLO_ELIGIBLE_THRESHOLD}",
        }

    result = enrich_specific_person(
        person_name=candidate_record.candidate_name,
        company_name=company_name,
        title=candidate_record.candidate_title,
    )

    # Update candidate record
    candidate_record.apollo_enrichment_status = result.get("status", "ERROR")
    candidate_record.apollo_email = result.get("email")
    candidate_record.apollo_email_confidence = result.get("email_confidence")
    candidate_record.apollo_phone = result.get("phone")
    candidate_record.apollo_response_json = result.get("raw_response")
    candidate_record.enriched_at = datetime.utcnow()

    if result.get("status") == "ENRICHED" and result.get("email"):
        candidate_record.verification_status = "APOLLO_ENRICHED"
        candidate_record.email_status = "EMAIL_FOUND"
    elif result.get("status") == "APOLLO_BLOCKED":
        candidate_record.apollo_enrichment_status = "APOLLO_BLOCKED"
    elif result.get("status") == "NO_RESULT":
        candidate_record.apollo_enrichment_status = "NO_RESULT"

    db.commit()

    return result


# ═════════════════════════════════════════════════════════════════════════
# STEP 7: Research Brief Assembly
# ═════════════════════════════════════════════════════════════════════════

def build_research_brief_with_persons(
    company: Company,
    candidates: List[DecisionMakerCandidate],
    signal_info: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build complete research brief with person discovery chain.

    Includes all 24 required fields from the specification.
    """
    # Sort candidates: verified first, then by score
    sorted_candidates = sorted(
        candidates,
        key=lambda c: (
            0 if c.verification_status == "PERSON_REJECTED" else 1,
            c.score_composite or 0,
        ),
        reverse=True,
    )

    primary = None
    secondary = []
    for c in sorted_candidates:
        if c.verification_status != "PERSON_REJECTED":
            if primary is None and c.contact_priority == "PRIMARY":
                primary = c
            elif primary is None:
                primary = c
            else:
                secondary.append(c)

    def _person_brief(c: DecisionMakerCandidate) -> Dict[str, Any]:
        return {
            "name": c.candidate_name or "PERSON UNKNOWN",
            "title": c.candidate_title,
            "facility": c.candidate_facility,
            "location": c.candidate_location,
            "persona": c.target_persona,
            "stakeholder_role": c.stakeholder_role,
            "verification_status": c.verification_status,
            "person_match_score": round(c.score_composite or 0, 3),
            "score_breakdown": {
                "company_match": round(c.score_company_match or 0, 3),
                "role_relevance": round(c.score_role_relevance or 0, 3),
                "facility_match": round(c.score_facility_match or 0, 3),
                "recency": round(c.score_recency or 0, 3),
                "evidence_quality": round(c.score_evidence_quality or 0, 3),
            },
            "evidence": c.evidence_sources or [],
            "public_profile_url": c.public_profile_url,
            "apollo_status": c.apollo_enrichment_status,
            "email": c.apollo_email or "NOT FOUND",
            "email_confidence": c.apollo_email_confidence or "UNKNOWN",
            "email_status": c.email_status,
            "phone": c.apollo_phone,
            "contact_priority": c.contact_priority,
            "priority_reason": c.priority_reason,
            "pending_research": c.pending_research_tasks or [],
        }

    brief = {
        # Company
        "company": company.name,
        "company_id": company.id,
        "facility": f"{company.city}, {company.state}",
        "industry": company.industry or "Manufacturing",

        # Signal
        "discovery_signal": signal_info.get("signal_type") if signal_info else "MANUAL",
        "signal_evidence": signal_info.get("event_title") if signal_info else None,
        "calibration_reasoning": signal_info.get("calibration_impact") if signal_info else None,
        "likely_requirement": signal_info.get("likely_parameters") if signal_info else [],

        # Persona
        "target_persona": primary.target_persona if primary else "PERSONA NOT INFERRED",

        # Actual Person
        "actual_person": _person_brief(primary) if primary else {
            "name": "NO VERIFIED PERSON FOUND",
            "verification_status": "RESEARCH REQUIRED",
            "person_match_score": 0,
        },

        # Secondary Contacts
        "secondary_contacts": [_person_brief(c) for c in secondary[:5]],

        # Contact Sequence
        "contact_sequence": (
            [primary.candidate_name] + [c.candidate_name for c in secondary[:3]]
            if primary else []
        ),
        "primary_contact_reason": primary.priority_reason if primary else "No verified person found",

        # Buying Intelligence
        "buying_window": company.buying_window or "UNKNOWN",
        "premium_potential": signal_info.get("price_sensitivity", "UNKNOWN") if signal_info else "UNKNOWN",
        "price_sensitivity": signal_info.get("price_sensitivity", "UNKNOWN") if signal_info else "UNKNOWN",

        # Epistemic State
        "what_we_know": [],
        "what_we_infer": [],
        "what_we_dont_know": [],

        # Action
        "next_best_action": "RESEARCH REQUIRED" if not primary else (
            "APOLLO ENRICHMENT" if primary.apollo_enrichment_status == "NOT_ATTEMPTED"
            else "CAMPAIGN READY" if primary.apollo_email
            else "ADDITIONAL RESEARCH"
        ),

        # Metadata
        "total_candidates": len(candidates),
        "verified_count": sum(1 for c in candidates if c.verification_status not in ("PERSON_REJECTED", "PERSONA_INFERRED")),
        "rejected_count": sum(1 for c in candidates if c.verification_status == "PERSON_REJECTED"),
    }

    # Populate epistemic state
    if primary and primary.candidate_name:
        brief["what_we_know"].append(f"Identified {primary.candidate_name} as {primary.candidate_title} at {company.name}")
    if primary and primary.evidence_sources:
        brief["what_we_know"].append(f"Evidence from {len(primary.evidence_sources)} source(s)")
    if signal_info:
        brief["what_we_infer"].append(f"Calibration demand inferred from {signal_info.get('signal_type', 'unknown')} signal")

    if not primary or primary.verification_status == "PERSON_CANDIDATE":
        brief["what_we_dont_know"].append("Cannot confirm this person is the current calibration decision-maker")
    if primary and primary.apollo_enrichment_status == "NOT_ATTEMPTED":
        brief["what_we_dont_know"].append("Contact email/phone not yet verified via Apollo")
    if not primary:
        brief["what_we_dont_know"].append("No identifiable decision-maker found through available research")

    return brief


# ═════════════════════════════════════════════════════════════════════════
# STEP 8: Full Pipeline Orchestration
# ═════════════════════════════════════════════════════════════════════════

def run_full_discovery_pipeline(
    company_id: int,
    db: Session,
    signal_type: Optional[str] = None,
    max_apollo_enrichments: int = 3,
) -> Dict[str, Any]:
    """Orchestrate the complete decision-maker discovery pipeline.

    Steps:
    1. Company lookup
    2. Persona inference
    3. Search query generation
    4. Web/public research
    5. Person candidate extraction
    6. Verification & scoring
    7. Apollo enrichment (top candidates only)
    8. Research brief assembly

    Reports each stage separately with REAL/MOCK/BLOCKED status.
    """
    pipeline_start = time.time()
    stages = {}

    # ── 1. Company Lookup ──────────────────────────────────────────────
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        return {"error": f"Company {company_id} not found", "stages": {}}

    stages["company_lookup"] = {
        "status": "REAL",
        "company": company.name,
        "city": company.city,
        "state": company.state,
        "industry": company.industry,
    }

    # ── 2. Persona Inference ──────────────────────────────────────────
    effective_signal = signal_type or "general_signal"
    personas = infer_target_personas(effective_signal, company.industry or "Manufacturing")
    stages["persona_inference"] = {
        "status": "REAL",
        "signal_type": effective_signal,
        "personas": personas,
    }

    # Create initial PERSONA_INFERRED candidates
    for persona_info in personas:
        existing = db.query(DecisionMakerCandidate).filter(
            DecisionMakerCandidate.company_id == company_id,
            DecisionMakerCandidate.target_persona == persona_info["persona"],
            DecisionMakerCandidate.verification_status == "PERSONA_INFERRED",
        ).first()

        if not existing:
            dmc = DecisionMakerCandidate(
                company_id=company_id,
                target_persona=persona_info["persona"],
                target_titles=persona_info["titles"],
                stakeholder_role=persona_info["stakeholder_role"],
                contact_priority=persona_info["priority"],
                priority_reason=persona_info["reason"],
                verification_status="PERSONA_INFERRED",
            )
            db.add(dmc)
    db.commit()

    # ── 3. Search Query Generation ────────────────────────────────────
    queries = generate_search_queries(
        company_name=company.name,
        personas=personas,
        city=company.city,
    )
    stages["search_queries"] = {
        "status": "REAL",
        "query_count": len(queries),
        "queries": [q["query"] for q in queries[:5]],  # Sample
    }

    # ── 4. Web/Public Research ────────────────────────────────────────
    search_results = execute_web_person_search(
        company_id=company_id,
        company_name=company.name,
        queries=queries,
        db=db,
        max_queries=6,
    )
    stages["person_search"] = {
        "status": search_results["overall_status"],
        "provider": search_results["search_provider"],
        "provider_statuses": search_results["provider_statuses"],
        "total_results": search_results["total_results"],
        "queries_executed": len(search_results["queries_executed"]),
    }

    # ── 5. Person Candidate Extraction ────────────────────────────────
    raw_candidates = extract_person_candidates(
        search_results=search_results["results"],
        company_name=company.name,
    )
    stages["candidates"] = {
        "status": "REAL" if raw_candidates else "NO_CANDIDATES_FOUND",
        "count": len(raw_candidates),
    }

    # ── 6. Verification & Scoring ─────────────────────────────────────
    verified_candidates = []
    rejected_candidates = []

    for raw_c in raw_candidates:
        verification = verify_person_candidate(raw_c, company)

        # Determine the persona for this candidate
        matching_persona = raw_c.get("persona", "Quality / Metrology")

        # Create or update DecisionMakerCandidate record
        dmc = DecisionMakerCandidate(
            company_id=company_id,
            target_persona=matching_persona,
            target_titles=PERSONA_TITLE_MAP.get(matching_persona, {}).get("titles", []),
            stakeholder_role=PERSONA_TITLE_MAP.get(matching_persona, {}).get("stakeholder_role", "Evaluator"),
            candidate_name=raw_c["candidate_name"],
            candidate_title=raw_c.get("candidate_title"),
            candidate_company_match=raw_c.get("candidate_company_match", False),
            candidate_facility=raw_c.get("candidate_facility", ""),
            candidate_location=raw_c.get("candidate_location", ""),
            evidence_sources=[{
                "source": raw_c.get("evidence_source", "web_search"),
                "url": raw_c.get("evidence_url", ""),
                "snippet": raw_c.get("evidence_snippet", ""),
                "retrieved_at": datetime.utcnow().isoformat(),
                "confidence": raw_c.get("raw_confidence", 0.5),
                "evidence_type": raw_c.get("evidence_type", "WEB_EVIDENCE"),
            }],
            search_queries_used=[raw_c.get("persona", "")],
            verification_status=verification["verification_status"],
            verification_confidence=verification["composite_score"],
            verification_notes=f"Composite score: {verification['composite_score']:.3f}",
            rejection_reason=verification.get("rejection_reason"),
            rejection_details=verification.get("rejection_details"),
            score_company_match=verification["scores"]["company_match"],
            score_role_relevance=verification["scores"]["role_relevance"],
            score_facility_match=verification["scores"]["facility_match"],
            score_recency=verification["scores"]["recency"],
            score_evidence_quality=verification["scores"]["evidence_quality"],
            score_composite=verification["composite_score"],
            pending_research_tasks=verification.get("pending_research_tasks", []),
        )

        if verification["verification_status"] == "PERSON_PUBLICLY_VERIFIED":
            dmc.verified_at = datetime.utcnow()
            if not verified_candidates:
                dmc.contact_priority = "PRIMARY"
                dmc.priority_reason = (
                    f"Selected as PRIMARY decision-maker: Highest verification match score ({verification['composite_score']:.2f}) "
                    f"for target {matching_persona} function at {company.name}."
                )
            elif len(verified_candidates) <= 2:
                dmc.contact_priority = "SECONDARY"
                dmc.priority_reason = (
                    f"Secondary stakeholder ({matching_persona}) with strong verification score ({verification['composite_score']:.2f})."
                )
            else:
                dmc.contact_priority = "OTHER"
                dmc.priority_reason = f"Additional stakeholder ({matching_persona}) identified at {company.name}."
        elif verification["verification_status"] == "PERSON_CANDIDATE":
            dmc.contact_priority = "OTHER"
            dmc.priority_reason = "Unverified candidate hypothesis — requires additional evidence before engagement."

        db.add(dmc)
        db.flush()

        if verification["verification_status"] == "PERSON_REJECTED":
            rejected_candidates.append(dmc)
        else:
            verified_candidates.append(dmc)

    db.commit()

    stages["public_evidence"] = {
        "status": "REAL",
        "verified_count": len(verified_candidates),
        "candidate_count": sum(1 for c in verified_candidates if c.verification_status == "PERSON_CANDIDATE"),
        "rejected_count": len(rejected_candidates),
        "rejection_reasons": [
            {"name": c.candidate_name, "reason": c.rejection_reason, "details": c.rejection_details}
            for c in rejected_candidates
        ],
    }

    stages["verification"] = {
        "status": "REAL",
        "verified": [
            {
                "name": c.candidate_name,
                "title": c.candidate_title,
                "status": c.verification_status,
                "score": round(c.score_composite or 0, 3),
                "apollo_eligible": (c.score_composite or 0) >= APOLLO_ELIGIBLE_THRESHOLD,
            }
            for c in verified_candidates
        ],
    }

    stages["person_match_score"] = {
        "status": "REAL",
        "weights": SCORE_WEIGHTS,
        "threshold_apollo": APOLLO_ELIGIBLE_THRESHOLD,
        "threshold_candidate": CANDIDATE_THRESHOLD,
    }

    # ── 7. Apollo Enrichment ──────────────────────────────────────────
    apollo_eligible = [
        c for c in verified_candidates
        if (c.score_composite or 0) >= APOLLO_ELIGIBLE_THRESHOLD
        and c.verification_status != "PERSON_REJECTED"
    ][:max_apollo_enrichments]

    apollo_results = []
    for candidate in apollo_eligible:
        result = enrich_candidate_via_apollo(candidate, company.name, db)
        apollo_results.append({
            "name": candidate.candidate_name,
            "status": result.get("status", "ERROR"),
            "email": result.get("email", "NOT FOUND"),
            "email_confidence": result.get("email_confidence"),
        })

    stages["apollo"] = {
        "status": "REAL" if apollo_results else ("BLOCKED" if not apollo_eligible else "NO_ELIGIBLE_CANDIDATES"),
        "eligible_count": len(apollo_eligible),
        "enriched_count": sum(1 for r in apollo_results if r["status"] == "ENRICHED"),
        "results": apollo_results,
    }

    # ── 8. Email Status ───────────────────────────────────────────────
    email_results = []
    for c in verified_candidates:
        email_results.append({
            "name": c.candidate_name,
            "email": c.apollo_email or "NOT FOUND",
            "email_status": c.email_status,
            "apollo_status": c.apollo_enrichment_status,
        })

    stages["email"] = {
        "status": "REAL",
        "results": email_results,
    }

    # ── 9. Research Brief ─────────────────────────────────────────────
    all_candidates = db.query(DecisionMakerCandidate).filter(
        DecisionMakerCandidate.company_id == company_id,
        DecisionMakerCandidate.candidate_name.isnot(None),
    ).all()

    signal_info = None
    if signal_type:
        from services.signal_discovery_engine import SIGNAL_TAXONOMY
        meta = SIGNAL_TAXONOMY.get(signal_type, {})
        signal_info = {
            "signal_type": signal_type,
            "event_title": meta.get("name", signal_type),
            "calibration_impact": f"Signal-driven calibration requirement for {company.industry}",
            "likely_parameters": ["Dimensional", "Thermal", "Pressure"],
            "price_sensitivity": meta.get("price_sensitivity", "Medium"),
        }

    brief = build_research_brief_with_persons(company, all_candidates, signal_info)

    stages["research_brief"] = {
        "status": "REAL",
        "has_verified_person": brief["actual_person"].get("verification_status") not in ("RESEARCH REQUIRED", None),
        "next_best_action": brief["next_best_action"],
    }

    elapsed = round(time.time() - pipeline_start, 2)

    return {
        "status": "PIPELINE_COMPLETE",
        "company_id": company_id,
        "company_name": company.name,
        "processing_time_seconds": elapsed,
        "stages": stages,
        "research_brief": brief,
        "summary": {
            "personas_inferred": len(personas),
            "queries_generated": len(queries),
            "search_results": search_results["total_results"],
            "candidates_found": len(raw_candidates),
            "candidates_verified": len(verified_candidates),
            "candidates_rejected": len(rejected_candidates),
            "apollo_enriched": sum(1 for r in apollo_results if r["status"] == "ENRICHED"),
            "emails_found": sum(1 for c in verified_candidates if c.apollo_email),
        },
    }


def get_company_decision_makers(
    company_id: int,
    db: Session,
) -> Dict[str, Any]:
    """Get all decision-maker candidates for a company with full status."""
    candidates = (
        db.query(DecisionMakerCandidate)
        .filter(DecisionMakerCandidate.company_id == company_id)
        .order_by(
            DecisionMakerCandidate.score_composite.desc().nullslast(),
            DecisionMakerCandidate.created_at.desc(),
        )
        .all()
    )

    return {
        "company_id": company_id,
        "total_candidates": len(candidates),
        "candidates": [
            {
                "id": c.id,
                "target_persona": c.target_persona,
                "stakeholder_role": c.stakeholder_role,
                "contact_priority": c.contact_priority,
                "priority_reason": c.priority_reason,
                "candidate_name": c.candidate_name,
                "candidate_title": c.candidate_title,
                "candidate_facility": c.candidate_facility,
                "candidate_location": c.candidate_location,
                "verification_status": c.verification_status,
                "verification_confidence": round(c.verification_confidence or 0, 3),
                "score_composite": round(c.score_composite or 0, 3),
                "score_breakdown": {
                    "company_match": round(c.score_company_match or 0, 3),
                    "role_relevance": round(c.score_role_relevance or 0, 3),
                    "facility_match": round(c.score_facility_match or 0, 3),
                    "recency": round(c.score_recency or 0, 3),
                    "evidence_quality": round(c.score_evidence_quality or 0, 3),
                },
                "evidence_sources": c.evidence_sources or [],
                "public_profile_url": c.public_profile_url,
                "apollo_enrichment_status": c.apollo_enrichment_status,
                "apollo_email": c.apollo_email,
                "apollo_email_confidence": c.apollo_email_confidence,
                "email_status": c.email_status,
                "rejection_reason": c.rejection_reason,
                "rejection_details": c.rejection_details,
                "pending_research_tasks": c.pending_research_tasks or [],
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "verified_at": c.verified_at.isoformat() if c.verified_at else None,
                "enriched_at": c.enriched_at.isoformat() if c.enriched_at else None,
            }
            for c in candidates
        ],
        "primary_decision_maker": next(
            (
                {
                    "id": c.id,
                    "target_persona": c.target_persona,
                    "stakeholder_role": c.stakeholder_role,
                    "contact_priority": c.contact_priority,
                    "priority_reason": c.priority_reason,
                    "candidate_name": c.candidate_name,
                    "candidate_title": c.candidate_title,
                    "candidate_facility": c.candidate_facility,
                    "candidate_location": c.candidate_location,
                    "verification_status": c.verification_status,
                    "verification_confidence": round(c.verification_confidence or 0, 3),
                    "score_composite": round(c.score_composite or 0, 3),
                    "composite_score": round(c.score_composite or 0, 3),
                    "score_breakdown": {
                        "company_match": round(c.score_company_match or 0, 3),
                        "role_relevance": round(c.score_role_relevance or 0, 3),
                        "facility_match": round(c.score_facility_match or 0, 3),
                        "recency": round(c.score_recency or 0, 3),
                        "evidence_quality": round(c.score_evidence_quality or 0, 3),
                    },
                    "evidence_sources": c.evidence_sources or [],
                    "evidence_url": (c.evidence_sources[0]["url"] if c.evidence_sources and isinstance(c.evidence_sources, list) and len(c.evidence_sources) > 0 and isinstance(c.evidence_sources[0], dict) and "url" in c.evidence_sources[0] else None),
                    "evidence_snippet": (c.evidence_sources[0]["snippet"] if c.evidence_sources and isinstance(c.evidence_sources, list) and len(c.evidence_sources) > 0 and isinstance(c.evidence_sources[0], dict) and "snippet" in c.evidence_sources[0] else None),
                    "public_profile_url": c.public_profile_url,
                    "apollo_enrichment_status": c.apollo_enrichment_status,
                    "apollo_email": c.apollo_email,
                    "email": c.apollo_email,
                    "email_status": c.email_status,
                    "priority_selection_reason": c.priority_reason,
                }
                for c in candidates
                if c.contact_priority == "PRIMARY" and c.candidate_name
            ),
            None,
        ),
        "secondary_stakeholders": [
            {
                "id": c.id,
                "target_persona": c.target_persona,
                "persona": c.target_persona,
                "stakeholder_role": c.stakeholder_role,
                "contact_priority": c.contact_priority,
                "candidate_name": c.candidate_name,
                "candidate_title": c.candidate_title,
                "candidate_facility": c.candidate_facility,
                "verification_status": c.verification_status,
                "score_composite": round(c.score_composite or 0, 3),
                "composite_score": round(c.score_composite or 0, 3),
                "score_breakdown": {
                    "company_match": round(c.score_company_match or 0, 3),
                    "role_relevance": round(c.score_role_relevance or 0, 3),
                    "facility_match": round(c.score_facility_match or 0, 3),
                    "recency": round(c.score_recency or 0, 3),
                    "evidence_quality": round(c.score_evidence_quality or 0, 3),
                },
                "evidence_url": (c.evidence_sources[0]["url"] if c.evidence_sources and isinstance(c.evidence_sources, list) and len(c.evidence_sources) > 0 and isinstance(c.evidence_sources[0], dict) and "url" in c.evidence_sources[0] else None),
                "evidence_snippet": (c.evidence_sources[0]["snippet"] if c.evidence_sources and isinstance(c.evidence_sources, list) and len(c.evidence_sources) > 0 and isinstance(c.evidence_sources[0], dict) and "snippet" in c.evidence_sources[0] else None),
                "apollo_enrichment_status": c.apollo_enrichment_status,
                "apollo_email": c.apollo_email,
                "email": c.apollo_email,
            }
            for c in candidates
            if c.contact_priority == "SECONDARY" and c.candidate_name
        ],
        "other_candidates": [
            {
                "id": c.id,
                "target_persona": c.target_persona,
                "candidate_name": c.candidate_name,
                "candidate_title": c.candidate_title,
                "verification_status": c.verification_status,
                "score_composite": round(c.score_composite or 0, 3),
                "composite_score": round(c.score_composite or 0, 3),
            }
            for c in candidates
            if c.contact_priority not in ("PRIMARY", "SECONDARY") and c.candidate_name
        ],
        "summary": {
            "persona_inferred": sum(1 for c in candidates if c.verification_status == "PERSONA_INFERRED"),
            "person_candidate": sum(1 for c in candidates if c.verification_status == "PERSON_CANDIDATE"),
            "publicly_verified": sum(1 for c in candidates if c.verification_status == "PERSON_PUBLICLY_VERIFIED"),
            "apollo_enriched": sum(1 for c in candidates if c.verification_status == "APOLLO_ENRICHED"),
            "email_verified": sum(1 for c in candidates if c.verification_status == "EMAIL_VERIFIED"),
            "rejected": sum(1 for c in candidates if c.verification_status == "PERSON_REJECTED"),
        },
    }
