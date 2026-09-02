from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, cast

import httpx
import openai
import pytest

from app.query_engine.domain_pack_loader import load_it_operations_domain_pack
from app.query_engine.llm_provider import PlanGenerationOutcome
from app.query_engine.openai_provider import (
    OpenAIProvider,
    ProviderFailure,
    build_safe_prompt_projection,
)
from app.query_engine.provider_config import OpenAIProviderSettings
from app.query_engine.semantic_catalog import build_semantic_catalog_projection


QUESTION = "Show active devices by operating system."
SCHEMA_CONTEXT = {
    "domain": "it_operations",
    "domain_name": "IT Operations",
    "domain_version": "1.0.0",
    "allowed_tables": ["devices"],
    "allowed_columns": {"devices": ["id", "operating_system"]},
    "tables": [
        {
            "name": "devices",
            "description": "Managed endpoint inventory.",
            "columns": [
                {"name": "id", "data_type": "uuid", "description": "Device ID."},
                {
                    "name": "operating_system",
                    "data_type": "text",
                    "description": "Installed operating system.",
                },
                {"name": "secret_column", "data_type": "text"},
            ],
        },
        {
            "name": "it_audit_events",
            "description": "protected sentinel",
            "columns": [{"name": "metadata", "data_type": "jsonb"}],
        },
    ],
    "business_terms": [
        {
            "name": "Active device",
            "description": "A currently managed device.",
            "related_tables": ["devices", "it_audit_events"],
        }
    ],
    "secret": "postgresql://user:password@database/queryops",
    "baseline_sql": "SELECT expected_answer FROM protected_table",
    "expected_rows": [{"email": "private@example.com"}],
}
USER_CONTEXT = {
    "scope_type": "department",
    "has_global_scope": False,
    "user_id": "00000000-0000-4000-8000-000000000123",
    "scope_key": "finance",
    "role": "manager",
    "email": "manager@example.com",
    "full_name": "Private Manager",
    "permissions": ["can_view_everything"],
}
ACTIVE_HUMAN_SCHEMA_CONTEXT = {
    "domain": "it_operations",
    "domain_name": "IT Operations",
    "domain_version": "1",
    "allowed_tables": ["directory_users"],
    "allowed_columns": {
        "directory_users": [
            "account_status",
            "account_type",
            "employee_status",
        ]
    },
    "tables": [
        {
            "name": "directory_users",
            "description": "Directory identity records.",
            "columns": [
                {"name": "account_status", "data_type": "string"},
                {"name": "account_type", "data_type": "string"},
                {"name": "employee_status", "data_type": "string"},
            ],
        }
    ],
    "business_terms": [],
}
DEVICE_PLAN = {
    "entity_ids": ["devices"],
    "concept_ids": [],
    "composition_rule_ids": [],
    "metric_id": None,
    "distinct": False,
    "literal_filters": [],
    "relationships": [],
    "output_fields": [
        {"entity_id": "devices", "column": "operating_system"}
    ],
    "aggregations": [],
    "group_by": [],
    "having": [],
    "order_by": [],
    "limit": None,
}
ACTIVE_HUMAN_PLAN = {
    "entity_ids": ["directory_users"],
    "concept_ids": [],
    "composition_rule_ids": [],
    "metric_id": "active_human_users",
    "distinct": False,
    "literal_filters": [],
    "relationships": [],
    "output_fields": [],
    "aggregations": [],
    "group_by": [],
    "having": [],
    "order_by": [],
    "limit": None,
}


