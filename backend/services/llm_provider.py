"""Production LLM routing: DeepSeek primary, Gemini fallback.

LLM output is advisory. Deterministic Salesoorja evidence gates remain final.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
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

ALLOWED_LLM_TASKS = TASK_CATEGORY_REASONING
DISALLOWED_LLM_TASKS = TASK_CATEGORY_DETERMINISTIC_ONLY

RETIRED_MODELS: set[str] = {
    "gemini-2.0-flash",
    "gemini-2.0-flash-exp",
    "gemini-1.0-pro",
    "gemini-pro",
}

VERIFIED_FREE_MODELS: dict[str, dict[str, Any]] = {
    "gemini": {
        "gemini-3.8-flash": {"free_allowed": True},
        "gemini-3.7-flash": {"free_allowed": True},
        "gemini-3.6-flash": {"free_allowed": True},
        "gemini-3.5-flash": {"free_allowed": True},
        "gemini-3.5-flash-lite": {"free_allowed": True},
        "gemini-3.1-flash-lite": {"free_allowed": True},
    },
    "hive": {
        "deepseek-ai/DeepSeek-V4.1-Flash": {"free_allowed": True},
    },
}


class QuotaExhaustedError(RuntimeError):
    def __init__(self, message: str, retry_after: Optional[int] = None):
        super().__init__(message)
        self.retry_after = retry_after


class LLMProviderNotAllowedError(RuntimeError):
    pass


def verify_provider_billing_mode(provider_name: str) -> tuple[bool, str]:
    allow_paid = bool(get_setting_value("ALLOW_PAID_LLM", False))
    cost_policy = str(
        get_setting_value("LLM_COST_POLICY", LLM_COST_POLICY_ZERO_COST)
    ).strip()
    if allow_paid and cost_policy != LLM_COST_POLICY_ZERO_COST:
        return True, "PAID_ALLOWED"

    provider = (provider_name or "").lower().strip()
    if provider in {"gemini", "google"}:
        mode = str(
            get_setting_value("GEMINI_ACCOUNT_MODE", "UNVERIFIED")
        ).strip().upper()
        if mode == "FREE_NO_BILLING":
            return True, mode
        if mode == "PAID":
            return False, PROVIDER_ACCOUNT_MODE_PAID_BLOCKED
        return False, PROVIDER_BILLING_STATUS_UNVERIFIED

    if provider in {"deepseek", "hive"}:
        mode = str(
            get_setting_value("HIVE_ACCOUNT_MODE", "UNVERIFIED")
        ).strip().upper()
        if mode in {"FREE", "PROMO_CREDIT"}:
            allow_overage = str(
                get_setting_value("HIVE_ALLOW_PAID_OVERAGE", "false")
            ).strip().lower()
            if mode == "PROMO_CREDIT" and allow_overage == "true":
                return True, "PROMO_CREDIT_OVERAGE_ALLOWED"
            return True, mode
        if mode == "PAID":
            return False, PROVIDER_ACCOUNT_MODE_PAID_BLOCKED
        return False, PROVIDER_BILLING_STATUS_UNVERIFIED

    return False, "UNKNOWN_PROVIDER"


def is_cost_allowed(provider_name: str, model_name: str) -> bool:
    allow_paid = bool(get_setting_value("ALLOW_PAID_LLM", False))
    cost_policy = str(
        get_setting_value("LLM_COST_POLICY", LLM_COST_POLICY_ZERO_COST)
    ).strip()
    if allow_paid and cost_policy != LLM_COST_POLICY_ZERO_COST:
        return True

    account_verified, _ = verify_provider_billing_mode(provider_name)
    if not account_verified or model_name in RETIRED_MODELS:
        return False

    provider = (provider_name or "").lower().strip()
    model = (model_name or "").strip()
    if provider in {"gemini", "google"}:
        return model in VERIFIED_FREE_MODELS["gemini"] or (
            "flash" in model.lower() and model not in RETIRED_MODELS
        )
    if provider in {"deepseek", "hive"}:
        return model in VERIFIED_FREE_MODELS["hive"]
    return False


def evaluate_llm_task_allowed(task_type: str) -> bool:
    task = (task_type or "").upper().strip()
    if task in DISALLOWED_LLM_TASKS:
        return False
    return task in ALLOWED_LLM_TASKS


def apply_reasoning_to_gate(
    deterministic_passed: bool,
    llm_reasoning: dict[str, Any],
) -> dict[str, Any]:
    if not deterministic_passed:
        return {
            "passed": False,
            "gate_decision": "FAILED_DETERMINISTIC",
            "reason": (
                "Deterministic gate failed; LLM semantic interpretation "
                "cannot override hard evidence rules."
            ),
            "llm_applied": False,
            "llm_reasoning": llm_reasoning,
        }
    return {
        "passed": bool(
            llm_reasoning.get("decision") in {"STRONG", "PASS", "QUALIFIED"}
        ),
        "gate_decision": llm_reasoning.get("decision", "HOLD"),
        "confidence": float(llm_reasoning.get("confidence", 0.7)),
        "reason": str(
            llm_reasoning.get("reason", "Passed with LLM verification.")
        ),
        "llm_applied": True,
        "llm_reasoning": llm_reasoning,
    }


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


# â”€â”€ Response Data Structure â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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
            decoder = json.JSONDecoder()
            object_start = raw.find("{")
            array_start = raw.find("[")
            starts = [index for index in (object_start, array_start) if index >= 0]
            if starts:
                first_start = min(starts)
                try:
                    parsed, _ = decoder.raw_decode(raw[first_start:])
                    return parsed
                except json.JSONDecodeError:
                    pass

            ranked_match = re.search(r'"ranked_candidates"\s*:\s*\[', raw)
            if ranked_match:
                cursor = ranked_match.end()
                recovered = []
                while cursor < len(raw):
                    while cursor < len(raw) and raw[cursor] in " \t\r\n,":
                        cursor += 1
                    if cursor >= len(raw) or raw[cursor] == "]":
                        break
                    if raw[cursor] != "{":
                        break
                    try:
                        item, consumed = decoder.raw_decode(raw[cursor:])
                    except json.JSONDecodeError:
                        break
                    if isinstance(item, dict):
                        recovered.append(item)
                    cursor += consumed
                if recovered:
                    return {"ranked_candidates": recovered, "_partial_recovery": True}

            logger.warning(f"Failed to parse JSON from LLM text: {raw[:200]}")
            return None


# â”€â”€ Provider Abstract Base Class â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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


# â”€â”€ 1. Google Gemini Developer API Free Tier â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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


# DeepSeek provider

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
        401  AUTHENTICATION_FAILURE  â€” blocks this instance; key invalid
        402  CREDIT_OR_BILLING_EXHAUSTED â€” blocks this instance; credit gone
        403  PERMISSION_OR_MODEL_ACCESS_DENIED â€” model-scoped block only;
             does NOT permanently block other Hive models unless account evidence.
        429  RATE_LIMIT â€” retryable with Retry-After backoff
        5xx  TRANSIENT_PROVIDER_FAILURE â€” retryable / failover eligible
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
                # Block the entire provider instance â€” all subsequent calls will fail.
                self._blocked = True
                self._status = LLM_STATUS_UNAVAILABLE
                raise RuntimeError(
                    "AUTHENTICATION_FAILURE: Hive API key rejected (HTTP 401). "
                    "Verify HIVE_API_KEY is correct and active."
                )

            elif resp.status_code in (402, 405):
                # CREDIT_OR_BILLING_EXHAUSTED: promotional credit or balance exhausted.
                # Block the entire provider instance â€” credit is gone.
                self._blocked = True
                self._status = LLM_PROVIDER_NOT_ALLOWED
                raise LLMProviderNotAllowedError(
                    f"CREDIT_OR_BILLING_EXHAUSTED: Hive returned HTTP {resp.status_code}. "
                    "Promotional credit or account balance is exhausted. "
                    "Provider BLOCKED under ZERO_COST_ONLY (HIVE_ALLOW_PAID_OVERAGE=false)."
                )

            elif resp.status_code == 403:
                # PERMISSION_OR_MODEL_ACCESS_DENIED: this model/endpoint is not accessible.
                # Block only this model â€” do NOT block the account for other models.
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


# Provider factory and fallback chain

class DeepSeekProvider(HiveProvider):
    """Primary DeepSeek adapter using the retained Hive API transport."""


class FallbackLLMProvider(LLMProvider):
    """Two-stage production chain: DeepSeek, then Gemini."""

    def __init__(
        self,
        primary: Optional[LLMProvider] = None,
        fallback: Optional[LLMProvider] = None,
        providers: Optional[list[LLMProvider]] = None,
    ):
        self.providers = (
            providers
            if providers is not None
            else [
                provider
                for provider in (primary, fallback)
                if provider is not None
            ]
        )

    def is_available(self) -> bool:
        return any(provider.is_available() for provider in self.providers)

    def complete(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 1500,
        response_format: Optional[str] = None,
        **kwargs: Any,
    ) -> LLMResponse:
        errors: list[str] = []
        for provider in self.providers:
            if not provider.is_available():
                continue
            try:
                return provider.complete(
                    system_prompt=system_prompt,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format=response_format,
                    **kwargs,
                )
            except (QuotaExhaustedError, LLMProviderNotAllowedError) as exc:
                logger.warning(
                    "Provider %s unavailable: %s; trying fallback.",
                    provider.__class__.__name__,
                    exc,
                )
                errors.append(f"{provider.__class__.__name__}: {exc}")
            except Exception as exc:
                logger.warning(
                    "Provider %s failed: %s; trying fallback.",
                    provider.__class__.__name__,
                    exc,
                )
                errors.append(f"{provider.__class__.__name__}: {exc}")

        detail = "; ".join(errors) if errors else "No configured provider available."
        raise QuotaExhaustedError(
            f"{LLM_STATUS_FREE_CAPACITY_EXHAUSTED}: {detail}"
        )


def get_provider(provider_name: str) -> LLMProvider:
    name = (provider_name or "").lower().strip()
    if name in {"deepseek", "hive"}:
        return DeepSeekProvider()
    if name in {"gemini", "google"}:
        return GeminiProvider()
    raise ValueError(f"Unknown LLM provider: {provider_name}")


def get_orchestrator_provider(
    task_type: str = "GENERAL_REASONING",
) -> Optional[LLMProvider]:
    task = (task_type or "GENERAL_REASONING").upper().strip()
    if not evaluate_llm_task_allowed(task):
        return None

    provider = FallbackLLMProvider(
        primary=DeepSeekProvider(),
        fallback=GeminiProvider(),
    )
    return provider if provider.is_available() else None
