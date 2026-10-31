from dataclasses import replace

import pytest

from app.query_engine.delivery import bound_metadata, restore_saved_bound
from app.query_engine.sql_validator import SQLValidationResult


def validation(limit=100):
    return SQLValidationResult(
        valid=True, sanitized_sql=f"SELECT id FROM licenses LIMIT {limit}",
        referenced_tables=["licenses"], input_limit=limit,
        effective_limit=limit, limit_source="input",
    )


@pytest.mark.parametrize("source,original,effective", [
    ("input", 0, 0), ("input", 100, 100), ("input", 500, 500),
    ("safety_added", None, 100), ("safety_clamped", 501, 500),
])
def test_restores_only_matching_server_bound_without_rewriting_sql(source, original, effective):
    fresh = validation(effective)
    metadata = {"validation": {
        "valid": True, "limit_source": source,
        "input_limit": original, "effective_limit": effective,
    }}
    restored = restore_saved_bound(fresh, metadata)
    assert restored.sanitized_sql == fresh.sanitized_sql
    assert restored.limit_source == source
    assert restored.input_limit == original
    assert restore_saved_bound(fresh, {"validation": bound_metadata(restored)}) == restored


@pytest.mark.parametrize("metadata", [
    None, {}, {"validation": []},
    {"validation": {"valid": True}},
    {"validation": {"valid": True, "limit_source": [], "input_limit": 100, "effective_limit": 100}},
    {"validation": {"valid": True, "limit_source": "input", "input_limit": True, "effective_limit": 100}},
    {"validation": {"valid": True, "limit_source": "input", "input_limit": 101, "effective_limit": 101}},
    {"validation": {"valid": True, "limit_source": "safety_added", "input_limit": None, "effective_limit": 99}},
    {"validation": {"valid": True, "limit_source": "safety_clamped", "input_limit": 101, "effective_limit": 100}},
])
def test_legacy_or_malformed_provenance_remains_unknown(metadata):
    fresh = validation()
    restored = restore_saved_bound(fresh, metadata)
    assert restored == replace(fresh, input_limit=None, limit_source=None)


@pytest.mark.parametrize("value", ["complete", "safety_limited", "unknown", None, [], {}, True, "bogus"])
def test_delivery_projection_exposes_only_the_known_enum(value):
    from app.query_engine.delivery import delivery_completeness
    from app.query_engine.sql_executor import SQLExecutionResult

    result = SQLExecutionResult(
        status="succeeded", columns=[], rows=[], row_count=0, duration_ms=0,
        truncated=False, execution_metadata={"delivery_completeness": value},
    )
    expected = value if isinstance(value, str) and value in {"complete", "safety_limited", "unknown"} else "unknown"
    assert delivery_completeness(result) == expected


def test_delivery_fixture_guard_rejects_before_connecting(monkeypatch):
    from scripts import prepare_delivery_e2e

    monkeypatch.delenv("M8_E2E_DATABASE_DISPOSABLE", raising=False)
    monkeypatch.setenv("M8_E2E_DATABASE_URL", "postgresql+psycopg://queryops:secret@localhost/queryops_test")

    def must_not_connect(*args, **kwargs):
        raise AssertionError("Unsafe fixture preparation reached the database.")

    monkeypatch.setattr(prepare_delivery_e2e, "create_engine", must_not_connect)
    assert prepare_delivery_e2e.main() == 2
