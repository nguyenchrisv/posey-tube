"""Tests for per-pin enable/disable (arm/disarm), persistence, and authorizeControl hook."""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from posey_tube.gpio import GPIOController
from posey_tube.pins import PinConfig


def _make_configs():
    return [
        PinConfig(
            name="led",
            bcm=17,
            direction="out",
            active_high=False,
            max_on_s=2,
            label="LED",
            enabled=True,
        ),
        PinConfig(
            name="btn",
            bcm=27,
            direction="in",
            pull="up",
            label="Button",
            enabled=True,
        ),
        PinConfig(
            name="relay",
            bcm=22,
            direction="out",
            active_high=True,
            max_on_s=3,
            label="Relay",
            enabled=False,  # starts disabled in config
        ),
    ]


def _make_configs_enabled():
    """Configs where all pins start enabled."""
    return [
        PinConfig(
            name="led",
            bcm=17,
            direction="out",
            active_high=False,
            max_on_s=2,
            label="LED",
            enabled=True,
        ),
        PinConfig(
            name="btn",
            bcm=27,
            direction="in",
            pull="up",
            label="Button",
            enabled=True,
        ),
        PinConfig(
            name="relay",
            bcm=22,
            direction="out",
            active_high=True,
            max_on_s=3,
            label="Relay",
            enabled=True,
        ),
    ]


def _make_fresh_controller(configs, state_path):
    """Create a fresh controller with the given configs and state path."""
    try:
        from gpiozero.pins.mock import MockFactory
    except ImportError:
        from gpiozero import MockFactory
    factory = MockFactory()
    ctrl = GPIOController(configs, pin_factory=factory, state_path=state_path)
    # Don't create locks here - let the caller do it
    return ctrl, factory


def _mock_pin_state(factory, bcm: int) -> bool:
    """Return the physical pin state (True=high, False=low) for a BCM number."""
    for pin_info, mock_pin in factory.pins.items():
        if bcm in pin_info.names:
            return mock_pin.state
    raise KeyError(bcm)


class TestEnableDisable:
    """Tests for per-pin enable/disable (arm/disarm)."""

    def test_disable_output_turns_off_first(self, controller, tmp_path):
        """Disabling an output that is on turns it off first, then locks it."""
        async def _run():
            # Start with led on
            await controller.set_output("led", True)
            state = await controller.get_state("led")
            assert state["on"] is True

            # Disable it
            state = await controller.set_enabled("led", False)
            assert state["enabled"] is False
            assert state["on"] is False

            # Re-enable
            state = await controller.set_enabled("led", True)
            assert state["enabled"] is True
            assert state["on"] is False  # stays off until explicitly turned on

        asyncio.run(_run())

    def test_disable_input(self, controller, tmp_path):
        """Inputs can be disabled too: they keep reporting state, flagged enabled: false."""
        async def _run():
            state = await controller.get_state("btn")
            assert state["enabled"] is True

            # Disable
            state = await controller.set_enabled("btn", False)
            assert state["enabled"] is False
            assert state["direction"] == "in"

            # Re-enable
            state = await controller.set_enabled("btn", True)
            assert state["enabled"] is True

        asyncio.run(_run())

    def test_disable_idempotent(self, controller, tmp_path):
        """Setting the same enabled state twice is a no-op."""
        async def _run():
            state = await controller.set_enabled("led", False)
            s1 = await controller.get_state("led")
            state = await controller.set_enabled("led", False)
            s2 = await controller.get_state("led")
            assert s1["since"] == s2["since"]

        asyncio.run(_run())

    def test_re_enable_allows_writes(self, controller, tmp_path):
        """Re-enabling a disabled pin allows writes again."""
        async def _run():
            # Disable
            await controller.set_enabled("led", False)
            state = await controller.get_state("led")
            assert state["enabled"] is False

            # Re-enable
            state = await controller.set_enabled("led", True)
            assert state["enabled"] is True

            # Now writes work
            state = await controller.set_output("led", True)
            assert state["on"] is True

        asyncio.run(_run())


class TestEnableDisablePersistence:
    """Tests for persisted disabled set across restarts."""

    def _make_fresh_controller(self, configs, state_path):
        """Create a fresh controller with the given configs and state path."""
        try:
            from gpiozero.pins.mock import MockFactory
        except ImportError:
            from gpiozero import MockFactory
        factory = MockFactory()
        ctrl = GPIOController(configs, pin_factory=factory, state_path=state_path)
        return ctrl, factory

    def test_disabled_set_persists(self, controller, tmp_path, configs):
        """Disabled set survives a simulated restart."""
        state_path = tmp_path / "state.json"

        # Disable a pin
        async def _run():
            ctrl, factory = self._make_fresh_controller(configs, state_path)
            await ctrl._ensure_locks()
            await ctrl.set_enabled("led", False)
            await ctrl.shutdown()
            factory.close()

        asyncio.run(_run())

        # New controller with same state file
        async def _run2():
            ctrl2, factory2 = self._make_fresh_controller(configs, state_path)
            await ctrl2._ensure_locks()
            state = await ctrl2.get_state("led")
            assert state["enabled"] is False
            await ctrl2.shutdown()
            factory2.close()

        asyncio.run(_run2())

    def test_config_enabled_false_persists(self, controller, tmp_path, configs):
        """Config enabled=false is persisted on first boot."""
        state_path = tmp_path / "state.json"

        async def _run():
            # relay starts disabled in config
            state = await controller.get_state("relay")
            assert state["enabled"] is False

            # Enable it
            await controller.set_enabled("relay", True)
            state = await controller.get_state("relay")
            assert state["enabled"] is True
            await controller.shutdown()

        asyncio.run(_run())

        # New controller: should see relay as enabled (state file overrides config)
        async def _run2():
            ctrl2, factory2 = self._make_fresh_controller(configs, state_path)
            await ctrl2._ensure_locks()
            state = await ctrl2.get_state("relay")
            assert state["enabled"] is True
            await ctrl2.shutdown()
            factory2.close()

        asyncio.run(_run2())

    def test_corrupt_state_file_falls_back(self, controller, tmp_path, configs):
        """Corrupt or missing state file falls back to config defaults with warning."""
        state_path = tmp_path / "corrupt_state.json"
        state_path.write_text("not json")

        async def _run():
            ctrl, factory = self._make_fresh_controller(configs, state_path)
            await ctrl._ensure_locks()
            # led is enabled in config, so should be enabled
            state = await ctrl.get_state("led")
            assert state["enabled"] is True
            # relay is disabled in config
            state = await ctrl.get_state("relay")
            assert state["enabled"] is False
            await ctrl.shutdown()
            factory.close()

        asyncio.run(_run())


