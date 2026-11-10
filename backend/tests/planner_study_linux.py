"""Run explicitly as root on disposable Linux, using a fresh ext4/XFS test mount."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile

from scripts import planner_study_launch as launch


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
