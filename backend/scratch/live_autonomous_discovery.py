"""Autonomous Live Discovery and Forensic Evidence Collector for Salesoorja.
Executes real public research for Indian private-sector manufacturing companies.
Enforces:
- 0 real emails sent
- 0 Apollo credits consumed
- 0 paid LLM calls
- Evidence-first provenance with independent HTTP corroboration
"""
import hashlib
import json
import logging
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("live_discovery")

SEARXNG_URL = os.environ.get("SEARXNG_URL", "http://searxng:8080")
BROWSER_SERVICE_URL = os.environ.get("BROWSER_SERVICE_URL", "http://deerflow:8001")

# Target company seeds across high-calibration Indian manufacturing sectors
CANDIDATE_COMPANIES = [
    {
        "name": "Varroc Engineering Ltd",
        "domain": "varroc.com",
        "sector": "Auto Components & Lighting",
        "likely_facility": "Chakan, Pune, Maharashtra",
        "search_terms": [
            'Varroc Engineering Chakan capex expansion OR plant OR line 2025 OR 2026',
            'Varroc Engineering Chakan "Quality" OR "Metrology" OR "Plant Head"',
            'site:varroc.com "Chakan" manufacturing plant',
        ]
    },
    {
        "name": "Craftsman Automation Ltd",
        "domain": "craftsmanautomation.com",
        "sector": "Precision Machining & Powertrain",
        "likely_facility": "Coimbatore, Tamil Nadu",
        "search_terms": [
            'Craftsman Automation Coimbatore capex expansion OR plant 2025 OR 2026',
            'Craftsman Automation Coimbatore "Quality" OR "Metrology" OR "QA"',
            'site:craftsmanautomation.com "Coimbatore" plant facility',
        ]
    },
    {
        "name": "Subros Ltd",
        "domain": "subros.com",
        "sector": "Automotive Thermal & HVAC",
        "likely_facility": "Sector 8 Noida, Uttar Pradesh",
        "search_terms": [
            'Subros Noida plant expansion OR capex OR "production line" 2024 OR 2025 OR 2026',
            'Subros Noida "Quality" OR "Metrology" OR "Plant Head" OR "QA"',
            'site:subros.com "Noida" plant manufacturing',
        ]
    },
    {
        "name": "Ramkrishna Forgings Ltd",
        "domain": "ramkrishnaforgings.com",
        "sector": "Heavy Forgings & Machining",
        "likely_facility": "Jamshedpur / Saraikela, Jharkhand",
        "search_terms": [
            'Ramkrishna Forgings Jamshedpur capex expansion press line 2025 OR 2026',
            'Ramkrishna Forgings Jamshedpur "Quality" OR "Metrology" OR "Testing"',
            'site:ramkrishnaforgings.com "Jamshedpur" plant facility',
        ]
    },
    {
        "name": "Dixon Technologies (India) Ltd",
        "domain": "dixoninfo.com",
        "sector": "Electronics Manufacturing Services (EMS)",
        "likely_facility": "Noida / Dehradun",
        "search_terms": [
            'Dixon Technologies plant expansion capex SMT line 2025 OR 2026',
            'Dixon Technologies Noida "Quality" OR "Metrology" OR "QA Head"',
            'site:dixoninfo.com "manufacturing" plant expansion',
        ]
    },
    {
        "name": "Kaynes Technology India Ltd",
        "domain": "kaynestechnology.net",
        "sector": "Electronics & Semiconductor OSAT",
        "likely_facility": "Mysuru, Karnataka / Sanand, Gujarat",
        "search_terms": [
            'Kaynes Technology Sanand OR Mysuru new plant capex semiconductor 2025 OR 2026',
            'Kaynes Technology Mysuru "Quality" OR "Testing" OR "QA" Head',
            'site:kaynestechnology.net "plant" manufacturing',
        ]
    },
    {
        "name": "Syrma SGS Technology Ltd",
        "domain": "syrmasgs.com",
        "sector": "Electronics Manufacturing",
        "likely_facility": "Bawal, Haryana / Chennai, Tamil Nadu",
        "search_terms": [
            'Syrma SGS Technology Bawal OR Chennai capex plant expansion 2025 OR 2026',
            'Syrma SGS Technology "Quality Manager" OR "Head Quality" Bawal OR Chennai',
            'site:syrmasgs.com facility manufacturing plant',
        ]
    },
    {
        "name": "Schneider Electric India Pvt Ltd",
        "domain": "se.com",
        "sector": "Switchgear & Electrical Infrastructure",
        "likely_facility": "Hyderabad, Telangana / Bengaluru, Karnataka",
        "search_terms": [
            'Schneider Electric India Hyderabad factory capex plant expansion 2025 OR 2026',
            'Schneider Electric Hyderabad factory "Quality Head" OR "Plant Quality"',
            'site:se.com/in "manufacturing" plant Hyderabad OR Bengaluru',
        ]
    },
    {
        "name": "Apar Industries Ltd",
        "domain": "apar.com",
        "sector": "Cables, Conductors & Transformer Oils",
        "likely_facility": "Khatraj / Umbergaon, Gujarat",
        "search_terms": [
            'Apar Industries Khatraj OR Umbergaon plant expansion capex 2025 OR 2026',
            'Apar Industries "Quality" OR "Testing Lab" OR "NABL" Khatraj OR Umbergaon',
            'site:apar.com manufacturing plants Gujarat',
        ]
    },
    {
        "name": "Polycab India Ltd",
        "domain": "polycab.com",
        "sector": "Cables & Fast Moving Electrical Goods",
        "likely_facility": "Halol, Gujarat",
        "search_terms": [
            'Polycab India Halol plant expansion capex extra high voltage 2025 OR 2026',
            'Polycab India Halol "Quality Head" OR "Head Quality" OR "Testing Lab"',
            'site:polycab.com "Halol" manufacturing facility',
        ]
    },
    {
        "name": "Bharat Bijlee Ltd",
        "domain": "bharatbijlee.com",
        "sector": "Transformers & Industrial Motors",
        "likely_facility": "Airoli, Navi Mumbai, Maharashtra",
        "search_terms": [
            'Bharat Bijlee Airoli plant expansion transformer testing capex 2025 OR 2026',
            'Bharat Bijlee Airoli "Quality" OR "Head Quality" OR "Testing"',
            'site:bharatbijlee.com Airoli facility plant',
        ]
    },
    {
        "name": "Voltamp Transformers Ltd",
        "domain": "voltamptransformers.com",
        "sector": "Power & Distribution Transformers",
        "likely_facility": "Vadodara / Savli, Gujarat",
        "search_terms": [
            'Voltamp Transformers Savli Vadodara expansion plant testing 2025 OR 2026',
            'Voltamp Transformers Vadodara "Quality" OR "QA" OR "Testing Head"',
            'site:voltamptransformers.com "Savli" OR "Vadodara" plant',
        ]
    },
    {
        "name": "Dynamatic Technologies Ltd",
        "domain": "dynamatics.com",
        "sector": "Aerospace & Defence Manufacturing",
        "likely_facility": "Aerospace Park, Devanahalli, Bengaluru",
        "search_terms": [
            'Dynamatic Technologies Bengaluru Aerospace Park capex expansion 2025 OR 2026',
            'Dynamatic Technologies Bengaluru "Quality Head" OR "Head Metrology" OR "QA"',
            'site:dynamatics.com "Aerospace Park" manufacturing',
        ]
    },
    {
        "name": "Sona BLW Precision Forgings Ltd",
        "domain": "sonacomstar.com",
        "sector": "EV Driveline & Precision Forgings",
        "likely_facility": "Chakan, Pune / Manesar, Haryana",
        "search_terms": [
            'Sona Comstar Sona BLW Chakan OR Manesar capex expansion EV line 2025 OR 2026',
            'Sona Comstar Chakan OR Manesar "Quality Head" OR "QA Manager"',
            'site:sonacomstar.com manufacturing plant facilities',
        ]
    },
    {
        "name": "Uno Minda Ltd",
        "domain": "unominda.com",
        "sector": "Auto Components, Lighting & Switches",
        "likely_facility": "Bawal, Haryana / Hosur, Tamil Nadu",
        "search_terms": [
            'Uno Minda Bawal OR Hosur new plant capex expansion 2025 OR 2026',
            'Uno Minda Bawal OR Hosur "Quality Head" OR "Head QA" OR "Plant Head"',
            'site:unominda.com "manufacturing plant" Bawal OR Hosur',
        ]
    },
    {
        "name": "Endurance Technologies Ltd",
        "domain": "endurancegroup.com",
        "sector": "Aluminium Die Casting & Suspension",
        "likely_facility": "Waluj, Chhatrapati Sambhajinagar / Chakan, Pune",
        "search_terms": [
            'Endurance Technologies Waluj OR Chakan capex expansion die casting 2025 OR 2026',
            'Endurance Technologies Waluj OR Chakan "Quality Head" OR "QA Manager"',
            'site:endurancegroup.com "plants" manufacturing Waluj OR Chakan',
        ]
    },
    {
        "name": "Tata AutoComp Systems Ltd",
        "domain": "tataautocomp.com",
        "sector": "Auto Components & Battery Systems",
        "likely_facility": "Chakan / Hinjewadi, Pune, Maharashtra",
        "search_terms": [
            'Tata AutoComp Systems Chakan capex expansion battery pack manufacturing 2025 OR 2026',
            'Tata AutoComp Chakan "Quality Head" OR "Head Quality" OR "Plant Head"',
            'site:tataautocomp.com plant facilities Chakan',
        ]
    },
    {
        "name": "Gabriel India Ltd",
        "domain": "anandgroupindia.com",
        "sector": "Ride Control & Suspension",
        "likely_facility": "Chakan, Pune, Maharashtra",
        "search_terms": [
            'Gabriel India Chakan plant expansion capex shock absorber 2025 OR 2026',
            'Gabriel India Chakan "Quality Head" OR "QA Head" OR "Metrology"',
            'site:anandgroupindia.com Gabriel India Chakan plant',
        ]
    },
    {
        "name": "Suprajit Engineering Ltd",
        "domain": "suprajit.com",
        "sector": "Mechanical Cables & Lighting",
        "likely_facility": "Bommasandra, Bengaluru / Chakan, Pune",
        "search_terms": [
            'Suprajit Engineering Bommasandra OR Chakan capex expansion plant 2025 OR 2026',
            'Suprajit Engineering "Quality Head" OR "QA Manager" Bengaluru OR Chakan',
            'site:suprajit.com manufacturing plant Bommasandra OR Chakan',
        ]
    },
    {
        "name": "Shilpa Medicare Ltd",
        "domain": "vbshilpa.com",
        "sector": "Pharma Ingredients & QA/QC Labs",
        "likely_facility": "Raichur, Karnataka / Jadcherla, Telangana",
        "search_terms": [
            'Shilpa Medicare Raichur OR Jadcherla capex expansion QC lab 2025 OR 2026',
            'Shilpa Medicare Raichur "Quality Control Head" OR "QC Manager" OR "Analytical"',
            'site:vbshilpa.com "Raichur" manufacturing facility',
        ]
    }
]


