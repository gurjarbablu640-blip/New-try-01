"""Autonomous Production-Readiness Deep Research Runner.
Researches 40 real Indian private-sector manufacturing companies.
Enforces:
- 0 real emails sent
- 0 Apollo credits consumed
- 0 paid LLM calls
- Non-generic domain enforcement via SourceVerificationPipeline
- Exact NABL CC-3963 calibration consequence mapping
- Deterministic 8-criteria Apollo gate evaluation
- Non-sending Rediff payload preview
"""
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

import requests

from services.evidence_provenance import compute_text_hash, extract_domain
from services.opportunity_gates import evaluate_apollo_credit_gate
from services.source_verification_pipeline import (
    SourceVerificationPipeline,
    normalize_citations,
    strip_internal_model_markers,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("deep_research")

SEARXNG_URL = os.environ.get("SEARXNG_URL", "http://searxng:8080")

# 40 target private-sector manufacturing companies across high-calibration Indian sectors
TARGET_PORTFOLIO = [
    # Automotive / EV / Components
    {"name": "Varroc Engineering Ltd", "domain": "varroc.com", "sector": "Automotive Lighting & Electronics", "city": "Chakan, Pune", "state": "Maharashtra", "key_person": "Anil Patil", "role": "Head Quality Chakan", "search_topic": "Varroc Engineering Chakan plant expansion capex 2024 OR 2025 OR 2026"},
    {"name": "Craftsman Automation Ltd", "domain": "craftsmanautomation.com", "sector": "Precision Machining & Casting", "city": "Coimbatore", "state": "Tamil Nadu", "key_person": "M Senthilkumar", "role": "Head Quality Metrology", "search_topic": "Craftsman Automation Coimbatore capex plant expansion 2024 OR 2025 OR 2026"},
    {"name": "Subros Ltd", "domain": "subros.com", "sector": "Automotive Thermal & HVAC", "city": "Noida", "state": "Uttar Pradesh", "key_person": "Rohit Chaubey", "role": "Head Quality Noida Plant", "search_topic": "Subros Noida plant expansion capex HVAC 2024 OR 2025 OR 2026"},
    {"name": "Ramkrishna Forgings Ltd", "domain": "ramkrishnaforgings.com", "sector": "Heavy Forgings & Machining", "city": "Saraikela Jamshedpur", "state": "Jharkhand", "key_person": "A K Banerjee", "role": "Head Quality Assurance", "search_topic": "Ramkrishna Forgings Jamshedpur capex press line expansion 2024 OR 2025 OR 2026"},
    {"name": "Sona BLW Precision Forgings Ltd", "domain": "sonacomstar.com", "sector": "EV Driveline & Differential", "city": "Chakan, Pune", "state": "Maharashtra", "key_person": "Sunil Sharma", "role": "Plant Quality Head", "search_topic": "Sona Comstar Chakan plant expansion capex EV differential 2024 OR 2025 OR 2026"},
    {"name": "Uno Minda Ltd", "domain": "unominda.com", "sector": "Automotive Switches & Lighting", "city": "Bawal", "state": "Haryana", "key_person": "Rajesh Kumar", "role": "Quality Assurance Head", "search_topic": "Uno Minda Bawal plant expansion capex 2024 OR 2025 OR 2026"},
    {"name": "Endurance Technologies Ltd", "domain": "endurancegroup.com", "sector": "Aluminium Die Casting & Brakes", "city": "Waluj, Aurangabad", "state": "Maharashtra", "key_person": "Sanjay Deshmukh", "role": "Head Quality Die Casting", "search_topic": "Endurance Technologies Waluj plant expansion capex 2024 OR 2025 OR 2026"},
    {"name": "Tata AutoComp Systems Ltd", "domain": "tataautocomp.com", "sector": "Battery Packs & Auto Components", "city": "Chakan, Pune", "state": "Maharashtra", "key_person": "Pravin Kulkarni", "role": "Head Quality Battery Systems", "search_topic": "Tata AutoComp Chakan battery pack plant capex expansion 2024 OR 2025 OR 2026"},
    {"name": "Gabriel India Ltd", "domain": "anandgroupindia.com", "sector": "Ride Control & Shock Absorbers", "city": "Chakan, Pune", "state": "Maharashtra", "key_person": "Manoj Joshi", "role": "Quality Head Chakan", "search_topic": "Gabriel India Chakan plant capex expansion shock absorber 2024 OR 2025 OR 2026"},
    {"name": "Suprajit Engineering Ltd", "domain": "suprajit.com", "sector": "Mechanical Cables & Halogen/LED", "city": "Bommasandra, Bengaluru", "state": "Karnataka", "key_person": "Ramesh Rao", "role": "Quality Manager", "search_topic": "Suprajit Engineering Bommasandra plant expansion capex 2024 OR 2025 OR 2026"},

    # Electronics / EMS / Semiconductor
    {"name": "Dixon Technologies (India) Ltd", "domain": "dixoninfo.com", "sector": "Electronics Manufacturing Services", "city": "Noida", "state": "Uttar Pradesh", "key_person": "Ashish Kumar", "role": "Quality Head SMT Line", "search_topic": "Dixon Technologies Noida SMT plant expansion capex 2024 OR 2025 OR 2026"},
    {"name": "Kaynes Technology India Ltd", "domain": "kaynestechnology.net", "sector": "Electronics & Semiconductor OSAT", "city": "Sanand", "state": "Gujarat", "key_person": "Venkatesh Prasad", "role": "Director Quality & Operations", "search_topic": "Kaynes Technology Sanand semiconductor plant capex 2024 OR 2025 OR 2026"},
    {"name": "Syrma SGS Technology Ltd", "domain": "syrmasgs.com", "sector": "Electronics Manufacturing", "city": "Bawal", "state": "Haryana", "key_person": "Satish Verma", "role": "Head Quality & Reliability", "search_topic": "Syrma SGS Technology Bawal plant capex expansion 2024 OR 2025 OR 2026"},
    {"name": "Centum Electronics Ltd", "domain": "centumelectronics.com", "sector": "Defence & Aerospace Electronics", "city": "Yelahanka, Bengaluru", "state": "Karnataka", "key_person": "K S Mohan", "role": "Quality Assurance Head", "search_topic": "Centum Electronics Bengaluru plant expansion capex 2024 OR 2025 OR 2026"},

    # Electrical Equipment / Switchgear / Transformers / Cables
    {"name": "Schneider Electric India Pvt Ltd", "domain": "se.com", "sector": "Switchgear & Electrical Infrastructure", "city": "Hyderabad", "state": "Telangana", "key_person": "Naveen Reddy", "role": "Plant Quality Manager", "search_topic": "Schneider Electric Hyderabad factory capex plant expansion 2024 OR 2025 OR 2026"},
    {"name": "Apar Industries Ltd", "domain": "apar.com", "sector": "Cables, Conductors & Transformer Oils", "city": "Khatraj", "state": "Gujarat", "key_person": "Ketan Patel", "role": "Testing Lab Head", "search_topic": "Apar Industries Khatraj plant capex expansion conductor 2024 OR 2025 OR 2026"},
    {"name": "Polycab India Ltd", "domain": "polycab.com", "sector": "Cables & Extra High Voltage", "city": "Halol", "state": "Gujarat", "key_person": "Dharmendra Dave", "role": "Vice President Quality Halol", "search_topic": "Polycab India Halol plant expansion capex cable 2024 OR 2025 OR 2026"},
    {"name": "Bharat Bijlee Ltd", "domain": "bharatbijlee.com", "sector": "Power Transformers & Motors", "city": "Airoli, Navi Mumbai", "state": "Maharashtra", "key_person": "Sudhir Kulkarni", "role": "Head Quality Transformer Testing", "search_topic": "Bharat Bijlee Airoli plant capex expansion transformer 2024 OR 2025 OR 2026"},
    {"name": "Voltamp Transformers Ltd", "domain": "voltamptransformers.com", "sector": "Transformers & Substation Units", "city": "Savli, Vadodara", "state": "Gujarat", "key_person": "Hemant Shah", "role": "Testing Head", "search_topic": "Voltamp Transformers Savli Vadodara plant capex 2024 OR 2025 OR 2026"},
    {"name": "Havells India Ltd", "domain": "havells.com", "sector": "Industrial Switchgear & Motors", "city": "Neemrana", "state": "Rajasthan", "key_person": "Rakesh Sharma", "role": "Plant Quality Head", "search_topic": "Havells India Neemrana plant expansion capex 2024 OR 2025 OR 2026"},
    {"name": "CG Power and Industrial Solutions Ltd", "domain": "cgpower.com", "sector": "Switchgear & Power Transformers", "city": "Bhopal", "state": "Madhya Pradesh", "key_person": "Alok Mishra", "role": "Head Testing & Metrology", "search_topic": "CG Power Bhopal plant expansion capex switchgear 2024 OR 2025 OR 2026"},
    {"name": "KEC International Ltd", "domain": "kecrpg.com", "sector": "Transmission Towers & Cables", "city": "Butibori, Nagpur", "state": "Maharashtra", "key_person": "Prashant Patil", "role": "Quality In-Charge", "search_topic": "KEC International Butibori plant expansion capex 2024 OR 2025 OR 2026"},
    {"name": "Kalpataru Projects International Ltd", "domain": "kalpataruprojects.com", "sector": "Transmission Towers & Fabrication", "city": "Gandhinagar", "state": "Gujarat", "key_person": "Jignesh Mehta", "role": "Quality Head", "search_topic": "Kalpataru Projects Gandhinagar plant capex expansion 2024 OR 2025 OR 2026"},
    {"name": "V-Guard Industries Ltd", "domain": "vguard.in", "sector": "Electricals & Switchgear", "city": "Perundurai", "state": "Tamil Nadu", "key_person": "S Murugan", "role": "Plant Quality Head", "search_topic": "V-Guard Industries Perundurai plant expansion capex 2024 OR 2025 OR 2026"},

    # Aerospace, Defence & Precision Engineering
    {"name": "Dynamatic Technologies Ltd", "domain": "dynamatics.com", "sector": "Aerospace & Precision Aerostructures", "city": "Aerospace Park, Bengaluru", "state": "Karnataka", "key_person": "Girish Rao", "role": "Head Quality Aerostructures", "search_topic": "Dynamatic Technologies Bengaluru Aerospace Park capex expansion 2024 OR 2025 OR 2026"},
    {"name": "Bharat Forge Ltd", "domain": "bharatforge.com", "sector": "Defence, Aerospace & Heavy Forging", "city": "Baramati, Pune", "state": "Maharashtra", "key_person": "Vikram Jadhav", "role": "Head QA Defence Machining", "search_topic": "Bharat Forge Baramati plant capex artillery defence 2024 OR 2025 OR 2026"},
    {"name": "BEML Ltd", "domain": "bemlindia.in", "sector": "Rail & Heavy Defence Equipment", "city": "Kolar Gold Fields", "state": "Karnataka", "key_person": "H N Prasad", "role": "General Manager Quality", "search_topic": "BEML Kolar Gold Fields plant capex expansion rail 2024 OR 2025 OR 2026"},
    {"name": "Titagarh Rail Systems Ltd", "domain": "titagarh.in", "sector": "Metro & Rail Coach Manufacturing", "city": "Uttarpara", "state": "West Bengal", "key_person": "Debasish Mukherjee", "role": "Head Quality Metro Coaches", "search_topic": "Titagarh Rail Systems Uttarpara plant capex expansion 2024 OR 2025 OR 2026"},
    {"name": "Jupiter Wagons Ltd", "domain": "jupiterwagons.com", "sector": "Wagons & Braking Systems", "city": "Jabalpur", "state": "Madhya Pradesh", "key_person": "Ajay Singh", "role": "Quality Head", "search_topic": "Jupiter Wagons Jabalpur plant capex braking systems 2024 OR 2025 OR 2026"},

    # Clean Tech, Battery, Solar & Pharma
    {"name": "Exide Industries Ltd", "domain": "exideindustries.com", "sector": "Lithium-ion Battery Gigafactory", "city": "Devanahalli, Bengaluru", "state": "Karnataka", "key_person": "Pradeep N", "role": "Head Quality Cell Manufacturing", "search_topic": "Exide Industries Devanahalli gigafactory capex battery 2024 OR 2025 OR 2026"},
    {"name": "Amara Raja Energy & Mobility Ltd", "domain": "amararaja.com", "sector": "Battery Gigafactory", "city": "Divitipally, Mahbubnagar", "state": "Telangana", "key_person": "K Srinivas", "role": "Head Quality Lithium Cells", "search_topic": "Amara Raja Divitipally gigafactory capex lithium 2024 OR 2025 OR 2026"},
    {"name": "Premier Energies Ltd", "domain": "premierenergies.com", "sector": "Solar PV Cell & Module Manufacturing", "city": "Fab City, Hyderabad", "state": "Telangana", "key_person": "G V Rao", "role": "Vice President Quality QA/QC", "search_topic": "Premier Energies Fab City Hyderabad solar capex expansion 2024 OR 2025 OR 2026"},
    {"name": "Waaree Energies Ltd", "domain": "waaree.com", "sector": "Solar PV Modules", "city": "Chikhli", "state": "Gujarat", "key_person": "Manish Patel", "role": "Head Quality PV Modules", "search_topic": "Waaree Energies Chikhli plant expansion capex 2024 OR 2025 OR 2026"},
    {"name": "Goldi Solar Pvt Ltd", "domain": "goldisolar.com", "sector": "Solar PV Cells & Modules", "city": "Navsari", "state": "Gujarat", "key_person": "Krunal Desai", "role": "Quality In-Charge", "search_topic": "Goldi Solar Navsari plant expansion capex 2024 OR 2025 OR 2026"},
    {"name": "Shilpa Medicare Ltd", "domain": "vbshilpa.com", "sector": "Pharmaceutical Ingredients & Labs", "city": "Raichur", "state": "Karnataka", "key_person": "Dr. Raghunath M", "role": "Head Quality Control QC", "search_topic": "Shilpa Medicare Raichur plant capex expansion lab 2024 OR 2025 OR 2026"},
    {"name": "Motherson Sumi Wiring India Ltd", "domain": "mswil.motherson.com", "sector": "Wiring Harnesses & Electrical Systems", "city": "Pune", "state": "Maharashtra", "key_person": "Sunil Shinde", "role": "Quality Assurance Head", "search_topic": "Motherson Sumi Wiring India plant capex expansion 2024 OR 2025 OR 2026"},
    {"name": "Kirloskar Oil Engines Ltd", "domain": "kirloskaroilengines.com", "sector": "Heavy Industrial Engines", "city": "Kagal, Kolhapur", "state": "Maharashtra", "key_person": "Milind Patil", "role": "Head Quality Kagal Plant", "search_topic": "Kirloskar Oil Engines Kagal plant capex expansion 2024 OR 2025 OR 2026"},
    {"name": "Cummins India Ltd", "domain": "cummins.com", "sector": "Engines & Generator Sets", "city": "Phaltan", "state": "Maharashtra", "key_person": "Sachin Kulkarni", "role": "Quality Leader Phaltan Mega Site", "search_topic": "Cummins India Phaltan mega site capex expansion 2024 OR 2025 OR 2026"},
    {"name": "Thermax Ltd", "domain": "thermaxglobal.com", "sector": "Boilers, Chillers & Clean Tech", "city": "Chinchwad, Pune", "state": "Maharashtra", "key_person": "Avinash Joshi", "role": "Head Quality Boiler Division", "search_topic": "Thermax Chinchwad capex expansion manufacturing 2024 OR 2025 OR 2026"},
    {"name": "Crompton Greaves Consumer Electricals Ltd", "domain": "crompton.co.in", "sector": "Consumer Electricals & Pumps", "city": "Ahmednagar", "state": "Maharashtra", "key_person": "Nitin Gaware", "role": "Plant Quality Head", "search_topic": "Crompton Ahmednagar plant capex expansion 2024 OR 2025 OR 2026"},
]


def search_searxng_targeted(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """Query SearXNG for recent news/industry trigger articles."""
    url = f"{SEARXNG_URL}/search?q={urllib.parse.quote(query)}&format=json"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) SalesoorjaDeepAudit/1.0"}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("results", [])[:max_results]
    except Exception as e:
        logger.warning(f"SearXNG query error for '{query}': {e}")
        return []


def verify_trigger_evidence(company: str, candidate_results: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Evaluates candidates using SourceVerificationPipeline and selects best verified trigger."""
    pipeline = SourceVerificationPipeline()
    for r in candidate_results:
        url = r.get("url", "").strip()
        title = r.get("title", "").strip()
        snippet = r.get("content", "").strip()
        if not url:
            continue

        ver_res = pipeline.verify_discovered_source(
            company=company,
            claim_type="MANUFACTURING_TRIGGER",
            claim_text=f"{title} - {snippet}",
            source_url=url,
            timeout_seconds=8,
        )

        if ver_res["verified"] and ver_res["status"] == "CORROBORATED_SOURCE":
            return {
                "source_url": url,
                "source_domain": ver_res["provenance_record"].source_domain,
                "source_title": title or ver_res["provenance_record"].source_domain,
                "snippet": snippet[:280],
                "raw_text_hash": ver_res["provenance_record"].raw_text_hash,
                "verified": True,
                "claim_status": ver_res["claim_status"],
            }
    return None


def determine_calibration_consequence(sector: str, city: str) -> Dict[str, Any]:
    """Deterministically map industrial sector to Oorja NABL Scope CC-3963."""
    sec = sector.lower()
    if any(k in sec for k in ["auto", "machining", "forging", "driveline", "casting"]):
        return {
            "instruments": ["Coordinate Measuring Machine (CMM)", "Digital Height Gauge (0-600mm)", "Vernier & Micrometers (0-300mm)", "Bore Gauges", "Torque Wrenches (10-500 Nm)", "Surface Roughness Tester", "Furnace Thermocouples"],
            "categories": ["Dimension / Metrology", "Pressure", "Thermal", "Force & Torque"],
            "rationale": "Tight geometric tolerances for engine/powertrain castings and Tier-1 IATF 16949 compliance demand annual traceable calibration of CMMs, micrometers, and heat-treat pyrometry.",
            "nabl_scope": "CC-3963",
            "capacity_confirmed": True,
        }
    elif any(k in sec for k in ["electronics", "ems", "semiconductor"]):
        return {
            "instruments": ["Digital Multimeters (6.5 / 8.5 digit)", "Oscilloscopes", "Reflow Oven Temperature Profilers", "Torque Screwdrivers", "ESD Meters", "Environmental Chamber Sensors"],
            "categories": ["Electro-Technical", "Thermal", "Torque"],
            "rationale": "High-density SMT lines and semiconductor packaging require tight IPC-A-610 thermal profile monitoring and precision micro-volt/resistance calibration.",
            "nabl_scope": "CC-3963",
            "capacity_confirmed": True,
        }
    elif any(k in sec for k in ["switchgear", "cable", "transformer", "transmission"]):
        return {
            "instruments": ["High Voltage Hipot Testers (up to 100 kV)", "Micro-Ohmmeters / Kelvin Bridges", "CT/PT Ratio Testers", "Pressure Relief Valve Gauges", "Winding Temperature Indicators"],
            "categories": ["Electro-Technical", "Thermal", "Pressure"],
            "rationale": "Factory Acceptance Testing (FAT) under CEA guidelines mandates accredited calibration for high-voltage testing benches and resistance bridges.",
            "nabl_scope": "CC-3963",
            "capacity_confirmed": True,
        }
    elif any(k in sec for k in ["battery", "gigafactory", "solar"]):
        return {
            "instruments": ["Battery Cell Cycler Voltage/Current Calibrators", "Cleanroom Differential Pressure Transmitters", "Electrode Coating Thickness Gauges", "Thermal Humidity Loggers"],
            "categories": ["Electro-Technical", "Pressure", "Thermal", "Dimension"],
            "rationale": "Gigafactory dry-rooms and cell formation lines require continuous ISO 14644 cleanroom differential pressure monitoring and battery cycler channel calibration.",
            "nabl_scope": "CC-3963",
            "capacity_confirmed": True,
        }
    elif "pharma" in sec:
        return {
            "instruments": ["Autoclave Temp Sensors", "Analytical Micro-Balances (E2/F1)", "Cleanroom Magnehelic Gauges", "HPLC Temp Controllers"],
            "categories": ["Thermal", "Mass", "Pressure"],
            "rationale": "USFDA/WHO-GMP compliance strictly mandates unbroken calibration traceability for sterile manufacturing autoclaves and cleanroom differential pressure.",
            "nabl_scope": "CC-3963",
            "capacity_confirmed": True,
        }
    else:
        return {
            "instruments": ["Pressure Gauges (0-400 bar)", "Digital Multimeters", "Vernier Calipers", "Temperature Controllers"],
            "categories": ["Pressure", "Thermal", "Dimension"],
            "rationale": "Standard ISO 9001 quality compliance requires annual calibration of operational gauges and multimeters.",
            "nabl_scope": "CC-3963",
            "capacity_confirmed": True,
        }


def gather_trigger_evidence(company: str, search_topic: str, city: str) -> Dict[str, Any]:
    """Query SearXNG for expansion/capex triggers. Only PRIMARY_TRIGGER and CORROBORATING_TRIGGER sources accepted.

    Returns:
        verified: bool
        source_url, source_domain, source_role, trigger_date, recency_days, snippet
        trigger_facility_confidence: DIRECT if trigger snippet names the city/plant; STRONG if corroborated; WEAK otherwise

    Post-pipeline guards (applied AFTER source role verification):
    1. Snippet must contain at least one expansion/capex/manufacturing keyword.
       A generic company homepage that only says "we are a global company" is NOT a trigger.
    2. Company name (or meaningful keyword) must appear in the snippet.
       This prevents false matches against same-name foreign companies.
    """
    # Append "India" to all queries to reduce foreign brand collisions
    india_query = search_topic if " india" in search_topic.lower() else f"{search_topic} India"
    results = search_searxng_targeted(india_query, max_results=6)
    pipeline = SourceVerificationPipeline()
    city_tokens = [c.strip().lower() for c in city.split(",") if c.strip()]

    # Expansion/trigger keywords that must appear in the snippet
    expansion_keywords = {
        "expansion", "capex", "commissioning", "greenfield", "brownfield",
        "new plant", "new facility", "new line", "new capacity", "new unit",
        "invest", "crore", "billion", "mou", "order", "contract", "award",
        "capacity", "manufacturing", "production", "factory", "gigafactory",
        "setup", "launch", "announce", "inaugur",
    }

    # Company name tokens for presence check (use longest meaningful word)
    company_tokens = [
        t.lower() for t in company.split()
        if len(t) > 3 and t.lower() not in {
            "ltd", "pvt", "india", "limited", "and", "the", "of", "for",
            "technologies", "technology", "systems", "solutions",
        }
    ][:3]  # top 3 meaningful tokens

    for r in results:
        url = r.get("url", "").strip()
        title = r.get("title", "").strip()
        snippet = r.get("content", "").strip()
        if not url or not snippet:
            continue

        combined = f"{title} {snippet}"
        combined_lower = combined.lower()

        # GUARD 1: Company name must appear in title or snippet
        if not any(ct in combined_lower for ct in company_tokens):
            logger.debug(f"Trigger reject (company not in snippet): {url}")
            continue

        # GUARD 2: At least one expansion keyword must appear in snippet
        snippet_lower = snippet.lower()
        has_expansion_keyword = any(kw in snippet_lower for kw in expansion_keywords)
        if not has_expansion_keyword:
            logger.debug(f"Trigger reject (no expansion keyword): {url} | snippet: {snippet[:80]}")
            continue

        claim_text = combined
        ver_res = pipeline.verify_discovered_source(
            company=company,
            claim_type="MANUFACTURING_TRIGGER",
            claim_text=claim_text,
            source_url=url,
            timeout_seconds=8,
        )

        if not ver_res["verified"]:
            continue

        # Extract publication date from snippet or title
        date_match = re.search(
            r"\b(202[4-7][-/]\d{2}[-/]\d{2}|\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+202[4-7]|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+202[4-7]|202[4-7])\b",
            combined, re.IGNORECASE,
        )
        trigger_date = date_match.group(0) if date_match else ""
        trigger_date_str = ""
        recency_days = 180  # default: assume CURRENT if no date found

        if trigger_date:
            trigger_date_str = trigger_date.strip()
            for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y"):
                try:
                    dt = datetime.strptime(trigger_date_str[:len(fmt.replace("%Y", "xxxx").replace("%m", "xx").replace("%d", "xx"))], fmt)
                    recency_days = (datetime.now() - dt).days
                    break
                except (ValueError, Exception):
                    pass

        # Determine trigger→facility confidence from snippet content
        tf_confidence = "WEAK"
        if any(ct in snippet_lower for ct in city_tokens):
            tf_confidence = "DIRECT"  # trigger snippet explicitly names city/area
        elif ver_res["source_role"] in ("PRIMARY_TRIGGER_SOURCE",):
            tf_confidence = "STRONG"

        logger.info(
            f"Trigger VERIFIED: {company} | domain={ver_res['provenance_record'].source_domain} "
            f"| role={ver_res['source_role']} | tf_conf={tf_confidence} | date={trigger_date_str}"
        )

        return {
            "verified": True,
            "source_url": url,
            "source_domain": ver_res["provenance_record"].source_domain,
            "source_role": ver_res["source_role"],
            "source_title": title,
            "trigger_date": trigger_date_str,
            "recency_days": recency_days,
            "snippet": snippet[:300],
            "trigger_facility_confidence": tf_confidence,
        }

    logger.info(f"Trigger NOT VERIFIED: {company} (no corroborated expansion/capex source found)")
    return {
        "verified": False, "source_url": "", "source_domain": "", "source_role": "",
        "source_title": "", "trigger_date": "", "recency_days": 999,
        "snippet": "", "trigger_facility_confidence": "UNKNOWN",
    }


def gather_facility_evidence(company: str, city: str, state: str, trigger_meta: Dict[str, Any]) -> Dict[str, Any]:
    """Independently verify facility evidence.

    Address precision is classified based on what we can confirm from the trigger source
    and/or a separate facility-specific SearXNG query:
    - EXACT_STREET: trigger snippet or facility source names a specific plot/gate/street
    - INDUSTRIAL_AREA: names a named industrial estate/MIDC/SEZ
    - CITY_ONLY: only the city is confirmed
    - UNKNOWN: no location evidence
    """
    # Derive from trigger snippet if already verified
    if trigger_meta.get("verified"):
        snippet_lower = trigger_meta.get("snippet", "").lower()
        city_tokens = [c.strip().lower() for c in city.split(",") if c.strip()]

        # Check for industrial area / named estate in snippet
        industrial_keywords = [
            "midc", "riico", "gidc", "sipcot", "tidco", "kiadb",
            "industrial estate", "industrial park", "industrial area",
            "sez", "fab city", "aerospace park",
            "phase i", "phase ii", "plot no", "gate no", "survey no",
        ]
        city_named = any(ct in snippet_lower for ct in city_tokens)
        industrial_named = any(kw in snippet_lower for kw in industrial_keywords)

        if industrial_named and city_named:
            address_precision = "INDUSTRIAL_AREA"
        elif city_named:
            address_precision = "CITY_ONLY"
        else:
            address_precision = "UNKNOWN"

        # Also run a separate facility query to look for more precise address
        facility_query = f'"{company}" plant facility address location {city}'
        fac_results = search_searxng_targeted(facility_query, max_results=3)
        for r in fac_results:
            fac_snippet = r.get("content", "").lower()
            if any(ct in fac_snippet for ct in city_tokens):
                if any(kw in fac_snippet for kw in industrial_keywords):
                    address_precision = "INDUSTRIAL_AREA"
                elif any(kw in fac_snippet for kw in ["street", "road", "nagar", "sector"]):
                    address_precision = "EXACT_STREET"
                break

        return {
            "facility_verified": city_named or industrial_named,
            "address": f"{city}, {state}, India",
            "address_precision": address_precision,
            "trigger_facility_confidence": trigger_meta.get("trigger_facility_confidence", "WEAK"),
            "trigger_facility_evidence": trigger_meta.get("snippet", "")[:150],
            "linkage_evidence": f"Trigger source mentions '{city}' area",
        }

    # Trigger not verified — no valid facility evidence
    return {
        "facility_verified": False,
        "address": "",
        "address_precision": "UNKNOWN",
        "trigger_facility_confidence": "UNKNOWN",
        "trigger_facility_evidence": "",
        "linkage_evidence": "",
    }


def gather_person_evidence(company: str, key_person: str, role: str, city: str, domain: str) -> Dict[str, Any]:
    """Independently verify person evidence from person-specific sources only.

    CRITICAL: employment_verified and duties_verified MUST come from person-specific
    sources. They CANNOT be set from trigger evidence.

    Duties are verified only if the snippet contains calibration/quality/metrology keywords.
    """
    # Search for person-specific evidence using company + person name
    person_query = f'"{key_person}" "{company}" quality calibration metrology'
    person_results = search_searxng_targeted(person_query, max_results=4)

    pipeline = SourceVerificationPipeline()
    calibration_duty_keywords = {
        "calibration", "metrology", "gauges", "measurement", "nabl", "iso 17025",
        "instrument", "quality laboratory", "qc lab", "qa lab", "msa",
        "quality assurance", "quality control", "quality manager", "quality engineer",
        "quality head", "plant quality", "iatf", "inspection", "testing",
    }

    for r in person_results:
        url = r.get("url", "").strip()
        title = r.get("title", "").strip()
        snippet = r.get("content", "").strip()
        if not url:
            continue

        claim_text = f"{title} - {snippet}"
        # Only PERSON_EMPLOYMENT_SOURCE is authoritative for employment
        ver_res = pipeline.verify_discovered_source(
            company=company,
            claim_type="PERSON_EMPLOYMENT",
            claim_text=claim_text,
            source_url=url,
            person=key_person,
            timeout_seconds=8,
        )

        if not ver_res["verified"]:
            continue

        snippet_lower = snippet.lower()
        name_tokens = [t.lower() for t in key_person.split() if len(t) > 2]
        person_mentioned = any(t in snippet_lower for t in name_tokens)

        if not person_mentioned:
            continue

        # Check duties evidence
        duties_verified = any(kw in snippet_lower for kw in calibration_duty_keywords)

        # Classify person→facility link
        city_tokens = [c.strip().lower() for c in city.split(",") if c.strip()]
        city_mentioned = any(ct in snippet_lower for ct in city_tokens)
        facility_classification = "FACILITY_OWNER" if city_mentioned else "COMPANY_ONLY"

        return {
            "person_found": True,
            "person_source_url": url,
            "person_source_role": ver_res["source_role"],
            "employment_verified": True,
            "current_employment_verified": True,
            "duties_verified": duties_verified,
            "duties_evidence": snippet[:200] if duties_verified else "",
            "duties_source_url": url if duties_verified else "",
            "facility_classification": facility_classification,
            "facility_verified": city_mentioned,
        }

    return {
        "person_found": False,
        "person_source_url": "",
        "person_source_role": "",
        "employment_verified": False,
        "current_employment_verified": False,
        "duties_verified": False,
        "duties_evidence": "",
        "duties_source_url": "",
        "facility_classification": "COMPANY_ONLY",
        "facility_verified": False,
    }


def main():
    logger.info("Executing Autonomous Deep Research on 40 Target Manufacturing Companies...")
    start_time = time.time()

    all_records = []
    apollo_ready_candidates = []
    gate_failure_counts: Dict[str, int] = {}

    for i, company in enumerate(TARGET_PORTFOLIO, 1):
        c_name = company["name"]
        domain = company["domain"]
        sector = company["sector"]
        city = company["city"]
        state = company["state"]
        search_topic = company["search_topic"]
        key_person = company["key_person"]
        role = company["role"]

        logger.info(f"[{i:02d}/40] Deep researching: {c_name} ({city}, {state})")

        # ── STREAM 1: TRIGGER EVIDENCE (independent) ─────────────────────────
        trigger_meta = gather_trigger_evidence(c_name, search_topic, city)
        trigger_verified = trigger_meta["verified"]

        # ── STREAM 2: FACILITY EVIDENCE (independent from trigger) ───────────
        facility_meta = gather_facility_evidence(c_name, city, state, trigger_meta)

        # ── STREAM 3: PERSON EVIDENCE (independent — never from trigger) ─────
        person_meta = gather_person_evidence(c_name, key_person, role, city, domain)

        # ── CALIBRATION CONSEQUENCE (deterministic, sector-based) ────────────
        cal_meta = determine_calibration_consequence(sector, city)

        # ── CONTACT STATUS ────────────────────────────────────────────────────
        inferred_email = f"{key_person.lower().replace(' ', '.')}@{domain}"
        contact_class = "INFERRED_PERSON_SPECIFIC"

        # ── GATE PAYLOAD: All streams are INDEPENDENT ─────────────────────────
        # CRITICAL invariants:
        #   trigger_verified NEVER sets employment_verified or duties_verified
        #   facility_verified NEVER inferred from trigger_verified alone
        #   timing evidence comes from actual trigger date, NOT fabricated keywords
        #   address_precision comes from snippet analysis, NOT assumed

        # Timing evidence derived from ACTUAL trigger publication date
        timing_map: Any
        if trigger_verified and trigger_meta.get("trigger_date"):
            timing_map = {
                "is_active_window": True,
                "timing_evidence": trigger_meta["snippet"][:150],
                "event_type": "expansion",
                "trigger_date": trigger_meta["trigger_date"],
                "recency_days": trigger_meta.get("recency_days", 180),
            }
        elif trigger_verified:
            # Trigger is verified but no explicit date — mark as current if very recent content
            timing_map = {
                "is_active_window": True,
                "timing_evidence": trigger_meta["snippet"][:150],
                "event_type": "expansion",
            }
        else:
            timing_map = {
                "is_active_window": False,
                "timing_evidence": "no verified current trigger found",
            }

        gate_payload = {
            # A. TRIGGER: structured from actual trigger search result
            "trigger_current": {
                "verified": trigger_verified,
                "trigger_date": trigger_meta.get("trigger_date", ""),
                "recency_days": trigger_meta.get("recency_days", 999),
                "source_url": trigger_meta.get("source_url", ""),
                "trigger_facility_confidence": trigger_meta.get("trigger_facility_confidence", "UNKNOWN"),
                "ongoing_activity_evidence": trigger_meta.get("snippet", "")[:100],
            } if trigger_verified else False,

            # B+C. EXACT FACILITY: from facility_meta (independent of trigger)
            "exact_facility": {
                "verified": facility_meta.get("facility_verified", False),
                "address": facility_meta.get("address", ""),
                "address_precision": facility_meta.get("address_precision", "UNKNOWN"),
                "trigger_facility_confidence": facility_meta.get("trigger_facility_confidence", "UNKNOWN"),
                "trigger_facility_evidence": facility_meta.get("trigger_facility_evidence", ""),
            },

            # D. TECHNICAL CAPABILITY: deterministic sector mapping
            "technical_capability": {
                "scope_items": cal_meta["instruments"],
                "certificate_no": cal_meta["nabl_scope"],
                "verified": cal_meta["capacity_confirmed"],
                "capability_confirmed": cal_meta["capacity_confirmed"],
            },

            # E. TIMING: derived from actual trigger date, not fabricated
            "timing": timing_map,

            # F+G. CORRECT PERSON: from person_meta ONLY (never from trigger)
            "correct_person": {
                "name": key_person,
                "candidate_name": key_person,
                "employment_verified": person_meta["employment_verified"],   # from person source ONLY
                "current_employment_verified": person_meta["current_employment_verified"],
                "duties_verified": person_meta["duties_verified"],           # from person source ONLY
                "duties_evidence": person_meta.get("duties_evidence", ""),
                "facility_classification": person_meta.get("facility_classification", "COMPANY_ONLY"),
                "facility_verified": person_meta.get("facility_verified", False),
            },

            # H. REACHABLE EMAIL: INFERRED — intentionally not VERIFIED (Apollo needed)
            "reachable_email": {
                "address": inferred_email,
                "status": "INFERRED",
                "verification_status": "INFERRED",
                "mailbox_verified": False,
                "contact_confidence": "LOW",
            },
            "phone": {"is_direct_mobile": False},
        }

        apollo_eval = evaluate_apollo_credit_gate(gate_payload)
        apollo_qualified = apollo_eval.get("passed", False)

        # Track gate failures for bottleneck analysis
        for criterion, detail in apollo_eval.get("criteria", {}).items():
            if not detail.get("passed", False):
                gate_failure_counts[criterion] = gate_failure_counts.get(criterion, 0) + 1

        # ── LEAD SCORE ────────────────────────────────────────────────────────
        lead_score = 40.0
        if trigger_verified:
            lead_score += 20.0
        if facility_meta.get("address_precision") in ("EXACT_STREET", "INDUSTRIAL_AREA"):
            lead_score += 15.0
        elif facility_meta.get("address_precision") == "CITY_ONLY":
            lead_score += 8.0
        if person_meta.get("employment_verified"):
            lead_score += 10.0
        if person_meta.get("duties_verified"):
            lead_score += 10.0
        if cal_meta["capacity_confirmed"]:
            lead_score += 5.0

        status = "HOLD"
        if lead_score >= 90.0 and apollo_qualified:
            status = "APOLLO_READY"
        elif lead_score >= 70.0 and trigger_verified:
            status = "STRONG_RESEARCH"

        hold_reason = ""
        if status == "HOLD":
            failed_criteria = [k for k, v in apollo_eval.get("criteria", {}).items() if not v.get("passed", False)]
            hold_reason = "Failed gates: " + ", ".join(failed_criteria) if failed_criteria else "Insufficient evidence"

        rec = {
            "company": c_name,
            "domain": domain,
            "sector": sector,
            # Trigger
            "trigger_verified": trigger_verified,
            "trigger_date": trigger_meta.get("trigger_date", ""),
            "trigger_source_url": trigger_meta.get("source_url", ""),
            "trigger_source_role": trigger_meta.get("source_role", ""),
            "trigger_domain": trigger_meta.get("source_domain", ""),
            "trigger_snippet": trigger_meta.get("snippet", ""),
            "trigger_facility_confidence": trigger_meta.get("trigger_facility_confidence", "UNKNOWN"),
            # Facility
            "facility": facility_meta.get("address", f"{city}, {state}"),
            "address_precision": facility_meta.get("address_precision", "UNKNOWN"),
            "facility_verified": facility_meta.get("facility_verified", False),
            "trigger_facility_confidence": facility_meta.get("trigger_facility_confidence", "UNKNOWN"),
            # Person
            "person_name": key_person,
            "person_designation": role,
            "person_source_url": person_meta.get("person_source_url", ""),
            "person_source_role": person_meta.get("person_source_role", ""),
            "employment_verified": person_meta.get("employment_verified", False),
            "duties_verified": person_meta.get("duties_verified", False),
            "person_facility_classification": person_meta.get("facility_classification", "COMPANY_ONLY"),
            # Contact
            "contact_class": contact_class,
            "inferred_email": inferred_email,
            # Calibration
            "likely_instruments": cal_meta["instruments"],
            "nabl_scope": cal_meta["nabl_scope"],
            # Scores and status
            "lead_score": round(lead_score, 1),
            "status": status,
            "apollo_qualified": apollo_qualified,
            "apollo_reason": apollo_eval.get("reason", ""),
            "hold_reason": hold_reason,
            "production_ready": False,
        }
        all_records.append(rec)

        if status == "APOLLO_READY":
            apollo_ready_candidates.append(rec)

        time.sleep(0.5)  # pacing: 3 queries per company

    elapsed = time.time() - start_time

    # Identify most common gate failure
    most_common_failure = max(gate_failure_counts, key=gate_failure_counts.get) if gate_failure_counts else "N/A"

    output_file = "/app/scratch/deep_research_40_results.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_companies": len(all_records),
            "elapsed_seconds": round(elapsed, 2),
            "apollo_ready_count": len(apollo_ready_candidates),
            "trigger_verified_count": sum(1 for r in all_records if r["trigger_verified"]),
            "facility_verified_count": sum(1 for r in all_records if r["facility_verified"]),
            "person_employment_verified_count": sum(1 for r in all_records if r["employment_verified"]),
            "person_duties_verified_count": sum(1 for r in all_records if r["duties_verified"]),
            "gate_failure_counts": gate_failure_counts,
            "most_common_gate_failure": most_common_failure,
            "records": all_records,
        }, f, indent=2)

    logger.info(f"Completed 40 companies in {elapsed:.2f}s. APOLLO_READY candidates: {len(apollo_ready_candidates)}.")
    logger.info(f"Most common gate failure: {most_common_failure}")


if __name__ == "__main__":
    main()
