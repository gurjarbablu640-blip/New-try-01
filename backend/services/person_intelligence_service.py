"""Person Intelligence & Decision-Maker Qualification Engine.

Implements the verified Salesoorja Decision-Maker Intelligence Architecture:
QUALIFIED TRIGGER -> EXACT FACILITY -> FUNCTION MAP -> PERSON CANDIDATE DISCOVERY
-> CURRENT EMPLOYMENT VERIFICATION -> FACILITY RELATIONSHIP -> FUNCTIONAL OWNERSHIP
-> AUTHORITY CLASS -> PERSON CONFIDENCE -> ONLY THEN APOLLO ELIGIBILITY.

Strict Tenets:
1. Human Truth: Rejection of company names, department names, product names,
   SEO titles, and non-human strings.
2. Authority & Function Hierarchy: Deterministic scoring of Plant Quality, Metrology,
   Calibration, and Plant Operations roles without requiring literal 'calibration'.
3. Multi-Query Adaptive Search across public LinkedIn indexed snippets and public management pages.
4. Deterministic Person Scoring from Zero (0-100):
   - Current Employment: 0-25
   - Facility Relationship: 0-25
   - Function Alignment: 0-25
   - Commercial Authority: 0-15
   - Source Quality & Recency: 0-10
   Threshold: >=85 = HIGH, 70-84 = MEDIUM, <70 = LOW.
   Only HIGH confidence qualifies for Apollo staging.
5. Primary and Secondary Person pairing.
6. Honest LinkedIn Provenance: LINKEDIN_SEARCH_SNIPPET, zero auth bypass.
"""
from __future__ import annotations

import logging
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

NOW_DT = datetime(2026, 9, 12, tzinfo=timezone.utc)

# ── Phase 2: Authority Hierarchy & Functional Roles ───────────────────────────
AUTHORITY_HIERARCHY = [
    "DIRECT_CALIBRATION_OWNER",
    "METROLOGY_OWNER",
    "STRONG_PLANT_QUALITY_OWNER",
    "FACILITY_OWNER",
    "GROUP_FUNCTION_OWNER",
    "FUNCTIONALLY_RELEVANT",
    "GENERAL_QUALITY",
    "COMPANY_ONLY",
    "UNKNOWN",
]

FUNCTION_MAP = {
    "CALIBRATION": ["calibration", "calibration lab", "calibration incharge", "standards lab"],
    "METROLOGY": ["metrology", "cmm", "measurement systems", "gauge calibration", "precision measurement"],
    "PLANT_QUALITY": ["plant quality", "head quality", "quality head", "qa head", "qc head", "dgm quality", "agm quality", "gm quality"],
    "QUALITY_SYSTEMS": ["quality systems", "qms", "iatf", "iso 9001", "iso/iec 17025", "audit quality"],
    "MANUFACTURING_QUALITY": ["manufacturing quality", "operations quality", "production quality", "shopfloor quality"],
    "TESTING_INSPECTION": ["testing", "inspection", "quality control", "metallurgical lab", "testing lab"],
    "FACILITY_OPERATIONS": ["plant head", "works manager", "factory manager", "operations head", "vp manufacturing", "plant director"],
    "MAINTENANCE_INSTRUMENTATION": ["maintenance head", "instrumentation head", "electrical & instrumentation", "plant maintenance"],
}

# ── Non-Human & Generic Rejections ───────────────────────────────────────────
NON_HUMAN_ENTITIES = {
    "ramakrishna", "ramakrishna mission", "sri ramakrishna", "swami vivekananda",
    "wikipedia", "britannica", "quora", "glassdoor", "ambitionbox", "zaubacorp",
    "tofler", "indiamart", "tradeindia", "justdial", "linkedin",
    "quality department", "operations team", "leadership team", "plant management",
    "careers", "job opening", "hiring", "recruitment", "human resources",
    "annual report", "financial results", "press release", "news desk", "web desk",
    "status", "smrt status", "dev smrt status", "profile", "updates", "contact us",
    "about us", "board of directors", "management team", "editorial team",
}

GENERIC_ROLE_PHRASES = {
    "operations leadership team", "head of plant operations", "quality team",
    "plant head", "quality manager", "general manager", "vice president",
    "director of operations", "executive director", "managing director",
    "head quality", "qa manager", "qc manager", "plant operations",
}

