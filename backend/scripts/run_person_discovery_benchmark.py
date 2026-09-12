"""Run the evaluation-only person benchmark with optional Hive/DeepSeek assistance."""
import argparse
import io
import json
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BACKEND_DIR)

from services.person_intelligence_service import discover_and_rank_decision_makers


BENCHMARK_PATH = os.path.join(BACKEND_DIR, "data", "benchmarks", "person_benchmark_cases.json")
BASELINE_PATH = os.path.join(BACKEND_DIR, "data", "runtime_state", "person_benchmark_results.json")
ASSISTED_PATH = os.path.join(BACKEND_DIR, "data", "runtime_state", "person_benchmark_deepseek_results.json")
MAX_HIVE_REQUESTS = 20


def normalize_person_name(name: str) -> str:
    tokens = re.findall(r"[a-z]+", (name or "").lower())
    return " ".join(token for token in tokens if token not in {"dr", "mr", "mrs", "ms", "shri", "smt"})


def find_expected_candidate(candidates: List[Dict[str, Any]], expected_person: str) -> tuple[int, Dict[str, Any] | None]:
    expected_key = normalize_person_name(expected_person)
    for index, candidate in enumerate(candidates):
        if normalize_person_name(str(candidate.get("name") or "")) == expected_key:
            return index, candidate
    return -1, None


def evaluate_cases(cases: List[Dict[str, Any]], *, use_deepseek: bool) -> Dict[str, Any]:
    metrics = {
        "KNOWN_CASES": len(cases),
        "PERSON_FOUND": 0,
        "CORRECT_TOP1": 0,
        "CORRECT_TOP3": 0,
        "CURRENT_EMPLOYMENT_VERIFIED": 0,
        "FACILITY_LINK_VERIFIED": 0,
        "HIGH_CONFIDENCE_PERSON": 0,
    }
    usage = {"requests": 0, "input_tokens": 0, "output_tokens": 0}
    case_results = []

    for case in cases:
        discovery = discover_and_rank_decision_makers(
            company_name=case["company"],
            facility_name=case.get("facility", ""),
            city=case.get("city", ""),
            max_candidates=5,
            use_deepseek=use_deepseek,
            commercial_trigger=case.get("function_context", ""),
            target_functions=[case.get("function_context", "Plant Quality")],
        )
        candidates = discovery.get("candidates", [])
        telemetry = discovery.get("telemetry", {})
        usage["requests"] += int(telemetry.get("hive_requests", 0) or 0)
        usage["input_tokens"] += int(telemetry.get("hive_input_tokens", 0) or 0)
        usage["output_tokens"] += int(telemetry.get("hive_output_tokens", 0) or 0)
        if usage["requests"] > MAX_HIVE_REQUESTS:
            raise RuntimeError(f"Hive benchmark request cap exceeded: {usage['requests']} > {MAX_HIVE_REQUESTS}")

        rank_index, matched = find_expected_candidate(candidates, case["expected_person"])
        if matched is not None:
            metrics["PERSON_FOUND"] += 1
            if rank_index == 0:
                metrics["CORRECT_TOP1"] += 1
            if rank_index < 3:
                metrics["CORRECT_TOP3"] += 1
            if matched.get("current_employment") == "VERIFIED":
                metrics["CURRENT_EMPLOYMENT_VERIFIED"] += 1
            if matched.get("facility_relationship") in {"FACILITY_OWNER", "FACILITY_FUNCTION_OWNER", "GROUP_FUNCTION_OWNER"}:
                metrics["FACILITY_LINK_VERIFIED"] += 1
            if matched.get("person_confidence") == "HIGH":
                metrics["HIGH_CONFIDENCE_PERSON"] += 1

        case_results.append({
            "case_id": case["id"],
            "company": case["company"],
            "expected_person": case["expected_person"],
            "found": matched is not None,
            "rank": rank_index + 1 if matched is not None else None,
            "matched_candidate": matched,
            "top_candidate": candidates[0] if candidates else None,
            "total_candidates": len(candidates),
            "telemetry": telemetry,
        })

    total = metrics["KNOWN_CASES"]
    metrics.update({
        "PERSON_DISCOVERY_RECALL": metrics["PERSON_FOUND"] / total * 100 if total else 0.0,
        "TOP1_ACCURACY": metrics["CORRECT_TOP1"] / total * 100 if total else 0.0,
        "TOP3_RECALL": metrics["CORRECT_TOP3"] / total * 100 if total else 0.0,
        "HIGH_CONFIDENCE_RATE": metrics["HIGH_CONFIDENCE_PERSON"] / total * 100 if total else 0.0,
    })
    return {"metrics": metrics, "hive_usage": usage, "case_results": case_results}


