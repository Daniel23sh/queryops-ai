"""Synthetic stored measurements for the guarded scoped Evaluation browser lane."""
from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.domains.it_operations.seed import seed_database
from app.evaluation.loader import load_it_operations_evaluation_v2_set
from app.evaluation.scoring import score_evaluation_case
from app.evaluation.selection import evaluation_dataset_digest
from app.models.product import EvaluationResult, EvaluationRun
from scripts.prepare_m8_e2e import UnsafeE2EDatabaseError, validated_e2e_database_url


def prepare_state(db: Session, state: str) -> dict[str, str]:
    seed_database(db, profile_name="small", reset=True)
    evaluation_set = load_it_operations_evaluation_v2_set()
    ids = {}
    now = datetime.now(UTC)
    groups = []
    if state == "visible":
        groups.append(("visible", ("itops-security-002", "itops-security-003")))
    if state in {"hidden", "visible"}:
        groups.append(("hidden", ("itops-security-001",)))
    for index, (label, case_ids) in enumerate(groups):
        run = EvaluationRun(
            name=f"Synthetic scoped browser {label}", run_type="manual_evaluation",
            status="succeeded", started_at=now - timedelta(seconds=1),
            completed_at=now + timedelta(seconds=index),
            summary={
                "provider": "mock", "model_label": "mock-queryops-v1",
                "dataset_id": evaluation_set.dataset_id,
                "dataset_version": evaluation_set.version,
                "dataset_digest": evaluation_dataset_digest(evaluation_set),
                # Deliberately unrelated totals must never enter scoped metrics.
                "selected_count": 9001, "completed_count": 9001,
            },
        )
        db.add(run)
        db.flush()
        ids[label] = str(run.id)
        for case_id in case_ids:
            case = evaluation_set.cases_by_id[case_id]
            score = score_evaluation_case(
                case, actual_outcome=case.expected_outcome,
                execution_succeeded=False, actual_referenced_tables=case.expected_tables,
            )
            assert score.passed
            db.add(EvaluationResult(
                evaluation_run_id=run.id, case_name=case.id, status="succeeded",
                score=score.score, expected_output={"outcome": case.expected_outcome.value},
                actual_output={
                    "outcome": case.expected_outcome.value, "execution_succeeded": False,
                    "referenced_tables": list(case.expected_tables), "error_code": None,
                },
                metrics={
                    **score.as_safe_metrics(), "difficulty": case.difficulty.value,
                    "category": case.category, "case_type": case.case_type.value,
                    "security_sensitive": case.security_sensitive, "duration_ms": 0.0,
                    "missing_row_count": 0, "extra_row_count": 0,
                    "query_execution_attempted": False,
                },
            ))
    db.commit()
    return ids


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("state", choices=("empty", "hidden", "visible"))
    args = parser.parse_args()
    try:
        target = validated_e2e_database_url(
            os.environ.get("M8_E2E_DATABASE_URL", ""),
            disposable_opt_in=os.environ.get("M8_E2E_DATABASE_DISPOSABLE"),
            application_url=os.environ.get("DATABASE_URL"),
            application_database_name=os.environ.get("POSTGRES_DB", "queryops"),
        )
        engine = create_engine(target)
        try:
            with Session(engine) as db:
                print(json.dumps(prepare_state(db, args.state)))
        finally:
            engine.dispose()
    except (UnsafeE2EDatabaseError, SQLAlchemyError):
        print("Scoped evaluation fixture failed safely.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
