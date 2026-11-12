"""Explicit integration check against a fresh owned study database, never the CI app DB."""
import json
import os

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.domains.it_operations.models import DirectoryUser, Group, UserGroupMembership
from scripts import planner_study as study
from scripts import planner_study_activation as activation
from scripts.planner_study_fixtures import key
from scripts.semantic_ownership_fixtures import count, field
from tests.test_planner_study_activation import KEY, fake_response


def test_full_guarded_study_and_post_dispatch_database_drift(tmp_path, monkeypatch):
    # Run explicitly with a newly migrated, commented database and synthetic owner receipt.
    owner = os.environ["PLANNER_STUDY_TEST_OWNER"]
    assert len(owner) == 32
    engine = study.owned_engine(os.environ["PLANNER_STUDY_TEST_DATABASE_URL"], live=True)
    monkeypatch.setattr(study, "source", lambda: "a" * 40)
    monkeypatch.setattr(study, "check_source", lambda _: None)
    monkeypatch.setattr(httpx, "HTTPTransport", lambda **_: pytest.fail("external network transport reached"))
    pack = study.load_it_operations_domain_pack()
    study.initialize(engine, owner)
    try:
        # A qualifying group in an unassigned scope must not enter the scalar count.
        with Session(engine) as db, db.begin():
            db.add(DirectoryUser(id=key("control-hidden-member"), employee_number="control-hidden-member",
                                 email="control-hidden-member@queryops.invalid", full_name="Hidden control",
                                 department_id=key("Sales")))
            db.add(Group(id=key("control-hidden-group"), name="Hidden control", group_type="distribution",
                         department_id=key("Sales")))
            db.flush()
            db.add(UserGroupMembership(user_id=key("control-hidden-member"), group_id=key("control-hidden-group"),
                                       department_id=key("Sales"), added_at=study.REFERENCE))
        with Session(engine) as db:
            manifest = study.prepare(db, pack, owner)
            posture, status, _, membership, *_ = study.CASES
            controls = (
                (posture, posture.plans[0], "pass", "strict_match", True),
                (posture, posture.plans[0].model_copy(update={"literal_filters": (
                    posture.plans[0].literal_filters[0].model_copy(update={"operator": "in", "value": ("laptop",)}),)}),
                 "interpretation", "equivalent", True),
                (posture, status.plans[0], "interpretation", "unestablished", False),
                (posture, posture.plans[0].model_copy(update={"concept_ids": ("non_compliant_device",)}),
                 "interpretation", "unestablished", False),
                (status, status.plans[0], "pass", "strict_match", True),
                (status, status.plans[0].model_copy(update={"literal_filters": status.plans[1].literal_filters}),
                 "interpretation", "equivalent", True),
                (status, posture.plans[0], "interpretation", "unestablished", False),
                (membership, membership.plans[0], "pass", "strict_match", True),
                (membership, membership.plans[0].model_copy(update={"aggregations": (
                    count(field("user_group_memberships", "group_id"), distinct=True),)}),
                 "interpretation", "equivalent", True),
                (membership, membership.plans[0].model_copy(update={"aggregations": (count(),)}),
                 "interpretation", "unestablished", "not_evaluated"),
            )
            controls_ledger = study.Ledger(tmp_path / "controls", manifest["fingerprint"])
            try:
                for ordinal, (case, plan, stage, comparison, rows_match) in enumerate(controls):
                    observation = study.offline_observe(engine, db, pack, case, "low", study.supplied(plan),
                                                        manifest, lambda: None,
                                                        before_dispatch=lambda: controls_ledger.reserve(ordinal))
                    assert observation.stage == stage
                    assert observation.diagnostics["plan_comparison"] == comparison
                    assert observation.diagnostics["result_multiset_match"] == rows_match
                    controls_ledger.complete(ordinal, observation)
                stored = controls_ledger.db.execute("SELECT result FROM slots ORDER BY ordinal").fetchall()
                assert len(stored) == 10
                assert all(json.loads(row[0])["diagnostics"]["version"] == 1 for row in stored)
            finally:
                controls_ledger.close()
        assert study.dry_run(engine, owner, manifest, tmp_path / "dry")["provider_dispatches"] == 0
        with monkeypatch.context() as patch:
            patch.setattr(study, "installed_runtime_versions", lambda: {"synthetic": "changed"})
            with pytest.raises(study.StudyStop, match="study_identity_changed"):
                study.checked_snapshot(engine, pack, owner, manifest)

        state = tmp_path.resolve() / "local-state"
        monkeypatch.setattr(activation, "STATE", state)
        monkeypatch.setattr(activation, "CLAIM", state / "test-claim")
        monkeypatch.setattr(activation, "EVIDENCE", activation.CLAIM / "evidence")
        monkeypatch.setenv("OPENAI_API_KEY", KEY)
        monkeypatch.setenv("OPENAI_PROJECT_ID", "proj_must_not_be_inherited")
        requests = []

        def reply(request):
            assert "openai-project" not in request.headers
            _, index, _ = study.slots()[len(requests)]
            requests.append(request)
            return httpx.Response(200, json=fake_response(study.supplied(next(iter(study.CASES[index].plans), None))))

        with monkeypatch.context() as patch:
            patch.setattr(httpx, "HTTPTransport", lambda **kwargs: httpx.MockTransport(reply))
            assert study.live(engine, owner, manifest)["passes"] == {"low": 16, "medium": 16}
            assert len(requests) == 32
            with pytest.raises(study.StudyStop, match="activation_already_claimed"):
                study.live(engine, owner, manifest)
        ledger = study.Ledger(tmp_path / "drift", manifest["fingerprint"])
        drift_requests = []

        def drift(request):
            drift_requests.append(request)
            with engine.begin() as db:
                db.execute(text("UPDATE devices SET hostname = 'changed' WHERE hostname = 'study-antivirus'"))
            return httpx.Response(200, json=fake_response(study.supplied(study.CASES[0].plans[0])))

        try:
            with pytest.raises(study.StudyStop, match="study_identity_changed"):
                study.run_live(engine, owner, manifest, KEY, ledger,
                               lambda: 45, lambda: httpx.MockTransport(drift))
            assert len(drift_requests) == 1
            assert ledger.db.execute("SELECT ordinal, result FROM slots").fetchall() == [(0, None)]
            assert json.loads(ledger.db.execute("SELECT seal FROM study").fetchone()[0]) == {
                "state": "stopped", "reason": "study_identity_changed"}
        finally:
            ledger.close()
    finally:
        engine.dispose()
