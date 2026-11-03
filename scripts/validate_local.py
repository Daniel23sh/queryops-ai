#!/usr/bin/env python3
"""Run the existing deterministic CI graph in disposable, offline containers."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import tarfile
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
LABEL = "io.queryops.validation"
GATES = ("backend", "postgres-security", "frontend", "e2e", "m8-primary-e2e")
PROXY_KEYS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
              "http_proxy", "https_proxy", "all_proxy", "no_proxy")


class ValidationError(Exception):
    pass


def clean_environment() -> dict[str, str]:
    # Never forward application settings, credentials, proxy or provider variables.
    return {key: os.environ[key] for key in ("PATH", "HOME", "TMPDIR", "DOCKER_CONFIG")
            if key in os.environ}


def command(*args: str, capture: bool = True) -> str:
    process = subprocess.Popen(args, cwd=ROOT, env=clean_environment(),
                               stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, text=True)
    try:
        output, _ = process.communicate()
    except BaseException:
        process.terminate()
        try:
            process.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
        raise
    if process.returncode:
        raise ValidationError(f"{args[0]} exited {process.returncode}")
    return output.strip() if capture else ""


class Run:
    def __init__(self, evidence: Path):
        self.token = "queryops-validation-" + uuid.uuid4().hex
        self.evidence = evidence
        self.containers: list[str] = []
        self.images: list[str] = []
        self.summary: dict = {"schema": "queryops-local-validation-v1", "run": self.token,
                              "status": "failed", "gates": {gate: {"status": "not_run"} for gate in (*GATES, "v1-deterministic-release-gates")}, "cleanup": "pending",
                              "incomplete_coverage": ["production readiness", "provider quality", "manual V1 QA"]}

    def save(self):
        temporary = self.evidence / "summary.tmp"
        temporary.write_text(json.dumps(self.summary, indent=2) + "\n")
        temporary.replace(self.evidence / "summary.json")

    def create(self, suffix: str, *args: str) -> str:
        name = self.token + "-" + suffix
        # No adoption, even if an existing container has a matching label.
        existing = command("docker", "ps", "-aq", "--filter", "name=^/" + name + "$")
        if existing:
            raise ValidationError("container name conflict")
        self.containers.append(name)
        # Docker also injects proxies from ~/.docker/config.json independently of env.
        proxy_env = [value for key in PROXY_KEYS for value in ("-e", key + "=")]
        identifier = command("docker", "create", "--name", name, "--label",
                             f"{LABEL}={self.token}", *proxy_env, *args)
        if not re.fullmatch(r"[a-f0-9]{64}", identifier):
            raise ValidationError("container identity missing")
        self.containers[self.containers.index(name)] = identifier
        return identifier

    def remove(self, identifier: str):
        if identifier.startswith(self.token):
            if not command("docker", "ps", "-aq", "--filter", "name=^/" + identifier + "$"):
                self.containers.remove(identifier)
                return
        identity = command("docker", "inspect", "--format", '{{.Id}} {{index .Config.Labels "' + LABEL + '"}}', identifier)
        actual_id, _, owner = identity.partition(" ")
        if owner != self.token or not re.fullmatch(r"[a-f0-9]{64}", actual_id):
            raise ValidationError("cleanup ownership mismatch")
        command("docker", "rm", "-f", "-v", actual_id)
        self.containers.remove(identifier)

    def cleanup(self):
        errors = []
        for identifier in list(reversed(self.containers)):
            try:
                self.remove(identifier)
            except ValidationError:
                errors.append({"kind": "container", "identity": identifier, "error": "cleanup failed or ownership mismatch"})
        for identifier in self.images:
            try:
                if not command("docker", "image", "ls", "-q", identifier):
                    continue
                identity = command("docker", "image", "inspect", "--format", '{{.Id}} {{index .Config.Labels "' + LABEL + '"}}', identifier)
                actual_id, _, owner = identity.partition(" ")
                if owner != self.token or not re.fullmatch(r"sha256:[a-f0-9]{64}", actual_id):
                    raise ValidationError("image ownership mismatch")
                command("docker", "image", "rm", actual_id)
            except ValidationError:
                errors.append({"kind": "image", "identity": identifier, "error": "cleanup failed or ownership mismatch"})
        self.summary["cleanup"] = errors or "complete"
        if errors:
            self.summary["status"] = "failed"
        self.save()

    def build(self, source: Path, dockerfile: str, suffix: str) -> str:
        tag = self.token + ":" + suffix
        if command("docker", "image", "ls", "-q", tag):
            raise ValidationError("image name conflict")
        self.images.append(tag)
        command("docker", "build", "--label", f"{LABEL}={self.token}", "-t", tag,
                "-f", str(source / dockerfile), str(source if suffix == "runner" else source / "backend"), capture=False)
        identifier = command("docker", "image", "inspect", "--format", "{{.Id}}", tag)
        self.summary[suffix + "_image"] = identifier
        return identifier

    def gate(self, gate: str, image: str):
        pg = None
        if gate in ("postgres-security", "e2e", "m8-primary-e2e"):
            pg = self.create(gate + "-postgres", "--network", "none", "--tmpfs",
                             "/var/lib/postgresql/data:rw", "-e", "POSTGRES_USER=queryops",
                             "-e", "POSTGRES_PASSWORD=local-validation-only", "-e", "POSTGRES_DB=queryops",
                             "postgres:16-alpine")
            command("docker", "start", pg)
            self.summary[gate + "_postgres_image"] = command("docker", "inspect", "--format", "{{.Image}}", pg)
        container = self.create(gate, "--network", "container:" + pg if pg else "none",
                                "--shm-size", "256m", "-e", "VALIDATION_GATE=" + gate, image)
        try:
            command("docker", "start", container)
            result = command("docker", "wait", container)
            command("docker", "cp", container + ":/evidence/summary.json", str(self.evidence / (gate + ".json")))
            report = json.loads((self.evidence / (gate + ".json")).read_text())
            self.summary["gates"][gate] = {key: report[key] for key in
                ("status", "steps", "suites", "postgresql", "migration", "chromium", "error", "active_step", "incomplete_coverage") if key in report}
            self.summary["gates"][gate]["report"] = gate + ".json"
            if "runtime" not in self.summary:
                self.summary["runtime"] = {key: report[key] for key in ("python", "node", "npm", "platform", "frontend_lock_sha256")}
            self.save()
            if result != "0" or report["status"] != "passed":
                raise ValidationError(gate + " failed; see sanitized gate report")
        finally:
            self.remove(container)
            if pg:
                self.remove(pg)

    def execute(self):
        if command("git", "status", "--porcelain", "--untracked-files=normal"):
            raise ValidationError("a clean committed checkout is required")
        self.summary["source_sha"] = command("git", "rev-parse", "HEAD")
        context = command("docker", "context", "show")
        endpoint = command("docker", "context", "inspect", context, "--format", "{{.Endpoints.docker.Host}}")
        if not endpoint.startswith("unix://"):
            raise ValidationError("local Unix-socket Docker context required")
        self.summary["docker_version"] = command("docker", "version", "--format", "{{.Server.Version}}")
        with tempfile.TemporaryDirectory(prefix=self.token) as directory:
            source = Path(directory)
            archive = source / "source.tar"
            command("git", "archive", "--format=tar", "-o", str(archive), self.summary["source_sha"])
            with tarfile.open(archive) as snapshot:
                # Only a trusted, committed repository tree enters the build context.
                snapshot.extractall(source, filter="data")
            archive.unlink()
            self.summary["stage"] = "build"
            self.save()
            print("Building clean source and dependencies", flush=True)
            image = self.build(source, "scripts/validation/Dockerfile", "runner")
            command("docker", "pull", "postgres:16-alpine", capture=False)
            self.summary["stage"] = "compose-boundary"
            self.save()
            compose = ["docker", "compose", "--project-name", self.token, "--env-file", "/dev/null", "-f", str(source / "docker-compose.yml")]
            for setting in ([], ["AUTH_MODE="]):
                try:
                    command("env", *setting, *compose, "config", "--quiet")
                except ValidationError:
                    continue
                raise ValidationError("Compose accepted missing/empty AUTH_MODE")
            positive_compose = ["docker", "compose", "--project-name", self.token, "--env-file", str(source / ".env.example"), "-f", str(source / "docker-compose.yml")]
            config = json.loads(command(*positive_compose, "config", "--format", "json"))
            if config["services"]["backend"]["environment"]["AUTH_MODE"] != "demo" or any(
                port["host_ip"] != "127.0.0.1" for service in config["services"].values() for port in service.get("ports", [])
            ):
                raise ValidationError("Compose boundary mismatch")
            # Build the supported backend Dockerfile, without Compose networks/binds.
            smoke_image = self.build(source, "backend/Dockerfile", "smoke")
            smoke = self.create("compose-smoke", "--network", "none", "-e", "AUTH_MODE=demo", smoke_image,
                                "python", "-c", 'from app.core.config import get_auth_mode; assert get_auth_mode() == "demo"; import pytest, json; from pathlib import Path; from validation_gate import junit_counts; result = pytest.main(["tests/test_auth_configuration.py", "tests/test_auth_session.py", "tests/test_permissions.py", "-q", "--junitxml=/tmp/smoke.xml"]); Path("/tmp/smoke.json").write_text(json.dumps(junit_counts(Path("/tmp/smoke.xml")))); raise SystemExit(result)')
            # The supported Dockerfile omits tests; copy only the committed tests.
            command("docker", "cp", str(source / "backend/tests"), smoke + ":/app/tests")
            command("docker", "cp", str(source / "scripts/validation/gate.py"), smoke + ":/app/validation_gate.py")
            command("docker", "start", smoke)
            result = command("docker", "wait", smoke)
            command("docker", "cp", smoke + ":/tmp/smoke.json", str(self.evidence / "compose-smoke.json"))
            counts = json.loads((self.evidence / "compose-smoke.json").read_text())
            self.summary["compose_smoke"] = counts
            self.save()
            if result != "0" or not counts["executed"] or counts["failed"] or counts["skipped"]:
                raise ValidationError("supported backend image smoke failed")
            self.remove(smoke)
            self.summary["compose_boundary"] = "passed (supported image, no Compose service startup)"
            for gate in GATES:
                print("Running " + gate, flush=True)
                self.summary["stage"] = gate
                self.save()
                self.gate(gate, image)
            self.summary["gates"]["v1-deterministic-release-gates"] = {"status": "passed"}
            self.summary["status"] = "passed"
            self.summary["stage"] = "complete"


def main() -> int:
    if __import__("sys").version_info < (3, 12):
        raise SystemExit("Host Python 3.12+ is required; container Python matches CI 3.12")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True, help="New directory outside the checkout")
    args = parser.parse_args()
    evidence = args.evidence.resolve()
    if evidence == ROOT or ROOT in evidence.parents:
        parser.error("evidence must be outside the checkout")
    evidence.mkdir(mode=0o700, parents=True, exist_ok=False)
    run = Run(evidence)
    def interrupted(signum, frame):
        raise KeyboardInterrupt
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)
    try:
        run.execute()
    except (ValidationError, KeyboardInterrupt, OSError, ValueError) as exc:
        run.summary["error"] = str(exc) if isinstance(exc, ValidationError) else type(exc).__name__
    finally:
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, signal.SIG_IGN)
        run.cleanup()
    print(json.dumps(run.summary, indent=2))
    return 0 if run.summary["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
