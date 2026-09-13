import json
from pathlib import Path
from unittest.mock import patch

import pytest

from services.llm_provider import LLMResponse
from scripts.run_person_discovery_benchmark import (
    BudgetedProvider,
    HiveRequestBudget,
    HiveRequestBudgetExceeded,
    evaluate_cases,
    find_expected_candidate,
    load_prior_baseline,
)


def test_expected_person_requires_exact_normalized_full_name():
    candidates = [{"name": "Yuvraj Singh jadam"}, {"name": "Dr. Ravi Singh"}]

    rank, candidate = find_expected_candidate(candidates, "Ravi Singh")

    assert rank == 1
    assert candidate == {"name": "Dr. Ravi Singh"}


def test_partial_surname_cannot_satisfy_benchmark_identity():
    rank, candidate = find_expected_candidate([{"name": "Ravi Kumar"}, {"name": "Singh Raviendra"}], "Ravi Singh")

    assert rank == -1
    assert candidate is None


def test_legacy_baseline_false_positive_is_removed():
    baseline = load_prior_baseline()

    assert baseline is not None
    assert baseline["metrics"]["KNOWN_CASES"] == 5
    assert baseline["metrics"]["PERSON_FOUND"] == 0
    assert baseline["metrics"]["PERSON_DISCOVERY_RECALL"] == 0.0


def test_hive_request_budget_blocks_request_eleven_and_persists(tmp_path):
    class SuccessfulProvider:
        def __init__(self):
            self.calls = 0

        def complete(self, *args, **kwargs):
            self.calls += 1
            return LLMResponse(
                text="{}",
                usage={"input_tokens": 10, "output_tokens": 5},
                provider="hive",
                model="deepseek-ai/DeepSeek-V4.1-Flash",
            )

    output_path = tmp_path / "benchmark.json"
    budget = HiveRequestBudget(output_path=str(output_path), input_usd_per_million=0.15, output_usd_per_million=0.60)
    underlying = SuccessfulProvider()
    provider = BudgetedProvider(underlying, budget)

    for _ in range(10):
        provider.complete()
    with pytest.raises(HiveRequestBudgetExceeded):
        provider.complete()

    persisted = json.loads(output_path.read_text(encoding="utf-8"))
    assert underlying.calls == 10
    assert persisted["hive_usage"]["attempted_requests"] == 10
    assert persisted["hive_usage"]["successful_requests"] == 10
    assert persisted["hive_usage"]["failed_requests"] == 0
    assert persisted["hive_usage"]["remaining_request_budget"] == 0


def test_expected_answer_never_enters_discovery_arguments():
    benchmark_case = {
        "id": "CASE-TEST",
        "company": "Example Manufacturing",
        "facility": "Pune Plant",
        "city": "Pune",
        "function_context": "Plant Quality",
        "expected_person": "Secret Gold Person",
        "expected_title": "Secret Gold Title",
    }
    discovery_result = {"candidates": [], "telemetry": {}}

    with patch(
        "scripts.run_person_discovery_benchmark.discover_and_rank_decision_makers",
        return_value=discovery_result,
    ) as discovery:
        evaluate_cases([benchmark_case], use_deepseek=False)

    production_arguments = discovery.call_args.kwargs
    serialized = json.dumps(production_arguments)
    assert "expected_person" not in production_arguments
    assert "expected_title" not in production_arguments
    assert "Secret Gold Person" not in serialized
    assert "Secret Gold Title" not in serialized


def test_pytest_scope_contains_no_live_hive_probe_scripts():
    repository_root = Path(__file__).resolve().parents[2]
    backend_root = Path(__file__).resolve().parents[1]
    pytest_config_path = repository_root / "pytest.ini"
    unsafe_scripts = list((backend_root / "scripts").glob("test_hive*.py"))

    if pytest_config_path.exists():
        pytest_config = pytest_config_path.read_text(encoding="utf-8")
        assert "testpaths = backend/tests" in pytest_config
    assert unsafe_scripts == []