COMPANY_SUFFIX_TOKENS = {
    "limited", "ltd", "private", "pvt", "corp", "corporation", "inc", "incorporated",
    "industries", "energy", "enterprises", "solutions", "technologies", "automotive",
    "forgings", "engineering", "india", "group", "co", "company", "holdings",
}


# ── Phase 5: Human Validation ────────────────────────────────────────────────
def is_human_person_candidate(name_str: str, company_name: str = "") -> Tuple[bool, str]:
    """Validate whether candidate string represents a genuine human decision-maker.

    Rejects: company names, department names, product names, SEO titles, generic phrases.
    Preserves: Indian initials, honorifics, compound names, and regional formats.
    """
    clean = (name_str or "").strip()
    if not clean:
        return False, "Candidate name is empty"

    # Remove trailing company/title fragments if separated by dash or pipe
    clean = re.split(r"\s*[-–|•]\s*", clean)[0].strip()

    tokens = re.findall(r"[a-zA-Z]+", clean)
    if not tokens:
        return False, "No alphabetic tokens found"

    clean_lower = clean.lower()

    # 1. Non-human known entities / organizations
    if clean_lower in NON_HUMAN_ENTITIES or any(nh == clean_lower for nh in NON_HUMAN_ENTITIES):
        return False, f"Matched known non-human entity: {clean}"

    # Check for historical/spiritual figures
    if any(h in clean_lower for h in ["ramakrishna", "vivekananda", "mahatma gandhi", "aurobindo"]):
        return False, f"Matched historical/spiritual non-commercial entity: {clean}"

    # 2. Generic role phrase alone
    if clean_lower in GENERIC_ROLE_PHRASES:
        return False, f"Candidate name is a generic role phrase, not a human name: {clean}"

    # Reject if any token is a company suffix or department indicator
    dept_tokens = {"department", "dept", "team", "leadership", "management", "assurance", "operations", "division"}
    tokens_lower = [t.lower() for t in tokens]
    if any(t in COMPANY_SUFFIX_TOKENS for t in tokens_lower):
        return False, f"Contains corporate/company suffix token: {clean}"
    if any(t in dept_tokens for t in tokens_lower):
        return False, f"Contains departmental/team term: {clean}"

    # 3. Company name match
    if company_name:
        comp_clean = re.sub(r"[^\w\s]", " ", company_name.lower())
        comp_tokens = [t for t in comp_clean.split() if t not in COMPANY_SUFFIX_TOKENS and len(t) > 2]
        name_tokens_clean = [t for t in tokens_lower if t not in COMPANY_SUFFIX_TOKENS and len(t) > 2]

        if comp_tokens and name_tokens_clean:
            matched = sum(1 for t in name_tokens_clean if t in comp_tokens)
            if matched >= len(name_tokens_clean):
                return False, f"Candidate name '{clean}' matches company name tokens '{company_name}'"
            if matched >= 2:
                return False, f"Candidate name '{clean}' has 2+ company name tokens"

    # 4. Characters / symbols check
    if re.search(r"[\d@:/\\_<>{}\[\]\*\+=#\$%^&~®™©|!?;]", clean):
        return False, "Contains digits or punctuation invalid for human names"

    # 5. Token length check (allow 2 to 4 tokens, plus optional honorific)
    # Honorifics
    honorifics = {"mr", "dr", "mrs", "ms", "shri", "smt", "prof", "er"}
    meaningful_tokens = [t for t in tokens if t.lower() not in honorifics]

    if len(meaningful_tokens) < 2:
        return False, f"Candidate name '{clean}' has fewer than 2 meaningful tokens"

    if len(meaningful_tokens) > 5:
        return False, f"Candidate name '{clean}' has too many tokens; likely a phrase or title"

    # 6. Reject SEO / web page title terms
    seo_terms = {"overview", "about", "careers", "jobs", "salary", "news", "updates", "status", "profile", "review"}
    if any(t.lower() in seo_terms for t in tokens):
        return False, f"Contains web page or SEO keyword: {clean}"

    return True, "Valid human person candidate"


