"""Offline Replay for Task 3C.1.3.

Replays:
- Electronics manufacturing services
- India’s Top Fastest
- Toyota to roll out solid
- ProjectX India
- pv magazine India
- Premier Energies
- Balaji Speciality Chemicals
- Ecosyms Solutions
- Super Screws
- HARMAN
- Waaree Energies
- Tata Electronics
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.entity_truth_gate import (
    EntityType,
    classify_entity_candidate,
    validate_company_entity,
    trim_headline_subject_boundary,
)

REPLAY_CASES = [
    # (name, expected_is_company, expected_class, context_text, url)
    ("Electronics manufacturing services", False, EntityType.GENERIC_INDUSTRY_TERM, "", "https://manufacturing.economictimes.indiatimes.com/tag/electronics+manufacturing+services"),
    ("India’s Top Fastest", False, EntityType.ARTICLE_HEADLINE_FRAGMENT, "India's Top Fastest-Growing EMS Companies", "https://cxotoday.com/press-release/indias-top-fastest-growing-ems-companies/"),
    ("Toyota to roll out solid", False, EntityType.ARTICLE_HEADLINE_FRAGMENT, "", "https://www.reuters.com/business/autos-transportation/toyota-roll-out-solid-state-battery-evs"),
    ("ProjectX India", False, EntityType.PUBLISHER, "", "https://projectxindia.com"),
    ("pv magazine India", False, EntityType.PUBLISHER, "", "https://www.pv-magazine-india.com"),
    ("Premier Energies", True, EntityType.COMPANY, "", "https://premierenergies.com"),
    ("Balaji Speciality Chemicals", True, EntityType.COMPANY, "", "https://balajispecialitychemicals.com"),
    ("Ecosyms Solutions", True, EntityType.COMPANY, "", "https://ecosyms.com"),
    ("Super Screws", True, EntityType.COMPANY, "", "https://superscrews.com"),
    ("HARMAN", True, EntityType.COMPANY, "", "https://news.harman.com"),
    ("Waaree Energies", True, EntityType.COMPANY, "", "https://waaree.com"),
    ("Tata Electronics", True, EntityType.COMPANY, "", "https://tataelectronics.com"),
]


def run_offline_replay():
    print("==================================================")
    print("TASK 3C.1.3 OFFLINE REPLAY BENCHMARK")
    print("==================================================")

    invalids_rejected = 0
    valids_preserved = 0
    fps = 0
    fns = 0

    for name, exp_comp, exp_cls, ctx, url in REPLAY_CASES:
        res = classify_entity_candidate(name, context_text=ctx, url=url)
        is_comp = res["is_company"]
        ecls = res["entity_class"]

        if exp_comp:
            if is_comp:
                valids_preserved += 1
                status = "OK (PRESERVED)"
            else:
                fns += 1
                status = f"FAIL (FN - rejected as {ecls})"
        else:
            if not is_comp:
                invalids_rejected += 1
                status = f"OK (REJECTED as {ecls})"
            else:
                fps += 1
                status = f"FAIL (FP - accepted as {ecls})"

        print(f"  {name:38} | Expected: {'COMPANY' if exp_comp else 'INVALID':7} | Actual: {ecls:26} | {status}")

    print("\nSUMMARY:")
    print(f"  REPLAY_SAMPLE_SIZE:        {len(REPLAY_CASES)}")
    print(f"  INVALIDS_REJECTED:         {invalids_rejected}")
    print(f"  VALID_COMPANIES_PRESERVED: {valids_preserved}")
    print(f"  FALSE_POSITIVES:           {fps}")
    print(f"  FALSE_NEGATIVES:           {fns}")
    print("==================================================")
    return fps == 0 and fns == 0


if __name__ == "__main__":
    success = run_offline_replay()
    sys.exit(0 if success else 1)
