from __future__ import annotations

import os
import threading
from collections.abc import Generator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.domains.it_operations.seed import seed_database
from app.models.product import AppUser, Dashboard, DashboardCard, SavedQuery


LOCAL_POSTGRES_URL = "postgresql+psycopg://queryops:queryops@localhost:5432/queryops"


def test_concurrent_layout_writer_observes_version_conflict_after_row_lock(
    postgres_engine: Engine,
) -> None:
    dashboard_id, card_id = _editor_dashboard(postgres_engine, "Concurrent editor")
    writer_started = threading.Event()
    writer_finished = threading.Event()
    conflict_observed = threading.Event()
    writer_errors: list[Exception] = []

    def stale_writer() -> None:
        try:
            with Session(postgres_engine) as session:
                with session.begin():
                    writer_started.set()
                    dashboard = session.scalar(
                        select(Dashboard)
                        .where(Dashboard.id == dashboard_id)
                        .with_for_update()
                    )
                    assert dashboard is not None
                    if dashboard.layout_version != 1:
                        conflict_observed.set()
                        return
                    card = session.scalar(
                        select(DashboardCard)
                        .where(DashboardCard.id == card_id)
                        .with_for_update()
                    )
                    assert card is not None
                    card.layout = _layout(y=99)
                    dashboard.layout_version += 1
        except Exception as exc:  # pragma: no cover - asserted below.
            writer_errors.append(exc)
        finally:
            writer_finished.set()

    with Session(postgres_engine) as first_writer:
        with first_writer.begin():
            dashboard = first_writer.scalar(
                select(Dashboard)
                .where(Dashboard.id == dashboard_id)
                .with_for_update()
            )
            card = first_writer.scalar(
                select(DashboardCard)
                .where(DashboardCard.id == card_id)
                .with_for_update()
            )
            assert dashboard is not None
            assert card is not None
            card.layout = _layout(y=0)
            dashboard.layout_version += 1

            worker = threading.Thread(target=stale_writer)
            worker.start()
            assert writer_started.wait(timeout=2)
            assert not writer_finished.wait(timeout=0.2)

        assert writer_finished.wait(timeout=2)
        worker.join(timeout=2)

    assert writer_errors == []
    assert conflict_observed.is_set()
    with Session(postgres_engine) as session:
        dashboard = session.get(Dashboard, dashboard_id)
        card = session.get(DashboardCard, card_id)
        assert dashboard is not None
        assert card is not None
        assert dashboard.layout_version == 2
        assert card.layout == _layout(y=0)


def test_failed_editor_transaction_rolls_back_layout_and_version(
    postgres_engine: Engine,
) -> None:
    dashboard_id, card_id = _editor_dashboard(postgres_engine, "Rollback editor")

    with Session(postgres_engine) as session:
        transaction = session.begin()
        dashboard = session.scalar(
            select(Dashboard)
            .where(Dashboard.id == dashboard_id)
            .with_for_update()
        )
        card = session.scalar(
            select(DashboardCard)
            .where(DashboardCard.id == card_id)
            .with_for_update()
        )
        assert dashboard is not None
        assert card is not None
        dashboard.layout_version = 2
        card.layout = _layout(y=7)
        session.flush()
        transaction.rollback()

    with Session(postgres_engine) as session:
        dashboard = session.get(Dashboard, dashboard_id)
        card = session.get(DashboardCard, card_id)
        assert dashboard is not None
        assert card is not None
        assert dashboard.layout_version == 1
        assert card.layout is None


def _editor_dashboard(engine: Engine, title: str) -> tuple:
    with Session(engine) as session:
        analyst = session.scalar(
            select(AppUser).where(AppUser.email == "demo.analyst@queryops.local")
        )
        assert analyst is not None
        dashboard = Dashboard(
            owner_user_id=analyst.id,
            title=title,
            visibility_scope="personal",
        )
        saved_query = SavedQuery(
            owner_user_id=analyst.id,
            name=f"{title} query",
            natural_language_question="Show editor data.",
            generated_sql="SELECT protected_value",
            visibility_scope="personal",
            parameters={},
        )
        session.add_all([dashboard, saved_query])
        session.flush()
        card = DashboardCard(
            dashboard_id=dashboard.id,
            saved_query_id=saved_query.id,
            title="Editor card",
            card_type="table",
            position=0,
        )
        session.add(card)
        session.commit()
        return dashboard.id, card.id


def _layout(*, y: int) -> dict:
    return {
        "version": 1,
        "desktop": {"x": 0, "y": y, "w": 6, "h": 3},
        "tablet": {"x": 0, "y": y, "w": 6, "h": 3},
        "mobile": {"x": 0, "y": y, "w": 1, "h": 3},
    }


@pytest.fixture(scope="session")
def postgres_engine() -> Generator[Engine, None, None]:
    database_url = _postgres_database_url()
    if not database_url.startswith("postgresql"):
        pytest.skip("PostgreSQL dashboard editor tests require PostgreSQL DATABASE_URL.")

    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            assert connection.dialect.name == "postgresql"
            connection.execute(text("SELECT 1"))
    except OperationalError as exc:
        engine.dispose()
        pytest.skip(f"PostgreSQL test database is unavailable: {exc}")

    _run_alembic_upgrade(database_url)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_database(session, profile_name="small", reset=True)
        session.commit()

    try:
        yield engine
    finally:
        engine.dispose()


def _postgres_database_url() -> str:
    explicit_test_url = os.environ.get("POSTGRES_TEST_DATABASE_URL")
    if explicit_test_url:
        return explicit_test_url

    database_url = os.environ.get("DATABASE_URL") or LOCAL_POSTGRES_URL
    parsed_url = make_url(database_url)
    if (
        not parsed_url.drivername.startswith("postgresql")
        or parsed_url.host not in {"localhost", "127.0.0.1", "::1"}
        or parsed_url.database != "queryops"
    ):
        raise pytest.UsageError(
            "Destructive dashboard editor tests require POSTGRES_TEST_DATABASE_URL "
            "or the local queryops PostgreSQL database."
        )
    return database_url


def _run_alembic_upgrade(database_url: str) -> None:
    backend_dir = Path(__file__).resolve().parents[1]
    alembic_config = Config(str(backend_dir / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(backend_dir / "alembic"))

    previous_database_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = database_url
    try:
        command.upgrade(alembic_config, "head")
    finally:
        if previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_database_url
