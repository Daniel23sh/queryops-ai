"""Run explicitly as root on disposable Linux, using a fresh ext4/XFS test mount."""
import hashlib
import os
from pathlib import Path
import signal
import site
import socket
import subprocess
import sys
import tempfile

import pytest

from scripts import planner_study as study
from scripts import planner_study_launch as launch
from tests.test_planner_study_activation import KEY, fake_manifest, synthetic_approval


def test_linux_peer_and_claim_permissions(monkeypatch):
    assert sys.platform == "linux" and os.getuid() == 0
    parent = Path(os.environ["PLANNER_STUDY_LINUX_TEST_ROOT"])
    assert subprocess.check_output(["findmnt", "-n", "-o", "FSTYPE", "-T", str(parent)],
                                   text=True).strip() in {"ext4", "xfs"}
    with tempfile.TemporaryDirectory(dir=parent) as temporary:
        state = Path(temporary)
        state.chmod(0o755)
        monkeypatch.setattr(launch, "STATE", state)
        monkeypatch.setattr(launch, "CLAIM", state / "test-claim")
        monkeypatch.setattr(launch, "EVIDENCE", launch.CLAIM / "evidence")
        launch.protected_directory(state)
        uid = gid = 65534
        code = """
import os, sys
from pathlib import Path
from scripts import planner_study_launch as launch
with launch.operator_channel(int(sys.argv[1])) as channel:
    launch.send(channel, {"ready": True})
    assert launch.receive(channel) == {"synthetic": True}
    claim = Path(sys.argv[2])
    for action in (lambda: claim.rename(claim.with_name("replacement")), claim.rmdir,
                   lambda: (claim / "approval.sha256").unlink()):
        try:
            action()
        except PermissionError:
            pass
        else:
            raise AssertionError("runner can replace the claim")
    (claim / "evidence" / "synthetic-receipt").touch()
    assert channel.recv(1) == b""
    try:
        launch.operator_present(channel)
    except launch.ActivationError:
        pass
    else:
        raise AssertionError("lost launcher remained authorized")
"""
        operator, runner = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        with operator, runner:
            operator.settimeout(15)
            child = subprocess.Popen([sys.executable, "-B", "-c", code, str(runner.fileno()), str(launch.CLAIM)],
                                     user=uid, group=gid, extra_groups=(), pass_fds=(runner.fileno(),))
            runner.close()
            try:
                assert launch.receive(operator) == {"ready": True}
                launch.claim("a" * 64, uid, gid)
                launch.send(operator, {"synthetic": True})
                operator.shutdown(socket.SHUT_WR)
                assert child.wait(timeout=15) == 0
                assert (launch.EVIDENCE / "synthetic-receipt").exists()
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait()


