"""Privileged, standard-library-only launcher for the one-shot planner study."""
from __future__ import annotations

import argparse
from datetime import UTC, datetime
from functools import partial
import hashlib
import json
import os
from pathlib import Path
import re
import select
import signal
import socket
import stat
import struct
import subprocess
import sys

STUDY_ID = "queryops-planner-study-v1"
STATE = Path("/var/lib/queryops") / STUDY_ID
CLAIM = STATE / "claimed"
EVIDENCE = CLAIM / "evidence"
MAX_DOCUMENT = 64_000
ENV = {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "LANG": "C.UTF-8",
       "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_NO_LAZY_FETCH": "1",
       "GIT_OPTIONAL_LOCKS": "0"}


class ActivationError(RuntimeError):
    """Fixed operator diagnostic code."""


def require(ok, code):
    if not ok:
        raise ActivationError(code)


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()


def decode(raw, limit=MAX_DOCUMENT):
    def unique(pairs):
        value = dict(pairs)
        require(len(value) == len(pairs), "duplicate_json_key")
        return value

    require(0 < len(raw) <= limit, "activation_document_invalid")
    value = json.loads(raw, object_pairs_hook=unique)
    require(isinstance(value, dict), "activation_document_invalid")
    return value


def protected(path, *, directory=False, private=False):
    info = path.lstat()
    kind = stat.S_ISDIR if directory else stat.S_ISREG
    forbidden = 0o077 if private else 0o022
    require(kind(info.st_mode) and info.st_uid == 0 and not info.st_mode & forbidden,
            "activation_path_unprotected")
    return info


def protected_directory(path):
    require(path.is_absolute() and path.resolve() == path, "activation_path_invalid")
    for parent in reversed(path.parents):
        protected(parent, directory=True)
    return protected(path, directory=True)


def protected_tree(path):
    def fail(exc):
        raise exc

    protected_directory(path)
    for base, dirs, files in os.walk(path, onerror=fail):
        for name in dirs + files:
            entry = Path(base) / name
            if entry.is_symlink():
                target = entry.resolve(strict=True)
                require(target.is_relative_to(path), "activation_path_unprotected")
                protected(target, directory=target.is_dir())
            else:
                protected(entry, directory=name in dirs)


def git(checkout, *args, user=None, group=None):
    metadata = checkout / ".git"
    git_dir = [f"--git-dir={metadata}"] if metadata.is_dir() else []
    runner = {"env": ENV, "user": user, "group": group, "extra_groups": ()} if user is not None else {}
    return subprocess.run(["git", "--no-replace-objects", f"--work-tree={checkout}",
                           *git_dir,
                           "-c", f"safe.directory={checkout}", "-c", "core.fsmonitor=false", *args],
                          cwd=checkout, capture_output=True, check=True, text=True, timeout=10, **runner).stdout.strip()


def verify_source(checkout, expected, read_git):
    require(isinstance(expected, str) and re.fullmatch(r"[0-9a-f]{40}", expected)
            and expected == read_git("rev-parse", "HEAD") == read_git("rev-parse", "refs/heads/main")
            == read_git("rev-parse", "refs/remotes/origin/main")
            and read_git("symbolic-ref", "--short", "HEAD") == "main"
            and all(line.startswith("H ") for line in read_git("ls-files", "-v").splitlines())
            and not read_git("ls-files", "--others", "-z")
            and not read_git("diff", "--cached", "--name-only", "-z", "--no-ext-diff", "--no-textconv", expected, "--"),
            "live_source_mismatch")
    # Git status may normalize bytes through checkout-local filters.
    for entry in read_git("ls-tree", "-rz", "--full-tree", expected).rstrip("\0").split("\0"):
        metadata, name = entry.split("\t", 1)
        mode, kind, blob = metadata.split()
        path = checkout / name
        require(kind == "blob" and mode in {"100644", "100755"} and path.is_relative_to(checkout) and path.is_file()
                and path.resolve() == path and bool(path.stat().st_mode & 0o100) == (mode == "100755"),
                "live_source_mismatch")
        data = path.read_bytes()
        actual = hashlib.sha1(f"blob {len(data)}\0".encode() + data, usedforsecurity=False).hexdigest()
        require(actual == blob, "live_source_mismatch")


def state_identity():
    require(sys.platform == "linux" and hasattr(socket, "SO_PEERCRED"), "activation_host_unsupported")
    info = protected_directory(STATE)
    machine = Path("/etc/machine-id")
    protected_directory(machine.parent)
    protected(machine)
    identity = machine.read_text().strip()
    require(bool(re.fullmatch(r"[0-9a-f]{32}", identity)) and identity != "0" * 32,
            "activation_host_identity_invalid")
    return {"host_sha256": digest(identity), "state_root": str(STATE),
            "state_device": info.st_dev, "state_inode": info.st_ino}


def read_private(path):
    protected(path, private=True)
    with path.open("rb") as file:
        data = file.read(MAX_DOCUMENT + 1)
    require(0 < len(data) <= MAX_DOCUMENT, "activation_document_invalid")
    return data


def utc(value):
    require(isinstance(value, str) and re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", value),
            "activation_window_invalid")
    return datetime.fromisoformat(value).astimezone(UTC)


