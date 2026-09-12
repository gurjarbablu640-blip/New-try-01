"""Salesoorja Fully Blind Production Readiness Benchmark Harness.

Benchmark Name: FULLY_BLIND_PRODUCTION_BENCHMARK

Evaluates the Salesoorja intelligence pipeline on 8 completely new,
unseen industrial manufacturing companies.

Starting inputs provided:
- company
- domain
- sector

STRICTLY OMITTED (Salesoorja must discover autonomously):
- NO target_facility
- NO city
- NO state
- NO trigger
- NO person
- NO expected score / answer key

Constraints:
- Temporary live Serper benchmark cap <= 80 requests
- Atomic Serper dual-reservation budget check on every query
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
from services.research_provider import research_router
from services.serper_budget_manager import serper_budget_manager, SerperBudgetExhaustedError
from services.trigger_discovery_service import (
    classify_source_tier,
    extract_event_date,
    evaluate_event_semantics,
    bind_trigger_to_facility,
    classify_calibration_opportunity,
    compute_lead_qualification_score,
    TRIGGER_FACILITY_DIRECT,
    TRIGGER_FACILITY_STRONG,
    TRIGGER_FACILITY_AMBIGUOUS,
    TRIGGER_FACILITY_NONE,
    SOURCE_TIER_A,
    SOURCE_TIER_B,
    SOURCE_TIER_C,
    SOURCE_TIER_D,
)
from services.person_intelligence_service import (
    discover_and_rank_decision_makers,
    is_human_person_candidate,
    INDIAN_CITIES_TO_STATE,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("fully_blind_benchmark")

BENCHMARK_RESULTS_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "data", "runtime_state", "fully_blind_8_benchmark_results.json")
)
BENCHMARK_MAX_LIVE_SERPER_REQUESTS = 80

# 8 completely new companies — non-overlapping with Gold 5 and prior 20 benchmark
TARGET_8_BLIND_COMPANIES = [
    {
        "company": "AIA Engineering Limited",
        "domain": "aiaengineering.com",
        "sector": "Heavy Engineering",
    },
    {
        "company": "Tube Investments of India Limited",
        "domain": "tiindia.com",
        "sector": "Automotive",
    },
    {
        "company": "Syngene International Limited",
        "domain": "syngeneintl.com",
        "sector": "Pharma",
    },
    {
        "company": "Sterlite Technologies Limited",
        "domain": "stl.tech",
        "sector": "Cables / Conductors",
    },
    {
        "company": "Carborundum Universal Limited",
        "domain": "cumi-murugappa.com",
        "sector": "Industrial Materials",
    },
    {
        "company": "Kaynes Technology India Limited",
        "domain": "kaynestechnology.co.in",
        "sector": "Electronics / EMS",
    },
    {
        "company": "Jindal Stainless Limited",
        "domain": "jindalstainless.com",
        "sector": "Steel",
    },
    {
        "company": "Greaves Cotton Limited",
        "domain": "greavescotton.com",
        "sector": "EV / Powertrain",
    },
]


def autonomously_discover_trigger_and_facility(
    company_name: str,
    domain: str,
    sector: str,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Discovers industrial commercial trigger AND exact manufacturing facility location from scratch."""
    # 1. Broad expansion / capex trigger query
    trigger_query = f'"{company_name}" (expansion OR capex OR commissioning OR "new plant" OR "new facility" OR "new line") India -stock -share'
    logger.info("Executing blind trigger discovery: %s", trigger_query)
    search_res = research_router.search(trigger_query, num_results=5)
    results = search_res.get("results", []) or []

    best_trigger: Optional[Dict[str, Any]] = None
    discovered_facility_info: Dict[str, Any] = {
        "facility_name": "",
        "city": "",
        "state": "",
        "discovery_mode": "AUTONOMOUS",
    }

    for r in results:
        title = str(r.get("title") or "")
        snippet = str(r.get("snippet") or "")
        url = str(r.get("url") or "")
        full_text = f"{title}. {snippet}"

        semantics = evaluate_event_semantics(full_text, title=title)
        if not semantics.get("is_verified"):
            continue

        src_tier = classify_source_tier(url)
        event_date_info = extract_event_date(full_text, title=title, url=url)

        # Autonomously identify any industrial city mentioned in the text
        detected_city = ""
        detected_state = ""
        text_lower = full_text.lower()
        for c_name in sorted(INDIAN_CITIES_TO_STATE.keys(), key=len, reverse=True):
            if re.search(r"\b" + re.escape(c_name) + r"\b", text_lower):
                detected_city = c_name.title()
                detected_state = INDIAN_CITIES_TO_STATE[c_name]
                break

        # Autonomously extract named plant or construct facility name
        plant_match = re.search(r"\b([A-Za-z]+(?:\s+[A-Za-z]+)?\s+(?:plant|facility|works|unit\s+\d+|unit\s+[IVX]+))\b", text_lower)
        if plant_match:
            cand_plant = plant_match.group(1).title()
            invalid_kw = {"power", "solar", "steel", "chemical", "manufacturing", "crore", "new", "mega", "first", "second", "third"}
            words = [w for w in cand_plant.split() if w.lower() not in invalid_kw]
            if words:
                detected_fac = cand_plant
            elif detected_city:
                detected_fac = f"{detected_city} Manufacturing Plant"
            else:
                detected_fac = f"{company_name} Plant"
        elif detected_city:
            detected_fac = f"{detected_city} Facility"
        else:
            detected_fac = f"{company_name} Operations"

        discovered_facility_info = {
            "facility_name": detected_fac,
            "city": detected_city,
            "state": detected_state,
            "discovery_mode": "EVENT_EXTRACTED",
        }

        binding = bind_trigger_to_facility(
            full_text,
            target_facility=detected_fac,
            target_city=detected_city,
            target_state=detected_state,
        )

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
            "facility_relationship": binding["linkage"].replace("TRIGGER_FACILITY_", ""),
            "facility_evidence": binding.get("reason"),
            "facility_binding": binding,
        }
        break

    if not best_trigger:
        # Fallback search for plant presence if no expansion event was found
        plant_query = f'"{company_name}" manufacturing (plant OR factory OR unit) India -stock'
        logger.info("Executing blind plant location discovery: %s", plant_query)
        fb_res = research_router.search(plant_query, num_results=3)
        fb_results = fb_res.get("results", []) or []

        detected_city = ""
        detected_state = ""
        for r in fb_results:
            title = str(r.get("title") or "")
            snippet = str(r.get("snippet") or "")
            url = str(r.get("url") or "")
            full_text = f"{title}. {snippet}"
            text_lower = full_text.lower()

            for c_name in sorted(INDIAN_CITIES_TO_STATE.keys(), key=len, reverse=True):
                if re.search(r"\b" + re.escape(c_name) + r"\b", text_lower):
                    detected_city = c_name.title()
                    detected_state = INDIAN_CITIES_TO_STATE[c_name]
                    break

            if detected_city:
                discovered_facility_info = {
                    "facility_name": f"{detected_city} Plant",
                    "city": detected_city,
                    "state": detected_state,
                    "discovery_mode": "DIRECTORY_EXTRACTED",
                }
                # Check if it has any event semantics
                semantics = evaluate_event_semantics(full_text, title=title)
                if semantics.get("is_verified"):
                    event_date_info = extract_event_date(full_text, title=title, url=url)
                    binding = bind_trigger_to_facility(
                        full_text,
                        target_facility=f"{detected_city} Plant",
                        target_city=detected_city,
                        target_state=detected_state,
                    )
                    best_trigger = {
                        "is_valid": True,
                        "trigger_type": semantics.get("trigger_type", "OTHER"),
                        "trigger_snippet": snippet[:250],
                        "trigger_date": event_date_info.get("trigger_date", "UNKNOWN_DATE"),
                        "days_ago": event_date_info.get("recency_days", 999),
                        "recency_tier": event_date_info.get("recency_tier", "DATE_UNKNOWN"),
                        "source_url": url,
                        "source_tier": classify_source_tier(url),
                        "facility_relationship": binding["linkage"].replace("TRIGGER_FACILITY_", ""),
                        "facility_evidence": binding.get("reason"),
                        "facility_binding": binding,
                    }
                else:
                    best_trigger = {
                        "is_valid": False,
                        "trigger_type": "STATIC_REFERENCE",
                        "trigger_snippet": snippet[:250],
                        "trigger_date": "UNKNOWN_DATE",
                        "days_ago": 999,
                        "recency_tier": "DATE_UNKNOWN",
                        "source_url": url,
                        "source_tier": classify_source_tier(url),
                        "facility_relationship": "STRONG",
                        "facility_evidence": f"Manufacturing unit identified in {detected_city} (static reference only).",
                        "facility_binding": {"linkage": "TRIGGER_FACILITY_STRONG", "is_bound": True},
                    }
                break

    if not best_trigger:
        best_trigger = {
            "is_valid": False,
            "trigger_type": "STATIC_REFERENCE",
            "trigger_snippet": "No industrial trigger or plant location discovered in public search",
            "trigger_date": "UNKNOWN_DATE",
            "days_ago": 999,
            "recency_tier": "DATE_UNKNOWN",
            "source_url": "",
            "source_tier": SOURCE_TIER_D,
            "facility_relationship": "NONE",
            "facility_evidence": "No manufacturing facility presence verified",
            "facility_binding": {"linkage": "TRIGGER_FACILITY_NONE", "is_bound": False},
        }

    return best_trigger, discovered_facility_info