class FakeResponses:
    def __init__(
        self,
        payload: dict[str, Any] | None = None,
        *,
        response: Any | None = None,
        error: Exception | None = None,
    ) -> None:
        self.payload = payload
        self.response = response
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def parse(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        if self.response is not None:
            return self.response
        parsed = kwargs["text_format"].model_validate_json(json.dumps(self.payload))
        return response_for(parsed)


class FakeClient:
    def __init__(
        self,
        payload: dict[str, Any] | None = None,
        *,
        response: Any | None = None,
        error: Exception | None = None,
    ) -> None:
        self.responses = FakeResponses(payload, response=response, error=error)


def provider_for(client: FakeClient) -> OpenAIProvider:
    return OpenAIProvider(
        OpenAIProviderSettings(api_key="test-key"),
        client=cast(Any, client),
    )


def response_for(parsed: Any, *, status: str = "completed") -> Any:
    return SimpleNamespace(
        output_parsed=parsed,
        output=[],
        status=status,
        usage=SimpleNamespace(
            input_tokens=100,
            output_tokens=20,
            total_tokens=120,
            input_tokens_details=SimpleNamespace(cached_tokens=25),
        ),
        id="response-id-must-not-persist",
    )


def _status_error(error_type: type[Exception], status: int) -> Exception:
    request = httpx.Request("POST", "https://example.invalid")
    response = httpx.Response(status, request=request)
    return cast(Any, error_type)(
        "raw secret provider response", response=response, body=None
    )


def _full_schema_context() -> dict[str, Any]:
    pack = load_it_operations_domain_pack()
    allowed_tables = set(pack.allowed_resource_table_names)
    tables = [table for table in pack.tables if table.name in allowed_tables]
    return {
        "domain": pack.domain_id,
        "domain_name": pack.name,
        "domain_version": pack.version,
        "allowed_tables": sorted(allowed_tables),
        "allowed_columns": {
            table.name: [column.name for column in table.columns]
            for table in tables
        },
        "tables": [
            {
                "name": table.name,
                "description": table.description,
                "columns": [
                    {
                        "name": column.name,
                        "data_type": column.data_type,
                        "description": column.description,
                    }
                    for column in table.columns
                ],
            }
            for table in tables
        ],
        "business_terms": [],
    }


def test_openai_client_disables_ambient_sdk_routing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client_arguments: dict[str, Any] = {}
    http_arguments: dict[str, Any] = {}
    fake_client = FakeClient()

    def fake_http_client(**kwargs: Any) -> object:
        http_arguments.update(kwargs)
        return object()

    def fake_openai(**kwargs: Any) -> FakeClient:
        client_arguments.update(kwargs)
        return fake_client

    monkeypatch.setattr(
        "app.query_engine.openai_provider.DefaultHttpxClient", fake_http_client
    )
    monkeypatch.setattr("app.query_engine.openai_provider.OpenAI", fake_openai)
    OpenAIProvider(OpenAIProviderSettings(api_key="test-key"))

    assert client_arguments["base_url"] == "https://api.openai.com/v1"
    assert client_arguments["organization"] == ""
    assert client_arguments["project"] == ""
    assert client_arguments["max_retries"] == 2
    assert http_arguments == {"timeout": 45.0, "trust_env": False}


def test_safe_prompt_projection_contains_only_explicit_authorized_fields() -> None:
    projection = build_safe_prompt_projection(
        QUESTION, SCHEMA_CONTEXT, USER_CONTEXT
    )
    serialized = json.dumps(projection, sort_keys=True)

    assert [table["name"] for table in projection["tables"]] == ["devices"]
    assert [
        column["name"] for column in projection["tables"][0]["columns"]
    ] == ["id", "operating_system"]
    for forbidden in (
        "private@example.com",
        "Private Manager",
        "00000000-0000-4000-8000-000000000123",
        "finance",
        "can_view_everything",
        "it_audit_events",
        "postgresql://",
        "baseline_sql",
        "expected_rows",
        "secret_column",
    ):
        assert forbidden not in serialized


def test_openai_provider_parses_plan_and_extracts_only_safe_usage() -> None:
    client = FakeClient(
        {
            "outcome": "plan",
            "semantic_plan": DEVICE_PLAN,
            "clarification_reason": None,
        }
    )

    result = provider_for(client).generate_plan(
        QUESTION, SCHEMA_CONTEXT, USER_CONTEXT, {}
    )

    assert result.semantic_plan is not None
    assert result.semantic_plan.entity_ids == ("devices",)
    assert not hasattr(result, "generated_sql")
    assert result.outcome is PlanGenerationOutcome.PLAN
    measurement = result.generation_metadata["provider_measurement"]
    assert measurement == {
        "provider": "openai",
        "model_label": "gpt-5.6-terra",
        "duration_ms": measurement["duration_ms"],
        "attempt_count": 1,
        "input_tokens": 100,
        "cached_input_tokens": 25,
        "output_tokens": 20,
        "total_tokens": 120,
    }
    call = client.responses.calls[0]
    assert call["model"] == "gpt-5.6-terra"
    assert call["reasoning"] == {"effort": "low"}
    assert call["max_output_tokens"] == 2048
    assert call["store"] is False
    for disabled in ("tools", "background", "stream", "conversation"):
        assert disabled not in call
    assert set(call["text_format"].model_json_schema()["properties"]) == {
        "outcome",
        "semantic_plan",
        "clarification_reason",
    }


def test_required_and_suggested_intent_remain_in_plan_only_request() -> None:
    question = "Show users with active license assignments by product."
    schema_context = _full_schema_context()
    user_context = {
        "scope_type": "global",
        "has_global_scope": True,
        "scope_reference_resolved": True,
    }
    projection = build_semantic_catalog_projection(
        load_it_operations_domain_pack().semantic_catalog,
        question,
        schema_context,
        user_context,
    )
    client = FakeClient(
        {
            "outcome": "plan",
            "semantic_plan": DEVICE_PLAN,
            "clarification_reason": None,
        }
    )

    provider_for(client).generate_plan(
        question,
        schema_context,
        user_context,
        {"semantic_catalog": projection},
    )

    call = client.responses.calls[0]
    prompt = json.loads(call["input"])
    result_intent = prompt["semantic_catalog"]["result_intent"]
    assert result_intent["required"] is None
    assert result_intent["suggested"]["row_grain"]["mode"] == "grouped"
    assert result_intent["suggested"]["group_by"] == [
        {"table": "licenses", "column": "product_name"}
    ]
    assert result_intent["suggested"]["required_output_fields"] == [
        {"table": "licenses", "column": "product_name"}
    ]
    assert result_intent["suggested"]["aggregations"] == [
        {
            "id": "subject_count",
            "function": "count",
            "target_field": {"table": "directory_users", "column": "id"},
            "distinct": True,
        }
    ]
    instructions = " ".join(call["instructions"].lower().split())
    assert "required intent is a deterministic mandatory semantic contract" in instructions
    assert "suggested intent is non-binding planner guidance" in instructions
    assert "do not treat suggested fields as mandatory" in instructions
    assert "preserve mandatory semantic evidence" in instructions
    assert "never emit sql" in instructions
    assert "return a catalog-referenced semantic_plan" in instructions
    assert "itops-" not in call["input"]
    assert "baseline" not in call["input"].lower()


def test_department_possessive_scope_is_resolved_by_authorization_context() -> None:
    question = "Show active devices in my department."
    client = FakeClient(
        {
            "outcome": "plan",
            "semantic_plan": DEVICE_PLAN,
            "clarification_reason": None,
        }
    )

    result = provider_for(client).generate_plan(
        question,
        SCHEMA_CONTEXT,
        USER_CONTEXT,
        {},
    )

    assert result.outcome is PlanGenerationOutcome.PLAN
    assert result.semantic_plan is not None
    call = client.responses.calls[0]
    prompt = json.loads(call["input"])
    assert prompt["authorization"] == {
        "scope_type": "department",
        "has_global_scope": False,
        "scope_reference_resolved": True,
    }
    instructions = " ".join(call["instructions"].lower().split())
    for possessive_reference in (
        "my department",
        "our department",
        "within my department",
        "my scope",
        "my authorized area",
    ):
        assert possessive_reference in instructions
    assert "do not require a department name or identifier" in instructions
    assert "without inventing or embedding a scope identifier" in instructions
    assert "postgresql rls" in instructions
    assert "genuinely missing or ambiguous" in instructions


def test_unresolved_scope_preserves_missing_information_clarification() -> None:
    client = FakeClient(
        {
            "outcome": "clarification",
            "semantic_plan": None,
            "clarification_reason": "missing_information",
        }
    )

    result = provider_for(client).generate_plan(
        "Show the relevant records for my authorized area.",
        SCHEMA_CONTEXT,
        {"scope_type": "none", "has_global_scope": False},
        {},
    )

    assert result.outcome is PlanGenerationOutcome.CLARIFICATION
    assert result.clarification_required is True
    assert result.semantic_plan is None
    assert not hasattr(result, "generated_sql")
    assert result.unsupported_reason == "missing_information"
    call = client.responses.calls[0]
    prompt = json.loads(call["input"])
    assert prompt["authorization"] == {
        "scope_type": "none",
        "has_global_scope": False,
        "scope_reference_resolved": False,
    }
    instructions = " ".join(call["instructions"].lower().split())
    assert "authorization scope is unresolved" in instructions


def test_structured_concept_overrides_only_matching_legacy_business_term() -> None:
    schema_context = {
        **SCHEMA_CONTEXT,
        "allowed_columns": {
            "devices": [
                "id",
                "operating_system",
                "compliance_status",
                "antivirus_status",
                "encryption_enabled",
            ]
        },
        "tables": [
            {
                **SCHEMA_CONTEXT["tables"][0],
                "columns": [
                    *SCHEMA_CONTEXT["tables"][0]["columns"],
                    {"name": "compliance_status", "data_type": "string"},
                    {"name": "antivirus_status", "data_type": "string"},
                    {"name": "encryption_enabled", "data_type": "boolean"},
                ],
            }
        ],
        "business_terms": [
            {
                "name": "non-compliant device",
                "description": "Conflicting legacy definition.",
                "related_tables": ["devices"],
            },
            {
                "name": "Active device",
                "description": "Unrelated fallback glossary definition.",
                "related_tables": ["devices"],
            },
        ],
    }
    projection = build_semantic_catalog_projection(
        load_it_operations_domain_pack().semantic_catalog,
        "Show non-compliant devices.",
        schema_context,
        USER_CONTEXT,
    )

    prompt = build_safe_prompt_projection(
        "Show non-compliant devices.",
        schema_context,
        USER_CONTEXT,
        projection,
    )

    assert [term["name"] for term in prompt["business_terms"]] == ["Active device"]
    assert {
        concept["id"] for concept in prompt["semantic_catalog"]["concepts"]
    } >= {
        "antivirus_attention_device",
        "non_compliant_device",
        "unencrypted_device",
    }
    assert [
        rule["id"] for rule in prompt["semantic_catalog"]["composition_rules"]
    ] == ["non_compliant_device_posture"]


def test_active_human_catalog_and_metric_planning_rules_are_preserved() -> None:
    question = "How many active human directory users are in my department?"
    user_context = {
        "scope_type": "department",
        "has_global_scope": False,
        "scope_reference_resolved": True,
    }
    projection = build_semantic_catalog_projection(
        load_it_operations_domain_pack().semantic_catalog,
        question,
        ACTIVE_HUMAN_SCHEMA_CONTEXT,
        user_context,
    )
    client = FakeClient(
        {
            "outcome": "plan",
            "semantic_plan": ACTIVE_HUMAN_PLAN,
            "clarification_reason": None,
        }
    )

    result = provider_for(client).generate_plan(
        question,
        ACTIVE_HUMAN_SCHEMA_CONTEXT,
        user_context,
        {"semantic_catalog": projection},
    )

    assert result.semantic_plan is not None
    assert result.semantic_plan.metric_id == "active_human_users"
    assert result.generation_metadata["semantic_catalog"] == (
        projection.as_observation()
    )
    call = client.responses.calls[0]
    prompt = json.loads(call["input"])
    concepts = {
        concept["id"]: concept
        for concept in prompt["semantic_catalog"]["concepts"]
    }
    active_human = concepts["active_human_directory_user"]
    assert {
        (item["column"], item["operator"], item["value"])
        for concept_id in active_human["all_of_concept_ids"]
        for item in concepts[concept_id]["required_predicates"]
    } == {
        ("account_type", "equals", "human"),
        ("employee_status", "equals", "active"),
        ("account_status", "equals", "active"),
    }
    instructions = " ".join(call["instructions"].lower().split())
    assert "preserve every structured required_predicate" in instructions
    assert "combine all_of_concept_ids conjunctively" in instructions
    assert "set metric_id to that metric" in instructions
    assert "do not add or restate its count or sum in aggregations" in instructions
    assert "sql renderer implements the metric definition" in instructions


def test_composition_rule_guidance_separates_representation_from_narrowing() -> None:
    client = FakeClient(
        {
            "outcome": "plan",
            "semantic_plan": DEVICE_PLAN,
            "clarification_reason": None,
        }
    )

    provider_for(client).generate_plan(QUESTION, SCHEMA_CONTEXT, USER_CONTEXT, {})

    assert len(client.responses.calls) == 1
    instructions = " ".join(client.responses.calls[0]["instructions"].lower().split())
    assert "represent each selected composition rule by its id in composition_rule_ids" in instructions
    assert (
        "selecting that id represents the rule's full semantics: the backend will "
        "combine all_of_concept_ids conjunctively and or_concept_ids with or semantics"
    ) in instructions
    assert (
        "do not copy a rule's or branches into top-level concept_ids merely to represent the rule"
    ) in instructions
    assert "top-level concept_ids are additional conjunctive constraints (and)" in instructions
    assert (
        "include an or branch as a top-level concept only when the user's request "
        "independently requires narrowing beyond the composition rule"
    ) in instructions
    assert "keep the rule selected so all its branches remain represented" in instructions
    assert (
        "r = a or b or c, a base request for r uses composition_rule_ids=[r], concept_ids=[]"
    ) in instructions
    assert (
        "an independently requested narrowing to b uses composition_rule_ids=[r], concept_ids=[b]"
    ) in instructions
    assert "represent every listed branch" not in instructions


def test_unexpected_sql_field_is_rejected_by_structured_output_schema() -> None:
    provider = provider_for(
        FakeClient(
            {
                "outcome": "plan",
                "semantic_plan": DEVICE_PLAN,
                "sql": "SELECT id FROM devices",
                "clarification_reason": None,
            }
        )
    )

    with pytest.raises(ProviderFailure) as exc_info:
        provider.generate_plan(QUESTION, SCHEMA_CONTEXT, USER_CONTEXT, {})

    assert exc_info.value.code == "provider_response_invalid"
    assert "SELECT" not in str(exc_info.value)


def test_malformed_semantic_plan_is_rejected() -> None:
    malformed = {**DEVICE_PLAN, "unexpected": "raw secret"}
    provider = provider_for(
        FakeClient(
            {
                "outcome": "plan",
                "semantic_plan": malformed,
                "clarification_reason": None,
            }
        )
    )

    with pytest.raises(ProviderFailure) as exc_info:
        provider.generate_plan(QUESTION, SCHEMA_CONTEXT, USER_CONTEXT, {})

    assert exc_info.value.code == "provider_response_invalid"
    assert "secret" not in str(exc_info.value).lower()


def test_openai_provider_returns_controlled_clarification_without_plan() -> None:
    result = provider_for(
        FakeClient(
            {
                "outcome": "clarification",
                "semantic_plan": None,
                "clarification_reason": "ambiguous_question",
            }
        )
    ).generate_plan(QUESTION, SCHEMA_CONTEXT, USER_CONTEXT, {})

    assert result.semantic_plan is None
    assert result.outcome is PlanGenerationOutcome.CLARIFICATION
    assert result.unsupported_reason == "ambiguous_question"
    assert result.safe_error == "Please clarify the query request."


def test_openai_provider_returns_bounded_unsafe_request_without_plan() -> None:
    question = "Delete every active human directory user."
    user_context = {
        "scope_type": "department",
        "has_global_scope": False,
        "scope_reference_resolved": True,
    }
    projection = build_semantic_catalog_projection(
        load_it_operations_domain_pack().semantic_catalog,
        question,
        ACTIVE_HUMAN_SCHEMA_CONTEXT,
        user_context,
    )
    client = FakeClient(
        {
            "outcome": "unsafe_request",
            "semantic_plan": None,
            "clarification_reason": None,
        }
    )

    result = provider_for(client).generate_plan(
        question,
        ACTIVE_HUMAN_SCHEMA_CONTEXT,
        user_context,
        {"semantic_catalog": projection},
    )

    assert result.outcome is PlanGenerationOutcome.UNSAFE_REQUEST
    assert result.semantic_plan is None
    assert result.unsupported_reason == "unsafe_request"
    assert result.generation_metadata["referenced_tables"] == ["directory_users"]
    assert "response-id-must-not-persist" not in str(result)


@pytest.mark.parametrize(
    "payload",
    [
        {"outcome": "plan", "semantic_plan": None, "clarification_reason": None},
        {
            "outcome": "plan",
            "semantic_plan": DEVICE_PLAN,
            "clarification_reason": "missing_information",
        },
        {
            "outcome": "clarification",
            "semantic_plan": DEVICE_PLAN,
            "clarification_reason": "missing_information",
        },
        {
            "outcome": "clarification",
            "semantic_plan": None,
            "clarification_reason": None,
        },
        {
            "outcome": "unsafe_request",
            "semantic_plan": DEVICE_PLAN,
            "clarification_reason": None,
        },
        {
            "outcome": "unsafe_request",
            "semantic_plan": None,
            "clarification_reason": "unsupported_request",
        },
        {"outcome": "unknown", "semantic_plan": None, "clarification_reason": None},
    ],
)
def test_openai_provider_rejects_inconsistent_structured_outcomes(
    payload: dict[str, Any],
) -> None:
    with pytest.raises(ProviderFailure) as exc_info:
        provider_for(FakeClient(payload)).generate_plan(
            QUESTION, SCHEMA_CONTEXT, USER_CONTEXT, {}
        )

    assert exc_info.value.code == "provider_response_invalid"


def test_openai_provider_maps_refusal_to_controlled_failure() -> None:
    response = response_for(None)
    response.output = [
        {"content": [{"type": "refusal", "refusal": "raw refusal detail"}]}
    ]

    with pytest.raises(ProviderFailure) as exc_info:
        provider_for(FakeClient(response=response)).generate_plan(
            QUESTION, SCHEMA_CONTEXT, USER_CONTEXT, {}
        )

    assert exc_info.value.code == "provider_refusal"
    assert "raw refusal detail" not in str(exc_info.value)


@pytest.mark.parametrize(
    "response",
    [response_for(None), response_for(object()), response_for(None, status="incomplete")],
)
def test_openai_provider_rejects_missing_or_incomplete_structured_output(
    response: Any,
) -> None:
    with pytest.raises(ProviderFailure) as exc_info:
        provider_for(FakeClient(response=response)).generate_plan(
            QUESTION, SCHEMA_CONTEXT, USER_CONTEXT, {}
        )

    assert exc_info.value.code == "provider_response_invalid"


def test_openai_provider_does_not_call_client_without_authorized_schema() -> None:
    client = FakeClient(
        {
            "outcome": "plan",
            "semantic_plan": DEVICE_PLAN,
            "clarification_reason": None,
        }
    )

    result = provider_for(client).generate_plan(
        QUESTION,
        {**SCHEMA_CONTEXT, "allowed_tables": [], "allowed_columns": {}, "tables": []},
        USER_CONTEXT,
        {},
    )

    assert result.clarification_required is True
    assert result.unsupported_reason == "no_authorized_schema"
    assert client.responses.calls == []


@pytest.mark.parametrize(
    ("error", "code", "fatal"),
    [
        (
            openai.APITimeoutError(
                request=httpx.Request("POST", "https://example.invalid")
            ),
            "provider_timeout",
            False,
        ),
        (_status_error(openai.RateLimitError, 429), "provider_unavailable", False),
        (
            _status_error(openai.AuthenticationError, 401),
            "provider_authentication_failed",
            True,
        ),
        (RuntimeError("raw secret provider payload"), "provider_unavailable", False),
    ],
)
def test_openai_provider_classifies_failures_without_raw_error_leakage(
    error: Exception,
    code: str,
    fatal: bool,
) -> None:
    with pytest.raises(ProviderFailure) as exc_info:
        provider_for(FakeClient(error=error)).generate_plan(
            QUESTION, SCHEMA_CONTEXT, USER_CONTEXT, {}
        )

    assert exc_info.value.code == code
    assert exc_info.value.fatal is fatal
    assert "raw" not in str(exc_info.value).lower()
    assert "secret" not in str(exc_info.value).lower()
