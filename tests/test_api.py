"""Continuation of API tests: pin write, pulse, all-off, validation."""

from __future__ import annotations

import pytest


class TestPinWrite:
    """POST /pins/{name}."""

    async def test_write_output_on(self, client, token):
        resp = await client.post(
            "/pins/led", headers={"Authorization": f"Bearer {token}"}, json={"on": True}
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["on"] is True
        assert data["name"] == "led"

    async def test_write_output_off(self, client, token):
        await client.post(
            "/pins/led", headers={"Authorization": f"Bearer {token}"}, json={"on": True}
        )
        resp = await client.post(
            "/pins/led", headers={"Authorization": f"Bearer {token}"}, json={"on": False}
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["on"] is False

    async def test_write_input_rejected_409(self, client, token):
        resp = await client.post(
            "/pins/btn", headers={"Authorization": f"Bearer {token}"}, json={"on": True}
        )
        assert resp.status == 409
        data = await resp.json()
        assert data["error"] == "pin is an input"

    async def test_write_unknown_pin_404(self, client, token):
        resp = await client.post(
            "/pins/unknown", headers={"Authorization": f"Bearer {token}"}, json={"on": True}
        )
        assert resp.status == 404

    async def test_write_both_on_and_pulse_422(self, client, token):
        resp = await client.post(
            "/pins/led",
            headers={"Authorization": f"Bearer {token}"},
            json={"on": True, "pulse_ms": 500},
        )
        assert resp.status == 422
        data = await resp.json()
        assert "both" in data["error"].lower()

    async def test_write_missing_fields_422(self, client, token):
        resp = await client.post(
            "/pins/led", headers={"Authorization": f"Bearer {token}"}, json={}
        )
        assert resp.status == 422
        data = await resp.json()
        assert "must contain" in data["error"]

    async def test_write_on_not_bool_422(self, client, token):
        resp = await client.post(
            "/pins/led",
            headers={"Authorization": f"Bearer {token}"},
            json={"on": "true"},
        )
        assert resp.status == 422

    async def test_write_pulse_ms_zero_422(self, client, token):
        resp = await client.post(
            "/pins/led",
            headers={"Authorization": f"Bearer {token}"},
            json={"pulse_ms": 0},
        )
        assert resp.status == 422

    async def test_write_pulse_ms_too_large_422(self, client, token):
        resp = await client.post(
            "/pins/led",
            headers={"Authorization": f"Bearer {token}"},
            json={"pulse_ms": 10001},
        )
        assert resp.status == 422
        data = await resp.json()
        assert "1..10000" in data["error"]

    async def test_write_pulse_not_int_422(self, client, token):
        resp = await client.post(
            "/pins/led",
            headers={"Authorization": f"Bearer {token}"},
            json={"pulse_ms": "500"},
        )
        assert resp.status == 422

    async def test_write_invalid_json_422(self, client, token):
        resp = await client.post(
            "/pins/led",
            headers={"Authorization": f"Bearer {token}"},
            data="not json",
        )
        assert resp.status == 422


class TestPulse:
    """POST /pins/{name} with pulse_ms."""

    async def test_pulse_turns_on_then_off(self, client, token):
        # Pulse 50 ms
        resp = await client.post(
            "/pins/led",
            headers={"Authorization": f"Bearer {token}"},
            json={"pulse_ms": 50},
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["on"] is True

        # Wait for pulse to expire
        import asyncio
        await asyncio.sleep(0.12)

        # Verify off
        import hmac
        resp = await client.get("/pins/led", headers={"Authorization": f"Bearer {token}"})
        data = await resp.json()
        assert data["on"] is False

    async def test_pulse_cancels_max_on(self, client, token):
        """Pulse should turn off regardless of max_on_s safety timer."""
        # relay has max_on_s=3, pulse 50 ms
        import asyncio
        await client.post(
            "/pins/relay",
            headers={"Authorization": f"Bearer {token}"},
            json={"pulse_ms": 50},
        )
        await asyncio.sleep(0.12)
        import hmac
        resp = await client.get("/pins/relay", headers={"Authorization": f"Bearer {token}"})
        data = await resp.json()
        assert data["on"] is False


class TestAllOff:
    """POST /all-off."""

    async def test_all_off_turns_everything_off(self, client, token):
        # Turn both outputs on
        await client.post(
            "/pins/led", headers={"Authorization": f"Bearer {token}"}, json={"on": True}
        )
        await client.post(
            "/pins/relay", headers={"Authorization": f"Bearer {token}"}, json={"on": True}
        )
        # All off
        resp = await client.post("/all-off", headers={"Authorization": f"Bearer {token}"})
        assert resp.status == 200
        data = await resp.json()
        assert data["ok"] is True

        # Verify both off
        import hmac
        for name in ("led", "relay"):
            resp = await client.get(f"/pins/{name}", headers={"Authorization": f"Bearer {token}"})
            data = await resp.json()
            assert data["on"] is False


class TestShutdown:
    """Shutdown turns outputs off (tested via controller.shutdown)."""

    def test_shutdown_turns_outputs_off(self, tmp_path):
        from posey_tube.gpio import GPIOController
        from posey_tube.pins import PinConfig

        try:
            from gpiozero.pins.mock import MockFactory
        except ImportError:
            from gpiozero import MockFactory

        factory = MockFactory()
        configs = [
            PinConfig(name="led", bcm=17, direction="out", active_high=False, max_on_s=2),
            PinConfig(name="relay", bcm=22, direction="out", active_high=True, max_on_s=3),
        ]
        ctrl = GPIOController(configs, pin_factory=factory, state_path=tmp_path / "state.json")
        # Manually turn on
        import asyncio

        def _get_pin_state(factory, bcm):
            for pin_info, mock_pin in factory.pins.items():
                if bcm in pin_info.names:
                    return mock_pin.state
            raise KeyError(bcm)

        async def _run():
            await ctrl.set_output("led", True)
            await ctrl.set_output("relay", True)
            await ctrl.shutdown()
            # Check pins
            # led active_low: off = high (True)
            assert _get_pin_state(factory, 17) is True
            # relay active_high: off = low (False)
            assert _get_pin_state(factory, 22) is False

        asyncio.run(_run())
        factory.close()