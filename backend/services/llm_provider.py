"""Provider abstraction layer for Zero-Cost LLM completions & reasoning.

Enforces strict zero-cost billing safety:
1. Model ID != Free Account: Requires BOTH free-eligible model AND verified non-billing account mode.
2. Google Gemini Developer API: Requires GEMINI_ACCOUNT_MODE=FREE_NO_BILLING. (Default UNVERIFIED blocks real dispatch).
3. Groq Cloud: Requires GROQ_ACCOUNT_MODE=FREE. (Default UNVERIFIED blocks real dispatch).
4. Cloudflare Workers AI: Requires CLOUDFLARE_ACCOUNT_MODE=FREE. (Paid accounts without spend ceilings are blocked).
5. OpenRouter: Requires OPENROUTER_ACCOUNT_MODE=FREE and model suffix ':free'.
6. Retired model quarantine: Retired models (such as gemini-2.0-flash) are blocked with MODEL_REMOVED.
7. Quota integrity: Quotas are tracked from provider response headers or marked UNKNOWN. No invented limits.
8. Persistent reasoning cache (LLMReasoningCache) prevents duplicate inference.
9. Hallucinated LLM reasoning CANNOT override failed deterministic evidence gates.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
import hashlib
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional

import requests

from config import settings
from services.settings_manager import get_setting_value

logger = logging.getLogger(__name__)

# ── Status & Policy Constants ───────────────────────────────────────────────
LLM_COST_POLICY_ZERO_COST = "ZERO_COST_ONLY"
LLM_STATUS_AVAILABLE = "AVAILABLE"
LLM_STATUS_RATE_LIMITED = "RATE_LIMITED"
LLM_STATUS_QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"
LLM_STATUS_MODEL_REMOVED = "MODEL_REMOVED"
LLM_STATUS_UNAVAILABLE = "UNAVAILABLE"
LLM_STATUS_MISCONFIGURED = "MISCONFIGURED"
LLM_STATUS_FREE_CAPACITY_EXHAUSTED = "FREE_CAPACITY_EXHAUSTED"
LLM_PROVIDER_NOT_ALLOWED = "LLM_PROVIDER_NOT_ALLOWED"

PROVIDER_BILLING_STATUS_UNVERIFIED = "PROVIDER_BILLING_STATUS_UNVERIFIED"
PROVIDER_ACCOUNT_MODE_PAID_BLOCKED = "PROVIDER_ACCOUNT_MODE_PAID_BLOCKED"


# ── Allowed & Disallowed Task Scopes ────────────────────────────────────────
ALLOWED_LLM_TASKS = {
    "TRIGGER_INTERPRETATION",
    "FACILITY_LINK_REASONING",
    "CALIBRATION_CONSEQUENCE_REASONING",
    "PERSON_COMPARISON",
    "CONTRADICTORY_EVIDENCE",
    "HIGH_VALUE_LEAD_REVIEW",
}

DISALLOWED_LLM_TASKS = {
    "DATE_COMPARISON",
    "PHONE_VALIDATION",
    "EMAIL_TYPE_CLASSIFICATION",
    "DEDUPLICATION",
    "NABL_SCOPE_MATCH",
    "APOLLO_CREDIT_GATE",
    "ARITHMETIC",
}


# ── Retired Models (Explicitly Disallowed & Quarantined) ────────────────────
RETIRED_MODELS: set[str] = {
    "gemini-2.0-flash",
    "gemini-2.0-flash-exp",
    "gemini-1.0-pro",
    "gemini-pro",
    "llama-3.3-70b-versatile",  # Deprecated on Groq developer free tier as of Aug 2026
    "llama-3.1-8b-instant",      # Deprecated on Groq developer free tier
}


# ── Verified Free Model Whitelist (Active 2026 Models) ─────────────────────
VERIFIED_FREE_MODELS: dict[str, dict[str, Any]] = {
    "gemini": {
        "gemini-3.8-flash": {"free_allowed": True, "structured": True, "context": 1048576},
        "gemini-3.7-flash": {"free_allowed": True, "structured": True, "context": 1048576},
        "gemini-3.6-flash": {"free_allowed": True, "structured": True, "context": 1048576},
        "gemini-3.5-flash": {"free_allowed": True, "structured": True, "context": 1048576},
        "gemini-3.5-flash-lite": {"free_allowed": True, "structured": True, "context": 1048576},
        "gemini-3.1-flash-lite": {"free_allowed": True, "structured": True, "context": 1048576},
    },
    "groq": {
        "openai/gpt-oss-120b": {"free_allowed": True, "structured": True, "context": 131072},
        "openai/gpt-oss-20b": {"free_allowed": True, "structured": True, "context": 131072},
        "qwen/qwen-2.5-72b-instruct": {"free_allowed": True, "structured": True, "context": 131072},
        "qwen/qwen-2.5-coder-32b": {"free_allowed": True, "structured": True, "context": 131072},
    },
    "cloudflare": {
        "@cf/meta/llama-3.1-8b-instruct": {"free_allowed": True, "structured": True, "context": 32768},
        "@cf/meta/llama-3-8b-instruct": {"free_allowed": True, "structured": True, "context": 8192},
    },
    "openrouter": {
        # Dynamically validated: any model ending with ":free" or "openrouter/free"
    },
}


class QuotaExhaustedError(RuntimeError):
    """Raised when a provider hits rate limit or quota exhaustion (HTTP 429)."""
    def __init__(self, message: str, retry_after: Optional[int] = None):
        super().__init__(message)
        self.retry_after = retry_after


class LLMProviderNotAllowedError(RuntimeError):
    """Raised when an unapproved, paid, retired, or billing-unverified provider/model is requested."""
    pass


# ── Account Mode & Billing Safety Verifier ──────────────────────────────────
def verify_provider_billing_mode(provider_name: str) -> tuple[bool, str]:
    """Verify whether a provider credentials/project are confirmed non-billing/free.
    Under ZERO_COST_ONLY:
    - Default UNVERIFIED returns False (must block real dispatch)
    - PAID returns False (strictly blocked)
    - FREE_NO_BILLING (Gemini) or FREE returns True
    """
    allow_paid = bool(get_setting_value("ALLOW_PAID_LLM", False))
    cost_policy = str(get_setting_value("LLM_COST_POLICY", LLM_COST_POLICY_ZERO_COST)).strip()

    if allow_paid and cost_policy != LLM_COST_POLICY_ZERO_COST:
        return True, "PAID_ALLOWED"

    p = (provider_name or "").lower().strip()

    if p in ("openai", "chatgpt"):
        return False, "PAID_OPENAI_BLOCKED"

    if p in ("gemini", "google"):
        mode = str(get_setting_value("GEMINI_ACCOUNT_MODE", "UNVERIFIED")).strip().upper()
        if mode == "FREE_NO_BILLING":
            return True, "FREE_NO_BILLING"
        elif mode == "PAID":
            return False, PROVIDER_ACCOUNT_MODE_PAID_BLOCKED
        return False, PROVIDER_BILLING_STATUS_UNVERIFIED

    if p == "groq":
        mode = str(get_setting_value("GROQ_ACCOUNT_MODE", "UNVERIFIED")).strip().upper()
        if mode == "FREE":
            return True, "FREE"
        elif mode == "PAID":
            return False, PROVIDER_ACCOUNT_MODE_PAID_BLOCKED
        return False, PROVIDER_BILLING_STATUS_UNVERIFIED

    if p == "cloudflare":
        mode = str(get_setting_value("CLOUDFLARE_ACCOUNT_MODE", "UNVERIFIED")).strip().upper()
        if mode == "FREE":
            return True, "FREE"
        elif mode == "PAID":
            return False, PROVIDER_ACCOUNT_MODE_PAID_BLOCKED
        return False, PROVIDER_BILLING_STATUS_UNVERIFIED

    if p == "openrouter":
        mode = str(get_setting_value("OPENROUTER_ACCOUNT_MODE", "UNVERIFIED")).strip().upper()
        if mode == "FREE":
            return True, "FREE"
        elif mode == "PAID":
            return False, PROVIDER_ACCOUNT_MODE_PAID_BLOCKED
        return False, PROVIDER_BILLING_STATUS_UNVERIFIED

    return False, "UNKNOWN_PROVIDER"


def is_cost_allowed(provider_name: str, model_name: str) -> bool:
    """Strictly enforce ZERO_COST_ONLY policy.
    Requires BOTH:
    A. Provider account mode is explicitly verified as non-billing/free.
    B. Model is not retired and is eligible for free use.
    """
    allow_paid = bool(get_setting_value("ALLOW_PAID_LLM", False))
    cost_policy = str(get_setting_value("LLM_COST_POLICY", LLM_COST_POLICY_ZERO_COST)).strip()

    if allow_paid and cost_policy != LLM_COST_POLICY_ZERO_COST:
        return True

    # 1. Verify account billing status
    account_verified, reason = verify_provider_billing_mode(provider_name)
    if not account_verified:
        return False

    p = (provider_name or "").lower().strip()
    m = (model_name or "").strip()

    # 2. Check for retired models
    if m in RETIRED_MODELS:
        return False

    # 3. Model eligibility per provider
    if p in ("gemini", "google"):
        return m in VERIFIED_FREE_MODELS["gemini"] or (("3." in m or "flash" in m.lower()) and m not in RETIRED_MODELS)

    if p == "groq":
        return m in VERIFIED_FREE_MODELS["groq"] or (m not in RETIRED_MODELS and bool(m))

    if p == "cloudflare":
        return m.startswith("@cf/")

    if p == "openrouter":
        return m.endswith(":free") or m == "openrouter/free"

    return False


def evaluate_llm_task_allowed(task_type: str) -> bool:
    """Verify whether a Salesoorja task is eligible for LLM semantic reasoning."""
    t = (task_type or "").upper().strip()
    if t in DISALLOWED_LLM_TASKS:
        return False
    return t in ALLOWED_LLM_TASKS


def apply_reasoning_to_gate(deterministic_passed: bool, llm_reasoning: dict[str, Any]) -> dict[str, Any]:
    """Ensure hard deterministic gates remain authoritative.
    An LLM cannot fabricate evidence to turn a failed hard gate into a pass.
    """
    if not deterministic_passed:
        return {
            "passed": False,
            "gate_decision": "FAILED_DETERMINISTIC",
            "reason": "Deterministic gate failed; LLM semantic interpretation cannot override hard evidence rules.",
            "llm_applied": False,
            "llm_reasoning": llm_reasoning,
        }
    return {
        "passed": bool(llm_reasoning.get("decision") in ("STRONG", "PASS", "QUALIFIED")),
        "gate_decision": llm_reasoning.get("decision", "HOLD"),
        "confidence": float(llm_reasoning.get("confidence", 0.7)),
        "reason": str(llm_reasoning.get("reason", "Passed with LLM verification.")),
        "llm_applied": True,
        "llm_reasoning": llm_reasoning,
    }


# ── Dynamic Quota Tracker (No Hardcoded Numbers) ───────────────────────────
@dataclass
class ProviderQuotaInfo:
    rpm: Optional[int] = None
    rpd: Optional[int] = None
    tpm: Optional[int] = None
    tpd: Optional[int] = None
    remaining_requests: Optional[int] = None
    remaining_tokens: Optional[int] = None
    reset_time: Optional[str] = None
    source: str = "UNKNOWN"


class DynamicQuotaTracker:
    def __init__(self):
        self._quotas: dict[str, ProviderQuotaInfo] = {}

    def update_from_headers(self, provider: str, headers: dict[str, str]):
        info = self._quotas.setdefault(provider, ProviderQuotaInfo())
        found = False
        for k, v in headers.items():
            k_lower = k.lower()
            if "remaining-requests" in k_lower and v.isdigit():
                info.remaining_requests = int(v)
                found = True
            elif "remaining-tokens" in k_lower and v.isdigit():
                info.remaining_tokens = int(v)
                found = True
            elif "limit-requests" in k_lower and v.isdigit():
                info.rpd = int(v)
                found = True
            elif "reset" in k_lower:
                info.reset_time = str(v)
                found = True
        if found:
            info.source = "RESPONSE_HEADERS"

    def get_quota(self, provider: str) -> ProviderQuotaInfo:
        return self._quotas.get(provider, ProviderQuotaInfo(source="UNKNOWN"))


quota_tracker = DynamicQuotaTracker()


# ── Response Data Structure ─────────────────────────────────────────────────
@dataclass
class LLMResponse:
    text: str
    usage: dict[str, int] = field(default_factory=lambda: {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0})
    provider: str = "unknown"
    model: str = "unknown"
    raw_response: Any = None
    cache_hit: bool = False
    status: str = LLM_STATUS_AVAILABLE
    quota: Optional[ProviderQuotaInfo] = None

    def parse_json(self) -> Optional[dict[str, Any]]:
        """Safely parse JSON response from LLM text."""
        raw = self.text.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            raw = "\n".join(lines).strip()
        try:
            return json.loads(raw)
        except Exception:
            start = raw.find("{")
            end = raw.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(raw[start:end + 1])
                except Exception:
                    pass
            start_arr = raw.find("[")
            end_arr = raw.rfind("]")
            if start_arr != -1 and end_arr != -1 and end_arr > start_arr:
                try:
                    return json.loads(raw[start_arr:end_arr + 1])
                except Exception:
                    pass
            logger.warning(f"Failed to parse JSON from LLM text: {raw[:200]}")
            return None


# ── Provider Abstract Base Class ────────────────────────────────────────────
class LLMProvider(ABC):
    @abstractmethod
    def complete(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 1500,
        response_format: Optional[str] = None,
    ) -> LLMResponse:
        """Execute a chat completion request."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this provider is configured and allowed under current cost policy."""
        pass

    def get_status(self) -> str:
        """Return provider health / rate limit status."""
        return getattr(self, "_status", LLM_STATUS_AVAILABLE)


