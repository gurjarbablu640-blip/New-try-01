"""Decision-Maker Discovery & Verification Engine.

Implements the complete 8-step pipeline:
1. Persona inference from signal/industry
2. Apollo identity-only person discovery
3. Bright Data profile verification
4. Person candidate extraction and scoring
5. Apollo enrichment (specific verified person)
6. Research brief assembly
7. Full pipeline orchestration

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
from models.facility import Facility
from models.intent_signal import CompanyIntentSignal
from models.person import Person
from models.decision_maker_candidate import (
    DecisionMakerCandidate,
    VERIFICATION_STATUSES,
    REJECTION_REASONS,
    STAKEHOLDER_ROLES,
)
from services.contact_confidence import validate_person_name
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
APOLLO_ELIGIBLE_THRESHOLD = 0.85
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
    max_queries: Optional[int] = None,
    free_only: bool = False,
) -> Dict[str, Any]:
    """Execute real web searches using configured research provider.

    Adheres to Serper per-company budget and evidence-driven early stop.
    Does NOT generate fictional search results.
    """
    all_results = []
    provider_status = research_router.get_provider_status()
    best_provider = research_router.get_best_search_provider()
    search_provider_used = best_provider or "none"
    overall_status = PROVIDER_LIVE if best_provider else PROVIDER_NOT_CONFIGURED

    # Record company researched in Serper budget manager
    try:
        from services.serper_budget_manager import serper_budget_manager
        serper_budget_manager.record_company_researched(1)
    except Exception:
        serper_budget_manager = None

    # Determine per-company query budget
    initial_budget = int(getattr(settings, "SERPER_INITIAL_QUERIES_PER_COMPANY", 4))
    hard_max_budget = int(getattr(settings, "SERPER_MAX_QUERIES_PER_COMPANY", 10))
    effective_max = max_queries if max_queries is not None else hard_max_budget
    limit = min(effective_max, hard_max_budget)

    executed_queries = []
    stopped_early = False

    for idx, q_info in enumerate(queries[:limit]):
        search_result = research_router.search(
            query=q_info["query"],
            num_results=5,
            company_id=company_id,
            db=db,
            free_only=free_only,
        )

        search_provider_used = search_result["provider"]
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
            if search_result["provider_status"] == "SERPER_DAILY_BUDGET_EXHAUSTED":
                break

        # Evidence-Driven Early Stop:
        # After completing the initial tier (or when sufficient evidence exists),
        # check if at least one credible candidate was extracted.
        if (idx + 1) >= min(initial_budget, len(queries)):
            candidates_so_far = extract_person_candidates(all_results, company_name)
            if candidates_so_far:
                company_obj = db.query(Company).filter(Company.id == company_id).first() if db else None
                if company_obj:
                    has_verified = any(
                        verify_person_candidate(c, company_obj).get("composite_score", 0.0) >= 0.75
                        for c in candidates_so_far
                    )
                    if has_verified:
                        stopped_early = True
                        if serper_budget_manager:
                            serper_budget_manager.record_search_stopped_early(1)
                        break

    return {
        "company_id": company_id,
        "company_name": company_name,
        "search_provider": search_provider_used,
        "provider_statuses": provider_status,
        "overall_status": overall_status,
        "queries_executed": executed_queries,
        "total_results": len(all_results),
        "results": all_results,
        "stopped_early": stopped_early,
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


GENERIC_SECTOR_STOP_WORDS = {
    "limited", "ltd", "private", "pvt", "inc", "corp", "corporation",
    "co", "the", "of", "and", "&", "india", "technologies", "technology",
    "tech", "laboratories", "laboratory", "labs", "lab", "energy",
    "industries", "industry", "solutions", "services", "enterprises",
    "enterprise", "group", "holdings", "systems", "products", "international"
}

OTHER_KNOWN_COMPANIES = [
    "dr. reddy", "dr reddy", "dr.reddy", "sun pharma", "cipla", "lupin",
    "aurobindo", "zydus", "torrent pharma", "biocon", "mankind pharma",
    "hetero", "laurus labs", "natco", "alkem", "glenmark", "abbott", "pfizer",
    "lava", "panasonic", "foxconn", "optiemus", "bhagwati", "micromax",
    "samsung", "apple", "xiaomi", "jabil", "flextronics", "pegatron", "wistron",
    "maruti suzuki", "maruti", "tata motors", "mahindra", "hyundai", "honda",
    "toyota", "bajaj auto", "hero motocorp", "bosch", "denso", "motherson",
    "endurance", "subros", "talbros", "kalyani", "bharat forge",
    "siemens", "abb", "schneider", "l&t", "larsen & toubro", "bhel",
    "gamesa", "vestas", "inox wind", "ge vernova", "ge renewable", "enercon",
    "hal", "bel", "isro", "airbus", "boeing", "lockheed", "safran", "collins aerospace"
]


def classify_company_evidence(
    candidate_name: str,
    evidence_text: str,
    target_company_name: str,
    target_domain: str = "",
) -> Dict[str, Any]:
    """Classify the company evidence for a candidate into one of 6 classes:
    - EXACT_CURRENT_COMPANY: Explicitly and currently employed at target company.
    - STRONG_CURRENT_COMPANY: Strong indicators of current role at target company.
    - AMBIGUOUS_COMPANY: Ambiguous mention, multiple companies, or unconfirmed link (requires corroboration).
    - OTHER_COMPANY: Associated with a different company (competitor, client, other firm).
    - FORMER_COMPANY: Past employee (ex-, former, previously at, past:, until).
    - UNKNOWN: Insufficient evidence of any company affiliation.

    Returns:
        company_evidence_status: str
        is_current_employee: bool
        passes_current_employment: bool
        requires_corroboration: bool
        reason: str
    """
    text = (evidence_text or "").strip()
    text_lower = text.lower()
    comp_lower = (target_company_name or "").lower().strip()
    cand_lower = (candidate_name or "").lower().strip()

    if not text or not comp_lower:
        return {
            "company_evidence_status": "UNKNOWN",
            "is_current_employee": False,
            "passes_current_employment": False,
            "requires_corroboration": False,
            "reason": "Empty evidence text or target company name for verification"
        }

    # Extract core distinctive tokens of target company
    raw_tokens = re.findall(r'[a-z0-9]+', comp_lower)
    core_tokens = [t for t in raw_tokens if t not in GENERIC_SECTOR_STOP_WORDS and len(t) >= 3]
    if not core_tokens:
        core_tokens = [t for t in raw_tokens if len(t) >= 3]

    has_target_core = any(ct in text_lower for ct in core_tokens)

    # 1. Check for FORMER_COMPANY
    former_patterns = [
        r'\b(?:ex-|former|previously\s+at|past\s*:|prior\s+to|was\s+at|served\s+as.*?until|left\s+)\b.*?(?:' + '|'.join(re.escape(t) for t in core_tokens) + r')',
        r'(?:' + '|'.join(re.escape(t) for t in core_tokens) + r').*?\b(?:until|till|\d{4}\s*-\s*20(?:1\d|2[0-4])\b)',
        r'\b(?:former|ex-)\s+[a-zA-Z\s,]+?\bat\s+(?:' + '|'.join(re.escape(t) for t in core_tokens) + r')',
    ]
    if any(re.search(pat, text_lower) for pat in former_patterns):
        return {
            "company_evidence_status": "FORMER_COMPANY",
            "is_current_employee": False,
            "passes_current_employment": False,
            "requires_corroboration": False,
            "reason": f"Evidence indicates former or past tenure at {target_company_name}, not current employment"
        }

    # 2. Check for OTHER_COMPANY (Cross-company contamination)
    detected_other = []
    for other in OTHER_KNOWN_COMPANIES:
        if any(ct in other for ct in core_tokens):
            continue
        if re.search(r'\b' + re.escape(other) + r'\b', text_lower):
            detected_other.append(other)

    other_appointment_patterns = [
        r'([a-z0-9&.\'\s]{3,35}?(?:laboratories|pharma|technologies|motors|electronics|energy|industries|ltd|limited))\s+(?:has\s+)?(?:elevated|appointed|promoted|named|hired)\s+([a-z\s]+)',
        r'([a-z\s]+)\s+(?:elevated|appointed|promoted|named|hired)\s+as\s+[a-z\s]+?\s+at\s+([a-z0-9&.\'\s]{3,35})',
    ]
    for pat in other_appointment_patterns:
        m = re.search(pat, text_lower)
        if m:
            comp_part = m.group(1).strip()
            if not any(ct in comp_part for ct in core_tokens):
                return {
                    "company_evidence_status": "OTHER_COMPANY",
                    "is_current_employee": False,
                    "passes_current_employment": False,
                    "requires_corroboration": False,
                    "reason": f"Candidate is explicitly associated with another company ('{comp_part.title()}') rather than target company {target_company_name}"
                }

    # If target core token is completely absent from the text:
    if not has_target_core:
        if detected_other:
            return {
                "company_evidence_status": "OTHER_COMPANY",
                "is_current_employee": False,
                "passes_current_employment": False,
                "requires_corroboration": False,
                "reason": f"Target company '{target_company_name}' absent; snippet refers to other company: {', '.join(detected_other)}"
            }
        return {
            "company_evidence_status": "UNKNOWN",
            "is_current_employee": False,
            "passes_current_employment": False,
            "requires_corroboration": False,
            "reason": f"Target company '{target_company_name}' core name not found in evidence text"
        }

    # Target core token IS present. But does candidate belong to target or other company?
    if detected_other:
        cand_tokens = cand_lower.split()
        surname = cand_tokens[-1] if cand_tokens else ""
        for other in detected_other:
            pat_other = r'\b' + re.escape(other) + r'\b.*?\b' + re.escape(surname) + r'\b'
            pat_other_rev = r'\b' + re.escape(surname) + r'\b.*?\bat\s+' + re.escape(other) + r'\b'
            if (surname and (re.search(pat_other, text_lower) or re.search(pat_other_rev, text_lower))) and not re.search(r'\bat\s+(?:' + '|'.join(re.escape(t) for t in core_tokens) + r')', text_lower):
                return {
                    "company_evidence_status": "OTHER_COMPANY",
                    "is_current_employee": False,
                    "passes_current_employment": False,
                    "requires_corroboration": False,
                    "reason": f"Candidate is associated with other company '{other.title()}' in multi-company context"
                }

        # Multiple companies without clear current attachment -> AMBIGUOUS_COMPANY
        if not re.search(r'\b(?:at|with)\s+(?:' + '|'.join(re.escape(t) for t in core_tokens) + r')\b', text_lower):
            return {
                "company_evidence_status": "AMBIGUOUS_COMPANY",
                "is_current_employee": False,
                "passes_current_employment": False,
                "requires_corroboration": True,
                "reason": f"Multiple companies mentioned ({', '.join(detected_other)} and {target_company_name}); current employer is ambiguous"
            }

    # 3. Check for EXACT_CURRENT_COMPANY vs STRONG_CURRENT_COMPANY
    direct_patterns = [
        r'\b(?:at|working\s+at|currently\s+at)\s+(?:' + '|'.join(re.escape(t) for t in core_tokens) + r')\b',
        r'(?:' + '|'.join(re.escape(t) for t in core_tokens) + r')\b.*?(?:plant\s+head|quality|manager|engineer|lead|head)\b',
        r'\b(?:plant\s+head|quality\s+head|manager|incharge)\s+at\s+(?:' + '|'.join(re.escape(t) for t in core_tokens) + r')\b',
        r'linkedin\s*-\s*[a-z\s]+.*?(?:' + '|'.join(re.escape(t) for t in core_tokens) + r')\b',
    ]
    if any(re.search(pat, text_lower) for pat in direct_patterns):
        if comp_lower in text_lower or (target_domain and target_domain in text_lower):
            return {
                "company_evidence_status": "EXACT_CURRENT_COMPANY",
                "is_current_employee": True,
                "passes_current_employment": True,
                "requires_corroboration": False,
                "reason": f"Directly and currently verified at {target_company_name}"
            }
        return {
            "company_evidence_status": "STRONG_CURRENT_COMPANY",
            "is_current_employee": True,
            "passes_current_employment": True,
            "requires_corroboration": False,
            "reason": f"Strong current role indicators at {target_company_name}"
        }

    return {
        "company_evidence_status": "AMBIGUOUS_COMPANY",
        "is_current_employee": False,
        "passes_current_employment": False,
        "requires_corroboration": True,
        "reason": f"Target company name '{target_company_name}' present, but direct role attachment to candidate is unconfirmed"
    }


def _fuzzy_company_match(text: str, company_name: str) -> float:
    """Calculate fuzzy match score between text and company name."""
    text_lower = text.lower()
    company_lower = company_name.lower()

    # Exact match
    if company_lower in text_lower:
        return 1.0

    # Key word overlap excluding generic sector words
    company_words = set(re.findall(r'[a-z0-9]+', company_lower))
    company_words -= GENERIC_SECTOR_STOP_WORDS
    if not company_words:
        # Fallback to non-stop words
        company_words = set(re.findall(r'[a-z0-9]+', company_lower)) - {"ltd", "pvt", "limited", "private", "inc", "co", "the", "and"}
    if not company_words:
        return 0.0

    matches = sum(1 for w in company_words if w in text_lower)
    return matches / len(company_words)



def _is_non_name(name: str) -> bool:
    """Filter out common false-positive name patterns."""
    name_clean = name.strip()
    val_res = validate_person_name(name_clean)
    if not val_res.get("is_human_name", True) or val_res.get("person_name_validation") == "INVALID_ROLE_TEXT":
        return True

    name_lower = name_clean.lower()
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
    return len(name_clean.split()) > 4 or len(name_clean.split()) < 2


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
    - Composite >= 0.85: PERSON_PUBLICLY_VERIFIED
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


def is_apollo_eligible_lead(
    candidate: Dict[str, Any],
    facility_info: Dict[str, Any],
    trigger_info: Dict[str, Any],
    contact_info: Optional[Dict[str, Any]] = None,
    opportunity_icp_score: float = 0.0,
) -> Tuple[bool, str]:
    """Strict Apollo Enrichment Gatekeeper (Phase 7).

    Guarantees paid Apollo credits are NEVER consumed unless:
    1. Industrial trigger is verified & current.
    2. Facility linkage is DIRECT or corroborated STRONG (never AMBIGUOUS or WEAK).
    3. Person candidate has HIGH confidence, verified current employment, relevant authority,
       and a source-backed facility relationship.
    4. Opportunity ICP score is at least 85.
    5. Free public contact research was performed, and contact remains unverified.
    """
    # 1. Trigger Check
    trigger_valid = trigger_info.get("valid_trigger") if "valid_trigger" in trigger_info else bool(trigger_info.get("trigger") or trigger_info.get("title"))
    if not trigger_valid:
        return False, "Trigger is invalid or unverified"

    # 2. Facility Check (Must be DIRECT or STRONG, NOT AMBIGUOUS/WEAK/UNKNOWN)
    fac_linkage = str(facility_info.get("linkage_confidence") or facility_info.get("trigger_facility_confidence") or "").upper()
    fac_verified = bool(facility_info.get("facility_verified") or facility_info.get("verified"))
    if not fac_verified or fac_linkage not in {"DIRECT", "STRONG"}:
        return False, f"Facility linkage is {fac_linkage or 'UNVERIFIED'}; Apollo credits cannot be spent on ambiguous facility"

    # 3. Person Check
    person_score = float(candidate.get("composite_score") or candidate.get("score") or candidate.get("functional_ownership_score") or 0.0)
    norm_score = person_score / 100.0 if person_score > 1.0 else person_score
    if norm_score < APOLLO_ELIGIBLE_THRESHOLD:
        return False, f"Candidate score {norm_score:.2f} is below Apollo HIGH-confidence threshold ({APOLLO_ELIGIBLE_THRESHOLD:.2f})"

    employment_verified = bool(
        candidate.get("current_company_verified")
        or candidate.get("employment_verified")
        or candidate.get("current_employment_verified")
        or str(candidate.get("current_employment") or "").upper() == "VERIFIED"
    )
    if not employment_verified:
        return False, "Candidate current employment is not verified"

    person_facility = str(candidate.get("facility_relationship") or candidate.get("person_facility_relationship") or "").upper()
    if person_facility not in {"DIRECT", "STRONG", "FACILITY_OWNER", "FACILITY_FUNCTION_OWNER", "GROUP_FUNCTION_OWNER"}:
        return False, f"Candidate person-to-facility relationship is {person_facility or 'UNKNOWN'}"

    authority = str(candidate.get("authority_class") or candidate.get("authority_classification") or "").upper()
    if authority not in {
        "DIRECT_CALIBRATION_OWNER",
        "METROLOGY_OWNER",
        "STRONG_PLANT_QUALITY_OWNER",
        "FACILITY_OWNER",
        "GROUP_FUNCTION_OWNER",
    }:
        return False, f"Candidate authority is {authority or 'UNKNOWN'}; responsible-person ownership is not verified"

    if float(opportunity_icp_score or 0) < 85.0:
        return False, f"Opportunity ICP score {float(opportunity_icp_score or 0):.1f} is below 85.0"

    # 4. Contact Check (Free research exhausted)
    if contact_info:
        if contact_info.get("mailbox_verified") is True:
            return False, "Person-specific contact is already verified; Apollo enrichment not required"
        if contact_info.get("evidence_level") == "VERIFIED_PERSON_SPECIFIC":
            return False, "Authoritative person-specific email already exists"

    return True, "Lead satisfies all 5 Apollo pre-requisites (valid trigger, direct/strong facility, verified person, unverified contact)"



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

    if candidate_record.verification_status != "CONTACT_ENRICHMENT_READY":
        return {
            "status": "SKIPPED",
            "reason": (
                f"Candidate status is {candidate_record.verification_status}; "
                "CONTACT_ENRICHMENT_READY is required before Apollo"
            ),
        }

    if candidate_record.verification_confidence < APOLLO_ELIGIBLE_THRESHOLD:
        return {
            "status": "SKIPPED",
            "reason": f"Confidence {candidate_record.verification_confidence:.2f} below Apollo threshold {APOLLO_ELIGIBLE_THRESHOLD}",
        }

    # Phase 8: Apollo Request Idempotency & Dedup Protection
    if candidate_record.apollo_enrichment_status in ("ENRICHED", "NO_RESULT") and candidate_record.enriched_at:
        age_hours = (datetime.utcnow() - candidate_record.enriched_at).total_seconds() / 3600.0
        if age_hours < 720.0:  # 30-day protection window
            return {
                "status": "SKIPPED_DEDUPLICATED",
                "reason": f"Candidate already enriched {age_hours:.1f}h ago (status: {candidate_record.apollo_enrichment_status}); credit protected by dedup window.",
                "email": candidate_record.apollo_email,
                "email_confidence": candidate_record.apollo_email_confidence,
                "phone": candidate_record.apollo_phone,
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

    # Phase 7: Strict Post-Enrichment Gating (Apollo NEVER automatically grants production send)
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


def reuse_crm_email(candidate, db):
    """Avoid enrichment when the same company's named CRM contact has a usable email."""
    if candidate.apollo_email or candidate.verification_status == "PERSON_REJECTED":
        return
    contacts = db.query(Person).filter(Person.company_id == candidate.company_id).all()
    target = " ".join((candidate.candidate_name or "").lower().split())
    for person in contacts:
        if " ".join((person.full_name or "").lower().split()) != target or not target:
            continue
        email = person.email or ""
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            continue
        if str(person.email_verification_status or "").lower() not in ("verified", "valid", "email_verified", "deliverable"):
            continue
        source = str(person.discovery_source or "").lower()
        if "mock" in source or "mock" in str(person.evidence_json or "").lower():
            continue
        if not person.evidence_json and source != "manual":
            continue
        candidate.apollo_email = email
        candidate.apollo_email_confidence = "CRM_REUSED"
        candidate.email_status = "EMAIL_FOUND"
        return


