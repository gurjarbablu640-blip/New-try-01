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
from dataclasses import dataclass, field
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
    "carbogen amcis", "carbogen amcis shanghai", "carbogen", "amcis",
    "propulsion systems", "powertrain systems", "quality systems", "chassis systems",
    "committee composition", "committee composition. designation", "composition. designation",
    "committee composition designation", "purchase head", "quality head",
    "midc", "gidc", "riico", "sipcot", "siidc", "kiadb", "hsiidc", "upsidc", "biada",
    "midc sinnar", "midc chakan", "midc satpur", "midc waluj",
}

GENERIC_ROLE_PHRASES = {
    "operations leadership team", "head of plant operations", "quality team",
    "plant head", "quality manager", "general manager", "vice president",
    "director of operations", "executive director", "managing director",
    "head quality", "qa manager", "qc manager", "plant operations",
    "quality head", "purchase head", "head purchase", "procurement head",
    "operations head", "operations team", "leadership team", "management team",
    "maintenance manager", "calibration manager", "metrology manager",
    "head qa", "head qc", "head of quality", "director quality",
    "supply chain head", "hr head", "business head",
}

GENERIC_ROLE_TOKENS = {
    "head", "manager", "director", "lead", "leader", "chief", "officer",
    "executive", "president", "vp", "gm", "avp", "dgm", "agm", "supervisor",
    "coordinator", "administrator", "specialist", "consultant", "advisor",
    "analyst", "engineer", "technician", "inspector", "auditor", "operator",
    "buyer", "incharge", "controller", "leadership", "officers", "personnel",
}

FUNCTION_AND_DEPT_TOKENS = {
    "quality", "qa", "qc", "qms", "purchase", "procurement", "sourcing",
    "operations", "plant", "works", "factory", "facility", "maintenance",
    "metrology", "calibration", "instrumentation", "testing", "inspection",
    "production", "manufacturing", "supply", "chain", "logistics", "stores",
    "safety", "ehs", "hse", "compliance", "regulatory", "engineering", "commercial",
    "systems", "subsystems", "division", "department", "dept", "team",
}

SUBSYSTEM_TOKENS = {
    "propulsion", "powertrain", "chassis", "aerodynamics", "telematics",
    "infotainment", "firmware", "hydraulics", "pneumatics", "avionics",
    "battery", "batteries", "substation", "transmission", "metallurgy",
}

GOVERNANCE_TERMS = {
    "committee", "composition", "designation", "remuneration", "nomination",
    "stakeholders", "stakeholder", "shareholding", "independent", "governance",
    "directors", "secretarial", "resolution", "agenda", "minutes", "charter",
}

FOREIGN_AND_CORP_ENTITIES = {
    "carbogen", "amcis", "shanghai", "beijing", "suzhou", "shenzhen",
    "guangzhou", "tokyo", "singapore", "malaysia", "germany", "switzerland",
    "basel", "aarau", "manchester", "london", "seattle", "detroit", "chicago",
}

RECRUITMENT_TERMS = {
    "walk-in", "walkin", "interview", "urgent", "requirement", "openings",
    "opening", "vacancies", "vacancy", "careers", "career", "hiring",
    "recruitment", "immediate", "joiner", "apply", "job", "jobs",
}

COMPANY_SUFFIX_TOKENS = {
    "limited", "ltd", "private", "pvt", "corp", "corporation", "inc", "incorporated",
    "industries", "energy", "enterprises", "solutions", "technologies", "automotive",
    "forgings", "engineering", "india", "group", "co", "company", "holdings",
}

GENERIC_FACILITY_TOKENS = {
    "plant", "facility", "works", "unit", "manufacturing", "complex",
    "division", "factory", "site", "headquarters", "office", "operations",
}