@pytest.mark.parametrize("scenario", ["grant", "sync_failure", "expiry"])
def test_actual_launcher_and_worker_handoff(monkeypatch, scenario):
    assert sys.platform == "linux" and os.getuid() == 0
    parent = Path(os.environ["PLANNER_STUDY_LINUX_TEST_ROOT"])
    with tempfile.TemporaryDirectory(dir=parent) as temporary:
        root = Path(temporary)
        root.chmod(0o755)
        state = root / "state"
        state.mkdir(mode=0o755)
        identity = {"host_sha256": "b" * 64, "state_root": str(state),
                    "state_device": state.stat().st_dev, "state_inode": state.stat().st_ino}
        monkeypatch.setattr(launch, "STATE", state)
        monkeypatch.setattr(launch, "CLAIM", state / "test-claim")
        monkeypatch.setattr(launch, "EVIDENCE", launch.CLAIM / "evidence")
        monkeypatch.setattr(launch, "state_identity", lambda: identity)
        uid = gid = 65534
        manifest, _ = fake_manifest(study.load_it_operations_domain_pack())
        approval = synthetic_approval(manifest, identity, uid, gid)
        documents = {"approval.json": launch.encode(approval), "manifest.json": launch.encode(manifest),
                     "database-url": "synthetic-not-a-url", "database-owner": "b" * 32,
                     "credential-synthetic": KEY}
        monkeypatch.setattr(launch, "read_private", lambda path: documents[path.name].encode())

        venv = root / "venv"
        subprocess.run([sys.executable, "-m", "venv", "--copies", "--without-pip", str(venv)], check=True)
        backend = root / "checkout" / "backend"
        scripts = backend / "scripts"
        scripts.mkdir(parents=True)
        (backend.parent / ".git").mkdir()
        worker = scripts / "planner_study.py"
        worker.write_text(f"""
import sys
from pathlib import Path
sys.path.extend({[str(study.ROOT / "backend"), *site.getsitepackages()]!r})
__file__ = {study.__file__!r}
exec(compile(Path(__file__).read_bytes(), __file__, "exec"))
from contextlib import nullcontext
launch.STATE = Path({str(state)!r})
launch.CLAIM = launch.STATE / "test-claim"
launch.EVIDENCE = launch.CLAIM / "evidence"
launch.state_identity = lambda: {identity!r}
class SyntheticEngine:
    def dispose(self):
        pass
owned_engine = lambda *args, **kwargs: SyntheticEngine()
checked_snapshot = lambda *args: None
Session = lambda *args: nullcontext()
offline_controls = lambda *args: None
def never_network(**kwargs):
    raise AssertionError("real transport constructed")
httpx.HTTPTransport = never_network
if {scenario!r} == "expiry":
    arm_timer = signal.setitimer
    signal.setitimer = lambda timer, seconds: arm_timer(timer, 0.25 if seconds else 0)
def run_live(engine, owner, manifest, approval, credential, ledger, gate, make_transport):
    assert gate() > 0
    assert hashlib.sha256(credential.encode()).hexdigest() == approval["credential_sha256"]
    (launch.EVIDENCE / "synthetic-grant-received").touch()
    if {scenario!r} == "expiry":
        time.sleep(5)
    return {{"synthetic": True}}
""")
        contents = worker.read_bytes()
        blob = hashlib.sha1(f"blob {len(contents)}\0".encode() + contents, usedforsecurity=False).hexdigest()
        worker_path = "backend/scripts/planner_study.py"

        def synthetic_git(checkout, command, *args, user, group):
            assert checkout == backend.parent and (user, group) == (uid, gid)
            if command == "ls-files":
                return "H " + worker_path if args == ("-v",) else ""
            return {"rev-parse": approval["source"], "symbolic-ref": "main", "diff": "",
                    "ls-tree": f"100644 blob {blob}\t{worker_path}\0"}[command]

        monkeypatch.setattr(launch, "git", synthetic_git)

        def execute():
            return launch.launch(venv / "bin" / "python", backend, uid, gid)

        receipt = launch.EVIDENCE / "synthetic-grant-received"
        git_metadata = backend.parent / ".git"
        git_metadata.rmdir()
        git_metadata.write_text("gitdir: /untrusted-metadata\n")
        with pytest.raises(launch.ActivationError, match="activation_path_unprotected"):
            execute()
        assert not launch.CLAIM.exists()
        git_metadata.unlink()
        git_metadata.mkdir()
        (git_metadata / "commondir").write_text("/untrusted-metadata\n")
        with pytest.raises(launch.ActivationError, match="activation_git_metadata_external"):
            execute()
        assert not launch.CLAIM.exists()
        (git_metadata / "commondir").unlink()
        worker.write_bytes(contents + b"\nraise RuntimeError('wrong checkout reached')\n")
        with pytest.raises(launch.ActivationError, match="live_source_mismatch"):
            execute()
        assert not launch.CLAIM.exists()
        worker.write_bytes(contents)
        if scenario == "sync_failure":
            def fail(_):
                raise OSError("synthetic sync failure")

            monkeypatch.setattr(launch, "sync_directory", fail)
            with pytest.raises(OSError, match="synthetic sync failure"):
                execute()
            assert not receipt.exists()
        elif scenario == "expiry":
            previous = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGALRM})
            previous_child = signal.signal(signal.SIGCHLD, signal.SIG_IGN)
            try:
                assert execute() == -signal.SIGALRM
            finally:
                signal.signal(signal.SIGCHLD, previous_child)
                signal.pthread_sigmask(signal.SIG_SETMASK, previous)
            assert receipt.exists()
        else:
            assert execute() == 0
            assert receipt.exists()
        assert launch.CLAIM.is_dir()
        with pytest.raises(launch.ActivationError, match="activation_already_claimed"):
            execute()
