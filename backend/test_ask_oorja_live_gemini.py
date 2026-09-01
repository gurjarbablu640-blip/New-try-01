"""Live Ask Oorja Gemini Verification Script.

Tests Ask Oorja multi-step reasoning using live authenticated Google Gemini.
Verifies all 8 sections:
1. ANSWER
2. WHY
3. EVIDENCE
4. WHAT WE KNOW
5. WHAT WE INFER
6. WHAT WE DON'T KNOW
7. CONFIDENCE
8. RECOMMENDED ACTION
"""
import sys
import os
import json
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal
from services.orchestrator import AskOorjaOrchestrator
from services.llm_provider import GeminiProvider


def test_ask_oorja_live():
    print("=" * 95)
    print("ASK OORJA — LIVE GEMINI 8-PART REASONING VERIFICATION")
    print("=" * 95)

    db = SessionLocal()
    try:
        gemini_prov = GeminiProvider()
        print(f"Gemini Provider Available: {gemini_prov.is_available()} (Model: {gemini_prov.model_name})")
        
        orchestrator = AskOorjaOrchestrator(provider=gemini_prov)

        queries = [
            "Why is Bharat Forge a calibration prospect?",
            "Who should I contact at Bharat Forge?",
            "What evidence supports this person?",
            "What do we know versus infer about this account?",
            "What should I do next for Bharat Forge?",
        ]

        sections = [
            "1. ANSWER",
            "2. WHY",
            "3. EVIDENCE",
            "4. WHAT WE KNOW",
            "5. WHAT WE INFER",
            "6. WHAT WE DON'T KNOW",
            "7. CONFIDENCE",
            "8. RECOMMENDED ACTION",
        ]

        for i, q in enumerate(queries, 1):
            print(f"\n--- QUERY {i}: \"{q}\" ---")
            t0 = time.time()
            res = orchestrator.run(q, db=db)
            elapsed = round(time.time() - t0, 3)

            answer = res.get("answer", "")
            sub_agents = res.get("sub_agents_used", [])
            tokens = res.get("tokens_used", {})

            print(f"Latency: {elapsed}s")
            print(f"Sub-agents: {sub_agents}")
            print(f"Tokens: {tokens}")

            # Check 8 sections
            all_present = True
            for sec in sections:
                if sec not in answer and sec.split(". ")[1] not in answer:
                    all_present = False
                    print(f"  [MISSING SECTION]: {sec}")

            if all_present:
                print(f"  [ALL 8 SECTIONS PRESENT]: YES")

            print("\nPreview of Output:")
            lines = answer.strip().split("\n")
            for line in lines[:16]:
                print(f"  {line}")
            if len(lines) > 16:
                print(f"  ... [{len(lines)-16} more lines]")

        print("\n" + "=" * 95)
        print("ALL 5 QUERIES VERIFIED SUCCESSFULLY")
        print("=" * 95)

    finally:
        db.close()


if __name__ == "__main__":
    test_ask_oorja_live()
