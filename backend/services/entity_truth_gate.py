"""Entity Truth Gate — Validates that discovered entities are genuine corporate organizations.

Prevents non-company entities from entering the Salesoorja pipeline:
- Public figures and political titles (PM Modi, Chief Minister, etc.)
- Editorial headlines and predicate verb phrases
- Geographic locations, states, and city names
- Events, expos, conferences, and summits
- Government bodies, public policies, and schemes
- Generic adjectives and abstract nouns
"""
from __future__ import annotations

import logging
import re
from typing import Tuple

logger = logging.getLogger(__name__)

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
    r"\b(?:shri|smt|dr|mr|mrs|ms)\b",
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
    r"\beyes\b", r"\bplans\b",
    r"\bopens\b", r"\bopened\b",
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
}

# Generic page, navigation, section, and website content labels
GENERIC_PAGE_AND_NAVIGATION_PATTERNS = [
    # "Our Businesses", "Our Business", "Our Products", "Our Services", "Our Solutions", "Our Company", etc.
    r"^our\s+(?:businesses|business|products|services|solutions|company|presence|offerings|team|people|vision|mission|brands|portfolio|clients|partners|ventures|divisions|units|locations|facilities|operations|leaders(?:hip)?|story|journey|catalog|catalogue|brochure)$",
    # "About Us", "About The Company", "About Our Company", "Who We Are", "What We Do", etc.
    r"^about\s+(?:us|the\s+company|our\s+company|our\s+group|group|ourselves)$",
    r"^(?:who\s+we\s+are|what\s+we\s+do|where\s+we\s+are|where\s+we\s+operate|how\s+we\s+work|why\s+choose\s+us|how\s+we\s+do\s+it)$",
    # "Contact Us", "Get In Touch", "Reach Us", "Locate Us"
    r"^(?:contact\s+(?:us|me)?|get\s+in\s+touch|reach\s+us|locate\s+us|find\s+us)$",
    # "Investor Relations", "Corporate Governance", "Financial Results", etc.
    r"^(?:investor\s+relations|investors?|financial\s+results|annual\s+reports?|quarterly\s+results|corporate\s+governance|shareholder\s+information)$",
    # "Careers", "Work With Us", "Join Our Team", etc.
    r"^(?:careers?|job\s+openings?|work\s+with\s+us|join\s+(?:us|our\s+team)|current\s+openings?|employment\s+opportunities?)$",
    # "Home", "Homepage", "Main Page", "Overview", "Company Overview", etc.
    r"^(?:home(?:page)?|main\s+page|overview|company\s+overview|business\s+overview|corporate\s+overview|welcome)$",
    # "Media", "News", "Press Release", etc.
    r"^(?:media(?:\s+centre|\s+center)?|news(?:\s+(&|and)\s+media)?|press\s+releases?|in\s+the\s+news|latest\s+news|newsroom)$",
    # "Locations", "Manufacturing Facilities", etc.
    r"^(?:locations?|our\s+locations?|global\s+presence|manufacturing\s+facilities|manufacturing\s+locations|our\s+facilities|facilities|plants?)$",
    # "Industries", "Solutions", "Products & Services", etc.
    r"^(?:industries(?:\s+served)?|sectors|solutions|products\s+(&|and)\s+services|services\s+(&|and)\s+products|our\s+offerings|offerings)$",
    # "Product Catalog", "Product Brochure", "Downloads", "Case Studies", etc.
    r"^(?:products?|services?|equipment|machinery|instrument|component)\s+(?:catalog|catalogue|brochure|line|range|category|categories|list|portfolio|specifications?|details|offerings?)$",
    r"^(?:catalog|catalogue|brochure|brochures|whitepapers?|case\s+studies|downloads?|gallery|faq|faqs|blog|blogs|articles?|sitemap|privacy\s+policy|terms\s+(?:of\s+use|and\s+conditions)|disclaimer)$",
    # Standalone single-word category/navigation labels without corporate modifiers
    r"^(?:business|businesses|manufacturing|corporate|enterprise|services?|products?|solutions?|industries|facilities|locations?|overview|careers?|news|media|home|catalog|catalogue|brochure|brochures|downloads?)$",
]