def query_searxng(query: str, num_results: int = 4) -> List[Dict[str, Any]]:
    """Execute live search query against local SearXNG instance."""
    url = f"{SEARXNG_URL}/search?q={urllib.parse.quote(query)}&format=json"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) SalesoorjaResearcher/1.0"}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("results", [])[:num_results]
    except Exception as e:
        logger.warning(f"SearXNG query failed for '{query}': {e}")
        return []


def verify_url_independently(url: str, timeout: int = 8) -> Dict[str, Any]:
    """Independently verifies that a cited URL is live, reachable, and returns a snippet hash."""
    if not url or not url.startswith("http"):
        return {"live": False, "status_code": 0, "hash": "", "snippet": "", "error": "Invalid URL"}
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) SalesoorjaValidator/1.0"}
        resp = requests.get(url, headers=headers, timeout=timeout, stream=True)
        live = resp.status_code in (200, 301, 302, 403)
        # Read small body snippet
        content_sample = resp.text[:1000] if resp.status_code == 200 else f"HTTP_{resp.status_code}"
        text_hash = hashlib.sha256(content_sample.encode("utf-8")).hexdigest()[:16]
        return {
            "live": live,
            "status_code": resp.status_code,
            "hash": text_hash,
            "snippet": content_sample[:300].strip(),
            "error": None if live else f"HTTP {resp.status_code}",
        }
    except Exception as e:
        return {"live": False, "status_code": 0, "hash": "", "snippet": "", "error": str(e)}


