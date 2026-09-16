"""Offline Replay Script for Task 3C Entity Resolution.

Replays 25 real candidates from Task 2 and Task 3B audits to measure:
- BEFORE vs AFTER entity acceptance
- BEFORE vs AFTER false positives
- Valid companies preserved vs lost
"""
import sys

from services.entity_truth_gate import (
    EntityType,
    classify_entity_candidate,
)

SAMPLE_CANDIDATES = [
    # (candidate_string, is_actually_valid_company, class_name)
    ("Waaree Energies relocates 6GW vertically", False, "Headline Fragment"),
    ("pv magazine India", False, "Publisher"),
    ("Automobile, Auto Components & EV", False, "Government Sector Label"),
    ("Business Data & Market Insights", False, "Market Research / Data Insights"),
    ("EV Charging Station Franchise", False, "Commercial Franchise Offer"),
    ("Times of India", False, "News Publisher"),
    ("Ems profiles", False, "Job Listing Heading"),
    ("Moulding Apqp Jobs", False, "Job Listing Heading"),
    ("Daily Morning Newsletter", False, "Newsletter Heading"),
    ("A 40 Billion", False, "Economic Counter Fragment"),
    ("ion cell", False, "Generic Product"),
    ("Omprakash Singh Bisht", False, "Person Name"),
    ("JMK Research", False, "Research Publisher"),
    ("IBEF", False, "Government Trade Foundation"),
    ("Our Businesses", False, "Navigation Heading"),
    ("Solar Module", False, "Generic Product"),
    ("Maruti Suzuki has", False, "Headline Fragment"),
    ("ITP Aero has", False, "Headline Fragment"),
    ("Jakson Engineers", True, "Authentic Company"),
    ("Reliance Industries", True, "Authentic Company"),
    ("VinFast", True, "Authentic Company"),
    ("Motherson", True, "Authentic Company"),
    ("Tata Electronics", True, "Authentic Company"),
    ("Neuron Energy", True, "Authentic Company"),
    ("Sundram Fasteners Limited", True, "Authentic Company"),
]


def run_offline_replay():
    sample_size = len(SAMPLE_CANDIDATES)

    before_accepted = 25
    before_false_positives = sum(1 for _, is_valid, _ in SAMPLE_CANDIDATES if not is_valid)
    before_valid_companies = sum(1 for _, is_valid, _ in SAMPLE_CANDIDATES if is_valid)

    after_accepted = 0
    after_false_positives = 0
    valid_companies_preserved = 0
    valid_companies_lost = 0
    false_negatives = []

    for name, is_valid, desc in SAMPLE_CANDIDATES:
        res = classify_entity_candidate(name)
        is_accepted = res["entity_class"] == EntityType.COMPANY

        if is_accepted:
            after_accepted += 1
            if not is_valid:
                after_false_positives += 1
            else:
                valid_companies_preserved += 1
        else:
            if is_valid:
                valid_companies_lost += 1
                false_negatives.append((name, res["reason"]))

    print("==================================================")
    print("TASK 3C.1 OFFLINE REPLAY AUDIT REPORT")
    print("==================================================")
    print(f"REPLAY_SAMPLE_SIZE: {sample_size}")
    print(f"BEFORE_ACCEPTED: {before_accepted}")
    print(f"AFTER_ACCEPTED: {after_accepted}")
    print(f"BEFORE_FALSE_POSITIVES: {before_false_positives}")
    print(f"AFTER_FALSE_POSITIVES: {after_false_positives}")
    print(f"VALID_COMPANIES_PRESERVED: {valid_companies_preserved}")
    print(f"VALID_COMPANIES_LOST: {valid_companies_lost}")
    if false_negatives:
        print(f"FALSE_NEGATIVES_INTRODUCED: {false_negatives}")
    else:
        print("FALSE_NEGATIVES_INTRODUCED: NONE")
    print("==================================================")

    assert after_false_positives == 0, f"Expected 0 after false positives, got {after_false_positives}"
    assert valid_companies_lost == 0, f"Expected 0 valid companies lost, got {valid_companies_lost}"
    assert valid_companies_preserved == before_valid_companies, "All valid companies must be preserved"
    print("ALL REPLAY ASSERTIONS PASSED!")


if __name__ == "__main__":
    run_offline_replay()