# ── Phase 5: Human Validation ────────────────────────────────────────────────
def is_human_person_candidate(name_str: str, company_name: str = "") -> Tuple[bool, str]:
    """Validate whether candidate string represents a genuine human decision-maker.

    Rejects: generic role phrases, departments, technical subsystems, governance headings,
             corporate/subsidiary entities, foreign locations, job listing terms.
    Preserves: Indian initials, honorifics, compound names, and regional formats.
    """
    clean = (name_str or "").strip()
    if not clean:
        return False, "Candidate name is empty"

    # Remove trailing company/title fragments if separated by dash or pipe
    clean = re.split(r"\s*[-–—|•]\s*", clean)[0].strip()

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

    tokens_lower = [t.lower() for t in tokens]

    # 3. Reject technical subsystems (e.g. 'Propulsion Systems')
    if any(t in SUBSYSTEM_TOKENS for t in tokens_lower):
        return False, f"Candidate name '{clean}' contains engineering subsystem/technical domain term"

    # 4. Reject governance / table heading artifacts (e.g. 'Committee Composition. Designation')
    if any(t in GOVERNANCE_TERMS for t in tokens_lower):
        return False, f"Candidate name '{clean}' contains corporate governance or document heading term"

    # 5. Reject foreign locations and corporate subsidiary names (e.g. 'CARBOGEN AMCIS Shanghai')
    if any(t in FOREIGN_AND_CORP_ENTITIES for t in tokens_lower):
        return False, f"Candidate name '{clean}' matches corporate entity, CDMO, or foreign geography"

    # 6. Reject recruitment / job listing terms
    if any(t in RECRUITMENT_TERMS for t in tokens_lower):
        return False, f"Candidate name '{clean}' contains recruitment/job listing phrase"

    # 7. Reject if ALL meaningful tokens are generic role or functional department tokens
    honorifics = {"mr", "dr", "mrs", "ms", "shri", "smt", "prof", "er"}
    non_honorific_tokens = [t for t in tokens_lower if t not in honorifics]
    if non_honorific_tokens and all(
        (t in GENERIC_ROLE_TOKENS or t in FUNCTION_AND_DEPT_TOKENS or t in COMPANY_SUFFIX_TOKENS)
        for t in non_honorific_tokens
    ):
        return False, f"Candidate name '{clean}' is a combination of generic role and department phrases"

    # Reject if any token is a company suffix or department indicator
    dept_tokens = {"department", "dept", "team", "leadership", "management", "assurance", "operations", "division"}
    if any(t in COMPANY_SUFFIX_TOKENS for t in tokens_lower):
        return False, f"Contains corporate/company suffix token: {clean}"
    if any(t in dept_tokens for t in tokens_lower):
        return False, f"Contains departmental/team term: {clean}"
    if any(t in NON_HUMAN_ENTITIES for t in tokens_lower):
        return False, f"Contains non-human entity token: {clean}"

    facility_terms = {"plant", "complex", "facility", "works", "factory", "refinery", "smelter", "foundry", "mill", "unit", "campus", "estate"}
    if any(t in facility_terms for t in tokens_lower):
        return False, f"Contains facility/plant term: {clean}"

    estate_terms = {
        "midc", "gidc", "riico", "sipcot", "siidc", "kiadb", "hsiidc", "upsidc", "biada",
        "dicc", "sez", "sinnar", "satpur", "chakan", "bhosari", "talegaon", "oragadam",
        "sriperumbudur", "waluj", "shendra", "butibori", "pithampur", "peenya",
    }
    if any(t in estate_terms for t in tokens_lower):
        return False, f"Candidate name '{clean}' contains industrial estate / development corporation term"


    # Reject location/city combinations with all-caps business acronyms (e.g. 'TPI CRSS Nashik')
    if any(t in INDIAN_CITIES_TO_STATE for t in tokens_lower):
        raw_non_city = [w for w in tokens if w.lower() not in INDIAN_CITIES_TO_STATE and w.lower() not in honorifics]
        if raw_non_city and all(w.isupper() or len(w) <= 3 for w in raw_non_city):
            return False, f"Candidate name '{clean}' is a facility or branch acronym with city name"

    # 8. Company name match
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

    # 9. Characters / symbols check
    if re.search(r"[\d@:/\\_<>{}\[\]\*\+=#\$%^&~®™©|!?;,]", clean):
        return False, "Contains digits or punctuation invalid for human names"

    # Check for invalid internal periods (dots allowed only on initials or honorifics)
    raw_words = clean.split()
    for w in raw_words:
        if "." in w:
            w_strip = w.rstrip(".").lower()
            # If word is not a single initial (1 char) and not a recognized honorific
            if len(w_strip) > 1 and w_strip not in honorifics:
                return False, f"Contains invalid sentence/table period in token: {w}"

    # 10. Token length check (allow 2 to 4 tokens, plus optional honorific)
    meaningful_tokens = [t for t in tokens if t.lower() not in honorifics]

    if len(meaningful_tokens) < 2:
        return False, f"Candidate name '{clean}' has fewer than 2 meaningful tokens"

    if len(meaningful_tokens) > 5:
        return False, f"Candidate name '{clean}' has too many tokens; likely a phrase or title"

    # 11. Reject SEO / web page title terms
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

    fac_clean = ""
    if facility_name:
        fac_tokens = [w for w in re.findall(r"\b\w+\b", facility_name) if w.lower() not in GENERIC_FACILITY_TOKENS]
        fac_clean = " ".join(fac_tokens).strip()

    # Tier 1: Target Facility LinkedIn Profile & Role Searches (Priority 1)
    if city:
        add(f'site:linkedin.com/in "{clean_company}" "{city}" quality', "FACILITY_LINKEDIN", f"{city} quality", "LINKEDIN_PUBLIC")
        add(f'"{clean_company}" "{city}" ("quality head" OR "quality manager" OR "plant quality")', "FACILITY_ROLE", f"{city} quality", "PUBLIC_WEB")
    if fac_clean and fac_clean.lower() != (city or "").lower():
        add(f'site:linkedin.com/in "{clean_company}" "{fac_clean}" quality', "FACILITY_LINKEDIN", f"{fac_clean} quality", "LINKEDIN_PUBLIC")
        add(f'"{clean_company}" "{fac_clean}" ("quality head" OR "plant head")', "FACILITY_ROLE", f"{fac_clean} quality", "PUBLIC_WEB")

    # Tier 2: Official Website & Document/PDF Searches (Priority 2)
    if clean_domain and city:
        add(f'site:{clean_domain} "{city}" quality', "OFFICIAL_FACILITY", f"{city} quality", "OFFICIAL_WEBSITE")
    if clean_domain and fac_clean:
        add(f'site:{clean_domain} filetype:pdf ("{fac_clean}" OR "{city}")', "OFFICIAL_DOCUMENT", f"{fac_clean} pdf", "DOCUMENT_OR_EVENT")
    elif clean_domain:
        add(f'site:{clean_domain} filetype:pdf ("plant" OR "quality")', "OFFICIAL_DOCUMENT", "quality pdf", "DOCUMENT_OR_EVENT")
    if city or fac_clean:
        loc_term = f'"{city}"' if city else f'"{fac_clean}"'
        add(f'"{clean_company}" filetype:pdf {loc_term} quality', "DOCUMENT_PDF", "plant quality pdf", "DOCUMENT_OR_EVENT")

    # Tier 3: Public Company Posts & Events (TPM / Awards / Inaugurations) (Priority 3)
    if city or fac_clean:
        loc_term = f'"{city}"' if city else f'"{fac_clean}"'
        add(f'site:linkedin.com/posts "{clean_company}" {loc_term} quality', "COMPANY_POSTS", "post quality", "COMPANY_POST")
        add(f'"{clean_company}" {loc_term} (TPM OR "quality award" OR "speaker quality")', "EVENT_AND_AWARDS", "events and awards", "DOCUMENT_OR_EVENT")

    # Tier 4: Corporate & Group Quality Leaders (for Group-Level Fallback Route) (Priority 4)
    add(f'"{clean_company}" ("group quality head" OR "corporate quality" OR "VP Quality" OR "Head Quality")', "GROUP_QUALITY", "group quality", "PUBLIC_WEB")
    add(f'site:linkedin.com/in "{clean_company}" ("head of quality" OR "quality director")', "GROUP_QUALITY_LINKEDIN", "head of quality", "LINKEDIN_PUBLIC")

    # Tier 5: Canonical Broad Plant & Quality Roles (Priority 5)
    for role in (
        "plant quality", "quality manager", "head quality", "quality head",
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
        fac_tokens = [w for w in re.findall(r"\b\w+\b", facility_name) if w.lower() not in GENERIC_FACILITY_TOKENS]
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
STRONG_CURRENT_PATTERNS = [
    r"\bpresent\b",
    r"\bcurrently\b",
    r"\bcurrent\s+role\b",
    r"\bcurrently\s+(?:serves|serving|working|leads|heading|at|with)\b",
    r"\bserves\s+as\b",
    r"\bworking\s+at\b",
    r"\b(?:202[0-6]|jan\s+202[0-6]|feb\s+202[0-6]|mar\s+202[0-6]|apr\s+202[0-6]|may\s+202[0-6]|jun\s+202[0-6]|jul\s+202[0-6]|aug\s+202[0-6]|sep\s+202[0-6]|oct\s+202[0-6]|nov\s+202[0-6]|dec\s+202[0-6])\s*[-–—to]+\s*present\b",
    r"\b202[4-6]\s*[-–—to]+\s*present\b",
    r"experience:\s*.*?\bpresent\b",
    r"\bleads\s+the\b",
    r"\bresponsible\s+for\b",
]


def classify_current_employment(snippet: str, title: str, company_name: str) -> str:
    """Classify current employment status from public evidence.

    Values: VERIFIED, PROBABLE, UNKNOWN, STALE, CONTRADICTED.
    Strict rule: Retrieval date or page year alone does NOT create VERIFIED without
    an explicit current-employment signal (Present, Currently, current role, serves as, etc.).
    """
    clean_title = (title or "").strip()
    clean_snippet = (snippet or "").strip()
    combined = f"{clean_title} {clean_snippet}".lower()

    comp_clean = re.sub(r"\b(limited|ltd|private|pvt|corp|corporation|inc)\b", "", company_name.lower()).strip()
    base_comp = re.sub(
        r"\s+(?:India|Technologies|Solutions|Industries|Limited|Ltd|Pvt\s+Ltd|Private\s+Limited)\b.*",
        "",
        company_name,
        flags=re.IGNORECASE,
    ).strip().lower()
    comp_tokens = set(t for t in comp_clean.split() if len(t) > 2)
    if not comp_tokens and base_comp:
        comp_tokens = set(t for t in base_comp.split() if len(t) > 2)

    def is_target_comp(c_str: str) -> bool:
        c_str_lower = c_str.lower()
        if comp_clean and comp_clean[:6] in c_str_lower:
            return True
        if base_comp and len(base_comp) >= 3 and base_comp in c_str_lower:
            return True
        if any(t in c_str_lower for t in comp_tokens):
            return True
        return False

    explicit_current = re.search(
        r"\bcurrently\s+(?:working\s+)?(?:at|with)\s+([^|.;]+)",
        combined,
    )
    if explicit_current:
        return "VERIFIED" if is_target_comp(explicit_current.group(1)) else "CONTRADICTED"

    present_experiences = re.findall(
        r"experience:\s*([^|.]+)\|[^.]{0,180}\bpresent\b",
        combined,
    )
    if any(is_target_comp(company) for company in present_experiences):
        return "VERIFIED"
    if present_experiences:
        return "CONTRADICTED"

    # 1. Direct Contradiction via Title headline: "@<Company>" or "at <Company>"
    headline_match = re.search(r"(?:@|\bat\s+)\s*([A-Za-z0-9\s&.-]{3,35})(?:\s*[-–—|•,]|\s*I\s*|\.\s|$)", clean_title)
    if headline_match:
        other_comp = headline_match.group(1).strip()
        other_lower = other_comp.lower()
        if (
            other_lower not in {"linkedin", "home", "work", "india", "plant"}
            and not any(w in other_lower for w in ["plant", "facility", "works", "factory", "site", "unit", "complex", "division", "location"])
            and not other_lower.startswith(("our ", "the ", "its "))
            and len(other_comp) >= 3
        ):
            if not is_target_comp(other_comp):
                return "CONTRADICTED"

    # 2. Contradicted via Snippet headline / current role
    snip_headline = re.search(r"^(?:[A-Za-z\s/&-]+)\s+(?:at|@)\s+([A-Za-z0-9\s&.-]+?)(?:\s*[-–—|•]|\.\s|$)", clean_snippet)
    if snip_headline:
        other_comp = snip_headline.group(1).strip()
        other_lower = other_comp.lower()
        if (
            other_lower not in {"linkedin", "home", "work", "india", "plant"}
            and not any(w in other_lower for w in ["plant", "facility", "works", "factory", "site", "unit", "complex", "division", "location"])
            and not other_lower.startswith(("our ", "the ", "its "))
            and not is_target_comp(other_comp)
        ):
            return "CONTRADICTED"

    # 3. Explicit former / past employment patterns for target company
    former_patterns = [
        r"\b(?:former|formerly|ex-|past|previously|prior to)\b.*?\b" + re.escape(base_comp),
        r"\b" + re.escape(base_comp) + r"\b.*?\buntil\s+(?:20\d{2}|19\d{2})",
        r"\b" + re.escape(base_comp) + r"\b.*?\btill\s+(?:20\d{2}|19\d{2})",
        r"\bpreviously\s+(?:worked|served|managed|held)\b",
        r"\bleft\s+" + re.escape(base_comp),
    ]
    for fp in former_patterns:
        if re.search(fp, combined):
            return "CONTRADICTED"

    # 4. Closed date ranges for target company ending in past (<= 2024)
    closed_date_patterns = [
        r"\b" + re.escape(base_comp) + r"[\w\s,()·–-]{0,50}\b(?:19\d{2}|20[01]\d|202[0-4])\s*[-–—to]+\s*(?:19\d{2}|20[01]\d|202[0-4])\b",
        r"\b(?:19\d{2}|20[01]\d|202[0-4])\s*[-–—to]+\s*(?:19\d{2}|20[01]\d|202[0-4])\b[\w\s,()·–-]{0,50}\b" + re.escape(base_comp),
    ]
    for cdp in closed_date_patterns:
        if re.search(cdp, combined):
            return "CONTRADICTED"

    # 5. Experience present at another company
    exp_present = re.search(r"experience:\s*([A-Za-z0-9\s&.-]+?)(?:\s*·|\s*\()(?:\bpresent\b|\bcurrent\b)", combined)
    if exp_present:
        curr_exp_comp = exp_present.group(1).strip()
        if curr_exp_comp and not is_target_comp(curr_exp_comp):
            return "CONTRADICTED"

    curr_at = re.search(r"\bcurrently\s+(?:at|with|working\s+at)\s+([A-Za-z0-9\s&.-]+)", combined)
    if curr_at:
        curr_at_comp = curr_at.group(1).strip()
        if curr_at_comp and not is_target_comp(curr_at_comp):
            return "CONTRADICTED"

    # 6. Target company verification
    has_company = is_target_comp(combined)
    if not has_company:
        return "UNKNOWN"

    has_experience_target = bool(
        (base_comp and len(base_comp) >= 3 and re.search(r"experience:\s*.*?" + re.escape(base_comp), combined))
        or (comp_clean and len(comp_clean) >= 3 and re.search(r"experience:\s*.*?" + re.escape(comp_clean[:8]), combined))
    )
    has_strong_present = any(re.search(pt, combined) for pt in STRONG_CURRENT_PATTERNS) or has_experience_target
    has_recent_year = any(y in combined for y in ["2024", "2025", "2026", "fy 25", "fy 26", "fy25", "fy26"])

    # Strict: Only explicit current-employment signals create VERIFIED
    if has_strong_present:
        return "VERIFIED"

    # Page date or recent year without explicit present is PROBABLE, never VERIFIED
    if has_recent_year:
        return "PROBABLE"

    return "UNKNOWN"




INDIAN_CITIES_TO_STATE = {
    # Gujarat
    "sanand": "gujarat", "ahmedabad": "gujarat", "waghodia": "gujarat", "vadodara": "gujarat",
    "baroda": "gujarat", "dahej": "gujarat", "bharuch": "gujarat", "halol": "gujarat",
    "panchmahal": "gujarat", "chikhli": "gujarat", "navsari": "gujarat", "surat": "gujarat",
    "rajkot": "gujarat", "metoda": "gujarat", "morbi": "gujarat", "hazira": "gujarat",
    "hansalpur": "gujarat", "kutch": "gujarat", "mundra": "gujarat", "ankleshwar": "gujarat",
    # Karnataka
    "dharwad": "karnataka", "hubli": "karnataka", "bengaluru": "karnataka", "bangalore": "karnataka",
    "peenya": "karnataka", "devanahalli": "karnataka", "bidadi": "karnataka", "hoskote": "karnataka",
    "mysuru": "karnataka", "mysore": "karnataka", "belagavi": "karnataka", "belgaum": "karnataka",
    # Himachal Pradesh
    "baddi": "himachal pradesh", "nalagarh": "himachal pradesh", "barotiwala": "himachal pradesh",
    "solan": "himachal pradesh", "kala amb": "himachal pradesh", "paonta sahib": "himachal pradesh",
    # Uttar Pradesh / NCR
    "noida": "uttar pradesh", "greater noida": "uttar pradesh", "ghaziabad": "uttar pradesh",
    "lucknow": "uttar pradesh", "kanpur": "uttar pradesh", "aligarh": "uttar pradesh",
    # Haryana
    "bawal": "haryana", "manesar": "haryana", "gurugram": "haryana", "gurgaon": "haryana",
    "faridabad": "haryana", "panipat": "haryana", "sonipat": "haryana", "rohtak": "haryana",
    # Maharashtra
    "pune": "maharashtra", "chakan": "maharashtra", "bhosari": "maharashtra", "talegaon": "maharashtra",
    "ranjangaon": "maharashtra", "mumbai": "maharashtra", "navi mumbai": "maharashtra", "thane": "maharashtra",
    "kagal": "maharashtra", "kolhapur": "maharashtra", "aurangabad": "maharashtra", "chhatrapati sambhajinagar": "maharashtra",
    "nagpur": "maharashtra", "nashik": "maharashtra", "tarapur": "maharashtra", "waluj": "maharashtra",
    # Tamil Nadu
    "chennai": "tamil nadu", "oragadam": "tamil nadu", "sriperumbudur": "tamil nadu", "maraimalai nagar": "tamil nadu",
    "irungattukottai": "tamil nadu", "hosur": "tamil nadu", "coimbatore": "tamil nadu", "krishnagiri": "tamil nadu",
    "pochampalli": "tamil nadu", "ranipet": "tamil nadu",
    # Telangana / Andhra Pradesh
    "hyderabad": "telangana", "mahbubnagar": "telangana", "divitipally": "telangana", "adibatla": "telangana",
    "kongara kalan": "telangana", "raviryala": "telangana", "medchal": "telangana", "patancheru": "telangana",
    "sri city": "andhra pradesh", "kakinada": "andhra pradesh", "visakhapatnam": "andhra pradesh", "vizag": "andhra pradesh",
    # Rajasthan
    "alwar": "rajasthan", "ghiloth": "rajasthan", "neemrana": "rajasthan", "bhiwadi": "rajasthan",
    "jaipur": "rajasthan", "udaipur": "rajasthan",
    # West Bengal / Jharkhand / Odisha
    "kolkata": "west bengal", "asansol": "west bengal", "jamuria": "west bengal", "durgapur": "west bengal",
    "jamshedpur": "jharkhand", "ranchi": "jharkhand", "bokaro": "jharkhand", "baliguma": "jharkhand",
    "bhubaneswar": "odisha", "rourkela": "odisha", "jharsuguda": "odisha",
    # Madhya Pradesh
    "indore": "madhya pradesh", "pithampur": "madhya pradesh", "bhopal": "madhya pradesh", "mandideep": "madhya pradesh",
}

KNOWN_MAJOR_CITIES = set(INDIAN_CITIES_TO_STATE.keys())

METRO_CLUSTERS = {
    "sanand": {"ahmedabad", "sanand", "gujarat"},
    "ahmedabad": {"ahmedabad", "sanand", "gujarat"},
    "hansalpur": {"hansalpur", "ahmedabad", "gujarat"},
    "waghodia": {"waghodia", "vadodara", "baroda", "gujarat"},
    "vadodara": {"waghodia", "vadodara", "baroda", "gujarat"},
    "halol": {"halol", "panchmahal", "vadodara", "gujarat"},
    "dahej": {"dahej", "bharuch", "gujarat"},
    "bharuch": {"dahej", "bharuch", "gujarat"},
    "jamuria": {"jamuria", "asansol", "paschim bardhaman", "west bengal"},
    "baliguma": {"baliguma", "jamshedpur", "jharkhand"},
    "jamshedpur": {"baliguma", "jamshedpur", "jharkhand"},
    "oragadam": {"oragadam", "sriperumbudur", "chennai", "tamil nadu"},
    "chennai": {"oragadam", "sriperumbudur", "chennai", "tamil nadu"},
    "baddi": {"baddi", "nalagarh", "solan", "himachal pradesh"},
    "dharwad": {"dharwad", "hubli", "karnataka"},
    "kagal": {"kagal", "kolhapur", "maharashtra"},
    "peenya": {"peenya", "bengaluru", "bangalore", "karnataka"},
    "bengaluru": {"peenya", "devanahalli", "bidadi", "bengaluru", "bangalore", "karnataka"},
    "hosur": {"hosur", "krishnagiri", "dharmapuri", "tamil nadu"},
    "nashik": {"nashik", "sinnar", "satpur", "ambad", "maharashtra"},
    "sinnar": {"nashik", "sinnar", "malegaon", "maharashtra"},
    "hyderabad": {"hyderabad", "kongara kalan", "rangareddy", "shamshabad", "telangana"},
    "kongara kalan": {"hyderabad", "kongara kalan", "rangareddy", "shamshabad", "telangana"},
}


def generate_facility_aliases(
    facility_name: str,
    city: str,
    state: str = "",
) -> List[str]:
    """Generates precise facility aliases before person verification (Phase 2).

    Includes:
    - cleaned facility name (excluding generic prefixes like 'in', 'plant', 'facility')
    - industrial estate / MIDC / GIDC / SIPCOT / KIADB / SEZ tokens
    - district / metro cluster names
    - nearest industrial town / cluster

    Crucial rule: state-only match is NEVER an alias.
    """
    aliases: List[str] = []
    t_city = (city or "").strip()
    t_fac = (facility_name or "").strip()
    t_state = (state or "").strip()
    if not t_state and t_city.lower() in INDIAN_CITIES_TO_STATE:
        t_state = INDIAN_CITIES_TO_STATE[t_city.lower()]

    # 1. Cleaned facility name
    # e.g. "In Nashik Plant" -> "Nashik"
    # "Hosur Plant" -> "Hosur"
    # "Kongara Kalan Facility" -> "Kongara Kalan"
    clean_fac = re.sub(r"\b(in|the|plant|facility|works|unit|factory|ltd|limited|campus)\b", "", t_fac, flags=re.IGNORECASE).strip()
    clean_fac = " ".join(clean_fac.split())
    if clean_fac and len(clean_fac) >= 3 and clean_fac.lower() != t_state.lower():
        aliases.append(clean_fac)

    # 2. City
    if t_city and t_city.lower() != t_state.lower() and t_city not in aliases:
        aliases.append(t_city)

    # 3. Known metro / industrial clusters
    c_lower = t_city.lower()
    if c_lower in METRO_CLUSTERS:
        for cl_item in METRO_CLUSTERS[c_lower]:
            cl_title = cl_item.title()
            if cl_item != t_state.lower() and cl_title not in aliases and len(cl_item) >= 3:
                aliases.append(cl_title)

    # 4. Explicit industrial estate / zone patterns in facility name
    zone_matches = re.findall(r"\b(sipcot|midc|gidc|sez|kiadb|tsiic|riico|biocon park|fab city|malegaon)\b", t_fac.lower())
    for zm in zone_matches:
        zm_str = zm.upper()
        if zm_str not in aliases:
            aliases.append(zm_str)
        if t_city:
            combo = f"{t_city} {zm_str}"
            if combo not in aliases:
                aliases.append(combo)

    # 5. State-specific industrial estate designations
    st_lower = t_state.lower()
    if t_city:
        if st_lower == "maharashtra":
            midc_alias = f"{t_city} MIDC"
            if midc_alias not in aliases:
                aliases.append(midc_alias)
        elif st_lower == "gujarat":
            gidc_alias = f"{t_city} GIDC"
            if gidc_alias not in aliases:
                aliases.append(gidc_alias)
        elif st_lower == "tamil nadu":
            sipcot_alias = f"{t_city} SIPCOT"
            if sipcot_alias not in aliases:
                aliases.append(sipcot_alias)
        elif st_lower == "karnataka":
            kiadb_alias = f"{t_city} KIADB"
            if kiadb_alias not in aliases:
                aliases.append(kiadb_alias)
        elif st_lower == "telangana":
            sez_alias = f"{t_city} SEZ"
            if sez_alias not in aliases:
                aliases.append(sez_alias)

    # Deduplicate preserving order (excluding state-only names)
    dedup: List[str] = []
    for a in aliases:
        if a and a not in dedup and a.lower() != t_state.lower():
            dedup.append(a)

    return dedup


def classify_facility_relationship(
    candidate_title: str,
    candidate_text: str,
    target_facility: str,
    target_city: str,
    target_state: str = "",
    facility_aliases: Optional[List[str]] = None,
) -> str:
    """Classify relationship between candidate and the target manufacturing facility.

    Values:
    FACILITY_OWNER: Direct head/manager of target plant.
    FACILITY_FUNCTION_OWNER: Direct QA/metrology/operations head at target facility.
    GROUP_FUNCTION_OWNER: Corporate or group-level quality/operations leader.
    OTHER_FACILITY_OWNER: Owner/manager of a DIFFERENT facility (contradiction).
    FACILITY_CONTRADICTED: Explicitly located at a different facility/city/state.
    FUNCTIONALLY_RELEVANT: Relevant role, facility link unverified.
    COMPANY_ONLY: Generic company link.
    UNKNOWN: Indeterminate.
    """
    clean_text = f"{candidate_title} {candidate_text}".lower()
    t_city = target_city.lower().strip() if target_city else ""
    t_fac = target_facility.lower().strip() if target_facility else ""
    t_state = target_state.lower().strip() if target_state else ""

    if not t_state and t_city in INDIAN_CITIES_TO_STATE:
        t_state = INDIAN_CITIES_TO_STATE[t_city]

    is_group = any(w in candidate_title.lower() for w in ["group", "corporate", "global", "chief", "vice president", "vp"]) or any(
        re.search(rf"\b{re.escape(term)}\b", candidate_title.lower())
        for term in ["head of quality", "head quality", "director quality", "director - quality", "head - quality", "manufacturing quality head"]
    )
    is_plant_head = any(w in candidate_title.lower() for w in ["plant head", "works manager", "factory manager", "unit head", "site head"])
    is_quality = any(w in candidate_title.lower() for w in ["quality", "qa", "qc", "metrology", "calibration"])

    designator_pattern = re.compile(
        r"\b(?:plant|unit|factory|facility|works|site)\s*(?:no\.?|number|#)?\s*[-:/]?\s*([ivxlcdm]+|\d+[a-z]?)\b",
        re.IGNORECASE,
    )
    target_designators = {match.casefold() for match in designator_pattern.findall(t_fac)}
    candidate_designators = {match.casefold() for match in designator_pattern.findall(clean_text)}
    if target_designators and candidate_designators and target_designators.isdisjoint(candidate_designators):
        if is_plant_head or any(
            word in candidate_title.lower()
            for word in ("head", "manager", "quality", "operations", "manufacturing", "production", "maintenance")
        ):
            return "OTHER_FACILITY_OWNER"
        return "FACILITY_CONTRADICTED"

    # Extract non-generic facility tokens
    fac_tokens = [w for w in t_fac.split() if len(w) >= 4 and w not in GENERIC_FACILITY_TOKENS]

    # Target cluster
    target_cluster = set(METRO_CLUSTERS.get(t_city, {t_city})) if t_city else set()
    if t_state:
        target_cluster.add(t_state)
    for w in fac_tokens:
        if w in INDIAN_CITIES_TO_STATE:
            target_cluster.add(w)
            target_cluster.add(INDIAN_CITIES_TO_STATE[w])

    if facility_aliases:
        for al in facility_aliases:
            al_clean = al.strip().lower()
            if al_clean and al_clean != t_state:
                target_cluster.add(al_clean)
                for part in al_clean.split():
                    if len(part) >= 4 and part not in GENERIC_FACILITY_TOKENS and part != t_state:
                        target_cluster.add(part)

    city_match = bool(t_city and (t_city in clean_text or any(c in clean_text for c in target_cluster if c != t_state)))
    fac_match = bool(
        (fac_tokens and any(w in clean_text for w in fac_tokens))
        or (facility_aliases and any(a.lower() in clean_text for a in facility_aliases if a.lower() != t_state))
    )

    # Detect explicit foreign/other city contradiction
    other_cities = [
        c for c, s in INDIAN_CITIES_TO_STATE.items()
        if re.search(rf"\b{c}\b", clean_text)
        and c not in target_cluster
        and (not t_state or s != t_state or c != t_city)
    ]

    # Contradiction check:
    if other_cities and not city_match and not fac_match:
        # Candidate explicitly located in a different Indian city / state
        if is_group and is_quality:
            return "GROUP_FUNCTION_OWNER"
        if is_plant_head or "plant" in candidate_title.lower() or "head of plant" in clean_text:
            return "OTHER_FACILITY_OWNER"
        return "FACILITY_CONTRADICTED"

    if (city_match or fac_match) and is_plant_head:
        return "FACILITY_OWNER"

    if (city_match or fac_match) and is_quality:
        return "FACILITY_FUNCTION_OWNER"

    if is_group and is_quality:
        return "GROUP_FUNCTION_OWNER"

    if is_plant_head:
        return "OTHER_FACILITY_OWNER" if t_city else "FACILITY_OWNER"

    if is_quality:
        return "FUNCTIONALLY_RELEVANT"

    if any(w in candidate_title.lower() for w in ["operations", "manufacturing", "production", "maintenance"]):
        return "FUNCTIONALLY_RELEVANT"

    return "COMPANY_ONLY"


def classify_authority_class(title: str, snippet: str = "") -> str:
    """Classify the person into Salesoorja priority authority hierarchy."""
    clean = f"{title} {snippet}".lower()
    t_clean = title.lower()

    # Detect junior individual contributors without decision authority
    junior_roles = [
        "qa engineer", "qc engineer", "quality engineer", "calibration engineer",
        "metrology engineer", "graduate engineer trainee", "get", "intern",
        "trainee", "executive quality", "quality executive", "technician",
        "junior engineer", "inspection engineer", "associate engineer",
    ]
    has_junior = any(re.search(rf"\b{re.escape(jr)}\b", t_clean) for jr in junior_roles)
    has_leadership = any(w in t_clean for w in [
        "head", "manager", "lead", "director", "chief", "vp", "president",
        "incharge", "dgm", "agm", "gm", "works manager", "plant head", "site head"
    ])
    if has_junior and not has_leadership:
        return "JUNIOR_IC"

    if any(w in clean for w in ["calibration lab", "calibration incharge", "head calibration"]):
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
    elif facility_relationship in ("OTHER_FACILITY_OWNER", "FACILITY_CONTRADICTED"):
        score_fac = 0.0
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
    elif authority_class == "JUNIOR_IC":
        score_fn = 6.0
    else:
        score_fn = 2.0

    # 4. Authority Level (0-15)
    t_lower = title.lower()
    if authority_class == "JUNIOR_IC":
        score_auth = 2.0
    elif any(w in t_lower for w in ["vp", "vice president", "director", "head", "general manager", "gm", "plant head"]):
        score_auth = 15.0
    elif any(w in t_lower for w in ["manager", "dgm", "agm", "lead"]):
        score_auth = 10.0
    elif any(w in t_lower for w in ["engineer", "specialist", "executive"]):
        score_auth = 5.0
    else:
        score_auth = 2.0

    # 5. Source Quality (0-10)
    if source_quality in ("OFFICIAL_COMPANY_PAGE", "COMPANY_PUBLIC_POST", "ANNUAL_REPORT", "PRESS_RELEASE", "LINKEDIN_PROFILE"):
        score_src = 10.0
    elif source_quality == "LINKEDIN_SEARCH_SNIPPET":
        score_src = 8.0
    elif source_quality in ("CONFERENCE_TECHNICAL", "TRADE_MEDIA"):
        score_src = 7.0
    elif source_quality == "PROFESSIONAL_DIRECTORY":
        score_src = 3.0
    else:
        score_src = 5.0

    total_score = score_emp + score_fac + score_fn + score_auth + score_src
    total_score = max(0.0, min(100.0, total_score))

    # Strict Confidence Classification
    # Cannot be HIGH if:
    # - facility is contradicted or other facility
    # - current employment is contradicted or stale
    # - role is junior individual contributor without authority
    # - source is only a professional directory (Task 4)
    if (
        facility_relationship in ("OTHER_FACILITY_OWNER", "FACILITY_CONTRADICTED")
        or current_employment in ("CONTRADICTED", "STALE")
        or authority_class == "JUNIOR_IC"
        or source_quality == "PROFESSIONAL_DIRECTORY"
    ):
        confidence = "LOW" if (source_quality == "PROFESSIONAL_DIRECTORY" and total_score < 70.0) else ("MEDIUM" if source_quality == "PROFESSIONAL_DIRECTORY" else "LOW")
    elif (
        total_score >= 85.0
        and current_employment == "VERIFIED"
        and facility_relationship in ("FACILITY_OWNER", "FACILITY_FUNCTION_OWNER", "GROUP_FUNCTION_OWNER")
        and source_quality != "PROFESSIONAL_DIRECTORY"
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
    r"[A-Z][A-Za-z'-]{1,30}(?:\s+(?:[A-Z]\.|\b[A-Z]\b|[A-Z][A-Za-z'-]{1,30})){1,4}"
)
PERSON_ROLE_PATTERN = (
    r"(?:Vice President|VP|AVP|Director|Plant Head|Site Head|Unit Head|Works Manager|"
    r"Factory Manager|General Manager|GM|DGM|AGM|Head(?:\s+of)?\s+(?:Plant\s+)?Quality|"
    r"Quality(?:\s+Assurance|\s+Control)?\s+(?:Head|Manager|Lead)|QA(?:\s*/\s*QC)?\s+(?:Head|Manager)|"
    r"QC\s+(?:Head|Manager)|Operations Head|Head of Operations|Manufacturing Head|"
    r"Head of Manufacturing|Metrology(?:\s+Head|\s+Manager)?|Calibration(?:\s+Head|\s+Manager|\s+Incharge)?|"
    r"Operational Excellence(?:\s+Head|\s+Lead)?|Instrumentation(?:\s+Head|\s+Manager)?|"
    r"Deputy Manager|Assistant Manager|(?:General\s+|Deputy\s+|Assistant\s+)?Manager)"
)


DIRECTORY_DOMAINS = {
    "kompass.com", "zaubacorp.com", "indiamart.com", "tofler.in", "justdial.com",
    "tradeindia.com", "instafinancials.com", "crunchbase.com", "zoominfo.com",
    "apollo.io", "lusha.com", "rocketreach.co", "signalhire.com", "aeroleads.com",
    "lead411.com",
}


def classify_person_source(url: str, title: str = "", company_domain: str = "") -> str:
    """Classify the public source surface used to discover or verify a candidate."""
    parsed = urlparse(url or "")
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.lower()
    clean_domain = company_domain.lower().removeprefix("www.").strip()
    combined = f"{title} {path}".lower()
    is_official = bool(clean_domain and (host == clean_domain or host.endswith(f".{clean_domain}")))

    if any(d in host for d in DIRECTORY_DOMAINS):
        return "PROFESSIONAL_DIRECTORY"
    if "linkedin.com/in/" in (url or "").lower():
        return "LINKEDIN_SEARCH_SNIPPET"
    if any(k in (url or "").lower() for k in ("linkedin.com/posts/", "linkedin.com/feed/", "linkedin.com/company/")):
        return "COMPANY_PUBLIC_POST"
    if path.endswith(".pdf") or any(term in combined for term in ("annual-report", "annual_report", "annual report", "presentation", "sustainability", "brsr")):
        return "ANNUAL_REPORT"
    if is_official and any(term in combined for term in ("news", "media", "press", "event", "award", "webinar", "post", "blog")):
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


SOURCE_PRIORITY_ORDER = [
    "OFFICIAL_COMPANY_PAGE",
    "ANNUAL_REPORT",
    "COMPANY_PUBLIC_POST",
    "LINKEDIN_PROFILE",
    "LINKEDIN_SEARCH_SNIPPET",
    "CONFERENCE_TECHNICAL",
    "TRADE_MEDIA",
    "PUBLIC_WEB_BIO",
    "PROFESSIONAL_DIRECTORY",
]


def classify_person_source_recency(
    source_date: str = "",
    snippet: str = "",
    reference_dt: Optional[datetime] = None,
) -> Tuple[str, Optional[int]]:
    """Classify recency of person evidence source into Salesoorja tiers:
    CURRENT: <= 180 days
    RECENT: 181–365 days
    OLDER: > 365 days
    UNDATED: No explicit date found
    """
    ref_dt = reference_dt or NOW_DT
    ref_year = ref_dt.year  # 2026

    clean_date = (source_date or "").strip()
    if clean_date:
        m_rel = re.search(r"(\d+)\s+(day|week|month|year)s?\s+ago", clean_date.lower())
        if m_rel:
            qty = int(m_rel.group(1))
            unit = m_rel.group(2)
            days = qty if unit == "day" else (qty * 7 if unit == "week" else (qty * 30 if unit == "month" else qty * 365))
            if days <= 180:
                return "CURRENT", days
            elif days <= 365:
                return "RECENT", days
            else:
                return "OLDER", days

        m_iso = re.search(r"\b(20\d{2})[-/](0[1-9]|1[0-2])[-/](0[1-9]|[12]\d|3[01])\b", clean_date)
        if m_iso:
            try:
                d = datetime(int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3)), tzinfo=timezone.utc)
                diff_days = max(0, (ref_dt - d).days)
                if diff_days <= 180:
                    return "CURRENT", diff_days
                elif diff_days <= 365:
                    return "RECENT", diff_days
                else:
                    return "OLDER", diff_days
            except Exception:
                pass

        m_my = re.search(r"\b([A-Za-z]{3,9})\s+(20\d{2})\b", clean_date)
        if m_my:
            try:
                dt_parsed = datetime.strptime(f"{m_my.group(1)[:3]} {m_my.group(2)}", "%b %Y").replace(tzinfo=timezone.utc)
                diff_days = max(0, (ref_dt - dt_parsed).days)
                if diff_days <= 180:
                    return "CURRENT", diff_days
                elif diff_days <= 365:
                    return "RECENT", diff_days
                else:
                    return "OLDER", diff_days
            except Exception:
                pass

        m_yr = re.search(r"\b(20\d{2})\b", clean_date)
        if m_yr:
            yr = int(m_yr.group(1))
            if yr >= ref_year:
                return "CURRENT", 90
            elif yr == ref_year - 1:
                return "RECENT", 270
            else:
                return "OLDER", (ref_year - yr) * 365

    comb_lower = (snippet or "").lower()
    if re.search(r"\b(?:present|currently|serving\s+as)\b", comb_lower) and any(y in comb_lower for y in ["2025", "2026", "fy 26"]):
        return "CURRENT", 60

    m_snip_yr = re.findall(r"\b(20\d{2})\b", comb_lower)
    if m_snip_yr:
        max_yr = max(int(y) for y in m_snip_yr)
        if max_yr >= ref_year:
            return "CURRENT", 90
        elif max_yr == ref_year - 1:
            return "RECENT", 270
        else:
            return "OLDER", (ref_year - max_yr) * 365

    return "UNDATED", None


