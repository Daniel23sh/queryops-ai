from __future__ import annotations

import uuid
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.models.product import Dashboard


def test_dashboard_layout_version_migration_backfills_defaults_and_downgrades(
    tmp_path: Path,
    monkeypatch,
) -> None:
    backend_dir = Path(__file__).resolve().parents[1]
    database_path = tmp_path / "queryops_dashboard_editor.sqlite"
    database_url = f"sqlite+pysqlite:///{database_path}"
    alembic_config = Config(str(backend_dir / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(backend_dir / "alembic"))
    monkeypatch.setenv("DATABASE_URL", database_url)

    command.upgrade(alembic_config, "0006_query_runtime_role")
    existing_dashboard_id = uuid.uuid4()
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO dashboards (
                        id,
                        title,
                        visibility_scope,
                        is_archived
                    ) VALUES (
                        :id,
                        :title,
                        'personal',
                        false
                    )
                    """
                ),
                {
                    "id": existing_dashboard_id.hex,
                    "title": "Existing dashboard",
                },
            )
    finally:
        engine.dispose()

    command.upgrade(alembic_config, "head")
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            assert connection.scalar(
                text(
                    "SELECT layout_version FROM dashboards WHERE id = :id"
                ),
                {"id": existing_dashboard_id.hex},
            ) == 1

        with Session(engine) as session:
            new_dashboard = Dashboard(
                title="New dashboard",
                visibility_scope="personal",
            )
            session.add(new_dashboard)
            session.commit()
            session.refresh(new_dashboard)
            assert new_dashboard.layout_version == 1
    finally:
        engine.dispose()

    command.downgrade(alembic_config, "0006_query_runtime_role")
    engine = create_engine(database_url)
    try:
        column_names = {
            column["name"] for column in inspect(engine).get_columns("dashboards")
        }
        assert "layout_version" not in column_names
    finally:
        engine.dispose()
