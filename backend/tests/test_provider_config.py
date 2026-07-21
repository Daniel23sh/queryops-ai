from __future__ import annotations

import pytest

from app.query_engine.domain_pack_loader import load_it_operations_domain_pack
from app.query_engine.mock_llm_provider import MockLLMProvider
from app.query_engine.openai_provider import OpenAIProvider
from app.query_engine.provider_config import (
    DEFAULT_OPENAI_MODEL,
    ProviderConfigurationError,
    ProviderId,
    create_provider,
    load_provider_settings,
    provider_descriptor,
)
from app.api.routes.queries import get_query_engine_service


def test_provider_settings_default_to_mock_without_credentials() -> None:
    settings = load_provider_settings({})

    assert settings.provider is ProviderId.MOCK
    assert settings.openai is None
    assert provider_descriptor(settings).model_label == "mock-queryops-v1"
    assert isinstance(
        create_provider(settings, load_it_operations_domain_pack()), MockLLMProvider
    )


def test_openai_key_alone_does_not_activate_openai() -> None:
    settings = load_provider_settings({"OPENAI_API_KEY": "should-not-activate"})

    assert settings.provider is ProviderId.MOCK
    assert settings.openai is None


def test_query_engine_dependency_remains_mock_with_api_key_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "unused-key")

    service = get_query_engine_service()

    assert isinstance(service._provider, MockLLMProvider)


def test_explicit_openai_uses_bounded_defaults_and_injected_client() -> None:
    settings = load_provider_settings(
        {"LLM_PROVIDER": "openai", "OPENAI_API_KEY": "test-key"}
    )
    client = object()

    provider = create_provider(
        settings,
        load_it_operations_domain_pack(),
        openai_client=client,
    )

    assert settings.openai is not None
    assert settings.openai.model == DEFAULT_OPENAI_MODEL
    assert settings.openai.timeout_seconds == 45.0
    assert settings.openai.max_retries == 2
    assert settings.openai.reasoning_effort == "low"
    assert settings.openai.max_output_tokens == 2048
    assert isinstance(provider, OpenAIProvider)


def test_explicit_openai_requires_credentials_without_leaking_config() -> None:
    with pytest.raises(ProviderConfigurationError) as exc_info:
        load_provider_settings({"LLM_PROVIDER": "openai"})

    assert exc_info.value.code == "provider_credentials_missing"
    assert "key" not in str(exc_info.value).lower()


@pytest.mark.parametrize(
    ("values", "override"),
    [
        ({"LLM_PROVIDER": "other"}, None),
        ({"LLM_PROVIDER": "openai", "OPENAI_API_KEY": "x", "OPENAI_MODEL": ""}, None),
        (
            {
                "LLM_PROVIDER": "openai",
                "OPENAI_API_KEY": "x",
                "OPENAI_TIMEOUT_SECONDS": "0",
            },
            None,
        ),
        (
            {
                "LLM_PROVIDER": "openai",
                "OPENAI_API_KEY": "x",
                "OPENAI_MAX_RETRIES": "3",
            },
            None,
        ),
        (
            {
                "LLM_PROVIDER": "openai",
                "OPENAI_API_KEY": "x",
                "OPENAI_REASONING_EFFORT": "max",
            },
            None,
        ),
        (
            {
                "LLM_PROVIDER": "openai",
                "OPENAI_API_KEY": "x",
                "OPENAI_MAX_OUTPUT_TOKENS": "5000",
            },
            None,
        ),
        ({"LLM_PROVIDER": "mock"}, "gpt-5.6-terra"),
    ],
)
def test_invalid_provider_configuration_fails_closed(
    values: dict[str, str], override: str | None
) -> None:
    with pytest.raises(ProviderConfigurationError):
        load_provider_settings(values, model_override=override)


def test_openai_rejects_caller_controlled_endpoint() -> None:
    with pytest.raises(ProviderConfigurationError) as exc_info:
        load_provider_settings(
            {
                "LLM_PROVIDER": "openai",
                "OPENAI_API_KEY": "test-key",
                "OPENAI_BASE_URL": "https://attacker.invalid/v1",
            }
        )

    assert exc_info.value.code == "unsupported_provider_endpoint"


def test_provider_settings_repr_does_not_expose_api_key() -> None:
    settings = load_provider_settings(
        {"LLM_PROVIDER": "openai", "OPENAI_API_KEY": "super-secret-key"}
    )

    assert "super-secret-key" not in repr(settings)
