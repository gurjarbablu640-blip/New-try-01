"""Salesoorja Plant-Specific Trigger Discovery Service.

Implements:
1. Explicit Trigger Taxonomy (PLANT_EXPANSION, NEW_PLANT, NEW_LINE, COMMISSIONING,
   METROLOGY_LAB_SETUP, QUALITY_LAB_SETUP, CAPACITY_EXPANSION, ORDER_RAMP_UP,
   QUALITY_HIRING, METROLOGY_HIRING, CALIBRATION_HIRING, INSTRUMENTATION_HIRING, etc.)
2. Source Tier Hierarchy (TIER_A: Press/BSE/Investor/Govt, TIER_B: Reputable news/industry,
   TIER_C: Job boards/LinkedIn, TIER_D: Generic marketing/SEO - cannot verify trigger)
3. Event Semantics Verification (rejects generic statements like 'leading manufacturer')
4. Date Extraction & Currentness Policy (0-180d = CURRENT, 181-365d = RECENT, >365d = STALE)
5. Facility Specificity Extraction (EXACT_FACILITY, INDUSTRIAL_AREA, CITY, STATE, COMPANY_ONLY)
6. Plant-Specific and Event-First Query Generators
"""
from __future__ import annotations

from datetime import datetime, timezone
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from services.evidence_provenance import extract_domain

logger = logging.getLogger(__name__)

# ── Trigger Taxonomy ──────────────────────────────────────────────────────────
TRIGGER_TYPES = {
    "PLANT_EXPANSION",
    "NEW_PLANT",
    "NEW_LINE",
    "COMMISSIONING",
    "NEW_EQUIPMENT",
    "NEW_LAB",
    "METROLOGY_LAB_SETUP",
    "QUALITY_LAB_SETUP",
    "CAPACITY_EXPANSION",
    "ORDER_RAMP_UP",
    "NEW_PRODUCT_MANUFACTURING",
    "CUSTOMER_OEM_APPROVAL",
    "EXPORT_RAMP",
    "RELOCATION",
    "PLANT_SHUTDOWN_MAINTENANCE",
    "AUDIT_CERTIFICATION",
    "QUALITY_HIRING",
    "METROLOGY_HIRING",
    "CALIBRATION_HIRING",
    "INSTRUMENTATION_HIRING",
    "MAINTENANCE_HIRING",
    "VALIDATION_QUALIFICATION",
    "FACILITY_MODERNIZATION",
}

HIRING_TRIGGER_TYPES = {
    "QUALITY_HIRING",
    "METROLOGY_HIRING",
    "CALIBRATION_HIRING",
    "INSTRUMENTATION_HIRING",
    "MAINTENANCE_HIRING",
}

# ── Source Tiers ──────────────────────────────────────────────────────────────
SOURCE_TIER_A = "TIER_A"  # Official IR/BSE/Govt/Press
SOURCE_TIER_B = "TIER_B"  # Reputable industry/business media
SOURCE_TIER_C = "TIER_C"  # LinkedIn posts, job boards, industry associations
SOURCE_TIER_D = "TIER_D"  # Generic home/about, directories, SEO articles (DISCOVERY ONLY)

TIER_A_DOMAINS = {
    "bseindia.com", "nseindia.com", "sebi.gov.in", "pib.gov.in", "dpiit.gov.in",
    "investindia.gov.in", "makeinindia.com", "midc.in", "tidco.com", "mca.gov.in"
}

TIER_B_DOMAINS = {
    "economictimes.indiatimes.com", "business-standard.com", "businesstoday.in",
    "livemint.com", "moneycontrol.com", "financialexpress.com", "thehindubusinessline.com",
    "thehindu.com", "reuters.com", "bloomberg.com", "autocarpro.in", "autocarindia.com",
    "evreporter.com", "pv-tech.org", "pharmabiz.com", "expresspharma.in", "electronicsforu.com",
    "cnbctv18.com", "ndtv.com", "freepressjournal.in", "businessworld.in", "fortuneindia.com",
    "timesofindia.indiatimes.com", "sahi.com", "crnasia.com"
}

