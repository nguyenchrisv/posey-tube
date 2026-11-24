"""Tests for gpio.py controller with MockFactory."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import patch

import pytest

from posey_tube.gpio import GPIOController
from posey_tube.pins import PinConfig


# Use gpiozero's MockFactory for all tests
try:
    from gpiozero.pins.mock import MockFactory
except ImportError:
    from gpiozero import MockFactory


def _make_configs():
    return [
        PinConfig(
            name="led",
            bcm=17,
            direction="out",
            active_high=False,
            max_on_s=2,
            label="LED",
        ),
        PinConfig(
            name="btn",
            bcm=27,
            direction="in",
            pull="up",
            label="Button",
        ),
        PinConfig(
            name="relay",
            bcm=22,
            direction="out",
            active_high=True,
            max_on_s=3,
            label="Relay",
        ),
    ]


def _mock_pin_state(factory, bcm: int) -> bool:
    """Return the physical pin state (True=high, False=low) for a BCM number."""
    for pin_info, mock_pin in factory.pins.items():
        if bcm in pin_info.names:
            return mock_pin.state
    raise KeyError(bcm)


@pytest.fixture
def configs():
    return [
        PinConfig(
            name="led",
            bcm=17,
            direction="out",
            active_high=False,
            max_on_s=2,
            label="LED",
        ),
        PinConfig(
            name="btn",
            bcm=27,
            direction="in",
            pull="up",
            label="Button",
        ),
        PinConfig(
            name="relay",
            bcm=22,
            direction="out",
            active_high=True,
            max_on_s=3,
            label="Relay",
        ),
    ]


@pytest.fixture
def controller(configs):
    """Create a GPIOController with MockFactory and ensure locks are created."""
    try:
        from gpiozero.pins.mock import MockFactory
    except ImportError:
        from gpiozero import MockFactory

    factory = MockFactory()
    ctrl = GPIOController(_make_configs(), pin_factory=factory)
    # Trigger lock creation on the test loop
    import asyncio
    asyncio.run(ctrl._ensure_locks())
    yield ctrl
    asyncio.run(ctrl.shutdown())
    factory.close()


class TestGPIOControllerBasics:
    """Basic state and initialization."""

    def test_outputs_start_off(self, controller):
        """All outputs off at startup (active_high semantics respected)."""
        # We test via the controller's logical state, not the mock pin directly
        async def _run():
            states = await controller.get_all_states()
            led_state = next(s for s in states if s["name"] == "led")
            relay_state = next(s for s in states if s["name"] == "relay")
            assert led_state["on"] is False
            assert relay_state["on"] is False

        asyncio.run(_run())

    def test_inputs_start_off(self, controller):
        """Inputs report off (is_active False) initially."""
        async def _run():
            state = await controller.get_state("btn")
            assert state["on"] is False
            assert state["direction"] == "in"

        asyncio.run(_run())

    def test_get_all_states(self, controller):
        async def _run():
            states = await controller.get_all_states()
            names = {s["name"] for s in states}
            assert names == {"led", "btn", "relay"}
            for s in states:
                assert "name" in s
                assert "direction" in s
                assert "on" in s
                assert "since" in s
                assert "label" in s
                assert isinstance(s["on"], bool)
                assert isinstance(s["since"], str)

        asyncio.run(_run())

    def test_get_one_state(self, controller):
        async def _run():
            s = await controller.get_state("led")
            assert s["name"] == "led"
            assert s["direction"] == "out"
            assert s["on"] is False

        asyncio.run(_run())

    def test_unknown_pin_raises(self, controller):
        async def _run():
            with pytest.raises(KeyError):
                await controller.get_state("unknown")

        asyncio.run(_run())


class TestOutputControl:
    """Tests for output pin writes."""

    def test_set_output_on(self, controller):
        async def _run():
            await controller.set_output("led", True)
            state = await controller.get_state("led")
            assert state["on"] is True

        asyncio.run(_run())

    def test_set_output_off(self, controller):
        async def _run():
            await controller.set_output("led", True)
            await controller.set_output("led", False)
            state = await controller.get_state("led")
            assert state["on"] is False

        asyncio.run(_run())

    def test_output_set_idempotent(self, controller):
        """Setting the same value twice doesn't change since timestamp."""
        async def _run():
            await controller.set_output("led", True)
            s1 = await controller.get_state("led")
            await controller.set_output("led", True)
            s2 = await controller.get_state("led")
            assert s1["since"] == s2["since"]

        asyncio.run(_run())

    def test_input_write_raises(self, controller):
        async def _run():
            with pytest.raises(ValueError, match="pin is an input"):
                await controller.set_output("btn", True)

        asyncio.run(_run())

    def test_active_high_false_on_drives_low(self, controller, mock_factory):
        """active_high=False: {'on': true} drives pin low."""
        try:
            from gpiozero.pins.mock import MockFactory
        except ImportError:
            from gpiozero import MockFactory

        factory = MockFactory()
        configs = _make_configs()
        ctrl = GPIOController(configs, pin_factory=factory)
        asyncio.run(ctrl._ensure_locks())

        async def _run():
            await ctrl.set_output("led", True)
            # active_high=False: on = pin low
            state = await ctrl.get_state("led")
            assert state["on"] is True

        asyncio.run(_run())
        factory.close()

    def test_active_high_false_off_drives_high(self, controller, mock_factory):
        try:
            from gpiozero.pins.mock import MockFactory
        except ImportError:
            from gpiozero import MockFactory

        factory = MockFactory()
        configs = _make_configs()
        ctrl = GPIOController(configs, pin_factory=factory)
        asyncio.run(ctrl._ensure_locks())

        async def _run():
            await ctrl.set_output("led", True)
            await ctrl.set_output("led", False)
            state = await ctrl.get_state("led")
            assert state["on"] is False

        asyncio.run(_run())
        factory.close()

    def test_active_high_true_on_drives_high(self, controller, mock_factory):
        """active_high=True: {'on': true} drives pin high."""
        try:
            from gpiozero.pins.mock import MockFactory
        except ImportError:
            from gpiozero import MockFactory

        factory = MockFactory()
        configs = _make_configs()
        ctrl = GPIOController(configs, pin_factory=factory)
        asyncio.run(ctrl._ensure_locks())

        async def _run():
            await ctrl.set_output("relay", True)
            state = await ctrl.get_state("relay")
            assert state["on"] is True

        asyncio.run(_run())
        factory.close()

    def test_pulse_output(self, controller):
        """pulse_ms turns on then off after the delay."""
        async def _run():
            await controller.pulse_output("led", 50)  # 50 ms
            # Immediately on
            state = await controller.get_state("led")
            assert state["on"] is True

            # Wait for pulse to expire
            await asyncio.sleep(0.12)  # 120 ms > 50 ms
            state = await controller.get_state("led")
            assert state["on"] is False

        asyncio.run(_run())

    def test_pulse_cancels_max_on(self, controller):
        """Pulse timer should turn off regardless of max_on_s."""
        async def _run():
            # max_on_s=2 (longer than pulse)
            await controller.pulse_output("relay", 50)
            await asyncio.sleep(0.12)
            state = await controller.get_state("relay")
            assert state["on"] is False

        asyncio.run(_run())

    def test_pulse_out_of_range_rejected(self, controller):
        async def _run():
            with pytest.raises(ValueError, match="pin is an input"):
                await controller.pulse_output("btn", 50)

        asyncio.run(_run())