# ── Phase 3: Multi-Query Person Discovery ────────────────────────────────────
def generate_person_search_queries(
    company_name: str,
    facility_name: Optional[str] = None,
    city: Optional[str] = None,
    max_queries: int = 12,
) -> List[Dict[str, str]]:
    """Generate adaptive 3-pass person discovery queries.

    Pass 1: Exact function (Quality, Metrology, Calibration).
    Pass 2: Facility / Plant ownership (Plant Head, City Quality).
    Pass 3: Broader authoritative leadership (VP Operations, QA QC Head).
    """
    clean_company = company_name.strip()
    c_loc = city or (facility_name if facility_name and len(facility_name) < 25 else "")
    queries = []

    # PASS 1: Exact function (High conversion for calibration/quality)
    p1_roles = ["Quality Head", "Plant Quality", "Head Quality", "Metrology", "Calibration"]
    for role in p1_roles:
        queries.append({
            "query": f'site:linkedin.com/in "{clean_company}" "{role}"',
            "pass": "PASS_1_EXACT_FUNCTION",
            "target_role": role,
        })

    # PASS 2: Facility ownership
    if c_loc:
        queries.append({
            "query": f'site:linkedin.com/in "{clean_company}" "{c_loc}" "Plant Head"',
            "pass": "PASS_2_FACILITY_OWNERSHIP",
            "target_role": "Plant Head",
        })
        queries.append({
            "query": f'site:linkedin.com/in "{clean_company}" "{c_loc}" Quality',
            "pass": "PASS_2_FACILITY_OWNERSHIP",
            "target_role": "Quality",
        })
        queries.append({
            "query": f'"{clean_company}" "{c_loc}" "Plant Head"',
            "pass": "PASS_2_FACILITY_OWNERSHIP",
            "target_role": "Plant Head",
        })
    else:
        queries.append({
            "query": f'site:linkedin.com/in "{clean_company}" "Plant Head"',
            "pass": "PASS_2_FACILITY_OWNERSHIP",
            "target_role": "Plant Head",
        })

    # PASS 3: Broader authoritative roles
    p3_roles = ["VP Quality", "Head Manufacturing Quality", "QA QC Head"]
    for role in p3_roles:
        queries.append({
            "query": f'"{clean_company}" "{role}"',
            "pass": "PASS_3_AUTHORITATIVE_LEADERSHIP",
            "target_role": role,
        })

    return queries[:max_queries]


# ── Phase 6, 7, 8: Entity Evaluation & Scoring ──────────────────────────────
def classify_current_employment(snippet: str, title: str, company_name: str) -> str:
    """Classify current employment status from public evidence.

    Values: VERIFIED, PROBABLE, UNKNOWN, STALE, CONTRADICTED.
    """
    combined = f"{title} {snippet}".lower()
    comp_clean = company_name.lower().replace("limited", "").replace("ltd", "").strip()

    # Contradicted / Former indicators
    former_patterns = [
        r"\b(?:former|formerly|ex-|past|previously)\b.*?\b" + re.escape(comp_clean[:8]),
        r"\b" + re.escape(comp_clean[:8]) + r"\b.*?\buntil\s+(?:20\d{2}|19\d{2})",
        r"\bpreviously\s+worked\s+at\s+" + re.escape(comp_clean[:8]),
    ]
    for fp in former_patterns:
        if re.search(fp, combined):
            return "CONTRADICTED"

    # Check for another current employer
    if re.search(r"experience:\s+[A-Za-z0-9\s]+(?:\(present\)|\bpresent\b)", combined) and comp_clean[:8] not in combined:
        return "CONTRADICTED"

    if re.search(r"\bcurrently\s+(?:at|with|working\s+at)\s+(?![a-z\s]*" + re.escape(comp_clean[:6]) + r")[a-z]+", combined):
        return "CONTRADICTED"

    # Verified current indicators
    has_company = comp_clean[:8] in combined
    if not has_company:
        return "UNKNOWN"

    present_terms = [r"\bpresent\b", r"\bcurrently\b", r"\bserving\s+as\b", r"\bleads\s+the\b", r"\bresponsible\s+for\b"]
    has_present = any(re.search(pt, combined) for pt in present_terms)
    has_current_exp = bool(re.search(r"experience:\s*.*?" + re.escape(comp_clean[:8]), combined))
    has_recent_year = any(y in combined for y in ["2024", "2025", "2026", "fy 25", "fy 26"])

    if has_current_exp or (has_company and (has_present or has_recent_year)):
        return "VERIFIED"

    if has_company:
        return "PROBABLE"

    return "UNKNOWN"


