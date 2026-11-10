from dataclasses import replace
import json
import sqlite3

import httpx
import pytest

from app.evaluation.loader import load_it_operations_evaluation_v2_set
from app.query_engine.domain_pack_loader import load_it_operations_domain_pack
from app.query_engine.llm_provider import PlanGenerationOutcome
from app.query_engine.plan_generator import PlanGeneratorResult
from app.query_engine.semantic_catalog import build_semantic_catalog_projection
from scripts import planner_study as study
from scripts.semantic_ownership_fixtures import count, offline_schema


def test_schedule_and_non_v2_fixtures():
    assert len(study.slots()) == len(set(study.slots())) == 32
    cases = study.CASES
    assert len({case.id for case in cases}) == 8
    assert sorted(sum(c.family == family for c in cases) for family in {c.family for c in cases}) == [2] * 4
    for i in range(8):
        assert [arm for b, j, arm in study.slots() if b == 1 and i == j] == [
            arm for b, j, arm in reversed(study.slots()) if b == 2 and i == j]
    def normalize(text):
        return " ".join(text.casefold().split())

    frozen = {normalize(c.question) for c in load_it_operations_evaluation_v2_set().cases}
    assert frozen.isdisjoint(normalize(c.question) for c in cases)
    assert [c.id for c in cases if c.hint_sensitive] == ["grain-memberships"]


def test_profile_compatibility_and_actual_request_shape(monkeypatch):
    monkeypatch.setattr(httpx, "HTTPTransport", lambda **_: pytest.fail("real transport constructed"))
    pack = load_it_operations_domain_pack()
    schema = offline_schema(pack)
    user = {"scope_type": "department", "scope_reference_resolved": True, "has_global_scope": False}
    case = study.CASES[0]
    projection = build_semantic_catalog_projection(pack.semantic_catalog, case.question, schema, user)
    prompt = study.build_safe_prompt_projection(case.question, schema, user, projection)
    context = None, schema, user, projection, prompt
    bodies = {arm: study.body(prompt, arm) for arm in study.ARMS}
    assert {key for key in bodies["low"] if bodies["low"][key] != bodies["medium"][key]} == {"reasoning"}
    observed = []
    for arm in study.ARMS:
        result = study.offline_generate(case, context, arm, study.supplied(case.plans[0]),
                                        study.digest(bodies[arm]), lambda: observed.append(arm))
        assert result.semantic_plan == case.plans[0]
        assert study.measurement(result)["attempt_count"] is None
    malformed = study.offline_generate(case, context, "low", "{bad", study.digest(bodies["low"]),
                                       lambda: observed.append("malformed"))
    assert study.score(None, pack, case, context, malformed) == "provider_invalid"
    assert observed == ["low", "medium", "malformed"]


def test_clarification_outcome_and_count_shape():
    ambiguous, resolved = [case for case in study.CASES if case.family == "clarification"]
    result = PlanGeneratorResult("openai", study.MODEL, PlanGenerationOutcome.CLARIFICATION,
                                 unsupported_reason="ambiguous_question")
    assert study.score(None, None, ambiguous, None, result) == "pass"
    assert study.score(None, None, resolved, None, result) == "interpretation"
    assert study.score(None, None, ambiguous, None,
                       replace(result, unsupported_reason="unresolved_scope")) == "interpretation"
    membership = next(case.plans[0] for case in study.CASES if case.hint_sensitive)
    joined_rows = membership.model_copy(update={"aggregations": (count(),)})
    assert study.plan_shape(membership) != study.plan_shape(joined_rows)


def test_one_shot_ledger_retains_pending_and_blocks_duplicates(tmp_path):
    path = tmp_path.resolve() / "ledger"
    ledger = study.Ledger(path, "a" * 64)
    try:
        with pytest.raises(study.StudyStop, match="slot_replay"):
            ledger.reserve(1)
        ledger.reserve(0)
        with pytest.raises(study.StudyStop, match="slot_replay"):
            ledger.reserve(0)
        with pytest.raises(study.StudyStop, match="slot_replay"):
            ledger.reserve(1)
        ledger.complete(0, study.Observation("pass", {"attempt_count": None}))
        with pytest.raises(study.StudyStop, match="slot_not_reserved"):
            ledger.complete(0, study.Observation("pass", {}))
        ledger.reserve(1)
    finally:
        ledger.close()
    with pytest.raises(FileExistsError):
        study.Ledger(path, "a" * 64)
    with sqlite3.connect(path / "slots.sqlite3") as db:
        rows = db.execute("SELECT ordinal, result FROM slots ORDER BY ordinal").fetchall()
    assert json.loads(rows[0][1]) == {"stage": "pass", "usage": {"attempt_count": None}}
    assert rows[1] == (1, None)


def test_persistence_error_blocks_next_reservation(tmp_path):
    ledger = study.Ledger(tmp_path.resolve() / "ledger", "b" * 64)
    try:
        ledger.reserve(0)
        ledger.db.execute("CREATE TRIGGER fail_result BEFORE UPDATE ON slots BEGIN SELECT RAISE(ABORT, 'test'); END")
        with pytest.raises(sqlite3.IntegrityError):
            ledger.complete(0, study.Observation("pass", {}))
        with pytest.raises(study.StudyStop, match="slot_replay"):
            ledger.reserve(1)
    finally:
        ledger.close()


def test_assessment_requires_two_unflagged_families_and_complete_usage():
    usage = {"input_tokens": 400, "output_tokens": 100, "duration_ms": 150,
             "attempt_count": 1, "usage_complete": True}
    observations = [study.Observation("interpretation" if arm == "low" and i in {0, 6} else "pass", usage)
                    for _, i, arm in study.slots()]
    verdict = study.assess(observations)
    assert verdict["advancement"] == "consider_medium"
    assert verdict["net_paired_gains"] == 4
    assert verdict["hint_sensitive"] == {"low": 2, "medium": 2}
    incomplete = observations.copy()
    incomplete[0] = replace(incomplete[0], usage={**usage, "usage_complete": False})
    assert study.assess(incomplete)["advancement"] == "inconclusive"
    failed = observations.copy()
    failed[0] = replace(failed[0], stage="conformance")
    with pytest.raises(study.StudyStop, match="study_invalid"):
        study.assess(failed)
    confounded = [study.Observation("interpretation" if arm == "low" and i in {0, 3} else "pass", usage)
                  for _, i, arm in study.slots()]
    assert study.assess(confounded)["advancement"] == "retain_low"


@pytest.mark.parametrize("url", [
    "postgresql+psycopg://test@localhost:5432/planner_study_test_0123456789abcdef",
    "postgresql+psycopg://test@127.0.0.1:5432/queryops",
    "postgresql+psycopg://test@127.0.0.1:5432/planner_study_test_0123456789abcdef?host=other",
])
def test_study_rejects_unowned_endpoint_shape(url):
    with pytest.raises(study.StudyStop, match="disposable_database_required"):
        study.owned_engine(url)