@dataclass
class PersonEvidencePacket:
    """Structured multi-source evidence packet grounding candidate qualification."""
    candidate_name: str
    current_title: str
    target_company: str
    target_facility: str = ""
    target_city: str = ""
    target_state: str = ""
    facility_aliases: List[str] = field(default_factory=list)

    employment_sources: List[Dict[str, Any]] = field(default_factory=list)
    employment_proofs: List[Dict[str, Any]] = field(default_factory=list)
    facility_sources: List[Dict[str, Any]] = field(default_factory=list)
    function_sources: List[Dict[str, Any]] = field(default_factory=list)
    authority_sources: List[Dict[str, Any]] = field(default_factory=list)
    post_sources: List[Dict[str, Any]] = field(default_factory=list)
    document_sources: List[Dict[str, Any]] = field(default_factory=list)

    current_employment: str = "UNKNOWN"
    facility_relationship: str = "UNKNOWN"
    function_ownership: str = "UNPROVEN"
    authority: str = "UNKNOWN"
    confidence: str = "LOW"
    score: float = 0.0
    contact_route: str = "UNASSIGNED"
    cross_source_corroborated: bool = False
    source_types: List[str] = field(default_factory=list)
    source_recencies: List[str] = field(default_factory=list)

    def add_source(
        self,
        url: str,
        title: str,
        snippet: str,
        source_type: str = "",
        company_domain: str = "",
        source_date: str = "",
    ) -> None:
        """Classifies and attaches a search result to the evidence packet."""
        stype = source_type or classify_person_source(url, title, company_domain=company_domain)
        if stype not in self.source_types:
            self.source_types.append(stype)

        recency, age_days = classify_person_source_recency(source_date, f"{title}. {snippet}")
        if recency not in self.source_recencies:
            self.source_recencies.append(recency)

        src_record = {
            "url": url,
            "title": title,
            "snippet": snippet[:400],
            "source_type": stype,
            "recency": recency,
            "age_days": age_days,
            "source_date": source_date,
        }

        text = f"{title}. {snippet}".strip().lower()

        # 1. Employment evidence: mentions company or experience
        c_clean = re.sub(r"[^\w\s]", " ", self.target_company.lower()).strip()
        c_tokens = [t for t in c_clean.split() if t not in COMPANY_SUFFIX_TOKENS and len(t) >= 3]
        has_company_mention = bool((c_tokens and any(t in text for t in c_tokens)) or "experience" in text or "present" in text or "linkedin.com/in/" in url.lower())

        if has_company_mention:
            st = classify_current_employment(snippet, title, self.target_company)
            base_comp = re.sub(
                r"\s+(?:India|Technologies|Solutions|Industries|Limited|Ltd|Pvt\s+Ltd|Private\s+Limited)\b.*",
                "",
                self.target_company,
                flags=re.IGNORECASE,
            ).strip().lower()
            has_exp_target = bool(
                (base_comp and len(base_comp) >= 3 and re.search(r"experience:\s*.*?" + re.escape(base_comp), text))
                or (c_clean and len(c_clean) >= 3 and re.search(r"experience:\s*.*?" + re.escape(c_clean[:8]), text))
            )
            has_present_sig = any(re.search(p, text, re.IGNORECASE) for p in STRONG_CURRENT_PATTERNS) or has_exp_target
            has_recent_yr = any(y in text for y in ["2025", "2026", "fy 25", "fy 26", "fy25", "fy26"])
            has_hist_yr = any(y in text for y in ["2019", "2020", "2021", "2022", "2023", "2024"]) or recency == "OLDER"

            retrieval_date = NOW_DT.strftime("%Y-%m-%d")
            pub_date = source_date or ("2026" if recency == "CURRENT" else ("2025" if recency == "RECENT" else ""))

            if st == "CONTRADICTED":
                date_signal = "CONTRADICTED"
                proof_category = "CONTRADICTED_EMPLOYMENT"
                has_explicit_current_other = bool(
                    re.search(r"\bcurrently\s+(?:working\s+)?(?:at|with)\b", text)
                    or re.search(r"experience:\s*[^.]{0,240}\bpresent\b", text)
                )
                strength = "STRONG_CONTRADICTING" if has_explicit_current_other else "CONTRADICTING"
            elif stype == "PROFESSIONAL_DIRECTORY":
                # Directory is SUPPORTING ONLY. Directory-only evidence != VERIFIED
                date_signal = "DIRECTORY_RECORD"
                proof_category = "RECENT_DIRECTORY_EVIDENCE"
                strength = "SUPPORTING_ONLY"
            elif stype in ("ANNUAL_REPORT", "PUBLIC_DOCUMENT") or url.lower().endswith(".pdf") or "annual report" in (title or "").lower():
                if has_present_sig:
                    date_signal = "PRESENT"
                    proof_category = "CURRENT_OFFICIAL_DOCUMENT"
                    strength = "STRONG_CURRENT_PROOF"
                else:
                    date_signal = "HISTORICAL" if has_hist_yr else "UNDATED"
                    proof_category = "HISTORICAL_EMPLOYMENT" if has_hist_yr else "UNDATED_EMPLOYMENT"
                    strength = "SUPPORTING_ONLY"
            elif stype in ("COMPANY_PUBLIC_POST", "COMPANY_POST") or "linkedin.com/posts" in url.lower():
                if has_present_sig:
                    date_signal = "PRESENT"
                    proof_category = "CURRENT_COMPANY_POST"
                    strength = "STRONG_CURRENT_PROOF"
                else:
                    date_signal = "HISTORICAL" if has_hist_yr else "UNDATED"
                    proof_category = "HISTORICAL_EMPLOYMENT" if has_hist_yr else "UNDATED_EMPLOYMENT"
                    strength = "SUPPORTING_ONLY"
            elif stype == "OFFICIAL_COMPANY_PAGE":
                if has_present_sig:
                    date_signal = "PRESENT"
                    proof_category = "CURRENT_PROFILE_EVIDENCE"
                    strength = "STRONG_CURRENT_PROOF"
                else:
                    date_signal = "UNDATED"
                    proof_category = "UNDATED_EMPLOYMENT"
                    strength = "SUPPORTING_ONLY"
            elif stype == "CONFERENCE_TECHNICAL":
                # Conference biography is SUPPORTING ONLY
                date_signal = "CONFERENCE_BIOGRAPHY"
                proof_category = "CURRENT_EVENT_EVIDENCE" if (recency in ("CURRENT", "RECENT") or has_recent_yr) else "HISTORICAL_EMPLOYMENT"
                strength = "SUPPORTING_ONLY"
            elif stype in ("LINKEDIN_SEARCH_SNIPPET", "LINKEDIN_PROFILE", "PUBLIC_WEB_BIO"):
                if has_present_sig:
                    date_signal = "PRESENT"
                    proof_category = "CURRENT_PROFILE_EVIDENCE"
                    strength = "STRONG_CURRENT_PROOF"
                elif has_recent_yr:
                    date_signal = "RECENT_YEAR"
                    proof_category = "UNDATED_EMPLOYMENT"
                    strength = "SUPPORTING_ONLY"
                else:
                    date_signal = "HISTORICAL" if has_hist_yr else "UNDATED"
                    proof_category = "HISTORICAL_EMPLOYMENT" if has_hist_yr else "UNDATED_EMPLOYMENT"
                    strength = "SUPPORTING_ONLY"
            else:
                date_signal = "UNDATED"
                proof_category = "UNDATED_EMPLOYMENT"
                strength = "SUPPORTING_ONLY"

            proof_record = {
                "source_url": url,
                "source_title": title,
                "snippet": snippet[:400],
                "source_type": stype,
                "publication_date": pub_date,
                "retrieval_date": retrieval_date,
                "employment_date_signal": date_signal,
                "target_company": self.target_company,
                "candidate_name": self.candidate_name,
                "classification": proof_category,
                "strength": strength,
                "recency": recency,
            }
            self.employment_proofs.append(proof_record)
            self.employment_sources.append(src_record)

        # 2. Facility evidence: mentions target city, state, facility, aliases, or other Indian industrial cities
        t_city = self.target_city.lower().strip() if self.target_city else ""
        t_fac = self.target_facility.lower().strip() if self.target_facility else ""
        has_target = (t_city and t_city in text) or (t_fac and any(w in text for w in t_fac.split() if len(w) >= 4 and w not in GENERIC_FACILITY_TOKENS))
        if not has_target and self.facility_aliases:
            has_target = any(a.lower() in text for a in self.facility_aliases if a.lower() != (self.target_state or "").lower())
        has_other_city = any(re.search(rf"\b{c}\b", text) for c in INDIAN_CITIES_TO_STATE if c != t_city)
        if has_target or has_other_city or any(w in text for w in ["plant", "works", "facility", "unit", "factory", "site", "location:"]):
            self.facility_sources.append(src_record)

        # 3. Function evidence: mentions quality, QA, QC, metrology, calibration, testing, operations
        if any(w in text for w in ["quality", "qa", "qc", "metrology", "calibration", "inspection", "testing", "operations", "manufacturing"]):
            self.function_sources.append(src_record)

        # 4. Authority evidence: mentions leadership titles
        if any(w in text for w in ["head", "manager", "vp", "vice president", "director", "general manager", "gm", "lead", "engineer", "specialist", "officer"]):
            self.authority_sources.append(src_record)

        # 5. Company post and document evidence tracking (Phase 3 & 4)
        if stype in ("COMPANY_PUBLIC_POST", "COMPANY_POST") or "linkedin.com/posts" in url.lower():
            self.post_sources.append(src_record)
        if stype in ("ANNUAL_REPORT", "PUBLIC_DOCUMENT") or url.lower().endswith(".pdf") or "annual report" in (title or "").lower():
            self.document_sources.append(src_record)

    def derive(self) -> None:
        """Deterministically derive multi-source verified attributes."""
        # 1. Current Employment
        # Explicit current-employer contradictions override current proof; ambiguous
        # headlines do not override structured target-company Present evidence.
        has_contradicted = (
            any(p.get("classification") == "CONTRADICTED_EMPLOYMENT" for p in self.employment_proofs)
            or any(classify_current_employment(s.get("snippet", ""), s.get("title", ""), self.target_company) == "CONTRADICTED" for s in self.employment_sources)
        )
        has_strong_contradiction = any(
            p.get("strength") == "STRONG_CONTRADICTING" for p in self.employment_proofs
        )
        has_strong_current_proof = any(p.get("strength") == "STRONG_CURRENT_PROOF" for p in self.employment_proofs)
        has_supporting_proof = any(p.get("strength") == "SUPPORTING_ONLY" for p in self.employment_proofs)

        if has_strong_contradiction:
            self.current_employment = "CONTRADICTED"
        elif has_strong_current_proof:
            self.current_employment = "VERIFIED"
        elif has_contradicted:
            self.current_employment = "CONTRADICTED"
        elif has_supporting_proof:
            # Supporting-only evidence (directory, old post, conference bio, undated snippet) may corroborate facility/function
            # but must NOT independently create VERIFIED current employment.
            has_recent_support = any(
                p.get("recency") in ("CURRENT", "RECENT") or p.get("employment_date_signal") in ("RECENT_YEAR", "DIRECTORY_RECORD")
                for p in self.employment_proofs
            )
            self.current_employment = "PROBABLE" if has_recent_support else "UNKNOWN"
        else:
            self.current_employment = "UNKNOWN"

        # 2. Facility Relationship
        combined_fac_text = " ".join(f"{s.get('title', '')} {s.get('snippet', '')}" for s in self.facility_sources[:5])
        fac_rel = classify_facility_relationship(
            self.current_title,
            combined_fac_text,
            self.target_facility,
            self.target_city,
            target_state=self.target_state,
            facility_aliases=self.facility_aliases,
        )

        # Task 4 Directory Rule: Directory sources alone must NOT create plant-specific ownership
        if self.source_types and all(stype == "PROFESSIONAL_DIRECTORY" for stype in self.source_types):
            if fac_rel in ("FACILITY_OWNER", "FACILITY_FUNCTION_OWNER"):
                fac_rel = "FUNCTIONALLY_RELEVANT"

        self.facility_relationship = fac_rel

        # 3. Function Ownership & Authority
        combined_fn_text = " ".join(f"{s.get('title', '')} {s.get('snippet', '')}" for s in self.function_sources[:5])
        auth_class = classify_authority_class(self.current_title, combined_fn_text)
        self.function_ownership = auth_class

        t_lower = self.current_title.lower()
        if auth_class == "JUNIOR_IC":
            self.authority = "JUNIOR_IC"
        elif any(w in t_lower for w in ["head", "director", "vp", "vice president", "general manager", "gm", "manager", "lead"]):
            self.authority = "DECISION_MAKER"
        else:
            self.authority = "INFLUENCER"

        # 4. Score and Confidence
        dominant_src = "PUBLIC_WEB_BIO"
        for p in SOURCE_PRIORITY_ORDER:
            if p in self.source_types:
                dominant_src = p
                break

        score, conf = compute_deterministic_person_score(
            current_employment=self.current_employment,
            facility_relationship=self.facility_relationship,
            authority_class=self.function_ownership,
            title=self.current_title,
            source_quality=dominant_src,
        )

        # Task 4 Directory Rule: Directory alone must never yield HIGH confidence
        if self.source_types and all(stype == "PROFESSIONAL_DIRECTORY" for stype in self.source_types):
            conf = "LOW" if score < 70.0 else "MEDIUM"

        self.score = score
        self.confidence = conf

        # 5. Contact Route Assignment (Phase 6)
        if self.facility_relationship in ("FACILITY_OWNER", "FACILITY_FUNCTION_OWNER"):
            self.contact_route = "PLANT_SPECIFIC_CONTACT"
        elif self.facility_relationship == "GROUP_FUNCTION_OWNER" or self.function_ownership == "GROUP_FUNCTION_OWNER":
            self.contact_route = "GROUP_LEVEL_CONTACT"
        else:
            self.contact_route = "HOLD"

        # 6. Cross-Source Corroboration (Phase 2)
        # Fuses historical plant/post evidence with fresh verified employment
        # Example A: 2024 plant post ("Plant Head, Nashik") + 2026 profile ("Present" at target company)
        # -> CURRENT_EMPLOYMENT = VERIFIED, FACILITY_RELATIONSHIP uses the plant post.
        has_plant_evidence = self.facility_relationship in ("FACILITY_OWNER", "FACILITY_FUNCTION_OWNER")
        has_post_or_doc_facility = any(
            s.get("source_type") in ("COMPANY_PUBLIC_POST", "ANNUAL_REPORT", "PUBLIC_DOCUMENT")
            for s in self.facility_sources
        )
        if (
            self.current_employment == "VERIFIED"
            and has_plant_evidence
            and (has_post_or_doc_facility or len(self.employment_sources) > 1 or len(self.source_types) > 1)
        ):
            self.cross_source_corroborated = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_name": self.candidate_name,
            "current_title": self.current_title,
            "target_company": self.target_company,
            "target_facility": self.target_facility,
            "target_city": self.target_city,
            "target_state": self.target_state,
            "facility_aliases": self.facility_aliases,
            "current_employment": self.current_employment,
            "facility_relationship": self.facility_relationship,
            "function_ownership": self.function_ownership,
            "authority": self.authority,
            "confidence": self.confidence,
            "score": self.score,
            "contact_route": self.contact_route,
            "cross_source_corroborated": self.cross_source_corroborated,
            "source_types": self.source_types,
            "source_recencies": self.source_recencies,
            "employment_sources_count": len(self.employment_sources),
            "facility_sources_count": len(self.facility_sources),
            "function_sources_count": len(self.function_sources),
            "authority_sources_count": len(self.authority_sources),
            "post_sources_count": len(self.post_sources),
            "document_sources_count": len(self.document_sources),
            "employment_proofs": self.employment_proofs,
            "strong_current_proofs_count": sum(1 for p in self.employment_proofs if p.get("strength") == "STRONG_CURRENT_PROOF"),
            "supporting_proofs_count": sum(1 for p in self.employment_proofs if p.get("strength") == "SUPPORTING_ONLY"),
            "contradicting_proofs_count": sum(
                1
                for p in self.employment_proofs
                if p.get("strength") in {"CONTRADICTING", "STRONG_CONTRADICTING"}
            ),
        }


