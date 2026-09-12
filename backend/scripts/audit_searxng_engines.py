"""SearXNG Search Engine Health Audit Script.

Tests individual search engines configured in SearXNG to measure:
- Availability (live vs dead)
- Average latency
- Results per query
- Rate limits / 429s / timeouts
- Useful industrial capex/commissioning hits
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from typing import Any, Dict, List
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from services.research_provider import research_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("searxng_audit")

# Engines to audit
ENGINES_TO_AUDIT = [
    "bing",
    "bing news",
    "yandex",
    "google",
    "duckduckgo",
    "yahoo",
    "qwant",
]

# Benchmark queries for industrial intelligence
TEST_QUERIES = [
    'Maruti Suzuki Hansalpur plant Gujarat "commercial production"',
    'Dixon Technologies Oragadam plant "manufacturing"',
    'Tata Electronics Hosur plant "expansion"',
    'JSW Steel Vijayanagar "commissioned"',
]

USEFUL_PATTERNS = [
    re.compile(r"\b(?:commission(?:ed|ing)|commercial production|new plant|capacity expansion|capex|manufacturing)\b", re.I)
]


def audit_searxng_engines() -> List[Dict[str, Any]]:
    # 1. Resolve base URL from research_router
    searxng_base = research_router.get_searxng_base_url()
    if not searxng_base:
        logger.error("No active SearXNG instance found!")
        return []

    logger.info(f"Auditing SearXNG engines via endpoint: {searxng_base}")


    engine_stats = []

    for engine in ENGINES_TO_AUDIT:
        stat = {
            "engine": engine,
            "enabled": True,
            "live": False,
            "queries_tested": len(TEST_QUERIES),
            "successful_queries": 0,
            "total_results": 0,
            "useful_trigger_hits": 0,
            "errors": 0,
            "rate_limits": 0,
            "timeouts": 0,
            "avg_latency_sec": 0.0,
        }

        latencies = []
        for q in TEST_QUERIES:
            params = {
                "q": q,
                "format": "json",
                "engines": engine,
                "language": "en-IN",
            }
            t0 = time.time()
            try:
                resp = requests.get(f"{searxng_base}/search", params=params, timeout=8)
                elapsed = time.time() - t0
                latencies.append(elapsed)

                if resp.status_code == 200:
                    stat["successful_queries"] += 1
                    data = resp.json()
                    res_list = data.get("results", [])
                    stat["total_results"] += len(res_list)

                    for item in res_list:
                        combo = f"{item.get('title', '')} {item.get('content', '')}"
                        if any(p.search(combo) for p in USEFUL_PATTERNS):
                            stat["useful_trigger_hits"] += 1

                    if res_list:
                        stat["live"] = True
                elif resp.status_code == 429:
                    stat["rate_limits"] += 1
                    stat["errors"] += 1
                else:
                    stat["errors"] += 1

            except requests.exceptions.Timeout:
                stat["timeouts"] += 1
                stat["errors"] += 1
            except Exception as e:
                stat["errors"] += 1

        stat["avg_latency_sec"] = round(sum(latencies) / max(1, len(latencies)), 3)
        if stat["successful_queries"] > 0 and stat["total_results"] > 0:
            stat["live"] = True

        engine_stats.append(stat)
        logger.info(
            f"Engine: {engine:<12} | Live: {str(stat['live']):<5} | Results: {stat['total_results']:<3} | "
            f"Useful Hits: {stat['useful_trigger_hits']:<3} | Errors: {stat['errors']} | Latency: {stat['avg_latency_sec']}s"
        )

    out_file = os.path.join(os.path.dirname(__file__), "..", "data", "runtime_state", "searxng_engine_audit.json")
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(engine_stats, f, indent=2)

    logger.info(f"Engine audit report saved to {out_file}")
    return engine_stats


if __name__ == "__main__":
    audit_searxng_engines()
