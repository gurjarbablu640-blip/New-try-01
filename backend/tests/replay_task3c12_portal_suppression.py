"""Task 3C.1.2 Offline Replay: Portal Suppression and Subject Recovery.

Replays real discovery items across portals, publishers, and manufacturers:
- ProjectX India
- New Projects Tracker-style source
- pv magazine-type publisher
- Real manufacturer official page
- Manufacturer newsroom page
- Legitimate engineering/projects company
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.entity_truth_gate import (
    EntityType,
    classify_entity_candidate,
    extract_clean_company_name_from_title,
    trim_headline_subject_boundary,
)

REPLAY_ITEMS = [
    {
        "category": "PORTAL_ARTICLE",
        "name": "ProjectX India",
        "title": "Voltamp Transformers to supply power transformers to GETCO - ProjectX India",
        "url": "https://projectxindia.com/2025/11/01/voltamp-transformers-to-supply-power-transformers-to-getco/",
        "is_portal": True,
        "expected_subjects": ["Voltamp Transformers"],
    },
    {
        "category": "PORTAL_CATEGORY",
        "name": "New Projects Tracker",
        "title": "Welcome to New Project Tracker - Projects India",
        "url": "https://www.newprojectstracker.net/projects-india/manufacturing?page=4",
        "is_portal": True,
        "expected_subjects": [""],
    },
    {
        "category": "PUBLISHER_ARTICLE",
        "name": "pv magazine India",
        "title": "Premier Energies commissions 5.6 GW solar module facility in Telangana - pv magazine India",
        "url": "https://www.pv-magazine.com/2026/03/31/premier-energies-commissions-5-6-gw-solar-module-facility-in-india/",
        "is_portal": True,
        "expected_subjects": ["Premier Energies"],
    },
    {
        "category": "MANUFACTURER_OFFICIAL",
        "name": "Waaree Energies",
        "title": "Waaree Energies Limited | Solar Panel Manufacturer in India",
        "url": "https://www.waaree.com/",
        "is_portal": False,
        "expected_subjects": ["Waaree Energies", "Waaree Energies Limited"],
    },
    {
        "category": "MANUFACTURER_NEWSROOM",
        "name": "Waaree Energies",
        "title": "Waaree Energies Announces New Solar Module Capacity in Gujarat",
        "url": "https://www.waaree.com/news/announcement",
        "is_portal": False,
        "expected_subjects": ["Waaree Energies"],
    },
    {
        "category": "LEGITIMATE_PROJECTS_CO",
        "name": "Tata Projects Limited",
        "title": "Tata Projects Limited to execute major industrial EPC facility in Gujarat",
        "url": "https://www.tataprojects.com/press-releases/industrial-facility",
        "is_portal": False,
        "expected_subjects": ["Tata Projects Limited"],
    },
]


def run_task3c12_replay():
    portals_tested = 0
    portals_rejected = 0
    article_subjects_recovered = 0
    valid_mfg_preserved = 0
    valid_mfg_total = 0
    false_positives = 0
    false_negatives = 0

    for item in REPLAY_ITEMS:
        name = item["name"]
        url = item.get("url", "")
        title = item.get("title", "")
        is_portal = item["is_portal"]
        expected_subjects = item["expected_subjects"]

        # 1. Test portal/source classification
        cls_res = classify_entity_candidate(name, url=url)
        if is_portal:
            portals_tested += 1
            if not cls_res["is_company"]:
                portals_rejected += 1
            else:
                false_positives += 1
        else:
            valid_mfg_total += 1
            if cls_res["is_company"]:
                valid_mfg_preserved += 1
            else:
                false_negatives += 1

        # 2. Test article subject recovery from title
        extracted_subject = extract_clean_company_name_from_title(title, url=url)
        if any(expected_subjects) or "" in expected_subjects:
            if extracted_subject in expected_subjects:
                article_subjects_recovered += 1
            else:
                print(f"Subject recovery mismatch for '{title}': got '{extracted_subject}', expected one of '{expected_subjects}'")

    print("==================================================")
    print("TASK 3C.1.2 OFFLINE REPLAY REPORT")
    print("==================================================")
    print(f"PORTALS_TESTED: {portals_tested}")
    print(f"PORTALS_REJECTED_CORRECTLY: {portals_rejected}")
    print(f"ARTICLE_SUBJECT_COMPANIES_RECOVERED: {article_subjects_recovered}")
    print(f"VALID_MANUFACTURERS_PRESERVED: {valid_mfg_preserved} / {valid_mfg_total}")
    print(f"FALSE_POSITIVES: {false_positives}")
    print(f"FALSE_NEGATIVES: {false_negatives}")
    print("==================================================")

    assert portals_rejected == portals_tested, "All portals must be rejected"
    assert valid_mfg_preserved == valid_mfg_total, "All valid manufacturers must be preserved"
    assert false_positives == 0, "Zero false positives allowed"
    assert false_negatives == 0, "Zero false negatives allowed"
    print("ALL REPLAY ASSERTIONS PASSED!")


if __name__ == "__main__":
    run_task3c12_replay()
