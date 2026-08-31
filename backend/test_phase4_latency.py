"""Phase 4: Latency, Token Cost, and Multi-Step Orchestrator Benchmark Suite.

Honest reporting on LLM provider availability, token counts, and simulated vs real latency.
"""
import json
import os
import sqlite3
import sys
import time
from datetime import date, datetime

from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.types import ARRAY
from sqlalchemy.dialects.postgresql import JSONB

sqlite3.register_adapter(list, json.dumps)
sqlite3.register_adapter(dict, json.dumps)

@compiles(ARRAY, "sqlite")
def compile_array_sqlite(type_, compiler, **kw):
    return "TEXT"

@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "TEXT"

backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from database import Base
from config import settings
from models.company import Company
from models.customer_asset import CustomerAsset
from models.person import Person
from models.sales_os import Quotation
from services.llm_provider import LLMProvider, LLMResponse, GeminiProvider, OpenAIProvider
from services.orchestrator import AskOorjaOrchestrator


class MockLatencyLLMProvider(LLMProvider):
    """
    Mock LLM provider with simulated response generation.
    Generates realistic dynamic token counts proportional to input prompt length.
    """
    def __init__(self, simulated_latency_per_call: float = 0.40):
        self.simulated_latency = simulated_latency_per_call
        self.call_count = 0

    def is_available(self) -> bool:
        return True

    def complete(self, system_prompt: str, messages: list[dict], temperature: float = 0.2, max_tokens: int = 1500, response_format: str = None) -> LLMResponse:
        self.call_count += 1
        time.sleep(self.simulated_latency)

        # Dynamic token accounting based on character counts
        total_in_chars = len(system_prompt) + sum(len(m.get("content", "")) for m in messages)
        in_tokens = max(50, total_in_chars // 4)
        out_tokens = 120 + (self.call_count * 15)

        return LLMResponse(
            text=json.dumps({
                "reasoning": f"Step {self.call_count} multi-step reasoning synthesized.",
                "recommended_price": 5175.0,
                "confidence": 0.94,
                "recommended_leads": [{"company_name": "Bharat Forge Ltd", "urgency": "High"}],
            }),
            usage={"input_tokens": in_tokens, "output_tokens": out_tokens, "total_tokens": in_tokens + out_tokens},
            provider="mock-simulator",
            model="mock-gemini-2.0-flash",
        )


def run_benchmarks():
    print("=" * 80)
    print("PHASE 4: ORCHESTRATOR LATENCY & TOKEN BENCHMARK REPORT")
    print("=" * 80)

    # 1. Check live environment keys
    has_google = bool(settings.GOOGLE_API_KEY or os.getenv("GOOGLE_API_KEY"))
    has_openai = bool(settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY"))
    has_anthropic = bool(settings.ANTHROPIC_API_KEY or os.getenv("ANTHROPIC_API_KEY"))

    print("\nAPI KEY CONFIGURATION STATUS:")
    print(f"  • GOOGLE_API_KEY set:    {'YES' if has_google else 'NO'}")
    print(f"  • OPENAI_API_KEY set:    {'YES' if has_openai else 'NO'}")
    print(f"  • ANTHROPIC_API_KEY set: {'YES' if has_anthropic else 'NO'}")

    if not (has_google or has_openai):
        print("\nNOTE: No live LLM keys are configured in environment.")
        print("Timing measurements below reflect MOCK-PROVIDER TIMINGS (0.40s simulated delay per LLM call)")
        print("and are NOT representative of live network/API latency. Real network latency requires a live key.")
    else:
        print("\nNOTE: Live LLM key detected. Executing benchmarks against active production provider.")

    print("\n" + "-" * 80)

    # Set up in-memory test DB
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    comp = Company(id=1, name="Bharat Forge Ltd", city="Pune", state="Maharashtra", industry="Automotive", icp_score=92, buying_window="next_30_days")
    person = Person(id=1, company_id=1, full_name="Sanjay Kulkarni", designation="VP Quality", phone="+91-9876543210", email="sanjay@bharatforge.local", is_decision_maker=True)
    asset = CustomerAsset(id=1, company_id=1, instrument_name="CMM Mitutoyo", parameter="Dimensions", calibration_due_date=date.today(), status="Active")
    quote = Quotation(id=1, company_id=1, quotation_number="Q-2026-BFL-001", customer_name="Bharat Forge Ltd", quotation_date=date.today(), subtotal=4500.0, total=4500.0, status="Approved")
    db.add_all([comp, person, asset, quote])
    db.commit()

    real_gemini = GeminiProvider()
    real_openai = OpenAIProvider()
    if real_gemini.is_available():
        provider = real_gemini
    elif real_openai.is_available():
        provider = real_openai
    else:
        provider = MockLatencyLLMProvider(simulated_latency_per_call=0.40)

    results = []

    # 1. Fast Path (1 Iteration - Single Sub-Agent: QuotationAdvisor)
    orch1 = AskOorjaOrchestrator(provider=provider, max_iterations=1)
    t0 = time.perf_counter()
    res1 = orch1.run(query="What is the quotation price for CMM calibration?", db=db)
    t1 = time.perf_counter()
    results.append({
        "profile": "1-Iteration Query (QuotationAdvisor only)",
        "iterations": res1["iterations"],
        "sub_agents": res1["sub_agents_used"],
        "latency_sec": round(t1 - t0, 3),
        "in_tokens": res1["tokens_used"]["input_tokens"],
        "out_tokens": res1["tokens_used"]["output_tokens"],
        "total_tokens": res1["tokens_used"]["total_tokens"],
    })

    # 2. Multi-Step (2 Iterations - LeadPrioritizer in iter 1 -> CalibrationAnalyst in iter 2)
    orch2 = AskOorjaOrchestrator(provider=provider, max_iterations=2)
    t0 = time.perf_counter()
    res2 = orch2.run(query="Which priority leads have upcoming calibration due dates?", db=db)
    t1 = time.perf_counter()
    results.append({
        "profile": "2-Iteration Query (LeadPrioritizer -> CalibrationAnalyst)",
        "iterations": res2["iterations"],
        "sub_agents": res2["sub_agents_used"],
        "latency_sec": round(t1 - t0, 3),
        "in_tokens": res2["tokens_used"]["input_tokens"],
        "out_tokens": res2["tokens_used"]["output_tokens"],
        "total_tokens": res2["tokens_used"]["total_tokens"],
    })

    # 3. Deep Exploration (6 Iterations - Hard Cap ceiling)
    orch6 = AskOorjaOrchestrator(provider=provider, max_iterations=6)
    # Force 6 iterations to verify loop behavior at cap
    orch6._evaluate_and_replan = lambda q, c, iter_count, prov: {"sufficient_answer": iter_count >= 6, "next_sub_agents": ["LeadPrioritizer" if iter_count % 2 == 0 else "CalibrationAnalyst"]}
    t0 = time.perf_counter()
    res6 = orch6.run(query="Perform deep territory audit and multi-step pipeline check", db=db)
    t1 = time.perf_counter()
    results.append({
        "profile": "6-Iteration Query (Deep Multi-Step Hard Cap)",
        "iterations": res6["iterations"],
        "sub_agents": res6["sub_agents_used"],
        "latency_sec": round(t1 - t0, 3),
        "in_tokens": res6["tokens_used"]["input_tokens"],
        "out_tokens": res6["tokens_used"]["output_tokens"],
        "total_tokens": res6["tokens_used"]["total_tokens"],
    })

    # Output Table
    print(f"{'Profile':<46} | {'Iter':<4} | {'Latency (s)':<11} | {'In Tokens':<9} | {'Out Tokens':<10} | {'Sub-Agents'}")
    print("-" * 120)
    for r in results:
        agents = ", ".join(r["sub_agents"])
        print(f"{r['profile']:<46} | {r['iterations']:<4} | {r['latency_sec']:<11} | {r['in_tokens']:<9} | {r['out_tokens']:<10} | {agents}")

    print("\n" + "=" * 80)
    db.close()


if __name__ == "__main__":
    run_benchmarks()
