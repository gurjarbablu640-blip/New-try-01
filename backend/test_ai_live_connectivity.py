"""Test live connectivity for OpenAI and Google Gemini using configured credentials."""
import time
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.settings_manager import get_setting_value, test_ai_provider_connection

def test_live_ai():
    print("=" * 80)
    print("AI PROVIDER LIVE CONNECTIVITY & CAPABILITY TEST")
    print("=" * 80)

    openai_key = str(get_setting_value('OPENAI_API_KEY', '')).strip()
    google_key = str(get_setting_value('GOOGLE_API_KEY', '')).strip()

    print(f"OpenAI Key: {'[SET]' if openai_key and not openai_key.startswith('mock_') and 'test-sample' not in openai_key else '[MOCK/TEST KEY]'}")
    print(f"Gemini Key: {'[SET]' if google_key and not google_key.startswith('mock_') and not google_key.startswith('YOUR_') else '[MOCK/TEST KEY]'}")

    # 1. Test OpenAI
    print("\n--- 1. OpenAI Diagnostic ---")
    diag_openai = test_ai_provider_connection("openai")
    print(f"Diagnostic Result: {diag_openai}")

    if openai_key and not openai_key.startswith('mock_') and 'test-sample' not in openai_key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=openai_key)
            t0 = time.time()
            res = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "Respond with JSON: {\"status\": \"ok\", \"provider\": \"openai\"}"}],
                response_format={"type": "json_object"},
                max_tokens=30
            )
            elapsed = round(time.time() - t0, 3)
            print(f"OpenAI Live Request: SUCCESS in {elapsed}s")
            print(f"Model: {res.model}")
            print(f"Response: {res.choices[0].message.content}")
            print(f"Tokens Used: prompt={res.usage.prompt_tokens}, completion={res.usage.completion_tokens}, total={res.usage.total_tokens}")
        except Exception as e:
            print(f"OpenAI Live Call Error: {e}")

    # 2. Test Gemini
    print("\n--- 2. Google Gemini Diagnostic ---")
    diag_gemini = test_ai_provider_connection("gemini")
    print(f"Diagnostic Result: {diag_gemini}")

    if google_key and not google_key.startswith('mock_') and not google_key.startswith('YOUR_'):
        try:
            import google.generativeai as genai
            genai.configure(api_key=google_key)
            model_name = "gemini-1.5-flash"
            model = genai.GenerativeModel(model_name)
            t0 = time.time()
            res = model.generate_content("Respond with JSON: {\"status\": \"ok\", \"provider\": \"gemini\"}")
            elapsed = round(time.time() - t0, 3)
            print(f"Gemini Live Request: SUCCESS in {elapsed}s")
            print(f"Model: {model_name}")
            print(f"Response: {res.text}")
        except Exception as e:
            print(f"Gemini Live Call Error: {e}")

    # 3. Test Serper Search Diagnostic
    print("\n--- 3. Serper Search Provider Diagnostic ---")
    from services.settings_manager import test_serper_connection
    diag_serper = test_serper_connection()
    print(f"Serper Diagnostic Result: {diag_serper}")

    # 4. Test Deterministic Fallback Reasoning Engine
    print("\n--- 4. Internal Deterministic Fallback & Causal Reasoning ---")
    from services.reasoning_engine import CAUSAL_TEMPLATES, EpistemicType
    print(f"Deterministic Rule Engine Status: LIVE & OPERATIONAL")
    print(f"Epistemic Types: {[e.value for e in EpistemicType]}")
    print(f"Available Causal Templates ({len(CAUSAL_TEMPLATES)}): {list(CAUSAL_TEMPLATES.keys())}")
    template = CAUSAL_TEMPLATES.get("plant_expansion")
    print(f"Plant Expansion Causal Chain: {' -> '.join(template['causal_chain'])}")
    print(f"Likely Parameters: {template['likely_parameters']}")

if __name__ == "__main__":
    test_live_ai()