def run_fully_blind_benchmark_for_company(
    company_meta: Dict[str, str],
    initial_live_requests: int,
) -> Dict[str, Any]:
    """Runs complete autonomous pipeline for one company starting with only company/domain/sector."""
    start_t = time.time()
    company_name = company_meta["company"]
    domain = company_meta["domain"]
    sector = company_meta["sector"]

    logger.info("==================================================")
    logger.info("PROCESSING FULLY BLIND [%s] - %s (%s)", sector, company_name, domain)

    live_start = serper_budget_manager.live_requests_today
    cache_start = serper_budget_manager.cache_hits_today

    # 1. Phase 1 & 2: Autonomous Trigger & Facility Discovery
    trigger_info, facility_info = autonomously_discover_trigger_and_facility(
        company_name=company_name,
        domain=domain,
        sector=sector,
    )

    discovered_fac = facility_info.get("facility_name") or ""
    discovered_city = facility_info.get("city") or ""
    discovered_state = facility_info.get("state") or ""

    logger.info(
        "AUTONOMOUS DISCOVERY RESULT for %s: Facility='%s', City='%s', State='%s', TriggerType='%s', ValidTrigger=%s",
        company_name,
        discovered_fac,
        discovered_city,
        discovered_state,
        trigger_info.get("trigger_type"),
        trigger_info.get("is_valid"),
    )

    # 2. Phase 3: Calibration Consequence
    cal_info = classify_calibration_opportunity(
        trigger_snippet=trigger_info.get("trigger_snippet", ""),
        sector=sector,
    )

    # 3. Phase 4: Decision-Maker Discovery
    # Targeted using the discovered facility/city
    person_discovery = discover_and_rank_decision_makers(
        company_name=company_name,
        facility_name=discovered_fac,
        city=discovered_city,
        company_domain=domain,
        sector=sector,
        search_router=research_router,
        max_candidates=5,
        target_functions=["Plant Quality", "Metrology", "Plant Head"],
    )

    candidates = person_discovery.get("candidates", []) or []
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
    queries_run = person_discovery.get("telemetry", {}).get("queries_run", 0) + 1

    duration_sec = round(time.time() - start_t, 2)

    # 4. Phase 5: Lead Qualification & Decompressed Scoring
    lead_score, priority_band, status, hold_reasons = compute_lead_qualification_score(
        trigger_info=trigger_info,
        person_info=top_person,
        facility_binding_info=trigger_info.get("facility_binding"),
        sector=sector,
    )

    # Phase 9: Forensic Verification
    manual_review_required = False
    review_notes = []

    if status == "READY_FOR_CONTACT_ENRICHMENT":
        cand_name_lower = str(top_person.get("name") or "").lower() if top_person else ""
        emp_status = str(top_person.get("current_employment") or "UNKNOWN").upper()
        if emp_status == "PROBABLE":
            manual_review_required = True
            review_notes.append("Employment is PROBABLE (lacks active 2026 present proof).")
        cand_title = str(top_person.get("title") or "").lower()
        if any(w in cand_title for w in ["deputy", "assistant", "consultant"]):
            manual_review_required = True
            review_notes.append("Generic or assistant title requires manual validation.")

    result_record = {
        "company": company_name,
        "domain": domain,
        "sector": sector,
        "discovered_facility": discovered_fac,
        "discovered_city": discovered_city,
        "discovered_state": discovered_state,
        "discovery_mode": facility_info.get("discovery_mode"),
        "trigger_type": trigger_info.get("trigger_type"),
        "trigger_is_valid": trigger_info.get("is_valid"),
        "trigger_date": trigger_info.get("trigger_date"),
        "recency_tier": trigger_info.get("recency_tier"),
        "days_ago": trigger_info.get("days_ago"),
        "trigger_snippet": trigger_info.get("trigger_snippet"),
        "trigger_source_url": trigger_info.get("source_url"),
        "source_tier": trigger_info.get("source_tier"),
        "facility_relationship": trigger_info.get("facility_relationship"),
        "facility_evidence": trigger_info.get("facility_evidence"),
        "calibration_evidence_type": cal_info.get("calibration_evidence_type"),
        "calibration_angle": cal_info.get("calibration_description"),
        "candidate_count": candidate_count,
        "top_person": {
            "name": top_person.get("name") if top_person else None,
            "title": top_person.get("title") if top_person else None,
            "current_employment": top_person.get("current_employment") if top_person else None,
            "facility_relationship": top_person.get("facility_relationship") if top_person else None,
            "authority_class": top_person.get("authority_class") if top_person else None,
            "person_confidence": top_person.get("person_confidence") if top_person else None,
            "person_score": top_person.get("person_score") if top_person else 0.0,
            "evidence_snippet": top_person.get("evidence_snippet") if top_person else None,
        } if top_person else None,
        "lead_score": lead_score,
        "priority_band": priority_band,
        "status": status,
        "hold_reasons": hold_reasons,
        "manual_review_required": manual_review_required,
        "review_notes": review_notes,
        "research_duration_sec": duration_sec,
        "serper_queries_used": queries_run,
        "serper_live_requests": company_live_requests,
        "serper_cache_hits": company_cache_hits,
        "stopped_early": stopped_early,
    }

    logger.info(
        "RESULT [%s] %s -> Band: %s, Score: %s, Status: %s, DiscoveredPerson: %s, Time: %ss, LiveSerper: %d, CacheHits: %d",
        company_name,
        discovered_city or "UnknownSite",
        priority_band,
        lead_score,
        status,
        top_person.get("name") if top_person else "None",
        duration_sec,
        company_live_requests,
        company_cache_hits,
    )
    return result_record