def create_person_evidence_packet(
    candidate_name: str,
    current_title: str,
    target_company: str,
    target_facility: str = "",
    target_city: str = "",
    target_state: str = "",
    initial_source: Optional[Dict[str, Any]] = None,
    company_domain: str = "",
    facility_aliases: Optional[List[str]] = None,
) -> PersonEvidencePacket:
    """Factory creating and initializing a PersonEvidencePacket."""
    packet = PersonEvidencePacket(
        candidate_name=candidate_name,
        current_title=current_title,
        target_company=target_company,
        target_facility=target_facility,
        target_city=target_city,
        target_state=target_state,
        facility_aliases=list(facility_aliases or []),
    )
    if initial_source:
        packet.add_source(
            url=str(initial_source.get("url") or ""),
            title=str(initial_source.get("title") or ""),
            snippet=str(initial_source.get("snippet") or initial_source.get("evidence_snippet") or ""),
            source_type=str(initial_source.get("source_type") or ""),
            company_domain=company_domain,
            source_date=str(initial_source.get("source_date") or initial_source.get("date") or initial_source.get("published_date") or ""),
        )
    packet.derive()
    return packet


def _brightdata_company_matches(candidate_company: str, target_company: str) -> bool:
    ignored = {"limited", "ltd", "private", "pvt", "inc", "corporation", "corp"}
    target_tokens = [
        token
        for token in re.findall(r"[a-z0-9]+", (target_company or "").casefold())
        if len(token) >= 3 and token not in ignored
    ]
    candidate_key = (candidate_company or "").casefold()
    return bool(candidate_key and target_tokens and all(token in candidate_key for token in target_tokens[:2]))


