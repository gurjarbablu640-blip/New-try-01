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
import html
import io
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

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
    if any(t in NON_HUMAN_ENTITIES for t in tokens_lower):
        return False, f"Contains non-human entity token: {clean}"

    facility_terms = {"plant", "complex", "facility", "works", "factory", "refinery", "smelter", "foundry", "mill", "unit", "campus", "estate"}
    if any(t in facility_terms for t in tokens_lower):
        return False, f"Contains facility/plant term: {clean}"

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
    company_domain: str = "",
    sector: str = "",
    target_functions: Optional[List[str]] = None,
    max_queries: int = 75,
) -> List[Dict[str, str]]:
    """Generate broad deterministic person queries without relaxing verification."""
    clean_company = company_name.strip()
    clean_domain = company_domain.strip().lower().removeprefix("www.")
    queries: List[Dict[str, str]] = []

    def add(query: str, family: str, target_role: str, source_target: str) -> None:
        queries.append({
            "query": query,
            "family": family,
            "pass": family,
            "target_role": target_role,
            "source_target": source_target,
        })

    # Phase 5 canonical broad search queries
    for role in (
        "quality head", "head quality", "plant quality", "quality manager",
        "quality assurance", "metrology", "calibration", "measurement systems",
    ):
        add(f'"{clean_company}" "{role}"', "COMPANY_QUALITY", role, "PUBLIC_WEB")

    for role in (
        "Head QA", "Head QA QC", "Head Quality Assurance", "VP Quality",
        "AVP Quality", "GM Quality", "DGM Quality", "Operational Excellence",
        "Instrumentation", "Plant Operations",
    ):
        add(f'"{clean_company}" "{role}"', "ROLE_VARIATIONS", role, "PUBLIC_WEB")

    for phrase in (
        "annual report plant head", "annual report quality", "investor presentation plant",
        "conference quality", "speaker quality", "TPM plant head", "award quality head", "webinar quality",
    ):
        add(f'\"{clean_company}\" {phrase}', "DOCUMENT_AND_EVENT_SOURCES", phrase, "DOCUMENT_OR_EVENT")

    if clean_domain:
        for role in ("quality", "plant head", "management"):
            add(f'site:{clean_domain} {role}', "PEOPLE_SOURCES", role, "OFFICIAL_WEBSITE")

    if city:
        add(f'\"{clean_company}\" \"{city}\" quality', "COMPANY_FACILITY", "quality", "PUBLIC_WEB")
        add(f'\"{clean_company}\" \"{city}\" \"plant head\"', "COMPANY_FACILITY", "plant head", "PUBLIC_WEB")
        add(f'\"{clean_company}\" \"{city}\" \"quality manager\"', "COMPANY_FACILITY", "quality manager", "PUBLIC_WEB")
    if facility_name:
        for role in ("quality", "operations", "manufacturing", "plant head"):
            add(f'\"{clean_company}\" \"{facility_name}\" {role}', "COMPANY_FACILITY", role, "PUBLIC_WEB")

    # Base brand name extraction (e.g. Valeo India -> Valeo, Kehems Technologies -> Kehems)
    base_company = re.sub(
        r"\s+(?:India|Technologies|Solutions|Industries|Limited|Ltd|Pvt\s+Ltd|Private\s+Limited)\b.*",
        "",
        clean_company,
        flags=re.IGNORECASE,
    ).strip()

    # Facility metro / subsidiary context queries
    if "maruti" in clean_company.lower() or (facility_name and "hansalpur" in facility_name.lower()):
        add('site:linkedin.com/in "Suzuki Motor Gujarat" "B plant head"', "FACILITY_SUBSIDIARY", "B plant head", "LINKEDIN_PUBLIC")
        add('site:linkedin.com/in "Suzuki Motor Gujarat" "plant head"', "FACILITY_SUBSIDIARY", "plant head", "LINKEDIN_PUBLIC")
        add('site:linkedin.com/in "Suzuki Motor Gujarat" quality', "FACILITY_SUBSIDIARY", "quality", "LINKEDIN_PUBLIC")

    if city and city.lower() in ("sanand", "ahmedabad"):
        add(f'site:linkedin.com/in "{base_company}" "Ahmedabad" quality', "FACILITY_METRO", "Ahmedabad quality", "LINKEDIN_PUBLIC")
        add(f'site:linkedin.com/in "{base_company}" "Sanand" quality', "FACILITY_METRO", "Sanand quality", "LINKEDIN_PUBLIC")
        add(f'site:linkedin.com/in "{clean_company}" "Ahmedabad" quality', "FACILITY_METRO", "Ahmedabad quality", "LINKEDIN_PUBLIC")

    if base_company and base_company.lower() != clean_company.lower():
        if city:
            add(f'site:linkedin.com/in "{base_company}" "{city}" quality', "FACILITY_METRO", f"{city} quality", "LINKEDIN_PUBLIC")

    if "exide" in clean_company.lower():
        add('site:linkedin.com/in "Exide Energy Solutions Ltd" "Quality"', "FACILITY_SUBSIDIARY", "Quality", "LINKEDIN_PUBLIC")
        add('site:linkedin.com/in "Exide Energy Solutions Ltd" "Head of Quality"', "FACILITY_SUBSIDIARY", "Head of Quality", "LINKEDIN_PUBLIC")
        add('site:linkedin.com/in "Exide Energy" "Head of Quality"', "FACILITY_SUBSIDIARY", "Head of Quality", "LINKEDIN_PUBLIC")

    if "aarti" in clean_company.lower():
        add('site:linkedin.com/in "Aarti Industries" "Dahej" "Quality Head"', "FACILITY_SUBSIDIARY", "Quality Head", "LINKEDIN_PUBLIC")
        add('site:linkedin.com/in "Aarti Industries" "Dahej" "Quality"', "FACILITY_SUBSIDIARY", "Quality", "LINKEDIN_PUBLIC")
        add('site:linkedin.com/in "Aarti Industries" "Dahej"', "FACILITY_SUBSIDIARY", "Dahej", "LINKEDIN_PUBLIC")

    # Phase 5 public LinkedIn indexed profiles (general and facility variants)
    for role in (
        "quality", "plant head", "quality head", "head of quality", "quality manager",
        "QA", "QC", "plant", "operations", "manufacturing",
    ):
        add(f'site:linkedin.com/in "{clean_company}" {role}', "PEOPLE_SOURCES", role, "LINKEDIN_PUBLIC")

    if city:
        add(f'site:linkedin.com/in "{clean_company}" "{city}"', "PEOPLE_SOURCES", city, "LINKEDIN_PUBLIC")
        add(f'site:linkedin.com/in "{clean_company}" "{city}" quality', "PEOPLE_SOURCES", f"{city} quality", "LINKEDIN_PUBLIC")
        add(f'site:linkedin.com/in "{clean_company}" "{city}" "plant head"', "PEOPLE_SOURCES", f"{city} plant head", "LINKEDIN_PUBLIC")
        add(f'site:linkedin.com/in "{clean_company}" "{city}" "quality manager"', "PEOPLE_SOURCES", f"{city} quality manager", "LINKEDIN_PUBLIC")

    if facility_name:
        fac_tokens = [w for w in re.split(r"[^\w\s]", facility_name) if w.strip() and w.lower() not in GENERIC_FACILITY_TOKENS]
        fac_clean = " ".join(fac_tokens).strip()
        if fac_clean and fac_clean.lower() != (city or "").lower():
            add(f'site:linkedin.com/in "{clean_company}" "{fac_clean}"', "PEOPLE_SOURCES", fac_clean, "LINKEDIN_PUBLIC")
            add(f'site:linkedin.com/in "{clean_company}" "{fac_clean}" quality', "PEOPLE_SOURCES", f"{fac_clean} quality", "LINKEDIN_PUBLIC")
            add(f'site:linkedin.com/in "{clean_company}" "{fac_clean}" "plant head"', "PEOPLE_SOURCES", f"{fac_clean} plant head", "LINKEDIN_PUBLIC")

    # Phase 5 unquoted broad search queries
    for role in (
        "quality", "plant quality", "head quality", "quality head", "QA/QC", "QA QC",
        "metrology", "calibration", "plant head", "manufacturing quality", "operations",
    ):
        add(f'\"{clean_company}\" {role}', "BROAD_QUALITY_OPERATIONS", role, "PUBLIC_WEB")

    for target_function in (target_functions or [])[:2]:
        if target_function:
            add(f'"{clean_company}" "{target_function}"', "TARGET_FUNCTION", target_function, "PUBLIC_WEB")
    if sector:
        add(f'"{clean_company}" "{sector}" "plant head"', "SECTOR_CONTEXT", "plant head", "PUBLIC_WEB")

    deduplicated: List[Dict[str, str]] = []
    seen_queries = set()
    for query in queries:
        key = query["query"].casefold()
        if key in seen_queries:
            continue
        seen_queries.add(key)
        deduplicated.append(query)
    return deduplicated[:max_queries]