GENERIC_FACILITY_TOKENS = {
    "plant", "facility", "works", "unit", "manufacturing", "complex",
    "division", "factory", "site", "headquarters", "office", "operations",
}

KNOWN_MAJOR_CITIES = {
    "pune", "mumbai", "chennai", "delhi", "gurgaon", "bangalore", "bengaluru",
    "hyderabad", "ahmedabad", "kolkata", "sanand", "jamshedpur", "indore", "dahej", "jamuria",
}


def classify_facility_relationship(
    candidate_title: str,
    candidate_text: str,
    target_facility: str,
    target_city: str,
) -> str:
    """Classify relationship between candidate and the target manufacturing facility.

    Values:
    FACILITY_OWNER
    FACILITY_FUNCTION_OWNER
    GROUP_FUNCTION_OWNER
    FUNCTIONALLY_RELEVANT
    COMPANY_ONLY
    UNKNOWN
    """
    clean_text = f"{candidate_title} {candidate_text}".lower()
    t_city = target_city.lower().strip() if target_city else ""
    t_fac = target_facility.lower().strip() if target_facility else ""

    is_plant_head = any(w in candidate_title.lower() for w in ["plant head", "works manager", "factory manager", "unit head", "site head"])
    is_quality = any(w in candidate_title.lower() for w in ["quality", "qa", "qc", "metrology", "calibration"])

    # Extract non-generic facility tokens
    fac_tokens = [w for w in t_fac.split() if len(w) >= 4 and w not in GENERIC_FACILITY_TOKENS]

    # Facility & city match indicators
    city_match = bool(t_city and len(t_city) > 2 and t_city in clean_text)
    fac_match = bool(fac_tokens and any(w in clean_text for w in fac_tokens))

    # Detect if candidate is explicitly located in a DIFFERENT known city
    if t_city:
        other_cities_in_text = [c for c in KNOWN_MAJOR_CITIES if c in clean_text and c != t_city]
        if other_cities_in_text and not city_match and not fac_match:
            # Explicit location mismatch
            if any(w in candidate_title.lower() for w in ["group", "corporate", "chief", "vice president", "vp"]) and is_quality:
                return "GROUP_FUNCTION_OWNER"
            return "COMPANY_ONLY"

    if is_plant_head and (city_match or fac_match):
        return "FACILITY_OWNER"

    if is_quality and (city_match or fac_match):
        return "FACILITY_FUNCTION_OWNER"

    if any(w in candidate_title.lower() for w in ["group", "corporate", "chief", "vice president", "vp"]) and is_quality:
        return "GROUP_FUNCTION_OWNER"

    if is_plant_head:
        return "FACILITY_OWNER" if not target_city else "FUNCTIONALLY_RELEVANT"

    if is_quality:
        return "FUNCTIONALLY_RELEVANT"

    if any(w in candidate_title.lower() for w in ["operations", "manufacturing", "production", "maintenance"]):
        return "FUNCTIONALLY_RELEVANT"

    return "COMPANY_ONLY"


def classify_authority_class(title: str, snippet: str = "") -> str:
    """Classify the person into Salesoorja priority authority hierarchy."""
    clean = f"{title} {snippet}".lower()

    if any(w in clean for w in ["calibration lab", "calibration incharge", "head calibration", "calibration engineer"]):
        return "DIRECT_CALIBRATION_OWNER"

    if any(w in clean for w in ["metrology", "cmm", "measurement systems"]):
        return "METROLOGY_OWNER"

    if any(w in clean for w in ["plant quality", "head quality", "quality head", "qa head", "qc head", "head of quality", "director quality"]):
        return "STRONG_PLANT_QUALITY_OWNER"

    if any(w in clean for w in ["plant head", "works manager", "factory manager", "unit head", "site head"]):
        return "FACILITY_OWNER"

    if any(w in clean for w in ["corporate quality", "group quality", "vp quality", "vice president quality"]):
        return "GROUP_FUNCTION_OWNER"

    if any(w in clean for w in ["quality assurance", "quality control", "qa manager", "qc manager", "manager quality"]):
        return "FUNCTIONALLY_RELEVANT"

    if "quality" in clean:
        return "GENERAL_QUALITY"

    if any(w in clean for w in ["operations", "manufacturing", "production", "maintenance"]):
        return "FUNCTIONALLY_RELEVANT"

    return "UNKNOWN"


