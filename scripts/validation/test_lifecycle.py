"""Real Docker adversarial lifecycle check; run explicitly on the host, no skips."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("validate_local", Path(__file__).resolve().parents[1] / "validate_local.py")
local = importlib.util.module_from_spec(spec)
spec.loader.exec_module(local)


class Lifecycle(unittest.TestCase):
    def test_sigterm_during_running_client_reaps_owned_resources(self):
        with tempfile.TemporaryDirectory() as folder:
            evidence = Path(folder) / "signal-evidence"
            script = f"""
import importlib.util, sys
spec = importlib.util.spec_from_file_location('local', {str(local.ROOT / 'scripts/validate_local.py')!r})
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
def execute(self):
    identifier = self.create('signal', '--network', 'none', '--tmpfs', '/var/lib/postgresql/data', '-e', 'POSTGRES_PASSWORD=synthetic-only', 'postgres:16-alpine')
    module.command('docker', 'start', identifier)
    self.summary['signal_container'] = identifier
    self.save()
    module.command('docker', 'wait', identifier)
module.Run.execute = execute
sys.argv = ['validate', '--evidence', {str(evidence)!r}]
raise SystemExit(module.main())
"""
            child = subprocess.Popen([__import__("sys").executable, "-c", script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                for _ in range(100):
                    if (evidence / "summary.json").exists():
                        report = json.loads((evidence / "summary.json").read_text())
                        if "signal_container" in report:
                            break
                    self.assertIsNone(child.poll(), "signal test exited before creating owned resource")
                    time.sleep(0.1)
                else:
                    self.fail("signal test setup timed out")
                child.terminate()
                self.assertEqual(child.wait(timeout=45), 1)
                report = json.loads((evidence / "summary.json").read_text())
                self.assertEqual(report["error"], "KeyboardInterrupt")
                self.assertEqual(report["cleanup"], "complete")
                time.sleep(1)
                self.assertEqual(local.command("docker", "ps", "-aq", "--filter", "label=" + local.LABEL + "=" + report["run"]), "")
            finally:
                if child.poll() is None:
                    child.terminate()
                    child.wait(timeout=45)

    def test_protected_resources_survive_rejection_partial_setup_and_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            run = local.Run(Path(folder))
            protected = local.command("docker", "create", "--name", run.token + "-conflict", "--network", "none",
                                      "--label", "protected=true", "--tmpfs", "/var/lib/postgresql/data", "-e",
                                      "POSTGRES_PASSWORD=synthetic-only", "postgres:16-alpine")
            volume = run.token + "-protected-volume"
            local.command("docker", "volume", "create", volume)
            try:
                local.command("docker", "start", protected)
                for _ in range(60):
                    try:
                        local.command("docker", "exec", protected, "pg_isready", "-h", "127.0.0.1", "-U", "postgres")
                        break
                    except local.ValidationError:
                        time.sleep(1)
                local.command("docker", "exec", protected, "psql", "-U", "postgres", "-c",
                              "CREATE DATABASE protected_user_db;")
                local.command("docker", "exec", protected, "psql", "-U", "postgres", "-d", "protected_user_db", "-c",
                              "CREATE TABLE sentinel(value text); INSERT INTO sentinel VALUES ('unchanged'); CREATE ROLE protected_cluster_role;")
                fingerprint_command = ("docker", "exec", protected, "psql", "-U", "postgres", "-d", "protected_user_db", "-Atc",
                                       "SELECT value FROM sentinel; SELECT datname FROM pg_database ORDER BY 1; SELECT rolname FROM pg_roles ORDER BY 1;")
                fingerprint = local.command(*fingerprint_command)
                before = local.command("docker", "inspect", protected)
                volume_before = local.command("docker", "volume", "inspect", volume)
                with self.assertRaises(local.ValidationError):
                    run.create("conflict", "postgres:16-alpine")
                # Simulate client failure after Docker successfully creates an owned container.
                original = local.command
                def partial(*args, **kwargs):
                    result = original(*args, **kwargs)
                    if args[1] == "create":
                        raise local.ValidationError("injected partial create failure")
                    return result
                with patch.object(local, "command", side_effect=partial):
                    with self.assertRaises(local.ValidationError):
                        run.create("partial", "--network", "none", "postgres:16-alpine")
                run.cleanup()
                self.assertEqual(run.summary["cleanup"], "complete")
                # An actual failed process and its owned anonymous volumes are cleaned.
                failed = run.create("failed", "--network", "none", "postgres:16-alpine", "sh", "-c", "exit 7")
                local.command("docker", "start", failed)
                self.assertEqual(local.command("docker", "wait", failed), "7")
                run.cleanup()
                self.assertEqual(run.summary["cleanup"], "complete")
                # Even a supplied foreign container ID must not be removed.
                run.containers.append(protected)
                run.cleanup()
                self.assertNotEqual(run.summary["cleanup"], "complete")
                self.assertEqual(local.command("docker", "inspect", protected), before)
                self.assertEqual(local.command("docker", "volume", "inspect", volume), volume_before)
                self.assertEqual(local.command(*fingerprint_command), fingerprint)
                run.containers.clear()
                # Unknown DB-target flags fail before any Docker operation.
                result = subprocess.run([__import__("sys").executable, str(local.ROOT / "scripts/validate_local.py"),
                                         "--database-url", "postgresql://localhost/protected"],
                                        capture_output=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(local.command("docker", "inspect", protected), before)
                self.assertEqual(json.loads(local.command("docker", "inspect", protected))[0]["HostConfig"]["PortBindings"], {})
            finally:
                local.command("docker", "rm", "-fv", protected)
                local.command("docker", "volume", "rm", volume)


if __name__ == "__main__":
    unittest.main()