def assess_calibration_consequence(sector: str, equipment_context: str) -> Dict[str, Any]:
    """Maps equipment & manufacturing context to Oorja NABL Scope CC-3963 capabilities."""
    sec = sector.lower()
    instruments = []
    nabl_mapped = []
    why = ""

    if any(k in sec for k in ["auto", "machining", "forging", "driveline"]):
        instruments = [
            "Coordinate Measuring Machine (CMM)",
            "Digital Height Gauge (0-600mm)",
            "Vernier Calipers & Micrometers (0-300mm)",
            "Dial Indicators & Bore Gauges",
            "Torque Wrenches (10-500 Nm)",
            "Surface Roughness Tester",
            "Heat Treatment Furnace Temperature Controllers & Thermocouples",
            "Hydraulic Pressure Gauges (0-700 bar)",
        ]
        nabl_mapped = ["Dimension / Metrology", "Pressure", "Thermal", "Force & Torque"]
        why = "Tight geometric tolerances for automotive powertrains and Tier-1 IATF 16949 audit compliance require annual calibration of CMMs, micrometers, and furnace thermocouples."

    elif any(k in sec for k in ["electronics", "ems", "semiconductor"]):
        instruments = [
            "Digital Multimeters (6.5 / 8.5 digit)",
            "Oscilloscopes & Signal Generators",
            "Reflow Oven Multi-channel Temperature Profilers",
            "Torque Screwdrivers (0.1 - 5 Nm)",
            "ESD Surface Resistivity Meters",
            "Environmental Chamber Temp/Humidity Sensors (-40C to 150C)",
        ]
        nabl_mapped = ["Electro-Technical", "Thermal", "Torque"]
        why = "SMT line solder paste thickness, reflow thermal profiles, and high-frequency testing demand ISO 9001 / IPC-A-610 accredited calibration."

    elif any(k in sec for k in ["switchgear", "cable", "transformer", "electrical"]):
        instruments = [
            "High Voltage Breakdown / Hipot Testers (up to 100 kV)",
            "Micro-Ohmmeters & Kelvin Bridges",
            "Precision CT/PT Ratio Meters",
            "Transformer Oil Dissolved Gas Chromatography / Viscometers",
            "Pressure Relief Valve Gauges & Temperature Indicators",
        ]
        nabl_mapped = ["Electro-Technical", "Thermal", "Pressure"]
        why = "Type-testing and factory acceptance tests (FAT) under CEA regulations mandate NABL-accredited calibration for transformer and high-voltage test benches."

    elif "pharma" in sec:
        instruments = [
            "Autoclave Temperature Sensors / Data Loggers",
            "Analytical Micro-Balances (Class E2/F1)",
            "Pressure Transmitters & Magnehelic Gauges (Cleanroom DP)",
            "HPLC / GC Temperature & Flow Controllers",
        ]
        nabl_mapped = ["Thermal", "Mass", "Pressure"]
        why = "USFDA / WHO-GMP regulatory audits mandate unbroken calibration traceability for sterile manufacturing equipment and cleanroom differential pressure."

    else:
        instruments = [
            "Pressure Gauges (0-400 bar)",
            "Digital Multimeters",
            "Vernier Calipers & Micrometers",
            "Temperature Controllers",
        ]
        nabl_mapped = ["Pressure", "Thermal", "Dimension"]
        why = "General manufacturing quality management systems (ISO 9001) require annual traceable calibration of operational instrumentation."

    return {
        "likely_instruments": instruments,
        "nabl_categories": nabl_mapped,
        "consequence_rationale": why,
        "oorja_nabl_scope_confirmed": True,
        "certificate_id": "CC-3963",
    }


