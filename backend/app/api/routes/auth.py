from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy.orm import Session

from fastapi import APIRouter, Depends, Request

from app.api.responses import error_response, success_response
from app.auth.providers import (
    AuthCredentials,
    DemoAuthProvider,
    InactiveUserError,
    InvalidCredentialsError,
)
from app.auth.permissions import (
    get_current_app_user_for_session,
    resolve_effective_permission_keys,
)
from app.auth.session import (
    clear_auth_cookies,
    create_csrf_token,
    csrf_is_valid,
    session_from_request,
    set_auth_cookies,
)
from app.db.session import get_db
from app.domains.it_operations.models import Department
from app.models.product import AppUser, Role, UserStatus


router = APIRouter(prefix="/api/v1")


class DemoLoginRequest(BaseModel):
    email: str


@router.post("/demo/login")
def demo_login(payload: DemoLoginRequest, db: Session = Depends(get_db)):
    provider = DemoAuthProvider()
    try:
        authenticated = provider.authenticate(
            AuthCredentials(email=payload.email),
            db,
        )
    except InvalidCredentialsError:
        return error_response(
            code="UNAUTHORIZED",
            message="Invalid demo login.",
            status_code=401,
        )
    except InactiveUserError:
        return error_response(
            code="FORBIDDEN",
            message="This user is not active.",
            status_code=403,
        )

    csrf_token = create_csrf_token()
    response = success_response(
        {
            "user": serialize_user(authenticated.user, db, authenticated.auth_mode),
            "requires_onboarding": authenticated.user.status != UserStatus.ACTIVE.value,
            "csrf_token": csrf_token,
        }
    )
    set_auth_cookies(
        response,
        user_id=authenticated.user.id,
        auth_provider=authenticated.user.auth_provider,
        csrf_token=csrf_token,
    )
    return response


@router.get("/auth/me")
def auth_me(request: Request, db: Session = Depends(get_db)):
    session_data = session_from_request(request)
    if session_data is None:
        return _unauthorized()

    user = get_current_app_user_for_session(session_data, db)
    if user is None:
        return _unauthorized()

    return success_response(serialize_user(user, db, session_data.auth_provider))


@router.post("/auth/logout")
def auth_logout(request: Request):
    session_data = session_from_request(request)
    if session_data is not None and not csrf_is_valid(request, session_data):
        return error_response(
            code="CSRF_TOKEN_MISSING",
            message="A valid CSRF token is required for this request.",
            status_code=403,
        )

    response = success_response({"ok": True})
    clear_auth_cookies(response)
    return response


def serialize_user(user: AppUser, db: Session, auth_mode: str) -> dict:
    role = db.get(Role, user.role_id) if user.role_id else None
    department = db.get(Department, user.department_id) if user.department_id else None
    return {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "role": role.name if role else None,
        "department_id": str(user.department_id) if user.department_id else None,
        "department": (
            {
                "id": str(department.id),
                "name": department.name,
            }
            if department
            else None
        ),
        "status": user.status,
        "permissions": resolve_effective_permission_keys(user, db),
        "auth_mode": auth_mode,
    }


def _unauthorized():
    return error_response(
        code="UNAUTHORIZED",
        message="Authentication is required.",
        status_code=401,
    )
