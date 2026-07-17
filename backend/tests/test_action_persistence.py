from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import configure_mappers

from app.db.base import Base
from app.domains.it_operations.models import ItAuditEvent
from app.models.product import (
    ActionPriority,
    ActionRequest,
    ActionRequestStatus,
    AppAuditLog,
    ApprovalStatus,
    ApprovalRequest,
    Notification,
    SupportedActionType,
)


ACTION_STATUS_CONSTRAINT = "ck_action_requests_status"
ACTION_PRIORITY_CONSTRAINT = "ck_action_requests_priority"
ACTION_COUNT_CONSTRAINTS = {
    "ck_action_requests_record_count",
    "ck_action_requests_skipped_count",
}


def test_action_requests_appears_in_base_metadata() -> None:
    assert "action_requests" in Base.metadata.tables


def test_action_and_approval_enums_match_locked_values() -> None:
    assert {value.value for value in SupportedActionType} == {
        "reclaim_unused_license",
        "disable_inactive_user",
    }
    assert {value.value for value in ActionRequestStatus} == {
        "draft_preview",
        "pending_approval",
        "approved_executing",
        "completed",
        "rejected",
        "failed",
        "cancelled",
        "expired",
    }
    assert {value.value for value in ActionPriority} == {"normal", "high", "urgent"}
    assert {value.value for value in ApprovalStatus} == {
        "pending",
        "approved",
        "rejected",
        "cancelled",
        "expired",
    }


def test_action_request_foreign_keys_and_relationships_are_explicit() -> None:
    table = Base.metadata.tables["action_requests"]

    assert _foreign_key_targets_by_column(table) == {
        "requested_by_app_user_id": "app_users",
        "source_query_run_id": "query_runs",
        "department_id": "departments",
        "scope_id": "access_scopes",
    }
    assert set(ActionRequest.__mapper__.relationships.keys()) == {
        "requester",
        "source_query_run",
        "scope",
        "department",
        "approval_request",
        "audit_logs",
    }


def test_action_request_constraints_and_idempotency_uniqueness_exist() -> None:
    table = Base.metadata.tables["action_requests"]
    check_names = {constraint.name for constraint in table.constraints if constraint.name}
    unique_names = {
        constraint.name
        for constraint in table.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }

    assert ACTION_STATUS_CONSTRAINT in check_names
    assert ACTION_PRIORITY_CONSTRAINT in check_names
    assert ACTION_COUNT_CONSTRAINTS <= check_names
    assert "uq_action_requests_idempotency_key" in unique_names


def test_one_approval_per_action_request_is_modeled() -> None:
    approval_table = Base.metadata.tables["approval_requests"]
    unique_columns = {
        tuple(column.name for column in constraint.columns)
        for constraint in approval_table.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }

    assert ("action_request_id",) in unique_columns
    assert ApprovalRequest.__mapper__.relationships["action_request"].uselist is False
    assert ActionRequest.__mapper__.relationships["approval_request"].uselist is False


def test_it_audit_event_keeps_directory_and_app_actor_foreign_keys_separate() -> None:
    table = Base.metadata.tables["it_audit_events"]
    actor_targets = _foreign_key_targets_by_column(table)

    assert actor_targets["actor_user_id"] == "directory_users"
    assert actor_targets["actor_app_user_id"] == "app_users"
    assert ItAuditEvent.__mapper__.relationships["actor_app_user"].uselist is False


def test_existing_notification_schema_represents_m8_notification_contract() -> None:
    table = Base.metadata.tables["notifications"]

    assert {
        "recipient_user_id",
        "notification_type",
        "title",
        "body",
        "related_resource_type",
        "related_resource_id",
        "status",
        "created_at",
        "read_at",
    } <= set(table.columns.keys())
    assert Notification.related_resource_type.property.columns[0].nullable is True
    assert Notification.related_resource_id.property.columns[0].nullable is True


def test_action_audit_fields_preserve_generic_metadata_contract() -> None:
    table = Base.metadata.tables["app_audit_logs"]

    assert {
        "action_request_id",
        "approval_request_id",
        "department_id",
        "scope_id",
        "scope_type",
        "scope_key",
        "severity",
        "before_state_json",
        "after_state_json",
        "self_approved",
        "audit_metadata",
    } <= set(table.columns.keys())
    assert set(AppAuditLog.__mapper__.relationships.keys()) >= {
        "action_request",
        "approval_request",
        "department",
        "scope",
    }