# ── 1. Google Gemini Developer API Free Tier ────────────────────────────────
def _normalize_gemini_model(model_name: Optional[str]) -> str:
    """Normalize model names to active 2026 Gemini Flash API identifiers."""
    if not model_name:
        return "gemini-3.7-flash"
    m = model_name.strip().lower()
    if "2.0" in m or "2" in m:
        return "gemini-2.0-flash"  # Will be rejected by retired check
    if "3.8" in m:
        return "gemini-3.8-flash"
    if "3.7" in m:
        return "gemini-3.7-flash"
    if "3.6" in m:
        return "gemini-3.6-flash"
    if "3.5" in m:
        return "gemini-3.5-flash"
    if "gemini" in m:
        return model_name.strip()
    return "gemini-3.7-flash"


class GeminiProvider(LLMProvider):
    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        if api_key is not None:
            self.api_key = api_key
        else:
            self.api_key = str(get_setting_value("GOOGLE_API_KEY", "")).strip() or str(get_setting_value("GEMINI_API_KEY", "")).strip()
        raw_model = model_name or str(get_setting_value("ORCHESTRATOR_GEMINI_MODEL", "")).strip() or "gemini-3.7-flash"
        self.model_name = _normalize_gemini_model(raw_model)
        self._status = LLM_STATUS_AVAILABLE
        self._retry_after_until: Optional[float] = None

    def is_available(self) -> bool:
        if self.model_name in RETIRED_MODELS:
            self._status = LLM_STATUS_MODEL_REMOVED
            return False
        if not is_cost_allowed("gemini", self.model_name):
            return False
        if self._retry_after_until and time.time() < self._retry_after_until:
            return False
        return bool(
            self.api_key
            and not self.api_key.startswith("mock_")
            and not self.api_key.startswith("YOUR_")
            and len(self.api_key) > 10
        )

    def complete(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 1500,
        response_format: Optional[str] = None,
    ) -> LLMResponse:
        if self.model_name in RETIRED_MODELS:
            self._status = LLM_STATUS_MODEL_REMOVED
            raise LLMProviderNotAllowedError(
                f"{LLM_STATUS_MODEL_REMOVED}: Model '{self.model_name}' has been retired by Google. Use current gemini-3.7-flash or active models."
            )

        account_verified, reason = verify_provider_billing_mode("gemini")
        if not account_verified:
            raise LLMProviderNotAllowedError(
                f"{reason}: Gemini account mode is '{get_setting_value('GEMINI_ACCOUNT_MODE', 'UNVERIFIED')}'. "
                f"Requires explicit 'GEMINI_ACCOUNT_MODE=FREE_NO_BILLING' under ZERO_COST_ONLY."
            )

        if not is_cost_allowed("gemini", self.model_name):
            raise LLMProviderNotAllowedError(f"Gemini model {self.model_name} is not permitted under ZERO_COST_ONLY policy.")

        if not self.is_available():
            if self._retry_after_until and time.time() < self._retry_after_until:
                raise QuotaExhaustedError(f"GeminiProvider is rate-limited until {self._retry_after_until}")
            raise RuntimeError("GeminiProvider is not available (GOOGLE_API_KEY missing or unconfigured).")

        contents = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": msg["content"]}]})

        if not contents:
            contents = [{"role": "user", "parts": [{"text": "Hello"}]}]

        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        if system_prompt:
            payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}
        if response_format == "json":
            payload["generationConfig"]["responseMimeType"] = "application/json"

        models_to_try = [self.model_name]
        for fallback_m in ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash"]:
            if fallback_m not in models_to_try and is_cost_allowed("gemini", fallback_m):
                models_to_try.append(fallback_m)

        last_err = None
        for m in models_to_try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={self.api_key}"
            try:
                resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=30)
                quota_tracker.update_from_headers("gemini", dict(resp.headers))

                if resp.status_code == 200:
                    data = resp.json()
                    candidates = data.get("candidates", [])
                    text = ""
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            text = parts[0].get("text", "")

                    usage_meta = data.get("usageMetadata", {})
                    input_tokens = usage_meta.get("promptTokenCount", 0)
                    output_tokens = usage_meta.get("candidatesTokenCount", 0)

                    self._status = LLM_STATUS_AVAILABLE
                    self._retry_after_until = None

                    return LLMResponse(
                        text=text or "",
                        usage={
                            "input_tokens": input_tokens,
                            "output_tokens": output_tokens,
                            "total_tokens": input_tokens + output_tokens,
                        },
                        provider="gemini",
                        model=m,
                        raw_response=data,
                        status=LLM_STATUS_AVAILABLE,
                        quota=quota_tracker.get_quota("gemini"),
                    )
                elif resp.status_code == 429:
                    self._status = LLM_STATUS_RATE_LIMITED
                    retry_header = resp.headers.get("Retry-After")
                    retry_seconds = int(retry_header) if retry_header and retry_header.isdigit() else 60
                    self._retry_after_until = time.time() + retry_seconds
                    raise QuotaExhaustedError(f"Gemini quota exhausted (HTTP 429): {resp.text}", retry_after=retry_seconds)
                else:
                    last_err = f"HTTP {resp.status_code}: {resp.text}"
            except QuotaExhaustedError:
                raise
            except Exception as e:
                last_err = str(e)

        raise RuntimeError(f"Gemini API request failed: {last_err}")