def compute_deterministic_person_score(
    current_employment: str,
    facility_relationship: str,
    authority_class: str,
    title: str,
    source_quality: str,
) -> Tuple[float, str]:
    """Compute deterministic person score (0-100) and confidence (HIGH/MEDIUM/LOW).

    Weights:
    - Current Employment: 0-25
    - Facility Relationship: 0-25
    - Function Alignment: 0-25
    - Authority: 0-15
    - Source Quality: 0-10
    """
    # 1. Current Employment (0-25)
    if current_employment == "VERIFIED":
        score_emp = 25.0
    elif current_employment == "PROBABLE":
        score_emp = 15.0
    elif current_employment == "UNKNOWN":
        score_emp = 5.0
    else:  # STALE or CONTRADICTED
        score_emp = 0.0

    # 2. Facility Relationship (0-25)
    if facility_relationship in ("FACILITY_OWNER", "FACILITY_FUNCTION_OWNER"):
        score_fac = 25.0
    elif facility_relationship == "GROUP_FUNCTION_OWNER":
        score_fac = 18.0
    elif facility_relationship == "FUNCTIONALLY_RELEVANT":
        score_fac = 12.0
    elif facility_relationship == "COMPANY_ONLY":
        score_fac = 5.0
    else:
        score_fac = 0.0

    # 3. Function Alignment (0-25)
    if authority_class in ("DIRECT_CALIBRATION_OWNER", "METROLOGY_OWNER"):
        score_fn = 25.0
    elif authority_class == "STRONG_PLANT_QUALITY_OWNER":
        score_fn = 23.0
    elif authority_class in ("FACILITY_OWNER", "GROUP_FUNCTION_OWNER"):
        score_fn = 20.0
    elif authority_class == "FUNCTIONALLY_RELEVANT":
        score_fn = 14.0
    elif authority_class == "GENERAL_QUALITY":
        score_fn = 10.0
    else:
        score_fn = 2.0

    # 4. Authority Level (0-15)
    t_lower = title.lower()
    if any(w in t_lower for w in ["vp", "vice president", "director", "head", "general manager", "gm", "plant head"]):
        score_auth = 15.0
    elif any(w in t_lower for w in ["manager", "dgm", "agm", "lead"]):
        score_auth = 10.0
    elif any(w in t_lower for w in ["engineer", "specialist", "executive"]):
        score_auth = 5.0
    else:
        score_auth = 2.0

    # 5. Source Quality (0-10)
    if source_quality in ("OFFICIAL_COMPANY_PAGE", "PRESS_RELEASE"):
        score_src = 10.0
    elif source_quality == "LINKEDIN_SEARCH_SNIPPET":
        score_src = 8.0
    else:
        score_src = 5.0

    total_score = score_emp + score_fac + score_fn + score_auth + score_src
    total_score = max(0.0, min(100.0, total_score))

    # Strict Confidence Classification
    # HIGH requires score >= 85, VERIFIED employment, and meaningful facility relationship
    if (
        total_score >= 85.0
        and current_employment == "VERIFIED"
        and facility_relationship in ("FACILITY_OWNER", "FACILITY_FUNCTION_OWNER", "GROUP_FUNCTION_OWNER")
    ):
        confidence = "HIGH"
    elif total_score >= 70.0 and current_employment in ("VERIFIED", "PROBABLE"):
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    return total_score, confidence


