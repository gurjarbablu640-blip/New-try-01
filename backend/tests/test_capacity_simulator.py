"""Tests for Capacity Simulator Engine.

Verifies:
- Distinct labeling: OBSERVED_BASELINE, TARGET_SCENARIO, VALIDATED
- Conservative confidence rating for small sample sizes
- Model requirements for 100 and 150 daily sends
- Rejection of premature TARGET_CAPABLE claims without sufficient validated evidence
"""
import pytest
from services.capacity_simulator import CapacitySimulator


def test_observed_baseline_labels_and_confidence():
    sim = CapacitySimulator()
    baseline = sim.calculate_observed_baseline(db=None)

    assert baseline["model_type"] == "OBSERVED_BASELINE"
    # Small real send sample must be rated LOW confidence
    assert baseline["confidence"] == "LOW"
    assert "tiny real send sample" in baseline["confidence_reason"].lower()
    # Query to send rate ~3.4%
    assert 0.02 <= baseline["rates"]["query_to_send_rate"] <= 0.05
    assert baseline["queries_per_send"] > 20


def test_target_scenario_distinct_from_evidence():
    sim = CapacitySimulator()
    scenario = sim.calculate_target_scenario()

    assert scenario["model_type"] == "TARGET_SCENARIO"
    assert scenario["confidence"] == "THEORETICAL_MODEL"
    # Scenarios for 100 and 150 sends must be within Serper 1500 ceiling
    req_100 = scenario["funnel_requirements_100_sends"]
    req_150 = scenario["funnel_requirements_150_sends"]
    assert req_100["within_serper_1500_ceiling"] is True
    assert req_150["within_serper_1500_ceiling"] is True


def test_validation_requires_sufficient_data():
    sim = CapacitySimulator()

    # 1. 5 queries -> INSUFFICIENT_DATA
    res_tiny = sim.evaluate_validation(soak_queries=5, soak_productive=2, soak_sends=0, soak_strong=1)
    assert res_tiny["status"] == "INSUFFICIENT_DATA"
    assert res_tiny["confidence"] == "LOW"

    # 2. 25 queries with productive yield -> VALIDATED
    res_soak = sim.evaluate_validation(soak_queries=25, soak_productive=12, soak_sends=1, soak_strong=5)
    assert res_soak["status"] == "VALIDATED"
    assert res_soak["confidence"] == "MEDIUM"
