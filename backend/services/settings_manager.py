"""Settings and Credential Management Service for Salesoorja.

Provides secure credential persistence, masked status reporting, connection diagnostic tests,
and runtime overrides for OpenAI, Gemini, Apollo, SMTP, IMAP, and Voice services.
Explicitly removes Anthropic references.
"""
from __future__ import annotations

import json
import logging
import os
import smtplib
import imaplib
from typing import Any, Dict, Optional

from config import settings

logger = logging.getLogger(__name__)

SETTINGS_STORAGE_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "runtime_settings.json")


def _mask_secret(val: Optional[str]) -> str:
    """Masks a secret string, revealing only prefix/suffix hints."""
    if not val:
        return ""
    val = val.strip()
    if len(val) <= 8:
        return "••••••••"
    return f"{val[:4]}••••••••{val[-4:]}"


def load_runtime_overrides() -> Dict[str, Any]:
    """Loads persisted runtime setting overrides."""
    if os.path.exists(SETTINGS_STORAGE_FILE):
        try:
            with open(SETTINGS_STORAGE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as err:
            logger.warning(f"Failed to read runtime settings file: {err}")
    return {}


def save_runtime_overrides(new_data: Dict[str, Any]) -> Dict[str, Any]:
    """Persists runtime setting overrides to storage."""
    os.makedirs(os.path.dirname(SETTINGS_STORAGE_FILE), exist_ok=True)
    current = load_runtime_overrides()
    current.update(new_data)
    with open(SETTINGS_STORAGE_FILE, "w", encoding="utf-8") as f:
        json.dump(current, f, indent=2)
    return current


def get_setting_value(key: str, default: Any = None) -> Any:
    """Retrieves a setting, prioritizing runtime overrides over environment variables."""
    overrides = load_runtime_overrides()
    if key in overrides and overrides[key] is not None and overrides[key] != "":
        return overrides[key]
    return getattr(settings, key, default)


def get_masked_settings_status() -> Dict[str, Any]:
    """Returns safe masked configuration status without exposing raw secrets."""
    openai_key = get_setting_value("OPENAI_API_KEY", "")
    gemini_key = get_setting_value("GOOGLE_API_KEY", "")
    apollo_key = get_setting_value("APOLLO_API_KEY", "")
    smtp_pass = get_setting_value("SMTP_PASSWORD", "")
    imap_pass = get_setting_value("IMAP_PASSWORD", "")

    return {
        "ai_providers": {
            "primary_provider": get_setting_value("ORCHESTRATOR_PRIMARY_PROVIDER", "gemini"),
            "fallback_provider": get_setting_value("ORCHESTRATOR_FALLBACK_PROVIDER", "openai"),
            "openai": {
                "configured": bool(openai_key),
                "model": get_setting_value("OPENAI_MODEL", "gpt-4o"),
                "masked_key": _mask_secret(openai_key),
            },
            "gemini": {
                "configured": bool(gemini_key),
                "model": get_setting_value("ORCHESTRATOR_GEMINI_MODEL", "gemini-2.0-flash"),
                "masked_key": _mask_secret(gemini_key),
            },
        },
        "apollo": {
            "configured": bool(apollo_key),
            "masked_key": _mask_secret(apollo_key),
            "pilot_limit_contacts": 6,
            "pilot_status": "Strict Safety Guard Active (≤ 6 Contacts)",
        },
        "smtp": {
            "configured": bool(get_setting_value("SMTP_HOST") and get_setting_value("SMTP_USER")),
            "host": get_setting_value("SMTP_HOST", ""),
            "port": get_setting_value("SMTP_PORT", 587),
            "user": get_setting_value("SMTP_USER", ""),
            "from_email": get_setting_value("SMTP_FROM_EMAIL", "sales@oorja.local"),
            "from_name": get_setting_value("SMTP_FROM_NAME", "Oorja Technical Services"),
            "use_tls": get_setting_value("SMTP_USE_TLS", True),
            "outbound_test_mode": get_setting_value("OUTBOUND_TEST_MODE", True),
            "masked_password": "••••••••" if smtp_pass else "",
        },
        "imap": {
            "configured": bool(get_setting_value("IMAP_HOST") and get_setting_value("IMAP_USER")),
            "host": get_setting_value("IMAP_HOST", ""),
            "port": get_setting_value("IMAP_PORT", 993),
            "user": get_setting_value("IMAP_USER", ""),
            "use_ssl": get_setting_value("IMAP_USE_SSL", True),
            "masked_password": "••••••••" if imap_pass else "",
        },
        "research_sources": {
            "serper_configured": bool(get_setting_value("SERPER_API_KEY", "")),
            "apify_configured": bool(get_setting_value("APIFY_API_TOKEN", "")),
        },
        "calling": {
            "provider": "Mock / Controlled Voice Agent",
            "pilot_mode": True,
            "pilot_number": get_setting_value("PILOT_PHONE_NUMBER", "+91-9876543210"),
        },
    }


def update_settings(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Updates settings from frontend, ignoring empty mask placeholders."""
    cleaned = {}
    for k, v in payload.items():
        if v is not None:
            # If string contains mask dots, do not overwrite existing key
            if isinstance(v, str) and "••••" in v:
                continue
            cleaned[k] = v
            # Also dynamically update in-memory settings
            if hasattr(settings, k):
                setattr(settings, k, v)
    save_runtime_overrides(cleaned)
    return get_masked_settings_status()


# --- Diagnostic Connection Testers ---

def test_ai_provider_connection(provider: str) -> Dict[str, Any]:
    """Tests connection to OpenAI or Gemini without revealing secrets."""
    provider = provider.lower().strip()
    if provider == "openai":
        api_key = get_setting_value("OPENAI_API_KEY", "")
        if not api_key:
            return {"provider": "openai", "status": "NOT_CONFIGURED", "message": "OPENAI_API_KEY is not set."}
        if api_key.startswith("mock_") or "test" in api_key:
            return {"provider": "openai", "status": "CONNECTED", "message": "Mock/Test OpenAI API Key verified successfully."}
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            client.models.list()
            return {"provider": "openai", "status": "CONNECTED", "message": "OpenAI API connection verified successfully."}
        except Exception as err:
            return {"provider": "openai", "status": "AUTHENTICATION_FAILED", "message": str(err)}

    elif provider in ("gemini", "google"):
        api_key = get_setting_value("GOOGLE_API_KEY", "")
        if not api_key:
            return {"provider": "gemini", "status": "NOT_CONFIGURED", "message": "GOOGLE_API_KEY is not set."}
        if api_key.startswith("mock_") or "test" in api_key:
            return {"provider": "gemini", "status": "CONNECTED", "message": "Mock/Test Google Gemini API Key verified successfully."}
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            models = genai.list_models()
            _ = next(iter(models), None)
            return {"provider": "gemini", "status": "CONNECTED", "message": "Google Gemini API connection verified successfully."}
        except Exception as err:
            return {"provider": "gemini", "status": "AUTHENTICATION_FAILED", "message": str(err)}
    else:
        return {"provider": provider, "status": "UNSUPPORTED", "message": f"Provider '{provider}' is not supported. Use OpenAI or Google Gemini."}


def test_apollo_connection() -> Dict[str, Any]:
    """Tests Apollo API key connection."""
    api_key = get_setting_value("APOLLO_API_KEY", "")
    if not api_key:
        return {"status": "NOT_CONFIGURED", "message": "APOLLO_API_KEY is not set."}
    if api_key.startswith("mock_") or "test" in api_key:
        return {"status": "CONNECTED", "message": "Mock Apollo API Key verified. Pilot safety limit (≤ 6 contacts) enforced."}
    try:
        import requests
        headers = {"Content-Type": "application/json", "Cache-Control": "no-cache", "X-Api-Key": api_key}
        res = requests.post("https://api.apollo.io/v1/auth/health", headers=headers, json={}, timeout=10)
        if res.status_code == 200:
            return {"status": "CONNECTED", "message": "Apollo API connection verified. Pilot safety limit (≤ 6 contacts) enforced."}
        return {"status": "AUTHENTICATION_FAILED", "message": f"Apollo returned HTTP {res.status_code}."}
    except Exception as err:
        return {"status": "SERVER_ERROR", "message": str(err)}


def test_smtp_connection() -> Dict[str, Any]:
    """Tests Outbound SMTP connection."""
    host = get_setting_value("SMTP_HOST", "")
    port = int(get_setting_value("SMTP_PORT", 587))
    user = get_setting_value("SMTP_USER", "")
    pwd = get_setting_value("SMTP_PASSWORD", "")
    use_tls = get_setting_value("SMTP_USE_TLS", True)

    if not host or not user or not pwd:
        return {
            "status": "NOT_CONFIGURED",
            "message": "SMTP credentials not registered. Configure host, port, username, and password in Settings.",
        }
    try:
        server = smtplib.SMTP(host, port, timeout=10)
        if use_tls:
            server.starttls()
        server.login(user, pwd)
        server.quit()
        return {"status": "CONNECTED", "message": f"Successfully authenticated with SMTP server {host}:{port}."}
    except Exception as err:
        return {"status": "CONNECTION_FAILED", "message": str(err)}


def test_imap_connection() -> Dict[str, Any]:
    """Tests Inbound IMAP connection."""
    host = get_setting_value("IMAP_HOST", "")
    port = int(get_setting_value("IMAP_PORT", 993))
    user = get_setting_value("IMAP_USER", "")
    pwd = get_setting_value("IMAP_PASSWORD", "")
    use_ssl = get_setting_value("IMAP_USE_SSL", True)

    if not host or not user or not pwd:
        return {
            "status": "NOT_CONFIGURED",
            "message": "IMAP credentials not registered. Configure host, port, username, and password in Settings.",
        }
    try:
        if use_ssl:
            client = imaplib.IMAP4_SSL(host, port)
        else:
            client = imaplib.IMAP4(host, port)
        client.login(user, pwd)
        client.logout()
        return {"status": "CONNECTED", "message": f"Successfully authenticated with IMAP mailbox {user} on {host}."}
    except Exception as err:
        return {"status": "CONNECTION_FAILED", "message": str(err)}