# ── Phase 4 & 10: Extraction & Candidate Ranking ──────────────────────────────
def extract_person_from_search_result(
    item: Dict[str, Any],
    company_name: str,
    facility_name: str = "",
    city: str = "",
) -> Optional[Dict[str, Any]]:
    """Extract and qualify a single person candidate from a search result item."""
    title_raw = item.get("title", "")
    snippet_raw = item.get("snippet", "") or item.get("content", "")
    url = item.get("url", "")

    # Clean non-human Wikipedia/Britannica URLs immediately
    if any(bad in url.lower() for bad in ["wikipedia.org", "britannica.com", "glassdoor.", "ambitionbox."]):
        return None

    # Check LinkedIn title format: "<Name> - <Title> - <Company> | LinkedIn"
    # or "<Name> - <Title> ... - LinkedIn"
    cand_name = ""
    cand_title = ""

    if "linkedin.com/in/" in url:
        m_li = re.match(r"^(.*?)\s*[-–|]\s*(.*?)(?:\s*[-–|]\s*(?:LinkedIn|Ramkrishna|Maruti|Shyam|Valeo|Kehems))", title_raw, re.IGNORECASE)
        if m_li:
            cand_name = m_li.group(1).strip()
            cand_title = m_li.group(2).strip()
        else:
            # Fallback split on first dash
            parts = re.split(r"\s*[-–|]\s*", title_raw)
            if len(parts) >= 2:
                cand_name = parts[0].strip()
                cand_title = parts[1].strip()
    else:
        # Generic web page extraction
        m_web = re.search(r"([A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+)\s*[-–|,]\s*(Plant Head|VP|Vice President|General Manager|Director|Head of Quality|Quality Manager|Operations Head|QA Head)", f"{title_raw} {snippet_raw}")
        if m_web:
            cand_name = m_web.group(1).strip()
            cand_title = m_web.group(2).strip()

    if not cand_name:
        return None

    # Validate human name
    is_human, reason = is_human_person_candidate(cand_name, company_name=company_name)
    if not is_human:
        return None

    # Clean candidate title
    clean_title = cand_title.replace(" | LinkedIn", "").replace(" - LinkedIn", "").strip()
    if not clean_title or len(clean_title) < 3:
        clean_title = "Operations / Quality Leadership"

    current_emp = classify_current_employment(snippet_raw, title_raw, company_name)
    fac_rel = classify_facility_relationship(clean_title, snippet_raw, facility_name, city)
    auth_class = classify_authority_class(clean_title, snippet_raw)
    src_quality = "LINKEDIN_SEARCH_SNIPPET" if "linkedin.com" in url else "PUBLIC_WEB_BIO"

    score, conf = compute_deterministic_person_score(
        current_employment=current_emp,
        facility_relationship=fac_rel,
        authority_class=auth_class,
        title=clean_title,
        source_quality=src_quality,
    )

    return {
        "name": cand_name,
        "title": clean_title,
        "company": company_name,
        "facility": facility_name or city,
        "location": item.get("location") or city or facility_name,
        "source_date": item.get("source_date") or item.get("published_date") or item.get("date") or "",
        "current_employment": current_emp,
        "facility_relationship": fac_rel,
        "authority_class": auth_class,
        "person_score": score,
        "person_confidence": conf,
        "source_url": url,
        "source_type": src_quality,
        "evidence_snippet": snippet_raw[:250],
    }


def _normalize_person_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def generate_deepseek_person_queries(
    company_name: str,
    facility_name: str,
    city: str,
    commercial_trigger: str,
    target_functions: List[str],
    provider: Any,
    max_queries: int = 3,
) -> Dict[str, Any]:
    """Generate up to three public-search queries; generated text is never evidence."""
    request_payload = {
        "company": company_name,
        "facility": facility_name,
        "city": city,
        "commercial_trigger": commercial_trigger,
        "target_functions": target_functions,
        "max_queries": min(max(int(max_queries), 0), 3),
    }
    response = provider.complete(
        system_prompt=(
            "Generate targeted public-web search queries for a manufacturing decision maker. "
            "Use only supplied facts. Queries are discovery instructions, never evidence. "
            "Return JSON as {\"queries\": [\"...\"]} with at most three queries."
        ),
        messages=[{"role": "user", "content": json.dumps(request_payload)}],
        response_format="json",
        temperature=0.1,
        max_tokens=300,
    )
    parsed = response.parse_json() or {}
    raw_queries = parsed.get("queries") if isinstance(parsed, dict) else []
    queries: List[str] = []
    for raw_query in raw_queries if isinstance(raw_queries, list) else []:
        query_value = raw_query.get("query") if isinstance(raw_query, dict) else raw_query
        if not isinstance(query_value, str):
            continue
        query = query_value.strip()
        if not query or len(query) > 300 or "\n" in query or query in queries:
            continue
        queries.append(query)
        if len(queries) >= request_payload["max_queries"]:
            break
    return {
        "queries": queries,
        "usage": dict(response.usage or {}),
        "provider": response.provider,
        "model": response.model,
    }


