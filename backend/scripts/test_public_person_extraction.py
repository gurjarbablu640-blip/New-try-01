import os
import sys
import re
import json
from typing import Dict, Any, Optional

sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.research_provider import research_router
from services.contact_confidence import validate_person_name, ACTION_VERB_PREFIXES, NON_HUMAN_NAME_TERMS
from services.decision_maker_discovery import classify_functional_role, score_candidate_functional_ownership
from services.llm_provider import GeminiProvider

gemini = GeminiProvider()

# Test 5 companies from the 26 qualified accounts
test_companies = [
    {"company": "Samvardhana Motherson International", "city": "Noida"},
    {"company": "Craftsman Automation", "city": "Coimbatore"},
    {"company": "Endurance Technologies", "city": "Aurangabad"},
    {"company": "Apollo Tyres", "city": "Chennai"},
    {"company": "Bharat Forge", "city": "Pune"},
]

print("=== Testing Public Professional Intelligence Extraction ===")

for target in test_companies:
    c_name = target["company"]
    city = target["city"]
    print(f"\nTarget: {c_name} ({city})")

    q1 = f'"{c_name}" ("Quality Head" OR "Head of Quality" OR "Plant Head" OR "VP Quality")'
    res = research_router.search(q1, num_results=5)
    results = res.get("results", [])

    if not results:
        q2 = f'"{c_name}" ("Factory Manager" OR "Operations Head" OR "Manufacturing Head")'
        res2 = research_router.search(q2, num_results=5)
        results = res2.get("results", [])

    print(f"  Search returned {len(results)} results")
    candidates = []

    # 1. Regex candidate extraction
    for r in results:
        t = r.get("title", "")
        s = r.get("content", "") or r.get("snippet", "")
        u = r.get("url", "")
        combo = f"{t} {s}"

        # Look for patterns like "Name, Title at Company" or "Name - Title"
        parts = re.split(r"[-|–—:]", t)[0].strip()
        clean = re.sub(r"^(Dr\.|Mr\.|Ms\.|Mrs\.)\s+", "", parts, flags=re.IGNORECASE).strip()
        val = validate_person_name(clean, company_name=c_name)
        if val.get("is_human_name") and 2 <= len(clean.split()) <= 4:
            role_func, role_hier, role_score = classify_functional_role(t, snippet=s)
            if role_score > 0 or re.search(r"(Quality|Plant|Manufacturing|Operations)", combo, re.I):
                cand_dict = {"name": clean, "title": t, "snippet": s, "evidence_url": u, "source_url": u}
                fac_dict = {"facility_name": city, "city": city, "state": ""}
                trig_dict = {"event": "Expansion", "trigger_type": "CAPEX"}
                score_res = score_candidate_functional_ownership(cand_dict, fac_dict, trig_dict, c_name)
                if score_res.get("total_score", 0.0) >= 50.0:
                    candidates.append({"name": clean, "title": t, "url": u, "score": score_res["total_score"], "source": "regex"})

    # 2. Gemini fallback extraction if regex found nothing
    if not candidates and results:
        snippets_text = "\n---\n".join([f"Title: {r.get('title')}\nSnippet: {r.get('content') or r.get('snippet')}\nURL: {r.get('url')}" for r in results[:4]])
        prompt = (
            f"Target Company: {c_name}\n"
            f"Location: {city}\n"
            f"Task: Extract any real human individual who is named as holding a plant, quality, manufacturing, or operations role at {c_name} from the text below.\n"
            f"CRITICAL REQUIREMENTS:\n"
            f"- MUST be a real human person's name (e.g. 'Rajesh Kumar', 'V. K. Sharma').\n"
            f"- NEVER return company names, products, divisions, websites, slogans, or non-human terms.\n"
            f"- If no specific human individual is explicitly named with their role, return {{\"name\": null, \"title\": null, \"url\": null}}.\n"
            f"- Output strictly a JSON object: {{\"name\": \"...\", \"title\": \"...\", \"url\": \"...\"}}\n\n"
            f"Search Evidence:\n{snippets_text}"
        )
        try:
            resp = gemini.complete(
                system_prompt="You are a professional industrial researcher extracting verified human leadership.",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=150
            )
            m = re.search(r"\{.*\}", resp.text, re.DOTALL)
            if m:
                parsed = json.loads(m.group(0))
                p_name = (parsed.get("name") or "").strip()
                if p_name and p_name.lower() != "null":
                    clean_llm = re.sub(r"^(Dr\.|Mr\.|Ms\.|Mrs\.)\s+", "", p_name, flags=re.IGNORECASE).strip()
                    val_llm = validate_person_name(clean_llm, company_name=c_name)
                    if val_llm.get("is_human_name") and 2 <= len(clean_llm.split()) <= 4:
                        candidates.append({
                            "name": clean_llm,
                            "title": parsed.get("title") or "Operations Leader",
                            "url": parsed.get("url") or results[0].get("url"),
                            "score": 75.0,
                            "source": "gemini_llm"
                        })
        except Exception as e:
            print(f"  Gemini extraction error: {e}")

    if candidates:
        for c in candidates:
            print(f"  [FOUND] {c['name']} | {c['title']} | Score: {c['score']} | {c['source']}")
    else:
        print("  [NO_PERSON] None found - strictly held.")
