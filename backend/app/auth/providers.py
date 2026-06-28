from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.product import AppUser, UserStatus


DEMO_USER_EMAILS = frozenset(
    {
        "demo.admin@queryops.local",
        "demo.analyst@queryops.local",
        "demo.manager@queryops.local",
        "demo.user@queryops.local",
    }
)


@dataclass(frozen=True)
class AuthCredentials:
    email: str | None = None
    access_token: str | None = None


@dataclass(frozen=True)
class AuthenticatedUser:
    user: AppUser
    auth_mode: str


class AuthProvider(Protocol):
    provider_name: str

    def authenticate(
        self,
        credentials: AuthCredentials,
        db: Session,
    ) -> AuthenticatedUser:
        """Authenticate credentials and return the matching local app user."""


class AuthProviderError(Exception):
    """Base class for auth provider failures."""


class InvalidCredentialsError(AuthProviderError):
    """Raised when credentials do not map to an allowed user."""


class InactiveUserError(AuthProviderError):
    """Raised when a local app user exists but cannot log in."""


class AuthProviderUnavailableError(AuthProviderError):
    """Raised when a provider is intentionally unavailable in this PR."""


class DemoAuthProvider:
    provider_name = "demo"

    def authenticate(
        self,
        credentials: AuthCredentials,
        db: Session,
    ) -> AuthenticatedUser:
        email = (credentials.email or "").strip().lower()
        if email not in DEMO_USER_EMAILS:
            raise InvalidCredentialsError("Unknown demo user.")

        user = db.scalar(
            select(AppUser).where(
                AppUser.auth_provider == self.provider_name,
                AppUser.email == email,
            )
        )
        if user is None:
            raise InvalidCredentialsError("Unknown demo user.")

        if user.status != UserStatus.ACTIVE.value:
            raise InactiveUserError("User is not active.")

        return AuthenticatedUser(user=user, auth_mode=self.provider_name)


class SupabaseAuthProvider:
    provider_name = "supabase"

    def authenticate(
        self,
        credentials: AuthCredentials,
        db: Session,
    ) -> AuthenticatedUser:
        raise AuthProviderUnavailableError(
            "Supabase auth is reserved for a later Milestone 2 PR."
        )
