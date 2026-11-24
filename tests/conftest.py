"""Shared test fixtures for posey-tube tests."""

from __future__ import annotations

import pytest

try:
    from gpiozero.pins.mock import MockFactory
except ImportError:
    from gpiozero import MockFactory

from posey_tube.gpio import GPIOController
from posey_tube.pins import PinConfig


def _make_configs():
    return [
        PinConfig(name="led", bcm=17, direction="out", active_high=False, max_on_s=2, label="LED"),
        PinConfig(name="btn", bcm=27, direction="in", pull="up", label="Button"),
        PinConfig(name="relay", bcm=22, direction="out", active_high=True, max_on_s=3, label="Relay"),
    ]


@pytest.fixture(scope="function")
def mock_factory():
    """Provide a MockFactory for each test."""
    factory = MockFactory()
    yield factory
    factory.close()


@pytest.fixture
def configs():
    return [
        PinConfig(name="led", bcm=17, direction="out", active_high=False, max_on_s=2, label="LED"),
        PinConfig(name="btn", bcm=27, direction="in", pull="up", label="Button"),
        PinConfig(name="relay", bcm=22, direction="out", active_high=True, max_on_s=3, label="Relay"),
    ]


@pytest.fixture
def controller(mock_factory, configs):
    """Create a GPIOController with MockFactory and ensure locks are created."""
    ctrl = GPIOController(configs, pin_factory=mock_factory)
    # Trigger lock creation on the test loop
    import asyncio
    asyncio.run(ctrl._ensure_locks())
    yield ctrl
    asyncio.run(ctrl.shutdown())


@pytest.fixture
def token() -> str:
    return "test-secret-token-123"


@pytest.fixture
def app(controller, token):
    from posey_tube.api import create_app

    return create_app(controller, token)


@pytest.fixture
async def client(app):
    from aiohttp.test_utils import TestServer, TestClient

    server = TestServer(app)
    await server.start_server()
    async with TestClient(server) as client:
        yield client
    await server.close()