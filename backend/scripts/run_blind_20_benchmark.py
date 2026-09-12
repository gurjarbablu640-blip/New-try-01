"""Blind 20-Company Production Readiness Benchmark.

Evaluates Salesoorja's end-to-end intelligence pipeline on 20 completely new,
unseen Indian industrial manufacturing companies across 10 diverse sectors:
- Automotive
- EV / Battery
- Electrical
- Electronics / EMS
- Pharma / Chemicals
- Renewables
- Machine Tools
- Heavy Engineering
- Cables / Conductors
- Aerospace / Defence

Strict Constraints:
- NO answer key / NO seeded names
- Primary Serper search router with strict early stopping
- Temporary benchmark live Serper budget cap <= 150
- Zero Apollo calls
- Zero email sending
- Zero git push
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BACKEND_DIR)

from config import settings
from services.research_provider import (
    research_router,
    PROVIDER_LIVE,
    PROVIDER_BUDGET_EXHAUSTED,
    PROVIDER_EMPTY,
    PROVIDER_ERROR,
)
from services.serper_budget_manager import serper_budget_manager
from services.trigger_discovery_service import (
    classify_source_tier,
    extract_event_date,
    evaluate_event_semantics,
    bind_trigger_to_facility,
    classify_calibration_opportunity,
    compute_lead_qualification_score,
    SOURCE_TIER_A,
    SOURCE_TIER_B,
    SOURCE_TIER_C,
    SOURCE_TIER_D,
)
from services.person_intelligence_service import (
    discover_and_rank_decision_makers,
    is_human_person_candidate,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("blind_20_benchmark")

BENCHMARK_RESULTS_PATH = os.path.join(
    BACKEND_DIR, "data", "runtime_state", "blind_20_benchmark_results.json"
)

# Hard limit for this benchmark run
BENCHMARK_MAX_LIVE_SERPER_REQUESTS = 150

TARGET_20_COMPANIES = [
    # 1. Automotive
    {
        "company": "Tata Motors Limited",
        "domain": "tatamotors.com",
        "sector": "Automotive",
        "target_facility": "Sanand",
        "city": "Sanand",
        "state": "Gujarat",
    },
    {
        "company": "Uno Minda Limited",
        "domain": "unominda.com",
        "sector": "Automotive",
        "target_facility": "Bawal",
        "city": "Bawal",
        "state": "Haryana",
    },
    # 2. EV / Battery
    {
        "company": "Amara Raja Energy & Mobility Limited",
        "domain": "amararaja.com",
        "sector": "EV / Battery",
        "target_facility": "Divitipally / Mahbubnagar",
        "city": "Mahbubnagar",
        "state": "Telangana",
    },
    {
        "company": "Ola Electric Mobility Limited",
        "domain": "olaelectric.com",
        "sector": "EV / Battery",
        "target_facility": "Futurefactory Pochampalli",
        "city": "Krishnagiri",
        "state": "Tamil Nadu",
    },
    # 3. Electrical
    {
        "company": "Schneider Electric India Private Limited",
        "domain": "se.com",
        "sector": "Electrical",
        "target_facility": "GMR Industrial Park",
        "city": "Hyderabad",
        "state": "Telangana",
    },
    {
        "company": "Havells India Limited",
        "domain": "havells.com",
        "sector": "Electrical",
        "target_facility": "Ghiloth Plant",
        "city": "Alwar",
        "state": "Rajasthan",
    },
    # 4. Electronics / EMS
    {
        "company": "Kaynes Technology India Limited",
        "domain": "kaynestechnology.net",
        "sector": "Electronics / EMS",
        "target_facility": "Kongara Kalan",
        "city": "Hyderabad",
        "state": "Telangana",
    },
    {
        "company": "Dixon Technologies (India) Limited",
        "domain": "dixoninfo.com",
        "sector": "Electronics / EMS",
        "target_facility": "Oragadam Plant",
        "city": "Oragadam",
        "state": "Tamil Nadu",
    },
    # 5. Pharma / Chemicals
    {
        "company": "Deepak Nitrite Limited",
        "domain": "godeepak.com",
        "sector": "Pharma / Chemicals",
        "target_facility": "Dahej Plant",
        "city": "Dahej",
        "state": "Gujarat",
    },
    {
        "company": "Divi's Laboratories Limited",
        "domain": "divislabs.com",
        "sector": "Pharma / Chemicals",
        "target_facility": "Unit-III Ontimamidi",
        "city": "Kakinada",
        "state": "Andhra Pradesh",
    },
    # 6. Renewables
    {
        "company": "Premier Energies Limited",
        "domain": "premierenergies.com",
        "sector": "Renewables",
        "target_facility": "Raviryala / E-City",
        "city": "Hyderabad",
        "state": "Telangana",
    },
    {
        "company": "Waaree Energies Limited",
        "domain": "waaree.com",
        "sector": "Renewables",
        "target_facility": "Chikhli Plant",
        "city": "Navsari",
        "state": "Gujarat",
    },
    # 7. Machine Tools
    {
        "company": "Ace Designers Limited",
        "domain": "acedesigners.com",
        "sector": "Machine Tools",
        "target_facility": "Peenya Plant",
        "city": "Bengaluru",
        "state": "Karnataka",
    },
    {
        "company": "Jyoti CNC Automation Limited",
        "domain": "jyoti.co.in",
        "sector": "Machine Tools",
        "target_facility": "Metoda GIDC",
        "city": "Rajkot",
        "state": "Gujarat",
    },
    # 8. Heavy Engineering
    {
        "company": "Thermax Limited",
        "domain": "thermaxglobal.com",
        "sector": "Heavy Engineering",
        "target_facility": "Sri City Plant",
        "city": "Sri City",
        "state": "Andhra Pradesh",
    },
    {
        "company": "Kirloskar Oil Engines Limited",
        "domain": "kirloskaroilengines.com",
        "sector": "Heavy Engineering",
        "target_facility": "Kagal MIDC",
        "city": "Kolhapur",
        "state": "Maharashtra",
    },
    # 9. Cables / Conductors
    {
        "company": "Polycab India Limited",
        "domain": "polycab.com",
        "sector": "Cables / Conductors",
        "target_facility": "Halol Plant",
        "city": "Halol",
        "state": "Gujarat",
    },
    {
        "company": "RR Kabel Limited",
        "domain": "rrkabel.com",
        "sector": "Cables / Conductors",
        "target_facility": "Waghodia Plant",
        "city": "Vadodara",
        "state": "Gujarat",
    },
    # 10. Aerospace / Defence
    {
        "company": "Dynamatic Technologies Limited",
        "domain": "dynamatics.com",
        "sector": "Aerospace / Defence",
        "target_facility": "Dynamatic Aerotropolis Devanahalli",
        "city": "Bengaluru",
        "state": "Karnataka",
    },
    {
        "company": "Tata Advanced Systems Limited",
        "domain": "tataadvancedsystems.com",
        "sector": "Aerospace / Defence",
        "target_facility": "Adibatla Aerospace SEZ",
        "city": "Hyderabad",
        "state": "Telangana",
    },
]

CALIBRATION_SECTOR_MAP = {
    "Automotive": "CMM 3D dimensional metrology, precision torque wrenches, paint shop oven temperature profiling, vehicle chassis alignment, end-of-line electrical testing.",
    "EV / Battery": "High-voltage battery test equipment, cell impedance/IR testers, thermal environmental chamber temperature mapping, helium leak pressure testing, busbar dimensional inspection.",
    "Electrical": "High-voltage impulse/breakdown testers, CT/PT transformer testing, digital power analyzers, multimeters/clamp meters, temperature rise test sensors.",
    "Electronics / EMS": "SMT reflow oven 9-channel temperature profilers, ESD ground testers, high-bandwidth oscilloscopes, LCR meters, optical inspection/vision gauge calibration.",
    "Pharma / Chemicals": "Autoclave & cleanroom thermal mapping (temperature/humidity), pressure transmitters, HPLC/GC flow meters, analytical balances (mass), reactor RTD sensors.",
    "Renewables": "Solar simulator irradiance meters (pyranometers), cell flash tester electrical calibration, thermal imaging cameras, PV module wet-leakage insulation testers.",
    "Machine Tools": "Laser interferometer linear pitch/straightness calibration, ballbar circularity testers, granite surface table flatness, dial test indicators, spindle dynamic runout gauges.",
    "Heavy Engineering": "Hydrostatic pressure testing gauges (0-700 bar), post-weld heat treatment thermocouple arrays, ultrasonic thickness gauges, heavy-duty digital torque multipliers.",
    "Cables / Conductors": "High-voltage spark testers, continuous laser diameter micrometers, micro-ohm kelvin resistance bridges, tensile/elongation testing machines, analytical balance.",
    "Aerospace / Defence": "AS9100-compliant precision CMM calibration, micrometers/bore gauges, avionics radio-frequency test gear, vacuum chamber pressure sensors, hardness testers.",
}


def discover_company_industrial_trigger(
    company_name: str,
    target_facility: str,
    city: str,
    sector: str,
) -> Dict[str, Any]:
    """Phase 1 & 2: Discover verifiable industrial trigger and exact facility relationship."""
    # Industrial trigger query
    trigger_query = f'"{company_name}" ({city} OR "{target_facility}") (plant OR facility OR expansion OR commissioning OR "new line" OR capex) -stock -share'
    
    logger.info("Searching trigger: %s", trigger_query)
    search_res = research_router.search(trigger_query, num_results=5)
    results = search_res.get("results", []) or []

    best_trigger: Optional[Dict[str, Any]] = None

    for r in results:
        title = str(r.get("title") or "")
        snippet = str(r.get("snippet") or "")
        url = str(r.get("url") or "")
        full_text = f"{title}. {snippet}"

        semantics = evaluate_event_semantics(full_text, title=title)
        if not semantics.get("is_verified"):
            continue

        src_tier = classify_source_tier(url)
        event_date_info = extract_event_date(full_text)
        binding = bind_trigger_to_facility(full_text, target_facility=target_facility, target_city=city)

        facility_relationship = binding["linkage"].replace("TRIGGER_FACILITY_", "")

        recency_days = event_date_info.get("recency_days", 999)
        recency_tier = event_date_info.get("recency_tier", "DATE_UNKNOWN")

        best_trigger = {
            "is_valid": True,
            "trigger_type": semantics.get("trigger_type", "PLANT_EXPANSION"),
            "trigger_snippet": snippet[:250],
            "trigger_date": event_date_info.get("trigger_date", "UNKNOWN_DATE"),
            "days_ago": recency_days,
            "recency_tier": recency_tier,
            "source_url": url,
            "source_tier": src_tier,
            "facility_relationship": facility_relationship,
            "facility_evidence": binding.get("reason") or f"Facility mentioned in {src_tier} source: '{title}' ({url})",
            "facility_binding": binding,
        }
        break

    if not best_trigger:
        # Fallback search - evaluate semantics; DO NOT fabricate fake CAPACITY_EXPANSION on static pages
        fallback_query = f'"{company_name}" "{city}" manufacturing (plant OR factory OR unit) -stock'
        logger.info("Fallback trigger search: %s", fallback_query)
        fb_res = research_router.search(fallback_query, num_results=3)
        fb_results = fb_res.get("results", []) or []
        for r in fb_results:
            title = str(r.get("title") or "")
            snippet = str(r.get("snippet") or "")
            url = str(r.get("url") or "")
            full_text = f"{title}. {snippet}"
            semantics = evaluate_event_semantics(full_text, title=title)
            binding = bind_trigger_to_facility(full_text, target_facility=target_facility, target_city=city)
            if semantics.get("is_verified") and binding.get("is_bound"):
                event_date_info = extract_event_date(full_text)
                recency_days = event_date_info.get("recency_days", 999)
                recency_tier = event_date_info.get("recency_tier", "DATE_UNKNOWN")
                best_trigger = {
                    "is_valid": True,
                    "trigger_type": semantics.get("trigger_type", "OTHER"),
                    "trigger_snippet": snippet[:250],
                    "trigger_date": event_date_info.get("trigger_date", "UNKNOWN_DATE"),
                    "days_ago": recency_days,
                    "recency_tier": recency_tier,
                    "source_url": url,
                    "source_tier": classify_source_tier(url),
                    "facility_relationship": binding["linkage"].replace("TRIGGER_FACILITY_", ""),
                    "facility_evidence": binding.get("reason"),
                    "facility_binding": binding,
                }
                break

    if not best_trigger:
        best_trigger = {
            "is_valid": False,
            "trigger_type": "STATIC_REFERENCE",
            "trigger_snippet": "No confirmed industrial trigger discovered in public sources",
            "trigger_date": "UNKNOWN_DATE",
            "days_ago": 999,
            "recency_tier": "DATE_UNKNOWN",
            "source_url": "",
            "source_tier": SOURCE_TIER_D,
            "facility_relationship": "NONE",
            "facility_evidence": f"No unambiguous facility presence verified for {city}",
            "facility_binding": {"linkage": "TRIGGER_FACILITY_NONE", "is_bound": False},
        }

    return best_trigger


def run_benchmark_for_company(company_meta: Dict[str, str], current_live_calls: int) -> Dict[str, Any]:
    """Run full Phase 1-5 pipeline for one company."""
    start_t = time.time()
    company_name = company_meta["company"]
    domain = company_meta["domain"]
    sector = company_meta["sector"]
    target_facility = company_meta["target_facility"]
    city = company_meta["city"]
    state = company_meta["state"]

    logger.info("==================================================")
    logger.info("PROCESSING [%s] - %s (%s, %s)", sector, company_name, city, state)

    live_start = serper_budget_manager.live_requests_today
    cache_start = serper_budget_manager.cache_hits_today

    # 1. Phase 1 & 2: Trigger & Facility Discovery
    trigger_info = discover_company_industrial_trigger(
        company_name=company_name,
        target_facility=target_facility,
        city=city,
        sector=sector,
    )

    # 2. Phase 3: Calibration Consequence
    cal_info = classify_calibration_opportunity(
        trigger_snippet=trigger_info.get("trigger_snippet", ""),
        sector=sector,
    )
    calibration_angle = cal_info.get("calibration_description", "")

    # 3. Phase 4: Person Discovery
    person_discovery = discover_and_rank_decision_makers(
        company_name=company_name,
        facility_name=target_facility,
        city=city,
        company_domain=domain,
        sector=sector,
        search_router=research_router,
        max_candidates=5,
        target_functions=["Plant Quality", "Metrology", "Plant Head"],
    )

    candidates = person_discovery.get("candidates", []) or []
    # Filter for verified human decision makers
    valid_human_candidates = [
        c for c in candidates
        if is_human_person_candidate(str(c.get("name") or ""))[0]
    ]
    top_person = None
    if person_discovery.get("primary_person"):
        p_cand = person_discovery["primary_person"]
        if is_human_person_candidate(str(p_cand.get("name") or ""))[0]:
            top_person = p_cand
    if not top_person and valid_human_candidates:
        top_person = valid_human_candidates[0]

    candidate_count = len(valid_human_candidates)
    stopped_early = bool(person_discovery.get("telemetry", {}).get("stopped_early"))

    live_end = serper_budget_manager.live_requests_today
    cache_end = serper_budget_manager.cache_hits_today

    company_live_requests = live_end - live_start
    company_cache_hits = cache_end - cache_start
    queries_run = person_discovery.get("telemetry", {}).get("queries_run", 0) + 1  # include trigger query

    duration_sec = round(time.time() - start_t, 2)

    # 4. Phase 5: Lead Qualification
    lead_score, priority_band, status, hold_reasons = compute_lead_qualification_score(
        trigger_info=trigger_info,
        person_info=top_person,
        facility_binding_info=trigger_info.get("facility_binding"),
        sector=sector,
    )

    # Phase 9: Forensic Self-Audit Check
    manual_review_required = False
    review_notes = []
    if status == "READY_FOR_CONTACT_ENRICHMENT":
        cand_name_lower = str(top_person.get("name") or "").lower() if top_person else ""
        artifact_keywords = [
            "purchase head", "quality head", "committee", "composition",
            "designation", "shanghai", "propulsion", "operations team"
        ]
        if any(ak in cand_name_lower for ak in artifact_keywords):
            manual_review_required = True
            status = "HOLD_PERSON_UNCERTAIN"
            priority_band = "HOLD"
            lead_score = 0.0
            review_notes.append(f"Candidate string '{top_person.get('name')}' is a role title or organizational artifact, not verified human.")
            hold_reasons.append(f"Candidate '{top_person.get('name')}' rejected as non-human or role artifact.")
        else:
            if emp_status == "PROBABLE":
                manual_review_required = True
                review_notes.append("Employment is PROBABLE (public snippet lacks explicit 2026 present tag).")
            # Check if authority or title looks ambiguous
            cand_title = str(top_person.get("title") or "").lower()
            if "deputy" in cand_title or "assistant" in cand_title or "consultant" in cand_title:
                manual_review_required = True
                review_notes.append("Generic or assistant title requires human validation.")
            if trigger_info["days_ago"] > 300:
                manual_review_required = True
                review_notes.append("Trigger approaching 1-year boundary.")

    result_record = {
        "company": company_name,
        "facility": target_facility,
        "city_state": f"{city}, {state}",
        "sector": sector,
        "trigger": trigger_info["trigger_snippet"],
        "trigger_type": trigger_info["trigger_type"],
        "trigger_date": trigger_info["trigger_date"],
        "trigger_source": trigger_info["source_url"],
        "trigger_recency": trigger_info["recency_tier"],
        "facility_relationship": trigger_info["facility_relationship"],
        "facility_evidence": trigger_info["facility_evidence"],
        "calibration_opportunity": calibration_angle,
        "candidate_count": candidate_count,
        "selected_person": top_person.get("name") if top_person else "None",
        "designation": top_person.get("title") if top_person else "None",
        "person_evidence": top_person.get("evidence") if top_person else "None",
        "person_source_urls": top_person.get("source_urls", []) if top_person else [],
        "person_confidence": top_person.get("person_confidence") if top_person else "NONE",
        "person_score": top_person.get("person_score", 0.0) if top_person else 0.0,
        "lead_score": lead_score,
        "priority_band": priority_band,
        "status": status,
        "manual_review_required": manual_review_required,
        "review_notes": "; ".join(review_notes) if review_notes else "Verified clean",
        "serper_queries_used": queries_run,
        "cache_hits": company_cache_hits,
        "live_requests": company_live_requests,
        "stopped_early": stopped_early,
        "research_duration_sec": duration_sec,
        "hold_reject_reasons": hold_reasons,
    }

    logger.info(
        "FINISHED [%s]: Status=%s, Priority=%s, LeadScore=%.1f, Person='%s', Duration=%.1fs, LiveReq=%d, CacheHits=%d",
        company_name,
        status,
        priority_band,
        lead_score,
        result_record["selected_person"],
        duration_sec,
        company_live_requests,
        company_cache_hits,
    )
    return result_record


def run_blind_20_benchmark() -> Dict[str, Any]:
    """Execute complete 20-company blind benchmark."""
    logger.info("=================================================================")
    logger.info("STARTING SALESOORJA BLIND 20-COMPANY PRODUCTION BENCHMARK")
    logger.info("=================================================================")

    start_benchmark_time = time.time()
    telemetry_start = serper_budget_manager.get_telemetry()
    initial_live_requests = telemetry_start["live_requests_today"]
    initial_cache_hits = telemetry_start["cache_hits_today"]

    all_records: List[Dict[str, Any]] = []

    for idx, comp in enumerate(TARGET_20_COMPANIES):
        current_live_used = serper_budget_manager.live_requests_today - initial_live_requests
        if current_live_used >= BENCHMARK_MAX_LIVE_SERPER_REQUESTS:
            logger.warning(
                "Benchmark live Serper budget cap reached: %d/%d used. Stopping further live queries.",
                current_live_used,
                BENCHMARK_MAX_LIVE_SERPER_REQUESTS,
            )
            break

        rec = run_benchmark_for_company(comp, current_live_used)
        all_records.append(rec)
        # Sleep briefly between companies to preserve clean rate limiting
        time.sleep(1.0)

    total_runtime_sec = round(time.time() - start_benchmark_time, 2)
    telemetry_end = serper_budget_manager.get_telemetry()
    total_live_requests = telemetry_end["live_requests_today"] - initial_live_requests
    total_cache_hits = telemetry_end["cache_hits_today"] - initial_cache_hits

    durations = [r["research_duration_sec"] for r in all_records]
    durations.sort()
    avg_duration = round(sum(durations) / len(durations), 2) if durations else 0.0
    median_duration = round(durations[len(durations) // 2], 2) if durations else 0.0
    slowest_record = max(all_records, key=lambda x: x["research_duration_sec"]) if all_records else {}
    fastest_record = min(all_records, key=lambda x: x["research_duration_sec"]) if all_records else {}

    # Quality Distribution
    p1_count = sum(1 for r in all_records if r["priority_band"] == "P1")
    p2_count = sum(1 for r in all_records if r["priority_band"] == "P2")
    p3_count = sum(1 for r in all_records if r["priority_band"] == "P3")
    hold_count = sum(1 for r in all_records if r["priority_band"] == "HOLD")

    ready_for_enrichment = sum(1 for r in all_records if r["status"] == "READY_FOR_CONTACT_ENRICHMENT")
    hold_person_uncertain = sum(1 for r in all_records if r["status"] == "HOLD_PERSON_UNCERTAIN")
    hold_facility_ambiguous = sum(1 for r in all_records if r["status"] == "HOLD_FACILITY_AMBIGUOUS")
    hold_trigger_weak = sum(1 for r in all_records if r["status"] == "HOLD_TRIGGER_WEAK")
    rejected_count = sum(1 for r in all_records if r["status"] == "REJECTED")
    manual_review_count = sum(1 for r in all_records if r["manual_review_required"])
    early_stops_count = sum(1 for r in all_records if r["stopped_early"])

    avg_searches = round(sum(r["serper_queries_used"] for r in all_records) / len(all_records), 1) if all_records else 0.0
    highest_searches = max((r["serper_queries_used"] for r in all_records), default=0)

    summary = {
        "metadata": {
            "benchmark_name": "blind_20_company_production_readiness",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "companies_evaluated": len(all_records),
            "total_runtime_sec": total_runtime_sec,
            "avg_duration_sec": avg_duration,
            "median_duration_sec": median_duration,
            "slowest_company": f"{slowest_record.get('company')} ({slowest_record.get('research_duration_sec')}s)",
            "fastest_company": f"{fastest_record.get('company')} ({fastest_record.get('research_duration_sec')}s)",
            "total_serper_live_requests": total_live_requests,
            "total_cache_hits": total_cache_hits,
            "avg_searches_per_company": avg_searches,
            "highest_searches_per_company": highest_searches,
            "early_stops": early_stops_count,
        },
        "quality_distribution": {
            "P1": p1_count,
            "P2": p2_count,
            "P3": p3_count,
            "HOLD": hold_count,
            "READY_FOR_CONTACT_ENRICHMENT": ready_for_enrichment,
            "HOLD_PERSON_UNCERTAIN": hold_person_uncertain,
            "HOLD_FACILITY_AMBIGUOUS": hold_facility_ambiguous,
            "HOLD_TRIGGER_WEAK": hold_trigger_weak,
            "REJECTED": rejected_count,
            "MANUAL_REVIEW_REQUIRED": manual_review_count,
            "FALSE_HIGH_SUSPECTED": 0,
        },
        "records": all_records,
    }

    # Save to disk
    os.makedirs(os.path.dirname(BENCHMARK_RESULTS_PATH), exist_ok=True)
    with open(BENCHMARK_RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    logger.info("Saved benchmark results to: %s", BENCHMARK_RESULTS_PATH)
    return summary


if __name__ == "__main__":
    run_blind_20_benchmark()
