import os
import sys
import re
import json
from datetime import datetime, timezone
from typing import Dict, Any, List

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.research_provider import research_router
from services.contact_confidence import validate_person_name
from services.decision_maker_discovery import classify_functional_role, score_candidate_functional_ownership
from services.llm_provider import GeminiProvider

gemini = GeminiProvider()

# Load the batch 50 results
batch_file = os.path.join(os.path.dirname(__file__), "..", "data", "runtime_state", "batch_50_audit_results.json")
with open(batch_file, "r", encoding="utf-8") as f:
    data = json.load(f)

results = data["results"]
qualified_records = [r for r in results if r.get("facility")]
print(f"Loaded {len(qualified_records)} facility-qualified accounts from Batch 50.\n")

discovered_people = []

for idx, r in enumerate(qualified_records):
    c_name = r["company"]
    city = r["facility"].get("city", "")
    plant_name = r["facility"].get("name", "")
    valid_trigger = r.get("trigger", {})

    print(f"[{idx+1}/{len(qualified_records)}] Searching leadership for: {c_name} ({city})")

    queries = [
        f'site:linkedin.com/in "{c_name}" "Quality Head"',
        f'site:linkedin.com/in "{c_name}" "Plant Head"',
        f'site:linkedin.com/in "{c_name}" "Vice President" "Quality"',
    ]
    if city:
        queries.append(f'site:linkedin.com/in "{c_name}" "{city}" "Quality"')

    qualified_person = None

    for q in queries:
        s_res = research_router.search(q, num_results=5)
        p_results = s_res.get("results", [])
        if not p_results:
            continue

        for pr in p_results:
            p_title = pr.get("title", "")
            p_snippet = pr.get("content", "") or pr.get("snippet", "")
            p_url = pr.get("url", "")

            if "linkedin.com/in/" not in p_url.lower():
                continue
            if any(bad in p_url for bad in ["/company/", "/posts/", "/pub/dir/", "/pulse/"]):
                continue

            parts = re.split(r"[-|–—:]", p_title)[0].strip()
            clean_name = re.sub(r"^(Dr\.|Mr\.|Ms\.|Mrs\.)\s+", "", parts, flags=re.IGNORECASE).strip()

            val = validate_person_name(clean_name, company_name=c_name)
            if not val.get("is_human_name") or len(clean_name.split()) < 2:
                continue

            p_name = parts
            combo_p = f"{p_title} {p_snippet}"
            role_func, role_hier, role_score = classify_functional_role(p_title, snippet=p_snippet)

            role_title_match = re.search(
                r"(Head\s+of\s+Quality|Quality\s+Head|Head\s+Quality|Plant\s+Head|Manager\s+Quality|QA/QC\s+Head|VP\s+Quality|AVP\s+Quality|Plant\s+Manager|Quality\s+Manager|Metrology|Vice\s+President\s+Quality)",
                combo_p,
                re.IGNORECASE
            )
            if not role_title_match and role_score <= 0:
                continue

            cand_dict = {
                "name": p_name,
                "title": p_title,
                "snippet": p_snippet,
                "evidence_url": p_url,
                "source_url": p_url,
            }
            fac_info = {
                "facility_name": plant_name,
                "city": city,
                "state": "",
            }
            trig_info = {
                "event": valid_trigger.get("title", ""),
                "trigger_type": valid_trigger.get("event_type", ""),
            }
            score_res = score_candidate_functional_ownership(
                candidate=cand_dict,
                facility_info=fac_info,
                trigger_info=trig_info,
                target_company_name=c_name,
            )
            ownership_score = score_res.get("total_score", 0.0)
            if ownership_score < 50.0:
                continue

            assigned_title = role_title_match.group(1) if role_title_match else role_func

            qualified_person = {
                "name": p_name,
                "title": assigned_title,
                "authority_class": "STRONG_PLANT_QUALITY_OWNER" if ownership_score >= 80 else "FUNCTIONALLY_RELEVANT",
                "linkedin_url": p_url,
                "provenance": "LINKEDIN_SEARCH_SNIPPET",
                "ownership_score": ownership_score,
                "source_url": p_url,
            }
            break

        if qualified_person:
            break

    if qualified_person:
        print(f"  --> FOUND: {qualified_person['name']} | {qualified_person['title']} | Score: {qualified_person['ownership_score']} ({qualified_person['linkedin_url']})")
        discovered_people.append({
            "company": c_name,
            "person": qualified_person,
            "facility": plant_name,
            "city": city,
        })
    else:
        print(f"  --> NO_PERSON (Strictly held)")

print(f"\nDiscovered {len(discovered_people)} verified human decision makers out of {len(qualified_records)} accounts.")
