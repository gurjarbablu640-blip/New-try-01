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
    words = clean_name.split()

    # Gate 1: Public figures, politicians, and official titles
    for pattern in POLITICAL_AND_PUBLIC_FIGURE_PATTERNS:
        if re.search(pattern, lowered):
            return False, f"Entity matches public figure or official title pattern ('{pattern}')"

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

    Handles news titles with action verbs by isolating the corporate subject.
    Returns clean name if valid, or empty string if rejected by entity truth gate.
    """
    raw_title = str(title or "").strip()
    if not raw_title:
        return ""

    # Split on common title separators: ' - ', ' | ', ' : ', ' — ', ' – '
    primary_chunk = re.split(r"\s*[-|:—–]\s*", raw_title)[0].strip()

    extracted = primary_chunk

    # Check for "at <Company>" or "hiring <Company>"
    if " at " in primary_chunk.lower():
        parts = re.split(r"\s+at\s+", primary_chunk, flags=re.IGNORECASE)
        if len(parts) > 1 and len(parts[1].strip()) >= 2:
            extracted = parts[1].strip()
    elif " hiring " in primary_chunk.lower():
        parts = re.split(r"\s+hiring\s+", primary_chunk, flags=re.IGNORECASE)
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
            if re.search(verb_pat, primary_chunk, re.IGNORECASE):
                lead_subject = re.split(verb_pat, primary_chunk, flags=re.IGNORECASE)[0].strip()
                if len(lead_subject) >= 2:
                    extracted = lead_subject
                break

    # Clean characters
    clean = re.sub(r"[^a-zA-Z0-9\s&.,-]", "", extracted).strip(" ,.-")

    # Validate through entity truth gate
    is_valid, reason = validate_company_entity(clean, context_text=raw_title)
    if not is_valid:
        logger.debug("Entity truth gate rejected candidate '%s' from title '%s': %s", clean, raw_title, reason)
        return ""

    return clean[:100]