def run_fully_blind_benchmark(benchmark_budget_cap: int = BENCHMARK_MAX_LIVE_SERPER_REQUESTS) -> Dict[str, Any]:
    """Execute complete fully blind 8-company benchmark with hard request cap."""
    logger.info("=================================================================")
    logger.info("STARTING SALESOORJA FULLY BLIND 8-COMPANY PRODUCTION BENCHMARK")
    logger.info("Hard Live Serper Request Cap: %d", benchmark_budget_cap)
    logger.info("=================================================================")

    start_benchmark_time = time.time()
    
    # Configure benchmark run budget cap
    serper_budget_manager.set_benchmark_run_budget(benchmark_budget_cap)

    telemetry_start = serper_budget_manager.get_telemetry()
    initial_live_requests = telemetry_start["live_requests_today"]
    initial_cache_hits = telemetry_start["cache_hits_today"]

    all_records: List[Dict[str, Any]] = []

    for idx, comp in enumerate(TARGET_8_BLIND_COMPANIES):
        current_live_used = serper_budget_manager.live_requests_today - initial_live_requests
        if current_live_used >= benchmark_budget_cap:
            logger.warning(
                "Benchmark live Serper budget cap reached: %d/%d used. Halting further live queries.",
                current_live_used,
                benchmark_budget_cap,
            )
            break

        rec = run_fully_blind_benchmark_for_company(comp, initial_live_requests)
        all_records.append(rec)
        # Sleep briefly between companies
        time.sleep(1.0)

    total_runtime_sec = round(time.time() - start_benchmark_time, 2)
    telemetry_end = serper_budget_manager.get_telemetry()
    total_live_requests = telemetry_end["live_requests_today"] - initial_live_requests
    total_cache_hits = telemetry_end["cache_hits_today"] - initial_cache_hits

    # Cleanly remove the benchmark cap
    serper_budget_manager.set_benchmark_run_budget(None)

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
    hold_facility_mismatch = sum(1 for r in all_records if r["status"] == "HOLD_FACILITY_MISMATCH")
    hold_person_contradicted = sum(1 for r in all_records if r["status"] == "HOLD_PERSON_CONTRADICTED")
    hold_trigger_weak = sum(1 for r in all_records if r["status"] == "HOLD_TRIGGER_WEAK")
    hold_trigger_stale = sum(1 for r in all_records if r["status"] == "HOLD_TRIGGER_STALE")
    hold_research = sum(1 for r in all_records if r["status"] == "HOLD_RESEARCH")

    valid_triggers_found = sum(1 for r in all_records if r["trigger_is_valid"])
    exact_facilities_discovered = sum(1 for r in all_records if r["discovered_city"])
    triggers_tied_to_facility = sum(1 for r in all_records if r["facility_relationship"] in ("DIRECT", "STRONG"))
    people_found = sum(1 for r in all_records if r["top_person"])
    people_strictly_verified = sum(
        1 for r in all_records
        if r["top_person"] and r["top_person"]["current_employment"] == "VERIFIED" and r["top_person"]["facility_relationship"] in ("FACILITY_OWNER", "GROUP_FUNCTION_OWNER")
    )

    summary = {
        "metadata": {
            "benchmark_name": "FULLY_BLIND_PRODUCTION_BENCHMARK",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "companies_evaluated": len(all_records),
            "total_runtime_sec": total_runtime_sec,
            "avg_duration_sec": avg_duration,
            "median_duration_sec": median_duration,
            "slowest_company": f"{slowest_record.get('company')} ({slowest_record.get('research_duration_sec')}s)",
            "fastest_company": f"{fastest_record.get('company')} ({fastest_record.get('research_duration_sec')}s)",
            "total_serper_live_requests": total_live_requests,
            "total_cache_hits": total_cache_hits,
            "benchmark_budget_cap": benchmark_budget_cap,
            "cap_overshot": total_live_requests > benchmark_budget_cap,
        },
        "forensic_truth_metrics": {
            "valid_triggers_found": valid_triggers_found,
            "exact_facilities_discovered": exact_facilities_discovered,
            "triggers_tied_to_facility": triggers_tied_to_facility,
            "people_discovered": people_found,
            "people_strictly_verified": people_strictly_verified,
            "ready_for_contact_enrichment": ready_for_enrichment,
        },
        "quality_distribution": {
            "P1": p1_count,
            "P2": p2_count,
            "P3": p3_count,
            "HOLD": hold_count,
            "READY_FOR_CONTACT_ENRICHMENT": ready_for_enrichment,
            "HOLD_PERSON_UNCERTAIN": hold_person_uncertain,
            "HOLD_FACILITY_AMBIGUOUS": hold_facility_ambiguous,
            "HOLD_FACILITY_MISMATCH": hold_facility_mismatch,
            "HOLD_PERSON_CONTRADICTED": hold_person_contradicted,
            "HOLD_TRIGGER_WEAK": hold_trigger_weak,
            "HOLD_TRIGGER_STALE": hold_trigger_stale,
            "HOLD_RESEARCH": hold_research,
        },
        "records": all_records,
    }

    os.makedirs(os.path.dirname(BENCHMARK_RESULTS_PATH), exist_ok=True)
    with open(BENCHMARK_RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    logger.info("Saved fully blind benchmark results to: %s", BENCHMARK_RESULTS_PATH)
    return summary


if __name__ == "__main__":
    run_fully_blind_benchmark()