def rank_candidates_with_deepseek(
    company_name: str,
    facility_name: str,
    city: str,
    commercial_trigger: str,
    target_functions: List[str],
    candidates: List[Dict[str, Any]],
    provider: Any,
) -> Dict[str, Any]:
    """Batch-rank known candidates without changing deterministic truth fields."""
    public_candidates = [
        {
            "name": candidate.get("name", ""),
            "title": candidate.get("title", ""),
            "source": candidate.get("source_url", ""),
            "snippet": candidate.get("evidence_snippet", ""),
            "source_date": candidate.get("source_date", ""),
            "location": candidate.get("location") or candidate.get("facility", ""),
        }
        for candidate in candidates
    ]
    request_payload = {
        "company": company_name,
        "facility": facility_name,
        "city": city,
        "commercial_trigger": commercial_trigger,
        "target_functions": target_functions,
        "candidates": public_candidates,
    }
    response = provider.complete(
        system_prompt=(
            "Rank only the supplied person candidates for calibration-related commercial outreach. "
            "Do not create people, employment facts, facility relationships, duties, or calibration ownership. "
            "Every positive assertion must map to the supplied title, snippet, location, source, or source date. "
            "Treat missing current-employment or facility evidence as missing. Return JSON with ranked_candidates; "
            "each item must include name, rank, current_employment_supported, facility_relationship, "
            "function_alignment, authority_class, confidence, evidence_reasons, and missing_evidence."
        ),
        messages=[{"role": "user", "content": json.dumps(request_payload)}],
        response_format="json",
        temperature=0.1,
        max_tokens=1200,
    )
    parsed = response.parse_json() or {}
    ranked_items = parsed.get("ranked_candidates") if isinstance(parsed, dict) else []
    assessments: Dict[str, Dict[str, Any]] = {}
    for item in ranked_items if isinstance(ranked_items, list) else []:
        if not isinstance(item, dict):
            continue
        key = _normalize_person_name(str(item.get("name") or ""))
        if key and key not in assessments:
            assessments[key] = item

    ranked_candidates: List[Dict[str, Any]] = []
    for candidate in candidates:
        candidate_copy = dict(candidate)
        assessment = assessments.get(_normalize_person_name(str(candidate.get("name") or "")))
        if assessment:
            candidate_copy["deepseek_assessment"] = assessment
            try:
                candidate_copy["deepseek_rank"] = int(assessment.get("rank"))
            except (TypeError, ValueError):
                candidate_copy["deepseek_rank"] = 9999
        ranked_candidates.append(candidate_copy)
    def ranking_key(candidate: Dict[str, Any]) -> tuple[int, float]:
        rank = int(candidate.get("deepseek_rank") or 9999)
        return rank, -float(candidate.get("person_score") or 0)

    ranked_candidates.sort(key=ranking_key)
    return {
        "candidates": ranked_candidates,
        "assessment_count": len(assessments),
        "usage": dict(response.usage or {}),
        "provider": response.provider,
        "model": response.model,
    }