TIER_C_DOMAINS = {
    "naukri.com", "indeed.com", "glassdoor.com", "shine.com", "monster.com",
    "timesjobs.com", "iimjobs.com", "hirist.com", "linkedin.com", "in.linkedin.com"
}


def classify_source_tier(url: str, domain: str = "", official_domain: str = "") -> str:
    """Classify the evidence tier of a discovered source."""
    clean_domain = (domain or extract_domain(url) or "").lower().replace("www.", "")
    clean_official = (official_domain or "").lower().replace("www.", "")
    url_lower = (url or "").lower()

    # Official company press release / IR
    if clean_official and (clean_domain == clean_official or clean_domain.endswith("." + clean_official)):
        if any(p in url_lower for p in ["press", "investor", "disclosure", "announcement", "news", "filing", "media"]):
            return SOURCE_TIER_A
        if any(p in url_lower for p in ["career", "careers", "jobs", "job", "opening"]):
            return SOURCE_TIER_A
        return SOURCE_TIER_D  # generic official homepage is Tier D (discovery only)

    # Global/corporate official press release paths
    if any(p in url_lower for p in ["/globalnews/", "/press-release", "/press_release", "/pressrelease", "/news-release"]):
        return SOURCE_TIER_A

    for d in TIER_A_DOMAINS:
        if clean_domain == d or clean_domain.endswith("." + d):
            return SOURCE_TIER_A

    for d in TIER_B_DOMAINS:
        if clean_domain == d or clean_domain.endswith("." + d):
            return SOURCE_TIER_B

    for d in TIER_C_DOMAINS:
        if clean_domain == d or clean_domain.endswith("." + d):
            return SOURCE_TIER_C

    return SOURCE_TIER_D


# ── Event Semantics Verification ──────────────────────────────────────────────
EVENT_ACTION_PATTERNS = [
    # Capex / Plant / Line Events
    (r"\b(will invest|is investing|invests|invested|investment of|investment planned|investment amount|investing in|capex of|capex planned)\b", "CAPACITY_EXPANSION"),
    (r"\b(commissioned|will commission|commissioning|inaugurated|opened|opening of|commencing operations|commence operations|commencement timing|starts production|started production)\b", "COMMISSIONING"),
    (r"\b(new plant|new manufacturing plant|new factory|new facility|construction of(?: [a-z]+)* plant|setting up plant|sets up plant|greenfield plant|second plant|third plant)\b", "NEW_PLANT"),
    (r"\b(new line|new manufacturing line|new assembly line|new production line|production line|new smt line|new press line)\b", "NEW_LINE"),
    (r"\b(expanding|expanding plant|plant expansion|expanding capacity|capacity expansion|capacity increased|facility expansion|expanding manufacturing)\b", "PLANT_EXPANSION"),
    (r"\b(new equipment|new machinery|production equipment|testing equipment)\b", "NEW_EQUIPMENT"),
    (r"\b(new lab|new laboratory|metrology lab|calibration lab|testing lab|quality laboratory|qc lab|qa lab)\b", "NEW_LAB"),
    (r"\b(commercial production|production commenced|commences production|ramp up|ramping up|production ramp)\b", "ORDER_RAMP_UP"),
    (r"\b(order awarded|bagged order|won contract|oem approval|oem nomination|customer approval)\b", "CUSTOMER_OEM_APPROVAL"),
    (r"\b(validation activity|validation qualification)\b", "VALIDATION_QUALIFICATION"),
    (r"\b(modernization|facility upgrade|retooling|equipment upgrade)\b", "FACILITY_MODERNIZATION"),
    # Hiring Events
    (r"\b(hiring|vacancy|opening|walk-in|recruiting|looking for)\b.*?\b(calibration|gauge|gage)\b", "CALIBRATION_HIRING"),
    (r"\b(hiring|vacancy|opening|walk-in|recruiting|looking for)\b.*?\b(metrology|measurement)\b", "METROLOGY_HIRING"),
    (r"\b(hiring|vacancy|opening|walk-in|recruiting|looking for)\b.*?\b(instrumentation|instrument)\b", "INSTRUMENTATION_HIRING"),
    (r"\b(hiring|vacancy|opening|walk-in|recruiting|looking for)\b.*?\b(plant quality|quality assurance|quality engineer|qa/qc)\b", "QUALITY_HIRING"),
    (r"\b(hiring|vacancy|opening|walk-in|recruiting|looking for)\b.*?\b(plant maintenance|equipment maintenance)\b", "MAINTENANCE_HIRING"),
]

