"""Live Key Verification Script.

Executes ONE real authenticated call for:
1. OpenAI (gpt-4o)
2. Gemini (gemini-2.0-flash / gemini-1.5-flash)
3. Apollo (Vinayagamoorthy Ramesh @ Bharat Forge Ltd)
4. Serper (Thermax Limited Pune Quality Manager)

Records exact status, HTTP code, latency, and response metadata WITHOUT printing secrets.
"""
import sys
import os
import json
import time
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.settings_manager import get_setting_value
from services.llm_provider import OpenAIProvider, GeminiProvider
from services.apollo_adapter import enrich_specific_person
from services.research_provider import research_router


def run_live_keys_test():
    print("=" * 95)
    print("SALESOORJA — LIVE AUTHENTICATED KEY VERIFICATION")
    print("=" * 95)

    # 1. OPENAI LIVE TEST
    print("\n--- 1. OPENAI LIVE REQUEST ---")
    openai_key = str(get_setting_value("OPENAI_API_KEY", "")).strip()
    print(f"OpenAI Key Present: {bool(openai_key)} (Length: {len(openai_key)})")
    
    openai_prov = OpenAIProvider()
    print(f"Model: {openai_prov.model_name}")
    t0 = time.time()
    try:
        res = openai_prov.complete(
            system_prompt="You are a JSON validation assistant. Respond strictly in JSON.",
            messages=[{"role": "user", "content": 'Return JSON: {"status": "ok", "purpose": "Salesoorja provider verification"}'}],
            response_format="json",
            max_tokens=60,
        )
        elapsed = round(time.time() - t0, 3)
        print(f"Result: SUCCESS (HTTP 200 OK)")
        print(f"Latency: {elapsed}s")
        print(f"Tokens: {res.usage}")
        print(f"Response: {res.text.strip()}")
        print("Status: OPENAI = LIVE VERIFIED")
    except Exception as e:
        elapsed = round(time.time() - t0, 3)
        print(f"Result: FAILED")
        print(f"Latency: {elapsed}s")
        print(f"Error: {e}")

    # 2. GEMINI LIVE TEST
    print("\n--- 2. GEMINI LIVE REQUEST ---")
    gemini_key = str(get_setting_value("GOOGLE_API_KEY", "")).strip()
    print(f"Gemini Key Present: {bool(gemini_key)} (Length: {len(gemini_key)})")
    
    gemini_prov = GeminiProvider()
    print(f"Model: {gemini_prov.model_name}")
    t0 = time.time()
    try:
        res = gemini_prov.complete(
            system_prompt="You are a JSON validation assistant. Respond strictly in JSON.",
            messages=[{"role": "user", "content": 'Return JSON: {"status": "ok", "purpose": "Salesoorja provider verification"}'}],
            response_format="json",
            max_tokens=60,
        )
        elapsed = round(time.time() - t0, 3)
        print(f"Result: SUCCESS (HTTP 200 OK)")
        print(f"Latency: {elapsed}s")
        print(f"Tokens: {res.usage}")
        print(f"Response: {res.text.strip()}")
        print("Status: GEMINI = LIVE VERIFIED")
    except Exception as e:
        elapsed = round(time.time() - t0, 3)
        print(f"Result: FAILED")
        print(f"Latency: {elapsed}s")
        print(f"Error: {e}")

    # 3. APOLLO LIVE PILOT TEST
    print("\n--- 3. APOLLO LIVE REQUEST (1 VERIFIED PERSON) ---")
    apollo_key = str(get_setting_value("APOLLO_API_KEY", "")).strip()
    print(f"Apollo Key Present: {bool(apollo_key)} (Length: {len(apollo_key)})")
    
    t0 = time.time()
    apollo_res = enrich_specific_person(
        person_name="Vinayagamoorthy Ramesh",
        company_name="Bharat Forge Ltd",
        title="Sr Manager Quality Dept",
    )
    elapsed = round(time.time() - t0, 3)
    print(f"Apollo Status: {apollo_res.get('status')}")
    print(f"Latency: {elapsed}s")
    print(f"Email Returned: {apollo_res.get('email')}")
    print(f"Email Confidence: {apollo_res.get('email_confidence')}")
    print(f"Phone Returned: {apollo_res.get('phone')}")
    print(f"Error Details: {apollo_res.get('error')}")
    print(f"Mock Mode: {apollo_res.get('mock_mode', False)}")

    # 4. SERPER LIVE SEARCH TEST
    print("\n--- 4. SERPER LIVE SEARCH (SECOND COMPANY) ---")
    t0 = time.time()
    search_res = research_router.search("Thermax Limited Pune Quality Manager", num_results=5)
    elapsed = round(time.time() - t0, 3)
    print(f"Search Status: {search_res.get('provider_status')}")
    print(f"Latency: {elapsed}s")
    print(f"Results Count: {len(search_res.get('results', []))}")
    for idx, r in enumerate(search_res.get('results', [])[:3], 1):
        clean_t = r['title'].encode('ascii', 'replace').decode('ascii')
        print(f"  {idx}. {clean_t} -> {r['url']}")

    print("\n" + "=" * 95)
    print("LIVE KEYS TEST COMPLETE")
    print("=" * 95)


if __name__ == "__main__":
    run_live_keys_test()
