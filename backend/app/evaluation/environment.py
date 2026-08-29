from __future__ import annotations

import hashlib
import json
import math
import platform
import re
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.base import Base
from app.domains.it_operations.seed import SeedSummary, expected_seed_table_counts
from app.evaluation.loader import load_it_operations_evaluation_set
from app.evaluation.selection import evaluation_dataset_digest
from app.query_engine.domain_pack_loader import load_it_operations_domain_pack
from app.query_engine.semantic_catalog import semantic_catalog_identity


EVALUATION_ENVIRONMENT_MANIFEST_VERSION = "queryops-evaluation-environment-v1"
EVALUATION_SEED_VERSION = "it-operations-seed-v1"
MAX_MANIFEST_BYTES = 64_000
MAX_REFERENCE_AGE = timedelta(hours=24)
MAX_FUTURE_SKEW = timedelta(minutes=5)
_SAFE_REVISION = re.compile(r"^[A-Za-z0-9_]{1,128}$")
_SAFE_SHA = re.compile(r"^[0-9a-f]{40}$")
_SAFE_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_SAFE_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+_ -]{0,127}$")

_FINGERPRINT_TABLES = (
    "access_scopes",
    "app_users",
    "data_resources",
    "departments",
    "devices",
    "directory_users",
    "groups",
    "license_assignments",
    "licenses",
    "login_events",
    "permissions",
    "role_permissions",
    "roles",
    "security_events",
    "software_installs",
    "support_tickets",
    "user_access_scopes",
    "user_group_memberships",
    "user_permissions",
)
_RUNTIME_PACKAGES = ("faker", "openai", "psycopg", "sqlalchemy")


class EvaluationEnvironmentError(RuntimeError):
    def __init__(self, code: str = "evaluation_environment_invalid") -> None:
        super().__init__("Evaluation environment evidence is invalid.")
        self.code = code
        self.safe_message = "Evaluation environment evidence is invalid."


@dataclass(frozen=True)
class EvaluationEnvironmentIdentity:
    manifest_version: str
    seed_version: str
    seed_profile: str
    seed: int
    reference_time: str
    source_git_sha: str
    alembic_revision: str
    postgres_version: str
    database_fingerprint: str
    dependency_manifest_hash: str

    def as_dict(self) -> dict[str, str | int]:
        return {
            "manifest_version": self.manifest_version,
            "seed_version": self.seed_version,
            "seed_profile": self.seed_profile,
            "seed": self.seed,
            "reference_time": self.reference_time,
            "source_git_sha": self.source_git_sha,
            "alembic_revision": self.alembic_revision,
            "postgres_version": self.postgres_version,
            "database_fingerprint": self.database_fingerprint,
            "dependency_manifest_hash": self.dependency_manifest_hash,
        }


def build_evaluation_environment_manifest(
    db: Session,
    seed_summary: SeedSummary,
    *,
    source_git_sha: str | None = None,
) -> dict[str, Any]:
    _require_release_database(db)
    if seed_summary.profile_name != "medium":
        raise EvaluationEnvironmentError("evaluation_seed_profile_invalid")
    if (
        seed_summary.seed != 42
        or seed_summary.table_counts != expected_seed_table_counts("medium")
    ):
        raise EvaluationEnvironmentError("evaluation_seed_profile_invalid")
    source_sha = source_git_sha or _clean_source_git_sha()
    if _SAFE_SHA.fullmatch(source_sha) is None:
        raise EvaluationEnvironmentError("evaluation_source_revision_invalid")

    evaluation_set = load_it_operations_evaluation_set()
    catalog = load_it_operations_domain_pack().semantic_catalog
    database_digest, table_counts = evaluation_database_fingerprint(db)
    identity = EvaluationEnvironmentIdentity(
        manifest_version=EVALUATION_ENVIRONMENT_MANIFEST_VERSION,
        seed_version=EVALUATION_SEED_VERSION,
        seed_profile=seed_summary.profile_name,
        seed=seed_summary.seed,
        reference_time=_utc_text(seed_summary.reference_now),
        source_git_sha=source_sha,
        alembic_revision=_alembic_revision(db),
        postgres_version=_postgres_version(db),
        database_fingerprint=database_digest,
        dependency_manifest_hash=_dependency_manifest_hash(),
    )
    return {
        "identity": identity.as_dict(),
        "dataset": {
            "id": evaluation_set.dataset_id,
            "version": evaluation_set.version,
            "digest": evaluation_dataset_digest(evaluation_set),
        },
        "semantic_catalog": semantic_catalog_identity(catalog),
        "database": {
            "table_counts": table_counts,
            "anomaly_counts": dict(sorted(seed_summary.anomaly_counts.items())),
        },
        "runtime": {
            "python": platform.python_version(),
            "packages": _runtime_versions(),
        },
    }


