"""Entity Truth Gate — Hardened Company Entity Resolution and False-Positive Suppression.

Implements Task 3C.1 deterministic entity classification:
- Explicit EntityType classifications (COMPANY, PERSON, PUBLISHER, NEWS_SOURCE, DIRECTORY,
  JOB_PORTAL, GOVERNMENT_SECTOR_LABEL, PRODUCT_OR_SERVICE, ARTICLE_HEADLINE_FRAGMENT,
  GENERIC_INDUSTRY_TERM, NAVIGATION_LABEL, UNKNOWN)
- Layered deterministic entity classification pipeline:
  1. Normalization (whitespace, quotes, HTML artifacts, bullets; preserve '&', '-', '.', '+')
  2. Obvious non-company rejection (empty, length < 2, numeric counters, dates, calendar years)
  3. Bounded in-memory rejected-entity cache
  4. Public figures & conservative person suppression
  5. Navigation & generic page labels
  6. Headline predicate verbs / editorial fragments
  7. Geographic locations alone
  8. Events, expos, summits, schemes, policies
  9. Publisher & news source suppression (dynamic domain + known list)
  10. Directory & job portal suppression
  11. Generic phrase, commercial offer, product, and government sector suppression
  12. Company positive shape validation
- Headline boundary trimming:
  Isolates corporate subject before action/predicate verbs when resolving entities from titles/headlines.
- Persistence guard: only EntityType.COMPANY may proceed into Company persistence.
"""
from __future__ import annotations

import html
import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class EntityType:
    COMPANY = "COMPANY"
    PERSON = "PERSON"
    PUBLISHER = "PUBLISHER"
    NEWS_SOURCE = "NEWS_SOURCE"
    DIRECTORY = "DIRECTORY"
    JOB_PORTAL = "JOB_PORTAL"
    GOVERNMENT_SECTOR_LABEL = "GOVERNMENT_SECTOR_LABEL"
    PRODUCT_OR_SERVICE = "PRODUCT_OR_SERVICE"
    ARTICLE_HEADLINE_FRAGMENT = "ARTICLE_HEADLINE_FRAGMENT"
    GENERIC_INDUSTRY_TERM = "GENERIC_INDUSTRY_TERM"
    NAVIGATION_LABEL = "NAVIGATION_LABEL"
    UNKNOWN = "UNKNOWN"


# Telemetry counters for entity classification and lifecycle
ENTITY_TELEMETRY: Dict[str, int] = {
    "ENTITY_RAW_CANDIDATES": 0,
    "ENTITY_COMPANY_ACCEPTED": 0,
    "ENTITY_REJECT_PERSON": 0,
    "ENTITY_REJECT_PUBLISHER": 0,
    "ENTITY_REJECT_DIRECTORY": 0,
    "ENTITY_REJECT_HEADLINE_FRAGMENT": 0,
    "ENTITY_REJECT_GENERIC": 0,
    "ENTITY_REJECT_PRODUCT_SERVICE": 0,
    "ENTITY_REJECT_NAVIGATION": 0,
    "ENTITY_REJECT_AMBIGUOUS": 0,
    "ENTITY_NORMALIZED_MATCH": 0,
    "COMPANY_ROWS_CREATED": 0,
}


def reset_entity_telemetry() -> None:
    for k in ENTITY_TELEMETRY:
        ENTITY_TELEMETRY[k] = 0


def record_entity_telemetry(entity_class: str) -> None:
    ENTITY_TELEMETRY["ENTITY_RAW_CANDIDATES"] += 1
    if entity_class == EntityType.COMPANY:
        ENTITY_TELEMETRY["ENTITY_COMPANY_ACCEPTED"] += 1
    elif entity_class == EntityType.PERSON:
        ENTITY_TELEMETRY["ENTITY_REJECT_PERSON"] += 1
    elif entity_class in (EntityType.PUBLISHER, EntityType.NEWS_SOURCE):
        ENTITY_TELEMETRY["ENTITY_REJECT_PUBLISHER"] += 1
    elif entity_class in (EntityType.DIRECTORY, EntityType.JOB_PORTAL):
        ENTITY_TELEMETRY["ENTITY_REJECT_DIRECTORY"] += 1
    elif entity_class == EntityType.ARTICLE_HEADLINE_FRAGMENT:
        ENTITY_TELEMETRY["ENTITY_REJECT_HEADLINE_FRAGMENT"] += 1
    elif entity_class in (EntityType.GENERIC_INDUSTRY_TERM, EntityType.GOVERNMENT_SECTOR_LABEL):
        ENTITY_TELEMETRY["ENTITY_REJECT_GENERIC"] += 1
    elif entity_class == EntityType.PRODUCT_OR_SERVICE:
        ENTITY_TELEMETRY["ENTITY_REJECT_PRODUCT_SERVICE"] += 1
    elif entity_class == EntityType.NAVIGATION_LABEL:
        ENTITY_TELEMETRY["ENTITY_REJECT_NAVIGATION"] += 1
    else:
        ENTITY_TELEMETRY["ENTITY_REJECT_AMBIGUOUS"] += 1


# Bounded in-memory LRU cache for rejected entities
_REJECTED_ENTITIES_CACHE: Dict[str, Dict[str, Any]] = {}
_MAX_REJECTED_CACHE_SIZE = 1000


def get_cached_rejection(norm_key: str) -> Optional[Tuple[str, str]]:
    if norm_key in _REJECTED_ENTITIES_CACHE:
        entry = _REJECTED_ENTITIES_CACHE[norm_key]
        return entry["entity_class"], entry["reason"]
    return None


def cache_rejection(norm_key: str, entity_class: str, reason: str, context: str = "") -> None:
    if len(_REJECTED_ENTITIES_CACHE) >= _MAX_REJECTED_CACHE_SIZE:
        for k in list(_REJECTED_ENTITIES_CACHE.keys())[:200]:
            _REJECTED_ENTITIES_CACHE.pop(k, None)
    _REJECTED_ENTITIES_CACHE[norm_key] = {
        "entity_class": entity_class,
        "reason": reason,
        "context": context[:100],
    }


def clear_rejected_entities_cache() -> None:
    _REJECTED_ENTITIES_CACHE.clear()


# Indian states and union territories
INDIAN_STATES = {
    "andhra pradesh", "arunachal pradesh", "assam", "bihar", "chhattisgarh",
    "goa", "gujarat", "haryana", "himachal pradesh", "jharkhand", "karnataka",
    "kerala", "madhya pradesh", "maharashtra", "manipur", "meghalaya", "mizoram",
    "nagaland", "odisha", "punjab", "rajasthan", "sikkim", "tamil nadu",
    "telangana", "tripura", "uttar pradesh", "uttarakhand", "west bengal",
    "delhi", "jammu and kashmir", "ladakh", "chandigarh", "puducherry", "india",
}

# Major cities / industrial hubs when appearing alone
INDIAN_CITIES = {
    "mumbai", "pune", "delhi", "bengaluru", "bangalore", "chennai", "hyderabad",
    "ahmedabad", "kolkata", "surat", "vadodara", "rajkot", "sanand", "chakan",
    "manesar", "gurugram", "gurgaon", "noida", "greater noida", "faridabad",
    "coimbatore", "hosur", "sriperumbudur", "oragadam", "bikaner", "kheda",
    "kalpakkam", "nashik", "aurangabad", "chhatrapati sambhaji nagar", "nagpur",
    "indore", "bhopal", "dharwad", "belagavi", "mysuru", "jamshedpur", "ranchi",
    "kanpur", "lucknow", "ghaziabad", "ludhiana", "jaipur", "visakhapatnam",
}