GENERIC_STATEMENTS = [
    r"\bleading manufacturer\b",
    r"\bhas manufacturing plants\b",
    r"\bquality is our priority\b",
    r"\bwelcome to\b",
    r"\babout us\b",
    r"\btop solar panel company\b",
    r"\bshareholder information\b",
    r"\bshare price today\b",
]


def event_semantics_verified(snippet: str, title: str = "") -> Tuple[bool, str, str]:
    """Checks whether text contains real commercial/industrial EVENT semantics.

    Returns:
        (is_event_verified, trigger_type, event_description)
    """
    text = f"{title} {snippet}".strip()
    text_lower = text.lower()

    # Reject if only contains generic marketing/SEO statements
    for gen in GENERIC_STATEMENTS:
        if re.search(gen, text_lower) and len(text_lower.split()) < 20:
            return False, "UNKNOWN", f"Generic non-event statement matched '{gen}'"

    for pattern, trig_type in EVENT_ACTION_PATTERNS:
        match = re.search(pattern, text_lower)
        if match:
            matched_phrase = match.group(0)
            return True, trig_type, f"Actionable event confirmed: '{matched_phrase}'"

    return False, "UNKNOWN", "No actionable event semantics found in source snippet"


# ── Date & Currentness ────────────────────────────────────────────────────────
DATE_PATTERNS = [
    # YYYY-MM-DD or YYYY/MM/DD
    r"\b(20[12]\d[-/]\d{2}[-/]\d{2})\b",
    # DD Month YYYY or Month DD, YYYY
    r"\b(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*,?\s+20[12]\d)\b",
    r"\b((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+20[12]\d)\b",
    # Month YYYY
    r"\b((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+20[12]\d)\b",
    # Relative: X days/weeks/months ago
    r"\b(\d+\s+(?:days?|weeks?|months?|hours?)\s+ago)\b",
    # Bare Year: 2018-2027
    r"\b(20[12]\d)\b",
]


def extract_event_date(text: str, title: str = "", now_dt: datetime | None = None) -> Dict[str, Any]:
    """Extract event publication/action date and compute recency status."""
    from datetime import timedelta
    combined_text = f"{text} {title}".strip()
    now_dt = now_dt or datetime.now(timezone.utc)
    for pat in DATE_PATTERNS:
        m = re.search(pat, combined_text, re.IGNORECASE)
        if m:
            raw_date = m.group(1).strip()
            # Check relative date
            m_rel = re.search(r"(\d+)\s+(day|week|month|hour)s?\s+ago", raw_date, re.IGNORECASE)
            if m_rel:
                val = int(m_rel.group(1))
                unit = m_rel.group(2).lower()
                if unit == "hour":
                    dt = now_dt - timedelta(hours=val)
                elif unit == "day":
                    dt = now_dt - timedelta(days=val)
                elif unit == "week":
                    dt = now_dt - timedelta(weeks=val)
                elif unit == "month":
                    dt = now_dt - timedelta(days=val * 30)
                recency_days = max(0, (now_dt - dt).days)
                return {
                    "event_date": dt.strftime("%Y-%m-%d"),
                    "recency_days": recency_days,
                    "ongoing_status": "CURRENT" if recency_days <= 180 else "RECENT",
                    "recency_status": "CURRENT" if recency_days <= 180 else "RECENT",
                    "has_date": True,
                }

            # Attempt parsing absolute date
            recency_days = 90  # Default if only year/month
            clean_date_str = raw_date.replace(",", "")
            for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d %b %Y", "%d %B %Y", "%B %d %Y", "%b %d %Y", "%B %Y", "%b %Y", "%Y"):
                try:
                    dt = datetime.strptime(clean_date_str, fmt).replace(tzinfo=timezone.utc)
                    recency_days = max(0, (now_dt - dt).days)
                    break
                except (ValueError, Exception):
                    pass

            if recency_days <= 180:
                rec_status = "CURRENT"
            elif recency_days <= 365:
                rec_status = "RECENT"
            else:
                rec_status = "STALE"

            return {
                "event_date": raw_date,
                "recency_days": recency_days,
                "ongoing_status": rec_status,
                "recency_status": rec_status,
                "has_date": True,
            }

    return {
        "event_date": "",
        "recency_days": 999,
        "ongoing_status": "DATE_UNKNOWN",
        "recency_status": "DATE_UNKNOWN",
        "has_date": False,
    }


