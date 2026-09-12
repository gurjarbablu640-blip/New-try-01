"""Run the conditional person ranking benchmark on frozen candidate discovery cases.

Enforces:
1. Two separate metrics:
   - CANDIDATE_DISCOVERY_RECALL (denominator: 5)
   - CONDITIONAL_RANKING_ACCURACY (denominator: 2 ranking-eligible cases)
2. Expected identities are EVALUATION-ONLY and never leak into prompts or metadata.
3. Strict Hive request budget (max 4 calls, hard stop before call 5).
4. DeepSeek-ai/DeepSeek-V4.1-Flash with small strict JSON schema.
5. Strict evidence rule: deterministic verifier rejects unsupported LLM claims.
6. Final deterministic gate: LLM cannot create HIGH confidence.
7. Ramkrishna positive control evaluated separately.
"""
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
from services.llm_provider import HiveProvider
from services.person_intelligence_service import (
    classify_authority_class,
    classify_current_employment,
    classify_facility_relationship,
    compute_deterministic_person_score,
    rank_candidates_with_deepseek,
)
from services.opportunity_gates import (
    READY_FOR_CONTACT_ENRICHMENT,
    evaluate_apollo_credit_gate,
    evaluate_opportunity_gates,
)

FROZEN_CANDIDATES_PATH = os.path.join(BACKEND_DIR, "data", "benchmarks", "frozen_ranking_candidates.json")
ALL_CASES_PATH = os.path.join(BACKEND_DIR, "data", "benchmarks", "person_benchmark_cases.json")
RESULTS_PATH = os.path.join(BACKEND_DIR, "data", "runtime_state", "conditional_ranking_benchmark_results.json")
MAX_HIVE_REQUESTS = 4