def merge_candidate_evidence(existing, discovered):
    """Reuse a candidate row, retaining rejections and accumulated evidence."""
    evidence = list(existing.evidence_sources or [])
    seen = {(item.get("url"), item.get("snippet")) for item in evidence}
    for item in discovered.evidence_sources or []:
        key = (item.get("url"), item.get("snippet"))
        if key not in seen:
            evidence.append(item)
            seen.add(key)
    existing.evidence_sources = evidence[-30:]
    if existing.verification_status == "PERSON_REJECTED":
        return existing
    # Fresh contradictory evidence can reject a previously accepted machine result.
    if discovered.verification_status == "PERSON_REJECTED":
        existing.verification_status = discovered.verification_status
        existing.rejection_reason = discovered.rejection_reason
        existing.rejection_details = discovered.rejection_details
    elif existing.verification_status not in ("APOLLO_ENRICHED", "EMAIL_VERIFIED"):
        existing.verification_status = discovered.verification_status
    for field in ("verification_confidence", "verification_notes", "score_composite",
                  "score_company_match", "score_role_relevance", "score_facility_match",
                  "score_recency", "score_evidence_quality", "pending_research_tasks"):
        setattr(existing, field, getattr(discovered, field))
    return existing


def run_full_discovery_pipeline(
    company_id: int,
    db: Session,
    signal_type: Optional[str] = None,
    max_apollo_enrichments: int = 3,
    max_queries: int = 6,
    free_only: bool = False,
    additional_evidence: Optional[List[Dict[str, Any]]] = None,
    before_apollo=None,
) -> Dict[str, Any]:
    """Orchestrate the complete decision-maker discovery pipeline.

    Steps:
    1. Company lookup
    2. Persona inference
    3. Apollo identity-only people discovery
    4. Bright Data profile verification and deterministic scoring
    5. Apollo enrichment after strict eligibility gates
    6. Research brief assembly

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
    facility_record = (
        db.query(Facility)
        .filter(Facility.company_id == company_id)
        .order_by(Facility.id.asc())
        .first()
    )
    target_facility = facility_record.name if facility_record else ""
    target_city = (facility_record.city if facility_record else None) or company.city or ""
    target_state = (facility_record.state if facility_record else None) or company.state or ""

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
    from services.apollo_adapter import APOLLO_PERSON_ROLE_FAMILIES
    from services.person_intelligence_service import (
        discover_people_with_apollo,
        verify_apollo_candidates_with_brightdata,
    )

    stages["search_queries"] = {
        "status": "REAL",
        "query_count": 1,
        "strategy": "APOLLO_IDENTITY_ONLY_PEOPLE_SEARCH",
        "role_families": APOLLO_PERSON_ROLE_FAMILIES,
    }

    discovery = discover_people_with_apollo(
        company_name=company.name,
        facility_name=target_facility,
        city=target_city,
        state=target_state,
        role_families=APOLLO_PERSON_ROLE_FAMILIES,
        max_candidates=5,
    )
    verification = verify_apollo_candidates_with_brightdata(
        discovery.get("candidates") or [],
        company_name=company.name,
        facility_name=target_facility,
        city=target_city,
        state=target_state,
        company_domain=company.domain or "",
        max_attempts=3,
    )
    raw_candidates = verification.get("candidates") or []

    # ── 4. Web/Public Research ────────────────────────────────────────
    public_person_evidence = [
        {
            "title": f"{candidate.get('name', '')} - {candidate.get('title', '')}",
            "snippet": candidate.get("evidence_snippet", ""),
            "url": candidate.get("linkedin_url", ""),
            "source": "BRIGHTDATA_LINKEDIN_PROFILE",
        }
        for candidate in raw_candidates
    ]
    search_results = {
        "search_provider": "apollo",
        "overall_status": verification.get("status", "ERROR"),
        "provider_statuses": {
            "apollo": discovery.get("status", "ERROR"),
            "brightdata_profile": verification.get("status", "ERROR"),
        },
        "queries_executed": [{"strategy": "apollo_identity_only_people_search"}],
        "total_results": len(raw_candidates),
        "results": public_person_evidence + list(additional_evidence or []),
    }
    stages["person_search"] = {
        "status": verification.get("status", "ERROR"),
        "provider": "apollo_then_brightdata",
        "people_search": discovery.get("status", "ERROR"),
        "profile_lookup": verification.get("status", "NOT_CALLED"),
        "total_results": search_results["total_results"],
        "queries_executed": int(discovery.get("telemetry", {}).get("APOLLO_SEARCH_CALLS", 0)),
        "apollo_telemetry": discovery.get("telemetry", {}),
        "brightdata_telemetry": verification.get("telemetry", {}),
        "verification_attempts": verification.get("attempts", []),
        "bright_dataset_search_role": "FALLBACK",
    }

    # ── 5. Person Candidate Extraction ────────────────────────────────
    stages["candidates"] = {
        "status": "REAL" if raw_candidates else "NO_CANDIDATES_FOUND",
        "count": len(raw_candidates),
    }

    # ── 6. Verification & Scoring ─────────────────────────────────────
    verified_candidates = []
    rejected_candidates = []
    candidate_evidence: Dict[Tuple[str, str], Dict[str, Any]] = {}

    for raw_c in raw_candidates:
        person_score = float(raw_c.get("person_score") or 0.0)
        normalized_score = person_score / 100.0
        verification_status = str(raw_c.get("verification_status") or "PERSON_CANDIDATE")
        current_employment = str(raw_c.get("current_employment") or "UNKNOWN")
        facility_relationship = str(raw_c.get("facility_relationship") or "UNKNOWN")
        function_ownership = str(raw_c.get("function_ownership") or "UNKNOWN")
        if current_employment == "CONTRADICTED":
            rejection_reason = "outdated_employment"
            rejection_details = "Structured LinkedIn experience identifies a different current employer"
        elif facility_relationship in {"OTHER_FACILITY_OWNER", "FACILITY_CONTRADICTED"}:
            rejection_reason = "wrong_facility"
            rejection_details = "Structured LinkedIn experience contradicts the target facility"
        else:
            rejection_reason = None
            rejection_details = None
        title_key = str(raw_c.get("title") or "").casefold()
        matching_persona = (
            "Quality / Metrology"
            if any(term in title_key for term in ("quality", "qa", "qc", "metrology", "calibration"))
            else "Maintenance / Plant"
        )
        role_score = 1.0 if function_ownership not in {"UNKNOWN", "COMPANY_ONLY", "JUNIOR_IC"} else 0.0
        facility_score = {
            "FACILITY_OWNER": 1.0,
            "FACILITY_FUNCTION_OWNER": 1.0,
            "GROUP_FUNCTION_OWNER": 0.75,
            "FUNCTIONALLY_RELEVANT": 0.5,
            "COMPANY_ONLY": 0.2,
        }.get(facility_relationship, 0.0)
        employment_score = {"VERIFIED": 1.0, "PROBABLE": 0.6, "UNKNOWN": 0.2}.get(current_employment, 0.0)

        # Create or update DecisionMakerCandidate record
        dmc = DecisionMakerCandidate(
            company_id=company_id,
            target_persona=matching_persona,
            target_titles=PERSONA_TITLE_MAP.get(matching_persona, {}).get("titles", []),
            stakeholder_role=PERSONA_TITLE_MAP.get(matching_persona, {}).get("stakeholder_role", "Evaluator"),
            candidate_name=raw_c["name"],
            candidate_title=raw_c.get("title"),
            candidate_company_match=current_employment in {"VERIFIED", "PROBABLE"},
            candidate_facility=(
                target_facility
                if facility_relationship in {"FACILITY_OWNER", "FACILITY_FUNCTION_OWNER"}
                else ""
            ),
            candidate_location=raw_c.get("location", ""),
            evidence_sources=[{
                "source": "BRIGHTDATA_LINKEDIN_PROFILE",
                "url": raw_c.get("linkedin_url", ""),
                "snippet": raw_c.get("evidence_snippet", ""),
                "retrieved_at": raw_c.get("retrieved_at") or datetime.utcnow().isoformat(),
                "confidence": raw_c.get("person_confidence", "LOW"),
                "evidence_type": "LINKEDIN_STRUCTURED_EVIDENCE",
                "field_provenance": raw_c.get("field_provenance", {}),
                "evidence_packet": raw_c.get("evidence_packet", {}),
            }],
            public_profile_url=raw_c.get("linkedin_url"),
            public_profile_evidence=raw_c.get("evidence_snippet", ""),
            search_queries_used=["APOLLO_IDENTITY_ONLY_SEARCH", "BRIGHTDATA_PROFILE_LOOKUP"],
            verification_status=verification_status,
            verification_confidence=normalized_score,
            verification_notes=f"Deterministic person score: {person_score:.1f}/100",
            rejection_reason=rejection_reason,
            rejection_details=rejection_details,
            score_company_match=employment_score,
            score_role_relevance=role_score,
            score_facility_match=facility_score,
            score_recency=employment_score,
            score_evidence_quality=(
                1.0
                if "LINKEDIN_PROFILE" in (raw_c.get("evidence_packet", {}).get("source_types") or [])
                else 0.8
            ),
            score_composite=normalized_score,
            pending_research_tasks=[] if verification_status == "PERSON_PUBLICLY_VERIFIED" else [{
                "task": "Obtain current employment or target-facility evidence",
                "reason": f"Current employment {current_employment}; facility relationship {facility_relationship}",
                "priority": "HIGH",
                "status": "PENDING",
            }],
        )

        if verification_status == "PERSON_PUBLICLY_VERIFIED":
            dmc.verified_at = datetime.utcnow()
            if not verified_candidates:
                dmc.contact_priority = "PRIMARY"
                dmc.priority_reason = (
                    f"Selected as PRIMARY decision-maker: Highest deterministic person score ({person_score:.1f}) "
                    f"for target {matching_persona} function at {company.name}."
                )
            elif len(verified_candidates) <= 2:
                dmc.contact_priority = "SECONDARY"
                dmc.priority_reason = (
                    f"Secondary stakeholder ({matching_persona}) with deterministic person score ({person_score:.1f})."
                )
            else:
                dmc.contact_priority = "OTHER"
                dmc.priority_reason = f"Additional stakeholder ({matching_persona}) identified at {company.name}."
        elif verification_status == "PERSON_CANDIDATE":
            dmc.contact_priority = "OTHER"
            dmc.priority_reason = "Unverified candidate hypothesis — requires additional evidence before engagement."

        existing_candidate = db.query(DecisionMakerCandidate).filter(
            DecisionMakerCandidate.company_id == company_id,
            DecisionMakerCandidate.candidate_name == dmc.candidate_name,
            DecisionMakerCandidate.candidate_title == dmc.candidate_title,
        ).first()
        if existing_candidate:
            dmc = merge_candidate_evidence(existing_candidate, dmc)
        else:
            db.add(dmc)
        db.flush()
        candidate_evidence[(dmc.candidate_name.casefold(), (dmc.candidate_title or "").casefold())] = raw_c

        if dmc.verification_status == "PERSON_REJECTED":
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

    stages["person_match_score"] = {
        "status": "REAL",
        "method": "EXISTING_DETERMINISTIC_PERSON_GATES",
        "threshold_apollo": APOLLO_ELIGIBLE_THRESHOLD * 100,
    }

    # ── 7. Apollo Enrichment ──────────────────────────────────────────
    from services.contact_confidence import enrich_free_candidate
    known_contacts = []
    for person in db.query(Person).filter(Person.company_id == company_id).all():
        for item in person.evidence_json or []:
            if isinstance(item, dict) and item.get('type') == 'email_assessment' and item.get('status') in ('VERIFIED', 'PUBLICLY_FOUND'):
                known_contacts.append({'name': person.full_name, 'email': person.email,
                                       'status': item['status'], 'source': item.get('evidence')})
    for candidate in verified_candidates:
        reuse_crm_email(candidate, db)
        enrich_free_candidate(candidate, company, search_results['results'], known_contacts)
    db.commit()

    active_signal = (
        db.query(CompanyIntentSignal)
        .filter(
            CompanyIntentSignal.company_id == company_id,
            CompanyIntentSignal.is_active == 1,
        )
        .order_by(CompanyIntentSignal.detected_at.desc())
        .first()
    )
    trigger_text = " ".join(
        part
        for part in (
            getattr(active_signal, "source_snippet", "") if active_signal else "",
            getattr(active_signal, "opportunity_note", "") if active_signal else "",
        )
        if part
    ).casefold()
    direct_facility_terms = []
    for facility_value in (
        target_facility,
        facility_record.plant_code if facility_record else "",
        facility_record.industrial_estate if facility_record else "",
    ):
        if not facility_value:
            continue
        direct_facility_terms.extend(
            token
            for token in re.findall(r"[a-z0-9]+", facility_value.casefold())
            if len(token) >= 3 and token not in {"plant", "unit", "facility", "factory"}
        )
    if any(term in trigger_text for term in direct_facility_terms):
        trigger_facility_confidence = "DIRECT"
    elif target_city and target_city.casefold() in trigger_text:
        trigger_facility_confidence = "STRONG"
    else:
        trigger_facility_confidence = "UNVERIFIED"
    facility_info = {
        "facility_verified": bool(
            facility_record
            and (facility_record.name or facility_record.plant_code or facility_record.address)
        ),
        "linkage_confidence": trigger_facility_confidence,
    }
    trigger_info = {
        "valid_trigger": bool(
            active_signal
            and active_signal.source_url
            and active_signal.source_snippet
            and (not active_signal.expires_at or active_signal.expires_at >= datetime.utcnow())
        )
    }
    apollo_gate_results: Dict[int, Tuple[bool, str]] = {}
    apollo_eligible = []
    for candidate in verified_candidates:
        raw = candidate_evidence.get(
            (candidate.candidate_name.casefold(), (candidate.candidate_title or "").casefold()),
            {},
        )
        eligible, reason = is_apollo_eligible_lead(
            {
                "composite_score": float(raw.get("person_score") or 0) / 100.0,
                "current_employment": raw.get("current_employment"),
                "facility_relationship": raw.get("facility_relationship"),
                "authority_class": raw.get("authority_class"),
            },
            facility_info,
            trigger_info,
            {"evidence_level": "NOT_FOUND"},
            opportunity_icp_score=float(company.icp_score or 0),
        )
        apollo_gate_results[candidate.id] = (eligible, reason)
        raw["ready_for_contact_enrichment"] = eligible
        if eligible and not candidate.apollo_email:
            candidate.verification_status = "CONTACT_ENRICHMENT_READY"
            apollo_eligible.append(candidate)
    db.commit()
    apollo_eligible = apollo_eligible[:max_apollo_enrichments]

    stages["verification"] = {
        "status": "REAL",
        "verified": [
            {
                "name": candidate.candidate_name,
                "title": candidate.candidate_title,
                "status": candidate.verification_status,
                "score": round((candidate.score_composite or 0) * 100, 1),
                "apollo_eligible": apollo_gate_results.get(candidate.id, (False, ""))[0],
                "apollo_gate_reason": apollo_gate_results.get(candidate.id, (False, "Not evaluated"))[1],
            }
            for candidate in verified_candidates
        ],
    }

    from services.person_intelligence_service import run_contact_fallback_ladder

    apollo_results = []
    ladder_candidates = []
    for candidate in verified_candidates:
        raw = candidate_evidence.get(
            (candidate.candidate_name.casefold(), (candidate.candidate_title or "").casefold()),
            {},
        )
        raw["_candidate_record"] = candidate
        ladder_candidates.append(raw)

    def enrich_ladder_candidate(raw_candidate):
        candidate_record = raw_candidate["_candidate_record"]
        if before_apollo is not None and not before_apollo():
            return {"status": "BLOCKED", "email": None, "phone": None}
        result = enrich_candidate_via_apollo(candidate_record, company.name, db)
        apollo_results.append({
            "name": candidate_record.candidate_name,
            "status": result.get("status", "ERROR"),
            "email": result.get("email", "NOT FOUND"),
            "email_confidence": result.get("email_confidence"),
        })
        if not result.get("email") and not result.get("phone"):
            candidate_record.verification_status = "PERSON_VERIFIED_CONTACT_MISSING"
        return result

    contact_ladder = run_contact_fallback_ladder(
        ladder_candidates,
        enrich_fn=enrich_ladder_candidate,
        max_attempts=min(max_apollo_enrichments, 3),
    )
    db.commit()

    stages["apollo"] = {
        "status": contact_ladder["status"],
        "eligible_count": len(apollo_eligible),
        "enriched_count": sum(1 for r in apollo_results if r["status"] == "ENRICHED"),
        "results": apollo_results,
        "attempts": contact_ladder["attempts"],
        "max_candidate_attempts": 3,
    }

    # ── 8. Email Status ───────────────────────────────────────────────
    email_results = []
    for c in verified_candidates:
        assessment = enrich_free_candidate(c, company, search_results['results'], known_contacts)
        email_results.append({
            "name": c.candidate_name,
            "email": c.apollo_email or "NOT FOUND",
            "email_status": c.email_status,
            "apollo_status": c.apollo_enrichment_status,
            "assessment": assessment,
        })
    db.commit()
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
        "public_evidence": search_results["results"],
        "candidates": [
            {
                **candidate_evidence.get(
                    (candidate.candidate_name.casefold(), (candidate.candidate_title or "").casefold()),
                    {},
                ),
                "id": candidate.id,
                "verification_status": candidate.verification_status,
            }
            for candidate in verified_candidates
        ],
        "candidate_ids": [c.id for c in verified_candidates + rejected_candidates],
        "summary": {
            "personas_inferred": len(personas),
            "queries_generated": 1,
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


# ═════════════════════════════════════════════════════════════════════════
# STEP 9: Functional Calibration Ownership Hierarchy & Candidate Ranking
# ═════════════════════════════════════════════════════════════════════════

FUNCTIONAL_HIERARCHY_LEVELS = [
    "METROLOGY_CALIBRATION_OWNER",        # 1. Metrology / Calibration owner
    "PLANT_QUALITY_HEAD",                 # 2. Plant Quality Head / Quality Manager / QA-QC Head
    "INSTRUMENTATION_VALIDATION_OWNER",   # 3. Instrumentation / Validation / Testing owner
    "MAINTENANCE_HEAD",                   # 4. Maintenance Head where calibration ownership is credible
    "PLANT_OPERATIONS_HEAD",              # 5. Plant Operations / Plant Head / Works Manager
    "PROCUREMENT_VENDOR_DEV",             # 6. Procurement / Vendor Development
    "GENERAL_CORPORATE_EXECUTIVE",        # 7. Senior general corporate / non-functional
]


def classify_functional_role(title: str, snippet: str = "") -> Tuple[str, str, int]:
    """Classify person into functional hierarchy level for calibration procurement.

    Preferred hierarchy:
    1. Metrology / Calibration owner (25 pts)
    2. Plant Quality Head / Quality Manager / QA-QC Head (22 pts)
    3. Instrumentation / Validation / Testing owner (20 pts)
    4. Maintenance Head where calibration ownership is credible (16 pts)
    5. Plant Operations / Plant Head only when evidence shows ownership or no stronger specialist exists (12 pts)
    6. Procurement / Vendor Development only when appropriate for supplier onboarding (8 pts)
    7. General Corporate Executive (4 pts)

    Returns: (function_name, hierarchy_level, base_duties_score_max_25)
    """
    t_lower = (title or "").lower()
    s_lower = (snippet or "").lower()

    # 1. Metrology / Calibration owner
    if any(k in t_lower for k in ["metrology", "calibration", "standards room", "dimensional lab", "standards lab"]):
        return ("Metrology / Calibration", "METROLOGY_CALIBRATION_OWNER", 25)
    if "calibration" in s_lower and any(k in t_lower for k in ["quality", "instrumentation", "lab"]):
        return ("Metrology / Calibration", "METROLOGY_CALIBRATION_OWNER", 25)

    # 2. Plant Quality Head / Quality Manager / QA-QC Head
    if any(k in t_lower for k in [
        "plant quality", "quality head", "head quality", "head of quality",
        "qa head", "qc head", "quality manager", "qa manager", "qc manager",
        "manager quality", "dgm quality", "agm quality", "gm quality",
        "vp quality", "head qa", "head - quality", "head- quality"
    ]):
        return ("Plant Quality / QA-QC", "PLANT_QUALITY_HEAD", 22)
    if "quality" in t_lower and any(k in t_lower for k in ["assurance", "control", "qms", "iatf", "cqo", "inspection"]):
        return ("Plant Quality / QA-QC", "PLANT_QUALITY_HEAD", 22)

    # 3. Instrumentation / Validation / Testing owner
    if any(k in t_lower for k in ["instrumentation", "validation", "testing", "test lab", "cqa", "analytical"]):
        return ("Instrumentation / Testing", "INSTRUMENTATION_VALIDATION_OWNER", 20)

    # 4. Maintenance Head where calibration ownership is credible
    if any(k in t_lower for k in [
        "maintenance head", "head maintenance", "maintenance manager",
        "chief engineer", "plant engineer", "engineering manager", "head engineering"
    ]):
        return ("Maintenance / Engineering", "MAINTENANCE_HEAD", 16)

    # 5. Plant Operations / Plant Head
    if any(k in t_lower for k in [
        "plant head", "works manager", "factory manager", "operations head",
        "head operations", "avp operations", "vp operations", "gm operations",
        "unit head", "general manager operations", "production head", "head of plant"
    ]):
        return ("Plant Operations", "PLANT_OPERATIONS_HEAD", 12)

    # 6. Procurement / Vendor Development
    if any(k in t_lower for k in ["purchase", "procurement", "vendor development", "sourcing", "supply chain"]):
        return ("Procurement / Commercial", "PROCUREMENT_VENDOR_DEV", 8)

    # 7. Generic corporate
    return ("Corporate Executive", "GENERAL_CORPORATE_EXECUTIVE", 4)


def score_candidate_functional_ownership(
    candidate: Dict[str, Any],
    facility_info: Dict[str, Any],
    trigger_info: Dict[str, Any],
    target_company_name: str = "",
) -> Dict[str, Any]:
    """Calculate the 100-point Functional Calibration Ownership Score for a candidate.

    Scoring weights (Evidence-Based):
    1. Current company verified: 20 pts
    2. Exact facility/location: 20 pts
    3. Actual duties/responsibilities (functional hierarchy): 25 pts
    4. Trigger/function alignment: 15 pts
    5. Calibration/metrology ownership evidence: 10 pts
    6. Seniority/authority: 5 pts
    7. Evidence recency/quality: 5 pts
    Total: 100 pts
    """
    scores: Dict[str, float] = {}
    title = candidate.get("candidate_title") or candidate.get("title") or ""
    snippet = candidate.get("evidence_snippet") or candidate.get("snippet") or ""
    name = candidate.get("candidate_name") or candidate.get("name") or ""
    cand_loc = (candidate.get("candidate_location") or candidate.get("location") or "").lower()
    t_lower = title.lower()
    s_lower = snippet.lower()
    combined = f"{t_lower} {s_lower}"

    # 1. Current Company Verified (max 20) with cross-company contamination check
    target_comp = target_company_name or candidate.get("target_company_name") or candidate.get("company_name") or ""
    if target_comp:
        comp_eval = classify_company_evidence(name, combined, target_comp)
        comp_status = comp_eval["company_evidence_status"]
        if comp_status == "EXACT_CURRENT_COMPANY":
            scores["current_company_verified"] = 20.0
            is_curr_emp = True
        elif comp_status == "STRONG_CURRENT_COMPANY":
            scores["current_company_verified"] = 18.0
            is_curr_emp = True
        elif comp_status == "AMBIGUOUS_COMPANY":
            scores["current_company_verified"] = 5.0
            is_curr_emp = False
        else:  # OTHER_COMPANY, FORMER_COMPANY, UNKNOWN
            scores["current_company_verified"] = 0.0
            is_curr_emp = False
        comp_reason = comp_eval["reason"]
    else:
        comp_match = candidate.get("candidate_company_match", False)
        if comp_match or candidate.get("current_company_verified", False):
            scores["current_company_verified"] = 20.0
            comp_status = "STRONG_CURRENT_COMPANY"
            is_curr_emp = True
            comp_reason = "Company match inferred from candidate context"
        else:
            scores["current_company_verified"] = 0.0
            comp_status = "UNKNOWN"
            is_curr_emp = False
            comp_reason = "Unverified company association"

    # 2. Exact Facility / Location Link (max 20)
    target_city = (facility_info.get("city") or "").lower()
    if target_city and target_city != "not_found" and (target_city in cand_loc or target_city in combined):
        scores["exact_facility_location"] = 20.0
        facility_link = f"DIRECT ({target_city.title()} verified)"
    elif any(state_term in cand_loc for state_term in ["haryana", "uttar pradesh", "andhra pradesh", "karnataka", "telangana", "gujarat", "maharashtra"]):
        scores["exact_facility_location"] = 12.0
        facility_link = "REGIONAL (State match)"
    elif any(k in t_lower for k in ["plant", "works", "unit", "site"]):
        scores["exact_facility_location"] = 10.0
        facility_link = "FACILITY_LEVEL (City unconfirmed)"
    elif any(k in t_lower for k in ["corporate", "group", "vp", "director"]):
        scores["exact_facility_location"] = 8.0
        facility_link = "GROUP_WIDE (Multi-plant oversight)"
    else:
        scores["exact_facility_location"] = 5.0
        facility_link = "COMPANY_WIDE (Unknown location)"

    # 3. Actual Duties / Responsibilities - Functional Hierarchy (max 25)
    func_name, hier_class, base_duty_score = classify_functional_role(title, snippet)
    scores["actual_duties_responsibilities"] = float(base_duty_score)

    # 4. Trigger / Function Alignment (max 15)
    trigger_title = (trigger_info.get("title") or "").lower()
    if any(k in trigger_title for k in ["plant", "capex", "commissioning", "facility", "expansion", "capacity"]):
        if hier_class in {"PLANT_QUALITY_HEAD", "METROLOGY_CALIBRATION_OWNER"}:
            scores["trigger_function_alignment"] = 15.0
        elif hier_class in {"INSTRUMENTATION_VALIDATION_OWNER", "MAINTENANCE_HEAD"}:
            scores["trigger_function_alignment"] = 14.0
        elif hier_class == "PLANT_OPERATIONS_HEAD":
            scores["trigger_function_alignment"] = 10.0
        else:
            scores["trigger_function_alignment"] = 5.0
    else:
        if hier_class in {"METROLOGY_CALIBRATION_OWNER", "PLANT_QUALITY_HEAD"}:
            scores["trigger_function_alignment"] = 12.0
        else:
            scores["trigger_function_alignment"] = 8.0

    # 5. Calibration / Metrology Ownership Evidence (max 10)
    has_explicit_cal = any(k in combined for k in ["metrology", "calibration", "cqc", "standards room", "dimensional", "iso 17025", "cmm", "gauge", "master equipment"])
    has_qa_testing = any(k in combined for k in ["quality assurance", "qa/qc", "testing lab", "validation", "inspection", "iatf 16949", "audit"])
    if has_explicit_cal:
        scores["calibration_metrology_ownership"] = 10.0
        cal_evidence = "EXPLICIT (Metrology/calibration scope documented)"
    elif has_qa_testing:
        scores["calibration_metrology_ownership"] = 7.0
        cal_evidence = "HIGH (QA/QC inspection & measurement equipment oversight)"
    elif hier_class in {"MAINTENANCE_HEAD", "INSTRUMENTATION_VALIDATION_OWNER"}:
        scores["calibration_metrology_ownership"] = 5.0
        cal_evidence = "MODERATE (Plant instrumentation/maintenance responsibility)"
    elif hier_class == "PLANT_OPERATIONS_HEAD":
        scores["calibration_metrology_ownership"] = 3.0
        cal_evidence = "INDIRECT (Overall plant operational sign-off)"
    else:
        scores["calibration_metrology_ownership"] = 1.0
        cal_evidence = "MINIMAL (Commercial/procurement only)"

    # 6. Seniority / Authority (max 5)
    if any(k in t_lower for k in ["head", "director", "vp", "chief", "avp", "gm", "general manager", "dgm", "agm"]):
        scores["seniority_authority"] = 5.0
        authority = "HIGH (Budget & vendor approval authority)"
    elif any(k in t_lower for k in ["manager", "lead", "in-charge", "incharge"]):
        scores["seniority_authority"] = 4.0
        authority = "OPERATIONAL (Direct calibration owner/manager)"
    elif any(k in t_lower for k in ["senior engineer", "specialist", "executive"]):
        scores["seniority_authority"] = 3.0
        authority = "TECHNICAL (Evaluator / user level)"
    else:
        scores["seniority_authority"] = 2.0
        authority = "GENERAL"

    # 7. Evidence Recency & Quality (max 5)
    recency_str = candidate.get("recency") or "2025-2026"
    ev_url = candidate.get("evidence_url") or candidate.get("source_url") or ""
    if "linkedin.com/in/" in ev_url or "official" in ev_url:
        scores["evidence_recency_quality"] = 5.0
    elif any(yr in snippet for yr in ["2026", "2025"]):
        scores["evidence_recency_quality"] = 5.0
    elif "2024" in snippet:
        scores["evidence_recency_quality"] = 4.0
    else:
        scores["evidence_recency_quality"] = 3.0

    total_score = round(sum(scores.values()), 1)

    return {
        "candidate_name": name,
        "candidate_title": title,
        "function": func_name,
        "hierarchy_class": hier_class,
        "functional_ownership_score": total_score,
        "score_breakdown": scores,
        "current_company_verified": is_curr_emp,
        "company_evidence_status": comp_status,
        "company_verification_reason": comp_reason,
        "facility_link": facility_link,
        "calibration_metrology_ownership_evidence": cal_evidence,
        "quality_instrumentation_responsibility": "DIRECT" if hier_class in {"METROLOGY_CALIBRATION_OWNER", "PLANT_QUALITY_HEAD", "INSTRUMENTATION_VALIDATION_OWNER"} else "SUPERVISORY" if hier_class in {"MAINTENANCE_HEAD", "PLANT_OPERATIONS_HEAD"} else "COMMERCIAL",
        "trigger_relevance": "HIGH" if scores["trigger_function_alignment"] >= 14.0 else "MEDIUM" if scores["trigger_function_alignment"] >= 10.0 else "LOW",
        "authority": authority,
        "source_url": ev_url,
        "evidence_snippet": snippet[:250],
        "recency": recency_str,
        "contact_confidence": candidate.get("contact_confidence", "PROBABLE"),
    }


def rank_calibration_candidates(
    candidates: List[Dict[str, Any]],
    facility_info: Dict[str, Any],
    trigger_info: Dict[str, Any],
    target_company_name: str = "",
) -> List[Dict[str, Any]]:
    """Rank all candidates using functional calibration ownership scoring.

    Returns candidates sorted descending by current company verification first,
    then by functional ownership score.
    """
    scored = [
        score_candidate_functional_ownership(cand, facility_info, trigger_info, target_company_name=target_company_name)
        for cand in candidates
    ]
    # Current company verified must win over unverified/other/former companies
    scored.sort(key=lambda x: (x["current_company_verified"], x["functional_ownership_score"]), reverse=True)
    return scored

