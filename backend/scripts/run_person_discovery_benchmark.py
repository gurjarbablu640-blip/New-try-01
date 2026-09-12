"""Run the frozen five-case person benchmark with a strict Hive request budget."""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BACKEND_DIR)

from config import settings
from services.person_intelligence_service import discover_and_rank_decision_makers


BENCHMARK_PATH = os.path.join(BACKEND_DIR, "data", "benchmarks", "person_benchmark_cases.json")
BASELINE_PATH = os.path.join(BACKEND_DIR, "data", "runtime_state", "person_benchmark_results.json")
ASSISTED_PATH = os.path.join(BACKEND_DIR, "data", "runtime_state", "person_benchmark_deepseek_results.json")
MAX_HIVE_REQUESTS = 10
KNOWN_PERSON_ALIASES: Dict[str, set[str]] = {}
VALID_FACILITY_RELATIONSHIPS = {"FACILITY_OWNER", "FACILITY_FUNCTION_OWNER", "GROUP_FUNCTION_OWNER"}
VALID_FUNCTION_AUTHORITIES = {
    "DIRECT_CALIBRATION_OWNER",
    "METROLOGY_OWNER",
    "STRONG_PLANT_QUALITY_OWNER",
    "FACILITY_OWNER",
    "GROUP_FUNCTION_OWNER",
}


