import pytest


@pytest.fixture
def disable_socket(socket_disabled):
    """Backward-compatible alias for the pytest-socket fixture used in this repo."""
    yield