def _brightdata_source_text(record: Dict[str, Any]) -> Tuple[str, str]:
    current_title = str(record.get("current_title") or record.get("headline") or "").strip()
    current_company = str(record.get("current_company") or "").strip()
    title = current_title
    if current_company:
        title = f"{current_title or 'Current role'} at {current_company}"
    snippets: List[str] = []
    if current_company:
        snippets.append(
            f"Currently working at {current_company} as {current_title or 'current employee'}."
        )
    evidence_snippet = str(record.get("evidence_snippet") or "").strip()
    if evidence_snippet:
        snippets.append(evidence_snippet)
    for experience in record.get("experience") or []:
        if not isinstance(experience, dict):
            continue
        company = str(experience.get("company") or "").strip()
        role = str(experience.get("title") or "").strip()
        start_date = str(experience.get("start_date") or "").strip()
        end_date = str(experience.get("end_date") or "").strip()
        if experience.get("is_current"):
            end_date = "Present"
        date_range = " - ".join(part for part in (start_date, end_date) if part)
        parts = [part for part in (company, role, date_range) if part]
        if parts:
            snippets.append("Experience: " + " | ".join(parts) + ".")
        experience_location = str(experience.get("location") or "").strip()
        if experience_location:
            snippets.append(f"Experience location: {experience_location}.")
    return title, " ".join(snippets)[:1200]


