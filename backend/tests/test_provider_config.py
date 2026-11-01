from __future__ import annotations

import pytest

from app.api.responses import ApiError
from app.api.routes.queries import get_query_engine_service
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


def test_query_engine_dependency_sanitizes_invalid_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(ApiError) as exc_info:
        get_query_engine_service()

    assert exc_info.value.code == "QUERY_PROVIDER_UNAVAILABLE"
    assert exc_info.value.status_code == 503
    assert "key" not in exc_info.value.message.lower()


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


@pytest.mark.parametrize(
    "unsupported_key",
    [
        "OPENAI_ADMIN_KEY",
        "OPENAI_BASE_URL",
        "OPENAI_CUSTOM_HEADERS",
        "OPENAI_ORG_ID",
        "OPENAI_PROJECT_ID",
        "OPENAI_WEBHOOK_SECRET",
    ],
)
def test_openai_rejects_caller_controlled_sdk_configuration(
    unsupported_key: str,
) -> None:
    with pytest.raises(ProviderConfigurationError) as exc_info:
        load_provider_settings(
            {
                "LLM_PROVIDER": "openai",
                "OPENAI_API_KEY": "test-key",
                unsupported_key: "untrusted-value",
            }
        )

    assert exc_info.value.code == "unsupported_provider_endpoint"


def test_provider_settings_repr_does_not_expose_api_key() -> None:
    settings = load_provider_settings(
        {"LLM_PROVIDER": "openai", "OPENAI_API_KEY": "super-secret-key"}
    )

    assert "super-secret-key" not in repr(settings)


def test_openai_settings_normalize_key_without_exposing_it() -> None:
    settings = load_provider_settings(
        {"LLM_PROVIDER": "openai", "OPENAI_API_KEY": "  test-key  "}
    )

    assert settings.openai is not None
    assert settings.openai.api_key == "test-key"
    assert "test-key" not in repr(settings)


@pytest.mark.parametrize("field,value", [
    ("model", "gpt-5.6-luna"), ("timeout_seconds", 44.0), ("max_retries", 1),
    ("reasoning_effort", "medium"), ("max_output_tokens", 2049),
])
def test_provider_runtime_identity_changes_for_every_behavior_setting(field, value):
    from dataclasses import replace
    from app.query_engine.provider_config import OpenAIProviderSettings, ProviderSettings, provider_runtime_identity
    settings = ProviderSettings(ProviderId.OPENAI, OpenAIProviderSettings(api_key="private-key"))
    changed = replace(settings, openai=replace(settings.openai, **{field: value}))
    assert provider_runtime_identity(settings) != provider_runtime_identity(changed)
    assert "private-key" not in repr(provider_runtime_identity(settings))
    assert provider_runtime_identity(settings) == provider_runtime_identity(replace(settings, openai=replace(settings.openai, api_key="different-secret")))


def test_provider_runtime_identity_uses_installed_versions_and_normalized_settings(monkeypatch):
    from app.query_engine import provider_config as config
    from dataclasses import replace
    settings = config.ProviderSettings(config.ProviderId.OPENAI, config.OpenAIProviderSettings(api_key="synthetic"))
    baseline = config.provider_runtime_identity(settings)
    assert baseline == config.provider_runtime_identity(replace(settings, openai=replace(settings.openai, timeout_seconds=45)))
    versions = config.installed_runtime_versions()
    assert {"httpx", "httpcore", "openai", "pydantic", "sqlglot", "psycopg-binary"} <= versions.keys()
    for package in versions:
        monkeypatch.setattr(config, "installed_runtime_versions", lambda package=package: {**versions, package: "0.0.synthetic"})
        assert baseline != config.provider_runtime_identity(settings), package


def test_provider_runtime_identity_changes_with_python_runtime(monkeypatch):
    from app.query_engine import provider_config as config
    settings = config.ProviderSettings()
    before = config.provider_runtime_identity(settings)
    monkeypatch.setattr(config.platform, "python_version", lambda: "0.0.changed")
    assert config.provider_runtime_identity(settings) != before
