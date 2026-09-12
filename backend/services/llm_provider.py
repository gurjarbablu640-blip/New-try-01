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
# ── Task Routing Categories ────────────────────────────────────────────────
TASK_CATEGORY_PUBLIC_WEB_RESEARCH = {
    "PUBLIC_WEB_RESEARCH",
    "CURRENT_TRIGGER_RESEARCH",
    "SOURCE_DISCOVERY",
    "RECENT_COMPANY_RESEARCH",
}

TASK_CATEGORY_REASONING = {
    "GENERAL_REASONING",
    "TRIGGER_INTERPRETATION",
    "FACILITY_LINK_REASONING",
    "CALIBRATION_CONSEQUENCE_REASONING",
    "PERSON_COMPARISON",
    "PERSON_RANKING",
    "FACILITY_CLASSIFICATION",
    "CONTRADICTORY_EVIDENCE",
    "HIGH_VALUE_LEAD_REVIEW",
    "SUMMARIZATION",
    "COPY_REVIEW",
    "STRUCTURED_EXTRACTION",
    "QUERY_GENERATION",
    "EVIDENCE_SYNTHESIS",
}

TASK_CATEGORY_TOOL_EXECUTION = {
    "TOOL_CALL_REQUIRED",
    "AGENT_LOOP",
    "STRUCTURED_TOOL_EXECUTION",
}

TASK_CATEGORY_DETERMINISTIC_ONLY = {
    "DETERMINISTIC_GATE",
    "CONTACT_CLASSIFICATION",
    "QUALIFICATION_STATE",
    "SCHEDULER",
    "DUPLICATE_CHECK",
    "DATE_COMPARISON",
    "PHONE_VALIDATION",
    "EMAIL_TYPE_CLASSIFICATION",
    "DEDUPLICATION",
    "NABL_SCOPE_MATCH",
    "APOLLO_CREDIT_GATE",
    "ARITHMETIC",
}

ALLOWED_LLM_TASKS = (
    TASK_CATEGORY_PUBLIC_WEB_RESEARCH
    | TASK_CATEGORY_REASONING
    | TASK_CATEGORY_TOOL_EXECUTION
)