# Common news, aggregator, social, and directory domains that report on third-party companies
NEWS_AND_AGGREGATOR_DOMAINS = {
    "economictimes.indiatimes.com", "business-standard.com", "livemint.com",
    "thehindu.com", "hindustantimes.com", "timesofindia.indiatimes.com",
    "reuters.com", "bloomberg.com", "cnbctv18.com", "moneycontrol.com",
    "financialexpress.com", "ndtv.com", "ndtvprofit.com", "zeeconnect.com",
    "theprint.in", "thewire.in", "scroll.in", "indiatoday.in", "news18.com",
    "pib.gov.in", "bseindia.com", "nseindia.com", "linkedin.com", "naukri.com",
    "indiamart.com", "wikipedia.org", "tradeindia.com", "zaubacorp.com",
    "tofler.in", "quickr.com", "justdial.com", "youtube.com", "facebook.com",
    "twitter.com", "x.com", "instagram.com",
}

# Recognized corporate suffixes indicating an actual organization
CORPORATE_SUFFIX_PATTERN = re.compile(
    r"\b(ltd|limited|pvt|private|inc|corp|corporation|gmbh|llc|co|enterprises|"
    r"industries|technologies|electronics|motors|energy|solutions|systems|"
    r"group|holdings|works|infra|power|engineering|manufacturing)\b",
    re.IGNORECASE,
)


def validate_company_entity(name: str, context_text: str = "") -> Tuple[bool, str]:
    """Deterministically validates whether a candidate entity is an actual company/organization.

    Returns:
        (True, "VALID_COMPANY_ENTITY") if passes all truth gates.
        (False, exact_rejection_reason) if rejected.
    """
    clean_name = str(name or "").strip()
    if not clean_name:
        return False, "Entity name is empty"

    if len(clean_name) < 2:
        return False, "Entity name is too short (< 2 characters)"

    lowered = clean_name.casefold()
    norm_lowered = re.sub(r"^[^\w]+|[^\w]+$", "", lowered).strip()
    words = clean_name.split()

    # Gate 1: Public figures, politicians, and official titles
    for pattern in POLITICAL_AND_PUBLIC_FIGURE_PATTERNS:
        if re.search(pattern, lowered):
            return False, f"Entity matches public figure or official title pattern ('{pattern}')"

    # Gate 1b: Generic page, navigation, section, and website content labels
    for pattern in GENERIC_PAGE_AND_NAVIGATION_PATTERNS:
        if re.match(pattern, norm_lowered):
            return False, f"Entity is a generic page or navigation heading ('{clean_name}')"

    # Gate 2: Event or calendar year (e.g. 'Source India 2026', 'Auto Expo 2026')
    if re.search(r"\b(20[2-3]\d)\b", lowered):
        return False, "Entity contains an event or calendar year"

    # Gate 3: Word Count Limit (headlines and phrases have many words)
    if len(words) > 5:
        return False, f"Entity word count ({len(words)}) exceeds maximum allowable for a corporate name"

    # Gate 4: Starts with numeric count or list indicator (e.g. '11 Verified Upcoming...')
    if re.match(r"^(\d+|[ivxlcdm]+)[\s\.\,\-]", lowered):
        return False, "Entity starts with a numeric counter or list index"

    # Gate 5: Editorial question / headline phrasing (e.g. 'Did you know...', 'Why...', 'Decoding...')
    if re.match(r"^(?:did\s+you\s+know|why|how|what|when|where|decoding|here\s+is)\b", lowered):
        return False, "Entity uses editorial question or headline phrasing"

    # Gate 5: Headline Action Verbs / Predicate Phrases
    for pattern in HEADLINE_VERB_PATTERNS:
        if re.search(pattern, lowered):
            return False, f"Entity contains headline action verb/predicate ('{pattern}')"

    # Gate 6: Geographic Locations / States / Cities alone
    if lowered in INDIAN_STATES:
        return False, f"Entity is a geographic state name ('{clean_name}')"
    if lowered in INDIAN_CITIES:
        return False, f"Entity is a geographic city name ('{clean_name}')"
    if any(lowered.endswith(f" {suffix}") for suffix in ("hub", "corridor", "state", "region", "landscape")):
        # Check if the prefix is a state or city (e.g. "Gujarat Semiconductor Hub")
        prefix = re.sub(r"\s+(?:semiconductor\s+)?(?:hub|corridor|state|region|landscape)$", "", lowered).strip()
        if prefix in INDIAN_STATES or prefix in INDIAN_CITIES:
            return False, f"Entity is a geographic region/hub ('{clean_name}')"

    # Gate 7: Events, Expos, Summits, Conferences
    for pattern in EVENT_PATTERNS:
        if re.search(pattern, lowered):
            return False, f"Entity matches event/expo/summit pattern ('{pattern}')"

    # Gate 8: Government Schemes, Policies, and Administrative Releases
    for pattern in GOVERNMENT_SCHEME_PATTERNS:
        if re.search(pattern, lowered):
            return False, f"Entity matches government scheme/policy/release pattern ('{pattern}')"

    # Gate 9: Generic Adjectives / Abstract Nouns
    if len(words) == 1 and lowered in GENERIC_NON_COMPANY_WORDS:
        return False, f"Entity is a single generic non-company word ('{clean_name}')"

    if all(w.casefold() in GENERIC_NON_COMPANY_WORDS for w in words):
        return False, f"Entity comprises only generic non-company terms ('{clean_name}')"

    # Gate 10: Ending with prepositions or trailing punctuation
    if lowered.endswith((" in", " at", " to", " on", " for", " with", " by", " of")):
        return False, "Entity ends with an incomplete preposition fragment"

    return True, "VALID_COMPANY_ENTITY"


