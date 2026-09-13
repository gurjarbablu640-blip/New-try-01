from unittest.mock import MagicMock, patch

import pytest

from services.llm_provider import (
    DeepSeekProvider,
    FallbackLLMProvider,
    GeminiProvider,
    LLMProvider,
    LLMResponse,
    apply_reasoning_to_gate,
    get_orchestrator_provider,
    get_provider,
)


def test_factory_exposes_only_deepseek_and_gemini():
    assert isinstance(get_provider("deepseek"), DeepSeekProvider)
    assert isinstance(get_provider("hive"), DeepSeekProvider)
    assert isinstance(get_provider("gemini"), GeminiProvider)
    for removed in ("openai", "groq", "openrouter", "cloudflare", "unorouter"):
        with pytest.raises(ValueError):
            get_provider(removed)


def test_orchestrator_builds_deepseek_then_gemini():
    with patch.object(DeepSeekProvider, "is_available", return_value=True):
        provider = get_orchestrator_provider("GENERAL_REASONING")

    assert isinstance(provider, FallbackLLMProvider)
    assert [type(item) for item in provider.providers] == [
        DeepSeekProvider,
        GeminiProvider,
    ]


def test_deterministic_tasks_never_receive_llm():
    assert get_orchestrator_provider("DETERMINISTIC_GATE") is None
    assert get_orchestrator_provider("APOLLO_CREDIT_GATE") is None


def test_fallback_uses_gemini_after_deepseek_failure():
    primary = MagicMock(spec=LLMProvider)
    secondary = MagicMock(spec=LLMProvider)
    primary.is_available.return_value = True
    secondary.is_available.return_value = True
    primary.complete.side_effect = RuntimeError("primary unavailable")
    secondary.complete.return_value = LLMResponse(
        text="fallback",
        provider="gemini",
        model="gemini-3.1-flash-lite",
    )

    response = FallbackLLMProvider(primary=primary, fallback=secondary).complete(
        system_prompt="system",
        messages=[{"role": "user", "content": "reason"}],
    )

    assert response.provider == "gemini"
    secondary.complete.assert_called_once()


def test_llm_cannot_override_failed_deterministic_gate():
    result = apply_reasoning_to_gate(
        False,
        {"decision": "QUALIFIED", "confidence": 1.0},
    )

    assert result["passed"] is False
    assert result["llm_applied"] is False
    assert result["gate_decision"] == "FAILED_DETERMINISTIC"