# ── Facility Link & Specificity in Trigger Discovery ─────────────────────────
INDUSTRIAL_AREA_KEYWORDS = [
    "midc", "gidc", "riico", "sipcot", "tidco", "kiadb", "hsiidc", "dic",
    "industrial area", "industrial estate", "industrial park", "industrial corridor",
    "sez", "export promotion park", "electronic city", "aerospace park",
    "phase i", "phase ii", "phase 1", "phase 2", "plot no", "gate no",
]


def extract_trigger_facility_link(
    text: str,
    known_city: str = "",
    known_industrial_area: str = "",
    known_plants: Optional[List[str]] = None,
    known_plant_name: str = "",
) -> Dict[str, Any]:
    """Extracts facility location details from trigger text and assigns specificity level:

    Specificity Levels:
    - EXACT_FACILITY: names a specific named unit / plant / plot
    - INDUSTRIAL_AREA: names a specific industrial estate/park/MIDC
    - CITY: names a specific city
    - STATE: names only a state
    - COMPANY_ONLY: no location mentioned
    """
    text_lower = text.lower()
    city_from_trigger = ""
    area_from_trigger = ""
    fac_name_from_trigger = ""
    specificity = "COMPANY_ONLY"

    plants_to_check = list(known_plants or [])
    if known_plant_name and known_plant_name not in plants_to_check:
        plants_to_check.append(known_plant_name)

    # 1. Exact facility / plant name matching
    if plants_to_check:
        for plant in plants_to_check:
            if plant.lower() in text_lower:
                fac_name_from_trigger = plant
                specificity = "EXACT_FACILITY"
                break

    # Plant naming regex e.g. "Chakan plant", "Sanand facility", "Unit 2", "Plant II"
    if not fac_name_from_trigger:
        plant_match = re.search(r"\b([A-Za-z]+(?:\s+[A-Za-z]+)?\s+(?:plant|facility|works|unit\s+\d+|unit\s+[IVX]+))\b", text_lower)
        if plant_match:
            candidate_plant = plant_match.group(1).strip()
            invalid_plant_terms = {
                "power", "solar", "steel", "chemical", "manufacturing", "crore",
                "mother", "new", "existing", "proposed", "mega", "upcoming",
                "second", "third", "first", "the", "a", "an", "its", "our",
                "this", "each", "every", "that", "their", "current", "assembly",
                "integrated", "dedicated", "advanced", "modern", "latest"
            }
            valid_words = [
                w for w in candidate_plant.split()
                if w.lower() not in invalid_plant_terms and w.lower() not in {"plant", "facility", "works"}
            ]
            if valid_words:
                fac_name_from_trigger = candidate_plant.title()
                if specificity != "EXACT_FACILITY":
                    specificity = "EXACT_FACILITY"

    # 2. Industrial area matching
    if known_industrial_area and known_industrial_area.lower() in text_lower:
        area_from_trigger = known_industrial_area
        if specificity != "EXACT_FACILITY":
            specificity = "INDUSTRIAL_AREA"
    else:
        for kw in INDUSTRIAL_AREA_KEYWORDS:
            if kw in text_lower:
                area_match = re.search(r"\b([A-Za-z]+(?:\s+[A-Za-z]+)?\s+" + re.escape(kw) + r")\b", text_lower)
                area_from_trigger = area_match.group(1).title() if area_match else kw.upper()
                if specificity != "EXACT_FACILITY":
                    specificity = "INDUSTRIAL_AREA"
                break

    # 3. City matching
    if known_city and known_city.lower() in text_lower:
        city_from_trigger = known_city
        if specificity not in ("EXACT_FACILITY", "INDUSTRIAL_AREA"):
            specificity = "CITY"
    else:
        # Common industrial cities
        common_cities = [
            "chakan", "pune", "sanand", "bawal", "coimbatore", "hosur", "noida",
            "gurugram", "gurgaon", "manesar", "aurangabad", "waluj", "chennai",
            "oragadam", "sriperumbudur", "bengaluru", "bangalore", "mysuru", "mysore",
            "jamshedpur", "vadodara", "savli", "makarpura", "nagpur", "butibori",
            "jabalpur", "kolhapur", "kagal", "dewas", "parwanoo", "navsari", "surat"
        ]
        for c in common_cities:
            if re.search(r"\b" + re.escape(c) + r"\b", text_lower):
                city_from_trigger = c.title()
                if specificity not in ("EXACT_FACILITY", "INDUSTRIAL_AREA"):
                    specificity = "CITY"
                break

    return {
        "facility_name_from_trigger": fac_name_from_trigger,
        "facility_city_from_trigger": city_from_trigger or known_city,
        "facility_area_from_trigger": area_from_trigger,
        "trigger_facility_specificity": specificity,
    }