def remaining(approval, *, now=None):
    now = datetime.now(UTC) if now is None else now
    start, end = utc(approval["starts_utc"]), utc(approval["expires_utc"])
    require(start <= now < end, "activation_outside_window")
    return (end - now).total_seconds()


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def claim(approval_sha256, uid, gid):
    # An empty directory already consumes the study. Never clean it up.
    CLAIM.mkdir(mode=0o755)
    sync_directory(STATE)
    CLAIM.chmod(0o755)
    with (CLAIM / "approval.sha256").open("x") as receipt:
        os.fchmod(receipt.fileno(), 0o644)
        receipt.write(approval_sha256 + "\n")
        receipt.flush()
        os.fsync(receipt.fileno())
    EVIDENCE.mkdir(mode=0o700)
    os.chown(EVIDENCE, uid, gid)
    sync_directory(EVIDENCE)
    sync_directory(CLAIM)


def send(channel, value):
    raw = encode(value).encode()
    require(len(raw) <= MAX_DOCUMENT and channel.send(raw) == len(raw), "activation_handoff_failed")


def receive(channel):
    return decode(channel.recv(MAX_DOCUMENT + 1))


def operator_channel(fd):
    require(sys.platform == "linux" and os.getuid() != 0 and os.geteuid() == os.getuid(),
            "activation_runner_invalid")
    channel = socket.socket(fileno=fd)
    try:
        require(channel.family == socket.AF_UNIX and channel.type == socket.SOCK_SEQPACKET,
                "activation_channel_invalid")
        peer_credentials = getattr(socket, "SO_PEERCRED")
        pid, uid, _ = struct.unpack("3i", channel.getsockopt(socket.SOL_SOCKET, peer_credentials, 12))
        require(uid == 0 and pid == os.getppid(), "activation_operator_unverified")
        os.set_inheritable(fd, False)
        channel.settimeout(300)
        return channel
    except BaseException:
        channel.close()
        raise


def operator_present(channel):
    require(not select.select([channel], [], [], 0)[0], "activation_operator_stopped")


def launch(python, backend, uid, gid):
    require(os.getuid() == os.geteuid() == 0 and uid > 0 and gid > 0, "activation_operator_required")
    signal.signal(signal.SIGCHLD, signal.SIG_DFL)
    identity = state_identity()
    filesystem = subprocess.run(["/usr/bin/findmnt", "-n", "-o", "FSTYPE", "-T", str(STATE)], env=ENV,
                                capture_output=True, text=True, check=True, timeout=5).stdout.strip()
    require(filesystem in {"ext4", "xfs"}, "activation_filesystem_unsupported")
    require(not os.path.lexists(CLAIM), "activation_already_claimed")
    approval = decode(read_private(STATE / "approval.json"))
    require(all(approval.get(key) == value for key, value in identity.items()), "activation_host_changed")
    require((approval.get("runner_uid"), approval.get("runner_gid")) == (uid, gid),
            "activation_runner_invalid")
    remaining(approval)
    manifest = decode(read_private(STATE / "manifest.json"))
    database_url = read_private(STATE / "database-url").decode().strip()
    owner = read_private(STATE / "database-owner").decode().strip()
    version = approval.get("credential_version")
    require(isinstance(version, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", version),
            "activation_credential_invalid")
    credential = read_private(STATE / ("credential-" + version)).decode().strip()
    require(bool(re.fullmatch(r"[A-Za-z0-9_-]{20,512}", credential))
            and hashlib.sha256(credential.encode()).hexdigest() == approval.get("credential_sha256"),
            "activation_credential_invalid")

    require(backend.name == "backend" and python.name == "python" and python.parent.name == "bin",
            "activation_installation_invalid")
    protected_tree(backend.parent)
    metadata = backend.parent / ".git"
    protected(metadata, directory=True)
    require(not any(os.path.lexists(metadata / name) for name in
                    ("commondir", "objects/info/alternates", "objects/info/http-alternates")),
            "activation_git_metadata_external")
    verify_source(backend.parent, approval["source"], partial(git, backend.parent, user=uid, group=gid))
    venv = python.parent.parent
    protected_tree(venv)
    protected(venv / "pyvenv.cfg")
    protected(python)
    operator, runner = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    with operator, runner:
        operator.settimeout(300)
        entry = (
            "import sys; from pathlib import Path; "
            "site = Path(sys.executable).parents[1] / 'lib' / "
            "f'python{sys.version_info.major}.{sys.version_info.minor}' / 'site-packages'; "
            "sys.path[:0] = [sys.argv.pop(1), str(site)]; "
            "from scripts.planner_study import main; raise SystemExit(main())"
        )
        child = subprocess.Popen(
            [str(python), "-I", "-B", "-S", "-c", entry, str(backend), "live", "--activation-fd", str(runner.fileno())],
            cwd=backend, env=ENV, user=uid, group=gid, extra_groups=(), umask=0o077,
            pass_fds=(runner.fileno(),), stdin=subprocess.DEVNULL,
        )
        runner.close()
        try:
            send(operator, {"approval": approval, "manifest": manifest, "database_url": database_url, "owner": owner})
            approval_sha = digest(approval)
            require(receive(operator) == {"ready": approval_sha}, "activation_preflight_failed")
            remaining(approval)
            claim(approval_sha, uid, gid)
            remaining(approval)
            send(operator, {"credential": credential})
            return child.wait()
        finally:
            # EOF also revokes the dispatch gate if the launcher is killed.
            operator.close()
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--backend", type=Path, required=True)
    parser.add_argument("--runner-uid", type=int, required=True)
    parser.add_argument("--runner-gid", type=int, required=True)
    args = parser.parse_args()
    try:
        return launch(args.python, args.backend, args.runner_uid, args.runner_gid)
    except ActivationError as exc:
        parser.exit(1, f"{exc}\n")
    except Exception:
        parser.exit(1, "activation_launcher_failed\n")


if __name__ == "__main__":
    raise SystemExit(main())
