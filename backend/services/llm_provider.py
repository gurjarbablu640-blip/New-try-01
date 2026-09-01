"""Provider abstraction layer for LLM completions (Gemini + OpenAI).

Provides unified interface with automatic failover, token tracking, and structured response parsing.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import json
import logging
from typing import Any, Optional

from config import settings

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    text: str
    usage: dict[str, int] = field(default_factory=lambda: {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0})
    provider: str = "unknown"
    model: str = "unknown"
    raw_response: Any = None

    def parse_json(self) -> Optional[dict[str, Any]]:
        """Safely parse JSON response from LLM text."""
        raw = self.text.strip()
        # Handle markdown code blocks
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
        """Check if this provider is configured with a valid API key."""
        pass


from config import settings
from services.settings_manager import get_setting_value

logger = logging.getLogger(__name__)


import requests

def _normalize_gemini_model(model_name: Optional[str]) -> str:
    """Normalize user-friendly or API model names to valid Gemini API identifiers."""
    if not model_name:
        return "gemini-3.6-flash"
    m = model_name.strip().lower()
    if "3.6" in m:
        return "gemini-3.6-flash"
    if "3.7" in m:
        return "gemini-3.7-flash"
    if "flash" in m:
        return "gemini-3.6-flash"
    if "gemini" in m:
        return model_name.strip()
    return "gemini-3.6-flash"


class GeminiProvider(LLMProvider):
    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        self.api_key = api_key or str(get_setting_value("GOOGLE_API_KEY", "")).strip()
        raw_model = model_name or str(get_setting_value("ORCHESTRATOR_GEMINI_MODEL", "")).strip() or "gemini-3.6-flash"
        self.model_name = _normalize_gemini_model(raw_model)

    def is_available(self) -> bool:
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
        if not self.is_available():
            raise RuntimeError("GeminiProvider is not available (GOOGLE_API_KEY missing or unconfigured).")

        # Format contents for Gemini REST API
        contents = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": msg["content"]}]})

        if not contents:
            contents = [{"role": "user", "parts": [{"text": "Hello"}]}]

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        if system_prompt:
            payload["systemInstruction"] = {
                "parts": [{"text": system_prompt}]
            }
        if response_format == "json":
            payload["generationConfig"]["responseMimeType"] = "application/json"

        # Try models in order: configured model -> gemini-3.6-flash -> gemini-3.7-flash -> gemini-flash-latest
        models_to_try = [self.model_name]
        for fallback_m in ["gemini-3.6-flash", "gemini-3.7-flash", "gemini-flash-latest"]:
            if fallback_m not in models_to_try:
                models_to_try.append(fallback_m)

        last_err = None
        for m in models_to_try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={self.api_key}"
            try:
                resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=30)
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
                    )
                else:
                    last_err = f"HTTP {resp.status_code}: {resp.text}"
            except Exception as e:
                last_err = str(e)

        raise RuntimeError(f"Gemini API request failed: {last_err}")


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        self.api_key = api_key or str(get_setting_value("OPENAI_API_KEY", "")).strip()
        self.model_name = model_name or str(get_setting_value("OPENAI_MODEL", "")).strip() or "gpt-4o"

    def is_available(self) -> bool:
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
        if not self.is_available():
            raise RuntimeError("OpenAIProvider is not available (OPENAI_API_KEY missing or unconfigured).")

        formatted_messages = []
        if system_prompt:
            formatted_messages.append({"role": "system", "content": system_prompt})
        for msg in messages:
            formatted_messages.append({"role": msg["role"], "content": msg["content"]})

        payload = {
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
        )


class FallbackLLMProvider(LLMProvider):
    def __init__(self, primary: LLMProvider, fallback: LLMProvider):
        self.primary = primary
        self.fallback = fallback

    def is_available(self) -> bool:
        return self.primary.is_available() or self.fallback.is_available()

    def complete(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 1500,
        response_format: Optional[str] = None,
    ) -> LLMResponse:
        if self.primary.is_available():
            try:
                return self.primary.complete(
                    system_prompt=system_prompt,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format=response_format,
                )
            except Exception as e:
                logger.warning(f"Primary LLM provider ({self.primary.__class__.__name__}) failed: {e}. Falling back to secondary.")

        if self.fallback.is_available():
            return self.fallback.complete(
                system_prompt=system_prompt,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format,
            )

        raise RuntimeError("No LLM provider available to complete request.")


def get_provider(provider_name: str) -> LLMProvider:
    """Factory to get an LLM provider by name."""
    name = (provider_name or "").lower().strip()
    if name in ["gemini", "google"]:
        return GeminiProvider()
    if name in ["openai", "chatgpt"]:
        return OpenAIProvider()
    raise ValueError(f"Unknown LLM provider: {provider_name}")


def get_orchestrator_provider() -> Optional[LLMProvider]:
    """
    Returns the configured orchestrator LLM provider with failover.
    If no provider API keys are configured, returns None so callers can fall back to deterministic logic.
    """
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
