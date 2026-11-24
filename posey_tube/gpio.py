"""GPIO backend over gpiozero; tests use gpiozero's MockFactory."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from gpiozero import DigitalInputDevice, DigitalOutputDevice

if TYPE_CHECKING:
    from .pins import PinConfig

_LOG = logging.getLogger(__name__)


@dataclass(slots=True)
class _PinState:
    """Runtime state for one pin."""

    config: PinConfig
    device: DigitalOutputDevice | DigitalInputDevice
    since: float
    on: bool
    # Timers for outputs
    max_on_timer: asyncio.TimerHandle | None = None
    pulse_timer: asyncio.TimerHandle | None = None
    # Per-pin lock for serialising writes
    lock: asyncio.Lock | None = None


class GPIOController:
    """Manages all configured pins, enforcing safety invariants.

    - Outputs start off (active_high semantics respected)
    - Per-pin asyncio lock serialises writes
    - Auto-off timer per output (max_on_s)
    - pulse_ms turns on then off (capped at 10 000 ms)
    - All outputs off on shutdown
    """

    def __init__(
        self,
        configs: list[PinConfig],
        pin_factory=None,
    ) -> None:
        self._configs = {c.name: c for c in configs}
        self._states: dict[str, _PinState] = {}
        self._factory = pin_factory
        self._loop: asyncio.AbstractEventLoop | None = None
        self._start_time = time.monotonic()

        # Create devices
        for cfg in configs:
            if cfg.direction == "out":
                dev = DigitalOutputDevice(
                    cfg.bcm,
                    active_high=cfg.active_high,
                    initial_value=False,  # off at start
                    pin_factory=pin_factory,
                )
                on = False
            else:
                pull_up: bool | None
                if cfg.pull == "up":
                    pull_up = True
                elif cfg.pull == "down":
                    pull_up = False
                else:
                    pull_up = None
                dev = DigitalInputDevice(
                    cfg.bcm,
                    pull_up=pull_up,
                    pin_factory=pin_factory,
                )
                on = False

            state = _PinState(
                config=cfg,
                device=dev,
                since=self._start_time,
                on=on,
            )
            self._states[cfg.name] = state

    def _loop_get(self) -> asyncio.AbstractEventLoop:
        if self._loop is None:
            self._loop = asyncio.get_running_loop()
        return self._loop

    async def _ensure_locks(self) -> None:
        """Lazy-create per-pin locks on the running loop."""
        for st in self._states.values():
            if st.lock is None:
                st.lock = asyncio.Lock()

    # ---- Public API ----

    async def get_all_states(self) -> list[dict]:
        """Return state of all pins for GET /pins."""
        await self._ensure_locks()
        result = []
        for name, st in self._states.items():
            on = self._read_on(st)
            result.append(
                {
                    "name": name,
                    "direction": st.config.direction,
                    "on": on,
                    "since": self._format_since(st.since),
                    "label": st.config.label,
                }
            )
        return result

    async def get_state(self, name: str) -> dict:
        """Return state of one pin for GET /pins/{name}."""
        await self._ensure_locks()
        st = self._states.get(name)
        if not st:
            raise KeyError(name)
        on = self._read_on(st)
        return {
            "name": name,
            "direction": st.config.direction,
            "on": on,
            "since": self._format_since(st.since),
            "label": st.config.label,
        }

    async def set_output(self, name: str, on: bool) -> dict:
        """Set an output pin on/off (steady). Returns new state."""
        await self._ensure_locks()
        st = self._states.get(name)
        if not st:
            raise KeyError(name)
        if st.config.direction != "out":
            raise ValueError("pin is an input")

        async with st.lock:
            if st.on == on:
                return await self.get_state(name)

            self._set_device(st, on)
            st.on = on
            now = time.monotonic()
            st.since = now

            # Re-schedule max_on_s auto-off timer
            self._schedule_max_on(st)

            return await self.get_state(name)

    async def pulse_output(self, name: str, pulse_ms: int) -> dict:
        """Turn on for pulse_ms ms, then off. Returns immediate state (on)."""
        await self._ensure_locks()
        st = self._states.get(name)
        if not st:
            raise KeyError(name)
        if st.config.direction != "out":
            raise ValueError("pin is an input")

        async with st.lock:
            self._set_device(st, True)
            st.on = True
            now = time.monotonic()
            st.since = now

            # Cancel any existing timers and schedule new ones
            self._cancel_timers(st)

            # Pulse off timer
            loop = self._loop_get()
            st.pulse_timer = loop.call_later(pulse_ms / 1000.0, lambda: loop.create_task(self._turn_off_pulse(st)))

            # Max-on timer (safety) — earliest wins
            self._schedule_max_on(st)

            return await self.get_state(name)

    async def all_off(self) -> dict:
        """Turn all outputs off and cancel all timers."""
        await self._ensure_locks()
        for st in self._states.values():
            if st.config.direction == "out" and st.on:
                async with st.lock:
                    self._set_device(st, False)
                    st.on = False
                    st.since = time.monotonic()
                self._cancel_timers(st)
        return {"ok": True}

    async def shutdown(self) -> None:
        """Turn all outputs off and cancel all timers; used on SIGTERM/SIGINT."""
        for st in self._states.values():
            if st.config.direction == "out":
                # No lock needed — nothing else is running
                self._set_device(st, False)
                st.on = False
                self._cancel_timers(st)

    # ---- Internal helpers ----

    def _read_on(self, st: _PinState) -> bool:
        """Return logical on/off for the pin."""
        if st.config.direction == "out":
            # DigitalOutputDevice.value is the logical value (True = on)
            return bool(st.device.value)
        # DigitalInputDevice.is_active respects active_high/pull semantics
        return bool(st.device.is_active)

    def _set_device(self, st: _PinState, on: bool) -> None:
        """Drive the physical device."""
        st.device.on() if on else st.device.off()

    def _schedule_max_on(self, st: _PinState) -> None:
        """(Re)schedule the max_on_s safety timer for an output."""
        if st.config.direction != "out" or st.config.max_on_s is None:
            return
        loop = self._loop_get()
        # Cancel any existing max-on timer
        if st.max_on_timer is not None:
            st.max_on_timer.cancel()
        st.max_on_timer = loop.call_later(st.config.max_on_s, lambda: loop.create_task(self._turn_off_max_on(st)))

    def _cancel_timers(self, st: _PinState) -> None:
        for t in (st.max_on_timer, st.pulse_timer):
            if t is not None:
                t.cancel()
        st.max_on_timer = None
        st.pulse_timer = None

    async def _turn_off_max_on(self, st: _PinState) -> None:
        """Callback when max_on_s expires (scheduled as task)."""
        if st.config.direction != "out" or not st.on:
            return
        async with st.lock:
            self._turn_off_internal(st)

    async def _turn_off_pulse(self, st: _PinState) -> None:
        """Callback when pulse_ms expires (scheduled as task)."""
        if st.config.direction != "out" or not st.on:
            return
        async with st.lock:
            self._turn_off_internal(st)

    def _turn_off_internal(self, st: _PinState) -> None:
        """Turn off without acquiring lock (already held)."""
        self._set_device(st, False)
        st.on = False
        st.since = time.monotonic()
        self._cancel_timers(st)

    @staticmethod
    def _format_since(ts: float) -> str:
        """Return ISO 8601 UTC timestamp for the given monotonic time."""
        # ts is time.monotonic() at the moment; map to wall clock
        wall_now = time.time()
        monotonic_now = time.monotonic()
        # Convert by adjusting epoch
        epoch = wall_now - monotonic_now
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch + ts))