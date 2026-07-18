from __future__ import annotations

import ipaddress
import os
import re

import pytest
from sqlalchemy.engine import URL, make_url


_SAFE_DATABASE_MARKER = re.compile(r"(?:^|[_-])(?:test|dev)(?:$|[_-])", re.IGNORECASE)
_ENDPOINT_QUERY_KEYS = frozenset(
    {"database", "dbname", "host", "hostaddr", "port", "service", "servicefile"}
)


def validated_disposable_database_url(database_url: str) -> str:
    if os.environ.get("POSTGRES_TEST_DATABASE_DISPOSABLE") != "1":
        pytest.fail(
            "Set POSTGRES_TEST_DATABASE_DISPOSABLE=1 to permit destructive action tests."
        )
    parsed = make_url(database_url)
    database_name = parsed.database
    if parsed.get_backend_name() != "postgresql" or not database_name:
        pytest.fail("Action tests require an explicit PostgreSQL database.")
    if _ENDPOINT_QUERY_KEYS.intersection(parsed.query):
        pytest.fail(
            "Destructive test database URLs cannot override the endpoint in "
            "query parameters."
        )
    if not _is_local_endpoint(parsed):
        pytest.fail("Destructive action tests require a local PostgreSQL endpoint.")

    application_url = os.environ.get("DATABASE_URL")
    if application_url:
        parsed_application_url = make_url(application_url)
        if _ENDPOINT_QUERY_KEYS.intersection(parsed_application_url.query):
            pytest.fail(
                "Cannot safely compare DATABASE_URL when it overrides the endpoint "
                "in query parameters."
            )
        if _database_identity(parsed_application_url) == _database_identity(parsed):
            pytest.fail("Refusing to use DATABASE_URL for destructive action tests.")
    application_database_name = os.environ.get("POSTGRES_DB", "queryops")
    if database_name.lower() == application_database_name.lower():
        pytest.fail(
            "Refusing to use the configured application database for destructive tests."
        )
    if _SAFE_DATABASE_MARKER.search(database_name) is None:
        pytest.fail(
            "The destructive test database name must include a test or dev marker."
        )
    return database_url


def _is_local_endpoint(database_url: URL) -> bool:
    host = (database_url.host or "localhost").rstrip(".").lower()
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _database_identity(database_url: URL) -> tuple[str, int, str | None]:
    host = (database_url.host or "localhost").rstrip(".").lower()
    try:
        if ipaddress.ip_address(host).is_loopback:
            host = "localhost"
    except ValueError:
        pass
    return host, database_url.port or 5432, database_url.database
