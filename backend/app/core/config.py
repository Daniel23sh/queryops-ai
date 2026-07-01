import os

SERVICE_NAME = "queryops-backend"
DEFAULT_DATABASE_URL = "postgresql+psycopg://queryops:queryops@localhost:5432/queryops"
DEFAULT_AUTH_MODE = "demo"
DEFAULT_SESSION_SECRET_KEY = "queryops-local-session-secret"
DEFAULT_SESSION_MAX_AGE_SECONDS = 28800
FRONTEND_DEV_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


def normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)

    return database_url


def get_database_url() -> str:
    return normalize_database_url(os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL))


def get_auth_mode() -> str:
    return os.environ.get("AUTH_MODE", DEFAULT_AUTH_MODE)


def get_session_secret_key() -> str:
    return os.environ.get("SESSION_SECRET_KEY", DEFAULT_SESSION_SECRET_KEY)


def get_session_cookie_secure() -> bool:
    return os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true"


def get_session_max_age_seconds() -> int:
    raw_value = os.environ.get(
        "SESSION_MAX_AGE_SECONDS",
        str(DEFAULT_SESSION_MAX_AGE_SECONDS),
    )
    try:
        max_age = int(raw_value)
    except ValueError:
        return DEFAULT_SESSION_MAX_AGE_SECONDS

    if max_age <= 0:
        return DEFAULT_SESSION_MAX_AGE_SECONDS
    return max_age