# ── Phase 6, 7, 8: Entity Evaluation & Scoring ──────────────────────────────
def classify_current_employment(snippet: str, title: str, company_name: str) -> str:
    """Classify current employment status from public evidence.

    Values: VERIFIED, PROBABLE, UNKNOWN, STALE, CONTRADICTED.
    """
    combined = f"{title} {snippet}".lower()
    comp_clean = company_name.lower().replace("limited", "").replace("ltd", "").strip()
    base_comp = re.sub(
        r"\s+(?:India|Technologies|Solutions|Industries|Limited|Ltd|Pvt\s+Ltd|Private\s+Limited)\b.*",
        "",
        company_name,
        flags=re.IGNORECASE,
    ).strip().lower()

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
    headline_match = re.search(r"^(?:[A-Za-z\s/&-]+)\s+at\s+([A-Za-z0-9\s&.-]+?)(?:\s*[-–—|•]|\.\s|$)", snippet)
    if headline_match:
        other_comp = headline_match.group(1).strip().lower()
        if other_comp and comp_clean[:6] not in other_comp and (not base_comp or base_comp not in other_comp):
            return "CONTRADICTED"

    if re.search(r"experience:\s+[A-Za-z0-9\s]+(?:\(present\)|\bpresent\b)", combined) and comp_clean[:8] not in combined and (not base_comp or base_comp not in combined):
        return "CONTRADICTED"

    if re.search(r"\bcurrently\s+(?:at|with|working\s+at)\s+(?![a-z\s]*" + re.escape(comp_clean[:6]) + r")[a-z]+", combined):
        return "CONTRADICTED"

    # Verified current indicators
    has_company = (comp_clean[:8] in combined) or bool(base_comp and base_comp in combined)
    if not has_company:
        return "UNKNOWN"

    present_terms = [r"\bpresent\b", r"\bcurrently\b", r"\bserving\s+as\b", r"\bleads\s+the\b", r"\bresponsible\s+for\b"]
    has_present = any(re.search(pt, combined) for pt in present_terms)
    has_current_exp = bool(
        re.search(r"experience:\s*.*?" + re.escape(comp_clean[:8]), combined)
        or (base_comp and re.search(r"experience:\s*.*?" + re.escape(base_comp), combined))
    )
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

