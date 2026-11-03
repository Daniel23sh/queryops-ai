"""Container-only adapter: execute authoritative CI run steps with safe reports."""
from __future__ import annotations

import importlib.metadata
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.request import urlopen
import xml.etree.ElementTree as ET

ROOT = Path("/src")
EVIDENCE = Path("/evidence")
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
GATES = ("backend", "postgres-security", "frontend", "e2e", "m8-primary-e2e")
URL = "postgresql+psycopg://queryops:local-validation-only@127.0.0.1:5432/"


def junit_counts(path: Path) -> dict[str, int]:
    root = ET.parse(path).getroot()
    cases = list(root.iter("testcase"))
    return {"executed": len(cases) - sum(case.find("skipped") is not None for case in cases),
            "passed": sum(not any(case.find(tag) is not None for tag in ("failure", "error", "skipped")) for case in cases),
            "failed": sum(any(case.find(tag) is not None for tag in ("failure", "error")) for case in cases),
            "skipped": sum(case.find("skipped") is not None for case in cases)}


def workflow_jobs() -> dict:
    # js-yaml is already installed by the locked ESLint dependency tree.
    script = "const fs=require('fs'); const yaml=require('js-yaml'); console.log(JSON.stringify(yaml.load(fs.readFileSync('../.github/workflows/ci.yml','utf8')).jobs))"
    return json.loads(subprocess.check_output(["node", "-e", script], cwd=FRONTEND, text=True))