def extract_clean_company_name_from_title(title: str) -> str:
    """Extracts and validates a clean corporate entity from a raw search title.

    Handles news titles with action verbs by isolating the corporate subject,
    and inspects title chunks to skip generic page headings (e.g., 'Our Businesses - Tata Electronics').
    Returns clean name if valid, or empty string if rejected by entity truth gate.
    """
    raw_title = str(title or "").strip()
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
            # Check for action verb patterns to isolate the leading subject
            for verb_pat in (
                r"\blaunches\b", r"\blaunched\b",
                r"\binaugurates\b", r"\binaugurated\b",
                r"\bcommissions\b", r"\bcommissioned\b",
                r"\bto\s+set\s+up\b", r"\bsets\s+up\b", r"\bsetting\s+up\b",
                r"\bexpands\b", r"\bexpanded\b",
                r"\bopens\b", r"\bopened\b",
                r"\binvests\b", r"\binvesting\b",
                r"\bannounces\b", r"\bannounced\b",
                r"\bcelebrates\b", r"\bsecures\b",
                r"\bunveils\b", r"\boperationalizes?\b",
            ):
                if re.search(verb_pat, chunk, re.IGNORECASE):
                    lead_subject = re.split(verb_pat, chunk, flags=re.IGNORECASE)[0].strip()
                    if len(lead_subject) >= 2:
                        extracted = lead_subject
                    break

        clean = re.sub(r"[^a-zA-Z0-9\s&.,-]", "", extracted).strip(" ,.-")
        if not clean:
            continue

        # Validate through entity truth gate
        is_valid, reason = validate_company_entity(clean, context_text=raw_title)
        if is_valid:
            return clean[:100]
        else:
            logger.debug("Skipping invalid/generic title chunk '%s': %s", clean, reason)

    return ""