# ── 2. Groq Cloud Free Tier Provider ────────────────────────────────────────
class GroqProvider(LLMProvider):
    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        if api_key is not None:
            self.api_key = api_key
        else:
            self.api_key = str(get_setting_value("GROQ_API_KEY", "")).strip()
        self.model_name = model_name or str(get_setting_value("GROQ_MODEL", "")).strip() or "openai/gpt-oss-20b"
        self._status = LLM_STATUS_AVAILABLE
        self._retry_after_until: Optional[float] = None

    def is_available(self) -> bool:
        if self.model_name in RETIRED_MODELS:
            self._status = LLM_STATUS_MODEL_REMOVED
            return False
        if not is_cost_allowed("groq", self.model_name):
            return False
        if self._retry_after_until and time.time() < self._retry_after_until:
            return False
        return bool(
            self.api_key
            and not self.api_key.startswith("mock_")
            and not self.api_key.startswith("YOUR_")
            and len(self.api_key) > 10
        )

    def complete(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 1500,
        response_format: Optional[str] = None,
    ) -> LLMResponse:
        if self.model_name in RETIRED_MODELS:
            self._status = LLM_STATUS_MODEL_REMOVED
            raise LLMProviderNotAllowedError(f"{LLM_STATUS_MODEL_REMOVED}: Model '{self.model_name}' has been deprecated on Groq.")

        account_verified, reason = verify_provider_billing_mode("groq")
        if not account_verified:
            raise LLMProviderNotAllowedError(
                f"{reason}: Groq account mode is '{get_setting_value('GROQ_ACCOUNT_MODE', 'UNVERIFIED')}'. "
                f"Requires explicit 'GROQ_ACCOUNT_MODE=FREE' under ZERO_COST_ONLY."
            )

        if not is_cost_allowed("groq", self.model_name):
            raise LLMProviderNotAllowedError(f"Groq model {self.model_name} is not permitted.")

        if not self.is_available():
            if self._retry_after_until and time.time() < self._retry_after_until:
                raise QuotaExhaustedError(f"GroqProvider is rate-limited until {self._retry_after_until}")
            raise RuntimeError("GroqProvider is not available (GROQ_API_KEY missing or unconfigured).")

        formatted_messages = []
        if system_prompt:
            formatted_messages.append({"role": "system", "content": system_prompt})
        for msg in messages:
            formatted_messages.append({"role": msg["role"], "content": msg["content"]})

        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": formatted_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format == "json":
            payload["response_format"] = {"type": "json_object"}

        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=30)
            quota_tracker.update_from_headers("groq", dict(resp.headers))

            if resp.status_code == 200:
                data = resp.json()
                choices = data.get("choices", [])
                text = choices[0].get("message", {}).get("content", "") if choices else ""
                usage = data.get("usage", {})
                input_tokens = usage.get("prompt_tokens", 0)
                output_tokens = usage.get("completion_tokens", 0)

                self._status = LLM_STATUS_AVAILABLE
                self._retry_after_until = None

                return LLMResponse(
                    text=text or "",
                    usage={
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "total_tokens": input_tokens + output_tokens,
                    },
                    provider="groq",
                    model=self.model_name,
                    raw_response=data,
                    status=LLM_STATUS_AVAILABLE,
                    quota=quota_tracker.get_quota("groq"),
                )
            elif resp.status_code == 429:
                self._status = LLM_STATUS_RATE_LIMITED
                retry_header = resp.headers.get("Retry-After")
                retry_seconds = int(retry_header) if retry_header and retry_header.isdigit() else 30
                self._retry_after_until = time.time() + retry_seconds
                raise QuotaExhaustedError(f"Groq quota exhausted (HTTP 429): {resp.text}", retry_after=retry_seconds)
            else:
                raise RuntimeError(f"Groq API HTTP {resp.status_code}: {resp.text}")
        except QuotaExhaustedError:
            raise
        except Exception as e:
            raise RuntimeError(f"Groq API call error: {e}")