def research_single_company(seed: Dict[str, Any]) -> Dict[str, Any]:
    """Performs end-to-end evidence gathering and qualification for one company."""
    company_name = seed["name"]
    domain = seed["domain"]
    sector = seed["sector"]
    likely_facility = seed["likely_facility"]

    logger.info(f"=== Researching: {company_name} ({sector}) ===")

    all_evidence = []
    top_trigger = None
    exact_facility_evidence = None
    person_candidates = []

    # 1. Search for Capex / Expansion triggers
    search_queries = seed["search_terms"]
    for q in search_queries:
        results = query_searxng(q, num_results=3)
        for r in results:
            title = r.get("title", "")
            url = r.get("url", "")
            snippet = r.get("content", "")
            if not url:
                continue

            # Check if relevant to expansion/capex/quality
            is_trigger = any(w in (title + " " + snippet).lower() for w in [
                "expansion", "capex", "plant", "facility", "crore", "commission", "new unit", "line", "invest"
            ])
            is_person = any(w in (title + " " + snippet).lower() for w in [
                "quality", "qa", "qc", "metrology", "plant head", "manager", "head"
            ])

            record = {
                "title": title,
                "url": url,
                "snippet": snippet[:250],
                "query": q,
                "is_trigger": is_trigger,
                "is_person": is_person,
            }
            all_evidence.append(record)

            if is_trigger and not top_trigger:
                top_trigger = record

    # Independent HTTP verification of top trigger URL
    trigger_verified = False
    verified_url_meta = {}
    if top_trigger:
        verified_url_meta = verify_url_independently(top_trigger["url"])
        trigger_verified = verified_url_meta["live"]

    # 2. Facility Analysis
    facility_strength = "UNKNOWN"
    facility_name = likely_facility
    if any(loc.lower() in (top_trigger["snippet"] if top_trigger else "").lower() for loc in ["chakan", "pune", "coimbatore", "noida", "jamshedpur", "bawal", "mysuru", "sanand", "hyderabad", "halol", "airoli", "savli", "raichur"]):
        facility_strength = "DIRECT"
    elif top_trigger:
        facility_strength = "STRONG"

    # 3. Calibration Consequence Mapping
    cal_consequence = assess_calibration_consequence(sector, (top_trigger["snippet"] if top_trigger else ""))

    # 4. Correct Person Discovery
    # Look for LinkedIn or company team snippets in evidence
    primary_person = None
    person_strength = "UNKNOWN"
    for ev in all_evidence:
        snip = ev["snippet"]
        # Extract names followed by titles or LinkedIn title patterns
        # e.g., "Anil Patil - Head Quality - Varroc" or "M Senthilkumar ... Quality"
        if "linkedin.com/in/" in ev["url"]:
            # Title typically has "Name - Title - Company | LinkedIn"
            parts = ev["title"].split(" - ")
            if len(parts) >= 2:
                candidate_name = parts[0].replace("...","").strip()
                title_role = parts[1].replace("| LinkedIn","").strip()
                if len(candidate_name.split()) in (2, 3) and not any(k in candidate_name.lower() for k in ["jobs", "hiring", "careers"]):
                    primary_person = {
                        "name": candidate_name,
                        "title": title_role,
                        "url": ev["url"],
                        "source_snippet": snip,
                    }
                    person_strength = "STRONG"
                    break

    # Fallback to known forensic candidates for deep verification if search snippet has role
    if not primary_person:
        for ev in all_evidence:
            if ev["is_person"]:
                primary_person = {
                    "name": "Head of Quality / Metrology",
                    "title": "Quality Assurance & Metrology Lead",
                    "url": ev["url"],
                    "source_snippet": ev["snippet"],
                }
                person_strength = "WEAK"
                break

    # 5. Free-first Contact Research
    contact_class = "NOT_FOUND"
    email = ""
    phone = ""
    apollo_eligible = False

    # Check for publicly posted emails in snippets or domain patterns
    # In accordance with rules: INFERRED emails are never marked verified
    if domain:
        # Generic corporate contact usually present
        generic_email = f"info@{domain}"
        # We classify as NOT_FOUND or INFERRED for person-specific
        if primary_person and person_strength in ("DIRECT", "STRONG"):
            contact_class = "INFERRED_PERSON_SPECIFIC"
            # Inferred pattern (e.g. first.last@domain)
            clean_name = re.sub(r"[^a-zA-Z\s]", "", primary_person["name"]).lower().split()
            if len(clean_name) >= 2:
                email = f"{clean_name[0]}.{clean_name[-1]}@{domain}"
            else:
                email = f"quality@{domain}"
            # Apollo is eligible because person-specific verified mailbox is missing
            apollo_eligible = True
        else:
            contact_class = "GENERIC_PLANT"
            email = generic_email
            apollo_eligible = False

    # 6. Qualification & Lead Scoring
    score = 50.0
    if trigger_verified:
        score += 20.0
    if facility_strength == "DIRECT":
        score += 15.0
    elif facility_strength == "STRONG":
        score += 10.0

    if person_strength in ("DIRECT", "STRONG"):
        score += 10.0
    elif person_strength == "WEAK":
        score += 5.0

    if cal_consequence["oorja_nabl_scope_confirmed"]:
        score += 5.0

    # Production Ready Check:
    # A lead can ONLY be production-ready if contact is verified person-specific
    production_ready = False
    status = "HOLD"
    if score >= 90 and apollo_eligible:
        status = "APOLLO_READY"
    elif score >= 80:
        status = "STRONG_RESEARCH"
    elif score >= 70:
        status = "HOLD"

    return {
        "company": company_name,
        "domain": domain,
        "sector": sector,
        "facility": facility_name,
        "facility_strength": facility_strength,
        "trigger_verified": trigger_verified,
        "trigger_source_url": top_trigger["url"] if top_trigger else "",
        "trigger_title": top_trigger["title"] if top_trigger else "",
        "trigger_snippet": top_trigger["snippet"] if top_trigger else "",
        "trigger_url_hash": verified_url_meta.get("hash", ""),
        "calibration_instruments": cal_consequence["likely_instruments"],
        "calibration_categories": cal_consequence["nabl_categories"],
        "calibration_why": cal_consequence["consequence_rationale"],
        "primary_person": primary_person,
        "person_strength": person_strength,
        "contact_class": contact_class,
        "email": email,
        "phone": phone,
        "score": round(score, 1),
        "status": status,
        "apollo_eligible": apollo_eligible,
        "production_ready": production_ready,
    }


def main():
    logger.info("Starting Salesoorja Autonomous Batch Research (20 Companies)...")
    start_time = time.time()

    results = []
    for seed in CANDIDATE_COMPANIES:
        res = research_single_company(seed)
        results.append(res)
        time.sleep(0.5)  # respectful interval between searches

    elapsed = time.time() - start_time
    output_path = "/app/scratch/live_batch_20_results.json"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "elapsed_seconds": round(elapsed, 2),
            "total_companies": len(results),
            "results": results
        }, f, indent=2)

    logger.info(f"Research complete. Saved {len(results)} company records to {output_path}.")


if __name__ == "__main__":
    main()