class HiveRequestBudgetExceeded(RuntimeError):
    """Raised before a Hive request would exceed the benchmark limit."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json_atomic(path: str, payload: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary_path = f"{path}.tmp"
    with open(temporary_path, "w", encoding="utf-8") as output_file:
        json.dump(payload, output_file, indent=2)
    os.replace(temporary_path, path)


class HiveRequestBudget:
    """Persist exact attempted, successful, failed, token, and cost counters."""

    def __init__(
        self,
        max_requests: int = MAX_HIVE_REQUESTS,
        output_path: Optional[str] = None,
        input_usd_per_million: Optional[float] = None,
        output_usd_per_million: Optional[float] = None,
    ) -> None:
        self.max_requests = int(max_requests)
        self.output_path = output_path
        self.input_usd_per_million = float(
            input_usd_per_million
            if input_usd_per_million is not None
            else settings.HIVE_INPUT_USD_PER_MILLION_TOKENS
        )
        self.output_usd_per_million = float(
            output_usd_per_million
            if output_usd_per_million is not None
            else settings.HIVE_OUTPUT_USD_PER_MILLION_TOKENS
        )
        self.attempted_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.telemetry_complete = True
        self.last_error: Optional[str] = None
        self.checkpoint_data: Dict[str, Any] = {}
        self._persist("RUNNING")

    def reserve_request(self) -> None:
        if self.attempted_requests >= self.max_requests:
            raise HiveRequestBudgetExceeded(
                f"Hive request budget exhausted at {self.max_requests}; request {self.max_requests + 1} was blocked"
            )
        self.attempted_requests += 1
        self._persist("RUNNING")

    def record_success(self, usage: Optional[Dict[str, Any]]) -> None:
        self.successful_requests += 1
        usage_data = usage or {}
        if "input_tokens" not in usage_data or "output_tokens" not in usage_data:
            self.telemetry_complete = False
        self.input_tokens += int(usage_data.get("input_tokens", 0) or 0)
        self.output_tokens += int(usage_data.get("output_tokens", 0) or 0)
        self._persist("RUNNING")

    def record_failure(self, error: Exception) -> None:
        self.failed_requests += 1
        self.last_error = type(error).__name__
        self._persist("RUNNING")

    def snapshot(self) -> Dict[str, Any]:
        estimated_cost: float | str
        if self.successful_requests and not self.telemetry_complete:
            estimated_cost = "NOT_AVAILABLE"
        else:
            estimated_cost = round(
                (self.input_tokens / 1_000_000 * self.input_usd_per_million)
                + (self.output_tokens / 1_000_000 * self.output_usd_per_million),
                8,
            )
        return {
            "max_requests": self.max_requests,
            "attempted_requests": self.attempted_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "input_tokens": self.input_tokens if self.telemetry_complete else "NOT_AVAILABLE",
            "output_tokens": self.output_tokens if self.telemetry_complete else "NOT_AVAILABLE",
            "total_tokens": self.input_tokens + self.output_tokens if self.telemetry_complete else "NOT_AVAILABLE",
            "estimated_usd_cost": estimated_cost,
            "remaining_request_budget": self.max_requests - self.attempted_requests,
            "input_usd_per_million_tokens": self.input_usd_per_million,
            "output_usd_per_million_tokens": self.output_usd_per_million,
            "paid_overage_allowed": False,
            "last_error": self.last_error,
        }

    def persist_status(self, status: str, **extra: Any) -> None:
        self.checkpoint_data.update(extra)
        self._persist(status, **extra)

    def _persist(self, status: str, **extra: Any) -> None:
        if not self.output_path:
            return
        payload = {
            "timestamp": utc_now(),
            "mode": "deepseek",
            "status": status,
            "hive_usage": self.snapshot(),
            **self.checkpoint_data,
            **extra,
        }
        write_json_atomic(self.output_path, payload)


class BudgetedProvider:
    """Count every attempted Hive completion and block request eleven."""

    def __init__(self, provider: Any, budget: HiveRequestBudget) -> None:
        self.provider = provider
        self.budget = budget

    def complete(self, *args: Any, **kwargs: Any) -> Any:
        self.budget.reserve_request()
        try:
            response = self.provider.complete(*args, **kwargs)
        except Exception as error:
            self.budget.record_failure(error)
            raise
        self.budget.record_success(dict(response.usage or {}))
        return response


def normalize_person_name(name: str) -> str:
    tokens = re.findall(r"[a-z]+", (name or "").lower())
    return " ".join(token for token in tokens if token not in {"dr", "mr", "mrs", "ms", "shri", "smt"})


def find_expected_candidate(
    candidates: List[Dict[str, Any]],
    expected_person: str,
    aliases: Optional[Dict[str, set[str]]] = None,
) -> tuple[int, Dict[str, Any] | None]:
    expected_key = normalize_person_name(expected_person)
    alias_registry = aliases if aliases is not None else KNOWN_PERSON_ALIASES
    accepted_names = {expected_key}
    accepted_names.update(normalize_person_name(alias) for alias in alias_registry.get(expected_key, set()))
    for index, candidate in enumerate(candidates):
        if normalize_person_name(str(candidate.get("name") or "")) in accepted_names:
            return index, candidate
    return -1, None


def candidate_summary(candidate: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not candidate:
        return None
    return {
        "name": candidate.get("name"),
        "title": candidate.get("title"),
        "person_score": candidate.get("person_score"),
        "person_confidence": candidate.get("person_confidence"),
        "current_employment": candidate.get("current_employment"),
        "facility_relationship": candidate.get("facility_relationship"),
        "authority_class": candidate.get("authority_class"),
        "source_url": candidate.get("source_url"),
    }


def failure_cause(
    matched: Optional[Dict[str, Any]],
    deterministic_rank: int,
    candidates: List[Dict[str, Any]],
) -> str:
    if matched is None:
        return "SEARCH_COVERAGE_FAILURE" if not candidates else "EXPECTED_PERSON_NOT_DISCOVERED"
    if matched.get("current_employment") != "VERIFIED":
        return "EMPLOYMENT_NOT_VERIFIED"
    if matched.get("facility_relationship") not in VALID_FACILITY_RELATIONSHIPS:
        return "FACILITY_LINK_NOT_VERIFIED"
    if matched.get("authority_class") not in VALID_FUNCTION_AUTHORITIES:
        return "FUNCTION_NOT_VERIFIED"
    if deterministic_rank > 3:
        return "BETTER_WRONG_CANDIDATE_RANKED"
    if matched.get("person_confidence") != "HIGH":
        return "SOURCE_COVERAGE_FAILURE"
    return "NONE"


def evaluate_cases(
    cases: List[Dict[str, Any]],
    *,
    use_deepseek: bool,
    ranking_provider: Any = None,
    search_router: Any = None,
    budget: Optional[HiveRequestBudget] = None,
) -> Dict[str, Any]:
    metrics = {
        "KNOWN_CASES": len(cases),
        "PERSON_FOUND": 0,
        "DEEPSEEK_CORRECT_TOP1": 0,
        "CORRECT_TOP1": 0,
        "CORRECT_TOP3": 0,
        "CORRECT_HIGH_CONFIDENCE": 0,
        "FALSE_HIGH_CONFIDENCE_COUNT": 0,
        "STRUCTURED_RANKING_APPLIED_CASES": 0,
        "STRUCTURED_RANKING_PARSE_FAILURES": 0,
        "HIVE_REQUEST_FAILURE_CASES": 0,
    }
    case_results = []

    for case in cases:
        discovery_kwargs = {
            "company_name": case["company"],
            "facility_name": case.get("facility", ""),
            "city": case.get("city", ""),
            "max_candidates": 20,
            "use_deepseek": use_deepseek,
            "ranking_provider": ranking_provider,
            "commercial_trigger": case.get("function_context", ""),
            "target_functions": [case.get("function_context", "Plant Quality")],
        }
        if search_router is not None:
            discovery_kwargs["search_router"] = search_router
        discovery = discover_and_rank_decision_makers(**discovery_kwargs)
        candidates = discovery.get("candidates", [])
        telemetry = discovery.get("telemetry", {})
        if telemetry.get("deepseek_ranking_applied"):
            metrics["STRUCTURED_RANKING_APPLIED_CASES"] += 1
        elif telemetry.get("deepseek_ranking_error") == "NO_VALID_STRUCTURED_RANKING":
            metrics["STRUCTURED_RANKING_PARSE_FAILURES"] += 1
        elif telemetry.get("deepseek_ranking_error"):
            metrics["HIVE_REQUEST_FAILURE_CASES"] += 1
        deepseek_candidates = sorted(
            [candidate for candidate in candidates if candidate.get("deepseek_rank") is not None],
            key=lambda candidate: int(candidate.get("deepseek_rank") or 9999),
        )

        deterministic_rank_index, matched = find_expected_candidate(candidates, case["expected_person"])
        deepseek_rank_index, _ = find_expected_candidate(deepseek_candidates, case["expected_person"])
        if matched is not None:
            metrics["PERSON_FOUND"] += 1
            if deterministic_rank_index == 0:
                metrics["CORRECT_TOP1"] += 1
            if deterministic_rank_index < 3:
                metrics["CORRECT_TOP3"] += 1
            if matched.get("person_confidence") == "HIGH":
                metrics["CORRECT_HIGH_CONFIDENCE"] += 1
        if deepseek_rank_index == 0:
            metrics["DEEPSEEK_CORRECT_TOP1"] += 1

        metrics["FALSE_HIGH_CONFIDENCE_COUNT"] += sum(
            1
            for candidate in candidates
            if candidate.get("person_confidence") == "HIGH"
            and normalize_person_name(candidate.get("name", "")) != normalize_person_name(case["expected_person"])
        )

        case_results.append({
            "case_id": case["id"],
            "company": case["company"],
            "facility": case.get("facility", ""),
            "expected_person": case["expected_person"],
            "candidates_found": len(candidates),
            "deepseek_top1": candidate_summary(deepseek_candidates[0] if deepseek_candidates else None),
            "final_deterministic_top1": candidate_summary(candidates[0] if candidates else None),
            "correct_top1": deterministic_rank_index == 0,
            "correct_in_top3": 0 <= deterministic_rank_index < 3,
            "person_confidence": matched.get("person_confidence") if matched else "NOT_FOUND",
            "failure_cause": failure_cause(matched, deterministic_rank_index + 1, candidates),
            "expected_candidate": candidate_summary(matched),
            "telemetry": telemetry,
        })

        if budget is not None:
            budget.persist_status("RUNNING", metrics=metrics, case_results=case_results)

    total = metrics["KNOWN_CASES"]
    metrics.update({
        "PERSON_DISCOVERY_RECALL": metrics["PERSON_FOUND"] / total * 100 if total else 0.0,
        "TOP1_ACCURACY": metrics["CORRECT_TOP1"] / total * 100 if total else 0.0,
        "TOP3_RECALL": metrics["CORRECT_TOP3"] / total * 100 if total else 0.0,
        "HIGH_CONFIDENCE_CORRECT_RATE": metrics["CORRECT_HIGH_CONFIDENCE"] / total * 100 if total else 0.0,
    })
    return {
        "metrics": metrics,
        "hive_usage": budget.snapshot() if budget is not None else {
            "max_requests": MAX_HIVE_REQUESTS,
            "attempted_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "remaining_request_budget": MAX_HIVE_REQUESTS,
        },
        "case_results": case_results,
    }


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
        "CORRECT_HIGH_CONFIDENCE": 0,
        "FALSE_HIGH_CONFIDENCE_COUNT": 0,
    }
    for case in case_results:
        matched = case.get("matched_candidate")
        if not matched or normalize_person_name(matched.get("name", "")) != normalize_person_name(case.get("expected_person", "")):
            continue
        corrected["PERSON_FOUND"] += 1
        top_candidate = case.get("top_candidate") or {}
        if normalize_person_name(top_candidate.get("name", "")) == normalize_person_name(case.get("expected_person", "")):
            corrected["CORRECT_TOP1"] += 1
            corrected["CORRECT_TOP3"] += 1
        if matched.get("person_confidence") == "HIGH":
            corrected["CORRECT_HIGH_CONFIDENCE"] += 1

    total = corrected["KNOWN_CASES"]
    corrected.update({
        "PERSON_DISCOVERY_RECALL": corrected["PERSON_FOUND"] / total * 100 if total else 0.0,
        "TOP1_ACCURACY": corrected["CORRECT_TOP1"] / total * 100 if total else 0.0,
        "TOP3_RECALL": corrected["CORRECT_TOP3"] / total * 100 if total else 0.0,
        "HIGH_CONFIDENCE_CORRECT_RATE": corrected["CORRECT_HIGH_CONFIDENCE"] / total * 100 if total else 0.0,
    })
    baseline["legacy_metrics"] = metrics
    baseline["metrics"] = corrected
    baseline["baseline_note"] = "Legacy substring name matching was corrected to exact normalized full-name matching."
    return baseline


def run_benchmark(mode: str = "deepseek") -> Dict[str, Any]:
    with open(BENCHMARK_PATH, "r", encoding="utf-8") as benchmark_file:
        cases = json.load(benchmark_file)

    prior_baseline = load_prior_baseline()
    budget: Optional[HiveRequestBudget] = None
    ranking_provider = None
    output_path = BASELINE_PATH
    if mode == "deepseek":
        if settings.HIVE_ALLOW_PAID_OVERAGE:
            raise RuntimeError("HIVE_ALLOW_PAID_OVERAGE must remain false for the controlled benchmark")
        from services.llm_provider import HiveProvider

        budget = HiveRequestBudget(output_path=ASSISTED_PATH)
        ranking_provider = BudgetedProvider(HiveProvider(), budget)
        output_path = ASSISTED_PATH

    try:
        result = evaluate_cases(
            cases,
            use_deepseek=mode == "deepseek",
            ranking_provider=ranking_provider,
            budget=budget,
        )
        result["timestamp"] = utc_now()
        result["mode"] = mode
        result["status"] = "COMPLETED"
        if mode == "deepseek":
            result["baseline"] = prior_baseline.get("metrics", {}) if prior_baseline else None
        write_json_atomic(output_path, result)
    except Exception as error:
        if budget is not None:
            budget.persist_status("FAILED", error_type=type(error).__name__)
        raise

    print(json.dumps({
        "mode": mode,
        "status": result["status"],
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