# Political titles, public figures, and honorifics
POLITICAL_AND_PUBLIC_FIGURE_PATTERNS = [
    r"\bpm\s+modi\b",
    r"\bprime\s+minister\b",
    r"\bchief\s+minister\b",
    r"\b(?:cm|pm)\b",
    r"\b(?:shri|smt|dr|mr|mrs|ms|prof)\b",
    r"\bhon(?:ou?rable|\'ble)?\b",
    r"\bminister\b",
    r"\bgovernor\b",
    r"\bpresident\b",
    r"\bsecretary\b",
    r"\bspokesperson\b",
    r"\bambassador\b",
    r"\bmla\b",
    r"\bmp\b",
    r"\byogi\s+adityanath\b",
    r"\bnarendra\s+modi\b",
    r"\bmk\s+stalin\b",
    r"\bhupendra\s+patel\b",
]

# Action verbs and predicate phrases common in news headlines
HEADLINE_VERB_PATTERNS = [
    r"\blaunches\b", r"\blaunched\b",
    r"\binaugurates\b", r"\binaugurated\b",
    r"\bcommissions\b", r"\bcommissioned\b",
    r"\bsets\s+up\b", r"\bsetting\s+up\b", r"\bto\s+set\s+up\b",
    r"\bexpands\b", r"\bexpanded\b",
    r"\binvests\b", r"\binvesting\b",
    r"\bannounces\b", r"\bannounced\b",
    r"\bvisits\b", r"\bvisiting\b",
    r"\bsecures\b", r"\bsecured\b",
    r"\bcelebrates\b", r"\bcelebrated\b",
    r"\bbegins\b", r"\bbegun\b",
    r"\bunveils\b", r"\bunveiled\b",
    r"\bboosts\b", r"\bboosted\b",
    r"\bsigns\b", r"\bsigned\b",
    r"\bmeets\b", r"\bmeeting\b",
    r"\breveals\b", r"\brevealed\b",
    r"\boperationalizes?\b", r"\boperationalised\b",
    r"\bapproves?\b", r"\bapproved\b",
    r"\blays\s+foundation\b",
    r"\binks\s+mou\b", r"\bsigns\s+mou\b",
    r"\beyes\b", r"\bplans\b", r"\bplanned\b",
    r"\bopens\b", r"\bopened\b",
    r"\brelocates\b", r"\brelocated\b", r"\bto\s+relocate\b",
    r"\bto\s+build\b", r"\bto\s+invest\b",
    r"\bhas\b", r"\bgets\b", r"\bwins\b", r"\braises\b",
    r"\battracts\b", r"\bacquires\b",
    r"\bto\s+supply\b", r"\bsupplies\b", r"\bsupplied\b",
    r"\bto\s+deliver\b", r"\bdelivers\b", r"\bdelivered\b",
    r"\bto\s+provide\b", r"\bprovides\b", r"\bprovided\b",
    r"\bto\s+manufacture\b", r"\bmanufactures\b", r"\bmanufactured\b",
    r"\bto\s+install\b", r"\binstalls\b", r"\binstalled\b",
    r"\bto\s+establish\b", r"\bestablishes\b", r"\bestablished\b",
    r"\bawards?\b", r"\bawarded\b",
    r"\bbags?\s+order\b", r"\bbags?\s+contract\b",
    r"\bsecures?\s+order\b", r"\bsecures?\s+contract\b",
    r"\bwins?\s+order\b", r"\bwins?\s+contract\b",
    r"\breceives?\s+order\b", r"\breceives?\s+contract\b", r"\breceived\s+order\b", r"\breceived\s+contract\b",
    r"\bto\s+develop\b", r"\bdevelops\b", r"\bdeveloped\b",
    r"\bto\s+execute\b", r"\bexecutes\b", r"\bexecuted\b",
    r"\bto\s+construct\b", r"\bconstructs\b", r"\bconstructed\b",
    r"\bto\s+implement\b", r"\bimplements\b", r"\bimplemented\b",
    # Task 3C.1.3 Expanded Action / Predicate Boundaries (Section 7)
    r"\bto\s+roll\s+out\b", r"\brolls\s+out\b", r"\brolled\s+out\b", r"\brolling\s+out\b",
    r"\bto\s+introduce\b", r"\bintroduces\b", r"\bintroduced\b", r"\bintroducing\b",
    r"\bto\s+produce\b", r"\bproduces\b", r"\bproduced\b", r"\bproducing\b",
    r"\bto\s+start\b", r"\bstarts\b", r"\bstarted\b", r"\bstarting\b",
    r"\bto\s+begin\b", r"\bbegins\b", r"\bbegan\b", r"\bbeginning\b",
    r"\bto\s+commence\b", r"\bcommences\b", r"\bcommenced\b", r"\bcommencing\b",
    r"\bto\s+launch\b", r"\blaunching\b",
    r"\bto\s+expand\b", r"\bexpanding\b",
    r"\bto\s+open\b", r"\bopening\b",
    r"\bto\s+raise\b", r"\braises\b", r"\braised\b", r"\braising\b",
    r"\bto\s+acquire\b", r"\bacquires\b", r"\bacquired\b", r"\bacquiring\b",
    r"\bto\s+set\s+up\b", r"\bsetting\s+up\b",
    r"\bwill\s+(?:build|invest|launch|start|expand|produce|manufacture|set\s+up|roll\s+out|develop|supply|install|add|open|establish|commence)\b",
    r"\bplans\s+to\b", r"\baims\s+to\b", r"\bexpects\s+to\b",
]


# Project Trackers, B2B Information Portals, and Industrial Databases
PROJECT_TRACKER_AND_PORTAL_PATTERNS = [
    r"\b(?:projects?|projectx|capex|tender|tenders)\s*(?:tracker|tracking|intelligence|monitor|database|portal|alert|alerts|info|watch|x)\b",
    r"^(?:new\s+)?projects?\s+(?:india|tracker|tracking|database|portal|monitor)\b",
    r"^welcome\s+to\s+.*\b(?:tracker|tracking|projects?|portal|database)\b",
    r"\b(?:market|business|industrial|industry|project)\s+intelligence\b",
    r"\b(?:industrial|industry|b2b|trade)\s+(?:media|portal|database|platform|insights?)\b",
    r"\b(?:projects?|tenders?)\s+database\b",
]

PROJECT_TRACKER_AND_PORTAL_DOMAINS = [
    "projectx", "projectxindia", "newprojectstracker", "projecttracker",
    "projectmonitor", "industrialprojects", "projectsindia", "projects-india",
    "projectstracker", "projectalert", "capextracker", "b2bportal", "tendersinfo",
]

MANUFACTURING_OWNERSHIP_PATTERNS = [
    r"\b(?:our|its)\s+(?:manufacturing\s+plants?|factory|factories|production\s+facilities?|manufacturing\s+facilities?|manufacturing\s+units?|manufacturing\s+locations?|plants?)\b",
    r"\b(?:we|company)\s+(?:manufacture|manufactures|produce|produces|fabricate|fabricates|operates?\s+(?:a|the|its)?\s*(?:plant|factory|facility))\b",
    r"\b(?:production|manufacturing)\s+capacity\s+of\b",
    r"\b(?:factory|plant)\s+address\b",
    r"\bfacility\s+ownership\b",
    r"\bour\s+facility\s+in\b",
    r"\bmanufacturing\s+facility\s+in\b",
]

# Superlative / Incomplete editorial headline fragments (Task 3C.1.3 Section 6)
SUPERLATIVE_AND_EDITORIAL_FRAGMENT_PATTERNS = [
    r"^(?:indias?|india['’]s|world(?:['’]s)?|asia(?:['’]s)?|global)\s+(?:top|fastest|leading|largest|biggest|best|growing)\b",
    r"^(?:top|fastest|leading|largest|biggest|best)\s+(?:fastest|growing|growth|manufacturers?|companies|players?|producers?|exporters?|suppliers?|startups?|\d+)\b",
    r"^(?:top|fastest|leading|largest|biggest|best)$",
    r"\b(?:fastest[- ]growing|leading\s+manufacturers?|top\s+fastest|top\s+growing|largest\s+players?|best\s+companies|top\s+companies|top\s+\d+)\b",
]