def resolve_canonical_company_identity(
    raw_candidate: str = "",
    title: str = "",
    snippet: str = "",
    url: str = "",
) -> Dict[str, Any]:
    """Deterministically resolves and validates canonical company identity from multi-evidence context.

    Prevents generic navigation headings ('Our Businesses', 'About Us', 'Careers') from passing,
    and resolves grounded corporate entities supported by title segments, snippets,
    and registered domains with zero invention.

    Returns:
        {
            "company_name": str,
            "confidence": float,
            "confidence_level": str,  # 'HIGH', 'MEDIUM', 'LOW', 'REJECTED'
            "canonicalization_method": str,  # 'EXPLICIT_TITLE_OR_SNIPPET', 'DOMAIN_CORROBORATED', 'MULTI_SOURCE_CORROBORATED', 'UNKNOWN'
            "evidence": str,
            "is_valid": bool,
            "rejection_reason": Optional[str],
        }
    """
    from urllib.parse import urlparse

    raw_candidate = str(raw_candidate or "").strip()
    title = str(title or "").strip()
    snippet = str(snippet or "").strip()
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

    # ── Strategy 1: Explicit Candidate Validation ─────────────────────────────
    if raw_candidate:
        is_valid, reason = validate_company_entity(raw_candidate, title)
        if is_valid:
            if _domain_corroborates(raw_candidate):
                return {
                    "company_name": raw_candidate,
                    "confidence": 0.95,
                    "confidence_level": "HIGH",
                    "canonicalization_method": "DOMAIN_CORROBORATED",
                    "evidence": f"Candidate '{raw_candidate}' corroborated by corporate domain '{parsed_netloc}'",
                    "is_valid": True,
                    "rejection_reason": None,
                }
            elif _domain_contradicts(raw_candidate):
                logger.debug("Domain contradiction: '%s' vs domain '%s'", raw_candidate, parsed_netloc)
                return {
                    "company_name": raw_candidate,
                    "confidence": 0.50,
                    "confidence_level": "LOW",
                    "canonicalization_method": "EXPLICIT_TITLE_OR_SNIPPET",
                    "evidence": f"Candidate '{raw_candidate}' contradicts corporate domain '{parsed_netloc}'",
                    "is_valid": False,
                    "rejection_reason": f"Company '{raw_candidate}' contradicts non-news domain '{parsed_netloc}'",
                }
            else:
                return {
                    "company_name": raw_candidate,
                    "confidence": 0.90,
                    "confidence_level": "HIGH",
                    "canonicalization_method": "EXPLICIT_TITLE_OR_SNIPPET",
                    "evidence": f"Candidate '{raw_candidate}' explicitly present in title",
                    "is_valid": True,
                    "rejection_reason": None,
                }

    # ── Strategy 2: Bounded Title Segment Canonical Resolution ───────────────
    clean_title_cand = extract_clean_company_name_from_title(title)
    if clean_title_cand:
        if _domain_corroborates(clean_title_cand):
            return {
                "company_name": clean_title_cand,
                "confidence": 0.95,
                "confidence_level": "HIGH",
                "canonicalization_method": "DOMAIN_CORROBORATED",
                "evidence": f"Title segment '{clean_title_cand}' corroborated by domain '{parsed_netloc}'",
                "is_valid": True,
                "rejection_reason": None,
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
            }

    # ── Strategy 3: Grounded Snippet Resolution ───────────────────────────────
    if snippet:
        corp_matches = re.findall(
            r"\b([A-Z][a-zA-Z0-9&.,'\s]{1,35}?\s+(?:Ltd|Limited|Pvt|Private Limited|Corporation|Industries|Technologies|Electronics|Motors|Energy|Enterprises|Components))\b",
            snippet,
        )
        for match in corp_matches:
            clean_m = match.strip(" ,.-")
            is_val, _ = validate_company_entity(clean_m, snippet)
            if is_val:
                if _domain_corroborates(clean_m):
                    return {
                        "company_name": clean_m,
                        "confidence": 0.92,
                        "confidence_level": "HIGH",
                        "canonicalization_method": "DOMAIN_CORROBORATED",
                        "evidence": f"Snippet entity '{clean_m}' corroborated by domain '{parsed_netloc}'",
                        "is_valid": True,
                        "rejection_reason": None,
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
                    }

    # ── Strategy 4: Zero-Invention Guard ──────────────────────────────────────
    rejection = (
        f"Entity candidate '{raw_candidate}' rejected as generic navigation/page heading and unsupported by grounded text evidence"
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
    }