def qualify_brightdata_person_records(
    records: List[Dict[str, Any]],
    *,
    company_name: str,
    facility_name: str = "",
    city: str = "",
    state: str = "",
    company_domain: str = "",
) -> Optional[Dict[str, Any]]:
    """Apply existing deterministic person gates to normalized Bright Data evidence."""
    usable = [record for record in records if isinstance(record, dict)]
    if not usable:
        return None
    strongest = usable[-1]
    candidate_name = str(strongest.get("name") or usable[0].get("name") or "").strip()
    is_human, _ = is_human_person_candidate(candidate_name, company_name=company_name)
    if not is_human:
        return None
    current_title = next(
        (
            str(record.get("current_title") or record.get("headline") or "").strip()
            for record in reversed(usable)
            if record.get("current_title") or record.get("headline")
        ),
        "",
    )
    aliases = generate_facility_aliases(
        facility_name=facility_name,
        city=city,
        state=state,
    )
    packet = PersonEvidencePacket(
        candidate_name=candidate_name,
        current_title=current_title,
        target_company=company_name,
        target_facility=facility_name,
        target_city=city,
        target_state=state,
        facility_aliases=aliases,
    )
    source_snippets: List[str] = []
    for record in usable:
        source_title, source_snippet = _brightdata_source_text(record)
        source_snippets.append(source_snippet)
        packet.add_source(
            url=str(record.get("linkedin_url") or ""),
            title=source_title,
            snippet=source_snippet,
            source_type=(
                "LINKEDIN_PROFILE"
                if record.get("evidence_kind") == "PROFILE_LOOKUP"
                else "LINKEDIN_SEARCH_SNIPPET"
            ),
            company_domain=company_domain,
            source_date=str(record.get("retrieved_at") or ""),
        )
    packet.derive()
    current_company = next(
        (
            str(record.get("current_company") or "").strip()
            for record in reversed(usable)
            if record.get("current_company")
        ),
        "",
    )
    profile_url = next(
        (
            str(record.get("linkedin_url") or "").strip()
            for record in reversed(usable)
            if record.get("linkedin_url")
        ),
        "",
    )
    location = next(
        (
            str(record.get("location") or "").strip()
            for record in reversed(usable)
            if record.get("location")
        ),
        "",
    )
    field_provenance: Dict[str, Any] = {}
    for record in usable:
        for field_name, provenance in (record.get("field_provenance") or {}).items():
            if provenance:
                field_provenance[field_name] = provenance
    if packet.current_employment == "CONTRADICTED" or packet.facility_relationship in {
        "OTHER_FACILITY_OWNER",
        "FACILITY_CONTRADICTED",
    }:
        verification_status = "PERSON_REJECTED"
    elif packet.current_employment == "VERIFIED" and packet.score >= 70:
        verification_status = "PERSON_PUBLICLY_VERIFIED"
    else:
        verification_status = "PERSON_CANDIDATE"
    return {
        "name": candidate_name,
        "title": current_title,
        "company": current_company,
        "linkedin_url": profile_url,
        "linkedin_id": str(strongest.get("linkedin_id") or ""),
        "location": location,
        "experience": strongest.get("experience") or [],
        "current_employment": packet.current_employment,
        "current_employment_verified": packet.current_employment == "VERIFIED",
        "facility_relationship": packet.facility_relationship,
        "facility_verified": packet.facility_relationship in {
            "FACILITY_OWNER",
            "FACILITY_FUNCTION_OWNER",
        },
        "function_ownership": packet.function_ownership,
        "authority_class": packet.function_ownership,
        "authority": packet.authority,
        "duties_verified": packet.function_ownership not in {
            "UNKNOWN",
            "COMPANY_ONLY",
            "GENERAL_QUALITY",
            "JUNIOR_IC",
        },
        "person_score": packet.score,
        "person_confidence": packet.confidence,
        "contact_route": packet.contact_route,
        "verification_status": verification_status,
        "evidence_snippet": " ".join(source_snippets)[:1200],
        "evidence_packet": packet.to_dict(),
        "field_provenance": field_provenance,
        "source": "BRIGHTDATA_LINKEDIN",
        "retrieved_at": str(strongest.get("retrieved_at") or ""),
        "ready_for_contact_enrichment": False,
    }


def discover_people_with_apollo(
    *,
    company_name: str,
    facility_name: str = "",
    city: str = "",
    state: str = "",
    role_families: Optional[List[str]] = None,
    max_candidates: int = 5,
    search_fn: Any = None,
) -> Dict[str, Any]:
    """Discover identity-only Apollo candidates and rank them locally."""
    from services.apollo_adapter import (
        APOLLO_PERSON_ROLE_FAMILIES,
        search_apollo_people_candidates,
    )
    from services.brightdata_linkedin_provider import rank_people_records

    roles = list(role_families or APOLLO_PERSON_ROLE_FAMILIES)
    caller = search_fn or search_apollo_people_candidates
    search_result = caller(
        company_name,
        locations=[location for location in (city, state) if location],
        titles=roles,
        max_results=10,
    )
    raw_candidates = search_result.get("candidates") or []
    normalized = [
        {
            "name": str(candidate.get("name") or "").strip(),
            "linkedin_url": str(candidate.get("linkedin_url") or "").strip(),
            "linkedin_id": str(candidate.get("apollo_id") or ""),
            "headline": str(candidate.get("title") or "").strip(),
            "location": str(candidate.get("location") or "").strip(),
            "current_company": str(candidate.get("company") or "").strip(),
            "current_title": str(candidate.get("title") or "").strip(),
            "experience": [],
            "source": "APOLLO_DISCOVERY",
            "evidence_kind": "APOLLO_DISCOVERY",
            "seniority": str(candidate.get("seniority") or "").strip(),
            "verification_status": "PERSON_CANDIDATE",
            "ready_for_contact_enrichment": False,
        }
        for candidate in raw_candidates
        if isinstance(candidate, dict)
    ]
    ranked = rank_people_records(
        normalized,
        company=company_name,
        facility=facility_name,
        city=city,
        role_families=roles,
    )
    retained_limit = min(max(int(max_candidates), 1), 5)
    return {
        "status": search_result.get("status", "ERROR"),
        "provider": "APOLLO",
        "candidates": ranked[:retained_limit],
        "telemetry": search_result.get("telemetry") or {
            "APOLLO_SEARCH_CALLS": 0,
            "CONTACT_REVEAL_CALLS": 0,
        },
    }


def verify_apollo_candidates_with_brightdata(
    candidates: List[Dict[str, Any]],
    *,
    company_name: str,
    facility_name: str = "",
    city: str = "",
    state: str = "",
    company_domain: str = "",
    max_attempts: int = 3,
    provider: Any = None,
) -> Dict[str, Any]:
    """Verify at most three Apollo identities using Bright Data profile evidence."""
    if provider is None:
        from services.brightdata_linkedin_provider import brightdata_linkedin_provider
        provider = brightdata_linkedin_provider

    attempts = []
    verified_candidates = []
    profile_fetches = 0
    attempt_limit = min(max(int(max_attempts), 1), 3)
    for discovery_candidate in candidates[:attempt_limit]:
        linkedin_url = str(discovery_candidate.get("linkedin_url") or "").strip()
        cand_name = str(discovery_candidate.get("name") or "").strip()

        # If linkedin_url is missing or invalid, resolve via public profile search
        if (not linkedin_url or "/in/" not in linkedin_url.lower()) and cand_name:
            try:
                from services.research_provider import ResearchProviderRouter
                router = ResearchProviderRouter()
                location_hint = city or state or ""
                search_query = f'site:linkedin.com/in "{cand_name}" "{company_name}" {location_hint}'.strip()
                search_res = router.search(search_query, num_results=3, use_cache=True)
                for r in (search_res.get("results") or []):
                    r_url = str((r.get("url") if isinstance(r, dict) else getattr(r, "url", "")) or "").strip()
                    if "/in/" in r_url.lower():
                        linkedin_url = r_url
                        discovery_candidate["linkedin_url"] = linkedin_url
                        r_title = str((r.get("title") if isinstance(r, dict) else getattr(r, "title", "")) or "")
                        r_snippet = str((r.get("snippet") if isinstance(r, dict) else getattr(r, "snippet", "")) or "")
                        if " - " in r_title:
                            extracted_full = r_title.split(" - ")[0].strip()
                            if extracted_full and len(extracted_full.split()) > len(cand_name.split()):
                                discovery_candidate["name"] = extracted_full
                        if r_snippet and not discovery_candidate.get("evidence_snippet"):
                            discovery_candidate["evidence_snippet"] = r_snippet
                        break
                if (not linkedin_url or "/in/" not in linkedin_url.lower()) and location_hint:
                    fallback_query = f'site:linkedin.com/in "{cand_name}" "{company_name}"'.strip()
                    search_res = router.search(fallback_query, num_results=3, use_cache=True)
                    for r in (search_res.get("results") or []):
                        r_url = str((r.get("url") if isinstance(r, dict) else getattr(r, "url", "")) or "").strip()
                        if "/in/" in r_url.lower():
                            linkedin_url = r_url
                            discovery_candidate["linkedin_url"] = linkedin_url
                            r_title = str((r.get("title") if isinstance(r, dict) else getattr(r, "title", "")) or "")
                            r_snippet = str((r.get("snippet") if isinstance(r, dict) else getattr(r, "snippet", "")) or "")
                            if " - " in r_title:
                                extracted_full = r_title.split(" - ")[0].strip()
                                if extracted_full and len(extracted_full.split()) > len(cand_name.split()):
                                    discovery_candidate["name"] = extracted_full
                            if r_snippet and not discovery_candidate.get("evidence_snippet"):
                                discovery_candidate["evidence_snippet"] = r_snippet
                            break
            except Exception as exc:
                logger.debug("Serper LinkedIn resolution skipped for %s: %s", cand_name, exc)

        if not linkedin_url or "/in/" not in linkedin_url.lower():
            attempts.append({
                "name": discovery_candidate.get("name"),
                "state": "WRONG_PERSON",
                "profile_status": "INVALID_PROFILE_URL",
            })
            continue
        profile_result = provider.get_person_profile(linkedin_url)
        profile_fetches += 1
        profile_record = profile_result.get("record")
        if not isinstance(profile_record, dict):
            attempts.append({
                "name": discovery_candidate.get("name"),
                "state": "WRONG_PERSON",
                "profile_status": profile_result.get("status", "ERROR"),
            })
            continue
        profile_evidence = dict(profile_record)
        profile_evidence["name"] = str(
            profile_evidence.get("name") or discovery_candidate.get("name") or ""
        ).strip()
        profile_evidence["linkedin_url"] = str(
            profile_evidence.get("linkedin_url") or linkedin_url
        ).strip()
        profile_evidence["current_company"] = str(
            profile_evidence.get("current_company") or discovery_candidate.get("company") or company_name
        ).strip()
        profile_evidence["current_title"] = str(
            profile_evidence.get("current_title")
            or profile_evidence.get("headline")
            or discovery_candidate.get("current_title")
            or discovery_candidate.get("title")
            or ""
        ).strip()
        profile_evidence["headline"] = str(
            profile_evidence.get("headline")
            or profile_evidence["current_title"]
            or discovery_candidate.get("headline")
            or ""
        ).strip()
        profile_evidence["location"] = str(
            profile_evidence.get("location") or discovery_candidate.get("location") or city or ""
        ).strip()
        if discovery_candidate.get("evidence_snippet") and not profile_evidence.get("evidence_snippet"):
            profile_evidence["evidence_snippet"] = discovery_candidate["evidence_snippet"]
        candidate = qualify_brightdata_person_records(
            [profile_evidence],
            company_name=company_name,
            facility_name=facility_name,
            city=city,
            state=state,
            company_domain=company_domain,
        )
        if not candidate:
            attempts.append({
                "name": discovery_candidate.get("name"),
                "state": "WRONG_PERSON",
                "profile_status": profile_result.get("status", "ERROR"),
            })
            continue
        if candidate.get("current_employment") == "CONTRADICTED":
            state_value = "CURRENT_EMPLOYMENT_CONTRADICTED"
        elif candidate.get("facility_relationship") in {
            "OTHER_FACILITY_OWNER",
            "FACILITY_CONTRADICTED",
        }:
            state_value = "WRONG_FACILITY"
        elif (
            candidate.get("current_employment") != "VERIFIED"
            or candidate.get("verification_status") != "PERSON_PUBLICLY_VERIFIED"
        ):
            state_value = "WRONG_PERSON"
        else:
            state_value = "PERSON_VERIFIED_CONTACT_MISSING"
        candidate.update({
            "apollo_discovery": dict(discovery_candidate),
            "bright_profile_verified": profile_result.get("status") == "WORKING",
            "profile_status": profile_result.get("status", "ERROR"),
            "funnel_state": state_value,
            "ready_for_contact_enrichment": False,
        })
        attempts.append({
            "name": candidate.get("name"),
            "state": state_value,
            "profile_status": candidate["profile_status"],
        })
        verified_candidates.append(candidate)

    has_viable_candidate = any(
        candidate.get("funnel_state") == "PERSON_VERIFIED_CONTACT_MISSING"
        for candidate in verified_candidates
    )
    return {
        "status": "READY" if has_viable_candidate else "HOLD_CONTACT_NOT_FOUND",
        "candidates": verified_candidates,
        "attempts": attempts,
        "profile_fetches": profile_fetches,
        "telemetry": provider.telemetry(),
    }