# ── 3. OpenRouter Free Tier Provider (Requires :free Model Suffix) ──────────
class OpenRouterProvider(LLMProvider):
    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        if api_key is not None:
            self.api_key = api_key
        else:
            self.api_key = str(get_setting_value("OPENROUTER_API_KEY", "")).strip()
        raw_m = model_name or str(get_setting_value("OPENROUTER_MODEL", "")).strip() or "meta-llama/llama-3.3-70b-instruct:free"
        self.model_name = raw_m
        self._status = LLM_STATUS_AVAILABLE
        self._retry_after_until: Optional[float] = None

    def is_available(self) -> bool:
        if not is_cost_allowed("openrouter", self.model_name):
            return False
        if self._retry_after_until and time.time() < self._retry_after_until:
            return False
        return bool(
            self.api_key
            and not self.api_key.startswith("mock_")
            and not self.api_key.startswith("YOUR_")
            and len(self.api_key) > 10
        )

    def complete(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 1500,
        response_format: Optional[str] = None,
    ) -> LLMResponse:
        account_verified, reason = verify_provider_billing_mode("openrouter")
        if not account_verified:
            raise LLMProviderNotAllowedError(
                f"{reason}: OpenRouter account mode is '{get_setting_value('OPENROUTER_ACCOUNT_MODE', 'UNVERIFIED')}'. "
                f"Requires explicit 'OPENROUTER_ACCOUNT_MODE=FREE' under ZERO_COST_ONLY."
            )

        if not is_cost_allowed("openrouter", self.model_name):
            raise LLMProviderNotAllowedError(
                f"LLM_PROVIDER_NOT_ALLOWED: Model '{self.model_name}' on OpenRouter must end with ':free' under ZERO_COST_ONLY policy."
            )

        if not self.is_available():
            if self._retry_after_until and time.time() < self._retry_after_until:
                raise QuotaExhaustedError(f"OpenRouterProvider is rate-limited until {self._retry_after_until}")
            raise RuntimeError("OpenRouterProvider is not available (OPENROUTER_API_KEY missing or unconfigured).")

        formatted_messages = []
        if system_prompt:
            formatted_messages.append({"role": "system", "content": system_prompt})
        for msg in messages:
            formatted_messages.append({"role": msg["role"], "content": msg["content"]})

        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": formatted_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format == "json":
            payload["response_format"] = {"type": "json_object"}

        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://salesoorja.local",
            "X-Title": "Salesoorja Zero-Cost Intelligence",
        }

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=30)
            quota_tracker.update_from_headers("openrouter", dict(resp.headers))

            if resp.status_code == 200:
                data = resp.json()
                choices = data.get("choices", [])
                text = choices[0].get("message", {}).get("content", "") if choices else ""
                usage = data.get("usage", {})
                input_tokens = usage.get("prompt_tokens", 0)
                output_tokens = usage.get("completion_tokens", 0)

                self._status = LLM_STATUS_AVAILABLE
                self._retry_after_until = None

                return LLMResponse(
                    text=text or "",
                    usage={
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "total_tokens": input_tokens + output_tokens,
                    },
                    provider="openrouter",
                    model=self.model_name,
                    raw_response=data,
                    status=LLM_STATUS_AVAILABLE,
                    quota=quota_tracker.get_quota("openrouter"),
                )
            elif resp.status_code in (402, 403):
                self._status = LLM_STATUS_QUOTA_EXHAUSTED
                raise LLMProviderNotAllowedError(f"OpenRouter free model quota unavailable (HTTP {resp.status_code}): {resp.text}")
            elif resp.status_code == 429:
                self._status = LLM_STATUS_RATE_LIMITED
                retry_header = resp.headers.get("Retry-After")
                retry_seconds = int(retry_header) if retry_header and retry_header.isdigit() else 30
                self._retry_after_until = time.time() + retry_seconds
                raise QuotaExhaustedError(f"OpenRouter quota exhausted (HTTP 429): {resp.text}", retry_after=retry_seconds)
            else:
                raise RuntimeError(f"OpenRouter API HTTP {resp.status_code}: {resp.text}")
        except (QuotaExhaustedError, LLMProviderNotAllowedError):
            raise
        except Exception as e:
            raise RuntimeError(f"OpenRouter API call error: {e}")


