from importlib import import_module
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


def test_base_metadata_registers_product_and_it_operations_tables() -> None:
    table_names = set(Base.metadata.tables)

    assert PRODUCT_TABLES <= table_names
    assert IT_OPERATIONS_DOMAIN_TABLES <= table_names


def test_directory_users_and_app_users_are_separate_tables() -> None:
    metadata = Base.metadata

    assert metadata.tables["app_users"] is not metadata.tables["directory_users"]
    assert "auth_provider" in metadata.tables["app_users"].columns
    assert "employee_number" in metadata.tables["directory_users"].columns


def test_it_operations_schema_has_key_foreign_keys() -> None:
    metadata = Base.metadata

    assert _foreign_key_targets(metadata.tables["directory_users"]) == {
        "departments",
        "directory_users",
    }
    assert _foreign_key_targets(metadata.tables["login_events"]) == {
        "departments",
        "devices",
        "directory_users",
    }
    assert _foreign_key_targets(metadata.tables["license_assignments"]) == {
        "app_users",
        "departments",
        "directory_users",
        "licenses",
    }
    assert _foreign_key_targets(metadata.tables["devices"]) == {
        "departments",
        "directory_users",
    }
    assert _foreign_key_targets(metadata.tables["software_installs"]) == {
        "departments",
        "devices",
    }
    assert _foreign_key_targets(metadata.tables["support_tickets"]) == {
        "departments",
        "directory_users",
    }
    assert _foreign_key_targets(metadata.tables["groups"]) == {"departments"}
    assert _foreign_key_targets(metadata.tables["user_group_memberships"]) == {
        "departments",
        "directory_users",
        "groups",
    }
    assert _foreign_key_targets(metadata.tables["security_events"]) == {
        "departments",
        "devices",
        "directory_users",
    }
    assert _foreign_key_targets(metadata.tables["it_audit_events"]) == {
        "departments",
        "directory_users",
    }


def test_user_group_memberships_uses_composite_primary_key() -> None:
    primary_key_columns = {
        column.name
        for column in Base.metadata.tables["user_group_memberships"].primary_key
    }

    assert primary_key_columns == {"user_id", "group_id"}


def test_it_operations_models_live_in_domain_package() -> None:
    domain_models = import_module("app.domains.it_operations.models")
    product_models = import_module("app.models.product")

    assert domain_models.DirectoryUser.__module__ == "app.domains.it_operations.models"
    assert domain_models.ItAuditEvent.__tablename__ == "it_audit_events"
    assert not hasattr(product_models, "DirectoryUser")
    assert not hasattr(product_models, "ItAuditEvent")


def test_domain_models_do_not_add_seed_or_generation_behavior() -> None:
    domain_models_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "domains"
        / "it_operations"
        / "models.py"
    )
    domain_models_source = domain_models_path.read_text()

    assert "Faker" not in domain_models_source
    assert "seed" not in domain_models_source.lower()


def test_it_operations_migration_upgrades_and_downgrades_sqlite_database(
    tmp_path: Path,
    monkeypatch,
) -> None:
    backend_dir = Path(__file__).resolve().parents[1]
    database_path = tmp_path / "queryops_it_operations_schema.sqlite"
    database_url = f"sqlite+pysqlite:///{database_path}"
    alembic_config = Config(str(backend_dir / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(backend_dir / "alembic"))
    monkeypatch.setenv("DATABASE_URL", database_url)

    command.upgrade(alembic_config, "head")

    engine = create_engine(database_url)
    try:
        upgraded_tables = set(inspect(engine).get_table_names())
        assert PRODUCT_TABLES <= upgraded_tables
        assert IT_OPERATIONS_DOMAIN_TABLES <= upgraded_tables
    finally:
        engine.dispose()

    command.downgrade(alembic_config, "0002_product_schema")

    engine = create_engine(database_url)
    try:
        downgraded_tables = set(inspect(engine).get_table_names())
        assert PRODUCT_TABLES <= downgraded_tables
        assert IT_OPERATIONS_DOMAIN_TABLES.isdisjoint(downgraded_tables)
    finally:
        engine.dispose()


def _foreign_key_targets(table) -> set[str]:
    return {foreign_key.column.table.name for foreign_key in table.foreign_keys}
