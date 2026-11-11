"""Local operator state and one-shot claim for the planner study."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import stat
import pwd
import subprocess

STUDY_ID = "queryops-planner-study-v1"
STATE = Path(pwd.getpwuid(os.getuid()).pw_dir).resolve() / "Library/Application Support/QueryOps" / STUDY_ID
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


def private(path, *, directory=False):
    info = path.lstat()
    kind = stat.S_ISDIR if directory else stat.S_ISREG
    require(path.is_absolute() and path.resolve() == path and kind(info.st_mode)
            and info.st_uid == os.getuid() and not info.st_mode & 0o077,
            "activation_path_unprotected")
    return info


def git(checkout, *args):
    return subprocess.run(["git", "--no-replace-objects", "-C", str(checkout),
                           "-c", "core.fsmonitor=false", *args], env=ENV,
                          capture_output=True, check=True, text=True, timeout=10).stdout.strip()


def verify_source(checkout, expected, read_git):
    require(isinstance(expected, str) and re.fullmatch(r"[0-9a-f]{40}", expected)
            and expected == read_git("rev-parse", "HEAD")
            and all(line.startswith("H ") for line in read_git("ls-files", "-v").splitlines())
            and not read_git("ls-files", "--others", "--exclude-standard", "-z")
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


def read_private(path):
    private(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as file:
        info = os.fstat(file.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and not info.st_mode & 0o077,
                "activation_path_unprotected")
        data = file.read(MAX_DOCUMENT + 1)
    require(0 < len(data) <= MAX_DOCUMENT, "activation_document_invalid")
    return data


def local_api_key(env_file):
    key = os.environ.get("OPENAI_API_KEY")
    if key is None:
        fd = os.open(env_file, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "r") as file:
            info = os.fstat(file.fileno())
            require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and not info.st_mode & 0o022,
                    "activation_config_unprotected")
            content = file.read(MAX_DOCUMENT + 1)
        require(len(content) <= MAX_DOCUMENT, "activation_config_too_large")
        matches = [re.fullmatch(r"(?:export\s+)?OPENAI_API_KEY\s*=\s*(.*)", line.strip())
                   for line in content.splitlines()]
        values = [shlex.split(match[1], comments=True) for match in matches if match]
        require(len(values) == 1 and len(values[0]) == 1, "activation_credential_invalid")
        key = values[0][0]
    require(bool(re.fullmatch(r"[A-Za-z0-9_-]{20,512}", key.strip())), "activation_credential_invalid")
    return key.strip()


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def claim(manifest_sha256):
    # An empty directory already consumes the study. Never clean it up.
    CLAIM.mkdir(mode=0o700)
    sync_directory(STATE)
    with (CLAIM / "manifest.sha256").open("x") as receipt:
        os.fchmod(receipt.fileno(), 0o600)
        receipt.write(manifest_sha256 + "\n")
        receipt.flush()
        os.fsync(receipt.fileno())
    EVIDENCE.mkdir(mode=0o700)
    sync_directory(EVIDENCE)
    sync_directory(CLAIM)