# ── 4. Cloudflare Workers AI Free Tier Provider ────────────────────────────
class CloudflareProvider(LLMProvider):
    def __init__(self, account_id: Optional[str] = None, api_token: Optional[str] = None, model_name: Optional[str] = None):
        if account_id is not None:
            self.account_id = account_id
        else:
            self.account_id = str(get_setting_value("CLOUDFLARE_ACCOUNT_ID", "")).strip()
        if api_token is not None:
            self.api_token = api_token
        else:
            self.api_token = str(get_setting_value("CLOUDFLARE_API_TOKEN", "")).strip()
        self.model_name = model_name or str(get_setting_value("CLOUDFLARE_MODEL", "")).strip() or "@cf/meta/llama-3.1-8b-instruct"
        self._status = LLM_STATUS_AVAILABLE
        self._retry_after_until: Optional[float] = None

    def is_available(self) -> bool:
        if not is_cost_allowed("cloudflare", self.model_name):
            return False
        if self._retry_after_until and time.time() < self._retry_after_until:
            return False
        return bool(
            self.account_id
            and self.api_token
            and not self.api_token.startswith("mock_")
            and not self.api_token.startswith("YOUR_")
            and len(self.api_token) > 10
        )

    def complete(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 1500,
        response_format: Optional[str] = None,
    ) -> LLMResponse:
        account_verified, reason = verify_provider_billing_mode("cloudflare")
        if not account_verified:
            raise LLMProviderNotAllowedError(
                f"{reason}: Cloudflare account mode is '{get_setting_value('CLOUDFLARE_ACCOUNT_MODE', 'UNVERIFIED')}'. "
                f"Paid Cloudflare accounts incur charges beyond 10,000 neurons without a spend ceiling. Blocked under ZERO_COST_ONLY."
            )

        if not is_cost_allowed("cloudflare", self.model_name):
            raise LLMProviderNotAllowedError(f"Cloudflare model {self.model_name} is not permitted.")

        if not self.is_available():
            if self._retry_after_until and time.time() < self._retry_after_until:
                raise QuotaExhaustedError(f"CloudflareProvider is rate-limited until {self._retry_after_until}")
            raise RuntimeError("CloudflareProvider is not available (CLOUDFLARE_ACCOUNT_ID or CLOUDFLARE_API_TOKEN missing).")

        formatted_messages = []
        if system_prompt:
            formatted_messages.append({"role": "system", "content": system_prompt})
        for msg in messages:
            formatted_messages.append({"role": msg["role"], "content": msg["content"]})

        payload = {
            "messages": formatted_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        url = f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/ai/run/{self.model_name}"
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                result = data.get("result", {})
                text = result.get("response", "") if isinstance(result, dict) else str(result)
                self._status = LLM_STATUS_AVAILABLE
                self._retry_after_until = None
                return LLMResponse(
                    text=text or "",
                    usage={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
                    provider="cloudflare",
                    model=self.model_name,
                    raw_response=data,
                    status=LLM_STATUS_AVAILABLE,
                    quota=quota_tracker.get_quota("cloudflare"),
                )
            elif resp.status_code == 429:
                self._status = LLM_STATUS_RATE_LIMITED
                retry_header = resp.headers.get("Retry-After")
                retry_seconds = int(retry_header) if retry_header and retry_header.isdigit() else 60
                self._retry_after_until = time.time() + retry_seconds
                raise QuotaExhaustedError(f"Cloudflare quota exhausted (HTTP 429): {resp.text}", retry_after=retry_seconds)
            else:
                raise RuntimeError(f"Cloudflare API HTTP {resp.status_code}: {resp.text}")
        except QuotaExhaustedError:
            raise
        except Exception as e:
            raise RuntimeError(f"Cloudflare API call error: {e}")


# ── 5. OpenAI Provider (Retained for Manual Use; Blocked under Zero-Cost) ───
class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        if api_key is not None:
            self.api_key = api_key
        else:
            self.api_key = str(get_setting_value("OPENAI_API_KEY", "")).strip()
        self.model_name = model_name or str(get_setting_value("OPENAI_MODEL", "")).strip() or "gpt-4o"

    def is_available(self) -> bool:
        # Strictly enforce ZERO_COST_ONLY: OpenAI is a paid API and must NEVER be selected automatically
        if not is_cost_allowed("openai", self.model_name):
            return False
        return bool(
            self.api_key
            and not self.api_key.startswith("mock_")
            and not self.api_key.startswith("YOUR_")
            and "test-sample" not in self.api_key
            and len(self.api_key) > 10
        )

    def complete(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 1500,
        response_format: Optional[str] = None,
    ) -> LLMResponse:
        if not is_cost_allowed("openai", self.model_name):
            raise LLMProviderNotAllowedError(
                "LLM_PROVIDER_NOT_ALLOWED: Paid OpenAI is blocked under ZERO_COST_ONLY policy."
            )

        if not self.is_available():
            raise RuntimeError("OpenAIProvider is not available (OPENAI_API_KEY missing or unconfigured).")

        formatted_messages = []
        if system_prompt:
            formatted_messages.append({"role": "system", "content": system_prompt})
        for msg in messages:
            formatted_messages.append({"role": msg["role"], "content": msg["content"]})

        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": formatted_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format == "json":
            payload["response_format"] = {"type": "json_object"}

        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        resp = requests.post(url, json=payload, headers=headers, timeout=30)
        if resp.status_code != 200:
            raise RuntimeError(f"OpenAI API HTTP {resp.status_code}: {resp.text}")

        data = resp.json()
        choices = data.get("choices", [])
        text = choices[0].get("message", {}).get("content", "") if choices else ""
        usage = data.get("usage", {})
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)

        return LLMResponse(
            text=text or "",
            usage={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
            },
            provider="openai",
            model=self.model_name,
            raw_response=data,
            status=LLM_STATUS_AVAILABLE,
        )


# ── 6. Persistent Reasoning Cache ──────────────────────────────────────────
class LLMReasoningCache:
    """Aggressive persistent disk cache for structured semantic reasoning queries."""

    def __init__(self, cache_dir: Optional[str] = None, ttl_days: int = 30):
        self.cache_dir = cache_dir or getattr(settings, "LLM_CACHE_DIR", "data/llm_cache")
        self.ttl_days = ttl_days or getattr(settings, "LLM_CACHE_TTL_DAYS", 30)
        self.enabled = getattr(settings, "LLM_CACHE_ENABLED", True)
        self._memory_cache: dict[str, dict[str, Any]] = {}
        self._cache_file = os.path.join(self.cache_dir, "reasoning_cache.json")
        self._load_cache()

    def _load_cache(self):
        if not self.enabled:
            return
        try:
            if os.path.exists(self._cache_file):
                with open(self._cache_file, "r", encoding="utf-8") as f:
                    self._memory_cache = json.load(f)
        except Exception as e:
            logger.warning("Failed to load LLM reasoning cache: %s", e)
            self._memory_cache = {}

    def _save_cache(self):
        if not self.enabled:
            return
        try:
            os.makedirs(self.cache_dir, exist_ok=True)
            with open(self._cache_file, "w", encoding="utf-8") as f:
                json.dump(self._memory_cache, f, indent=2)
        except Exception as e:
            logger.warning("Failed to save LLM reasoning cache: %s", e)

    @staticmethod
    def compute_key(task_type: str, company: str, facility: str, evidence: Any, schema_version: str = "v1") -> str:
        canonical_evidence = json.dumps(evidence, sort_keys=True, default=str) if isinstance(evidence, (dict, list)) else str(evidence)
        raw_key = f"{task_type.upper().strip()}:{company.lower().strip()}:{facility.lower().strip()}:{schema_version}:{canonical_evidence}"
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    def get(self, task_type: str, company: str, facility: str, evidence: Any, schema_version: str = "v1") -> Optional[dict[str, Any]]:
        if not self.enabled:
            return None
        key = self.compute_key(task_type, company, facility, evidence, schema_version)
        entry = self._memory_cache.get(key)
        if not entry:
            return None

        # Check TTL
        created_at = entry.get("timestamp")
        if created_at:
            try:
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(created_at)).total_seconds()
                if age > self.ttl_days * 86400:
                    del self._memory_cache[key]
                    return None
            except Exception:
                pass

        return entry

    def set(
        self,
        task_type: str,
        company: str,
        facility: str,
        evidence: Any,
        output: Any,
        provider: str,
        model: str,
        tokens_used: Optional[dict[str, int]] = None,
        schema_version: str = "v1",
    ):
        if not self.enabled:
            return
        key = self.compute_key(task_type, company, facility, evidence, schema_version)
        self._memory_cache[key] = {
            "task_type": task_type,
            "company": company,
            "facility": facility,
            "output": output,
            "provider": provider,
            "model": model,
            "tokens_used": tokens_used or {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "CACHED",
        }
        self._save_cache()

    def clear(self):
        self._memory_cache.clear()
        if os.path.exists(self._cache_file):
            try:
                os.remove(self._cache_file)
            except Exception:
                pass


llm_reasoning_cache = LLMReasoningCache()


# ── 7. Fallback & Zero-Cost Router Provider ─────────────────────────────────
class FallbackLLMProvider(LLMProvider):
    """Router supporting a chain of prioritized free providers with automatic failover."""

    def __init__(self, primary: Optional[LLMProvider] = None, fallback: Optional[LLMProvider] = None, providers: Optional[list[LLMProvider]] = None):
        if providers:
            self.providers = providers
        else:
            self.providers = [p for p in [primary, fallback] if p is not None]

    def is_available(self) -> bool:
        return any(p.is_available() for p in self.providers)

    def complete(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 1500,
        response_format: Optional[str] = None,
    ) -> LLMResponse:
        errors = []
        for p in self.providers:
            if not p.is_available():
                continue
            try:
                return p.complete(
                    system_prompt=system_prompt,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format=response_format,
                )
            except (QuotaExhaustedError, LLMProviderNotAllowedError) as e:
                logger.warning("Provider %s rate-limited/disallowed: %s. Failing over to next free provider.", p.__class__.__name__, e)
                errors.append(f"{p.__class__.__name__}: {e}")
            except Exception as e:
                logger.warning("Provider %s failed: %s. Failing over to next free provider.", p.__class__.__name__, e)
                errors.append(f"{p.__class__.__name__}: {e}")

        err_msg = "; ".join(errors) if errors else "No configured free providers were available."
        raise QuotaExhaustedError(f"{LLM_STATUS_FREE_CAPACITY_EXHAUSTED}: {err_msg}")


class ZeroCostRouter(FallbackLLMProvider):
    """Default Salesoorja Zero-Cost Provider Router.
    Prioritizes:
    1. Gemini Free (gemini-3.7-flash, non-billing account)
    2. Groq Free (openai/gpt-oss-20b, free plan)
    3. Cloudflare Free (@cf/meta/llama-3.1-8b-instruct, free plan)
    4. OpenRouter Free (:free models only)
    """

    def __init__(self):
        free_chain: list[LLMProvider] = [
            GeminiProvider(),
            GroqProvider(),
            CloudflareProvider(),
            OpenRouterProvider(),
        ]
        super().__init__(providers=free_chain)


# ── 8. Factory Functions ───────────────────────────────────────────────────
def get_provider(provider_name: str) -> LLMProvider:
    """Factory to get an LLM provider by name."""
    name = (provider_name or "").lower().strip()
    if name in ["gemini", "google"]:
        return GeminiProvider()
    if name in ["groq"]:
        return GroqProvider()
    if name in ["openrouter"]:
        return OpenRouterProvider()
    if name in ["cloudflare"]:
        return CloudflareProvider()
    if name in ["openai", "chatgpt"]:
        return OpenAIProvider()
    raise ValueError(f"Unknown LLM provider: {provider_name}")


def get_orchestrator_provider() -> Optional[LLMProvider]:
    """Returns the configured zero-cost orchestrator LLM provider with failover.
    When ALLOW_PAID_LLM=False, OpenAI is strictly omitted from the chain.
    If no free provider API keys are configured or account mode is UNVERIFIED,
    returns None so callers can fall back to deterministic logic without crashing.
    """
    allow_paid = bool(get_setting_value("ALLOW_PAID_LLM", False))
    cost_policy = str(get_setting_value("LLM_COST_POLICY", LLM_COST_POLICY_ZERO_COST)).strip()

    if not allow_paid or cost_policy == LLM_COST_POLICY_ZERO_COST:
        router = ZeroCostRouter()
        if router.is_available():
            return router
        return None

    # Paid-allowed mode (manual legacy support only):
    primary_name = str(get_setting_value("ORCHESTRATOR_PRIMARY_PROVIDER", "gemini")).strip()
    fallback_name = str(get_setting_value("ORCHESTRATOR_FALLBACK_PROVIDER", "openai")).strip()

    try:
        primary = get_provider(primary_name)
    except Exception:
        primary = GeminiProvider()

    try:
        fallback = get_provider(fallback_name)
    except Exception:
        fallback = OpenAIProvider()

    provider = FallbackLLMProvider(primary=primary, fallback=fallback)
    if provider.is_available():
        return provider
    return None


# ── 9. Dual-Model Analyst + Verifier Protocol ──────────────────────────────
def run_analyst_verifier_protocol(
    task_type: str,
    company: str,
    facility: str,
    evidence: Any,
    icp_score: float = 0.0,
    analyst_provider: Optional[LLMProvider] = None,
    verifier_provider: Optional[LLMProvider] = None,
) -> dict[str, Any]:
    """Execute high-value reasoning protocol:
    1. Check cache first.
    2. Model A (Analyst) evaluates evidence -> structured output.
    3. If ICP >= 90 and ambiguity exists, Model B (Verifier) audits conclusion.
    4. If Analyst and Verifier disagree -> result becomes NEEDS_MORE_RESEARCH (never averaged).
    """
    if not evaluate_llm_task_allowed(task_type):
        return {
            "decision": "NOT_ALLOWED",
            "confidence": 0.0,
            "reason": f"Task '{task_type}' is deterministic and not permitted for LLM reasoning.",
            "requires_more_research": False,
            "cache_hit": False,
        }

    # 1. Check cache
    cached = llm_reasoning_cache.get(task_type, company, facility, evidence)
    if cached:
        res = cached["output"]
        if isinstance(res, dict):
            res = dict(res)
            res["cache_hit"] = True
            return res
        return {
            "decision": "CACHED",
            "reason": str(res),
            "confidence": 0.85,
            "cache_hit": True,
        }

    # Obtain providers
    analyst = analyst_provider or get_orchestrator_provider()
    if not analyst or not analyst.is_available():
        return {
            "decision": "HOLD",
            "confidence": 0.5,
            "reason": f"{LLM_STATUS_FREE_CAPACITY_EXHAUSTED}: No free LLM provider available.",
            "requires_more_research": True,
            "cache_hit": False,
        }

    system_prompt = (
        "You are Salesoorja's senior calibration sales intelligence analyst.\n"
        "Analyze the supplied factual evidence strictly without inventing triggers, facilities, people, or capabilities.\n"
        "Return machine-readable JSON with keys:\n"
        "- decision: 'STRONG' | 'BORDERLINE' | 'DISQUALIFIED'\n"
        "- confidence: float between 0.0 and 1.0\n"
        "- reason: concise rationale string\n"
        "- supporting_evidence_ids: list of strings\n"
        "- contradictions: list of contradiction strings\n"
        "- uncertainties: list of uncertainty strings\n"
        "- requires_more_research: boolean\n"
    )

    user_content = {
        "task_type": task_type,
        "company": company,
        "facility": facility,
        "evidence": evidence,
    }

    try:
        analyst_resp = analyst.complete(
            system_prompt=system_prompt,
            messages=[{"role": "user", "content": json.dumps(user_content)}],
            response_format="json",
        )
        parsed = analyst_resp.parse_json()
        if not parsed:
            parsed = {
                "decision": "BORDERLINE",
                "confidence": 0.5,
                "reason": analyst_resp.text[:300],
                "requires_more_research": True,
                "contradictions": [],
                "uncertainties": ["Non-JSON output received from analyst"],
            }
    except (QuotaExhaustedError, LLMProviderNotAllowedError) as e:
        return {
            "decision": "HOLD",
            "confidence": 0.5,
            "reason": f"{LLM_STATUS_FREE_CAPACITY_EXHAUSTED}: {e}",
            "requires_more_research": True,
            "cache_hit": False,
        }
    except Exception as e:
        return {
            "decision": "HOLD",
            "confidence": 0.5,
            "reason": f"Analyst reasoning failed: {e}",
            "requires_more_research": True,
            "cache_hit": False,
        }

    # Check if high-value lead warrants a Verifier call
    has_ambiguity = (
        parsed.get("requires_more_research")
        or bool(parsed.get("contradictions"))
        or float(parsed.get("confidence", 1.0)) < 0.85
        or parsed.get("decision") in ("BORDERLINE", "AMBIGUOUS")
    )

    if float(icp_score or 0) >= 90 and has_ambiguity:
        verifier = verifier_provider or GroqProvider()
        if not verifier.is_available() or verifier.__class__ == analyst.__class__:
            verifier = GroqProvider() if not isinstance(analyst, GroqProvider) else GeminiProvider()

        if verifier.is_available():
            verifier_system = (
                "You are an independent verification auditor for B2B calibration sales leads.\n"
                "Examine the evidence and the Analyst's conclusion.\n"
                "Return JSON with keys:\n"
                "- verdict: 'SUPPORTED' | 'PARTIALLY_SUPPORTED' | 'NOT_SUPPORTED' | 'INSUFFICIENT_EVIDENCE'\n"
                "- critique: concise explanation\n"
            )
            verifier_user = {
                "evidence": evidence,
                "analyst_conclusion": parsed,
            }
            try:
                v_resp = verifier.complete(
                    system_prompt=verifier_system,
                    messages=[{"role": "user", "content": json.dumps(verifier_user)}],
                    response_format="json",
                )
                v_parsed = v_resp.parse_json() or {}
                verdict = v_parsed.get("verdict", "INSUFFICIENT_EVIDENCE")
                parsed["verifier_verdict"] = verdict
                parsed["verifier_critique"] = v_parsed.get("critique", "")

                if verdict in ("NOT_SUPPORTED", "INSUFFICIENT_EVIDENCE"):
                    parsed["decision"] = "NEEDS_MORE_RESEARCH"
                    parsed["requires_more_research"] = True
                    parsed["reason"] = f"Analyst and Verifier disagreed. Verifier verdict: {verdict}. {parsed.get('verifier_critique', '')}"
            except Exception as e:
                logger.warning("Verifier call failed; retaining analyst conclusion with flag: %s", e)
                parsed["verifier_error"] = str(e)

    # Store in cache
    llm_reasoning_cache.set(
        task_type=task_type,
        company=company,
        facility=facility,
        evidence=evidence,
        output=parsed,
        provider=getattr(analyst_resp, "provider", "unknown"),
        model=getattr(analyst_resp, "model", "unknown"),
        tokens_used=getattr(analyst_resp, "usage", None),
    )

    parsed["cache_hit"] = False
    return parsed
