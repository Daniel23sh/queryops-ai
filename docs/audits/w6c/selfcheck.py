"""Test audit guards without opening a database or making a provider request."""
import sys
from pathlib import Path
from unittest.mock import patch

import probe


def main():
    original = Path.read_bytes
    for name in ("heldout-v1.json", "witnesses.py", "fixture.py"):
        def altered(path, name=name):
            raw = original(path)
            return raw + b"\n" if path == probe.HERE / name else raw

        with patch.object(Path, "read_bytes", altered), patch(
            "builtins.__import__", wraps=__import__
        ) as imports, patch.object(
            probe, "create_engine", side_effect=AssertionError("DB reached")
        ) as engine, patch.object(sys, "argv", ["probe", "--initialize", "--out", "/tmp/w6c-guard.json"]):
            try:
                probe.main()
            except AssertionError as exc:
                assert str(exc) == name
            else:
                raise AssertionError("Changed frozen input was accepted")
            engine.assert_not_called()
            assert not any(call.args[0] in {"fixture", "witnesses"} for call in imports.call_args_list)
    print("3 frozen-input guards rejected changes before artifact imports or DB construction")


if __name__ == "__main__":
    main()
