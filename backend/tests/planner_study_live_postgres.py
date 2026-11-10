"""Explicit integration check against a fresh owned study database, never the CI app DB."""
import json
import os

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from scripts import planner_study as study
from tests.test_planner_study_activation import KEY, PROJECT, fake_response


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

        def run(label, *, drift=False):
            requests = []
            ledger = study.Ledger(tmp_path / label, manifest["fingerprint"])

            def reply(req):
                _, index, _ = study.slots()[len(requests)]
                requests.append(json.loads(req.content))
                case = study.CASES[index]
                if drift:
                    with engine.begin() as db:
                        db.execute(text("UPDATE devices SET hostname = 'changed' WHERE hostname = 'study-antivirus'"))
                return httpx.Response(200, json=fake_response(study.supplied(next(iter(case.plans), None))))

            def execute():
                return study.run_live(engine, owner, manifest, {"project": PROJECT}, KEY, ledger,
                                      lambda: 45, lambda: httpx.MockTransport(reply))

            try:
                if drift:
                    with pytest.raises(study.StudyStop, match="study_identity_changed"):
                        execute()
                    assert len(requests) == 1
                    assert ledger.db.execute("SELECT ordinal, result FROM slots").fetchall() == [(0, None)]
                    assert json.loads(ledger.db.execute("SELECT seal FROM study").fetchone()[0]) == {
                        "state": "stopped", "reason": "study_identity_changed"}
                else:
                    assert execute()["passes"] == {"low": 16, "medium": 16}
                    assert len(requests) == 32
            finally:
                ledger.close()

        run("complete")
        run("drift", drift=True)
    finally:
        engine.dispose()
