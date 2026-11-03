import pytest


@pytest.fixture(autouse=True)
def explicit_demo_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    """Synthetic tests explicitly opt in; application code has no auth default."""
    monkeypatch.setenv("AUTH_MODE", "demo")