class Gate:
    def __init__(self, name: str):
        if name not in GATES:
            raise ValueError("unknown gate")
        self.name = name
        self.jobs = workflow_jobs()
        if set(self.jobs) != set(GATES) | {"v1-deterministic-release-gates"}:
            raise ValueError("CI graph changed; update adapter")
        if set(self.jobs["v1-deterministic-release-gates"]["needs"]) != set(GATES):
            raise ValueError("CI aggregate dependencies changed")
        self.env = {**os.environ, "AUTH_MODE": "demo", "LLM_PROVIDER": "mock", "DATABASE_URL": URL + "queryops",
                    "SESSION_SECRET_KEY": "validation-synthetic-session-only", "SESSION_COOKIE_SECURE": "false",
                    "VITE_API_BASE_URL": "http://127.0.0.1:8000", "PLAYWRIGHT_BASE_URL": "http://127.0.0.1:5173",
                    "PLAYWRIGHT_SKIP_WEBSERVER": "1", "M8_E2E_PYTHON": "python", "POSTGRES_DB": "queryops",
                    "PLAYWRIGHT_JUNIT_OUTPUT_FILE": "/evidence/playwright.xml", "PYTHONPATH": str(BACKEND)}
        self.report: dict = {"status": "failed", "steps": [], "suites": {}, "incomplete_coverage": [],
                             "python": subprocess.check_output(["python", "--version"], text=True).strip(),
                             "node": subprocess.check_output(["node", "--version"], text=True).strip(),
                             "dependencies": dict(sorted((item.metadata["Name"], item.version) for item in importlib.metadata.distributions())),
                             "frontend_lock_sha256": hashlib.sha256((FRONTEND / "package-lock.json").read_bytes()).hexdigest(),
                             "frontend_dependencies": json.loads(subprocess.check_output(["npm", "ls", "--depth=0", "--json"], cwd=FRONTEND, text=True))["dependencies"],
                             "npm": subprocess.check_output(["npm", "--version"], text=True).strip()}
        self.processes: list[subprocess.Popen] = []
        EVIDENCE.mkdir(exist_ok=True)
        self.save()

    def save(self):
        (EVIDENCE / "summary.json").write_text(json.dumps(self.report, indent=2) + "\n")

    def shell(self, text: str, cwd: Path):
        subprocess.run(["bash", "-e", "-o", "pipefail", "-c", text], cwd=cwd, env=self.env, check=True)

    def step(self, step: dict):
        self.report["active_step"] = step["name"]
        self.save()
        text = step["run"]
        cwd = ROOT / step.get("working-directory", ".")
        if step["name"] == "Run backend tests":
            text += " --junitxml=/evidence/backend.xml"
        elif step["name"] == "Run frontend tests":
            text += " -- --reporter=junit --outputFile=/evidence/frontend.xml"
        elif self.name in ("e2e", "m8-primary-e2e"):
            text = text.replace("npx playwright test", "npx playwright test --reporter=line,junit")
        self.shell(text, cwd)
        self.report["steps"].append(step["name"])
        self.save()

    def postgres(self, database: str):
        import psycopg
        from psycopg import sql
        for _ in range(60):
            try:
                with psycopg.connect(URL.replace("+psycopg", "") + "queryops", autocommit=True) as db:
                    self.report["postgresql"] = db.execute("SHOW server_version").fetchone()[0]
                    # CREATE DATABASE fails if present; never DROP or adopt an existing DB.
                    db.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
                return
            except psycopg.OperationalError:
                time.sleep(1)
        raise RuntimeError("PostgreSQL did not become ready")

    def migrations(self, database: str):
        application_url = self.env["DATABASE_URL"]
        self.env["DATABASE_URL"] = URL + database
        try:
            self.shell("alembic upgrade head\nalembic current\nalembic check", BACKEND)
            from sqlalchemy import create_engine, text
            engine = create_engine(self.env["DATABASE_URL"])
            with engine.connect() as db:
                self.report["migration"] = db.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
            engine.dispose()
        finally:
            self.env["DATABASE_URL"] = application_url

    def start_application(self, database: str):
        runtime = {**self.env, "DATABASE_URL": URL + database}
        for args, cwd in ((["python", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"], BACKEND),
                          (["npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", "5173", "--strictPort"], FRONTEND)):
            self.processes.append(subprocess.Popen(args, cwd=cwd, env=runtime, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        # /health proves liveness only. Authenticated API + seeded templates prove readiness.
        probe = """
import httpx
with httpx.Client(base_url='http://127.0.0.1:8000') as client:
    assert client.get('/health').json()['status'] == 'ok'
    response = client.post('/api/v1/demo/login', json={'email': 'demo.admin@queryops.local'})
    assert response.status_code == 200
    assert client.get('/api/v1/auth/me').status_code == 200
    response = client.get('/api/v1/query-templates')
    assert response.status_code == 200
"""
        for _ in range(60):
            if any(process.poll() is not None for process in self.processes):
                raise RuntimeError("application process exited")
            try:
                with urlopen("http://127.0.0.1:5173", timeout=1) as response:
                    assert response.status == 200
                subprocess.run(["python", "-c", probe], cwd=BACKEND, env=runtime, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                self.report["readiness"] = "frontend HTTP + authenticated persisted demo API"
                return
            except (OSError, subprocess.CalledProcessError):
                time.sleep(1)
        raise RuntimeError("application readiness timeout")

    def collect(self, name: str, path: Path, *, zero_skips: bool):
        counts = junit_counts(path)
        self.report["suites"][name] = counts
        self.save()
        if counts["executed"] == 0 or counts["failed"] or (zero_skips and counts["skipped"]):
            raise RuntimeError("required suite empty, failed or skipped")

    def execute(self):
        steps = self.jobs[self.name]["steps"]
        if self.name == "backend":
            names = {"Run Ruff", "Run Pyright readiness boundary", "Verify Python compilation", "Run backend tests"}
        elif self.name == "frontend":
            names = {"Run ESLint", "Type-check application", "Type-check Node and Vite configuration", "Run frontend tests", "Build frontend"}
        elif self.name == "postgres-security":
            database = "queryops_security_test"
            self.postgres(database)
            self.env.update(POSTGRES_TEST_DATABASE_URL=URL + database, POSTGRES_TEST_DATABASE_DISPOSABLE="1")
            self.migrations(database)
            names = {"Run exact 20-case M8 release-blocking suite", "Run complete PostgreSQL backend suite"}
        else:
            database = "queryops_e2e_test" if self.name == "m8-primary-e2e" else "queryops_general_e2e_test"
            self.postgres(database)
            self.migrations(database)
            if self.name == "m8-primary-e2e":
                self.env.update(M8_E2E_DATABASE_URL=URL + database, M8_E2E_DATABASE_DISPOSABLE="1")
                preparation = next(step for step in steps if step.get("name") == "Apply migrations, seed, and prepare exact-scope workflow")
                self.step(preparation)
            else:
                self.env["DATABASE_URL"] = URL + database
                preparation = next(step for step in steps if step.get("name") == "Apply database migrations and seed deterministic data")
                self.step(preparation)
            self.start_application(database)
            names = {"Run governed action and access-workflow integrity flows"} if self.name == "m8-primary-e2e" else {"Run focused Playwright flows"}
        selected = [step for step in steps if step.get("name") in names]
        if {step["name"] for step in selected} != names:
            raise ValueError("CI steps changed; update adapter")
        for step in selected:
            if self.name == "m8-primary-e2e":
                # Separate reports for each sequential fixture/reset boundary.
                for index, line in enumerate(step["run"].strip().splitlines()):
                    self.env["PLAYWRIGHT_JUNIT_OUTPUT_FILE"] = f"/evidence/browser-{index}.xml"
                    self.step({**step, "run": line})
                    self.collect(line.split()[3], EVIDENCE / f"browser-{index}.xml", zero_skips=True)
            else:
                self.step(step)
        if self.name in ("backend", "frontend"):
            self.collect(self.name, EVIDENCE / (self.name + ".xml"), zero_skips=self.name == "frontend")
            if self.name == "backend":
                self.report["incomplete_coverage"] = ["default backend PostgreSQL skips; executed separately in postgres-security"]
        elif self.name == "postgres-security":
            self.collect("m8-action-release", Path("/tmp/m8-action-release.xml"), zero_skips=True)
            if self.report["suites"]["m8-action-release"]["executed"] != 20:
                raise RuntimeError("exact action release suite changed")
            self.collect("postgres-backend", Path("/tmp/postgres-backend.xml"), zero_skips=True)
            cases = list(ET.parse("/tmp/postgres-backend.xml").getroot().iter("testcase"))
            evaluation = [case for case in cases if case.get("classname") == "tests.test_evaluation_reads_postgres"]
            if not evaluation:
                raise RuntimeError("persisted Evaluation suite not executed")
        elif self.name == "e2e":
            self.collect("general-playwright", EVIDENCE / "playwright.xml", zero_skips=True)
        self.report["status"] = "passed"
        self.save()


def main():
    gate = Gate(os.environ["VALIDATION_GATE"])
    try:
        gate.execute()
    except Exception as exc:
        # Only types, counts and fixed stage names cross the container boundary.
        gate.report["error"] = type(exc).__name__
        for path in [*EVIDENCE.glob("*.xml"), Path("/tmp/m8-action-release.xml"), Path("/tmp/postgres-backend.xml")]:
            try:
                gate.report["suites"][path.stem] = junit_counts(path)
            except (ET.ParseError, OSError):
                pass
    finally:
        for process in reversed(gate.processes):
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        gate.save()
    return 0 if gate.report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