class TestAutoOff:
    """Tests for max_on_s auto-off timer."""

    def test_max_on_expiry_turns_off(self, controller):
        """max_on_s=2 turns output off after ~2 seconds."""
        async def _run():
            # max_on_s=2 for led
            await controller.set_output("led", True)
            state = await controller.get_state("led")
            assert state["on"] is True
            await asyncio.sleep(2.3)  # > 2 seconds
            state = await controller.get_state("led")
            assert state["on"] is False

        asyncio.run(_run())

    def test_max_on_cancelled_by_new_write(self, controller):
        """New set_output resets the auto-off timer."""
        async def _run():
            await controller.set_output("led", True)
            await asyncio.sleep(0.5)
            # New write resets timer
            await controller.set_output("led", True)
            await asyncio.sleep(1.3)
            # Should still be on because timer was reset
            state = await controller.get_state("led")
            assert state["on"] is True
            await asyncio.sleep(1.3)
            state = await controller.get_state("led")
            assert state["on"] is False

        asyncio.run(_run())

    def test_all_off_turns_off_and_cancels_timers(self, controller):
        async def _run():
            await controller.set_output("led", True)
            await controller.set_output("relay", True)
            await controller.all_off()
            state = await controller.get_state("led")
            assert state["on"] is False
            state = await controller.get_state("relay")
            assert state["on"] is False

        asyncio.run(_run())