def run_contact_fallback_ladder(
    candidates: List[Dict[str, Any]],
    *,
    enrich_fn: Any,
    max_attempts: int = 3,
) -> Dict[str, Any]:
    """Enrich verified people sequentially and stop at the first usable contact."""
    attempts = []
    enrichment_calls = 0
    attempt_limit = min(max(int(max_attempts), 0), 3)
    for candidate in candidates[:attempt_limit]:
        state_value = str(candidate.get("funnel_state") or "WRONG_PERSON")
        if state_value in {"WRONG_PERSON", "WRONG_FACILITY", "CURRENT_EMPLOYMENT_CONTRADICTED"}:
            attempts.append({"name": candidate.get("name"), "state": state_value})
            continue
        gate_passed = bool(
            candidate.get("bright_profile_verified")
            and candidate.get("ready_for_contact_enrichment")
            and candidate.get("current_employment") == "VERIFIED"
            and candidate.get("facility_relationship")
            in {"FACILITY_OWNER", "FACILITY_FUNCTION_OWNER", "GROUP_FUNCTION_OWNER"}
            and candidate.get("function_ownership")
            not in {"UNKNOWN", "COMPANY_ONLY", "GENERAL_QUALITY", "JUNIOR_IC"}
            and candidate.get("authority") == "DECISION_MAKER"
            and candidate.get("person_confidence") == "HIGH"
            and float(candidate.get("person_score") or 0) >= 85
        )
        if not gate_passed:
            attempts.append({"name": candidate.get("name"), "state": "PERSON_VERIFIED_CONTACT_MISSING"})
            continue
        result = enrich_fn(candidate)
        enrichment_calls += 1
        if result.get("email") or result.get("phone"):
            attempts.append({"name": candidate.get("name"), "state": "CONTACT_FOUND"})
            return {
                "status": "CONTACT_FOUND",
                "attempts": attempts,
                "enrichment_calls": enrichment_calls,
                "result": result,
            }
        candidate["funnel_state"] = "PERSON_VERIFIED_CONTACT_MISSING"
        attempts.append({"name": candidate.get("name"), "state": candidate["funnel_state"]})
    return {
        "status": "HOLD_CONTACT_NOT_FOUND",
        "attempts": attempts,
        "enrichment_calls": enrichment_calls,
        "result": None,
    }


def discover_people_with_brightdata(
    *,
    company_name: str,
    facility_name: str = "",
    city: str = "",
    state: str = "",
    company_domain: str = "",
    role_families: Optional[List[str]] = None,
    max_candidates: int = 5,
    max_profile_fetches: int = 2,
    provider: Any = None,
) -> Dict[str, Any]:
    """Discover candidates through Bright Data and then apply deterministic gates."""
    if provider is None:
        from services.brightdata_linkedin_provider import brightdata_linkedin_provider
        provider = brightdata_linkedin_provider
    from services.brightdata_linkedin_provider import PRIORITY_ROLE_FAMILIES

    roles = list(role_families or PRIORITY_ROLE_FAMILIES)
    search_result = provider.search_people(
        company=company_name,
        facility=facility_name,
        city=city,
        state=state,
        role_families=roles,
        max_candidates=min(max(int(max_candidates), 1), 5),
    )
    search_records = search_result.get("records") or []
    if not search_records:
        return {
            "status": "CONFIG_REQUIRED" if search_result.get("status") == "CONFIG_REQUIRED" else "HOLD",
            "provider": "BRIGHTDATA_LINKEDIN",
            "search_status": search_result.get("status", "ERROR"),
            "profile_status": "NOT_CALLED",
            "candidates": [],
            "telemetry": provider.telemetry(),
        }

    candidate_records: List[List[Dict[str, Any]]] = [[record] for record in search_records]
    candidates = [
        qualify_brightdata_person_records(
            records,
            company_name=company_name,
            facility_name=facility_name,
            city=city,
            state=state,
            company_domain=company_domain,
        )
        for records in candidate_records
    ]
    candidates = [candidate for candidate in candidates if candidate]
    candidates.sort(key=_person_sort_key)

    profile_statuses: List[str] = []
    profile_budget = min(max(int(max_profile_fetches), 0), 2)
    profiled = 0
    for candidate in candidates:
        needs_profile = (
            candidate.get("current_employment") != "VERIFIED"
            or candidate.get("facility_relationship")
            not in {"FACILITY_OWNER", "FACILITY_FUNCTION_OWNER", "GROUP_FUNCTION_OWNER"}
            or float(candidate.get("person_score") or 0) < 85
        )
        if not needs_profile or profiled >= profile_budget or not candidate.get("linkedin_url"):
            continue
        profile_result = provider.get_person_profile(str(candidate["linkedin_url"]))
        profile_statuses.append(str(profile_result.get("status") or "ERROR"))
        profiled += 1
        profile_record = profile_result.get("record")
        if not profile_record:
            continue
        matching_index = next(
            (
                index
                for index, records in enumerate(candidate_records)
                if records[0].get("linkedin_url") == candidate.get("linkedin_url")
            ),
            None,
        )
        if matching_index is None:
            continue
        candidate_records[matching_index].append(profile_record)

    candidates = [
        qualify_brightdata_person_records(
            records,
            company_name=company_name,
            facility_name=facility_name,
            city=city,
            state=state,
            company_domain=company_domain,
        )
        for records in candidate_records
    ]
    candidates = [candidate for candidate in candidates if candidate]
    candidates.sort(key=_person_sort_key)
    return {
        "status": "READY" if candidates else "HOLD",
        "provider": "BRIGHTDATA_LINKEDIN",
        "search_status": search_result.get("status", "ERROR"),
        "profile_status": (
            "NOT_CALLED"
            if not profile_statuses
            else ("WORKING" if any(status == "WORKING" for status in profile_statuses) else profile_statuses[-1])
        ),
        "candidates": candidates[: min(max(int(max_candidates), 1), 5)],
        "telemetry": provider.telemetry(),
    }


