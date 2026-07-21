from __future__ import annotations

import os
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.query_engine.domain_pack import DomainPack
from app.query_engine.llm_provider import LLMProvider
from app.query_engine.mock_llm_provider import MockLLMProvider


DEFAULT_OPENAI_MODEL = "gpt-5.6-terra"
DEFAULT_OPENAI_TIMEOUT_SECONDS = 45.0
DEFAULT_OPENAI_MAX_RETRIES = 2
DEFAULT_OPENAI_REASONING_EFFORT = "low"
DEFAULT_OPENAI_MAX_OUTPUT_TOKENS = 2048
MODEL_LABEL_MAX_LENGTH = 128
MODEL_LABEL_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
SUPPORTED_REASONING_EFFORTS = frozenset({"none", "low", "medium", "high"})
OFFICIAL_OPENAI_BASE_URL = "https://api.openai.com/v1"


class ProviderId(str, Enum):
    MOCK = "mock"
    OPENAI = "openai"


class ProviderConfigurationError(RuntimeError):
    def __init__(self, code: str = "provider_configuration_invalid") -> None:
        super().__init__("LLM provider configuration is invalid.")
        self.code = code
        self.safe_message = "LLM provider configuration is invalid."


@dataclass(frozen=True)
class OpenAIProviderSettings:
    api_key: str = field(repr=False)
    model: str = DEFAULT_OPENAI_MODEL
    timeout_seconds: float = DEFAULT_OPENAI_TIMEOUT_SECONDS
    max_retries: int = DEFAULT_OPENAI_MAX_RETRIES
    reasoning_effort: str = DEFAULT_OPENAI_REASONING_EFFORT
    max_output_tokens: int = DEFAULT_OPENAI_MAX_OUTPUT_TOKENS

    def __post_init__(self) -> None:
        if not isinstance(self.api_key, str) or not self.api_key.strip():
            raise ProviderConfigurationError("provider_credentials_missing")
        if not valid_model_label(self.model):
            raise ProviderConfigurationError("provider_model_invalid")
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, int | float)
            or not math.isfinite(float(self.timeout_seconds))
            or not 1.0 <= float(self.timeout_seconds) <= 120.0
        ):
            raise ProviderConfigurationError("provider_timeout_invalid")
        if (
            isinstance(self.max_retries, bool)
            or not isinstance(self.max_retries, int)
            or not 0 <= self.max_retries <= 2
        ):
            raise ProviderConfigurationError("provider_retries_invalid")
        if self.reasoning_effort not in SUPPORTED_REASONING_EFFORTS:
            raise ProviderConfigurationError("provider_reasoning_effort_invalid")
        if (
            isinstance(self.max_output_tokens, bool)
            or not isinstance(self.max_output_tokens, int)
            or not 128 <= self.max_output_tokens <= 4096
        ):
            raise ProviderConfigurationError("provider_output_tokens_invalid")


@dataclass(frozen=True)
class ProviderSettings:
    provider: ProviderId = ProviderId.MOCK
    openai: OpenAIProviderSettings | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.provider, ProviderId):
            raise ProviderConfigurationError()
        if (self.provider is ProviderId.OPENAI) != (self.openai is not None):
            raise ProviderConfigurationError()

    @property
    def model_label(self) -> str:
        if self.provider is ProviderId.MOCK:
            return MockLLMProvider.model_name
        if self.openai is None:
            raise ProviderConfigurationError()
        return self.openai.model


@dataclass(frozen=True)
class ProviderDescriptor:
    provider: ProviderId
    model_label: str

    def __post_init__(self) -> None:
        if not isinstance(self.provider, ProviderId) or not valid_model_label(
            self.model_label
        ):
            raise ProviderConfigurationError()
        if (
            self.provider is ProviderId.MOCK
            and self.model_label != MockLLMProvider.model_name
        ):
            raise ProviderConfigurationError("provider_model_mismatch")


def load_provider_settings(
    environ: Mapping[str, str] | None = None,
    *,
    provider_override: str | None = None,
    model_override: str | None = None,
) -> ProviderSettings:
    values = environ if environ is not None else os.environ
    raw_provider = provider_override if provider_override is not None else values.get(
        "LLM_PROVIDER", ProviderId.MOCK.value
    )
    try:
        provider = ProviderId(raw_provider)
    except (TypeError, ValueError) as exc:
        raise ProviderConfigurationError() from exc

    if provider is ProviderId.MOCK:
        if model_override is not None:
            raise ProviderConfigurationError("provider_model_mismatch")
        return ProviderSettings(provider=provider)

    if values.get("OPENAI_BASE_URL", "").strip():
        raise ProviderConfigurationError("unsupported_provider_endpoint")

    api_key = values.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ProviderConfigurationError("provider_credentials_missing")

    model = (
        model_override
        if model_override is not None
        else values.get("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
    )
    if not valid_model_label(model):
        raise ProviderConfigurationError("provider_model_invalid")

    timeout_seconds = _bounded_float(
        values.get("OPENAI_TIMEOUT_SECONDS", str(DEFAULT_OPENAI_TIMEOUT_SECONDS)),
        minimum=1.0,
        maximum=120.0,
    )
    max_retries = _bounded_int(
        values.get("OPENAI_MAX_RETRIES", str(DEFAULT_OPENAI_MAX_RETRIES)),
        minimum=0,
        maximum=2,
    )
    reasoning_effort = values.get(
        "OPENAI_REASONING_EFFORT", DEFAULT_OPENAI_REASONING_EFFORT
    )
    if reasoning_effort not in SUPPORTED_REASONING_EFFORTS:
        raise ProviderConfigurationError("provider_reasoning_effort_invalid")
    max_output_tokens = _bounded_int(
        values.get(
            "OPENAI_MAX_OUTPUT_TOKENS", str(DEFAULT_OPENAI_MAX_OUTPUT_TOKENS)
        ),
        minimum=128,
        maximum=4096,
    )
    return ProviderSettings(
        provider=provider,
        openai=OpenAIProviderSettings(
            api_key=api_key,
            model=model,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            reasoning_effort=reasoning_effort,
            max_output_tokens=max_output_tokens,
        ),
    )


def provider_descriptor(settings: ProviderSettings) -> ProviderDescriptor:
    return ProviderDescriptor(
        provider=settings.provider,
        model_label=settings.model_label,
    )


def create_provider(
    settings: ProviderSettings,
    domain_pack: DomainPack,
    *,
    openai_client: Any | None = None,
) -> LLMProvider:
    if settings.provider is ProviderId.MOCK:
        return MockLLMProvider(domain_pack)
    if settings.openai is None:
        raise ProviderConfigurationError()

    from app.query_engine.openai_provider import OpenAIProvider

    return OpenAIProvider(settings.openai, client=openai_client)


def valid_model_label(value: Any) -> bool:
    return isinstance(value, str) and bool(MODEL_LABEL_PATTERN.fullmatch(value))


def _bounded_int(raw_value: Any, *, minimum: int, maximum: int) -> int:
    try:
        value = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ProviderConfigurationError() from exc
    if isinstance(raw_value, bool) or not minimum <= value <= maximum:
        raise ProviderConfigurationError()
    return value


def _bounded_float(raw_value: Any, *, minimum: float, maximum: float) -> float:
    try:
        value = float(raw_value)
    except (TypeError, ValueError) as exc:
        raise ProviderConfigurationError() from exc
    if not minimum <= value <= maximum:
        raise ProviderConfigurationError()
    return value