class TestAllOff:
    """Tests for /all-off endpoint."""

    def test_all_off_unaffected_by_disabled(self, controller, tmp_path):
        """/all-off turns off all outputs regardless of enabled state."""
        async def _run():
            # Enable relay first (it starts disabled in config)
            await controller.set_enabled("relay", True)
            await controller.set_output("led", True)
            await controller.set_output("relay", True)
            await controller.set_enabled("led", False)  # disable while on

            await controller.all_off()

            state = await controller.get_state("led")
            assert state["on"] is False
            state = await controller.get_state("relay")
            assert state["on"] is False

        asyncio.run(_run())


class TestAuthorizeControlHook:
    """Tests for the authorize_control hook."""

    def test_hook_allows_by_default(self, controller, tmp_path):
        """Default authorize_control allows everything."""
        async def _run():
            # Should not raise
            await controller.authorize_control("led", "on")
            await controller.authorize_control("led", "pulse")
            await controller.authorize_control("led", "enabled")

        asyncio.run(_run())

    def test_hook_can_block(self, controller, tmp_path):
        """Subclass can override authorize_control to block."""
        async def _run():
            class BlockingController(GPIOController):
                async def authorize_control(self, name, action):
                    raise PermissionError("blocked by hook")

            # Create a fresh factory for the blocking controller to avoid pin conflicts
            try:
                from gpiozero.pins.mock import MockFactory
            except ImportError:
                from gpiozero import MockFactory
            factory = MockFactory()
            blocking_ctrl = BlockingController(
                _make_configs(), pin_factory=factory, state_path=tmp_path / "state.json"
            )
            await blocking_ctrl._ensure_locks()

            with pytest.raises(PermissionError, match="blocked by hook"):
                await blocking_ctrl.set_output("led", True)

            await blocking_ctrl.shutdown()
            factory.close()

        asyncio.run(_run())


class TestDisabledWriteReturns423:
    """API-level: writes to disabled pins return 423 Locked."""

    async def test_write_on_disabled_returns_423(self, client, token):
        # Disable the led
        await client.post(
            "/pins/led",
            headers={"Authorization": f"Bearer {token}"},
            json={"enabled": False},
        )
        # Try to turn on
        resp = await client.post(
            "/pins/led",
            headers={"Authorization": f"Bearer {token}"},
            json={"on": True},
        )
        assert resp.status == 423
        data = await resp.json()
        assert "disabled" in data["error"].lower()

    async def test_write_pulse_disabled_returns_423(self, client, token):
        # Disable the relay
        await client.post(
            "/pins/relay",
            headers={"Authorization": f"Bearer {token}"},
            json={"enabled": False},
        )
        # Try to pulse
        resp = await client.post(
            "/pins/relay",
            headers={"Authorization": f"Bearer {token}"},
            json={"pulse_ms": 500},
        )
        assert resp.status == 423

    async def test_re_enable_allows_write(self, client, token):
        # Disable then re-enable
        await client.post(
            "/pins/led",
            headers={"Authorization": f"Bearer {token}"},
            json={"enabled": False},
        )
        await client.post(
            "/pins/led",
            headers={"Authorization": f"Bearer {token}"},
            json={"enabled": True},
        )
        # Write should work now
        resp = await client.post(
            "/pins/led",
            headers={"Authorization": f"Bearer {token}"},
            json={"on": True},
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["on"] is True

    async def test_all_off_works_on_disabled(self, client, token):
        """all-off still turns off disabled outputs."""
        await client.post(
            "/pins/led",
            headers={"Authorization": f"Bearer {token}"},
            json={"on": True},
        )
        await client.post(
            "/pins/led",
            headers={"Authorization": f"Bearer {token}"},
            json={"enabled": False},
        )
        resp = await client.post(
            "/all-off", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status == 200

        # Verify off
        import hmac
        resp = await client.get("/pins/led", headers={"Authorization": f"Bearer {token}"})
        data = await resp.json()
        assert data["on"] is False


class TestConfigEnabledDefaults:
    """Tests for config enabled=false start-up state."""

    def test_config_enabled_false_at_start(self, controller, tmp_path):
        """Pin with enabled=false in config starts disabled."""
        async def _run():
            state = await controller.get_state("relay")
            assert state["enabled"] is False
            assert state["on"] is False

        asyncio.run(_run())

    def test_config_enabled_true_at_start(self, controller, tmp_path):
        """Pin with no enabled (default true) starts enabled."""
        async def _run():
            state = await controller.get_state("led")
            assert state["enabled"] is True

        asyncio.run(_run())