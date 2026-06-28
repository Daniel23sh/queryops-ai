from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.core.config import get_database_url, normalize_database_url
from app.db.base import Base
from app.db.session import create_session_factory


def test_database_url_defaults_to_psycopg_driver(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert get_database_url().startswith("postgresql+psycopg://")


def test_database_url_normalizes_postgresql_scheme() -> None:
    database_url = "postgresql://queryops:queryops@localhost:5432/queryops"

    assert (
        normalize_database_url(database_url)
        == "postgresql+psycopg://queryops:queryops@localhost:5432/queryops"
    )


def test_database_metadata_starts_without_tables() -> None:
    assert not Base.metadata.tables


def test_session_factory_can_create_session_without_connecting() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = create_session_factory(engine)

    session = session_factory()
    try:
        assert session.bind is engine
    finally:
        session.close()