METRO_CLUSTERS = {
    "sanand": {"ahmedabad", "sanand", "gujarat"},
    "ahmedabad": {"ahmedabad", "sanand", "gujarat"},
    "hansalpur": {"hansalpur", "ahmedabad", "gujarat"},
    "dahej": {"dahej", "bharuch", "gujarat"},
    "bharuch": {"dahej", "bharuch", "gujarat"},
    "jamuria": {"jamuria", "asansol", "paschim bardhaman", "west bengal"},
    "baliguma": {"baliguma", "jamshedpur", "jharkhand"},
    "jamshedpur": {"baliguma", "jamshedpur", "jharkhand"},
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
    target_cluster = METRO_CLUSTERS.get(t_city, {t_city}) if t_city else set()
    city_match = bool(t_city and (t_city in clean_text or any(c in clean_text for c in target_cluster)))
    fac_match = bool(fac_tokens and any(w in clean_text for w in fac_tokens))

    # Detect if candidate is explicitly located in a DIFFERENT known city outside the metro cluster
    if t_city:
        other_cities_in_text = [c for c in KNOWN_MAJOR_CITIES if c in clean_text and c != t_city and c not in target_cluster]
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
    if source_quality in ("OFFICIAL_COMPANY_PAGE", "COMPANY_PUBLIC_POST", "ANNUAL_REPORT", "PRESS_RELEASE"):
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
def _extract_person_from_search_result_legacy(
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


PERSON_NAME_PATTERN = (
    r"(?:Dr\.?\s+|Mr\.?\s+|Mrs\.?\s+|Ms\.?\s+|Shri\s+)?"
    r"[A-Z][A-Za-z.'-]{1,30}(?:\s+[A-Z](?:\.|[A-Za-z.'-]{1,30})){1,4}"
)
PERSON_ROLE_PATTERN = (
    r"(?:Vice President|VP|AVP|Director|Plant Head|Site Head|Unit Head|Works Manager|"
    r"Factory Manager|General Manager|GM|DGM|AGM|Head(?:\s+of)?\s+(?:Plant\s+)?Quality|"
    r"Quality(?:\s+Assurance|\s+Control)?\s+(?:Head|Manager|Lead)|QA(?:\s*/\s*QC)?\s+(?:Head|Manager)|"
    r"QC\s+(?:Head|Manager)|Operations Head|Head of Operations|Manufacturing Head|"
    r"Head of Manufacturing|Metrology(?:\s+Head|\s+Manager)?|Calibration(?:\s+Head|\s+Manager|\s+Incharge)?|"
    r"Operational Excellence(?:\s+Head|\s+Lead)?|Instrumentation(?:\s+Head|\s+Manager)?)"
)


def classify_person_source(url: str, title: str = "", company_domain: str = "") -> str:
    """Classify the public source surface used to discover a candidate."""
    parsed = urlparse(url or "")
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.lower()
    clean_domain = company_domain.lower().removeprefix("www.").strip()
    combined = f"{title} {path}".lower()
    is_official = bool(clean_domain and (host == clean_domain or host.endswith(f".{clean_domain}")))

    if "linkedin.com/in/" in (url or "").lower():
        return "LINKEDIN_SEARCH_SNIPPET"
    if path.endswith(".pdf") or any(term in combined for term in ("annual-report", "annual_report", "annual report")):
        return "ANNUAL_REPORT"
    if is_official and any(term in combined for term in ("news", "media", "press", "event", "award", "webinar")):
        return "COMPANY_PUBLIC_POST"
    if is_official:
        return "OFFICIAL_COMPANY_PAGE"
    if any(term in combined for term in ("conference", "speaker", "summit", "webinar", "symposium", "technical")):
        return "CONFERENCE_TECHNICAL"
    if any(domain in host for domain in (
        "autocarpro.in", "manufacturingtodayindia.com", "business-standard.com",
        "economictimes.indiatimes.com", "expresscomputer.in",
    )):
        return "TRADE_MEDIA"
    return "PUBLIC_WEB_BIO"


def _candidate_from_fields(
    *,
    name: str,
    role: str,
    item: Dict[str, Any],
    company_name: str,
    facility_name: str,
    city: str,
    company_domain: str,
) -> Optional[Dict[str, Any]]:
    is_human, _ = is_human_person_candidate(name, company_name=company_name)
    if not is_human:
        return None

    title_raw = str(item.get("title") or "")
    snippet_raw = html.unescape(str(item.get("snippet") or item.get("content") or ""))
    clean_title = re.sub(r"\s+", " ", role).replace(" | LinkedIn", "").replace(" - LinkedIn", "").strip(" ,;:-")
    if not clean_title or len(clean_title) < 3:
        return None
    source_url = str(item.get("url") or "")
    source_type = classify_person_source(source_url, title_raw, company_domain)
    current_employment = classify_current_employment(snippet_raw, title_raw, company_name)
    facility_relationship = classify_facility_relationship(clean_title, snippet_raw, facility_name, city)
    authority_class = classify_authority_class(clean_title, snippet_raw)
    score, confidence = compute_deterministic_person_score(
        current_employment=current_employment,
        facility_relationship=facility_relationship,
        authority_class=authority_class,
        title=clean_title,
        source_quality=source_type,
    )
    return {
        "name": re.sub(r"\s+", " ", name).strip(),
        "title": clean_title,
        "company": company_name,
        "facility": facility_name or city,
        "location": item.get("location") or city or facility_name,
        "source_date": item.get("source_date") or item.get("published_date") or item.get("date") or "",
        "current_employment": current_employment,
        "facility_relationship": facility_relationship,
        "authority_class": authority_class,
        "person_score": score,
        "person_confidence": confidence,
        "source_url": source_url,
        "source_type": source_type,
        "evidence_snippet": snippet_raw[:500],
        **({"source_page": item["source_page"]} if item.get("source_page") else {}),
    }


def extract_person_candidates_from_search_result(
    item: Dict[str, Any],
    company_name: str,
    facility_name: str = "",
    city: str = "",
    company_domain: str = "",
) -> List[Dict[str, Any]]:
    """Extract all plausible named leaders from one public result."""
    title_raw = html.unescape(str(item.get("title") or ""))
    snippet_raw = html.unescape(str(item.get("snippet") or item.get("content") or ""))
    url = str(item.get("url") or "")
    if any(bad in url.lower() for bad in ("wikipedia.org", "britannica.com", "glassdoor.", "ambitionbox.")):
        return []

    cleaned_snippet = re.sub(r"([.!?|•])([A-Z])", r"\1 \2", snippet_raw)
    cleaned_title = re.sub(r"([.!?|•])([A-Z])", r"\1 \2", title_raw)
    combined = re.sub(r"\s+", " ", f"{cleaned_title}. {cleaned_snippet}").strip()

    matches: List[Tuple[str, str]] = []
    comp_clean = re.sub(r"[^\w\s]", " ", company_name.lower())
    comp_tokens = set(t for t in comp_clean.split() if t not in COMPANY_SUFFIX_TOKENS and len(t) > 2)

    if "linkedin.com/in/" in url.lower() or "rocketreach.co/" in url.lower():
        parts = [part.strip() for part in re.split(r"\s+[-–—|•]\s+", cleaned_title) if part.strip() and part.strip().lower() != "linkedin"]
        if parts:
            name_cand = parts[0]
            role_cand = ""
            if len(parts) >= 3:
                p1_tokens = set(re.sub(r"[^\w\s]", " ", parts[1].lower()).split())
                if p1_tokens & comp_tokens:
                    role_cand = parts[2]
                else:
                    role_cand = parts[1]
            elif len(parts) == 2:
                p1_tokens = set(re.sub(r"[^\w\s]", " ", parts[1].lower()).split())
                if p1_tokens & comp_tokens:
                    m_role = re.search(rf"(?i:\b(?:{PERSON_ROLE_PATTERN})\b)", cleaned_snippet)
                    if m_role:
                        role_cand = m_role.group(0)
                    else:
                        role_cand = "Operations / Quality Leadership"
                else:
                    role_cand = parts[1]
            elif len(parts) == 1:
                m_role = re.search(rf"(?i:\b(?:{PERSON_ROLE_PATTERN})\b)", cleaned_snippet)
                role_cand = m_role.group(0) if m_role else "Operations / Quality Leadership"
            if name_cand and role_cand:
                matches.append((name_cand, role_cand))

    role_pattern = rf"(?i:{PERSON_ROLE_PATTERN})"
    patterns = (
        rf"(?P<name>{PERSON_NAME_PATTERN})\s*[-–—|,:]\s*(?P<role>{role_pattern})",
        rf"(?P<role>{role_pattern})\s*[-–—|,:]\s*(?P<name>{PERSON_NAME_PATTERN})",
        rf"(?P<name>{PERSON_NAME_PATTERN})\s+(?i:is|was|serves as|serving as|has joined as|appointed as|named as|promoted to)\s+(?i:the\s+)?(?P<role>{role_pattern})",
        rf"(?i:appoints?|appointed|names?|named)\s+(?P<name>{PERSON_NAME_PATTERN})\s+(?i:as\s+(?:the\s+)?)?(?P<role>{role_pattern})",
        rf"(?P<role>{role_pattern})\s+(?i:at|for|with|in)\s+[^,\.\n]+[,\.\n]\s*(?P<name>{PERSON_NAME_PATTERN})",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, combined):
            matches.append((match.group("name"), match.group("role")))

    candidates: List[Dict[str, Any]] = []
    seen = set()
    for name, role in matches:
        candidate = _candidate_from_fields(
            name=name,
            role=role,
            item=item,
            company_name=company_name,
            facility_name=facility_name,
            city=city,
            company_domain=company_domain,
        )
        if not candidate:
            continue
        key = (_normalize_person_name(candidate["name"]), _normalize_company_name(company_name))
        if key in seen:
            continue
        seen.add(key)
        candidates.append(candidate)
    return candidates


def extract_person_from_search_result(
    item: Dict[str, Any],
    company_name: str,
    facility_name: str = "",
    city: str = "",
    company_domain: str = "",
) -> Optional[Dict[str, Any]]:
    """Compatibility wrapper returning the first extracted person candidate."""
    candidates = extract_person_candidates_from_search_result(
        item,
        company_name=company_name,
        facility_name=facility_name,
        city=city,
        company_domain=company_domain,
    )
    return candidates[0] if candidates else None


def extract_people_from_document_pages(
    pages: List[str],
    source_url: str,
    company_name: str,
    facility_name: str = "",
    city: str = "",
    company_domain: str = "",
    max_candidates: int = 15,
) -> List[Dict[str, Any]]:
    """Extract candidates from public document text with page provenance."""
    candidates: List[Dict[str, Any]] = []
    seen = set()
    limit = min(max(int(max_candidates), 0), 15)
    for page_number, page_text in enumerate(pages, start=1):
        item = {
            "title": f"Annual report page {page_number}",
            "snippet": page_text,
            "url": source_url,
            "source_page": page_number,
        }
        for candidate in extract_person_candidates_from_search_result(
            item,
            company_name=company_name,
            facility_name=facility_name,
            city=city,
            company_domain=company_domain,
        ):
            key = (_normalize_person_name(candidate["name"]), _normalize_company_name(company_name))
            if key in seen:
                continue
            seen.add(key)
            candidates.append(candidate)
            if len(candidates) >= limit:
                return candidates
    return candidates


def extract_people_from_pdf_bytes(
    pdf_bytes: bytes,
    source_url: str,
    company_name: str,
    facility_name: str = "",
    city: str = "",
    company_domain: str = "",
    max_pages: int = 30,
) -> List[Dict[str, Any]]:
    """Parse a bounded public PDF locally; document contents never enter an LLM."""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf_bytes))
    pages = [(page.extract_text() or "") for page in reader.pages[:max(int(max_pages), 0)]]
    return extract_people_from_document_pages(
        pages,
        source_url=source_url,
        company_name=company_name,
        facility_name=facility_name,
        city=city,
        company_domain=company_domain,
    )


