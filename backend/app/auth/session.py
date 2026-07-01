from __future__ import annotations

import base64
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from hashlib import sha256
from typing import Any
from uuid import UUID

from fastapi import Request
from fastapi.responses import Response

from app.core.config import (
    get_session_cookie_secure,
    get_session_max_age_seconds,
    get_session_secret_key,
)


SESSION_COOKIE_NAME = "qo_session"
CSRF_COOKIE_NAME = "qo_csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"


@dataclass(frozen=True)
class SessionData:
    user_id: UUID
    auth_provider: str
    csrf_token: str
    iat: int
    exp: int


def create_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def create_session_token(
    *,
    user_id: UUID,
    auth_provider: str,
    csrf_token: str,
) -> str:
    issued_at = int(time.time())
    expires_at = issued_at + get_session_max_age_seconds()
    payload = {
        "user_id": str(user_id),
        "auth_provider": auth_provider,
        "csrf_token": csrf_token,
        "iat": issued_at,
        "exp": expires_at,
    }
    encoded_payload = _base64_encode_json(payload)
    signature = _sign(encoded_payload)
    return f"{encoded_payload}.{signature}"


def decode_session_token(token: str | None) -> SessionData | None:
    if not token or "." not in token:
        return None

    encoded_payload, signature = token.rsplit(".", 1)
    if not hmac.compare_digest(_sign(encoded_payload), signature):
        return None

    try:
        payload = _base64_decode_json(encoded_payload)
        issued_at = int(payload["iat"])
        expires_at = int(payload["exp"])
        if expires_at <= int(time.time()):
            return None
        return SessionData(
            user_id=UUID(str(payload["user_id"])),
            auth_provider=str(payload["auth_provider"]),
            csrf_token=str(payload["csrf_token"]),
            iat=issued_at,
            exp=expires_at,
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def session_from_request(request: Request) -> SessionData | None:
    return decode_session_token(request.cookies.get(SESSION_COOKIE_NAME))


def csrf_is_valid(request: Request, session_data: SessionData) -> bool:
    header_token = request.headers.get(CSRF_HEADER_NAME)
    cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
    if not header_token or not cookie_token:
        return False

    return (
        hmac.compare_digest(header_token, session_data.csrf_token)
        and hmac.compare_digest(cookie_token, session_data.csrf_token)
    )


def set_auth_cookies(
    response: Response,
    *,
    user_id: UUID,
    auth_provider: str,
    csrf_token: str,
) -> None:
    secure = get_session_cookie_secure()
    max_age = get_session_max_age_seconds()
    response.set_cookie(
        SESSION_COOKIE_NAME,
        create_session_token(
            user_id=user_id,
            auth_provider=auth_provider,
            csrf_token=csrf_token,
        ),
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
        max_age=max_age,
    )
    response.set_cookie(
        CSRF_COOKIE_NAME,
        csrf_token,
        httponly=False,
        secure=secure,
        samesite="lax",
        path="/",
        max_age=max_age,
    )


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME, path="/", samesite="lax")
    response.delete_cookie(CSRF_COOKIE_NAME, path="/", samesite="lax")


def _base64_encode_json(payload: dict[str, Any]) -> str:
    raw_payload = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return base64.urlsafe_b64encode(raw_payload).decode().rstrip("=")


def _base64_decode_json(encoded_payload: str) -> dict[str, Any]:
    padded_payload = encoded_payload + "=" * (-len(encoded_payload) % 4)
    raw_payload = base64.urlsafe_b64decode(padded_payload.encode())
    decoded = json.loads(raw_payload)
    if not isinstance(decoded, dict):
        raise TypeError("Session payload must be an object.")
    return decoded


def _sign(encoded_payload: str) -> str:
    digest = hmac.new(
        get_session_secret_key().encode(),
        encoded_payload.encode(),
        sha256,
    ).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")