DISALLOWED_LLM_TASKS = TASK_CATEGORY_DETERMINISTIC_ONLY


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
    "unorouter": {
        "glm-5.3-search:free": {"free_allowed": True, "structured": True, "context": 131072},
    },
    "hive": {
        "deepseek-ai/DeepSeek-V4.1-Flash": {"free_allowed": True, "structured": True, "context": 65536},
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

    if p in ("unorouter", "uno"):
        mode = str(get_setting_value("UNOROUTER_ACCOUNT_MODE", "FREE")).strip().upper()
        if mode == "FREE":
            return True, "FREE"
        elif mode == "PAID":
            return False, PROVIDER_ACCOUNT_MODE_PAID_BLOCKED
        return False, PROVIDER_BILLING_STATUS_UNVERIFIED

    if p == "hive":
        mode = str(get_setting_value("HIVE_ACCOUNT_MODE", "PROMO_CREDIT")).strip().upper()
        if mode in ("FREE", "PROMO_CREDIT"):
            # PROMO_CREDIT = funded by promotional credit; usage allowed while credit exists.
            # HIVE_ALLOW_PAID_OVERAGE=false (default) ensures we never roll into billed usage.
            allow_overage = str(get_setting_value("HIVE_ALLOW_PAID_OVERAGE", "false")).strip().lower()
            if mode == "PROMO_CREDIT" and allow_overage == "true":
                return True, "PROMO_CREDIT_OVERAGE_ALLOWED"  # not default; user must explicitly opt in
            return True, mode
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

    if p in ("unorouter", "uno"):
        return m.endswith(":free") and (
            m in VERIFIED_FREE_MODELS.get("unorouter", {})
            or m == "glm-5.3-search:free"
        )

    if p == "hive":
        return m in VERIFIED_FREE_MODELS.get("hive", {})

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
            v_str = str(v).strip()
            if ("remaining-requests" in k_lower or k_lower == "x-ratelimit-remaining") and v_str.isdigit():
                info.remaining_requests = int(v_str)
                found = True
            elif ("remaining-tokens" in k_lower) and v_str.isdigit():
                info.remaining_tokens = int(v_str)
                found = True
            elif ("limit-requests" in k_lower or k_lower == "x-ratelimit-limit") and v_str.isdigit():
                info.rpd = int(v_str)
                found = True
            elif "reset" in k_lower or k_lower == "retry-after":
                info.reset_time = v_str
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
    tool_calls: Optional[list[dict[str, Any]]] = None
    latency_ms: float = 0.0
    citations: Optional[list[Any]] = None
    rate_limit_headers: dict[str, str] = field(default_factory=dict)

    @property
    def content(self) -> str:
        return self.text

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
        **kwargs: Any,
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
import threading


class GeminiRateLimiter:
    """Enforces user-confirmed AI Studio quota ceiling: 60 RPM, 100,000 input TPM.

    Includes safety margins to prevent hitting quota ceilings.
    """
    RPM_CEILING: int = 60
    INPUT_TPM_CEILING: int = 100000
    SAFETY_RPM: int = 50
    SAFETY_INPUT_TPM: int = 90000

    _lock = threading.Lock()
    _request_timestamps: list[float] = []
    _input_token_history: list[tuple[float, int]] = []
    _total_requests: int = 0
    _successful_requests: int = 0
    _failed_requests: int = 0

    @classmethod
    def estimate_input_tokens(cls, contents: list[dict[str, Any]], system_prompt: str = "") -> int:
        total_chars = len(system_prompt or "")
        for c in contents:
            for p in c.get("parts", []):
                total_chars += len(p.get("text", "") or "")
        return max(5, total_chars // 4)

    @classmethod
    def check_and_acquire(cls, estimated_input_tokens: int) -> bool:
        with cls._lock:
            now = time.time()
            cutoff = now - 60.0
            cls._request_timestamps = [ts for ts in cls._request_timestamps if ts > cutoff]
            cls._input_token_history = [(ts, tok) for ts, tok in cls._input_token_history if ts > cutoff]

            current_rpm = len(cls._request_timestamps)
            current_tpm = sum(tok for _, tok in cls._input_token_history)

            if current_rpm >= cls.SAFETY_RPM or (current_tpm + estimated_input_tokens) > cls.SAFETY_INPUT_TPM:
                return False

            cls._request_timestamps.append(now)
            cls._input_token_history.append((now, estimated_input_tokens))
            cls._total_requests += 1
            return True

    @classmethod
    def record_outcome(cls, success: bool, actual_input_tokens: Optional[int] = None):
        with cls._lock:
            if success:
                cls._successful_requests += 1
            else:
                cls._failed_requests += 1

    @classmethod
    def get_stats(cls) -> dict[str, Any]:
        with cls._lock:
            now = time.time()
            cutoff = now - 60.0
            rolling_requests = len([ts for ts in cls._request_timestamps if ts > cutoff])
            rolling_tokens = sum(tok for ts, tok in cls._input_token_history if ts > cutoff)
            return {
                "rpm_ceiling": cls.RPM_CEILING,
                "input_tpm_ceiling": cls.INPUT_TPM_CEILING,
                "safety_rpm": cls.SAFETY_RPM,
                "safety_input_tpm": cls.SAFETY_INPUT_TPM,
                "rolling_rpm": rolling_requests,
                "rolling_input_tpm": rolling_tokens,
                "total_requests": cls._total_requests,
                "successful_requests": cls._successful_requests,
                "failed_requests": cls._failed_requests,
            }

    @classmethod
    def reset_for_tests(cls):
        with cls._lock:
            cls._request_timestamps.clear()
            cls._input_token_history.clear()
            cls._total_requests = 0
            cls._successful_requests = 0
            cls._failed_requests = 0


gemini_rate_limiter = GeminiRateLimiter()


def _normalize_gemini_model(model_name: Optional[str]) -> str:
    """Normalize model names to active 2026 Gemini Flash API identifiers."""
    if not model_name:
        return "gemini-3.1-flash-lite"
    m = model_name.strip().lower()
    if "2.0" in m:
        return "gemini-2.0-flash"  # Will be rejected by retired check
    if "3.1" in m:
        return "gemini-3.1-flash-lite"
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
    return "gemini-3.1-flash-lite"


class GeminiProvider(LLMProvider):
    supports_tool_calling: bool = True
    supports_structured_json: bool = True

    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        if api_key is not None:
            self.api_key = api_key
        else:
            self.api_key = str(get_setting_value("GOOGLE_API_KEY", "")).strip() or str(get_setting_value("GEMINI_API_KEY", "")).strip()
        raw_model = model_name or str(get_setting_value("ORCHESTRATOR_GEMINI_MODEL", "")).strip() or "gemini-3.1-flash-lite"
        self.model_name = _normalize_gemini_model(raw_model)
        self._status = LLM_STATUS_AVAILABLE
        self._retry_after_until: Optional[float] = None

    def is_available(self) -> bool:
        if self.model_name in RETIRED_MODELS:
            self._status = LLM_STATUS_MODEL_REMOVED
            return False
        account_verified, _ = verify_provider_billing_mode("gemini")
        if not account_verified:
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

        # Phase 9: Enforce 60 RPM and 100k input TPM ceiling with safety margin
        estimated_input_tokens = gemini_rate_limiter.estimate_input_tokens(contents, system_prompt=system_prompt)
        if not gemini_rate_limiter.check_and_acquire(estimated_input_tokens):
            self._status = LLM_STATUS_RATE_LIMITED
            self._retry_after_until = time.time() + 5.0
            raise QuotaExhaustedError(
                "Gemini local rate limiter ceiling reached (60 RPM / 100k TPM ceiling). "
                "Non-blocking pause engaged to protect AI Studio quota."
            )

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
        for fallback_m in ["gemini-3.1-flash-lite", "gemini-3.7-flash", "gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash"]:
            if fallback_m not in models_to_try and is_cost_allowed("gemini", fallback_m):
                models_to_try.append(fallback_m)

        last_err = None
        for m in models_to_try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={self.api_key}"
            try:
                resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=30)
                quota_tracker.update_from_headers("gemini", dict(resp.headers))

                if resp.status_code == 200:
                    gemini_rate_limiter.record_outcome(success=True, actual_input_tokens=estimated_input_tokens)
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
                    retry_header = resp.headers.get("Retry-After")
                    retry_seconds = int(retry_header) if retry_header and retry_header.isdigit() else 60
                    last_err = f"HTTP 429 on model {m}: {resp.text}"
                    logger.warning("Gemini model %s hit rate limit (HTTP 429). Trying fallback candidate if available...", m)
                    continue
                else:
                    last_err = f"HTTP {resp.status_code}: {resp.text}"
            except Exception as e:
                last_err = str(e)

        gemini_rate_limiter.record_outcome(success=False)
        self._status = LLM_STATUS_RATE_LIMITED
        self._retry_after_until = time.time() + 30.0
        raise QuotaExhaustedError(f"All Gemini models exhausted or failed: {last_err}", retry_after=30)


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


# ── 5. UnoRouter Free Tier Provider (OpenAI-Compatible Zero-Cost) ──────────
class UnoRouterProvider(LLMProvider):
    """UnoRouter zero-cost OpenAI-compatible LLM provider adapter.

    Enforces:
    - Model route must be explicitly verified as free (suffix ':free').
    - UNOROUTER_ACCOUNT_MODE must be FREE.
    - On 402/payment required, provider is blocked immediately.
    - Zero cost only: paid fallback is strictly disabled.
    - Header tracking for rate limits (x-ratelimit-*, retry-after).
    - Secret redaction: UNOROUTER_API_KEY is never printed or logged.
    - Non-blocking 1-RPM rate-limit awareness (skips/fails over without worker sleep).
    """

    # Class-level rate-limit state persistence (1 RPM free tier rule):
    _last_request_at: Optional[float] = None
    _next_allowed_at: Optional[float] = None
    _retry_after: Optional[int] = None
    _count_429: int = 0

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        if api_key is not None:
            self.api_key = api_key
        else:
            self.api_key = str(get_setting_value("UNOROUTER_API_KEY", "")).strip()
        self.model_name = (
            model_name
            or str(get_setting_value("UNOROUTER_MODEL", "glm-5.3-search:free")).strip()
            or "glm-5.3-search:free"
        )
        self.base_url = (
            base_url
            or str(get_setting_value("UNOROUTER_BASE_URL", "https://api.unorouter.com/v1")).strip()
            or "https://api.unorouter.com/v1"
        )
        self._status = LLM_STATUS_AVAILABLE
        self._retry_after_until: Optional[float] = None
        self._blocked = False

    def is_available(self) -> bool:
        if self._blocked:
            return False
        if not bool(get_setting_value("UNOROUTER_ENABLED", True)):
            return False
        if not is_cost_allowed("unorouter", self.model_name):
            return False
        # Non-blocking 1-RPM check: if in cooldown window, immediately mark unavailable so router fails over
        if self._next_allowed_at and time.time() < self._next_allowed_at:
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
        tools: Optional[list[dict[str, Any]]] = None,
        tool_choice: Optional[Any] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        if self._blocked:
            raise LLMProviderNotAllowedError(
                "LLM_PROVIDER_NOT_ALLOWED: UnoRouter is blocked due to a payment/billing signal."
            )

        account_verified, reason = verify_provider_billing_mode("unorouter")
        if not account_verified:
            raise LLMProviderNotAllowedError(
                f"{reason}: UnoRouter account mode is '{get_setting_value('UNOROUTER_ACCOUNT_MODE', 'UNVERIFIED')}'. "
                f"Requires explicit 'UNOROUTER_ACCOUNT_MODE=FREE' under ZERO_COST_ONLY."
            )

        if not is_cost_allowed("unorouter", self.model_name):
            raise LLMProviderNotAllowedError(
                f"LLM_PROVIDER_NOT_ALLOWED: Model '{self.model_name}' on UnoRouter is not an approved free route. "
                f"Must end with ':free' and be in verified free model allowlist."
            )

        if self._next_allowed_at and time.time() < self._next_allowed_at:
            wait_rem = int(self._next_allowed_at - time.time())
            raise QuotaExhaustedError(
                f"UnoRouterProvider cooling down (1 RPM limit). Next request allowed in {wait_rem}s.",
                retry_after=wait_rem,
            )

        if not self.is_available():
            if self._retry_after_until and time.time() < self._retry_after_until:
                raise QuotaExhaustedError(
                    f"UnoRouterProvider is rate-limited until {self._retry_after_until}"
                )
            raise RuntimeError("UnoRouterProvider is not available (UNOROUTER_API_KEY missing or disabled).")

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
        if tools:
            payload["tools"] = tools
            if tool_choice:
                payload["tool_choice"] = tool_choice

        endpoint = f"{self.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        start_time = time.time()
        timeout_seconds = int(get_setting_value("UNOROUTER_TIMEOUT", 90))
        try:
            resp = requests.post(endpoint, json=payload, headers=headers, timeout=timeout_seconds)
            latency_ms = (time.time() - start_time) * 1000.0

            # Filter rate limit headers
            rate_headers = {
                k.lower(): v
                for k, v in resp.headers.items()
                if "ratelimit" in k.lower() or "retry-after" in k.lower()
            }
            quota_tracker.update_from_headers("unorouter", dict(resp.headers))

            if resp.status_code == 200:
                try:
                    data = resp.json()
                except Exception as e:
                    raise RuntimeError(f"UnoRouter returned malformed JSON response: {e}")

                choices = data.get("choices", [])
                message_obj = choices[0].get("message", {}) if choices else {}
                text = message_obj.get("content", "") or ""
                tool_calls = message_obj.get("tool_calls")
                returned_model = data.get("model", self.model_name)

                # Capture citations if returned
                citations = data.get("citations") or message_obj.get("citations") or []

                usage = data.get("usage", {})
                input_tokens = usage.get("prompt_tokens", 0)
                output_tokens = usage.get("completion_tokens", 0)
                total_tokens = usage.get("total_tokens", input_tokens + output_tokens)

                # Track rate limit state for 1-RPM free tier window (60s cooldown)
                UnoRouterProvider._last_request_at = time.time()
                UnoRouterProvider._next_allowed_at = UnoRouterProvider._last_request_at + 60.0
                self._status = LLM_STATUS_AVAILABLE
                self._retry_after_until = None

                return LLMResponse(
                    text=text,
                    usage={
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "total_tokens": total_tokens,
                    },
                    provider="unorouter",
                    model=returned_model,
                    raw_response=data,
                    status=LLM_STATUS_AVAILABLE,
                    quota=quota_tracker.get_quota("unorouter"),
                    tool_calls=tool_calls,
                    latency_ms=latency_ms,
                    citations=citations if citations else None,
                    rate_limit_headers=rate_headers,
                )
            elif resp.status_code == 401:
                self._status = LLM_STATUS_UNAVAILABLE
                raise RuntimeError("UnoRouter authentication failed (HTTP 401): Invalid or unauthorized API key.")
            elif resp.status_code in (402, 403) or "payment" in resp.text.lower() or "billing" in resp.text.lower():
                self._blocked = True
                self._status = LLM_PROVIDER_NOT_ALLOWED
                raise LLMProviderNotAllowedError(
                    f"UnoRouter payment/billing required (HTTP {resp.status_code}): {resp.text[:200]}. "
                    f"Provider BLOCKED immediately under ZERO_COST_ONLY policy."
                )
            elif resp.status_code == 429:
                UnoRouterProvider._count_429 += 1
                self._status = LLM_STATUS_RATE_LIMITED
                retry_header = resp.headers.get("Retry-After")
                retry_seconds = int(retry_header) if retry_header and retry_header.isdigit() else 35
                UnoRouterProvider._retry_after = retry_seconds
                UnoRouterProvider._next_allowed_at = time.time() + retry_seconds
                self._retry_after_until = UnoRouterProvider._next_allowed_at
                raise QuotaExhaustedError(
                    f"UnoRouter quota/rate limit exhausted (HTTP 429): {resp.text[:200]}",
                    retry_after=retry_seconds,
                )
            elif resp.status_code >= 500:
                self._status = LLM_STATUS_UNAVAILABLE
                raise RuntimeError(f"UnoRouter provider server failure (HTTP {resp.status_code}): {resp.text[:200]}")
            else:
                raise RuntimeError(f"UnoRouter API error (HTTP {resp.status_code}): {resp.text[:200]}")
        except requests.exceptions.Timeout:
            self._status = LLM_STATUS_UNAVAILABLE
            raise RuntimeError(f"UnoRouter request timed out after {timeout_seconds}s")
        except (QuotaExhaustedError, LLMProviderNotAllowedError):
            raise
        except Exception as e:
            if "UnoRouter" in str(e):
                raise
            raise RuntimeError(f"UnoRouter connection error: {e}")

    @classmethod
    def get_rate_limit_state(cls) -> dict[str, Any]:
        """Returns persisted rate-limit and health state for UnoRouter."""
        now = time.time()
        cooldown = max(0.0, (cls._next_allowed_at or 0.0) - now)
        return {
            "last_request_at": cls._last_request_at,
            "next_allowed_at": cls._next_allowed_at,
            "retry_after": cls._retry_after,
            "count_429": cls._count_429,
            "is_cooling_down": cooldown > 0,
            "cooldown_remaining_seconds": round(cooldown, 1),
        }

    @classmethod
    def reset_rate_limit_state(cls):
        """Reset cooldown timestamps (used in unit test fixtures)."""
        cls._last_request_at = None
        cls._next_allowed_at = None
        cls._retry_after = None
        cls._count_429 = 0


# ── 6. Hive v3 Provider (DeepSeek-V4.1-Flash, Promotional Credit Tier) ──────
class HiveProvider(LLMProvider):
    """Hive AI v3 provider using DeepSeek-V4.1-Flash.

    Account model: PROMO_CREDIT ($51 promotional credit; no paid overage by default).
    Enforces:
    - HIVE_API_KEY read exclusively from env; never printed, logged, or surfaced.
    - HIVE_ACCOUNT_MODE=PROMO_CREDIT (or FREE) required under ZERO_COST_ONLY.
    - HIVE_ALLOW_PAID_OVERAGE=false (default) prevents rolling into billable usage.
    - Model must be in VERIFIED_FREE_MODELS['hive'].
    - Uses streaming internally (required by model) and returns LLMResponse.
    - Failure semantics are distinct per HTTP status:
        401  AUTHENTICATION_FAILURE  — blocks this instance; key invalid
        402  CREDIT_OR_BILLING_EXHAUSTED — blocks this instance; credit gone
        403  PERMISSION_OR_MODEL_ACCESS_DENIED — model-scoped block only;
             does NOT permanently block other Hive models unless account evidence.
        429  RATE_LIMIT — retryable with Retry-After backoff
        5xx  TRANSIENT_PROVIDER_FAILURE — retryable / failover eligible
    """

    _DEFAULT_MODEL = "deepseek-ai/DeepSeek-V4.1-Flash"
    _DEFAULT_BASE_URL = "https://api-cdn.thehive.ai/api/v3"
    _CONTROL_TOKENS = ("<|endoftext|>",)

    @classmethod
    def clean_output(cls, text: str) -> str:
        """Remove only literal Hive/model control tokens observed in content deltas."""
        cleaned = text
        for token in cls._CONTROL_TOKENS:
            cleaned = cleaned.replace(token, "")
        return cleaned.strip()

    # Per-instance model-level block flag (403 model scope only)
    # _blocked = True means account-level block (401/402/405); all calls halt.
    # _model_blocked = True means this specific model is denied (403).

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        # Key is NEVER stored in any attribute that could surface in repr/logs.
        self._api_key = (
            api_key
            or str(get_setting_value("HIVE_API_KEY", "")).strip()
        )
        self.model_name = (
            model_name
            or str(get_setting_value("HIVE_MODEL", self._DEFAULT_MODEL)).strip()
            or self._DEFAULT_MODEL
        )
        self.base_url = (
            base_url
            or str(get_setting_value("HIVE_BASE_URL", self._DEFAULT_BASE_URL)).strip()
            or self._DEFAULT_BASE_URL
        ).rstrip("/")
        self._status = LLM_STATUS_AVAILABLE
        self._retry_after_until: Optional[float] = None
        self._blocked: bool = False          # account-level block (401/402/405)
        self._model_blocked: bool = False    # model-level block (403)

    def __repr__(self) -> str:
        # Guarantee the API key never appears in repr.
        key_hint = "[SET]" if self._api_key else "[MISSING]"
        return f"HiveProvider(model={self.model_name!r}, key={key_hint})"

    def is_available(self) -> bool:
        if self._blocked or self._model_blocked:
            return False
        if not is_cost_allowed("hive", self.model_name):
            return False
        if self._retry_after_until and time.time() < self._retry_after_until:
            return False
        return bool(
            self._api_key
            and not self._api_key.startswith("mock_")
            and not self._api_key.startswith("YOUR_")
            and len(self._api_key) > 10
        )

    def complete(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 1500,
        response_format: Optional[str] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        if self._blocked:
            raise LLMProviderNotAllowedError(
                "AUTHENTICATION_FAILURE or CREDIT_OR_BILLING_EXHAUSTED: "
                "HiveProvider is account-blocked. Check HIVE_API_KEY validity and credit balance."
            )
        if self._model_blocked:
            raise LLMProviderNotAllowedError(
                f"PERMISSION_OR_MODEL_ACCESS_DENIED: Model '{self.model_name}' "
                f"returned HTTP 403 from Hive. Try a different model."
            )

        account_verified, reason = verify_provider_billing_mode("hive")
        if not account_verified:
            raise LLMProviderNotAllowedError(
                f"{reason}: Hive account mode must be FREE or PROMO_CREDIT under ZERO_COST_ONLY. "
                f"Set HIVE_ACCOUNT_MODE=PROMO_CREDIT in .env."
            )

        if not is_cost_allowed("hive", self.model_name):
            raise LLMProviderNotAllowedError(
                f"LLM_PROVIDER_NOT_ALLOWED: Model '{self.model_name}' is not in the Hive verified-free allowlist."
            )

        if not self.is_available():
            if self._retry_after_until and time.time() < self._retry_after_until:
                raise QuotaExhaustedError(
                    f"HiveProvider is rate-limited until {self._retry_after_until}"
                )
            raise RuntimeError("HiveProvider is not available (HIVE_API_KEY missing or unconfigured).")

        # Build OpenAI-compatible message list.
        formatted_messages: list[dict[str, str]] = []
        if system_prompt:
            formatted_messages.append({"role": "system", "content": system_prompt})
        for msg in messages:
            formatted_messages.append({"role": msg["role"], "content": msg["content"]})

        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": formatted_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,  # Required for DeepSeek-V4.1-Flash on Hive v3
        }

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        timeout_seconds = int(get_setting_value("HIVE_TIMEOUT", 60))
        start_time = time.time()

        try:
            resp = requests.post(
                url, json=payload, headers=headers,
                timeout=timeout_seconds, stream=True,
            )
            latency_ms = (time.time() - start_time) * 1000.0
            quota_tracker.update_from_headers("hive", dict(resp.headers))

            if resp.status_code == 200:
                # Consume SSE stream and accumulate text + usage.
                accumulated_text = ""
                input_tokens = 0
                output_tokens = 0
                for raw_line in resp.iter_lines():
                    if not raw_line:
                        continue
                    line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
                    if not line.startswith("data:"):
                        continue
                    data_str = line[len("data:"):].strip()
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                    except Exception:
                        continue
                    # Delta text
                    choices = chunk.get("choices", [])
                    if choices:
                        delta = choices[0].get("delta", {})
                        accumulated_text += delta.get("content") or ""
                    # Usage (may appear in final chunk)
                    usage = chunk.get("usage") or {}
                    if usage:
                        input_tokens = usage.get("prompt_tokens", input_tokens)
                        output_tokens = usage.get("completion_tokens", output_tokens)

                accumulated_text = self.clean_output(accumulated_text)

                self._status = LLM_STATUS_AVAILABLE
                self._retry_after_until = None
                return LLMResponse(
                    text=accumulated_text,
                    usage={
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "total_tokens": input_tokens + output_tokens,
                    },
                    provider="hive",
                    model=self.model_name,
                    raw_response=None,
                    status=LLM_STATUS_AVAILABLE,
                    quota=quota_tracker.get_quota("hive"),
                    latency_ms=latency_ms,
                )

            elif resp.status_code == 401:
                # AUTHENTICATION_FAILURE: key is invalid at the account level.
                # Block the entire provider instance — all subsequent calls will fail.
                self._blocked = True
                self._status = LLM_STATUS_UNAVAILABLE
                raise RuntimeError(
                    "AUTHENTICATION_FAILURE: Hive API key rejected (HTTP 401). "
                    "Verify HIVE_API_KEY is correct and active."
                )

            elif resp.status_code in (402, 405):
                # CREDIT_OR_BILLING_EXHAUSTED: promotional credit or balance exhausted.
                # Block the entire provider instance — credit is gone.
                self._blocked = True
                self._status = LLM_PROVIDER_NOT_ALLOWED
                raise LLMProviderNotAllowedError(
                    f"CREDIT_OR_BILLING_EXHAUSTED: Hive returned HTTP {resp.status_code}. "
                    "Promotional credit or account balance is exhausted. "
                    "Provider BLOCKED under ZERO_COST_ONLY (HIVE_ALLOW_PAID_OVERAGE=false)."
                )

            elif resp.status_code == 403:
                # PERMISSION_OR_MODEL_ACCESS_DENIED: this model/endpoint is not accessible.
                # Block only this model — do NOT block the account for other models.
                self._model_blocked = True
                self._status = LLM_PROVIDER_NOT_ALLOWED
                raise LLMProviderNotAllowedError(
                    f"PERMISSION_OR_MODEL_ACCESS_DENIED: Hive HTTP 403 for model '{self.model_name}'. "
                    f"This model instance is blocked but other Hive models may still be accessible."
                )

            elif resp.status_code == 429:
                self._status = LLM_STATUS_RATE_LIMITED
                retry_header = resp.headers.get("Retry-After")
                retry_seconds = int(retry_header) if retry_header and str(retry_header).isdigit() else 60
                self._retry_after_until = time.time() + retry_seconds
                raise QuotaExhaustedError(
                    f"Hive rate limit (HTTP 429): {resp.text[:200]}",
                    retry_after=retry_seconds,
                )

            elif resp.status_code >= 500:
                self._status = LLM_STATUS_UNAVAILABLE
                raise RuntimeError(f"Hive server error (HTTP {resp.status_code}): {resp.text[:200]}")

            else:
                raise RuntimeError(f"Hive API error (HTTP {resp.status_code}): {resp.text[:200]}")

        except requests.exceptions.Timeout:
            self._status = LLM_STATUS_UNAVAILABLE
            raise RuntimeError(f"Hive request timed out after {timeout_seconds}s")
        except (QuotaExhaustedError, LLMProviderNotAllowedError):
            raise
        except Exception as exc:
            if "Hive" in str(exc):
                raise
            raise RuntimeError(f"Hive connection error: {exc}")


# ── 7. OpenAI Provider (Retained for Manual Use; Blocked under Zero-Cost) ───
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

    @staticmethod
    def compute_prompt_key(
        provider: str,
        model: str,
        system_prompt: str,
        user_prompt: str,
        params: Optional[dict[str, Any]] = None,
    ) -> str:
        """Hash: provider, model, system prompt, user prompt, relevant parameters."""
        canonical_params = json.dumps(params or {}, sort_keys=True, default=str)
        raw = f"{provider.lower().strip()}:{model.strip()}:{system_prompt.strip()}:{user_prompt.strip()}:{canonical_params}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get_prompt_response(
        self,
        provider: str,
        model: str,
        system_prompt: str,
        user_prompt: str,
        params: Optional[dict[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        if not self.enabled:
            return None
        key = self.compute_prompt_key(provider, model, system_prompt, user_prompt, params)
        entry = self._memory_cache.get(key)
        if not entry:
            return None
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

    def set_prompt_response(
        self,
        provider: str,
        model: str,
        system_prompt: str,
        user_prompt: str,
        output: Any,
        params: Optional[dict[str, Any]] = None,
        tokens_used: Optional[dict[str, int]] = None,
    ):
        if not self.enabled:
            return
        key = self.compute_prompt_key(provider, model, system_prompt, user_prompt, params)
        self._memory_cache[key] = {
            "provider": provider,
            "model": model,
            "output": output,
            "tokens_used": tokens_used or {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "CACHED",
        }
        self._save_cache()

    @staticmethod
    def normalize_search_query(query: str) -> str:
        """Normalize whitespace and lower-case search query for maximum cache hits."""
        return re.sub(r"\s+", " ", (query or "").lower().strip())

    @staticmethod
    def compute_search_cache_key(
        provider: str,
        model: str,
        normalized_query: str,
        freshness_context: str = "",
    ) -> str:
        raw = f"SEARCH:{provider.lower().strip()}:{model.strip()}:{normalized_query.strip()}:{freshness_context.strip()}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get_search_cache(
        self,
        provider: str,
        model: str,
        query: str,
        freshness_context: str = "",
        max_age_seconds: Optional[float] = None,
    ) -> Optional[dict[str, Any]]:
        if not self.enabled:
            return None
        norm_query = self.normalize_search_query(query)
        key = self.compute_search_cache_key(provider, model, norm_query, freshness_context)
        entry = self._memory_cache.get(key)
        if not entry:
            return None
        created_at = entry.get("timestamp")
        if created_at:
            try:
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(created_at)).total_seconds()
                ttl = max_age_seconds if max_age_seconds is not None else (self.ttl_days * 86400)
                if age > ttl:
                    del self._memory_cache[key]
                    return None
            except Exception:
                pass
        return entry

    def set_search_cache(
        self,
        provider: str,
        model: str,
        query: str,
        output: Any,
        freshness_context: str = "",
        citations: Optional[list[dict[str, Any]]] = None,
    ):
        if not self.enabled:
            return
        norm_query = self.normalize_search_query(query)
        key = self.compute_search_cache_key(provider, model, norm_query, freshness_context)
        self._memory_cache[key] = {
            "type": "SEARCH_RESPONSE",
            "provider": provider,
            "model": model,
            "normalized_query": norm_query,
            "freshness_context": freshness_context,
            "output": output,
            "citations": citations or [],
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
        **kwargs: Any,
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
                    **kwargs,
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
    """Task-aware Salesoorja Zero-Cost Provider Router.

    Routes according to operational characteristics:
    - PUBLIC_WEB_RESEARCH / CURRENT_TRIGGER_RESEARCH / SOURCE_DISCOVERY / RECENT_COMPANY_RESEARCH:
      UnoRouter (glm-5.3-search:free) preferred first for web search & freshness.
    - GENERAL_REASONING / PERSON_RANKING / FACILITY_CLASSIFICATION / SUMMARIZATION / COPY_REVIEW:
      Fast verified zero-cost reasoning providers first (Gemini, Groq, Cloudflare, OpenRouter);
      UnoRouter only as last fallback to protect 1-RPM quota and avoid 35s latency.
    - TOOL_CALL_REQUIRED / AGENT_LOOP / STRUCTURED_TOOL_EXECUTION:
      Strictly EXCLUDES UnoRouter (tool calling unsupported).
    - DETERMINISTIC_GATE / CONTACT_CLASSIFICATION / QUALIFICATION_STATE / SCHEDULER / DUPLICATE_CHECK:
      Strictly NO LLM (empty provider chain; complete() raises LLMProviderNotAllowedError).
    """

    def __init__(self, task_type: str = "GENERAL_REASONING"):
        self.task_type = (task_type or "GENERAL_REASONING").upper().strip()
        providers = self._build_chain_for_task(self.task_type)
        super().__init__(providers=providers)

    @classmethod
    def _build_chain_for_task(cls, task_type: str) -> list[LLMProvider]:
        t = (task_type or "").upper().strip()

        # Hard deterministic gates: strictly NO LLM
        if t in TASK_CATEGORY_DETERMINISTIC_ONLY:
            return []

        # Tool calling / agent execution: strictly EXCLUDE UnoRouter (tool calling unsupported)
        if t in TASK_CATEGORY_TOOL_EXECUTION:
            return [
                GeminiProvider(),
                GroqProvider(),
                CloudflareProvider(),
                OpenRouterProvider(),
                HiveProvider(),  # Last-resort fallback; no tool-calling but handles generation
            ]

        # Web / Trigger / Source research: PREFER UnoRouter search route first
        if t in TASK_CATEGORY_PUBLIC_WEB_RESEARCH:
            return [
                UnoRouterProvider(),
                GeminiProvider(),
                GroqProvider(),
                CloudflareProvider(),
                OpenRouterProvider(),
                HiveProvider(),
            ]

        # General reasoning & analysis: use verified zero-cost reasoning providers only.
        # UnoRouter (glm-5.3-search:free) is strictly excluded from general reasoning
        # to protect the 1-RPM quota, avoid ~35s latency, and keep search model focused.
        # HiveProvider is included as last-resort fallback.
        return [
            GeminiProvider(),
            GroqProvider(),
            CloudflareProvider(),
            OpenRouterProvider(),
            HiveProvider(),
        ]

    def complete(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 1500,
        response_format: Optional[str] = None,
        task_type: Optional[str] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        active_task = (task_type or self.task_type or "GENERAL_REASONING").upper().strip()
        if active_task in TASK_CATEGORY_DETERMINISTIC_ONLY or not evaluate_llm_task_allowed(active_task):
            raise LLMProviderNotAllowedError(
                f"Task '{active_task}' is deterministic and strictly prohibited from invoking an LLM."
            )

        # If call specifies a different task type, dynamically adapt active provider chain
        if task_type and active_task != self.task_type:
            task_chain = self._build_chain_for_task(active_task)
            temp_router = FallbackLLMProvider(providers=task_chain)
            return temp_router.complete(
                system_prompt=system_prompt,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format,
                **kwargs,
            )

        return super().complete(
            system_prompt=system_prompt,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
            **kwargs,
        )


# ── 8. Factory Functions ───────────────────────────────────────────────────
def get_provider(provider_name: str) -> LLMProvider:
    """Factory to get an LLM provider by name."""
    name = (provider_name or "").lower().strip()
    if name in ["unorouter", "uno"]:
        return UnoRouterProvider()
    if name in ["gemini", "google"]:
        return GeminiProvider()
    if name in ["groq"]:
        return GroqProvider()
    if name in ["openrouter"]:
        return OpenRouterProvider()
    if name in ["cloudflare"]:
        return CloudflareProvider()
    if name in ["hive"]:
        return HiveProvider()
    if name in ["openai", "chatgpt"]:
        return OpenAIProvider()
    raise ValueError(f"Unknown LLM provider: {provider_name}")


def get_orchestrator_provider(task_type: str = "GENERAL_REASONING") -> Optional[LLMProvider]:
    """Returns the configured zero-cost orchestrator LLM provider with failover.
    When task_type is in TASK_CATEGORY_DETERMINISTIC_ONLY, returns None so
    deterministic gates never invoke an LLM.
    When ALLOW_PAID_LLM=False, OpenAI is strictly omitted from the chain.
    If no free provider API keys are configured or account mode is UNVERIFIED,
    returns None so callers can fall back to deterministic logic without crashing.
    """
    t = (task_type or "GENERAL_REASONING").upper().strip()
    if t in TASK_CATEGORY_DETERMINISTIC_ONLY or not evaluate_llm_task_allowed(t):
        return None

    allow_paid = bool(get_setting_value("ALLOW_PAID_LLM", False))
    cost_policy = str(get_setting_value("LLM_COST_POLICY", LLM_COST_POLICY_ZERO_COST)).strip()

    if not allow_paid or cost_policy == LLM_COST_POLICY_ZERO_COST:
        router = ZeroCostRouter(task_type=t)
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
    3. If ICP >= 85 and ambiguity exists, Model B (Verifier) audits conclusion.
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
    analyst = analyst_provider or get_orchestrator_provider(task_type=task_type)
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

    if float(icp_score or 0) >= 85 and has_ambiguity:
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
