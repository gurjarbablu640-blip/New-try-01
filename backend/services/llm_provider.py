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


class GeminiProvider(LLMProvider):
    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        self.api_key = api_key or settings.GOOGLE_API_KEY
        self.model_name = model_name or settings.ORCHESTRATOR_GEMINI_MODEL or "gemini-2.0-flash"
        self._configured = False
        if self.api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                self._configured = True
            except Exception as e:
                logger.warning(f"Could not configure Google GenAI: {e}")

    def is_available(self) -> bool:
        return bool(self.api_key and self._configured)

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

        import google.generativeai as genai

        generation_config = {
            "temperature": temperature,
            "max_output_tokens": max_tokens,
        }
        if response_format == "json":
            generation_config["response_mime_type"] = "application/json"

        # Build model with system instruction
        model = genai.GenerativeModel(
            model_name=self.model_name,
            system_instruction=system_prompt if system_prompt else None,
            generation_config=generation_config,
        )

        # Build contents from message list
        contents = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            contents.append({"role": role, "parts": [msg["content"]]})

        if not contents:
            contents = [{"role": "user", "parts": ["Hello"]}]

        response = model.generate_content(contents)
        text = response.text if response and response.text else ""

        # Extract usage metadata if available
        input_tokens = 0
        output_tokens = 0
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            input_tokens = getattr(response.usage_metadata, "prompt_token_count", 0) or 0
            output_tokens = getattr(response.usage_metadata, "candidates_token_count", 0) or 0

        return LLMResponse(
            text=text,
            usage={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
            },
            provider="gemini",
            model=self.model_name,
            raw_response=response,
        )


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.model_name = model_name or settings.ORCHESTRATOR_OPENAI_MODEL or "gpt-4o"
        self._client = None
        if self.api_key:
            try:
                from openai import OpenAI
                self._client = OpenAI(api_key=self.api_key)
            except Exception as e:
                logger.warning(f"Could not initialize OpenAI client: {e}")

    def is_available(self) -> bool:
        return bool(self.api_key and self._client is not None)

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

        kwargs: dict[str, Any] = {
            "model": self.model_name,
            "messages": formatted_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format == "json":
            kwargs["response_format"] = {"type": "json_object"}

        response = self._client.chat.completions.create(**kwargs)
        choice = response.choices[0] if response.choices else None
        text = choice.message.content if choice and choice.message else ""

        input_tokens = response.usage.prompt_tokens if response.usage else 0
        output_tokens = response.usage.completion_tokens if response.usage else 0

        return LLMResponse(
            text=text or "",
            usage={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
            },
            provider="openai",
            model=self.model_name,
            raw_response=response,
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
    primary_name = getattr(settings, "ORCHESTRATOR_PRIMARY_PROVIDER", "gemini")
    fallback_name = getattr(settings, "ORCHESTRATOR_FALLBACK_PROVIDER", "openai")

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
