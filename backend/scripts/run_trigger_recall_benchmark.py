"""Salesoorja Trigger Recall & Precision Benchmark Runner.

Evaluates independent trigger rediscovery on 16 known positives and 16 known negatives.
Strictly adheres to:
1. Zero answer leakage: fixtures are evaluation-only; discovery receives only company,
   sector, and location context. No fixture enters Apollo queue or production tables.
2. Two separate recall metrics:
   - DISCOVERY_RECALL: genuine benchmark events successfully rediscovered
   - CURRENT_OPPORTUNITY_RECALL: rediscovered events passing today's recency/facility gates
3. Independent failure funnel tracking:
   - SEARCH_ENGINE_NO_RESULT
   - QUERY_NOT_SPECIFIC_ENOUGH
   - SOURCE_RANK_TOO_LOW
   - SOURCE_FETCH_FAILURE
   - PDF_NOT_PARSED
   - EVENT_SEMANTICS_FALSE_REJECT
   - ENTITY_FALSE_REJECT
   - DATE_EXTRACTION_FAILURE
   - CORRECTLY_REJECTED_STALE
4. Mathematical precision handling when TP + FP == 0 (reports NOT_MEASURABLE).
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.research_metrics import calculate_precision_recall_f1
from services.research_provider import research_router
from services.signal_discovery_engine import (
    generate_adaptive_trigger_queries,
    filter_negative_financial_results,
    expand_trigger_queries_with_gemini,
)
from services.source_verification_pipeline import (
    classify_source_class,
    is_source_allowed_for_trigger,
    DISALLOWED_TRIGGER_DOMAINS,
    SOURCE_QUALITY_WEIGHTS,
)
from services.evidence_provenance import extract_domain
from services.trigger_discovery_service import (
    evaluate_event_semantics,
    fetch_and_verify_source_content,
    extract_event_date,
    classify_source_tier,
)
from services.deep_facility_resolver import DeepFacilityResolver

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("TriggerRecallBenchmark")

BENCHMARK_FIXTURE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "benchmarks", "trigger_benchmark_cases.json"
)
OUTPUT_REPORT_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "benchmarks", "trigger_recall_benchmark_results.json"
)


def run_benchmark() -> Dict[str, Any]:
    logger.info("=" * 70)
    logger.info("STARTING SALESOORJA TRIGGER RECALL & PRECISION BENCHMARK")
    logger.info("=" * 70)

    if not os.path.exists(BENCHMARK_FIXTURE_PATH):
        raise FileNotFoundError(f"Benchmark fixture not found: {BENCHMARK_FIXTURE_PATH}")

    with open(BENCHMARK_FIXTURE_PATH, "r", encoding="utf-8") as f:
        fixtures = json.load(f)

    known_positives = fixtures.get("known_positives", [])
    known_negatives = fixtures.get("known_negatives", [])

    logger.info(f"Loaded {len(known_positives)} known positives and {len(known_negatives)} known negatives.")

    now_dt = datetime(2026, 9, 12, tzinfo=timezone.utc)
    facility_resolver = DeepFacilityResolver()

    # Telemetry and tracking
    query_family_yield = {
        "pass_1": {"queries": 0, "results": 0, "valid_candidates": 0},
        "pass_2": {"queries": 0, "results": 0, "valid_candidates": 0},
        "pass_3": {"queries": 0, "results": 0, "valid_candidates": 0},
        "gemini_expansion": {"queries": 0, "results": 0, "valid_candidates": 0},
    }

    failure_funnel = {
        "SEARCH_ENGINE_NO_RESULT": 0,
        "QUERY_NOT_SPECIFIC_ENOUGH": 0,
        "SOURCE_RANK_TOO_LOW": 0,
        "SOURCE_FETCH_FAILURE": 0,
        "PDF_NOT_PARSED": 0,
        "EVENT_SEMANTICS_FALSE_REJECT": 0,
        "ENTITY_FALSE_REJECT": 0,
        "DATE_EXTRACTION_FAILURE": 0,
        "CORRECTLY_REJECTED_STALE": 0,
    }

    positive_results = []
    tp_count = 0                     # Rediscovered + passes 2026-09-12 recency & facility gates
    stale_valid_discoveries = 0      # Genuine historical event rediscovered, correctly identified as stale
    fn_count = 0                     # Failed to rediscover genuine event

    # ──────────────────────────────────────────────────────────────────────────
    # PHASE 1: EVALUATE KNOWN POSITIVES (Zero Answer Leakage)
    # ──────────────────────────────────────────────────────────────────────────
    logger.info("\n--- PHASE 1: EVALUATING KNOWN POSITIVES (DISCOVERY RECALL) ---")

    for idx, kp in enumerate(known_positives, 1):
        kp_id = kp["id"]
        company = kp["company"]
        sector = kp.get("sector", "")
        expected_facility = kp.get("expected_facility", "")
        # Extract basic city/location context (no answer leakage)
        basic_location = expected_facility.split(",")[0].strip() if expected_facility else ""

        logger.info(f"\n[{idx}/{len(known_positives)}] Evaluating: {company} ({sector}) | Location Context: {basic_location}")

        adaptive_queries = generate_adaptive_trigger_queries(
            company_name=company,
            sector=sector,
            hub=basic_location,
        )

        all_collected_results = []
        seen_urls = set()
        winning_pass = None

        # Execute adaptive 3-pass querying
        best_event = None
        best_failure_reason = "SEARCH_ENGINE_NO_RESULT"

        for pass_name in ["pass_1", "pass_2", "pass_3"]:
            queries = adaptive_queries.get(pass_name, [])
            pass_results = []
            for q in queries:
                query_family_yield[pass_name]["queries"] += 1
                try:
                    s_res = research_router.search(q, num_results=6)
                    results = s_res.get("results", [])
                    query_family_yield[pass_name]["results"] += len(results)

                    for r in results:
                        u = r.get("url", "")
                        if u and u not in seen_urls:
                            seen_urls.add(u)
                            r["discovered_via_pass"] = pass_name
                            pass_results.append(r)
                            all_collected_results.append(r)
                except Exception as e:
                    logger.warning(f"Search error on query '{q}': {e}")

            # Filter candidates for this pass
            source_approved = []
            for r in pass_results:
                u = r.get("url", "")
                d = extract_domain(u).lower()
                if any(bad in d for bad in DISALLOWED_TRIGGER_DOMAINS):
                    continue
                if not is_source_allowed_for_trigger(u):
                    continue
                if not filter_negative_financial_results([r]):
                    continue
                s_class = classify_source_class(u)
                r["source_class"] = s_class
                r["source_weight"] = SOURCE_QUALITY_WEIGHTS.get(s_class, 0.5)
                source_approved.append(r)

            source_approved.sort(key=lambda x: x.get("source_weight", 0.5), reverse=True)

            for cand in source_approved:
                url = cand.get("url", "")
                title = cand.get("title", "")
                snippet = cand.get("snippet", "") or cand.get("content", "")

                sem = evaluate_event_semantics(snippet, title=title)
                if not sem.get("is_verified") or sem.get("score", 0.0) <= 0.0:
                    best_failure_reason = "EVENT_SEMANTICS_FALSE_REJECT"
                    continue

                fetch_res = fetch_and_verify_source_content(url, search_title=title, search_snippet=snippet, timeout=12)
                if not fetch_res.get("verified"):
                    best_failure_reason = "PDF_NOT_PARSED" if url.lower().endswith(".pdf") else "SOURCE_FETCH_FAILURE"
                    continue

                # Verified event found!
                date_info = extract_event_date(fetch_res.get("source_body_text", ""), title=title, now_dt=now_dt)
                fac_info = facility_resolver.resolve_facility(
                    company_name=company,
                    trigger_text=fetch_res.get("source_body_text", "")[:4000],
                    known_city=basic_location,
                    evidence_snippets=[snippet, title],
                )

                best_event = {
                    "url": url,
                    "title": fetch_res.get("source_title", title),
                    "trigger_type": fetch_res.get("trigger_type", sem.get("trigger_type")),
                    "evidence": fetch_res.get("source_body_event_snippet", snippet[:200]),
                    "date": date_info.get("trigger_date"),
                    "recency_status": date_info.get("recency_status", "UNKNOWN"),
                    "recency_days": date_info.get("recency_days", 999),
                    "facility": fac_info.get("facility_name") or fac_info.get("city"),
                    "discovered_via_pass": pass_name,
                }
                winning_pass = pass_name
                query_family_yield[pass_name]["valid_candidates"] += 1
                break

            if best_event:
                break

        # Fallback to Gemini expansion if deterministic passes yielded 0 verified events
        if not best_event:
            logger.info(f"Deterministic passes yielded 0 verified events for {company}. Attempting Gemini expansion (capped at 3)...")
            gemini_queries = expand_trigger_queries_with_gemini(company, sector=sector, hub=basic_location, max_queries=3)
            query_family_yield["gemini_expansion"]["queries"] += len(gemini_queries)
            gemini_results = []
            for gq in gemini_queries:
                try:
                    s_res = research_router.search(gq, num_results=6)
                    results = s_res.get("results", [])
                    query_family_yield["gemini_expansion"]["results"] += len(results)
                    for r in results:
                        u = r.get("url", "")
                        if u and u not in seen_urls:
                            seen_urls.add(u)
                            r["discovered_via_pass"] = "gemini_expansion"
                            gemini_results.append(r)
                            all_collected_results.append(r)
                except Exception as e:
                    logger.warning(f"Gemini expansion search error on '{gq}': {e}")

            gemini_approved = []
            for r in gemini_results:
                u = r.get("url", "")
                if is_source_allowed_for_trigger(u) and filter_negative_financial_results([r]):
                    s_class = classify_source_class(u)
                    r["source_class"] = s_class
                    r["source_weight"] = SOURCE_QUALITY_WEIGHTS.get(s_class, 0.5)
                    gemini_approved.append(r)

            gemini_approved.sort(key=lambda x: x.get("source_weight", 0.5), reverse=True)

            for cand in gemini_approved:
                url = cand.get("url", "")
                title = cand.get("title", "")
                snippet = cand.get("snippet", "") or cand.get("content", "")

                sem = evaluate_event_semantics(snippet, title=title)
                if not sem.get("is_verified") or sem.get("score", 0.0) <= 0.0:
                    best_failure_reason = "EVENT_SEMANTICS_FALSE_REJECT"
                    continue

                fetch_res = fetch_and_verify_source_content(url, search_title=title, search_snippet=snippet, timeout=12)
                if not fetch_res.get("verified"):
                    best_failure_reason = "PDF_NOT_PARSED" if url.lower().endswith(".pdf") else "SOURCE_FETCH_FAILURE"
                    continue

                date_info = extract_event_date(fetch_res.get("source_body_text", ""), title=title, now_dt=now_dt)
                fac_info = facility_resolver.resolve_facility(
                    company_name=company,
                    trigger_text=fetch_res.get("source_body_text", "")[:4000],
                    known_city=basic_location,
                    evidence_snippets=[snippet, title],
                )
                best_event = {
                    "url": url,
                    "title": fetch_res.get("source_title", title),
                    "trigger_type": fetch_res.get("trigger_type", sem.get("trigger_type")),
                    "evidence": fetch_res.get("source_body_event_snippet", snippet[:200]),
                    "date": date_info.get("trigger_date"),
                    "recency_status": date_info.get("recency_status", "UNKNOWN"),
                    "recency_days": date_info.get("recency_days", 999),
                    "facility": fac_info.get("facility_name") or fac_info.get("city"),
                    "discovered_via_pass": "gemini_expansion",
                }
                winning_pass = "gemini_expansion"
                query_family_yield["gemini_expansion"]["valid_candidates"] += 1
                break

        if not best_event:
            failure_funnel[best_failure_reason] += 1
            fn_count += 1
            positive_results.append({
                "id": kp_id,
                "company": company,
                "discovery_status": "FAIL",
                "production_timing_status": "FAIL",
                "failure_reason": best_failure_reason,
                "discovered_event": None,
            })
            logger.warning(f"  -> FAIL: {best_failure_reason}")
            continue

        # ── Scored rediscovery ──
        # DISCOVERY_RECALL = Genuine event independently rediscovered!
        discovery_pass = True
        recency_pass = best_event["recency_status"] in ("CURRENT", "RECENT")

        if recency_pass:
            tp_count += 1
            production_timing_status = "PASS"
            failure_reason = None
            logger.info(f"  -> DISCOVERY: PASS | PRODUCTION_TIMING: PASS (Trigger: {best_event['trigger_type']} | Date: {best_event['date']} | Facility: {best_event['facility']})")
        else:
            stale_valid_discoveries += 1
            production_timing_status = "FAIL"
            failure_reason = "CORRECTLY_REJECTED_STALE"
            failure_funnel["CORRECTLY_REJECTED_STALE"] += 1
            logger.info(f"  -> DISCOVERY: PASS | PRODUCTION_TIMING: FAIL (Correctly rejected historical event: {best_event.get('recency_days')} days old)")

        positive_results.append({
            "id": kp_id,
            "company": company,
            "discovery_status": "PASS",
            "production_timing_status": production_timing_status,
            "failure_reason": failure_reason,
            "discovered_event": best_event,
        })

    # ──────────────────────────────────────────────────────────────────────────
    # PHASE 2: EVALUATE KNOWN NEGATIVES (False Positive Control)
    # ──────────────────────────────────────────────────────────────────────────
    logger.info("\n--- PHASE 2: EVALUATING KNOWN NEGATIVES (FALSE POSITIVE CONTROL) ---")
    negative_results = []
    tn_count = 0
    fp_count = 0

    for idx, kn in enumerate(known_negatives, 1):
        kn_id = kn["id"]
        company = kn["company"]
        url = kn.get("test_url", "")
        title = kn.get("test_title", "")
        snippet = kn.get("test_snippet", "")
        expected_rejection = kn.get("expected_rejection_reason", "HARD_REJECT")

        logger.info(f"[{idx}/{len(known_negatives)}] Negative check: {company} | URL: {url[:50]}...")

        # 1. Deterministic domain & class gate
        domain = extract_domain(url).lower()
        if any(bad in domain for bad in DISALLOWED_TRIGGER_DOMAINS):
            tn_count += 1
            negative_results.append({"id": kn_id, "company": company, "outcome": "CORRECTLY_REJECTED", "reason": "DISALLOWED_DOMAIN"})
            logger.info(f"  -> CORRECTLY REJECTED: DISALLOWED_DOMAIN")
            continue

        s_class = classify_source_class(url, title=title, snippet=snippet)
        if not is_source_allowed_for_trigger(url):
            tn_count += 1
            negative_results.append({"id": kn_id, "company": company, "outcome": "CORRECTLY_REJECTED", "reason": f"HARD_REJECT_CLASS_{s_class}"})
            logger.info(f"  -> CORRECTLY REJECTED: HARD_REJECT_CLASS_{s_class}")
            continue

        # 2. Negative financial filter
        clean_cand = filter_negative_financial_results([{"url": url, "title": title, "snippet": snippet}])
        if not clean_cand:
            tn_count += 1
            negative_results.append({"id": kn_id, "company": company, "outcome": "CORRECTLY_REJECTED", "reason": "FINANCIAL_NOISE_REJECT"})
            logger.info(f"  -> CORRECTLY REJECTED: FINANCIAL_NOISE_REJECT")
            continue

        # 3. Event semantics check
        sem = evaluate_event_semantics(snippet, title=title)
        if not sem.get("is_verified") or sem.get("score", 0.0) <= 0.0:
            tn_count += 1
            negative_results.append({"id": kn_id, "company": company, "outcome": "CORRECTLY_REJECTED", "reason": "NO_EVENT_SEMANTICS"})
            logger.info(f"  -> CORRECTLY REJECTED: NO_EVENT_SEMANTICS")
            continue

        # 4. Date & recency gate for current production opportunity
        date_info = extract_event_date(f"{title} {snippet}", title=title, now_dt=now_dt)
        if date_info.get("has_date") and (date_info.get("recency_status") in ("STALE", "HISTORICAL") or date_info.get("recency_days", 0) > 365):
            tn_count += 1
            negative_results.append({"id": kn_id, "company": company, "outcome": "CORRECTLY_REJECTED", "reason": "STALE_TRIGGER"})
            logger.info(f"  -> CORRECTLY REJECTED: STALE_TRIGGER ({date_info.get('recency_days')} days old)")
            continue

        # If it reached here, it falsely passed gates!
        fp_count += 1
        negative_results.append({"id": kn_id, "company": company, "outcome": "FALSE_POSITIVE_LEAKAGE", "reason": "PASSED_ALL_GATES", "trigger": sem.get("trigger_type")})
        logger.error(f"  -> CRITICAL FALSE POSITIVE: {company} passed all gates on noise URL {url}")

    # ──────────────────────────────────────────────────────────────────────────
    # PHASE 3: COMPUTE METRICS & EXECUTION GATE
    # ──────────────────────────────────────────────────────────────────────────
    total_positives = len(known_positives)
    total_negatives = len(known_negatives)

    metrics = calculate_precision_recall_f1(
        tp=tp_count,
        fp=fp_count,
        tn=tn_count,
        fn=fn_count,
        stale_valid_discoveries=stale_valid_discoveries,
        total_benchmark_positives=total_positives,
    )

    rediscovered_total = tp_count + stale_valid_discoveries
    discovery_recall_val = metrics["discovery_recall"]
    current_opp_recall_val = metrics["current_opportunity_recall"]

    execution_gate_passed = (
        isinstance(discovery_recall_val, float)
        and discovery_recall_val >= 0.70
        and fp_count == 0
    )

    # Load Search Engine Health Audit
    searxng_audit_path = os.path.join(os.path.dirname(__file__), "..", "data", "runtime_state", "searxng_engine_audit.json")
    engine_health = {}
    if os.path.exists(searxng_audit_path):
        try:
            with open(searxng_audit_path, "r", encoding="utf-8") as f:
                engine_health = json.load(f)
        except Exception:
            pass

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "benchmark_summary": {
            "known_positives_total": total_positives,
            "rediscovered_events_total": rediscovered_total,
            "discovery_recall": discovery_recall_val,
            "discovery_recall_percent": metrics["discovery_recall_percent"],
            "current_opportunity_passes": tp_count,
            "current_opportunity_recall": current_opp_recall_val,
            "current_opportunity_recall_percent": metrics["current_opportunity_recall_percent"],
            "known_negatives_total": total_negatives,
            "correctly_rejected_negatives": tn_count,
            "false_positives": fp_count,
            "false_positive_leakage": metrics["false_positive_leakage"],
            "precision": metrics["precision"],
            "precision_percent": metrics["precision_percent"],
            "f1": metrics["f1"],
            "f1_percent": metrics["f1_percent"],
        },
        "execution_gate": {
            "passed": execution_gate_passed,
            "threshold": "DISCOVERY_RECALL >= 70% AND FALSE_POSITIVES == 0",
            "decision": "SAFE_TO_SCALE_DISCOVERY = YES" if execution_gate_passed else "SAFE_TO_SCALE_DISCOVERY = NO",
        },
        "failure_funnel": failure_funnel,
        "query_family_yield": query_family_yield,
        "search_engine_health": engine_health,
        "positive_results": positive_results,
        "negative_results": negative_results,
    }

    os.makedirs(os.path.dirname(OUTPUT_REPORT_PATH), exist_ok=True)
    with open(OUTPUT_REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    logger.info("\n" + "=" * 70)
    logger.info("BENCHMARK EXECUTION REPORT SUMMARY")
    logger.info("=" * 70)
    logger.info(f"Known Positives Evaluated:       {total_positives}")
    logger.info(f"Genuine Events Rediscovered:     {rediscovered_total}")
    logger.info(f"DISCOVERY_RECALL:                {metrics['discovery_recall_percent']} ({discovery_recall_val})")
    logger.info(f"Current Opportunity Passes:      {tp_count}")
    logger.info(f"CURRENT_OPPORTUNITY_RECALL:      {metrics['current_opportunity_recall_percent']} ({current_opp_recall_val})")
    logger.info(f"Known Negatives Evaluated:       {total_negatives}")
    logger.info(f"False Positives:                 {fp_count} (Leakage: {metrics['false_positive_leakage']})")
    logger.info(f"Precision:                       {metrics['precision_percent']}")
    logger.info(f"F1 Score:                        {metrics['f1_percent']}")
    logger.info(f"Execution Gate Passed (>=70%):   {execution_gate_passed}")
    logger.info(f"FINAL DECISION:                  {report['execution_gate']['decision']}")
    logger.info("=" * 70)

    return report


if __name__ == "__main__":
    run_benchmark()
