from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.db.base import Base


PRODUCT_TABLES = {
    "app_users",
    "roles",
    "permissions",
    "role_permissions",
    "user_permissions",
    "role_upgrade_requests",
    "dashboards",
    "dashboard_cards",
    "saved_queries",
    "query_runs",
    "approval_requests",
    "notifications",
    "evaluation_runs",
    "evaluation_results",
    "app_audit_logs",
}

IT_OPERATIONS_DOMAIN_TABLES = {
    "departments",
    "directory_users",
    "login_events",
    "licenses",
    "license_assignments",
    "devices",
    "software_installs",
    "support_tickets",
    "groups",
    "user_group_memberships",
    "security_events",
    "it_audit_events",
}


def test_base_metadata_registers_product_tables_only() -> None:
    table_names = set(Base.metadata.tables)

    assert PRODUCT_TABLES <= table_names
    assert IT_OPERATIONS_DOMAIN_TABLES.isdisjoint(table_names)


def test_product_schema_has_key_foreign_keys() -> None:
    metadata = Base.metadata

    assert _foreign_key_targets(metadata.tables["app_users"]) == {"roles"}
    assert _foreign_key_targets(metadata.tables["role_permissions"]) == {
        "roles",
        "permissions",
    }
    assert _foreign_key_targets(metadata.tables["user_permissions"]) == {
        "app_users",
        "permissions",
    }
    assert _foreign_key_targets(metadata.tables["role_upgrade_requests"]) == {
        "app_users",
        "roles",
    }
    assert _foreign_key_targets(metadata.tables["dashboard_cards"]) == {
        "dashboards",
        "saved_queries",
    }
    assert _foreign_key_targets(metadata.tables["query_runs"]) == {
        "app_users",
        "saved_queries",
    }
    assert _foreign_key_targets(metadata.tables["approval_requests"]) == {
        "app_users",
        "query_runs",
    }
    assert _foreign_key_targets(metadata.tables["evaluation_results"]) == {
        "evaluation_runs",
        "query_runs",
    }


def test_role_permissions_uses_composite_primary_key() -> None:
    primary_key_columns = {
        column.name for column in Base.metadata.tables["role_permissions"].primary_key
    }

    assert primary_key_columns == {"role_id", "permission_id"}


def test_product_migration_upgrades_and_downgrades_sqlite_database(
    tmp_path: Path,
    monkeypatch,
) -> None:
    backend_dir = Path(__file__).resolve().parents[1]
    database_path = tmp_path / "queryops_product_schema.sqlite"
    database_url = f"sqlite+pysqlite:///{database_path}"
    alembic_config = Config(str(backend_dir / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(backend_dir / "alembic"))
    monkeypatch.setenv("DATABASE_URL", database_url)

    command.upgrade(alembic_config, "head")

    engine = create_engine(database_url)
    try:
        upgraded_tables = set(inspect(engine).get_table_names())
        assert PRODUCT_TABLES <= upgraded_tables
        assert IT_OPERATIONS_DOMAIN_TABLES.isdisjoint(upgraded_tables)
    finally:
        engine.dispose()

    command.downgrade(alembic_config, "base")

    engine = create_engine(database_url)
    try:
        downgraded_tables = set(inspect(engine).get_table_names())
        assert PRODUCT_TABLES.isdisjoint(downgraded_tables)
    finally:
        engine.dispose()


def _foreign_key_targets(table) -> set[str]:
    return {foreign_key.column.table.name for foreign_key in table.foreign_keys}
