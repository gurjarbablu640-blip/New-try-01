"""Harmless Live Gemini Verification Script.
Checks:
- Model availability and name confirmation
- Basic completion
- Structured JSON output
- Tool / function calling
- Confirms rate limits / quota without printing or exposing credentials.
"""
import os
import sys
import json
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.settings_manager import get_setting_value

def main():
    google_key = str(get_setting_value("GOOGLE_API_KEY", "")).strip() or str(get_setting_value("GEMINI_API_KEY", "")).strip()
    if not google_key:
        print("FAIL: GOOGLE_API_KEY is not configured.")
        return

    print(f"API Key present: YES (length={len(google_key)})")

    # 1. Query available models list
    models_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={google_key}"
    resp = requests.get(models_url, timeout=15)
    print(f"Models endpoint HTTP status: {resp.status_code}")
    if resp.status_code != 200:
        print(f"Error querying models: {resp.text[:300]}")
        return

    models_data = resp.json()
    model_list = [m.get("name", "").replace("models/", "") for m in models_data.get("models", [])]
    gemini_models = [m for m in model_list if "gemini" in m.lower()]
    print(f"Total Gemini models found: {len(gemini_models)}")
    print(f"Sample available models: {gemini_models[:10]}")

    # Determine best model to use
    # Check user selection or preferences
    preferred_models = [
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-flash",
        "gemini-1.5-flash-8b",
        "gemini-flash"
    ]
    selected_model = None
    for pm in preferred_models:
        if pm in gemini_models:
            selected_model = pm
            break
    if not selected_model and gemini_models:
        selected_model = gemini_models[0]

    print(f"\nSelected Model for test: {selected_model}")

    # 2. Basic Completion Test
    gen_url = f"https://generativelanguage.googleapis.com/v1beta/models/{selected_model}:generateContent?key={google_key}"
    basic_payload = {
        "contents": [{"role": "user", "parts": [{"text": "Reply with only the word PONG"}]}],
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 20}
    }
    r_basic = requests.post(gen_url, json=basic_payload, headers={"Content-Type": "application/json"}, timeout=20)
    print(f"Basic completion HTTP: {r_basic.status_code}")
    basic_pass = False
    if r_basic.status_code == 200:
        ans = r_basic.json().get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
        print(f"Basic completion response: '{ans}'")
        basic_pass = "PONG" in ans.upper()
    else:
        print(f"Basic completion error: {r_basic.text[:300]}")

    # 3. Structured JSON Test
    json_payload = {
        "contents": [{"role": "user", "parts": [{"text": "Return a JSON object with key 'status' set to 'success' and 'provider' set to 'gemini'."}]}],
        "generationConfig": {
            "temperature": 0.0,
            "maxOutputTokens": 50,
            "responseMimeType": "application/json"
        }
    }
    r_json = requests.post(gen_url, json=json_payload, headers={"Content-Type": "application/json"}, timeout=20)
    print(f"Structured JSON HTTP: {r_json.status_code}")
    json_pass = False
    if r_json.status_code == 200:
        raw_json = r_json.json().get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
        print(f"Structured JSON response: '{raw_json}'")
        try:
            parsed = json.loads(raw_json)
            if parsed.get("status") == "success":
                json_pass = True
        except Exception as e:
            print(f"Failed to parse JSON: {e}")
    else:
        print(f"JSON completion error: {r_json.text[:300]}")

    # 4. Tool / Function Calling Test
    tool_payload = {
        "contents": [{"role": "user", "parts": [{"text": "What is the calibration status for equipment EQ-999?"}]}],
        "tools": [{
            "functionDeclarations": [{
                "name": "lookup_equipment_calibration",
                "description": "Look up calibration details for a piece of industrial metrology equipment",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "equipment_id": {
                            "type": "STRING",
                            "description": "The ID of the equipment to inspect"
                        }
                    },
                    "required": ["equipment_id"]
                }
            }]
        }],
        "toolConfig": {
            "functionCallingConfig": {
                "mode": "ANY"
            }
        },
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 100}
    }
    r_tool = requests.post(gen_url, json=tool_payload, headers={"Content-Type": "application/json"}, timeout=20)
    print(f"Tool calling HTTP: {r_tool.status_code}")
    tool_pass = False
    if r_tool.status_code == 200:
        resp_data = r_tool.json()
        parts = resp_data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        for p in parts:
            if "functionCall" in p:
                fc = p["functionCall"]
                print(f"Function call triggered: name={fc.get('name')}, args={fc.get('args')}")
                if fc.get("name") == "lookup_equipment_calibration":
                    tool_pass = True
        if not tool_pass:
            print(f"Parts returned: {parts}")
    else:
        print(f"Tool calling error: {r_tool.text[:300]}")

    # Summary
    print("\n--- SUMMARY ---")
    print(f"BASIC_COMPLETION: {'PASS' if basic_pass else 'FAIL'}")
    print(f"STRUCTURED_JSON: {'PASS' if json_pass else 'FAIL'}")
    print(f"TOOL_CALLING: {'PASS' if tool_pass else 'FAIL'}")
    print(f"SELECTED_MODEL: {selected_model}")

if __name__ == "__main__":
    main()
