"""Salesoorja Entity Resolution Service.

Constructs canonical identities for target companies and classifies source entity-match confidence:
- EXACT_ENTITY: Official domain or verified exact legal corporate match.
- STRONG_ENTITY: Reputable secondary source unambiguously identifying company, sector, and geography.
- AMBIGUOUS_ENTITY: Colliding/generic tokens (e.g. "Bharat", "Gabriel", "Sona") without definitive company qualifiers.
- WRONG_ENTITY: Entirely different company/brand (e.g. Bharatgas for Bharat Forge, US Craftsman hand tools, Uno card game).

Rules:
- WRONG_ENTITY: discarded immediately.
- AMBIGUOUS_ENTITY: cannot verify evidence.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class EntityProfile:
    canonical_company_name: str
    legal_name: str
    official_domain: str
    alternate_domains: List[str] = field(default_factory=list)
    sector: str = ""
    country: str = "India"
    known_manufacturing_locations: List[Dict[str, str]] = field(default_factory=list)
    aliases: List[str] = field(default_factory=list)
    ambiguous_name_tokens: List[str] = field(default_factory=list)
    wrong_entity_markers: List[str] = field(default_factory=list)


# Canonical registry for target industrial portfolios
CANONICAL_TARGET_ENTITIES: Dict[str, EntityProfile] = {
    "Gabriel India Ltd": EntityProfile(
        canonical_company_name="Gabriel India Ltd",
        legal_name="Gabriel India Limited",
        official_domain="anandgroupindia.com",
        alternate_domains=["gabrielindia.com"],
        sector="Ride Control & Shock Absorbers",
        country="India",
        known_manufacturing_locations=[
            {"city": "Chakan", "district": "Pune", "state": "Maharashtra", "industrial_area": "MIDC Chakan", "facility_name": "Chakan Plant", "is_unique_in_city": True},
            {"city": "Khandsa", "district": "Gurugram", "state": "Haryana", "industrial_area": "Khandsa Industrial Area", "facility_name": "Gurugram Plant", "is_unique_in_city": True},
            {"city": "Sanand", "district": "Ahmedabad", "state": "Gujarat", "industrial_area": "GIDC Sanand", "facility_name": "Sanand Plant", "is_unique_in_city": True},
            {"city": "Hosur", "district": "Krishnagiri", "state": "Tamil Nadu", "industrial_area": "SIPCOT Industrial Complex", "facility_name": "Hosur Plant", "is_unique_in_city": True},
            {"city": "Dewas", "district": "Dewas", "state": "Madhya Pradesh", "industrial_area": "Industrial Area Dewas", "facility_name": "Dewas Plant", "is_unique_in_city": True},
            {"city": "Parwanoo", "district": "Solan", "state": "Himachal Pradesh", "industrial_area": "Sector 2 Parwanoo", "facility_name": "Parwanoo Plant", "is_unique_in_city": True},
        ],
        aliases=["Gabriel India", "Gabriel Anand Group"],
        ambiguous_name_tokens=["gabriel", "archangel", "magalhaes", "bajpayee", "dey vlogs"],
        wrong_entity_markers=["archangel", "magalhães", "footballer", "actor", "vlogs", "baby name"],
    ),
    "Kaynes Technology India Ltd": EntityProfile(
        canonical_company_name="Kaynes Technology India Ltd",
        legal_name="Kaynes Technology India Limited",
        official_domain="kaynestechnology.net",
        alternate_domains=["kaynestechnology.co.in", "kaynessemi.com"],
        sector="Electronics & Semiconductor OSAT",
        country="India",
        known_manufacturing_locations=[
            {"city": "Sanand", "district": "Ahmedabad", "state": "Gujarat", "industrial_area": "GIDC Sanand II", "facility_name": "Kaynes Semicon OSAT Facility", "is_unique_in_city": True},
            {"city": "Mysuru", "district": "Mysore", "state": "Karnataka", "industrial_area": "Hebbal Industrial Area", "facility_name": "Hebbal Mysore Unit", "is_unique_in_city": False},
            {"city": "Bengaluru", "district": "Bengaluru", "state": "Karnataka", "industrial_area": "Electronic City", "facility_name": "Bangalore Unit", "is_unique_in_city": False},
            {"city": "Manesar", "district": "Gurugram", "state": "Haryana", "industrial_area": "IMT Manesar", "facility_name": "Manesar Unit", "is_unique_in_city": True},
        ],
        aliases=["Kaynes Technology", "Kaynes Semicon", "Kaynes"],
        ambiguous_name_tokens=["kaynes"],
        wrong_entity_markers=["keynes", "john maynard", "economist", "cairns"],
    ),
    "Syrma SGS Technology Ltd": EntityProfile(
        canonical_company_name="Syrma SGS Technology Ltd",
        legal_name="Syrma SGS Technology Limited",
        official_domain="syrmasgs.com",
        alternate_domains=["syrma.com"],
        sector="Electronics Manufacturing Services",
        country="India",
        known_manufacturing_locations=[
            {"city": "Bawal", "district": "Rewari", "state": "Haryana", "industrial_area": "HSIIDC Industrial Growth Centre Bawal", "facility_name": "Bawal Manufacturing Plant", "is_unique_in_city": True},
            {"city": "Chennai", "district": "Chennai", "state": "Tamil Nadu", "industrial_area": "MEPZ-SEZ Tambaram", "facility_name": "MEPZ Plant", "is_unique_in_city": False},
            {"city": "Bengaluru", "district": "Bengaluru", "state": "Karnataka", "industrial_area": "Electronic City", "facility_name": "Bangalore Plant", "is_unique_in_city": False},
            {"city": "Manesar", "district": "Gurugram", "state": "Haryana", "industrial_area": "IMT Manesar", "facility_name": "Manesar Plant", "is_unique_in_city": True},
        ],
        aliases=["Syrma SGS", "Syrma Technology", "Tandon Group Syrma"],
        ambiguous_name_tokens=["sgs", "inspection", "certification agency"],
        wrong_entity_markers=["société générale de surveillance", "sgs sa", "geneva certification", "sgs inspection"],
    ),
    "Centum Electronics Ltd": EntityProfile(
        canonical_company_name="Centum Electronics Ltd",
        legal_name="Centum Electronics Limited",
        official_domain="centumelectronics.com",
        alternate_domains=[],
        sector="Defence & Aerospace Electronics",
        country="India",
        known_manufacturing_locations=[
            {"city": "Bengaluru", "district": "Bengaluru", "state": "Karnataka", "industrial_area": "Yelahanka New Town / Devanahalli Aerospace Park", "facility_name": "Aerospace & Defence Complex Yelahanka", "is_unique_in_city": True},
        ],
        aliases=["Centum Electronics", "Centum Group"],
        ambiguous_name_tokens=["centum", "centum learning", "centum financial"],
        wrong_entity_markers=["centum learning", "centum financial", "centum academy"],
    ),
    "Bharat Bijlee Ltd": EntityProfile(
        canonical_company_name="Bharat Bijlee Ltd",
        legal_name="Bharat Bijlee Limited",
        official_domain="bharatbijlee.com",
        alternate_domains=[],
        sector="Power Transformers & Industrial Motors",
        country="India",
        known_manufacturing_locations=[
            {"city": "Navi Mumbai", "district": "Thane", "state": "Maharashtra", "industrial_area": "TTC Industrial Area, Airoli", "facility_name": "Airoli Manufacturing Complex", "is_unique_in_city": True},
        ],
        aliases=["Bharat Bijlee", "BBL"],
        ambiguous_name_tokens=["bharat", "bijlee", "bharatgas", "petroleum"],
        wrong_entity_markers=["ebharatgas", "bharat petroleum", "lpg cylinder", "cooking gas", "bpcl", "bharat electronics", "bel india"],
    ),
    "Voltamp Transformers Ltd": EntityProfile(
        canonical_company_name="Voltamp Transformers Ltd",
        legal_name="Voltamp Transformers Limited",
        official_domain="voltamptransformers.com",
        alternate_domains=[],
        sector="Transformers & Substation Units",
        country="India",
        known_manufacturing_locations=[
            {"city": "Vadodara", "district": "Vadodara", "state": "Gujarat", "industrial_area": "Savli GIDC / Makarpura GIDC", "facility_name": "Savli Manufacturing Works", "is_unique_in_city": True},
        ],
        aliases=["Voltamp Transformers", "Voltamp Vadodara"],
        ambiguous_name_tokens=["voltamp", "voltamp oman"],
        wrong_entity_markers=["voltamp electricals pvt ltd", "voltamp.in", "voltamp oman", "switchgear panel board"],
    ),
    "KEC International Ltd": EntityProfile(
        canonical_company_name="KEC International Ltd",
        legal_name="KEC International Limited",
        official_domain="kecrpg.com",
        alternate_domains=["rpg.com"],
        sector="Power Transmission Towers, Cables & Railways",
        country="India",
        known_manufacturing_locations=[
            {"city": "Nagpur", "district": "Nagpur", "state": "Maharashtra", "industrial_area": "MIDC Butibori", "facility_name": "Butibori Tower Plant", "is_unique_in_city": True},
            {"city": "Jabalpur", "district": "Jabalpur", "state": "Madhya Pradesh", "industrial_area": "Richhai Industrial Area", "facility_name": "Jabalpur Tower Plant", "is_unique_in_city": True},
            {"city": "Vadodara", "district": "Vadodara", "state": "Gujarat", "industrial_area": "Baska, Halol Road", "facility_name": "Vadodara Cable Plant", "is_unique_in_city": True},
            {"city": "Mysuru", "district": "Mysore", "state": "Karnataka", "industrial_area": "Belagola Industrial Area", "facility_name": "Mysore Cable Plant", "is_unique_in_city": True},
        ],
        aliases=["KEC International", "KEC RPG", "RPG KEC"],
        ambiguous_name_tokens=["kec", "kec engineering college"],
        wrong_entity_markers=["kec college", "kongu engineering", "katihar engineering", "krishna engineering"],
    ),
    "Bharat Forge Ltd": EntityProfile(
        canonical_company_name="Bharat Forge Ltd",
        legal_name="Bharat Forge Limited",
        official_domain="bharatforge.com",
        alternate_domains=["kalyanigroup.com"],
        sector="Heavy Forgings, Automotive, Defence & Aerospace",
        country="India",
        known_manufacturing_locations=[
            {"city": "Pune", "district": "Pune", "state": "Maharashtra", "industrial_area": "Mundhwa Industrial Area", "facility_name": "Mundhwa Heavy Forging Complex", "is_unique_in_city": False},
            {"city": "Baramati", "district": "Pune", "state": "Maharashtra", "industrial_area": "MIDC Baramati", "facility_name": "Baramati Precision Forging Plant", "is_unique_in_city": True},
            {"city": "Chakan", "district": "Pune", "state": "Maharashtra", "industrial_area": "MIDC Chakan Phase II", "facility_name": "Chakan Machining Plant", "is_unique_in_city": True},
        ],
        aliases=["Bharat Forge", "Kalyani Bharat Forge"],
        ambiguous_name_tokens=["bharat", "forge", "bharatgas", "bpcl"],
        wrong_entity_markers=["ebharatgas", "bharat petroleum", "lpg cylinder", "cooking gas", "bpcl", "bharat electronics", "bel india"],
    ),
    "Amara Raja Energy & Mobility Ltd": EntityProfile(
        canonical_company_name="Amara Raja Energy & Mobility Ltd",
        legal_name="Amara Raja Energy & Mobility Limited",
        official_domain="amararaja.com",
        alternate_domains=["amararajabatteries.com"],
        sector="Battery Gigafactory, Lead-Acid & Lithium-Ion Cells",
        country="India",
        known_manufacturing_locations=[
            {"city": "Mahbubnagar", "district": "Mahbubnagar", "state": "Telangana", "industrial_area": "Divitipally Industrial Park", "facility_name": "Amara Raja Giga Corridor", "is_unique_in_city": True},
            {"city": "Tirupati", "district": "Tirupati", "state": "Andhra Pradesh", "industrial_area": "Karakambadi Industrial Area", "facility_name": "Karakambadi Battery Complex", "is_unique_in_city": True},
        ],
        aliases=["Amara Raja", "Amara Raja Batteries", "ARE&M"],
        ambiguous_name_tokens=["amara", "raja"],
        wrong_entity_markers=["raja biscuits", "amara raja foundation only", "amara hotel"],
    ),
    "Goldi Solar Pvt Ltd": EntityProfile(
        canonical_company_name="Goldi Solar Pvt Ltd",
        legal_name="Goldi Solar Private Limited",
        official_domain="goldisolar.com",
        alternate_domains=[],
        sector="Solar PV Cells & Modules",
        country="India",
        known_manufacturing_locations=[
            {"city": "Navsari", "district": "Navsari", "state": "Gujarat", "industrial_area": "GIDC Navsari", "facility_name": "Navsari Solar Module Plant", "is_unique_in_city": True},
            {"city": "Surat", "district": "Surat", "state": "Gujarat", "industrial_area": "Pipodara Industrial Area", "facility_name": "Pipodara Facility", "is_unique_in_city": True},
        ],
        aliases=["Goldi Solar", "Goldi"],
        ambiguous_name_tokens=["goldi", "goldie"],
        wrong_entity_markers=["goldie masala", "goldi spices", "goldie hawn", "dog name"],
    ),
    "Motherson Sumi Wiring India Ltd": EntityProfile(
        canonical_company_name="Motherson Sumi Wiring India Ltd",
        legal_name="Motherson Sumi Wiring India Limited",
        official_domain="mswil.motherson.com",
        alternate_domains=["motherson.com"],
        sector="Automotive Wiring Harnesses & Electrical Systems",
        country="India",
        known_manufacturing_locations=[
            {"city": "Pune", "district": "Pune", "state": "Maharashtra", "industrial_area": "MIDC Chakan / Bhosari", "facility_name": "Pune Wiring Harness Unit", "is_unique_in_city": True},
            {"city": "Noida", "district": "Gautam Buddha Nagar", "state": "Uttar Pradesh", "industrial_area": "Sector 85 Noida", "facility_name": "Noida Harness Facility", "is_unique_in_city": True},
            {"city": "Chennai", "district": "Kanchipuram", "state": "Tamil Nadu", "industrial_area": "Oragadam Industrial Corridor", "facility_name": "Chennai Harness Plant", "is_unique_in_city": True},
            {"city": "Sanand", "district": "Ahmedabad", "state": "Gujarat", "industrial_area": "GIDC Sanand II", "facility_name": "Sanand Harness Unit", "is_unique_in_city": True},
        ],
        aliases=["Motherson Sumi Wiring", "MSWIL", "Motherson Wiring"],
        ambiguous_name_tokens=["motherson", "sumi"],
        wrong_entity_markers=["samvardhana motherson international only", "motherson medical", "sumitomo chemical"],
    ),
    "Kirloskar Oil Engines Ltd": EntityProfile(
        canonical_company_name="Kirloskar Oil Engines Ltd",
        legal_name="Kirloskar Oil Engines Limited",
        official_domain="kirloskaroilengines.com",
        alternate_domains=["kirloskar.com"],
        sector="Heavy Industrial Engines, Gensets & Agri Equipment",
        country="India",
        known_manufacturing_locations=[
            {"city": "Kolhapur", "district": "Kolhapur", "state": "Maharashtra", "industrial_area": "MIDC Kagal-Hatkanangale Five Star", "facility_name": "Kagal Large Engine Plant", "is_unique_in_city": True},
            {"city": "Pune", "district": "Pune", "state": "Maharashtra", "industrial_area": "Khadki Industrial Area", "facility_name": "Khadki Works", "is_unique_in_city": True},
            {"city": "Rajkot", "district": "Rajkot", "state": "Gujarat", "industrial_area": "Aji Industrial Area", "facility_name": "Rajkot Engine Plant", "is_unique_in_city": True},
            {"city": "Nashik", "district": "Nashik", "state": "Maharashtra", "industrial_area": "MIDC Ambad", "facility_name": "Ambad Nashik Plant", "is_unique_in_city": True},
        ],
        aliases=["Kirloskar Oil Engines", "KOEL", "Kirloskar Engines"],
        ambiguous_name_tokens=["kirloskar"],
        wrong_entity_markers=["kirloskar brothers limited", "kirloskar ferrous", "kirloskar pneumatic", "kirloskar electric company", "kbl pumps"],
    ),
    "Thermax Ltd": EntityProfile(
        canonical_company_name="Thermax Ltd",
        legal_name="Thermax Limited",
        official_domain="thermaxglobal.com",
        alternate_domains=[],
        sector="Industrial Boilers, Chillers, Water Treatment & Clean Tech",
        country="India",
        known_manufacturing_locations=[
            {"city": "Pune", "district": "Pune", "state": "Maharashtra", "industrial_area": "Chinchwad MIDC", "facility_name": "Chinchwad Boiler & Heating Plant", "is_unique_in_city": True},
            {"city": "Shirwal", "district": "Satara", "state": "Maharashtra", "industrial_area": "MIDC Shirwal", "facility_name": "Shirwal Absorption Chiller & Boiler Complex", "is_unique_in_city": True},
            {"city": "Dahej", "district": "Bharuch", "state": "Gujarat", "industrial_area": "GIDC Dahej SEZ", "facility_name": "Dahej Chemical & Water Works", "is_unique_in_city": True},
            {"city": "Savli", "district": "Vadodara", "state": "Gujarat", "industrial_area": "GIDC Savli", "facility_name": "Savli Works", "is_unique_in_city": True},
        ],
        aliases=["Thermax", "Thermax Global"],
        ambiguous_name_tokens=["thermax"],
        wrong_entity_markers=["thermax insulation usa", "dupont thermax", "dow thermax sheeting"],
    ),
}


def get_canonical_profile(company_name: str) -> Optional[EntityProfile]:
    """Retrieve canonical entity profile for a target company name."""
    clean = company_name.strip().lower()
    for name, profile in CANONICAL_TARGET_ENTITIES.items():
        if clean == name.lower():
            return profile
        if clean in [a.lower() for a in profile.aliases]:
            return profile
        # Substring / token matching
        c_tokens = [t for t in re.split(r"[^\w]+", name.lower()) if len(t) > 3 and t not in ("limited", "india")]
        if all(t in clean for t in c_tokens):
            return profile
    return None


def resolve_entity_match(
    company_name: str,
    source_url: str,
    source_domain: str,
    source_title: str,
    snippet: str,
) -> Tuple[str, str]:
    """Classify the confidence that a source refers to the exact corporate entity.

    Returns:
        (confidence_status, reason)
        where confidence_status in ("EXACT_ENTITY", "STRONG_ENTITY", "AMBIGUOUS_ENTITY", "WRONG_ENTITY")
    """
    profile = get_canonical_profile(company_name)
    clean_domain = (source_domain or "").lower().replace("www.", "")
    combined_text = f"{source_title} {snippet} {source_url}".lower()

    if not profile:
        return "AMBIGUOUS_ENTITY", f"Company '{company_name}' not in canonical entity registry; cannot verify entity match."

    # 1. Check for hard wrong-entity markers
    for marker in profile.wrong_entity_markers:
        if marker.lower() in combined_text or marker.lower() in clean_domain:
            return "WRONG_ENTITY", f"Matched wrong-entity marker '{marker}' in source (domain: {clean_domain}). Discarding source."

    # 2. Check for exact official domain match
    target_domains = [d.lower().replace("www.", "") for d in [profile.official_domain] + profile.alternate_domains]
    if any(clean_domain == td or clean_domain.endswith("." + td) for td in target_domains):
        return "EXACT_ENTITY", f"Source domain '{clean_domain}' matches official corporate domain '{profile.official_domain}'."

    # 3. Check for exact legal name match in snippet/title
    clean_legal = profile.legal_name.lower()
    clean_canonical = profile.canonical_company_name.lower()
    if clean_legal in combined_text or clean_canonical in combined_text:
        # Verify sector or Indian manufacturing context
        sector_tokens = [t for t in re.split(r"[^\w]+", profile.sector.lower()) if len(t) > 3]
        has_context = any(st in combined_text for st in sector_tokens) or any(
            loc["city"].lower() in combined_text for loc in profile.known_manufacturing_locations
        ) or any(k in combined_text for k in ["india", "manufacturing", "plant", "factory", "capex", "expansion"])
        if has_context:
            return "STRONG_ENTITY", f"Source text contains verified legal/canonical name '{profile.canonical_company_name}' with corroborated manufacturing context."

    # 4. Check for ambiguous token collision without definitive company qualifiers
    has_ambiguous_token = any(tok in combined_text for tok in profile.ambiguous_name_tokens)
    name_tokens = [t for t in re.split(r"[^\w]+", profile.canonical_company_name.lower()) if len(t) > 3 and t not in ("limited", "india", "pvt")]
    matched_name_tokens = [t for t in name_tokens if t in combined_text]

    if len(matched_name_tokens) < len(name_tokens):
        if has_ambiguous_token:
            return "AMBIGUOUS_ENTITY", f"Matched ambiguous name token without full canonical name match. Source discarded."
        return "AMBIGUOUS_ENTITY", f"Insufficient company name token corroboration in snippet (matched {matched_name_tokens} of {name_tokens})."

    # If full name tokens match but domain is 3rd party news/gov
    gov_or_bse = any(ext in clean_domain for ext in ["bseindia.com", "nseindia.com", "sebi.gov.in", "gov.in", "pib.gov.in"])
    reputable_news = any(news in clean_domain for news in ["economictimes", "business-standard", "livemint", "moneycontrol", "reuters", "thehindu"])

    if gov_or_bse or reputable_news:
        return "STRONG_ENTITY", f"Reputable financial/regulatory source '{clean_domain}' contains full canonical entity name."

    return "STRONG_ENTITY", f"Source from '{clean_domain}' contains full company name corroboration."
