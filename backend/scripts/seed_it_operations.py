from __future__ import annotations

import argparse

from app.db.session import SessionLocal
from app.domains.it_operations.seed import seed_database
from app.domains.it_operations.seed_profiles import SEED_PROFILES


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
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    session = SessionLocal()
    try:
        summary = seed_database(session, profile_name=args.profile, reset=args.reset)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    print(summary.format())


if __name__ == "__main__":
    main()