# Generic Industry / Service Category detection (Task 3C.1.3 Section 4 & 5)
GENERIC_CATEGORY_AND_INDUSTRY_PATTERNS = [
    r"\b(?:contract|electronics|semiconductor|battery|solar\s+module|automotive|precision\s+engineering|electrical\s+equipment|industrial\s+automation|renewable\s+energy|metal\s+fabrication|packaging\s+machinery|cnc\s+machining)\s+(?:manufacturing\s+services?|manufacturing|components?|solutions?|manufacturers?|systems?|equipments?|technolog(?:y|ies))\b",
    r"^(?:electronics|contract|semiconductor|battery|automotive|aerospace|pharmaceutical|chemical|textile|plastics?|metal|precision|solar|wind|ev)\s+(?:manufacturing\s+services?|manufacturing|components?|solutions?|manufacturers?|systems?|equipments?|services?)\b",
    r"\b(?:manufacturing\s+services?|contract\s+manufacturing|precision\s+engineering\s+services?|industrial\s+automation\s+solutions?|electrical\s+equipment\s+manufacturers?|solar\s+module\s+manufacturing|battery\s+manufacturing|semiconductor\s+manufacturing\s+services?)\b",
    r"^(?:electronics\s+manufacturing\s+services|contract\s+manufacturing\s+services|automotive\s+components|precision\s+engineering\s+services|solar\s+module\s+manufacturing|battery\s+manufacturing|electrical\s+equipment\s+manufacturers|industrial\s+automation\s+solutions|semiconductor\s+manufacturing\s+services)$",
]

# Events, expos, conferences, and exhibitions
EVENT_PATTERNS = [
    r"\bexpo\b", r"\bexhibition\b", r"\bsummit\b", r"\bconclave\b",
    r"\bconference\b", r"\bforum\b", r"\bsymposium\b", r"\bfair\b",
    r"\btrade\s+show\b",
]

# Government schemes, policies, and administrative releases
GOVERNMENT_SCHEME_PATTERNS = [
    r"\bscheme\b", r"\byojana\b", r"\bpolicy\b", r"\binitiative\b",
    r"\bmission\b", r"\blandscape\b", r"\bgovt\b", r"\bgovernment\b",
    r"\bministry\b", r"\bdepartment\b", r"\bpress\s+notes?\b",
    r"\bpress\s+release\b", r"\bcabinet\b", r"\bhub\b", r"\bcorridor\b",
]

# Generic adjectives, numbers, and editorial words
GENERIC_NON_COMPANY_WORDS = {
    "huge", "new", "latest", "big", "major", "upcoming", "top", "global",
    "scale", "verified", "projects", "news", "report", "overview", "market",
    "hiring", "jobs", "why", "how", "what", "where", "when", "indias", "india",
    "decoding", "here", "today", "tomorrow", "single", "world", "largest",
    "product", "products", "catalog", "catalogue", "brochure", "brochures",
    "services", "equipment", "machinery", "category", "categories",
    "specification", "specifications", "downloads", "gallery", "portfolio",
    "mega", "ultra", "prime", "smart", "eco", "green", "clean", "future",
    "vision", "national", "premier", "online", "portal", "platform", "app",
    "fastest", "leading", "growing", "growth", "best", "biggest",
    "manufacturing", "contract", "electronics", "components", "solutions",
    "engineering", "automation", "electrical", "semiconductor",
}

# Generic page, navigation, section, and website content labels
GENERIC_PAGE_AND_NAVIGATION_PATTERNS = [
    r"^our\s+(?:businesses|business|products|services|solutions|company|presence|offerings|team|people|vision|mission|brands|portfolio|clients|partners|ventures|divisions|units|locations|facilities|operations|leaders(?:hip)?|story|journey|catalog|catalogue|brochure)$",
    r"^about\s+(?:us|the\s+company|our\s+company|our\s+group|group|ourselves)$",
    r"^(?:who\s+we\s+are|what\s+we\s+do|where\s+we\s+are|where\s+we\s+operate|how\s+we\s+work|why\s+choose\s+us|how\s+we\s+do\s+it)$",
    r"^(?:contact\s+(?:us|me)?|get\s+in\s+touch|reach\s+us|locate\s+us|find\s+us)$",
    r"^(?:investor\s+relations|investors?|financial\s+results|annual\s+reports?|quarterly\s+results|corporate\s+governance|shareholder\s+information)$",
    r"^(?:careers?|job\s+openings?|work\s+with\s+us|join\s+(?:us|our\s+team)|current\s+openings?|employment\s+opportunities?)$",
    r"^(?:home(?:page)?|main\s+page|overview|company\s+overview|business\s+overview|corporate\s+overview|welcome)$",
    r"^(?:media(?:\s+centre|\s+center)?|news(?:\s+(&|and)\s+media)?|press\s+releases?|in\s+the\s+news|latest\s+news|newsroom)$",
    r"^(?:locations?|our\s+locations?|global\s+presence|manufacturing\s+facilities|manufacturing\s+locations|our\s+facilities|facilities|plants?)$",
    r"^(?:industries(?:\s+served)?|sectors|solutions|products\s+(&|and)\s+services|services\s+(&|and)\s+products|our\s+offerings|offerings)$",
    r"^(?:products?|services?|equipment|machinery|instrument|component)\s+(?:catalog|catalogue|brochure|line|range|category|categories|list|portfolio|specifications?|details|offerings?)$",
    r"^(?:catalog|catalogue|brochure|brochures|whitepapers?|case\s+studies|downloads?|gallery|faq|faqs|blog|blogs|articles?|sitemap|privacy\s+policy|terms\s+(?:of\s+use|and\s+conditions)|disclaimer)$",
    r"^(?:business|businesses|manufacturing|corporate|enterprise|services?|products?|solutions?|industries|facilities|locations?|overview|careers?|news|media|home|catalog|catalogue|brochure|brochures|downloads?)$",
]

# Directory, aggregator, job board, and reporting platforms
DIRECTORY_AND_JOB_DOMAINS = {
    "naukri.com", "indeed.com", "indiamart.com", "tradeindia.com", "scribd.com",
    "zaubacorp.com", "tofler.in", "quickr.com", "justdial.com", "linkedin.com",
    "glassdoor.com", "shine.com", "foundit.in", "monsterindia.com",
    "yellowpages.in", "sulekha.com", "exportersindia.com",
}

# Common news, aggregator, media, and analyst domains
NEWS_AND_AGGREGATOR_DOMAINS = {
    "thehindubusinessline.com", "economictimes.indiatimes.com", "business-standard.com", "livemint.com",
    "thehindu.com", "hindustantimes.com", "timesofindia.indiatimes.com",
    "reuters.com", "bloomberg.com", "cnbctv18.com", "moneycontrol.com",
    "financialexpress.com", "ndtv.com", "ndtvprofit.com", "zeeconnect.com",
    "theprint.in", "thewire.in", "scroll.in", "indiatoday.in", "news18.com",
    "pib.gov.in", "bseindia.com", "nseindia.com", "pv-magazine-india.com",
    "pv-magazine.com", "autocarpro.in", "etauto.com", "jmkresearch.com",
    "ibef.org", "mercomindia.com", "saurenergy.com", "energytrend.com",
    "spglobal.com", "woodmac.com", "fitchratings.com", "crisil.com",
    "icra.in", "careedge.in", "careratings.com", "investingintamilnadu.com",
    "nredcap.in", "autopunditz.com", "poidata.io",
}

# Known news, publisher, and research institute names for high-confidence shortcut
KNOWN_PUBLISHERS = {
    "pv magazine", "pv magazine india", "ibef", "businessline", "the hindu businessline",
    "economic times", "the economic times", "jmk research", "reuters", "bloomberg",
    "moneycontrol", "financial express", "livemint", "times of india", "business standard",
    "etauto", "autocar professional", "s&p global", "zee news", "ndtv", "ndtv profit",
    "cnbc-tv18", "cnbc tv18", "hindustan times", "the print", "the wire", "scroll.in",
    "pib", "pib delhi", "mercom india", "saur energy", "crisil", "icra", "care ratings",
    "careedge", "autopunditz", "poi data", "investing in tamil nadu",
}

