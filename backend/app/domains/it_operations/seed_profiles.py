from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SeedProfile:
    name: str
    seed: int
    departments: int
    human_directory_users: int
    service_accounts: int
    devices: int
    licenses: int
    license_assignments: int
    login_events: int
    support_tickets: int
    groups: int
    user_group_memberships: int
    security_events: int
    software_installs: int
    it_audit_events: int
    app_users: int = 4

    @property
    def total_directory_users(self) -> int:
        return self.human_directory_users + self.service_accounts


SEED_PROFILES: dict[str, SeedProfile] = {
    "small": SeedProfile(
        name="small",
        seed=42,
        departments=4,
        human_directory_users=40,
        service_accounts=8,
        devices=60,
        licenses=8,
        license_assignments=100,
        login_events=500,
        support_tickets=50,
        groups=10,
        user_group_memberships=90,
        security_events=40,
        software_installs=160,
        it_audit_events=120,
    ),
    "medium": SeedProfile(
        name="medium",
        seed=42,
        departments=8,
        human_directory_users=600,
        service_accounts=80,
        devices=900,
        licenses=8,
        license_assignments=1200,
        login_events=10000,
        support_tickets=350,
        groups=24,
        user_group_memberships=1200,
        security_events=250,
        software_installs=2000,
        it_audit_events=1000,
    ),
}


def get_seed_profile(name: str) -> SeedProfile:
    try:
        return SEED_PROFILES[name]
    except KeyError as exc:
        choices = ", ".join(sorted(SEED_PROFILES))
        raise ValueError(f"Unknown seed profile {name!r}. Expected one of: {choices}") from exc
