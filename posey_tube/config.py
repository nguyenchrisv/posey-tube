"""Configuration loader: parses config.toml and secrets.env, validates pins."""

from __future__ import annotations

import os
import sys
import tomllib
from pathlib import Path

from .pins import PinConfig


class ConfigError(Exception):
    """Raised when configuration is invalid."""

    pass


# Pins reserved on the Pi Zero W (I2C 0/1, UART, ID EEPROM)
_RESERVED_BCM = {0, 1, 2, 3, 14, 15}

# Config and secrets file locations
DEFAULT_CONFIG_PATH = Path("/etc/posey-tube/config.toml")
DEFAULT_SECRETS_PATH = Path("/etc/posey-tube/secrets.env")


def _env_path(env_var: str, default: Path) -> Path:
    """Return path from env var or default."""
    val = os.environ.get(env_var)
    return Path(val) if val else default


def load_config(path: Path | None = None) -> list[PinConfig]:
    """Load and validate ``config.toml``.

    ``path`` may be a Path or None (uses POSEY_TUBE_CONFIG env var or default).
    Raises ConfigError with a clear message on any validation failure.
    """
    cfg_path = _env_path("POSEY_TUBE_CONFIG", DEFAULT_CONFIG_PATH) if path is None else Path(path)
    if not cfg_path.is_file():
        raise ConfigError(f"Config file not found: {cfg_path}")

    try:
        with cfg_path.open("rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"Invalid TOML in {cfg_path}: {e}")

    pins_table = data.get("pins")
    if not isinstance(pins_table, dict):
        raise ConfigError("Missing or invalid [pins] table")

    configs: list[PinConfig] = []
    seen_bcm: set[int] = set()

    for name, table in pins_table.items():
        if not isinstance(table, dict):
            raise ConfigError(f"Pin '{name}': expected a table")

        # Direction
        direction = table.get("direction")
        if direction not in ("out", "in"):
            raise ConfigError(f"Pin '{name}': direction must be 'out' or 'in'")

        # BCM
        bcm = table.get("bcm")
        if not isinstance(bcm, int):
            raise ConfigError(f"Pin '{name}': bcm must be an integer")
        if bcm < 0 or bcm > 27:
            raise ConfigError(f"Pin '{name}': bcm {bcm} out of range 0-27")
        if bcm in _RESERVED_BCM:
            raise ConfigError(f"Pin '{name}': BCM {bcm} is reserved (I2C/UART/EEPROM)")
        if bcm in seen_bcm:
            raise ConfigError(f"Pin '{name}': BCM {bcm} already used")
        seen_bcm.add(bcm)

        # active_high
        active_high = table.get("active_high", True)
        if not isinstance(active_high, bool):
            raise ConfigError(f"Pin '{name}': active_high must be a boolean")

        # max_on_s (required for outputs)
        max_on_s = table.get("max_on_s")
        if direction == "out":
            if not isinstance(max_on_s, int):
                raise ConfigError(f"Pin '{name}': max_on_s is required for outputs and must be an integer")
            if max_on_s < 1 or max_on_s > 86_400:
                raise ConfigError(f"Pin '{name}': max_on_s must be 1..86400")
        else:
            if max_on_s is not None:
                raise ConfigError(f"Pin '{name}': max_on_s is only for outputs")

        # pull (inputs only)
        pull = table.get("pull")
        if direction == "in":
            if pull not in ("up", "down", "none", None):
                raise ConfigError(f"Pin '{name}': pull must be 'up', 'down', 'none' or omitted")
        else:
            if pull is not None:
                raise ConfigError(f"Pin '{name}': pull is only for inputs")

        # label (optional)
        label = table.get("label", "")
        if not isinstance(label, str):
            raise ConfigError(f"Pin '{name}': label must be a string")

        # enabled (optional, default True): start-up arm/disarm state
        enabled = table.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ConfigError(f"Pin '{name}': enabled must be a boolean")

        configs.append(
            PinConfig(
                name=name,
                bcm=bcm,
                direction=direction,
                active_high=active_high,
                max_on_s=max_on_s,
                pull=pull if direction == "in" else None,
                label=label,
                enabled=enabled,
            )
        )

    if not configs:
        raise ConfigError("No pins configured")

    return configs


def load_token(path: Path | None = None) -> str:
    """Load the API token from ``secrets.env`` (``POSEY_TUBE_TOKEN=...``)."""
    sec_path = _env_path("POSEY_TUBE_SECRETS", DEFAULT_SECRETS_PATH) if path is None else Path(path)
    if not sec_path.is_file():
        raise ConfigError(f"Secrets file not found: {sec_path}")

    token = None
    with sec_path.open() as f:
        for line in f:
            line = line.strip()
            if line.startswith("POSEY_TUBE_TOKEN="):
                token = line.split("=", 1)[1].strip()
                # Allow optional surrounding quotes
                if (token.startswith('"') and token.endswith('"')) or (
                    token.startswith("'") and token.endswith("'")
                ):
                    token = token[1:-1]
                break

    if not token:
        raise ConfigError(f"POSEY_TUBE_TOKEN not set in {sec_path}")
    return token


def _main():
    # Allow: python -m posey_tube.config [path]  -> prints parsed config for debugging
    if len(sys.argv) > 1:
        try:
            configs = load_config(sys.argv[1])
            for c in configs:
                print(c)
        except ConfigError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"UNEXPECTED: {e}", file=sys.stderr)
            sys.exit(2)


if __name__ == "__main__":
    _main()