# Recognized corporate suffixes indicating an actual organization
LEGAL_CORPORATE_SUFFIX_PATTERN = re.compile(
    r"\b(?:ltd|limited|pvt|private\s+limited|pvt\s+ltd|inc|incorporated|corp|corporation|gmbh|llc|plc)\b",
    re.IGNORECASE,
)

CORPORATE_SUFFIX_PATTERN = re.compile(
    r"\b(ltd|limited|pvt|private|inc|corp|corporation|gmbh|llc|co|enterprises|"
    r"industries|technologies|electronics|motors|energy|solutions|systems|"
    r"group|holdings|works|infra|power|engineering|manufacturing|components|"
    r"steel|chemicals|fasteners|renewables|auto|automotive|instruments)\b",
    re.IGNORECASE,
)


def normalize_entity_candidate(raw: str) -> str:
    """Normalizes whitespace, HTML entities, leading/trailing punctuation, quotes, bullets.
    Preserves meaningful corporate punctuation: '&', '-', '.', '+'.
    """
    if not raw:
        return ""
    text = html.unescape(str(raw))
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(
        r"^[\s\"'“”‘’•·\-\|\:\;\(\)\[\]\{\}\,\.\*]+|[\s\"'“”‘’•·\-\|\:\;\(\)\[\]\{\}\,\.\*]+$",
        "",
        text,
    ).strip()
    return text