def test_migration_preserves_rows_and_round_trips_0007(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend_dir = Path(__file__).resolve().parents[1]
    database_url = f"sqlite+pysqlite:///{tmp_path / 'action-foundation.sqlite'}"
    alembic_config = Config(str(backend_dir / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(backend_dir / "alembic"))
    monkeypatch.setenv("DATABASE_URL", database_url)

    command.upgrade(alembic_config, "0007_dashboard_layout_version")

    app_user_id = uuid.uuid4().hex
    approval_id = uuid.uuid4().hex
    notification_id = uuid.uuid4().hex
    audit_id = uuid.uuid4().hex
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                """
                INSERT INTO app_users (id, auth_provider, email, full_name, status)
                VALUES (?, 'demo', 'legacy@example.test', 'Legacy User', 'active')
                """,
                (app_user_id,),
            )
            connection.exec_driver_sql(
                """
                INSERT INTO approval_requests
                    (id, requester_user_id, request_type, title, status)
                VALUES (?, ?, 'query_review', 'Legacy approval', 'pending')
                """,
                (approval_id, app_user_id),
            )
            connection.exec_driver_sql(
                """
                INSERT INTO notifications
                    (id, recipient_user_id, notification_type, title, status)
                VALUES (?, ?, 'legacy_notice', 'Legacy notification', 'unread')
                """,
                (notification_id, app_user_id),
            )
            connection.exec_driver_sql(
                """
                INSERT INTO app_audit_logs (id, actor_user_id, event_type, audit_metadata)
                VALUES (?, ?, 'legacy_event', '{"source": "legacy"}')
                """,
                (audit_id, app_user_id),
            )

        command.upgrade(alembic_config, "head")

        upgraded = inspect(engine)
        assert "action_requests" in upgraded.get_table_names()
        assert {
            "action_request_id",
            "required_approver_role",
            "expires_at",
        } <= {column["name"] for column in upgraded.get_columns("approval_requests")}
        assert {
            "action_request_id",
            "approval_request_id",
            "scope_id",
            "before_state_json",
            "after_state_json",
            "self_approved",
        } <= {column["name"] for column in upgraded.get_columns("app_audit_logs")}
        assert "actor_app_user_id" in {
            column["name"] for column in upgraded.get_columns("it_audit_events")
        }
        assert ACTION_STATUS_CONSTRAINT in {
            constraint["name"]
            for constraint in upgraded.get_check_constraints("action_requests")
        }
        assert ACTION_PRIORITY_CONSTRAINT in {
            constraint["name"]
            for constraint in upgraded.get_check_constraints("action_requests")
        }

        with engine.connect() as connection:
            assert connection.exec_driver_sql(
                "SELECT status FROM approval_requests WHERE id = ?",
                (approval_id,),
            ).scalar_one() == "pending"
            assert connection.exec_driver_sql(
                "SELECT status FROM notifications WHERE id = ?",
                (notification_id,),
            ).scalar_one() == "unread"
            assert connection.exec_driver_sql(
                "SELECT event_type FROM app_audit_logs WHERE id = ?",
                (audit_id,),
            ).scalar_one() == "legacy_event"

        action_request_id = uuid.uuid4().hex
        with engine.begin() as connection:
            connection.exec_driver_sql(
                """
                INSERT INTO action_requests (
                    id, action_type, requested_by_app_user_id,
                    access_context_snapshot_json, access_decision_snapshot_json,
                    preview_json, policy_flags_json, skipped_records_json,
                    idempotency_key
                ) VALUES (
                    ?, 'reclaim_unused_license', ?, '{}', '{}', '{}', '{}', '[]', ?
                )
                """,
                (action_request_id, app_user_id, f"action:{action_request_id}"),
            )
            connection.exec_driver_sql(
                """
                INSERT INTO approval_requests
                    (id, action_request_id, request_type, title, status)
                VALUES (?, ?, 'action', 'Action approval', 'pending')
                """,
                (uuid.uuid4().hex, action_request_id),
            )

        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.exec_driver_sql(
                    """
                    INSERT INTO approval_requests
                        (id, action_request_id, request_type, title, status)
                    VALUES (?, ?, 'action', 'Duplicate action approval', 'pending')
                    """,
                    (uuid.uuid4().hex, action_request_id),
                )

        command.downgrade(alembic_config, "0007_dashboard_layout_version")

        downgraded = inspect(engine)
        assert "action_requests" not in downgraded.get_table_names()
        assert "action_request_id" not in {
            column["name"] for column in downgraded.get_columns("approval_requests")
        }
        with engine.connect() as connection:
            assert connection.exec_driver_sql(
                "SELECT title FROM approval_requests WHERE id = ?",
                (approval_id,),
            ).scalar_one() == "Legacy approval"
            assert connection.exec_driver_sql(
                "SELECT title FROM notifications WHERE id = ?",
                (notification_id,),
            ).scalar_one() == "Legacy notification"
            assert connection.exec_driver_sql(
                "SELECT event_type FROM app_audit_logs WHERE id = ?",
                (audit_id,),
            ).scalar_one() == "legacy_event"
    finally:
        engine.dispose()


def test_all_mappers_configure_with_action_relationships() -> None:
    configure_mappers()


def _foreign_key_targets_by_column(table) -> dict[str, str]:
    return {
        foreign_key.parent.name: foreign_key.column.table.name
        for foreign_key in table.foreign_keys
    }