def verify_candidate_stage_b(
    candidate: Dict[str, Any],
    company_name: str,
    facility_name: str = "",
    city: str = "",
    search_router: Any = None,
    max_searches: int = 5,
    company_domain: str = "",
    telemetry: Optional[Dict[str, Any]] = None,
    facility_aliases: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Stage B: Targeted exact-name verification searches for an independently discovered candidate.

    Runs up to max_searches (bounded to 5) targeted queries:
    1. "{name}" "{company}"
    2. "{name}" "{company}" "{city}" (or quality if city empty)
    3. site:linkedin.com/in "{name}" "{company}"
    4. "{name}" "{company}" "{alias}" (or "plant quality")
    5. "{name}" "{company}" "quality manager"
    Collects multi-source evidence into a PersonEvidencePacket and updates candidate attributes.
    """
    if search_router is None:
        from services.research_provider import research_router
        search_router = research_router

    cand_name = str(candidate.get("name") or "").strip()
    cand_title = str(candidate.get("title") or "").strip()
    if not cand_name:
        return candidate

    aliases = list(facility_aliases or [])
    if not aliases:
        aliases = generate_facility_aliases(
            facility_name=facility_name,
            city=city,
            state=str(candidate.get("state") or ""),
        )

    packet = create_person_evidence_packet(
        candidate_name=cand_name,
        current_title=cand_title,
        target_company=company_name,
        target_facility=facility_name,
        target_city=city,
        target_state=str(candidate.get("state") or ""),
        initial_source={
            "url": str(candidate.get("source_url") or ""),
            "title": str(candidate.get("title") or ""),
            "snippet": str(candidate.get("evidence_snippet") or ""),
            "source_type": str(candidate.get("source_type") or ""),
            "source_date": str(candidate.get("source_date") or ""),
        },
        company_domain=company_domain,
        facility_aliases=aliases,
    )

    clean_domain = company_domain.lower().removeprefix("www.").strip() if company_domain else ""
    query_candidates = [
        f'"{cand_name}" "{company_name}" present',
        f'site:linkedin.com/in "{cand_name}" "{company_name}"',
    ]
    if city:
        query_candidates.append(f'"{cand_name}" "{company_name}" "{city}"')
    else:
        query_candidates.append(f'"{cand_name}" "{company_name}" current')

    for al in aliases:
        if al and al.lower() not in (city.lower(), company_name.lower()):
            query_candidates.append(f'"{cand_name}" "{company_name}" "{al}"')
            break

    if clean_domain:
        query_candidates.append(f'site:{clean_domain} "{cand_name}"')
    query_candidates.append(f'"{cand_name}" "{company_name}" current')
    query_candidates.append(f'"{cand_name}" "{company_name}" 2026')
    query_candidates.append(f'"{cand_name}" "{company_name}" plant quality')

    # Deduplicate while preserving order, bounded to min(max_searches, 4)
    dedup_queries: List[str] = []
    for q in query_candidates:
        if q not in dedup_queries and len(dedup_queries) < min(max_searches, 4):
            dedup_queries.append(q)

    for q in dedup_queries:
        try:
            search_res = search_router.search(q, num_results=5)
            if telemetry is not None:
                telemetry["queries_run"] = telemetry.get("queries_run", 0) + 1
                telemetry["stage_b_queries_run"] = telemetry.get("stage_b_queries_run", 0) + 1
            results = search_res.get("results", []) or []
            cand_tokens = [t.lower() for t in cand_name.split() if len(t) >= 3]
            for r in results:
                u = str(r.get("url") or "")
                t = str(r.get("title") or "")
                s = str(r.get("snippet") or "")
                comb_lower = f"{t} {s}".lower()
                if not cand_tokens or any(tok in comb_lower for tok in cand_tokens):
                    packet.add_source(
                        url=u,
                        title=t,
                        snippet=s,
                        company_domain=company_domain,
                        source_date=str(r.get("date") or r.get("source_date") or ""),
                    )
        except Exception as e:
            logger.warning("Stage B verification query '%s' failed for %s: %s", q, cand_name, e)

        packet.derive()
        if (
            packet.confidence == "HIGH"
            and packet.current_employment == "VERIFIED"
            and packet.facility_relationship in ("FACILITY_OWNER", "FACILITY_FUNCTION_OWNER")
        ):
            break

    packet.derive()

    cand_copy = dict(candidate)
    cand_copy["current_employment"] = packet.current_employment
    cand_copy["facility_relationship"] = packet.facility_relationship
    cand_copy["authority_class"] = packet.function_ownership
    cand_copy["person_score"] = packet.score
    cand_copy["person_confidence"] = packet.confidence
    cand_copy["contact_route"] = packet.contact_route
    cand_copy["cross_source_corroborated"] = packet.cross_source_corroborated
    cand_copy["evidence_packet"] = packet.to_dict()

    top_snippets = []
    for src_list in (packet.employment_sources, packet.facility_sources):
        for s in src_list:
            snip = s.get("snippet", "").strip()
            if snip and snip not in top_snippets:
                top_snippets.append(snip)
                break
    if top_snippets:
        cand_copy["evidence_snippet"] = " ... ".join(top_snippets)[:500]

    return cand_copy


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
    target_state = str(item.get("state") or "")
    source_date = str(item.get("source_date") or item.get("published_date") or item.get("date") or "")

    packet = create_person_evidence_packet(
        candidate_name=name,
        current_title=clean_title,
        target_company=company_name,
        target_facility=facility_name,
        target_city=city,
        target_state=target_state,
        initial_source={
            "url": source_url,
            "title": title_raw,
            "snippet": snippet_raw,
            "source_type": source_type,
            "source_date": source_date,
        },
        company_domain=company_domain,
    )

    return {
        "name": re.sub(r"\s+", " ", name).strip(),
        "title": clean_title,
        "company": company_name,
        "facility": facility_name or city,
        "location": item.get("location") or city or facility_name,
        "source_date": item.get("source_date") or item.get("published_date") or item.get("date") or "",
        "current_employment": packet.current_employment,
        "facility_relationship": packet.facility_relationship,
        "authority_class": packet.function_ownership,
        "person_score": packet.score,
        "person_confidence": packet.confidence,
        "contact_route": packet.contact_route,
        "source_url": source_url,
        "source_type": source_type,
        "evidence_snippet": snippet_raw[:500],
        "evidence_packet": packet.to_dict(),
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

    if any(k in url.lower() for k in ("linkedin.com/in/", "rocketreach.co/", "aeroleads.com", "signalhire.com", "zoominfo.com")):
        parts = [part.strip() for part in re.split(r"\s+[-–—|•]\s+", cleaned_title) if part.strip() and part.strip().lower() != "linkedin"]
        if parts:
            is_h, _ = is_human_person_candidate(parts[0], company_name=company_name)
            if is_h:
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
        rf"(?P<name>{PERSON_NAME_PATTERN})\s+(?i:is|was|is listed as|listed as|serves as|serving as|has joined as|appointed as|named as|promoted to)\s+(?i:a\s+|an\s+|the\s+)?(?P<role>{role_pattern})",
        rf"(?i:appoints?|appointed|names?|named)\s+(?P<name>{PERSON_NAME_PATTERN})\s+(?i:as\s+(?:the\s+)?)?(?P<role>{role_pattern})",
        rf"(?P<role>{role_pattern})\s+(?i:at|for|with|in)\s+[^,\.\n]+[,\.\n]\s*(?P<name>{PERSON_NAME_PATTERN})",
        rf"(?P<name>{PERSON_NAME_PATTERN})\s+(?i:is listed as|listed as)\s+(?i:a\s+|an\s+|the\s+)?(?P<role>{role_pattern})",
        rf"(?i:congratulat\w+|award\w+|recogniz\w+|felicitat\w+)\s+(?P<name>{PERSON_NAME_PATTERN})\s*[-–—|,:(]?\s*(?P<role>{role_pattern})",
        rf"(?P<name>{PERSON_NAME_PATTERN})\s*[-–—|,:(]?\s*(?P<role>{role_pattern})\s+(?i:received|won|awarded|recognized|felicitated)",
        rf"(?i:speaker|keynote|presented by|led by|under the leadership of)\s+(?P<name>{PERSON_NAME_PATTERN})\s*[-–—|,:(]?\s*(?P<role>{role_pattern})",
        rf"(?P<name>{PERSON_NAME_PATTERN})\s*,\s*(?P<role>{role_pattern})\s+(?i:at|of|for)\s+(?i:our|the)?\s*[^,\.\n]+(?i:plant|facility|works|unit)",
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


def _person_sort_key(candidate: Dict[str, Any]) -> Tuple[int, float, int, int, str]:
    fac_rel = str(candidate.get("facility_relationship") or "")
    # Penalize contradicted candidates so they never rank above target-facility or uncontradicted candidates
    contradicted_penalty = 1 if fac_rel in ("OTHER_FACILITY_OWNER", "FACILITY_CONTRADICTED") else 0
    authority_index = (
        AUTHORITY_HIERARCHY.index(candidate["authority_class"])
        if candidate.get("authority_class") in AUTHORITY_HIERARCHY else 99
    )
    return (
        contradicted_penalty,
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
    max_company_queries: Optional[int] = None,
    max_stage_b_searches: int = 3,
    max_stage_b_candidates: int = 2,
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
    facility_aliases = generate_facility_aliases(
        facility_name=facility_name,
        city=city,
        state=INDIAN_CITIES_TO_STATE.get(city.lower(), ""),
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

    def _has_sufficient_evidence(candidates: List[Dict[str, Any]]) -> bool:
        for c in candidates:
            if c.get("person_confidence") == "HIGH":
                return True
            score = float(c.get("person_score") or 0.0)
            emp = str(c.get("current_employment") or "").upper()
            fac = str(c.get("facility_relationship") or "").upper()
            auth = str(c.get("authority_class") or "").upper()
            if (
                score >= 75.0
                and emp == "VERIFIED"
                and fac in ("FACILITY_OWNER", "FACILITY_FUNCTION_OWNER", "GROUP_FUNCTION_OWNER", "FUNCTIONALLY_RELEVANT")
                and auth not in ("UNKNOWN", "COMPANY_ONLY")
            ):
                return True
        return False

    # Budget & Early Stop Management
    try:
        from services.serper_budget_manager import serper_budget_manager
        serper_budget_manager.record_company_researched(1)
    except Exception:
        serper_budget_manager = None

    try:
        from config import settings
        initial_budget = int(getattr(settings, "SERPER_INITIAL_QUERIES_PER_COMPANY", 4))
        max_company_budget = int(getattr(settings, "SERPER_MAX_QUERIES_PER_COMPANY", 10))
    except Exception:
        initial_budget = 4
        max_company_budget = 10

    if max_company_queries is not None:
        initial_budget = min(initial_budget, max_company_queries)
        max_company_budget = max_company_queries

    stopped_early = False

    if not stopped_early:
        # 1. Initial Tier: 3-5 intelligent queries
        initial_tier_queries = deterministic_queries[:initial_budget]
        collect_candidates(initial_tier_queries)

        if _has_sufficient_evidence(all_candidates):
            stopped_early = True
            telemetry["stopped_early"] = True
            telemetry["early_stop_reason"] = "SUFFICIENT_EVIDENCE_INITIAL_TIER"
            if serper_budget_manager:
                serper_budget_manager.record_search_stopped_early(1)
        else:
            # 2. Targeted Tier: execute remaining queries up to max_company_budget, checking early stop
            targeted_queries = deterministic_queries[initial_budget:max_company_budget]
            for i in range(0, len(targeted_queries), 2):
                if _has_sufficient_evidence(all_candidates):
                    stopped_early = True
                    telemetry["stopped_early"] = True
                    telemetry["early_stop_reason"] = "SUFFICIENT_EVIDENCE_TARGETED_TIER"
                    if serper_budget_manager:
                        serper_budget_manager.record_search_stopped_early(1)
                    break
                collect_candidates(targeted_queries[i:i+2])

            if not stopped_early and _has_sufficient_evidence(all_candidates):
                stopped_early = True
                telemetry["stopped_early"] = True
                telemetry["early_stop_reason"] = "SUFFICIENT_EVIDENCE_TARGETED_TIER"
                if serper_budget_manager:
                    serper_budget_manager.record_search_stopped_early(1)

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
    if reused_queries:
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

    # Phase 2: Generate facility aliases (if not already generated)
    if not facility_aliases:
        facility_aliases = generate_facility_aliases(
            facility_name=facility_name,
            city=city,
            state=INDIAN_CITIES_TO_STATE.get(city.lower(), ""),
        )

    all_candidates.sort(key=_person_sort_key)
    all_candidates = all_candidates[:15]

    # STAGE B: Targeted Exact-Name Verification with Multi-Candidate Fallback (Phase 5)
    # Evaluate serious candidates sequentially (up to 3).
    # Skip Stage B if a candidate is already conclusively verified with HIGH confidence for target facility.
    # Stop as soon as SUFFICIENT evidence is found for target facility.
    # If a candidate is CONTRADICTED, OTHER_FACILITY, or INSUFFICIENT, fallback to next credible candidate.
    already_conclusive = any(
        c.get("person_confidence") == "HIGH"
        and c.get("current_employment") == "VERIFIED"
        and c.get("facility_relationship") in ("FACILITY_OWNER", "FACILITY_FUNCTION_OWNER")
        for c in all_candidates[:3]
    )

    serious_candidates = [] if already_conclusive else [
        c for c in all_candidates
        if float(c.get("person_score", 0.0) or 0.0) >= 45.0
        and str(c.get("authority_class") or "") != "JUNIOR_IC"
    ][:max_stage_b_candidates]

    verified_map: Dict[str, Dict[str, Any]] = {}
    for serious_c in serious_candidates:
        c_name = str(serious_c.get("name") or "")
        norm_name = _normalize_person_name(c_name)
        updated_cand = verify_candidate_stage_b(
            candidate=serious_c,
            company_name=company_name,
            facility_name=facility_name,
            city=city,
            search_router=search_router,
            max_searches=max_stage_b_searches,
            company_domain=company_domain,
            telemetry=telemetry,
            facility_aliases=facility_aliases,
        )
        verified_map[norm_name] = updated_cand

        emp = str(updated_cand.get("current_employment") or "").upper()
        fac = str(updated_cand.get("facility_relationship") or "").upper()
        conf = str(updated_cand.get("person_confidence") or "").upper()
        score = float(updated_cand.get("person_score") or 0.0)

        is_sufficient = (
            conf == "HIGH"
            or (emp == "VERIFIED" and fac in ("FACILITY_OWNER", "FACILITY_FUNCTION_OWNER"))
            or (emp == "VERIFIED" and fac == "GROUP_FUNCTION_OWNER" and score >= 75.0)
        )
        if is_sufficient:
            # Sufficient target facility evidence established! Stop fallback.
            break

    verified_candidates = []
    for candidate in all_candidates:
        c_name_norm = _normalize_person_name(str(candidate.get("name") or ""))
        if c_name_norm in verified_map:
            verified_candidates.append(verified_map[c_name_norm])
        else:
            verified_candidates.append(candidate)

    all_candidates = verified_candidates
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
    primary = returned_candidates[0] if returned_candidates else None
    contact_route = primary.get("contact_route", "UNASSIGNED") if primary else "UNASSIGNED"
    return {
        "primary_person": primary,
        "secondary_person": returned_candidates[1] if len(returned_candidates) > 1 else None,
        "candidates": returned_candidates,
        "contact_route": contact_route,
        "candidates_before_llm": candidates_before_llm,
        "telemetry": telemetry,
    }