def write_evaluation_environment_manifest(
    path: str | Path,
    manifest: Mapping[str, Any],
) -> None:
    payload = json.dumps(
        manifest,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    if len(payload.encode("utf-8")) > MAX_MANIFEST_BYTES:
        raise EvaluationEnvironmentError("evaluation_environment_invalid")
    target = Path(path)
    try:
        with target.open("x", encoding="utf-8") as handle:
            handle.write(payload)
            handle.write("\n")
    except FileExistsError as exc:
        raise EvaluationEnvironmentError("evaluation_manifest_exists") from exc
    except OSError as exc:
        raise EvaluationEnvironmentError("evaluation_manifest_write_failed") from exc


def validate_evaluation_environment_manifest(
    db: Session,
    path: str | Path,
    *,
    now: datetime | None = None,
    source_git_sha: str | None = None,
) -> EvaluationEnvironmentIdentity:
    document = _load_manifest(path)
    identity = _parse_identity(document.get("identity"))
    expected_sha = source_git_sha or _clean_source_git_sha()
    if identity.source_git_sha != expected_sha:
        raise EvaluationEnvironmentError("evaluation_source_revision_mismatch")

    reference_time = _parse_utc_text(identity.reference_time)
    current_time = (now or datetime.now(UTC)).astimezone(UTC)
    age = current_time - reference_time
    if age < -MAX_FUTURE_SKEW or age > MAX_REFERENCE_AGE:
        raise EvaluationEnvironmentError("evaluation_reference_time_stale")

    _require_release_database(db)
    digest, table_counts = evaluation_database_fingerprint(db)
    if (
        identity.alembic_revision != _alembic_revision(db)
        or identity.postgres_version != _postgres_version(db)
        or identity.database_fingerprint != digest
        or identity.dependency_manifest_hash != _dependency_manifest_hash()
    ):
        raise EvaluationEnvironmentError("evaluation_environment_mismatch")

    database = _exact_mapping(document.get("database"), {"table_counts", "anomaly_counts"})
    if database is None or database.get("table_counts") != table_counts:
        raise EvaluationEnvironmentError("evaluation_environment_mismatch")
    if not _valid_counts(database.get("anomaly_counts")):
        raise EvaluationEnvironmentError("evaluation_environment_invalid")

    evaluation_set = load_it_operations_evaluation_set()
    expected_dataset = {
        "id": evaluation_set.dataset_id,
        "version": evaluation_set.version,
        "digest": evaluation_dataset_digest(evaluation_set),
    }
    if document.get("dataset") != expected_dataset:
        raise EvaluationEnvironmentError("evaluation_dataset_identity_mismatch")
    expected_catalog = semantic_catalog_identity(
        load_it_operations_domain_pack().semantic_catalog
    )
    if document.get("semantic_catalog") != expected_catalog:
        raise EvaluationEnvironmentError("evaluation_catalog_identity_mismatch")

    runtime = _exact_mapping(document.get("runtime"), {"python", "packages"})
    if runtime is None or runtime.get("python") != platform.python_version():
        raise EvaluationEnvironmentError("evaluation_environment_mismatch")
    if runtime.get("packages") != _runtime_versions():
        raise EvaluationEnvironmentError("evaluation_environment_mismatch")
    return identity


def validate_persisted_environment_identity(
    value: Any,
) -> EvaluationEnvironmentIdentity | None:
    try:
        return _parse_identity(value)
    except EvaluationEnvironmentError:
        return None


def reference_time_is_eligible(
    identity: EvaluationEnvironmentIdentity,
    started_at: datetime,
) -> bool:
    try:
        reference_time = _parse_utc_text(identity.reference_time)
    except EvaluationEnvironmentError:
        return False
    normalized_start = (
        started_at.replace(tzinfo=UTC)
        if started_at.tzinfo is None
        else started_at.astimezone(UTC)
    )
    age = normalized_start - reference_time
    return -MAX_FUTURE_SKEW <= age <= MAX_REFERENCE_AGE


def evaluation_database_fingerprint(db: Session) -> tuple[str, dict[str, int]]:
    hasher = hashlib.sha256()
    counts: dict[str, int] = {}
    for table_name in _FINGERPRINT_TABLES:
        table = Base.metadata.tables.get(table_name)
        if table is None:
            raise EvaluationEnvironmentError("evaluation_environment_invalid")
        primary_keys = tuple(table.primary_key.columns)
        if not primary_keys:
            raise EvaluationEnvironmentError("evaluation_environment_invalid")
        rows = db.execute(select(table).order_by(*primary_keys)).mappings()
        count = 0
        hasher.update(f"table:{table_name}\n".encode())
        for row in rows:
            document = {
                column.name: _canonical_value(row[column.name])
                for column in table.columns
            }
            encoded = json.dumps(
                document,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            ).encode("utf-8")
            hasher.update(encoded)
            hasher.update(b"\n")
            count += 1
        counts[table_name] = count
        hasher.update(f"count:{count}\n".encode())
    return hasher.hexdigest(), counts


def _canonical_value(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise EvaluationEnvironmentError("evaluation_environment_invalid")
        return format(value, ".17g")
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        return _utc_text(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Enum):
        return _canonical_value(value.value)
    if isinstance(value, Mapping):
        return {
            str(key): _canonical_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, list | tuple):
        return [_canonical_value(item) for item in value]
    raise EvaluationEnvironmentError("evaluation_environment_invalid")


def _parse_identity(value: Any) -> EvaluationEnvironmentIdentity:
    fields = {
        "manifest_version",
        "seed_version",
        "seed_profile",
        "seed",
        "reference_time",
        "source_git_sha",
        "alembic_revision",
        "postgres_version",
        "database_fingerprint",
        "dependency_manifest_hash",
    }
    mapping = _exact_mapping(value, fields)
    if mapping is None:
        raise EvaluationEnvironmentError()
    seed = mapping.get("seed")
    identity = EvaluationEnvironmentIdentity(
        manifest_version=_safe_text(mapping.get("manifest_version")),
        seed_version=_safe_text(mapping.get("seed_version")),
        seed_profile=_safe_text(mapping.get("seed_profile")),
        seed=(seed if isinstance(seed, int) and not isinstance(seed, bool) else -1),
        reference_time=_safe_text(mapping.get("reference_time")),
        source_git_sha=_safe_text(mapping.get("source_git_sha")),
        alembic_revision=_safe_text(mapping.get("alembic_revision")),
        postgres_version=_safe_text(mapping.get("postgres_version")),
        database_fingerprint=_safe_text(mapping.get("database_fingerprint")),
        dependency_manifest_hash=_safe_text(mapping.get("dependency_manifest_hash")),
    )
    if (
        identity.manifest_version != EVALUATION_ENVIRONMENT_MANIFEST_VERSION
        or identity.seed_version != EVALUATION_SEED_VERSION
        or identity.seed_profile != "medium"
        or not 0 <= identity.seed <= 2_147_483_647
        or _SAFE_SHA.fullmatch(identity.source_git_sha) is None
        or _SAFE_REVISION.fullmatch(identity.alembic_revision) is None
        or _SAFE_VERSION.fullmatch(identity.postgres_version) is None
        or _SAFE_DIGEST.fullmatch(identity.database_fingerprint) is None
        or _SAFE_DIGEST.fullmatch(identity.dependency_manifest_hash) is None
    ):
        raise EvaluationEnvironmentError()
    _parse_utc_text(identity.reference_time)
    return identity


def _load_manifest(path: str | Path) -> Mapping[str, Any]:
    target = Path(path)
    try:
        if target.stat().st_size > MAX_MANIFEST_BYTES:
            raise EvaluationEnvironmentError()
        value = json.loads(target.read_text(encoding="utf-8"))
    except EvaluationEnvironmentError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvaluationEnvironmentError() from exc
    mapping = _exact_mapping(
        value,
        {"identity", "dataset", "semantic_catalog", "database", "runtime"},
    )
    if mapping is None:
        raise EvaluationEnvironmentError()
    return mapping


def _require_release_database(db: Session) -> None:
    if db.get_bind().dialect.name != "postgresql":
        raise EvaluationEnvironmentError("postgres_required")
    database_name = db.scalar(text("SELECT current_database()"))
    if not isinstance(database_name, str) or not any(
        marker in database_name.lower() for marker in ("test", "eval", "e2e")
    ):
        raise EvaluationEnvironmentError("disposable_database_required")


def _alembic_revision(db: Session) -> str:
    revision = db.scalar(text("SELECT version_num FROM alembic_version"))
    if not isinstance(revision, str) or _SAFE_REVISION.fullmatch(revision) is None:
        raise EvaluationEnvironmentError("evaluation_environment_invalid")
    return revision


def _postgres_version(db: Session) -> str:
    value = db.scalar(text("SHOW server_version"))
    return _safe_text(value)


def _dependency_manifest_hash() -> str:
    path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise EvaluationEnvironmentError("evaluation_environment_invalid") from exc


def _runtime_versions() -> dict[str, str]:
    result: dict[str, str] = {}
    for package in _RUNTIME_PACKAGES:
        try:
            result[package] = _safe_text(version(package))
        except PackageNotFoundError as exc:
            raise EvaluationEnvironmentError("evaluation_environment_invalid") from exc
    return result


def _clean_source_git_sha() -> str:
    repository = Path(__file__).resolve().parents[3]
    try:
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise EvaluationEnvironmentError("evaluation_source_revision_invalid") from exc
    if status.stdout or _SAFE_SHA.fullmatch(revision) is None:
        raise EvaluationEnvironmentError("evaluation_source_revision_invalid")
    return revision


def _utc_text(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    normalized = value.astimezone(UTC).replace(microsecond=0)
    return normalized.isoformat().replace("+00:00", "Z")


def _parse_utc_text(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise EvaluationEnvironmentError() from exc
    if parsed.tzinfo is None or _utc_text(parsed) != value:
        raise EvaluationEnvironmentError()
    return parsed.astimezone(UTC)


def _safe_text(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 128
        or any(ord(character) < 32 for character in value)
    ):
        raise EvaluationEnvironmentError()
    return value


def _exact_mapping(value: Any, fields: set[str]) -> Mapping[str, Any] | None:
    if not isinstance(value, Mapping) or set(value) != fields:
        return None
    return value


def _valid_counts(value: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and all(
            isinstance(key, str)
            and isinstance(count, int)
            and not isinstance(count, bool)
            and 0 <= count <= 10_000_000
            for key, count in value.items()
        )
    )
