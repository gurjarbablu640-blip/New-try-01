from scripts.run_person_discovery_benchmark import find_expected_candidate, load_prior_baseline


def test_expected_person_requires_exact_normalized_full_name():
    candidates = [{"name": "Yuvraj Singh jadam"}, {"name": "Dr. Ravi Singh"}]

    rank, candidate = find_expected_candidate(candidates, "Ravi Singh")

    assert rank == 1
    assert candidate == {"name": "Dr. Ravi Singh"}


def test_legacy_baseline_false_positive_is_removed():
    baseline = load_prior_baseline()

    assert baseline is not None
    assert baseline["metrics"]["KNOWN_CASES"] == 5
    assert baseline["metrics"]["PERSON_FOUND"] == 0
    assert baseline["metrics"]["PERSON_DISCOVERY_RECALL"] == 0.0
