"""Persisted runtime state: disabled-pin set, written atomically.

The state file survives reboots so a disabled (disarmed) pin is not
silently re-armed. Missing or corrupt file → fall back to config
defaults with a warning.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path

_LOG = logging.getLogger(__name__)

DEFAULT_STATE_PATH = Path("/var/lib/posey-tube/state.json")


def _env_path(env_var: str, default: Path) -> Path:
    val = os.environ.get(env_var)
    return Path(val) if val else default


def state_path(path: Path | None = None) -> Path:
    """Resolve the state file path (param > env > default)."""
    if path is not None:
        return Path(path)
    return _env_path("POSEY_TUBE_STATE", DEFAULT_STATE_PATH)


def load_disabled(path: Path | None = None) -> set[str] | None:
    """Load the persisted disabled-pin set.

    Returns None when the file is missing or corrupt (caller falls back
    to config defaults and logs a warning).
    """
    p = state_path(path)
    if not p.is_file():
        return None
    try:
        with p.open() as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        _LOG.warning("Corrupt state file %s (%s); using config defaults", p, e)
        return None

    if not isinstance(data, dict) or not isinstance(data.get("disabled"), list):
        _LOG.warning("State file %s has unexpected shape; using config defaults", p)
        return None

    names = data["disabled"]
    if not all(isinstance(n, str) for n in names):
        _LOG.warning("State file %s has invalid pin names; using config defaults", p)
        return None
    return set(names)


def save_disabled(disabled: set[str], path: Path | None = None) -> None:
    """Persist the disabled set atomically (tmp file + os.replace).

    Read-modify-write: other top-level sections in the state file (e.g.
    future toggle values from #8) are preserved.
    """
    p = state_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    # Preserve unknown sections; start fresh on corrupt file
    existing: dict = {}
    if p.is_file():
        try:
            with p.open() as f:
                data = json.load(f)
            if isinstance(data, dict):
                existing = data
        except (json.JSONDecodeError, OSError):
            pass
    existing["disabled"] = sorted(disabled)
    payload = json.dumps(existing, indent=2)

    # Atomic write: same directory, fsync, then rename over the target
    fd, tmp_name = tempfile.mkstemp(dir=str(p.parent), prefix=".state-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, p)
    except OSError:
        # Best effort cleanup; state write failure is logged, not fatal
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise