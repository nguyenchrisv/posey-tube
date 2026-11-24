"""Pin model: name, BCM number, direction, active_high, max_on_s, pull, label."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PinConfig:
    """One configured GPIO pin.

    ``direction`` is ``"out"`` or ``"in"``. ``active_high=False`` means the
    pin is driven low when logically on (common for relay boards).
    ``max_on_s`` is required for outputs: the auto-off safety timer.
    ``pull`` is only meaningful for inputs: ``"up"``, ``"down"`` or ``"none"``.
    """

    name: str
    bcm: int
    direction: str
    active_high: bool = True
    max_on_s: int | None = None
    pull: str | None = None
    label: str = ""

    @property
    def is_output(self) -> bool:
        return self.direction == "out"
