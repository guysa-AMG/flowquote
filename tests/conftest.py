import pytest

from app.config import settings


@pytest.fixture(autouse=True)
def configure_test_pin(monkeypatch):
    monkeypatch.setattr(settings, "auth_pin", "1234")


@pytest.fixture
def disable_socket(socket_disabled):
    """Backward-compatible alias for the pytest-socket fixture used in this repo."""
    yield