def discover_and_rank_decision_makers(
    company_name: str,
    facility_name: str = "",
    city: str = "",
    search_router: Any = None,
    max_candidates: int = 5,
    use_deepseek: bool = False,
    ranking_provider: Any = None,
    commercial_trigger: str = "",
    target_functions: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Execute end-to-end multi-query person discovery and return Primary + Secondary candidates.

    Returns:
    {
        "primary_person": dict | None,
        "secondary_person": dict | None,
        "candidates": list[dict],
        "telemetry": dict,
    }
    """
    if search_router is None:
        from services.research_provider import research_router
        search_router = research_router

    queries = generate_person_search_queries(company_name, facility_name=facility_name, city=city)

    all_candidates = []
    seen_names = set()
    telemetry = {
        "queries_run": 0,
        "results_returned": 0,
        "raw_candidates_extracted": 0,
        "non_human_rejected": 0,
        "verified_employment_count": 0,
        "high_confidence_count": 0,
        "hive_requests": 0,
        "hive_input_tokens": 0,
        "hive_output_tokens": 0,
        "deepseek_queries_generated": 0,
    }

    def collect_candidates(query_objects: List[Dict[str, str]]) -> None:
        for q_obj in query_objects:
            q = q_obj["query"]
            telemetry["queries_run"] += 1
            res = search_router.search(q, num_results=5)
            items = res.get("results", [])
            telemetry["results_returned"] += len(items)

            for item in items:
                cand = extract_person_from_search_result(
                    item,
                    company_name=company_name,
                    facility_name=facility_name,
                    city=city,
                )
                if not cand:
                    continue

                name_key = cand["name"].lower()
                if name_key in seen_names:
                    continue

                seen_names.add(name_key)
                all_candidates.append(cand)
                telemetry["raw_candidates_extracted"] += 1

                if cand["current_employment"] == "VERIFIED":
                    telemetry["verified_employment_count"] += 1
                if cand["person_confidence"] == "HIGH":
                    telemetry["high_confidence_count"] += 1

    collect_candidates(queries)

    functions = target_functions or ["Plant Quality", "Metrology", "Plant Head"]
    if use_deepseek:
        if ranking_provider is None:
            from services.llm_provider import get_provider
            ranking_provider = get_provider("hive")
        if not any(candidate.get("person_confidence") == "HIGH" for candidate in all_candidates):
            try:
                generated = generate_deepseek_person_queries(
                    company_name=company_name,
                    facility_name=facility_name,
                    city=city,
                    commercial_trigger=commercial_trigger,
                    target_functions=functions,
                    provider=ranking_provider,
                    max_queries=3,
                )
                telemetry["hive_requests"] += 1
                telemetry["hive_input_tokens"] += int(generated["usage"].get("input_tokens", 0) or 0)
                telemetry["hive_output_tokens"] += int(generated["usage"].get("output_tokens", 0) or 0)
                generated_queries = [
                    {"query": query, "pass": "PASS_4_DEEPSEEK_QUERY", "target_role": "LLM_GENERATED"}
                    for query in generated["queries"]
                ]
                telemetry["deepseek_queries_generated"] = len(generated_queries)
                collect_candidates(generated_queries)
            except Exception as exc:
                telemetry["deepseek_query_error"] = type(exc).__name__

        if all_candidates:
            try:
                deterministic_pool = sorted(
                    all_candidates,
                    key=lambda candidate: (
                        -float(candidate.get("person_score") or 0),
                        AUTHORITY_HIERARCHY.index(candidate["authority_class"])
                        if candidate.get("authority_class") in AUTHORITY_HIERARCHY else 99,
                    ),
                )[:20]
                ranked = rank_candidates_with_deepseek(
                    company_name=company_name,
                    facility_name=facility_name,
                    city=city,
                    commercial_trigger=commercial_trigger,
                    target_functions=functions,
                    candidates=deterministic_pool,
                    provider=ranking_provider,
                )
                telemetry["hive_requests"] += 1
                telemetry["hive_input_tokens"] += int(ranked["usage"].get("input_tokens", 0) or 0)
                telemetry["hive_output_tokens"] += int(ranked["usage"].get("output_tokens", 0) or 0)
                ranked_by_name = {
                    _normalize_person_name(candidate.get("name", "")): candidate
                    for candidate in ranked["candidates"]
                }
                all_candidates = [
                    ranked_by_name.get(_normalize_person_name(candidate.get("name", "")), candidate)
                    for candidate in all_candidates
                ]
                deepseek_candidates = sorted(
                    [candidate for candidate in ranked["candidates"] if candidate.get("deepseek_rank") is not None],
                    key=lambda candidate: (
                        int(candidate.get("deepseek_rank") or 9999),
                        -float(candidate.get("person_score") or 0),
                    ),
                )
                telemetry["deepseek_top1"] = deepseek_candidates[0].get("name") if deepseek_candidates else None
                telemetry["deepseek_ranking_applied"] = bool(ranked["assessment_count"])
                if not ranked["assessment_count"]:
                    telemetry["deepseek_ranking_error"] = "NO_VALID_STRUCTURED_RANKING"
            except Exception as exc:
                telemetry["deepseek_ranking_applied"] = False
                telemetry["deepseek_ranking_error"] = type(exc).__name__

    all_candidates.sort(
        key=lambda c: (
            -c["person_score"],
            AUTHORITY_HIERARCHY.index(c["authority_class"]) if c["authority_class"] in AUTHORITY_HIERARCHY else 99,
            int(c.get("deepseek_rank") or 9999),
        )
    )

    primary = all_candidates[0] if all_candidates else None
    secondary = all_candidates[1] if len(all_candidates) > 1 else None

    return {
        "primary_person": primary,
        "secondary_person": secondary,
        "candidates": all_candidates[:max_candidates],
        "telemetry": telemetry,
    }
