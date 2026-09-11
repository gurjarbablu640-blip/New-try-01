"""Targeted script for remaining UnoRouter evaluations:
- Test B (Person Ranking)
- Test C (Conflicting Facility Classification)
- Search Freshness / Citation Check
- Cache Verification

Paces requests by 65 seconds to adhere to 1 RPM free tier rule.
"""
import json
import os
import sys
import time

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.llm_provider import UnoRouterProvider, llm_reasoning_cache

def wait_rate_limit(seconds=65):
    print(f"\n[Pacing] Waiting {seconds}s for 1 RPM rate limit window...")
    time.sleep(seconds)

def main():
    p = UnoRouterProvider()
    p._retry_after_until = None
    
    # 1. TEST B
    print("\n--- TEST B: Person / Decision Maker Ranking ---")
    prompt_b = (
        "Given 4 possible people/titles at an automotive manufacturing plant:\n"
        "1. Anil Patil — Head of Quality & Operational Excellence\n"
        "2. Suresh Kumar — Senior Manager IT Systems\n"
        "3. Rajesh Deshmukh — Plant HR Lead\n"
        "4. Ramesh Kulkarni — Assistant Manager Quality Control & Calibration Lab\n"
        "Rank who is most likely to own plant quality and calibration equipment vendor decisions (1 = highest priority). "
        "Return JSON with keys: 'ranked_candidates' (list of objects with 'rank', 'name', 'title', 'reason')."
    )
    t0 = time.time()
    resp_b = p.complete(
        system_prompt="You are a B2B sales intelligence specialist. Output valid JSON.",
        messages=[{"role": "user", "content": prompt_b}],
        response_format="json",
        temperature=0.2,
        max_tokens=500,
    )
    print(f"Latency B: {time.time()-t0:.2f}s")
    print(f"Response B:\n{resp_b.text.strip()}")
    
    wait_rate_limit(65)
    p._retry_after_until = None
    
    # 2. TEST C
    print("\n--- TEST C: Conflicting Facility Evidence Classification ---")
    prompt_c = (
        "Given the following facility evidence:\n"
        "Evidence 1: Official annual report lists 'Plot B-14, Chakan MIDC Phase 2, Pune, Maharashtra'.\n"
        "Evidence 2: A press release mentions a 'new facility in Pune outskirts near Talegaon'.\n"
        "Classify the certainty of the Chakan plant location into exactly one of: DIRECT, STRONG, WEAK, or UNKNOWN. "
        "Return JSON with keys: 'classification', 'confidence', 'rationale'."
    )
    t0 = time.time()
    resp_c = p.complete(
        system_prompt="You are a facility verification analyst. Output valid JSON.",
        messages=[{"role": "user", "content": prompt_c}],
        response_format="json",
        temperature=0.2,
        max_tokens=400,
    )
    print(f"Latency C: {time.time()-t0:.2f}s")
    print(f"Response C:\n{resp_c.text.strip()}")
    
    wait_rate_limit(65)
    p._retry_after_until = None
    
    # 3. SEARCH FRESHNESS
    print("\n--- SEARCH FRESHNESS & CITATION EVALUATION ---")
    prompt_s = (
        "What recent manufacturing or expansion announcements occurred in 2025 or 2026 for Dixon Technologies or Tata Electronics in India? "
        "Include dates, locations, and any source citations/URLs available."
    )
    t0 = time.time()
    resp_s = p.complete(
        system_prompt="Provide factual information with source citations if available.",
        messages=[{"role": "user", "content": prompt_s}],
        temperature=0.2,
        max_tokens=600,
    )
    print(f"Latency Search: {time.time()-t0:.2f}s")
    print(f"Search Response Text:\n{resp_s.text.strip()}")
    print(f"Citations extracted: {resp_s.citations}")
    print(f"Raw response keys: {list(resp_s.raw_response.keys()) if isinstance(resp_s.raw_response, dict) else 'N/A'}")
    
    wait_rate_limit(65)
    p._retry_after_until = None
    
    # 4. CACHE TEST
    print("\n--- CACHE VERIFICATION ---")
    test_user = "Reply with word: CACHE_TEST_123"
    sys_prompt = "Deterministic test helper"
    
    # First call
    t0 = time.time()
    resp_cache = p.complete(
        system_prompt=sys_prompt,
        messages=[{"role": "user", "content": test_user}],
        max_tokens=20,
    )
    t1 = time.time()
    print(f"Live call text: {resp_cache.text.strip()} (Time: {(t1-t0)*1000:.1f}ms)")
    
    llm_reasoning_cache.set_prompt_response(
        provider="unorouter",
        model=p.model_name,
        system_prompt=sys_prompt,
        user_prompt=test_user,
        output={"text": resp_cache.text.strip()},
    )
    
    cached = llm_reasoning_cache.get_prompt_response(
        provider="unorouter",
        model=p.model_name,
        system_prompt=sys_prompt,
        user_prompt=test_user,
    )
    print(f"Cache retrieved: {cached is not None}")
    if cached:
        print(f"Cached output: {cached['output']}")
        print("CACHE STATUS: PASS")
    else:
        print("CACHE STATUS: FAIL")

if __name__ == "__main__":
    main()
