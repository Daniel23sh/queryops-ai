from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

from app.db.session import SessionLocal
from app.domains.it_operations.seed import seed_database
from app.domains.it_operations.seed_profiles import SEED_PROFILES
from app.evaluation.environment import (
    EvaluationEnvironmentError,
    build_evaluation_environment_manifest,
    write_evaluation_environment_manifest,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed QueryOps AI development data.")
    parser.add_argument(
        "--profile",
        choices=sorted(SEED_PROFILES),
        default="medium",
        help="Dataset size profile to seed.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete existing seeded rows before inserting the selected profile.",
    )
    parser.add_argument(
        "--reference-time",
        help="Explicit timezone-aware ISO-8601 seed reference time.",
    )
    parser.add_argument(
        "--manifest-out",
        help="Create a new sanitized release-environment manifest at this path.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.manifest_out and (args.profile != "medium" or not args.reset):
        print(
            "Seed failed: evaluation_manifest_requires_medium_reset",
            file=sys.stderr,
        )
        return 2
    if args.manifest_out and not args.reference_time:
        print(
            "Seed failed: evaluation_manifest_reference_time_required",
            file=sys.stderr,
        )
        return 2
    if args.manifest_out and Path(args.manifest_out).exists():
        print("Seed failed: evaluation_manifest_exists", file=sys.stderr)
        return 2
    try:
        reference_time = _parse_reference_time(args.reference_time)
    except ValueError:
        print("Seed failed: seed_reference_time_invalid", file=sys.stderr)
        return 2

    session = SessionLocal()
    manifest = None
    try:
        options = {"reference_now": reference_time} if reference_time else {}
        summary = seed_database(
            session,
            profile_name=args.profile,
            reset=args.reset,
            **options,
        )
        if args.manifest_out:
            manifest = build_evaluation_environment_manifest(session, summary)
        session.commit()
    except EvaluationEnvironmentError as exc:
        session.rollback()
        print(f"Seed failed: {exc.code}", file=sys.stderr)
        return 2
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    if args.manifest_out and manifest is not None:
        try:
            write_evaluation_environment_manifest(args.manifest_out, manifest)
        except EvaluationEnvironmentError as exc:
            print(f"Seed failed: {exc.code}", file=sys.stderr)
            return 2
    print(summary.format())
    return 0


def _parse_reference_time(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.microsecond != 0:
        raise ValueError("Reference time must be timezone-aware and second-aligned.")
    return parsed.astimezone(UTC)


if __name__ == "__main__":
    raise SystemExit(main())