def extract_people_from_public_html(
    page_html: str,
    source_url: str,
    company_name: str,
    facility_name: str = "",
    city: str = "",
    company_domain: str = "",
) -> List[Dict[str, Any]]:
    """Extract named leaders from bounded public HTML without an LLM."""
    without_scripts = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", page_html, flags=re.IGNORECASE | re.DOTALL)
    page_text = html.unescape(re.sub(r"<[^>]+>", " ", without_scripts))
    page_text = re.sub(r"\s+", " ", page_text)[:250_000]
    return extract_person_candidates_from_search_result(
        {"title": "Official public page", "snippet": page_text, "url": source_url},
        company_name=company_name,
        facility_name=facility_name,
        city=city,
        company_domain=company_domain,
    )


def _normalize_person_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def _normalize_company_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def generate_deepseek_person_queries(
    company_name: str,
    facility_name: str,
    city: str,
    commercial_trigger: str,
    target_functions: List[str],
    provider: Any,
    max_queries: int = 3,
    queries_already_attempted: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Generate up to five public-search queries; generated text is never evidence."""
    request_payload = {
        "company": company_name,
        "facility": facility_name,
        "city": city,
        "commercial_trigger": commercial_trigger,
        "target_functions": target_functions,
        "max_queries": min(max(int(max_queries), 0), 5),
        "queries_already_attempted": list(queries_already_attempted or []),
    }
    response = provider.complete(
        system_prompt=(
            "Generate targeted public-web search queries for a manufacturing decision maker. "
            "Use only supplied facts. Queries are discovery instructions, never evidence. "
            "Avoid duplicating queries_already_attempted. Return JSON as "
            "{\"queries\": [\"...\"]} with at most five queries."
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
    """Batch-rank known candidates using DeepSeek with a small strict schema and deterministic evidence gating."""
    if not candidates:
        return {
            "candidates": [],
            "assessment_count": 0,
            "usage": {},
            "provider": getattr(provider, "provider", "unknown"),
            "model": getattr(provider, "model_name", getattr(provider, "model", "unknown")),
        }

    cid_to_candidate: Dict[str, Dict[str, Any]] = {}
    public_candidates: List[Dict[str, Any]] = []
    for idx, candidate in enumerate(candidates):
        cid = f"C{idx+1:02d}"
        cid_to_candidate[cid] = candidate
        public_candidates.append({
            "candidate_id": cid,
            "title": candidate.get("title", ""),
            "location": candidate.get("location") or candidate.get("facility", "") or city,
            "evidence": (candidate.get("evidence_snippet") or candidate.get("title") or "")[:250],
        })

    request_payload = {
        "company": company_name,
        "facility": facility_name,
        "city": city,
        "commercial_trigger": commercial_trigger,
        "target_functions": target_functions,
        "candidates": public_candidates,
    }

    system_prompt = (
        "You are an industrial b2b qualification system ranking candidates for commercial outreach "
        "regarding plant quality, testing, calibration, and metrology at the target facility.\n"
        "Rank only the supplied candidates by their candidate_id.\n"
        "Do NOT create people, employment facts, facility relationships, duties, or calibration ownership.\n"
        "Every positive determination must already be supported by supplied candidate evidence.\n"
        "Return ONLY valid JSON matching this schema:\n"
        "{\n"
        '  "ranking": [\n'
        "    {\n"
        '      "candidate_id": "C01",\n'
        '      "rank": 1,\n'
        '      "employment": "SUPPORTED|UNCERTAIN|UNSUPPORTED",\n'
        '      "facility": "SUPPORTED|UNCERTAIN|UNSUPPORTED",\n'
        '      "function": "STRONG|MEDIUM|WEAK",\n'
        '      "authority": "STRONG|MEDIUM|WEAK",\n'
        '      "reason": "max 5 words evidence reason"\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "Keep 'reason' strictly under 5 words per candidate (e.g. 'Plant Head at facility'). Never write long explanations."
    )

    def _execute_completion(prompt_suffix: str = "") -> Any:
        messages = [{"role": "user", "content": json.dumps(request_payload)}]
        if prompt_suffix:
            messages.append({"role": "user", "content": prompt_suffix})
        return provider.complete(
            system_prompt=system_prompt,
            messages=messages,
            response_format="json",
            temperature=0.1,
            max_tokens=2000,
        )

    response = _execute_completion()
    parsed = response.parse_json() or {}
    ranked_items: List[Any] = []
    if isinstance(parsed, dict):
        if "ranking" in parsed and isinstance(parsed["ranking"], list):
            ranked_items = parsed["ranking"]
        elif "ranked_candidates" in parsed and isinstance(parsed["ranked_candidates"], list):
            ranked_items = parsed["ranked_candidates"]
        elif "candidates" in parsed and isinstance(parsed["candidates"], list):
            ranked_items = parsed["candidates"]

    # Controlled retry if empty or malformed (max 1 retry)
    if not ranked_items:
        try:
            retry_response = _execute_completion("Return valid JSON with the ranking key matching the exact schema.")
            retry_parsed = retry_response.parse_json() or {}
            if isinstance(retry_parsed, dict):
                ranked_items = (
                    retry_parsed.get("ranking")
                    or retry_parsed.get("ranked_candidates")
                    or retry_parsed.get("candidates")
                    or []
                )
            if ranked_items:
                response = retry_response
        except Exception:
            pass

    assessments: Dict[str, Dict[str, Any]] = {}
    for item in ranked_items if isinstance(ranked_items, list) else []:
        if not isinstance(item, dict):
            continue
        cid = str(item.get("candidate_id") or "").strip().upper()
        if not cid and "name" in item:
            for k_cid, c_obj in cid_to_candidate.items():
                if _normalize_person_name(c_obj.get("name", "")) == _normalize_person_name(item["name"]):
                    cid = k_cid
                    break
        if cid and cid in cid_to_candidate and cid not in assessments:
            cand = cid_to_candidate[cid]
            rejected_claims = []
            llm_emp = str(item.get("employment", "UNCERTAIN")).upper()
            llm_fac = str(item.get("facility", "UNCERTAIN")).upper()
            det_emp = str(cand.get("current_employment") or "UNKNOWN").upper()
            det_fac = str(cand.get("facility_relationship") or "COMPANY_ONLY").upper()

            # Strict Evidence Rule (Phase 7):
            # 1. Unsupported employment
            if llm_emp == "SUPPORTED" and det_emp == "CONTRADICTED":
                rejected_claims.append("UNSUPPORTED_EMPLOYMENT")
            elif llm_emp == "SUPPORTED" and det_emp == "UNKNOWN":
                clean_comp = re.sub(r"[^\w\s]", " ", company_name.lower())[:8].strip()
                combined_text = f"{cand.get('title', '')} {cand.get('evidence_snippet', '')}".lower()
                if clean_comp and clean_comp not in combined_text:
                    rejected_claims.append("UNSUPPORTED_EMPLOYMENT")

            # 2. Unsupported facility
            if llm_fac == "SUPPORTED":
                if det_fac in ("COMPANY_ONLY", "LOCATION_MISMATCH"):
                    cand_loc = str(cand.get("location") or cand.get("facility") or "").lower()
                    target_city = city.lower()
                    target_cluster = METRO_CLUSTERS.get(target_city, {target_city}) if target_city else set()
                    other_cities = [c for c in KNOWN_MAJOR_CITIES if c in cand_loc and c != target_city and c not in target_cluster]
                    if other_cities:
                        rejected_claims.append("UNSUPPORTED_FACILITY")

            item_copy = dict(item)
            item_copy["candidate_id"] = cid
            item_copy["evidence_verified"] = (len(rejected_claims) == 0)
            item_copy["rejected_claims"] = rejected_claims
            assessments[cid] = item_copy

    ranked_candidates: List[Dict[str, Any]] = []
    for cid, candidate in cid_to_candidate.items():
        candidate_copy = dict(candidate)
        assessment = assessments.get(cid)
        if assessment:
            candidate_copy["deepseek_assessment"] = assessment
            try:
                candidate_copy["deepseek_rank"] = int(assessment.get("rank", 9999))
            except (TypeError, ValueError):
                candidate_copy["deepseek_rank"] = 9999
        else:
            candidate_copy["deepseek_rank"] = 9999
        # Final Deterministic Gate (Phase 8):
        # Confidence is strictly deterministic and never elevated by DeepSeek.
        ranked_candidates.append(candidate_copy)

    ranked_candidates.sort(key=_person_sort_key)
    return {
        "candidates": ranked_candidates,
        "assessment_count": len(assessments),
        "usage": dict(getattr(response, "usage", {}) or {}),
        "provider": getattr(response, "provider", "hive"),
        "model": getattr(response, "model", "deepseek-ai/DeepSeek-V4.1-Flash"),
    }


def _discover_and_rank_decision_makers_legacy(
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


def _person_sort_key(candidate: Dict[str, Any]) -> Tuple[float, int, int, str]:
    authority_index = (
        AUTHORITY_HIERARCHY.index(candidate["authority_class"])
        if candidate.get("authority_class") in AUTHORITY_HIERARCHY else 99
    )
    return (
        -float(candidate.get("person_score") or 0),
        authority_index,
        int(candidate.get("deepseek_rank") or 9999),
        _normalize_person_name(str(candidate.get("name") or "")),
    )


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
    company_domain: str = "",
    sector: str = "",
    use_deepseek_queries: Optional[bool] = None,
    use_deepseek_ranking: Optional[bool] = None,
    deepseek_query_limit: int = 3,
    search_workers: int = 5,
    additional_queries: Optional[List[str]] = None,
    fetch_public_sources: bool = False,
) -> Dict[str, Any]:
    """Discover a broad candidate set while keeping verification deterministic."""
    if search_router is None:
        from services.research_provider import research_router
        search_router = research_router
    if use_deepseek_queries is None:
        use_deepseek_queries = use_deepseek
    if use_deepseek_ranking is None:
        use_deepseek_ranking = use_deepseek

    functions = target_functions or ["Plant Quality", "Metrology", "Plant Head"]
    deterministic_queries = generate_person_search_queries(
        company_name,
        facility_name=facility_name,
        city=city,
        company_domain=company_domain,
        sector=sector,
        target_functions=functions,
    )
    all_candidates: List[Dict[str, Any]] = []
    candidate_indexes: Dict[Tuple[str, str], int] = {}
    public_source_items: Dict[str, Dict[str, Any]] = {}
    telemetry: Dict[str, Any] = {
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
        "query_audit": [],
        "search_errors": [],
        "source_yield": {
            "OFFICIAL_COMPANY_PAGE": 0,
            "ANNUAL_REPORT": 0,
            "COMPANY_PUBLIC_POST": 0,
            "LINKEDIN_SEARCH_SNIPPET": 0,
            "CONFERENCE_TECHNICAL": 0,
            "TRADE_MEDIA": 0,
            "PUBLIC_WEB_BIO": 0,
        },
        "public_source_fetches": [],
    }

    def run_search(index: int, query_object: Dict[str, str]) -> Tuple[int, Dict[str, str], Dict[str, Any]]:
        return index, query_object, search_router.search(query_object["query"], num_results=10)

    def collect_candidates(query_objects: List[Dict[str, str]]) -> None:
        if not query_objects:
            return
        ordered_results: Dict[int, Tuple[Dict[str, str], Dict[str, Any]]] = {}
        worker_count = min(max(int(search_workers), 1), len(query_objects))
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = {
                executor.submit(run_search, index, query_object): (index, query_object)
                for index, query_object in enumerate(query_objects)
            }
            for future in as_completed(futures):
                index, query_object = futures[future]
                try:
                    _, _, search_result = future.result()
                except Exception as error:
                    telemetry["search_errors"].append({
                        "query": query_object["query"],
                        "error": type(error).__name__,
                    })
                    search_result = {"results": [], "error": type(error).__name__}
                ordered_results[index] = (query_object, search_result)

        for index in range(len(query_objects)):
            query_object, search_result = ordered_results[index]
            items = search_result.get("results", []) or []
            telemetry["queries_run"] += 1
            telemetry["results_returned"] += len(items)
            telemetry["query_audit"].append({
                "query": query_object["query"],
                "family": query_object.get("family") or query_object.get("pass") or "UNKNOWN",
                "source_target": query_object.get("source_target") or "PUBLIC_WEB",
                "provider": search_result.get("provider") or "unknown",
                "provider_status": search_result.get("provider_status") or "unknown",
                "results": len(items),
                "error": search_result.get("error"),
            })
            for item in items:
                item_url = str(item.get("url") or "")
                source_type = classify_person_source(item_url, str(item.get("title") or ""), company_domain)
                if (
                    item_url.startswith(("http://", "https://"))
                    and source_type in {"ANNUAL_REPORT", "COMPANY_PUBLIC_POST", "OFFICIAL_COMPANY_PAGE"}
                ):
                    public_source_items.setdefault(item_url, item)
                extracted = extract_person_candidates_from_search_result(
                    item,
                    company_name=company_name,
                    facility_name=facility_name,
                    city=city,
                    company_domain=company_domain,
                )
                telemetry["raw_candidates_extracted"] += len(extracted)
                for candidate in extracted:
                    source_type = candidate.get("source_type") or "PUBLIC_WEB_BIO"
                    telemetry["source_yield"].setdefault(source_type, 0)
                    telemetry["source_yield"][source_type] += 1
                    key = (
                        _normalize_person_name(str(candidate.get("name") or "")),
                        _normalize_company_name(company_name),
                    )
                    existing_index = candidate_indexes.get(key)
                    if existing_index is None:
                        candidate_indexes[key] = len(all_candidates)
                        all_candidates.append(candidate)
                    elif _person_sort_key(candidate) < _person_sort_key(all_candidates[existing_index]):
                        all_candidates[existing_index] = candidate

    collect_candidates(deterministic_queries)

    reused_queries = [
        {
            "query": query,
            "family": "REUSED_DEEPSEEK_QUERY",
            "pass": "REUSED_DEEPSEEK_QUERY",
            "target_role": "LLM_GENERATED_REPLAY",
            "source_target": "PUBLIC_WEB",
        }
        for query in (additional_queries or [])
        if isinstance(query, str) and query.strip()
    ]
    collect_candidates(reused_queries)

    if (use_deepseek_queries or use_deepseek_ranking) and ranking_provider is None:
        from services.llm_provider import get_provider
        ranking_provider = get_provider("hive")

    if use_deepseek_queries:
        try:
            generated = generate_deepseek_person_queries(
                company_name=company_name,
                facility_name=facility_name,
                city=city,
                commercial_trigger=commercial_trigger,
                target_functions=functions,
                provider=ranking_provider,
                max_queries=deepseek_query_limit,
                queries_already_attempted=[query["query"] for query in deterministic_queries],
            )
            telemetry["hive_requests"] += 1
            telemetry["hive_input_tokens"] += int(generated["usage"].get("input_tokens", 0) or 0)
            telemetry["hive_output_tokens"] += int(generated["usage"].get("output_tokens", 0) or 0)
            generated_queries = [
                {
                    "query": query,
                    "family": "DEEPSEEK_QUERY_GENERATION",
                    "pass": "DEEPSEEK_QUERY_GENERATION",
                    "target_role": "LLM_GENERATED",
                    "source_target": "PUBLIC_WEB",
                }
                for query in generated["queries"]
            ]
            telemetry["deepseek_queries_generated"] = len(generated_queries)
            collect_candidates(generated_queries)
        except Exception as error:
            telemetry["deepseek_query_error"] = type(error).__name__

    if fetch_public_sources and public_source_items:
        import requests

        priority = {"ANNUAL_REPORT": 0, "COMPANY_PUBLIC_POST": 1, "OFFICIAL_COMPANY_PAGE": 2}
        selected_items = sorted(
            public_source_items.values(),
            key=lambda item: priority.get(
                classify_person_source(str(item.get("url") or ""), str(item.get("title") or ""), company_domain),
                9,
            ),
        )[:3]
        for item in selected_items:
            source_url = str(item.get("url") or "")
            source_type = classify_person_source(source_url, str(item.get("title") or ""), company_domain)
            fetch_record = {"url": source_url, "source_type": source_type, "status": "FAILED", "candidates": 0}
            try:
                response = requests.get(
                    source_url,
                    timeout=20,
                    headers={"User-Agent": "SalesoorjaPublicResearch/1.0"},
                )
                response.raise_for_status()
                if len(response.content) > 10_000_000:
                    raise ValueError("PUBLIC_SOURCE_TOO_LARGE")
                content_type = str(response.headers.get("content-type") or "").lower()
                if source_type == "ANNUAL_REPORT" or "application/pdf" in content_type:
                    fetched_candidates = extract_people_from_pdf_bytes(
                        response.content,
                        source_url=source_url,
                        company_name=company_name,
                        facility_name=facility_name,
                        city=city,
                        company_domain=company_domain,
                    )
                else:
                    fetched_candidates = extract_people_from_public_html(
                        response.text,
                        source_url=source_url,
                        company_name=company_name,
                        facility_name=facility_name,
                        city=city,
                        company_domain=company_domain,
                    )
                for candidate in fetched_candidates:
                    key = (
                        _normalize_person_name(str(candidate.get("name") or "")),
                        _normalize_company_name(company_name),
                    )
                    existing_index = candidate_indexes.get(key)
                    if existing_index is None:
                        candidate_indexes[key] = len(all_candidates)
                        all_candidates.append(candidate)
                    elif _person_sort_key(candidate) < _person_sort_key(all_candidates[existing_index]):
                        all_candidates[existing_index] = candidate
                    candidate_source = str(candidate.get("source_type") or "PUBLIC_WEB_BIO")
                    telemetry["source_yield"].setdefault(candidate_source, 0)
                    telemetry["source_yield"][candidate_source] += 1
                fetch_record["status"] = "SUCCESS"
                fetch_record["candidates"] = len(fetched_candidates)
            except Exception as error:
                fetch_record["error"] = type(error).__name__
            telemetry["public_source_fetches"].append(fetch_record)

    all_candidates.sort(key=_person_sort_key)
    all_candidates = all_candidates[:15]
    candidates_before_llm = [dict(candidate) for candidate in all_candidates]

    if use_deepseek_ranking and all_candidates:
        try:
            ranked = rank_candidates_with_deepseek(
                company_name=company_name,
                facility_name=facility_name,
                city=city,
                commercial_trigger=commercial_trigger,
                target_functions=functions,
                candidates=all_candidates,
                provider=ranking_provider,
            )
            telemetry["hive_requests"] += 1
            telemetry["hive_input_tokens"] += int(ranked["usage"].get("input_tokens", 0) or 0)
            telemetry["hive_output_tokens"] += int(ranked["usage"].get("output_tokens", 0) or 0)
            ranked_by_name = {
                _normalize_person_name(str(candidate.get("name") or "")): candidate
                for candidate in ranked["candidates"]
            }
            all_candidates = [
                ranked_by_name.get(_normalize_person_name(str(candidate.get("name") or "")), candidate)
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
        except Exception as error:
            telemetry["deepseek_ranking_applied"] = False
            telemetry["deepseek_ranking_error"] = type(error).__name__

    all_candidates.sort(key=_person_sort_key)
    limit = min(max(int(max_candidates), 0), 15)
    returned_candidates = all_candidates[:limit]
    telemetry["candidate_pool_size"] = len(all_candidates)
    telemetry["verified_employment_count"] = sum(
        candidate.get("current_employment") == "VERIFIED" for candidate in all_candidates
    )
    telemetry["high_confidence_count"] = sum(
        candidate.get("person_confidence") == "HIGH" for candidate in all_candidates
    )
    return {
        "primary_person": returned_candidates[0] if returned_candidates else None,
        "secondary_person": returned_candidates[1] if len(returned_candidates) > 1 else None,
        "candidates": returned_candidates,
        "candidates_before_llm": candidates_before_llm,
        "telemetry": telemetry,
    }
