import sys
import os
import json
import time

sys.path.insert(0, "/app")

from services.llm_provider import UnoRouterProvider, get_provider

prov = UnoRouterProvider(model_name="glm-5.3-search:free")
prompt = (
    "Provide 5 real, verifiable 2025 or 2026 Indian manufacturing plant expansion, commissioning, or new factory setup announcements. "
    "For each, include: Company Name, Facility Location (City, State, Industrial Area), Event (e.g. new plant, commissioning, line expansion), Date, and official or business media source URL. "
    "Output valid JSON array with keys: company, city, state, industrial_area, event_type, event_description, date, source_url."
)

try:
    resp = prov.complete(
        system_prompt="You are an industrial market research intelligence engine. Output only valid JSON.",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=1200,
        response_format="json",
    )
    print("UnoRouter Text:\n", resp.text)
    print("Citations:\n", resp.citations)
except Exception as e:
    print("Error calling UnoRouter:", e)
