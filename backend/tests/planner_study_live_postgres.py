"""Explicit integration check against a fresh owned study database, never the CI app DB."""
import json
import os

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from scripts import planner_study as study
from scripts import planner_study_activation as activation
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
        with Session(engine) as db:
            manifest = study.prepare(db, pack, owner)
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