def generate_plant_specific_queries(
    company_name: str,
    domain: str = "",
    known_city: str = "",
    known_area: str = "",
    official_domain: str = "",
    city: str = "",
    sector: str = "",
) -> List[str]:
    """Generate high-signal, plant-specific queries incorporating 2026/2025 recency, known plants, and hiring vocabulary."""
    clean_domain = (domain or official_domain).lower().replace("www.", "")
    target_city = known_city or city
    queries = []

    # 1. Capex / Commissioning / Expansion queries
    if target_city:
        queries.append(f'"{company_name}" "{target_city}" expansion plant 2026 India')
        queries.append(f'"{company_name}" "{target_city}" commissioning 2026')
        queries.append(f'"{company_name}" new line "{target_city}" 2026')
        queries.append(f'"{company_name}" capex "{target_city}" 2025 OR 2026')
    else:
        queries.append(f'"{company_name}" expansion plant 2026 India')
        queries.append(f'"{company_name}" commissioning plant 2026')

    # 2. Quality / Metrology / Lab setup queries
    if target_city:
        queries.append(f'"{company_name}" "{target_city}" metrology lab')
        queries.append(f'"{company_name}" "{target_city}" quality hiring')
    else:
        queries.append(f'"{company_name}" quality lab setup 2025 OR 2026')
        queries.append(f'"{company_name}" metrology engineer hiring India')

    # 3. Official domain searches
    if clean_domain:
        queries.append(f'site:{clean_domain} expansion 2026')
        queries.append(f'site:{clean_domain} commissioning')
        queries.append(f'site:{clean_domain} capex')
        queries.append(f'site:{clean_domain} filetype:pdf expansion')

    return queries


# ── Event-First Discovery Queries (Phase 11) ──────────────────────────────────
EVENT_FIRST_SEARCH_QUERIES = [
    "India new manufacturing plant September 2026",
    "India manufacturing expansion September 2026 capex",
    "new automotive plant commissioning India 2026",
    "new electronics factory India SMT 2026",
    "new EV component plant India 2026 capex",
    "new solar module line India 2026 commissioning",
    "new battery gigafactory plant India 2026",
    "new aerospace manufacturing facility India 2026",
    "manufacturing plant commissioning India 2026",
    "quality metrology hiring plant India 2026",
]


def generate_event_first_discovery_queries() -> List[str]:
    """Generates the Phase 11 event-first discovery query list."""
    return list(EVENT_FIRST_SEARCH_QUERIES)