class HiveRequestBudgetExceeded(RuntimeError):
    """Raised when a Hive request would exceed the benchmark limit."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json_atomic(path: str, payload: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary_path = f"{path}.tmp"
    with open(temporary_path, "w", encoding="utf-8") as output_file:
        json.dump(payload, output_file, indent=2)
    import time
    for attempt in range(5):
        try:
            os.replace(temporary_path, path)
            break
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.02)


class HiveRequestBudget:
    """Track exact attempted, successful, failed, token, and cost counters."""

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

    @property
    def remaining_request_budget(self) -> int:
        return self.max_requests - self.attempted_requests

    def reserve_request(self) -> None:
        if self.attempted_requests >= self.max_requests:
            raise HiveRequestBudgetExceeded(
                f"Hive request budget exhausted at {self.max_requests}; request {self.max_requests + 1} blocked"
            )
        self.attempted_requests += 1

    def record_success(self, usage: Optional[Dict[str, Any]]) -> None:
        self.successful_requests += 1
        usage_data = usage or {}
        if "input_tokens" not in usage_data or "output_tokens" not in usage_data:
            self.telemetry_complete = False
        self.input_tokens += int(usage_data.get("input_tokens", 0) or 0)
        self.output_tokens += int(usage_data.get("output_tokens", 0) or 0)

    def record_failure(self, error: Exception) -> None:
        self.failed_requests += 1
        self.last_error = type(error).__name__

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
            "paid_overage_allowed": False,
            "last_error": self.last_error,
        }


class BudgetedProvider:
    """Wraps an LLM provider and counts each call against the budget."""

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


def normalize_name(name: str) -> str:
    tokens = re.findall(r"[a-z]+", (name or "").lower())
    return " ".join(token for token in tokens if token not in {"dr", "mr", "mrs", "ms", "shri", "smt"})


def find_candidate_index(candidates: List[Dict[str, Any]], expected_name: str) -> tuple[int, Optional[Dict[str, Any]]]:
    norm_expected = normalize_name(expected_name)
    for idx, cand in enumerate(candidates):
        if normalize_name(str(cand.get("name") or "")) == norm_expected:
            return idx, cand
    return -1, None


def evaluate_ramkrishna_positive_control() -> Dict[str, Any]:
    """Positive control: Ramkrishna Forgings Plant V / Baliguma -> Krishna Kumar Jha."""
    title = "Plant Head – Plant V"
    snippet = "Krishna Kumar Jha serves as Plant Head – Plant V at Ramkrishna Forgings Plant V Baliguma Jamshedpur facility in 2025."
    company = "Ramkrishna Forgings"
    facility = "Plant V Baliguma"
    city = "Jamshedpur"

    emp = classify_current_employment(snippet, title, company)
    fac = classify_facility_relationship(title, snippet, facility, city)
    auth = classify_authority_class(title)
    score, conf = compute_deterministic_person_score(emp, fac, auth, title, "LINKEDIN_SEARCH_SNIPPET")

    opportunity_record = {
        "trigger_current": {
            "verified": True,
            "trigger_date": "2026-03-06",
            "recency_days": 10,
            "trigger_facility_confidence": "DIRECT",
            "ongoing_activity_evidence": "Ramkrishna Forgings commissions 8,000-ton hot forging press line at Plant V Baliguma",
        },
        "exact_facility": {
            "verified": True,
            "address": "Plant V, Baliguma, Saraikela-Kharswan, Jharkhand",
            "address_precision": "EXACT_PLANT",
            "trigger_facility_confidence": "DIRECT",
            "trigger_facility_evidence": "Commenced commercial production at Plant V Baliguma",
        },
        "calibration_demand": True,
        "technical_capability": True,
        "timing": {
            "is_active_window": True,
            "timing_evidence": "8000-ton press line commissioned March 2026",
            "event_type": "commissioning",
            "trigger_date": "2026-03-06",
        },
        "correct_person": {
            "name": "Krishna Kumar Jha",
            "employment_verified": True,
            "current_employment": emp,
            "facility_verified": True,
            "duties_verified": True,
            "facility_classification": fac,
            "authority_class": auth,
            "person_confidence": conf,
        },
        "reachable_email": {"address": "", "status": "not_found"},
        "score": 90,
        "source": "public_press",
    }

    apollo_gate = evaluate_apollo_credit_gate(opportunity_record)
    outbound_gate = evaluate_opportunity_gates(opportunity_record)

    passed_all = (
        conf == "HIGH"
        and apollo_gate.get("status") == READY_FOR_CONTACT_ENRICHMENT
        and not outbound_gate.get("ready_for_email")
    )

    return {
        "company": company,
        "facility": facility,
        "person_name": "Krishna Kumar Jha",
        "title": title,
        "current_employment": emp,
        "facility_relationship": fac,
        "authority_class": auth,
        "person_score": score,
        "person_confidence": conf,
        "apollo_gate_status": apollo_gate.get("status"),
        "ready_for_contact_enrichment": apollo_gate.get("status") == READY_FOR_CONTACT_ENRICHMENT,
        "ready_for_email": outbound_gate.get("ready_for_email"),
        "control_passed": passed_all,
    }


def run_conditional_ranking_benchmark() -> Dict[str, Any]:
    # 1. Load frozen candidate pools
    with open(FROZEN_CANDIDATES_PATH, "r", encoding="utf-8") as f:
        frozen_pools = json.load(f)

    with open(ALL_CASES_PATH, "r", encoding="utf-8") as f:
        all_cases = json.load(f)

    # Discovery metrics (all 5 cases)
    total_gold_cases = len(all_cases)
    discovered_cases = [c for c in all_cases if c["id"] in frozen_pools]
    discovered_expected = len(discovered_cases)
    candidate_set_recall = round((discovered_expected / total_gold_cases) * 100.0, 2)

    # 2. Setup Hive Budget (max 4 calls, DeepSeek-V4.1-Flash)
    budget = HiveRequestBudget(max_requests=MAX_HIVE_REQUESTS, output_path=RESULTS_PATH)
    raw_provider = HiveProvider(model_name="deepseek-ai/DeepSeek-V4.1-Flash")
    budgeted_provider = BudgetedProvider(raw_provider, budget)

    # 3. Benchmark execution for the 2 ranking-eligible cases
    case_results = []
    det_top1_count = 0
    det_top3_count = 0
    deepseek_top1_count = 0
    deepseek_top3_count = 0
    correct_high_count = 0
    false_high_count = 0

    ranking_eligible_cases = [c for c in all_cases if c["id"] in ("CASE-01", "CASE-02")]

    for case in ranking_eligible_cases:
        case_id = case["id"]
        pool_data = frozen_pools[case_id]
        candidates = pool_data["candidates"]
        expected_person = case["expected_person"]

        # Phase 4: Deterministic baseline position
        det_idx, det_matched = find_candidate_index(candidates, expected_person)
        det_pos = det_idx + 1 if det_idx >= 0 else None
        is_det_top1 = (det_idx == 0)
        is_det_top3 = (0 <= det_idx < 3)
        if is_det_top1:
            det_top1_count += 1
        if is_det_top3:
            det_top3_count += 1

        # Phase 5 & 6 & 7 & 8: DeepSeek ranking with small schema and deterministic verification
        # NOTE: expected_person is NEVER passed to rank_candidates_with_deepseek!
        deepseek_res = rank_candidates_with_deepseek(
            company_name=case["company"],
            facility_name=case.get("facility", ""),
            city=case.get("city", ""),
            commercial_trigger=case.get("function_context", ""),
            target_functions=[case.get("function_context", "Plant Quality")],
            candidates=candidates,
            provider=budgeted_provider,
        )

        ranked_candidates = deepseek_res["candidates"]
        deepseek_idx, deepseek_matched = find_candidate_index(ranked_candidates, expected_person)
        deepseek_pos = deepseek_idx + 1 if deepseek_idx >= 0 else None
        is_deepseek_top1 = (deepseek_idx == 0)
        is_deepseek_top3 = (0 <= deepseek_idx < 3)

        if is_deepseek_top1:
            deepseek_top1_count += 1
        if is_deepseek_top3:
            deepseek_top3_count += 1

        # Final deterministic confidence of the expected person
        final_conf = deepseek_matched.get("person_confidence") if deepseek_matched else "NOT_FOUND"
        if is_deepseek_top1 and final_conf == "HIGH":
            correct_high_count += 1

        # Check for false HIGH: any top-1 candidate who is HIGH but not expected person
        top_cand = ranked_candidates[0] if ranked_candidates else None
        if top_cand and top_cand.get("person_confidence") == "HIGH":
            if normalize_name(top_cand.get("name", "")) != normalize_name(expected_person):
                false_high_count += 1

        # Diagnostic failure cause
        failure = "NONE"
        if not is_deepseek_top1:
            if not is_deepseek_top3:
                failure = "RANKER_PREFERRED_WRONG_AUTHORITY"
            else:
                failure = "FUNCTION_ALIGNMENT_TOO_WEAK"

        case_results.append({
            "case_id": case_id,
            "company": case["company"],
            "facility": case.get("facility", ""),
            "candidate_count": len(candidates),
            "expected_candidate_starting_pos": det_pos,
            "deterministic_final_pos": det_pos,
            "deepseek_pos": deepseek_pos,
            "expected_person": expected_person,
            "top1_candidate_name": top_cand.get("name") if top_cand else None,
            "final_deterministic_confidence": final_conf,
            "correct_top1": is_deepseek_top1,
            "correct_top3": is_deepseek_top3,
            "evidence_sufficient": (final_conf in ("HIGH", "MEDIUM")),
            "failure_cause": failure,
            "deepseek_assessment_count": deepseek_res.get("assessment_count", 0),
        })

    # Metrics calculation
    num_eligible = len(ranking_eligible_cases)  # 2
    conditional_top1_acc = round((deepseek_top1_count / num_eligible) * 100.0, 2)
    conditional_top3_rec = round((deepseek_top3_count / num_eligible) * 100.0, 2)
    false_high_rate = round((false_high_count / num_eligible) * 100.0, 2)
    end_to_end_correct_top1 = deepseek_top1_count  # out of 5

    # Positive control evaluation
    pos_control = evaluate_ramkrishna_positive_control()

    telemetry = budget.snapshot()

    benchmark_output = {
        "timestamp": utc_now(),
        "candidate_discovery": {
            "total_gold_cases": total_gold_cases,
            "discovered_expected": discovered_expected,
            "candidate_set_recall_pct": candidate_set_recall,
            "undiscovered_cases": [c["id"] for c in all_cases if c["id"] not in frozen_pools],
        },
        "deterministic_baseline": {
            "cases_evaluated": num_eligible,
            "top1": f"{det_top1_count} / {num_eligible}",
            "top3": f"{det_top3_count} / {num_eligible}",
            "top1_pct": round((det_top1_count / num_eligible) * 100.0, 2),
            "top3_pct": round((det_top3_count / num_eligible) * 100.0, 2),
        },
        "deepseek_ranking": {
            "cases_evaluated": num_eligible,
            "top1": f"{deepseek_top1_count} / {num_eligible}",
            "top3": f"{deepseek_top3_count} / {num_eligible}",
            "correct_high": f"{correct_high_count} / {num_eligible}",
            "false_high": false_high_count,
            "conditional_top1_accuracy_pct": conditional_top1_acc,
            "conditional_top3_recall_pct": conditional_top3_rec,
            "false_high_confidence_rate_pct": false_high_rate,
            "end_to_end_correct_top1": f"{end_to_end_correct_top1} / {total_gold_cases}",
        },
        "case_table": case_results,
        "positive_control": pos_control,
        "hive_telemetry": telemetry,
    }

    write_json_atomic(RESULTS_PATH, benchmark_output)
    return benchmark_output


def print_report(res: Dict[str, Any]) -> None:
    print("\n" + "=" * 60)
    print("CONDITIONAL PERSON RANKING BENCHMARK REPORT")
    print("=" * 60)
    cd = res["candidate_discovery"]
    print(f"\nCANDIDATE DISCOVERY:")
    print(f"  total gold cases:        {cd['total_gold_cases']}")
    print(f"  expected discovered:     {cd['discovered_expected']}")
    print(f"  candidate-set recall:    {cd['candidate_set_recall_pct']}%")

    db = res["deterministic_baseline"]
    print(f"\nDETERMINISTIC RANKING BASELINE:")
    print(f"  top1:                    {db['top1']} ({db['top1_pct']}%)")
    print(f"  top3:                    {db['top3']} ({db['top3_pct']}%)")

    ds = res["deepseek_ranking"]
    print(f"\nDEEPSEEK RANKING (CONDITIONAL ON DISCOVERY):")
    print(f"  top1:                    {ds['top1']} ({ds['conditional_top1_accuracy_pct']}%)")
    print(f"  top3:                    {ds['top3']} ({ds['conditional_top3_recall_pct']}%)")
    print(f"  correct HIGH:            {ds['correct_high']}")
    print(f"  false HIGH:              {ds['false_high']}")
    print(f"  conditional top1 acc:    {ds['conditional_top1_accuracy_pct']}%")
    print(f"  conditional top3 rec:    {ds['conditional_top3_recall_pct']}%")
    print(f"  END-TO-END CORRECT TOP1: {ds['end_to_end_correct_top1']}")

    print(f"\nFORENSIC CASE TABLE:")
    for ct in res["case_table"]:
        print(f"  * Case: {ct['case_id']} | {ct['company']} ({ct['facility']})")
        print(f"    Expected:            {ct['expected_person']}")
        print(f"    Candidates in pool:  {ct['candidate_count']}")
        print(f"    Deterministic pos:   {ct['deterministic_final_pos']}")
        print(f"    DeepSeek pos:        {ct['deepseek_pos']}")
        print(f"    Top1 candidate:      {ct['top1_candidate_name']}")
        print(f"    Final confidence:    {ct['final_deterministic_confidence']}")
        print(f"    Correct Top1?:       {ct['correct_top1']}")
        print(f"    Correct Top3?:       {ct['correct_top3']}")
        print(f"    Evidence sufficient: {ct['evidence_sufficient']}")
        print(f"    Failure cause:       {ct['failure_cause']}")

    pc = res["positive_control"]
    print(f"\nRAMKRISHNA POSITIVE CONTROL:")
    print(f"  Company:                 {pc['company']}")
    print(f"  Facility:                {pc['facility']}")
    print(f"  Candidate:               {pc['person_name']} ({pc['title']})")
    print(f"  Confidence:              {pc['person_confidence']}")
    print(f"  Apollo gate status:      {pc['apollo_gate_status']}")
    print(f"  Ready for email:         {pc['ready_for_email']}")
    print(f"  Control passed:          {pc['control_passed']}")

    ht = res["hive_telemetry"]
    print(f"\nHIVE TELEMETRY:")
    print(f"  attempted requests:      {ht['attempted_requests']}")
    print(f"  successful requests:     {ht['successful_requests']}")
    print(f"  failed requests:         {ht['failed_requests']}")
    print(f"  input tokens:            {ht['input_tokens']}")
    print(f"  output tokens:           {ht['output_tokens']}")
    print(f"  estimated cost:          ${ht['estimated_usd_cost']}")
    print(f"  remaining budget:        {ht['remaining_request_budget']}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    output = run_conditional_ranking_benchmark()
    print_report(output)
