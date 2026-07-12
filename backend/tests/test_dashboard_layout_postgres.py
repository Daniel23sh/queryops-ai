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


def test_dashboard_layout_lock_blocks_concurrent_card_insert(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session:
        manager = user_by_email(session, "demo.manager@queryops.local")
        dashboard = Dashboard(
            owner_user_id=manager.id,
            title="Concurrent layout dashboard",
            visibility_scope="personal",
        )
        saved_query = SavedQuery(
            owner_user_id=manager.id,
            name="Concurrent layout query",
            natural_language_question="Show saved cards.",
            generated_sql="SELECT private_value_that_must_not_leak",
            visibility_scope="personal",
            parameters={},
        )
        session.add_all([dashboard, saved_query])
        session.flush()
        session.add(
            DashboardCard(
                dashboard_id=dashboard.id,
                saved_query_id=saved_query.id,
                title="Existing card",
                card_type="table",
                position=0,
            )
        )
        session.commit()
        dashboard_id = dashboard.id
        saved_query_id = saved_query.id

    insert_started = threading.Event()
    insert_finished = threading.Event()
    insert_errors: list[Exception] = []

    def insert_card() -> None:
        try:
            with Session(postgres_engine) as session:
                insert_started.set()
                session.add(
                    DashboardCard(
                        dashboard_id=dashboard_id,
                        saved_query_id=saved_query_id,
                        title="Concurrent card",
                        card_type="table",
                        position=1,
                    )
                )
                session.commit()
        except Exception as exc:  # pragma: no cover - asserted below.
            insert_errors.append(exc)
        finally:
            insert_finished.set()

    with Session(postgres_engine) as locked_session:
        with locked_session.begin():
            locked_dashboard = locked_session.scalar(
                select(Dashboard)
                .where(Dashboard.id == dashboard_id)
                .with_for_update()
            )
            assert locked_dashboard is not None

            worker = threading.Thread(target=insert_card)
            worker.start()
            assert insert_started.wait(timeout=2)
            assert not insert_finished.wait(timeout=0.2)

        assert insert_finished.wait(timeout=2)
        worker.join(timeout=2)

    assert insert_errors == []
    with Session(postgres_engine) as session:
        cards = session.scalars(
            select(DashboardCard)
            .where(DashboardCard.dashboard_id == dashboard_id)
            .order_by(DashboardCard.position)
        ).all()
    assert [card.title for card in cards] == ["Existing card", "Concurrent card"]


def user_by_email(session: Session, email: str) -> AppUser:
    user = session.scalar(select(AppUser).where(AppUser.email == email))
    assert user is not None
    return user


@pytest.fixture(scope="session")
def postgres_engine() -> Generator[Engine, None, None]:
    database_url = postgres_database_url()
    if not database_url.startswith("postgresql"):
        pytest.skip("PostgreSQL dashboard layout tests require PostgreSQL DATABASE_URL.")

    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            assert connection.dialect.name == "postgresql"
            connection.execute(text("SELECT 1"))
    except OperationalError as exc:
        engine.dispose()
        pytest.skip(f"PostgreSQL test database is unavailable: {exc}")

    run_alembic_upgrade(database_url)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_database(session, profile_name="small", reset=True)
        session.commit()

    try:
        yield engine
    finally:
        engine.dispose()


def postgres_database_url() -> str:
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
            "Destructive dashboard layout tests require POSTGRES_TEST_DATABASE_URL "
            "or the local queryops PostgreSQL database."
        )
    return database_url


def run_alembic_upgrade(database_url: str) -> None:
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