def get_normalized_comparison_key(name: str) -> str:
    """Generates a canonical lookup key for deduplication.
    Normalizes legal suffixes (Pvt Ltd, Limited, LLP, etc.) and punctuation,
    WITHOUT altering the evidence-grounded display/canonical company name.
    """
    clean = normalize_entity_candidate(name).casefold()
    clean = re.sub(
        r"\b(?:private\s+limited|pvt\.?\s*ltd\.?|limited|ltd\.?|llp|inc\.?|corp\.?|corporation|gmbh|co\.?|co\s+ltd\.?)\b",
        "",
        clean,
        flags=re.IGNORECASE,
    ).strip()
    clean = re.sub(r"[^\w\s]", "", clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def trim_headline_subject_boundary(text: str) -> Tuple[str, bool]:
    """Isolates the corporate subject boundary preceding action/predicate text in headlines.

    Examples:
    'Waaree Energies relocates 6GW vertically' -> ('Waaree Energies', True)
    'Maruti Suzuki has' -> ('Maruti Suzuki', True)
    'ITP Aero has' -> ('ITP Aero', True)
    'Toyota to build three assembly plants' -> ('Toyota', True)

    Returns (trimmed_subject, did_trim).
    CRITICAL: Only accepts the left-hand portion if it independently passes company validation!
    """
    raw = normalize_entity_candidate(text)
    if not raw:
        return "", False

    for verb_pat in HEADLINE_VERB_PATTERNS:
        match = re.search(verb_pat, raw, re.IGNORECASE)
        if match:
            lead_candidate = raw[: match.start()].strip()
            lead_candidate = re.sub(r"[,;:\-\s]+$", "", lead_candidate).strip()
            lead_candidate = re.sub(r"\s+(?:in|at|to|on|for|with|by|of)$", "", lead_candidate, flags=re.I).strip()
            if len(lead_candidate) >= 2 and len(lead_candidate.split()) <= 5:
                valid, _ = validate_company_entity(lead_candidate)
                if valid:
                    return lead_candidate, True

    return raw, False


def classify_entity_candidate(
    candidate: str,
    context_text: str = "",
    url: str = "",
    site_name: str = "",
) -> Dict[str, Any]:
    """Classifies candidate entity into explicit EntityType categories.

    Pipeline:
    1. Normalization
    2. Empty / length / numeric / calendar checks
    3. Cached rejection check
    4. Public figures & person suppression
    5. Navigation & generic page labels
    6. Headline predicate verbs / editorial fragments
    7. Geographic location alone
    8. Events, expos, summits, schemes, policies
    9. Publisher & news source suppression (dynamic domain + known list)
    10. Directory & job portal suppression
    11. Generic phrase, commercial offer, product, and government sector suppression
    12. Company positive shape validation
    """
    raw = normalize_entity_candidate(candidate)
    if not raw:
        return {
            "candidate": candidate,
            "entity_class": EntityType.UNKNOWN,
            "is_company": False,
            "confidence": 0.0,
            "reason": "Entity candidate is empty",
            "normalized_key": "",
        }

    norm_key = get_normalized_comparison_key(raw)
    lowered = raw.casefold()
    words = raw.split()
    has_corp_suffix = bool(CORPORATE_SUFFIX_PATTERN.search(lowered))
    has_legal_corp_suffix = bool(LEGAL_CORPORATE_SUFFIX_PATTERN.search(lowered))

    cached = get_cached_rejection(norm_key)
    if cached and not has_legal_corp_suffix:
        cached_class, cached_reason = cached
        return {
            "candidate": raw,
            "entity_class": cached_class,
            "is_company": False,
            "confidence": 0.0,
            "reason": f"Cached rejection: {cached_reason}",
            "normalized_key": norm_key,
        }

    if len(raw) < 2:
        reason = "Entity candidate is too short (< 2 chars)"
        cache_rejection(norm_key, EntityType.UNKNOWN, reason)
        return {
            "candidate": raw,
            "entity_class": EntityType.UNKNOWN,
            "is_company": False,
            "confidence": 0.0,
            "reason": reason,
            "normalized_key": norm_key,
        }

    lowered = raw.casefold()
    words = raw.split()

    # Gate 1: Numeric counters or economic fragments (e.g. 'A 40 Billion', '11 Verified Upcoming...')
    if re.match(r"^(?:a\s+)?[\$₹]?\s*\d+\s*(?:billion|million|crore|cr|bn|mn)\b", lowered) or re.match(r"^(\d+|[ivxlcdm]+)[\s\.\,\-]", lowered):
        reason = f"Candidate is a numeric/economic fragment or counter ('{raw}')"
        cache_rejection(norm_key, EntityType.ARTICLE_HEADLINE_FRAGMENT, reason)
        return {
            "candidate": raw,
            "entity_class": EntityType.ARTICLE_HEADLINE_FRAGMENT,
            "is_company": False,
            "confidence": 0.0,
            "reason": reason,
            "normalized_key": norm_key,
        }

    # Gate 2: Event or calendar year
    if re.search(r"\b(20[2-3]\d)\b", lowered):
        reason = f"Candidate contains an event or calendar year ('{raw}')"
        cache_rejection(norm_key, EntityType.ARTICLE_HEADLINE_FRAGMENT, reason)
        return {
            "candidate": raw,
            "entity_class": EntityType.ARTICLE_HEADLINE_FRAGMENT,
            "is_company": False,
            "confidence": 0.0,
            "reason": reason,
            "normalized_key": norm_key,
        }

    # Gate 3: Public figures, politicians, official titles (Highest priority)
    for pattern in POLITICAL_AND_PUBLIC_FIGURE_PATTERNS:
        if re.search(pattern, lowered):
            reason = f"Entity matches public figure or official title pattern ('{pattern}')"
            cache_rejection(norm_key, EntityType.PERSON, reason)
            return {
                "candidate": raw,
                "entity_class": EntityType.PERSON,
                "is_company": False,
                "confidence": 0.0,
                "reason": reason,
                "normalized_key": norm_key,
            }

    # Gate 4: Generic page and navigation headings
    for pattern in GENERIC_PAGE_AND_NAVIGATION_PATTERNS:
        if re.match(pattern, lowered):
            reason = f"Entity is a generic page or navigation heading ('{raw}')"
            cache_rejection(norm_key, EntityType.NAVIGATION_LABEL, reason)
            return {
                "candidate": raw,
                "entity_class": EntityType.NAVIGATION_LABEL,
                "is_company": False,
                "confidence": 0.0,
                "reason": reason,
                "normalized_key": norm_key,
            }

    # Gate 5: Editorial questions and headline action verbs / predicate phrases
    if re.match(r"^(?:did\s+you\s+know|why|how|what|when|where|decoding|here\s+is)\b", lowered):
        reason = "Entity uses editorial question or headline phrasing"
        cache_rejection(norm_key, EntityType.ARTICLE_HEADLINE_FRAGMENT, reason)
        return {
            "candidate": raw,
            "entity_class": EntityType.ARTICLE_HEADLINE_FRAGMENT,
            "is_company": False,
            "confidence": 0.0,
            "reason": reason,
            "normalized_key": norm_key,
        }

    for verb_pat in HEADLINE_VERB_PATTERNS:
        if re.search(verb_pat, lowered):
            reason = f"Entity contains headline action verb/predicate ('{verb_pat}')"
            cache_rejection(norm_key, EntityType.ARTICLE_HEADLINE_FRAGMENT, reason)
            return {
                "candidate": raw,
                "entity_class": EntityType.ARTICLE_HEADLINE_FRAGMENT,
                "is_company": False,
                "confidence": 0.0,
                "reason": reason,
                "normalized_key": norm_key,
            }

    has_corp_suffix = bool(CORPORATE_SUFFIX_PATTERN.search(lowered))

    # Gate 5b: Superlative / Incomplete editorial headline fragments (Task 3C.1.3 Section 6)
    if not has_legal_corp_suffix:
        for sup_pat in SUPERLATIVE_AND_EDITORIAL_FRAGMENT_PATTERNS:
            if re.search(sup_pat, lowered):
                reason = f"Entity matches superlative/editorial headline fragment pattern ('{sup_pat}')"
                cache_rejection(norm_key, EntityType.ARTICLE_HEADLINE_FRAGMENT, reason)
                return {
                    "candidate": raw,
                    "entity_class": EntityType.ARTICLE_HEADLINE_FRAGMENT,
                    "is_company": False,
                    "confidence": 0.0,
                    "reason": reason,
                    "normalized_key": norm_key,
                }

    # Gate 5c: Contextual continuation check (Task 3C.1.3 Section 9)
    if context_text and not has_legal_corp_suffix:
        norm_cand = re.sub(r"[^\w\s]", "", raw).strip().lower()
        norm_ctx = re.sub(r"[^\w\s]", "", context_text).strip().lower()
        if norm_cand in norm_ctx and norm_cand != norm_ctx:
            idx = norm_ctx.find(norm_cand)
            after = norm_ctx[idx + len(norm_cand):].strip()
            if re.match(r"^(?:growing|growth|manufacturers?|companies|players?|producers?|exporters?|suppliers?|startups?|firms?|brands?)\b", after):
                reason = f"Candidate is an incomplete title fragment preceding '{after.split()[0]}' ('{raw}')"
                cache_rejection(norm_key, EntityType.ARTICLE_HEADLINE_FRAGMENT, reason)
                return {
                    "candidate": raw,
                    "entity_class": EntityType.ARTICLE_HEADLINE_FRAGMENT,
                    "is_company": False,
                    "confidence": 0.0,
                    "reason": reason,
                    "normalized_key": norm_key,
                }

    # Gate 5d: Generic Industry / Service Category detection (Task 3C.1.3 Section 4 & 5)
    if not has_legal_corp_suffix:
        for cat_pat in GENERIC_CATEGORY_AND_INDUSTRY_PATTERNS:
            if re.search(cat_pat, lowered):
                reason = f"Candidate is a generic industry/service category term ('{raw}')"
                cache_rejection(norm_key, EntityType.GENERIC_INDUSTRY_TERM, reason)
                return {
                    "candidate": raw,
                    "entity_class": EntityType.GENERIC_INDUSTRY_TERM,
                    "is_company": False,
                    "confidence": 0.0,
                    "reason": reason,
                    "normalized_key": norm_key,
                }

        if url:
            try:
                parsed_path = urlparse(url).path.lower()
                if re.search(r"/(?:tag|tags|category|categories|topic|topics|search|industry|industries|sector|sectors)/", parsed_path):
                    cand_slug = re.sub(r"[^\w\s]", "", lowered).replace(" ", "[-_+]")
                    if re.search(cand_slug, parsed_path) or any(t in parsed_path for t in words if len(t) >= 4):
                        reason = f"Candidate matches taxonomy/tag/category URL path ('{raw}')"
                        cache_rejection(norm_key, EntityType.GENERIC_INDUSTRY_TERM, reason)
                        return {
                            "candidate": raw,
                            "entity_class": EntityType.GENERIC_INDUSTRY_TERM,
                            "is_company": False,
                            "confidence": 0.0,
                            "reason": reason,
                            "normalized_key": norm_key,
                        }
            except Exception:
                pass

    # Gate 6: Geographic locations alone
    if lowered in INDIAN_STATES:
        reason = f"Entity is a geographic state name ('{raw}')"
        cache_rejection(norm_key, EntityType.GOVERNMENT_SECTOR_LABEL, reason)
        return {
            "candidate": raw,
            "entity_class": EntityType.GOVERNMENT_SECTOR_LABEL,
            "is_company": False,
            "confidence": 0.0,
            "reason": reason,
            "normalized_key": norm_key,
        }

    if lowered in INDIAN_CITIES:
        reason = f"Entity is a geographic city name ('{raw}')"
        cache_rejection(norm_key, EntityType.GOVERNMENT_SECTOR_LABEL, reason)
        return {
            "candidate": raw,
            "entity_class": EntityType.GOVERNMENT_SECTOR_LABEL,
            "is_company": False,
            "confidence": 0.0,
            "reason": reason,
            "normalized_key": norm_key,
        }

    if any(lowered.endswith(f" {suffix}") for suffix in ("hub", "corridor", "state", "region", "landscape")):
        prefix = re.sub(r"\s+(?:semiconductor\s+)?(?:hub|corridor|state|region|landscape)$", "", lowered).strip()
        if prefix in INDIAN_STATES or prefix in INDIAN_CITIES:
            reason = f"Entity is a geographic region/hub ('{raw}')"
            cache_rejection(norm_key, EntityType.GOVERNMENT_SECTOR_LABEL, reason)
            return {
                "candidate": raw,
                "entity_class": EntityType.GOVERNMENT_SECTOR_LABEL,
                "is_company": False,
                "confidence": 0.0,
                "reason": reason,
                "normalized_key": norm_key,
            }

    # Gate 7: Events, Expos, Summits, Conferences
    for pattern in EVENT_PATTERNS:
        if re.search(pattern, lowered):
            reason = f"Entity matches event/expo/summit pattern ('{pattern}')"
            cache_rejection(norm_key, EntityType.ARTICLE_HEADLINE_FRAGMENT, reason)
            return {
                "candidate": raw,
                "entity_class": EntityType.ARTICLE_HEADLINE_FRAGMENT,
                "is_company": False,
                "confidence": 0.0,
                "reason": reason,
                "normalized_key": norm_key,
            }

    # Gate 8: Government Schemes, Policies, and Administrative Releases
    for pattern in GOVERNMENT_SCHEME_PATTERNS:
        if re.search(pattern, lowered):
            reason = f"Entity matches government scheme/policy/release pattern ('{pattern}')"
            cache_rejection(norm_key, EntityType.GOVERNMENT_SECTOR_LABEL, reason)
            return {
                "candidate": raw,
                "entity_class": EntityType.GOVERNMENT_SECTOR_LABEL,
                "is_company": False,
                "confidence": 0.0,
                "reason": reason,
                "normalized_key": norm_key,
            }

    # Gate 9: Directory & Job Portal Suppression
    job_and_directory_patterns = [
        r"\b(?:jobs?|hiring|openings?|vacancies|recruitment|profiles?|apqp)\b",
        r"^(?:careers?|jobs?|openings?|vacancies|working)\s+(?:at|in|with)\b",
        r"\b(?:manufacturers|suppliers|exporters|dealers|distributors|wholesalers)\s+(?:in|near|across|of)\b",
        r"\b(?:top|best|list\s+of)\s+.*\b(?:manufacturers|companies|suppliers|exporters)\b",
        r"^how\s+many\s+.*\b(?:manufacturers|companies|suppliers)\b",
    ]
    for pat in job_and_directory_patterns:
        if re.search(pat, lowered):
            reason = f"Matches directory or job-listing heading ('{raw}')"
            cache_rejection(norm_key, EntityType.JOB_PORTAL if "job" in pat or "profile" in pat or "apqp" in pat else EntityType.DIRECTORY, reason)
            return {
                "candidate": raw,
                "entity_class": EntityType.JOB_PORTAL if "job" in pat or "profile" in pat or "apqp" in pat else EntityType.DIRECTORY,
                "is_company": False,
                "confidence": 0.0,
                "reason": reason,
                "normalized_key": norm_key,
            }

    if url:
        parsed_netloc = urlparse(url).netloc.casefold().removeprefix("www.")
        if any(d in parsed_netloc for d in DIRECTORY_AND_JOB_DOMAINS):
            for dom_token in re.findall(r"[a-z0-9]+", parsed_netloc):
                if dom_token in lowered and len(dom_token) >= 4:
                    reason = f"Candidate matches directory/job board domain ('{parsed_netloc}')"
                    cache_rejection(norm_key, EntityType.DIRECTORY, reason)
                    return {
                        "candidate": raw,
                        "entity_class": EntityType.DIRECTORY,
                        "is_company": False,
                        "confidence": 0.0,
                        "reason": reason,
                        "normalized_key": norm_key,
                    }


    # Gate 9B: Project Trackers, B2B Intelligence Portals & Industrial Databases
    # Check Manufacturer Exception:
    has_manufacturing_evidence = False
    combined_context = f"{context_text} {candidate}".casefold()
    if any(re.search(pat, combined_context) for pat in MANUFACTURING_OWNERSHIP_PATTERNS):
        has_manufacturing_evidence = True

    # Check if candidate is a legitimate company with corporate legal suffix (e.g. Tata Projects Limited)
    is_legitimate_project_company = False
    if CORPORATE_SUFFIX_PATTERN.search(lowered):
        portal_subwords = {"tracker", "tracking", "intelligence", "database", "portal", "monitor", "alert", "media", "b2b", "news", "newsletter", "insight", "insights", "projectx"}
        if not any(sw in lowered for sw in portal_subwords):
            is_legitimate_project_company = True

    if not has_manufacturing_evidence and not is_legitimate_project_company:
        # 1. Name patterns for project tracking / intelligence / portal
        for pat in PROJECT_TRACKER_AND_PORTAL_PATTERNS:
            if re.search(pat, lowered):
                reason = f"Candidate is a project tracker / B2B media / project intelligence portal ('{raw}')"
                cache_rejection(norm_key, EntityType.PUBLISHER, reason)
                return {
                    "candidate": raw,
                    "entity_class": EntityType.PUBLISHER,
                    "is_company": False,
                    "confidence": 0.0,
                    "reason": reason,
                    "normalized_key": norm_key,
                }

        # 2. Domain matching: candidate matches source tracker / portal domain
        if url:
            parsed_netloc_9b = urlparse(url).netloc.casefold().removeprefix("www.")
            if any(ptd in parsed_netloc_9b for ptd in PROJECT_TRACKER_AND_PORTAL_DOMAINS):
                for dom_tok in re.findall(r"[a-z0-9]+", parsed_netloc_9b):
                    if dom_tok in lowered and len(dom_tok) >= 4 and dom_tok not in ("india", "global", "online"):
                        reason = f"Candidate matches project tracker/portal domain ('{parsed_netloc_9b}')"
                        cache_rejection(norm_key, EntityType.PUBLISHER, reason)
                        return {
                            "candidate": raw,
                            "entity_class": EntityType.PUBLISHER,
                            "is_company": False,
                            "confidence": 0.0,
                            "reason": reason,
                            "normalized_key": norm_key,
                        }
                if ("project" in parsed_netloc_9b or "tracker" in parsed_netloc_9b) and ("project" in lowered or "tracker" in lowered):
                    reason = f"Candidate derives from project tracking site domain ('{parsed_netloc_9b}')"
                    cache_rejection(norm_key, EntityType.PUBLISHER, reason)
                    return {
                        "candidate": raw,
                        "entity_class": EntityType.PUBLISHER,
                        "is_company": False,
                        "confidence": 0.0,
                        "reason": reason,
                        "normalized_key": norm_key,
                    }

    # Gate 10: Publisher & News Source Suppression
    # 1. Known publishers list
    if lowered in KNOWN_PUBLISHERS or norm_key in {"pv magazine", "pv magazine india", "jmk research", "ibef", "businessline"}:
        reason = f"Candidate is a known news or research publication ('{raw}')"
        cache_rejection(norm_key, EntityType.PUBLISHER, reason)
        return {
            "candidate": raw,
            "entity_class": EntityType.PUBLISHER,
            "is_company": False,
            "confidence": 0.0,
            "reason": reason,
            "normalized_key": norm_key,
        }

    # 2. Dynamic URL domain match against candidate (e.g. pv-magazine-india.com vs 'pv magazine India')
    if url:
        parsed_netloc = urlparse(url).netloc.casefold().removeprefix("www.")
        domain_parts = [p for p in re.split(r"[\.\-]", parsed_netloc) if p not in ("com", "co", "in", "org", "net", "io", "news", "media")]
        cand_tokens = [w for w in re.findall(r"[a-z0-9]+", lowered) if len(w) >= 2]
        if domain_parts and cand_tokens:
            overlap = set(domain_parts).intersection(cand_tokens)
            if len(overlap) >= 2 or (len(cand_tokens) == 1 and overlap):
                if any(nd in parsed_netloc for nd in NEWS_AND_AGGREGATOR_DOMAINS) or "magazine" in lowered or "times" in lowered or "daily" in lowered:
                    reason = f"Candidate dynamically matches news publisher domain '{parsed_netloc}'"
                    cache_rejection(norm_key, EntityType.PUBLISHER, reason)
                    return {
                        "candidate": raw,
                        "entity_class": EntityType.PUBLISHER,
                        "is_company": False,
                        "confidence": 0.0,
                        "reason": reason,
                        "normalized_key": norm_key,
                    }

    # Gate 11: Person name heuristics (e.g. 'Omprakash Singh Bisht')
    if (
        2 <= len(words) <= 3
        and not CORPORATE_SUFFIX_PATTERN.search(lowered)
        and not any(w in lowered for w in ("technologies", "energy", "solar", "motors", "fasteners", "steel", "forge", "electronics"))
    ):
        indian_surnames_and_middles = {
            "singh", "sharma", "patel", "kumar", "verma", "yadav", "gupta", "mishra",
            "joshi", "bisht", "nair", "reddy", "rao", "shukla", "pandey", "choudhary",
            "chauhan", "rathore", "agarwal", "bhat", "das", "deshmukh", "kulkarni",
            "shinde", "jain", "bose", "sen", "mehta", "shah",
        }
        word_tokens = [w.casefold() for w in words]
        if any(w in indian_surnames_and_middles for w in word_tokens[1:]):
            reason = f"Matches individual human name pattern ('{raw}')"
            cache_rejection(norm_key, EntityType.PERSON, reason)
            return {
                "candidate": raw,
                "entity_class": EntityType.PERSON,
                "is_company": False,
                "confidence": 0.0,
                "reason": reason,
                "normalized_key": norm_key,
            }

    # Gate 12: Generic phrase, product, franchise, and government sector suppression
    # Multi-sector list: e.g. "Automobile, Auto Components & EV"
    if re.search(r"\b(?:automobile|auto\s+components?|ev|renewables?|electronics?|power)\s*(?:,|&|and)\s*(?:automobile|auto\s+components?|ev|renewables?|electronics?|power)\b", lowered):
        reason = f"Candidate is a multi-sector category label ('{raw}')"
        cache_rejection(norm_key, EntityType.GOVERNMENT_SECTOR_LABEL, reason)
        return {
            "candidate": raw,
            "entity_class": EntityType.GOVERNMENT_SECTOR_LABEL,
            "is_company": False,
            "confidence": 0.0,
            "reason": reason,
            "normalized_key": norm_key,
        }

    # Commercial franchise, marketing, newsletter, or report offerings
    if re.search(r"\b(?:franchise|dealership|distributorship|newsletter|market\s+insights|data\s+insights|business\s+data)\b", lowered):
        reason = f"Candidate is a generic commercial franchise, newsletter, or market data phrase ('{raw}')"
        cache_rejection(norm_key, EntityType.PRODUCT_OR_SERVICE, reason)
        return {
            "candidate": raw,
            "entity_class": EntityType.PRODUCT_OR_SERVICE,
            "is_company": False,
            "confidence": 0.0,
            "reason": reason,
            "normalized_key": norm_key,
        }

    # Standalone generic products or terms
    generic_product_terms = {
        "ev", "solar module", "solar modules", "solar cell", "solar cells",
        "ion cell", "ion cells", "lithium ion", "battery pack", "battery packs",
        "electric vehicle", "electric vehicles", "wind turbine", "green hydrogen",
        "semiconductor", "semiconductors", "daily morning newsletter",
    }
    if lowered in generic_product_terms or norm_key in {"ev", "solar module", "ion cell", "daily morning newsletter"}:
        reason = f"Candidate is a generic product or publication phrase ('{raw}')"
        cache_rejection(norm_key, EntityType.GENERIC_INDUSTRY_TERM, reason)
        return {
            "candidate": raw,
            "entity_class": EntityType.GENERIC_INDUSTRY_TERM,
            "is_company": False,
            "confidence": 0.0,
            "reason": reason,
            "normalized_key": norm_key,
        }

    # Gate 13: Generic adjectives / abstract nouns alone
    if len(words) == 1 and lowered in GENERIC_NON_COMPANY_WORDS:
        reason = f"Entity is a single generic non-company word ('{raw}')"
        cache_rejection(norm_key, EntityType.GENERIC_INDUSTRY_TERM, reason)
        return {
            "candidate": raw,
            "entity_class": EntityType.GENERIC_INDUSTRY_TERM,
            "is_company": False,
            "confidence": 0.0,
            "reason": reason,
            "normalized_key": norm_key,
        }

    if all(w.casefold() in GENERIC_NON_COMPANY_WORDS for w in words) and not has_legal_corp_suffix:
        reason = f"Entity comprises only generic non-company terms ('{raw}')"
        cache_rejection(norm_key, EntityType.GENERIC_INDUSTRY_TERM, reason)
        return {
            "candidate": raw,
            "entity_class": EntityType.GENERIC_INDUSTRY_TERM,
            "is_company": False,
            "confidence": 0.0,
            "reason": reason,
            "normalized_key": norm_key,
        }

    # Gate 14: Incomplete trailing preposition fragment
    if lowered.endswith((" in", " at", " to", " on", " for", " with", " by", " of")):
        reason = "Entity ends with an incomplete preposition fragment"
        cache_rejection(norm_key, EntityType.ARTICLE_HEADLINE_FRAGMENT, reason)
        return {
            "candidate": raw,
            "entity_class": EntityType.ARTICLE_HEADLINE_FRAGMENT,
            "is_company": False,
            "confidence": 0.0,
            "reason": reason,
            "normalized_key": norm_key,
        }

    # Gate 15: Word count limit (> 5 words is almost certainly an editorial clause)
    if len(words) > 5:
        reason = f"Entity word count ({len(words)}) exceeds maximum allowable for a corporate name"
        cache_rejection(norm_key, EntityType.ARTICLE_HEADLINE_FRAGMENT, reason)
        return {
            "candidate": raw,
            "entity_class": EntityType.ARTICLE_HEADLINE_FRAGMENT,
            "is_company": False,
            "confidence": 0.0,
            "reason": reason,
            "normalized_key": norm_key,
        }

    # Passed all rejection gates -> corporate shape validation
    conf = 0.85
    if CORPORATE_SUFFIX_PATTERN.search(lowered):
        conf = 0.95

    return {
        "candidate": raw,
        "trimmed_candidate": raw,
        "entity_class": EntityType.COMPANY,
        "is_company": True,
        "confidence": conf,
        "reason": "VALID_COMPANY_ENTITY",
        "normalized_key": norm_key,
    }


def validate_company_entity(name: str, context_text: str = "", url: str = "") -> Tuple[bool, str]:
    """Deterministically validates whether a candidate entity is an actual company/organization.

    Maintains full backwards compatibility with existing codebase.
    Returns:
        (True, "VALID_COMPANY_ENTITY") if passes all truth gates.
        (False, exact_rejection_reason) if rejected.
    """
    res = classify_entity_candidate(name, context_text=context_text, url=url)
    record_entity_telemetry(res["entity_class"])
    if res["is_company"]:
        return True, "VALID_COMPANY_ENTITY"
    return False, res["reason"]


def extract_clean_company_name_from_title(title: str, url: str = "") -> str:
    """Extracts and validates a clean corporate entity from a raw search title.

    Handles news titles with action verbs by isolating the corporate subject,
    and inspects title chunks to skip generic page headings (e.g., 'Our Businesses - Tata Electronics').
    Returns clean name if valid, or empty string if rejected by entity truth gate.
    """
    raw_title = normalize_entity_candidate(title)
    if not raw_title:
        return ""

    # Split on common title separators: ' - ', ' | ', ' : ', ' — ', ' – '
    chunks = [c.strip() for c in re.split(r"\s*[-|:—–]\s*", raw_title) if c.strip()]
    if not chunks:
        return ""

    for chunk in chunks:
        extracted = chunk

        # Check for "at <Company>" or "hiring <Company>"
        if " at " in chunk.lower():
            parts = re.split(r"\s+at\s+", chunk, flags=re.IGNORECASE)
            if len(parts) > 1 and len(parts[1].strip()) >= 2:
                extracted = parts[1].strip()
        elif " hiring " in chunk.lower():
            parts = re.split(r"\s+hiring\s+", chunk, flags=re.IGNORECASE)
            if len(parts) > 0 and len(parts[0].strip()) >= 2:
                extracted = parts[0].strip()
        else:
            # Check headline predicate trimming first
            trimmed, did_trim = trim_headline_subject_boundary(chunk)
            if did_trim:
                extracted = trimmed

        clean = normalize_entity_candidate(extracted)
        if not clean:
            continue

        res = classify_entity_candidate(clean, context_text=raw_title, url=url)
        # If this chunk is a publisher, news source, directory, or portal, NEVER accept as company
        if res["entity_class"] in (EntityType.PUBLISHER, EntityType.NEWS_SOURCE, EntityType.DIRECTORY, EntityType.JOB_PORTAL):
            logger.debug("Skipping publisher/source portal chunk '%s': %s", clean, res["reason"])
            continue

        if res["is_company"]:
            final_cand = res.get("trimmed_candidate") or clean
            return final_cand[:100]
        else:
            logger.debug("Skipping invalid/non-company title chunk '%s': %s", clean, res["reason"])

    return ""


def resolve_canonical_company_identity(
    raw_candidate: str = "",
    title: str = "",
    snippet: str = "",
    url: str = "",
) -> Dict[str, Any]:
    """Deterministically resolves and validates canonical company identity from multi-evidence context.

    Prevents generic navigation headings ('Our Businesses', 'About Us', 'Careers'),
    publishers ('pv magazine India'), and headline fragments from passing,
    and resolves grounded corporate entities supported by title segments, snippets,
    and registered domains with zero invention.

    Returns:
        {
            "company_name": str,
            "confidence": float,
            "confidence_level": str,  # 'HIGH', 'MEDIUM', 'LOW', 'REJECTED'
            "canonicalization_method": str,
            "evidence": str,
            "is_valid": bool,
            "rejection_reason": Optional[str],
            "entity_class": str,
            "normalized_key": str,
        }
    """
    raw_candidate = normalize_entity_candidate(raw_candidate)
    title = normalize_entity_candidate(title)
    snippet = normalize_entity_candidate(snippet)
    url = str(url or "").strip()

    parsed_netloc = ""
    domain_tokens: List[str] = []
    is_news = False
    if url:
        try:
            netloc = urlparse(url).netloc.casefold().removeprefix("www.")
            parsed_netloc = netloc
            is_news = any(nd in netloc for nd in NEWS_AND_AGGREGATOR_DOMAINS) or bool(
                re.search(r"(?:news|media|press|times|daily|journal|mag|magazine|report|wire|post|chronicle|express|today|insider|review|watch|bulletin|update|portal|blog|forum|telecom|energy|power|auto|mobility|tech)", netloc)
            )
            common_subdomains = {
                "www", "investors", "investor", "ir", "careers", "career", "jobs",
                "news", "media", "press", "about", "corporate", "corp", "global",
                "blog", "web", "m", "mobile", "en", "in", "us", "uk", "apac", "emea",
            }
            common_tlds = {"com", "co", "in", "org", "net", "edu", "gov", "io", "ai", "biz", "info", "me", "tech"}
            raw_parts = [p.strip() for p in netloc.split(".") if p.strip()]
            domain_tokens = [
                re.sub(r"(?:group|india|limited|ltd|corp)$", "", p).strip()
                for p in raw_parts
                if p not in common_subdomains and p not in common_tlds and len(p) >= 3
            ]
        except Exception:
            pass

    def _domain_corroborates(cand_name: str) -> bool:
        if is_news or not domain_tokens:
            return False
        cand_tokens = [w.casefold() for w in re.findall(r"[a-zA-Z0-9]+", cand_name) if len(w) >= 3]
        if not cand_tokens:
            return False
        return any(t in dt or dt in t for t in cand_tokens for dt in domain_tokens if dt)

    def _domain_contradicts(cand_name: str) -> bool:
        if is_news or not domain_tokens:
            return False
        cand_tokens = [w.casefold() for w in re.findall(r"[a-zA-Z0-9]+", cand_name) if len(w) >= 3]
        if cand_tokens and not any(t in dt or dt in t for t in cand_tokens for dt in domain_tokens if dt):
            return True
        return False

    # ── Strategy 1: Explicit Candidate Classification & Boundary Trimming ───────
    if raw_candidate:
        cls_res = classify_entity_candidate(raw_candidate, context_text=title, url=url)
        cand_to_use = cls_res.get("trimmed_candidate") or raw_candidate
        if cls_res["is_company"]:
            if _domain_corroborates(cand_to_use):
                return {
                    "company_name": cand_to_use,
                    "confidence": 0.95,
                    "confidence_level": "HIGH",
                    "canonicalization_method": "DOMAIN_CORROBORATED",
                    "evidence": f"Candidate '{cand_to_use}' corroborated by corporate domain '{parsed_netloc}'",
                    "is_valid": True,
                    "rejection_reason": None,
                    "entity_class": EntityType.COMPANY,
                    "normalized_key": cls_res["normalized_key"],
                }
            elif _domain_contradicts(cand_to_use):
                logger.debug("Domain contradiction: '%s' vs domain '%s'", cand_to_use, parsed_netloc)
                return {
                    "company_name": cand_to_use,
                    "confidence": 0.50,
                    "confidence_level": "LOW",
                    "canonicalization_method": "EXPLICIT_TITLE_OR_SNIPPET",
                    "evidence": f"Candidate '{cand_to_use}' contradicts corporate domain '{parsed_netloc}'",
                    "is_valid": False,
                    "rejection_reason": f"Company '{cand_to_use}' contradicts non-news domain '{parsed_netloc}'",
                    "entity_class": EntityType.UNKNOWN,
                    "normalized_key": cls_res["normalized_key"],
                }
            else:
                return {
                    "company_name": cand_to_use,
                    "confidence": 0.90,
                    "confidence_level": "HIGH",
                    "canonicalization_method": "EXPLICIT_TITLE_OR_SNIPPET",
                    "evidence": f"Candidate '{cand_to_use}' explicitly present in title",
                    "is_valid": True,
                    "rejection_reason": None,
                    "entity_class": EntityType.COMPANY,
                    "normalized_key": cls_res["normalized_key"],
                }

    # ── Strategy 2: Bounded Title Segment Canonical Resolution ───────────────
    clean_title_cand = extract_clean_company_name_from_title(title, url=url)
    if clean_title_cand:
        cls_title = classify_entity_candidate(clean_title_cand, context_text=title, url=url)
        if cls_title["is_company"]:
            if _domain_corroborates(clean_title_cand):
                return {
                    "company_name": clean_title_cand,
                    "confidence": 0.95,
                    "confidence_level": "HIGH",
                    "canonicalization_method": "DOMAIN_CORROBORATED",
                    "evidence": f"Title segment '{clean_title_cand}' corroborated by domain '{parsed_netloc}'",
                    "is_valid": True,
                    "rejection_reason": None,
                    "entity_class": EntityType.COMPANY,
                    "normalized_key": cls_title["normalized_key"],
                }
            else:
                return {
                    "company_name": clean_title_cand,
                    "confidence": 0.88,
                    "confidence_level": "HIGH",
                    "canonicalization_method": "MULTI_SOURCE_CORROBORATED" if (snippet and clean_title_cand.lower() in snippet.lower()) else "EXPLICIT_TITLE_OR_SNIPPET",
                    "evidence": f"Title segment '{clean_title_cand}' verified as genuine corporate entity",
                    "is_valid": True,
                    "rejection_reason": None,
                    "entity_class": EntityType.COMPANY,
                    "normalized_key": cls_title["normalized_key"],
                }

    # ── Strategy 3: Grounded Snippet Resolution ───────────────────────────────
    if snippet:
        corp_matches = re.findall(
            r"\b([A-Z][a-zA-Z0-9&.,'\s]{1,35}?\s+(?:Ltd|Limited|Pvt|Private Limited|Corporation|Industries|Technologies|Electronics|Motors|Energy|Enterprises|Components))\b",
            snippet,
        )
        for match in corp_matches:
            clean_m = normalize_entity_candidate(match)
            cls_m = classify_entity_candidate(clean_m, context_text=snippet, url=url)
            if cls_m["is_company"]:
                if _domain_corroborates(clean_m):
                    return {
                        "company_name": clean_m,
                        "confidence": 0.92,
                        "confidence_level": "HIGH",
                        "canonicalization_method": "DOMAIN_CORROBORATED",
                        "evidence": f"Snippet entity '{clean_m}' corroborated by domain '{parsed_netloc}'",
                        "is_valid": True,
                        "rejection_reason": None,
                        "entity_class": EntityType.COMPANY,
                        "normalized_key": cls_m["normalized_key"],
                    }
                elif is_news or not parsed_netloc:
                    return {
                        "company_name": clean_m,
                        "confidence": 0.85,
                        "confidence_level": "MEDIUM",
                        "canonicalization_method": "EXPLICIT_TITLE_OR_SNIPPET",
                        "evidence": f"Snippet entity '{clean_m}' with explicit corporate suffix",
                        "is_valid": True,
                        "rejection_reason": None,
                        "entity_class": EntityType.COMPANY,
                        "normalized_key": cls_m["normalized_key"],
                    }

    # ── Strategy 4: Zero-Invention Guard (Fail closed) ─────────────────────────
    last_cls = classify_entity_candidate(raw_candidate, url=url) if raw_candidate else {"entity_class": EntityType.UNKNOWN, "reason": "No candidate"}
    rejection = (
        f"Entity candidate '{raw_candidate}' rejected ({last_cls['reason']})"
        if raw_candidate
        else f"Title '{title[:50]}' contains no grounded corporate entity"
    )
    return {
        "company_name": "",
        "confidence": 0.0,
        "confidence_level": "REJECTED",
        "canonicalization_method": "UNKNOWN",
        "evidence": "No grounded corporate entity in search evidence",
        "is_valid": False,
        "rejection_reason": rejection,
        "entity_class": last_cls["entity_class"],
        "normalized_key": get_normalized_comparison_key(raw_candidate) if raw_candidate else "",
    }