def load_prior_baseline() -> Dict[str, Any] | None:
    if not os.path.exists(BASELINE_PATH):
        return None
    with open(BASELINE_PATH, "r", encoding="utf-8") as baseline_file:
        baseline = json.load(baseline_file)
    metrics = baseline.get("metrics", {})
    if "KNOWN_CASES" in metrics:
        return baseline

    case_results = baseline.get("case_results", [])
    corrected = {
        "KNOWN_CASES": len(case_results),
        "PERSON_FOUND": 0,
        "CORRECT_TOP1": 0,
        "CORRECT_TOP3": 0,
        "CURRENT_EMPLOYMENT_VERIFIED": 0,
        "FACILITY_LINK_VERIFIED": 0,
        "HIGH_CONFIDENCE_PERSON": 0,
    }
    for case in case_results:
        matched = case.get("matched_candidate")
        if not matched or normalize_person_name(matched.get("name", "")) != normalize_person_name(case.get("expected_person", "")):
            continue
        corrected["PERSON_FOUND"] += 1
        rank = case.get("rank")
        top_candidate = case.get("top_candidate") or {}
        if rank is None and normalize_person_name(top_candidate.get("name", "")) == normalize_person_name(case.get("expected_person", "")):
            rank = 1
        if rank == 1:
            corrected["CORRECT_TOP1"] += 1
        if rank is not None and rank <= 3:
            corrected["CORRECT_TOP3"] += 1
        if matched.get("current_employment") == "VERIFIED":
            corrected["CURRENT_EMPLOYMENT_VERIFIED"] += 1
        if matched.get("facility_relationship") in {"FACILITY_OWNER", "FACILITY_FUNCTION_OWNER", "GROUP_FUNCTION_OWNER"}:
            corrected["FACILITY_LINK_VERIFIED"] += 1
        if matched.get("person_confidence") == "HIGH":
            corrected["HIGH_CONFIDENCE_PERSON"] += 1

    total = corrected["KNOWN_CASES"]
    corrected.update({
        "PERSON_DISCOVERY_RECALL": corrected["PERSON_FOUND"] / total * 100 if total else 0.0,
        "TOP1_ACCURACY": corrected["CORRECT_TOP1"] / total * 100 if total else 0.0,
        "TOP3_RECALL": corrected["CORRECT_TOP3"] / total * 100 if total else 0.0,
        "HIGH_CONFIDENCE_RATE": corrected["HIGH_CONFIDENCE_PERSON"] / total * 100 if total else 0.0,
    })
    baseline["legacy_metrics"] = metrics
    baseline["metrics"] = corrected
    baseline["baseline_note"] = "Legacy substring name matching was corrected to exact normalized full-name matching."
    return baseline


def run_benchmark(mode: str = "deepseek") -> Dict[str, Any]:
    with open(BENCHMARK_PATH, "r", encoding="utf-8") as benchmark_file:
        cases = json.load(benchmark_file)

    prior_baseline = load_prior_baseline()
    result = evaluate_cases(cases, use_deepseek=mode == "deepseek")
    result["timestamp"] = datetime.now(timezone.utc).isoformat()
    result["mode"] = mode
    if mode == "deepseek":
        result["baseline"] = prior_baseline.get("metrics", {}) if prior_baseline else None
        output_path = ASSISTED_PATH
    else:
        output_path = BASELINE_PATH

    with open(output_path, "w", encoding="utf-8") as output_file:
        json.dump(result, output_file, indent=2)

    print(json.dumps({
        "mode": mode,
        "metrics": result["metrics"],
        "hive_usage": result["hive_usage"],
        "output_path": output_path,
    }, indent=2))
    return result


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("baseline", "deepseek"), default="deepseek")
    arguments = parser.parse_args()
    run_benchmark(arguments.mode)
